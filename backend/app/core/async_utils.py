# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
async_utils.py
==============
Utilities for robust async task management, background task error handling,
and safe coroutine execution across varied event loop contexts.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, Optional

logger = logging.getLogger("app.core.async_utils")


def create_task_with_logging(
    coro: Coroutine[Any, Any, Any],
    task_name: Optional[str] = None,
    custom_logger: Optional[logging.Logger] = None,
) -> asyncio.Task:
    """Create a background asyncio task with an automatic error callback.

    Ensures that unexpected exceptions raised in fire-and-forget background tasks
    are logged with full traceback rather than disappearing silently.

    Args:
        coro: The coroutine to execute.
        task_name: Optional descriptive label for the task.
        custom_logger: Optional custom logger instance.

    Returns:
        asyncio.Task: The created and scheduled task.
    """
    log = custom_logger or logger
    name = task_name or getattr(coro, "__qualname__", "background_task")
    task = asyncio.create_task(coro, name=name)

    def _done_callback(t: asyncio.Task) -> None:
        try:
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    log.error(
                        "Background task '%s' failed with exception: %s",
                        name,
                        exc,
                        exc_info=exc,
                    )
        except Exception as cb_err:
            log.warning("Error in done callback for task '%s': %s", name, cb_err)

    task.add_done_callback(_done_callback)
    return task
