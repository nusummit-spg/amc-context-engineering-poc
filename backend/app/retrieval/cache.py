# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Unified Semantic query caching layer (Phase 1 & Phase 2).

Embeds incoming queries and performs fast vector lookup against previously answered queries.
If cosine similarity >= sim_threshold (default 0.95), returns cached answer in <30ms,
bypassing Neo4j traversal and LLM generation.
Supports both orchestrator lookup() and engine check() APIs, pre-warming, TTL, and corpus invalidation.
"""
import logging
import time
from typing import Any, Optional, Tuple

import faiss
import numpy as np

logger = logging.getLogger("retrieval.cache")


class SemanticQueryCache:
    def __init__(
        self,
        dim: int = 384,
        sim_threshold: float = 0.95,
        max_entries: int = 5000,
        ttl_seconds: int = 3600,
    ) -> None:
        self._dim = dim
        self._threshold = sim_threshold
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._index = faiss.IndexFlatIP(dim)
        self._cache_data: list[dict[str, Any]] = []
        # Normalized vectors kept alongside entries so clear_expired() can rebuild
        # the FAISS index without paying to re-embed every surviving query.
        self._vectors: list[np.ndarray] = []
        try:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except Exception:
            self._embedder = None

    def count(self) -> int:
        return self._index.ntotal

    def _to_vector(self, query: str | np.ndarray, embedder: Any = None) -> np.ndarray:
        if isinstance(query, np.ndarray):
            vec = query.astype("float32")
            if vec.ndim == 1:
                vec = np.expand_dims(vec, axis=0)
            return vec
        active_emb = embedder or self._embedder
        if active_emb is not None:
            raw = active_emb(query) if callable(active_emb) else active_emb.embed([query])
            if hasattr(raw, "__iter__") and not isinstance(raw, np.ndarray):
                raw = list(raw)
            arr = np.array(raw, dtype="float32")
            if arr.ndim == 1:
                arr = np.expand_dims(arr, axis=0)
            return arr
        return np.zeros((1, self._dim), dtype="float32")

    def lookup(
        self,
        query: str | np.ndarray,
        embedder: Any = None,
        corpus_version: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Look up query. Returns cached result dict if cosine similarity >= threshold and not expired."""
        if self._index.ntotal == 0:
            return None

        try:
            vec_copy = np.ascontiguousarray(self._to_vector(query, embedder), dtype="float32")
            faiss.normalize_L2(vec_copy)

            scores, ids = self._index.search(vec_copy, 1)
            score = float(scores[0][0])
            idx = int(ids[0][0])

            if idx != -1 and score >= self._threshold and idx < len(self._cache_data):
                hit_data = self._cache_data[idx].copy()
                
                # Check TTL
                age = time.time() - hit_data.get("timestamp", 0)
                if age > self._ttl_seconds:
                    logger.debug("Cache entry expired (age: %.1fs > ttl: %ds)", age, self._ttl_seconds)
                    return None

                # Check corpus version
                if corpus_version and hit_data.get("corpus_version") and hit_data.get("corpus_version") != corpus_version:
                    logger.debug("Cache entry corpus mismatch (%s vs %s)", hit_data.get("corpus_version"), corpus_version)
                    return None

                logger.info("Semantic cache HIT (similarity: %.4f, age: %.1fs)", score, age)
                hit_data["cache_hit"] = True
                hit_data["cache_similarity"] = score
                return hit_data

            logger.debug("Semantic cache MISS (best similarity: %.4f)", score if idx != -1 else 0.0)
            return None
        except Exception as exc:
            logger.warning("Cache lookup error: %s", exc)
            return None

    def check(self, query: str) -> Tuple[Optional[dict], float]:
        """Returns (cached_payload, latency_ms) if a semantic hit is found, else (None, latency_ms).
        Compatible with engine/semantic_cache API."""
        t0 = time.perf_counter()
        entry = self.lookup(query)
        latency = (time.perf_counter() - t0) * 1000.0
        return entry, latency

    def store(
        self,
        query: str | np.ndarray,
        response: dict[str, Any],
        embedder: Any = None,
        corpus_version: Optional[str] = None,
        model_version: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> None:
        """Store query and associated response payload in cache."""
        try:
            if self._index.ntotal >= self._max_entries:
                self.clear()

            vec_copy = np.ascontiguousarray(self._to_vector(query, embedder), dtype="float32")
            faiss.normalize_L2(vec_copy)

            self._index.add(vec_copy)
            self._vectors.append(vec_copy)
            entry = {
                "timestamp": time.time(),
                "query": query if isinstance(query, str) else "",
                "corpus_version": corpus_version,
                "model_version": model_version,
                "prompt_version": prompt_version,
                **response,
            }
            self._cache_data.append(entry)
            logger.info("Stored response in semantic cache (total entries: %d)", self._index.ntotal)
        except Exception as exc:
            logger.warning("Cache store error: %s", exc)

    def warm_cache_patterns(self, precomputed_items: list[tuple[str, dict]]):
        """Pre-populates semantic cache with precomputed archetypes/answers."""
        for query, payload in precomputed_items:
            self.store(query, payload)
        logger.info("Pre-warmed semantic cache with %d items.", len(precomputed_items))

    def invalidate(self, corpus_version: Optional[str] = None) -> None:
        """Invalidate entries matching corpus_version or clear completely."""
        if not corpus_version:
            self.clear()
            return
        
        retained_data = []
        for entry in self._cache_data:
            if entry.get("corpus_version") != corpus_version:
                retained_data.append(entry)
        
        self.clear()
        for item in retained_data:
            q = item.get("query", "")
            if q:
                self.store(q, item, corpus_version=item.get("corpus_version"))
        logger.info("Invalidated cache for corpus_version=%s (retained entries: %d)", corpus_version, len(self._cache_data))

    def invalidate_corpus(self, corpus_version: str) -> None:
        self.invalidate(corpus_version=corpus_version)

    def clear_expired(self) -> int:
        """Drop TTL-expired entries and rebuild the index. Returns entries removed.

        Called by the nightly cache-maintenance job. Unlike invalidate(), this
        preserves every entry that is still within its TTL.
        """
        if not self._cache_data:
            return 0

        now = time.time()
        survivors: list[dict[str, Any]] = []
        survivor_vectors: list[np.ndarray] = []

        for i, entry in enumerate(self._cache_data):
            age = now - entry.get("timestamp", 0)
            if age <= self._ttl_seconds:
                survivors.append(entry)
                if i < len(self._vectors):
                    survivor_vectors.append(self._vectors[i])

        removed = len(self._cache_data) - len(survivors)
        if removed == 0:
            return 0

        # Only rebuild if every survivor still has its vector; otherwise the
        # positional mapping between the index and _cache_data would break.
        if len(survivor_vectors) != len(survivors):
            logger.warning("Cache vector/entry mismatch during expiry sweep; clearing cache instead.")
            self.clear()
            return removed

        self._index.reset()
        self._cache_data = survivors
        self._vectors = survivor_vectors
        for vec in survivor_vectors:
            self._index.add(vec)

        logger.info("Pruned %d expired semantic cache entries (%d remain).", removed, len(survivors))
        return removed

    def clear(self) -> None:
        self._index.reset()
        self._cache_data.clear()
        self._vectors.clear()
        logger.info("Cleared semantic query cache.")


UnifiedSemanticCache = SemanticQueryCache

_global_semantic_cache: Optional[UnifiedSemanticCache] = None


def get_semantic_cache() -> UnifiedSemanticCache:
    global _global_semantic_cache
    if _global_semantic_cache is None:
        _global_semantic_cache = UnifiedSemanticCache()
    return _global_semantic_cache
