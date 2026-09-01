// ==========================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
//
// Author: NuSummit Developers
//
// ==========================================================

// ===========================================================================
// Core staleness detection logic with thread pooling
// ===========================================================================

use crate::types::{CheckResult, DocumentRecord, DriftReport};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Instant;

const USER_AGENT: &str = "AMC-ContextEngineering-StalenessCheck/1.0";
const HTTP_TIMEOUT_SECS: u64 = 10;

/// Main detector struct
pub struct StalenessDetector;

impl StalenessDetector {
    /// Run drift check on documents (using thread pool for parallelism)
    pub fn check_documents(
        records: Vec<DocumentRecord>,
        concurrency: Option<usize>,
    ) -> DriftReport {
        let start = Instant::now();
        let concurrency = concurrency.unwrap_or(8);

        // Use thread pool for concurrent HTTP requests
        let pool = threadpool::ThreadPool::new(concurrency);
        let results = Arc::new(Mutex::new(vec![]));

        for record in records {
            let results = results.clone();
            pool.execute(move || {
                let result = Self::check_single_document(&record);
                results.lock().unwrap().push(result);
            });
        }

        pool.join();
        let elapsed = start.elapsed().as_millis() as u64;

        // Aggregate results
        let checked_results = results.lock().unwrap().clone();
        Self::aggregate_results(checked_results, elapsed)
    }

    /// Check a single document using blocking HTTP
    fn check_single_document(record: &DocumentRecord) -> CheckResult {
        use curl::easy::Easy;

        // Skip invalid URLs
        if !record.source_url.starts_with("http") {
            return CheckResult::error(
                record.filename.clone(),
                record.source_url.clone(),
                "Invalid URL".to_string(),
            );
        }

        let mut easy = match Easy::new() {
            Ok(e) => e,
            Err(err) => {
                return CheckResult::error(
                    record.filename.clone(),
                    record.source_url.clone(),
                    format!("Failed to create HTTP client: {}", err),
                )
            }
        };

        // Configure HEAD request
        let _ = easy.custom_request("HEAD");
        let _ = easy.url(&record.source_url);
        let _ = easy.useragent(USER_AGENT);
        let _ = easy.timeout(std::time::Duration::from_secs(HTTP_TIMEOUT_SECS));
        let _ = easy.follow_location(true);

        // Perform request
        let mut headers = vec![];
        {
            let mut header_transfer = easy.transfer();
            let _ = header_transfer.header_function(|header| {
                headers.push(header.to_vec());
                true
            });
            match header_transfer.perform() {
                Ok(_) => {}
                Err(err) => {
                    return CheckResult::error(
                        record.filename.clone(),
                        record.source_url.clone(),
                        format!("HTTP error: {}", err),
                    )
                }
            }
        }

        // Get status code
        let status = match easy.response_code() {
            Ok(code) => code as u16,
            Err(err) => {
                return CheckResult::error(
                    record.filename.clone(),
                    record.source_url.clone(),
                    format!("Failed to get response code: {}", err),
                )
            }
        };

        // Extract Last-Modified header
        let last_modified = headers
            .iter()
            .find_map(|h| {
                let header_str = String::from_utf8_lossy(h);
                if header_str.starts_with("Last-Modified:") {
                    Some(
                        header_str
                            .strip_prefix("Last-Modified:")?
                            .trim()
                            .to_string(),
                    )
                } else {
                    None
                }
            });

        match status {
            200 => CheckResult::ok(
                record.filename.clone(),
                record.source_url.clone(),
                status,
                last_modified,
            ),
            404 => CheckResult::not_found(record.filename.clone(), record.source_url.clone()),
            _ => CheckResult::ok(
                record.filename.clone(),
                record.source_url.clone(),
                status,
                last_modified,
            ),
        }
    }

    /// Aggregate individual results into report
    fn aggregate_results(results: Vec<CheckResult>, elapsed_ms: u64) -> DriftReport {
        let mut report = DriftReport::empty();
        report.elapsed_ms = elapsed_ms;

        for result in results {
            report.checked_count += 1;

            if let Some(ref error) = result.error_message {
                report.error_count += 1;
                report.error_filenames.push(result.filename);
            } else if result.status_code == 404 {
                report.not_found_count += 1;
                report.not_found_filenames.push(result.filename);
            } else if result.is_available {
                report.available_count += 1;
            }
        }

        report.checked_at = chrono::Utc::now().to_rfc3339();
        report
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_check_result_creation() {
        let result = CheckResult::ok(
            "test.pdf".to_string(),
            "https://example.com/test.pdf".to_string(),
            200,
            None,
        );
        assert_eq!(result.status_code, 200);
        assert!(result.is_available);
    }
}
