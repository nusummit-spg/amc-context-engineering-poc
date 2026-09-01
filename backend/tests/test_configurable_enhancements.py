# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Unit tests for configurable enhancements:
1. Multi-provider LLM with disabled-by-default fallbacks
2. Pre-retrieval safety guardrails
3. Event-driven cache invalidation on ingestion
4. Canary traffic routing
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.config import Settings
from app.core.llm import LLMClient
from app.retrieval.cache import SemanticQueryCache
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.schemas.api import QueryRequest


@pytest.mark.asyncio
async def test_multi_provider_llm_disabled_fallback_by_default():
    """Verify that when primary provider (Groq) fails, fallbacks are NOT called if enable_multi_provider_fallback=False."""
    settings = Settings(
        llm_provider="groq",
        enable_multi_provider_fallback=False,
        enable_local_llm_fallback=False,
    )
    with patch("app.core.llm.get_settings", return_value=settings):
        client = LLMClient()
        client._call_groq = AsyncMock(side_effect=RuntimeError("Groq 401 Unauthorized"))
        client._call_openai = AsyncMock(return_value="OpenAI response")
        client._call_local_llm = AsyncMock(return_value="Local response")

        with pytest.raises(RuntimeError, match="Groq 401 Unauthorized"):
            await client.complete("test prompt")

        # Assert fallbacks were NOT called
        client._call_openai.assert_not_called()
        client._call_local_llm.assert_not_called()


@pytest.mark.asyncio
async def test_multi_provider_llm_enabled_fallback_when_configured():
    """Verify that fallback to secondary provider executes when explicitly enabled."""
    settings = Settings(
        llm_provider="groq",
        enable_multi_provider_fallback=True,
        enable_local_llm_fallback=False,
    )
    with patch("app.core.llm.get_settings", return_value=settings):
        client = LLMClient()
        client._call_groq = AsyncMock(side_effect=RuntimeError("Groq 401 Unauthorized"))
        client._call_openai = AsyncMock(return_value="OpenAI synthesis result")
        client._call_local_llm = AsyncMock(return_value="Local response")

        result = await client.complete("test prompt")
        assert result == "OpenAI synthesis result"
        client._call_openai.assert_called_once()
        client._call_local_llm.assert_not_called()


@pytest.mark.asyncio
async def test_pre_retrieval_safety_guardrail_interceptor():
    """Verify that guaranteed return queries are short-circuited with statutory refusal."""
    orchestrator = RetrievalOrchestrator(
        intent_classifier=MagicMock(),
        resolver=MagicMock(),
        traversal=MagicMock(),
        vector_store=MagicMock(),
        assembler=MagicMock(),
        synthesizer=MagicMock(),
    )
    
    resp = await orchestrator.answer("Can you promise a guaranteed 15% annual return on equity funds?")
    assert resp.synthesis is not None
    assert "cannot guarantee returns" in resp.synthesis.answer.lower()
    assert resp.trace is not None
    assert resp.trace.serving_engine == "v2"
    assert resp.trace.quality_gate_passed is True


def test_event_driven_cache_invalidation():
    """Verify that cache.invalidate() purges only the target corpus version entries."""
    cache = SemanticQueryCache(dim=384)
    
    # Store entries for two different corpus versions
    cache.store("query v2", {"answer": "Answer for v2"}, corpus_version="v2_baseline")
    cache.store("query v3", {"answer": "Answer for v3"}, corpus_version="v3_experimental")
    
    assert cache.count() == 2
    
    # Invalidate only v2_baseline
    cache.invalidate(corpus_version="v2_baseline")
    
    # Check that v3 is retained and v2 is purged
    hit_v2 = cache.lookup("query v2", corpus_version="v2_baseline")
    hit_v3 = cache.lookup("query v3", corpus_version="v3_experimental")
    
    assert hit_v2 is None
    assert hit_v3 is not None
    assert hit_v3.get("answer") == "Answer for v3"
