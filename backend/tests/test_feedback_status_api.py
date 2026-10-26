# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_feedback_status_api.py
===========================
Integration tests for Contextual Feedback-Status Awareness API endpoints:
- GET /api/feedback/status (read-only probe on modal open)
- POST /api/feedback (linking to existing issue and updating contributor count)
- Query lookup via response_id
- Entity guard in API layer
- Multi-user contributor aggregation
"""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from app.core.database import SessionLocal
from app.feedback.issue_matcher import reset_issue_matcher
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.feedback_issues_table import FeedbackIssue
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.response_feedback_table import ResponseFeedback


@pytest.fixture(scope="module")
def client():
    """TestClient fixture initializing FastAPI application."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_matcher_state():
    session = SessionLocal()
    session.query(ResponseFeedback).delete()
    session.query(FeedbackIssue).delete()
    session.commit()
    session.close()
    reset_issue_matcher()
    yield
    session = SessionLocal()
    session.query(ResponseFeedback).delete()
    session.query(FeedbackIssue).delete()
    session.commit()
    session.close()
    reset_issue_matcher()


@pytest.fixture
def db_session():
    """Database session fixture that cleans up test records."""
    session: Session = SessionLocal()
    created_response_ids = []
    created_feedback_ids = []
    created_issue_ids = []
    created_session_ids = []

    def register(response_id=None, feedback_id=None, issue_id=None, session_id=None):
        if response_id:
            created_response_ids.append(response_id)
        if feedback_id:
            created_feedback_ids.append(feedback_id)
        if issue_id:
            created_issue_ids.append(issue_id)
        if session_id:
            created_session_ids.append(session_id)

    session.register = register

    try:
        yield session
    finally:
        try:
            for fb_id in created_feedback_ids:
                session.query(ResponseFeedback).filter(ResponseFeedback.feedback_id == fb_id).delete()
            for resp_id in created_response_ids:
                session.query(ResponseFeedback).filter(ResponseFeedback.response_id == resp_id).delete()
                session.query(QueryEvidence).filter(QueryEvidence.response_id == resp_id).delete()
            for iss_id in created_issue_ids:
                session.query(FeedbackIssue).filter(FeedbackIssue.issue_id == iss_id).delete()
            for sess_id in created_session_ids:
                session.query(ChatSession).filter(ChatSession.session_id == sess_id).delete()
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()


def test_status_endpoint_no_existing_issue(client):
    """GET /api/feedback/status returns has_existing_issue=False when no issues exist."""
    resp = client.get("/api/feedback/status?query=How is alpha calculated for equity mutual funds?")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_existing_issue"] is False


def test_e2e_feedback_status_awareness_journey(client, db_session):
    """
    Full end-to-end multi-user journey:
    1. Alice submits feedback for a query -> Issue created.
    2. Bob opens modal on identical query -> GET /api/feedback/status shows banner with contributor_count=1.
    3. Bob submits feedback -> linked to Alice's issue, contributor_count=2.
    4. Carol checks status via response_id -> sees existing issue.
    5. Dave checks status for a query about a DIFFERENT fund -> has_existing_issue=False.
    """
    uid = uuid.uuid4().hex[:8]
    resp_id_alice = f"resp_{uid}_1"
    session_id_alice = f"sess_{uid}_1"
    query_text = "What is the expense ratio of NuSummit Bluechip Fund?"

    # Seed ChatSession and QueryEvidence for Alice's response turn
    chat_sess_alice = ChatSession(
        session_id=session_id_alice,
        user_id="alice",
        created_at="2026-10-14T00:00:00Z",
        updated_at="2026-10-14T00:00:00Z",
    )
    db_session.add(chat_sess_alice)
    db_session.commit()
    db_session.register(session_id=session_id_alice)

    qe_alice = QueryEvidence(
        response_id=resp_id_alice,
        session_id=session_id_alice,
        user_id="alice",
        query_text=query_text,
        assembled_context_json=[{"content": "sample context"}],
        synthesis_output_json={"answer": "1.25%"},
        retrieval_mode="contextgraph",
        created_at="2026-10-14T00:00:00Z",
    )
    db_session.add(qe_alice)
    db_session.commit()
    db_session.register(response_id=resp_id_alice)

    # 1. Alice submits feedback
    alice_payload = {
        "response_id": resp_id_alice,
        "interaction_id": f"int_{uid}_1",
        "session_id": session_id_alice,
        "turn_number": 1,
        "query_text": query_text,
        "actor_id": "alice@amc.com",
        "actor_role": "Analyst",
        "selected_categories": ["F01"],
        "feedback_text": "TER reported is 1.25% but current TER is 1.45%",
    }
    headers = {"X-User-Role": "Reviewer"}
    alice_res = client.post("/api/feedback", json=alice_payload, headers=headers)
    assert alice_res.status_code == 201
    alice_data = alice_res.json()
    assert alice_data["status"] == "recorded"
    assert alice_data["was_matched_to_existing_issue"] is False
    assert alice_data["issue_id"] is not None
    created_issue_id = alice_data["issue_id"]
    db_session.register(feedback_id=alice_data["feedback_id"], issue_id=created_issue_id)

    # 2. Bob opens feedback modal for identical query
    status_res = client.get(
        f"/api/feedback/status?query={query_text}",
        headers=headers,
    )
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["has_existing_issue"] is True
    assert status_data["issue_id"] == created_issue_id
    assert status_data["status"] == "reported"
    assert status_data["match_type"] == "exact"
    assert status_data["contributor_count"] == 1
    assert "already been reported" in status_data["message"]

    # 3. Bob submits feedback on the same issue
    resp_id_bob = f"resp_{uid}_2"
    bob_payload = {
        "response_id": resp_id_bob,
        "interaction_id": f"int_{uid}_2",
        "session_id": f"sess_{uid}_2",
        "turn_number": 1,
        "query_text": query_text,
        "actor_id": "bob@amc.com",
        "actor_role": "Analyst",
        "selected_categories": ["F01"],
        "feedback_text": "Confirmed, TER is outdated",
    }
    bob_res = client.post("/api/feedback", json=bob_payload, headers=headers)
    assert bob_res.status_code == 201
    bob_data = bob_res.json()
    assert bob_data["was_matched_to_existing_issue"] is True
    assert bob_data["issue_id"] == created_issue_id
    db_session.register(feedback_id=bob_data["feedback_id"])

    # Verify contributor count is now 2
    status_after_bob = client.get(f"/api/feedback/status?query={query_text}", headers=headers)
    assert status_after_bob.json()["contributor_count"] == 2

    # 4. Carol checks status via response_id (without providing query string)
    status_via_resp = client.get(f"/api/feedback/status?response_id={resp_id_alice}", headers=headers)
    assert status_via_resp.status_code == 200
    assert status_via_resp.json()["has_existing_issue"] is True
    assert status_via_resp.json()["issue_id"] == created_issue_id

    # 5. Dave checks status for a query about a DIFFERENT fund
    status_diff_fund = client.get(
        "/api/feedback/status?query=What is the expense ratio of NuSummit Debt Fund?",
        headers=headers,
    )
    assert status_diff_fund.status_code == 200
    # Must NOT match due to Entity Guard!
    assert status_diff_fund.json()["has_existing_issue"] is False
