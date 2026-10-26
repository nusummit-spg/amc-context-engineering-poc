# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Unit tests for the 5 domain-specific Compliance Agents and Orchestrator."""
import pytest
from app.compliance.agents.governance_agent import GovernanceAgent
from app.compliance.agents.kyc_agent import KYCAgent
from app.compliance.agents.portfolio_agent import PortfolioAgent
from app.compliance.agents.reporting_agent import ReportingAgent
from app.compliance.agents.risk_agent import RiskAgent


@pytest.mark.asyncio
async def test_portfolio_agent(mock_graph, rules_engine):
    agent = PortfolioAgent(mock_graph, rules_engine)
    res = await agent.audit_fund("Adani_Growth_2024")

    assert res.agent_type == "portfolio"
    assert res.compliance_status == "non_compliant"
    assert len(res.violations) >= 1
    assert any(v.rule_id == "RULE_PORT_CONC_001" for v in res.violations)


@pytest.mark.asyncio
async def test_governance_agent(mock_graph, rules_engine):
    agent = GovernanceAgent(mock_graph, rules_engine)

    # Compliant fund
    good_res = await agent.audit_fund(
        "HDFC_Top_100_2024",
        {
            "fund_id": "HDFC_Top_100_2024",
            "category": "equity_fund",
            "manager_certified": True,
            "independent_trustee_pct": 0.65,
        },
    )
    assert good_res.compliance_status == "compliant"
    assert len(good_res.violations) == 0

    # Non-compliant fund (uncertified manager)
    bad_res = await agent.audit_fund(
        "Bad_Fund_2024",
        {
            "fund_id": "Bad_Fund_2024",
            "category": "equity_fund",
            "manager_certified": False,
            "independent_trustee_pct": 0.30,
        },
    )
    assert bad_res.compliance_status == "non_compliant"
    assert len(bad_res.violations) >= 2


@pytest.mark.asyncio
async def test_kyc_agent(mock_graph, rules_engine):
    agent = KYCAgent(mock_graph, rules_engine)

    # KYC expired fund
    res = await agent.audit_fund(
        "HDFC_Top_100_2024",
        {
            "fund_id": "HDFC_Top_100_2024",
            "category": "equity_fund",
            "kyc_days_old": 420,  # >365 days
            "unverified_pep_accounts": 1,  # Critical breach
        },
    )
    assert res.compliance_status == "non_compliant"
    assert len(res.violations) >= 2
    rule_ids = {v.rule_id for v in res.violations}
    assert "RULE_KYC_RECENCY_001" in rule_ids
    assert "RULE_KYC_PEP_001" in rule_ids


@pytest.mark.asyncio
async def test_risk_agent(mock_graph, rules_engine):
    agent = RiskAgent(mock_graph, rules_engine)

    # High VaR and low liquidity buffer
    res = await agent.audit_fund(
        "Risky_Fund_2024",
        {
            "fund_id": "Risky_Fund_2024",
            "category": "equity_fund",
            "cash_buffer_pct": 0.02,  # < 5% minimum
            "daily_var_99": 0.055,  # > 4% maximum
        },
    )
    assert res.compliance_status == "non_compliant"
    assert len(res.violations) >= 2


@pytest.mark.asyncio
async def test_reporting_agent(mock_graph, rules_engine):
    agent = ReportingAgent(mock_graph, rules_engine)

    # Delayed NAV upload
    res = await agent.audit_fund(
        "Late_Fund_2024",
        {
            "fund_id": "Late_Fund_2024",
            "category": "equity_fund",
            "nav_upload_delay_minutes": 45,  # Late upload
        },
    )
    assert res.compliance_status == "non_compliant"
    assert len(res.violations) >= 1
    assert res.violations[0].rule_id == "RULE_REP_NAV_TIME_001"


@pytest.mark.asyncio
async def test_compliance_agent_orchestrator(compliance_orchestrator):
    fund_data = {
        "fund_id": "Adani_Growth_2024",
        "category": "equity_fund",
        "region": "SEBI",
        "holdings": {
            "max_single_holding": 0.18,
            "max_sector_holding": 0.35,
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

    result = await compliance_orchestrator.audit_fund_all_domains("Adani_Growth_2024", fund_data)
    assert result["fund_id"] == "Adani_Growth_2024"
    assert result["overall_status"] == "non_compliant"
    assert result["total_violations"] >= 3
    assert "portfolio" in result["domain_breakdown"]
    assert "governance" in result["domain_breakdown"]
    assert "kyc" in result["domain_breakdown"]
    assert "risk" in result["domain_breakdown"]
    assert "reporting" in result["domain_breakdown"]
    assert result["audit_latency_ms"] >= 0.0
