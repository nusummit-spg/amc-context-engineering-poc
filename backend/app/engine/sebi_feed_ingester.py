# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
sebi_feed_ingester.py
=======================
Channel A: Poll SEBI RSS feed for regulatory circulars.
- Detect new/updated entries
- Download PDFs with rate limiting
- Detect supersessions via title parsing
- Log all activity

Rate limits:
  - 1 RSS poll per 5 minutes
  - 3 PDF downloads per minute
  
Legal gate: Historical backfill waits for Phase 0 legal permission letter.
Live feed polling can proceed without special approval.
"""
from __future__ import annotations
import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import feedparser
import requests

from app.engine import config
from app.engine.ingestion_gateway import (
    IngestNamespace,
    IngestRequest,
    IngestionChannel,
    process_ingest,
)


logger = logging.getLogger(__name__)
_SEBI_POLL_LOG = config.LOG_DIR / "sebi_poll_log.jsonl"
_SEBI_ENTRY_HASH_FILE = config.LOG_DIR / "sebi_entry_hashes.txt"


class RateLimiter:
    """Token-bucket rate limiter."""
    
    def __init__(self, rate_per_minute: float):
        self.rate_per_minute = rate_per_minute
        self.tokens = rate_per_minute
        self.last_refill = time.time()
    
    def acquire(self, tokens: float = 1.0, blocking: bool = True) -> bool:
        """
        Try to acquire tokens. If blocking=True, wait if needed.
        Returns True if tokens acquired, False if rate limit exceeded (non-blocking).
        """
        now = time.time()
        elapsed = now - self.last_refill
        
        # Refill tokens
        refill_rate = self.rate_per_minute / 60.0
        self.tokens = min(self.rate_per_minute, self.tokens + elapsed * refill_rate)
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        
        if blocking:
            wait_time = (tokens - self.tokens) / refill_rate
            time.sleep(wait_time)
            self.tokens -= tokens
            return True
        
        return False


class SEBIFeedIngester:
    """Ingester for SEBI regulatory feed."""
    
    def __init__(
        self,
        rss_url: str = config.SEBI_RSS_URL,
        poll_interval_minutes: int = config.SEBI_POLL_INTERVAL_MINUTES,
        download_rate_limit: int = config.SEBI_DOWNLOAD_RATE_LIMIT
    ):
        self.rss_url = rss_url
        self.poll_interval_minutes = poll_interval_minutes
        self.download_rate_limiter = RateLimiter(download_rate_limit)
        self.session = requests.Session()
        self._known_hashes = self._load_known_hashes()
    
    def _load_known_hashes(self) -> set[str]:
        """Load set of known entry hashes to avoid reprocessing."""
        if _SEBI_ENTRY_HASH_FILE.exists():
            return set(_SEBI_ENTRY_HASH_FILE.read_text().strip().split("\n"))
        return set()
    
    def _save_entry_hash(self, entry_hash: str) -> None:
        """Record a new entry hash."""
        with open(_SEBI_ENTRY_HASH_FILE, "a") as f:
            f.write(entry_hash + "\n")
        self._known_hashes.add(entry_hash)
    
    def poll_sebi_rss(self) -> Dict[str, Any]:
        """
        Poll SEBI RSS feed and return results.
        
        Returns:
            Report with new_entries, supersessions, downloaded_count, errors
        """
        logger.info(f"[sebi] Polling RSS feed: {self.rss_url}")
        
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_entries": [],
            "supersessions_detected": [],
            "downloaded_count": 0,
            "errors": [],
        }
        
        try:
            feed = feedparser.parse(self.rss_url)
        except Exception as e:
            logger.error(f"[sebi] Failed to parse RSS: {e}")
            report["errors"].append(str(e))
            return report
        
        if feed.bozo:
            logger.warning(f"[sebi] RSS parsing warnings: {feed.bozo_exception}")
        
        for entry in feed.entries[:20]:  # Limit to recent 20
            entry_hash = hashlib.sha256(
                f"{entry.title}{entry.published}".encode()
            ).hexdigest()
            
            # Skip if we've already processed this entry
            if entry_hash in self._known_hashes:
                continue
            
            logger.info(f"[sebi] New entry: {entry.title}")
            report["new_entries"].append({
                "title": entry.title,
                "published": entry.published,
                "link": entry.link,
            })
            self._save_entry_hash(entry_hash)
            
            # Detect supersession from title
            supersession = self.detect_supersession_from_title(entry.title)
            if supersession:
                logger.info(f"[sebi] Supersession detected: {supersession}")
                report["supersessions_detected"].append(supersession)
            
            # Download PDF
            if entry.link:
                try:
                    self.download_rate_limiter.acquire(blocking=True)
                    pdf_path = self.download_circular_pdf(entry.link)
                    if pdf_path:
                        report["downloaded_count"] += 1
                except Exception as e:
                    logger.error(f"[sebi] Failed to download {entry.link}: {e}")
                    report["errors"].append(str(e))
        
        logger.info(f"[sebi] Poll complete: {report['downloaded_count']} new PDFs")
        return report
    
    def detect_supersession_from_title(self, title: str) -> Optional[Dict[str, str]]:
        """
        Parse title for supersession keywords.
        
        Examples:
          - "Circular 123 (Superseded by Circular 456)"
          - "Amendment to Master Circular XYZ"
          
        Returns:
            dict with {old: ..., new: ...} if supersession detected, else None
        """
        # Pattern 1: "X (Superseded by Y)"
        m = re.search(
            r"(?:Circular|Master Circular)[\s-]*(\d+)\s*\(.*Superseded\s+by\s*(?:Circular|Master Circular)[\s-]*(\d+)",
            title,
            re.IGNORECASE
        )
        if m:
            return {"old": m.group(1), "new": m.group(2), "reason": "superseded"}
        
        # Pattern 2: "Amendment to X"
        m = re.search(
            r"(?:Amendment|Modification).*?(?:Circular|Master Circular)[\s-]*(\d+)",
            title,
            re.IGNORECASE
        )
        if m:
            return {"old": m.group(1), "new": None, "reason": "amended"}
        
        return None
    
    def download_circular_pdf(self, url: str, dest_dir: Path = None) -> Optional[Path]:
        """
        Download a circular PDF from the given URL.
        
        Args:
            url: direct PDF URL or HTML page containing PDF link
            dest_dir: directory to save PDF (default: logs/sebi_temp)
            
        Returns:
            Path to saved PDF, or None if failed
        """
        dest_dir = dest_dir or (config.LOG_DIR / "sebi_temp")
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            logger.info(f"[sebi] Downloading: {url}")
            resp = self.session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            
            # Extract filename from URL or Content-Disposition
            filename = url.split("/")[-1]
            if "content-disposition" in resp.headers:
                import re as _re
                m = _re.search(
                    r'filename="(.+?)"',
                    resp.headers["content-disposition"]
                )
                if m:
                    filename = m.group(1)
            
            # Ensure .pdf extension
            if not filename.lower().endswith(".pdf"):
                filename = filename.split("?")[0]  # Strip query params
                if not filename.endswith(".pdf"):
                    filename = filename + ".pdf"
            
            pdf_path = dest_dir / filename
            pdf_path.write_bytes(resp.content)
            
            logger.info(f"[sebi] Downloaded: {pdf_path}")
            
            # Ingest through gateway
            req = IngestRequest(
                file_path=pdf_path,
                source_channel=IngestionChannel.SEBI_RSS,
                namespace=IngestNamespace.SEBI_CIRCULAR,
                source_url=url,
                ingested_by="sebi_ingester",
                metadata={"sebi_pdf": True}
            )
            result = process_ingest(req)
            
            if result.success:
                logger.info(f"[sebi] Ingested PDF: {filename}")
                return pdf_path
            else:
                logger.info(f"[sebi] PDF ingest rejected: {result.reason}")
                # Return path even if rejected (may be duplicate)
                return pdf_path
        
        except Exception as e:
            logger.error(f"[sebi] Download failed: {e}")
            return None
    
    def run_daily_sebi_poll(self) -> Dict[str, Any]:
        """
        Run a daily SEBI poll cycle.
        Can be called by the pipeline scheduler.
        """
        return self.poll_sebi_rss()


def get_sebi_poll_log() -> list[Dict[str, Any]]:
    """Read SEBI poll log."""
    import json
    events = []
    if _SEBI_POLL_LOG.exists():
        with open(_SEBI_POLL_LOG, "r") as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


if __name__ == "__main__":
    ingester = SEBIFeedIngester()
    report = ingester.run_daily_sebi_poll()
    print(report)
