# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_compliance_alerts.py
===============================
Tests verifying the real-time compliance alerting and escalation system (Gap 6):
1. SLA breach detection across active remediations
2. Multi-tier escalation: L1 Analyst -> L2 Risk Manager -> L3 Chief Compliance Officer
3. 15-minute alert suppression/deduplication window
4. Alert lifecycle: generation -> acknowledgment -> resolution with audit notes
5. REST endpoints for alert query and management
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.main import create_app
from app.compliance.metrics_store import get_metrics_store
from app.schemas.remediation_metrics import RemediationMetrics
from app.schemas.compliance_alert import AlertSeverity, AlertStatus, EscalationTier


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_sla_breach_detection_and_escalation_tiers():
    store = get_metrics_store()
    now = datetime.utcnow()

    # 1. Past due critical violation -> L3 CCO
    crit_rem = RemediationMetrics(
        remediation_id="REM_ALERT_CRIT",
        violation_id="VIO_ALERT_CRIT",
        severity_level="CRITICAL",
        sla_target_hours=24.0,
        sla_target_date=(now - timedelta(hours=2)).isoformat(),  # Overdue
        detected_at=(now - timedelta(hours=26)).isoformat(),
        remediation_action="Restore required margin balance",
        remediation_owner_user_id="lead_analyst",
        created_at=(now - timedelta(hours=26)).isoformat(),
        updated_at=(now - timedelta(hours=26)).isoformat(),
    )
    store.record_remediation(crit_rem)

    alerts = store.detect_sla_breaches_and_generate_alerts()
    crit_alerts = [a for a in alerts if a.violation_id == "VIO_ALERT_CRIT"]
    assert len(crit_alerts) == 1
    assert crit_alerts[0].escalation_tier == EscalationTier.L3_CCO
    assert crit_alerts[0].severity == AlertSeverity.CRITICAL


def test_alert_suppression_window_prevents_duplicate_storms():
    store = get_metrics_store()
    # Running breach detection immediately again must NOT generate duplicate alerts
    second_run = store.detect_sla_breaches_and_generate_alerts()
    crit_duplicate = [a for a in second_run if a.violation_id == "VIO_ALERT_CRIT"]
    assert len(crit_duplicate) == 0  # Cleanly suppressed by 15-minute window!


def test_alert_acknowledgment_and_resolution_endpoints(client):
    # Trigger scan via endpoint
    scan_res = client.post("/api/compliance/alerts/evaluate-breaches")
    assert scan_res.status_code == 200

    # Get active alerts
    list_res = client.get("/api/compliance/alerts?status=ACTIVE")
    assert list_res.status_code == 200
    alerts = list_res.json()
    assert len(alerts) >= 1
    target_alert_id = alerts[0]["alert_id"]

    # Acknowledge alert
    ack_res = client.post(
        f"/api/compliance/alerts/{target_alert_id}/acknowledge",
        json={"user_id": "cco_officer_1"}
    )
    assert ack_res.status_code == 200
    ack_data = ack_res.json()
    assert ack_data["status"] == "ACKNOWLEDGED"
    assert ack_data["acknowledged_by_user_id"] == "cco_officer_1"

    # Resolve alert
    resolve_res = client.post(
        f"/api/compliance/alerts/{target_alert_id}/resolve",
        json={
            "user_id": "cco_officer_1",
            "resolution_notes": "Statutory margin restored; verified by custodian bank.",
        }
    )
    assert resolve_res.status_code == 200
    resolve_data = resolve_res.json()
    assert resolve_data["status"] == "RESOLVED"
    assert resolve_data["resolved_by_user_id"] == "cco_officer_1"
    assert "margin restored" in resolve_data["resolution_notes"]
