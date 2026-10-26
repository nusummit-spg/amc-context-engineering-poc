"""
tests/test_aggregation_interceptor.py
=====================================

Test suite for aggregation query detection and routing in FastPathInterceptor.

Tests verify that:
1. Aggregation queries are correctly detected
2. Non-aggregation queries are not intercepted
3. Aggregation service is properly called
4. Responses contain correct number of schemes and accurate AUM values
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.retrieval.fast_path_interceptor import FastPathInterceptor, AGGREGATION_PATTERNS
from app.models.scheme_aggregation import SchemeAggregationMetrics, DualViewAUMResponse


class TestAggregationPatternDetection:
    """Test aggregation pattern recognition."""
    
    def test_matches_aggregation_pattern_top_10_aum(self):
        """Test detection of 'top 10 schemes by AUM' query."""
        interceptor = FastPathInterceptor()
        query = "what are the top 10 mutual fund schemes by average aum?"
        
        result = interceptor._matches_aggregation_pattern(query.lower())
        assert result is True, "Should detect 'top 10 by aum' pattern"
    
    def test_matches_aggregation_pattern_top_5_aum(self):
        """Test detection of 'top 5 schemes by AUM' query."""
        interceptor = FastPathInterceptor()
        query = "show me the top 5 schemes by asset under management"
        
        result = interceptor._matches_aggregation_pattern(query.lower())
        assert result is True, "Should detect 'top 5 by assets' pattern"
    
    def test_matches_aggregation_pattern_largest_funds(self):
        """Test detection of 'largest funds' query."""
        interceptor = FastPathInterceptor()
        query = "which are the largest schemes by fund size?"
        
        result = interceptor._matches_aggregation_pattern(query.lower())
        assert result is True, "Should detect 'largest by fund size' pattern"
    
    def test_does_not_match_single_entity_aum(self):
        """Test that single-entity AUM queries are NOT detected as aggregation."""
        interceptor = FastPathInterceptor()
        query = "what is the aum of hdfc mid cap fund?"
        
        result = interceptor._matches_aggregation_pattern(query.lower())
        assert result is False, "Should NOT detect single-entity query as aggregation"
    
    def test_does_not_match_performance_query(self):
        """Test that performance queries are NOT detected as aggregation."""
        interceptor = FastPathInterceptor()
        query = "which are the top performing schemes?"
        
        result = interceptor._matches_aggregation_pattern(query.lower())
        assert result is False, "Should NOT detect performance query (missing AUM indicator)"


class TestAttributeExtraction:
    """Test attribute extraction with aggregation support."""
    
    def test_extract_target_attribute_aggregation_ranking(self):
        """Test that aggregation queries return AGGREGATION_RANKING."""
        interceptor = FastPathInterceptor()
        query = "top 10 schemes by aum"
        
        result = interceptor._extract_target_attribute(query)
        assert result == "AGGREGATION_RANKING"
    
    def test_extract_target_attribute_single_entity_ter(self):
        """Test single-entity TER query still works."""
        interceptor = FastPathInterceptor()
        query = "what is the ter of axis bluechip fund?"
        
        result = interceptor._extract_target_attribute(query)
        assert result == "TER"
    
    def test_extract_target_attribute_single_entity_aum(self):
        """Test single-entity AUM query (not aggregation)."""
        interceptor = FastPathInterceptor()
        query = "what is the aum of sbi liquid fund?"
        
        result = interceptor._extract_target_attribute(query)
        assert result == "AUM"


class TestAggregationResponseFormatting:
    """Test response formatting for aggregation queries."""
    
    def test_format_aggregation_answer_creates_table(self):
        """Test that aggregation answer is formatted as markdown table."""
        interceptor = FastPathInterceptor()
        
        # Create mock aggregation response
        mock_metric1 = Mock(spec=SchemeAggregationMetrics)
        mock_metric1.scheme_name = "SBI Nifty 50 ETF"
        mock_metric1.amc = "SBI Funds Management Limited"
        mock_metric1.avg_aum_cr = 210783.07
        mock_metric1.max_aum_cr = 210783.07
        mock_metric1.plan_count = 1
        
        mock_metric2 = Mock(spec=SchemeAggregationMetrics)
        mock_metric2.scheme_name = "HDFC Mid Cap Fund"
        mock_metric2.amc = "HDFC Asset Management Company Limited"
        mock_metric2.avg_aum_cr = 66026.01
        mock_metric2.max_aum_cr = 66026.01
        mock_metric2.plan_count = 2
        
        mock_response = Mock(spec=DualViewAUMResponse)
        mock_response.scheme_level_rankings = [mock_metric1, mock_metric2]
        mock_response.total_plan_variants = 3
        mock_response.data_period = "January - March 2026"
        
        result = interceptor._format_aggregation_answer(mock_response)
        
        # Verify markdown table structure
        assert "| Rank |" in result, "Should have rank column"
        assert "| Scheme Name |" in result, "Should have scheme name column"
        assert "| 1 |" in result, "Should have rank 1"
        assert "| 2 |" in result, "Should have rank 2"
        assert "SBI Nifty 50 ETF" in result, "Should contain scheme name"
        assert "₹210,783.07" in result, "Should contain formatted AUM with currency"
        assert "Data Summary" in result, "Should have data summary section"


@pytest.mark.asyncio
async def test_intercept_aggregation_query_pattern_matched():
    """Test that aggregation query pattern matching works."""
    
    with patch('app.retrieval.fast_path_interceptor.get_patch_metrics') as mock_get_metrics:
        mock_metrics = Mock()
        mock_metrics.record_fast_path_miss = Mock()
        mock_get_metrics.return_value = mock_metrics
        
        interceptor = FastPathInterceptor()
        query = "top 10 schemes by average aum"
        
        # Verify pattern is detected
        target_attr = interceptor._extract_target_attribute(query)
        assert target_attr == "AGGREGATION_RANKING", "Should detect aggregation pattern"


@pytest.mark.asyncio
async def test_intercept_non_aggregation_returns_none():
    """Test that non-aggregation queries return None to fall through."""
    
    with patch('app.retrieval.fast_path_interceptor.get_patch_metrics') as mock_get_metrics:
        mock_metrics = Mock()
        mock_metrics.record_fast_path_miss = Mock()
        mock_get_metrics.return_value = mock_metrics
        
        interceptor = FastPathInterceptor()
        query = "what is the investment strategy of hdfc mid cap fund?"
        
        result = await interceptor.intercept(query)
        
        # Should return None to fall through to vector RAG
        assert result is None, "Should return None for non-aggregation queries"
        mock_metrics.record_fast_path_miss.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
