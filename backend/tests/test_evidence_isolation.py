# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_evidence_isolation.py
==========================
Phase 3 Validation Tests: Query Evidence & Retrieval Pipeline Authorization.
Verifies:
1. `user_id` is mandatory in `QueryEvidenceRecorder.record()`.
2. Cross-user evidence recording in another user's session is rejected.
3. `AMCEvidenceAdapter.get_evidence_snapshot()` enforces user & tenant ownership.
4. `AMCEvidenceAdapter.get_followup_activity()` scopes activity to the user.
5. Chat query endpoints enforce session ownership and record evidence with verified user_id.
6. Audit query evidence listing is strictly user & tenant scoped.
"""
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.auth.security import issue_session_token
from app.core.database import SessionLocal
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.query_evidence_table import QueryEvidence
from app.retrieval.query_evidence_recorder import QueryEvidenceRecorder
from app.adapters.feedback_adapters import AMCEvidenceAdapter


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_evidence_dir(monkeypatch):
    """Temporary directory for query evidence files."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_query_evidence_"))
    recorder = QueryEvidenceRecorder(evidence_dir=temp_dir)
    yield recorder, temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def token_user_a():
    settings = get_settings()
    token, _ = issue_session_token("sarah.compliance", settings.auth_secret_key, ttl_minutes=60)
    return token


@pytest.fixture
def token_user_b():
    settings = get_settings()
    token, _ = issue_session_token("vikram.pm", settings.auth_secret_key, ttl_minutes=60)
    return token


@pytest.fixture(autouse=True)
def cleanup_test_evidence_and_sessions():
    def _do_clean():
        test_session_ids = [
            "sess-ev-user-a",
            "sess-ev-user-b",
            "sess-ev-cross-tenant",
        ]
        test_response_ids = [
            "resp-ev-001",
            "resp-ev-002",
            "resp-ev-003",
            "resp-ev-cross",
        ]
        with SessionLocal() as db:
            for rid in test_response_ids:
                row = db.query(QueryEvidence).filter_by(response_id=rid).first()
                if row:
                    db.delete(row)
            for sid in test_session_ids:
                sess = db.query(ChatSession).filter_by(session_id=sid).first()
                if sess:
                    db.delete(sess)
            db.commit()

    _do_clean()
    yield
    _do_clean()


def test_record_requires_user_id(temp_evidence_dir):
    """QueryEvidenceRecorder must reject recording without a valid user_id."""
    recorder, _ = temp_evidence_dir
    
    # 1. Empty user_id
    res_empty = recorder.record(
        response_id="resp-ev-001",
        session_id="sess-ev-user-a",
        query_text="What are SEBI investment limits?",
        assembled_context_json={"sources": []},
        synthesis_output_json={"answer": "Limits are defined under Reg 16."},
        user_id="",
    )
    assert res_empty is None, "Recording with empty user_id must be rejected"

    # 2. Whitespace-only user_id
    res_ws = recorder.record(
        response_id="resp-ev-001",
        session_id="sess-ev-user-a",
        query_text="What are SEBI investment limits?",
        assembled_context_json={"sources": []},
        synthesis_output_json={"answer": "Limits are defined under Reg 16."},
        user_id="   ",
    )
    assert res_ws is None, "Recording with whitespace user_id must be rejected"


def test_record_verifies_session_ownership(temp_evidence_dir):
    """Recorder must reject recording evidence in a session owned by another user."""
    recorder, _ = temp_evidence_dir

    # User B owns sess-ev-user-b
    with SessionLocal() as db:
        db.add(ChatSession(
            session_id="sess-ev-user-b",
            user_id="vikram.pm",
            created_at="2026-10-12T10:00:00Z",
            updated_at="2026-10-12T10:00:00Z",
        ))
        db.commit()

    # User A (sarah.compliance) attempts to record evidence into User B's session
    cross_rec = recorder.record(
        response_id="resp-ev-cross",
        session_id="sess-ev-user-b",
        query_text="Malicious query injection",
        assembled_context_json={"sources": []},
        synthesis_output_json={"answer": "Exploit"},
        user_id="sarah.compliance",
    )
    assert cross_rec is None, "Recording evidence in another user's session must be rejected"

    # User B (legitimate owner) records evidence -> Success
    valid_rec = recorder.record(
        response_id="resp-ev-002",
        session_id="sess-ev-user-b",
        query_text="Portfolio review question",
        assembled_context_json={"sources": []},
        synthesis_output_json={"answer": "Portfolio analysis"},
        user_id="vikram.pm",
    )
    assert valid_rec is not None
    assert valid_rec["user_id"] == "vikram.pm"

    # Verify in DB: QueryEvidence has user_id stamped properly
    with SessionLocal() as db:
        row = db.query(QueryEvidence).filter_by(response_id="resp-ev-002").first()
        assert row is not None
        assert row.user_id == "vikram.pm"


def test_evidence_adapter_ownership_isolation():
    """AMCEvidenceAdapter must enforce requesting_user_id and tenant_id."""
    adapter = AMCEvidenceAdapter()

    # Create evidence records for User A and User B
    with SessionLocal() as db:
        # Pre-create sessions
        db.add(ChatSession(
            session_id="sess-ev-user-a",
            user_id="sarah.compliance",
            tenant_id="tenant-alpha",
            created_at="2026-10-12T10:00:00Z",
            updated_at="2026-10-12T10:00:00Z",
        ))
        db.add(ChatSession(
            session_id="sess-ev-user-b",
            user_id="vikram.pm",
            tenant_id="tenant-beta",
            created_at="2026-10-12T10:00:00Z",
            updated_at="2026-10-12T10:00:00Z",
        ))

        db.add(QueryEvidence(
            response_id="resp-ev-001",
            session_id="sess-ev-user-a",
            user_id="sarah.compliance",
            tenant_id="tenant-alpha",
            query_text="Compliance check",
            assembled_context_json={"chunks": ["chunk1"]},
            synthesis_output_json={"answer": "Compliance answer"},
            created_at="2026-10-12T10:05:00Z",
        ))
        db.add(QueryEvidence(
            response_id="resp-ev-002",
            session_id="sess-ev-user-b",
            user_id="vikram.pm",
            tenant_id="tenant-beta",
            query_text="Portfolio query",
            assembled_context_json={"chunks": ["chunk2"]},
            synthesis_output_json={"answer": "Portfolio answer"},
            created_at="2026-10-12T10:05:00Z",
        ))
        db.commit()

    # 1. User B tries to read User A's evidence -> KeyError
    with pytest.raises(KeyError):
        adapter.get_evidence_snapshot(
            response_id="resp-ev-001",
            requesting_user_id="vikram.pm",
        )

    # 2. User A reads their own evidence -> Success
    snap_a = adapter.get_evidence_snapshot(
        response_id="resp-ev-001",
        requesting_user_id="sarah.compliance",
    )
    assert snap_a.response_id == "resp-ev-001"
    assert snap_a.original_query == "Compliance check"

    # 3. Tenant mismatch check -> KeyError
    with pytest.raises(KeyError):
        adapter.get_evidence_snapshot(
            response_id="resp-ev-001",
            requesting_user_id="sarah.compliance",
            tenant_id="tenant-beta",  # Wrong tenant
        )

    # 4. validate_response_exists scopes check to requesting user
    assert adapter.validate_response_exists("resp-ev-001", requesting_user_id="sarah.compliance") is True
    assert adapter.validate_response_exists("resp-ev-001", requesting_user_id="vikram.pm") is False
    assert adapter.validate_response_exists("resp-ev-001", requesting_user_id="sarah.compliance", tenant_id="wrong-tenant") is False


def test_evidence_adapter_followup_scoped_to_user():
    """Follow-up query extraction must only return subsequent queries from the same user."""
    adapter = AMCEvidenceAdapter()

    with SessionLocal() as db:
        db.add(ChatSession(
            session_id="sess-ev-user-a",
            user_id="sarah.compliance",
            created_at="2026-10-12T10:00:00Z",
            updated_at="2026-10-12T10:00:00Z",
        ))
        # Anchor response
        db.add(QueryEvidence(
            response_id="resp-ev-001",
            session_id="sess-ev-user-a",
            user_id="sarah.compliance",
            query_text="Initial query",
            assembled_context_json={},
            synthesis_output_json={"answer": "Initial answer"},
            created_at="2026-10-12T10:00:00Z",
        ))
        # Subsequent response from same user
        db.add(QueryEvidence(
            response_id="resp-ev-002",
            session_id="sess-ev-user-a",
            user_id="sarah.compliance",
            query_text="Follow-up clarification",
            assembled_context_json={},
            synthesis_output_json={"answer": "Clarification"},
            created_at="2026-10-12T10:05:00Z",
        ))
        db.commit()

    # User A queries follow-ups: sees the clarification
    followups_a = adapter.get_followup_activity(
        session_id="sess-ev-user-a",
        response_id="resp-ev-001",
        window_minutes=15,
        requesting_user_id="sarah.compliance",
    )
    assert len(followups_a) == 1
    assert followups_a[0].text == "Follow-up clarification"

    # User B queries follow-ups on User A's session: sees nothing
    followups_b = adapter.get_followup_activity(
        session_id="sess-ev-user-a",
        response_id="resp-ev-001",
        window_minutes=15,
        requesting_user_id="vikram.pm",
    )
    assert len(followups_b) == 0


def test_chat_endpoint_rejects_cross_user_session(client, token_user_a, token_user_b):
    """Sending a chat query to a session owned by another user returns 404."""
    # User B creates session sess-ev-user-b
    with SessionLocal() as db:
        db.add(ChatSession(
            session_id="sess-ev-user-b",
            user_id="vikram.pm",
            created_at="2026-10-12T10:00:00Z",
            updated_at="2026-10-12T10:00:00Z",
        ))
        db.commit()

    # User A sends chat query targeting sess-ev-user-b
    resp = client.post(
        "/api/chat/v2",
        json={
            "query": "Show me the portfolio details",
            "session_id": "sess-ev-user-b",
            "history": [],
        },
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    assert resp.status_code == 404, (
        f"Cross-user session chat query should return 404, got {resp.status_code}"
    )


def test_audit_query_evidence_list_scoped_to_user(client, token_user_a, token_user_b):
    """Audit schema query-evidence endpoint returns only the current user's evidence."""
    with SessionLocal() as db:
        db.add(ChatSession(
            session_id="sess-ev-user-a",
            user_id="sarah.compliance",
            created_at="2026-10-12T10:00:00Z",
            updated_at="2026-10-12T10:00:00Z",
        ))
        db.add(ChatSession(
            session_id="sess-ev-user-b",
            user_id="vikram.pm",
            created_at="2026-10-12T10:00:00Z",
            updated_at="2026-10-12T10:00:00Z",
        ))
        db.add(QueryEvidence(
            response_id="resp-ev-001",
            session_id="sess-ev-user-a",
            user_id="sarah.compliance",
            query_text="Sarah compliance audit record",
            assembled_context_json={},
            synthesis_output_json={},
            created_at="2026-10-12T10:00:00Z",
        ))
        db.add(QueryEvidence(
            response_id="resp-ev-002",
            session_id="sess-ev-user-b",
            user_id="vikram.pm",
            query_text="Vikram portfolio audit record",
            assembled_context_json={},
            synthesis_output_json={},
            created_at="2026-10-12T10:00:00Z",
        ))
        db.commit()

    # User A calls GET /api/audit-schema/query-evidence
    res_a = client.get(
        "/api/audit-schema/query-evidence",
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    assert res_a.status_code == 200
    rows_a = res_a.json()
    rids_a = [r["response_id"] for r in rows_a]
    assert "resp-ev-001" in rids_a
    assert "resp-ev-002" not in rids_a, "User A must not see User B's audit evidence"

    # User B calls GET /api/audit-schema/query-evidence
    res_b = client.get(
        "/api/audit-schema/query-evidence",
        headers={"Authorization": f"Bearer {token_user_b}"},
    )
    assert res_b.status_code == 200
    rows_b = res_b.json()
    rids_b = [r["response_id"] for r in rows_b]
    assert "resp-ev-002" in rids_b
    assert "resp-ev-001" not in rids_b, "User B must not see User A's audit evidence"
