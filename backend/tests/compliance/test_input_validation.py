# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_input_validation.py
========================
Tests strict input validation, edge cases, date boundaries, and health probes.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api import deps
from app.main import create_app
from app.schemas.compliance_models import (
    AuditFundRequest,
    AuditBatchRequest,
    ResolveViolationRequest,
    RegionEnum,
)


@pytest.fixture
def app_instance():
    container = deps.init_container()
    mock_g = MagicMock()
    mock_g.run = AsyncMock(return_value=[])
    mock_g.ping = AsyncMock(return_value=True)
    container.graph = mock_g
    return create_app()


def test_resolve_violation_request_validation():
    # Valid
    req = ResolveViolationRequest(resolution_action="Remediated holding by selling 5%")
    assert req.resolution_action == "Remediated holding by selling 5%"

    # Empty / whitespace only should fail
    with pytest.raises(ValidationError):
        ResolveViolationRequest(resolution_action="   ")

    # Too short (< 3 chars) should fail
    with pytest.raises(ValidationError):
        ResolveViolationRequest(resolution_action="ab")


def test_audit_fund_request_validation():
    # Valid
    req = AuditFundRequest(fund_id="SEBI_FUND_001", region=RegionEnum.SEBI)
    assert req.fund_id == "SEBI_FUND_001"

    # Invalid characters in fund_id
    with pytest.raises(ValidationError):
        AuditFundRequest(fund_id="FUND; DROP TABLE funds;--")

    with pytest.raises(ValidationError):
        AuditFundRequest(fund_id="FUND$$##@!")


@pytest.mark.asyncio
async def test_audit_report_date_validation(app_instance):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid date format
        resp = await client.get("/api/compliance/audit-report?start_date=2024/01/01&end_date=2024/02/01")
        assert resp.status_code == 400
        assert "Invalid date format" in resp.json()["detail"]

        # start_date > end_date
        resp2 = await client.get("/api/compliance/audit-report?start_date=2024-05-01&end_date=2024-01-01")
        assert resp2.status_code == 400
        assert "must be earlier than or equal to end_date" in resp2.json()["detail"]

        # Valid date range
        resp3 = await client.get("/api/compliance/audit-report?start_date=2024-01-01&end_date=2024-05-01")
        assert resp3.status_code == 200
        data = resp3.json()
        assert "remediation_rate" in data


@pytest.mark.asyncio
async def test_compliance_health_probe(app_instance):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/compliance/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "amc-compliance-engine"
        assert data["status"] in ["healthy", "degraded"]
        assert "rule_breakdown_by_region" in data
        assert len(data["active_agents"]) == 5
        assert data["uptime_seconds"] >= 0.0


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint(app_instance):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/compliance/metrics/prometheus")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        text = resp.text
        assert "amc_compliance_score_ratio" in text
        assert "amc_compliance_violations_total" in text
        assert "amc_compliance_uptime_seconds" in text
