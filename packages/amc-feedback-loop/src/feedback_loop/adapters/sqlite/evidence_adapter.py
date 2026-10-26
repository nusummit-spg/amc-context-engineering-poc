"""
SQLite concrete implementation of AbstractEvidenceAdapter.

Reads from:
  - query_evidence   → EvidenceSnapshot  (get_evidence_snapshot)
  - query_evidence   → FollowUpQuery list (get_followup_activity)
  - query_evidence   → existence check    (validate_response_exists)

The query_evidence table stores the full frozen D0-D3 context (assembled
context JSON, synthesis output) per response_id. The assembled_context_json
column holds the retrieved chunks; synthesis_output_json holds the generated
response text.

Usage
-----
    from feedback_loop.adapters.sqlite.evidence_adapter import SQLiteEvidenceAdapter

    adapter = SQLiteEvidenceAdapter(db_url="sqlite:///path/to/compliance_audit.db")
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from feedback_loop.models import QueryEvidence as ORM_QueryEvidence
from feedback_loop.adapters.evidence import AbstractEvidenceAdapter
import feedback_loop.domain_models as dm


def _parse_dt(value: str | None) -> datetime:
    """Parse dt.

    Args:
        value (str | None): The value.

    Returns:
        datetime: Resulting datetime instance.
    """
    if value is None:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _chunks_from_context(assembled_context_json) -> list[dm.EvidenceChunk]:
    """Extract EvidenceChunks from the assembled_context_json column.

    Expected shape (flexible — handles both list and dict wrappers):
        [{"id": "C_001", "snippet": "...", "source_version": "v1"}, ...]
    or
        {"sources": [{"id": "C_001", "snippet": "...", ...}], ...}

    Args:
        assembled_context_json: The assembled context json.

    Returns:
        list[dm.EvidenceChunk]: List of resulting items or records.
    """
    if assembled_context_json is None:
        return []

    sources: list = []
    if isinstance(assembled_context_json, list):
        sources = assembled_context_json
    elif isinstance(assembled_context_json, dict):
        sources = assembled_context_json.get("sources", [])

    chunks = []
    for i, src in enumerate(sources):
        if not isinstance(src, dict):
            continue
        chunks.append(
            dm.EvidenceChunk(
                chunk_id=str(src.get("id", src.get("chunk_id", f"chunk_{i}"))),
                value=src.get("value") or src.get("snippet"),
                source_version=src.get("source_version"),
                content=src.get("content") or src.get("snippet"),
            )
        )
    return chunks


def _response_text_from_synthesis(synthesis_output_json) -> str:
    """Extract the generated response text from synthesis_output_json.

    Expected shape:
        {"answer": "...", "confidence": 0.9, ...}
    or
        "plain string"

    Args:
        synthesis_output_json: The synthesis output json.

    Returns:
        str: Resulting str instance.
    """
    if synthesis_output_json is None:
        return ""
    if isinstance(synthesis_output_json, str):
        return synthesis_output_json
    if isinstance(synthesis_output_json, dict):
        return (
            synthesis_output_json.get("answer")
            or synthesis_output_json.get("response")
            or synthesis_output_json.get("text")
            or ""
        )
    return ""


class SQLiteEvidenceAdapter(AbstractEvidenceAdapter):
    """
    Concrete AbstractEvidenceAdapter reading from the query_evidence table.

    Thread safety: each method opens its own session, matching the pattern
    in SQLiteDatabaseAdapter.
    """

    def __init__(self, db_url: str) -> None:
        """Initialize a new instance of SQLiteEvidenceAdapter.

        Args:
            db_url (str): The db url.
        """
        self._engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self._engine, "connect")
        def _enable_fk(dbapi_conn, _rec):
            """Enable fk.

            Args:
                dbapi_conn: The dbapi conn.
                _rec: The  rec.
            """
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        self._Session = sessionmaker(bind=self._engine, autoflush=False, autocommit=False)

    def get_evidence_snapshot(self, response_id: str) -> dm.EvidenceSnapshot:
        """Fetch the frozen D0-D3 context for a given response_id from
        query_evidence.

        Column mapping:
          query_text              → original_query
          synthesis_output_json   → response_text (extracted)
          assembled_context_json  → evidence_selected (chunked)

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            dm.EvidenceSnapshot: Resulting dm.EvidenceSnapshot instance.
        """
        with self._Session() as session:
            row = session.get(ORM_QueryEvidence, response_id)
            if row is None:
                raise KeyError(
                    f"No query_evidence row found for response_id={response_id}"
                )

            return dm.EvidenceSnapshot(
                response_id=row.response_id,
                original_query=row.query_text,
                response_text=_response_text_from_synthesis(row.synthesis_output_json),
                entity_name=None,   # extracted by ClassificationService in Step 1
                evidence_selected=_chunks_from_context(row.assembled_context_json),
            )

    def get_followup_activity(
        self,
        session_id: str,
        response_id: str,
        window_minutes: int,
    ) -> list[dm.FollowUpQuery]:
        """Return subsequent query_evidence rows for the same session_id that
        were created within window_minutes after the reference response.

        The reference response's own created_at is used as the window start.
        Rows are ordered by created_at ascending so dissatisfaction detection
        always sees the first follow-up query first.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            window_minutes (int): Collection or list of window minutes.

        Returns:
            list[dm.FollowUpQuery]: List of resulting items or records.
        """
        with self._Session() as session:
            # Get the reference row's timestamp
            ref_row = session.get(ORM_QueryEvidence, response_id)
            if ref_row is None:
                return []

            ref_ts = _parse_dt(ref_row.created_at)
            window_end = ref_ts + timedelta(minutes=window_minutes)
            window_end_iso = window_end.isoformat()
            ref_ts_iso = ref_ts.isoformat()

            stmt = (
                select(ORM_QueryEvidence)
                .where(
                    ORM_QueryEvidence.session_id == session_id,
                    ORM_QueryEvidence.response_id != response_id,
                    ORM_QueryEvidence.created_at > ref_ts_iso,
                    ORM_QueryEvidence.created_at <= window_end_iso,
                )
                .order_by(ORM_QueryEvidence.created_at)
            )
            rows = session.scalars(stmt).all()

            return [
                dm.FollowUpQuery(
                    query_id=r.response_id,   # reuse response_id as query_id
                    text=r.query_text,
                    created_at=_parse_dt(r.created_at),
                )
                for r in rows
            ]

    def validate_response_exists(self, response_id: str) -> bool:
        """Fast existence check against the query_evidence table.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        with self._Session() as session:
            stmt = select(ORM_QueryEvidence.response_id).where(
                ORM_QueryEvidence.response_id == response_id
            )
            return session.scalars(stmt).first() is not None
