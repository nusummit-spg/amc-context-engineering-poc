# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
ingestion_gateway.py
====================
Unified ingestion entry point for all acquisition channels.
Handles SHA-256 hash deduplication, provenance ledger updates, and file routing.
"""
from __future__ import annotations
import shutil
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import config
import provenance_ledger


class IngestNamespace(str, Enum):
    SHARED = "shared"
    ADMIN_UPLOAD = "admin_upload"
    SEBI_CIRCULAR = "sebi_circular"
    AMFI_REGULATORY = "amfi_regulatory"
    MEMBER_DOCUMENT = "member_document"


@dataclass
class IngestRequest:
    filepath: Optional[Path] = None
    file_path: Optional[Path] = None
    acquisition_channel: Optional[str] = None
    source_channel: Optional[Any] = None
    source_url: str = ""
    doc_type: str = "circular"   # "circular" | "master_circular" | "faq" | "nav_data"
    department: str = "IMD"      # "IMD" | "MRD" | "MIRSD" | "HO" | "CFD" | "GENERAL"
    entity_type: str = "AMC"     # "AMC" | "Broker" | "RA" | "All"
    status: str = "active"
    authorized_by: str = "system"
    ingested_by: Optional[str] = None
    supersedes: Optional[str] = None
    namespace: Any = "shared"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.file_path is not None and self.filepath is None:
            self.filepath = Path(self.file_path)
        elif self.filepath is not None:
            self.filepath = Path(self.filepath)

        if self.source_channel is not None and self.acquisition_channel is None:
            self.acquisition_channel = getattr(self.source_channel, "value", str(self.source_channel))
        elif self.acquisition_channel is None:
            self.acquisition_channel = "admin_upload"

        if self.ingested_by and self.authorized_by == "system":
            self.authorized_by = self.ingested_by

        if isinstance(self.namespace, Enum):
            self.namespace = self.namespace.value

        if self.metadata:
            self.doc_type = self.metadata.get("doc_type", self.doc_type)
            self.department = self.metadata.get("department", self.department)
            self.entity_type = self.metadata.get("entity_type", self.entity_type)


@dataclass
class IngestResult:
    accepted: bool
    reason: str                  # "new_document" | "already_indexed" | "content_modified" | "rejected"
    sha256_hash: str
    provenance_id: str
    destination_path: Path

    @property
    def success(self) -> bool:
        return self.accepted

    @property
    def document_hash(self) -> str:
        return self.sha256_hash


def process_ingest(req: IngestRequest) -> IngestResult:
    """
    Ingest a document into the system pipeline:
    1. Compute SHA-256 hash
    2. Check provenance ledger for duplicate hash / filename
    3. Route file to target directory under data/AMC/
    4. Write provenance record to SQLite
    5. Handle supersession status update if applicable
    """
    if not req.filepath.exists():
        return IngestResult(
            accepted=False,
            reason="file_not_found",
            sha256_hash="",
            provenance_id="",
            destination_path=req.filepath
        )

    sha = provenance_ledger.compute_file_hash(req.filepath)
    fname = req.filepath.name

    # Check hash duplicate
    existing_hash_rec = provenance_ledger.find_by_hash(sha)
    if existing_hash_rec is not None:
        return IngestResult(
            accepted=False,
            reason="already_indexed",
            sha256_hash=sha,
            provenance_id=existing_hash_rec.provenance_id,
            destination_path=req.filepath
        )

    prov_id = str(uuid.uuid4())
    dest_dir = config.DATA_DIR / req.namespace / ("SEBI_Circulars" if req.doc_type == "circular" else "Reference")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / fname

    if req.filepath.resolve() != dest_file.resolve():
        shutil.copy2(req.filepath, dest_file)

    rec = provenance_ledger.ProvenanceRecord(
        provenance_id=prov_id,
        filename=fname,
        sha256_hash=sha,
        acquisition_channel=req.acquisition_channel,
        source_url=req.source_url,
        doc_type=req.doc_type,
        department=req.department,
        entity_type=req.entity_type,
        status=req.status,
        supersedes=req.supersedes,
        ingest_timestamp=datetime.now().isoformat(),
        authorized_by=req.authorized_by
    )
    provenance_ledger.write_record(rec)

    # Handle supersession link
    if req.supersedes:
        provenance_ledger.update_status(req.supersedes, "superseded", superseded_by=fname)

    return IngestResult(
        accepted=True,
        reason="new_document",
        sha256_hash=sha,
        provenance_id=prov_id,
        destination_path=dest_file
    )
