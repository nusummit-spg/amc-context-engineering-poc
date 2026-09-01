# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

from unittest.mock import AsyncMock, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.api import deps
from app.config import get_settings
from app.schemas.query import QueryIntent, QueryType, SynthesisOutput


@pytest.fixture
def app():
    settings = get_settings()
    container = deps.init_container()
    
    # Mock LLM calls
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value="Synthesized test answer for categorization rules.")
    
    async def mock_structured(prompt, schema, **kwargs):
        if isinstance(schema, dict) and "query_type" in schema.get("properties", {}):
            return {
                "query_type": "compliance_check",
                "entities_mentioned": ["SEBI"],
                "taxonomy_paths": ["Compliance/Regulatory Circulars/Disclosure/FY26"],
                "requires_graph": True,
                "requires_vector": True,
                "reasoning": "Query about SEBI categorization rules",
            }
        else:
            return {
                "answer": "Under SEBI 2017 circular, large cap schemes must invest at least 80% in large cap stocks.",
                "confidence": "high",
                "compliance_note": "Derived from SEBI 2017 Master Circular",
                "structured_rows": [],
                "citations": [{"source_index": 1, "document_title": "Categorization and Rationalization of Mutual Fund Schemes.pdf"}],
            }

    mock_llm.complete_structured = AsyncMock(side_effect=mock_structured)
    container.llm = mock_llm
    container.orchestrator._intent._llm = mock_llm
    container.orchestrator._synthesizer._llm = mock_llm

    mock_g = MagicMock()
    mock_g.run = AsyncMock(return_value=[])
    mock_g.ping = AsyncMock(return_value=True)
    container.graph = mock_g
    container.orchestrator._traversal._graph = mock_g
    
    return create_app()



@pytest.mark.asyncio
async def test_status_endpoint_data_planes(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "serving_engine" in data
        assert "legacy_index" in data
        assert "modern_index" in data
        assert data["legacy_index"]["parents"] == 386

        resp_dp = await client.get("/api/status/data-planes")
        assert resp_dp.status_code == 200
        dp_data = resp_dp.json()
        assert "query_engines_available" in dp_data
        assert "legacy" in dp_data["query_engines_available"]
        assert "v2" in dp_data["query_engines_available"]


@pytest.mark.asyncio
async def test_query_v2_and_chat_v2_endpoints(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test /api/query/v2
        query_payload = {
            "query": "What are the equity scheme categorization rules under SEBI 2017 circular?",
            "mode": "both",
            "top_k": 3,
        }
        resp = await client.post("/api/query/v2", json=query_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["serving_engine"] == "v2"
        assert data["corpus_version"] == "v2_baseline_20260814"
        assert "trace" in data
        assert data["trace"] is not None
        assert data["trace"]["serving_engine"] == "v2"
        assert "request_total_ms" in data["trace"]

        # Test /api/chat/v2
        chat_payload = {
            "query": "How do those rules classify large cap schemes?",
            "session_id": "test_session_001",
            "history": [
                {"role": "user", "content": "What are the equity scheme categorization rules under SEBI 2017 circular?"},
                {"role": "assistant", "content": "SEBI 2017 mandates specific definitions for large cap, mid cap, and small cap equity schemes."},
            ],
            "mode": "both",
        }
        chat_resp = await client.post("/api/chat/v2", json=chat_payload)
        assert chat_resp.status_code == 200
        chat_data = chat_resp.json()
        assert chat_data["serving_engine"] == "v2"
        assert chat_data["session_id"] == "test_session_001"
        assert chat_data["turn_index"] == 2
        assert "trace" in chat_data
