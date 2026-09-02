# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_phase3_schemas.py
============================
Unit tests for the 3 Phase 3 Dashboard Layer Pydantic schemas:
1. AuditTrailAccessMetrics
2. RealTimeMonitoringMetrics
3. ComplianceDashboardKPIs
"""

import pytest
from pydantic import ValidationError

from app.schemas.audit_trail_access import AuditTrailAccessMetrics
from app.schemas.realtime_monitoring import RealTimeMonitoringMetrics
from app.schemas.compliance_dashboard_kpis import ComplianceDashboardKPIs


# ---------------------------------------------------------------------------
# 1. AuditTrailAccessMetrics Schema Tests
# ---------------------------------------------------------------------------

def test_audit_trail_access_valid():
    log = AuditTrailAccessMetrics(
        access_log_id="LOG_TEST_001",
        user_id="user_compliance_lead",
        user_role="COMPLIANCE_OFFICER",
        resource_accessed="FUND_001_TER_TABLE",
        access_purpose="SEBI_INSPECTION",
        is_integrity_verified=True,
        accessed_at="2026-08-17T17:00:00Z",
    )
    assert log.access_log_id == "LOG_TEST_001"
    assert log.user_role == "COMPLIANCE_OFFICER"
    assert log.is_integrity_verified is True


def test_audit_trail_access_missing_fields():
    with pytest.raises(ValidationError):
        AuditTrailAccessMetrics(
            access_log_id="LOG_BAD",
            # missing user_id, user_role, etc.
        )


# ---------------------------------------------------------------------------
# 2. RealTimeMonitoringMetrics Schema Tests
# ---------------------------------------------------------------------------

def test_realtime_monitoring_valid():
    rtm = RealTimeMonitoringMetrics(
        monitoring_id="MON_TEST_001",
        monitoring_window_start="2026-08-17T09:00:00Z",
        intraday_detections_count=4,
        active_alerts_count=1,
        avg_alert_response_time_sec=1.35,
        system_uptime_pct=99.98,
        engine_throughput_qps=180.5,
    )
    assert rtm.monitoring_id == "MON_TEST_001"
    assert rtm.intraday_detections_count == 4
    assert rtm.system_uptime_pct == 99.98
    assert rtm.engine_throughput_qps == 180.5


def test_realtime_monitoring_invalid_bounds():
    with pytest.raises(ValidationError):
        RealTimeMonitoringMetrics(
            monitoring_id="MON_BAD",
            monitoring_window_start="2026-08-17T09:00:00Z",
            system_uptime_pct=150.0,  # Exceeds 100%
        )


# ---------------------------------------------------------------------------
# 3. ComplianceDashboardKPIs Schema Tests
# ---------------------------------------------------------------------------

def test_compliance_dashboard_kpis_valid():
    kpis = ComplianceDashboardKPIs(
        kpi_id="KPI_TEST_001",
        reporting_date="2026-08-17",
        overall_compliance_index=95.0,
        open_violations_count=1,
        critical_violations_count=0,
        sla_adherence_rate_pct=98.5,
        violation_velocity_period_pct=-12.0,
        peer_benchmarking_percentile=94.0,
        systemic_risk_exposure_pct=1.5,
        executive_summary="Excellent compliance health with 98.5% SLA adherence.",
    )
    assert kpis.kpi_id == "KPI_TEST_001"
    assert kpis.overall_compliance_index == 95.0
    assert kpis.peer_benchmarking_percentile == 94.0
    assert kpis.critical_violations_count == 0


def test_compliance_dashboard_kpis_invalid_bounds():
    with pytest.raises(ValidationError):
        ComplianceDashboardKPIs(
            kpi_id="KPI_BAD",
            reporting_date="2026-08-17",
            overall_compliance_index=110.0,  # Exceeds 100
            open_violations_count=0,
            critical_violations_count=0,
            sla_adherence_rate_pct=90.0,
            peer_benchmarking_percentile=50.0,
            executive_summary="Test",
        )
