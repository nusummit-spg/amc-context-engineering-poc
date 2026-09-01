# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
provenance_ledger.py
======================
SQLite-backed provenance tracking for all ingested documents.
Provides the single source of truth for:
  - Document hashes (deduplication)
  - Ingestion source/channel (RSS, portal, admin, etc.)
  - Active/superseded/rejected status
  - Source URLs and metadata
  - Ingestion timestamps and audit trail

This module is load-bearing for every acquisition channel.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.engine import config


class DocumentStatus(str, Enum):
    """Document lifecycle status."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    PENDING_CONFIRMATION = "pending_confirmation"


class IngestionChannel(str, Enum):
    """Source channel identifier."""
    ADMIN_MANUAL = "admin_manual"
    MEMBER_PORTAL = "member_portal"
    AMFI_NAV = "amfi_nav"
    SEBI_RSS = "sebi_rss"
    BACKFILL_MIGRATION = "backfill_migration"


@dataclass
class ProvenanceRecord:
    """Immutable record of a document's origin and processing."""
    document_hash: str
    filename: str
    source_channel: str
    source_url: Optional[str]
    ingestion_timestamp: str
    ingestion_by: str
    namespace: str
    original_filename: Optional[str] = None
    status: str = DocumentStatus.ACTIVE.value
    metadata: Optional[Dict[str, Any]] = None
    superseded_by_hash: Optional[str] = None
    rejection_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, excluding None metadata."""
        d = asdict(self)
        if d.get("metadata") is None:
            d["metadata"] = "{}"
        elif isinstance(d["metadata"], dict):
            d["metadata"] = json.dumps(d["metadata"])
        return d


class ProvenanceLedger:
    """Thread-safe SQLite provenance store."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Args:
            db_path: path to SQLite DB. Defaults to logs/provenance.db
        """
        self.db_path = db_path or (config.LOG_DIR / "provenance.db")
        self._lock = threading.RLock()
        self._init_schema()
    
    def _init_schema(self):
        """Initialize/migrate schema on first connection."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS provenance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        document_hash TEXT NOT NULL UNIQUE,
                        filename TEXT NOT NULL,
                        source_channel TEXT NOT NULL,
                        source_url TEXT,
                        ingestion_timestamp TEXT NOT NULL,
                        ingestion_by TEXT NOT NULL,
                        namespace TEXT NOT NULL,
                        original_filename TEXT,
                        status TEXT NOT NULL DEFAULT 'active',
                        metadata TEXT,
                        superseded_by_hash TEXT,
                        rejection_reason TEXT,
                        created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_document_hash 
                    ON provenance(document_hash);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_filename 
                    ON provenance(filename);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_source_channel 
                    ON provenance(source_channel);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_status 
                    ON provenance(status);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_namespace 
                    ON provenance(namespace);
                """)
                conn.commit()
    
    def insert_record(self, record: ProvenanceRecord) -> bool:
        """
        Insert a provenance record.
        
        Args:
            record: ProvenanceRecord to insert
            
        Returns:
            True if inserted; False if hash already exists (dedup)
        """
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT INTO provenance (
                            document_hash, filename, source_channel, source_url,
                            ingestion_timestamp, ingestion_by, namespace,
                            original_filename, status, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.document_hash,
                        record.filename,
                        record.source_channel,
                        record.source_url,
                        record.ingestion_timestamp,
                        record.ingestion_by,
                        record.namespace,
                        record.original_filename,
                        record.status,
                        record.metadata if isinstance(record.metadata, str) 
                        else json.dumps(record.metadata or {})
                    ))
                    conn.commit()
                    return True
            except sqlite3.IntegrityError:
                return False
    
    def find_by_hash(self, document_hash: str) -> Optional[ProvenanceRecord]:
        """Find a provenance record by document hash."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM provenance WHERE document_hash = ?",
                    (document_hash,)
                ).fetchone()
                if row:
                    return self._row_to_record(row)
        return None
    
    def find_by_filename(self, filename: str) -> Optional[ProvenanceRecord]:
        """Find most recent provenance record by filename."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM provenance WHERE filename = ? ORDER BY created_at DESC LIMIT 1",
                    (filename,)
                ).fetchone()
                if row:
                    return self._row_to_record(row)
        return None
    
    def get_active_filenames(self, namespace: str = "") -> List[str]:
        """Get all active document filenames, optionally filtered by namespace."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                query = "SELECT DISTINCT filename FROM provenance WHERE status = ?"
                params = [DocumentStatus.ACTIVE.value]
                
                if namespace:
                    query += " AND namespace = ?"
                    params.append(namespace)
                
                query += " ORDER BY filename"
                rows = conn.execute(query, params).fetchall()
                return [row[0] for row in rows]
    
    def update_status(
        self,
        document_hash: str,
        new_status: DocumentStatus,
        reason: Optional[str] = None,
        superseded_by_hash: Optional[str] = None
    ) -> bool:
        """Update document status (e.g., mark as superseded/rejected)."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE provenance
                    SET status = ?,
                        rejection_reason = ?,
                        superseded_by_hash = ?
                    WHERE document_hash = ?
                """, (
                    new_status.value,
                    reason,
                    superseded_by_hash,
                    document_hash
                ))
                conn.commit()
                return conn.total_changes > 0
    
    def get_by_source_channel(
        self,
        channel: IngestionChannel,
        status: Optional[DocumentStatus] = None,
        limit: int = 1000
    ) -> List[ProvenanceRecord]:
        """Fetch records by source channel, optionally filtered by status."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                query = "SELECT * FROM provenance WHERE source_channel = ?"
                params = [channel.value]
                
                if status:
                    query += " AND status = ?"
                    params.append(status.value)
                
                query += " ORDER BY ingestion_timestamp DESC LIMIT ?"
                params.append(limit)
                
                rows = conn.execute(query, params).fetchall()
                return [self._row_to_record(row) for row in rows]
    
    def get_all_records(self, status: Optional[DocumentStatus] = None) -> List[ProvenanceRecord]:
        """Fetch all records, optionally filtered by status."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                query = "SELECT * FROM provenance"
                params = []
                
                if status:
                    query += " WHERE status = ?"
                    params.append(status.value)
                
                query += " ORDER BY created_at DESC"
                rows = conn.execute(query, params).fetchall()
                return [self._row_to_record(row) for row in rows]
    
    def get_superseded_pairs(self) -> List[tuple[str, str]]:
        """Get all (superseded_hash, superseding_hash) pairs."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute("""
                    SELECT document_hash, superseded_by_hash
                    FROM provenance
                    WHERE status = ? AND superseded_by_hash IS NOT NULL
                """, (DocumentStatus.SUPERSEDED.value,)).fetchall()
                return rows
    
    def count_by_status(self) -> Dict[str, int]:
        """Get count of documents by status."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute("""
                    SELECT status, COUNT(*) as count
                    FROM provenance
                    GROUP BY status
                """).fetchall()
                return {row[0]: row[1] for row in rows}
    
    def backfill_existing_documents(self, data_dir: Path = config.DATA_DIR) -> int:
        """
        Migrate existing data/AMC/ PDFs into provenance ledger.
        Used during Phase 0 to establish initial state.
        
        Args:
            data_dir: root directory of existing documents
            
        Returns:
            count of newly inserted records
        """
        count = 0
        for pdf_path in data_dir.rglob("*.pdf"):
            content = pdf_path.read_bytes()
            doc_hash = hashlib.sha256(content).hexdigest()
            
            # Skip if already in ledger (idempotent)
            if self.find_by_hash(doc_hash):
                continue
            
            record = ProvenanceRecord(
                document_hash=doc_hash,
                filename=pdf_path.name,
                source_channel=IngestionChannel.BACKFILL_MIGRATION.value,
                source_url=None,
                ingestion_timestamp=datetime.now(timezone.utc).isoformat(),
                ingestion_by="system_backfill",
                namespace="amfi_regulatory",
                original_filename=None,
                status=DocumentStatus.ACTIVE.value,
                metadata={"original_path": str(pdf_path.relative_to(config.PROJECT_ROOT))}
            )
            
            if self.insert_record(record):
                count += 1
        
        return count
    
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ProvenanceRecord:
        """Convert SQLite row to ProvenanceRecord."""
        metadata = row["metadata"]
        if metadata:
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        
        return ProvenanceRecord(
            document_hash=row["document_hash"],
            filename=row["filename"],
            source_channel=row["source_channel"],
            source_url=row["source_url"],
            ingestion_timestamp=row["ingestion_timestamp"],
            ingestion_by=row["ingestion_by"],
            namespace=row["namespace"],
            original_filename=row["original_filename"],
            status=row["status"],
            metadata=metadata,
            superseded_by_hash=row["superseded_by_hash"],
            rejection_reason=row["rejection_reason"]
        )


# Module singleton
_ledger: Optional[ProvenanceLedger] = None


def get_ledger() -> ProvenanceLedger:
    """Get the global provenance ledger instance."""
    global _ledger
    if _ledger is None:
        _ledger = ProvenanceLedger()
    return _ledger


if __name__ == "__main__":
    # Quick test
    ledger = get_ledger()
    count = ledger.backfill_existing_documents()
    print(f"Backfilled {count} documents")
    print(f"Status distribution: {ledger.count_by_status()}")
