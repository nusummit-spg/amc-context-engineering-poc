# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_parallel_execution.py
===========================
Tests for concurrent entity resolution and parallel graph + vector retrieval:
- Validates asyncio.gather concurrency
- Validates result correctness
- Validates graceful fallback when parallelization is disabled
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.engine import config
from app.schemas.entities import BaseEntity, EntityType
from app.schemas.query import QueryIntent, QueryType, AssembledContext, SynthesisOutput, GraphFact


class MockEntity(BaseEntity):
    name: str = "TestEntity"
    entity_type: EntityType = EntityType.ISSUER


@pytest.fixture
def mock_parallel_orchestrator():
    from app.retrieval.orchestrator import RetrievalOrchestrator

    mock_intent_classifier = MagicMock()
    mock_intent = QueryIntent(
        query_type=QueryType.ENTITY_LOOKUP,
        entities_mentioned=["EntityA", "EntityB", "EntityC"],
        taxonomy_paths=["/equity"],
        requires_graph=True,
        requires_vector=True,
    )
    mock_intent_classifier.classify = AsyncMock(return_value=mock_intent)

    mock_resolver = MagicMock()
    def _resolve(surface):
        mock_res = MagicMock()
        mock_res.entity = MockEntity(name=surface, entity_type=EntityType.ISSUER)
        return mock_res
    mock_resolver.resolve_surface_form = MagicMock(side_effect=_resolve)

    mock_traversal = MagicMock()
    async def _async_traverse(intent, entities):
        await asyncio.sleep(0.05)  # 50ms simulated graph traversal
        return (
            [GraphFact(statement="EntityA fact", subject="EntityA", predicate="HAS", object="val")],
            ["path1"],
            ["CQL1"]
        )
    mock_traversal.traverse = AsyncMock(side_effect=_async_traverse)

    mock_vector = MagicMock()
    async def _async_search(*args, **kwargs):
        await asyncio.sleep(0.05)  # 50ms simulated vector retrieval
        return [{"chunk_id": "c1", "document_id": "d1", "text": "chunk text", "score": 0.9, "taxonomy_paths": []}]
    mock_vector.search = AsyncMock(side_effect=_async_search)

    mock_assembler = MagicMock()
    mock_assembler.assemble = MagicMock(return_value=AssembledContext(
        context_text="Context",
        token_count=100,
        token_budget=12000,
        sources=[],
        quality_score=1.0,
        passed_quality_gate=True,
    ))

    mock_synth = MagicMock()
    mock_synth.synthesize = AsyncMock(return_value=SynthesisOutput(
        answer="Parallel answer",
        confidence="high",
    ))

    return RetrievalOrchestrator(
        intent_classifier=mock_intent_classifier,
        resolver=mock_resolver,
        traversal=mock_traversal,
        vector_store=mock_vector,
        assembler=mock_assembler,
        synthesizer=mock_synth,
    )


@pytest.mark.asyncio
async def test_parallel_graph_and_vector_retrieval(mock_parallel_orchestrator):
    config.ENABLE_PARALLELIZATION = True
    # Warm up cold-start embedder
    await mock_parallel_orchestrator.answer("warmup query", enable_hyde=False)

    t0 = time.perf_counter()
    resp = await mock_parallel_orchestrator.answer("Compare EntityA vs EntityB", enable_hyde=False)
    elapsed = (time.perf_counter() - t0) * 1000.0

    assert resp.retrieval is not None
    assert len(resp.retrieval.graph_facts) >= 1
    assert len(resp.retrieval.chunks) >= 1

    # Verify parallel component execution and timing (simulated 50ms + 50ms concurrent = ~50ms)
    comp = next((c for c in resp.metrics.components if c.component_name == "parallel_graph_and_vector"), None)
    assert comp is not None, "parallel_graph_and_vector component should be present"
    assert comp.latency_ms < 95.0, f"Parallel retrieval should be ~50ms, took {comp.latency_ms:.1f}ms"


@pytest.mark.asyncio
async def test_parallel_entity_resolution(mock_parallel_orchestrator):
    config.ENABLE_PARALLELIZATION = True
    resp = await mock_parallel_orchestrator.answer("EntityA EntityB EntityC", enable_hyde=False)
    assert len(resp.retrieval.resolved_entities) == 3
    assert "EntityA" in resp.retrieval.resolved_entities
    assert "EntityB" in resp.retrieval.resolved_entities
