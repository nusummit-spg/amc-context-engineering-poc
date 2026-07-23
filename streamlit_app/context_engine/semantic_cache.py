"""
semantic_cache.py
===================
Lightweight in-memory FAISS semantic cache for query/answer pairs.

Sits in front of retrieval.py's traditional_rag()/hybrid_graphrag(): on a
cosine-similarity hit against a previously answered query, the cached full
result dict is returned immediately, skipping NER/graph/vector/LLM entirely.

Reuses the exact same embedder faiss_store.py already loads (via
faiss_store._get_embedder()) — no second model is loaded for this cache.

Cache key is namespaced by `mode` ("traditional" / "hybrid") so the two
pipelines never serve each other's answers. Capped at
config.SEMANTIC_CACHE_MAX_ENTRIES entries; FAISS's IndexFlatIP has no
in-place row deletion, so eviction rebuilds the index from the retained
(already-computed) vectors rather than re-embedding anything.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import numpy as np

import config
import faiss_store

_index = None
_payloads: List[dict] = []
_vectors: List[np.ndarray] = []


def _embedding_dim(embedder) -> int:
    """sentence-transformers renamed this method (get_sentence_embedding_dimension
    -> get_embedding_dimension) across versions in the wild — support both."""
    if hasattr(embedder, "get_embedding_dimension"):
        return embedder.get_embedding_dimension()
    return embedder.get_sentence_embedding_dimension()


def _get_index():
    global _index
    if _index is None:
        import faiss
        dim = _embedding_dim(faiss_store._get_embedder())
        _index = faiss.IndexFlatIP(dim)
    return _index


def _embed_one(text: str) -> np.ndarray:
    embedder = faiss_store._get_embedder()
    return embedder.encode([text], normalize_embeddings=True).astype("float32")


def check(query: str, mode: str) -> Optional[Dict[str, Any]]:
    """Returns the cached result dict on a semantic hit for the same `mode`,
    else None. Searches the top-5 nearest neighbors (not just top-1) since
    the index mixes both modes together — the nearest vector overall might
    belong to the other mode even when a same-mode near-duplicate exists a
    little further down."""
    index = _get_index()
    if index.ntotal == 0:
        return None

    q_vec = _embed_one(query)
    k = min(5, index.ntotal)
    scores, indices = index.search(q_vec, k)

    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(_payloads):
            continue
        entry = _payloads[idx]
        if entry["mode"] != mode:
            continue
        if float(score) >= config.SEMANTIC_CACHE_SIMILARITY_THRESHOLD:
            print(f"  [cache] HIT mode={mode} score={float(score):.3f} "
                  f">= {config.SEMANTIC_CACHE_SIMILARITY_THRESHOLD} "
                  f"(matched: \"{entry['query'][:60]}\")", flush=True)
            return entry["result"]
    return None


def store(query: str, mode: str, result: Dict[str, Any]) -> None:
    """Adds a query/result pair to the cache, evicting the oldest entry if
    this pushes the cache past SEMANTIC_CACHE_MAX_ENTRIES."""
    index = _get_index()
    vec = _embed_one(query)
    index.add(vec)
    _vectors.append(vec)
    _payloads.append({"query": query, "mode": mode, "result": result})

    if len(_payloads) > config.SEMANTIC_CACHE_MAX_ENTRIES:
        _evict_oldest()


def _evict_oldest() -> None:
    global _index
    import faiss
    _payloads.pop(0)
    _vectors.pop(0)
    dim = _embedding_dim(faiss_store._get_embedder())
    new_index = faiss.IndexFlatIP(dim)
    if _vectors:
        new_index.add(np.vstack(_vectors))
    _index = new_index


def size() -> int:
    return len(_payloads)


def clear() -> None:
    """Resets the cache — mainly useful for local testing/eval scripts that
    want a clean cache per run."""
    global _index
    _index = None
    _payloads.clear()
    _vectors.clear()
