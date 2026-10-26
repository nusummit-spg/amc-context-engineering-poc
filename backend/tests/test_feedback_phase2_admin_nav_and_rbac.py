# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_feedback_phase2_admin_nav_and_rbac.py
===========================================
Phase 2 Integration tests covering:
1. Admin access to GET /api/feedback/issues and GET /api/admin/feedback/issues.
2. Stale-UI / IDOR authorization enforcement: non-admin roles (ESG Analyst, Retail Investor,
   Viewer) get 403 Forbidden even if UI state requests the endpoint.
3. Repair / status transition endpoints reject non-admin users with 403 Forbidden.
4. Tenant isolation for admin issue queries (multi-tenant tenant_id scoping).
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
        FeedbackIssueCategoryCount.issue_id.like("iss_phase2_%")
    ).delete()
    session.query(ResponseFeedback).filter(
        ResponseFeedback.issue_id.like("iss_phase2_%")
    ).delete()
    session.query(FeedbackIssue).filter(
        (FeedbackIssue.issue_id.like("iss_phase2_%")) |
        (FeedbackIssue.issue_id.in_(["iss_alpha_99", "iss_beta_99"]))
    ).delete()
    session.commit()
    session.close()
    yield
    session = SessionLocal()
    session.query(FeedbackIssueCategoryCount).filter(
        FeedbackIssueCategoryCount.issue_id.like("iss_phase2_%")
    ).delete()
    session.query(ResponseFeedback).filter(
        ResponseFeedback.issue_id.like("iss_phase2_%")
    ).delete()
    session.query(FeedbackIssue).filter(
        (FeedbackIssue.issue_id.like("iss_phase2_%")) |
        (FeedbackIssue.issue_id.in_(["iss_alpha_99", "iss_beta_99"]))
    ).delete()
    session.commit()
    session.close()


@pytest.fixture
def auth_users_fixture(db_session):
    """Seed test users with different roles and tenants."""
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
                department="Operations",
                status="Active",
                tenant_id=tenant_id,
            )
            db_session.add(user)
            db_session.commit()
        token, _ = issue_session_token(username, settings.auth_secret_key, ttl_minutes=60)
        return {"username": username, "token": token, "role": role, "tenant_id": tenant_id}

    admin_user = get_or_create("admin_p2", "Compliance & Regulatory Officer", "tenant_alpha")
    analyst_user = get_or_create("analyst_p2", "ESG & Sustainability Analyst", "tenant_alpha")
    investor_user = get_or_create("investor_p2", "Retail Investor / Public Client", "tenant_beta")

    return {
        "admin": admin_user,
        "analyst": analyst_user,
        "investor": investor_user,
    }


def test_admin_can_access_feedback_issues_and_alias(client: LiveApiClient, db_session: Session, auth_users_fixture):
    """Admin role gets 200 from both /api/feedback/issues and /api/admin/feedback/issues."""
    # Seed issue
    issue1 = FeedbackIssue(
        issue_id="iss_phase2_01",
        canonical_query_text="What are SEBI limits on debt funds?",
        query_hash="hash_p2_01",
        status=IssueStatus.REPORTED.value,
        contributor_count=2,
        tenant_id="tenant_alpha",
    )
    db_session.add(issue1)
    db_session.commit()

    admin_headers = {"Authorization": f"Bearer {auth_users_fixture['admin']['token']}"}

    # 1. Main endpoint
    res = client.get("/api/feedback/issues", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert any(i["issue_id"] == "iss_phase2_01" for i in data["items"])

    # 2. Admin alias endpoint (Section 7.3)
    alias_res = client.get("/api/admin/feedback/issues", headers=admin_headers)
    assert alias_res.status_code == 200
    alias_data = alias_res.json()
    assert alias_data["total"] >= 1
    assert any(i["issue_id"] == "iss_phase2_01" for i in alias_data["items"])


def test_non_admin_roles_rejected_with_403(client: LiveApiClient, db_session: Session, auth_users_fixture):
    """
    Edge case: stale-UI or direct URL manipulation by non-admin roles MUST 403 (§8).
    Neither analyst nor retail investor may view the issue triage queue.
    """
    issue = FeedbackIssue(
        issue_id="iss_phase2_secret",
        canonical_query_text="Internal confidential fund query",
        query_hash="hash_p2_secret",
        status=IssueStatus.UNDER_REVIEW.value,
        contributor_count=1,
    )
    db_session.add(issue)
    db_session.commit()

    # Analyst session
    analyst_headers = {"Authorization": f"Bearer {auth_users_fixture['analyst']['token']}"}
    res_analyst = client.get("/api/feedback/issues", headers=analyst_headers)
    assert res_analyst.status_code == 403
    assert "Admin-tier role required" in res_analyst.json()["detail"]

    res_analyst_alias = client.get("/api/admin/feedback/issues", headers=analyst_headers)
    assert res_analyst_alias.status_code == 403

    # Retail investor session
    investor_headers = {"Authorization": f"Bearer {auth_users_fixture['investor']['token']}"}
    res_investor = client.get("/api/feedback/issues", headers=investor_headers)
    assert res_investor.status_code == 403

    # Non-admin header explicitly passed
    header_res = client.get("/api/feedback/issues", headers={"X-User-Role": "viewer"})
    assert header_res.status_code == 403


def test_non_admin_cannot_trigger_repair_or_status_transition(client: LiveApiClient, db_session: Session, auth_users_fixture):
    """Non-admin cannot initiate repair or update issue lifecycle status."""
    issue = FeedbackIssue(
        issue_id="iss_phase2_triage",
        canonical_query_text="Expense ratio discrepancy in Mirae Asset Large Cap",
        query_hash="hash_p2_triage",
        status=IssueStatus.REPORTED.value,
        contributor_count=1,
    )
    db_session.add(issue)
    db_session.commit()

    analyst_headers = {"Authorization": f"Bearer {auth_users_fixture['analyst']['token']}"}

    # Repair transition attempt
    repair_res = client.post(
        f"/api/feedback/issues/{issue.issue_id}/repair",
        headers=analyst_headers,
        json={"actor_id": "analyst_p2"},
    )
    assert repair_res.status_code == 403

    # Status update attempt
    status_res = client.post(
        f"/api/feedback/issues/{issue.issue_id}/status",
        headers=analyst_headers,
        json={"status": "resolved", "resolution_notes": "Trying to bypass"},
    )
    assert status_res.status_code == 403


def test_tenant_isolation_on_admin_issues_query(client: LiveApiClient, db_session: Session, auth_users_fixture):
    """Multi-tenant isolation: admin on tenant_alpha sees tenant_alpha issues, not tenant_beta."""
    issue_a = FeedbackIssue(
        issue_id="iss_alpha_99",
        canonical_query_text="Alpha tenant query",
        query_hash="hash_alpha_99",
        status=IssueStatus.REPORTED.value,
        tenant_id="tenant_alpha",
    )
    issue_b = FeedbackIssue(
        issue_id="iss_beta_99",
        canonical_query_text="Beta tenant query",
        query_hash="hash_beta_99",
        status=IssueStatus.REPORTED.value,
        tenant_id="tenant_beta",
    )
    db_session.add_all([issue_a, issue_b])
    db_session.commit()

    admin_headers = {"Authorization": f"Bearer {auth_users_fixture['admin']['token']}"}

    res = client.get("/api/feedback/issues", headers=admin_headers)
    assert res.status_code == 200
    item_ids = [item["issue_id"] for item in res.json()["items"]]
    assert "iss_alpha_99" in item_ids
    assert "iss_beta_99" not in item_ids
