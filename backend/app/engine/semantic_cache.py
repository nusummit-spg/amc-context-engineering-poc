# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
semantic_cache.py
=================
Consolidated semantic cache facade.
Delegates to UnifiedSemanticCache (app.retrieval.cache) for sub-millisecond,
FAISS-backed semantic similarity without heavy model load latencies.
"""
from typing import Any, Dict, List, Optional, Tuple
from app.retrieval.cache import UnifiedSemanticCache, get_semantic_cache


class SemanticCache:
    """Wrapper around UnifiedSemanticCache providing engine compatibility."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", threshold: float = 0.88):
        """Initialize a new instance of SemanticCache.

        Args:
            model_name (str): Name of the model.
            threshold (float): Score threshold for matching.
        """
        self._cache = UnifiedSemanticCache(sim_threshold=threshold)
        self.threshold = threshold

    def check(
        self,
        query: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Tuple[Optional[dict], float]:
        """Check.

        Args:
            query (str): Search query or input text.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            Tuple[Optional[dict], float]: Dictionary containing result data or status.
        """
        return self._cache.check(query, user_id=user_id, tenant_id=tenant_id)

    def store(
        self,
        query: str,
        payload: dict,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        """Store.

        Args:
            query (str): Search query or input text.
            payload (dict): Request or event payload.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
        """
        self._cache.store(query, payload, user_id=user_id, tenant_id=tenant_id)

    def invalidate_user(self, user_id: str, tenant_id: Optional[str] = None) -> int:
        """Invalidate user.

        Args:
            user_id (str): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            int: Resulting int instance.
        """
        return self._cache.invalidate_user(user_id, tenant_id)

    def clear(self):
        """Clear.
        """
        self._cache.clear()

    def warm_cache_patterns(self, precomputed_items: List[Tuple[str, dict]]):
        """Warm cache patterns.

        Args:
            precomputed_items (List[Tuple[str, dict]]): Collection or list of precomputed items.
        """
        self._cache.warm_cache_patterns(precomputed_items)


def get_cache() -> UnifiedSemanticCache:
    """Returns the process-wide canonical semantic cache instance.

    Returns:
        UnifiedSemanticCache: Resulting UnifiedSemanticCache instance.
    """
    return get_semantic_cache()

