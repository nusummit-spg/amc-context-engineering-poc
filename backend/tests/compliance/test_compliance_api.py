# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Integration tests for the Compliance REST API endpoints."""
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
async def test_api_compliance_scorecard(app_instance):
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/compliance/scorecard?region=SEBI")
        assert response.status_code == 200
        data = response.json()
        assert "overall_compliance_score" in data
        assert "compliance_percentage" in data
        assert "total_rules" in data
        assert "violations" in data
        assert data["region"] == "SEBI"


@pytest.mark.asyncio
async def test_api_compliance_load_rules(app_instance):
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://test"
    ) as client:
        response = await client.post("/api/compliance/load-rules")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["rules_loaded"] >= 8


@pytest.mark.asyncio
async def test_api_compliance_audit_and_violations(app_instance):
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://test"
    ) as client:
        # 1. Trigger Audit
        audit_resp = await client.post("/api/compliance/audit?region=SEBI")
        assert audit_resp.status_code == 200
        audit_data = audit_resp.json()
        assert audit_data["audit_id"].startswith("AUDIT_")
        assert audit_data["total_funds"] >= 4
        assert audit_data["total_violations"] >= 1

        # 2. Get Violations
        v_resp = await client.get("/api/compliance/violations?region=SEBI&severity=high")
        assert v_resp.status_code == 200
        violations = v_resp.json()
        assert isinstance(violations, list)
        if violations:
            assert all(v["severity"] == "high" for v in violations)

        # 3. Fund Violations
        f_resp = await client.get("/api/compliance/fund/Adani_Growth_2024/violations")
        assert f_resp.status_code == 200
        f_violations = f_resp.json()
        assert isinstance(f_violations, list)

        # 4. Resolve Violation
        if violations:
            v_id = violations[0]["violation_id"]
            res_resp = await client.post(
                f"/api/compliance/violations/{v_id}/resolve",
                json={"resolution_action": "Portfolio rebalanced to 14.5% tech weight."}
            )
            assert res_resp.status_code == 200
            assert res_resp.json()["status"] == "remediated"


@pytest.mark.asyncio
async def test_api_compliance_multi_agent_audit(app_instance):
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://test"
    ) as client:
        payload = {
            "fund_id": "Adani_Growth_2024",
            "fund_data": {
                "fund_id": "Adani_Growth_2024",
                "category": "equity_fund",
                "region": "SEBI",
                "holdings": {
                    "max_single_holding": 0.18,
                    "max_sector_holding": 0.34,
                    "sponsor_group_exposure": 0.12,
                },
                "manager_certified": True,
                "independent_trustee_pct": 0.60,
                "kyc_days_old": 120,
                "unverified_pep_accounts": 0,
                "cash_buffer_pct": 0.06,
                "daily_var_99": 0.03,
                "nav_upload_delay_minutes": 0,
            }
        }
        response = await client.post("/api/compliance/agents/audit", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["fund_id"] == "Adani_Growth_2024"
        assert data["overall_status"] == "non_compliant"
        assert data["total_violations"] >= 3
        assert "domain_breakdown" in data
        assert "portfolio" in data["domain_breakdown"]
        assert "governance" in data["domain_breakdown"]
        assert "kyc" in data["domain_breakdown"]
        assert "risk" in data["domain_breakdown"]
        assert "reporting" in data["domain_breakdown"]
