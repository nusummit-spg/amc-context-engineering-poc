# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
logging.py — Comprehensive, consistent logging mechanism for AMC Feedback Loop.
Provides terminal execution tracing with log level, timestamp, module/component,
execution step, file/path, and persistent file logging (.log and .json).
"""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


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
    if p.suffix or p.name.endswith((".log", ".json", ".jsonl")):
        log_dir = p.parent
    else:
        log_dir = p

    try:
        if not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logging.getLogger("feedback_loop").warning(
            "Could not verify or create log directory %s: %s", log_dir, exc
        )
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
    for anchor in ["/packages/", "/backend/", "/src/"]:
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
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level_str = record.levelname.ljust(7)
        component = getattr(record, "component", None) or record.name
        step = getattr(record, "step", None) or getattr(record, "execution_step", None)
        step_part = f"[STEP: {step}]" if step else "[STEP: -]"
        file_path = format_relative_path(record.pathname, record.lineno)

        msg = record.getMessage()
        header = f"{now_str} | {level_str} | [{component}] | {step_part} | [{file_path}]"
        formatted_msg = f"{header} - {msg}"

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

        msg = record.getMessage()
        header = f"{now_str} | {level_str} | [{component}] | {step_part} | [{file_path}]"
        formatted_msg = f"{header} - {msg}"

        if record.exc_info:
            formatted_msg += "\n" + self.formatException(record.exc_info)
        return formatted_msg


class JSONFormatter(logging.Formatter):
    """Machine-readable structured JSON formatter for feedback loop."""

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
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        for key, val in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName",
                "component", "step", "execution_step", "file_path"
            }:
                try:
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
    elif not getattr(logger, "name", "").startswith("feedback_loop"):
        merged_extra["component"] = "feedback_loop"
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


_logging_initialized = False


def setup_feedback_logging(
    level: str = "INFO",
    log_format: str = "text",
    log_file: Optional[str] = None,
    enable_file_logging: bool = True,
    json_log_file: Optional[str] = None,
    enable_json_logging: bool = True,
    log_dir: Optional[str] = None,
) -> None:
    """Sets up Feedback Loop logging with console output and persistent file logging (.log and .json).
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
    global _logging_initialized

    feedback_logger = logging.getLogger("feedback_loop")
    log_level = getattr(logging, level.upper(), logging.INFO)
    feedback_logger.setLevel(log_level)

    # Clear existing handlers to prevent duplicates
    for handler in list(feedback_logger.handlers):
        feedback_logger.removeHandler(handler)

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
    feedback_logger.addHandler(console_handler)

    # Determine log directory
    env_log_dir = os.getenv("FEEDBACK_LOG_DIR") or os.getenv("LOG_DIR")
    # Priority: passed log_dir -> env var -> backend/logs (if exists) -> logs
    default_dir = "logs"
    if not (log_dir or env_log_dir):
        candidate_backend = Path("backend/logs")
        if candidate_backend.exists() and candidate_backend.is_dir():
            default_dir = "backend/logs"
        elif Path("../../backend/logs").exists():
            default_dir = "../../backend/logs"

    target_dir_str = log_dir or env_log_dir or default_dir
    base_dir_path = ensure_log_directory(target_dir_str)
    effective_dir = base_dir_path if base_dir_path.is_dir() else base_dir_path.parent

    # 2. Text File Handler (.log format)
    if enable_file_logging:
        target_file = log_file or os.getenv("FEEDBACK_LOG_FILE") or str(effective_dir / "feedback_loop.log")
        try:
            log_path = ensure_log_directory(target_file)
            file_handler = RotatingFileHandler(
                str(log_path),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(DetailedFileFormatter())
            feedback_logger.addHandler(file_handler)
        except Exception as exc:
            feedback_logger.warning("Could not initialize text file logging at %s: %s", target_file, exc)

    # 3. JSON File Handler (.json / .jsonl format)
    if enable_json_logging:
        target_json = json_log_file or os.getenv("FEEDBACK_JSON_LOG_FILE") or str(effective_dir / "feedback_loop.jsonl")
        try:
            json_path = ensure_log_directory(target_json)
            json_handler = RotatingFileHandler(
                str(json_path),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            json_handler.setLevel(log_level)
            json_handler.setFormatter(JSONFormatter())
            feedback_logger.addHandler(json_handler)
        except Exception as exc:
            feedback_logger.warning("Could not initialize JSON file logging at %s: %s", target_json, exc)

    _logging_initialized = True


def get_feedback_logger(name: str = "feedback_loop") -> logging.Logger:
    """Returns a logger namespaced under feedback_loop to share root configuration.

    Args:
        name (str): Name of the entity or component.

    Returns:
        logging.Logger: Resulting logging.Logger instance.
    """
    if not _logging_initialized:
        setup_feedback_logging()
    if name.startswith("feedback_loop"):
        return logging.getLogger(name)
    return logging.getLogger(f"feedback_loop.{name}")
