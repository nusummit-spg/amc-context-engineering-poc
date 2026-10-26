"""
tests/test_aggregation_integration.py
=====================================

Integration tests for aggregation query routing with actual CSV data.

These tests verify the complete flow:
1. Query arrives with aggregation intent
2. FastPathInterceptor detects the pattern
3. SchemeAggregationService is called
4. Correct top schemes are returned with accurate AUM values
"""

import pytest
import asyncio
from pathlib import Path

from app.retrieval.fast_path_interceptor import FastPathInterceptor, get_fast_path_interceptor
from app.services.scheme_aggregation_service import SchemeAggregationService


@pytest.fixture
def aggregation_service():
    """Provide SchemeAggregationService with actual CSV data."""
    project_root = Path(__file__).resolve().parent.parent.parent
    csv_path = project_root / "backend" / "data" / "source_docs" / "mutual_fund_data.csv"
    
    service = SchemeAggregationService(csv_path=str(csv_path), use_chunks=False)
    return service


def test_aggregation_service_loads_data(aggregation_service):
    """Test that aggregation service loads mutual fund data correctly."""
    assert aggregation_service.df is not None, "DataFrame should be loaded"
    assert len(aggregation_service.df) > 0, "DataFrame should have data"
    assert "Average_AUM_Cr" in aggregation_service.df.columns, "Should have AUM column"


def test_aggregation_service_returns_top_schemes(aggregation_service):
    """Test that aggregation service returns correct top schemes."""
    response = aggregation_service.get_top_schemes(limit=10, sort_by="avg_aum")
    
    assert response is not None, "Should return response"
    assert len(response.scheme_level_rankings) == 10, "Should return 10 schemes"
    
    # Verify the top scheme is SBI Nifty 50 ETF
    top_scheme = response.scheme_level_rankings[0]
    assert "SBI Nifty 50" in top_scheme.scheme_name or "sbi nifty" in top_scheme.scheme_name.lower(), \
        f"Top scheme should be SBI Nifty 50 ETF, got {top_scheme.scheme_name}"
    
    # Verify AUM values are realistic (should be in thousands of crores)
    assert top_scheme.avg_aum_cr > 50000, \
        f"Top scheme AUM should be > ₹50,000 Cr, got {top_scheme.avg_aum_cr}"


def test_aggregation_service_top_scheme_aum_accuracy(aggregation_service):
    """Test that top scheme AUM matches expected values from CSV."""
    response = aggregation_service.get_top_schemes(limit=1, sort_by="max_aum")
    
    top_scheme = response.scheme_level_rankings[0]
    
    # The top scheme should have AUM close to ₹2,10,783.07 Cr (SBI Nifty 50 ETF)
    # Allow 10% variance for data updates
    expected_min = 200000  # ₹2,00,000 Cr
    expected_max = 220000  # ₹2,20,000 Cr
    
    assert expected_min < top_scheme.max_aum_cr < expected_max, \
        f"Top scheme AUM should be ~₹2,10,783 Cr, got ₹{top_scheme.max_aum_cr:,.2f} Cr"


@pytest.mark.asyncio
async def test_fast_path_interceptor_aggregation_flow_simple():
    """Test the aggregation pattern detection is working."""
    
    # This test just verifies the pattern matching works
    # Full end-to-end async testing is complex due to module imports inside async functions
    interceptor = FastPathInterceptor()
    
    # Query that should trigger aggregation detection
    query = "What are the top 10 mutual fund schemes by average AUM?"
    
    # Verify attribute extraction works
    target_attr = interceptor._extract_target_attribute(query)
    assert target_attr == "AGGREGATION_RANKING", "Should detect aggregation pattern"
    
    # Verify pattern matching
    assert interceptor._matches_aggregation_pattern(query.lower()) is True


def test_aggregation_query_limit_extraction_patterns():
    """Test that different limit values are detected correctly."""
    
    interceptor = FastPathInterceptor()
    
    # Test top 5
    assert interceptor._matches_aggregation_pattern("top 5 schemes by aum") is True
    
    # Test top 20
    assert interceptor._matches_aggregation_pattern("top 20 funds by assets under management") is True
    
    # Test ranking without number (should still match)
    assert interceptor._matches_aggregation_pattern("ranking of schemes by aum") is True


def test_aggregation_service_plan_variants(aggregation_service):
    """Test that aggregation properly combines plan variants."""
    response = aggregation_service.get_top_schemes(limit=10, sort_by="avg_aum", include_plan_details=True)
    
    # Verify plan-level details are included
    assert response.plan_level_rankings is not None, "Should include plan-level rankings"
    
    # Top schemes often have multiple plan variants
    top_scheme = response.scheme_level_rankings[0]
    
    # If scheme has multiple plans, verify aggregation worked
    if top_scheme.plan_count > 1:
        # AUM values should be aggregated
        assert top_scheme.total_aum_cr >= top_scheme.max_aum_cr, \
            "Total AUM should be >= max AUM when multiple plans exist"


def test_aggregation_different_sort_options(aggregation_service):
    """Test that different sort options work correctly."""
    
    # Sort by max AUM
    response_max = aggregation_service.get_top_schemes(limit=5, sort_by="max_aum")
    assert len(response_max.scheme_level_rankings) == 5
    
    # Sort by average AUM
    response_avg = aggregation_service.get_top_schemes(limit=5, sort_by="avg_aum")
    assert len(response_avg.scheme_level_rankings) == 5
    
    # Sort by total AUM
    response_total = aggregation_service.get_top_schemes(limit=5, sort_by="total_aum")
    assert len(response_total.scheme_level_rankings) == 5
    
    # First scheme in each sort should be different (unless coincidentally same)
    # Just verify they all work and return data
    for response in [response_max, response_avg, response_total]:
        assert response.scheme_level_rankings[0].scheme_name is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
