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
import hashlib
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
        """Initialize a new instance of SemanticQueryCache.

        Args:
            dim (int): The dim.
            sim_threshold (float): The sim threshold.
            max_entries (int): Collection or list of max entries.
            ttl_seconds (int): Collection or list of ttl seconds.
        """
        self._dim = dim
        self._threshold = sim_threshold
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._index = faiss.IndexFlatIP(dim)
        self._cache_data: list[dict[str, Any]] = []
        # Normalized vectors kept alongside entries so clear_expired() can rebuild
        # the FAISS index without paying to re-embed every surviving query.
        self._vectors: list[np.ndarray] = []
        # In-memory exact string hash index: MD5 fingerprint -> cache_data index (<1ms Gate 1)
        self._exact_hash_index: dict[str, int] = {}
        try:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except Exception:
            self._embedder = None

    @staticmethod
    def _fingerprint(query: str, user_id: Optional[str] = None, tenant_id: Optional[str] = None) -> str:
        """Normalized string fingerprint for O(1) exact cache probe with user/tenant scoping.

        Args:
            query (str): Search query or input text.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            str: Resulting str instance.
        """
        if user_id:
            from app.core.cache_utils import generate_cache_key
            return generate_cache_key(
                namespace="semantic_cache",
                key_components={"query": query.strip().lower()},
                user_id=user_id,
                tenant_id=tenant_id,
            )
        return hashlib.md5(query.strip().lower().encode("utf-8")).hexdigest()

    def count(self) -> int:
        """Count.

        Returns:
            int: Resulting int instance.
        """
        return self._index.ntotal

    def _to_vector(self, query: str | np.ndarray, embedder: Any = None) -> np.ndarray:
        """To vector.

        Args:
            query (str | np.ndarray): Search query or input text.
            embedder (Any): The embedder.

        Returns:
            np.ndarray: Resulting np.ndarray instance.
        """
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
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Look up query. Returns cached result dict if exact hit or cosine similarity >= threshold and not expired.

        Dual-Gate Caching Strategy:
        - Gate 1: O(1) MD5 exact string fingerprint match (<1ms, bypasses FastEmbed model)
        - Gate 2: FAISS vector similarity search (~20ms, for semantically related paraphrases)

        Args:
            query (str | np.ndarray): Search query or input text.
            embedder (Any): The embedder.
            corpus_version (Optional[str]): Version of the active document corpus.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            Optional[dict[str, Any]]: Dictionary containing result data or status.
        """
        # --- Gate 1: Exact string fingerprint probe (<1ms) ---
        if isinstance(query, str) and query.strip():
            fp = self._fingerprint(query, user_id=user_id, tenant_id=tenant_id)
            if fp in self._exact_hash_index:
                idx = self._exact_hash_index[fp]
                if idx < len(self._cache_data):
                    hit_data = self._cache_data[idx].copy()
                    age = time.time() - hit_data.get("timestamp", 0)
                    valid = True
                    if user_id and hit_data.get("user_id") != user_id:
                        valid = False
                    if tenant_id and hit_data.get("tenant_id") != tenant_id:
                        valid = False
                    if age > self._ttl_seconds:
                        logger.debug("Fingerprint cache entry expired (age: %.1fs > ttl: %ds)", age, self._ttl_seconds)
                        valid = False
                    if corpus_version and hit_data.get("corpus_version") and hit_data.get("corpus_version") != corpus_version:
                        logger.debug("Fingerprint cache corpus mismatch (%s vs %s)", hit_data.get("corpus_version"), corpus_version)
                        valid = False

                    if valid:
                        logger.info("Exact fingerprint cache HIT (<1ms, fp=%s, age: %.1fs)", fp[:8], age)
                        hit_data["cache_hit"] = True
                        hit_data["cache_similarity"] = 1.0
                        hit_data["cache_kind"] = "exact"
                        hit_data["hit_type"] = "Fingerprint"
                        return hit_data

        # --- Gate 2: FAISS cosine vector search ---
        if self._index.ntotal == 0:
            return None

        try:
            vec_copy = np.ascontiguousarray(self._to_vector(query, embedder), dtype="float32")
            faiss.normalize_L2(vec_copy)

            k = min(10, self._index.ntotal)
            scores, ids = self._index.search(vec_copy, k)

            for rank in range(k):
                score = float(scores[0][rank])
                idx = int(ids[0][rank])

                if idx != -1 and score >= self._threshold and idx < len(self._cache_data):
                    hit_data = self._cache_data[idx].copy()

                    # Check user and tenant scoping
                    if user_id and hit_data.get("user_id") != user_id:
                        continue
                    if tenant_id and hit_data.get("tenant_id") != tenant_id:
                        continue

                    # Check TTL
                    age = time.time() - hit_data.get("timestamp", 0)
                    if age > self._ttl_seconds:
                        logger.debug("Cache entry expired (age: %.1fs > ttl: %ds)", age, self._ttl_seconds)
                        continue

                    # Check corpus version
                    if corpus_version and hit_data.get("corpus_version") and hit_data.get("corpus_version") != corpus_version:
                        logger.debug("Cache entry corpus mismatch (%s vs %s)", hit_data.get("corpus_version"), corpus_version)
                        continue

                    logger.info("Semantic cache HIT (similarity: %.4f, age: %.1fs)", score, age)
                    hit_data["cache_hit"] = True
                    hit_data["cache_similarity"] = score
                    hit_data["cache_kind"] = "semantic"
                    hit_data["hit_type"] = "Semantic"
                    return hit_data

            logger.debug("Semantic cache MISS")
            return None
        except Exception as exc:
            logger.warning("Cache lookup error: %s", exc)
            return None

    def check(
        self,
        query: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Tuple[Optional[dict], float]:
        """Returns (cached_payload, latency_ms) if a semantic hit is found, else (None, latency_ms).
        Compatible with engine/semantic_cache API.

        Args:
            query (str): Search query or input text.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            Tuple[Optional[dict], float]: Dictionary containing result data or status.
        """
        t0 = time.perf_counter()
        entry = self.lookup(query, user_id=user_id, tenant_id=tenant_id)
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
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Store query and associated response payload in cache.

        Args:
            query (str | np.ndarray): Search query or input text.
            response (dict[str, Any]): FastAPI response instance.
            embedder (Any): The embedder.
            corpus_version (Optional[str]): Version of the active document corpus.
            model_version (Optional[str]): The model version.
            prompt_version (Optional[str]): The prompt version.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
        """
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
                "user_id": user_id,
                "tenant_id": tenant_id,
                **response,
            }
            new_idx = len(self._cache_data)
            self._cache_data.append(entry)
            if isinstance(query, str) and query.strip():
                fp = self._fingerprint(query, user_id=user_id, tenant_id=tenant_id)
                self._exact_hash_index[fp] = new_idx
            logger.info("Stored response in semantic cache (total entries: %d)", self._index.ntotal)
        except Exception as exc:
            logger.warning("Cache store error: %s", exc)

    def warm_cache_patterns(self, precomputed_items: list[tuple[str, dict]]):
        """Pre-populates semantic cache with precomputed archetypes/answers.

        Args:
            precomputed_items (list[tuple[str, dict]]): Collection or list of precomputed items.
        """
        for query, payload in precomputed_items:
            self.store(query, payload)
        logger.info("Pre-warmed semantic cache with %d items.", len(precomputed_items))

    def invalidate(self, corpus_version: Optional[str] = None) -> None:
        """Invalidate entries matching corpus_version or clear completely.

        Args:
            corpus_version (Optional[str]): Version of the active document corpus.
        """
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
        """Invalidate corpus.

        Args:
            corpus_version (str): Version of the active document corpus.
        """
        self.invalidate(corpus_version=corpus_version)

    def clear_expired(self) -> int:
        """Drop TTL-expired entries and rebuild the index. Returns entries removed.

        Called by the nightly cache-maintenance job. Unlike invalidate(), this
        preserves every entry that is still within its TTL.

        Returns:
            int: Resulting int instance.
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
        self._exact_hash_index = {
            self._fingerprint(entry["query"], user_id=entry.get("user_id"), tenant_id=entry.get("tenant_id")): idx
            for idx, entry in enumerate(survivors)
            if entry.get("query") and isinstance(entry["query"], str)
        }
        for vec in survivor_vectors:
            self._index.add(vec)

        logger.info("Pruned %d expired semantic cache entries (%d remain).", removed, len(survivors))
        return removed

    def invalidate_user(self, user_id: str, tenant_id: Optional[str] = None) -> int:
        """Purge all cache entries belonging to user_id (and tenant_id) and rebuild index.

        Args:
            user_id (str): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            int: Resulting int instance.
        """
        if not user_id or not self._cache_data:
            return 0

        clean_user = str(user_id).strip()
        clean_tenant = str(tenant_id).strip() if tenant_id else None

        survivors: list[dict[str, Any]] = []
        survivor_vectors: list[np.ndarray] = []

        for i, entry in enumerate(self._cache_data):
            match = (entry.get("user_id") == clean_user)
            if match and clean_tenant:
                match = (entry.get("tenant_id") == clean_tenant)
            if not match:
                survivors.append(entry)
                if i < len(self._vectors):
                    survivor_vectors.append(self._vectors[i])

        removed = len(self._cache_data) - len(survivors)
        if removed == 0:
            return 0

        if len(survivor_vectors) != len(survivors):
            logger.warning("Cache vector/entry mismatch during user invalidation; clearing cache instead.")
            self.clear()
            return removed

        self._index.reset()
        self._cache_data = survivors
        self._vectors = survivor_vectors
        self._exact_hash_index = {
            self._fingerprint(entry["query"], user_id=entry.get("user_id"), tenant_id=entry.get("tenant_id")): idx
            for idx, entry in enumerate(survivors)
            if entry.get("query") and isinstance(entry["query"], str)
        }
        for vec in survivor_vectors:
            self._index.add(vec)

        logger.info("Invalidated %d semantic cache entries for user %s (%d remain).", removed, clean_user, len(survivors))
        return removed

    def clear(self) -> None:
        """Clear.
        """
        self._index.reset()
        self._cache_data.clear()
        self._vectors.clear()
        self._exact_hash_index.clear()
        logger.info("Cleared semantic query cache.")


UnifiedSemanticCache = SemanticQueryCache

_global_semantic_cache: Optional[UnifiedSemanticCache] = None


def get_semantic_cache() -> UnifiedSemanticCache:
    """Retrieve semantic cache.

    Returns:
        UnifiedSemanticCache: Resulting UnifiedSemanticCache instance.
    """
    global _global_semantic_cache
    if _global_semantic_cache is None:
        _global_semantic_cache = UnifiedSemanticCache()
    return _global_semantic_cache


def invalidate_user_semantic_cache(user_id: str, tenant_id: Optional[str] = None) -> int:
    """Invalidate all semantic cache entries for a specific user.

    Args:
        user_id (str): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        int: Resulting int instance.
    """
    return get_semantic_cache().invalidate_user(user_id, tenant_id)

