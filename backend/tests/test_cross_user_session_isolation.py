import os
import sys
import pytest
from starlette.testclient import TestClient

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app
from app.core.database import SessionLocal
from app.schemas.chat_sessions_table import ChatSession

client = TestClient(app)

def test_cross_user_session_id_auto_heals_without_404():
    """
    Test that when User B's client accidentally sends User A's session_id
    (e.g., from browser localStorage leakage across logins):
    1. User A's data is isolated and untouched.
    2. User B does NOT get a 404 error on /api/chat/stream.
    3. User B does NOT get a 404 error on /api/sessions/{session_id}.
    """
    # 1. User A (compliance_officer) logs in
    login_a = client.post("/api/auth/login", json={"username": "compliance_officer", "password": "Compliance@2026"})
    assert login_a.status_code == 200
    token_a = login_a.json()["token"]

    session_a_id = "test_sess_user_a_isolation_123"

    # Save User A's session
    save_a = client.post(
        f"/api/sessions/{session_a_id}",
        json={
            "session_id": session_a_id,
            "title": "User A Private Conversation",
            "history": [{"role": "user", "content": "Confidential query from User A"}],
        },
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert save_a.status_code == 200

    # Verify User A owns session_a_id in database
    with SessionLocal() as db:
        sess_rec = db.query(ChatSession).filter_by(session_id=session_a_id).first()
        assert sess_rec is not None
        assert sess_rec.user_id == "compliance_officer"

    # 2. User B (sarah.compliance) logs in
    login_b = client.post("/api/auth/login", json={"username": "sarah.compliance", "password": "Compliance@2026"})
    assert login_b.status_code == 200
    token_b = login_b.json()["token"]

    # User B sends POST /api/chat/stream using User A's session_a_id
    stream_resp = client.post(
        "/api/chat/stream",
        json={
            "query": "What are mutual fund borrowing limits?",
            "history": [],
            "session_id": session_a_id,  # Foreign session ID!
            "mode": "contextgraph"
        },
        headers={"Authorization": f"Bearer {token_b}"}
    )
    # MUST NOT be 404!
    assert stream_resp.status_code == 200, f"Expected 200, got {stream_resp.status_code}: {stream_resp.text}"
    # Header should reflect a newly allocated session ID
    rekeyed_id = stream_resp.headers.get("X-Session-ID")
    assert rekeyed_id is not None
    assert rekeyed_id != session_a_id

    # 3. User B calls POST /api/sessions/{session_a_id} using User A's session_a_id
    save_b = client.post(
        f"/api/sessions/{session_a_id}",
        json={
            "session_id": session_a_id,
            "title": "User B Conversation",
            "history": [{"role": "user", "content": "Sarah query"}],
        },
        headers={"Authorization": f"Bearer {token_b}"}
    )
    # Must be 404 to block unauthorized cross-user session overwrite
    assert save_b.status_code == 404, f"Expected 404, got {save_b.status_code}: {save_b.text}"

    # 4. Verify User A's session was NEVER overwritten or corrupted
    with SessionLocal() as db:
        orig = db.query(ChatSession).filter_by(session_id=session_a_id).first()
        assert orig is not None
        assert orig.user_id == "compliance_officer"

    # Clean up test sessions
    client.delete(f"/api/sessions/{session_a_id}", headers={"Authorization": f"Bearer {token_a}"})
    if rekeyed_id:
        client.delete(f"/api/sessions/{rekeyed_id}", headers={"Authorization": f"Bearer {token_b}"})
