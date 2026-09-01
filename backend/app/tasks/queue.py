# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS3 — Async task queue for ingestion jobs (simple asyncio queue, no Celery).

A single background worker consumes jobs so heavy ingestion (LLM extraction)
never blocks API requests. Job status is polled via /ingest/status/{job_id}.
"""
import asyncio
import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("tasks")


@dataclass
class IngestJob:
    job_id: str
    paths: list[Path]
    status: str = "queued"          # queued | running | completed | failed
    docs_done: int = 0
    docs_total: int = 0
    stage: str = "queued"
    errors: list[str] = field(default_factory=list)


class IngestQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[IngestJob] = asyncio.Queue()
        self._jobs: dict[str, IngestJob] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._pipeline = None  # set at startup (avoids import cycle)

    def bind_pipeline(self, pipeline) -> None:
        self._pipeline = pipeline

    def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None

    def enqueue(self, paths: list[Path]) -> IngestJob:
        job = IngestJob(job_id=str(uuid4()), paths=paths, docs_total=len(paths))
        self._jobs[job.job_id] = job
        self._queue.put_nowait(job)
        return job

    def get_job(self, job_id: str) -> Optional[IngestJob]:
        return self._jobs.get(job_id)

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            job.status = "running"
            for path in job.paths:
                job.stage = f"ingesting {path.name}"
                try:
                    await self._pipeline.ingest_file(path)
                    job.docs_done += 1
                except Exception as exc:
                    logger.error("Ingestion failed for %s: %s\n%s",
                                 path.name, exc, traceback.format_exc())
                    job.errors.append(f"{path.name}: {exc}")
            job.status = "failed" if job.errors and job.docs_done == 0 else "completed"
            job.stage = "done"
            self._queue.task_done()


ingest_queue = IngestQueue()
