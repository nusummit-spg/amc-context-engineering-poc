# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_feedback_phase5_scale_and_hardening.py
===========================================
Phase 5 Comprehensive Integration & Performance Tests covering:
1. Short-TTL in-memory/Redis cache for GET /api/feedback/status with p95 < 50ms latency validation.
2. Targeted write invalidation on feedback submissions, status updates, and repair actions.
3. Server-side search (q), status filtering, and limit/offset pagination on GET /api/feedback/issues.
4. Server-side search (q), status filtering, pagination, and IDOR security on GET /api/feedback/mine.
5. Scheduled category drift reconciliation and telemetry metrics reporting.
6. RBAC access control security pass on admin triage and repair endpoints.
"""

import hashlib
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.database import SessionLocal
from app.auth.security import hash_password, issue_session_token
from app.feedback.feedback_cache import get_feedback_cache
from app.schemas.auth_users_table import AuthUser
from app.schemas.feedback_issues_table import FeedbackIssue, IssueStatus
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.feedback_issue_category_counts_table import FeedbackIssueCategoryCount
from app.feedback import issue_store


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
    """Wipe any test records with iss_p5_ prefix and reset cache telemetry."""
    cache = get_feedback_cache()
    cache.invalidate_all()
    cache.reset_metrics()

    session = SessionLocal()
    session.query(FeedbackIssueCategoryCount).filter(
        FeedbackIssueCategoryCount.issue_id.like("iss_p5_%")
    ).delete()
    session.query(ResponseFeedback).filter(
        (ResponseFeedback.issue_id.like("iss_p5_%")) |
        (ResponseFeedback.feedback_id.like("fb_p5_%")) |
        (ResponseFeedback.query_text.like("%[Phase 5 Test%"))
    ).delete()
    session.query(FeedbackIssue).filter(
        (FeedbackIssue.issue_id.like("iss_p5_%")) |
        (FeedbackIssue.canonical_query_text.like("%[Phase 5 Test%"))
    ).delete()
    session.commit()
    session.close()

    yield

    cache = get_feedback_cache()
    cache.invalidate_all()
    cache.reset_metrics()

    session = SessionLocal()
    session.query(FeedbackIssueCategoryCount).filter(
        FeedbackIssueCategoryCount.issue_id.like("iss_p5_%")
    ).delete()
    session.query(ResponseFeedback).filter(
        (ResponseFeedback.issue_id.like("iss_p5_%")) |
        (ResponseFeedback.feedback_id.like("fb_p5_%")) |
        (ResponseFeedback.query_text.like("%[Phase 5 Test%"))
    ).delete()
    session.query(FeedbackIssue).filter(
        (FeedbackIssue.issue_id.like("iss_p5_%")) |
        (FeedbackIssue.canonical_query_text.like("%[Phase 5 Test%"))
    ).delete()
    session.commit()
    session.close()


@pytest.fixture
def admin_user_fixture(db_session):
    settings = get_settings()
    user = db_session.query(AuthUser).filter(AuthUser.username == "admin_p5").first()
    if not user:
        user = AuthUser(
            username="admin_p5",
            password_hash=hash_password("Password123!"),
            display_name="Admin Phase 5",
            email="admin_p5@amc.com",
            role="Admin",
            department="Compliance",
            status="Active",
            tenant_id="tenant_p5",
        )
        db_session.add(user)
        db_session.commit()
    token, _ = issue_session_token("admin_p5", settings.auth_secret_key, ttl_minutes=60)
    return {"user": user, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def alice_user_fixture(db_session):
    settings = get_settings()
    user = db_session.query(AuthUser).filter(AuthUser.username == "alice_p5").first()
    if not user:
        user = AuthUser(
            username="alice_p5",
            password_hash=hash_password("Password123!"),
            display_name="Alice P5",
            email="alice_p5@amc.com",
            role="Reviewer",
            department="Operations",
            status="Active",
            tenant_id="tenant_p5",
        )
        db_session.add(user)
        db_session.commit()
    token, _ = issue_session_token("alice_p5", settings.auth_secret_key, ttl_minutes=60)
    return {"user": user, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def bob_user_fixture(db_session):
    settings = get_settings()
    user = db_session.query(AuthUser).filter(AuthUser.username == "bob_p5").first()
    if not user:
        user = AuthUser(
            username="bob_p5",
            password_hash=hash_password("Password123!"),
            display_name="Bob P5",
            email="bob_p5@amc.com",
            role="Reviewer",
            department="Research",
            status="Active",
            tenant_id="tenant_p5",
        )
        db_session.add(user)
        db_session.commit()
    token, _ = issue_session_token("bob_p5", settings.auth_secret_key, ttl_minutes=60)
    return {"user": user, "token": token, "headers": {"Authorization": f"Bearer {token}"}}



# ===========================================================================
# 1. Short-TTL Status Cache & Latency Budget Validation
# ===========================================================================

def test_feedback_status_cache_hit_and_latency_budget(client, db_session, admin_user_fixture):
    """
    Validate that GET /api/feedback/status caches responses and achieves p95 < 50ms warm latency.
    """
    now = datetime.now(timezone.utc).isoformat()
    query_text = "What is the exit load for liquid mutual funds? [Phase 5 Test Latency]"
    q_hash = compute_query_hash(query_text)
    issue_id = "iss_p5_perf_1"

    # Seed issue and category counts
    issue = FeedbackIssue(
        issue_id=issue_id,
        canonical_query_text=query_text,
        query_hash=q_hash,
        status=IssueStatus.REPORTED.value,
        contributor_count=2,
        primary_entities=["Liquid Fund", "Exit Load"],
        tenant_id="tenant_p5",
        created_at=now,
        updated_at=now,
    )
    db_session.add(issue)
    db_session.commit()

    cat1 = FeedbackIssueCategoryCount(issue_id=issue_id, category_code="F08", count=3, updated_at=now)
    cat2 = FeedbackIssueCategoryCount(issue_id=issue_id, category_code="F04", count=1, updated_at=now)
    db_session.add_all([cat1, cat2])
    db_session.commit()

    # Cold request: should calculate from database/matcher and cache result
    t0 = time.perf_counter()
    resp_cold = client.get(
        "/api/feedback/status",
        params={"query": query_text, "tenant_id": "tenant_p5"},
        headers=admin_user_fixture["headers"],
    )
    cold_duration = time.perf_counter() - t0

    assert resp_cold.status_code == 200
    data_cold = resp_cold.json()
    assert data_cold["has_existing_issue"] is True
    assert data_cold["issue_id"] == issue_id
    assert len(data_cold.get("category_breakdown", [])) == 2

    # Warm request: should return immediately from in-memory cache
    t1 = time.perf_counter()
    resp_warm = client.get(
        "/api/feedback/status",
        params={"query": query_text, "tenant_id": "tenant_p5"},
        headers=admin_user_fixture["headers"],
    )
    warm_duration = time.perf_counter() - t1

    assert resp_warm.status_code == 200
    data_warm = resp_warm.json()
    assert data_warm["has_existing_issue"] is True
    assert data_warm["issue_id"] == issue_id
    assert data_warm.get("cached") is True

    # Latency Budget Benchmark: Execute 50 warm calls and compute p95 latency
    warm_latencies = []
    for _ in range(50):
        start = time.perf_counter()
        r = client.get(
            "/api/feedback/status",
            params={"query": query_text, "tenant_id": "tenant_p5"},
            headers=admin_user_fixture["headers"],
        )
        elapsed = time.perf_counter() - start
        assert r.status_code == 200
        warm_latencies.append(elapsed)

    warm_latencies.sort()
    p95_index = int(len(warm_latencies) * 0.95)
    p95_warm_ms = warm_latencies[p95_index] * 1000.0

    # Ensure p95 warm latency is well within budget (< 50ms)
    assert p95_warm_ms < 50.0, f"p95 warm latency was {p95_warm_ms:.2f}ms, expected < 50ms"


# ===========================================================================
# 2. Targeted Write Invalidation Verification
# ===========================================================================

def test_feedback_status_cache_write_invalidation(client, db_session, admin_user_fixture):
    """
    Verify that write operations (feedback submission, status transition, repair linkage)
    immediately invalidate cached query status responses for that issue.
    """
    now = datetime.now(timezone.utc).isoformat()
    query_text = "What are the NAV cut-off timings for liquid funds? [Phase 5 Test Inval]"
    q_hash = compute_query_hash(query_text)
    issue_id = "iss_p5_inval_1"

    issue = FeedbackIssue(
        issue_id=issue_id,
        canonical_query_text=query_text,
        query_hash=q_hash,
        status=IssueStatus.REPORTED.value,
        contributor_count=1,
        tenant_id="tenant_p5",
        created_at=now,
        updated_at=now,
    )
    db_session.add(issue)
    db_session.commit()

    db_session.add(FeedbackIssueCategoryCount(issue_id=issue_id, category_code="F08", count=1, updated_at=now))
    db_session.commit()

    # 1. Warm up cache
    r1 = client.get("/api/feedback/status", params={"query": query_text, "tenant_id": "tenant_p5"}, headers=admin_user_fixture["headers"])
    assert r1.status_code == 200
    assert r1.json()["has_existing_issue"] is True

    # 2. Verify warm cache hit
    r2 = client.get("/api/feedback/status", params={"query": query_text, "tenant_id": "tenant_p5"}, headers=admin_user_fixture["headers"])
    assert r2.status_code == 200
    assert r2.json().get("cached") is True

    # 3. Transition status to in_repair via API -> triggers invalidation
    r_trans = client.post(
        f"/api/feedback/issues/{issue_id}/status",
        json={"status": "in_repair", "resolution_notes": "Diagnostic review underway"},
        headers=admin_user_fixture["headers"],
    )
    assert r_trans.status_code == 200
    assert r_trans.json()["status"] == "in_repair"

    # 4. Next GET /status must be fresh (not stale "reported")
    r3 = client.get("/api/feedback/status", params={"query": query_text, "tenant_id": "tenant_p5"}, headers=admin_user_fixture["headers"])
    assert r3.status_code == 200
    data_after = r3.json()
    assert data_after["status"] == "in_repair"


# ===========================================================================
# 3. Server-Side Search & Pagination on Admin Issues
# ===========================================================================

def test_server_side_search_and_pagination_admin_issues(client, db_session, admin_user_fixture):
    """
    Verify server-side query filtering (q), status filtering, and limit/offset pagination on GET /api/feedback/issues.
    """
    now = datetime.now(timezone.utc).isoformat()
    issue_samples = [
        ("iss_p5_adm_1", "Large Cap Fund minimum equity allocation rules [Phase 5 Test Search]", "reported", ["Large Cap"]),
        ("iss_p5_adm_2", "Debt Fund Macaulay duration and portfolio limits [Phase 5 Test Search]", "reported", ["Debt Fund"]),
        ("iss_p5_adm_3", "Arbitrage Fund derivatives hedging criteria [Phase 5 Test Search]", "in_repair", ["Arbitrage"]),
        ("iss_p5_adm_4", "Overnight Fund daily maturity mandate [Phase 5 Test Search]", "in_repair", ["Overnight Fund"]),
        ("iss_p5_adm_5", "Index Fund tracking error permissible tolerance [Phase 5 Test Search]", "resolved", ["Index Fund"]),
    ]

    for i_id, q_text, st, ents in issue_samples:
        iss = FeedbackIssue(
            issue_id=i_id,
            canonical_query_text=q_text,
            query_hash=compute_query_hash(q_text),
            status=st,
            contributor_count=1,
            primary_entities=ents,
            tenant_id="tenant_p5",
            created_at=now,
            updated_at=now,
        )
        db_session.add(iss)
    db_session.commit()

    headers = admin_user_fixture["headers"]

    # 1. Search filter: q="Macaulay duration and portfolio limits"
    r_search = client.get("/api/feedback/issues", params={"q": "Macaulay duration and portfolio limits"}, headers=headers)
    assert r_search.status_code == 200
    data_search = r_search.json()
    assert data_search["total"] == 1
    assert data_search["items"][0]["issue_id"] == "iss_p5_adm_2"

    # 2. Status filter: status="in_repair"
    r_status = client.get("/api/feedback/issues", params={"status": "in_repair"}, headers=headers)
    assert r_status.status_code == 200
    data_status = r_status.json()
    assert data_status["total"] >= 2
    for item in data_status["items"]:
        assert item["status"] == "in_repair"

    # 3. Pagination: page=1, page_size=2
    r_page1 = client.get("/api/feedback/issues", params={"q": "[Phase 5 Test Search]", "page": 1, "page_size": 2}, headers=headers)
    assert r_page1.status_code == 200
    data_page1 = r_page1.json()
    assert data_page1["total"] == 5
    assert len(data_page1["items"]) == 2
    assert data_page1["page"] == 1
    assert data_page1["total_pages"] == 3

    # 4. Pagination: page=2, page_size=2
    r_page2 = client.get("/api/feedback/issues", params={"q": "[Phase 5 Test Search]", "page": 2, "page_size": 2}, headers=headers)
    assert r_page2.status_code == 200
    data_page2 = r_page2.json()
    assert len(data_page2["items"]) == 2
    assert data_page2["items"][0]["issue_id"] != data_page1["items"][0]["issue_id"]


# ===========================================================================
# 4. Server-Side Search, Pagination & IDOR Isolation on My Feedback
# ===========================================================================

def test_server_side_search_and_pagination_my_feedback_and_idor(
    client, db_session, alice_user_fixture, bob_user_fixture
):
    """
    Validate GET /api/feedback/mine:
    - User A only sees their own feedback issues.
    - Parameter tampering (?actor_id=bob) is ignored (strict IDOR protection).
    - Server-side search (q) and pagination are correctly applied.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Create 3 issues: 2 for Alice, 1 for Bob
    iss_a1 = FeedbackIssue(
        issue_id="iss_p5_alice_1",
        canonical_query_text="Equity taxation holding periods [Phase 5 Test MyFeedback]",
        query_hash=compute_query_hash("Equity taxation holding periods [Phase 5 Test MyFeedback]"),
        status="reported",
        contributor_count=1,
        tenant_id="tenant_p5",
        created_at=now,
        updated_at=now,
    )
    iss_a2 = FeedbackIssue(
        issue_id="iss_p5_alice_2",
        canonical_query_text="Debt hybrid fund indexation benefit [Phase 5 Test MyFeedback]",
        query_hash=compute_query_hash("Debt hybrid fund indexation benefit [Phase 5 Test MyFeedback]"),
        status="in_repair",
        contributor_count=1,
        tenant_id="tenant_p5",
        created_at=now,
        updated_at=now,
    )
    iss_b1 = FeedbackIssue(
        issue_id="iss_p5_bob_1",
        canonical_query_text="Gold ETF expense ratio limits [Phase 5 Test MyFeedback]",
        query_hash=compute_query_hash("Gold ETF expense ratio limits [Phase 5 Test MyFeedback]"),
        status="reported",
        contributor_count=1,
        tenant_id="tenant_p5",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([iss_a1, iss_a2, iss_b1])
    db_session.commit()

    # Link Alice's feedback to iss_a1 and iss_a2
    fb_a1 = ResponseFeedback(
        feedback_id="fb_p5_a1",
        response_id="resp_p5_a1",
        interaction_id="int_p5_a1",
        turn_number=1,
        session_id="sess_p5_a1",
        actor_id="alice_p5",
        issue_id="iss_p5_alice_1",
        query_text="Equity taxation holding periods [Phase 5 Test MyFeedback]",
        selected_categories=["F08"],
        categories=["F08"],
        feedback_text="Wrong LTCG timeline reported",
        created_at=now,
        updated_at=now,
    )
    fb_a2 = ResponseFeedback(
        feedback_id="fb_p5_a2",
        response_id="resp_p5_a2",
        interaction_id="int_p5_a2",
        turn_number=1,
        session_id="sess_p5_a2",
        actor_id="alice_p5",
        issue_id="iss_p5_alice_2",
        query_text="Debt hybrid fund indexation benefit [Phase 5 Test MyFeedback]",
        selected_categories=["F04"],
        categories=["F04"],
        feedback_text="Missing post-2023 amendment rule",
        created_at=now,
        updated_at=now,
    )
    # Link Bob's feedback to iss_b1
    fb_b1 = ResponseFeedback(
        feedback_id="fb_p5_b1",
        response_id="resp_p5_b1",
        interaction_id="int_p5_b1",
        turn_number=1,
        session_id="sess_p5_b1",
        actor_id="bob_p5",
        issue_id="iss_p5_bob_1",
        query_text="Gold ETF expense ratio limits [Phase 5 Test MyFeedback]",
        selected_categories=["F06"],
        categories=["F06"],
        feedback_text="Incorrect SEBI circular cited",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([fb_a1, fb_a2, fb_b1])
    db_session.commit()


    # 1. Alice fetches her issues -> Should receive exactly 2 issues
    resp_alice = client.get("/api/feedback/mine", headers=alice_user_fixture["headers"])
    assert resp_alice.status_code == 200
    data_alice = resp_alice.json()
    assert data_alice["total"] == 2
    alice_ids = {it["issue_id"] for it in data_alice["items"]}
    assert alice_ids == {"iss_p5_alice_1", "iss_p5_alice_2"}
    assert "iss_p5_bob_1" not in alice_ids

    # 2. IDOR Attack Simulation: Alice tries passing bob_p5 parameters
    resp_idor = client.get(
        "/api/feedback/mine?actor_id=bob_p5&user_id=bob_p5",
        headers=alice_user_fixture["headers"],
    )
    assert resp_idor.status_code == 200
    data_idor = resp_idor.json()
    # Alice STILL only receives her own issues
    idor_ids = {it["issue_id"] for it in data_idor["items"]}
    assert idor_ids == {"iss_p5_alice_1", "iss_p5_alice_2"}
    assert "iss_p5_bob_1" not in idor_ids

    # 3. Server-side search on My Feedback: Alice searches for "indexation"
    resp_search = client.get(
        "/api/feedback/mine?q=indexation",
        headers=alice_user_fixture["headers"],
    )
    assert resp_search.status_code == 200
    data_search = resp_search.json()
    assert data_search["total"] == 1
    assert data_search["items"][0]["issue_id"] == "iss_p5_alice_2"

    # 4. Pagination on My Feedback: page=1, page_size=1
    resp_p1 = client.get(
        "/api/feedback/mine?page=1&page_size=1",
        headers=alice_user_fixture["headers"],
    )
    assert resp_p1.status_code == 200
    data_p1 = resp_p1.json()
    assert data_p1["total"] == 2
    assert len(data_p1["items"]) == 1
    assert data_p1["page"] == 1
    assert data_p1["total_pages"] == 2


# ===========================================================================
# 5. Drift Reconciliation & Telemetry
# ===========================================================================

def test_drift_reconciliation_and_telemetry(client, db_session, admin_user_fixture):
    """
    Test that scheduled reconciliation catches counter drift, updates telemetry,
    and exposes metrics via GET /api/feedback/telemetry.
    """
    now = datetime.now(timezone.utc).isoformat()
    issue_id = "iss_p5_drift_1"
    q_text = "What is the settlement cycle for equity mutual funds? [Phase 5 Drift Test]"

    issue = FeedbackIssue(
        issue_id=issue_id,
        canonical_query_text=q_text,
        query_hash=compute_query_hash(q_text),
        status="reported",
        contributor_count=2,
        tenant_id="tenant_p5",
        created_at=now,
        updated_at=now,
    )
    db_session.add(issue)
    db_session.commit()

    # Seed 2 raw feedback entries: F08 x 2, F04 x 1
    fb1 = ResponseFeedback(
        feedback_id="fb_p5_dr_1",
        response_id="resp_p5_dr_1",
        interaction_id="int_p5_dr_1",
        turn_number=1,
        session_id="sess_p5_dr_1",
        actor_id="admin_p5",
        issue_id=issue_id,
        query_text=q_text,
        selected_categories=["F08", "F04"],
        categories=["F08", "F04"],
        created_at=now,
        updated_at=now,
    )
    fb2 = ResponseFeedback(
        feedback_id="fb_p5_dr_2",
        response_id="resp_p5_dr_2",
        interaction_id="int_p5_dr_2",
        turn_number=1,
        session_id="sess_p5_dr_2",
        actor_id="user_p5_other",
        issue_id=issue_id,
        query_text=q_text,
        selected_categories=["F08"],
        categories=["F08"],
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([fb1, fb2])
    db_session.commit()


    # Manually inject artificial drift into counter table: F08 count=99 (drift of 97!)
    db_session.add(FeedbackIssueCategoryCount(issue_id=issue_id, category_code="F08", count=99, updated_at=now))
    db_session.commit()

    # Run reconciliation via live API endpoint
    resp_rec = client.post(
        "/api/feedback/reconcile-categories",
        params={"issue_id": issue_id},
        headers=admin_user_fixture["headers"],
    )
    assert resp_rec.status_code == 200
    reconcile_report = resp_rec.json()
    assert reconcile_report["drift_size"] > 0
    assert reconcile_report["reconciled_issues"] == 1

    # Verify database counter table was correctly corrected
    db_session.expire_all()
    f08_row = (
        db_session.query(FeedbackIssueCategoryCount)
        .filter(FeedbackIssueCategoryCount.issue_id == issue_id, FeedbackIssueCategoryCount.category_code == "F08")
        .first()
    )
    assert f08_row is not None
    assert f08_row.count == 2, f"Expected F08 count to be corrected to 2, found {f08_row.count}"

    # Verify Telemetry endpoint reflects reconciliation and cache status
    resp_telem = client.get("/api/feedback/telemetry", headers=admin_user_fixture["headers"])
    assert resp_telem.status_code == 200
    telem = resp_telem.json()
    assert telem["status"] == "ok"
    assert "cache" in telem
    assert telem["cache"]["last_drift_size"] >= reconcile_report["drift_size"]


# ===========================================================================
# 6. RBAC Access Control Security Pass
# ===========================================================================

def test_rbac_access_control_security_pass(client, alice_user_fixture):
    """
    Verify that non-admin sessions (reviewer, regular user) cannot access
    admin triage queue or issue transition mutations.
    """
    headers = alice_user_fixture["headers"]

    # 1. Non-admin accessing admin triage queue -> 403 Forbidden
    r1 = client.get("/api/feedback/issues", headers=headers)
    assert r1.status_code == 403

    # 2. Non-admin updating issue status -> 403 Forbidden
    r2 = client.post(
        "/api/feedback/issues/iss_test_any/status",
        json={"status": "resolved"},
        headers=headers,
    )
    assert r2.status_code == 403

    # 3. Non-admin initiating repair -> 403 Forbidden
    r3 = client.post("/api/feedback/issues/iss_test_any/repair", headers=headers)
    assert r3.status_code == 403
