# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
import pytest

from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback
from app.feedback.session_manager import SessionManager
from app.feedback.timeout_processor import TimeoutProcessor


@pytest.mark.asyncio
async def test_process_timed_out_responses():
    """Verify TimeoutProcessor enriches old responses."""
    resp_id = f"resp_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_{uuid.uuid4().hex[:8]}"
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()

    db = SessionLocal()
    try:
        feedback = ResponseFeedback(
            feedback_id=f"fb_{uuid.uuid4().hex[:8]}",
            response_id=resp_id,
            interaction_id="int_1",
            session_id=sess_id,
            turn_number=1,
            query_text="What is the exit load?",
            selected_categories=[],
            created_at=old_time,
            updated_at=old_time,
        )
        db.add(feedback)
        db.commit()

        processor = TimeoutProcessor(check_interval=1, timeout_seconds=180)
        enriched_count = await processor.process_timed_out_responses()

        assert enriched_count >= 1

        db.refresh(feedback)
        assert feedback.automated_category == "implicit_positive"
        assert feedback.automated_confidence == 0.70

    finally:
        db.query(ResponseFeedback).filter_by(response_id=resp_id).delete()
        db.commit()
        db.close()


@pytest.mark.asyncio
async def test_timeout_processor_lifecycle():
    """Verify start and stop lifecycle of TimeoutProcessor."""
    processor = TimeoutProcessor(check_interval=1, timeout_seconds=180)
    await processor.start()
    assert processor._running is True
    assert processor._task is not None

    # Wait briefly
    await asyncio.sleep(0.05)

    await processor.stop()
    assert processor._running is False
    assert processor._task is None
