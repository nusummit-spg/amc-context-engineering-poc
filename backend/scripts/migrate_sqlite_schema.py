# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
migrate_sqlite_schema.py
========================
Automated SQLite schema alignment migration for local / test SQLite database (data.db).
Ensures tables and columns match the active SQLAlchemy models:
- repair_proposals: adds corrected_value (Wave 1.3 B03)
- graph_mutations: adds verified_value, verification_timestamp, verification_receipt (B03)
- invitation_tokens: aligns token -> token_hash, redemption_attempts, last_attempt_at (SEC-03 / A05)
- reindex_jobs: creates table if not exists (B04)
- outbox_events: creates table if not exists (B05)
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logger = logging.getLogger("app.db.migrate_sqlite_schema")

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data.db"


def run_migration(db_path: Optional[Path] = None) -> bool:
    """Run SQLite schema alignment migration.

    Args:
        db_path (Optional[Path]): Filesystem path to the database file.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    target_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if not target_path.exists():
        logger.info("Database %s does not exist yet; schema creation will apply directly.", target_path)
        return True

    logger.info("Applying SQLite schema alignment migration to %s ...", target_path)
    conn = sqlite3.connect(str(target_path))
    cursor = conn.cursor()

    try:
        # 1. repair_proposals: add corrected_value
        cursor.execute("PRAGMA table_info(repair_proposals)")
        rp_cols = {row[1] for row in cursor.fetchall()}
        if rp_cols and "corrected_value" not in rp_cols:
            logger.info("Adding corrected_value to repair_proposals...")
            cursor.execute("ALTER TABLE repair_proposals ADD COLUMN corrected_value TEXT")

        # 2. graph_mutations: add verification columns
        cursor.execute("PRAGMA table_info(graph_mutations)")
        gm_cols = {row[1] for row in cursor.fetchall()}
        if gm_cols:
            if "verified_value" not in gm_cols:
                logger.info("Adding verified_value to graph_mutations...")
                cursor.execute("ALTER TABLE graph_mutations ADD COLUMN verified_value TEXT")
            if "verification_timestamp" not in gm_cols:
                logger.info("Adding verification_timestamp to graph_mutations...")
                cursor.execute("ALTER TABLE graph_mutations ADD COLUMN verification_timestamp VARCHAR(40)")
            if "verification_receipt" not in gm_cols:
                logger.info("Adding verification_receipt to graph_mutations...")
                cursor.execute("ALTER TABLE graph_mutations ADD COLUMN verification_receipt JSON")

        # 3. invitation_tokens: ensure token_hash schema
        cursor.execute("PRAGMA table_info(invitation_tokens)")
        inv_cols = {row[1] for row in cursor.fetchall()}
        if inv_cols and "token_hash" not in inv_cols:
            logger.info("Migrating invitation_tokens to token_hash schema...")
            from app.auth.invitation_tokens import hash_invitation_token
            
            cursor.execute("SELECT token, username, expires_at, created_by, created_at, used, used_at, used_from_ip FROM invitation_tokens")
            old_rows = cursor.fetchall()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invitation_tokens_v2 (
                    token_hash VARCHAR(64) PRIMARY KEY,
                    username VARCHAR(128) NOT NULL,
                    expires_at DATETIME NOT NULL,
                    created_by VARCHAR(128) NOT NULL,
                    created_at DATETIME NOT NULL,
                    used BOOLEAN NOT NULL DEFAULT 0,
                    used_at DATETIME,
                    used_from_ip VARCHAR(45),
                    redemption_attempts INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at DATETIME
                )
            """)

            for row in old_rows:
                token_val, uname, exp, cby, cat, used, uat, uip = row
                thash = hash_invitation_token(token_val) if token_val else ""
                cursor.execute("""
                    INSERT OR REPLACE INTO invitation_tokens_v2
                    (token_hash, username, expires_at, created_by, created_at, used, used_at, used_from_ip, redemption_attempts, last_attempt_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
                """, (thash, uname, exp, cby, cat, used, uat, uip))

            cursor.execute("DROP TABLE invitation_tokens")
            cursor.execute("ALTER TABLE invitation_tokens_v2 RENAME TO invitation_tokens")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_username ON invitation_tokens (username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_expires ON invitation_tokens (expires_at)")

        # 4. reindex_jobs: create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reindex_jobs (
                job_id VARCHAR(64) PRIMARY KEY,
                proposal_id VARCHAR(64),
                document_ids JSON,
                document_count INTEGER NOT NULL DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                started_at VARCHAR(40) NOT NULL,
                completed_at VARCHAR(40),
                verified BOOLEAN NOT NULL DEFAULT 0,
                verification_receipt JSON,
                error TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reindex_proposal_id ON reindex_jobs (proposal_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reindex_status ON reindex_jobs (status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reindex_started_at ON reindex_jobs (started_at)")

        # 5. outbox_events: create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS outbox_events (
                event_id VARCHAR(64) PRIMARY KEY,
                aggregate_type VARCHAR(64) NOT NULL,
                aggregate_id VARCHAR(64) NOT NULL,
                event_type VARCHAR(64) NOT NULL,
                payload JSON NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at VARCHAR(40) NOT NULL,
                processed_at VARCHAR(40),
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                error TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outbox_aggregate_id ON outbox_events (aggregate_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outbox_status_created ON outbox_events (status, created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outbox_created_at ON outbox_events (created_at)")

        conn.commit()
        logger.info("SQLite schema alignment migration applied successfully to %s", target_path)
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("Failed to apply SQLite schema alignment migration: %s", exc)
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
