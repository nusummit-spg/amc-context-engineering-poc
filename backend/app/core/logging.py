# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS3 — Structured JSON / Text request logging, correlation context, and logger setup."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time
import uuid
import warnings
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Context variables for correlation across asynchronous tasks and modules
request_id_ctx: ContextVar[str] = ContextVar("request_id_ctx", default="")
session_id_ctx: ContextVar[str] = ContextVar("session_id_ctx", default="")


def get_current_request_id() -> str:
    """Returns the current request ID from context if set."""
    return request_id_ctx.get()


def get_current_session_id() -> str:
    """Returns the current session ID from context if set."""
    return session_id_ctx.get()


def set_correlation_ids(request_id: str, session_id: str = "") -> None:
    """Explicitly sets correlation IDs for the current task/context."""
    if request_id:
        request_id_ctx.set(request_id)
    if session_id:
        session_id_ctx.set(session_id)


class JSONFormatter(logging.Formatter):
    """Machine-readable structured JSON formatter with correlation IDs and stack traces."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_current_request_id() or None,
            "session_id": getattr(record, "session_id", None) or get_current_session_id() or None,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields if provided
        for key, val in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName",
                "request_id", "session_id"
            }:
                try:
                    # Only include serializable extra values
                    json.dumps(val)
                    log_data[key] = val
                except (TypeError, OverflowError):
                    log_data[key] = str(val)

        return json.dumps(log_data)


def setup_logging(
    level: str = "INFO",
    log_format: str = "text",
    log_file: Optional[str] = None,
    enable_file_logging: bool = True,
) -> None:
    """Sets up root logging with either text or JSON format and optional file output."""
    root_logger = logging.getLogger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates on reconfiguration
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    if log_format.lower() == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
    root_logger.addHandler(console_handler)

    # File Handler (JSON structured log file for operational auditing)
    if enable_file_logging:
        target_file = log_file or "logs/app.log"
        try:
            log_path = Path(target_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                str(log_path),
                maxBytes=10 * 1024 * 1024,  # 10 MB per file
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(JSONFormatter())
            root_logger.addHandler(file_handler)
        except Exception as exc:
            # Fallback gracefully if directory is non-writable
            root_logger.warning("Could not initialize file logging at %s: %s", target_file, exc)

    # Filter third-party log noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)

    warnings.filterwarnings("ignore", message=r".*unauthenticated requests to the HF Hub.*")
    warnings.filterwarnings("ignore", message=r".*`fitz` API is deprecated.*")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs requests, binds correlation IDs to async context, and records latency."""

    async def dispatch(self, request: Request, call_next):
        # Extract or generate correlation IDs
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        session_id = (
            request.headers.get("X-Session-ID")
            or request.query_params.get("session_id")
            or ""
        )

        # Set context variables for this request task
        req_token = request_id_ctx.set(request_id)
        sess_token = session_id_ctx.set(session_id)

        logger = logging.getLogger("api")
        start = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if elapsed_ms > 1000:
                logger.warning(
                    "[SLOW_REQUEST] rid=%s %s %s -> %s (%.1fms)",
                    request_id,
                    request.method,
                    request.url.path,
                    response.status_code,
                    elapsed_ms,
                )
            else:
                logger.info(
                    "rid=%s %s %s -> %s (%dms)",
                    request_id,
                    request.method,
                    request.url.path,
                    response.status_code,
                    int(elapsed_ms),
                )

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{int(elapsed_ms)}ms"
            response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
            return response
        finally:
            request_id_ctx.reset(req_token)
            session_id_ctx.reset(sess_token)
