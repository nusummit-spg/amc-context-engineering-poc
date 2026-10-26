"""
Integration tests for background scheduler jobs.
Verifies all 5 background jobs are registered and executable.
"""
import pytest
from app.tasks.scheduler import get_scheduler

@pytest.mark.integration
def test_background_jobs_registered():
    """Verify all 5 background jobs are registered in the scheduler."""
    scheduler = get_scheduler()

    expected_jobs = [
        "sebi_polling",
        "staleness_check",
        "governance_batch",
        "cache_maintenance",
        "metrics_aggregation",
    ]

    registered_jobs = [job.id for job in scheduler.scheduler.get_jobs()]

    for job_id in expected_jobs:
        assert job_id in registered_jobs, f"Job {job_id} not registered. Available: {registered_jobs}"
        print(f"✓ Job registered: {job_id}")

    print("\n✅ All 5 background jobs registered successfully")

@pytest.mark.asyncio
@pytest.mark.integration
async def test_governance_batch_execution():
    """Trigger governance batch manually and verify structured report."""
    from app.tasks.governance_batch import GovernanceBatch

    batch = GovernanceBatch()
    report = await batch.process(lookback_days=7)

    assert isinstance(report, dict)
    assert "considered" in report
    assert "deployed" in report
    assert "errors" in report
    print(f"✓ Governance batch execution successful: {report}")
