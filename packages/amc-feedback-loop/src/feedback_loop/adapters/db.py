"""
Database adapter -- abstract contract + in-memory stub.

AbstractDatabaseAdapter defines the exact persistence surface the pipeline
needs. Concrete implementations (SQLiteDatabaseAdapter, a future Postgres
adapter, etc.) inherit from it and supply real DB operations.

InMemoryDatabaseAdapter is a thread-safe dict-backed stub for tests and
local development -- it has no external dependencies.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

from feedback_loop.domain_models import (
    FeedbackRecord,
    IngestionStatus,
    LifecycleStatus,
    UnifiedEvaluationRecord,
)


# ---------------------------------------------------------------------------
# Abstract base -- defines the contract every backend must implement
# ---------------------------------------------------------------------------

class AbstractDatabaseAdapter(ABC):
    """
    Persistence contract for the Human Feedback Loop module.

    The module never builds SQL directly. All DB access goes through this
    interface so the backing store can be swapped without touching pipeline
    logic.
    """

    # -- response_feedback (source of FeedbackRecord rows) -------------------

    @abstractmethod
    def fetch_feedback_record(self, feedback_id: str) -> FeedbackRecord:
        """Retrieve the response_feedback row identified by feedback_id and
        return it as a fully populated Pydantic FeedbackRecord.

        Raises KeyError when feedback_id is not found so the caller
        (IngestService.on_ingest) surfaces the error immediately rather
        than failing deep inside the pipeline.

        Implementations are responsible for:
          - mapping ORM / raw DB columns to FeedbackRecord fields
          - deriving `source` (active vs passive)
          - deriving `ingestion_status` from whatever status signal the
            backing table provides
          - capping `notes` at 2000 chars to satisfy Pydantic max_length
          - leaving `entity_name` / `entity_type` as None (populated by
            Step 1 NER, not by the DB layer)

        Args:
            feedback_id (str): Unique identifier of the feedback.

        Returns:
            FeedbackRecord: Resulting FeedbackRecord instance.
        """
        ...

    @abstractmethod
    def update_ingestion_status(
        self, feedback_id: str, status: IngestionStatus
    ) -> None:
        """Record the delivery outcome for a feedback row.

        Called by IngestService after each on_ingest() attempt:
          - IngestionStatus.SENT   -- pipeline completed, record written
          - IngestionStatus.FAILED -- pipeline raised, row needs retry

        Implementations that track this via a dedicated column update it
        here. Implementations that derive status implicitly (e.g. checking
        whether unified_record_ref is set) may treat this as a no-op.

        Args:
            feedback_id (str): Unique identifier of the feedback.
            status (IngestionStatus): Target status value.
        """
        ...

    @abstractmethod
    def fetch_pending_feedback_records(
        self, older_than_minutes: int = 5
    ) -> list[FeedbackRecord]:
        """Return all feedback rows that have not yet been successfully
        processed and whose received_at / created_at is older than the
        given threshold.

        Used by IngestService.retry_sweep() to reprocess rows whose first
        pipeline attempt failed or whose webhook delivery was dropped.
        The caller is responsible for not reprocessing rows concurrently.

        Args:
            older_than_minutes (int): Collection or list of older than minutes.

        Returns:
            list[FeedbackRecord]: List of resulting items or records.
        """
        ...

    # -- unified_evaluation_records (destination for built records) ----------

    @abstractmethod
    def write_unified_record(self, record: UnifiedEvaluationRecord) -> None:
        """Insert one row into unified_evaluation_records.

        Called exactly once per successfully processed feedback row
        (the single-write guarantee). Implementations should raise on
        duplicate response_id rather than silently overwriting.

        Args:
            record (UnifiedEvaluationRecord): The record.
        """
        ...

    @abstractmethod
    def find_open_cluster(
        self, response_id: str, entity_name: Optional[str]
    ) -> Optional[UnifiedEvaluationRecord]:
        """Return the existing open unified_evaluation_records row for this
        response_id, or None if none exists.

        Used by RecordBuilder (Step 2) to detect duplicate feedback for
        the same response so it can short-circuit and avoid building a
        second record for the same underlying issue.

        Args:
            response_id (str): Unique identifier of the response.
            entity_name (Optional[str]): Name of the entity.

        Returns:
            Optional[UnifiedEvaluationRecord]: Matching object or record if found, None otherwise.
        """
        ...

    @abstractmethod
    def unified_record_exists(self, response_id: str) -> bool:
        """Return True if a unified_evaluation_records row already exists
        for this response_id.

        Checked by RecordBuilder before starting the 4-step build as a
        guard against double-processing on retries.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        ...


# ---------------------------------------------------------------------------
# In-memory stub -- for tests and local development only
# ---------------------------------------------------------------------------

class InMemoryDatabaseAdapter(AbstractDatabaseAdapter):
    """
    Thread-safe in-memory implementation backed by plain Python dicts.

    Intended only for unit tests and local development. Seed it before
    each test using seed_feedback() and inspect results via get_all_unified().

    Not for production use -- state is lost when the process exits.
    """

    def __init__(self) -> None:
        """Initialize a new instance of InMemoryDatabaseAdapter.
        """
        self._lock = threading.Lock()
        self._feedback: dict[str, FeedbackRecord] = {}        # feedback_id -> row
        self._unified: dict[str, UnifiedEvaluationRecord] = {}  # response_id -> row

    # -- Seeding helpers (test convenience) ----------------------------------

    def seed_feedback(self, record: FeedbackRecord) -> None:
        """Pre-load a FeedbackRecord so fetch_feedback_record can find it.

        Args:
            record (FeedbackRecord): The record.
        """
        with self._lock:
            self._feedback[record.feedback_id] = record

    def get_all_unified(self) -> list[UnifiedEvaluationRecord]:
        """Return all written UnifiedEvaluationRecords (for test assertions).

        Returns:
            list[UnifiedEvaluationRecord]: List of resulting items or records.
        """
        with self._lock:
            return list(self._unified.values())

    def fetch_unified_record(
        self, response_id: str
    ) -> Optional[UnifiedEvaluationRecord]:
        """Return the written UnifiedEvaluationRecord for response_id, or None.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            Optional[UnifiedEvaluationRecord]: Matching object or record if found, None otherwise.
        """
        with self._lock:
            return self._unified.get(response_id)

    # -- AbstractDatabaseAdapter implementation ------------------------------

    def fetch_feedback_record(self, feedback_id: str) -> FeedbackRecord:
        """Look up a pre-seeded FeedbackRecord by its feedback_id.

        In tests, rows are seeded directly via seed_feedback() with fully
        populated Pydantic models -- there is no ORM layer and no column
        mapping to do. The dict lookup is the complete implementation.

        Raises KeyError when the id is not found, matching the contract.

        Args:
            feedback_id (str): Unique identifier of the feedback.

        Returns:
            FeedbackRecord: Resulting FeedbackRecord instance.
        """
        with self._lock:
            record = self._feedback.get(feedback_id)
            if record is None:
                raise KeyError(f"feedback_record not found: {feedback_id!r}")
            return record

    def update_ingestion_status(
        self, feedback_id: str, status: IngestionStatus
    ) -> None:
        """Update the ingestion_status field on a seeded FeedbackRecord.

        Uses Pydantic model_copy so the original record is not mutated
        (important for test isolation when assertions run after the update).

        Args:
            feedback_id (str): Unique identifier of the feedback.
            status (IngestionStatus): Target status value.
        """
        with self._lock:
            if feedback_id not in self._feedback:
                raise KeyError(f"feedback_record not found: {feedback_id!r}")
            existing = self._feedback[feedback_id]
            self._feedback[feedback_id] = existing.model_copy(
                update={"ingestion_status": status}
            )

    def fetch_pending_feedback_records(
        self, older_than_minutes: int = 5
    ) -> list[FeedbackRecord]:
        """Return seeded FeedbackRecords that are PENDING or FAILED and whose
        received_at is older than older_than_minutes.

        Mirrors the retry-sweep query the SQLite adapter runs against the
        database, using the same age threshold logic.

        Args:
            older_than_minutes (int): Collection or list of older than minutes.

        Returns:
            list[FeedbackRecord]: List of resulting items or records.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        with self._lock:
            return [
                r for r in self._feedback.values()
                if r.ingestion_status in (IngestionStatus.PENDING, IngestionStatus.FAILED)
                and r.received_at <= cutoff
            ]

    def write_unified_record(self, record: UnifiedEvaluationRecord) -> None:
        """Store a built UnifiedEvaluationRecord keyed by response_id.

        Args:
            record (UnifiedEvaluationRecord): The record.
        """
        with self._lock:
            self._unified[record.response_id] = record

    def find_open_cluster(
        self, response_id: str, entity_name: Optional[str]
    ) -> Optional[UnifiedEvaluationRecord]:
        """Return the open unified record for response_id, or None.

        Args:
            response_id (str): Unique identifier of the response.
            entity_name (Optional[str]): Name of the entity.

        Returns:
            Optional[UnifiedEvaluationRecord]: Matching object or record if found, None otherwise.
        """
        with self._lock:
            existing = self._unified.get(response_id)
            if existing and existing.lifecycle_status == LifecycleStatus.OPEN:
                return existing
            return None

    def unified_record_exists(self, response_id: str) -> bool:
        """True if a unified record has been written for this response_id.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        with self._lock:
            return response_id in self._unified
