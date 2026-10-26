# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_rollback_protocols.py
===========================
Verification test suite for Section 5: Rollback & Emergency Contingency Protocols.

Tests validate:
1. Hard Rollback to legacy (QUERY_ENGINE='legacy') in /query and /chat
2. Canary Rollback with percentage routing (QUERY_ENGINE='canary')
3. Shadow Mode execution (QUERY_ENGINE='shadow')
4. Seamless recovery back to V2 Active (QUERY_ENGINE='v2')
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.deps import Container, get_container
from app.config import Settings
from app.main import create_app
from app.models.api import QueryResponse, ChatResponse


@pytest.fixture
def mock_app():
    container = Container()
    container.settings = Settings(query_engine="v2")
    container.settings.groq_api_key = "gsk_mock_api_key"

    from app.models.query import QueryIntent, SynthesisOutput, AssembledContext, QueryTrace, RetrievalResult, QueryType
    
    intent = QueryIntent(query_type=QueryType.ENTITY_LOOKUP, entities_mentioned=["Adani"], taxonomy_paths=[])
    retrieval_res = RetrievalResult(intent=intent, graph_facts=[], chunks=[], traversal_paths=[])
    context = AssembledContext(context_text="Mock context text", token_count=10, token_budget=1000, sources=[])
    synthesis = SynthesisOutput(answer="Mock V2 Answer from orchestrator", confidence="high", compliance_note="High confidence", citations=[], structured_rows=[])
    trace = QueryTrace(
        vector_ms=5.0, rerank_ms=2.0, graph_ms=3.0, ner_ms=1.0,
        generation_ms=10.0, assembly_ms=1.0, request_total_ms=22.0,
        input_tokens=100, output_tokens=50, cache_hit=False, cache_kind=None,
        tokens_saved=0, cold_equivalent_tokens=0,
    )

    mock_resp = MagicMock()
    mock_resp.intent = intent
    mock_resp.retrieval = retrieval_res
    mock_resp.context = context
    mock_resp.synthesis = synthesis
    mock_resp.trace = trace
    mock_orch = MagicMock()
    mock_orch.answer = AsyncMock(return_value=mock_resp)
    mock_orch.traditional_search = AsyncMock(return_value=[])
    container.orchestrator = mock_orch

    mock_g = MagicMock()
    mock_g.ping = AsyncMock(return_value=True)
    container.graph = mock_g

    mock_v = MagicMock()
    mock_v.ping = MagicMock(return_value=True)
    mock_v.count = MagicMock(return_value=100)
    mock_v.list_documents = AsyncMock(return_value=["doc1.pdf"])
    container.vector = mock_v

    app = create_app()
    app.dependency_overrides[get_container] = lambda: container
    return app, container


@pytest.mark.asyncio
async def test_v2_active_routing(mock_app):
    """When QUERY_ENGINE='v2', production routes serve from V2 orchestrator."""
    app, container = mock_app
    container.settings.query_engine = "v2"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/query", json={"query": "Test query", "mode": "contextgraph"})
        assert resp.status_code == 200
        assert resp.headers.get("x-serving-engine") == "v2"
        data = resp.json()
        assert data["serving_engine"] == "v2"
        assert container.orchestrator.answer.called


@pytest.mark.asyncio
async def test_hard_rollback_to_legacy(mock_app):
    """When QUERY_ENGINE='legacy', traffic immediately falls back to legacy engine."""
    app, container = mock_app
    container.settings.query_engine = "legacy"

    with patch("app.engine.retrieval.hybrid_graphrag") as mock_hybrid, \
         patch("app.engine.graph_store.get_entity_type_summary", return_value=[]):
        mock_hybrid.return_value = {
            "answer": "Legacy hybrid response",
            "active_labels": [],
            "graph_nodes": [],
            "graph_edges": [],
            "total_time": 0.05,
            "citations": [],
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/query", json={"query": "Test query", "mode": "contextgraph"})
            assert resp.status_code == 200
            assert resp.headers.get("x-serving-engine") == "legacy"
            data = resp.json()
            assert data["serving_engine"] == "legacy"
            assert data["corpus_version"] == "amc_master_legacy"


@pytest.mark.asyncio
async def test_canary_rollback_routing(mock_app):
    """When QUERY_ENGINE='canary', traffic splits according to canary_percentage."""
    app, container = mock_app
    container.settings.query_engine = "canary"
    container.settings.canary_percentage = 100  # 100% routes to v2 canary

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/query", json={"query": "Test canary query", "mode": "contextgraph"})
        assert resp.status_code == 200
        assert "canary-v2 (100%)" in resp.headers.get("x-serving-engine")
        data = resp.json()
        assert data["serving_engine"] == "canary-v2 (100%)"

    # Now test 0% canary routes to legacy
    container.settings.canary_percentage = 0
    with patch("app.engine.retrieval.hybrid_graphrag") as mock_hybrid, \
         patch("app.engine.graph_store.get_entity_type_summary", return_value=[]):
        mock_hybrid.return_value = {
            "answer": "Legacy hybrid response",
            "active_labels": [],
            "graph_nodes": [],
            "graph_edges": [],
            "total_time": 0.05,
            "citations": [],
        }
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/query", json={"query": "Test canary query", "mode": "contextgraph"})
            assert resp.status_code == 200
            assert resp.headers.get("x-serving-engine") == "legacy"
            assert resp.json()["serving_engine"] == "legacy"


@pytest.mark.asyncio
async def test_shadow_mode_execution(mock_app):
    """When QUERY_ENGINE='shadow', legacy serves synchronously while V2 executes in background."""
    app, container = mock_app
    container.settings.query_engine = "shadow"

    with patch("app.engine.retrieval.hybrid_graphrag") as mock_hybrid, \
         patch("app.engine.graph_store.get_entity_type_summary", return_value=[]), \
         patch("app.retrieval.shadow.ShadowRunner.execute_shadow") as mock_shadow:
        mock_hybrid.return_value = {
            "answer": "Legacy answer with shadow",
            "active_labels": [],
            "graph_nodes": [],
            "graph_edges": [],
            "total_time": 0.05,
            "citations": [],
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/query", json={"query": "Test shadow query", "mode": "contextgraph"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["serving_engine"] == "legacy"
            assert mock_shadow.called
