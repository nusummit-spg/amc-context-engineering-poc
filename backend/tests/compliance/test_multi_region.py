# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_multi_region.py
====================
Verifies multi-jurisdiction compliance evaluation across SEBI, SEC, and ESMA.
"""
import pytest
from app.compliance.agents.portfolio_agent import PortfolioAgent
from app.compliance.agents.governance_agent import GovernanceAgent
from app.compliance.agents.kyc_agent import KYCAgent
from app.compliance.agents.risk_agent import RiskAgent
from app.compliance.agents.reporting_agent import ReportingAgent
from app.compliance.rules_engine import RulesEngine


@pytest.mark.asyncio
async def test_multi_region_rule_loading():
    engine = RulesEngine()
    await engine.load_rules()

    sebi_rules = await engine.get_applicable_rules(region="SEBI")
    sec_rules = await engine.get_applicable_rules(region="SEC")
    esma_rules = await engine.get_applicable_rules(region="ESMA")

    assert len(sebi_rules) >= 5
    assert len(sec_rules) >= 4
    assert len(esma_rules) >= 3


@pytest.mark.asyncio
async def test_portfolio_agent_sec_5_percent_rule():
    agent = PortfolioAgent()
    # 8% holding violates SEC 5% rule but passes SEBI 15% rule
    fund_data_sec = {
        "fund_id": "SEC_FUND_001",
        "category": "equity_fund",
        "region": "SEC",
        "holdings": {"max_single_holding": 0.08, "max_sector_holding": 0.20},
    }
    sec_res = await agent.audit_fund("SEC_FUND_001", fund_data_sec, region="SEC")
    assert sec_res.compliance_status == "non_compliant"
    assert any("RULE_SEC_PORT_CONC_001" == v.rule_id for v in sec_res.violations)

    fund_data_sebi = {
        "fund_id": "SEBI_FUND_001",
        "category": "equity_fund",
        "region": "SEBI",
        "holdings": {"max_single_holding": 0.08, "max_sector_holding": 0.20},
    }
    sebi_res = await agent.audit_fund("SEBI_FUND_001", fund_data_sebi, region="SEBI")
    assert sebi_res.compliance_status == "compliant"


@pytest.mark.asyncio
async def test_governance_agent_multi_region():
    agent = GovernanceAgent()
    # 45% independent trustees passes SEC (40%) but fails SEBI (50%)
    fund_data = {
        "fund_id": "TEST_FUND_001",
        "category": "equity_fund",
        "independent_trustee_pct": 0.45,
        "manager_certified": 1,
    }
    sebi_res = await agent.audit_fund("TEST_FUND_001", fund_data, region="SEBI")
    assert sebi_res.compliance_status == "non_compliant"

    sec_res = await agent.audit_fund("TEST_FUND_001", fund_data, region="SEC")
    assert sec_res.compliance_status == "compliant"
