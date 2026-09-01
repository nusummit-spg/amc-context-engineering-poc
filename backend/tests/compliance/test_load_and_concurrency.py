# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_load_and_concurrency.py
============================
Load and concurrency testing suite simulating 10+ concurrent users and batch fund audits.
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
import pytest
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.compliance.agents.orchestrator import ComplianceAgentOrchestrator
from app.compliance.rules_engine import RulesEngine
from app.main import create_app


@pytest.fixture
def mock_container():
    container = deps.init_container()
    mock_g = MagicMock()
    mock_g.run = AsyncMock(return_value=[])
    mock_g.ping = AsyncMock(return_value=True)
    container.graph = mock_g
    engine = RulesEngine(graph_client=mock_g)
    container.rules_engine = engine
    container.compliance_orchestrator = ComplianceAgentOrchestrator(graph_client=mock_g, rules_engine=engine)
    return container


@pytest.fixture
def app_instance(mock_container):
    return create_app()


@pytest.mark.asyncio
async def test_concurrent_scorecard_requests_sla(app_instance):
    """Simulate 15 concurrent users requesting scorecards simultaneously."""
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Initial request to prime cache
        await client.get("/api/compliance/scorecard?region=SEBI")

        start = time.perf_counter()
        tasks = [
            client.get("/api/compliance/scorecard?region=SEBI")
            for _ in range(15)
        ]
        responses = await asyncio.gather(*tasks)
        elapsed_total_ms = (time.perf_counter() - start) * 1000.0

        for r in responses:
            assert r.status_code == 200
            data = r.json()
            assert "overall_compliance_score" in data

        # Cached responses should return well under 500ms SLA for all 15 requests combined
        assert elapsed_total_ms < 500.0


@pytest.mark.asyncio
async def test_batch_audit_100_funds_sla(mock_container):
    """Verify batch audit of 100 funds completes within <5000ms SLA."""
    orchestrator = mock_container.compliance_orchestrator
    funds = [
        {
            "fund_id": f"PERF_FUND_{i:03d}",
            "fund_name": f"Performance Fund {i}",
            "category": "equity_fund",
            "region": "SEBI",
            "holdings": {"max_single_holding": 0.08, "max_sector_holding": 0.20},
            "manager_certified": True,
            "independent_trustee_pct": 0.60,
            "kyc_days_old": 120,
            "unverified_pep_accounts": 0,
            "cash_buffer_pct": 0.07,
            "daily_var_99": 0.025,
            "nav_upload_delay_minutes": 0,
        }
        for i in range(100)
    ]

    start = time.perf_counter()
    res = await orchestrator.audit_all_funds(funds=funds, region="SEBI", concurrency=20)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert res["total_funds"] == 100
    assert elapsed_ms < 5000.0  # Strict SLA < 5s for 100 funds
