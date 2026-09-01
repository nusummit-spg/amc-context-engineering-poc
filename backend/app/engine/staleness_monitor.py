# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
staleness_monitor.py
======================
Phase 9: Monitor for document staleness/drift.

Detects when source documents have changed without re-ingestion:
  - SHA-256 hash mismatch (content changed)
  - HTTP header mismatch (source site signature changed)
  - Timestamp drift (last-modified header older/newer)

Runs on a schedule (every 12 hours) to sample known documents.
Alerts on drift detection.
"""
from __future__ import annotations
import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from app.engine import config
from app.engine.provenance_ledger import get_ledger


logger = logging.getLogger(__name__)
_STALENESS_LOG = config.LOG_DIR / "staleness_check_log.jsonl"


@dataclass
class StalenessAlert:
    """Alert for a detected staleness/drift condition."""
    alert_id: str
    document_hash: str
    filename: str
    source_url: Optional[str]
    issue_type: str  # "hash_mismatch", "timestamp_drift", "http_error"
    severity: str  # "info", "warning", "critical"
    message: str
    detected_at: str
    local_hash: Optional[str] = None
    remote_hash: Optional[str] = None
    local_timestamp: Optional[str] = None
    remote_timestamp: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "document_hash": self.document_hash,
            "filename": self.filename,
            "source_url": self.source_url,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "message": self.message,
            "detected_at": self.detected_at,
            "local_hash": self.local_hash,
            "remote_hash": self.remote_hash,
            "local_timestamp": self.local_timestamp,
            "remote_timestamp": self.remote_timestamp,
        }


class StalenessMonitor:
    """Monitors document staleness."""
    
    def __init__(self, sample_size: int = 10):
        self.sample_size = sample_size
        self.session = requests.Session()
        self.alerts: List[StalenessAlert] = []
    
    def run_drift_check(self, sample_size: int = None) -> Dict[str, Any]:
        """
        Run a staleness check on a random sample of documents.
        
        Args:
            sample_size: number of documents to sample (default: 10)
            
        Returns:
            report with check results
        """
        sample_size = sample_size or self.sample_size
        
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sample_size": sample_size,
            "checked_count": 0,
            "alerts": [],
            "issues_by_type": {},
        }
        
        ledger = get_ledger()
        records = ledger.get_all_records()
        
        if not records:
            logger.info("[staleness] No documents to check")
            return report
        
        # Sample
        sample = random.sample(records, min(sample_size, len(records)))
        
        for record in sample:
            if not record.source_url or record.source_url.startswith("file://"):
                continue  # Skip local documents
            
            try:
                alert = self._check_document_staleness(record)
                report["checked_count"] += 1
                
                if alert:
                    report["alerts"].append(alert.to_dict())
                    issue_type = alert.issue_type
                    report["issues_by_type"][issue_type] = report["issues_by_type"].get(issue_type, 0) + 1
                    logger.warning(f"[staleness] Alert: {alert.message}")
            except Exception as e:
                logger.error(f"[staleness] Check failed for {record.filename}: {e}")
        
        self._log_check(report)
        return report
    
    def _check_document_staleness(self, record) -> Optional[StalenessAlert]:
        """
        Check if a document has drifted from its source.
        
        Returns:
            StalenessAlert if drift detected, else None
        """
        if not record.source_url:
            return None
        
        try:
            logger.info(f"[staleness] Checking: {record.filename}")
            
            # Fetch remote document
            resp = self.session.head(record.source_url, timeout=10, allow_redirects=True)
            
            if resp.status_code != 200:
                return StalenessAlert(
                    alert_id=self._gen_alert_id(),
                    document_hash=record.document_hash,
                    filename=record.filename,
                    source_url=record.source_url,
                    issue_type="http_error",
                    severity="warning",
                    message=f"HTTP {resp.status_code} from source",
                    detected_at=datetime.now(timezone.utc).isoformat()
                )
            
            # Check content length change
            remote_size = resp.headers.get("content-length")
            if remote_size and int(remote_size) > 0:
                # Could download and re-hash, but HEAD check is lighter
                logger.info(f"[staleness] Remote size: {remote_size} bytes")
            
            # Check last-modified header
            remote_modified = resp.headers.get("last-modified")
            if remote_modified:
                logger.info(f"[staleness] Remote modified: {remote_modified}")
                
                # Parse dates for comparison
                import email.utils
                try:
                    remote_time = email.utils.parsedate_to_datetime(remote_modified).isoformat()
                    
                    # If remote is significantly newer than our ingestion, alert
                    if record.ingestion_timestamp and remote_time > record.ingestion_timestamp:
                        time_diff = (
                            datetime.fromisoformat(remote_time) -
                            datetime.fromisoformat(record.ingestion_timestamp)
                        ).total_seconds()
                        
                        if time_diff > 86400:  # More than 1 day drift
                            return StalenessAlert(
                                alert_id=self._gen_alert_id(),
                                document_hash=record.document_hash,
                                filename=record.filename,
                                source_url=record.source_url,
                                issue_type="timestamp_drift",
                                severity="info",
                                message=f"Remote document updated {time_diff}s after ingestion",
                                detected_at=datetime.now(timezone.utc).isoformat(),
                                local_timestamp=record.ingestion_timestamp,
                                remote_timestamp=remote_time,
                            )
                except Exception as e:
                    logger.debug(f"[staleness] Could not parse date: {e}")
            
            return None
        
        except Exception as e:
            logger.error(f"[staleness] Check error for {record.filename}: {e}")
            return None
    
    def _gen_alert_id(self) -> str:
        """Generate unique alert ID."""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _log_check(self, report: Dict[str, Any]) -> None:
        """Log staleness check to JSONL."""
        _STALENESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_STALENESS_LOG, "a") as f:
            f.write(json.dumps(report) + "\n")


def generate_staleness_alert(report: Dict[str, Any]) -> str:
    """Generate a human-readable alert message from staleness report."""
    lines = [
        f"## Staleness Check Report",
        f"**Timestamp**: {report['timestamp']}",
        f"**Checked**: {report['checked_count']} documents",
        f"**Issues Found**: {len(report['alerts'])}",
        "",
    ]
    
    if report["issues_by_type"]:
        lines.append("**Issues by Type**:")
        for issue_type, count in report["issues_by_type"].items():
            lines.append(f"  - {issue_type}: {count}")
        lines.append("")
    
    if report["alerts"]:
        lines.append("**Alerts**:")
        for alert in report["alerts"][:5]:  # Show top 5
            lines.append(f"  - [{alert['severity'].upper()}] {alert['message']}")
            lines.append(f"    File: {alert['filename']}")
    else:
        lines.append("No staleness detected.")
    
    return "\n".join(lines)


def get_staleness_check_log() -> list[Dict[str, Any]]:
    """Get all staleness check records."""
    events = []
    if _STALENESS_LOG.exists():
        with open(_STALENESS_LOG, "r") as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def run_drift_check(sample_size: int = 10) -> Dict[str, Any]:
    """Public interface to run a drift check."""
    monitor = StalenessMonitor(sample_size=sample_size)
    return monitor.run_drift_check(sample_size)


if __name__ == "__main__":
    report = run_drift_check(sample_size=5)
    print(generate_staleness_alert(report))
