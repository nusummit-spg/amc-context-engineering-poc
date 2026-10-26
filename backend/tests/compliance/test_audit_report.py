# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_audit_report.py
====================
Tests GET /api/compliance/audit-report, metrics, and RBAC via AsyncClient.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient
from app.main import create_app


@pytest.fixture
def app_instance():
    from app.api import deps
    container = deps.init_container()
    mock_g = MagicMock()
    mock_g.run = AsyncMock(return_value=[])
    mock_g.ping = AsyncMock(return_value=True)
    container.graph = mock_g
    if hasattr(container, "rules_engine") and container.rules_engine:
        container.rules_engine.graph = mock_g
    if hasattr(container, "violation_detector") and container.violation_detector:
        container.violation_detector.graph = mock_g
    return create_app()


@pytest.mark.asyncio
async def test_get_agent_metrics_api(app_instance):
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/compliance/agents/metrics?region=SEBI")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert "overall_latency_ms" in data
        assert "PortfolioAgent" in data["agents"]
        assert "GovernanceAgent" in data["agents"]


@pytest.mark.asyncio
async def test_get_audit_report_api(app_instance):
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/compliance/audit-report",
            params={"start_date": "2026-01-01", "end_date": "2026-12-31", "region": "SEBI"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "period" in data
        assert "total_violations" in data
        assert "remediation_rate" in data
        assert "generated_at" in data


@pytest.mark.asyncio
async def test_scorecard_latency_header(app_instance):
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/compliance/scorecard?region=SEBI")
        assert response.status_code == 200
        assert "x-process-time" in response.headers
        assert response.json()["overall_compliance_score"] >= 0.0


@pytest.mark.asyncio
async def test_resolve_violation_rbac(app_instance):
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://test"
    ) as client:
        # Viewer role cannot resolve
        res_viewer = await client.post(
            "/api/compliance/violations/V_TEST_001/resolve",
            json={"resolution_action": "Fixed portfolio weight to 12%"},
            headers={"X-User-Role": "viewer"}
        )
        assert res_viewer.status_code == 403

        # Resolver role can resolve
        res_resolver = await client.post(
            "/api/compliance/violations/V_TEST_001/resolve",
            json={"resolution_action": "Fixed portfolio weight to 12%"},
            headers={"X-User-Role": "resolver"}
        )
        assert res_resolver.status_code == 200
        assert res_resolver.json()["status"] == "remediated"

