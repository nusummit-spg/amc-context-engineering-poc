# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Unit tests for the deterministic Compliance Rules Engine."""
import pytest
from app.compliance.rules_engine import ComplianceViolation, RulesEngine


def test_parse_condition():
    engine = RulesEngine(None)

    metric, op, thresh = engine._parse_condition("holdings.max_single_holding > 0.15")
    assert metric == "holdings.max_single_holding"
    assert op == "gt"
    assert thresh == 0.15

    metric, op, thresh = engine._parse_condition("manager_certified != 1")
    assert metric == "manager_certified"
    assert op == "neq"
    assert thresh == 1

    metric, op, thresh = engine._parse_condition("independent_trustee_pct < 0.50")
    assert metric == "independent_trustee_pct"
    assert op == "lt"
    assert thresh == 0.50


@pytest.mark.asyncio
async def test_evaluate_rule_concentration_violation(rules_engine):
    fund_data = {
        "fund_id": "Adani_Growth_2024",
        "category": "equity_fund",
        "holdings": {
            "max_single_holding": 0.18  # 18% > 15% limit
        },
        "region": "SEBI",
    }

    violation = await rules_engine.evaluate_rule("RULE_PORT_CONC_001", fund_data)
    assert violation is not None
    assert violation.severity == "high"
    assert violation.actual_value == 0.18
    assert violation.threshold_value == 0.15
    assert violation.rule_id == "RULE_PORT_CONC_001"


@pytest.mark.asyncio
async def test_evaluate_rule_no_violation(rules_engine):
    fund_data = {
        "fund_id": "HDFC_Top_100_2024",
        "category": "equity_fund",
        "holdings": {
            "max_single_holding": 0.09  # 9% < 15% limit
        },
        "region": "SEBI",
    }

    violation = await rules_engine.evaluate_rule("RULE_PORT_CONC_001", fund_data)
    assert violation is None


@pytest.mark.asyncio
async def test_evaluate_rule_exclusion(rules_engine):
    fund_data = {
        "fund_id": "ICICI_Tech_Sector_2024",
        "category": "sector_fund",  # Excluded from standard concentration cap
        "holdings": {
            "max_single_holding": 0.25,
            "max_sector_holding": 0.45,
        },
        "region": "SEBI",
    }

    violation = await rules_engine.evaluate_rule("RULE_PORT_CONC_001", fund_data)
    assert violation is None  # Excluded category


@pytest.mark.asyncio
async def test_evaluate_rule_manager_certification(rules_engine):
    fund_data = {
        "fund_id": "Adani_Growth_2024",
        "category": "equity_fund",
        "manager_certified": False,  # Breaches certification rule
        "region": "SEBI",
    }

    violation = await rules_engine.evaluate_rule("RULE_GOV_MGR_CERT_001", fund_data)
    assert violation is not None
    assert violation.severity == "high"
    assert violation.rule_id == "RULE_GOV_MGR_CERT_001"


@pytest.mark.asyncio
async def test_evaluate_fund_multiple_rules(rules_engine):
    fund_data = {
        "fund_id": "Adani_Growth_2024",
        "category": "equity_fund",
        "holdings": {
            "max_single_holding": 0.18,  # Violates RULE_PORT_CONC_001
            "max_sector_holding": 0.35,  # Violates RULE_PORT_SECTOR_001
            "sponsor_group_exposure": 0.12,  # Violates RULE_PORT_RELATED_001
        },
        "manager_certified": True,
        "independent_trustee_pct": 0.60,
        "kyc_days_old": 100,
        "unverified_pep_accounts": 0,
        "cash_buffer_pct": 0.07,
        "daily_var_99": 0.02,
        "nav_upload_delay_minutes": 0,
        "region": "SEBI",
    }

    violations = await rules_engine.evaluate_fund("Adani_Growth_2024", fund_data)
    assert len(violations) >= 3
    rule_ids = {v.rule_id for v in violations}
    assert "RULE_PORT_CONC_001" in rule_ids
    assert "RULE_PORT_SECTOR_001" in rule_ids
    assert "RULE_PORT_RELATED_001" in rule_ids


def test_violation_to_dict():
    violation = ComplianceViolation(
        violation_id="V_20240115_001",
        rule_id="RULE_PORT_CONC_001",
        rule_title="Concentration Limit",
        fund_id="Adani_Growth_2024",
        severity="high",
        confidence=0.95,
        actual_value=0.18,
        threshold_value=0.15,
        description="Technology 18% > 15% limit",
        evidence_docs=["NAV_20240115.csv"],
        detected_at="2024-01-15T10:30:00Z",
        region="SEBI",
    )

    d = violation.to_dict()
    assert d["violation_id"] == "V_20240115_001"
    assert d["severity"] == "high"
    assert d["actual_value"] == 0.18
    assert d["threshold_value"] == 0.15
    assert d["status"] == "detected"


@pytest.mark.asyncio
async def test_store_violations(rules_engine):
    violation = ComplianceViolation(
        violation_id="V_STORE_TEST_001",
        rule_id="RULE_PORT_CONC_001",
        rule_title="Concentration Limit",
        fund_id="Adani_Growth_2024",
        severity="high",
        confidence=0.95,
        actual_value=0.18,
        threshold_value=0.15,
        description="Breach test",
    )

    count = await rules_engine.store_violations([violation])
    assert count == 1
    assert "V_STORE_TEST_001" in rules_engine._violations_cache
