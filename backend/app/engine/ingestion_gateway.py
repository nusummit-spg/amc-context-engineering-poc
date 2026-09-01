# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
ingestion_gateway.py
======================
Central ingestion point for all acquisition channels.
Handles:
  - Deduplication by content hash (prevents duplicate indexing)
  - Namespace routing (keeps different document types separate)
  - Provenance record creation
  - Connection to downstream build_index.py

This is the load-bearing module that every channel (admin, portal, AMFI, SEBI)
routes through. No document reaches build_index.py without passing through here.
"""
from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from app.engine import config
from app.engine.provenance_ledger import (
    DocumentStatus,
    IngestionChannel,
    ProvenanceRecord,
    get_ledger,
)


logger = logging.getLogger(__name__)


class IngestNamespace(str, Enum):
    """Logical groupings for ingested documents."""
    AMFI_REGULATORY = "amfi_regulatory"      # NAV, scheme data
    SEBI_CIRCULAR = "sebi_circular"          # Regulatory circulars
    MEMBER_DOCUMENT = "member_document"      # Portal uploads
    ADMIN_UPLOAD = "admin_upload"            # Admin UI uploads


@dataclass
class IngestRequest:
    """Request to ingest a document."""
    file_path: Path
    source_channel: IngestionChannel
    namespace: IngestNamespace
    source_url: Optional[str] = None
    ingested_by: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> tuple[bool, str]:
        """Validate request. Returns (is_valid, error_message)."""
        if not self.file_path.exists():
            return False, f"File not found: {self.file_path}"
        
        if self.file_path.suffix.lower() not in config.SUPPORTED_EXTS:
            return False, f"Unsupported extension: {self.file_path.suffix}"
        
        if self.file_path.stat().st_size == 0:
            return False, "File is empty"
        
        return True, ""


@dataclass
class IngestResult:
    """Result of an ingestion attempt."""
    success: bool
    document_hash: Optional[str] = None
    filename: Optional[str] = None
    was_duplicate: bool = False
    reason: Optional[str] = None
    provenance_record: Optional[ProvenanceRecord] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for logging/serialization."""
        return {
            "success": self.success,
            "document_hash": self.document_hash,
            "filename": self.filename,
            "was_duplicate": self.was_duplicate,
            "reason": self.reason,
        }


def compute_document_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of document for dedup."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def process_ingest(request: IngestRequest) -> IngestResult:
    """
    Process an ingestion request end-to-end.
    
    Flow:
      1. Validate request
      2. Compute content hash
      3. Check for duplicate (hash already in ledger)
      4. Create provenance record
      5. Insert into ledger
      6. Return result
    
    Args:
        request: IngestRequest with file and metadata
        
    Returns:
        IngestResult indicating success/failure and reason
    """
    # Validate
    is_valid, error = request.validate()
    if not is_valid:
        return IngestResult(
            success=False,
            reason=error
        )
    
    # Compute hash
    try:
        doc_hash = compute_document_hash(request.file_path)
    except Exception as e:
        return IngestResult(
            success=False,
            reason=f"Failed to compute hash: {str(e)}"
        )
    
    # Check for duplicate
    ledger = get_ledger()
    existing = ledger.find_by_hash(doc_hash)
    if existing:
        logger.info(
            f"[ingestion] Duplicate detected: {request.file_path.name} "
            f"(hash {doc_hash[:8]}... already ingested from {existing.source_channel})"
        )
        return IngestResult(
            success=False,
            document_hash=doc_hash,
            filename=request.file_path.name,
            was_duplicate=True,
            reason="Duplicate content (same hash already ingested)",
            provenance_record=existing
        )
    
    # Create provenance record
    now = datetime.now(timezone.utc).isoformat()
    record = ProvenanceRecord(
        document_hash=doc_hash,
        filename=request.file_path.name,
        source_channel=request.source_channel.value,
        source_url=request.source_url,
        ingestion_timestamp=now,
        ingestion_by=request.ingested_by,
        namespace=request.namespace.value,
        original_filename=request.file_path.name,
        status=DocumentStatus.ACTIVE.value,
        metadata=request.metadata or {}
    )
    
    # Insert into ledger
    if not ledger.insert_record(record):
        return IngestResult(
            success=False,
            document_hash=doc_hash,
            filename=request.file_path.name,
            reason="Failed to insert into provenance ledger (DB error)"
        )
    
    logger.info(
        f"[ingestion] Ingested {request.file_path.name} "
        f"(hash {doc_hash[:8]}..., channel={request.source_channel.value})"
    )
    
    return IngestResult(
        success=True,
        document_hash=doc_hash,
        filename=request.file_path.name,
        was_duplicate=False,
        provenance_record=record
    )


def batch_process_ingest(requests: list[IngestRequest]) -> list[IngestResult]:
    """
    Process multiple ingestion requests.
    
    Args:
        requests: list of IngestRequest objects
        
    Returns:
        list of IngestResult objects (parallel to input requests)
    """
    results = []
    for req in requests:
        result = process_ingest(req)
        results.append(result)
    return results


def get_ingest_stats() -> Dict[str, Any]:
    """Get ingestion statistics from provenance ledger."""
    ledger = get_ledger()
    records = ledger.get_all_records()
    
    by_channel = {}
    by_namespace = {}
    by_status = {}
    
    for rec in records:
        ch = rec.source_channel
        ns = rec.namespace
        st = rec.status
        
        by_channel[ch] = by_channel.get(ch, 0) + 1
        by_namespace[ns] = by_namespace.get(ns, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1
    
    return {
        "total_documents": len(records),
        "by_channel": by_channel,
        "by_namespace": by_namespace,
        "by_status": by_status,
    }


if __name__ == "__main__":
    # Quick test
    test_file = config.DATA_DIR / "test.pdf"
    if not test_file.exists():
        print("No test file found, skipping demo")
    else:
        req = IngestRequest(
            file_path=test_file,
            source_channel=IngestionChannel.ADMIN_MANUAL,
            namespace=IngestNamespace.ADMIN_UPLOAD,
            ingested_by="test_user"
        )
        result = process_ingest(req)
        print(f"Ingest result: {result.to_dict()}")
        print(f"Stats: {get_ingest_stats()}")
