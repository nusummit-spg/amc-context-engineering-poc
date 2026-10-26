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
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("tasks")


@dataclass
class IngestJob:
    job_id: str
    paths: list[Path]
    status: str = "queued"          # queued | running | completed | failed | rejected
    docs_done: int = 0
    docs_total: int = 0
    stage: str = "queued"
    errors: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class IngestQueue:
    def __init__(self, max_queue_size: int = 100, max_job_history: int = 1000) -> None:
        """Initialize a new instance of IngestQueue.
        
        Args:
            max_queue_size (int): Maximum number of jobs in queue (prevents unbounded growth)
            max_job_history (int): Maximum number of completed jobs to keep in memory
        """
        self._queue: asyncio.Queue[IngestJob] = asyncio.Queue(maxsize=max_queue_size)
        self._jobs: OrderedDict[str, IngestJob] = OrderedDict()
        self._max_job_history = max_job_history
        self._worker_task: Optional[asyncio.Task] = None
        self._pipeline = None  # set at startup (avoids import cycle)

    def bind_pipeline(self, pipeline) -> None:
        """Bind pipeline.

        Args:
            pipeline: The pipeline.
        """
        self._pipeline = pipeline

    def start(self) -> None:
        """Start operation.
        """
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Stop worker task gracefully with timeout."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as exc:
                logger.warning("Error stopping ingest queue worker: %s", exc)
            finally:
                self._worker_task = None

    def enqueue(self, paths: list[Path]) -> IngestJob:
        """Enqueue.

        Args:
            paths (list[Path]): Collection or list of paths.

        Returns:
            IngestJob: Resulting IngestJob instance.
        """
        job = IngestJob(job_id=str(uuid4()), paths=paths, docs_total=len(paths))
        
        # Prune old completed jobs before adding new (LRU eviction)
        while len(self._jobs) >= self._max_job_history:
            oldest_id, oldest_job = self._jobs.popitem(last=False)
            logger.info("Pruned old job from history: %s (status=%s)", oldest_id, oldest_job.status)
        
        self._jobs[job.job_id] = job
        
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            job.status = "rejected"
            job.errors.append("Queue full - too many pending jobs. Try again later.")
            logger.error("Ingest queue full (%d jobs), rejecting job %s", self._queue.qsize(), job.job_id)
        
        return job

    def get_job(self, job_id: str) -> Optional[IngestJob]:
        """Retrieve job.

        Args:
            job_id (str): Unique identifier of the job.

        Returns:
            Optional[IngestJob]: Matching object or record if found, None otherwise.
        """
        return self._jobs.get(job_id)

    async def _worker(self) -> None:
        """Worker.
        """
        while True:
            try:
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
                
            except Exception as worker_exc:
                logger.error("Ingest worker error: %s", worker_exc, exc_info=True)
                await asyncio.sleep(5)  # Backoff before retry
            job.status = "failed" if job.errors and job.docs_done == 0 else "completed"
            job.stage = "done"
            self._queue.task_done()


ingest_queue = IngestQueue()
