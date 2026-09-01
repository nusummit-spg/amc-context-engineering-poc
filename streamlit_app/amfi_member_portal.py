# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
amfi_member_portal.py
=====================
Layer 1D Acquisition Channel — AMFI Member Portal / Official Inbox Integration.
Ingests documents officially addressed to the AMC (zero legal reproduction risk).
"""
from __future__ import annotations
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

import config
import ingestion_gateway


def get_member_inbox_path() -> Path:
    inbox = getattr(config, "MEMBER_PORTAL_INBOX", config.PROJECT_ROOT / "data" / "AMC" / "member_portal_inbox")
    inbox.mkdir(parents=True, exist_ok=True)
    return inbox


def ingest_from_member_inbox(authorized_user: str = "compliance_officer") -> List[Dict[str, Any]]:
    """
    Scans the AMC's designated member portal inbox folder.
    Processes all PDF/document files through ingestion_gateway.
    """
    inbox_dir = get_member_inbox_path()
    results = []

    for path in inbox_dir.glob("*"):
        if path.is_file() and path.suffix.lower() in config.SUPPORTED_EXTS:
            req = ingestion_gateway.IngestRequest(
                filepath=path,
                acquisition_channel="amfi_member_portal",
                source_url=f"member_inbox://{path.name}",
                doc_type="circular" if "circular" in path.name.lower() else "reference",
                department="IMD",
                entity_type="AMC",
                status="active",
                authorized_by=authorized_user,
                namespace="shared"
            )
            res = ingestion_gateway.process_ingest(req)
            results.append({
                "filename": path.name,
                "accepted": res.accepted,
                "reason": res.reason,
                "sha256": res.sha256_hash[:12]
            })

    if results:
        print(f"  [AMFI Member Portal] Processed {len(results)} inbox documents.", flush=True)
    return results
