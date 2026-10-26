# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import pytest
import warnings
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.deps import Container, get_container
from app.config import Settings
from app.main import create_app
from app.models.query import QueryIntent, SynthesisOutput, AssembledContext, QueryTrace, RetrievalResult, QueryType


@pytest.fixture
def mock_app():
    container = Container()
    container.settings = Settings(query_engine="v2")
    container.settings.groq_api_key = "gsk_mock_api_key"

    intent = QueryIntent(query_type=QueryType.ENTITY_LOOKUP, entities_mentioned=["SEBI"], taxonomy_paths=[])
    retrieval_res = RetrievalResult(intent=intent, graph_facts=[], chunks=[], traversal_paths=[])
    context = AssembledContext(context_text="Context text", token_count=10, token_budget=1000, sources=[])
    synthesis = SynthesisOutput(
        answer="V2 synthetic response for legacy route",
        confidence="high",
        compliance_note="Grounded in evidence",
        citations=[],
        structured_rows=[],
    )
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

    test_app = create_app()
    test_app.dependency_overrides[get_container] = lambda: container
    return test_app, container


def test_retrieval_module_deprecation_warning():
    """Verify that importing or reloading retrieval.py raises a DeprecationWarning."""
    import importlib
    import app.engine.retrieval as ret
    with pytest.deprecated_call():
        importlib.reload(ret)


@pytest.mark.asyncio
async def test_traditional_endpoint_deprecation_headers_v2(mock_app):
    """Verify that POST /query/traditional returns RFC 8594 deprecation headers and v2 output."""
    test_app, _ = mock_app
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/query/traditional", json={"query": "What is SEBI?"})
        assert resp.status_code == 200
        headers = resp.headers
        assert headers.get("deprecation") == "true"
        assert headers.get("sunset") == "2026-10-22"
        assert 'rel="successor-version"' in headers.get("link", "")
        assert headers.get("x-serving-engine") == "v2"
        data = resp.json()
        assert data["serving_engine"] == "v2"


@pytest.mark.asyncio
async def test_contextgraph_endpoint_deprecation_headers_v2(mock_app):
    """Verify that POST /query/contextgraph returns RFC 8594 deprecation headers and v2 output."""
    test_app, _ = mock_app
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/query/contextgraph", json={"query": "What is SEBI?"})
        assert resp.status_code == 200
        headers = resp.headers
        assert headers.get("deprecation") == "true"
        assert headers.get("sunset") == "2026-10-22"
        assert 'rel="successor-version"' in headers.get("link", "")
        assert headers.get("x-serving-engine") == "v2"
        data = resp.json()
        assert data["serving_engine"] == "v2"


@pytest.mark.asyncio
async def test_legacy_fallback_when_query_engine_is_legacy(mock_app):
    """Verify that if QUERY_ENGINE=legacy, endpoints fall back to the legacy engine."""
    test_app, container = mock_app
    container.settings.query_engine = "legacy"

    mock_legacy_trad = {
        "docs": [],
        "answer": "Legacy traditional answer",
        "retrieve_time": 0.01,
        "llm_time": 0.02,
        "total_time": 0.03,
    }

    with patch("app.api.routes.query._get_store", return_value=MagicMock()), \
         patch("app.engine.retrieval.traditional_rag", return_value=mock_legacy_trad):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/query/traditional", json={"query": "Test legacy"})
            assert resp.status_code == 200
            assert resp.headers.get("deprecation") == "true"
            assert resp.headers.get("x-serving-engine") == "legacy"
            data = resp.json()
            assert data["serving_engine"] == "legacy"
