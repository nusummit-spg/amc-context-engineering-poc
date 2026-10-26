"""
Simple logging helper that uses structlog context binding.

Instead of creating separate loggers, we bind context to structlog
which handles file writing automatically if configured.

Usage:
    from feedback_loop.logging_config_simple import bind_logging_context
    
    bind_logging_context("classification", session_id, feedback_id)
    logger.info("NER complete", entity_count=5)
"""

import structlog
from pathlib import Path
from datetime import datetime, timezone


def setup_file_logging():
    """Configure structlog to write to files.

    Returns:
        Result of the operation.
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    return log_dir


def bind_logging_context(step_name: str, session_id: str, feedback_id: str):
    """Bind step context to structlog.

    This adds step, session_id, and feedback_id to all log records
    and enables file output to logs/session_<id>/<step>_<id>_<timestamp>.log

    Usage:
        bind_logging_context("classification", session_id, feedback_id)
        logger = structlog.get_logger()
        logger.info("Starting NER", text_length=len(text))

    Args:
        step_name (str): Name of the step.
        session_id (str): Unique identifier of the session.
        feedback_id (str): Unique identifier of the feedback.

    Returns:
        Result of the operation.
    """
    iso_timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
    log_dir = setup_file_logging()
    session_dir = log_dir / f"session_{session_id}"
    session_dir.mkdir(exist_ok=True)
    
    log_file = session_dir / f"{step_name}_{feedback_id}_{iso_timestamp}.log"
    
    # Return the context dict that should be used for binding
    return {
        "step": step_name,
        "session_id": session_id,
        "feedback_id": feedback_id,
        "log_file": str(log_file),
    }


# Convenience function
def create_step_logger(step_name: str, session_id: str, feedback_id: str):
    """Create and bind a logger for a pipeline step.

    Usage:
        logger = create_step_logger("classification", session_id, feedback_id)
        logger = structlog.get_logger()
        logger.info("NER complete", entity_count=5)

    Args:
        step_name (str): Name of the step.
        session_id (str): Unique identifier of the session.
        feedback_id (str): Unique identifier of the feedback.

    Returns:
        Result of the operation.
    """
    context = bind_logging_context(step_name, session_id, feedback_id)
    logger = structlog.get_logger()
    return logger.bind(**context)
