# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================
# app/feedback/feedback_cache.py
"""
Feedback Status & Category Breakdown Cache (Phase 5).
Provides short-TTL in-memory caching for `GET /api/feedback/status` and `category_breakdown`
keyed by (tenant_id, query_hash/clean_query).
Features:
- High performance point lookup with p95 latency < 50ms warm.
- Reverse-indexed by `issue_id` for instant targeted invalidation on feedback writes,
  status transitions, and repair linkages.
- Real-time telemetry tracking: hits, misses, hit rate %, invalidations, drift size,
  and reconciliation timestamps.
- Thread-safe using threading.Lock.
"""

import hashlib
import logging
import threading
import time
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("app.feedback.feedback_cache")


class FeedbackStatusCache:
    """Thread-safe in-memory cache for feedback status checks."""

    def __init__(self, default_ttl_seconds: float = 10.0):
        """Initialize a new instance of FeedbackStatusCache.

        Args:
            default_ttl_seconds (float): Collection or list of default ttl seconds.
        """
        self._default_ttl: float = default_ttl_seconds
        self._lock = threading.Lock()
        # key -> {"data": dict, "issue_id": Optional[str], "expires_at": float}
        self._cache: Dict[str, Dict[str, Any]] = {}
        # issue_id -> Set[key]
        self._issue_index: Dict[str, Set[str]] = {}

        # Telemetry metrics
        self._hits: int = 0
        self._misses: int = 0
        self._invalidations: int = 0
        self._reconciliations_count: int = 0
        self._last_reconciliation_at: Optional[str] = None
        self._last_drift_size: int = 0

    @staticmethod
    def make_key(tenant_id: Optional[str], query: str) -> str:
        """Make key.

        Args:
            tenant_id (Optional[str]): Unique identifier of the tenant.
            query (str): Search query or input text.

        Returns:
            str: Resulting str instance.
        """
        clean_q = (query or "").strip().lower()
        q_hash = hashlib.md5(clean_q.encode("utf-8")).hexdigest()
        tenant = (tenant_id or "default").strip().lower()
        return f"{tenant}:{q_hash}"

    def get(self, tenant_id: Optional[str], query: str) -> Optional[Dict[str, Any]]:
        """Lookup cached status response for tenant and query. Returns None on miss or expiration.

        Args:
            tenant_id (Optional[str]): Unique identifier of the tenant.
            query (str): Search query or input text.

        Returns:
            Optional[Dict[str, Any]]: Dictionary containing result data or status.
        """
        if not query:
            return None

        key = self.make_key(tenant_id, query)
        now = time.time()

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry["expires_at"] < now:
                # Expired
                self._evict_key_locked(key)
                self._misses += 1
                return None

            self._hits += 1
            # Return fresh copy so callers don't mutate cache internal dictionary
            cached_data = dict(entry["data"])
            cached_data["cached"] = True
            return cached_data

    def set(
        self,
        tenant_id: Optional[str],
        query: str,
        data: Dict[str, Any],
        issue_id: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Cache status response for tenant and query, linked to issue_id for targeted invalidation.

        Args:
            tenant_id (Optional[str]): Unique identifier of the tenant.
            query (str): Search query or input text.
            data (Dict[str, Any]): Input data payload.
            issue_id (Optional[str]): Unique identifier of the issue.
            ttl_seconds (Optional[float]): Collection or list of ttl seconds.
        """
        if not query:
            return

        key = self.make_key(tenant_id, query)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = time.time() + ttl

        # Clean out any temporary/transient fields before storing
        clean_data = {k: v for k, v in data.items() if k != "cached"}

        with self._lock:
            # If key already mapped to an old issue_id, update reverse index
            existing = self._cache.get(key)
            if existing and existing.get("issue_id"):
                old_issue = existing["issue_id"]
                if old_issue in self._issue_index:
                    self._issue_index[old_issue].discard(key)

            self._cache[key] = {
                "data": clean_data,
                "issue_id": issue_id,
                "expires_at": expires_at,
            }

            if issue_id:
                self._issue_index.setdefault(issue_id, set()).add(key)

    def invalidate_issue(self, issue_id: Optional[str]) -> int:
        """Evict all cached query status responses associated with issue_id.

        Args:
            issue_id (Optional[str]): Unique identifier of the issue.

        Returns:
            int: Resulting int instance.
        """
        if not issue_id:
            return 0

        evicted_count = 0
        with self._lock:
            keys = self._issue_index.pop(issue_id, set())
            for key in keys:
                if key in self._cache:
                    del self._cache[key]
                    evicted_count += 1
            self._invalidations += evicted_count

        if evicted_count > 0:
            logger.info(
                "[FEEDBACK_CACHE_INVALIDATED] Purged %d status cache entries for issue_id=%s",
                evicted_count,
                issue_id,
            )
        return evicted_count

    def invalidate_all(self) -> int:
        """Clear the entire cache.

        Returns:
            int: Resulting int instance.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._issue_index.clear()
            self._invalidations += count
        logger.info("[FEEDBACK_CACHE_CLEARED] Flushed all %d entries from feedback cache", count)
        return count

    def record_reconciliation(self, drift_size: int, issues_reconciled: int) -> None:
        """Record reconciliation job telemetry and purge cache to prevent stale counts.

        Args:
            drift_size (int): The drift size.
            issues_reconciled (int): The issues reconciled.
        """
        from datetime import datetime, timezone
        with self._lock:
            self._reconciliations_count += 1
            self._last_drift_size = drift_size
            self._last_reconciliation_at = datetime.now(timezone.utc).isoformat()
            self._cache.clear()
            self._issue_index.clear()

    def get_telemetry(self) -> Dict[str, Any]:
        """Return cache hit/miss stats and reconciliation telemetry.

        Returns:
            Dict[str, Any]: Dictionary containing result data or status.
        """
        with self._lock:
            now = time.time()
            active_entries = sum(1 for e in self._cache.values() if e["expires_at"] >= now)
            total = self._hits + self._misses
            hit_rate = round((self._hits / total) * 100, 2) if total > 0 else 0.0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total,
                "hit_rate_pct": hit_rate,
                "active_entries": active_entries,
                "total_invalidations": self._invalidations,
                "reconciliations_count": self._reconciliations_count,
                "last_reconciliation_at": self._last_reconciliation_at,
                "last_drift_size": self._last_drift_size,
                "default_ttl_seconds": self._default_ttl,
            }

    def reset_metrics(self) -> None:
        """Reset hit/miss telemetry counters (useful for benchmarks & unit tests)."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._invalidations = 0

    def _evict_key_locked(self, key: str) -> None:
        """Evict key locked.

        Args:
            key (str): The key.
        """
        entry = self._cache.pop(key, None)
        if entry and entry.get("issue_id"):
            iss = entry["issue_id"]
            if iss in self._issue_index:
                self._issue_index[iss].discard(key)


_CACHE_INSTANCE: Optional[FeedbackStatusCache] = None
_CACHE_INIT_LOCK = threading.Lock()


def get_feedback_cache() -> FeedbackStatusCache:
    """Singleton getter for FeedbackStatusCache.

    Returns:
        FeedbackStatusCache: Resulting FeedbackStatusCache instance.
    """
    global _CACHE_INSTANCE
    if _CACHE_INSTANCE is None:
        with _CACHE_INIT_LOCK:
            if _CACHE_INSTANCE is None:
                _CACHE_INSTANCE = FeedbackStatusCache(default_ttl_seconds=10.0)
    return _CACHE_INSTANCE
