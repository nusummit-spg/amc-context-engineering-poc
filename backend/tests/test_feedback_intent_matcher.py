# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_feedback_intent_matcher.py
===============================
Unit tests for FeedbackIntentMatcher:
- Exact and semantic query matching
- Filter by non-empty selected_categories and feedback_text
- Check repair status in UnifiedEvaluationRecord (pending: open / diagnosing)
- Suppress notice for same user (actor_id / session_id)
- Suppress notice when intent cache is cleared
- Handle multiple matches (highest similarity + match_count)
- Privacy masking: strip original_query_text for non-admins
- Cross-domain mismatch filtering
"""

import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.feedback.intent_matcher import (
    FeedbackIntentMatcher,
    get_intent_matcher,
    clear_pending_feedback_cache,
    reset_cache_clear_timestamp,
)
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.models import EntryRoute, RootCause, LifecycleStatus, RepairTarget


@pytest.fixture(autouse=True)
def clean_cache_state():
    """Ensure in-memory caches and suppress flags are reset before each test."""
    clear_pending_feedback_cache(suppress_prior_feedbacks=False)
    reset_cache_clear_timestamp()
    yield
    clear_pending_feedback_cache(suppress_prior_feedbacks=False)
    reset_cache_clear_timestamp()


@pytest.fixture
def db_session():
    """Yield a database session and clean up created test records after each test."""
    session: Session = SessionLocal()
    created_response_ids = []
    created_feedback_ids = []

    def register(response_id=None, feedback_id=None):
        if response_id:
            created_response_ids.append(response_id)
        if feedback_id:
            created_feedback_ids.append(feedback_id)

    session.register = register

    try:
        yield session
    finally:
        try:
            for resp_id in created_response_ids:
                session.query(UnifiedEvaluationRecord).filter(
                    UnifiedEvaluationRecord.response_id == resp_id
                ).delete()
            for fb_id in created_feedback_ids:
                session.query(ResponseFeedback).filter(
                    ResponseFeedback.feedback_id == fb_id
                ).delete()
            for resp_id in created_response_ids:
                session.query(QueryEvidence).filter(
                    QueryEvidence.response_id == resp_id
                ).delete()
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()


def create_fixture_records(
    db: Session,
    query_text: str,
    categories: list = None,
    feedback_text: str = "Issue with calculation",
    repair: bool = True,
    repair_target: str = "vector",
    lifecycle_status: LifecycleStatus = LifecycleStatus.OPEN,
    actor_id: str = "user_alpha",
    session_id: str = "session_alpha",
    created_at: str = None,
):
    """Helper to insert QueryEvidence, ResponseFeedback, and UnifiedEvaluationRecord."""
    uid = uuid.uuid4().hex[:8]
    resp_id = f"resp_{uid}"
    fb_id = f"fb_{uid}"
    now_iso = created_at or datetime.now(timezone.utc).isoformat()

    if categories is None:
        categories = ["F02"]

    # 1. QueryEvidence
    qe = QueryEvidence(
        response_id=resp_id,
        session_id=session_id,
        query_text=query_text,
        assembled_context_json=[{"content": "sample context"}],
        synthesis_output_json={"answer": "sample answer"},
        retrieval_mode="contextgraph",
        created_at=now_iso,
    )
    db.add(qe)

    # 2. ResponseFeedback
    fb = ResponseFeedback(
        feedback_id=fb_id,
        response_id=resp_id,
        interaction_id=f"int_{uid}",
        session_id=session_id,
        turn_number=1,
        query_text=query_text,
        actor_id=actor_id,
        actor_role="Analyst",
        selected_categories=categories,
        feedback_text=feedback_text,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(fb)

    # 3. UnifiedEvaluationRecord
    uer = UnifiedEvaluationRecord(
        response_id=resp_id,
        session_id=session_id,
        entry_route=EntryRoute.HITL,
        feedback_ref=fb_id,
        evidence_snapshot_ref=resp_id,
        root_cause=RootCause.RETRIEVAL,
        lifecycle_status=lifecycle_status,
        repair=repair,
        repair_target=RepairTarget(repair_target) if (repair and repair_target) else None,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(uer)
    db.commit()

    if hasattr(db, "register"):
        db.register(response_id=resp_id, feedback_id=fb_id)

    return resp_id, fb_id


@pytest.mark.asyncio
async def test_exact_match_returns_pending_notice(db_session):
    """Exact query match should detect pending repair and return notice."""
    query = "What is the TER of Axis Bluechip Fund Direct Plan?"
    create_fixture_records(
        db_session,
        query_text=query,
        categories=["F02"],
        feedback_text="TER is shown as 0.75% but actual is 0.82%",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
    )

    matcher = FeedbackIntentMatcher(similarity_threshold=0.88)
    notice = await matcher.check_pending_feedback(
        query=query,
        actor_id="user_beta",  # Different user
        session_id="session_beta",
        db=db_session,
    )

    assert notice is not None
    assert notice.has_pending_feedback is True
    assert notice.similarity_score >= 0.99
    assert notice.repair_lifecycle_status == "open"
    assert "F02" in notice.feedback_categories
    assert notice.match_count == 1
    assert notice.suppressed_by_cache_clear is False


@pytest.mark.asyncio
async def test_semantic_match_returns_pending_notice(db_session):
    """Semantically close query should match above threshold."""
    create_fixture_records(
        db_session,
        query_text="What is the exit load for HDFC Top 100 Fund?",
        categories=["F01"],
        feedback_text="Incorrect exit load period mentioned",
        repair=True,
        lifecycle_status=LifecycleStatus.DIAGNOSING,
        actor_id="user_alpha",
    )

    matcher = FeedbackIntentMatcher(similarity_threshold=0.80)
    # Similar query with minor wording variation
    similar_query = "What is the exit load for HDFC Top 100?"
    notice = await matcher.check_pending_feedback(
        query=similar_query,
        actor_id="user_beta",
        session_id="session_beta",
        db=db_session,
    )

    assert notice is not None
    assert notice.has_pending_feedback is True
    assert notice.repair_lifecycle_status == "diagnosing"
    assert "F01" in notice.feedback_categories


@pytest.mark.asyncio
async def test_incomplete_feedback_not_matched(db_session):
    """Feedbacks missing categories or feedback_text must be ignored."""
    query = "What is the AUM of SBI Small Cap Fund?"

    # Case 1: Empty categories
    create_fixture_records(
        db_session,
        query_text=query,
        categories=[],
        feedback_text="Missing AUM details",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
    )

    matcher = FeedbackIntentMatcher(similarity_threshold=0.85)
    notice = await matcher.check_pending_feedback(
        query=query,
        actor_id="user_beta",
        db=db_session,
    )
    assert notice is None

    # Case 2: Empty feedback_text
    create_fixture_records(
        db_session,
        query_text="What is the benchmark of SBI Small Cap Fund?",
        categories=["F03"],
        feedback_text="",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
    )
    notice2 = await matcher.check_pending_feedback(
        query="What is the benchmark of SBI Small Cap Fund?",
        actor_id="user_beta",
        db=db_session,
    )
    assert notice2 is None


@pytest.mark.asyncio
async def test_resolved_repair_not_matched(db_session):
    """When repair is already resolved or not marked for repair, no notice should appear."""
    query = "What is the expense ratio for Nippon India Growth Fund?"

    # Resolved repair
    create_fixture_records(
        db_session,
        query_text=query,
        categories=["F02"],
        feedback_text="Expense ratio calculation was off",
        repair=True,
        lifecycle_status=LifecycleStatus.RESOLVED,
        actor_id="user_alpha",
    )

    matcher = FeedbackIntentMatcher(similarity_threshold=0.85)
    notice = await matcher.check_pending_feedback(
        query=query,
        actor_id="user_beta",
        db=db_session,
    )
    assert notice is None

    # Not marked for repair (repair=False)
    query_norepair = "What is the NAV of Nippon India Growth Fund?"
    create_fixture_records(
        db_session,
        query_text=query_norepair,
        categories=["F01"],
        feedback_text="User noted personal preference",
        repair=False,
        repair_target=None,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
    )
    notice_norepair = await matcher.check_pending_feedback(
        query=query_norepair,
        actor_id="user_beta",
        db=db_session,
    )
    assert notice_norepair is None


@pytest.mark.asyncio
async def test_same_user_suppression(db_session):
    """The user who submitted original feedback should NOT see the notice."""
    query = "What is the lock-in period for Mirae Asset ELSS Tax Saver Fund?"
    create_fixture_records(
        db_session,
        query_text=query,
        categories=["F04"],
        feedback_text="Incorrect lock-in period stated",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="compliance_officer_1",
    )

    matcher = FeedbackIntentMatcher(similarity_threshold=0.88)

    # 1. Same user queries -> Suppressed (None)
    same_user_notice = await matcher.check_pending_feedback(
        query=query,
        actor_id="compliance_officer_1",
        db=db_session,
    )
    assert same_user_notice is None

    # 2. Another user queries -> Notice shown
    other_user_notice = await matcher.check_pending_feedback(
        query=query,
        actor_id="compliance_officer_2",
        db=db_session,
    )
    assert other_user_notice is not None
    assert other_user_notice.has_pending_feedback is True


@pytest.mark.asyncio
async def test_intent_cache_clear_suppresses_prior_feedback(db_session):
    """Clearing intent cache suppresses notifications for feedbacks created prior to clear."""
    query = "What is the minimum SIP amount for Parag Parikh Flexi Cap Fund?"
    # Created 10 seconds ago
    past_iso = "2026-09-01T10:00:00+00:00"
    create_fixture_records(
        db_session,
        query_text=query,
        categories=["F02"],
        feedback_text="Minimum SIP is 1000 not 500",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
        created_at=past_iso,
    )

    matcher = FeedbackIntentMatcher(similarity_threshold=0.88)

    # 1. Query before clear -> notice is present
    notice_before = await matcher.check_pending_feedback(
        query=query,
        actor_id="user_beta",
        db=db_session,
    )
    assert notice_before is not None
    assert notice_before.has_pending_feedback is True

    # 2. Clear pending feedback cache with suppression
    clear_pending_feedback_cache(suppress_prior_feedbacks=True)

    # 3. Query after clear -> notice is suppressed because created_at is before cache clear
    notice_after = await matcher.check_pending_feedback(
        query=query,
        actor_id="user_beta",
        db=db_session,
    )
    assert notice_after is None

    # 4. Reset cache clear timestamp -> notice becomes visible again
    reset_cache_clear_timestamp()
    clear_pending_feedback_cache(suppress_prior_feedbacks=False)
    notice_restored = await matcher.check_pending_feedback(
        query=query,
        actor_id="user_beta",
        db=db_session,
    )
    assert notice_restored is not None


@pytest.mark.asyncio
async def test_multiple_matches_selects_highest_similarity(db_session):
    """When multiple pending feedbacks match, select the top similarity and report match_count."""
    base_query = "What is the fund manager name for Kotak Emerging Equity Scheme?"

    # Match 1: exact match
    create_fixture_records(
        db_session,
        query_text=base_query,
        categories=["F01"],
        feedback_text="Pankaj Tibrewal is no longer fund manager",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
    )

    # Match 2: slightly different query
    create_fixture_records(
        db_session,
        query_text="Who manages Kotak Emerging Equity Scheme?",
        categories=["F05"],
        feedback_text="Manager updated recently",
        repair=True,
        lifecycle_status=LifecycleStatus.DIAGNOSING,
        actor_id="user_gamma",
    )

    matcher = FeedbackIntentMatcher(similarity_threshold=0.75)
    notice = await matcher.check_pending_feedback(
        query=base_query,
        actor_id="user_beta",
        db=db_session,
    )

    assert notice is not None
    assert notice.has_pending_feedback is True
    assert notice.match_count >= 2
    # Exact match similarity should be 1.0
    assert notice.similarity_score >= 0.99
    assert notice.repair_lifecycle_status == "open"


@pytest.mark.asyncio
async def test_privacy_masking_original_query(db_session):
    """Original query text must be stripped for non-admin roles and visible only to admin."""
    query = "What is the riskometer category of ICICI Prudential Bluechip?"
    create_fixture_records(
        db_session,
        query_text=query,
        categories=["F03"],
        feedback_text="Riskometer is Very High, not High",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
    )

    matcher = FeedbackIntentMatcher(similarity_threshold=0.88)

    # 1. Regular user role -> original_query_text is None
    user_notice = await matcher.check_pending_feedback(
        query=query,
        actor_id="user_beta",
        role="Investor / User",
        db=db_session,
    )
    assert user_notice is not None
    assert user_notice.original_query_text is None

    # Clear query cache to avoid cached notice with same key
    clear_pending_feedback_cache(suppress_prior_feedbacks=False)

    # 2. Admin role -> original_query_text is exposed
    admin_notice = await matcher.check_pending_feedback(
        query=query,
        actor_id="admin_user",
        role="Admin Compliance Officer",
        db=db_session,
    )
    assert admin_notice is not None
    assert admin_notice.original_query_text == query
