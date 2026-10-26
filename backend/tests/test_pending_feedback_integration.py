# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_pending_feedback_integration.py
====================================
Integration tests for Feedback Pending Repair Notification API endpoints:
- GET /api/feedback/pending-notice
- GET /api/query/{response_id}/pending-feedback
- POST /api/admin/intent-cache/clear integration
- Role-based privacy on API endpoints
"""

import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from app.core.database import SessionLocal
from app.feedback.intent_matcher import clear_pending_feedback_cache, reset_cache_clear_timestamp
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.models import EntryRoute, RootCause, LifecycleStatus, RepairTarget


@pytest.fixture(scope="module")
def client():
    """TestClient fixture initializing FastAPI application."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_cache_state():
    """Reset notice cache and suppress timestamps around tests."""
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


def seed_pending_feedback(
    db: Session,
    query_text: str,
    categories: list = None,
    feedback_text: str = "TER calculation is wrong",
    repair: bool = True,
    lifecycle_status: LifecycleStatus = LifecycleStatus.OPEN,
    actor_id: str = "reviewer_a",
):
    uid = uuid.uuid4().hex[:8]
    resp_id = f"resp_api_{uid}"
    fb_id = f"fb_api_{uid}"
    now_iso = datetime.now(timezone.utc).isoformat()

    if categories is None:
        categories = ["F02"]

    qe = QueryEvidence(
        response_id=resp_id,
        session_id=f"sess_{uid}",
        query_text=query_text,
        assembled_context_json=[{"content": "mock"}],
        synthesis_output_json={"answer": "mock"},
        retrieval_mode="contextgraph",
        created_at=now_iso,
    )
    db.add(qe)

    fb = ResponseFeedback(
        feedback_id=fb_id,
        response_id=resp_id,
        interaction_id=f"int_{uid}",
        session_id=f"sess_{uid}",
        turn_number=1,
        query_text=query_text,
        actor_id=actor_id,
        actor_role="Compliance Officer",
        selected_categories=categories,
        feedback_text=feedback_text,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(fb)

    uer = UnifiedEvaluationRecord(
        response_id=resp_id,
        session_id=f"sess_{uid}",
        entry_route=EntryRoute.HITL,
        feedback_ref=fb_id,
        evidence_snapshot_ref=resp_id,
        root_cause=RootCause.RETRIEVAL,
        lifecycle_status=lifecycle_status,
        repair=repair,
        repair_target=RepairTarget.VECTOR if repair else None,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(uer)
    db.commit()

    if hasattr(db, "register"):
        db.register(response_id=resp_id, feedback_id=fb_id)

    return resp_id, fb_id


def test_get_pending_notice_no_match(client):
    """GET /api/feedback/pending-notice returns null when no matching repair exists."""
    res = client.get(
        "/api/feedback/pending-notice",
        params={"query": "A completely unprecedented query with no previous reports 12345"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "pending_feedback_notice" in data
    assert data["pending_feedback_notice"] is None


def test_get_pending_notice_with_match(client, db_session):
    """GET /api/feedback/pending-notice returns notice when matching pending repair exists."""
    test_query = "What is the portfolio turnover ratio of Franklin India Bluechip Fund?"
    seed_pending_feedback(
        db_session,
        query_text=test_query,
        categories=["F02", "F03"],
        feedback_text="Portfolio turnover is 24%, not 12%",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
    )

    # Different user checks as non-admin viewer
    res = client.get(
        "/api/feedback/pending-notice",
        params={
            "query": test_query,
            "actor_id": "user_beta",
        },
        headers={"X-User-Role": "viewer"},
    )
    assert res.status_code == 200
    data = res.json()
    notice = data["pending_feedback_notice"]
    assert notice is not None
    assert notice["has_pending_feedback"] is True
    assert notice["repair_lifecycle_status"] == "open"
    assert "F02" in notice["feedback_categories"]
    assert notice["similarity_score"] >= 0.99
    # Non-admin user should not see original query text
    assert notice["original_query_text"] is None


def test_get_pending_notice_admin_privacy(client, db_session):
    """Admin role sees original_query_text while non-admin has it masked."""
    test_query = "What is the benchmark index for Mirae Asset Large Cap Fund?"
    seed_pending_feedback(
        db_session,
        query_text=test_query,
        categories=["F01"],
        feedback_text="Benchmark was updated to NIFTY 100 TRI",
        repair=True,
        lifecycle_status=LifecycleStatus.DIAGNOSING,
        actor_id="user_alpha",
    )

    # Call with Admin header
    res = client.get(
        "/api/feedback/pending-notice",
        params={
            "query": test_query,
            "actor_id": "user_admin",
        },
        headers={"X-User-Role": "admin"},
    )
    assert res.status_code == 200
    notice = res.json()["pending_feedback_notice"]
    assert notice is not None
    assert notice["original_query_text"] == test_query


def test_clear_intent_cache_invalidates_notice(client, db_session):
    """POST /api/admin/intent-cache/clear clears cache and suppresses prior pending notices."""
    test_query = "What is the standard deviation of Axis Small Cap Fund?"
    seed_pending_feedback(
        db_session,
        query_text=test_query,
        categories=["F02"],
        feedback_text="Risk metric calculation discrepancy",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
    )

    # Notice is visible before clear
    res1 = client.get(
        "/api/feedback/pending-notice",
        params={"query": test_query, "actor_id": "user_beta"},
    )
    assert res1.status_code == 200
    assert res1.json()["pending_feedback_notice"] is not None

    # Clear intent cache via admin API
    clear_res = client.post(
        "/api/admin/intent-cache/clear",
        headers={"X-User-Role": "admin"},
    )
    assert clear_res.status_code == 200
    clear_data = clear_res.json()
    assert "feedback_pending_notice_cache" in clear_data.get("cleared_layers", [])

    # Notice is now suppressed
    res2 = client.get(
        "/api/feedback/pending-notice",
        params={"query": test_query, "actor_id": "user_beta"},
    )
    assert res2.status_code == 200
    assert res2.json()["pending_feedback_notice"] is None


def test_get_response_pending_feedback_notice_endpoint(client, db_session):
    """GET /api/query/{response_id}/pending-feedback returns notice for a specific response."""
    test_query = "What is the Sharpe ratio of DSP Flexi Cap Fund?"
    resp_id, fb_id = seed_pending_feedback(
        db_session,
        query_text=test_query,
        categories=["F02"],
        feedback_text="Sharpe ratio uses wrong risk free rate",
        repair=True,
        lifecycle_status=LifecycleStatus.OPEN,
        actor_id="user_alpha",
    )

    res = client.get(f"/api/query/{resp_id}/pending-feedback")
    assert res.status_code == 200
    data = res.json()
    assert "pending_feedback_notice" in data
    # Note: query by same query returns notice
    assert data["pending_feedback_notice"] is not None
    assert data["pending_feedback_notice"]["has_pending_feedback"] is True
