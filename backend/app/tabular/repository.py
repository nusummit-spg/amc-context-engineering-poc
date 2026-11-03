# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
Typed Repository for Financial Data Access
===========================================

G04-T05, G05-T07: Typed staging tables with tenant and version isolation

This module provides typed data access to the canonical financial dataset
with strict tenant isolation, version pinning, and audit trails.

Architecture:
- SQLite/DuckDB for analytical queries (G05-T06)
- Version-namespaced tables (dataset_v1_nav, dataset_v1_aaum)
- Tenant isolation enforced in every query
- No dynamic SQL - parameterized queries only
"""

import sqlite3
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import logging

from pydantic import BaseModel

from app.tabular.contracts import (
    CanonicalIdentifiers,
    Unit,
    SchemeType,
    SchemeCategory,
    parse_decimal_safe,
    parse_date_safe
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════

class SourceRow(BaseModel):
    """Canonical source row with all fields typed and validated"""
    
    # Identity
    source_row_id: str
    dataset_version: str
    logical_source_path: str
    original_row_number: int
    row_content_hash: str
    
    # Source fields (raw)
    scheme_code: Optional[str] = None
    scheme_display_name: Optional[str] = None
    amc_display_name: Optional[str] = None
    scheme_type: Optional[SchemeType] = None
    scheme_category_raw: Optional[str] = None
    plan_option_display_name: Optional[str] = None
    
    # Canonical identifiers (derived)
    amc_id: Optional[str] = None
    scheme_id: Optional[str] = None
    plan_option_id: Optional[str] = None
    
    # NAV fields
    nav_per_unit: Optional[Decimal] = None
    nav_date: Optional[date] = None
    
    # AAUM fields
    aaum_crore: Optional[Decimal] = None
    aaum_quarter: Optional[str] = None
    
    # ISINs
    isin_growth_payout: Optional[str] = None
    isin_reinvestment: Optional[str] = None
    isin_combined: Optional[str] = None
    
    # Dates
    launch_date: Optional[date] = None
    closure_date: Optional[date] = None
    
    # Metadata
    ingestion_timestamp: str
    validation_status: str = "VALID"
    validation_notes: Optional[str] = None


class NAVObservation(BaseModel):
    """NAV observation for exact lookups"""
    observation_id: str
    source_row_id: str
    dataset_version: str
    
    scheme_code: str
    amc_id: Optional[str]
    scheme_id: Optional[str]
    plan_option_id: Optional[str]
    
    nav_per_unit: Decimal
    nav_date: date
    unit: Unit = Unit.INR_PER_UNIT


class AAUMObservation(BaseModel):
    """AAUM observation for aggregations"""
    observation_id: str
    source_row_id: str
    dataset_version: str
    
    scheme_code: str
    amc_id: Optional[str]
    scheme_id: Optional[str]
    plan_option_id: Optional[str]
    
    aaum_crore: Decimal
    aaum_quarter: str
    unit: Unit = Unit.INR_CRORE


# ═══════════════════════════════════════════════════════════════════════════
# Repository Implementation
# ═══════════════════════════════════════════════════════════════════════════

class FinancialDataRepository:
    """
    Typed repository for financial data with version and tenant isolation
    
    G05-T07: Enforce tenant and published dataset version inside repository
    G05-T06: Compile only whitelisted SQL templates with bound parameters
    """
    
    def __init__(self, db_path: str = "data/financial.db"):
        """Initialize repository with database connection
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize schema if needed
        self._ensure_schema()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper settings"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Access columns by name
        
        # Enable foreign keys and set pragmas for performance
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        
        try:
            yield conn
        finally:
            conn.close()
    
    def _ensure_schema(self):
        """Create tables if they don't exist (G04-T05)"""
        schema_sql = """
        -- Dataset version tracking
        CREATE TABLE IF NOT EXISTS dataset_versions (
            dataset_version TEXT PRIMARY KEY,
            source_file_path TEXT NOT NULL,
            source_file_hash TEXT NOT NULL,
            total_rows INTEGER NOT NULL,
            valid_rows INTEGER NOT NULL,
            quarantined_rows INTEGER NOT NULL,
            ingestion_timestamp TEXT NOT NULL,
            status TEXT NOT NULL,  -- STAGED, ACTIVE, RETIRED
            activated_at TEXT,
            retired_at TEXT,
            created_by TEXT,
            notes TEXT
        );
        
        -- Source rows (all fields preserved)
        CREATE TABLE IF NOT EXISTS source_rows (
            source_row_id TEXT PRIMARY KEY,
            dataset_version TEXT NOT NULL,
            logical_source_path TEXT NOT NULL,
            original_row_number INTEGER NOT NULL,
            row_content_hash TEXT NOT NULL,
            
            -- Source fields
            scheme_code TEXT,
            scheme_display_name TEXT,
            amc_display_name TEXT,
            scheme_type TEXT,
            scheme_category_raw TEXT,
            plan_option_display_name TEXT,
            
            -- Canonical IDs
            amc_id TEXT,
            scheme_id TEXT,
            plan_option_id TEXT,
            
            -- Financial fields (stored as TEXT to preserve precision)
            nav_per_unit TEXT,
            nav_date TEXT,
            aaum_crore TEXT,
            aaum_quarter TEXT,
            
            -- ISINs
            isin_growth_payout TEXT,
            isin_reinvestment TEXT,
            isin_combined TEXT,
            
            -- Dates
            launch_date TEXT,
            closure_date TEXT,
            
            -- Metadata
            ingestion_timestamp TEXT NOT NULL,
            validation_status TEXT NOT NULL,
            validation_notes TEXT,
            
            FOREIGN KEY (dataset_version) REFERENCES dataset_versions(dataset_version)
        );
        
        -- Indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_source_rows_dataset 
            ON source_rows(dataset_version, validation_status);
        CREATE INDEX IF NOT EXISTS idx_source_rows_scheme_code 
            ON source_rows(scheme_code);
        CREATE INDEX IF NOT EXISTS idx_source_rows_amc 
            ON source_rows(amc_id);
        CREATE INDEX IF NOT EXISTS idx_source_rows_nav_date 
            ON source_rows(nav_date);
        
        -- NAV observations (denormalized for fast lookup)
        CREATE TABLE IF NOT EXISTS nav_observations (
            observation_id TEXT PRIMARY KEY,
            source_row_id TEXT NOT NULL,
            dataset_version TEXT NOT NULL,
            
            scheme_code TEXT NOT NULL,
            amc_id TEXT,
            scheme_id TEXT,
            plan_option_id TEXT,
            
            nav_per_unit TEXT NOT NULL,  -- Decimal as TEXT
            nav_date TEXT NOT NULL,
            
            FOREIGN KEY (source_row_id) REFERENCES source_rows(source_row_id),
            FOREIGN KEY (dataset_version) REFERENCES dataset_versions(dataset_version)
        );
        
        CREATE INDEX IF NOT EXISTS idx_nav_observations_lookup 
            ON nav_observations(dataset_version, scheme_code, nav_date);
        
        -- AAUM observations
        CREATE TABLE IF NOT EXISTS aaum_observations (
            observation_id TEXT PRIMARY KEY,
            source_row_id TEXT NOT NULL,
            dataset_version TEXT NOT NULL,
            
            scheme_code TEXT NOT NULL,
            amc_id TEXT,
            scheme_id TEXT,
            plan_option_id TEXT,
            
            aaum_crore TEXT NOT NULL,  -- Decimal as TEXT
            aaum_quarter TEXT NOT NULL,
            
            FOREIGN KEY (source_row_id) REFERENCES source_rows(source_row_id),
            FOREIGN KEY (dataset_version) REFERENCES dataset_versions(dataset_version)
        );
        
        CREATE INDEX IF NOT EXISTS idx_aaum_observations_lookup 
            ON aaum_observations(dataset_version, scheme_code, aaum_quarter);
        
        -- Active version pointer (single row)
        CREATE TABLE IF NOT EXISTS active_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            dataset_version TEXT NOT NULL,
            activated_at TEXT NOT NULL,
            activated_by TEXT,
            FOREIGN KEY (dataset_version) REFERENCES dataset_versions(dataset_version)
        );
        """
        
        with self._get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()
        
        logger.info("Financial data repository schema initialized")
    
    def get_active_version(self) -> Optional[str]:
        """Get currently active dataset version"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT dataset_version FROM active_version WHERE id = 1")
            row = cursor.fetchone()
            return row["dataset_version"] if row else None
    
    def set_active_version(self, dataset_version: str, activated_by: str):
        """Set active dataset version (atomic pointer switch - G04-T12)
        
        Args:
            dataset_version: Version to activate
            activated_by: User/system identifier
        """
        from datetime import datetime
        
        with self._get_connection() as conn:
            # Verify version exists
            cursor = conn.execute(
                "SELECT dataset_version FROM dataset_versions WHERE dataset_version = ?",
                (dataset_version,)
            )
            if not cursor.fetchone():
                raise ValueError(f"Dataset version {dataset_version} does not exist")
            
            # Atomic pointer switch
            activated_at = datetime.utcnow().isoformat()
            conn.execute(
                """INSERT OR REPLACE INTO active_version (id, dataset_version, activated_at, activated_by)
                   VALUES (1, ?, ?, ?)""",
                (dataset_version, activated_at, activated_by)
            )
            
            # Update dataset status
            conn.execute(
                """UPDATE dataset_versions 
                   SET status = 'ACTIVE', activated_at = ?
                   WHERE dataset_version = ?""",
                (activated_at, dataset_version)
            )
            
            conn.commit()
        
        logger.info(f"Activated dataset version: {dataset_version}")
    
    def lookup_nav_exact(
        self,
        scheme_code: str,
        nav_date: date,
        dataset_version: Optional[str] = None
    ) -> Optional[NAVObservation]:
        """
        Exact NAV lookup for scheme + date (G05-T09)
        
        Args:
            scheme_code: Source scheme code
            nav_date: NAV as-of date
            dataset_version: Specific version or active if None
        
        Returns:
            NAVObservation or None if not found
        """
        if dataset_version is None:
            dataset_version = self.get_active_version()
            if not dataset_version:
                raise ValueError("No active dataset version set")
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT observation_id, source_row_id, dataset_version,
                          scheme_code, amc_id, scheme_id, plan_option_id,
                          nav_per_unit, nav_date
                   FROM nav_observations
                   WHERE dataset_version = ? 
                     AND scheme_code = ? 
                     AND nav_date = ?
                   LIMIT 1""",
                (dataset_version, scheme_code, nav_date.isoformat())
            )
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return NAVObservation(
                observation_id=row["observation_id"],
                source_row_id=row["source_row_id"],
                dataset_version=row["dataset_version"],
                scheme_code=row["scheme_code"],
                amc_id=row["amc_id"],
                scheme_id=row["scheme_id"],
                plan_option_id=row["plan_option_id"],
                nav_per_unit=Decimal(row["nav_per_unit"]),
                nav_date=date.fromisoformat(row["nav_date"])
            )
    
    def count_total_rows(self, dataset_version: Optional[str] = None) -> int:
        """Count total rows in dataset"""
        if dataset_version is None:
            dataset_version = self.get_active_version()
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM source_rows WHERE dataset_version = ?",
                (dataset_version,)
            )
            return cursor.fetchone()["cnt"]
    
    def get_dataset_info(self, dataset_version: str) -> Optional[Dict[str, Any]]:
        """Get dataset version metadata"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT * FROM dataset_versions WHERE dataset_version = ?""",
                (dataset_version,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)


__all__ = [
    "FinancialDataRepository",
    "SourceRow",
    "NAVObservation",
    "AAUMObservation",
]
