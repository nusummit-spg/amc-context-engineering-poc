"""
SQLite concrete implementation of AbstractDatabaseAdapter.

Translates the module's persistence contract into SQLAlchemy ORM operations
against the compliance_audit.db tables:
  - response_feedback           source of FeedbackRecord rows
  - unified_evaluation_records  destination for built records

The module Pydantic models (FeedbackRecord, UnifiedEvaluationRecord) are
kept entirely separate from the SQLAlchemy ORM models; this adapter is the
translation layer between the two.

Usage
-----
    from feedback_loop.adapters.sqlite.db_adapter import SQLiteDatabaseAdapter

    adapter = SQLiteDatabaseAdapter(db_url="sqlite:///path/to/compliance_audit.db")
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session, sessionmaker

# ORM models (SQLAlchemy) -- live in src/feedback_loop/models.py
from feedback_loop.models import (
    ResponseFeedback as ORM_ResponseFeedback,
    UnifiedEvaluationRecord as ORM_UnifiedEvaluationRecord,
)

import feedback_loop.domain_models as dm
from feedback_loop.adapters.db import AbstractDatabaseAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(value: str | None) -> datetime:
    """Parse an ISO timestamp string into a timezone-aware datetime.

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


def _resolve_feedback_type(
    categories: list,
    automated_category: str | None,
) -> dm.FeedbackType:
    """Resolve the best FeedbackType from the available category signals.

    Priority:
      1. automated_category  -- set by the system classifier; highest confidence
      2. selected_categories -- user-picked tags; first matching enum value wins
      3. FeedbackType.OTHER  -- safe fallback when nothing matches

    selected_categories is a JSON list of arbitrary UI strings
    (e.g. ["wrong_number", "hallucination"]).  We normalise each entry to
    lowercase and try it against the enum, taking the first hit.

    Args:
        categories (list): Collection or list of categories.
        automated_category (str | None): The automated category.

    Returns:
        dm.FeedbackType: Resulting dm.FeedbackType instance.
    """
    candidates: list[str] = []
    if automated_category:
        candidates.append(automated_category.strip().lower())
    candidates.extend(str(c).strip().lower() for c in (categories or []))

    for candidate in candidates:
        try:
            return dm.FeedbackType(candidate)
        except ValueError:
            continue

    return dm.FeedbackType.OTHER


def _resolve_notes(row: ORM_ResponseFeedback) -> str | None:
    """Return the feedback text, hard-capped at 2000 chars to satisfy the
    Pydantic max_length constraint.

    feedback_text is the authoritative column where user feedback is stored.
    free_text is kept as a fallback for rows inserted before the schema
    update added feedback_text.

    Preference order:
      1. feedback_text  -- primary: where feedback is stored
      2. free_text      -- fallback: legacy column
      3. None           -- passive row with no text submitted

    Args:
        row (ORM_ResponseFeedback): The row.

    Returns:
        str | None: Resulting str | None instance.
    """
    raw = row.feedback_text or row.free_text or None
    if raw is None:
        return None
    return raw[:2000]


def _resolve_corrections(row: ORM_ResponseFeedback) -> dict | None:
    """Build the corrections dict the pipeline uses for structured entity/value
    corrections.  When this is non-None, Step 1 (ClassificationService) skips
    NER extraction because explicit structured data already exists.

    Sources tried in order:
      1. classification_json -- pre-filled by an upstream classifier
      2. feedback_span       -- JSON-encoded span the user highlighted
         Expected shape: {"proposed_entity": "...", "proposed_value": "..."}
      3. None

    Args:
        row (ORM_ResponseFeedback): The row.

    Returns:
        dict | None: Dictionary containing result data or status.
    """
    if isinstance(row.classification_json, dict) and row.classification_json:
        return row.classification_json

    if row.feedback_span:
        try:
            parsed = json.loads(row.feedback_span)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except (ValueError, TypeError):
            pass

    return None


# ---------------------------------------------------------------------------
# Main mapping function
# ---------------------------------------------------------------------------

def _orm_to_feedback_record(row: ORM_ResponseFeedback) -> dm.FeedbackRecord:
    """Translate one ResponseFeedback ORM row into the Pydantic FeedbackRecord
    the pipeline expects.

    Column -> field mapping
    --------------------------------------------------------------------------
    feedback_id          -> feedback_id     (PK, pass-through)
    response_id          -> response_id
    session_id           -> session_id
    actor_id             -> user_id
    created_at           -> received_at     (server-side write time)
    client_timestamp     -> timestamp       (client-supplied; may be None)

    source  (derived from actor_role):
      "system"         -> FeedbackSource.PASSIVE  (silent system capture)
      anything / None  -> FeedbackSource.ACTIVE   (human submitted)

    feedback_type  (resolved via _resolve_feedback_type):
      automated_category > selected_categories[*] > OTHER
      Tries each candidate against the FeedbackType enum, first match wins.

    notes  (resolved via _resolve_notes, capped at 2000 chars):
      feedback_text > free_text > None

    corrections  (resolved via _resolve_corrections):
      classification_json > feedback_span (parsed JSON) > None
      Non-None value causes Step 1 to skip NER entirely.

    entity_name / entity_type:
      Always None -- populated by Step 1 NER against notes/response_text.
      The ORM row has no dedicated entity columns.

    ingestion_status  (derived from unified_record_ref):
      IS NOT NULL -> SENT    (already processed; retry sweep ignores it)
      IS NULL     -> PENDING (needs processing)

    rating:
      response_feedback has no rating column; pipeline receives UNRATED.
    --------------------------------------------------------------------------

    Args:
        row (ORM_ResponseFeedback): The row.

    Returns:
        dm.FeedbackRecord: Resulting dm.FeedbackRecord instance.
    """
    actor_role = (row.actor_role or "").lower()
    source = (
        dm.FeedbackSource.PASSIVE
        if actor_role == "system"
        else dm.FeedbackSource.ACTIVE
    )

    feedback_type = _resolve_feedback_type(
        categories=row.selected_categories or [],
        automated_category=row.automated_category,
    )

    notes = _resolve_notes(row)
    corrections = _resolve_corrections(row)

    ingestion_status = (
        dm.IngestionStatus.SENT
        if row.unified_record_ref
        else dm.IngestionStatus.PENDING
    )

    return dm.FeedbackRecord(
        feedback_id=row.feedback_id,
        response_id=row.response_id,
        session_id=row.session_id,
        user_id=row.actor_id,
        rating=dm.RatingType.UNRATED,    # no rating column in ORM schema
        feedback_type=feedback_type,
        entity_name=None,                # populated by Step 1 NER
        entity_type=None,
        notes=notes,
        corrections=corrections,
        source=source,
        received_at=_parse_dt(row.created_at),
        timestamp=_parse_dt(row.client_timestamp) if row.client_timestamp else None,
        ingestion_status=ingestion_status,
    )


# ---------------------------------------------------------------------------
# ORM -> Pydantic for unified_evaluation_records
# ---------------------------------------------------------------------------

def _pydantic_to_orm_unified(
    record: dm.UnifiedEvaluationRecord,
) -> ORM_UnifiedEvaluationRecord:
    """Map the Pydantic UnifiedEvaluationRecord to the SQLAlchemy ORM model.

    Args:
        record (dm.UnifiedEvaluationRecord): The record.

    Returns:
        ORM_UnifiedEvaluationRecord: Resulting ORM_UnifiedEvaluationRecord instance.
    """
    return ORM_UnifiedEvaluationRecord(
        session_id=record.session_id,
        response_id=record.response_id,
        entry_route=record.entry_route,
        feedback_ref=record.feedback_ref,
        evidence_snapshot_ref=record.evidence_snapshot_ref,
        root_cause=record.root_cause,
        severity=record.severity,
        lifecycle_status=record.lifecycle_status,
        dissatisfaction_evidence_json=record.dissatisfaction_evidence,
        repair=getattr(record, "repair", False),
        repair_target=getattr(record, "repair_target", None),
        deterministic_results=record.deterministic_results,
        gnn_plausibility_score=record.gnn_plausibility_score,
        semantic_results=record.semantic_results,
        llm_evaluation=record.llm_evaluation,
        adjudication_verdict=record.adjudication_verdict,
        adjudication_confidence=record.adjudication_confidence,
        created_by="feedback_loop_module",
    )


# ---------------------------------------------------------------------------
# Adapter class
# ---------------------------------------------------------------------------

class SQLiteDatabaseAdapter(AbstractDatabaseAdapter):
    """
    Concrete AbstractDatabaseAdapter backed by SQLite via SQLAlchemy.

    Pass the same db_url used by the rest of the application so all writes
    share a single connection pool.

    Thread safety: each public method opens and closes its own session.
    This is safe for the ThreadPoolExecutor used by RecordBuilder (steps
    1 and 2 run concurrently on different rows of data, never sharing a
    session).
    """

    def __init__(self, db_url: str) -> None:
        """Initialize a new instance of SQLiteDatabaseAdapter.

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

    def _session(self) -> Session:
        """Session.

        Returns:
            Session: Resulting Session instance.
        """
        return self._Session()

    # -----------------------------------------------------------------------
    # feedback_records  (backed by response_feedback table)
    # -----------------------------------------------------------------------

    def fetch_feedback_record(self, feedback_id: str) -> dm.FeedbackRecord:
        """Look up a response_feedback row by its primary key and return a
        fully populated Pydantic FeedbackRecord.

        Raises KeyError when feedback_id does not exist so IngestService
        can surface the error immediately rather than failing deep in the
        pipeline.

        The translation from ORM to Pydantic is done by _orm_to_feedback_record;
        see that function for the complete field-by-field mapping.

        Args:
            feedback_id (str): Unique identifier of the feedback.

        Returns:
            dm.FeedbackRecord: Resulting dm.FeedbackRecord instance.
        """
        with self._session() as session:
            row = session.get(ORM_ResponseFeedback, feedback_id)
            if row is None:
                raise KeyError(
                    f"response_feedback row not found: feedback_id={feedback_id!r}"
                )
            return _orm_to_feedback_record(row)

    def update_ingestion_status(
        self, feedback_id: str, status: dm.IngestionStatus
    ) -> None:
        """The response_feedback table has no ingestion_status column.
        Delivery state is tracked implicitly via unified_record_ref:
          unified_record_ref IS NULL     -> PENDING
          unified_record_ref IS NOT NULL -> SENT (written by write_unified_record)

        This method is intentionally a no-op.  Add an ingestion_status
        column to response_feedback and fill in the UPDATE if you need
        explicit status tracking.

        Args:
            feedback_id (str): Unique identifier of the feedback.
            status (dm.IngestionStatus): Target status value.
        """

    def fetch_pending_feedback_records(
        self, older_than_minutes: int = 5
    ) -> list[dm.FeedbackRecord]:
        """Return rows that have never been successfully processed
        (unified_record_ref IS NULL) and are older than the threshold.

        Used by IngestService.retry_sweep() to reprocess rows whose first
        pipeline attempt failed or whose webhook was never delivered.

        Args:
            older_than_minutes (int): Collection or list of older than minutes.

        Returns:
            list[dm.FeedbackRecord]: List of resulting items or records.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        ).isoformat()

        with self._session() as session:
            stmt = (
                select(ORM_ResponseFeedback)
                .where(
                    ORM_ResponseFeedback.unified_record_ref.is_(None),
                    ORM_ResponseFeedback.created_at <= cutoff,
                )
                .order_by(ORM_ResponseFeedback.created_at)
            )
            rows = session.scalars(stmt).all()
            return [_orm_to_feedback_record(r) for r in rows]

    # -----------------------------------------------------------------------
    # unified_evaluation_records
    # -----------------------------------------------------------------------

    def write_unified_record(self, record: dm.UnifiedEvaluationRecord) -> None:
        """Insert one unified_evaluation_records row and back-fill
        unified_record_ref + root_cause on the originating response_feedback
        row so the retry sweep treats it as processed.

        Args:
            record (dm.UnifiedEvaluationRecord): The record.
        """
        with self._session() as session:
            session.add(_pydantic_to_orm_unified(record))
            session.flush()  # Flush insert to DB before FK update

            if record.feedback_ref:
                session.execute(
                    update(ORM_ResponseFeedback)
                    .where(ORM_ResponseFeedback.feedback_id == record.feedback_ref)
                    .values(
                        unified_record_ref=record.response_id,
                        root_cause=record.root_cause,
                    )
                )

            session.commit()

    def find_open_cluster(
        self, response_id: str, entity_name: Optional[str]
    ) -> Optional[dm.UnifiedEvaluationRecord]:
        """Return the open unified_evaluation_records row for this response_id,
        or None if no cluster exists.  Used by RecordBuilder to short-circuit
        duplicate feedback rows for the same response.

        Args:
            response_id (str): Unique identifier of the response.
            entity_name (Optional[str]): Name of the entity.

        Returns:
            Optional[dm.UnifiedEvaluationRecord]: Matching object or record if found, None otherwise.
        """
        with self._session() as session:
            stmt = select(ORM_UnifiedEvaluationRecord).where(
                ORM_UnifiedEvaluationRecord.response_id == response_id,
                ORM_UnifiedEvaluationRecord.lifecycle_status == "open",
            )
            row = session.scalars(stmt).first()
            if row is None:
                return None
            return dm.UnifiedEvaluationRecord(
                session_id=row.session_id,
                response_id=row.response_id,
                entry_route=row.entry_route,
                evidence_snapshot_ref=row.evidence_snapshot_ref,
                lifecycle_status=row.lifecycle_status,
                root_cause=row.root_cause,
            )

    def unified_record_exists(self, response_id: str) -> bool:
        """True if a unified_evaluation_records row already exists for this response.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        with self._session() as session:
            stmt = select(ORM_UnifiedEvaluationRecord.response_id).where(
                ORM_UnifiedEvaluationRecord.response_id == response_id
            )
            return session.scalars(stmt).first() is not None
