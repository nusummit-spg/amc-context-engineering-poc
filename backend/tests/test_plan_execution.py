# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_plan_execution.py
======================
Covers the wiring that makes the Week 3-6 features actually take effect:
- a complex ExecutionPlan drives one concurrent retrieval branch per sub-query
- corpus-wide aggregations reach the Cypher path with no resolved entities
- the streaming path records metrics and parallelizes like answer() does
- the dual-scope graph query is issued in a single roundtrip
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine import config
from app.schemas.entities import BaseEntity, EntityType
from app.schemas.query import (
    AssembledContext, GraphFact, QueryIntent, QueryType, SynthesisOutput,
)


class MockEntity(BaseEntity):
    name: str = "TestEntity"
    entity_type: EntityType = EntityType.ISSUER


def build_orchestrator(intent: QueryIntent, search_recorder: list):
    from app.retrieval.orchestrator import RetrievalOrchestrator

    classifier = MagicMock()
    classifier.classify = AsyncMock(return_value=intent)

    resolver = MagicMock()

    def _resolve(surface):
        res = MagicMock()
        res.entity = MockEntity(name=surface, entity_type=EntityType.ISSUER)
        return res

    resolver.resolve_surface_form = MagicMock(side_effect=_resolve)

    traversal = MagicMock()
    traversal.traverse = AsyncMock(return_value=(
        [GraphFact(statement="EntityA holds EntityB", subject="EntityA",
                   predicate="HOLDS", object="EntityB")], ["path"], ["CQL"],
    ))

    vector = MagicMock()

    async def _search(query, **kwargs):
        # Assign the id before awaiting: branches run concurrently, so reading
        # the counter after the sleep would give every branch the same id.
        cid = f"chunk_{len(search_recorder) + 1}"
        search_recorder.append({"query": query, "top_k": kwargs.get("top_k")})
        await asyncio.sleep(0.02)
        return [{"chunk_id": cid, "document_id": "d", "text": "t", "score": 0.9, "taxonomy_paths": []}]

    vector.search = AsyncMock(side_effect=_search)

    assembler = MagicMock()
    assembler.assemble = MagicMock(return_value=AssembledContext(
        context_text="ctx", token_count=10, token_budget=12000,
        sources=[], quality_score=1.0, passed_quality_gate=True,
    ))

    synth = MagicMock()
    synth.synthesize = AsyncMock(return_value=SynthesisOutput(answer="answer", confidence="high"))

    return RetrievalOrchestrator(
        intent_classifier=classifier, resolver=resolver, traversal=traversal,
        vector_store=vector, assembler=assembler, synthesizer=synth,
    )


@pytest.fixture(autouse=True)
def isolate_semantic_cache():
    """The semantic cache is a process-wide singleton; without clearing it a
    query answered by one test is served from cache in the next, and the
    assertions silently exercise the cache short-circuit instead."""
    from app.retrieval.cache import get_semantic_cache
    get_semantic_cache().clear()
    yield
    get_semantic_cache().clear()


LOOKUP_INTENT = QueryIntent(
    query_type=QueryType.ENTITY_LOOKUP,
    entities_mentioned=["EntityA", "EntityB"],
    taxonomy_paths=["/equity"],
    requires_graph=True, requires_vector=True,
)


@pytest.mark.asyncio
async def test_complex_plan_fans_out_into_branch_searches():
    """A comparison query must retrieve per-branch, not as one blended query."""
    config.ENABLE_QUERY_DECOMPOSITION = True
    searches: list = []
    orch = build_orchestrator(LOOKUP_INTENT, searches)

    resp = await orch.answer(
        "Compare the risk profile of EntityA versus EntityB across sectors and time",
        enable_hyde=False, enable_decomposition=True,
    )

    assert len(searches) >= 2, (
        f"Complex plan should issue one search per branch, got {len(searches)}: {searches}"
    )
    # Branches must carry the decomposed sub-queries, not the whole query verbatim.
    assert any("EntityA" in s["query"] and "EntityB" not in s["query"] for s in searches)
    # Merged, deduped chunks from every branch.
    assert len({c.chunk_id for c in resp.retrieval.chunks}) == len(resp.retrieval.chunks)
    assert len(resp.retrieval.chunks) >= 2


@pytest.mark.asyncio
async def test_simple_plan_issues_single_search():
    """Simple queries must not pay for fan-out."""
    config.ENABLE_QUERY_DECOMPOSITION = True
    searches: list = []
    orch = build_orchestrator(LOOKUP_INTENT, searches)

    await orch.answer("What is the NAV of EntityA?", enable_hyde=False, enable_decomposition=True)
    assert len(searches) == 1


@pytest.mark.asyncio
async def test_decomposition_disabled_issues_single_search():
    searches: list = []
    orch = build_orchestrator(LOOKUP_INTENT, searches)
    await orch.answer(
        "Compare the risk profile of EntityA versus EntityB across sectors and time",
        enable_hyde=False, enable_decomposition=False,
    )
    assert len(searches) == 1


@pytest.mark.asyncio
async def test_corpus_wide_aggregation_reaches_cypher_without_entities():
    """The Cypher path exists for corpus-wide aggregations, which resolve no
    entities. It must not be skipped for lack of a product scope."""
    config.ENABLE_CYPHER_AUTO_CORRECTION = True
    agg_intent = QueryIntent(
        query_type=QueryType.EXPOSURE_AGGREGATION,
        entities_mentioned=[],           # nothing resolves for a corpus-wide question
        taxonomy_paths=[],
        requires_graph=True, requires_vector=True,
        requires_cypher=True, aggregation_type="sum",
    )
    searches: list = []
    orch = build_orchestrator(agg_intent, searches)

    with patch("app.engine.text_to_cypher.generate_and_run_with_correction") as mock_cypher:
        mock_cypher.return_value = ([{"total_aum": 12345}], {"source": "llm_direct", "cypher": "MATCH ..."})
        resp = await orch.answer("What is the total AUM of all equity schemes?", enable_hyde=False)

    assert mock_cypher.called, "Cypher aggregation must run for corpus-wide aggregations"
    assert mock_cypher.call_args.kwargs["allow_global_scope"] is True
    assert mock_cypher.call_args.kwargs["product_names"] == set()
    assert {"total_aum": 12345} in resp.synthesis.structured_rows


def test_generate_and_run_returns_early_without_scope_by_default():
    """Default behaviour is unchanged for scoped callers."""
    from app.engine import text_to_cypher
    rows, usage = text_to_cypher.generate_and_run_with_correction("q", product_names=set())
    assert rows is None
    assert usage["source"] == "none"


@pytest.mark.asyncio
async def test_stream_records_metrics_and_parallelizes():
    """Streaming is the chat path; it must feed the same metrics store."""
    from app.core.metrics import get_metrics_store

    config.ENABLE_PARALLELIZATION = True
    searches: list = []
    orch = build_orchestrator(LOOKUP_INTENT, searches)
    orch._synthesizer._llm = MagicMock()

    async def _stream(prompt, system=None):
        for word in ["streamed", "answer"]:
            yield word + " "

    orch._synthesizer._llm.complete_stream = _stream

    store = get_metrics_store()
    before = len(store.metrics)

    events = [ev async for ev in orch.answer_stream("What is the NAV of EntityA?", enable_hyde=False)]

    assert any(ev["type"] == "answer_chunk" for ev in events)
    assert any(ev["type"] == "complete" for ev in events)
    assert len(store.metrics) == before + 1, "Streaming path should record one metric"

    recorded = store.metrics[-1]
    assert recorded.query_type == QueryType.ENTITY_LOOKUP.value
    assert recorded.entities_count == 2
    assert recorded.vector_chunks_retrieved >= 1


def test_merged_dual_scope_edges_match_standard_edge_shape():
    """Callers swap between the two graph helpers, so keys must line up."""
    from app.engine import graph_store

    rows = [{
        "s": "EntityA", "s_label": "ISSUER", "s_product": "FundX",
        "rel": "HOLDS", "conf": 0.9, "o": "EntityB", "o_label": "ISSUER",
        "source_priority": 1,
    }]
    with patch.object(graph_store, "run_safe_cypher", return_value=(rows, None)) as mock_run:
        result = graph_store.get_subgraph_with_fallback(
            entity_names=["EntityA"], product_names=["FundX"],
        )

    assert mock_run.call_count == 1, "Dual scope must cost exactly one roundtrip"
    assert result["matched_by"] == "entity"
    assert set(result["edges"][0]) >= {"s", "rel", "o", "conf"}
    assert sorted(result["nodes"]) == ["EntityA", "EntityB"]


def test_merged_dual_scope_empty_scopes():
    from app.engine import graph_store
    result = graph_store.get_subgraph_with_fallback(entity_names=[], product_names=[])
    assert result["edges"] == []
    assert result["matched_by"] == "none"


def test_persisted_metrics_summary_reads_disk(tmp_path):
    """Ops scripts run out-of-process; the disk records are their only view."""
    from app.core.metrics import load_persisted_metrics, summarize_persisted_metrics

    for i, latency in enumerate([100.0, 200.0, 300.0]):
        (tmp_path / f"metrics_2026_{i}.json").write_text(json.dumps({
            "request_id": f"r{i}", "query": "q", "query_type": "general",
            "timestamp": f"2026-09-08T10:0{i}:00", "total_latency_ms": latency,
            "total_input_tokens": 10, "total_output_tokens": 5,
            "cache_hit": i == 0, "citation_accuracy": 1.0, "hallucination_detected": False,
        }), encoding="utf-8")

    assert len(load_persisted_metrics(tmp_path)) == 3
    summary = summarize_persisted_metrics(tmp_path)
    assert summary["count"] == 3
    assert summary["latency_avg_ms"] == 200.0
    assert summary["token_avg"] == 15.0
    assert summary["cache_hit_rate"] == pytest.approx(0.333, abs=0.01)


def test_persisted_metrics_window_filter(tmp_path):
    import os
    from app.core.metrics import load_persisted_metrics

    old = tmp_path / "metrics_old.json"
    old.write_text(json.dumps({"request_id": "old", "total_latency_ms": 1.0}), encoding="utf-8")
    os.utime(old, (time.time() - 7200, time.time() - 7200))

    (tmp_path / "metrics_new.json").write_text(
        json.dumps({"request_id": "new", "total_latency_ms": 1.0}), encoding="utf-8")

    recent = load_persisted_metrics(tmp_path, since_seconds=3600)
    assert [r["request_id"] for r in recent] == ["new"]
