# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS3 — Structured error responses, exception handlers, and error tracking."""
from collections import deque
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("core.errors")


class ErrorTracker:
    """In-memory error rate and error occurrence tracker for observability."""

    def __init__(self, max_recent: int = 50):
        self.total_requests: int = 0
        self.errors_4xx: int = 0
        self.errors_5xx: int = 0
        self.recent_errors: deque = deque(maxlen=max_recent)

    def record_request(self) -> None:
        self.total_requests += 1

    def record_error(
        self,
        status_code: int,
        error_code: str,
        message: str,
        path: str = "",
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        if 400 <= status_code < 500:
            self.errors_4xx += 1
        elif status_code >= 500:
            self.errors_5xx += 1

        self.recent_errors.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status_code": status_code,
            "error_code": error_code,
            "message": message,
            "path": path,
            "detail": detail or {},
        })

    def summary(self) -> Dict[str, Any]:
        total_errors = self.errors_4xx + self.errors_5xx
        error_rate = round(total_errors / self.total_requests, 4) if self.total_requests > 0 else 0.0
        return {
            "total_requests": self.total_requests,
            "errors_4xx": self.errors_4xx,
            "errors_5xx": self.errors_5xx,
            "total_errors": total_errors,
            "error_rate": error_rate,
            "recent_errors": list(self.recent_errors),
        }

    def clear(self) -> None:
        self.total_requests = 0
        self.errors_4xx = 0
        self.errors_5xx = 0
        self.recent_errors.clear()


_error_tracker: Optional[ErrorTracker] = None


def get_error_tracker() -> ErrorTracker:
    global _error_tracker
    if _error_tracker is None:
        _error_tracker = ErrorTracker()
    return _error_tracker


class AppError(Exception):
    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, detail: dict | None = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"


class ValidationFailedError(AppError):
    status_code = 422
    error_code = "validation_failed"


class UpstreamError(AppError):
    """Neo4j / Qdrant / LLM dependency failure."""
    status_code = 502
    error_code = "upstream_error"


class ContextQualityError(AppError):
    """Raised when assembled context fails the quality gate (WS5d)."""
    status_code = 422
    error_code = "context_quality_gate_failed"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    tracker = get_error_tracker()
    tracker.record_error(
        status_code=exc.status_code,
        error_code=exc.error_code,
        message=exc.message,
        path=str(request.url.path),
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "detail": exc.detail,
                "path": str(request.url.path),
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception on %s %s: %s", request.method, request.url.path, exc)
    tracker = get_error_tracker()
    tracker.record_error(
        status_code=500,
        error_code="internal_server_error",
        message=str(exc) or "An unexpected internal server error occurred.",
        path=str(request.url.path),
        detail={"exception_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "An unexpected internal server error occurred.",
                "detail": {"exception_type": type(exc).__name__},
                "path": str(request.url.path),
            }
        },
    )
