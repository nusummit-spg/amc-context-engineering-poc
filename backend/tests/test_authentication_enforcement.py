# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_authentication_enforcement.py
==================================
Phase 1 Validation Tests: Authentication & Authorization Infrastructure.
Ensures mandatory server-side authentication, eliminates header spoofing,
and validates database schema updates and indexes for user ownership.
"""
import time
import pytest
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.main import app
from app.config import get_settings
from app.auth.security import issue_session_token
from app.auth.repository import AuthUserRecord
from app.api.deps import get_auth_service
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.query_evidence_table import QueryEvidence


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_service():
    return get_auth_service()


@pytest.fixture
def valid_token(auth_service):
    settings = get_settings()
    token, _ = issue_session_token("sarah.compliance", settings.auth_secret_key, ttl_minutes=60)
    return token


def test_missing_token_returns_401(client):
    """Any protected endpoint must reject requests without Bearer token."""
    endpoints = [
        ("/api/sessions", "GET"),
        ("/api/sessions/test-session-123", "GET"),
        ("/api/review-queue/pending", "GET"),
        ("/api/chat/query", "POST"),
    ]

    for path, method in endpoints:
        if method == "GET":
            response = client.get(path)
        else:
            response = client.post(path, json={})

        assert response.status_code == 401, f"{method} {path} should require authentication, got {response.status_code}"
        assert "Bearer" in response.headers.get("WWW-Authenticate", "")
        detail = response.json().get("detail", "")
        assert "Missing" in detail or "token" in detail


def test_invalid_token_returns_401(client):
    """Invalid tokens must be rejected."""
    response = client.get(
        "/api/sessions",
        headers={"Authorization": "Bearer invalid_token_xyz"}
    )
    assert response.status_code == 401
    assert "Bearer" in response.headers.get("WWW-Authenticate", "")


def test_malformed_auth_header_returns_401(client):
    """Non-Bearer or empty token format must be rejected."""
    # Missing Bearer prefix
    resp1 = client.get(
        "/api/sessions",
        headers={"Authorization": "Basic some_credentials"}
    )
    assert resp1.status_code == 401
    assert "Bearer" in resp1.headers.get("WWW-Authenticate", "")

    # Bearer with empty token
    resp2 = client.get(
        "/api/sessions",
        headers={"Authorization": "Bearer "}
    )
    assert resp2.status_code == 401
    assert "Bearer" in resp2.headers.get("WWW-Authenticate", "")


def test_expired_token_returns_401(client):
    """Expired tokens must be rejected."""
    settings = get_settings()
    # Issue a token with -10 minutes TTL (expired in the past)
    token, _ = issue_session_token("sarah.compliance", settings.auth_secret_key, ttl_minutes=-10)

    response = client.get(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert "Bearer" in response.headers.get("WWW-Authenticate", "")


def test_inactive_user_token_returns_403(client, auth_service):
    """A valid token for an inactive user must return 403 Forbidden."""
    settings = get_settings()
    # Ensure repository is loaded first
    auth_service._repository.get_by_username("sarah.compliance")

    # Temporarily register an inactive user
    from app.core.database import SessionLocal
    from app.schemas.auth_users_table import AuthUser

    with SessionLocal() as db:
        db.query(AuthUser).filter_by(username="inactive.analyst").delete()
        db.add(AuthUser(
            username="inactive.analyst",
            email="inactive@example.com",
            password_hash="pbkdf2_sha256$260000$00$00",
            display_name="Inactive Analyst",
            role="Compliance Analyst",
            status="Inactive",
        ))
        db.commit()

    if hasattr(auth_service._repository, "_users"):
        inactive_user = AuthUserRecord(
            username="inactive.analyst",
            password_hash="pbkdf2_sha256$260000$00$00",
            display_name="Inactive Analyst",
            role="Compliance Analyst",
            status="Inactive",
        )
        auth_service._repository._users["inactive.analyst"] = inactive_user

    try:
        token, _ = issue_session_token("inactive.analyst", settings.auth_secret_key, ttl_minutes=60)
        response = client.get(
            "/api/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
        assert "inactive" in response.json().get("detail", "").lower()
    finally:
        with SessionLocal() as db:
            db.query(AuthUser).filter_by(username="inactive.analyst").delete()
            db.commit()
        if hasattr(auth_service._repository, "_users"):
            auth_service._repository._users.pop("inactive.analyst", None)


def test_valid_token_authenticated(client, valid_token):
    """A valid token allows accessing protected endpoints."""
    response = client.get(
        "/api/sessions",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_spoofed_user_header_ignored(client, valid_token):
    """X-User-ID header must be ignored; only token-derived identity is trusted."""
    # When escalating an answer in the review queue, escalated_by must come from token (sarah.compliance)
    # even if an attacker passes X-User-ID: hacker_bob
    escalate_payload = {
        "response_id": "test_resp_spoof_check_001",
        "query": "Test compliance rule query",
        "user_answer": "Test answer content",
        "reason": "confidence_low",
        "confidence_score": 0.45,
    }

    response = client.post(
        "/api/review-queue/escalate",
        json=escalate_payload,
        headers={
            "Authorization": f"Bearer {valid_token}",
            "X-User-ID": "hacker_bob",  # Spoofed user ID
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    item_id = data["item_id"]

    from app.db.review_queue_repository import get_review_queue_repo
    repo = get_review_queue_repo()
    item = await repo.get_by_id(item_id)
    assert item is not None
    assert item.metadata.get("escalated_by") == "sarah.compliance"
    assert item.metadata.get("escalated_by") != "hacker_bob"


def test_chat_sessions_schema_user_and_tenant():
    """Verify ChatSession model schema has mandatory user_id, tenant_id, and composite indexes."""
    mapper = inspect(ChatSession)
    
    # user_id must be NOT NULL (nullable=False)
    user_id_col = mapper.columns["user_id"]
    assert not user_id_col.nullable, "ChatSession.user_id must be non-nullable"

    # tenant_id must exist and be nullable
    tenant_id_col = mapper.columns["tenant_id"]
    assert tenant_id_col.nullable, "ChatSession.tenant_id must be nullable"

    # Verify indexes
    index_names = {idx.name for idx in ChatSession.__table__.indexes}
    assert "idx_session_user_tenant" in index_names, "Missing idx_session_user_tenant index"
    assert "idx_session_user_created" in index_names, "Missing idx_session_user_created index"


def test_query_evidence_schema_user_and_tenant():
    """Verify QueryEvidence model schema has mandatory user_id, tenant_id, and composite indexes."""
    mapper = inspect(QueryEvidence)

    # user_id must be NOT NULL (nullable=False)
    user_id_col = mapper.columns["user_id"]
    assert not user_id_col.nullable, "QueryEvidence.user_id must be non-nullable"

    # tenant_id must exist and be nullable
    tenant_id_col = mapper.columns["tenant_id"]
    assert tenant_id_col.nullable, "QueryEvidence.tenant_id must be nullable"

    # Verify indexes
    index_names = {idx.name for idx in QueryEvidence.__table__.indexes}
    assert "idx_qe_session_user" in index_names, "Missing idx_qe_session_user index"
    assert "idx_qe_user_session" in index_names, "Missing idx_qe_user_session index"
    assert "idx_qe_tenant_user" in index_names, "Missing idx_qe_tenant_user index"


def test_database_migration_applied():
    """Verify SQLite database data.db has all required columns and indexes."""
    db_path = Path(__file__).resolve().parents[1] / "data.db"
    if not db_path.exists():
        pytest.skip("data.db does not exist in backend directory")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check chat_sessions columns
        cursor.execute("PRAGMA table_info(chat_sessions)")
        cs_cols = {row[1] for row in cursor.fetchall()}
        assert "user_id" in cs_cols, "chat_sessions missing user_id"
        assert "tenant_id" in cs_cols, "chat_sessions missing tenant_id"

        # Check no NULL user_ids exist in chat_sessions
        cursor.execute("SELECT COUNT(*) FROM chat_sessions WHERE user_id IS NULL")
        null_count = cursor.fetchone()[0]
        assert null_count == 0, "chat_sessions contains NULL user_id records"

        # Check query_evidence columns
        cursor.execute("PRAGMA table_info(query_evidence)")
        qe_cols = {row[1] for row in cursor.fetchall()}
        assert "user_id" in qe_cols, "query_evidence missing user_id"
        assert "tenant_id" in qe_cols, "query_evidence missing tenant_id"

        # Check no NULL user_ids exist in query_evidence
        cursor.execute("SELECT COUNT(*) FROM query_evidence WHERE user_id IS NULL")
        qe_null_count = cursor.fetchone()[0]
        assert qe_null_count == 0, "query_evidence contains NULL user_id records"

        # Check indexes exist
        cursor.execute("PRAGMA index_list(chat_sessions)")
        cs_indexes = {row[1] for row in cursor.fetchall()}
        assert "idx_session_user_tenant" in cs_indexes, "Missing idx_session_user_tenant index on chat_sessions"
        assert "idx_session_user_created" in cs_indexes, "Missing idx_session_user_created index on chat_sessions"

        cursor.execute("PRAGMA index_list(query_evidence)")
        qe_indexes = {row[1] for row in cursor.fetchall()}
        assert "idx_qe_session_user" in qe_indexes, "Missing idx_qe_session_user index on query_evidence"
        assert "idx_qe_user_session" in qe_indexes, "Missing idx_qe_user_session index on query_evidence"
        assert "idx_qe_tenant_user" in qe_indexes, "Missing idx_qe_tenant_user index on query_evidence"
    finally:
        conn.close()
