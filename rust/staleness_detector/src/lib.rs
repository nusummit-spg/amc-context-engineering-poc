// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
//
// Author: NuSummit Developers
// ===========================================================================

//! Staleness Drift Detection - Rust Implementation
//! High-performance async HTTP-based document availability checking

use std::ffi::{CStr, CString};
use std::os::raw::c_char;

mod checker;
mod types;

use checker::StalenessDetector;
use types::{CDriftReport, CDocumentRecord, DocumentRecord, DriftReport};

pub const VERSION: &str = "0.1.0";

/// C-compatible struct for list of documents
#[repr(C)]
pub struct DocumentList {
    pub records: *const CDocumentRecord,
    pub count: usize,
}

/// Check documents for staleness (C FFI entry point)
/// Returns pointer to DriftReport allocated on Rust side
#[no_mangle]
pub extern "C" fn check_documents_c(
    docs: *const CDocumentRecord,
    count: usize,
    concurrency: usize,
) -> *mut CDriftReport {
    if docs.is_null() || count == 0 {
        return std::ptr::null_mut();
    }

    // Convert C records to Rust records
    let mut records = vec![];
    unsafe {
        let docs_slice = std::slice::from_raw_parts(docs, count);
        for cdoc in docs_slice {
            let filename = if !cdoc.filename_ptr.is_null() {
                CStr::from_ptr(cdoc.filename_ptr)
                    .to_str()
                    .unwrap_or("unknown")
                    .to_string()
            } else {
                "unknown".to_string()
            };

            let source_url = if !cdoc.source_url_ptr.is_null() {
                CStr::from_ptr(cdoc.source_url_ptr)
                    .to_str()
                    .unwrap_or("")
                    .to_string()
            } else {
                String::new()
            };

            let document_hash = if !cdoc.document_hash_ptr.is_null() {
                CStr::from_ptr(cdoc.document_hash_ptr)
                    .to_str()
                    .unwrap_or("")
                    .to_string()
            } else {
                String::new()
            };

            records.push(DocumentRecord {
                document_hash,
                filename,
                source_channel: "sebi_rss".to_string(),
                source_url,
                ingestion_timestamp: chrono::Utc::now().to_rfc3339(),
                namespace: "regulatory".to_string(),
            });
        }
    }

    // Run drift check
    let report = StalenessDetector::check_documents(
        records,
        if concurrency > 0 { Some(concurrency) } else { None },
    );

    // Convert to C struct
    let c_report = convert_drift_report_to_c(report);
    Box::into_raw(Box::new(c_report))
}

/// Free DriftReport allocated by Rust
#[no_mangle]
pub extern "C" fn free_drift_report(report: *mut CDriftReport) {
    if !report.is_null() {
        unsafe {
            let r = Box::from_raw(report);

            // Free all allocated strings
            if !r.checked_at_ptr.is_null() {
                let _ = CString::from_raw(r.checked_at_ptr as *mut c_char);
            }

            // Free not_found_files array
            if !r.not_found_files_ptr.is_null() && r.not_found_files_count > 0 {
                let files =
                    std::slice::from_raw_parts(r.not_found_files_ptr, r.not_found_files_count);
                for file_ptr in files {
                    if !file_ptr.is_null() {
                        let _ = CString::from_raw(*file_ptr as *mut c_char);
                    }
                }
                let _ = Box::from_raw(r.not_found_files_ptr as *mut *const c_char);
            }
        }
    }
}

/// Convert Rust DriftReport to C struct
fn convert_drift_report_to_c(report: DriftReport) -> CDriftReport {
    let checked_at = CString::new(report.checked_at).unwrap_or_else(|_| CString::new("").unwrap());
    let checked_at_ptr = checked_at.into_raw() as *const c_char;

    // Convert not_found_filenames to C array
    let mut not_found_files_ptrs = vec![];
    for filename in &report.not_found_filenames {
        if let Ok(c_str) = CString::new(filename.clone()) {
            not_found_files_ptrs.push(c_str.into_raw() as *const c_char);
        }
    }

    let not_found_files_ptr = if !not_found_files_ptrs.is_empty() {
        Box::leak(not_found_files_ptrs.into_boxed_slice()) as *const _ as *const *const c_char
    } else {
        std::ptr::null()
    };

    CDriftReport {
        checked_count: report.checked_count,
        available_count: report.available_count,
        not_found_count: report.not_found_count,
        error_count: report.error_count,
        drifted_count: report.drifted_filenames.len(),
        not_found_files_ptr,
        not_found_files_count: report.not_found_filenames.len(),
        checked_at_ptr,
        elapsed_ms: report.elapsed_ms,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_version() {
        assert_eq!(VERSION, "0.1.0");
    }

    #[test]
    fn test_empty_check() {
        let report = unsafe { check_documents_c(std::ptr::null(), 0, 0) };
        assert!(report.is_null());
    }
}
