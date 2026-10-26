"""
SQLiteEvidenceAdapter — production implementation.

Reads from AMC's query_evidence table and session query logs to:
1. Fetch frozen evidence snapshots (point-in-time copies)
2. Retrieve follow-up queries within a time window
3. Validate response existence

This adapter decouples the feedback-loop from AMC's internal schema
— all reads go through this interface.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import and_, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from feedback_loop.adapters.evidence import AbstractEvidenceAdapter
from feedback_loop.domain_models import (
    EvidenceChunk,
    EvidenceSnapshot,
    FollowUpQuery,
)

logger = structlog.get_logger(__name__)


class SQLiteEvidenceAdapter(AbstractEvidenceAdapter):
    """
    Production evidence adapter reading from AMC's database tables.

    Assumes:
      - query_evidence table with response metadata + context
      - query_log (or similar) table with user queries per session
      - ResponseMetadataCache for fast existence checks (optional)

    Usage:
        from feedback_loop.adapters.sqlite_evidence_adapter import SQLiteEvidenceAdapter

        evidence = SQLiteEvidenceAdapter(db_url="sqlite:///amc.db")
        snapshot = evidence.get_evidence_snapshot(response_id)
        followups = evidence.get_followup_activity(session_id, response_id, window_minutes=30)
    """

    def __init__(self, db_url: str = "sqlite:///amc.db") -> None:
        """
        Initialize with database connection.

        Args:
            db_url: SQLAlchemy connection string to AMC's database
        """
        self._engine = create_engine(db_url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine)
        self._log = logger.bind(adapter="sqlite_evidence")

    def get_evidence_snapshot(self, response_id: str) -> EvidenceSnapshot:
        """
        Fetch and freeze the evidence for a given response.

        Reads from query_evidence table and creates an immutable snapshot
        of the response + context at the moment of ingestion.

        Args:
            response_id: Response UUID to fetch evidence for

        Returns:
            EvidenceSnapshot: Frozen copy of response + evidence

        Raises:
            KeyError: If response_id not found in query_evidence
        """
        from feedback_loop.models import QueryEvidence

        with self._session_factory() as session:
            row = session.query(QueryEvidence).filter(
                QueryEvidence.response_id == response_id
            ).first()

        if row is None:
            self._log.warning("response_not_found", response_id=response_id)
            raise KeyError(f"No interaction_evidence snapshot found for response_id={response_id}")

        # Extract evidence chunks from assembled_context_json
        evidence_selected = self._extract_evidence_chunks(row.assembled_context_json)

        # Extract entity name from response (if available)
        entity_name = self._extract_entity_name(row.synthesis_output_json)

        # Freeze snapshot
        snapshot = EvidenceSnapshot(
            response_id=response_id,
            original_query=row.query_text or "",
            response_text=row.synthesis_output_json.get("response_text", "") if isinstance(row.synthesis_output_json, dict) else "",
            entity_name=entity_name,
            evidence_selected=evidence_selected,
        )

        self._log.info(
            "evidence_snapshot_frozen",
            response_id=response_id,
            evidence_chunk_count=len(evidence_selected),
        )
        return snapshot

    def get_followup_activity(
        self,
        session_id: str,
        response_id: str,
        window_minutes: int,
    ) -> list[FollowUpQuery]:
        """
        Fetch follow-up queries in the same session within a time window.

        Queries are ordered by created_at ascending (chronological).

        Args:
            session_id: User session UUID
            response_id: Response UUID (to find its timestamp)
            window_minutes: Look for queries within N minutes after response

        Returns:
            list[FollowUpQuery]: Chronologically ordered follow-up queries,
                               empty list if none found
        """
        from feedback_loop.models import QueryEvidence

        # Step 1: Find the response timestamp
        with self._session_factory() as session:
            response_row = session.query(QueryEvidence).filter(
                QueryEvidence.response_id == response_id
            ).first()

        if response_row is None:
            self._log.debug("response_not_found_for_followup", response_id=response_id)
            return []

        # Parse created_at (stored as ISO string in DB)
        if isinstance(response_row.created_at, str):
            response_time = datetime.fromisoformat(response_row.created_at)
        else:
            response_time = response_row.created_at

        # Step 2: Find queries in the time window
        # NOTE: This assumes a query_log or query_events table exists
        # If your schema differs, adjust the table name and column names
        window_start = response_time
        window_end = response_time + timedelta(minutes=window_minutes)

        with self._session_factory() as session:
            # Try to fetch from query_log table (adjust if your table is named differently)
            try:
                from feedback_loop.models import QueryLog
            except ImportError:
                self._log.warning("QueryLog table not found, returning empty followups")
                return []

            followup_rows = session.query(QueryLog).filter(
                and_(
                    QueryLog.session_id == session_id,
                    QueryLog.created_at >= window_start.isoformat() if isinstance(window_start, datetime) else window_start,
                    QueryLog.created_at <= window_end.isoformat() if isinstance(window_end, datetime) else window_end,
                )
            ).order_by(QueryLog.created_at.asc()).all()

        if not followup_rows:
            self._log.debug(
                "no_followup_queries",
                session_id=session_id,
                response_id=response_id,
                window_minutes=window_minutes,
            )
            return []

        # Convert to Pydantic FollowUpQuery
        followups = [
            FollowUpQuery(
                query_id=row.query_id or row.response_id,  # Fallback if query_id missing
                text=row.query_text or row.text,
                created_at=datetime.fromisoformat(row.created_at) if isinstance(row.created_at, str) else row.created_at,
            )
            for row in followup_rows
        ]

        self._log.info(
            "followup_queries_found",
            session_id=session_id,
            count=len(followups),
            window_minutes=window_minutes,
        )
        return followups

    def validate_response_exists(self, response_id: str) -> bool:
        """
        Fast existence check for a response.

        In production, this would ideally hit a ResponseMetadataCache
        (24h TTL) for ~1ms lookups. Falls back to query_evidence table.

        Args:
            response_id: Response to check

        Returns:
            True if response exists, False otherwise
        """
        from feedback_loop.models import QueryEvidence

        with self._session_factory() as session:
            count = session.query(QueryEvidence).filter(
                QueryEvidence.response_id == response_id
            ).count()

        exists = count > 0
        self._log.debug("response_exists_check", response_id=response_id, exists=exists)
        return exists

    # -- Private helpers --

    def _extract_evidence_chunks(self, assembled_context_json: dict | list | None) -> list[EvidenceChunk]:
        """Extract evidence chunks from assembled_context_json.

        Transforms:
            assembled_context_json = {
                "context_items": [
                    {"chunk_id": "c1", "value": "...", "source_version": "v1"},
                    ...
                ]
            }

        Into:
            [EvidenceChunk(chunk_id="c1", value="...", source_version="v1"), ...]

        Args:
            assembled_context_json (dict | list | None): The assembled context json.

        Returns:
            list[EvidenceChunk]: List of resulting items or records.
        """
        if not assembled_context_json:
            return []

        if isinstance(assembled_context_json, str):
            try:
                assembled_context_json = json.loads(assembled_context_json)
            except json.JSONDecodeError:
                self._log.warning("failed_to_parse_assembled_context")
                return []

        if not isinstance(assembled_context_json, dict):
            return []

        # Extract context_items array
        context_items = assembled_context_json.get("context_items", [])
        if not context_items:
            return []

        chunks = []
        for item in context_items:
            if not isinstance(item, dict):
                continue

            chunk = EvidenceChunk(
                chunk_id=item.get("chunk_id", ""),
                value=item.get("value"),
                source_version=item.get("source_version"),
                content=item.get("content"),
            )
            chunks.append(chunk)

        return chunks

    def _extract_entity_name(self, synthesis_output_json: dict | list | None) -> Optional[str]:
        """Extract entity name from response synthesis output.

        Looks for patterns like:
            {"entity": "Axis Bluechip", "entity_name": "Axis Bluechip", ...}

        Returns:
            Entity name if found, None otherwise

        Args:
            synthesis_output_json (dict | list | None): The synthesis output json.
        """
        if not synthesis_output_json or not isinstance(synthesis_output_json, dict):
            return None

        # Try common field names
        for key in ["entity", "entity_name", "fund_name", "fund", "entity_mentioned"]:
            if key in synthesis_output_json:
                value = synthesis_output_json[key]
                if isinstance(value, str) and value.strip():
                    return value

        return None
