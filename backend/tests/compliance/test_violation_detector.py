# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Unit tests for Violation Detector and Escalation Engine."""
import pytest
from app.compliance.escalation_engine import EscalationEngine
from app.compliance.rules_engine import ComplianceViolation


@pytest.mark.asyncio
async def test_audit_all_funds(violation_detector):
    result = await violation_detector.audit_all_funds(region="SEBI")

    assert result.audit_id.startswith("AUDIT_")
    assert result.total_funds >= 4
    assert result.total_violations >= 1
    assert result.total_rules_evaluated >= 8
    assert "critical" in result.regions["SEBI"]["severity_breakdown"]
    assert "high" in result.regions["SEBI"]["severity_breakdown"]


@pytest.mark.asyncio
async def test_get_violations_and_resolution(violation_detector):
    # Run audit first
    await violation_detector.audit_all_funds(region="SEBI")

    violations = await violation_detector.get_violations(region="SEBI", status="detected")
    assert len(violations) >= 1

    first_v = violations[0]
    resolve_res = await violation_detector.resolve_violation(
        violation_id=first_v.violation_id,
        resolution_action="Portfolio rebalanced within regulatory thresholds.",
    )
    assert resolve_res["status"] == "remediated"
    assert resolve_res["violation_id"] == first_v.violation_id


@pytest.mark.asyncio
async def test_compliance_scorecard(violation_detector):
    await violation_detector.audit_all_funds(region="SEBI")

    scorecard = await violation_detector.get_compliance_scorecard(region="SEBI")
    assert "overall_compliance_score" in scorecard
    assert 0.0 <= scorecard["overall_compliance_score"] <= 100.0
    assert scorecard["total_rules"] >= 8
    assert "violations" in scorecard
    assert scorecard["region"] == "SEBI"


def test_escalation_engine_routing():
    engine = EscalationEngine()

    critical_violation = ComplianceViolation(
        violation_id="V_TEST_CRIT_001",
        rule_id="RULE_PORT_RELATED_001",
        rule_title="Sponsor Exposure",
        fund_id="Adani_Growth_2024",
        severity="critical",
        confidence=0.99,
        actual_value=0.12,
        threshold_value=0.10,
        description="Sponsor group limit breached",
        region="SEBI",
    )

    assignment = engine.route_violation(critical_violation)
    assert assignment.severity == "critical"
    assert "chief_compliance_officer" in assignment.assigned_roles
    assert assignment.requires_board_approval is True
