# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_session_isolation.py
=========================
Phase 2 Validation Tests: Session API Authorization & Isolation.
Verifies that:
1. User A cannot list User B's sessions.
2. User A receives 404 when attempting to read User B's session.
3. User A receives 404 when attempting to overwrite User B's session.
4. User A receives 404 when attempting to delete User B's session.
5. Multi-tenant boundaries prevent cross-tenant access.
6. Unauthenticated requests to all session endpoints are rejected with 401.
7. Attempting to spoof user_id in session payload is sanitized server-side.
"""
import json
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.auth.security import issue_session_token
from app.api.routes import sessions as sessions_route
from app.core.database import SessionLocal
from app.schemas.chat_sessions_table import ChatSession


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_sessions_dir(monkeypatch):
    """Isolate session file storage to a temporary directory."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_isolation_sessions_"))
    monkeypatch.setattr(sessions_route, "SESSIONS_DIR", temp_dir)
    yield temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def token_user_a():
    """Token for User A (sarah.compliance)."""
    settings = get_settings()
    token, _ = issue_session_token("sarah.compliance", settings.auth_secret_key, ttl_minutes=60)
    return token


@pytest.fixture
def token_user_b():
    """Token for User B (vikram.pm)."""
    settings = get_settings()
    token, _ = issue_session_token("vikram.pm", settings.auth_secret_key, ttl_minutes=60)
    return token


@pytest.fixture(autouse=True)
def cleanup_database_sessions():
    """Clean up any test sessions created in the database during tests."""
    def _clean():
        test_session_ids = [
            "iso-sess-user-a-01",
            "iso-sess-user-b-01",
            "iso-sess-user-b-02",
            "iso-sess-tenant-t1",
            "iso-sess-tenant-t2",
            "iso-sess-spoof-attempt",
        ]
        with SessionLocal() as db:
            for sid in test_session_ids:
                row = db.query(ChatSession).filter_by(session_id=sid).first()
                if row:
                    db.delete(row)
            db.commit()

    _clean()
    yield
    _clean()


def test_unauthenticated_session_endpoints_return_401(client, temp_sessions_dir):
    """All session endpoints must reject unauthenticated requests with 401."""
    sess_id = "unauth-test-sess"
    
    # List
    r_list = client.get("/api/sessions")
    assert r_list.status_code == 401
    assert "Bearer" in r_list.headers.get("WWW-Authenticate", "")

    # Get
    r_get = client.get(f"/api/sessions/{sess_id}")
    assert r_get.status_code == 401

    # Post
    r_post = client.post(f"/api/sessions/{sess_id}", json={"history": [{"role": "user", "content": "hi"}]})
    assert r_post.status_code == 401

    # Delete
    r_del = client.delete(f"/api/sessions/{sess_id}")
    assert r_del.status_code == 401


def test_user_a_cannot_list_user_b_sessions(client, temp_sessions_dir, token_user_a, token_user_b):
    """User A should not see User B's sessions when listing sessions."""
    sess_a = "iso-sess-user-a-01"
    sess_b = "iso-sess-user-b-01"

    # User A creates a session
    resp_a = client.post(
        f"/api/sessions/{sess_a}",
        json={"history": [{"role": "user", "content": "User A compliance question"}]},
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    assert resp_a.status_code == 200

    # User B creates a session
    resp_b = client.post(
        f"/api/sessions/{sess_b}",
        json={"history": [{"role": "user", "content": "User B portfolio allocation"}]},
        headers={"Authorization": f"Bearer {token_user_b}"},
    )
    assert resp_b.status_code == 200

    # User A lists sessions: must see sess_a, must NOT see sess_b
    list_a = client.get(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    assert list_a.status_code == 200
    ids_a = [s["session_id"] for s in list_a.json()]
    assert sess_a in ids_a
    assert sess_b not in ids_a, "User A must not see User B's session in list"

    # User B lists sessions: must see sess_b, must NOT see sess_a
    list_b = client.get(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token_user_b}"},
    )
    assert list_b.status_code == 200
    ids_b = [s["session_id"] for s in list_b.json()]
    assert sess_b in ids_b
    assert sess_a not in ids_b, "User B must not see User A's session in list"


def test_user_a_cannot_read_user_b_session(client, temp_sessions_dir, token_user_a, token_user_b):
    """User A must receive 404 (never 403 or 200) when requesting User B's session."""
    sess_b = "iso-sess-user-b-01"

    # User B creates a session
    client.post(
        f"/api/sessions/{sess_b}",
        json={
            "session_id": sess_b,
            "title": "Confidential Portfolio Strategy",
            "history": [
                {"role": "user", "content": "Show confidential trade history for Q3"},
                {"role": "assistant", "content": "Here is the confidential data: 12345"},
            ],
        },
        headers={"Authorization": f"Bearer {token_user_b}"},
    )

    # User A tries to read User B's session
    cross_read = client.get(
        f"/api/sessions/{sess_b}",
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    # Must return 404 to avoid leaking session existence
    assert cross_read.status_code == 404, (
        f"Cross-user read should return 404 Not Found, got {cross_read.status_code}"
    )

    # User B can read their own session
    owner_read = client.get(
        f"/api/sessions/{sess_b}",
        headers={"Authorization": f"Bearer {token_user_b}"},
    )
    assert owner_read.status_code == 200
    data = owner_read.json()
    assert data["session_id"] == sess_b
    assert data["user_id"] == "vikram.pm"
    assert len(data["history"]) == 2


def test_user_a_cannot_overwrite_user_b_session(client, temp_sessions_dir, token_user_a, token_user_b):
    """User A must receive 404 and cannot overwrite User B's session data."""
    sess_b = "iso-sess-user-b-01"

    # User B creates initial session
    client.post(
        f"/api/sessions/{sess_b}",
        json={"history": [{"role": "user", "content": "Original User B content"}]},
        headers={"Authorization": f"Bearer {token_user_b}"},
    )

    # User A attempts to overwrite User B's session
    malicious_resp = client.post(
        f"/api/sessions/{sess_b}",
        json={"history": [{"role": "user", "content": "MALICIOUS OVERWRITE BY USER A"}]},
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    assert malicious_resp.status_code == 404, (
        f"Cross-user overwrite should return 404, got {malicious_resp.status_code}"
    )

    # Verify User B's session remains untouched on disk and in database
    owner_read = client.get(
        f"/api/sessions/{sess_b}",
        headers={"Authorization": f"Bearer {token_user_b}"},
    )
    assert owner_read.status_code == 200
    assert owner_read.json()["history"][0]["content"] == "Original User B content"

    # Verify DB ownership is still User B
    with SessionLocal() as db:
        record = db.query(ChatSession).filter_by(session_id=sess_b).first()
        assert record is not None
        assert record.user_id == "vikram.pm"


def test_user_a_cannot_delete_user_b_session(client, temp_sessions_dir, token_user_a, token_user_b):
    """User A must receive 404 and cannot delete User B's session."""
    sess_b = "iso-sess-user-b-01"

    # User B creates session
    client.post(
        f"/api/sessions/{sess_b}",
        json={"history": [{"role": "user", "content": "User B important session"}]},
        headers={"Authorization": f"Bearer {token_user_b}"},
    )

    file_path = temp_sessions_dir / f"{sess_b}.json"
    assert file_path.exists()

    # User A tries to delete User B's session
    del_cross = client.delete(
        f"/api/sessions/{sess_b}",
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    assert del_cross.status_code == 404, (
        f"Cross-user delete should return 404, got {del_cross.status_code}"
    )

    # File and DB record must still exist
    assert file_path.exists()
    with SessionLocal() as db:
        record = db.query(ChatSession).filter_by(session_id=sess_b).first()
        assert record is not None

    # User B can delete their own session
    del_owner = client.delete(
        f"/api/sessions/{sess_b}",
        headers={"Authorization": f"Bearer {token_user_b}"},
    )
    assert del_owner.status_code == 200
    assert del_owner.json()["status"] == "deleted"
    assert not file_path.exists()

    # Once deleted, deleting again returns 404
    del_again = client.delete(
        f"/api/sessions/{sess_b}",
        headers={"Authorization": f"Bearer {token_user_b}"},
    )
    assert del_again.status_code == 404


def test_tenant_isolation_boundary(client, temp_sessions_dir):
    """Sessions belonging to tenant T1 must be invisible and inaccessible to tenant T2."""
    from app.api.deps import get_current_user
    from app.auth.service import AuthenticatedUser

    sess_t1 = "iso-sess-tenant-t1"
    
    user_tenant_1 = AuthenticatedUser(
        username="tenant_user",
        display_name="Tenant User 1",
        role="Analyst",
        department="Finance",
        email="t1@example.com",
        avatar_initials="T1",
        status="Active",
        tenant_id="tenant-alpha",
    )

    user_tenant_2 = AuthenticatedUser(
        username="tenant_user",  # Even with identical username
        display_name="Tenant User 2",
        role="Analyst",
        department="Finance",
        email="t2@example.com",
        avatar_initials="T2",
        status="Active",
        tenant_id="tenant-beta",
    )

    # Act as Tenant 1 User to create session
    app.dependency_overrides[get_current_user] = lambda: user_tenant_1
    try:
        resp = client.post(
            f"/api/sessions/{sess_t1}",
            json={"history": [{"role": "user", "content": "Tenant Alpha confidential data"}]},
            headers={"Authorization": "Bearer fake_token"},
        )
        assert resp.status_code == 200

        # Switch identity to Tenant 2 User
        app.dependency_overrides[get_current_user] = lambda: user_tenant_2

        # 1. Listing should not return sess_t1
        list_resp = client.get(
            "/api/sessions",
            headers={"Authorization": "Bearer fake_token"},
        )
        assert list_resp.status_code == 200
        assert sess_t1 not in [s["session_id"] for s in list_resp.json()]

        # 2. Get should return 404
        get_resp = client.get(
            f"/api/sessions/{sess_t1}",
            headers={"Authorization": "Bearer fake_token"},
        )
        assert get_resp.status_code == 404

        # 3. Overwrite should return 404
        post_resp = client.post(
            f"/api/sessions/{sess_t1}",
            json={"history": [{"role": "user", "content": "Tenant Beta overwrite attempt"}]},
            headers={"Authorization": "Bearer fake_token"},
        )
        assert post_resp.status_code == 404

        # 4. Delete should return 404
        del_resp = client.delete(
            f"/api/sessions/{sess_t1}",
            headers={"Authorization": "Bearer fake_token"},
        )
        assert del_resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_session_saving_sanitizes_user_id(client, temp_sessions_dir, token_user_a):
    """Even if client sends a malicious user_id in payload, server overrides with current user."""
    sess_id = "iso-sess-spoof-attempt"
    spoofed_payload = {
        "session_id": sess_id,
        "user_id": "victim_admin",
        "tenant_id": "malicious_tenant",
        "history": [{"role": "user", "content": "Sanitize check"}],
    }

    resp = client.post(
        f"/api/sessions/{sess_id}",
        json=spoofed_payload,
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "sarah.compliance"

    # Check on disk: user_id stamped to authenticated user
    file_path = temp_sessions_dir / f"{sess_id}.json"
    content = json.loads(file_path.read_text(encoding="utf-8"))
    assert content["user_id"] == "sarah.compliance"

    # Check in DB: user_id matches authenticated user
    with SessionLocal() as db:
        record = db.query(ChatSession).filter_by(session_id=sess_id).first()
        assert record is not None
        assert record.user_id == "sarah.compliance"
