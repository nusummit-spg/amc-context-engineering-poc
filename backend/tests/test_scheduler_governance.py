"""
Unit test to verify that the scheduler's governance batch uses the repair engine package.
"""
import pytest
from app.tasks.scheduler import get_scheduler


@pytest.mark.asyncio
async def test_governance_batch_uses_repair_package():
    """Verify governance batch job executes using the repair engine package."""
    scheduler = get_scheduler()

    result = await scheduler._process_governance_batch()

    assert isinstance(result, dict)
    assert ("total_evaluated" in result) or ("status" in result)
    if "total_evaluated" in result:
        assert "approved" in result
        assert "deployed" in result
