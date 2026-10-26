# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_feedback_phase4_category_breakdown.py
==========================================
Phase 4 Integration tests covering:
1. Category breakdown presence in GET /api/feedback/status.
2. Descending count sorting of category breakdown items.
3. Top-5 capping of breakdown pills on the status endpoint.
4. Atomic upsert increments on feedback submissions.
5. Category reconciliation endpoint POST /api/feedback/reconcile-categories.
"""

import hashlib
import uuid
import pytest
import requests
from datetime import datetime
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.database import SessionLocal
from app.auth.security import hash_password, issue_session_token
from app.schemas.auth_users_table import AuthUser
from app.schemas.feedback_issues_table import FeedbackIssue, IssueStatus
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.feedback_issue_category_counts_table import FeedbackIssueCategoryCount


def compute_query_hash(query: str) -> str:
    return hashlib.md5(query.strip().lower().encode("utf-8")).hexdigest()


class LiveApiClient:
    """HTTP client targeting the live FastAPI server instance."""
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url

    def get(self, path, **kwargs):
        return requests.get(f"{self.base_url}{path}", **kwargs)

    def post(self, path, **kwargs):
        return requests.post(f"{self.base_url}{path}", **kwargs)


@pytest.fixture(scope="module")
def client():
    return LiveApiClient()


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_test_state():
    session = SessionLocal()
    session.query(FeedbackIssueCategoryCount).filter(
        FeedbackIssueCategoryCount.issue_id.like("iss_p4_%")
    ).delete()
    session.query(ResponseFeedback).filter(
        (ResponseFeedback.issue_id.like("iss_p4_%")) |
        (ResponseFeedback.feedback_id.like("fb_p4_%")) |
        (ResponseFeedback.query_text.like("%Phase 4 Test%"))
    ).delete()
    session.query(FeedbackIssue).filter(
        (FeedbackIssue.issue_id.like("iss_p4_%")) |
        (FeedbackIssue.canonical_query_text.like("%Phase 4 Test%"))
    ).delete()
    session.commit()
    session.close()
    yield
    session = SessionLocal()
    session.query(FeedbackIssueCategoryCount).filter(
        FeedbackIssueCategoryCount.issue_id.like("iss_p4_%")
    ).delete()
    session.query(ResponseFeedback).filter(
        (ResponseFeedback.issue_id.like("iss_p4_%")) |
        (ResponseFeedback.feedback_id.like("fb_p4_%")) |
        (ResponseFeedback.query_text.like("%Phase 4 Test%"))
    ).delete()
    session.query(FeedbackIssue).filter(
        (FeedbackIssue.issue_id.like("iss_p4_%")) |
        (FeedbackIssue.canonical_query_text.like("%Phase 4 Test%"))
    ).delete()
    session.commit()
    session.close()


@pytest.fixture
def admin_user_fixture(db_session):
    """Seed admin user for status & reconciliation requests."""
    settings = get_settings()
    user = db_session.query(AuthUser).filter(AuthUser.username == "admin_p4").first()
    if not user:
        user = AuthUser(
            username="admin_p4",
            password_hash=hash_password("Password123!"),
            display_name="User admin_p4",
            email="admin_p4@amc.com",
            role="Compliance & Regulatory Officer",
            department="Compliance",
            status="Active",
            tenant_id="tenant_p4",
        )
        db_session.add(user)
        db_session.commit()
    token, _ = issue_session_token("admin_p4", settings.auth_secret_key, ttl_minutes=60)
    return {"username": "admin_p4", "token": token, "role": user.role, "tenant_id": "tenant_p4"}


def test_feedback_status_returns_sorted_category_breakdown(client: LiveApiClient, db_session: Session):
    """
    GET /api/feedback/status returns category_breakdown sorted descending by count (§5.2, §7.1).
    """
    query = "What are SEBI limits on debt fund exposure to AT1 bonds?"
    q_hash = compute_query_hash(query)

    # 1. Seed issue
    issue = FeedbackIssue(
        issue_id="iss_p4_001",
        canonical_query_text=query,
        query_hash=q_hash,
        status=IssueStatus.IN_REPAIR.value,
        contributor_count=4,
    )
    db_session.add(issue)
    db_session.commit()

    # 2. Seed category counts: F08=3, F04=2, F06=1
    counts = [
        FeedbackIssueCategoryCount(issue_id=issue.issue_id, category_code="F08", count=3),
        FeedbackIssueCategoryCount(issue_id=issue.issue_id, category_code="F04", count=2),
        FeedbackIssueCategoryCount(issue_id=issue.issue_id, category_code="F06", count=1),
    ]
    db_session.add_all(counts)
    db_session.commit()

    # 3. Probe status endpoint
    res = client.get(
        "/api/feedback/status",
        params={"query": query},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["has_existing_issue"] is True
    assert data["issue_id"] == "iss_p4_001"
    assert data["status"] == "in_repair"
    assert data["contributor_count"] == 4

    breakdown = data.get("category_breakdown", [])
    assert len(breakdown) == 3

    # Check order: descending by count
    assert breakdown[0]["code"] == "F08"
    assert breakdown[0]["count"] == 3
    assert "Wrong Numbers" in breakdown[0]["label"]

    assert breakdown[1]["code"] == "F04"
    assert breakdown[1]["count"] == 2
    assert "Missing Key Documents" in breakdown[1]["label"]

    assert breakdown[2]["code"] == "F06"
    assert breakdown[2]["count"] == 1
    assert "Incorrect Citations" in breakdown[2]["label"]


def test_category_breakdown_capped_at_top_5(client: LiveApiClient, db_session: Session):
    """
    Status endpoint caps category_breakdown to top 5 categories (§5.2, §8).
    """
    query = "Liquid fund NAV cut-off timing regulations"
    q_hash = compute_query_hash(query)

    issue = FeedbackIssue(
        issue_id="iss_p4_many_cats",
        canonical_query_text=query,
        query_hash=q_hash,
        status=IssueStatus.REPORTED.value,
        contributor_count=8,
    )
    db_session.add(issue)
    db_session.commit()

    # Seed 8 distinct categories
    cats = [
        FeedbackIssueCategoryCount(issue_id=issue.issue_id, category_code=f"F{i:02d}", count=10 - i)
        for i in range(1, 9)
    ]
    db_session.add_all(cats)
    db_session.commit()

    res = client.get(
        "/api/feedback/status",
        params={"query": query},
    )
    assert res.status_code == 200
    data = res.json()

    breakdown = data.get("category_breakdown", [])
    assert len(breakdown) == 5
    # Must be top 5 by count (F01..F05)
    codes = [item["code"] for item in breakdown]
    assert codes == ["F01", "F02", "F03", "F04", "F05"]


def test_atomic_upsert_increments_category_counts(client: LiveApiClient, db_session: Session, admin_user_fixture):
    """
    Submitting feedback updates the category count atomically via UPSERT (§6.2).
    """
    headers = {"Authorization": f"Bearer {admin_user_fixture['token']}"}
    unique_suffix = uuid.uuid4().hex[:8]
    query_text = f"What is the minimum SIP amount under SEBI guidelines? [Phase 4 Test {unique_suffix}]"

    # First submission with categories F08 and F04
    res1 = client.post(
        "/api/feedback",
        headers=headers,
        json={
            "response_id": f"resp_p4_up1_{unique_suffix}",
            "interaction_id": f"int_p4_up1_{unique_suffix}",
            "session_id": f"sess_p4_up1_{unique_suffix}",
            "turn_number": 1,
            "query_text": query_text,
            "selected_categories": ["F08", "F04"],
            "feedback_text": "First report",
        },
    )
    assert res1.status_code in [200, 201]

    # Check status endpoint reflects counts
    status1 = client.get("/api/feedback/status", params={"query": query_text})
    assert status1.status_code == 200
    b1 = {item["code"]: item["count"] for item in status1.json().get("category_breakdown", [])}
    assert b1.get("F08") == 1
    assert b1.get("F04") == 1

    # Second submission on same query with category F08
    res2 = client.post(
        "/api/feedback",
        headers=headers,
        json={
            "response_id": f"resp_p4_up2_{unique_suffix}",
            "interaction_id": f"int_p4_up2_{unique_suffix}",
            "session_id": f"sess_p4_up2_{unique_suffix}",
            "turn_number": 2,
            "query_text": query_text,
            "selected_categories": ["F08"],
            "feedback_text": "Second report confirming F08",
        },
    )
    assert res2.status_code in [200, 201]

    # Verify F08 incremented to 2 while F04 remains 1
    status2 = client.get("/api/feedback/status", params={"query": query_text})
    assert status2.status_code == 200
    b2 = {item["code"]: item["count"] for item in status2.json().get("category_breakdown", [])}
    assert b2.get("F08") == 2
    assert b2.get("F04") == 1


def test_reconcile_categories_endpoint(client: LiveApiClient, db_session: Session, admin_user_fixture):
    """
    POST /api/feedback/reconcile-categories successfully recalculates counts
    from raw response_feedback entries (§8, §9).
    """
    headers = {"Authorization": f"Bearer {admin_user_fixture['token']}"}

    # Seed an issue and two feedback entries
    query = "Side-pocketing limits for defaulting entities"
    q_hash = compute_query_hash(query)

    issue = FeedbackIssue(
        issue_id="iss_p4_reconcile",
        canonical_query_text=query,
        query_hash=q_hash,
        status=IssueStatus.REPORTED.value,
        contributor_count=2,
    )
    db_session.add(issue)
    db_session.commit()

    fb1 = ResponseFeedback(
        feedback_id="fb_p4_rec1",
        response_id="resp_p4_rec1",
        interaction_id="int_p4_rec1",
        session_id="sess_p4_rec1",
        turn_number=1,
        query_text=issue.canonical_query_text,
        actor_id="admin_p4",
        issue_id=issue.issue_id,
        selected_categories=["F02", "F03"],
        categories=["F02", "F03"],
    )
    fb2 = ResponseFeedback(
        feedback_id="fb_p4_rec2",
        response_id="resp_p4_rec2",
        interaction_id="int_p4_rec2",
        session_id="sess_p4_rec2",
        turn_number=1,
        query_text=issue.canonical_query_text,
        actor_id="user_other",
        issue_id=issue.issue_id,
        selected_categories=["F02"],
        categories=["F02"],
    )
    db_session.add_all([fb1, fb2])
    db_session.commit()

    # Intentionally corrupt/empty category counts for this issue
    db_session.query(FeedbackIssueCategoryCount).filter(
        FeedbackIssueCategoryCount.issue_id == issue.issue_id
    ).delete()
    db_session.commit()

    # Call reconciliation endpoint
    recon_res = client.post(
        f"/api/feedback/reconcile-categories?issue_id={issue.issue_id}",
        headers=headers,
    )
    assert recon_res.status_code == 200
    res_data = recon_res.json()
    assert res_data.get("reconciled_issues", 0) >= 1

    # Verify counts were restored: F02=2, F03=1
    reconciled_counts = db_session.query(FeedbackIssueCategoryCount).filter(
        FeedbackIssueCategoryCount.issue_id == issue.issue_id
    ).all()
    c_map = {r.category_code: r.count for r in reconciled_counts}
    assert c_map.get("F02") == 2
    assert c_map.get("F03") == 1
