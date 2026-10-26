# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_unified_cache.py
======================
Unit tests for UnifiedSemanticCache:
- Lookup & Store
- check() & warm_cache_patterns() compatibility
- Corpus version filtering & invalidation
- TTL expiry
"""
import time
import pytest
from app.retrieval.cache import UnifiedSemanticCache, get_semantic_cache


class TestUnifiedSemanticCache:
    def setup_method(self):
        self.cache = UnifiedSemanticCache(sim_threshold=0.85, ttl_seconds=3600)
        self.cache.clear()

    def test_store_and_lookup_exact(self):
        payload = {"answer": "Adani Growth NAV is 142.35", "confidence": "high"}
        self.cache.store("What is the NAV of Adani Growth?", payload)
        
        hit = self.cache.lookup("What is the NAV of Adani Growth?")
        assert hit is not None
        assert hit["cache_hit"] is True
        assert hit["answer"] == payload["answer"]

    def test_check_api_compatibility(self):
        payload = {"answer": "Tata Balanced scheme details"}
        self.cache.store("Tell me about Tata Balanced scheme", payload)
        
        result, latency_ms = self.cache.check("Tell me about Tata Balanced scheme")
        assert result is not None
        assert latency_ms >= 0.0
        assert result["answer"] == payload["answer"]

    def test_warm_cache_patterns(self):
        patterns = [
            ("Pattern 1 query", {"answer": "Answer 1"}),
            ("Pattern 2 query", {"answer": "Answer 2"}),
        ]
        self.cache.warm_cache_patterns(patterns)
        assert self.cache.count() == 2

        res, _ = self.cache.check("Pattern 1 query")
        assert res is not None
        assert res["answer"] == "Answer 1"

    def test_corpus_invalidation(self):
        self.cache.store("q1", {"answer": "a1"}, corpus_version="v1")
        self.cache.store("q2", {"answer": "a2"}, corpus_version="v2")
        
        assert self.cache.count() == 2
        self.cache.invalidate(corpus_version="v1")
        
        assert self.cache.lookup("q1", corpus_version="v1") is None
        assert self.cache.lookup("q2", corpus_version="v2") is not None

    def test_dual_gate_exact_fingerprint_short_circuit(self):
        payload = {"answer": "Short circuit test answer", "confidence": "high"}
        self.cache.store("Exact match test query", payload)

        class FailingEmbedder:
            def __call__(self, text):
                raise AssertionError("Embedder was called during exact fingerprint hit!")
            def embed(self, texts):
                raise AssertionError("Embedder was called during exact fingerprint hit!")

        # Must succeed via Gate 1 without invoking FailingEmbedder
        hit = self.cache.lookup("Exact match test query", embedder=FailingEmbedder())
        assert hit is not None
        assert hit["cache_hit"] is True
        assert hit.get("cache_kind") == "exact"
        assert hit.get("hit_type") == "Fingerprint"
        assert hit["answer"] == payload["answer"]
