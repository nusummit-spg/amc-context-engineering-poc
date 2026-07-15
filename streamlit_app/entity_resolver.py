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

import config
import graph_store
import faiss_store  # reuse _get_embedder() — same model already loaded

_candidate_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 300  # seconds — candidate pool refreshes every 5 min, not every query


def _cache_key(product_names: frozenset | None) -> str:
    return "|".join(sorted(product_names)) if product_names else "__all__"


_embedding_cache: dict[str, Any] = {}  # text -> vector, persists across calls

def _get_candidates(product_names: set | None = None) -> list[dict]:
    key = _cache_key(frozenset(product_names) if product_names else None)
    now = time.time()
    if key in _candidate_cache:
        ts, cached = _candidate_cache[key]
        if now - ts < _CACHE_TTL:
            return cached
    candidates = graph_store.get_all_entity_texts(product_names=product_names, limit=150)  # was 500
    _candidate_cache[key] = (now, candidates)
    return candidates


def resolve_entities_for_query(entity_texts: list[str], product_names: set | None = None,
                                threshold: float = None) -> dict[str, list[str]]:
    threshold = threshold if threshold is not None else config.SIMILARITY_MATCH_THRESHOLD
    if not entity_texts:
        return {}

    candidates = _get_candidates(product_names)
    if not candidates:
        return {t: [] for t in entity_texts}

    model = faiss_store._get_embedder()
    candidate_texts = [c["text"] for c in candidates]

    # ── embed only texts not already cached — this is the real fix ────────
    uncached = [t for t in candidate_texts if t not in _embedding_cache]
    if uncached:
        new_vecs = model.encode(uncached, normalize_embeddings=True).astype("float32")
        for t, v in zip(uncached, new_vecs):
            _embedding_cache[t] = v
    candidate_vecs = np.array([_embedding_cache[t] for t in candidate_texts])

    query_vecs = model.encode(entity_texts, normalize_embeddings=True).astype("float32")

    results: dict[str, list[str]] = {}
    for i, qtext in enumerate(entity_texts):
        sims = candidate_vecs @ query_vecs[i]
        order = np.argsort(-sims)
        matched_sorted = list(dict.fromkeys(
            candidate_texts[j] for j in order if sims[j] >= threshold))
        results[qtext] = matched_sorted[:10]
    return results