# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
entity_resolver.py
====================
Similarity-based entity resolution — replaces naive substring CONTAINS
matching, which let a generic word (e.g. "debt") silently match every node
containing that substring across the ENTIRE graph, regardless of whether it
was actually the right entity for the question being asked.

Reuses the same sentence-transformer embedder faiss_store already loads for
vector search — no second model, no extra memory or startup cost.
"""
from __future__ import annotations
import time
from typing import Optional
from typing import Any

import numpy as np

from app.engine import config
from app.engine import graph_store
from app.engine import faiss_store  # reuse _get_embedder() — same model already loaded

_candidate_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 86400  # seconds — candidate pool refreshes every 24 hours, not every 5 min


def _cache_key(
    product_names: frozenset | None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    """Cache key.

    Args:
        product_names (frozenset | None): Collection or list of product names.
        user_id (Optional[str]): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        str: Resulting str instance.
    """
    prods_str = "|".join(sorted(product_names)) if product_names else "__all__"
    if user_id:
        from app.core.cache_utils import generate_cache_key
        return generate_cache_key(
            namespace="entity_resolve",
            key_components={"products": prods_str},
            user_id=user_id,
            tenant_id=tenant_id,
        )
    return prods_str


_embedding_cache: dict[str, Any] = {}  # candidate text -> vector, persists across calls
_query_vec_cache: dict[str, Any] = {}  # query entity text -> vector, persists across calls


def clear_resolver_cache():
    """Clears candidate and embedding caches."""
    global _candidate_cache, _embedding_cache, _query_vec_cache
    _candidate_cache.clear()
    _embedding_cache.clear()
    _query_vec_cache.clear()


def invalidate_user_resolver_cache(user_id: str, tenant_id: Optional[str] = None) -> int:
    """Invalidate entity candidate cache entries for a specific user.

    Args:
        user_id (str): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        int: Resulting int instance.
    """
    from app.core.cache_utils import invalidate_user_cache
    return invalidate_user_cache(_candidate_cache, "entity_resolve", user_id, tenant_id)


def _get_candidates(
    product_names: set | None = None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> list[dict]:
    """Retrieve candidates.

    Args:
        product_names (set | None): Collection or list of product names.
        user_id (Optional[str]): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        list[dict]: List of resulting items or records.
    """
    key = _cache_key(frozenset(product_names) if product_names else None, user_id=user_id, tenant_id=tenant_id)
    now = time.time()
    if key in _candidate_cache:
        ts, cached = _candidate_cache[key]
        if now - ts < _CACHE_TTL:
            return cached
    try:
        candidates = graph_store.get_all_entity_texts(product_names=product_names, limit=150)
    except Exception:
        candidates = []
    _candidate_cache[key] = (now, candidates)
    return candidates



def resolve_entities_for_query(
    entity_texts: list[str],
    product_names: set | None = None,
    threshold: float = None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict[str, list[str]]:
    """Resolve entities for query.

    Args:
        entity_texts (list[str]): Collection or list of entity texts.
        product_names (set | None): Collection or list of product names.
        threshold (float): Score threshold for matching.
        user_id (Optional[str]): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        dict[str, list[str]]: List of resulting items or records.
    """
    threshold = threshold if threshold is not None else config.SIMILARITY_MATCH_THRESHOLD
    if not entity_texts:
        return {}

    candidates = _get_candidates(product_names, user_id=user_id, tenant_id=tenant_id)
    if not candidates:
        return {t: [] for t in entity_texts}

    model = faiss_store._get_embedder()
    candidate_texts = [c["text"] for c in candidates]

    # ── embed only candidate texts not already cached ────────────────────────
    uncached = [t for t in candidate_texts if t not in _embedding_cache]
    if uncached:
        new_vecs = model.encode(uncached, normalize_embeddings=True).astype("float32")
        for t, v in zip(uncached, new_vecs):
            _embedding_cache[t] = v
    candidate_vecs = np.array([_embedding_cache[t] for t in candidate_texts])

    # ── embed only query entity texts not already cached ─────────────────────
    uncached_queries = [t for t in entity_texts if t not in _query_vec_cache]
    if uncached_queries:
        new_qvecs = model.encode(uncached_queries, normalize_embeddings=True).astype("float32")
        for t, v in zip(uncached_queries, new_qvecs):
            _query_vec_cache[t] = v
    query_vecs = np.array([_query_vec_cache[t] for t in entity_texts])

    results: dict[str, list[str]] = {}
    for i, qtext in enumerate(entity_texts):
        sims = candidate_vecs @ query_vecs[i]
        order = np.argsort(-sims)
        matched_sorted = list(dict.fromkeys(
            candidate_texts[j] for j in order if sims[j] >= threshold))
        results[qtext] = matched_sorted[:10]
    return results

