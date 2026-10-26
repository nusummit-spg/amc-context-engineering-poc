"""Business logic service for lifecycle manager."""

import asyncio
from datetime import datetime, timezone, timedelta
import logging
from typing import Optional, Union

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.models import LifecycleStatus

logger = logging.getLogger("app.services.lifecycle_manager")


class LifecycleManager:
    """Manage lifecycle state transitions for unified_evaluation_records."""

    VALID_TRANSITIONS = {
        LifecycleStatus.OPEN: [LifecycleStatus.DIAGNOSING],
        LifecycleStatus.DIAGNOSING: [LifecycleStatus.RESOLVED, LifecycleStatus.OPEN],
        LifecycleStatus.RESOLVED: [LifecycleStatus.MONITORING],
        LifecycleStatus.MONITORING: [],  # Terminal state
    }

    def advance(
        self,
        session_id: str,
        response_id: str,
        new_status: Union[LifecycleStatus, str],
        reason: str,
        db: Session
    ) -> bool:
        """Transition record to new lifecycle status.
        Validates transition is allowed according to state machine rules.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            new_status (Union[LifecycleStatus, str]): Collection or list of new status.
            reason (str): The reason.
            db (Session): Database session instance.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        record = (
            db.query(UnifiedEvaluationRecord)
            .filter(
                UnifiedEvaluationRecord.session_id == session_id,
                UnifiedEvaluationRecord.response_id == response_id
            )
            .first()
        )

        if not record:
            raise ValueError(f"Record not found: {response_id}")

        # Normalize statuses to LifecycleStatus enum
        if isinstance(record.lifecycle_status, LifecycleStatus):
            current_status = record.lifecycle_status
        else:
            current_status = LifecycleStatus(str(record.lifecycle_status).lower())

        if isinstance(new_status, str):
            target_status = LifecycleStatus(new_status.lower())
        else:
            target_status = new_status

        # Validate transition
        allowed = self.VALID_TRANSITIONS.get(current_status, [])
        if target_status not in allowed:
            raise ValueError(f"Invalid transition: {current_status.value} -> {target_status.value}")

        # Update status
        record.lifecycle_status = target_status.value
        record.updated_at = datetime.now(timezone.utc).isoformat()

        # Log transition
        self._log_transition(record, current_status, target_status, reason, db)

        db.commit()
        logger.info(
            "Lifecycle transition: %s -> %s (reason: %s, record: %s)",
            current_status.value,
            target_status.value,
            reason,
            response_id
        )
        return True

    def _log_transition(
        self,
        record: UnifiedEvaluationRecord,
        old_status: LifecycleStatus,
        new_status: LifecycleStatus,
        reason: str,
        db: Session
    ):
        """Store or log transition history.

        Args:
            record (UnifiedEvaluationRecord): The record.
            old_status (LifecycleStatus): Collection or list of old status.
            new_status (LifecycleStatus): Collection or list of new status.
            reason (str): The reason.
            db (Session): Database session instance.
        """
        logger.info(
            "Lifecycle event: record=%s, %s -> %s, reason=%s",
            record.response_id,
            old_status.value,
            new_status.value,
            reason
        )

    def auto_advance_resolved_to_monitoring(self, observation_days: int = 7) -> int:
        """Automatically advance RESOLVED records to MONITORING after observation period.

        Args:
            observation_days (int): Collection or list of observation days.

        Returns:
            int: Resulting int instance.
        """
        db = SessionLocal()
        advanced_count = 0
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=observation_days)

            resolved_records = (
                db.query(UnifiedEvaluationRecord)
                .filter(
                    UnifiedEvaluationRecord.lifecycle_status.in_([LifecycleStatus.RESOLVED, LifecycleStatus.RESOLVED.value]),
                    UnifiedEvaluationRecord.updated_at <= cutoff.isoformat()
                )
                .all()
            )

            for record in resolved_records:
                try:
                    self.advance(
                        session_id=record.session_id,
                        response_id=record.response_id,
                        new_status=LifecycleStatus.MONITORING,
                        reason=f"Observation period ({observation_days}d) completed",
                        db=db
                    )
                    advanced_count += 1
                except Exception as exc:
                    logger.error("Failed to advance record %s: %s", record.response_id, exc)

            logger.info("Auto-advanced %d records to MONITORING", advanced_count)
            return advanced_count

        finally:
            db.close()


_running_task: Optional[asyncio.Task] = None
_shutdown_event = asyncio.Event()


async def start_lifecycle_manager(interval_seconds: int = 86400):
    """Background task loop for lifecycle manager.

    Args:
        interval_seconds (int): Collection or list of interval seconds.
    """
    manager = LifecycleManager()
    logger.info("LifecycleManager background loop started (interval=%ds)", interval_seconds)

    while not _shutdown_event.is_set():
        try:
            await asyncio.wait_for(_shutdown_event.wait(), timeout=interval_seconds)
            break
        except asyncio.TimeoutError:
            pass

        try:
            manager.auto_advance_resolved_to_monitoring(observation_days=7)
        except Exception as exc:
            logger.error("Lifecycle manager periodic check error: %s", exc)


def stop_lifecycle_manager():
    """Stop lifecycle manager.
    """
    _shutdown_event.set()
