# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
shared_context_cache.py
========================
In-memory cache for shared Neo4j subgraphs and few-shot examples across batch evaluations.
Reduces redundant database/graph queries within a 1-hour window.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.evaluation.shared_context_cache")


class SharedContextCache:
    """
    Cache shared Neo4j subgraphs and few-shot examples across batch evaluations.
    Reduces redundant database queries within a 1-hour window.
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize a new instance of SharedContextCache.

        Args:
            ttl_seconds (int): Collection or list of ttl seconds.
        """
        self.ttl_seconds = ttl_seconds
        self._subgraph_cache: Dict[str, Dict[str, Any]] = {}
        self._fewshot_cache: Dict[str, Dict[str, Any]] = {}

    def get_subgraph(self, entity_id: str, hops: int = 1) -> Optional[dict]:
        """Retrieve cached 1-hop or n-hop subgraph for entity.

        Args:
            entity_id (str): Unique identifier of the entity.
            hops (int): Collection or list of hops.

        Returns:
            Optional[dict]: Dictionary containing result data or status.
        """
        key = f"{entity_id}_{hops}"
        cached = self._subgraph_cache.get(key)
        if cached:
            age = (datetime.now(timezone.utc) - cached["timestamp"]).total_seconds()
            if age < self.ttl_seconds:
                return cached["data"]
        return None

    def set_subgraph(self, entity_id: str, hops: int, data: dict) -> None:
        """Cache subgraph result.

        Args:
            entity_id (str): Unique identifier of the entity.
            hops (int): Collection or list of hops.
            data (dict): Input data payload.
        """
        key = f"{entity_id}_{hops}"
        self._subgraph_cache[key] = {
            "data": data,
            "timestamp": datetime.now(timezone.utc),
        }

    def get_fewshot_examples(self, category: str) -> Optional[list]:
        """Retrieve cached few-shot examples for rule category.

        Args:
            category (str): Classification category.

        Returns:
            Optional[list]: List of resulting items or records.
        """
        cached = self._fewshot_cache.get(category)
        if cached:
            age = (datetime.now(timezone.utc) - cached["timestamp"]).total_seconds()
            if age < self.ttl_seconds * 24:  # 24h TTL for examples
                return cached["data"]
        return None

    def set_fewshot_examples(self, category: str, examples: list) -> None:
        """Cache few-shot examples.

        Args:
            category (str): Classification category.
            examples (list): Collection or list of examples.
        """
        self._fewshot_cache[category] = {
            "data": examples,
            "timestamp": datetime.now(timezone.utc),
        }

    def clear_expired(self) -> None:
        """Cleanup expired entries."""
        now = datetime.now(timezone.utc)

        expired_subgraph_keys = [
            k for k, v in self._subgraph_cache.items()
            if (now - v["timestamp"]).total_seconds() > self.ttl_seconds
        ]
        for key in expired_subgraph_keys:
            del self._subgraph_cache[key]

        expired_fewshot_keys = [
            k for k, v in self._fewshot_cache.items()
            if (now - v["timestamp"]).total_seconds() > self.ttl_seconds * 24
        ]
        for key in expired_fewshot_keys:
            del self._fewshot_cache[key]


# Global singleton
_shared_cache: Optional[SharedContextCache] = None


def get_shared_cache() -> SharedContextCache:
    """Retrieve or initialize the global SharedContextCache singleton.

    Returns:
        SharedContextCache: Resulting SharedContextCache instance.
    """
    global _shared_cache
    if _shared_cache is None:
        _shared_cache = SharedContextCache()
    return _shared_cache
