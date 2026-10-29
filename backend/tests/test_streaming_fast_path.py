"""Test streaming fast-path interceptor integration."""
import pytest
import inspect


@pytest.mark.asyncio
async def test_answer_stream_has_fast_path_interceptor():
    """Verify that answer_stream() method has fast-path interceptor code integrated."""
    from app.retrieval.orchestrator import RetrievalOrchestrator
    
    # Get the source code of answer_stream method
    source = inspect.getsource(RetrievalOrchestrator.answer_stream)
    
    # Verify fast-path interceptor is present in answer_stream
    assert "get_fast_path_interceptor" in source, "answer_stream should call get_fast_path_interceptor"
    assert "fast_path.intercept" in source, "answer_stream should call fast_path.intercept()"
    assert "FAST_PATH_INTERCEPTOR_STREAM" in source, "answer_stream should log fast-path interceptor trigger"
    assert "answer_chunk" in source, "answer_stream should stream answer chunks"
    assert "complete" in source, "answer_stream should yield complete event"


@pytest.mark.asyncio  
async def test_aggregation_query_detection():
    """Test that aggregation queries are properly detected in streaming."""
    from app.retrieval.fast_path_interceptor import FastPathInterceptor
    
    interceptor = FastPathInterceptor()
    
    # Test aggregation pattern matching
    test_queries = [
        ("What are the top 10 mutual fund schemes by average AUM?", True),
        ("Show top 5 schemes by AUM", True),
        ("top 20 schemes by average aum", True),
        ("What is the TER of Axis Midcap Fund?", False),
        ("Performance of SBI Small Cap Fund", False),
    ]
    
    for query, should_match in test_queries:
        matches = interceptor._matches_aggregation_pattern(query.lower())
        assert matches == should_match, f"Query '{query}' aggregation detection mismatch"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
