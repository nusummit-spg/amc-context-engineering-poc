# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
migrate_user_ownership.py
=========================
Database migration to enforce mandatory user ownership and tenant isolation
on `chat_sessions` and `query_evidence` tables (Phase 1 Security Remediation).
"""
import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.db.migrate_user_ownership")

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data.db"


def run_migration(db_path: Optional[Path] = None) -> bool:
    """Run migration.

    Args:
        db_path (Optional[Path]): Filesystem path to the db.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    target_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if not target_path.exists():
        logger.info("Database %s does not exist yet; schema creation will apply directly.", target_path)
        return True

    logger.info("Applying user ownership migration to %s ...", target_path)
    conn = sqlite3.connect(str(target_path))
    cursor = conn.cursor()

    try:
        # 1. Inspect chat_sessions columns
        cursor.execute("PRAGMA table_info(chat_sessions)")
        cs_cols = {row[1] for row in cursor.fetchall()}

        if cs_cols:
            if "tenant_id" not in cs_cols:
                logger.info("Adding tenant_id to chat_sessions...")
                cursor.execute("ALTER TABLE chat_sessions ADD COLUMN tenant_id VARCHAR(36)")

            cursor.execute("UPDATE chat_sessions SET user_id = 'system_migration' WHERE user_id IS NULL")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_user_tenant ON chat_sessions (user_id, tenant_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_user_created ON chat_sessions (user_id, created_at)")
            logger.info("chat_sessions indexes created successfully.")

        # 2. Inspect query_evidence columns
        cursor.execute("PRAGMA table_info(query_evidence)")
        qe_cols = {row[1] for row in cursor.fetchall()}

        if qe_cols:
            if "user_id" not in qe_cols:
                logger.info("Adding user_id to query_evidence...")
                cursor.execute("ALTER TABLE query_evidence ADD COLUMN user_id VARCHAR(36) NOT NULL DEFAULT 'system_migration'")

            cursor.execute("UPDATE query_evidence SET user_id = 'system_migration' WHERE user_id IS NULL")

            if "tenant_id" not in qe_cols:
                logger.info("Adding tenant_id to query_evidence...")
                cursor.execute("ALTER TABLE query_evidence ADD COLUMN tenant_id VARCHAR(36)")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_qe_session_user ON query_evidence (session_id, user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_qe_user_session ON query_evidence (user_id, session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_qe_tenant_user ON query_evidence (tenant_id, user_id)")
            logger.info("query_evidence indexes created successfully.")

        conn.commit()
        logger.info("User ownership migration completed successfully on %s", target_path)
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("Migration failed: %s", exc, exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    print("Migration success:", success)
