"""
Centralized logging configuration for feedback-loop pipeline.

Directory structure:
  logs/
    session_<session_id>/
      <feedback_id>/
        step_1_classification_<timestamp>.log
        step_2_enrichment_<timestamp>.log
        step_3_router_<timestamp>.log
        step_4_adjudication_<timestamp>.log
"""

import logging
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid


from feedback_loop.logging import ensure_log_directory


def _ensure_log_dir(session_id: str, feedback_id: str) -> Path:
    """Create nested log directories: logs/session_<id>/<feedback_id>/

    Args:
        session_id (str): Unique identifier of the session.
        feedback_id (str): Unique identifier of the feedback.

    Returns:
        Path: Resulting Path instance.
    """
    log_base = Path("logs")
    session_dir = log_base / f"session_{session_id}"
    feedback_dir = session_dir / feedback_id
    ensure_log_directory(feedback_dir)
    return feedback_dir


class StepLoggerAdapter(logging.LoggerAdapter):
    """
    Adapter that forwards arbitrary keyword arguments into record extra dict,
    preventing TypeError: Logger._log() got an unexpected keyword argument.
    """
    def process(self, msg, kwargs):
        """Process operation.

        Args:
            msg: The msg.
            kwargs: Keyword arguments.

        Returns:
            Result of the operation.
        """
        standard_kwargs = {"exc_info", "stack_info", "stacklevel", "extra"}
        extra = kwargs.get("extra", {})
        if not isinstance(extra, dict):
            extra = {}
        non_standard = {k: v for k, v in list(kwargs.items()) if k not in standard_kwargs}
        for k in non_standard:
            del kwargs[k]
        extra.update(non_standard)
        kwargs["extra"] = extra
        return msg, kwargs


def get_step_logger(
    step_name: str,
    session_id: str,
    feedback_id: str,
    log_level: int = logging.INFO,
) -> logging.LoggerAdapter:
    """Create a UNIQUE logger for each step with its own file handler.

    Each call creates a fresh logger to ensure separate log files.

    Log files created at:
      logs/session_<session_id>/<feedback_id>/step_<step_name>_<timestamp>.log

    Example:
        logger = get_step_logger("classification", session_id, feedback_id)
        logger.info("NER complete", entity_count=5)

    Args:
        step_name (str): Name of the step.
        session_id (str): Unique identifier of the session.
        feedback_id (str): Unique identifier of the feedback.
        log_level (int): The log level.

    Returns:
        logging.LoggerAdapter: Resulting logging.LoggerAdapter instance.
    """
    log_dir = _ensure_log_dir(session_id, feedback_id)
    
    iso_timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
    log_file = log_dir / f"{step_name}_{iso_timestamp}.log"
    
    # Create a UNIQUE logger for each step call to avoid handler reuse
    unique_logger_name = f"feedback_loop.{step_name}.{feedback_id}.{uuid.uuid4().hex[:8]}"
    logger = logging.getLogger(unique_logger_name)
    
    # Clear any existing handlers to ensure fresh start
    logger.handlers = []
    logger.setLevel(log_level)
    logger.propagate = False  # Don't propagate to root logger
    
    # Create file handler (THIS STEP'S LOG ONLY)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(JSONFormatter(step_name, session_id, feedback_id))
    logger.addHandler(file_handler)
    
    # Create console handler for human-readable output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(f"[{step_name}] %(levelname)s: %(message)s")
    )
    logger.addHandler(console_handler)
    
    return StepLoggerAdapter(logger, {})


class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""
    
    def __init__(self, step_name: str, session_id: str, feedback_id: str):
        """Initialize a new instance of JSONFormatter.

        Args:
            step_name (str): Name of the step.
            session_id (str): Unique identifier of the session.
            feedback_id (str): Unique identifier of the feedback.
        """
        super().__init__()
        self.step_name = step_name
        self.session_id = session_id
        self.feedback_id = feedback_id
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record (logging.LogRecord): The record.

        Returns:
            str: Resulting str instance.
        """
        log_data = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "step": self.step_name,
            "session_id": self.session_id,
            "feedback_id": self.feedback_id,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if not key.startswith("_") and key not in {
                    "name", "msg", "args", "created", "filename", "funcName",
                    "levelname", "levelno", "lineno", "module", "msecs",
                    "message", "pathname", "process", "processName", "relativeCreated",
                    "thread", "threadName", "exc_info", "exc_text", "stack_info"
                }:
                    log_data[key] = value
        
        return json.dumps(log_data, default=str)


STEP_NAMES = {
    "classification": "step_1_classification",
    "enrichment": "step_2_enrichment",
    "router": "step_3_router",
    "adjudication": "step_4_adjudication",
}


def get_pipeline_logger(
    step_key: str,
    session_id: str,
    feedback_id: str,
) -> logging.Logger:
    """Get logger with standardized step naming.

    Args:
        step_key (str): The step key.
        session_id (str): Unique identifier of the session.
        feedback_id (str): Unique identifier of the feedback.

    Returns:
        logging.Logger: Resulting logging.Logger instance.
    """
    step_name = STEP_NAMES.get(step_key, step_key)
    return get_step_logger(step_name, session_id, feedback_id)
