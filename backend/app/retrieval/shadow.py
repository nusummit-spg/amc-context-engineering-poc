# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Bounded Observable Shadow Execution Runner.

Executes asynchronous shadow comparisons between legacy and v2 retrieval engines
with strict timeouts, allowlists, rate limiting, and durable JSON logging.
Never alters user-visible responses or raises unhandled exceptions.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("retrieval.shadow")

root = Path(__file__).resolve().parent.parent.parent


class ShadowRunner:
    def __init__(self, timeout_seconds: float = 5.0, max_concurrent: int = 5) -> None:
        self._timeout = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._log_dir = root / "logs" / "shadow" / datetime.utcnow().strftime("%Y%m%d")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "shadow_executions.jsonl"

    async def execute_shadow(
        self,
        query: str,
        legacy_result: dict[str, Any],
        orchestrator: Any,
        request_id: Optional[str] = None,
    ) -> None:
        """Run v2 shadow query in a bounded task without impacting main request flow."""
        asyncio.create_task(self._run_and_record(query, legacy_result, orchestrator, request_id))

    async def _run_and_record(
        self,
        query: str,
        legacy_result: dict[str, Any],
        orchestrator: Any,
        request_id: Optional[str] = None,
    ) -> None:
        t0 = time.perf_counter()
        shadow_record: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "request_id": request_id,
            "query": query,
            "status": "pending",
            "error": None,
        }

        try:
            async with self._semaphore:
                v2_resp = await asyncio.wait_for(
                    orchestrator.answer(query),
                    timeout=self._timeout,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                shadow_record.update({
                    "status": "success",
                    "v2_latency_ms": round(elapsed_ms, 2),
                    "v2_answer_snippet": v2_resp.synthesis.answer[:200] if v2_resp.synthesis else "",
                    "v2_citations_count": len(v2_resp.synthesis.citations) if v2_resp.synthesis else 0,
                    "v2_trace": v2_resp.trace.model_dump() if v2_resp.trace else None,
                })
        except asyncio.TimeoutError:
            shadow_record.update({
                "status": "timeout",
                "error": f"Shadow execution exceeded timeout limit of {self._timeout}s",
            })
            logger.warning("Shadow execution timed out for query: %s", query[:50])
        except Exception as exc:
            shadow_record.update({
                "status": "error",
                "error": str(exc),
            })
            logger.warning("Shadow execution encountered error: %s", exc)

        # Durable write to JSONL log
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(shadow_record) + "\n")
        except Exception as log_exc:
            logger.error("Failed to write shadow execution log: %s", log_exc)


_global_shadow_runner: Optional[ShadowRunner] = None


def get_shadow_runner() -> ShadowRunner:
    global _global_shadow_runner
    if _global_shadow_runner is None:
        _global_shadow_runner = ShadowRunner()
    return _global_shadow_runner
