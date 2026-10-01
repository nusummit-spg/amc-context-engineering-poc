# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
timeout_processor.py
====================
Periodic background worker that processes expired sessions (older than 180s timeout window).
Enriches skeleton ResponseFeedback records with telemetry and implicit satisfaction signals.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.feedback.metrics_enrichment import get_metrics_enricher
from app.feedback.session_manager import get_session_manager
from sqlalchemy import or_
from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback

logger = logging.getLogger("app.feedback.timeout_processor")


class TimeoutProcessor:
    """
    Background worker that checks for timed-out responses every `check_interval` seconds,
    enriches them with MetricsEnricher, and marks them as enriched.
    """

    def __init__(self, check_interval: int = 60, timeout_seconds: int = 180):
        self.check_interval = check_interval
        self.timeout_seconds = timeout_seconds
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False

    async def process_timed_out_responses(self) -> int:
        """
        Runs one cycle of enrichment for timed-out responses from both
        SessionManager and database skeletons.
        Returns the number of responses enriched in this cycle.
        """
        enricher = get_metrics_enricher()
        session_manager = get_session_manager()

        enriched_count = 0
        target_responses = set()

        # 1. Gather from SessionManager
        try:
            sm_unenriched = await session_manager.get_unenriched_responses()
            for sid, rid in sm_unenriched:
                target_responses.add((sid, rid))
        except Exception as sm_exc:
            logger.debug("Could not get unenriched responses from SessionManager: %s", sm_exc)

        # 2. Gather from DB skeletons older than timeout window
        db = SessionLocal()
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=self.timeout_seconds)).isoformat()
            db_skeletons = (
                db.query(ResponseFeedback)
                .filter(
                    ResponseFeedback.automated_category.is_(None),
                    ResponseFeedback.actor_id.is_(None),
                    or_(ResponseFeedback.feedback_text.is_(None), ResponseFeedback.feedback_text == ""),
                    or_(ResponseFeedback.selected_categories.is_(None), ResponseFeedback.selected_categories == "[]"),
                    ResponseFeedback.created_at <= cutoff,
                )
                .limit(100)
                .all()
            )
            for row in db_skeletons:
                target_responses.add((row.session_id, row.response_id))
        except Exception as db_exc:
            logger.debug("Could not query DB skeletons for timeout processor: %s", db_exc)
        finally:
            db.close()

        # 3. Enrich each identified response
        for session_id, response_id in target_responses:
            try:
                success = await enricher.enrich_response(session_id, response_id)
                if success:
                    await session_manager.mark_enriched(session_id, response_id)
                    enriched_count += 1
            except Exception as exc:
                logger.error("Enrichment failed for response %s in session %s: %s", response_id, session_id, exc)

        if enriched_count > 0:
            logger.info("TimeoutProcessor enriched %d responses", enriched_count)

        return enriched_count

    async def _process_loop(self) -> None:
        """Continuous background loop running every check_interval seconds."""
        logger.info("TimeoutProcessor loop started (interval=%ds)", self.check_interval)
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self.process_timed_out_responses()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in TimeoutProcessor loop: %s", exc)

    async def start(self) -> None:
        """Start the background processing task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("TimeoutProcessor started")

    async def stop(self) -> None:
        """Stop the background processing task gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("TimeoutProcessor stopped")


# Global singleton instance
_timeout_processor: Optional[TimeoutProcessor] = None


def get_timeout_processor(
    check_interval: Optional[int] = None,
    timeout_seconds: Optional[int] = None,
) -> TimeoutProcessor:
    """Retrieve or create the global TimeoutProcessor singleton."""
    global _timeout_processor
    if _timeout_processor is None:
        try:
            from app.config import get_settings
            settings = get_settings()
            interval = check_interval or getattr(settings, "passive_feedback_processor_interval", 60)
            timeout = timeout_seconds or getattr(settings, "passive_feedback_timeout", 180)
        except Exception:
            interval = check_interval or 60
            timeout = timeout_seconds or 180

        _timeout_processor = TimeoutProcessor(
            check_interval=interval,
            timeout_seconds=timeout,
        )
    return _timeout_processor


async def start_timeout_processor() -> TimeoutProcessor:
    """Start and return the global TimeoutProcessor singleton."""
    processor = get_timeout_processor()
    await processor.start()
    return processor


async def stop_timeout_processor() -> None:
    """Stop the global TimeoutProcessor singleton."""
    global _timeout_processor
    if _timeout_processor is not None:
        await _timeout_processor.stop()
