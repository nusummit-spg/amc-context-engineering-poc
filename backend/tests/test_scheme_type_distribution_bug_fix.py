"""
tests/test_scheme_type_distribution_bug_fix.py
===============================================

Verification tests for the end-to-end bug fix:
  Bug 1: get_top_amcs() now has scheme_type breakdown
  Bug 2: _is_amc_scheme_type_distribution_query() detects distribution queries
  Bug 3: _format_amc_scheme_type_distribution_answer() includes Open/Close/Interval columns

Tests verify the query:
  "What is the distribution of Open Ended vs. Close Ended schemes among the top 5 largest AMCs?"

Should route to: AGGREGATION_AMC_SCHEME_TYPE → _intercept_amc_scheme_type_distribution_query()
And produce a table with Open Ended | Close Ended | Interval Fund columns.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.retrieval.fast_path_interceptor import FastPathInterceptor
from app.services.scheme_aggregation_service import get_aggregation_service


class TestSchemeTypeDistributionDetection:
    """Test Bug Fix #2: Query detection for scheme-type distribution."""
    
    def test_is_amc_scheme_type_distribution_query_basic(self):
        """Test detection of 'distribution of Open/Close Ended among top 5 AMCs' query."""
        interceptor = FastPathInterceptor()
        query_lower = "what is the distribution of open ended vs. close ended schemes among the top 5 largest amcs?".lower()
        
        result = interceptor._is_amc_scheme_type_distribution_query(query_lower)
        assert result is True, "Should detect scheme-type distribution query"
    
    def test_is_amc_scheme_type_distribution_query_breakdown(self):
        """Test detection of 'breakdown of scheme types' query."""
        interceptor = FastPathInterceptor()
        query_lower = "breakdown of scheme types across top 3 fund houses".lower()
        
        result = interceptor._is_amc_scheme_type_distribution_query(query_lower)
        assert result is True, "Should detect scheme-type breakdown query"
    
    def test_is_amc_scheme_type_distribution_query_no_distribution(self):
        """Test that non-distribution AMC queries are NOT detected as scheme-type distribution."""
        interceptor = FastPathInterceptor()
        query_lower = "what are the top 5 largest amcs by aum?".lower()
        
        result = interceptor._is_amc_scheme_type_distribution_query(query_lower)
        assert result is False, "Should NOT detect non-distribution AMC query"
    
    def test_extract_target_attribute_scheme_type_distribution(self):
        """Test routing of scheme-type distribution query to AGGREGATION_AMC_SCHEME_TYPE."""
        interceptor = FastPathInterceptor()
        query = "What is the distribution of Open Ended vs. Close Ended schemes among the top 5 largest AMCs?"
        
        target = interceptor._extract_target_attribute(query)
        assert target == "AGGREGATION_AMC_SCHEME_TYPE", \
            f"Expected AGGREGATION_AMC_SCHEME_TYPE, got {target}"
    
    def test_extract_target_attribute_scheme_type_has_priority(self):
        """Test that scheme-type distribution check happens before generic AMC aggregation."""
        interceptor = FastPathInterceptor()
        # Query mentions both "AMC" and scheme-type distribution
        query = "distribution of Open Ended and Close Ended schemes across top 3 AMCs"
        
        target = interceptor._extract_target_attribute(query)
        # Should route to more specific scheme-type distribution, NOT generic AMC aggregation
        assert target == "AGGREGATION_AMC_SCHEME_TYPE", \
            f"Scheme-type should have priority over generic AMC aggregation. Got: {target}"


class TestSchemeTypeDistributionService:
    """Test Bug Fix #1: Service method for scheme-type breakdown."""
    
    @pytest.fixture
    def service(self):
        """Get aggregation service with test data loaded."""
        return get_aggregation_service()
    
    def test_get_scheme_type_distribution_by_amc_returns_list(self, service):
        """Test that method returns a list of dicts with correct structure."""
        result = service.get_scheme_type_distribution_by_amc(limit=5)
        
        assert isinstance(result, list), "Result should be a list"
        assert len(result) > 0, "Should return at least one AMC"
        assert len(result) <= 5, "Should respect limit parameter"
    
    def test_get_scheme_type_distribution_has_breakdown(self, service):
        """Test that each result dict has scheme_type_breakdown."""
        result = service.get_scheme_type_distribution_by_amc(limit=5)
        
        for row in result:
            assert "scheme_type_breakdown" in row, "Each row must have scheme_type_breakdown"
            assert isinstance(row["scheme_type_breakdown"], dict), \
                "scheme_type_breakdown must be a dict"
            
            # Verify structure of scheme_type_breakdown
            for stype, info in row["scheme_type_breakdown"].items():
                assert "count" in info, f"Missing 'count' in {stype} breakdown"
                assert "pct" in info, f"Missing 'pct' in {stype} breakdown"
                assert isinstance(info["count"], int), f"count should be int, got {type(info['count'])}"
                assert isinstance(info["pct"], (int, float)), f"pct should be numeric"
    
    def test_get_scheme_type_distribution_totals_correct(self, service):
        """Test that percentages sum to 100 for each AMC."""
        result = service.get_scheme_type_distribution_by_amc(limit=5)
        
        for row in result:
            total_pct = sum(info["pct"] for info in row["scheme_type_breakdown"].values())
            # Allow small rounding error (99.9 to 100.1)
            assert 99.5 <= total_pct <= 100.5, \
                f"AMC {row['amc']} percentages sum to {total_pct}%, should be ~100%"
    
    def test_get_scheme_type_distribution_distinct_schemes(self, service):
        """Test that total distinct schemes equals sum of scheme-type counts."""
        result = service.get_scheme_type_distribution_by_amc(limit=5)
        
        for row in result:
            breakdown_sum = sum(info["count"] for info in row["scheme_type_breakdown"].values())
            assert row["total_distinct_schemes"] == breakdown_sum, \
                f"AMC {row['amc']}: total_distinct_schemes ({row['total_distinct_schemes']}) " \
                f"should equal sum of breakdown ({breakdown_sum})"


class TestSchemeTypeDistributionFormatting:
    """Test Bug Fix #3: Response formatting with Open/Close/Interval columns."""
    
    def test_format_amc_scheme_type_distribution_answer_has_columns(self):
        """Test that formatted answer includes scheme-type columns."""
        interceptor = FastPathInterceptor()
        
        # Sample distribution data matching service output
        distribution = [
            {
                "rank": 1,
                "amc": "SBI Funds Management Limited",
                "total_aum_cr": 1260906.03,
                "total_distinct_schemes": 127,
                "scheme_type_breakdown": {
                    "Open Ended": {"count": 109, "pct": 85.8},
                    "Close Ended": {"count": 18, "pct": 14.2},
                },
            },
            {
                "rank": 2,
                "amc": "ICICI Prudential Asset Management",
                "total_aum_cr": 1155055.0,
                "total_distinct_schemes": 150,
                "scheme_type_breakdown": {
                    "Open Ended": {"count": 100, "pct": 66.7},
                    "Close Ended": {"count": 50, "pct": 33.3},
                },
            },
        ]
        
        answer = interceptor._format_amc_scheme_type_distribution_answer(distribution)
        
        # Verify answer is a string
        assert isinstance(answer, str), "Answer should be a string"
        
        # Verify it's markdown with header
        assert "##" in answer, "Should have markdown headers"
        assert "| Rank |" in answer, "Should have table with Rank column"
        assert "Open Ended" in answer, "Should have Open Ended column"
        assert "Close Ended" in answer, "Should have Close Ended column"
        
        # Verify counts are shown
        assert "109" in answer, "Should show open ended count for SBI"
        assert "18" in answer or "14.2" in answer, "Should show close ended count/pct for SBI"
    
    def test_format_includes_percentages(self):
        """Test that formatting includes percentage breakdown."""
        interceptor = FastPathInterceptor()
        
        distribution = [
            {
                "rank": 1,
                "amc": "Test AMC",
                "total_aum_cr": 100.0,
                "total_distinct_schemes": 100,
                "scheme_type_breakdown": {
                    "Open Ended": {"count": 60, "pct": 60.0},
                    "Close Ended": {"count": 40, "pct": 40.0},
                },
            },
        ]
        
        answer = interceptor._format_amc_scheme_type_distribution_answer(distribution)
        
        # Verify percentages are shown
        assert "60.0%" in answer, "Should show Open Ended percentage"
        assert "40.0%" in answer, "Should show Close Ended percentage"
    
    def test_format_handles_interval_fund(self):
        """Test that formatting correctly handles Interval Fund type if present."""
        interceptor = FastPathInterceptor()
        
        distribution = [
            {
                "rank": 1,
                "amc": "Test AMC",
                "total_aum_cr": 100.0,
                "total_distinct_schemes": 110,
                "scheme_type_breakdown": {
                    "Open Ended": {"count": 60, "pct": 54.5},
                    "Close Ended": {"count": 40, "pct": 36.4},
                    "Interval Fund": {"count": 10, "pct": 9.1},
                },
            },
        ]
        
        answer = interceptor._format_amc_scheme_type_distribution_answer(distribution)
        
        # Verify Interval Fund is shown
        assert "Interval Fund" in answer, "Should handle Interval Fund type"
        assert "10" in answer, "Should show Interval Fund count"


class TestSchemeTypeDistributionEndToEnd:
    """End-to-end test for the complete fix."""
    
    def test_query_routes_correctly(self):
        """Test that the full query detection and routing works."""
        interceptor = FastPathInterceptor()
        
        query = "What is the distribution of Open Ended vs. Close Ended schemes among the top 5 largest AMCs?"
        
        # Step 1: Query detection
        target = interceptor._extract_target_attribute(query)
        assert target == "AGGREGATION_AMC_SCHEME_TYPE"
        
        # Step 2: Verify method exists and can be called (async test in integration tests)
        assert hasattr(interceptor, "_intercept_amc_scheme_type_distribution_query"), \
            "Interceptor should have scheme-type distribution handler"
    
    def test_service_and_formatting_integration(self):
        """Test that service output can be formatted correctly."""
        service = get_aggregation_service()
        interceptor = FastPathInterceptor()
        
        # Step 1: Get distribution from service
        distribution = service.get_scheme_type_distribution_by_amc(limit=5)
        
        # Step 2: Format it
        answer = interceptor._format_amc_scheme_type_distribution_answer(distribution)
        
        # Step 3: Verify formatted output has required elements
        assert isinstance(answer, str)
        assert len(answer) > 0
        assert "Open Ended" in answer or "Close Ended" in answer or len(distribution) == 0, \
            "Answer should have scheme-type breakdown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
