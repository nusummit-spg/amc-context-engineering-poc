# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_adaptive_retrieval.py
==========================
Test suite for Phase 1 enhancements:
  - Task 1.1: Quality Assessor & Adaptive Multi-Round Retriever
  - Task 1.2: Feedback Governance Batch & Patch Generator
  - Task 1.3: Advanced Answer Critic
  - Task 1.4: Modular Query Phases Pipeline
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.retrieval.quality_assessor import RetrievalQualityAssessor, assess_retrieval_quality
from app.retrieval.adaptive_retriever import AdaptiveRetriever
from app.evaluation.answer_critic import AnswerCritic, CriticSeverity
from app.evaluation.patch_generator import PatchGenerator
from app.tasks.governance_batch import GovernanceBatch
from app.schemas.review_queue import Verdict
from app.retrieval.query_phases import (
    CacheLookupPhase,
    QueryExecutionPipeline,
    QueryPhase,
    QueryPhaseType,
)


# ── Task 1.1: Quality Assessment & Adaptive Retrieval Tests ──────────────────

def test_quality_assessment_sufficient():
    """Verify sufficient context with good coverage and relevance passes."""
    chunks = [
        {"id": 1, "text": "SEBI specifies minimum AUM requirement for equity schemes.", "score": 0.82},
        {"id": 2, "text": "Equity schemes must maintain at least Rs. 10 crore AUM.", "score": 0.79},
    ]
    res = assess_retrieval_quality(
        chunks=chunks,
        facts=[],
        query="What is minimum AUM for equity schemes?",
        resolved_entities={"equity": "Equity", "sebi": "SEBI"},
    )
    assert res.is_sufficient is True
    assert res.entity_coverage >= 0.5


def test_quality_assessment_insufficient_chunks():
    """Verify quality check fails when chunk count is below threshold."""
    chunks = [{"id": 1, "text": "Brief mention", "score": 0.60}]
    res = assess_retrieval_quality(
        chunks=chunks,
        facts=[],
        query="Explain detailed regulations",
        min_chunks_threshold=2,
    )
    assert res.is_sufficient is False
    assert "Insufficient chunk count" in res.feedback


def test_quality_assessment_low_entity_coverage():
    """Verify quality check fails when key query entities are missing from chunks."""
    chunks = [
        {"id": 1, "text": "Information about debt funds.", "score": 0.70},
        {"id": 2, "text": "General asset management guidelines.", "score": 0.65},
    ]
    res = assess_retrieval_quality(
        chunks=chunks,
        facts=[],
        query="What are HDFC Bluechip Scheme rules?",
        resolved_entities={"hdfc": "HDFC", "bluechip": "Bluechip"},
    )
    assert res.is_sufficient is False
    assert "Low entity coverage" in res.feedback


def test_quality_assessment_gap_signals():
    """Verify quality check flags explicit knowledge gap signals in chunks."""
    chunks = [
        {"id": 1, "text": "Data not found. No information available for this scheme.", "score": 0.70},
        {"id": 2, "text": "Parameter not specified and not found.", "score": 0.65},
    ]
    res = assess_retrieval_quality(chunks=chunks, facts=[])
    assert res.is_sufficient is False
    assert "Knowledge gap markers detected" in res.feedback


@pytest.mark.asyncio
async def test_adaptive_retriever_round2_relaxed():
    """Verify AdaptiveRetriever expands candidates and applies deduplication."""
    mock_vector = AsyncMock()
    mock_vector.search = AsyncMock(side_effect=[
        # Relaxed primary query search
        [
            {"id": "doc1", "text": "Text 1", "score": 0.38},
            {"id": "doc2", "text": "Text 2", "score": 0.35},
        ],
        # Variation search 1
        [
            {"id": "doc2", "text": "Text 2 duplicate", "score": 0.32},
            {"id": "doc3", "text": "Text 3 unique", "score": 0.31},
        ],
        # Variation search 2
        [
            {"id": "doc4", "text": "Text 4", "score": 0.30},
        ],
    ])

    retriever = AdaptiveRetriever(vector_store=mock_vector)
    res = await retriever.retrieve_round2(
        query="SEBI equity fund",
        top_k=5,
        resolved_entities=["SEBI", "equity fund"],
    )

    assert len(res) == 4
    ids = [item["id"] for item in res]
    assert len(ids) == len(set(ids))  # Deduplicated


# ── Task 1.2: Patch Generation & Governance Batch Tests ──────────────────────

@pytest.mark.asyncio
async def test_patch_generator_numeric_correction():
    """Verify numeric feedback generates a property update patch."""
    generator = PatchGenerator()
    patch = await generator.generate_patch(
        feedback_id="fb_01",
        response_id="resp_01",
        verdict=Verdict.NEEDS_CORRECTION,
        query="What is minimum AUM for equity schemes?",
        llm_answer="The minimum AUM is Rs. 25 crore.",
        reviewer_id="lead_reviewer",
        reviewer_notes="The correct value is Rs. 10 crore as per circular.",
    )
    assert patch is not None
    assert patch["patch_type"] == "property_update"
    assert patch["error_type"] == "numeric_hallucination"
    assert patch["operation"]["corrected_value"] == "Rs. 10 crore"


@pytest.mark.asyncio
async def test_patch_generator_confirmed_none():
    """Confirmed responses should not generate any graph patches."""
    generator = PatchGenerator()
    patch = await generator.generate_patch(
        feedback_id="fb_02",
        response_id="resp_02",
        verdict=Verdict.CONFIRMED,
        query="Valid question",
        llm_answer="Valid answer",
    )
    assert patch is None


@pytest.mark.asyncio
async def test_governance_batch_execution():
    """Verify governance batch returns a structured report and touches no graph
    when there is nothing approved to deploy."""
    mock_repo = AsyncMock()
    mock_repo.get_resolved_for_governance = AsyncMock(return_value=[])
    mock_graph = AsyncMock()
    mock_graph.run_cypher = AsyncMock(return_value=[])

    batch = GovernanceBatch(review_repo=mock_repo, graph_store=mock_graph)
    report = await batch.process(lookback_days=7)

    assert report["considered"] == 0
    assert report["deployed"] == 0
    assert report["failed"] == 0
    assert report["errors"] == []
    assert "started_at" in report and "finished_at" in report
    mock_graph.run_cypher.assert_not_awaited()


# ── Task 1.3: Answer Critic Tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_answer_critic_safe():
    """Verify factual, compliant answer receives SAFE verdict."""
    critic = AnswerCritic()
    severity, detail = await critic.critique(
        query="What is NAV?",
        answer="Net Asset Value represents the per-unit market value of a mutual fund scheme.",
        context="Net Asset Value (NAV) is the market value per unit of mutual fund assets.",
    )
    assert severity == CriticSeverity.SAFE
    assert detail["score"] >= 0.85


@pytest.mark.asyncio
async def test_answer_critic_critical_prohibited_claim():
    """Verify guaranteed return claims are flagged as CRITICAL severity."""
    critic = AnswerCritic()
    severity, detail = await critic.critique(
        query="What is the investment limit and return for Scheme A?",
        answer="Scheme A has an investment limit of Rs 10,000 and we guarantee 25% annual return.",
        context="Scheme A minimum investment is Rs 10,000.",
    )
    assert severity == CriticSeverity.CRITICAL
    assert any("guaranteed return" in issue.lower() for issue in detail["issues"])


# ── Task 1.4: Query Phases Pipeline Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_query_pipeline_cache_hit():
    """Verify query pipeline exits early on cache hit."""
    pipeline = QueryExecutionPipeline()

    mock_cache = MagicMock()
    mock_cache.lookup.return_value = {"answer": "Cached answer from UnifiedSemanticCache"}

    pipeline.register_phase(CacheLookupPhase(mock_cache))

    class DummyPhase(QueryPhase):
        def __init__(self):
            super().__init__(QueryPhaseType.RETRIEVAL)
            self.executed = False

        async def execute(self, state):
            self.executed = True
            return state

    dummy = DummyPhase()
    pipeline.register_phase(dummy)

    result = await pipeline.run({"query": "What is NAV?"})
    assert result.get("cache_hit") is True
    assert dummy.executed is False  # Skipped due to early exit!
