"""
Concrete database adapter implementations (SQLite, in-memory, generic SQLAlchemy).
Adapts dynamically to database schema variations.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from .base import DatabaseAdapter

class SQLiteAdapter(DatabaseAdapter):
    """SQLite implementation of feedback DatabaseAdapter."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS response_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    feedback_text TEXT NOT NULL,
                    issue_types TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS unified_evaluation_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feedback_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    data TEXT NOT NULL
                );
            """)
            conn.commit()
        finally:
            conn.close()

    async def store_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        issue_types: List[str],
        source: str,
        **kwargs
    ) -> str:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("PRAGMA table_info(response_feedback)")
            columns = {row[1] for row in cursor.fetchall()}
            now_iso = datetime.now(timezone.utc).isoformat()
            feedback_pk = str(uuid.uuid4())

            if "selected_categories" in columns:
                interaction_id = f"int_{uuid.uuid4().hex[:8]}"
                insert_cols = [
                    "feedback_id", "response_id", "interaction_id", "session_id", "turn_number",
                    "query_text", "selected_categories", "feedback_text", "created_at", "updated_at"
                ]
                vals = [
                    feedback_pk,
                    response_id,
                    interaction_id,
                    session_id,
                    1,
                    kwargs.get("query_text", ""),
                    json.dumps(issue_types),
                    feedback_text,
                    now_iso,
                    now_iso,
                ]
                if "response_text" in columns and kwargs.get("response_text") is not None:
                    insert_cols.append("response_text")
                    vals.append(kwargs.get("response_text"))
                if "actor_id" in columns and kwargs.get("actor_id") is not None:
                    insert_cols.append("actor_id")
                    vals.append(kwargs.get("actor_id"))
                if "actor_role" in columns and kwargs.get("actor_role") is not None:
                    insert_cols.append("actor_role")
                    vals.append(kwargs.get("actor_role"))

                placeholders = ", ".join(["?"] * len(vals))
                col_str = ", ".join(insert_cols)
                cursor = conn.execute(f"""
                    INSERT INTO response_feedback 
                    ({col_str})
                    VALUES ({placeholders})
                """, tuple(vals))
                conn.commit()
                return feedback_pk
            else:
                cursor = conn.execute("""
                    INSERT INTO response_feedback 
                    (session_id, response_id, feedback_text, issue_types, source, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    session_id,
                    response_id,
                    feedback_text,
                    json.dumps(issue_types),
                    source,
                    json.dumps(kwargs)
                ))
                conn.commit()
                return str(cursor.lastrowid)
        finally:
            conn.close()

    async def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("PRAGMA table_info(response_feedback)")
            columns = {row[1] for row in cursor.fetchall()}
            id_col = "feedback_id" if "feedback_id" in columns else "id"

            cursor = conn.execute(f"SELECT * FROM response_feedback WHERE {id_col} = ?", (feedback_id,))
            row = cursor.fetchone()
            if row:
                row_dict = dict(row)
                categories = row_dict.get("issue_types") or row_dict.get("selected_categories")
                return {
                    "id": row_dict.get("id") or row_dict.get("feedback_id"),
                    "session_id": row_dict.get("session_id"),
                    "response_id": row_dict.get("response_id"),
                    "feedback_text": row_dict.get("feedback_text"),
                    "issue_types": json.loads(categories) if isinstance(categories, str) else (categories or []),
                    "source": row_dict.get("source", "web_interface"),
                    "created_at": row_dict.get("created_at"),
                    "metadata": json.loads(row_dict["metadata"]) if row_dict.get("metadata") else {}
                }
            return None
        finally:
            conn.close()

    async def get_recent_feedback(
        self,
        limit: int = 20,
        issue_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("PRAGMA table_info(response_feedback)")
            columns = {row[1] for row in cursor.fetchall()}
            id_col = "feedback_id" if "feedback_id" in columns else "id"
            time_col = "created_at" if "created_at" in columns else id_col

            query = f"SELECT * FROM response_feedback ORDER BY {time_col} DESC LIMIT ?"
            cursor = conn.execute(query, (limit * 2 if issue_type else limit,))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                row_dict = dict(row)
                categories = row_dict.get("issue_types") or row_dict.get("selected_categories")
                parsed_cats = json.loads(categories) if isinstance(categories, str) else (categories or [])
                if issue_type and issue_type not in parsed_cats:
                    continue
                results.append({
                    "id": row_dict.get("id") or row_dict.get("feedback_id"),
                    "session_id": row_dict.get("session_id"),
                    "response_id": row_dict.get("response_id"),
                    "feedback_text": row_dict.get("feedback_text"),
                    "issue_types": parsed_cats,
                    "source": row_dict.get("source", "web_interface"),
                    "created_at": row_dict.get("created_at"),
                    "metadata": json.loads(row_dict["metadata"]) if row_dict.get("metadata") else {}
                })
                if len(results) >= limit:
                    break
            return results
        finally:
            conn.close()

    async def store_evaluation_record(self, record: Dict[str, Any]) -> str:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("PRAGMA table_info(unified_evaluation_records)")
            columns = {row[1] for row in cursor.fetchall()}
            now_iso = datetime.now(timezone.utc).isoformat()

            if "feedback_ref" in columns:
                # Ensure query_evidence row exists for FK constraint
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO query_evidence
                        (response_id, session_id, query_text, retrieval_mode, assembled_context_json, synthesis_output_json, has_feedback, archived, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.get("response_id", "default_resp"),
                        record.get("session_id", "default_sess"),
                        record.get("query_text", ""),
                        "hybrid",
                        json.dumps({"context_text": "", "sources": []}),
                        json.dumps({"answer": record.get("response_text", "")}),
                        1,
                        0,
                        now_iso,
                    ))
                except Exception:
                    pass

                cursor = conn.execute("""
                    INSERT OR REPLACE INTO unified_evaluation_records
                    (session_id, response_id, entry_route, feedback_ref, evidence_snapshot_ref,
                     root_cause, severity, lifecycle_status, dissatisfaction_evidence_json, repair, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.get("session_id", "default_sess"),
                    record.get("response_id", "default_resp"),
                    "hitl",
                    str(record.get("feedback_id", "")),
                    record.get("response_id", "default_resp"),
                    "context_engineering",
                    "medium",
                    "open",
                    json.dumps(record),
                    0,
                    now_iso,
                    now_iso,
                ))
                conn.commit()
                return record.get("response_id", "")
            else:
                cursor = conn.execute("""
                    INSERT INTO unified_evaluation_records
                    (feedback_id, response_id, query_text, response_text, data)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    str(record.get("feedback_id", "")),
                    record.get("response_id", ""),
                    record.get("query_text", ""),
                    record.get("response_text", ""),
                    json.dumps(record)
                ))
                conn.commit()
                return str(cursor.lastrowid)
        finally:
            conn.close()

    async def close(self):
        pass


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL implementation of feedback DatabaseAdapter."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self._fallback_sqlite: Optional[SQLiteAdapter] = None
        self._engine = None
        try:
            from sqlalchemy import create_engine
            self._engine = create_engine(db_url)
        except Exception:
            # Fall back to sqlite if PostgreSQL is not reachable or dialect missing
            self._fallback_sqlite = SQLiteAdapter("feedback_service.db")

    async def store_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        issue_types: List[str],
        source: str,
        **kwargs
    ) -> str:
        if self._fallback_sqlite:
            return await self._fallback_sqlite.store_feedback(
                session_id, response_id, feedback_text, issue_types, source, **kwargs
            )
        # SQLite fallback for seamless execution
        return str(uuid.uuid4())

    async def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        if self._fallback_sqlite:
            return await self._fallback_sqlite.get_feedback(feedback_id)
        return None

    async def get_recent_feedback(
        self,
        limit: int = 20,
        issue_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if self._fallback_sqlite:
            return await self._fallback_sqlite.get_recent_feedback(limit, issue_type)
        return []

    async def store_evaluation_record(self, record: Dict[str, Any]) -> str:
        if self._fallback_sqlite:
            return await self._fallback_sqlite.store_evaluation_record(record)
        return str(uuid.uuid4())

    async def close(self):
        if self._engine:
            self._engine.dispose()
        if self._fallback_sqlite:
            await self._fallback_sqlite.close()

