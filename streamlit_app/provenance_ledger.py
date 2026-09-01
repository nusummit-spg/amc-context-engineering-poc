# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
provenance_ledger.py
====================
SQLite-backed provenance ledger for SEBI Regulation 16C compliance logging.
Tracks document acquisition channel, SHA-256 hash, status (active/superseded/withdrawn),
authorizing user, and legal lineage.
"""
from __future__ import annotations
import os
import sqlite3
import hashlib
from enum import Enum
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Set

import config

DB_PATH = config.PROJECT_ROOT / "logs" / "provenance_ledger.db"


class DocumentStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    PENDING_CONFIRMATION = "pending_confirmation"


class IngestionChannel(str, Enum):
    ADMIN_MANUAL = "admin_manual"
    MEMBER_PORTAL = "member_portal"
    AMFI_NAV = "amfi_nav"
    SEBI_RSS = "sebi_rss"
    BACKFILL_MIGRATION = "backfill_migration"
    ADMIN_UPLOAD = "admin_upload"
    AMFI_MEMBER_PORTAL = "amfi_member_portal"


@dataclass
class ProvenanceRecord:
    provenance_id: str
    filename: str
    sha256_hash: str
    acquisition_channel: str
    source_url: str
    doc_type: str
    department: str
    entity_type: str
    status: str = "active"
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    ingest_timestamp: str = ""
    authorized_by: str = "system"
    drift_detected: int = 0
    graph_node_count: int = 0


def get_connection() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS provenance (
                provenance_id       TEXT PRIMARY KEY,
                filename            TEXT NOT NULL UNIQUE,
                sha256_hash         TEXT NOT NULL,
                acquisition_channel TEXT NOT NULL,
                source_url          TEXT,
                doc_type            TEXT,
                department          TEXT,
                entity_type         TEXT,
                status              TEXT DEFAULT 'active',
                supersedes          TEXT,
                superseded_by       TEXT,
                ingest_timestamp    TEXT NOT NULL,
                authorized_by       TEXT NOT NULL,
                drift_detected      INTEGER DEFAULT 0,
                graph_node_count    INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON provenance(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON provenance(sha256_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dept ON provenance(department)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity ON provenance(entity_type)")


def compute_file_hash(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_by_filename(filename: str) -> Optional[ProvenanceRecord]:
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM provenance WHERE filename = ?", (filename,))
        row = cur.fetchone()
        if row:
            return ProvenanceRecord(**dict(row))
        return None
    finally:
        conn.close()


def find_by_hash(sha256_hash: str) -> Optional[ProvenanceRecord]:
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM provenance WHERE sha256_hash = ?", (sha256_hash,))
        row = cur.fetchone()
        if row:
            return ProvenanceRecord(**dict(row))
        return None
    finally:
        conn.close()


def get_active_filenames() -> Set[str]:
    conn = get_connection()
    try:
        cur = conn.execute("SELECT filename FROM provenance WHERE status = 'active'")
        return {row["filename"] for row in cur.fetchall()}
    finally:
        conn.close()


def write_record(record: ProvenanceRecord) -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO provenance (
                    provenance_id, filename, sha256_hash, acquisition_channel,
                    source_url, doc_type, department, entity_type, status,
                    supersedes, superseded_by, ingest_timestamp, authorized_by,
                    drift_detected, graph_node_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.provenance_id, record.filename, record.sha256_hash,
                record.acquisition_channel, record.source_url, record.doc_type,
                record.department, record.entity_type, record.status,
                record.supersedes, record.superseded_by, record.ingest_timestamp,
                record.authorized_by, record.drift_detected, record.graph_node_count
            ))
    finally:
        conn.close()


def update_status(filename: str, new_status: str, superseded_by: Optional[str] = None) -> None:
    conn = get_connection()
    try:
        with conn:
            if superseded_by:
                conn.execute("""
                    UPDATE provenance
                    SET status = ?, superseded_by = ?
                    WHERE filename = ?
                """, (new_status, superseded_by, filename))
            else:
                conn.execute("""
                    UPDATE provenance
                    SET status = ?
                    WHERE filename = ?
                """, (new_status, filename))
    finally:
        conn.close()


def mark_drift(filename: str, drifted: bool = True) -> None:
    conn = get_connection()
    try:
        with conn:
            conn.execute("UPDATE provenance SET drift_detected = ? WHERE filename = ?", (1 if drifted else 0, filename))
    finally:
        conn.close()


def get_all_records() -> List[ProvenanceRecord]:
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM provenance ORDER BY ingest_timestamp DESC")
        return [ProvenanceRecord(**dict(row)) for row in cur.fetchall()]
    finally:
        conn.close()


def backfill_existing_documents() -> int:
    """One-time migration to register pre-existing AMC data files into SQLite ledger."""
    count = 0
    amc_root = config.DATA_DIR
    if not amc_root.exists():
        return 0

    import uuid
    for path in amc_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in config.SUPPORTED_EXTS:
            fname = path.name
            if find_by_filename(fname) is None:
                sha = compute_file_hash(path)
                rec = ProvenanceRecord(
                    provenance_id=str(uuid.uuid4()),
                    filename=fname,
                    sha256_hash=sha,
                    acquisition_channel="manual_public_download",
                    source_url="",
                    doc_type="circular" if "SEBI" in fname else "reference",
                    department="IMD" if "SEBI" in fname else "GENERAL",
                    entity_type="AMC",
                    status="active",
                    ingest_timestamp=datetime.now().isoformat(),
                    authorized_by="system_backfill"
                )
                write_record(rec)
                count += 1
    if count > 0:
        print(f"  [ProvenanceLedger] Backfilled {count} pre-existing documents into SQLite database.", flush=True)
    return count


def generate_compliance_report() -> str:
    """Export markdown Regulation 16C legal compliance report."""
    records = get_all_records()
    total = len(records)
    active = sum(1 for r in records if r.status == "active")
    superseded = sum(1 for r in records if r.status == "superseded")
    drifted = sum(1 for r in records if r.drift_detected)

    lines = [
        "# SEBI Regulation 16C — Legal Ingestion & Provenance Audit Ledger",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | **Total Indexed Documents**: {total}",
        f"**Active Documents**: {active} | **Superseded Documents**: {superseded} | **Drift Alerts**: {drifted}",
        "",
        "| Filename | Acquisition Channel | SHA-256 (Prefix) | Status | Department | Authorized By | Timestamp |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records[:50]:
        lines.append(
            f"| `{r.filename[:40]}` | `{r.acquisition_channel}` | `{r.sha256_hash[:12]}` | `{r.status}` | `{r.department}` | `{r.authorized_by}` | {r.ingest_timestamp[:10]} |"
        )
    return "\n".join(lines)


# Run auto-backfill on module load so existing AMC files are immediately covered
try:
    backfill_existing_documents()
except Exception as _e:
    print(f"  [ProvenanceLedger] Initial backfill notice: {_e}", flush=True)
