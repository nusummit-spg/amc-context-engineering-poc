# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import os
import sys
from pathlib import Path

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.query_evidence_table import QueryEvidence
from app.feedback.session_manager import get_session_manager
from app.feedback.timeout_processor import TimeoutProcessor
from app.api.routes.feedback import run_follow_up_detection_logic


@pytest.fixture(scope="module")
def app_client():
    app = create_app()
    with TestClient(app) as client:
        yield client


def test_passive_feedback_health_endpoint(app_client):
    """GET /api/health/passive-feedback returns healthy status and session stats."""
    response = app_client.get("/api/health/passive-feedback")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert "session_count" in data
    assert data["timeout_seconds"] == 180
    assert data["enabled"] is True


@pytest.mark.asyncio
async def test_passive_detection_correction_workflow():
    """
    End-to-end flow:
    1. Turn 1 query response created with skeleton feedback.
    2. SessionManager registers response.
    3. Turn 2 follow-up correction arrives within 180s.
    4. Auto follow-up detection flags correction and populates F08 category.
    """
    unique_id = uuid.uuid4().hex[:8]
    session_id = f"test_sess_{unique_id}"
    resp1_id = f"resp_1_{unique_id}"
    resp2_id = f"resp_2_{unique_id}"

    db = SessionLocal()
    session_manager = get_session_manager()

    try:
        # Step 1: Create skeleton feedback for Turn 1
        now = datetime.now(timezone.utc)
        skeleton = ResponseFeedback(
            feedback_id=f"fb_{unique_id}",
            response_id=resp1_id,
            interaction_id=f"int_{unique_id}",
            session_id=session_id,
            turn_number=1,
            query_text="What is the TER of Axis Bluechip Fund?",
            actor_id=None,
            selected_categories=[],
            feedback_text=None,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        db.add(skeleton)
        db.commit()

        # Step 2: Register Turn 1 in SessionManager
        prev = await session_manager.register_response(
            session_id=session_id,
            response_id=resp1_id,
            query_text="What is the TER of Axis Bluechip Fund?",
            timestamp=now,
        )
        assert prev is None  # First turn

        # Step 3: Turn 2 arrives 30s later (correction attempt)
        later = now + timedelta(seconds=30)
        eligible_prev = await session_manager.register_response(
            session_id=session_id,
            response_id=resp2_id,
            query_text="No, that's wrong! The TER of Axis Bluechip Fund is actually 0.82%.",
            timestamp=later,
        )
        assert eligible_prev is not None
        assert eligible_prev.response_id == resp1_id

        # Mark detected to avoid re-triggering
        await session_manager.mark_detected(session_id, eligible_prev.response_id)

        # Step 4: Run detection logic
        result = await run_follow_up_detection_logic(
            session_id=session_id,
            previous_response_id=eligible_prev.response_id,
            follow_up_query="No, that's wrong! The TER of Axis Bluechip Fund is actually 0.82%.",
            original_query=eligible_prev.query_text,
            original_response="The TER of Axis Bluechip Fund is 0.70%.",
        )

        assert result["is_correction"] is True
        assert result["correction_detected"] is True
        assert result["feedback_created"] is True
        assert result["structured_claim"]["attribute"] == "TER"
        assert "0.82" in str(result["structured_claim"]["asserted_value"])

        # Verify DB feedback record was updated
        db.refresh(skeleton)
        assert "F08" in skeleton.selected_categories
        assert skeleton.automated_category == "auto_correction_detected"
        assert skeleton.automated_confidence > 0.0

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_passive_detection_benign_workflow():
    """Benign follow-up does not trigger correction or F08 tagging."""
    unique_id = uuid.uuid4().hex[:8]
    session_id = f"test_benign_{unique_id}"
    resp1_id = f"resp_1_{unique_id}"
    resp2_id = f"resp_2_{unique_id}"

    db = SessionLocal()
    session_manager = get_session_manager()

    try:
        now = datetime.now(timezone.utc)
        skeleton = ResponseFeedback(
            feedback_id=f"fb_{unique_id}",
            response_id=resp1_id,
            interaction_id=f"int_{unique_id}",
            session_id=session_id,
            turn_number=1,
            query_text="What is the NAV of SBI Small Cap Fund?",
            actor_id=None,
            selected_categories=[],
            feedback_text=None,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        db.add(skeleton)
        db.commit()

        await session_manager.register_response(
            session_id=session_id,
            response_id=resp1_id,
            query_text="What is the NAV of SBI Small Cap Fund?",
            timestamp=now,
        )

        later = now + timedelta(seconds=20)
        eligible_prev = await session_manager.register_response(
            session_id=session_id,
            response_id=resp2_id,
            query_text="Thanks! Can you also tell me who the fund manager is?",
            timestamp=later,
        )
        assert eligible_prev is not None

        result = await run_follow_up_detection_logic(
            session_id=session_id,
            previous_response_id=eligible_prev.response_id,
            follow_up_query="Thanks! Can you also tell me who the fund manager is?",
            original_query=eligible_prev.query_text,
            original_response="The NAV of SBI Small Cap Fund is 142.30.",
        )

        assert result["is_correction"] is False
        assert result["correction_detected"] is False

        db.refresh(skeleton)
        assert "F08" not in skeleton.selected_categories

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_timeout_enrichment_integration():
    """Verify TimeoutProcessor integrates with SessionManager to enrich expired turns."""
    unique_id = uuid.uuid4().hex[:8]
    session_id = f"test_timeout_{unique_id}"
    resp_id = f"resp_{unique_id}"

    db = SessionLocal()
    session_manager = get_session_manager()

    try:
        # Create response 200s ago (beyond 180s)
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=200))
        skeleton = ResponseFeedback(
            feedback_id=f"fb_{unique_id}",
            response_id=resp_id,
            interaction_id=f"int_{unique_id}",
            session_id=session_id,
            turn_number=1,
            query_text="Tell me about mutual fund taxation",
            actor_id=None,
            selected_categories=[],
            feedback_text=None,
            created_at=old_time.isoformat(),
            updated_at=old_time.isoformat(),
        )
        db.add(skeleton)
        db.commit()

        await session_manager.register_response(
            session_id=session_id,
            response_id=resp_id,
            query_text="Tell me about mutual fund taxation",
            timestamp=old_time,
        )

        processor = TimeoutProcessor(check_interval=1, timeout_seconds=180)
        enriched_count = await processor.process_timed_out_responses()

        assert enriched_count >= 1

        db.refresh(skeleton)
        assert skeleton.automated_category == "implicit_positive"
        assert skeleton.automated_confidence == 0.70

    finally:
        db.query(ResponseFeedback).filter(ResponseFeedback.session_id == session_id).delete()
        db.commit()
        db.close()
