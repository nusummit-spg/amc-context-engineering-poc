# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from app.feedback.session_manager import (
    SessionManager,
    SessionResponse,
    get_session_manager,
    start_session_manager,
    stop_session_manager,
)


@pytest.mark.asyncio
async def test_register_first_response():
    """First query in a session should return None (no previous response)."""
    manager = SessionManager(timeout_seconds=180)
    prev = await manager.register_response("sess_1", "resp_1", "What is the TER of HDFC?")
    assert prev is None
    state = await manager.get_session_state("sess_1")
    assert state is not None
    assert len(state.responses) == 1
    assert state.responses[0].response_id == "resp_1"


@pytest.mark.asyncio
async def test_register_within_timeout():
    """Second query within timeout window should return previous response."""
    manager = SessionManager(timeout_seconds=180)
    now = datetime.now(timezone.utc)
    await manager.register_response("sess_1", "resp_1", "What is the TER?", timestamp=now)
    
    # 45 seconds later
    later = now + timedelta(seconds=45)
    prev = await manager.register_response("sess_1", "resp_2", "Actually it is 2.5%", timestamp=later)
    
    assert prev is not None
    assert prev.response_id == "resp_1"
    assert prev.query_text == "What is the TER?"


@pytest.mark.asyncio
async def test_register_outside_timeout():
    """Second query outside timeout window should return None."""
    manager = SessionManager(timeout_seconds=180)
    now = datetime.now(timezone.utc)
    await manager.register_response("sess_1", "resp_1", "What is the TER?", timestamp=now)
    
    # 200 seconds later (beyond 180s)
    later = now + timedelta(seconds=200)
    prev = await manager.register_response("sess_1", "resp_2", "New question", timestamp=later)
    
    assert prev is None


@pytest.mark.asyncio
async def test_mark_detected():
    """Marking detected should prevent the response from being returned again."""
    manager = SessionManager(timeout_seconds=180)
    now = datetime.now(timezone.utc)
    await manager.register_response("sess_1", "resp_1", "Query 1", timestamp=now)
    
    # Mark detected
    marked = await manager.mark_detected("sess_1", "resp_1")
    assert marked is True
    
    # Next turn: resp_1 should not be returned because it was already detected
    prev = await manager.register_response("sess_1", "resp_2", "Query 2", timestamp=now + timedelta(seconds=10))
    assert prev is None


@pytest.mark.asyncio
async def test_mark_enriched():
    """Marking enriched updates the enriched flag."""
    manager = SessionManager(timeout_seconds=180)
    await manager.register_response("sess_1", "resp_1", "Query 1")
    marked = await manager.mark_enriched("sess_1", "resp_1")
    assert marked is True
    
    state = await manager.get_session_state("sess_1")
    assert state.responses[0].enriched is True


@pytest.mark.asyncio
async def test_get_unenriched_responses():
    """Returns responses older than timeout that have not been enriched."""
    manager = SessionManager(timeout_seconds=180)
    now = datetime.now(timezone.utc)
    
    # resp_old: 200s ago
    await manager.register_response("sess_old", "resp_old", "Old query", timestamp=now - timedelta(seconds=200))
    # resp_new: 10s ago
    await manager.register_response("sess_new", "resp_new", "Recent query", timestamp=now - timedelta(seconds=10))
    
    unenriched = await manager.get_unenriched_responses()
    assert ("sess_old", "resp_old") in unenriched
    assert ("sess_new", "resp_new") not in unenriched
    
    # Mark enriched and check again
    await manager.mark_enriched("sess_old", "resp_old")
    unenriched_after = await manager.get_unenriched_responses()
    assert ("sess_old", "resp_old") not in unenriched_after


@pytest.mark.asyncio
async def test_cleanup_expired_sessions():
    """Cleans up sessions older than 2x timeout."""
    manager = SessionManager(timeout_seconds=60)
    now = datetime.now(timezone.utc)
    
    # Register session and artificially backdate activity
    await manager.register_response("sess_expired", "resp_1", "Old query", timestamp=now - timedelta(seconds=150))
    await manager.register_response("sess_active", "resp_2", "Active query", timestamp=now)
    
    # sess_expired last_activity is > 120s old
    evicted_count = await manager.cleanup_expired_sessions()
    assert evicted_count == 1
    assert await manager.get_session_state("sess_expired") is None
    assert await manager.get_session_state("sess_active") is not None


@pytest.mark.asyncio
async def test_capacity_max_sessions():
    """Evicts oldest session when max_sessions is exceeded."""
    manager = SessionManager(timeout_seconds=180, max_sessions=2)
    now = datetime.now(timezone.utc)
    
    await manager.register_response("sess_1", "resp_1", "Q1", timestamp=now)
    await manager.register_response("sess_2", "resp_2", "Q2", timestamp=now + timedelta(seconds=5))
    # Third session exceeds max_sessions (2)
    await manager.register_response("sess_3", "resp_3", "Q3", timestamp=now + timedelta(seconds=10))
    
    assert await manager.get_session_state("sess_1") is None  # Oldest evicted
    assert await manager.get_session_state("sess_2") is not None
    assert await manager.get_session_state("sess_3") is not None


@pytest.mark.asyncio
async def test_concurrent_registrations():
    """Handles concurrent registrations safely."""
    manager = SessionManager(timeout_seconds=180)
    
    async def add_turn(i: int):
        await manager.register_response("sess_concurrent", f"resp_{i}", f"Query {i}")
    
    await asyncio.gather(*(add_turn(i) for i in range(20)))
    state = await manager.get_session_state("sess_concurrent")
    assert len(state.responses) == 20


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    """Verifies start and stop lifecycle of SessionManager."""
    manager = SessionManager(timeout_seconds=60, cleanup_interval=1)
    await manager.start()
    assert manager._running is True
    assert manager._cleanup_task is not None
    
    await manager.stop()
    assert manager._running is False
    assert manager._cleanup_task is None
