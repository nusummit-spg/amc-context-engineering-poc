# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
rate_limiter.py
===============
Core Rate Limiting, Sliding Window Token-Bucket, and User Tier Quota Management.
Implements Task 0.4 of the Chief Architect Implementation Plan.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("app.core.rate_limiter")

QUOTA_CONFIG = {
    "free": {
        "queries_per_hour": 10,
        "queries_per_day": 100,
    },
    "premium": {
        "queries_per_hour": 1000,
        "queries_per_day": 10000,
    },
    "enterprise": {
        "queries_per_hour": None,  # Unlimited
        "queries_per_day": None,
    },
    "admin": {
        "queries_per_hour": None,
        "queries_per_day": None,
    }
}


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter per client key (e.g. IP or token)."""

    def __init__(self, default_limit: int = 60, default_window_seconds: int = 60):
        self._default_limit = default_limit
        self._default_window = default_window_seconds
        self._lock = threading.Lock()
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(
        self,
        key: str,
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """
        Check if request is allowed under rate limit.
        Returns: (is_allowed: bool, remaining_requests: int)
        """
        limit = max_requests if max_requests is not None else self._default_limit
        window = window_seconds if window_seconds is not None else self._default_window
        now = time.time()
        window_start = now - window

        with self._lock:
            # Prune expired timestamps
            timestamps = [t for t in self._requests[key] if t > window_start]
            self._requests[key] = timestamps

            if len(timestamps) >= limit:
                return False, 0

            self._requests[key].append(now)
            remaining = limit - len(self._requests[key])
            return True, remaining

    def reset(self, key: Optional[str] = None):
        """Reset limiter state for testing or manual administrative override."""
        with self._lock:
            if key:
                self._requests.pop(key, None)
            else:
                self._requests.clear()


class UserQuotaTracker:
    """Tracks hourly and daily query quotas partitioned by user subscription tiers."""

    def __init__(self):
        self._lock = threading.Lock()
        self.usage: Dict[str, dict] = {}

    def check_quota(self, user_id: str, tier: str = "free") -> Tuple[bool, str]:
        """
        Check if user has exceeded hourly or daily quota.
        Returns: (allowed: bool, reason: str)
        """
        normalized_tier = tier.lower().strip()
        if normalized_tier not in QUOTA_CONFIG:
            normalized_tier = "free"

        quota = QUOTA_CONFIG[normalized_tier]
        now = datetime.utcnow()

        with self._lock:
            if user_id not in self.usage:
                self.usage[user_id] = {
                    "hour_start": now,
                    "day_start": now,
                    "hour_count": 0,
                    "day_count": 0,
                }

            user_data = self.usage[user_id]

            # Reset hourly window if elapsed
            if (now - user_data["hour_start"]).total_seconds() >= 3600:
                user_data["hour_start"] = now
                user_data["hour_count"] = 0

            # Reset daily window if elapsed
            if (now - user_data["day_start"]).total_seconds() >= 86400:
                user_data["day_start"] = now
                user_data["day_count"] = 0

            # Check limits
            h_limit = quota["queries_per_hour"]
            if h_limit is not None and user_data["hour_count"] >= h_limit:
                return False, f"Hourly limit of {h_limit} queries exceeded for tier '{normalized_tier}'"

            d_limit = quota["queries_per_day"]
            if d_limit is not None and user_data["day_count"] >= d_limit:
                return False, f"Daily limit of {d_limit} queries exceeded for tier '{normalized_tier}'"

            # Increment count
            user_data["hour_count"] += 1
            user_data["day_count"] += 1
            return True, "OK"

    def reset(self, user_id: Optional[str] = None):
        """Reset quota tracker counters."""
        with self._lock:
            if user_id:
                self.usage.pop(user_id, None)
            else:
                self.usage.clear()


# Singletons
_rate_limiter = SlidingWindowRateLimiter(default_limit=60, default_window_seconds=60)
_quota_tracker = UserQuotaTracker()


def get_ip_rate_limiter() -> SlidingWindowRateLimiter:
    return _rate_limiter


def get_user_quota_tracker() -> UserQuotaTracker:
    return _quota_tracker


def check_user_quota(user_id: str, tier: str = "free") -> Tuple[bool, str]:
    return _quota_tracker.check_quota(user_id, tier)
