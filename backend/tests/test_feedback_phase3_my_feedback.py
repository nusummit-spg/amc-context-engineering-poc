# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_feedback_phase3_my_feedback.py
===================================
Phase 3 Integration tests covering:
1. Unauthenticated rejection (401 Unauthorized) on GET /api/feedback/mine.
2. Personal scope enforcement: users see only their own reported/matched issues.
3. Category extraction: user_reported_categories maps directly from user's submission.
4. Anonymization: contributor identities of other users are strictly hidden; only also_reported_by_count is exposed.
5. Insecure Direct Object Reference (IDOR) immunity: client parameters cannot alter the session user scope.
6. Multi-tenant isolation on personal feedback queries.
7. Pagination (limit and offset) behavior on /mine.
"""

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
        FeedbackIssueCategoryCount.issue_id.like("iss_p3_%")
    ).delete()
    session.query(ResponseFeedback).filter(
        (ResponseFeedback.issue_id.like("iss_p3_%")) |
        (ResponseFeedback.feedback_id.like("fb_p3_%"))
    ).delete()
    session.query(FeedbackIssue).filter(
        FeedbackIssue.issue_id.like("iss_p3_%")
    ).delete()
    session.commit()
    session.close()
    yield
    session = SessionLocal()
    session.query(FeedbackIssueCategoryCount).filter(
        FeedbackIssueCategoryCount.issue_id.like("iss_p3_%")
    ).delete()
    session.query(ResponseFeedback).filter(
        (ResponseFeedback.issue_id.like("iss_p3_%")) |
        (ResponseFeedback.feedback_id.like("fb_p3_%"))
    ).delete()
    session.query(FeedbackIssue).filter(
        FeedbackIssue.issue_id.like("iss_p3_%")
    ).delete()
    session.commit()
    session.close()


@pytest.fixture
def auth_users_fixture(db_session):
    """Seed distinct test users across tenants."""
    settings = get_settings()

    def get_or_create(username: str, role: str, tenant_id: str = None):
        user = db_session.query(AuthUser).filter(AuthUser.username == username).first()
        if not user:
            user = AuthUser(
                username=username,
                password_hash=hash_password("Password123!"),
                display_name=f"User {username}",
                email=f"{username}@amc.com",
                role=role,
                department="Research",
                status="Active",
                tenant_id=tenant_id,
            )
            db_session.add(user)
            db_session.commit()
        token, _ = issue_session_token(username, settings.auth_secret_key, ttl_minutes=60)
        return {"username": username, "token": token, "role": role, "tenant_id": tenant_id}

    user_a = get_or_create("user_p3_a", "ESG & Sustainability Analyst", "tenant_alpha")
    user_b = get_or_create("user_p3_b", "Retail Investor / Public Client", "tenant_alpha")
    user_c = get_or_create("user_p3_c", "Fund Manager", "tenant_beta")

    return {
        "user_a": user_a,
        "user_b": user_b,
        "user_c": user_c,
    }


def test_unauthenticated_request_rejected(client: LiveApiClient):
    """GET /api/feedback/mine requires Bearer token authentication (401 Unauthorized)."""
    res = client.get("/api/feedback/mine")
    assert res.status_code == 401
    assert "Missing authentication token" in res.json().get("detail", "")


def test_user_sees_own_reported_issues_and_categories(client: LiveApiClient, db_session: Session, auth_users_fixture):
    """
    User A retrieves their own reported issue, verifying canonical query text,
    repair task status, and extracted user_reported_categories (§4, §7.2).
    """
    user_a = auth_users_fixture["user_a"]

    # 1. Seed an issue
    issue = FeedbackIssue(
        issue_id="iss_p3_001",
        canonical_query_text="What are SEBI limits on debt fund exposure to AT1 bonds?",
        query_hash="hash_p3_001",
        status=IssueStatus.IN_REPAIR.value,
        repair_task_id="task_repair_at1_01",
        contributor_count=1,
        tenant_id="tenant_alpha",
    )
    db_session.add(issue)

    # 2. Seed User A's feedback entry
    fb_entry = ResponseFeedback(
        feedback_id="fb_p3_001",
        response_id="resp_p3_001",
        interaction_id="int_p3_001",
        session_id="sess_p3_001",
        turn_number=1,
        query_text=issue.canonical_query_text,
        actor_id=user_a["username"],
        actor_role=user_a["role"],
        issue_id=issue.issue_id,
        selected_categories=["F08", "F04"],
        categories=["F08", "F04"],
        feedback_text="SEBI 2021 circular specifies 10% limit, response said 15%",
    )
    db_session.add(fb_entry)
    db_session.commit()

    # 3. Call GET /api/feedback/mine with User A's token
    headers = {"Authorization": f"Bearer {user_a['token']}"}
    res = client.get("/api/feedback/mine", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total"] >= 1
    matched = next((item for item in data["items"] if item["issue_id"] == "iss_p3_001"), None)
    assert matched is not None
    assert matched["canonical_query_text"] == "What are SEBI limits on debt fund exposure to AT1 bonds?"
    assert matched["status"] == "in_repair"
    assert matched["repair_task_id"] == "task_repair_at1_01"
    assert sorted(matched["user_reported_categories"]) == ["F04", "F08"]
    assert matched["also_reported_by_count"] == 0
    assert "SEBI 2021 circular specifies 10% limit" in matched["user_feedback_texts"][0]


def test_personal_view_anonymizes_other_contributors(client: LiveApiClient, db_session: Session, auth_users_fixture):
    """
    Issue reported by both User A and User B.
    User A sees also_reported_by_count = 1, with ZERO trace of User B's identity or username (§4).
    """
    user_a = auth_users_fixture["user_a"]
    user_b = auth_users_fixture["user_b"]

    issue = FeedbackIssue(
        issue_id="iss_p3_shared",
        canonical_query_text="Mirae Asset Large Cap TER calculation discrepancy",
        query_hash="hash_p3_shared",
        status=IssueStatus.UNDER_REVIEW.value,
        contributor_count=2,
        tenant_id="tenant_alpha",
    )
    db_session.add(issue)

    # User A feedback
    fb_a = ResponseFeedback(
        feedback_id="fb_p3_shared_a",
        response_id="resp_p3_sha",
        interaction_id="int_p3_sha",
        session_id="sess_p3_sha",
        turn_number=1,
        query_text=issue.canonical_query_text,
        actor_id=user_a["username"],
        issue_id=issue.issue_id,
        selected_categories=["F08"],
        categories=["F08"],
        feedback_text="User A comments on TER",
    )
    # User B feedback
    fb_b = ResponseFeedback(
        feedback_id="fb_p3_shared_b",
        response_id="resp_p3_shb",
        interaction_id="int_p3_shb",
        session_id="sess_p3_shb",
        turn_number=1,
        query_text=issue.canonical_query_text,
        actor_id=user_b["username"],
        issue_id=issue.issue_id,
        selected_categories=["F06"],
        categories=["F06"],
        feedback_text="User B secret notes and identity",
    )
    db_session.add_all([fb_a, fb_b])
    db_session.commit()

    # User A calls /mine
    headers = {"Authorization": f"Bearer {user_a['token']}"}
    res = client.get("/api/feedback/mine", headers=headers)
    assert res.status_code == 200
    item = next(i for i in res.json()["items"] if i["issue_id"] == "iss_p3_shared")

    # Contributor count check: max(0, 2 - 1) = 1
    assert item["also_reported_by_count"] == 1

    # Security check: User B's username and comment MUST NOT be present in User A's response
    raw_response_text = res.text
    assert user_b["username"] not in raw_response_text
    assert "User B secret notes and identity" not in raw_response_text


def test_idor_protection_user_cannot_see_others_issues(client: LiveApiClient, db_session: Session, auth_users_fixture):
    """
    IDOR test (§8): User C never reported on issue iss_p3_secret.
    Even with client parameter tampering (?user_id=user_p3_a), User C gets total=0.
    """
    user_a = auth_users_fixture["user_a"]
    user_c = auth_users_fixture["user_c"]

    issue = FeedbackIssue(
        issue_id="iss_p3_secret",
        canonical_query_text="Proprietary alpha factor model query",
        query_hash="hash_p3_secret",
        status=IssueStatus.REPORTED.value,
        contributor_count=1,
        tenant_id="tenant_alpha",
    )
    db_session.add(issue)

    fb_a = ResponseFeedback(
        feedback_id="fb_p3_secret_a",
        response_id="resp_p3_sec",
        interaction_id="int_p3_sec",
        session_id="sess_p3_sec",
        turn_number=1,
        query_text=issue.canonical_query_text,
        actor_id=user_a["username"],
        issue_id=issue.issue_id,
        selected_categories=["F01"],
        categories=["F01"],
    )
    db_session.add(fb_a)
    db_session.commit()

    # User C attempts parameter tampering to view User A's issues
    headers_c = {"Authorization": f"Bearer {user_c['token']}"}
    res_idor = client.get(f"/api/feedback/mine?user_id={user_a['username']}&actor_id={user_a['username']}", headers=headers_c)
    assert res_idor.status_code == 200
    data_c = res_idor.json()

    # User C must NOT see User A's secret issue
    assert not any(i["issue_id"] == "iss_p3_secret" for i in data_c.get("items", []))


def test_multi_tenant_isolation_on_mine(client: LiveApiClient, db_session: Session, auth_users_fixture):
    """
    Tenant isolation test (§8): If User A submits feedback linked to an issue in tenant_beta,
    the tenant filter prevents cross-tenant visibility.
    """
    user_a = auth_users_fixture["user_a"]  # tenant_alpha

    issue_beta = FeedbackIssue(
        issue_id="iss_p3_cross_tenant",
        canonical_query_text="Cross tenant issue query",
        query_hash="hash_p3_cross",
        status=IssueStatus.REPORTED.value,
        contributor_count=1,
        tenant_id="tenant_beta",
    )
    db_session.add(issue_beta)

    fb_entry = ResponseFeedback(
        feedback_id="fb_p3_cross_a",
        response_id="resp_p3_cross",
        interaction_id="int_p3_cross",
        session_id="sess_p3_cross",
        turn_number=1,
        query_text=issue_beta.canonical_query_text,
        actor_id=user_a["username"],
        issue_id=issue_beta.issue_id,
        selected_categories=["F02"],
        categories=["F02"],
    )
    db_session.add(fb_entry)
    db_session.commit()

    headers_a = {"Authorization": f"Bearer {user_a['token']}"}
    res = client.get("/api/feedback/mine", headers=headers_a)
    assert res.status_code == 200
    items = res.json()["items"]
    assert not any(i["issue_id"] == "iss_p3_cross_tenant" for i in items)


def test_pagination_on_mine(client: LiveApiClient, db_session: Session, auth_users_fixture):
    """Verifies limit and offset pagination on /api/feedback/mine."""
    user_a = auth_users_fixture["user_a"]

    # Seed 3 distinct issues for user A
    for idx in range(1, 4):
        iss = FeedbackIssue(
            issue_id=f"iss_p3_page_{idx}",
            canonical_query_text=f"Pagination query test {idx}",
            query_hash=f"hash_p3_page_{idx}",
            status=IssueStatus.REPORTED.value,
            contributor_count=1,
            tenant_id="tenant_alpha",
        )
        fb = ResponseFeedback(
            feedback_id=f"fb_p3_page_{idx}",
            response_id=f"resp_p3_page_{idx}",
            interaction_id=f"int_p3_page_{idx}",
            session_id=f"sess_p3_page_{idx}",
            turn_number=1,
            query_text=iss.canonical_query_text,
            actor_id=user_a["username"],
            issue_id=iss.issue_id,
            selected_categories=["F05"],
            categories=["F05"],
        )
        db_session.add_all([iss, fb])
    db_session.commit()

    headers = {"Authorization": f"Bearer {user_a['token']}"}

    # Request limit=2, offset=0
    res1 = client.get("/api/feedback/mine?limit=2&offset=0", headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["total"] >= 3
    assert len(data1["items"]) == 2

    # Request limit=2, offset=2
    res2 = client.get("/api/feedback/mine?limit=2&offset=2", headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["items"]) >= 1

    # Ensure items in page 1 and page 2 do not overlap
    ids_p1 = {item["issue_id"] for item in data1["items"]}
    ids_p2 = {item["issue_id"] for item in data2["items"]}
    assert len(ids_p1.intersection(ids_p2)) == 0
