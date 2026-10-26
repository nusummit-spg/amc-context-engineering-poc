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
    """Returns the current request ID from context if set.

    Returns:
        str: Resulting str instance.
    """
    return request_id_ctx.get()


def get_current_session_id() -> str:
    """Returns the current session ID from context if set.

    Returns:
        str: Resulting str instance.
    """
    return session_id_ctx.get()


def set_correlation_ids(request_id: str, session_id: str = "") -> None:
    """Explicitly sets correlation IDs for the current task/context.

    Args:
        request_id (str): Unique identifier of the request.
        session_id (str): Unique identifier of the session.
    """
    if request_id:
        request_id_ctx.set(request_id)
    if session_id:
        session_id_ctx.set(session_id)


def ensure_log_directory(target_path: Path | str) -> Path:
    """Checks whether the configured log directory exists; if it exists, reuses it.
    If it does not exist, creates it automatically before generating the log file.
    Returns the resolved Path object.

    Args:
        target_path (Path | str): Filesystem path to the target.

    Returns:
        Path: Resulting Path instance.
    """
    p = Path(target_path).resolve()
    # If target has a file extension or ends with .log/.json/.jsonl, target the parent directory
    if p.suffix or p.name.endswith((".log", ".json", ".jsonl")):
        log_dir = p.parent
    else:
        log_dir = p

    try:
        if not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logging.getLogger("app.logging").warning("Could not verify or create log directory %s: %s", log_dir, exc)
    return p


def format_relative_path(pathname: Optional[str], lineno: int) -> str:
    """Formats file path cleanly for terminal and log display.

    Args:
        pathname (Optional[str]): The pathname.
        lineno (int): The lineno.

    Returns:
        str: Resulting str instance.
    """
    if not pathname:
        return f"unknown:{lineno}"
    norm = pathname.replace("\\", "/")
    for anchor in ["/backend/", "/packages/", "/src/"]:
        if anchor in norm:
            idx = norm.find(anchor)
            return f"{norm[idx+1:]}:{lineno}"
    p = Path(pathname)
    return f"{p.name}:{lineno}"


class DetailedConsoleFormatter(logging.Formatter):
    """
    Terminal formatter providing clear execution tracking:
    [TIMESTAMP] | [LEVEL] | [MODULE/COMPONENT] | [STEP: <EXECUTION_STEP>] | [FILE:LINE] - MESSAGE
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format operation.

        Args:
            record (logging.LogRecord): The record.

        Returns:
            str: Resulting str instance.
        """
        # Timestamp with millisecond precision
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Log level
        level_str = record.levelname.ljust(7)

        # Module / Component
        component = getattr(record, "component", None) or record.name

        # Execution Step
        step = getattr(record, "step", None) or getattr(record, "execution_step", None)
        step_part = f"[STEP: {step}]" if step else "[STEP: -]"

        # Corresponding File / Path
        file_path = format_relative_path(record.pathname, record.lineno)

        # Correlation IDs if available
        rid = getattr(record, "request_id", None) or get_current_request_id()
        sid = getattr(record, "session_id", None) or get_current_session_id()
        corr_parts = []
        if rid:
            corr_parts.append(f"rid={rid}")
        if sid:
            corr_parts.append(f"sid={sid}")
        corr_str = f" ({' '.join(corr_parts)})" if corr_parts else ""

        msg = record.getMessage()

        header = f"{now_str} | {level_str} | [{component}] | {step_part} | [{file_path}]"
        formatted_msg = f"{header} - {msg}{corr_str}"

        if record.exc_info:
            formatted_msg += "\n" + self.formatException(record.exc_info)
        return formatted_msg


class DetailedFileFormatter(logging.Formatter):
    """File formatter providing consistent, structured text output for .log files."""

    def format(self, record: logging.LogRecord) -> str:
        """Format operation.

        Args:
            record (logging.LogRecord): The record.

        Returns:
            str: Resulting str instance.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        level_str = record.levelname.ljust(7)
        component = getattr(record, "component", None) or record.name
        step = getattr(record, "step", None) or getattr(record, "execution_step", None)
        step_part = f"[STEP: {step}]" if step else "[STEP: -]"
        file_path = format_relative_path(record.pathname, record.lineno)

        rid = getattr(record, "request_id", None) or get_current_request_id()
        sid = getattr(record, "session_id", None) or get_current_session_id()
        corr_parts = []
        if rid:
            corr_parts.append(f"rid={rid}")
        if sid:
            corr_parts.append(f"sid={sid}")
        corr_str = f" ({' '.join(corr_parts)})" if corr_parts else ""

        msg = record.getMessage()
        header = f"{now_str} | {level_str} | [{component}] | {step_part} | [{file_path}]"
        formatted_msg = f"{header} - {msg}{corr_str}"

        if record.exc_info:
            formatted_msg += "\n" + self.formatException(record.exc_info)
        return formatted_msg


class JSONFormatter(logging.Formatter):
    """Machine-readable structured JSON formatter with correlation IDs, steps, and stack traces."""

    def format(self, record: logging.LogRecord) -> str:
        """Format operation.

        Args:
            record (logging.LogRecord): The record.

        Returns:
            str: Resulting str instance.
        """
        step = getattr(record, "step", None) or getattr(record, "execution_step", None)
        component = getattr(record, "component", None) or record.name
        file_path = format_relative_path(record.pathname, record.lineno)

        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "component": component,
            "step": step,
            "file_path": file_path,
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
                "request_id", "session_id", "component", "step", "execution_step", "file_path"
            }:
                try:
                    # Only include serializable extra values
                    json.dumps(val)
                    log_data[key] = val
                except (TypeError, OverflowError):
                    log_data[key] = str(val)

        return json.dumps(log_data)


def log_step(
    logger: logging.Logger,
    level: int,
    step: str,
    message: str,
    *args,
    component: Optional[str] = None,
    extra: Optional[dict] = None,
    stacklevel: int = 2,
    **kwargs
) -> None:
    """Logs an execution step with clear step identification and file tracing.

    Args:
        logger (logging.Logger): The logger.
        level (int): The level.
        step (str): The step.
        message (str): Message text or payload.
        component (Optional[str]): The component.
        extra (Optional[dict]): The extra.
        stacklevel (int): The stacklevel.
    """
    merged_extra = {"step": step}
    if component:
        merged_extra["component"] = component
    if extra:
        merged_extra.update(extra)
    logger.log(level, message, *args, extra=merged_extra, stacklevel=stacklevel, **kwargs)


def log_step_info(logger: logging.Logger, step: str, message: str, *args, **kwargs) -> None:
    """Log step info.

    Args:
        logger (logging.Logger): The logger.
        step (str): The step.
        message (str): Message text or payload.
    """
    log_step(logger, logging.INFO, step, message, *args, stacklevel=3, **kwargs)


def log_step_warning(logger: logging.Logger, step: str, message: str, *args, **kwargs) -> None:
    """Log step warning.

    Args:
        logger (logging.Logger): The logger.
        step (str): The step.
        message (str): Message text or payload.
    """
    log_step(logger, logging.WARNING, step, message, *args, stacklevel=3, **kwargs)


def log_step_error(logger: logging.Logger, step: str, message: str, *args, **kwargs) -> None:
    """Log step error.

    Args:
        logger (logging.Logger): The logger.
        step (str): The step.
        message (str): Message text or payload.
    """
    log_step(logger, logging.ERROR, step, message, *args, stacklevel=3, **kwargs)


def log_step_debug(logger: logging.Logger, step: str, message: str, *args, **kwargs) -> None:
    """Log step debug.

    Args:
        logger (logging.Logger): The logger.
        step (str): The step.
        message (str): Message text or payload.
    """
    log_step(logger, logging.DEBUG, step, message, *args, stacklevel=3, **kwargs)


def log_v2_query_audit(audit_data: dict, log_dir: Optional[Path | str] = None) -> None:
    """Replicates the legacy query execution audit logger for V2.
    Outputs structured execution audit log to console and persists to
    logs/query_execution_audit_{timestamp}.jsonl.

    Args:
        audit_data (dict): The audit data.
        log_dir (Optional[Path | str]): The log dir.
    """
    timestamp = datetime.now().isoformat()
    audit_data["timestamp"] = timestamp
    if "serving_engine" not in audit_data:
        audit_data["serving_engine"] = "v2"

    query_str = audit_data.get("query", "")
    q_type = str(audit_data.get("query_type", "UNKNOWN")).upper()
    entities = audit_data.get("entities", audit_data.get("entities_resolved", []))
    matched_by = audit_data.get("graph_matched_by", "entity/subgraph")
    graph_nodes = audit_data.get("graph_nodes_count", 0)
    graph_edges = audit_data.get("graph_edges_count", 0)
    vector_hits = audit_data.get("vector_hits_raw", 0)
    vector_bypassed = audit_data.get("vector_bypassed", False)
    cache_hit = audit_data.get("cache_hit", False)
    patches = audit_data.get("patches_applied", 0)
    llm_model = audit_data.get("llm_model", "openai/gpt-oss-120b")
    in_tokens = audit_data.get("input_tokens", 0)
    out_tokens = audit_data.get("output_tokens", 0)

    lat_ner = audit_data.get("latency_ner_ms", 0.0)
    lat_graph = audit_data.get("latency_graph_ms", 0.0)
    lat_vector = audit_data.get("latency_vector_ms", 0.0)
    lat_asm = audit_data.get("latency_assembly_ms", 0.0)
    lat_llm = audit_data.get("latency_llm_ms", 0.0)
    lat_total = audit_data.get("latency_total_ms", 0.0)

    # Legacy-equivalent terminal banner for V2
    print("\n================================================================================", flush=True)
    print(f"  [V2 QUERY AUDIT LOG] {timestamp} (Engine: V2 ContextGraph)", flush=True)
    print("================================================================================", flush=True)
    print(f"  Query             : \"{query_str}\"", flush=True)
    print(f"  Classified Type   : {q_type} (Pillar 1 Intent-Driven Routing)", flush=True)
    print(f"  Entities Resolved : {len(entities)} entities -> {entities[:8] if isinstance(entities, list) else entities}", flush=True)
    print(f"  Graph Traversal   : Matched by '{matched_by}' | {graph_nodes} nodes/facts | {graph_edges} edges", flush=True)
    print(f"  Vector Retrieval  : {vector_hits} candidates | Cache Hit={cache_hit} | Bypassed={vector_bypassed}", flush=True)
    print(f"  Enrichment Mode   : Patches Applied={patches} | Quality Gate={'PASS' if audit_data.get('quality_gate_passed', True) else 'FAIL'}", flush=True)
    print(f"  LLM Model         : {llm_model} | Input Tokens: {in_tokens} | Output Tokens: {out_tokens}", flush=True)
    print(f"  Latencies (ms)    : NER={lat_ner:.1f}ms | Graph={lat_graph:.1f}ms | Vector={lat_vector:.1f}ms | Assembly={lat_asm:.1f}ms | LLM={lat_llm:.1f}ms | Total={lat_total:.1f}ms", flush=True)
    print("================================================================================\n", flush=True)

    # Ensure log directory exists (reused if exists, created if not)
    base_dir = ensure_log_directory(Path(log_dir) if log_dir else Path("logs"))
    target_dir = base_dir if base_dir.is_dir() else base_dir.parent
    safe_ts = timestamp.replace(":", "-")
    audit_file = target_dir / f"query_execution_audit_{safe_ts}.jsonl"
    try:
        with open(audit_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(audit_data, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"  [V2 Audit Log Warning] Could not write to {audit_file.name}: {exc}", flush=True)


def setup_logging(
    level: str = "INFO",
    log_format: str = "text",
    log_file: Optional[str] = None,
    enable_file_logging: bool = True,
    json_log_file: Optional[str] = None,
    enable_json_logging: bool = True,
    log_dir: Optional[str] = None,
) -> None:
    """Sets up root logging with terminal output and persistent file logging (.log and .json).
    Checks whether log directory exists, reusing or automatically creating it.
    Avoids duplicate handler initialization.

    Args:
        level (str): The level.
        log_format (str): The log format.
        log_file (Optional[str]): The log file.
        enable_file_logging (bool): Whether file logging is enabled or satisfied.
        json_log_file (Optional[str]): The json log file.
        enable_json_logging (bool): Whether json logging is enabled or satisfied.
        log_dir (Optional[str]): The log dir.
    """
    root_logger = logging.getLogger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates on reconfiguration
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # 1. Console Handler (ensure UTF-8 safe on Windows platforms)
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    if log_format.lower() == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(DetailedConsoleFormatter())
    root_logger.addHandler(console_handler)

    # Target directory resolution
    base_dir_path = ensure_log_directory(log_dir or "logs")
    effective_dir = base_dir_path if base_dir_path.is_dir() else base_dir_path.parent

    # 2. Persistent Text File Handler (.log format)
    if enable_file_logging:
        target_file = log_file or str(effective_dir / "app.log")
        try:
            log_path = ensure_log_directory(target_file)
            file_handler = RotatingFileHandler(
                str(log_path),
                maxBytes=10 * 1024 * 1024,  # 10 MB per file
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(DetailedFileFormatter())
            root_logger.addHandler(file_handler)
        except Exception as exc:
            root_logger.warning("Could not initialize text file logging at %s: %s", target_file, exc)

    # 3. Persistent JSON / JSONL File Handler (.json / .jsonl format)
    if enable_json_logging:
        target_json = json_log_file or str(effective_dir / "app.jsonl")
        try:
            json_path = ensure_log_directory(target_json)
            json_handler = RotatingFileHandler(
                str(json_path),
                maxBytes=10 * 1024 * 1024,  # 10 MB per file
                backupCount=5,
                encoding="utf-8",
            )
            json_handler.setLevel(log_level)
            json_handler.setFormatter(JSONFormatter())
            root_logger.addHandler(json_handler)
        except Exception as exc:
            root_logger.warning("Could not initialize JSON file logging at %s: %s", target_json, exc)

    # Filter third-party log noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)

    warnings.filterwarnings("ignore", message=r".*unauthenticated requests to the HF Hub.*")
    warnings.filterwarnings("ignore", message=r".*`fitz` API is deprecated.*")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs requests, binds correlation IDs to async context, and records latency."""

    async def dispatch(self, request: Request, call_next):
        """Dispatch.

        Args:
            request (Request): FastAPI request instance.
            call_next: The call next.

        Returns:
            Result of the operation.
        """
        # Extract or generate correlation IDs
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Trace-ID")
            or str(uuid.uuid4())[:8]
        )
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
            response.headers["X-Trace-ID"] = request_id
            response.headers["X-Process-Time"] = f"{int(elapsed_ms)}ms"
            response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
            return response
        finally:
            request_id_ctx.reset(req_token)
            session_id_ctx.reset(sess_token)
