# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
session_manager.py
==================
In-memory session tracker and timeout enforcement for passive feedback detection.
Tracks query timestamps per session and determines eligibility for follow-up correction detection.
"""

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("app.feedback.session_manager")


@dataclass
class SessionResponse:
    """Represents a single query response turn within a session."""
    response_id: str
    query_text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    detected: bool = False    # Whether follow-up detection has been run
    enriched: bool = False    # Whether automatic telemetry/metrics have been enriched


@dataclass
class SessionState:
    """Tracks history and activity timestamp for an active session."""
    session_id: str
    responses: List[SessionResponse] = field(default_factory=list)
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SessionManager:
    """
    Manages in-memory state of active chat sessions.
    Enforces the passive feedback detection timeout window (default 180s)
    and manages background eviction of expired sessions.
    """

    def __init__(
        self,
        timeout_seconds: int = 180,
        cleanup_interval: int = 300,
        max_sessions: int = 10000,
    ):
        """Initialize a new instance of SessionManager.

        Args:
            timeout_seconds (int): Collection or list of timeout seconds.
            cleanup_interval (int): The cleanup interval.
            max_sessions (int): Collection or list of max sessions.
        """
        self.timeout_seconds = timeout_seconds
        self.cleanup_interval = cleanup_interval
        self.max_sessions = max_sessions
        self._sessions: OrderedDict[str, SessionState] = OrderedDict()
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running: bool = False

    async def register_response(
        self,
        session_id: str,
        response_id: str,
        query_text: str,
        timestamp: Optional[datetime] = None,
    ) -> Optional[SessionResponse]:
        """Registers a new query response turn.
        If a previous response exists within the timeout window and hasn't been
        detected yet, returns that previous response as eligible for follow-up detection.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            query_text (str): The query text.
            timestamp (Optional[datetime]): The timestamp.

        Returns:
            Optional[SessionResponse]: Matching object or record if found, None otherwise.
        """
        now = timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        new_resp = SessionResponse(
            response_id=response_id,
            query_text=query_text,
            timestamp=now,
        )

        async with self._lock:
            if session_id in self._sessions:
                state = self._sessions[session_id]
                state.last_activity = now
                
                # Move to end (mark as recently used)
                self._sessions.move_to_end(session_id)

                eligible_prev: Optional[SessionResponse] = None
                # Check the most recent prior response
                if state.responses:
                    prev = state.responses[-1]
                    prev_ts = prev.timestamp
                    if prev_ts.tzinfo is None:
                        prev_ts = prev_ts.replace(tzinfo=timezone.utc)

                    age = (now - prev_ts).total_seconds()
                    if not prev.detected and age <= self.timeout_seconds:
                        eligible_prev = prev
                
                # Also enforce per-session response limit (prevent single session from consuming all memory)
                max_responses_per_session = 100
                if len(state.responses) > max_responses_per_session:
                    state.responses = state.responses[-max_responses_per_session:]
                    logger.info("Truncated session %s to %d recent responses", session_id, max_responses_per_session)

                state.responses.append(new_resp)
                return eligible_prev
            else:
                # Capacity management / LRU eviction
                if len(self._sessions) >= self.max_sessions:
                    oldest_id, oldest_state = self._sessions.popitem(last=False)
                    logger.info("Evicted oldest session %s due to max_sessions limit (responses=%d)", oldest_id, len(oldest_state.responses))

                self._sessions[session_id] = SessionState(
                    session_id=session_id,
                    responses=[new_resp],
                    last_activity=now,
                )
                try:
                    from app.core.metrics import passive_feedback_sessions_tracked, passive_feedback_sessions_active
                    passive_feedback_sessions_tracked.inc()
                    passive_feedback_sessions_active.set(len(self._sessions))
                except Exception:
                    pass
                return None

    async def mark_detected(self, session_id: str, response_id: str) -> bool:
        """Mark a response as having had follow-up detection performed.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        async with self._lock:
            if session_id in self._sessions:
                for resp in self._sessions[session_id].responses:
                    if resp.response_id == response_id:
                        resp.detected = True
                        return True
        return False

    async def mark_enriched(self, session_id: str, response_id: str) -> bool:
        """Mark a response as having had telemetry/metrics enriched.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        async with self._lock:
            if session_id in self._sessions:
                for resp in self._sessions[session_id].responses:
                    if resp.response_id == response_id:
                        resp.enriched = True
                        return True
        return False

    async def get_unenriched_responses(self) -> List[Tuple[str, str]]:
        """Return list of (session_id, response_id) for responses older than
        timeout_seconds that have not yet been enriched.

        Returns:
            List[Tuple[str, str]]: List of resulting items or records.
        """
        now = datetime.now(timezone.utc)
        unenriched: List[Tuple[str, str]] = []

        async with self._lock:
            for session_id, state in self._sessions.items():
                for resp in state.responses:
                    if not resp.enriched:
                        resp_ts = resp.timestamp
                        if resp_ts.tzinfo is None:
                            resp_ts = resp_ts.replace(tzinfo=timezone.utc)
                        age = (now - resp_ts).total_seconds()
                        if age >= self.timeout_seconds:
                            unenriched.append((session_id, resp.response_id))
        return unenriched

    async def get_session_state(self, session_id: str) -> Optional[SessionState]:
        """Inspect current state of a session.

        Args:
            session_id (str): Unique identifier of the session.

        Returns:
            Optional[SessionState]: Matching object or record if found, None otherwise.
        """
        async with self._lock:
            return self._sessions.get(session_id)

    async def cleanup_expired_sessions(self) -> int:
        """Removes sessions whose last activity is older than 2x timeout.

        Returns:
            int: Resulting int instance.
        """
        now = datetime.now(timezone.utc)
        cutoff_seconds = 2 * self.timeout_seconds
        removed_count = 0

        async with self._lock:
            expired = [
                sid
                for sid, state in self._sessions.items()
                if (now - (state.last_activity if state.last_activity.tzinfo else state.last_activity.replace(tzinfo=timezone.utc))).total_seconds() > cutoff_seconds
            ]
            for sid in expired:
                del self._sessions[sid]
                removed_count += 1

        if removed_count > 0:
            logger.info("Cleaned up %d expired passive feedback sessions", removed_count)
        return removed_count

    async def _cleanup_loop(self) -> None:
        """Background loop to periodically prune stale sessions."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in SessionManager cleanup loop: %s", exc)

    async def start(self) -> None:
        """Start the background cleanup loop."""
        if self._running:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(
            "SessionManager started (timeout=%ds, cleanup_interval=%ds)",
            self.timeout_seconds,
            self.cleanup_interval,
        )

    async def stop(self) -> None:
        """Stop the background cleanup loop and wait for completion."""
        self._running = False
        if self._cleanup_task:
            try:
                self._cleanup_task.cancel()
                # Wait for cancellation to complete with timeout
                await asyncio.wait_for(self._cleanup_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Cleanup task did not stop within 5 seconds, forcing termination")
            except asyncio.CancelledError:
                pass  # Expected when task is cancelled
            except Exception as exc:
                logger.error("Error stopping cleanup task: %s", exc)
            finally:
                self._cleanup_task = None
        logger.info("SessionManager stopped")


# Global singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager(timeout_seconds: Optional[int] = None) -> SessionManager:
    """Retrieve or create the global SessionManager singleton.

    Args:
        timeout_seconds (Optional[int]): Collection or list of timeout seconds.

    Returns:
        SessionManager: Resulting SessionManager instance.
    """
    global _session_manager
    if _session_manager is None:
        try:
            from app.config import get_settings
            settings = get_settings()
            timeout = timeout_seconds or getattr(settings, "passive_feedback_timeout", 180)
            cleanup_interval = getattr(settings, "passive_feedback_cleanup_interval", 300)
            max_size = getattr(settings, "passive_session_max_size", 10000)
        except Exception:
            timeout = timeout_seconds or 180
            cleanup_interval = 300
            max_size = 10000

        _session_manager = SessionManager(
            timeout_seconds=timeout,
            cleanup_interval=cleanup_interval,
            max_sessions=max_size,
        )
    return _session_manager


async def start_session_manager() -> SessionManager:
    """Start and return the global SessionManager singleton.

    Returns:
        SessionManager: Resulting SessionManager instance.
    """
    manager = get_session_manager()
    await manager.start()
    return manager


async def stop_session_manager() -> None:
    """Stop the global SessionManager singleton."""
    global _session_manager
    if _session_manager is not None:
        await _session_manager.stop()
