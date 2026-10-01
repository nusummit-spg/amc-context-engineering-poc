# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
feedback_timer.py
=================
Manages feedback-recording lifecycle and 5-minute timer behavior in data.db.

Core Behaviors:
1. Whenever a user submits a query, start a 5-minute timer.
2. If the user does not provide a follow-up query or feedback within 5 minutes,
   automatically insert a record into `response_feedback` with `selected_categories`
   empty ([]) and `feedback_text` left NULL/None.
3. If the user submits another query within the same chat session before the 5-minute
   timer expires, immediately create the feedback record for the previous query
   instead of waiting for the full 5 minutes, then start a new 5-minute timer
   for the latest query.
4. If feedback is submitted for a query (either on-time or late after the timer
   expired), do not create a duplicate record—instead, identify and update the
   existing feedback record associated with that query/session with the provided
   `selected_categories` and `feedback_text`.
5. Strictly handle session boundaries, concurrent requests, timer expiration,
   duplicate prevention, late feedback, follow-up queries, and errors with
   clear structured logging.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from app.core.database import SessionLocal
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.response_feedback_table import ResponseFeedback

logger = logging.getLogger("app.feedback.timer")


@dataclass
class PendingTurn:
    """Represents an active, in-flight query response turn waiting for feedback or follow-up."""
    session_id: str
    response_id: str
    interaction_id: str
    turn_number: int
    query_text: str
    response_text: Optional[str] = None
    created_at: datetime = None
    timer_task: Optional[asyncio.Task] = None
    is_recorded: bool = False

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class FeedbackTimerManager:
    """
    Thread-safe and async-safe manager for per-turn feedback timers and
    automatic persistence into data.db.
    """

    def __init__(self, default_timeout_seconds: Optional[int] = None):
        if default_timeout_seconds is not None:
            self.default_timeout_seconds = default_timeout_seconds
        else:
            try:
                from app.config import get_settings
                self.default_timeout_seconds = getattr(get_settings(), "feedback_timer_seconds", 300)
            except Exception:
                self.default_timeout_seconds = 300

        self._pending_turns: Dict[str, PendingTurn] = {}  # session_id -> PendingTurn
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]

    async def on_query_submitted(
        self,
        session_id: str,
        response_id: str,
        interaction_id: str,
        turn_number: int,
        query_text: str,
        response_text: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        """
        Invoked when a user submits a query and a response is produced.
        If a previous query in the same session was awaiting timer expiration,
        cancels that timer, immediately records its feedback skeleton into data.db,
        and starts a new 5-minute timer for the current query.
        """
        lock = await self._get_session_lock(session_id)
        async with lock:
            prev_turn = self._pending_turns.get(session_id)
            if prev_turn and not prev_turn.is_recorded:
                # Follow-up query detected within the same session before timer expired
                logger.info(
                    "[FOLLOW_UP_QUERY_DETECTED] session_id=%s, previous_response_id=%s, new_response_id=%s, previous_turn=%d",
                    session_id,
                    prev_turn.response_id,
                    response_id,
                    prev_turn.turn_number,
                )
                # Cancel the previous timer
                if prev_turn.timer_task and not prev_turn.timer_task.done():
                    prev_turn.timer_task.cancel()
                    logger.info(
                        "[TIMER_CANCELLED] Cancelled previous timer for session_id=%s, response_id=%s due to follow-up query",
                        session_id,
                        prev_turn.response_id,
                    )
                # Immediately create the feedback record for the previous query
                await asyncio.to_thread(self._insert_empty_feedback_record_sync, prev_turn, reason="follow_up_query")
                prev_turn.is_recorded = True

            # Register new turn and start timer
            timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
            new_turn = PendingTurn(
                session_id=session_id,
                response_id=response_id,
                interaction_id=interaction_id,
                turn_number=turn_number,
                query_text=query_text,
                response_text=response_text,
                created_at=datetime.now(timezone.utc),
            )
            self._pending_turns[session_id] = new_turn

            # Start the async timer
            task = asyncio.create_task(
                self._timer_callback(session_id=session_id, response_id=response_id, timeout_seconds=timeout)
            )
            new_turn.timer_task = task
            logger.info(
                "[TIMER_CREATED] Started %ds timer for session_id=%s, response_id=%s, turn_number=%d",
                timeout,
                session_id,
                response_id,
                turn_number,
            )

    async def _timer_callback(self, session_id: str, response_id: str, timeout_seconds: int) -> None:
        """Coroutine executed for the timer duration."""
        try:
            await asyncio.sleep(timeout_seconds)
        except asyncio.CancelledError:
            # Timer was cancelled by a follow-up query or explicit feedback
            return

        lock = await self._get_session_lock(session_id)
        async with lock:
            turn = self._pending_turns.get(session_id)
            if turn and turn.response_id == response_id and not turn.is_recorded:
                logger.info(
                    "[TIMER_EXPIRED] %ds timer expired for session_id=%s, response_id=%s, turn_number=%d without follow-up or feedback",
                    timeout_seconds,
                    session_id,
                    response_id,
                    turn.turn_number,
                )
                await asyncio.to_thread(self._insert_empty_feedback_record_sync, turn, reason="timer_expiration")
                turn.is_recorded = True

    def _insert_empty_feedback_record_sync(self, turn: PendingTurn, reason: str) -> Optional[str]:
        """
        Synchronously insert a record into response_feedback table with
        selected_categories=[] and feedback_text=None. Handles duplicate prevention.
        """
        db = SessionLocal()
        try:
            # Ensure ChatSession exists
            session = db.query(ChatSession).filter_by(session_id=turn.session_id).first()
            if not session:
                session = ChatSession(session_id=turn.session_id)
                db.add(session)
                db.commit()

            # Duplicate prevention: Check if feedback record already exists for this query
            existing = db.query(ResponseFeedback).filter(
                (ResponseFeedback.response_id == turn.response_id) |
                ((ResponseFeedback.session_id == turn.session_id) & (ResponseFeedback.interaction_id == turn.interaction_id))
            ).first()

            if existing:
                logger.info(
                    "[DUPLICATE_PREVENTED] Feedback record already exists in data.db (feedback_id=%s, response_id=%s, session_id=%s) during %s. Skipping insertion.",
                    existing.feedback_id,
                    turn.response_id,
                    turn.session_id,
                    reason,
                )
                turn.is_recorded = True
                return existing.feedback_id

            now_iso = datetime.now(timezone.utc).isoformat()
            feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
            new_record = ResponseFeedback(
                feedback_id=feedback_id,
                response_id=turn.response_id,
                interaction_id=turn.interaction_id,
                session_id=turn.session_id,
                turn_number=turn.turn_number,
                query_text=turn.query_text,
                response_text=turn.response_text,
                actor_id=None,
                actor_role=None,
                selected_categories=[],  # empty
                feedback_text=None,     # NULL
                created_at=now_iso,
                updated_at=now_iso,
            )
            db.add(new_record)
            db.commit()
            turn.is_recorded = True
            logger.info(
                "[RECORD_INSERTED] Automatically inserted feedback record into data.db: feedback_id=%s, response_id=%s, session_id=%s, turn_number=%d, reason=%s",
                feedback_id,
                turn.response_id,
                turn.session_id,
                turn.turn_number,
                reason,
            )
            return feedback_id
        except Exception as exc:
            db.rollback()
            logger.error(
                "[FEEDBACK_TIMER_ERROR] Failed inserting feedback record for session_id=%s, response_id=%s, reason=%s: %s",
                turn.session_id,
                turn.response_id,
                reason,
                exc,
                exc_info=True,
            )
            raise
        finally:
            db.close()

    async def on_feedback_submitted(
        self,
        session_id: str,
        response_id: str,
        selected_categories: List[str],
        feedback_text: Optional[str] = None,
        interaction_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        query_text: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        client_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invoked when explicit user/reviewer feedback is submitted.
        Cancels any active timer for this response turn.
        If an existing record is in data.db (e.g. from timer expiration or follow-up query),
        updates that record with the provided categories and feedback text to prevent duplicates.
        If no record exists, inserts a new feedback record.
        """
        lock = await self._get_session_lock(session_id)
        async with lock:
            turn = self._pending_turns.get(session_id)
            if turn and turn.response_id == response_id:
                if turn.timer_task and not turn.timer_task.done():
                    turn.timer_task.cancel()
                    logger.info(
                        "[TIMER_CANCELLED] Cancelled active timer for session_id=%s, response_id=%s due to incoming feedback",
                        session_id,
                        response_id,
                    )
                turn.is_recorded = True

            result = await asyncio.to_thread(
                self._upsert_feedback_sync,
                session_id=session_id,
                response_id=response_id,
                selected_categories=selected_categories,
                feedback_text=feedback_text,
                interaction_id=interaction_id,
                turn_number=turn_number,
                query_text=query_text,
                actor_id=actor_id,
                actor_role=actor_role,
                client_timestamp=client_timestamp,
            )
            return result

    def _upsert_feedback_sync(
        self,
        session_id: str,
        response_id: str,
        selected_categories: List[str],
        feedback_text: Optional[str] = None,
        interaction_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        query_text: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        client_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronously upserts feedback into data.db, handling late feedback and duplicate prevention."""
        db = SessionLocal()
        try:
            # Ensure ChatSession exists
            session = db.query(ChatSession).filter_by(session_id=session_id).first()
            if not session:
                session = ChatSession(session_id=session_id)
                db.add(session)
                db.commit()

            # Identify existing record associated with this query/session
            existing = db.query(ResponseFeedback).filter(
                (ResponseFeedback.response_id == response_id) |
                ((ResponseFeedback.session_id == session_id) & (ResponseFeedback.interaction_id == interaction_id))
            ).first()

            now_iso = datetime.now(timezone.utc).isoformat()
            feedback_text_clean = (feedback_text or "").strip() or None

            if existing:
                # Existing record found (from timer expiration, follow-up query, or prior submission)
                logger.info(
                    "[LATE_FEEDBACK_HANDLED] Identified existing feedback record feedback_id=%s for session_id=%s, response_id=%s. Updating record without duplicates.",
                    existing.feedback_id,
                    session_id,
                    response_id,
                )
                existing.selected_categories = selected_categories
                if feedback_text_clean is not None:
                    existing.feedback_text = feedback_text_clean
                if actor_id:
                    existing.actor_id = actor_id
                if actor_role:
                    existing.actor_role = actor_role
                if client_timestamp:
                    existing.client_timestamp = client_timestamp
                if interaction_id and not existing.interaction_id:
                    existing.interaction_id = interaction_id
                if turn_number and not existing.turn_number:
                    existing.turn_number = turn_number
                if query_text and not existing.query_text:
                    existing.query_text = query_text
                existing.updated_at = now_iso
                db.commit()

                logger.info(
                    "[RECORD_UPDATED] Updated existing feedback record feedback_id=%s in data.db for response_id=%s",
                    existing.feedback_id,
                    response_id,
                )
                logger.info(
                    "[DUPLICATE_PREVENTED] Prevented duplicate record creation for session_id=%s, response_id=%s; updated feedback_id=%s",
                    session_id,
                    response_id,
                    existing.feedback_id,
                )
                return {
                    "feedback_id": existing.feedback_id,
                    "response_id": response_id,
                    "status": "updated",
                    "stored_at": now_iso,
                }
            else:
                # No record exists yet: insert new feedback record
                feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
                new_record = ResponseFeedback(
                    feedback_id=feedback_id,
                    response_id=response_id,
                    interaction_id=interaction_id or f"int_{uuid.uuid4().hex[:12]}",
                    session_id=session_id,
                    turn_number=turn_number or 1,
                    query_text=query_text,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    selected_categories=selected_categories,
                    feedback_text=feedback_text_clean,
                    client_timestamp=client_timestamp,
                    created_at=now_iso,
                    updated_at=now_iso,
                )
                db.add(new_record)
                db.commit()
                logger.info(
                    "[RECORD_INSERTED] Inserted user feedback record into data.db: feedback_id=%s, response_id=%s, session_id=%s",
                    feedback_id,
                    response_id,
                    session_id,
                )
                return {
                    "feedback_id": feedback_id,
                    "response_id": response_id,
                    "status": "recorded",
                    "stored_at": now_iso,
                }
        except Exception as exc:
            db.rollback()
            logger.error(
                "[FEEDBACK_TIMER_ERROR] Failed upserting feedback for session_id=%s, response_id=%s: %s",
                session_id,
                response_id,
                exc,
                exc_info=True,
            )
            raise
        finally:
            db.close()

    async def get_pending_turn(self, session_id: str) -> Optional[PendingTurn]:
        """Inspect the current pending turn for a session."""
        lock = await self._get_session_lock(session_id)
        async with lock:
            return self._pending_turns.get(session_id)

    async def cancel_session(self, session_id: str) -> None:
        """Cancel any running timer for a session."""
        lock = await self._get_session_lock(session_id)
        async with lock:
            turn = self._pending_turns.pop(session_id, None)
            if turn and turn.timer_task and not turn.timer_task.done():
                turn.timer_task.cancel()
                logger.info(
                    "[TIMER_CANCELLED] Cancelled timer for session_id=%s, response_id=%s during session cleanup",
                    session_id,
                    turn.response_id,
                )

    async def stop_all(self) -> None:
        """Gracefully stop and cancel all pending timer tasks across all sessions."""
        async with self._global_lock:
            for session_id, turn in list(self._pending_turns.items()):
                if turn.timer_task and not turn.timer_task.done():
                    turn.timer_task.cancel()
                    try:
                        await turn.timer_task
                    except (asyncio.CancelledError, Exception):
                        pass
            self._pending_turns.clear()
            logger.info("FeedbackTimerManager: All active feedback timers cancelled and stopped.")


# Global singleton instance
_feedback_timer_manager: Optional[FeedbackTimerManager] = None


def get_feedback_timer_manager(default_timeout_seconds: Optional[int] = None) -> FeedbackTimerManager:
    """Retrieve or create the global FeedbackTimerManager singleton."""
    global _feedback_timer_manager
    if _feedback_timer_manager is None:
        _feedback_timer_manager = FeedbackTimerManager(default_timeout_seconds=default_timeout_seconds)
    return _feedback_timer_manager
