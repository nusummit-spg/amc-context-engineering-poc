# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.query_evidence_table import QueryEvidence
from app.feedback.metrics_enrichment import MetricsEnricher, get_metrics_enricher


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.asyncio
async def test_enrich_with_query_evidence_high_quality(in_memory_db):
    """Enriches with high quality score (>= 8.0)."""
    resp_id = f"resp_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    feedback = ResponseFeedback(
        feedback_id=f"fb_{uuid.uuid4().hex[:8]}",
        response_id=resp_id,
        interaction_id="int_1",
        session_id=sess_id,
        turn_number=1,
        query_text="What is TER?",
        selected_categories=[],
        created_at=now_iso,
        updated_at=now_iso,
    )
    evidence = QueryEvidence(
        response_id=resp_id,
        session_id=sess_id,
        query_text="What is TER?",
        assembled_context_json={},
        synthesis_output_json={"answer": "The TER is 1.5%."},
        quality_score=8.5,
        created_at=now_iso,
    )
    in_memory_db.add(feedback)
    in_memory_db.add(evidence)
    in_memory_db.commit()

    enricher = MetricsEnricher()
    success = await enricher.enrich_response(sess_id, resp_id, db=in_memory_db)
    assert success is True

    updated_fb = in_memory_db.query(ResponseFeedback).filter_by(response_id=resp_id).first()
    assert updated_fb.automated_category == "auto_high_quality"
    assert updated_fb.automated_confidence == 0.85
    assert updated_fb.response_text == "The TER is 1.5%."


@pytest.mark.asyncio
async def test_enrich_with_query_evidence_medium_and_low(in_memory_db):
    """Tests categorization of medium (5-8) and low (<5) quality scores."""
    enricher = MetricsEnricher()
    cat_med, conf_med = enricher._categorize_quality(6.5)
    assert cat_med == "auto_medium_quality"
    assert conf_med == 0.65

    cat_low, conf_low = enricher._categorize_quality(4.2)
    assert cat_low == "auto_low_quality"
    assert conf_low == 0.42

    cat_comp, conf_comp = enricher._categorize_quality(9.0, compliance_severity="HIGH")
    assert cat_comp == "auto_compliance_issue"
    assert conf_comp == 0.90


@pytest.mark.asyncio
async def test_enrich_implicit_positive_after_timeout(in_memory_db):
    """Enriches with implicit_positive if dwell time >= 180s without user complaint."""
    resp_id = f"resp_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_{uuid.uuid4().hex[:8]}"
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()

    feedback = ResponseFeedback(
        feedback_id=f"fb_{uuid.uuid4().hex[:8]}",
        response_id=resp_id,
        interaction_id="int_1",
        session_id=sess_id,
        turn_number=1,
        query_text="What is NAV?",
        selected_categories=[],
        created_at=old_time,
        updated_at=old_time,
    )
    in_memory_db.add(feedback)
    in_memory_db.commit()

    enricher = MetricsEnricher()
    success = await enricher.enrich_response(sess_id, resp_id, db=in_memory_db)
    assert success is True

    updated_fb = in_memory_db.query(ResponseFeedback).filter_by(response_id=resp_id).first()
    assert updated_fb.automated_category == "implicit_positive"
    assert updated_fb.automated_confidence == 0.70


@pytest.mark.asyncio
async def test_enrich_idempotency(in_memory_db):
    """Already human-reviewed or categorized records should not be overwritten."""
    resp_id = f"resp_{uuid.uuid4().hex[:8]}"
    sess_id = f"sess_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    feedback = ResponseFeedback(
        feedback_id=f"fb_{uuid.uuid4().hex[:8]}",
        response_id=resp_id,
        interaction_id="int_1",
        session_id=sess_id,
        turn_number=1,
        query_text="What is NAV?",
        actor_id="user_admin",
        selected_categories=["F08"],
        automated_category="manual_correction",
        created_at=now_iso,
        updated_at=now_iso,
    )
    in_memory_db.add(feedback)
    in_memory_db.commit()

    enricher = MetricsEnricher()
    success = await enricher.enrich_response(sess_id, resp_id, db=in_memory_db)
    assert success is True

    unchanged = in_memory_db.query(ResponseFeedback).filter_by(response_id=resp_id).first()
    assert unchanged.automated_category == "manual_correction"
    assert unchanged.actor_id == "user_admin"


@pytest.mark.asyncio
async def test_enrich_nonexistent_returns_false(in_memory_db):
    """Enriching a non-existent response returns False cleanly."""
    enricher = MetricsEnricher()
    success = await enricher.enrich_response("nonexistent_session", "nonexistent_response", db=in_memory_db)
    assert success is False
