# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
migrate_feedback_issues.py
==========================
Database migration to add the `feedback_issues` table and extend `response_feedback`
with `issue_id` and `match_type` columns for the Contextual Feedback Status Awareness feature.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.db.migrate_feedback_issues")

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

    logger.info("Applying feedback issues migration to %s ...", target_path)
    conn = sqlite3.connect(str(target_path))
    cursor = conn.cursor()

    try:
        # 1. Create feedback_issues table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_issues (
                issue_id VARCHAR(64) PRIMARY KEY,
                canonical_query_text TEXT NOT NULL,
                query_hash VARCHAR(64) NOT NULL,
                query_embedding_ref VARCHAR(64),
                primary_entities JSON NOT NULL,
                taxonomy_paths JSON NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'reported',
                repair_task_id VARCHAR(64),
                contributor_count INTEGER NOT NULL DEFAULT 1,
                tenant_id VARCHAR(64),
                created_at VARCHAR(40) NOT NULL,
                updated_at VARCHAR(40) NOT NULL,
                resolution_notes TEXT
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_issues_query_hash ON feedback_issues (query_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_issues_status ON feedback_issues (status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_issues_tenant ON feedback_issues (tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_issues_created ON feedback_issues (created_at)")

        # 2. Create feedback_issue_category_counts table if not exists (Phase 1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_issue_category_counts (
                issue_id VARCHAR(64) NOT NULL,
                category_code VARCHAR(10) NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                updated_at VARCHAR(40) NOT NULL,
                PRIMARY KEY (issue_id, category_code),
                FOREIGN KEY (issue_id) REFERENCES feedback_issues(issue_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_category_counts_issue_id ON feedback_issue_category_counts (issue_id)")

        # 3. Inspect response_feedback columns
        cursor.execute("PRAGMA table_info(response_feedback)")
        rf_cols = {row[1] for row in cursor.fetchall()}

        if rf_cols:
            if "issue_id" not in rf_cols:
                logger.info("Adding issue_id to response_feedback...")
                cursor.execute("ALTER TABLE response_feedback ADD COLUMN issue_id VARCHAR(64)")

            if "match_type" not in rf_cols:
                logger.info("Adding match_type to response_feedback...")
                cursor.execute("ALTER TABLE response_feedback ADD COLUMN match_type VARCHAR(20)")

            if "categories" not in rf_cols:
                logger.info("Adding categories JSON column to response_feedback...")
                cursor.execute("ALTER TABLE response_feedback ADD COLUMN categories JSON")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_response_feedback_issue_id ON response_feedback (issue_id)")

        conn.commit()
        logger.info("Feedback issues migration applied successfully to %s", target_path)
        return True
    except Exception as exc:
        conn.rollback()
        logger.error("Failed to apply feedback issues migration: %s", exc)
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
