"""
adapters_config.py re-exporting core adapters for modular architecture.
"""
from app.core.adapters import (
    create_feedback_config,
    create_repair_config,
    get_feedback_loop,
    get_repair_engine,
    PlatformNeo4jGraphAdapter,
)

__all__ = [
    "create_feedback_config",
    "create_repair_config",
    "get_feedback_loop",
    "get_repair_engine",
    "PlatformNeo4jGraphAdapter",
]
