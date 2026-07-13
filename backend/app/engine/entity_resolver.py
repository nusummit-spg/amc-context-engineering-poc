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

import numpy as np

from app.engine import config
from app.engine import graph_store
from app.engine import faiss_store  # reuse _get_embedder() — same model already loaded

_candidate_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 300  # seconds — candidate pool refreshes every 5 min, not every query


def _cache_key(product_names: frozenset | None) -> str:
    return "|".join(sorted(product_names)) if product_names else "__all__"


def _get_candidates(product_names: set | None = None) -> list[dict]:
    key = _cache_key(frozenset(product_names) if product_names else None)
    now = time.time()
    if key in _candidate_cache:
        ts, cached = _candidate_cache[key]
        if now - ts < _CACHE_TTL:
            return cached
    candidates = graph_store.get_all_entity_texts(product_names=product_names, limit=500)
    _candidate_cache[key] = (now, candidates)
    return candidates


def resolve_entities_for_query(entity_texts: list[str], product_names: set | None = None,
                                threshold: float = None) -> dict[str, list[str]]:
    """
    For each input entity text, returns graph node texts that are genuinely
    similar by embedding cosine similarity, scoped to product_names if given.
    A generic word that doesn't closely match any specific node text returns
    an EMPTY list, rather than a broad substring match — this is the direct
    fix for the "debt" bug.
    """
    threshold = threshold if threshold is not None else config.SIMILARITY_MATCH_THRESHOLD
    if not entity_texts:
        return {}

    candidates = _get_candidates(product_names)
    if not candidates:
        return {t: [] for t in entity_texts}

    model = faiss_store._get_embedder()
    candidate_texts = [c["text"] for c in candidates]
    candidate_vecs = model.encode(candidate_texts, normalize_embeddings=True).astype("float32")
    query_vecs = model.encode(entity_texts, normalize_embeddings=True).astype("float32")

    results: dict[str, list[str]] = {}
    for i, qtext in enumerate(entity_texts):
        sims = candidate_vecs @ query_vecs[i]
        order = np.argsort(-sims)
        matched_sorted = list(dict.fromkeys(
            candidate_texts[j] for j in order if sims[j] >= threshold))
        results[qtext] = matched_sorted[:10]
    return results