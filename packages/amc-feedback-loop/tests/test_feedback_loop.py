"""
Unit tests for amc-feedback-loop package.
"""
import pytest
import tempfile
import os
from pathlib import Path
from amc_feedback import FeedbackLoop, FeedbackConfig, SQLiteAdapter, FollowUpDetectionRequest

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if Path(path).exists():
        Path(path).unlink()

@pytest.mark.asyncio
async def test_process_correction_feedback(temp_db):
    config = FeedbackConfig(domain_name="amc", fuzzy_match_threshold=0.7)
    db = SQLiteAdapter(temp_db)
    loop = FeedbackLoop(config=config, db_adapter=db)

    claim = await loop.process_feedback(
        session_id="s1",
        response_id="r1",
        feedback_text="Axis Bluechip Fund TER is actually 0.82%, not 0.79%",
        original_query="What is TER?",
        original_response="TER is 0.79%"
    )

    assert claim is not None
    assert claim.attribute == "TER"
    assert claim.asserted_value == "0.82"
    assert claim.rejected_value == "0.79"
    assert claim.resolved_entity_name == "Axis Bluechip Fund"
    await loop.close()

@pytest.mark.asyncio
async def test_positive_feedback_ignored(temp_db):
    config = FeedbackConfig(domain_name="amc")
    db = SQLiteAdapter(temp_db)
    loop = FeedbackLoop(config=config, db_adapter=db)

    claim = await loop.process_feedback(
        session_id="s2",
        response_id="r2",
        feedback_text="Thank you, this answer was very helpful and accurate!",
        original_query="What is TER?",
        original_response="TER is 0.79%"
    )

    assert claim is None
    await loop.close()

@pytest.mark.asyncio
async def test_follow_up_detection(temp_db):
    config = FeedbackConfig(domain_name="amc")
    db = SQLiteAdapter(temp_db)
    loop = FeedbackLoop(config=config, db_adapter=db)

    req = FollowUpDetectionRequest(
        session_id="s3",
        previous_response_id="r3",
        original_query="What is the TER of Axis Bluechip Fund?",
        original_response="The TER is 0.79%",
        follow_up_query="No, Axis Bluechip Fund TER is actually 0.82%",
    )
    res = await loop.detect_follow_up(req)

    assert res.is_correction is True
    assert res.structured_claim is not None
    assert res.structured_claim.attribute == "TER"
    assert res.structured_claim.asserted_value == "0.82"
    await loop.close()
