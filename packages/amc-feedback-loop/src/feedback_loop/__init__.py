"""
Human Feedback Loop module — public API surface.

The host application only needs to import from this module:

    from feedback_loop import start_feedback_loop, FeedbackLoopConfig
    from feedback_loop.adapters import AbstractDatabaseAdapter, AbstractEvidenceAdapter
"""

from feedback_loop.api import start_feedback_loop
from feedback_loop.config import DEFAULT_ATTRIBUTE_KEYWORDS, FeedbackConfig, FeedbackLoopConfig
from feedback_loop.loop import (
    FeedbackLoop,
    FollowUpDetectionRequest,
    FollowUpDetectionResult,
    SQLiteAdapter,
    StructuredClaim,
)
from feedback_loop.logging import (
    DetailedConsoleFormatter,
    DetailedFileFormatter,
    JSONFormatter,
    ensure_log_directory,
    get_feedback_logger,
    log_step,
    log_step_debug,
    log_step_error,
    log_step_info,
    log_step_warning,
    setup_feedback_logging,
)

__all__ = [
    "start_feedback_loop",
    "FeedbackLoopConfig",
    "FeedbackConfig",
    "DEFAULT_ATTRIBUTE_KEYWORDS",
    "FeedbackLoop",
    "SQLiteAdapter",
    "StructuredClaim",
    "FollowUpDetectionRequest",
    "FollowUpDetectionResult",
    "setup_feedback_logging",
    "get_feedback_logger",
    "ensure_log_directory",
    "log_step",
    "log_step_info",
    "log_step_warning",
    "log_step_error",
    "log_step_debug",
    "DetailedConsoleFormatter",
    "DetailedFileFormatter",
    "JSONFormatter",
]
