# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_feedback_phase1_categories_and_mine.py
============================================
Phase 1 Integration and Unit tests for:
1. `categories` JSON column on response_feedback.
2. `feedback_issue_category_counts` atomic UPSERT and running totals.
3. `GET /api/feedback/status` category breakdown and feature flag toggle.
4. `GET /api/feedback/mine` strictly session-scoped retrieval, anonymization, and IDOR protection.
5. Multi-tenant isolation for /mine endpoint.
6. Category count drift reconciliation job scaffolding.
"""

import uuid
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from app.config import get_settings
from app.core.database import SessionLocal
from app.auth.security import hash_password, issue_session_token
from app.feedback.issue_matcher import reset_issue_matcher
from app.feedback import issue_store
from app.schemas.auth_users_table import AuthUser
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.feedback_issues_table import FeedbackIssue
from app.schemas.feedback_issue_category_counts_table import FeedbackIssueCategoryCount
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.response_feedback_table import ResponseFeedback


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_test_state():
    session = SessionLocal()
    session.query(FeedbackIssueCategoryCount).delete()
    session.query(ResponseFeedback).delete()
    session.query(FeedbackIssue).delete()
    session.commit()
    session.close()
    reset_issue_matcher()
    yield
    session = SessionLocal()
    session.query(FeedbackIssueCategoryCount).delete()
    session.query(ResponseFeedback).delete()
    session.query(FeedbackIssue).delete()
    session.commit()
    session.close()
    reset_issue_matcher()


@pytest.fixture
def test_users(db_session):
    """Create test users in auth_users table and return auth tokens."""
    settings = get_settings()
    created_usernames = []

    def make_user(username: str, role: str = "Reviewer", tenant_id: str = None) -> tuple[str, str]:
        user = db_session.query(AuthUser).filter(AuthUser.username == username).first()
        if not user:
            user = AuthUser(
                username=username,
                password_hash=hash_password("Password123!"),
                display_name=f"User {username}",
                email=f"{username}@amc.com",
                role=role,
                department="Compliance",
                status="Active",
                tenant_id=tenant_id,
            )
            db_session.add(user)
            db_session.commit()
            created_usernames.append(username)
        token, _ = issue_session_token(username, settings.auth_secret_key, ttl_minutes=60)
        return username, token

    u_alice, tok_alice = make_user("alice_p1", role="Reviewer", tenant_id="tenant_a")
    u_bob, tok_bob = make_user("bob_p1", role="Reviewer", tenant_id="tenant_a")
    u_carol, tok_carol = make_user("carol_p1", role="Reviewer", tenant_id="tenant_b")

    yield {
        "alice": {"username": u_alice, "token": tok_alice, "tenant": "tenant_a"},
        "bob": {"username": u_bob, "token": tok_bob, "tenant": "tenant_a"},
        "carol": {"username": u_carol, "token": tok_carol, "tenant": "tenant_b"},
    }

    session = SessionLocal()
    for un in created_usernames:
        session.query(AuthUser).filter(AuthUser.username == un).delete()
    session.commit()
    session.close()


@pytest.fixture
def db_session():
    session: Session = SessionLocal()
    created_sessions = []
    created_responses = []

    def register(session_id=None, response_id=None):
        if session_id:
            created_sessions.append(session_id)
        if response_id:
            created_responses.append(response_id)

    session.register = register
    try:
        yield session
    finally:
        try:
            for rid in created_responses:
                session.query(ResponseFeedback).filter(ResponseFeedback.response_id == rid).delete()
                session.query(QueryEvidence).filter(QueryEvidence.response_id == rid).delete()
            for sid in created_sessions:
                session.query(ChatSession).filter(ChatSession.session_id == sid).delete()
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()


def test_feedback_categories_column_and_atomic_upsert(client, db_session, test_users):
    """
    Test 1: Categories JSON column stores selected categories.
    Test 2: Atomic UPSERT running totals in feedback_issue_category_counts.
    """
    uid = uuid.uuid4().hex[:8]
    sess_id = f"sess_{uid}"
    resp_id = f"resp_{uid}"
    query = "What is the exit load for NuSummit Flexicap Fund?"

    chat_sess = ChatSession(session_id=sess_id, user_id="alice_p1")
    db_session.add(chat_sess)
    db_session.commit()
    db_session.register(session_id=sess_id, response_id=resp_id)

    # Alice submits feedback with categories F08 and F04
    headers_alice = {
        "Authorization": f"Bearer {test_users['alice']['token']}",
        "X-User-Role": "Reviewer",
    }
    payload_alice = {
        "response_id": resp_id,
        "interaction_id": f"int_{uid}_1",
        "session_id": sess_id,
        "turn_number": 1,
        "query_text": query,
        "selected_categories": ["F08", "F04"],
        "feedback_text": "Wrong exit load percentage and circular reference",
    }

    res = client.post("/api/feedback", json=payload_alice, headers=headers_alice)
    assert res.status_code == 201
    issue_id = res.json()["issue_id"]
    assert issue_id is not None

    # Verify ResponseFeedback has categories populated
    rf = db_session.query(ResponseFeedback).filter(ResponseFeedback.response_id == resp_id).first()
    assert rf is not None
    assert rf.categories == ["F08", "F04"]
    assert rf.selected_categories == ["F08", "F04"]

    # Verify atomic UPSERT created entries with count 1
    c_f08 = db_session.query(FeedbackIssueCategoryCount).filter_by(issue_id=issue_id, category_code="F08").first()
    c_f04 = db_session.query(FeedbackIssueCategoryCount).filter_by(issue_id=issue_id, category_code="F04").first()
    assert c_f08 is not None and c_f08.count == 1
    assert c_f04 is not None and c_f04.count == 1

    # Bob submits feedback for identical query with categories F08 and F06
    resp_id_bob = f"resp_{uid}_bob"
    db_session.register(response_id=resp_id_bob)
    headers_bob = {
        "Authorization": f"Bearer {test_users['bob']['token']}",
        "X-User-Role": "Reviewer",
    }
    payload_bob = {
        "response_id": resp_id_bob,
        "interaction_id": f"int_{uid}_2",
        "session_id": sess_id,
        "turn_number": 1,
        "query_text": query,
        "selected_categories": ["F08", "F06"],
        "feedback_text": "Confirming wrong exit load number",
    }
    res_bob = client.post("/api/feedback", json=payload_bob, headers=headers_bob)
    assert res_bob.status_code == 201
    assert res_bob.json()["issue_id"] == issue_id

    # Verify category counts: F08 is now 2, F04 is 1, F06 is 1
    db_session.expire_all()
    c_f08_updated = db_session.query(FeedbackIssueCategoryCount).filter_by(issue_id=issue_id, category_code="F08").first()
    c_f04_updated = db_session.query(FeedbackIssueCategoryCount).filter_by(issue_id=issue_id, category_code="F04").first()
    c_f06_updated = db_session.query(FeedbackIssueCategoryCount).filter_by(issue_id=issue_id, category_code="F06").first()

    assert c_f08_updated.count == 2
    assert c_f04_updated.count == 1
    assert c_f06_updated.count == 1


def test_status_endpoint_category_breakdown_and_flag(client, db_session, test_users):
    """
    Test 3: GET /api/feedback/status returns sorted category_breakdown with labels.
    Test 4: Feature flag FEEDBACK_CATEGORY_BREAKDOWN_ENABLED toggles breakdown.
    """
    uid = uuid.uuid4().hex[:8]
    sess_id = f"sess_{uid}"
    resp_id = f"resp_{uid}"
    query = "What is the benchmark index for NuSummit Large Cap?"

    chat_sess = ChatSession(session_id=sess_id, user_id="alice_p1")
    db_session.add(chat_sess)
    db_session.commit()
    db_session.register(session_id=sess_id, response_id=resp_id)

    headers = {
        "Authorization": f"Bearer {test_users['alice']['token']}",
        "X-User-Role": "Reviewer",
    }
    payload = {
        "response_id": resp_id,
        "interaction_id": f"int_{uid}",
        "session_id": sess_id,
        "turn_number": 1,
        "query_text": query,
        "selected_categories": ["F01", "F08"],
        "feedback_text": "Wrong benchmark named",
    }
    res = client.post("/api/feedback", json=payload, headers=headers)
    assert res.status_code == 201
    issue_id = res.json()["issue_id"]

    # Call status endpoint
    status_res = client.get(f"/api/feedback/status?query={query}", headers=headers)
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["has_existing_issue"] is True
    assert data["issue_id"] == issue_id
    assert "category_breakdown" in data
    assert len(data["category_breakdown"]) == 2

    # Check breakdown format and labels
    codes = [item["code"] for item in data["category_breakdown"]]
    assert "F01" in codes
    assert "F08" in codes
    for item in data["category_breakdown"]:
        assert item["count"] >= 1
        assert len(item["label"]) > 0

    # Feature flag test: temporarily disable breakdown
    settings = get_settings()
    orig_flag = settings.feedback_category_breakdown_enabled
    try:
        settings.feedback_category_breakdown_enabled = False
        status_res_disabled = client.get(f"/api/feedback/status?query={query}", headers=headers)
        assert status_res_disabled.status_code == 200
        assert status_res_disabled.json().get("category_breakdown") is None
    finally:
        settings.feedback_category_breakdown_enabled = orig_flag


def test_get_my_feedback_authentication_and_idor(client, db_session, test_users):
    """
    Test 5: GET /api/feedback/mine requires authentication (401 on missing/invalid token).
    Test 6: User A sees only User A's feedback; User B sees only User B's.
    Test 7: IDOR negative test — tampering with query parameters does not reveal other users' issues.
    Test 8: Anonymization — contributors count is reported as also_reported_by_count without names.
    """
    # 1. Unauthenticated request must return 401
    unauth_res = client.get("/api/feedback/mine")
    assert unauth_res.status_code == 401

    invalid_res = client.get("/api/feedback/mine", headers={"Authorization": "Bearer invalid_token_123"})
    assert invalid_res.status_code == 401

    uid = uuid.uuid4().hex[:8]
    sess_alice = f"sess_{uid}_alice"
    sess_bob = f"sess_{uid}_bob"
    resp_alice = f"resp_{uid}_alice"
    resp_bob = f"resp_{uid}_bob"

    chat_sess_a = ChatSession(session_id=sess_alice, user_id=test_users["alice"]["username"])
    chat_sess_b = ChatSession(session_id=sess_bob, user_id=test_users["bob"]["username"])
    db_session.add_all([chat_sess_a, chat_sess_b])
    db_session.commit()
    db_session.register(session_id=sess_alice, response_id=resp_alice)
    db_session.register(session_id=sess_bob, response_id=resp_bob)

    query_a = "Query exclusively submitted by Alice regarding TER"
    query_b = "Query exclusively submitted by Bob regarding NAV"

    # Alice submits on query A
    client.post(
        "/api/feedback",
        json={
            "response_id": resp_alice,
            "interaction_id": f"int_{uid}_a",
            "session_id": sess_alice,
            "turn_number": 1,
            "query_text": query_a,
            "selected_categories": ["F08"],
            "feedback_text": "Alice commentary about TER",
        },
        headers={"Authorization": f"Bearer {test_users['alice']['token']}", "X-User-Role": "Reviewer"},
    )

    # Bob submits on query B
    client.post(
        "/api/feedback",
        json={
            "response_id": resp_bob,
            "interaction_id": f"int_{uid}_b",
            "session_id": sess_bob,
            "turn_number": 1,
            "query_text": query_b,
            "selected_categories": ["F02"],
            "feedback_text": "Bob commentary about NAV",
        },
        headers={"Authorization": f"Bearer {test_users['bob']['token']}", "X-User-Role": "Reviewer"},
    )

    # Alice views /api/feedback/mine
    mine_alice = client.get(
        "/api/feedback/mine",
        headers={"Authorization": f"Bearer {test_users['alice']['token']}"},
    )
    assert mine_alice.status_code == 200
    data_a = mine_alice.json()
    assert data_a["total"] == 1
    assert data_a["items"][0]["canonical_query_text"] == query_a
    assert data_a["items"][0]["user_reported_categories"] == ["F08"]
    assert data_a["items"][0]["user_feedback_texts"] == ["Alice commentary about TER"]
    assert data_a["items"][0]["also_reported_by_count"] == 0

    # Bob views /api/feedback/mine
    mine_bob = client.get(
        "/api/feedback/mine",
        headers={"Authorization": f"Bearer {test_users['bob']['token']}"},
    )
    assert mine_bob.status_code == 200
    data_b = mine_bob.json()
    assert data_b["total"] == 1
    assert data_b["items"][0]["canonical_query_text"] == query_b
    assert data_b["items"][0]["user_reported_categories"] == ["F02"]

    # IDOR test: Alice attempts to supply user_id/actor_id=bob_p1 in parameters
    idor_res = client.get(
        "/api/feedback/mine?user_id=bob_p1&actor_id=bob_p1",
        headers={"Authorization": f"Bearer {test_users['alice']['token']}"},
    )
    assert idor_res.status_code == 200
    idor_data = idor_res.json()
    # Must still ONLY return Alice's query A — Bob's query B must never be visible!
    assert idor_data["total"] == 1
    assert idor_data["items"][0]["canonical_query_text"] == query_a

    # Anonymization test: Bob now also reports query A
    resp_bob_a = f"resp_{uid}_bob_on_a"
    db_session.register(response_id=resp_bob_a)
    client.post(
        "/api/feedback",
        json={
            "response_id": resp_bob_a,
            "interaction_id": f"int_{uid}_b_on_a",
            "session_id": sess_bob,
            "turn_number": 2,
            "query_text": query_a,
            "selected_categories": ["F01"],
            "feedback_text": "Bob's private note on query A",
        },
        headers={"Authorization": f"Bearer {test_users['bob']['token']}", "X-User-Role": "Reviewer"},
    )

    # Alice views /mine again
    mine_alice_again = client.get(
        "/api/feedback/mine",
        headers={"Authorization": f"Bearer {test_users['alice']['token']}"},
    )
    assert mine_alice_again.status_code == 200
    data_a2 = mine_alice_again.json()
    assert data_a2["total"] == 1
    item_a2 = data_a2["items"][0]
    # Anonymized count: Bob is the 1 other contributor
    assert item_a2["also_reported_by_count"] == 1
    # Alice's view only contains Alice's categories (F08), not Bob's (F01)
    assert item_a2["user_reported_categories"] == ["F08"]
    # Alice's view only contains Alice's comment, never Bob's
    assert "Bob's private note on query A" not in item_a2["user_feedback_texts"]


def test_reconciliation_job(db_session):
    """
    Test 9: Category counts drift reconciliation job recomputes counts from raw response_feedback rows.
    """
    uid = uuid.uuid4().hex[:8]
    issue = FeedbackIssue(
        issue_id=f"iss_reconcile_{uid}",
        canonical_query_text="Reconciliation test query",
        query_hash=f"hash_{uid}",
        status="reported",
        contributor_count=2,
    )
    db_session.add(issue)
    db_session.commit()

    # Add two feedback entries with categories
    fb1 = ResponseFeedback(
        feedback_id=f"fb1_{uid}",
        response_id=f"resp1_{uid}",
        interaction_id="int1",
        session_id="sess1",
        turn_number=1,
        selected_categories=["F08", "F04"],
        categories=["F08", "F04"],
        issue_id=issue.issue_id,
    )
    fb2 = ResponseFeedback(
        feedback_id=f"fb2_{uid}",
        response_id=f"resp2_{uid}",
        interaction_id="int2",
        session_id="sess2",
        turn_number=1,
        selected_categories=["F08", "F06"],
        categories=["F08", "F06"],
        issue_id=issue.issue_id,
    )
    # Intentionally insert wrong drifted count
    wrong_count = FeedbackIssueCategoryCount(
        issue_id=issue.issue_id,
        category_code="F08",
        count=99,  # Drifted
    )
    db_session.add_all([fb1, fb2, wrong_count])
    db_session.commit()

    # Run reconciliation
    res = issue_store.reconcile_issue_category_counts(db=db_session, issue_id=issue.issue_id)
    assert res["reconciled_issues"] == 1

    # Verify drift corrected: F08 should be 2, F04 is 1, F06 is 1
    c_f08 = db_session.query(FeedbackIssueCategoryCount).filter_by(issue_id=issue.issue_id, category_code="F08").first()
    c_f04 = db_session.query(FeedbackIssueCategoryCount).filter_by(issue_id=issue.issue_id, category_code="F04").first()
    c_f06 = db_session.query(FeedbackIssueCategoryCount).filter_by(issue_id=issue.issue_id, category_code="F06").first()

    assert c_f08.count == 2
    assert c_f04.count == 1
    assert c_f06.count == 1
