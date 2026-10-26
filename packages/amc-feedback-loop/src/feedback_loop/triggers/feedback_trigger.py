"""
feedback_trigger.py
===================
SQLAlchemy event hook that automatically fires start_feedback_loop()
whenever a ResponseFeedback row is inserted into the session.

How to wire it
--------------
Call register_feedback_trigger() once at application startup, passing the
same SQLAlchemy Session factory your app uses:

    from feedback_loop.triggers.feedback_trigger import register_feedback_trigger
    from feedback_loop.adapters.sqlite import SQLiteDatabaseAdapter, SQLiteEvidenceAdapter
    from feedback_loop import FeedbackLoopConfig

    DB_URL = "sqlite:///src/database/scripts/compliance_audit.db"

    db_adapter  = SQLiteDatabaseAdapter(db_url=DB_URL)
    ev_adapter  = SQLiteEvidenceAdapter(db_url=DB_URL)
    config      = FeedbackLoopConfig()

    register_feedback_trigger(
        session_factory=SessionLocal,   # your app's sessionmaker instance
        config=config,
        db_adapter=db_adapter,
        ev_adapter=ev_adapter,
    )

After that, any session.add(ResponseFeedback(...)) followed by session.commit()
will automatically kick off the 4-step pipeline and write a
unified_evaluation_records row.

Design notes
------------
- The trigger fires on after_flush (after the INSERT is issued to SQLite but
  before the outer transaction commits) so the feedback row is readable by
  the pipeline within the same connection.
- The pipeline runs synchronously in the same thread. For production workloads
  consider moving to an async task queue (Celery, ARQ) — swap the body of
  _run_pipeline for a task.delay() call.
- Errors inside the pipeline are caught and logged; they do NOT roll back the
  original ResponseFeedback insert. The retry sweep will reprocess failed rows.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import event
from sqlalchemy.orm import Session

from feedback_loop import start_feedback_loop, FeedbackLoopConfig
from feedback_loop.adapters.db import AbstractDatabaseAdapter
from feedback_loop.adapters.evidence import AbstractEvidenceAdapter
from feedback_loop.models import ResponseFeedback

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

logger = structlog.get_logger(__name__)


def register_feedback_trigger(
    session_factory,           # sqlalchemy.orm.sessionmaker instance
    config: FeedbackLoopConfig,
    db_adapter: AbstractDatabaseAdapter,
    ev_adapter: AbstractEvidenceAdapter,
) -> None:
    """Attach an after_flush listener to the given session factory so that
    every new ResponseFeedback insert automatically triggers the pipeline.

    Safe to call multiple times — SQLAlchemy deduplicates identical listeners.

    Args:
        session_factory: The session factory.
        config (FeedbackLoopConfig): Configuration dictionary or settings object.
        db_adapter (AbstractDatabaseAdapter): The db adapter.
        ev_adapter (AbstractEvidenceAdapter): The ev adapter.
    """

    @event.listens_for(session_factory, "after_flush")
    def _on_flush(session: Session, flush_context) -> None:
        """Fires after every flush. Collects newly inserted ResponseFeedback rows.

        Args:
            session (Session): Database session or client session instance.
            flush_context: The flush context.
        """
        pending = [
            (obj.feedback_id, obj.response_id, obj.session_id, (obj.actor_role or "").lower())
            for obj in session.new
            if isinstance(obj, ResponseFeedback)
        ]
        if pending:
            session.info.setdefault("_pending_feedback_triggers", []).extend(pending)

    @event.listens_for(session_factory, "after_commit")
    def _on_commit(session: Session) -> None:
        """Fires after commit. Invokes the pipeline for each committed ResponseFeedback row.

        Args:
            session (Session): Database session or client session instance.
        """
        pending = session.info.pop("_pending_feedback_triggers", [])
        for feedback_id, response_id, session_id, actor_role in pending:
            source = "passive" if actor_role == "system" else "active"

            log = logger.bind(
                feedback_id=feedback_id,
                response_id=response_id,
                session_id=session_id,
                source=source,
            )
            log.info("feedback_trigger_fired")

            try:
                result = start_feedback_loop(
                    feedback_id=feedback_id,
                    session_id=session_id,
                    response_id=response_id,
                    source=source,
                    config=config,
                    db=db_adapter,
                    evidence_adapter=ev_adapter,
                )
                log.info("feedback_trigger_complete", produced_record=result)

            except KeyError as exc:
                log.warning(
                    "feedback_trigger_missing_evidence",
                    error=str(exc),
                )
            except Exception as exc:
                log.error(
                    "feedback_trigger_pipeline_error",
                    error=str(exc),
                    exc_info=True,
                )

    @event.listens_for(session_factory, "after_rollback")
    def _on_rollback(session: Session) -> None:
        """Clear pending triggers if transaction was rolled back.

        Args:
            session (Session): Database session or client session instance.
        """
        session.info.pop("_pending_feedback_triggers", None)

    logger.info(
        "feedback_trigger_registered",
        session_factory=str(session_factory),
    )
