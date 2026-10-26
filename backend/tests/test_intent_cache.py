# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_intent_cache.py
====================
Comprehensive verification and validation test suite for the Intent Cache.
Tests:
1. Intent & Payload Storage & Disk Persistence (Dual-Gate store).
2. Retrieval on subsequent matching requests (Fingerprint probe & Semantic cosine lookup).
3. Intent Reuse & Performance (<30ms latency, token savings).
4. Refresh & Invalidation (Selective domain invalidation, global clear, /api/admin/cache/clear).
5. Cache-Hit and Cache-Miss behavior (Cold query, duplicate query, unrelated query).
6. Handling of different and similar intents (Domain isolation, query_type gating).
7. Prevention of incorrect or stale data (Date entity guard, TTL expiration, corpus version mismatch).
8. Savings Ledger accounting (Tokens, cost, CO2 tracking).
9. End-to-End Pipeline & API verification.
"""
import os
import sys
import time
import json
import tempfile
import numpy as np
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure sys.path has project directories with backend prioritized
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import intent_cache
except ImportError:
    from streamlit_app import intent_cache

from streamlit_app.intent_cache import (
    IntentAwareCache,
    CacheEntry,
    SavingsLedger,
    classify_domain_intent,
    _extract_date_entities,
    DOMAIN_PATTERNS,
    DOMAIN_TTL,
    CACHE_THRESHOLD_BY_INTENT,
)
from app.engine.semantic_cache import SemanticCache, get_cache as get_engine_cache
from app.retrieval.cache import SemanticQueryCache
from app.api.routes import admin as admin_route


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_cache_dir():
    """Create an isolated temporary directory for disk persistence tests."""
    with tempfile.TemporaryDirectory(prefix="test_intent_cache_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def isolated_intent_cache(temp_cache_dir):
    """Provide an isolated IntentAwareCache instance pointing to a temp disk path."""
    disk_path = str(temp_cache_dir / "intent_cache_store.json")
    cache = IntentAwareCache(shadow_mode=False, disk_path=disk_path)
    cache.clear_all()
    return cache


def _mock_unit_vector(dim: int = 384, seed: int = 42) -> np.ndarray:
    """Generate a reproducible normalized unit embedding vector."""
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-9)


def _slightly_perturbed_vector(base_vec: np.ndarray, similarity: float = 0.98) -> np.ndarray:
    """Generate a vector with guaranteed high cosine similarity to the base vector."""
    dim = len(base_vec)
    rng = np.random.RandomState(99)
    noise = rng.randn(dim).astype(np.float32)
    noise -= np.dot(noise, base_vec) * base_vec
    noise /= (np.linalg.norm(noise) + 1e-9)
    perturbed = similarity * base_vec + np.sqrt(max(0.0, 1.0 - similarity**2)) * noise
    return perturbed.astype(np.float32)


def _orthogonal_vector(dim: int = 384) -> np.ndarray:
    """Generate an unrelated/orthogonal vector for cache-miss tests."""
    rng = np.random.RandomState(777)
    vec = rng.randn(dim).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Intent Classification & Domain Partitioning Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentClassification:
    """Verify that user queries are correctly classified into domain intents."""

    def test_domain_intent_classification(self):
        # sebi_regulation
        assert classify_domain_intent("What is the SEBI circular on categorization?") == "sebi_regulation"
        assert classify_domain_intent("What are PMLA and AML guidelines?") == "sebi_regulation"
        assert classify_domain_intent("Explain the lock-in period for ELSS folio") == "sebi_regulation"

        # esg_sustainability
        assert classify_domain_intent("What are the BRSR decarbonization targets?") == "esg_sustainability"
        assert classify_domain_intent("Tell me about carbon emissions and net zero") == "esg_sustainability"
        assert classify_domain_intent("Renewable energy and climate metrics") == "esg_sustainability"

        # financial_performance
        assert classify_domain_intent("What was the company's EBITDA and revenue in Q3 FY24?") == "financial_performance"
        assert classify_domain_intent("Check debt leverage and credit rating") == "financial_performance"

        # fund_performance
        assert classify_domain_intent("Compare the expense ratio and TER for flexicap fund") == "fund_performance"
        assert classify_domain_intent("What is the exit load for this hybrid scheme benchmarked to Nifty?") == "fund_performance"

        # corporate_governance
        assert classify_domain_intent("Who is the Principal Officer for FIU-IND compliance?") == "corporate_governance"
        assert classify_domain_intent("Review board audit committee and ERP governance") == "corporate_governance"

    def test_default_fallback_domain(self):
        # Neutral query without domain keywords defaults safely to sebi_regulation
        assert classify_domain_intent("Hello, can you help me?") == "sebi_regulation"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Date Entity Extraction & Guard Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDateEntityGuards:
    """Verify regex date extraction and entity guarding to prevent false hits on temporal queries."""

    def test_extract_date_entities(self):
        text = "What was the EBITDA in Q1 FY24 compared to 15 July 2023?"
        dates = _extract_date_entities(text)
        assert any("q1 fy24" in d.lower() or "q1" in d.lower() for d in dates) or len(dates) >= 1
        assert "2023" in dates or any("july" in d.lower() for d in dates)

    def test_date_entity_prevents_stale_or_wrong_quarter_hit(self, isolated_intent_cache):
        cache = isolated_intent_cache
        dim = 384
        vec_q1 = _mock_unit_vector(dim, seed=10)
        # Highly similar embedding for Q2 query
        vec_q2 = _slightly_perturbed_vector(vec_q1, similarity=0.99)

        q1_text = "What was the fund revenue in Q1 FY24?"
        q2_text = "What was the fund revenue in Q2 FY24?"

        cache.store(
            query_vec=vec_q1,
            query_type="direct_lookup",
            domain_intent="financial_performance",
            query_text=q1_text,
            answer="Revenue in Q1 FY24 was 120 Crores INR.",
            provenance=[{"doc": "Quarterly_Financials_Q1.pdf", "page": 3}],
            confidence_label="high confidence",
            confidence_reason="verified",
            total_tokens=1500,
        )

        # 1. Exact Q1 query MUST hit
        hit_q1 = cache.lookup(vec_q1, "direct_lookup", "financial_performance", q1_text)
        assert hit_q1 is not None
        assert "120 Crores" in hit_q1.answer

        # 2. Q2 query MUST MISS despite high vector similarity due to Date Entity Guard!
        hit_q2 = cache.lookup(vec_q2, "direct_lookup", "financial_performance", q2_text)
        assert hit_q2 is None, "Cache should MISS when query dates differ, preventing stale quarter data!"

    def test_fingerprint_probe_date_entity_guard(self, isolated_intent_cache):
        cache = isolated_intent_cache
        vec = _mock_unit_vector(384, seed=12)
        q_text = "What was the dividend yield on 15 March 2024?"

        cache.store(
            query_vec=vec,
            query_type="direct_lookup",
            domain_intent="fund_performance",
            query_text=q_text,
            answer="Dividend yield was 2.4%",
            provenance=[],
            confidence_label="high",
            confidence_reason="verified",
            total_tokens=800,
        )

        # Matching probe
        hit = cache.fingerprint_probe(q_text, query_type="direct_lookup", domain_intent="fund_performance")
        assert hit is not None
        assert hit.answer == "Dividend yield was 2.4%"

        # Different date in probe
        miss = cache.fingerprint_probe("What was the dividend yield on 20 April 2024?", query_type="direct_lookup", domain_intent="fund_performance")
        assert miss is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Storage & Disk Persistence Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheStorageAndPersistence:
    """Verify that entries are properly structured in memory and persisted to disk."""

    def test_store_and_disk_persistence(self, temp_cache_dir):
        disk_path = str(temp_cache_dir / "persisted_cache.json")
        cache1 = IntentAwareCache(shadow_mode=False, disk_path=disk_path)
        cache1.clear_all()

        vec = _mock_unit_vector(384, seed=20)
        query = "What is the borrowing limit for mutual funds?"
        answer = "Under SEBI regulations, an AMC may borrow up to 20% of net assets."
        provenance = [{"doc": "SEBI_Mutual_Funds_1996.pdf", "page": 14}]

        cache1.store(
            query_vec=vec,
            query_type="v2_dual_regime_taxonomy",
            domain_intent="sebi_regulation",
            query_text=query,
            answer=answer,
            provenance=provenance,
            confidence_label="high confidence (verified)",
            confidence_reason="SEBI Regulation 44",
            total_tokens=1850,
            input_tokens_cold=1700,
            output_tokens_cold=150,
            graph_nodes=["Mutual Fund", "Borrowing Limit"],
            graph_edges=[{"s": "Mutual Fund", "rel": "BORROWING_LIMIT", "o": "20%"}],
        )

        # Verify disk file was created and contains valid JSON
        assert os.path.exists(disk_path)
        with open(disk_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "sebi_regulation" in data
        assert len(data["sebi_regulation"]) == 1
        assert data["sebi_regulation"][0]["query_text"] == query
        assert data["sebi_regulation"][0]["total_tokens"] == 1850

        # Instantiate a new Cache from the same disk file (simulating app restart)
        cache2 = IntentAwareCache(shadow_mode=False, disk_path=disk_path)
        stats = cache2.stats()
        assert stats["buckets"]["sebi_regulation"] == 1

        # Lookup on the newly restored cache instance
        hit = cache2.lookup(vec, "v2_dual_regime_taxonomy", "sebi_regulation", query)
        assert hit is not None
        assert hit.answer == answer
        assert hit.total_tokens == 1850
        assert "Borrowing Limit" in hit.graph_nodes


# ─────────────────────────────────────────────────────────────────────────────
# 4. Retrieval, Cache-Hit, and Cache-Miss Behavior Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRetrievalHitMissBehavior:
    """Validate Stage 1 (Fingerprint) & Stage 2 (Semantic Cosine) lookup mechanisms."""

    def test_fingerprint_probe_exact_hit(self, isolated_intent_cache):
        cache = isolated_intent_cache
        vec = _mock_unit_vector(384, seed=30)
        query = "Explain the minimum investment requirement for SIFs"
        answer = "Under SEBI SIF framework, the minimum investment is 10 Lakhs INR."

        cache.store(
            query_vec=vec,
            query_type="v2_dual_regime_taxonomy",
            domain_intent="sebi_regulation",
            query_text=query,
            answer=answer,
            provenance=[],
            confidence_label="high",
            confidence_reason="regulatory",
            total_tokens=1200,
        )

        # Stage 1: Exact probe (case-insensitive and trimmed)
        probe_hit = cache.fingerprint_probe("  explain the minimum investment requirement for sifs  ")
        assert probe_hit is not None
        assert probe_hit.answer == answer
        assert cache.stats()["hits"] == 1

    def test_semantic_lookup_hit_on_paraphrased_query(self, isolated_intent_cache):
        cache = isolated_intent_cache
        dim = 384
        vec1 = _mock_unit_vector(dim, seed=40)
        vec2 = _slightly_perturbed_vector(vec1, similarity=0.98)  # high cosine sim ~0.98

        query1 = "What is the portfolio overlap limit for thematic funds?"
        query2 = "What are the limits on portfolio overlap in thematic and sectoral schemes?"
        answer = "Under 2026 rules, portfolio overlap limit for thematic funds is capped at 50%."

        cache.store(
            query_vec=vec1,
            query_type="v2_dual_regime_taxonomy",
            domain_intent="sebi_regulation",
            query_text=query1,
            answer=answer,
            provenance=[{"doc": "SEBI_Thematic_Overlap_2026.pdf", "page": 5}],
            confidence_label="high confidence",
            confidence_reason="verified rule",
            total_tokens=2100,
        )

        # Query 2 (paraphrase) should hit semantic cache
        hit = cache.lookup(vec2, "v2_dual_regime_taxonomy", "sebi_regulation", query2)
        assert hit is not None
        assert "capped at 50%" in hit.answer
        assert cache.stats()["hits"] == 1

    def test_dissimilar_query_results_in_cache_miss(self, isolated_intent_cache):
        cache = isolated_intent_cache
        dim = 384
        vec1 = _mock_unit_vector(dim, seed=50)
        vec_unrelated = _orthogonal_vector(dim)

        query1 = "What is the lock-in period for ELSS mutual funds?"
        query_unrelated = "How many branches does the AMC operate in Gujarat?"

        cache.store(
            query_vec=vec1,
            query_type="v2_dual_regime_taxonomy",
            domain_intent="sebi_regulation",
            query_text=query1,
            answer="ELSS funds have a mandatory lock-in period of 3 years.",
            provenance=[],
            confidence_label="high",
            confidence_reason="statutory",
            total_tokens=1100,
        )

        # Unrelated query should MISS
        miss = cache.lookup(vec_unrelated, "v2_dual_regime_taxonomy", "sebi_regulation", query_unrelated)
        assert miss is None
        assert cache.stats()["misses"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. Handling of Different vs. Similar Intents (Domain & Type Isolation)
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentAndDomainIsolation:
    """Ensure the cache partitions entries cleanly and prevents cross-domain contamination."""

    def test_domain_isolation_cross_domain_miss(self, isolated_intent_cache):
        cache = isolated_intent_cache
        dim = 384
        # Even with identical vector!
        shared_vec = _mock_unit_vector(dim, seed=60)

        # Store in 'sebi_regulation' domain
        cache.store(
            query_vec=shared_vec,
            query_type="v2_dual_regime_taxonomy",
            domain_intent="sebi_regulation",
            query_text="Audit and governance rules",
            answer="SEBI mandates half-yearly internal audit report submissions.",
            provenance=[],
            confidence_label="high",
            confidence_reason="regulation",
            total_tokens=1400,
        )

        # Lookup in 'corporate_governance' domain bucket MUST MISS
        miss = cache.lookup(shared_vec, "v2_dual_regime_taxonomy", "corporate_governance", "Audit and governance rules")
        assert miss is None, "Cross-domain lookup must not return entries from a different domain bucket!"

        # Lookup in 'sebi_regulation' domain MUST HIT
        hit = cache.lookup(shared_vec, "v2_dual_regime_taxonomy", "sebi_regulation", "Audit and governance rules")
        assert hit is not None

    def test_query_type_isolation(self, isolated_intent_cache):
        cache = isolated_intent_cache
        dim = 384
        vec = _mock_unit_vector(dim, seed=70)
        query = "What is the TER of Scheme A and Scheme B?"

        # Stored as 'direct_lookup'
        cache.store(
            query_vec=vec,
            query_type="direct_lookup",
            domain_intent="fund_performance",
            query_text=query,
            answer="Scheme A TER: 1.25%, Scheme B TER: 1.10%",
            provenance=[],
            confidence_label="high",
            confidence_reason="fact",
            total_tokens=950,
        )

        # Lookup with query_type='comparison' MUST MISS
        miss = cache.lookup(vec, "comparison", "fund_performance", query)
        assert miss is None, "Cache must isolate different query types to prevent structural response mismatches!"

        # Lookup with query_type='direct_lookup' MUST HIT
        hit = cache.lookup(vec, "direct_lookup", "fund_performance", query)
        assert hit is not None


# ─────────────────────────────────────────────────────────────────────────────
# 6. TTL Expiration & Stale Data Prevention Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTTLExpirationAndStaleness:
    """Verify that expired entries are evicted and never returned to the user."""

    def test_expired_entry_is_evicted_on_lookup(self, isolated_intent_cache):
        cache = isolated_intent_cache
        dim = 384
        vec = _mock_unit_vector(dim, seed=80)
        query = "Latest Q3 debt leverage ratio"

        cache.store(
            query_vec=vec,
            query_type="direct_lookup",
            domain_intent="financial_performance",
            query_text=query,
            answer="Debt leverage ratio was 1.8x",
            provenance=[],
            confidence_label="medium",
            confidence_reason="historical",
            total_tokens=900,
        )

        # Verify entry exists
        assert len(cache._entries_by_domain["financial_performance"]) == 1

        # Simulate expiration by rolling back the created_at timestamp past DOMAIN_TTL
        ttl = DOMAIN_TTL["financial_performance"]  # 7 days = 604800s
        cache._entries_by_domain["financial_performance"][0].created_at = time.time() - (ttl + 1000)

        # Lookup must detect expiration, evict entry, and return None
        hit = cache.lookup(vec, "direct_lookup", "financial_performance", query)
        assert hit is None, "Expired entry must NOT be returned!"
        assert len(cache._entries_by_domain["financial_performance"]) == 0, "Expired entry must be pruned from memory!"

    def test_fingerprint_probe_honors_ttl(self, isolated_intent_cache):
        cache = isolated_intent_cache
        vec = _mock_unit_vector(384, seed=85)
        query = "Quick ESG carbon score"

        cache.store(
            query_vec=vec,
            query_type="v2_dual_regime_taxonomy",
            domain_intent="esg_sustainability",
            query_text=query,
            answer="Score is 84/100",
            provenance=[],
            confidence_label="high",
            confidence_reason="BRSR",
            total_tokens=600,
        )

        # Expire the entry
        ttl = DOMAIN_TTL["esg_sustainability"]
        cache._fingerprint_index[hashlib_md5(query)].created_at = time.time() - (ttl + 500)

        # Probe should return None
        hit = cache.fingerprint_probe(query, query_type="v2_dual_regime_taxonomy", domain_intent="esg_sustainability")
        assert hit is None


def hashlib_md5(text: str) -> str:
    import hashlib
    return hashlib.md5(text.lower().strip().encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Invalidation & Refresh Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheInvalidationAndRefresh:
    """Validate selective domain invalidation, full clear, and refresh workflows."""

    def test_selective_domain_invalidation(self, isolated_intent_cache):
        cache = isolated_intent_cache
        vec_sebi = _mock_unit_vector(384, seed=90)
        vec_esg = _mock_unit_vector(384, seed=91)

        cache.store(
            query_vec=vec_sebi,
            query_type="v2_dual_regime_taxonomy",
            domain_intent="sebi_regulation",
            query_text="SEBI scheme categorization rule",
            answer="Categorization rules defined in 2017 circular.",
            provenance=[],
            confidence_label="high",
            confidence_reason="verified",
            total_tokens=1500,
        )

        cache.store(
            query_vec=vec_esg,
            query_type="v2_dual_regime_taxonomy",
            domain_intent="esg_sustainability",
            query_text="BRSR core scope 1 emission norms",
            answer="Scope 1 emissions must be third-party assured.",
            provenance=[],
            confidence_label="high",
            confidence_reason="verified",
            total_tokens=1800,
        )

        assert cache.stats()["buckets"]["sebi_regulation"] == 1
        assert cache.stats()["buckets"]["esg_sustainability"] == 1

        # Invalidate ONLY 'sebi_regulation' (e.g. after reindexing a SEBI circular)
        cache.invalidate_domain("sebi_regulation")

        # SEBI bucket should now be empty
        assert cache.stats()["buckets"]["sebi_regulation"] == 0
        assert cache.lookup(vec_sebi, "v2_dual_regime_taxonomy", "sebi_regulation", "SEBI scheme categorization rule") is None

        # ESG bucket must remain completely intact and functional!
        assert cache.stats()["buckets"]["esg_sustainability"] == 1
        esg_hit = cache.lookup(vec_esg, "v2_dual_regime_taxonomy", "esg_sustainability", "BRSR core scope 1 emission norms")
        assert esg_hit is not None
        assert "Scope 1 emissions" in esg_hit.answer

    def test_clear_all_resets_everything(self, isolated_intent_cache):
        cache = isolated_intent_cache
        vec = _mock_unit_vector(384, seed=95)

        cache.store(
            query_vec=vec,
            query_type="v2_dual_regime_taxonomy",
            domain_intent="fund_performance",
            query_text="Active share of flexicap fund",
            answer="Active share is 72%",
            provenance=[],
            confidence_label="high",
            confidence_reason="fact",
            total_tokens=1000,
        )

        assert cache.stats()["buckets"]["fund_performance"] == 1

        # Clear all
        cache.clear_all()

        stats = cache.stats()
        for domain, count in stats["buckets"].items():
            assert count == 0
        assert len(cache._fingerprint_index) == 0

        # Subsequent lookup must be a MISS
        assert cache.lookup(vec, "v2_dual_regime_taxonomy", "fund_performance", "Active share of flexicap fund") is None


# ─────────────────────────────────────────────────────────────────────────────
# 8. Savings Ledger Accounting Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSavingsLedger:
    """Verify cumulative computation of token, dollar, and carbon savings on cache hits."""

    def test_savings_ledger_recording(self, temp_cache_dir):
        ledger_path = str(temp_cache_dir / "test_savings_ledger.json")
        ledger = SavingsLedger(disk_path=ledger_path)

        assert ledger.summary()["total_hits"] == 0
        assert ledger.summary()["tokens_saved_cumulative"] == 0

        # Record 1 hit saving 2,500 tokens
        ledger.record_hit(tokens_saved=2500, cold_cost_usd=0.0031)

        summary = ledger.summary()
        assert summary["total_hits"] == 1
        assert summary["tokens_saved_cumulative"] == 2500
        assert summary["cost_saved_cumulative_usd"] == 0.0031
        assert summary["co2_saved_grams"] == 0.5  # 2500 * 0.0002

        # Record a miss
        ledger.record_miss()
        summary2 = ledger.summary()
        assert summary2["total_misses"] == 1
        assert summary2["hit_rate_pct"] == 50.0

        # Reload from disk
        ledger2 = SavingsLedger(disk_path=ledger_path)
        assert ledger2.summary()["total_hits"] == 1
        assert ledger2.summary()["tokens_saved_cumulative"] == 2500


# ─────────────────────────────────────────────────────────────────────────────
# 9. API Admin Clear Endpoint & Engine Multi-Layer Invalidation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminCacheClearEndpoint:
    """Verify that /api/admin/cache/clear clears IntentAwareCache, SemanticCache, and RetrievalCache."""

    def test_admin_cache_clear_endpoint(self):
        admin_app = FastAPI()
        admin_app.include_router(admin_route.router, prefix="/api")
        client = TestClient(admin_app)

        # Pre-seed engine semantic cache
        eng_cache = get_engine_cache()
        eng_cache.store("test query for engine cache", {"answer": "cached answer", "telemetry_breakdown": {}})
        assert eng_cache.next_id >= 1

        # Pre-seed global intent cache
        glob_cache = intent_cache.get_cache()
        glob_cache.store(
            query_vec=_mock_unit_vector(384),
            query_type="direct_lookup",
            domain_intent="sebi_regulation",
            query_text="pre-seed query",
            answer="pre-seed answer",
            provenance=[],
            confidence_label="high",
            confidence_reason="seed",
            total_tokens=1000,
        )
        assert glob_cache.stats()["buckets"]["sebi_regulation"] >= 1

        # Call clear endpoint
        res = client.post("/api/admin/cache/clear")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["cleared"] is True
        assert "engine_semantic_cache" in data["cleared_layers"]

        # Verify engine semantic cache is reset
        assert eng_cache.next_id == 0
        assert len(eng_cache.storage) == 0

        # Verify global intent cache is reset
        assert glob_cache.stats()["buckets"]["sebi_regulation"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 10. Engine Semantic Cache (FAISS + SentenceTransformers) Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEngineSemanticCache:
    """Verify app.engine.semantic_cache.SemanticCache FAISS vector search and latency."""

    def test_engine_semantic_cache_hit_and_miss(self):
        cache = SemanticCache(threshold=0.50)
        cache.clear()

        query1 = "What are SEBI guidelines for algos?"
        payload1 = {
            "answer": "SEBI algorithmic trading circular requires order-level audit trails.",
            "total_tokens": 1450,
            "telemetry_breakdown": {"pipeline_mode": "ContextGraph Hybrid RAG"}
        }

        # 1. Cold check -> MISS
        res_cold, lat_cold = cache.check(query1)
        assert res_cold is None
        assert lat_cold < 500.0  # ms

        # 2. Store in cache
        cache.store(query1, payload1)
        assert cache.next_id == 1

        # 3. Exact query -> HIT
        hit, lat_hit = cache.check(query1)
        assert hit is not None
        assert "algorithmic trading circular" in hit["answer"]
        assert lat_hit < 150.0  # rapid retrieval in milliseconds

        # 4. Semantically close query -> HIT
        query_similar = "What are the SEBI rules and guidelines for algorithmic trading?"
        hit_sim, lat_sim = cache.check(query_similar)
        assert hit_sim is not None
        assert "algorithmic trading circular" in hit_sim["answer"]

        # 5. Dissimilar query -> MISS
        query_diff = "What is the corporate social responsibility spending requirement?"
        miss, _ = cache.check(query_diff)
        assert miss is None

        # 6. Clear cache -> Subsequent check MISS
        cache.clear()
        assert cache.next_id == 0
        hit_after_clear, _ = cache.check(query1)
        assert hit_after_clear is None


# ─────────────────────────────────────────────────────────────────────────────
# 11. Retrieval Semantic Query Cache (TTL & Corpus Version Invalidation) Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRetrievalSemanticQueryCache:
    """Verify app.retrieval.cache.SemanticQueryCache corpus version gating and TTL."""

    def test_corpus_version_invalidation_guard(self):
        dim = 384
        cache = SemanticQueryCache(dim=dim, sim_threshold=0.90, ttl_seconds=3600)
        cache.clear()

        vec = _mock_unit_vector(dim, seed=101)
        query = "What is the AMC net worth requirement?"
        response = {"answer": "Minimum net worth is 50 Crores INR."}

        # Store with corpus_version="v1.0"
        cache.store(query=vec, response=response, corpus_version="v1.0")
        assert cache.count() == 1

        # Lookup with matching corpus_version="v1.0" -> HIT
        hit = cache.lookup(query=vec, corpus_version="v1.0")
        assert hit is not None
        assert hit["answer"] == response["answer"]
        assert hit["cache_hit"] is True

        # Lookup with updated corpus_version="v2.0" -> MISS (prevents stale corpus data!)
        miss = cache.lookup(query=vec, corpus_version="v2.0")
        assert miss is None, "Corpus version mismatch must invalidate cache hit to prevent drift!"

        # Invalidate corpus_version "v1.0"
        cache.invalidate(corpus_version="v1.0")
        assert cache.count() == 0
        assert cache.lookup(query=vec, corpus_version="v1.0") is None

    def test_retrieval_cache_ttl_expiration(self):
        dim = 384
        # Short TTL of 1 second
        cache = SemanticQueryCache(dim=dim, sim_threshold=0.90, ttl_seconds=1)
        cache.clear()

        vec = _mock_unit_vector(dim, seed=102)
        cache.store(query=vec, response={"answer": "Temporary data"})

        # Immediate lookup -> HIT
        assert cache.lookup(query=vec) is not None

        # Simulate expiration
        cache._cache_data[0]["timestamp"] = time.time() - 10

        # Post-TTL lookup -> MISS
        assert cache.lookup(query=vec) is None

