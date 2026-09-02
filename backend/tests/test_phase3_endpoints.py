# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_phase3_endpoints.py
==============================
Integration tests for the 5 Phase 3 Dashboard Layer API endpoints:
1. Executive Compliance Dashboard KPIs (GET & POST refresh)
2. Real-Time Engine Monitoring (GET)
3. Audit Trail Access Logs (GET list & POST log)
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client():
    """TestClient fixture initializing FastAPI application."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


# ===========================================================================
# 1. Executive Compliance Dashboard KPIs Endpoint Tests
# ===========================================================================

def test_get_compliance_dashboard_kpis(client):
    """GET /api/compliance/dashboard/kpis returns valid executive KPIs."""
    res = client.get("/api/compliance/dashboard/kpis")
    assert res.status_code == 200
    data = res.json()
    assert "overall_compliance_index" in data
    assert data["overall_compliance_index"] >= 0.0
    assert data["overall_compliance_index"] <= 100.0
    assert "sla_adherence_rate_pct" in data
    assert "peer_benchmarking_percentile" in data
    assert "executive_summary" in data


def test_refresh_compliance_dashboard_kpis(client):
    """POST /api/compliance/dashboard/kpis/refresh triggers live recomputation."""
    res = client.post("/api/compliance/dashboard/kpis/refresh")
    assert res.status_code == 200
    data = res.json()
    assert "overall_compliance_index" in data
    assert data["overall_compliance_index"] > 50.0
    assert data["sla_adherence_rate_pct"] > 0


# ===========================================================================
# 2. Real-Time Monitoring Endpoint Tests
# ===========================================================================

def test_get_realtime_compliance_monitoring(client):
    """GET /api/compliance/dashboard/realtime-monitoring returns live engine metrics."""
    res = client.get("/api/compliance/dashboard/realtime-monitoring")
    assert res.status_code == 200
    data = res.json()
    assert "system_uptime_pct" in data
    assert data["system_uptime_pct"] >= 99.0
    assert "engine_throughput_qps" in data
    assert data["engine_throughput_qps"] >= 0.0
    assert "avg_alert_response_time_sec" in data


# ===========================================================================
# 3. Audit Trail Access Logs Endpoint Tests
# ===========================================================================

def test_list_audit_trail_access_logs(client):
    """GET /api/compliance/audit-trail/access-logs returns list of access logs."""
    res = client.get("/api/compliance/audit-trail/access-logs?limit=20")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["is_integrity_verified"] is True


def test_list_audit_trail_access_logs_filtered(client):
    """GET /api/compliance/audit-trail/access-logs with user_id filter."""
    res = client.get("/api/compliance/audit-trail/access-logs?user_id=compliance_officer_1")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert all(item["user_id"] == "compliance_officer_1" for item in data)


def test_log_audit_trail_access_event(client):
    """POST /api/compliance/audit-trail/access-logs registers a new access log."""
    payload = {
        "access_log_id": "ACCESS_LOG_TEST_NEW",
        "user_id": "lead_internal_auditor",
        "user_role": "AUDITOR",
        "resource_accessed": "DOC_SEBI_CIR_2017_114",
        "access_purpose": "STATUTORY_AUDIT",
        "is_integrity_verified": True,
        "accessed_at": "2026-08-17T18:00:00Z",
    }
    res = client.post("/api/compliance/audit-trail/access-logs", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["access_log_id"] == "ACCESS_LOG_TEST_NEW"
    assert data["user_role"] == "AUDITOR"

    # Verify retrieval
    verify_res = client.get("/api/compliance/audit-trail/access-logs?user_id=lead_internal_auditor")
    assert verify_res.status_code == 200
    assert len(verify_res.json()) >= 1
