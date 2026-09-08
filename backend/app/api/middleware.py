# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
middleware.py
=============
FastAPI Middlewares for Rate Limiting, User Quota Enforcement, and Request Auditing.
Implements Task 0.4 of the Chief Architect Implementation Plan.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.rate_limiter import check_user_quota, get_ip_rate_limiter

logger = logging.getLogger("app.api.middleware")

# Paths exempt from rate limits
EXEMPT_PREFIXES = (
    "/health",
    "/metrics",
    "/api/metrics",
    "/api/status",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static",
    "/files",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces both IP-level sliding window and user tier-based quotas."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Fast bypass for operational and documentation endpoints
        if any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
            return await call_next(request)

        # 1. IP-level rate limiting
        client_ip = "127.0.0.1"
        if request.client and request.client.host:
            client_ip = request.client.host

        ip_limiter = get_ip_rate_limiter()
        allowed_ip, remaining = ip_limiter.is_allowed(client_ip)
        if not allowed_ip:
            logger.warning("IP rate limit exceeded for %s on %s", client_ip, path)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "IP rate limit exceeded. Please slow down your requests.",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )

        # 2. User tier-based quota checking (if calling /api/query, /api/chat)
        if path.startswith("/api/query") or path.startswith("/api/chat"):
            user_id = request.headers.get("X-User-ID")
            tier = request.headers.get("X-User-Tier", "free")

            if user_id:
                allowed_quota, quota_message = check_user_quota(user_id, tier)
                if not allowed_quota:
                    logger.warning("User quota exceeded for user=%s (tier=%s): %s", user_id, tier, quota_message)
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": quota_message,
                            "user_id": user_id,
                            "tier": tier,
                            "retry_after": 3600,
                        },
                        headers={"Retry-After": "3600"},
                    )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


class ValidationMiddleware(BaseHTTPMiddleware):
    """Request logging and tracing middleware."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - t0) * 1000

        # Log slow or non-200 responses
        if response.status_code >= 400 or latency_ms > 1000:
            logger.info(
                "[%s] %s -> status=%d (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                latency_ms,
            )

        response.headers["X-Process-Time-Ms"] = f"{latency_ms:.2f}"
        return response
