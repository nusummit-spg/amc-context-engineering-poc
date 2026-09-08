# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_phase0_e2e.py
==================
Comprehensive End-to-End and Unit Test Suite for Phase 0 production readiness:
  - Task 0.1: Human Review Queue (Repository, API, Lifecycle)
  - Task 0.2: NLI Evaluator & Multi-Tier Verdict Generator
  - Task 0.3: Background Scheduler
  - Task 0.4: Input Validation, Rate Limiter, and User Tier Quotas
"""
import asyncio
import time

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from app.main import create_app
from app.db.review_queue_repository import ReviewQueueRepository
from app.schemas.review_queue import ReviewQueueItem, ReviewReason, ReviewStatus, Verdict
from app.evaluation.nli_evaluator import NLIEvaluator
from app.evaluation.verdict_generator import VerdictGenerator
from app.tasks.scheduler import TaskScheduler
from app.core.rate_limiter import SlidingWindowRateLimiter, UserQuotaTracker
from app.schemas.api import QueryRequest


@pytest.fixture
def test_repo(tmp_path):
    """Isolated SQLite repository for test execution."""
    db_file = str(tmp_path / "test_review_queue.db")
    repo = ReviewQueueRepository(db_file)
    return repo


@pytest.fixture
def client():
    """FastAPI TestClient instance."""
    app = create_app()
    return TestClient(app)


# ── Task 0.1: Review Queue Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_queue_lifecycle(test_repo):
    """Test item enqueue, pending retrieval, assignment, approval, and statistics."""
    item = ReviewQueueItem(
        response_id="resp_001",
        query="What is the minimum AUM for debt funds?",
        user_answer="Rs 5 crore",
        reason=ReviewReason.CONFIDENCE_LOW,
        confidence_score=0.35,
    )
    item_id = await test_repo.enqueue(item)
    assert item_id == item.id

    # Unassigned check
    unassigned = await test_repo.get_unassigned(limit=10)
    assert len(unassigned) >= 1
    assert unassigned[0].id == item_id
    assert unassigned[0].status == ReviewStatus.PENDING

    # Assign
    assigned = await test_repo.assign_to_user(item_id, "analyst_1")
    assert assigned is True

    # Pending for user
    pending = await test_repo.get_pending_for_user("analyst_1")
    assert len(pending) == 1
    assert pending[0].assigned_to == "analyst_1"
    assert pending[0].status == ReviewStatus.IN_REVIEW

    # Approve
    approved = await test_repo.approve(
        item_id=item_id,
        verdict="confirmed",
        notes="Verified in SEBI Master Circular",
        reviewer_id="analyst_1"
    )
    assert approved is True

    # Stats
    stats = await test_repo.get_stats(time_range_days=7)
    assert stats["approved"]["count"] == 1
    assert stats["total"] >= 1


@pytest.mark.asyncio
async def test_review_queue_rejection(test_repo):
    """Test rejecting review returns item to pending and resets assignee."""
    item = ReviewQueueItem(
        response_id="resp_002",
        query="Explain liquid fund exit load",
        user_answer="Guaranteed 0% exit load",
        reason=ReviewReason.HALLUCINATION_DETECTED,
        confidence_score=0.20,
    )
    item_id = await test_repo.enqueue(item)
    await test_repo.assign_to_user(item_id, "analyst_2")

    # Reject
    rejected = await test_repo.reject(
        item_id=item_id,
        reason="Needs re-verification from SEBI circular",
        reviewer_id="analyst_2"
    )
    assert rejected is True

    fetched = await test_repo.get_by_id(item_id)
    assert fetched.status == ReviewStatus.PENDING
    assert fetched.assigned_to is None
    assert fetched.rejection_reason == "Needs re-verification from SEBI circular"


def test_review_queue_api_endpoints(client):
    """Test review queue REST API endpoints."""
    headers = {"X-User-ID": "compliance_lead"}

    # 1. Escalate
    esc_resp = client.post(
        "/api/review-queue/escalate",
        json={
            "response_id": "resp_api_test",
            "query": "Is capital guaranteed in equity funds?",
            "user_answer": "Yes, equity funds guarantee 12% returns.",
            "reason": "compliance_violation",
            "confidence_score": 0.15,
        },
        headers=headers,
    )
    assert esc_resp.status_code == 200
    data = esc_resp.json()
    assert "item_id" in data
    item_id = data["item_id"]

    # 2. Get unassigned
    unassigned_resp = client.get("/api/review-queue/unassigned", headers=headers)
    assert unassigned_resp.status_code == 200
    assert any(it["id"] == item_id for it in unassigned_resp.json()["items"])

    # 3. Assign
    assign_resp = client.post(
        f"/api/review-queue/{item_id}/assign",
        json={"user_id": "compliance_lead"},
        headers=headers,
    )
    assert assign_resp.status_code == 200

    # 4. Pending
    pending_resp = client.get("/api/review-queue/pending", headers=headers)
    assert pending_resp.status_code == 200
    assert any(it["id"] == item_id for it in pending_resp.json()["items"])

    # 5. Approve
    app_resp = client.post(
        f"/api/review-queue/{item_id}/approve",
        json={"verdict": "needs_correction", "notes": "Guaranteed returns strictly prohibited"},
        headers=headers,
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "approved"

    # 6. Stats
    stats_resp = client.get("/api/review-queue/stats?days=7", headers=headers)
    assert stats_resp.status_code == 200
    assert stats_resp.json()["total"] >= 1


# ── Task 0.2: NLI Evaluator & Verdict Generator Tests ────────────────────────

def test_nli_entailment():
    """Verify NLI evaluator identifies factual entailment."""
    nli = NLIEvaluator()
    premise = "SEBI circular specifies minimum AUM of Rs. 10 crore for equity fund launch"
    hypothesis = "The minimum AUM requirement for launching an equity fund is Rs. 10 crore"
    label, conf = nli.evaluate(premise, hypothesis)
    assert label == "entailment"
    assert conf > 0.70


def test_nli_contradiction():
    """Verify NLI evaluator flags regulatory and numeric contradictions."""
    nli = NLIEvaluator()
    premise = "SEBI strictly prohibits guaranteed returns on mutual funds"
    hypothesis = "Mutual funds can guarantee 15% annual returns to all investors"
    label, conf = nli.evaluate(premise, hypothesis)
    assert label == "contradiction"
    assert conf > 0.75


def test_nli_batch():
    """Verify batch evaluation."""
    nli = NLIEvaluator()
    p = ["SEBI regulates mutual funds.", "NSE operates stock exchanges."]
    h = ["SEBI is the regulator of mutual funds.", "Mutual funds guarantee 50% profit."]
    results = nli.batch_evaluate(p, h)
    assert len(results) == 2
    assert results[0]["label"] == "entailment"
    assert results[1]["label"] == "contradiction"


@pytest.mark.asyncio
async def test_verdict_generator_tiers():
    """Verify multi-tier verdict generator across rules, NLI, and heuristics."""
    vg = VerdictGenerator()

    # Tier 0 rule match: guaranteed returns
    verdict, meta = await vg.generate_verdict(
        query="What returns can I expect?",
        retrieved_context="Mutual funds are subject to market risks.",
        llm_answer="We guarantee 20% annual returns without loss.",
        confidence_score=0.9,
    )
    assert verdict == Verdict.NEEDS_CORRECTION
    assert meta["tier"] == 0

    # Tier 0 rule match: explicit user hallucination flag
    verdict, meta = await vg.generate_verdict(
        query="Who is the CIO?",
        retrieved_context="John Doe is the Chief Investment Officer.",
        llm_answer="Jane Doe is the CIO.",
        user_feedback="This is a complete hallucination, wrong person.",
        confidence_score=0.8,
    )
    assert verdict == Verdict.NEEDS_CORRECTION
    assert meta["tier"] == 0

    # Tier 1 NLI entailment
    verdict, meta = await vg.generate_verdict(
        query="What is the minimum AUM?",
        retrieved_context="SEBI mandates a minimum AUM of Rs 10 crore for equity schemes.",
        llm_answer="The minimum AUM for equity schemes is Rs 10 crore.",
        confidence_score=0.85,
    )
    assert verdict == Verdict.CONFIRMED

    # Tier 2 Heuristic ambiguous (low score)
    verdict, meta = await vg.generate_verdict(
        query="Generic question",
        retrieved_context="Some broad market information",
        llm_answer="Market sentiment is neutral today.",
        confidence_score=0.25,
    )
    assert verdict == Verdict.AMBIGUOUS
    assert meta["tier"] == 2


# ── Task 0.3: Scheduler Tests ────────────────────────────────────────────────

def test_scheduler_jobs_registration():
    """Verify all 5 scheduled jobs are properly registered."""
    scheduler = TaskScheduler()
    jobs = scheduler.get_jobs()
    job_ids = [j["id"] for j in jobs]
    assert len(jobs) >= 5
    assert "sebi_polling" in job_ids
    assert "staleness_check" in job_ids
    assert "governance_batch" in job_ids
    assert "cache_maintenance" in job_ids
    assert "metrics_aggregation" in job_ids


def test_scheduler_start_stop():
    """Verify scheduler startup and shutdown."""
    scheduler = TaskScheduler()
    scheduler.start()
    assert scheduler._is_running is True
    scheduler.stop()
    assert scheduler._is_running is False


def test_scheduler_jobs_have_future_run_times():
    """Every registered job must advertise when it next runs."""
    scheduler = TaskScheduler()
    for job in scheduler.get_jobs():
        assert job["next_run_time"], f"job {job['id']} has no next_run_time"


def test_cron_spec_matching_and_advance():
    """CronSpec drives the stdlib fallback engine; verify its schedule maths."""
    from datetime import datetime

    from app.tasks.scheduler import CronSpec

    daily_3am = CronSpec(hour=3, minute=0)
    assert daily_3am.matches(datetime(2026, 9, 8, 3, 0))
    assert not daily_3am.matches(datetime(2026, 9, 8, 4, 0))
    assert daily_3am.next_run_after(datetime(2026, 9, 8, 3, 30)) == datetime(2026, 9, 9, 3, 0)

    hourly = CronSpec(minute=0)
    assert hourly.next_run_after(datetime(2026, 9, 8, 3, 30)) == datetime(2026, 9, 8, 4, 0)

    # Friday 09:00 UTC — 2026-09-08 is a Tuesday, so the next run is 2026-09-11.
    weekly = CronSpec(day_of_week="fri", hour=9, minute=0)
    assert weekly.next_run_after(datetime(2026, 9, 8, 10, 0)) == datetime(2026, 9, 11, 9, 0)


def test_fallback_scheduler_actually_fires_due_jobs():
    """Regression: the fallback engine used to register jobs but never run them."""
    from datetime import datetime, timedelta

    from app.tasks.scheduler import CronSpec, FallbackScheduler

    fired = []
    sched = FallbackScheduler(tick_seconds=1)
    job = sched.add_job(lambda: fired.append(1), id="probe", name="probe", cron=CronSpec(minute=0))

    # Make the job overdue, then let one tick of the loop pick it up.
    job.next_run_time = datetime.utcnow() - timedelta(seconds=1)
    sched.start()
    try:
        deadline = time.time() + 5
        while not fired and time.time() < deadline:
            time.sleep(0.1)
    finally:
        sched.shutdown(wait=True)

    assert fired, "FallbackScheduler did not execute an overdue job"
    assert job.run_count >= 1
    assert job.next_run_time > datetime.utcnow()


@pytest.mark.asyncio
async def test_scheduler_run_job_now_reports_outcome():
    """On-demand job execution returns a status record rather than swallowing errors."""
    scheduler = TaskScheduler()
    result = await scheduler.run_job_now("metrics_aggregation")
    assert result["status"] in ("success", "error")
    assert "ran_at" in result and "duration_ms" in result

    with pytest.raises(KeyError):
        await scheduler.run_job_now("no_such_job")


# ── Task 0.4: Input Validation & Rate Limiting Tests ─────────────────────────

def test_sliding_window_rate_limiter():
    """Verify sliding window rate limiter blocks on exceeding limit."""
    limiter = SlidingWindowRateLimiter(default_limit=5, default_window_seconds=10)
    client_ip = "192.168.1.50"

    for _ in range(5):
        allowed, remaining = limiter.is_allowed(client_ip)
        assert allowed is True

    # 6th request should be blocked
    allowed, remaining = limiter.is_allowed(client_ip)
    assert allowed is False
    assert remaining == 0


def test_user_quota_tracker_free_tier():
    """Verify free tier users are capped at 10 requests per hour."""
    tracker = UserQuotaTracker()
    user_id = "free_user_001"

    for _ in range(10):
        allowed, _ = tracker.check_quota(user_id, tier="free")
        assert allowed is True

    # 11th request fails
    allowed, msg = tracker.check_quota(user_id, tier="free")
    assert allowed is False
    assert "limit of 10 queries exceeded" in msg


def test_user_quota_tracker_premium_tier():
    """Verify premium tier users have high limits."""
    tracker = UserQuotaTracker()
    user_id = "prem_user_001"

    for _ in range(25):
        allowed, _ = tracker.check_quota(user_id, tier="premium")
        assert allowed is True


def test_input_validation_sqli_blocked():
    """Verify SQL injection payloads fail validation."""
    with pytest.raises(ValueError, match="Potentially unsafe SQL injection pattern"):
        QueryRequest(query="'; DROP TABLE users; --")

    with pytest.raises(ValueError, match="Potentially unsafe SQL injection pattern"):
        QueryRequest(query="UNION SELECT * FROM information_schema")


def test_input_validation_xss_blocked():
    """Verify script injection payloads fail validation."""
    with pytest.raises(ValueError, match="Script tags and javascript URIs are not permitted"):
        QueryRequest(query="<script>alert('XSS')</script>")


def test_input_validation_repetition_blocked():
    """Verify degenerate repetitive queries are rejected."""
    with pytest.raises(ValueError, match="Query is too repetitive or degenerate"):
        QueryRequest(query="aaaaaaaaaaaaaaaaaaaa")


def test_valid_query_accepted():
    """Verify normal financial query passes validation cleanly."""
    req = QueryRequest(query="What is the minimum AUM requirement for index funds?", mode="contextgraph")
    assert req.query == "What is the minimum AUM requirement for index funds?"
