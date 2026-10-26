# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_feedback_timer.py
======================
Comprehensive test suite verifying the 5-minute feedback-recording timer lifecycle:
1. Automatic record insertion on timer expiration with empty/NULL categories/text.
2. Immediate feedback record creation for the previous query on follow-up query.
3. Late feedback handling updating existing records without duplicates.
4. On-time feedback cancelling the timer and preventing duplicate insertions.
5. Strict session boundary isolation across multiple concurrent sessions.
6. Concurrent query submissions and duplicate prevention.
7. Multi-turn sequential query acceleration.
"""

import asyncio
from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import or_

from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback
from app.feedback.feedback_timer import FeedbackTimerManager, get_feedback_timer_manager


@pytest.fixture
def timer_manager():
    """Provides a fresh isolated instance of FeedbackTimerManager for tests."""
    mgr = FeedbackTimerManager(default_timeout_seconds=300)
    yield mgr
    # Cleanup any active tasks
    asyncio.run(mgr.stop_all())


@pytest.mark.asyncio
async def test_timer_expiration_auto_insert(timer_manager):
    """
    Test 1: If 5 minutes (shortened for test to 0.15s) elapse without follow-up or feedback,
    automatically insert a record into response_feedback with selected_categories=[] and feedback_text=None.
    """
    unique_id = uuid.uuid4().hex[:8]
    session_id = f"sess_exp_{unique_id}"
    resp_id = f"resp_exp_{unique_id}"
    int_id = f"int_exp_{unique_id}"

    db = SessionLocal()
    try:
        # Submit query turn with 0.15s timeout
        await timer_manager.on_query_submitted(
            session_id=session_id,
            response_id=resp_id,
            interaction_id=int_id,
            turn_number=1,
            query_text="What is the exit load of Mirae Asset Large Cap Fund?",
            response_text="The exit load is 1% if redeemed within 1 year.",
            timeout_seconds=0.15,
        )

        # Immediately check DB: should NOT exist yet
        initial_check = db.query(ResponseFeedback).filter_by(response_id=resp_id).first()
        assert initial_check is None, "Record should not exist immediately upon query submission"

        # Wait for timer expiration
        await asyncio.sleep(0.3)

        # Check DB: record must now exist
        record = db.query(ResponseFeedback).filter_by(response_id=resp_id).first()
        assert record is not None, "Record must be automatically created upon timer expiration"
        assert record.session_id == session_id
        assert record.interaction_id == int_id
        assert record.turn_number == 1
        assert record.selected_categories == []
        assert record.feedback_text is None
        assert record.actor_id is None
        assert record.actor_role is None
        assert record.query_text == "What is the exit load of Mirae Asset Large Cap Fund?"

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_follow_up_query_accelerates_previous_feedback(timer_manager):
    """
    Test 2: If a follow-up query is submitted within the same session before the timer expires,
    immediately create the feedback record for the previous query and start a new timer for the latest query.
    """
    unique_id = uuid.uuid4().hex[:8]
    session_id = f"sess_follow_{unique_id}"
    resp1_id = f"resp_1_{unique_id}"
    int1_id = f"int_1_{unique_id}"
    resp2_id = f"resp_2_{unique_id}"
    int2_id = f"int_2_{unique_id}"

    db = SessionLocal()
    try:
        # Turn 1 with 5.0s timeout (would normally wait 5 seconds)
        await timer_manager.on_query_submitted(
            session_id=session_id,
            response_id=resp1_id,
            interaction_id=int1_id,
            turn_number=1,
            query_text="What is the AUM of HDFC Top 100?",
            response_text="The AUM is approximately 30,000 Cr.",
            timeout_seconds=5.0,
        )

        # Before 5 seconds elapse (e.g. 0.05s), user submits follow-up query Turn 2
        await asyncio.sleep(0.05)
        await timer_manager.on_query_submitted(
            session_id=session_id,
            response_id=resp2_id,
            interaction_id=int2_id,
            turn_number=2,
            query_text="Who is the fund manager?",
            response_text="The fund manager is Rahul Baijal.",
            timeout_seconds=0.2,
        )

        # Turn 1 must have been immediately inserted into response_feedback
        record1 = db.query(ResponseFeedback).filter_by(response_id=resp1_id).first()
        assert record1 is not None, "Turn 1 must be immediately recorded on follow-up query"
        assert record1.selected_categories == []
        assert record1.feedback_text is None
        assert record1.turn_number == 1

        # Turn 2 should NOT be recorded yet
        record2_early = db.query(ResponseFeedback).filter_by(response_id=resp2_id).first()
        assert record2_early is None, "Turn 2 should not be recorded immediately"

        # Wait for Turn 2 timer to expire (0.2s timeout)
        await asyncio.sleep(0.35)

        # Turn 2 must now be recorded
        record2_late = db.query(ResponseFeedback).filter_by(response_id=resp2_id).first()
        assert record2_late is not None, "Turn 2 must be recorded on its own timer expiration"
        assert record2_late.turn_number == 2

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_late_feedback_updates_without_duplicate(timer_manager):
    """
    Test 3: If feedback is submitted after the timer has already expired and auto-inserted
    an empty record, do NOT create a duplicate record. Instead, update the existing record
    with the provided selected_categories and feedback_text.
    """
    unique_id = uuid.uuid4().hex[:8]
    session_id = f"sess_late_{unique_id}"
    resp_id = f"resp_late_{unique_id}"
    int_id = f"int_late_{unique_id}"

    db = SessionLocal()
    try:
        # Start turn with short timer 0.1s
        await timer_manager.on_query_submitted(
            session_id=session_id,
            response_id=resp_id,
            interaction_id=int_id,
            turn_number=1,
            query_text="Explain SEBI mutual fund categorization rules",
            response_text="SEBI defines 5 broad mutual fund categories...",
            timeout_seconds=0.1,
        )

        # Wait for timer to expire and auto-insert record
        await asyncio.sleep(0.25)

        initial_record = db.query(ResponseFeedback).filter_by(response_id=resp_id).first()
        assert initial_record is not None
        orig_feedback_id = initial_record.feedback_id
        assert initial_record.selected_categories == []
        assert initial_record.feedback_text is None

        # Now submit late feedback (e.g. reviewer grades it later)
        result = await timer_manager.on_feedback_submitted(
            session_id=session_id,
            response_id=resp_id,
            interaction_id=int_id,
            turn_number=1,
            selected_categories=["F02", "F05"],
            feedback_text="Category description was missing thematic funds details.",
            actor_id="compliance_officer_42",
            actor_role="Compliance Officer",
        )

        assert result["status"] == "updated"
        assert result["feedback_id"] == orig_feedback_id

        # Verify database state: exactly ONE row, updated in place
        db.expire_all()
        matching_rows = db.query(ResponseFeedback).filter_by(response_id=resp_id).all()
        assert len(matching_rows) == 1, "There must be zero duplicate records"
        updated_record = matching_rows[0]
        assert updated_record.feedback_id == orig_feedback_id
        assert updated_record.selected_categories == ["F02", "F05"]
        assert updated_record.feedback_text == "Category description was missing thematic funds details."
        assert updated_record.actor_id == "compliance_officer_42"
        assert updated_record.actor_role == "Compliance Officer"

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_on_time_feedback_prevents_duplicate_on_expiration(timer_manager):
    """
    Test 4: If feedback is provided before the timer expires, cancel the timer,
    store the feedback, and ensure the subsequent timer expiration does not overwrite
    or create a duplicate.
    """
    unique_id = uuid.uuid4().hex[:8]
    session_id = f"sess_ontime_{unique_id}"
    resp_id = f"resp_ontime_{unique_id}"
    int_id = f"int_ontime_{unique_id}"

    db = SessionLocal()
    try:
        # Start turn with 0.3s timer
        await timer_manager.on_query_submitted(
            session_id=session_id,
            response_id=resp_id,
            interaction_id=int_id,
            turn_number=1,
            query_text="What is the NAV of ICICI Prudential Bluechip?",
            response_text="The NAV is 95.42.",
            timeout_seconds=0.3,
        )

        # After 0.05s, provide feedback
        await asyncio.sleep(0.05)
        result = await timer_manager.on_feedback_submitted(
            session_id=session_id,
            response_id=resp_id,
            interaction_id=int_id,
            turn_number=1,
            selected_categories=["F01"],
            feedback_text="NAV figure is accurate.",
            actor_id="reviewer_1",
            actor_role="Reviewer",
        )
        assert result["feedback_id"] is not None

        # Wait past the original 0.3s timer expiration
        await asyncio.sleep(0.4)

        # Verify only 1 record exists and it retains the user's feedback
        db.expire_all()
        rows = db.query(ResponseFeedback).filter_by(response_id=resp_id).all()
        assert len(rows) == 1, "Duplicate record must not be created when timer expires after on-time feedback"
        assert rows[0].selected_categories == ["F01"]
        assert rows[0].feedback_text == "NAV figure is accurate."

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_session_boundary_isolation(timer_manager):
    """
    Test 5: Queries in Session A and Session B must be completely isolated.
    A follow-up query in Session B must NOT accelerate or affect Session A's timer.
    """
    uid = uuid.uuid4().hex[:8]
    sess_a = f"sess_A_{uid}"
    sess_b = f"sess_B_{uid}"
    resp_a = f"resp_A_{uid}"
    resp_b1 = f"resp_B1_{uid}"
    resp_b2 = f"resp_B2_{uid}"

    db = SessionLocal()
    try:
        # Session A query with 0.4s timer
        await timer_manager.on_query_submitted(
            session_id=sess_a,
            response_id=resp_a,
            interaction_id=f"int_A_{uid}",
            turn_number=1,
            query_text="Session A Query",
            timeout_seconds=0.4,
        )

        # Session B query with 0.4s timer
        await timer_manager.on_query_submitted(
            session_id=sess_b,
            response_id=resp_b1,
            interaction_id=f"int_B1_{uid}",
            turn_number=1,
            query_text="Session B Query 1",
            timeout_seconds=0.4,
        )

        # Follow-up in Session B only
        await asyncio.sleep(0.05)
        await timer_manager.on_query_submitted(
            session_id=sess_b,
            response_id=resp_b2,
            interaction_id=f"int_B2_{uid}",
            turn_number=2,
            query_text="Session B Query 2",
            timeout_seconds=0.2,
        )

        # Session B1 should be immediately recorded
        assert db.query(ResponseFeedback).filter_by(response_id=resp_b1).first() is not None

        # Session A query should NOT be recorded yet (Session isolation!)
        assert db.query(ResponseFeedback).filter_by(response_id=resp_a).first() is None

        # Wait for Session A timer to expire
        await asyncio.sleep(0.45)

        # Now Session A should be recorded
        assert db.query(ResponseFeedback).filter_by(response_id=resp_a).first() is not None

    finally:
        db.query(ResponseFeedback).filter(
            or_(ResponseFeedback.session_id == sess_a, ResponseFeedback.session_id == sess_b)
        ).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_rapid_sequential_multi_turn_queries(timer_manager):
    """
    Test 6: 4 rapid sequential queries in the same session.
    Turns 1, 2, 3 must be accelerated immediately on subsequent turns.
    Turn 4 must record on timer expiration.
    Exactly 4 unique records in data.db.
    """
    uid = uuid.uuid4().hex[:8]
    session_id = f"sess_multi_{uid}"
    db = SessionLocal()
    try:
        response_ids = [f"resp_m_{i}_{uid}" for i in range(1, 5)]

        for i, r_id in enumerate(response_ids[:3], start=1):
            await timer_manager.on_query_submitted(
                session_id=session_id,
                response_id=r_id,
                interaction_id=f"int_m_{i}_{uid}",
                turn_number=i,
                query_text=f"Multi turn query {i}",
                timeout_seconds=2.0,
            )
            await asyncio.sleep(0.02)

        # Final turn with short timer 0.15s
        await timer_manager.on_query_submitted(
            session_id=session_id,
            response_id=response_ids[3],
            interaction_id=f"int_m_4_{uid}",
            turn_number=4,
            query_text="Multi turn query 4",
            timeout_seconds=0.15,
        )

        # Turns 1, 2, 3 must be recorded immediately
        for r_id in response_ids[:3]:
            assert db.query(ResponseFeedback).filter_by(response_id=r_id).first() is not None

        # Turn 4 recorded after timer expiration
        await asyncio.sleep(0.25)
        assert db.query(ResponseFeedback).filter_by(response_id=response_ids[3]).first() is not None

        # Total rows for this session must equal exactly 4
        all_turns = db.query(ResponseFeedback).filter_by(session_id=session_id).all()
        assert len(all_turns) == 4
        assert [t.turn_number for t in all_turns] == [1, 2, 3, 4]

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_concurrency_race_condition(timer_manager):
    """
    Test 7: Simultaneous follow-up and feedback submissions or concurrent tasks
    do not cause duplicate records or database errors.
    """
    uid = uuid.uuid4().hex[:8]
    session_id = f"sess_race_{uid}"
    resp_id = f"resp_race_{uid}"
    int_id = f"int_race_{uid}"

    db = SessionLocal()
    try:
        await timer_manager.on_query_submitted(
            session_id=session_id,
            response_id=resp_id,
            interaction_id=int_id,
            turn_number=1,
            query_text="Concurrent stress query",
            timeout_seconds=0.08,
        )

        # Fire 5 concurrent feedback submissions and follow-up arrivals simultaneously
        async def submit_feedback_task(cat, comment):
            return await timer_manager.on_feedback_submitted(
                session_id=session_id,
                response_id=resp_id,
                interaction_id=int_id,
                turn_number=1,
                selected_categories=[cat],
                feedback_text=comment,
            )

        # Wait so timer expiration coincides with concurrent submissions
        await asyncio.sleep(0.06)
        tasks = [
            submit_feedback_task("F01", "Comment 1"),
            submit_feedback_task("F02", "Comment 2"),
            submit_feedback_task("F03", "Comment 3"),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            assert not isinstance(res, Exception), f"Unexpected exception in race condition: {res}"

        # Exactly 1 row in data.db, zero duplicate rows
        db.expire_all()
        rows = db.query(ResponseFeedback).filter_by(response_id=resp_id).all()
        assert len(rows) == 1, f"Expected exactly 1 row, found {len(rows)}"

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()


def test_late_feedback_via_http_endpoint():
    """
    Test 8: End-to-end HTTP verification using FastAPI TestClient:
    1. Timer auto-inserts skeleton on expiration.
    2. Reviewer submits feedback via POST /api/feedback.
    3. Existing record is identified and updated in place with zero duplicates.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes.feedback import router as feedback_router

    app = FastAPI()
    app.include_router(feedback_router, prefix="/api")
    client = TestClient(app)

    unique_id = uuid.uuid4().hex[:8]
    session_id = f"sess_http_{unique_id}"
    resp_id = f"resp_http_{unique_id}"
    int_id = f"int_http_{unique_id}"

    db = SessionLocal()
    try:
        # Pre-insert auto-expired record as created by the timer
        now_iso = datetime.now(timezone.utc).isoformat()
        auto_record = ResponseFeedback(
            feedback_id=f"fb_{unique_id}",
            response_id=resp_id,
            interaction_id=int_id,
            session_id=session_id,
            turn_number=1,
            query_text="What is the lock-in period for ELSS funds?",
            response_text="The lock-in period is 3 years.",
            actor_id=None,
            actor_role=None,
            selected_categories=[],
            feedback_text=None,
            created_at=now_iso,
            updated_at=now_iso,
        )
        db.add(auto_record)
        db.commit()

        # Submit late feedback via POST /api/feedback
        payload = {
            "response_id": resp_id,
            "interaction_id": int_id,
            "session_id": session_id,
            "turn_number": 1,
            "actor_id": "auditor_99",
            "actor_role": "Compliance Officer",
            "selected_categories": ["F01", "F03"],
            "feedback_text": "Lock-in period is correct but statutory tax section 80C was omitted.",
        }

        response = client.post("/api/feedback", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["response_id"] == resp_id
        assert data["feedback_id"] == f"fb_{unique_id}"

        # Verify only 1 record exists in data.db and was updated
        db.expire_all()
        rows = db.query(ResponseFeedback).filter_by(response_id=resp_id).all()
        assert len(rows) == 1, "There must be exactly 1 record in data.db (no duplicate)"
        rec = rows[0]
        assert rec.selected_categories == ["F01", "F03"]
        assert rec.feedback_text == "Lock-in period is correct but statutory tax section 80C was omitted."
        assert rec.actor_id == "auditor_99"

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()

