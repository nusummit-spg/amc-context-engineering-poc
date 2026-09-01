# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
amfi_member_portal.py
======================
Channel C: Watch the member portal inbox directory for new PDFs.
When a file appears, ingest it through the gateway automatically.

Requirements:
  - watchdog (file system event monitoring)
  - Debouncing for in-progress writes (2-second wait)
  - Magic byte validation (PDF header check)
  - Logging to logs/member_portal_log.jsonl
"""
from __future__ import annotations
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # Provide stub for when watchdog is not available
    class FileSystemEventHandler:  # type: ignore
        pass
    class Observer:  # type: ignore
        pass

from app.engine import config
from app.engine.ingestion_gateway import (
    IngestNamespace,
    IngestRequest,
    IngestionChannel,
    process_ingest,
)


logger = logging.getLogger(__name__)
_MEMBER_PORTAL_LOG = config.LOG_DIR / "member_portal_log.jsonl"


def _is_pdf(file_path: Path) -> bool:
    """Check if file has PDF magic bytes."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(4)
        return header == b"%PDF"
    except Exception:
        return False


def _is_file_ready(file_path: Path, max_wait: float = 2.0) -> bool:
    """
    Check if file is ready for ingestion (not being written).
    Waits up to max_wait seconds for file size to stabilize.
    """
    try:
        initial_size = file_path.stat().st_size
        time.sleep(0.2)  # Brief wait
        final_size = file_path.stat().st_size
        
        # If size changed, file is still being written
        if initial_size != final_size:
            remaining = max_wait - 0.2
            if remaining > 0:
                time.sleep(remaining)
                return _is_file_ready(file_path, remaining - 0.2)
            return False
        
        return True
    except Exception:
        return False


def _log_ingest_event(event_type: str, file_path: Path, result: Any) -> None:
    """Log ingestion event to JSONL for audit trail."""
    record = {
        "timestamp": time.time(),
        "event_type": event_type,
        "file": file_path.name,
        "result": result.to_dict() if hasattr(result, "to_dict") else str(result),
    }
    with open(_MEMBER_PORTAL_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


class MemberPortalFileHandler(FileSystemEventHandler):
    """Handles file system events in the member portal inbox."""
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        logger.info(f"[member_portal] File detected: {file_path.name}")
        
        # Wait for write to complete
        if not _is_file_ready(file_path):
            logger.warning(f"[member_portal] Timeout waiting for file ready: {file_path.name}")
            _log_ingest_event("file_not_ready", file_path, None)
            return
        
        # Validate PDF
        if not _is_pdf(file_path):
            logger.warning(f"[member_portal] Not a valid PDF: {file_path.name}")
            _log_ingest_event("invalid_pdf", file_path, None)
            return
        
        # Ingest
        try:
            request = IngestRequest(
                file_path=file_path,
                source_channel=IngestionChannel.MEMBER_PORTAL,
                namespace=IngestNamespace.MEMBER_DOCUMENT,
                source_url=f"file://{file_path.name}",
                ingested_by="member_portal_watcher",
                metadata={"portal_inbox": True}
            )
            result = process_ingest(request)
            
            if result.success:
                logger.info(f"[member_portal] Ingested: {file_path.name}")
            else:
                logger.info(
                    f"[member_portal] Ingest rejected: {file_path.name} "
                    f"({result.reason})"
                )
            
            _log_ingest_event("ingest_attempt", file_path, result)
        except Exception as e:
            logger.error(f"[member_portal] Error ingesting {file_path.name}: {e}")
            _log_ingest_event("error", file_path, str(e))


class MemberPortalWatcher:
    """Background watcher for member portal inbox."""
    
    def __init__(self, inbox_dir: Path = config.MEMBER_PORTAL_INBOX):
        if not WATCHDOG_AVAILABLE:
            raise ImportError("watchdog library required for MemberPortalWatcher")
        
        self.inbox_dir = inbox_dir
        self.observer = Observer()
        self.event_handler = MemberPortalFileHandler()
    
    def start(self) -> None:
        """Start watching the inbox directory."""
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(self.event_handler, str(self.inbox_dir), recursive=False)
        self.observer.start()
        logger.info(f"[member_portal] Watcher started on {self.inbox_dir}")
    
    def stop(self) -> None:
        """Stop watching."""
        self.observer.stop()
        self.observer.join(timeout=5)
        logger.info("[member_portal] Watcher stopped")
    
    def is_alive(self) -> bool:
        """Check if watcher is still running."""
        return self.observer.is_alive()


def get_member_portal_log() -> list[Dict[str, Any]]:
    """Read and parse member portal audit log."""
    events = []
    if _MEMBER_PORTAL_LOG.exists():
        with open(_MEMBER_PORTAL_LOG, "r") as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def get_member_portal_stats() -> Dict[str, Any]:
    """Get statistics on member portal ingestions."""
    events = get_member_portal_log()
    
    stats = {
        "total_events": len(events),
        "ingest_attempts": sum(1 for e in events if e.get("event_type") == "ingest_attempt"),
        "successes": sum(
            1 for e in events 
            if e.get("event_type") == "ingest_attempt" 
            and e.get("result", {}).get("success") is True
        ),
        "duplicates": sum(
            1 for e in events 
            if e.get("event_type") == "ingest_attempt" 
            and e.get("result", {}).get("was_duplicate") is True
        ),
        "errors": sum(1 for e in events if e.get("event_type") == "error"),
    }
    return stats


if __name__ == "__main__":
    if not WATCHDOG_AVAILABLE:
        print("Please install watchdog: pip install watchdog")
    else:
        watcher = MemberPortalWatcher()
        watcher.start()
        try:
            import signal
            signal.pause()
        except KeyboardInterrupt:
            watcher.stop()
            print("Watcher stopped.")
