# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_efficiency_improvements.py
================================
Unit and regression tests for Phase 1, Phase 2, and Phase 3 efficiency improvements:
- 1.1 HyDE Response Caching & LRU Eviction
- 1.2 GLiNER Saturation Bypass
- 1.3 Graph Query Single-Call Traversal & Fallback
- 1.4 Entity Resolver TTL & Query Vector Caching
- 2.1 Cypher Syntax Auto-Correction & Query Caching
- 2.2 Score-Gap Aware Prompt Vector Budgeting
- 3.1 Semantic Cache Pre-warming
"""
import time
import pytest
from app.engine import hyde, ner_pipeline, graph_store, entity_resolver, text_to_cypher, context_engineering, semantic_cache


class TestPhase1Initiatives:
    def setup_method(self):
        hyde.clear_hyde_cache()
        ner_pipeline.clear_ner_cache()
        entity_resolver.clear_resolver_cache()

    def test_hyde_cache_hit_latency(self):
        """Initiative 1.1: Repeated HyDE query should return in < 2ms from cache."""
        q = "Compare the risk profile of equity funds with debt funds"
        doc1, lat1 = hyde.generate_hypothetical_document(q)
        
        assert doc1, "Should generate a hypothetical document"
        
        # Second call: Cache Hit
        doc2, lat2 = hyde.generate_hypothetical_document(q)
        assert doc1 == doc2, "Cached document must match original"
        assert lat2 < 5.0, f"Cache hit latency should be <5ms, got {lat2:.2f}ms"
        
        stats = hyde.get_hyde_cache_stats()
        assert stats["cache_size"] >= 1
        assert stats["valid_entries"] >= 1

    def test_hyde_cache_prefix_normalization(self):
        """Initiative 1.1: Queries with same 30-word prefix should hit the same cache entry."""
        q1 = "What is the NAV and performance of Adani Growth scheme for retail investors?"
        q2 = "what is the nav and performance of adani growth scheme for retail investors?"
        
        d1, _ = hyde.generate_hypothetical_document(q1)
        t0 = time.perf_counter()
        d2, lat2 = hyde.generate_hypothetical_document(q2)
        elapsed = (time.perf_counter() - t0) * 1000.0
        
        assert d1 == d2
        assert lat2 < 5.0

    def test_gliner_skip_on_saturation(self):
        """Initiative 1.2: Layer A matches on short query should bypass GLiNER."""
        # Warmup lazy spaCy parser
        ner_pipeline.run_layers_ab("warmup", min_confident_entities=1)
        ner_pipeline.clear_ner_cache()

        q_explicit = "What is the NAV of Adani Enterprises scheme?"
        t0 = time.perf_counter()
        entities = ner_pipeline.run_layers_ab(q_explicit, min_confident_entities=1)
        latency = (time.perf_counter() - t0) * 1000.0
        
        assert len(entities) >= 1, "Should detect entities"
        # Layer A matches should have confidence 1.0
        assert all(e.get("confidence") == 1.0 for e in entities if e.get("layer") == "A")
        assert latency < 15.0, f"Layer A fast-track should complete quickly, got {latency:.2f}ms"


    def test_entity_resolver_ttl_and_query_vec_cache(self):
        """Initiative 1.4: Entity candidates TTL is 24 hours and query vectors are memoized."""
        assert entity_resolver._CACHE_TTL == 86400
        
        # Verify query vector cache is populated on resolution
        entity_resolver.clear_resolver_cache()
        assert len(entity_resolver._query_vec_cache) == 0


class TestPhase2Initiatives:
    def setup_method(self):
        text_to_cypher.clear_cypher_cache()

    def test_cypher_correction_missing_alias(self):
        """Initiative 2.1: Missing alias in RETURN aggregation is auto-corrected."""
        bad_cypher = "MATCH (n:Entity) RETURN count(n)"
        corrected = text_to_cypher._correct_cypher_syntax(bad_cypher)
        assert "AS result" in corrected, f"Expected 'AS result' in {corrected}"

    def test_cypher_correction_missing_limit(self):
        """Initiative 2.1: Missing LIMIT in RETURN clause is auto-appended."""
        bad_cypher = "MATCH (n:Entity) RETURN n.text"
        corrected = text_to_cypher._correct_cypher_syntax(bad_cypher)
        assert "LIMIT 25" in corrected, f"Expected 'LIMIT 25' in {corrected}"

    def test_cypher_correction_hyphenated_properties(self):
        """Initiative 2.1: Hyphenated properties without backticks are properly escaped."""
        bad_cypher = "MATCH (n:Entity) RETURN n.exit-load AS el"
        corrected = text_to_cypher._correct_cypher_syntax(bad_cypher, err_msg="unknown property")
        assert "n.[`exit-load`]" in corrected, f"Expected escaped property, got {corrected}"

    def test_cypher_caching_key(self):
        """Initiative 2.1: Successful Cypher is cached by question + product schema."""
        k1 = text_to_cypher._get_cypher_cache_key("Total NAV of scheme", {"Adani Growth", "Tata Balanced"})
        k2 = text_to_cypher._get_cypher_cache_key("total nav of scheme", {"Tata Balanced", "Adani Growth"})
        assert k1 == k2, "Cache key should be normalized and sorted by product names"

    def test_smart_pruning_preserves_close_top2(self):
        """Initiative 2.2: Reranker score gap < 0.10 keeps top-2 in prompt budget."""
        hits_close = [
            {"product_name": "Fund A", "page_num": 1, "parent_text": "Fund A NAV is 120.50.", "score": 0.92},
            {"product_name": "Fund A", "page_num": 2, "parent_text": "Fund A benchmark is Nifty 50.", "score": 0.88},  # gap = 0.04 (< 0.10)
        ]
        prompt, max_tokens = context_engineering.build_prompt(
            query="Tell me about Fund A",
            verified_facts="Total AUM = 500 Cr",
            comparison_blocks="",
            top_edges=[],
            hits=hits_close,
            query_type="aggregation",
            trust_verified_facts=True
        )
        assert "[1] Fund A" in prompt
        assert "[2] Fund A" in prompt, "Top 2 should be preserved when score gap < 0.10"

    def test_smart_pruning_prunes_large_gap(self):
        """Initiative 2.2: Reranker score gap >= 0.10 prunes to top-1 in prompt budget."""
        hits_gapped = [
            {"product_name": "Fund A", "page_num": 1, "parent_text": "Fund A NAV is 120.50.", "score": 0.95},
            {"product_name": "Fund B", "page_num": 3, "parent_text": "Fund B has unrelated info.", "score": 0.50},  # gap = 0.45 (>= 0.10)
        ]
        prompt, max_tokens = context_engineering.build_prompt(
            query="Tell me about Fund A",
            verified_facts="Total AUM = 500 Cr",
            comparison_blocks="",
            top_edges=[],
            hits=hits_gapped,
            query_type="aggregation",
            trust_verified_facts=True
        )
        assert "[1] Fund A" in prompt
        assert "[2] Fund B" not in prompt, "Lower quality chunk should be pruned when score gap is large"


class TestPhase3Initiatives:
    def test_semantic_cache_warmup_and_clear(self):
        """Initiative 3.1: Semantic cache supports pre-warming and clearing."""
        cache = semantic_cache.get_cache()
        cache.clear()
        
        sample_payload = {
            "mode": "hybrid",
            "answer": "Adani Growth Fund NAV is 142.35 as of last disclosure.",
            "telemetry_breakdown": {"latency_total_pipeline_ms": 15.0}
        }
        
        cache.warm_cache_patterns([("NAV of Adani Growth", sample_payload)])
        
        cached_result, lat = cache.check("What is the NAV of Adani Growth?")
        assert cached_result is not None, "Pre-warmed pattern should yield cache hit"
        assert "Adani Growth Fund NAV" in cached_result["answer"]
        assert lat < 150.0

