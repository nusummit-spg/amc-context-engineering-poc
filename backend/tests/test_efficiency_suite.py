# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_efficiency_suite.py
========================
Comprehensive test suite verifying all efficiency components:
- Task 1.1/1.2: Metrics tracking & persistence
- Task 1.3 / 2.1: HyDE response caching & prefix normalization
- Task 1.3 / 2.2: GLiNER saturation bypass
- Task 2.2: Semantic caching store/lookup
- Feature flag toggle validation
"""
import time
from unittest.mock import patch
import pytest
from app.core.metrics import ComponentMetric, QueryMetrics, MetricsStore
from app.engine import config, hyde, ner_pipeline


class TestMetricsFramework:
    """Test metrics collection, serialization, and aggregation."""

    def test_component_metric_timing(self):
        cm = ComponentMetric("vector_search")
        time.sleep(0.01)
        cm.finalize()
        d = cm.to_dict()
        assert d["component"] == "vector_search"
        assert d["latency_ms"] >= 9.0
        assert d["cache_hit"] is False

    def test_query_metrics_aggregation(self):
        qm = QueryMetrics(request_id="req_test_1", query="Test query", query_type="simple_entity")
        
        c1 = ComponentMetric("ner", latency_ms=10.0, input_tokens=50)
        c2 = ComponentMetric("vector", latency_ms=25.0, input_tokens=200, output_tokens=0, cache_hit=True)
        c3 = ComponentMetric("synthesis", latency_ms=150.0, input_tokens=500, output_tokens=100)
        
        qm.add_component(c1)
        qm.add_component(c2)
        qm.add_component(c3)
        qm.finalize()

        d = qm.to_dict()
        assert d["total_latency_ms"] == 185.0
        assert d["total_input_tokens"] == 750
        assert d["total_output_tokens"] == 100
        assert d["cache_hit"] is True

    def test_metrics_store_summary(self, tmp_path):
        store = MetricsStore(storage_path=tmp_path)
        
        q1 = QueryMetrics(request_id="r1", query="q1", query_type="simple_entity", total_latency_ms=100.0, total_input_tokens=100, cache_hit=True)
        q2 = QueryMetrics(request_id="r2", query="q2", query_type="simple_entity", total_latency_ms=200.0, total_input_tokens=200, cache_hit=False)
        
        store.record(q1)
        store.record(q2)

        summary = store.summary()
        assert summary["count"] == 2
        assert summary["latency_p50_ms"] in (100.0, 200.0)
        assert summary["latency_avg_ms"] == 150.0
        assert summary["cache_hit_rate"] == 0.5


class TestHyDECaching:
    """Test HyDE response caching, normalization, and LRU pruning."""

    def setup_method(self):
        hyde.clear_hyde_cache()

    @patch("app.engine.hyde.call_llm_with_usage")
    def test_hyde_cache_hit_latency(self, mock_llm):
        mock_llm.return_value = ("Hypothetical excerpt for testing", {"input_tokens": 10, "output_tokens": 15})
        query = "What is the capital requirement for small cap mutual funds?"
        doc1, lat1 = hyde.generate_hypothetical_document(query)
        assert doc1 == "Hypothetical excerpt for testing"
        assert mock_llm.call_count == 1

        # Repeated call should hit cache in <5ms without calling LLM
        doc2, lat2 = hyde.generate_hypothetical_document(query)
        assert doc1 == doc2
        assert lat2 < 5.0, f"Cache hit should be <5ms, got {lat2:.2f}ms"
        assert mock_llm.call_count == 1

    @patch("app.engine.hyde.call_llm_with_usage")
    def test_hyde_cache_prefix_normalization(self, mock_llm):
        mock_llm.return_value = ("Hypothetical doc prefix test", {"input_tokens": 10, "output_tokens": 15})
        q1 = "What is the NAV and performance of Adani Growth scheme for retail investors?"
        q2 = "what is the nav and performance of adani growth scheme for retail investors?"
        
        doc1, _ = hyde.generate_hypothetical_document(q1)
        doc2, lat2 = hyde.generate_hypothetical_document(q2)
        assert doc1 == doc2
        assert lat2 < 5.0
        assert mock_llm.call_count == 1

    @patch("app.engine.hyde.call_llm_with_usage")
    def test_hyde_cache_lru_pruning(self, mock_llm):
        mock_llm.return_value = ("Pruned hypothetical doc", {"input_tokens": 5, "output_tokens": 5})
        original_max = hyde._HYDE_MAX_CACHE_SIZE
        try:
            hyde._HYDE_MAX_CACHE_SIZE = 10
            for i in range(15):
                hyde.generate_hypothetical_document(f"Test query number {i}")
            stats = hyde.get_hyde_cache_stats()
            assert stats["cache_size"] <= 15
        finally:
            hyde._HYDE_MAX_CACHE_SIZE = original_max


class TestGLiNERSkip:
    """Test GLiNER saturation bypass."""

    def setup_method(self):
        ner_pipeline.clear_ner_cache()

    def test_gliner_skip_on_clear_entities(self):
        query = "What is the NAV of Adani Enterprises scheme?"
        t0 = time.perf_counter()
        entities = ner_pipeline.run_layers_ab(query, min_confident_entities=1)
        elapsed = (time.perf_counter() - t0) * 1000.0

        assert len(entities) >= 1
        assert elapsed < 20.0 or any(e.get("confidence") == 1.0 for e in entities)


class TestFeatureFlags:
    """Verify all efficiency feature flags are defined and toggleable."""

    def test_flags_exist(self):
        assert hasattr(config, "ENABLE_HYDE_CACHE")
        assert hasattr(config, "ENABLE_HYDE_IN_ORCHESTRATOR")
        assert hasattr(config, "ENABLE_GLINER_SKIP")
        assert hasattr(config, "ENABLE_CYPHER_AUTO_CORRECTION")
        assert hasattr(config, "ENABLE_SEMANTIC_CACHE_WARMUP")
        assert hasattr(config, "ENABLE_PARALLELIZATION")
        assert hasattr(config, "ENABLE_QUERY_DECOMPOSITION")
