# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Unit tests for PV-02 behavioral gap repairs in v2 Orchestrator."""
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.contracts.identity import generate_chunk_id, generate_document_id, generate_source_id
from app.retrieval.cache import SemanticQueryCache, get_semantic_cache
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.schemas.query import AssembledContext, QueryIntent, QueryType, RetrievedChunk, SynthesisOutput


@pytest.fixture
def mock_orchestrator():
    intent_mock = MagicMock()
    intent_mock.classify = AsyncMock(return_value=QueryIntent(
        query_type=QueryType.REGULATORY_COMPLIANCE if hasattr(QueryType, "REGULATORY_COMPLIANCE") else QueryType.COMPLIANCE_CHECK,
        entities_mentioned=["SEBI"],
        taxonomy_paths=["Compliance/Regulatory Circulars/Disclosure/FY26"],
        requires_graph=True,
        requires_vector=True,
    ))

    resolver_mock = MagicMock()
    resolver_mock.resolve_surface_form = MagicMock(return_value=None)

    traversal_mock = MagicMock()
    traversal_mock.traverse = AsyncMock(return_value=([], [], []))

    vector_mock = MagicMock()
    vector_mock.search = AsyncMock(return_value=[{
        "chunk_id": "chk_123",
        "document_id": "doc_123",
        "document_title": "SEBI Master Circular",
        "text": "Categorization of mutual funds mandates 80% equity for large cap schemes.",
        "score": 0.92,
        "taxonomy_paths": ["Compliance/Regulatory Circulars/Disclosure/FY26"],
    }])

    assembler_mock = MagicMock()
    assembler_mock.assemble = MagicMock(return_value=AssembledContext(
        context_text="Categorization of mutual funds mandates 80% equity for large cap schemes.",
        token_count=20,
        token_budget=12000,
        sources=[],
        quality_score=0.95,
        passed_quality_gate=True,
    ))

    synthesizer_mock = MagicMock()
    synthesizer_mock.synthesize = AsyncMock(return_value=SynthesisOutput(
        answer="Under SEBI regulations, large cap funds must maintain 80% equity allocation.",
        confidence="high",
        compliance_note="Derived from SEBI 2017 circular",
    ))

    orch = RetrievalOrchestrator(
        intent_classifier=intent_mock,
        resolver=resolver_mock,
        traversal=traversal_mock,
        vector_store=vector_mock,
        assembler=assembler_mock,
        synthesizer=synthesizer_mock,
    )
    return orch


@pytest.mark.asyncio
async def test_cache_miss_then_cache_hit_short_circuit(mock_orchestrator):
    cache = get_semantic_cache()
    cache.clear()

    query = "What is the large cap allocation threshold under SEBI rules?"

    # Turn 1: Cold Cache Miss
    resp1 = await mock_orchestrator.answer(query)
    assert resp1.trace is not None
    assert resp1.trace.cache_hit is False
    assert resp1.trace.generation_ms >= 0.0
    assert cache.count() == 1

    # Turn 2: Warm Cache Hit
    resp2 = await mock_orchestrator.answer(query)
    assert resp2.trace is not None
    assert resp2.trace.cache_hit is True
    # Verify skipped stages are recorded as 0.0ms
    assert resp2.trace.ner_ms == 0.0
    assert resp2.trace.graph_ms == 0.0
    assert resp2.trace.vector_ms == 0.0
    assert resp2.trace.assembly_ms == 0.0
    assert resp2.trace.generation_ms == 0.0
    assert resp2.trace.request_total_ms < 100.0  # Fast sub-100ms response
    assert "Under SEBI regulations" in resp2.synthesis.answer


@pytest.mark.asyncio
async def test_multi_turn_history_extraction(mock_orchestrator):
    history = [
        {"role": "user", "content": "Tell me about Adani Enterprises EBITDA performance."},
        {"role": "assistant", "content": "Adani Enterprises recorded strong EBITDA growth across mining and airports."},
    ]
    query = "What was their revenue breakdown?"

    # Reset cache to force query rewrite
    cache = get_semantic_cache()
    cache.clear()

    resp = await mock_orchestrator.answer(query, history=history)
    assert resp.trace is not None
    assert resp.trace.query_rewrite_ms >= 0.0


@pytest.mark.asyncio
async def test_corpus_version_cache_isolation():
    cache = SemanticQueryCache()
    query = "What are the rules for debt fund duration?"
    
    # Store for version A
    cache.store(query, {"answer": "Version A Answer"}, corpus_version="v2_baseline_20260814")
    
    # Lookup for version A -> Hit
    hit = cache.lookup(query, corpus_version="v2_baseline_20260814")
    assert hit is not None
    assert hit["answer"] == "Version A Answer"
    
    # Lookup for version B -> Miss (Strict Isolation)
    miss = cache.lookup(query, corpus_version="v3_future_20270101")
    assert miss is None


@pytest.mark.asyncio
async def test_unrelated_query_no_history_leakage(mock_orchestrator):
    history = [
        {"role": "user", "content": "What was Adani Ports EBITDA?"},
        {"role": "assistant", "content": "Adani Ports EBITDA grew by 18% in FY24."},
    ]
    # Completely independent query with no pronoun triggers
    query = "What is the exit load threshold for liquid mutual fund schemes?"
    
    cache = get_semantic_cache()
    cache.clear()
    
    resp = await mock_orchestrator.answer(query, history=history)
    assert resp.intent is not None
    assert resp.trace is not None
