# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
feedback.py
===========
SQLite-backed feedback store for human failure-taxonomy feedback capture.
Provides persistent audit trail and upsert semantics on (response_id, actor_id).
"""

from __future__ import annotations

import datetime
import json
import logging
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.engine import config

logger = logging.getLogger("app.db.feedback")


class FeedbackStore:
    """Thread-safe SQLite store for response feedback."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is not None:
            self.db_path = db_path
        else:
            # Stored under logs/feedback.db
            self.db_path = config.LOG_DIR / "feedback.db"
        self._lock = threading.RLock()
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create a sqlite connection with Row row_factory."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Ensure response_feedback table and indices exist."""
        with self._lock:
            with self.get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS response_feedback (
                        feedback_id         TEXT PRIMARY KEY,
                        response_id         TEXT NOT NULL,
                        interaction_id      TEXT NOT NULL,
                        session_id          TEXT NOT NULL,
                        turn_number         INTEGER NOT NULL,
                        query_text          TEXT,
                        actor_id            TEXT,
                        actor_role          TEXT,
                        selected_categories TEXT NOT NULL,
                        free_text           TEXT,
                        client_timestamp   TEXT,
                        created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                        updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
                        UNIQUE(response_id, actor_id)
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_response
                    ON response_feedback(response_id);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_session
                    ON response_feedback(session_id);
                """)
                conn.commit()
        logger.info("Feedback SQLite store initialized at %s", self.db_path)

    def upsert_feedback(
        self,
        response_id: str,
        interaction_id: str,
        session_id: str,
        turn_number: int,
        selected_categories: list[str],
        query_text: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        free_text: Optional[str] = None,
        client_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upsert a feedback submission.
        Treats (response_id, actor_id) as natural key.
        """
        effective_actor = (actor_id or "").strip() or session_id
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        categories_json = json.dumps(selected_categories)

        with self._lock:
            with self.get_connection() as conn:
                existing = conn.execute(
                    "SELECT feedback_id FROM response_feedback WHERE response_id = ? AND actor_id = ?",
                    (response_id, effective_actor),
                ).fetchone()

                if existing:
                    feedback_id = existing["feedback_id"]
                    conn.execute(
                        """
                        UPDATE response_feedback
                        SET interaction_id = ?,
                            session_id = ?,
                            turn_number = ?,
                            query_text = coalesce(?, query_text),
                            actor_role = coalesce(?, actor_role),
                            selected_categories = ?,
                            free_text = ?,
                            client_timestamp = coalesce(?, client_timestamp),
                            updated_at = ?
                        WHERE feedback_id = ?
                        """,
                        (
                            interaction_id,
                            session_id,
                            turn_number,
                            query_text,
                            actor_role,
                            categories_json,
                            free_text,
                            client_timestamp,
                            now,
                            feedback_id,
                        ),
                    )
                else:
                    feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
                    conn.execute(
                        """
                        INSERT INTO response_feedback (
                            feedback_id, response_id, interaction_id, session_id,
                            turn_number, query_text, actor_id, actor_role,
                            selected_categories, free_text, client_timestamp,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            feedback_id,
                            response_id,
                            interaction_id,
                            session_id,
                            turn_number,
                            query_text,
                            effective_actor,
                            actor_role or "Compliance & Regulatory Officer",
                            categories_json,
                            free_text,
                            client_timestamp,
                            now,
                            now,
                        ),
                    )
                conn.commit()

        return {
            "feedback_id": feedback_id,
            "response_id": response_id,
            "stored_at": now,
            "status": "recorded",
        }

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        categories = []
        raw_cats = row["selected_categories"]
        if raw_cats:
            try:
                categories = json.loads(raw_cats)
            except Exception:
                categories = []

        return {
            "feedback_id": row["feedback_id"],
            "response_id": row["response_id"],
            "interaction_id": row["interaction_id"],
            "session_id": row["session_id"],
            "turn_number": row["turn_number"],
            "query_text": row["query_text"],
            "actor_id": row["actor_id"],
            "actor_role": row["actor_role"],
            "selected_categories": categories,
            "free_text": row["free_text"],
            "client_timestamp": row["client_timestamp"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_by_response_id(self, response_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            with self.get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM response_feedback WHERE response_id = ? ORDER BY updated_at DESC",
                    (response_id,),
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]

    def get_by_session_id(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            with self.get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM response_feedback WHERE session_id = ? ORDER BY turn_number ASC, updated_at DESC",
                    (session_id,),
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]

    def list_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            with self.get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM response_feedback ORDER BY updated_at DESC LIMIT ?",
                    (max(1, min(limit, 500)),),
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]


_store_instance: Optional[FeedbackStore] = None


def get_feedback_store() -> FeedbackStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = FeedbackStore()
    return _store_instance
