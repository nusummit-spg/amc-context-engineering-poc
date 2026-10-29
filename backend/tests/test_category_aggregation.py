"""
tests/test_category_aggregation.py
==================================
Unit and integration tests for mutual fund category aggregation,
deterministic fast-path interception, Layer 2 tabular fallback,
and Layer 3 grounding guardrail.
"""

import pytest
import asyncio
from app.services.scheme_aggregation_service import SchemeAggregationService
from app.retrieval.fast_path_interceptor import FastPathInterceptor
from app.models.query import SynthesisOutput
from app.retrieval.orchestrator import RetrievalOrchestrator


@pytest.fixture(scope="module")
def aggregation_service():
    """Shared service instance loaded once for tests."""
    return SchemeAggregationService()


def test_category_breakdown_metrics(aggregation_service):
    """Test category breakdown against ground-truth CSV."""
    res = aggregation_service.get_category_aum_breakdown()
    
    # 1. Total market AUM should match ~82.85 Lakh Crores
    assert res.total_market_aum_cr > 8_000_000, f"Expected > 80 Lakh Cr, got {res.total_market_aum_cr}"
    assert res.total_distinct_schemes > 3_000, f"Expected > 3000 distinct schemes, got {res.total_distinct_schemes}"
    assert res.total_folios == 16245, f"Expected 16,245 folios, got {res.total_folios}"
    
    # 2. Check top categories
    categories = res.categories
    assert len(categories) > 5
    
    # Equity should be Rank 1
    assert categories[0].rank == 1
    assert categories[0].category == "Equity Schemes"
    assert categories[0].total_aum_cr > 3_000_000  # Over 30 Lakh Crores
    assert categories[0].distinct_schemes > 500
    assert categories[0].pct_of_total_aum > 40.0
    
    # Debt should be Rank 2
    assert categories[1].rank == 2
    assert categories[1].category == "Debt Schemes"
    assert categories[1].total_aum_cr > 1_500_000
    
    # 3. Sum of percentages should roughly equal 100%
    total_pct = sum(c.pct_of_total_aum for c in categories)
    assert 99.0 <= total_pct <= 100.5


def test_detailed_category_breakdown(aggregation_service):
    """Test detailed SEBI category breakdown."""
    res = aggregation_service.get_category_aum_breakdown(detailed=True)
    assert len(res.categories) > 20
    # Make sure Large Cap, Mid Cap, Liquid etc. are present
    cat_names = [c.category for c in res.categories]
    assert any("Large Cap" in name for name in cat_names)
    assert any("Liquid" in name for name in cat_names)


@pytest.mark.asyncio
async def test_fast_path_category_interception():
    """Test deterministic fast-path interception of category breakdown queries."""
    interceptor = FastPathInterceptor()
    queries = [
        "What is the breakdown of total AUM and number of schemes across different mutual fund categories?",
        "Show me total AUM across mutual fund categories",
        "Which mutual fund categories have the highest AUM?",
        "Distribution of schemes and AUM by category",
    ]
    for q in queries:
        target_attr = interceptor._extract_target_attribute(q)
        assert target_attr == "AGGREGATION_CATEGORY", f"Failed to detect AGGREGATION_CATEGORY for query: {q}"
        resp = await interceptor.intercept(q)
        assert resp is not None, f"Fast-path failed to intercept query: {q}"
        assert resp.synthesis is not None
        assert "Equity Schemes" in resp.synthesis.answer
        assert len(resp.synthesis.structured_rows) >= 5
        assert resp.synthesis.confidence == "high"


def test_orchestrator_layer2_tabular_fallback():
    """Test Layer 2 tabular fallback in RetrievalOrchestrator."""
    orchestrator = object.__new__(RetrievalOrchestrator)
    query = "What is the breakdown of total AUM and number of schemes across different mutual fund categories?"
    facts, rows = orchestrator._populate_tabular_aggregation_facts(query)
    
    assert len(facts) >= 5
    assert len(rows) >= 5
    assert rows[0]["category"] == "Equity Schemes"
    assert "₹3,517,433.31 Cr" in rows[0]["total_aum_cr"]
    assert facts[0].predicate == "HAS_CATEGORY_AUM"


def test_orchestrator_layer3_guardrail_enforcement():
    """Test Layer 3 grounding guardrail overrides hallucinated LLM responses."""
    orchestrator = object.__new__(RetrievalOrchestrator)
    query = "What is the breakdown of total AUM and number of schemes across different mutual fund categories?"
    facts, rows = orchestrator._populate_tabular_aggregation_facts(query)
    
    hallucinated_synth = SynthesisOutput(
        answer="The only mutual-fund category present in the supplied structured facts is Income. Eight distinct schemes are identified. No AUM figures are included.",
        confidence="medium",
        citations=[],
        provenance=[],
    )
    
    enforced_synth, overridden = orchestrator._enforce_aggregation_guardrail(
        query=query,
        synthesis=hallucinated_synth,
        rows=rows,
        critic_escalated=False,
    )
    
    assert overridden is True
    assert "Equity Schemes" in enforced_synth.answer
    assert "Debt Schemes" in enforced_synth.answer
    assert enforced_synth.confidence == "high"
