// ==========================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
//
// Author: NuSummit Developers
//
// ==========================================================

// ===========================================================================
// Data structures for staleness detection
// ===========================================================================

use serde::{Deserialize, Serialize};
use std::os::raw::c_char;

/// Represents a document record to check
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentRecord {
    pub document_hash: String,
    pub filename: String,
    pub source_channel: String,
    pub source_url: String,
    pub ingestion_timestamp: String,
    pub namespace: String,
}

/// Result of checking a single document
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckResult {
    pub filename: String,
    pub source_url: String,
    pub status_code: u16,
    pub is_available: bool,
    pub is_drifted: bool,
    pub error_message: Option<String>,
    pub last_modified: Option<String>,
}

/// Overall drift report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriftReport {
    pub checked_count: usize,
    pub available_count: usize,
    pub not_found_count: usize,
    pub error_count: usize,
    pub drifted_filenames: Vec<String>,
    pub not_found_filenames: Vec<String>,
    pub error_filenames: Vec<String>,
    pub checked_at: String,
    pub elapsed_ms: u64,
}

/// C-compatible struct for FFI
#[repr(C)]
pub struct CDocumentRecord {
    pub filename_ptr: *const c_char,
    pub source_url_ptr: *const c_char,
    pub document_hash_ptr: *const c_char,
}

/// C-compatible drift report for FFI
#[repr(C)]
pub struct CDriftReport {
    pub checked_count: usize,
    pub available_count: usize,
    pub not_found_count: usize,
    pub error_count: usize,
    pub drifted_count: usize,
    pub not_found_files_ptr: *const *const c_char,
    pub not_found_files_count: usize,
    pub checked_at_ptr: *const c_char,
    pub elapsed_ms: u64,
}

impl DriftReport {
    /// Create empty report
    pub fn empty() -> Self {
        Self {
            checked_count: 0,
            available_count: 0,
            not_found_count: 0,
            error_count: 0,
            drifted_filenames: vec![],
            not_found_filenames: vec![],
            error_filenames: vec![],
            checked_at: chrono::Utc::now().to_rfc3339(),
            elapsed_ms: 0,
        }
    }

    /// Convert to JSON string
    pub fn to_json(&self) -> String {
        serde_json::to_string(self).unwrap_or_else(|_| "{}".to_string())
    }
}

impl CheckResult {
    /// Create an error result
    pub fn error(filename: String, url: String, error: String) -> Self {
        Self {
            filename,
            source_url: url,
            status_code: 0,
            is_available: false,
            is_drifted: false,
            error_message: Some(error),
            last_modified: None,
        }
    }

    /// Create a not-found result (404)
    pub fn not_found(filename: String, url: String) -> Self {
        Self {
            filename,
            source_url: url,
            status_code: 404,
            is_available: false,
            is_drifted: false,
            error_message: None,
            last_modified: None,
        }
    }

    /// Create a success result
    pub fn ok(filename: String, url: String, status: u16, last_mod: Option<String>) -> Self {
        let is_available = status == 200;
        Self {
            filename,
            source_url: url,
            status_code: status,
            is_available,
            is_drifted: false,
            error_message: None,
            last_modified: last_mod,
        }
    }
}
