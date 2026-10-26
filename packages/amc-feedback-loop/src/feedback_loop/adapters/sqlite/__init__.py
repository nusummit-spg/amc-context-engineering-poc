"""
SQLite adapter package.

Exports the two concrete adapters for wiring start_feedback_loop()
against the compliance_audit.db SQLite database.

Usage
-----
    from feedback_loop.adapters.sqlite import SQLiteDatabaseAdapter, SQLiteEvidenceAdapter

    DB_URL = "sqlite:///path/to/compliance_audit.db"
    db  = SQLiteDatabaseAdapter(db_url=DB_URL)
    ev  = SQLiteEvidenceAdapter(db_url=DB_URL)
"""

from feedback_loop.adapters.sqlite.db_adapter import SQLiteDatabaseAdapter
from feedback_loop.adapters.sqlite.evidence_adapter import SQLiteEvidenceAdapter

__all__ = ["SQLiteDatabaseAdapter", "SQLiteEvidenceAdapter"]
