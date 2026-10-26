"""
IngestService ” entry point for the Human Feedback Loop module.

Two entry points:
  on_ingest(...)     Called by AMC's webhook immediately after insert.
  retry_sweep(...)   Called by a scheduler (e.g. every 5 min) to re-send
                     any rows still in 'pending' or 'failed' state.

Both paths converge on RecordBuilder.build() then a single DB write.
"""

from __future__ import annotations

import structlog

from feedback_loop.adapters.db import AbstractDatabaseAdapter
from feedback_loop.adapters.evidence import AbstractEvidenceAdapter
from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.domain_models import FeedbackSource, IngestionStatus
from feedback_loop.orchestrator import RecordBuilder
from feedback_loop.logging import (
    get_feedback_logger,
    log_step_info,
    log_step_warning,
    log_step_error,
)

logger = structlog.get_logger(__name__)
step_logger = get_feedback_logger("ingest")


class IngestService:
    """
    Handles webhook ingestion and the retry sweep.

    Construction is cheap ” one instance per application lifetime is fine.
    """

    def __init__(
        self,
        config: FeedbackLoopConfig,
        db: AbstractDatabaseAdapter,
        evidence_adapter: AbstractEvidenceAdapter,
    ) -> None:
        """Initialize a new instance of IngestService.

        Args:
            config (FeedbackLoopConfig): Configuration dictionary or settings object.
            db (AbstractDatabaseAdapter): Database session instance.
            evidence_adapter (AbstractEvidenceAdapter): The evidence adapter.
        """
        self._config = config
        self._db = db
        self._builder = RecordBuilder(config, db, evidence_adapter)

    #  Primary path (webhook) 

    def on_ingest(
        self,
        feedback_id: str,
        session_id: str,
        response_id: str,
        source: str,
    ) -> bool:
        """Process one feedback_records row.

        Called by AMC's webhook (active path) OR by retry_sweep (failed rows).

        Returns True on success, False when the row was a duplicate or the
        build produced no record (both are non-error outcomes).
        Raises on unrecoverable errors so the caller can mark ingestion_status='failed'.

        Args:
            feedback_id (str): Unique identifier of the feedback.
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            source (str): The source.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        log = logger.bind(
            feedback_id=feedback_id,
            session_id=session_id,
            response_id=response_id,
            source=source,
        )
        log_step_info(
            step_logger,
            "INGEST_START",
            "Feedback ingest started: feedback_id=%s, response_id=%s, source=%s",
            feedback_id,
            response_id,
            source,
        )
        log.info("ingest_started")

        # Fetch the full row  adapter raises KeyError if not found
        row = self._db.fetch_feedback_record(feedback_id)

        # Validate source matches (defensive; AMC owns the source field)
        if row.source != source:
            log_step_warning(
                step_logger,
                "SOURCE_MISMATCH",
                "Source mismatch for %s: db=%s, webhook=%s",
                feedback_id,
                row.source,
                source,
            )
            log.warning(
                "source_mismatch",
                db_source=row.source,
                webhook_source=source,
            )

        try:
            record = self._builder.build(row)
        except Exception as exc:
            self._db.update_ingestion_status(feedback_id, IngestionStatus.FAILED)
            log_step_error(
                step_logger,
                "INGEST_BUILD_FAILED",
                "Build failed for %s: %s",
                feedback_id,
                exc,
            )
            log.error("build_failed", error=str(exc))
            raise

        if record is None:
            # Duplicate or already-processed ” not an error
            log_step_info(
                step_logger,
                "INGEST_DUPLICATE_SKIPPED",
                "Feedback %s skipped (duplicate or already processed)",
                feedback_id,
            )
            log.info("ingest_skipped_duplicate_or_existing")
            self._db.update_ingestion_status(feedback_id, IngestionStatus.SENT)
            return False

        # Single DB write ” unified_evaluation_records
        self._db.write_unified_record(record)
        self._db.update_ingestion_status(feedback_id, IngestionStatus.SENT)

        log_step_info(
            step_logger,
            "INGEST_RECORD_PERSISTED",
            "Unified evaluation record persisted for feedback_id=%s: entry_route=%s, root_cause=%s, severity=%s",
            feedback_id,
            record.entry_route,
            record.root_cause,
            record.severity,
        )
        log.info(
            "ingest_complete",
            entry_route=record.entry_route,
            root_cause=record.root_cause,
            severity=record.severity,
        )
        return True

    #  Retry sweep 

    def retry_sweep(self, older_than_minutes: int = 5) -> dict[str, int]:
        """Re-process any feedback_records rows that are still in 'pending' or
        'failed' state after the given age threshold.

        Designed to be called on a schedule (e.g. every 5 minutes) by a
        background job or cron.  Safe to call concurrently ” DB-level
        optimistic locking or idempotency checks in the builder prevent
        double-processing.

        Returns a summary dict: {'attempted': n, 'succeeded': n, 'failed': n}

        Args:
            older_than_minutes (int): Collection or list of older than minutes.

        Returns:
            dict[str, int]: Dictionary containing result data or status.
        """
        pending = self._db.fetch_pending_feedback_records(
            older_than_minutes=older_than_minutes
        )
        summary = {"attempted": len(pending), "succeeded": 0, "failed": 0}

        if not pending:
            logger.info("retry_sweep_nothing_pending")
            return summary

        logger.info("retry_sweep_started", count=len(pending))

        for row in pending:
            try:
                self.on_ingest(
                    feedback_id=row.feedback_id,
                    session_id=row.session_id,
                    response_id=row.response_id,
                    source=row.source,
                )
                summary["succeeded"] += 1
            except Exception as exc:
                summary["failed"] += 1
                logger.warning(
                    "retry_sweep_row_failed",
                    feedback_id=row.feedback_id,
                    error=str(exc),
                )

        logger.info("retry_sweep_complete", **summary)
        return summary


