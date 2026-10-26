# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
# ===========================================================================

"""Security tests for Phase 4: Cache Isolation & State Management.

Verifies:
1. Cache key generation enforces mandatory user_id and tenant scoping.
2. User isolation across cache keys prevents cross-user collisions.
3. Invalidation functions safely target only the specified user's data.
4. UserScopedRedisCache enforces boundary isolation.
5. text_to_cypher, entity_resolver, hyde, intent_cache, and SemanticQueryCache
   strictly isolate cached responses between users.
"""
import pytest
import numpy as np

from app.core.cache_utils import generate_cache_key, invalidate_user_cache
from app.core.redis_client import UserScopedRedisCache
from app.engine import text_to_cypher, entity_resolver, hyde
from app.engine.intent_cache import IntentAwareCache, CacheEntry
from app.retrieval.cache import SemanticQueryCache


def test_generate_cache_key_requires_user_id():
    """Verify generate_cache_key raises ValueError when user_id is empty or missing."""
    with pytest.raises(ValueError, match="user_id is mandatory"):
        generate_cache_key("cypher", {"q": "test"}, user_id="")

    with pytest.raises(ValueError, match="user_id is mandatory"):
        generate_cache_key("cypher", {"q": "test"}, user_id="   ")

    with pytest.raises(ValueError, match="user_id is mandatory"):
        generate_cache_key("cypher", {"q": "test"}, user_id=None)  # type: ignore


def test_generate_cache_key_user_and_tenant_isolation():
    """Verify distinct cache keys are produced for different users and tenants."""
    key_a = generate_cache_key(
        namespace="cypher",
        key_components={"query": "nav tata flexi cap", "products": "Tata Flexi Cap"},
        user_id="user_alpha",
        tenant_id="tenant_1",
    )
    key_b = generate_cache_key(
        namespace="cypher",
        key_components={"query": "nav tata flexi cap", "products": "Tata Flexi Cap"},
        user_id="user_beta",
        tenant_id="tenant_1",
    )
    key_tenant2 = generate_cache_key(
        namespace="cypher",
        key_components={"query": "nav tata flexi cap", "products": "Tata Flexi Cap"},
        user_id="user_alpha",
        tenant_id="tenant_2",
    )

    assert key_a != key_b
    assert key_a != key_tenant2
    assert ":user:user_alpha:" in key_a
    assert ":user:user_beta:" in key_b
    assert ":tenant:tenant_1:" in key_a
    assert ":tenant:tenant_2:" in key_tenant2


def test_invalidate_user_cache_in_memory():
    """Verify invalidate_user_cache only deletes keys belonging to target user."""
    store = {}
    key_a1 = generate_cache_key("intent", {"q": "1"}, user_id="alice", tenant_id="t1")
    key_a2 = generate_cache_key("intent", {"q": "2"}, user_id="alice", tenant_id="t1")
    key_b1 = generate_cache_key("intent", {"q": "1"}, user_id="bob", tenant_id="t1")

    store[key_a1] = "val_a1"
    store[key_a2] = "val_a2"
    store[key_b1] = "val_b1"

    deleted = invalidate_user_cache(store, "intent", user_id="alice", tenant_id="t1")
    assert deleted == 2
    assert key_a1 not in store
    assert key_a2 not in store
    assert key_b1 in store
    assert store[key_b1] == "val_b1"


def test_user_scoped_redis_cache_isolation():
    """Verify UserScopedRedisCache prevents cross-user access."""
    class FakeRedis:
        def __init__(self):
            self._storage = {}

        def get(self, key):
            return self._storage.get(key)

        def setex(self, key, ttl, val):
            self._storage[key] = val
            return True

        def keys(self, pattern):
            import fnmatch
            return [k for k in self._storage if fnmatch.fnmatch(k, pattern)]

        def delete(self, *keys):
            count = 0
            for k in keys:
                if k in self._storage:
                    del self._storage[k]
                    count += 1
            return count

    fake_redis = FakeRedis()
    cache = UserScopedRedisCache(fake_redis)

    # Set value for Alice
    cache.set(
        namespace="vector_search",
        key_components={"query": "risk metrics"},
        value={"score": 0.95, "text": "Confidential portfolio details for Alice"},
        user_id="alice",
        tenant_id="amc_1",
    )

    # Bob attempts to fetch with identical query components
    bob_val = cache.get(
        namespace="vector_search",
        key_components={"query": "risk metrics"},
        user_id="bob",
        tenant_id="amc_1",
    )
    assert bob_val is None

    # Alice fetches with identical query components
    alice_val = cache.get(
        namespace="vector_search",
        key_components={"query": "risk metrics"},
        user_id="alice",
        tenant_id="amc_1",
    )
    assert alice_val is not None
    assert alice_val["score"] == 0.95

    # Invalidate Alice's cache
    deleted = cache.invalidate_user("alice", tenant_id="amc_1", namespace="vector_search")
    assert deleted == 1
    assert cache.get("vector_search", {"query": "risk metrics"}, "alice", "amc_1") is None


def test_cypher_cache_user_isolation():
    """Verify text_to_cypher cache keys and storage isolate users."""
    text_to_cypher.clear_cypher_cache()

    key_u1 = text_to_cypher._get_cypher_cache_key(
        "total aum", {"Tata Flexi Cap"}, user_id="user1", tenant_id="tenantA"
    )
    key_u2 = text_to_cypher._get_cypher_cache_key(
        "total aum", {"Tata Flexi Cap"}, user_id="user2", tenant_id="tenantA"
    )

    assert key_u1 != key_u2
    assert ":user:user1:" in key_u1
    assert ":user:user2:" in key_u2

    # Manually store for user 1
    text_to_cypher._CYPHER_CACHE[key_u1] = "MATCH (n:Scheme) RETURN n.aum"
    assert key_u2 not in text_to_cypher._CYPHER_CACHE

    # Invalidate user 1
    removed = text_to_cypher.invalidate_user_cypher_cache("user1", "tenantA")
    assert removed == 1
    assert key_u1 not in text_to_cypher._CYPHER_CACHE


def test_entity_resolver_cache_user_isolation():
    """Verify entity_resolver candidate cache isolates by user/tenant."""
    entity_resolver.clear_resolver_cache()

    key_u1 = entity_resolver._cache_key(frozenset(["Tata"]), user_id="alice", tenant_id="t1")
    key_u2 = entity_resolver._cache_key(frozenset(["Tata"]), user_id="bob", tenant_id="t1")

    assert key_u1 != key_u2
    assert ":user:alice:" in key_u1
    assert ":user:bob:" in key_u2

    entity_resolver._candidate_cache[key_u1] = (100.0, [{"name": "Tata"}])
    assert key_u2 not in entity_resolver._candidate_cache

    removed = entity_resolver.invalidate_user_resolver_cache("alice", "t1")
    assert removed == 1
    assert key_u1 not in entity_resolver._candidate_cache


def test_hyde_cache_user_isolation():
    """Verify hyde cache isolates by user and tenant."""
    hyde.clear_hyde_cache()

    key_a = hyde._get_cache_key("what is the exit load?", user_id="alice", tenant_id="t1")
    key_b = hyde._get_cache_key("what is the exit load?", user_id="bob", tenant_id="t1")

    assert key_a != key_b
    assert ":user:alice:" in key_a
    assert ":user:bob:" in key_b

    hyde._HYDE_CACHE[key_a] = ("Hypothetical document for Alice", 100.0)
    assert key_b not in hyde._HYDE_CACHE

    removed = hyde.invalidate_user_hyde_cache("alice", "t1")
    assert removed == 1
    assert key_a not in hyde._HYDE_CACHE


def test_intent_cache_user_isolation(tmp_path):
    """Verify IntentAwareCache isolates fingerprint probe, lookup, and invalidation."""
    disk_file = str(tmp_path / "test_intent_cache.json")
    cache = IntentAwareCache(shadow_mode=False, disk_path=disk_file)

    dummy_vec = np.ones(384, dtype=np.float32)
    dummy_vec = dummy_vec / np.linalg.norm(dummy_vec)

    # Store entry for Alice
    cache.store(
        query_vec=dummy_vec,
        query_type="v2_dual_regime_taxonomy",
        domain_intent="portfolio_holdings",
        query_text="top 10 holdings of tata flexi cap",
        answer="Holdings for Alice",
        provenance=[],
        confidence_label="high",
        confidence_reason="test",
        total_tokens=150,
        user_id="alice",
        tenant_id="t1",
    )

    # Bob probes with identical query text
    bob_hit = cache.fingerprint_probe(
        query_text="top 10 holdings of tata flexi cap",
        user_id="bob",
        tenant_id="t1",
    )
    assert bob_hit is None, "Bob must not hit Alice's cached intent fingerprint"

    # Alice probes with identical query text
    alice_hit = cache.fingerprint_probe(
        query_text="top 10 holdings of tata flexi cap",
        user_id="alice",
        tenant_id="t1",
    )
    assert alice_hit is not None
    assert alice_hit.answer == "Holdings for Alice"

    # Bob vector lookup with identical vector
    bob_lookup = cache.lookup(
        query_vec=dummy_vec,
        query_type="v2_dual_regime_taxonomy",
        domain_intent="portfolio_holdings",
        query_text="top 10 holdings of tata flexi cap",
        user_id="bob",
        tenant_id="t1",
    )
    assert bob_lookup is None, "Bob must not hit Alice's vector cached entry"

    # Alice vector lookup
    alice_lookup = cache.lookup(
        query_vec=dummy_vec,
        query_type="v2_dual_regime_taxonomy",
        domain_intent="portfolio_holdings",
        query_text="top 10 holdings of tata flexi cap",
        user_id="alice",
        tenant_id="t1",
    )
    assert alice_lookup is not None

    # Invalidate Alice
    removed = cache.invalidate_user("alice", "t1")
    assert removed == 1
    assert cache.fingerprint_probe("top 10 holdings of tata flexi cap", user_id="alice", tenant_id="t1") is None


def test_semantic_query_cache_user_isolation():
    """Verify SemanticQueryCache enforces user and tenant isolation on Gate 1 and Gate 2."""
    cache = SemanticQueryCache(dim=384, sim_threshold=0.85)

    dummy_vec = np.ones((1, 384), dtype=np.float32)

    # Store entry for User 1
    cache.store(
        query="what is the expense ratio?",
        response={"answer": "Expense ratio is 1.5%", "confidence": "high"},
        user_id="user1",
        tenant_id="amc_a",
    )

    # Gate 1: Exact probe by User 2 -> must return None
    user2_exact = cache.lookup(
        query="what is the expense ratio?",
        user_id="user2",
        tenant_id="amc_a",
    )
    assert user2_exact is None, "User 2 must not get exact hit for User 1's cached entry"

    # Gate 1: Exact probe by User 1 -> must return hit
    user1_exact = cache.lookup(
        query="what is the expense ratio?",
        user_id="user1",
        tenant_id="amc_a",
    )
    assert user1_exact is not None
    assert user1_exact.get("cache_hit") is True
    assert user1_exact.get("answer") == "Expense ratio is 1.5%"

    # Gate 2: Vector lookup test
    vec = np.ones((1, 384), dtype=np.float32)
    cache.store(
        query=vec,
        response={"answer": "Vector answer for User 1", "confidence": "high"},
        user_id="user1",
        tenant_id="amc_a",
    )

    # Gate 2: Vector lookup by User 2 -> must return None
    user2_vector = cache.lookup(
        query=vec,
        user_id="user2",
        tenant_id="amc_a",
    )
    assert user2_vector is None, "User 2 must not get vector hit for User 1's cached entry"

    # Gate 2: Vector lookup by User 1 -> must return hit
    user1_vector = cache.lookup(
        query=vec,
        user_id="user1",
        tenant_id="amc_a",
    )
    assert user1_vector is not None
    assert user1_vector.get("cache_hit") is True
    assert user1_vector.get("answer") == "Vector answer for User 1"

    # Invalidate User 1
    removed = cache.invalidate_user("user1", "amc_a")
    assert removed == 2
    assert cache.count() == 0
    assert cache.lookup("what is the expense ratio?", user_id="user1", tenant_id="amc_a") is None
