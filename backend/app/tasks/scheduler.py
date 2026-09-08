# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
scheduler.py
============
Background Task Scheduler for autonomous lifecycle management and ingestion.
Implements Task 0.3 of the Chief Architect Implementation Plan.
Coordinates:
  - Daily SEBI RSS circular polling
  - Regulatory staleness drift detection
  - Weekly governance feedback batch processing
  - Semantic cache TTL maintenance
  - Hourly metrics aggregation
Supports APScheduler when installed, with a functional stdlib background fallback
that evaluates UTC cron schedules on a ticking daemon thread.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("app.tasks.scheduler")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    HAVE_APSCHEDULER = True
except ImportError:
    HAVE_APSCHEDULER = False
    BackgroundScheduler = None
    CronTrigger = None

# How often the fallback engine wakes up to look for due jobs.
FALLBACK_TICK_SECONDS = 30

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class CronSpec:
    """
    Minimal UTC cron descriptor understood by the fallback engine.

    hour=None means "every hour" (matching APScheduler's CronTrigger(minute=0)),
    day_of_week=None means "every day".
    """

    def __init__(
        self,
        minute: int = 0,
        hour: Optional[int] = None,
        day_of_week: Optional[str] = None,
    ):
        self.minute = minute
        self.hour = hour
        self.day_of_week = day_of_week

    def matches(self, moment: datetime) -> bool:
        if moment.minute != self.minute:
            return False
        if self.hour is not None and moment.hour != self.hour:
            return False
        if self.day_of_week is not None:
            target = _WEEKDAYS.get(self.day_of_week.lower())
            if target is not None and moment.weekday() != target:
                return False
        return True

    def next_run_after(self, moment: datetime) -> datetime:
        """Walk forward minute-by-minute (bounded to 8 days) to the next match."""
        candidate = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(8 * 24 * 60):
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        return moment + timedelta(days=1)

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"CronSpec(minute={self.minute}, hour={self.hour}, dow={self.day_of_week})"


class FallbackJob:
    """Represents a scheduled job in the zero-dependency fallback scheduler."""

    def __init__(
        self,
        job_id: str,
        name: str,
        func: Callable,
        args: Optional[List[Any]] = None,
        cron: Optional[CronSpec] = None,
    ):
        self.id = job_id
        self.name = name
        self.func = func
        self.args = args or []
        self.cron = cron or CronSpec(minute=0)
        self.next_run_time = self.cron.next_run_after(datetime.now(timezone.utc).replace(tzinfo=None))
        self.last_run_time: Optional[datetime] = None
        self.run_count = 0
        self.error_count = 0

    def run(self):
        """Execute the job body, recording success/failure counters."""
        self.last_run_time = datetime.utcnow()
        self.run_count += 1
        try:
            self.func(*self.args)
        except Exception as exc:
            self.error_count += 1
            logger.error("Fallback job %s raised: %s", self.id, exc)
        finally:
            self.next_run_time = self.cron.next_run_after(datetime.utcnow())


class FallbackScheduler:
    """
    Thread-based background scheduler used when APScheduler is not installed.

    Unlike a no-op placeholder, this engine really does fire jobs: a daemon
    thread ticks every FALLBACK_TICK_SECONDS and runs every job whose next
    run time has elapsed.
    """

    def __init__(self, daemon: bool = True, tick_seconds: int = FALLBACK_TICK_SECONDS):
        self.daemon = daemon
        self.tick_seconds = tick_seconds
        self._jobs: Dict[str, FallbackJob] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._wake = threading.Event()

    def add_job(self, func, trigger=None, args=None, id=None, name=None, cron: Optional[CronSpec] = None, **kwargs):
        job = FallbackJob(
            job_id=id or str(len(self._jobs) + 1),
            name=name or id,
            func=func,
            args=args,
            cron=cron,
        )
        self._jobs[job.id] = job
        return job

    def start(self):
        if self._running:
            return
        self._running = True
        self._wake.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="FallbackScheduler",
            daemon=self.daemon,
        )
        self._thread.start()
        logger.info("FallbackScheduler loop started (tick=%ss, %d jobs)", self.tick_seconds, len(self._jobs))

    def _run_loop(self):
        while self._running:
            now = datetime.utcnow()
            for job in list(self._jobs.values()):
                if not self._running:
                    break
                if job.next_run_time and now >= job.next_run_time:
                    logger.info("FallbackScheduler firing job '%s'", job.id)
                    job.run()
            # Interruptible sleep so shutdown() returns promptly.
            self._wake.wait(timeout=self.tick_seconds)
            self._wake.clear()

    def shutdown(self, wait: bool = False):
        self._running = False
        self._wake.set()
        if wait and self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.tick_seconds + 5)
        self._thread = None

    def get_jobs(self) -> List[FallbackJob]:
        return list(self._jobs.values())

    def run_job_now(self, job_id: str) -> bool:
        """Fire a registered job immediately (used by tests and ops tooling)."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.run()
        return True


class TaskScheduler:
    """Production scheduler powered by APScheduler with a working stdlib fallback."""

    def __init__(self):
        if HAVE_APSCHEDULER:
            self.scheduler = BackgroundScheduler(daemon=True)
            logger.info("TaskScheduler initialized with APScheduler engine")
        else:
            self.scheduler = FallbackScheduler(daemon=True)
            logger.warning(
                "APScheduler not installed - using stdlib FallbackScheduler. "
                "Install apscheduler for production-grade cron semantics."
            )

        self._is_running = False
        self._last_results: Dict[str, Dict[str, Any]] = {}
        self._setup_tasks()

    # ── Registration ──────────────────────────────────────────────────────

    def _add_job(self, func: Callable, job_id: str, name: str, cron: CronSpec):
        """Register one job against whichever engine is active."""
        if HAVE_APSCHEDULER:
            kwargs: Dict[str, Any] = {"minute": cron.minute, "timezone": "UTC"}
            if cron.hour is not None:
                kwargs["hour"] = cron.hour
            if cron.day_of_week is not None:
                kwargs["day_of_week"] = cron.day_of_week
            self.scheduler.add_job(
                self._job_wrapper,
                CronTrigger(**kwargs),
                args=[func, job_id],
                id=job_id,
                name=name,
                coalesce=True,
                misfire_grace_time=600,
                replace_existing=True,
            )
        else:
            self.scheduler.add_job(
                self._job_wrapper,
                args=[func, job_id],
                id=job_id,
                name=name,
                cron=cron,
            )
        logger.info("Scheduled job '%s' (%s) at %r UTC", job_id, name, cron)

    def _setup_tasks(self):
        """Register autonomous background jobs."""
        self._add_job(self._poll_sebi_feeds, "sebi_polling", "SEBI RSS Feed Polling", CronSpec(hour=3, minute=0))
        self._add_job(self._check_regulatory_staleness, "staleness_check", "Regulatory Staleness Check", CronSpec(hour=6, minute=0))
        self._add_job(self._process_governance_batch, "governance_batch", "Governance Feedback Batch", CronSpec(day_of_week="fri", hour=9, minute=0))
        self._add_job(self._maintain_caches, "cache_maintenance", "Semantic Cache Maintenance", CronSpec(hour=2, minute=0))
        self._add_job(self._aggregate_metrics, "metrics_aggregation", "Hourly Performance Metrics Aggregation", CronSpec(minute=0))
        logger.info("Registered 5 background tasks in scheduler")

    # ── Execution plumbing ────────────────────────────────────────────────

    def _job_wrapper(self, coro_or_func, job_id: str):
        """Run a job (sync or async) inside the scheduler's worker thread."""
        started = time.perf_counter()
        try:
            if asyncio.iscoroutinefunction(coro_or_func):
                result = asyncio.run(coro_or_func())
            else:
                result = coro_or_func()
            self._last_results[job_id] = {
                "status": "success",
                "result": result,
                "ran_at": datetime.utcnow().isoformat(),
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            return result
        except Exception as exc:
            logger.error("Job %s encountered error: %s", job_id, exc, exc_info=True)
            self._last_results[job_id] = {
                "status": "error",
                "error": str(exc),
                "ran_at": datetime.utcnow().isoformat(),
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            return None

    async def run_job_now(self, job_id: str) -> Dict[str, Any]:
        """Trigger a registered job on demand (ops tooling / tests)."""
        handlers = {
            "sebi_polling": self._poll_sebi_feeds,
            "staleness_check": self._check_regulatory_staleness,
            "governance_batch": self._process_governance_batch,
            "cache_maintenance": self._maintain_caches,
            "metrics_aggregation": self._aggregate_metrics,
        }
        handler = handlers.get(job_id)
        if handler is None:
            raise KeyError(f"Unknown scheduler job '{job_id}'")

        started = time.perf_counter()
        try:
            result = await handler()
            record = {"status": "success", "result": result}
        except Exception as exc:
            logger.error("On-demand job %s failed: %s", job_id, exc, exc_info=True)
            record = {"status": "error", "error": str(exc)}

        record["ran_at"] = datetime.utcnow().isoformat()
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
        self._last_results[job_id] = record
        return record

    # ── Job bodies ────────────────────────────────────────────────────────

    async def _poll_sebi_feeds(self) -> Dict[str, Any]:
        """Poll SEBI RSS feeds for new circulars and trigger ingestion."""
        logger.info("[Job] Starting SEBI feed polling...")
        try:
            from app.engine.sebi_feed_ingester import SEBIFeedIngester

            ingester = SEBIFeedIngester()
            report = await asyncio.to_thread(ingester.run_daily_sebi_poll)
            report = report or {}
            logger.info(
                "SEBI feed polling complete: %d new entries, %d PDFs downloaded, "
                "%d supersessions detected, %d errors",
                len(report.get("new_entries", []) or []),
                report.get("downloaded_count", 0),
                len(report.get("supersessions_detected", []) or []),
                len(report.get("errors", []) or []),
            )
            return report
        except Exception as exc:
            logger.warning("SEBI feed polling failed: %s", exc)
            return {"status": "failed", "error": str(exc)}

    async def _check_regulatory_staleness(self) -> Dict[str, Any]:
        """Check for superseded documents and regulatory staleness drift."""
        logger.info("[Job] Checking regulatory staleness...")
        try:
            from app.engine.staleness_monitor import generate_staleness_alert, run_drift_check

            report = await asyncio.to_thread(run_drift_check)
            report = report or {}
            alerts = report.get("alerts", [])
            if alerts:
                logger.warning("Staleness check raised %d alert(s)", len(alerts))
                try:
                    logger.warning("%s", generate_staleness_alert(report))
                except Exception:
                    pass
            else:
                logger.info("Staleness check completed: no drift detected")
            return report
        except Exception as exc:
            logger.warning("Regulatory staleness check failed: %s", exc)
            return {"status": "failed", "error": str(exc)}

    async def _process_governance_batch(self) -> Dict[str, Any]:
        """Process approved corrections in the weekly governance batch."""
        logger.info("[Job] Running weekly governance feedback batch...")
        try:
            from app.tasks.governance_batch import get_governance_batch

            batch = get_governance_batch()
            report = await batch.process()
            logger.info(
                "Governance batch processed: %d deployed, %d failed, %d skipped",
                report.get("deployed", 0),
                report.get("failed", 0),
                report.get("skipped", 0),
            )
            return report
        except Exception as exc:
            logger.warning("Governance batch failed: %s", exc)
            return {"status": "failed", "error": str(exc)}

    async def _maintain_caches(self) -> Dict[str, Any]:
        """Clean expired entries from the semantic query cache."""
        logger.info("[Job] Performing cache maintenance...")
        try:
            from app.retrieval.cache import get_semantic_cache

            cache = get_semantic_cache()
            before = cache.count() if hasattr(cache, "count") else 0

            if not hasattr(cache, "clear_expired"):
                logger.warning("Semantic cache exposes no clear_expired(); skipping maintenance")
                return {"cleaned": 0, "before": before, "status": "unsupported"}

            cleaned = cache.clear_expired() or 0
            logger.info("Cache maintenance removed %d expired entries (%d remain)", cleaned, before - cleaned)
            return {"cleaned": cleaned, "before": before}
        except Exception as exc:
            logger.warning("Cache maintenance failed: %s", exc)
            return {"status": "failed", "error": str(exc)}

    async def _aggregate_metrics(self) -> Dict[str, Any]:
        """Aggregate hourly operational metrics."""
        logger.info("[Job] Aggregating hourly performance metrics...")
        try:
            from app.core.metrics import get_metrics_store

            summary = get_metrics_store().summary()
            logger.info(
                "Hourly metrics: %d queries, p50 %.1fms / p99 %.1fms, cache hit rate %.1f%%",
                summary.get("count", 0),
                float(summary.get("latency_p50_ms", 0.0) or 0.0),
                float(summary.get("latency_p99_ms", 0.0) or 0.0),
                float(summary.get("cache_hit_rate", 0.0) or 0.0) * 100,
            )
            return summary
        except Exception as exc:
            logger.warning("Metrics aggregation failed: %s", exc)
            return {"status": "failed", "error": str(exc)}

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        """Start the background scheduler."""
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("Background TaskScheduler started (%d jobs)", len(self.scheduler.get_jobs()))

    def stop(self):
        """Stop the background scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Background TaskScheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._is_running

    def get_jobs(self) -> List[Dict[str, Any]]:
        """List registered jobs, next run times, and last execution outcome."""
        jobs = []
        for job in self.scheduler.get_jobs():
            nxt = None
            if getattr(job, "next_run_time", None):
                nxt = job.next_run_time.isoformat()
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": nxt,
                "last_result": self._last_results.get(job.id),
            })
        return jobs


# Global instance
_scheduler_instance: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TaskScheduler()
    return _scheduler_instance
