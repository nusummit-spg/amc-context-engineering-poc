# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
feedback_retry.py
==================
Retry mechanism for pending/failed feedback loop executions with exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback

logger = logging.getLogger("app.services.feedback_retry")


class FeedbackRetryService:
    """Retry failed/pending feedback loop triggers."""

    def __init__(self, retry_intervals: Optional[List[int]] = None):
        """Initialize a new instance of FeedbackRetryService.

        Args:
            retry_intervals (Optional[List[int]]): Collection or list of retry intervals.
        """
        self.retry_intervals = retry_intervals or [60, 300, 900]  # 1min, 5min, 15min
        self._exceeded_logged: set[str] = set()

    async def process_retries(self) -> int:
        """Find pending feedback records and retry trigger.

        Returns:
            int: Resulting int instance.
        """
        db = SessionLocal()
        retried_count = 0
        try:
            # Find records between 1 minute and 35 minutes old with no unified_record_ref
            now = datetime.now(timezone.utc)
            cutoff_max = now - timedelta(seconds=2100)  # 35 min cutoff
            cutoff_min = now - timedelta(seconds=60)    # 1 min cutoff

            pending = (
                db.query(ResponseFeedback)
                .filter(
                    ResponseFeedback.unified_record_ref.is_(None),
                    ResponseFeedback.created_at >= cutoff_max.isoformat(),
                    ResponseFeedback.created_at <= cutoff_min.isoformat(),
                )
                .limit(50)
                .all()
            )

            for record in pending:
                try:
                    record_dt = datetime.fromisoformat(record.created_at)
                    if record_dt.tzinfo is None:
                        record_dt = record_dt.replace(tzinfo=timezone.utc)
                    age_seconds = (now - record_dt).total_seconds()
                except Exception:
                    continue

                should_retry = any(
                    abs(age_seconds - interval) < 45  # 45s tolerance
                    for interval in self.retry_intervals
                ) or (age_seconds < 120 and age_seconds >= 60)

                if should_retry:
                    try:
                        from app.services.feedback import trigger_feedback_loop
                        await asyncio.to_thread(
                            trigger_feedback_loop,
                            feedback_id=record.feedback_id,
                            session_id=record.session_id,
                            response_id=record.response_id,
                            source="active" if record.feedback_text else "passive",
                        )
                        retried_count += 1
                        logger.info("Retry trigger executed for feedback %s", record.feedback_id)
                    except Exception as exc:
                        logger.error("Retry failed for feedback %s: %s", record.feedback_id, exc)

                if age_seconds > 1800 and record.feedback_id not in self._exceeded_logged:
                    self._exceeded_logged.add(record.feedback_id)
                    logger.warning("Feedback %s exceeded retry window (30m)", record.feedback_id)
            return retried_count
        finally:
            db.close()


_running: bool = False
_retry_task: Optional[asyncio.Task] = None


async def start_retry_service(interval_seconds: int = 60) -> None:
    """Background task running feedback retry sweeps.

    Args:
        interval_seconds (int): Collection or list of interval seconds.
    """
    global _running, _retry_task
    if _running:
        return
    _running = True
    service = FeedbackRetryService()
    logger.info("FeedbackRetryService started (interval=%ds)", interval_seconds)
    while _running:
        try:
            await asyncio.sleep(interval_seconds)
            await service.process_retries()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Retry service error: %s", exc)


async def stop_retry_service() -> None:
    """Stop the background retry service gracefully."""
    global _running, _retry_task
    _running = False
    if _retry_task and not _retry_task.done():
        _retry_task.cancel()
        try:
            await asyncio.wait_for(_retry_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        except Exception as exc:
            logger.warning("Error stopping retry service task: %s", exc)
        finally:
            _retry_task = None
