# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_sessions_api.py
====================
Unit tests for session management API routes (/api/sessions).
"""
import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import sessions as sessions_route

# Build test app with sessions router
test_app = FastAPI()
test_app.include_router(sessions_route.router, prefix="/api")


@pytest.fixture
def temp_sessions_dir(monkeypatch):
    """Create a temporary directory for session storage tests."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_chat_sessions_"))
    monkeypatch.setattr(sessions_route, "SESSIONS_DIR", temp_dir)
    yield temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_list_sessions_empty(temp_sessions_dir):
    client = TestClient(test_app)
    response = client.get("/api/sessions")
    assert response.status_code == 200
    assert response.json() == []


def test_save_and_get_session(temp_sessions_dir):
    client = TestClient(test_app)
    session_id = "test-session-uuid-1234"
    payload = {
        "session_id": session_id,
        "history": [
            {"role": "user", "content": "What is the NAV of HDFC Top 100?", "turn_index": 0},
            {"role": "assistant", "content": "The NAV is 950.50", "turn_index": 0},
        ]
    }

    # Save session
    save_resp = client.post(f"/api/sessions/{session_id}", json=payload)
    assert save_resp.status_code == 200
    assert save_resp.json() == {"status": "ok", "session_id": session_id}

    # Verify file exists on disk with 2-space indentation and UTF-8
    file_path = temp_sessions_dir / f"{session_id}.json"
    assert file_path.exists()
    content = file_path.read_text(encoding="utf-8")
    assert '  "session_id": "test-session-uuid-1234"' in content

    # Get session
    get_resp = client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["session_id"] == session_id
    assert len(data["history"]) == 2


def test_list_sessions_preview_and_sorting(temp_sessions_dir):
    client = TestClient(test_app)

    # Create session 1
    s1 = temp_sessions_dir / "sess-1.json"
    s1.write_text(json.dumps([
        {"role": "user", "content": "Short query"},
        {"role": "assistant", "content": "Short answer"}
    ]), encoding="utf-8")
    os.utime(s1, (1000, 1000))

    # Create session 2 with long query (> 45 chars)
    s2 = temp_sessions_dir / "sess-2.json"
    s2.write_text(json.dumps([
        {"role": "user", "content": "What are the SEBI limits on large cap equity funds under Regulation 16C?"},
        {"role": "assistant", "content": "Here is the answer"}
    ]), encoding="utf-8")
    os.utime(s2, (2000, 2000))

    # Create corrupt file
    corrupt = temp_sessions_dir / "corrupt.json"
    corrupt.write_text("invalid json content {{{", encoding="utf-8")

    list_resp = client.get("/api/sessions")
    assert list_resp.status_code == 200
    items = list_resp.json()

    # Corrupt file should be skipped gracefully
    assert len(items) == 2

    # Newest first
    assert items[0]["session_id"] == "sess-2"
    assert items[0]["preview"] == "What are the SEBI limits on large cap equity…"
    assert len(items[0]["preview"]) == 45
    assert items[0]["turn_count"] == 1

    assert items[1]["session_id"] == "sess-1"
    assert items[1]["preview"] == "Short query"
    assert items[1]["turn_count"] == 1


def test_delete_session(temp_sessions_dir):
    client = TestClient(test_app)
    session_id = "sess-to-delete"
    path = temp_sessions_dir / f"{session_id}.json"
    path.write_text(json.dumps({"session_id": session_id, "history": []}), encoding="utf-8")

    del_resp = client.delete(f"/api/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"status": "deleted", "session_id": session_id}
    assert not path.exists()

    # Delete non-existent
    del_resp2 = client.delete(f"/api/sessions/{session_id}")
    assert del_resp2.status_code == 200
    assert del_resp2.json() == {"status": "not_found", "session_id": session_id}
