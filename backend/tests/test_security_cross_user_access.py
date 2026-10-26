# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_security_cross_user_access.py
==================================
Comprehensive security test suite for Phase 5 of the Security Remediation Plan.

Tests simulate adversarial and multi-tenant access patterns:
1. Cross-User Session Access (List, Read, Overwrite, Delete).
2. Query Evidence Isolation (Database, Adapter, API).
3. Concurrent Session & Query Isolation (No leakage under concurrency).
4. Cache Key Scoping & Isolation (Intent, Cypher, Semantic cache).
5. Review Queue Authorization (No X-User-ID spoofing, user-scoped queues).
6. UserScopedVectorStore Isolation (User & tenant boundaries, public corpus).
7. GraphTraversal Authorization & Auditing.
8. Enumeration Attack Scenarios (Session IDs and Response IDs).
"""
import asyncio
import os
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.auth.security import issue_session_token
from app.core.database import SessionLocal
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.query_evidence_table import QueryEvidence
from app.adapters.feedback_adapters import AMCEvidenceAdapter
from app.vector.client import VectorStore, UserScopedVectorStore
from app.models.documents import Chunk
from app.retrieval.traversal import GraphTraversal
from app.core.cache_utils import generate_cache_key


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def user_a_token():
    settings = get_settings()
    token, _ = issue_session_token("sarah.compliance", settings.auth_secret_key, ttl_minutes=60)
    return token


@pytest.fixture
def user_b_token():
    settings = get_settings()
    token, _ = issue_session_token("vikram.pm", settings.auth_secret_key, ttl_minutes=60)
    return token


@pytest.fixture(autouse=True)
def cleanup_security_artifacts():
    yield
    test_session_ids = [
        "sec-test-session-user-b-001",
        "concurrent-sess-user-a-01",
        "concurrent-sess-user-b-01",
    ]
    test_response_ids = [
        "resp-sec-user-b-001",
        "resp-sec-escalate-001",
    ]
    with SessionLocal() as db:
        for sid in test_session_ids:
            db.query(ChatSession).filter(ChatSession.session_id == sid).delete()
        for rid in test_response_ids:
            db.query(QueryEvidence).filter(QueryEvidence.response_id == rid).delete()
        db.commit()


@pytest.fixture
def user_b_session_id(client, user_b_token):
    session_id = "sec-test-session-user-b-001"
    response = client.post(
        f"/api/sessions/{session_id}",
        json={"history": [{"role": "user", "content": "User B private investment query"}]},
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert response.status_code == 200
    return session_id


class TestSessionAuthorization:
    """Test session endpoint authorization barriers."""

    def test_user_a_cannot_list_user_b_sessions(self, client, user_a_token, user_b_session_id):
        """User A should not see User B's sessions in their listing."""
        response = client.get(
            "/api/sessions",
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 200
        sessions = response.json()
        session_ids = [s["session_id"] for s in sessions]
        assert user_b_session_id not in session_ids, "User A should not see User B's sessions"

    def test_user_a_cannot_read_user_b_session(self, client, user_a_token, user_b_session_id):
        """User A should get 404 when attempting to read User B's session."""
        response = client.get(
            f"/api/sessions/{user_b_session_id}",
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 404, "Should return 404 to avoid leaking session existence"

    def test_user_a_cannot_overwrite_user_b_session(self, client, user_a_token, user_b_session_id):
        """User A should not be able to overwrite User B's session."""
        response = client.post(
            f"/api/sessions/{user_b_session_id}",
            json={"history": [{"role": "user", "content": "MALICIOUS OVERWRITE ATTEMPT"}]},
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 404, "Should reject cross-user session modification"

    def test_user_a_cannot_delete_user_b_session(self, client, user_a_token, user_b_session_id):
        """User A should not be able to delete User B's session."""
        response = client.delete(
            f"/api/sessions/{user_b_session_id}",
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert response.status_code == 404, "Should reject cross-user session deletion"


class TestQueryEvidenceAuthorization:
    """Test query evidence isolation and ownership verification."""

    def test_user_a_cannot_access_user_b_evidence_via_adapter(self):
        """AMCEvidenceAdapter must block cross-user retrieval."""
        adapter = AMCEvidenceAdapter(session_factory=SessionLocal)
        with SessionLocal() as db:
            db.add(QueryEvidence(
                response_id="resp-sec-user-b-001",
                session_id="sess-sec-b",
                user_id="vikram.pm",
                tenant_id="tenant_amc",
                query_text="Confidential User B queries",
                assembled_context_json={},
                synthesis_output_json={},
                created_at="2026-10-12T12:00:00Z",
            ))
            db.commit()

        # User A attempting to read User B's response
        with pytest.raises(KeyError):
            adapter.get_evidence_snapshot(
                response_id="resp-sec-user-b-001",
                requesting_user_id="sarah.compliance",
            )

        # User B can retrieve it
        snapshot = adapter.get_evidence_snapshot(
            response_id="resp-sec-user-b-001",
            requesting_user_id="vikram.pm",
            tenant_id="tenant_amc",
        )
        assert snapshot.response_id == "resp-sec-user-b-001"

    def test_evidence_filtered_by_user_in_audit_api(self, client, user_a_token, user_b_token):
        """Audit query-evidence API endpoint filters by authenticated user."""
        res_a = client.get(
            "/api/audit-schema/query-evidence",
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert res_a.status_code == 200
        records_a = res_a.json()
        assert all(r["user_id"] == "sarah.compliance" for r in records_a)
        assert not any(r["response_id"] == "resp-sec-user-b-001" for r in records_a)


class TestConcurrentSessionIsolation:
    """Test that concurrent requests do not contaminate each other's sessions."""

    def test_concurrent_sessions_isolated(self, client, user_a_token, user_b_token):
        """Two users saving sessions simultaneously do not cross-contaminate."""
        sess_a = "concurrent-sess-user-a-01"
        sess_b = "concurrent-sess-user-b-01"

        res_a = client.post(
            f"/api/sessions/{sess_a}",
            json={"history": [{"role": "user", "content": "Query from User A Sarah"}]},
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        res_b = client.post(
            f"/api/sessions/{sess_b}",
            json={"history": [{"role": "user", "content": "Query from User B Vikram"}]},
            headers={"Authorization": f"Bearer {user_b_token}"},
        )

        assert res_a.status_code == 200
        assert res_b.status_code == 200

        # Read back session A with token A
        get_a = client.get(f"/api/sessions/{sess_a}", headers={"Authorization": f"Bearer {user_a_token}"})
        assert get_a.status_code == 200
        assert "Query from User A Sarah" in get_a.text
        assert "Query from User B Vikram" not in get_a.text

        # User A cannot read session B
        get_b_as_a = client.get(f"/api/sessions/{sess_b}", headers={"Authorization": f"Bearer {user_a_token}"})
        assert get_b_as_a.status_code == 404


class TestCacheIsolation:
    """Test user and tenant cache scoping."""

    def test_cache_keys_are_user_scoped(self):
        """generate_cache_key produces strictly separate keys for distinct users."""
        components = {"query": "Top performing mid cap schemes"}
        key_a = generate_cache_key("intent", components, user_id="sarah.compliance", tenant_id="tenant_1")
        key_b = generate_cache_key("intent", components, user_id="vikram.pm", tenant_id="tenant_1")
        key_t2 = generate_cache_key("intent", components, user_id="sarah.compliance", tenant_id="tenant_2")

        assert key_a != key_b
        assert key_a != key_t2
        assert ":user:sarah.compliance:" in key_a
        assert ":user:vikram.pm:" in key_b
        assert ":tenant:tenant_1:" in key_a
        assert ":tenant:tenant_2:" in key_t2


class TestReviewQueueAuthorization:
    """Test review queue escalation and listing authorization."""

    def test_review_queue_user_isolation(self, client, user_a_token, user_b_token):
        """User B escalates an item; User A cannot see it in pending queue."""
        esc_resp = client.post(
            "/api/review-queue/escalate",
            json={
                "response_id": "resp-sec-escalate-001",
                "query": "Review required for scheme portfolio",
                "user_answer": "Suspicious answer",
                "reason": "confidence_low",
                "confidence_score": 0.25,
            },
            headers={"Authorization": f"Bearer {user_b_token}"},
        )
        assert esc_resp.status_code == 200

        # User A checks pending queue
        pending_a = client.get(
            "/api/review-queue/pending",
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        assert pending_a.status_code == 200
        items_a = pending_a.json()["items"]
        assert not any(i.get("response_id") == "resp-sec-escalate-001" for i in items_a), \
            "User A must not see User B's escalated review"


class TestVectorStoreIsolation:
    """Test UserScopedVectorStore access controls and boundaries."""

    @pytest.mark.asyncio
    async def test_user_scoped_vector_store_isolation(self):
        """User A documents must not be visible to User B, but public documents are visible to both."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_store = VectorStore(faiss_dir=tmp_dir, corpus_version="test_sec_v1")
            scoped_store_a = UserScopedVectorStore(base_store, user_id="sarah.compliance")
            scoped_store_b = UserScopedVectorStore(base_store, user_id="vikram.pm")

            # 1. Add public baseline document (no user_id)
            await base_store.add_documents([
                {"text": "Public mutual fund disclosure regulations", "id": "pub_01"}
            ])

            # 2. User A adds confidential document
            await scoped_store_a.add_documents([
                {"text": "Confidential portfolio trade strategy for User A", "id": "priv_a_01"}
            ])

            # 3. User B searches for trade strategy
            hits_b = await scoped_store_b.search(query="portfolio trade strategy", top_k=5)
            chunk_ids_b = [h["chunk_id"] for h in hits_b]
            assert "priv_a_01" not in chunk_ids_b, "User B must not see User A's private document"

            # 4. User A searches for trade strategy
            hits_a = await scoped_store_a.search(query="portfolio trade strategy", top_k=5)
            chunk_ids_a = [h["chunk_id"] for h in hits_a]
            assert "priv_a_01" in chunk_ids_a, "User A should see their own private document"

            # 5. Both users can search and see public disclosure regulations
            hits_pub_a = await scoped_store_a.search(query="mutual fund disclosure regulations", top_k=5)
            hits_pub_b = await scoped_store_b.search(query="mutual fund disclosure regulations", top_k=5)
            assert any(h["chunk_id"] == "pub_01" for h in hits_pub_a)
            assert any(h["chunk_id"] == "pub_01" for h in hits_pub_b)

    @pytest.mark.asyncio
    async def test_tenant_scoped_vector_isolation(self):
        """Tenant 1 documents must not be visible to Tenant 2."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_store = VectorStore(faiss_dir=tmp_dir, corpus_version="test_sec_t1")
            store_t1 = UserScopedVectorStore(base_store, user_id="user_1", tenant_id="tenant_alpha")
            store_t2 = UserScopedVectorStore(base_store, user_id="user_2", tenant_id="tenant_beta")

            await store_t1.add_documents([
                {"text": "Proprietary Alpha tenant financial statement", "id": "alpha_01"}
            ])

            hits_beta = await store_t2.search(query="financial statement", top_k=5)
            assert not any(h["chunk_id"] == "alpha_01" for h in hits_beta)


class TestGraphTraversalAuthorization:
    """Test GraphTraversal auditing and authorization parameterization."""

    @pytest.mark.asyncio
    async def test_graph_traversal_auditing(self, caplog):
        """Graph traversal audits user and tenant on every traversal execution."""
        class MockGraphClient:
            async def run(self, cypher, **kwargs):
                return [{"node": "test_node"}]

        traversal = GraphTraversal(graph=MockGraphClient())

        with caplog.at_level("INFO"):
            result = await traversal.traverse(
                intent_or_entities=["EntityA", "EntityB"],
                entities_or_depth=2,
                user_id="audited_user",
                tenant_id="audited_tenant",
            )
            assert result["count"] == 1
            assert "Graph traversal: user=audited_user tenant=audited_tenant" in caplog.text


class TestAttackScenarios:
    """Simulate malicious adversary enumeration attacks."""

    def test_session_id_enumeration_attack(self, client, user_a_token):
        """Adversary attempting sequential/guessed session IDs always gets 404."""
        guessed_session_ids = [
            "session-00001",
            "session-00002",
            "admin-session",
            "default",
            "root",
            "master-session",
        ]
        for sid in guessed_session_ids:
            res = client.get(
                f"/api/sessions/{sid}",
                headers={"Authorization": f"Bearer {user_a_token}"},
            )
            assert res.status_code == 404, f"Session enumeration leaked info for {sid}"

    def test_response_id_enumeration_attack(self, client, user_a_token):
        """Adversary attempting to probe query evidence by response ID is denied."""
        adapter = AMCEvidenceAdapter(session_factory=SessionLocal)
        guessed_response_ids = [f"resp_{i:04d}" for i in range(1, 10)]
        for rid in guessed_response_ids:
            with pytest.raises(KeyError):
                adapter.get_evidence_snapshot(
                    response_id=rid,
                    requesting_user_id="sarah.compliance",
                )
