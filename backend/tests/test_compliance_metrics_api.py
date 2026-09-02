# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_compliance_metrics_api.py
====================================
End-to-End integration tests for the compliance and audit metrics pipeline:
1. Create and track violation remediation metrics
2. Verify SLA adherence report calculations
3. Test audit trail cryptographic verification (/verify and /verify-integrity)
4. Trigger Neo4j synchronization endpoint (/sync-neo4j)
5. Export regulatory CSV reports for statutory filings (/export)
6. Fetch executive dashboard KPIs (/dashboard/kpis)
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_e2e_violation_to_remediation_workflow(client):
    # 1. Record a new remediation
    payload = {
        "remediation_id": "REM_E2E_999",
        "violation_id": "VIO_E2E_999",
        "severity_level": "CRITICAL",
        "sla_target_hours": 24.0,
        "sla_target_date": "2026-09-03T10:00:00Z",
        "detected_at": "2026-09-02T10:00:00Z",
        "remediation_action": "Liquidity buffer restored to 10% minimum threshold",
        "remediation_owner_user_id": "head_of_risk",
        "created_at": "2026-09-02T10:00:00Z",
        "updated_at": "2026-09-02T10:00:00Z",
    }
    create_res = client.post("/api/compliance/remediations", json=payload)
    assert create_res.status_code == 201
    assert create_res.json()["remediation_id"] == "REM_E2E_999"

    # 2. Retrieve remediation
    get_res = client.get("/api/compliance/violations/VIO_E2E_999/remediation-metrics")
    assert get_res.status_code == 200
    assert get_res.json()["sla_adherence"] == "PENDING"

    # 3. Patch remediation with completion
    patch_res = client.patch("/api/compliance/violations/VIO_E2E_999/remediation", json={
        "remediation_actual_completion_at": "2026-09-02T22:00:00Z",  # 12h later (target was 24)
        "remediation_effectiveness": "EFFECTIVE",
        "verified_by_user_id": "compliance_director",
    })
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["resolution_time_hours"] == 12.0
    assert data["sla_variance_hours"] == -12.0  # 12h early
    assert data["sla_adherence"] == "WITHIN_SLA"

    # 4. Check SLA report includes updated statistics
    sla_res = client.get("/api/compliance/remediation-sla-report?period=2026-09")
    assert sla_res.status_code == 200
    sla_data = sla_res.json()
    assert sla_data["within_sla_count"] >= 1
    assert sla_data["sla_adherence_pct"] > 0.0


def test_e2e_audit_trail_verification_aliases(client):
    # Both /verify and /verify-integrity must return successful cryptographic proof
    res1 = client.get("/api/compliance/audit-trail/verify")
    assert res1.status_code == 200
    assert res1.json()["is_valid"] is True
    assert res1.json()["tamper_proof"] == "SHA-256-HASH-CHAIN-VERIFIED"

    res2 = client.get("/api/compliance/audit-trail/verify-integrity")
    assert res2.status_code == 200
    assert res2.json()["is_valid"] is True


def test_e2e_neo4j_sync_endpoint(client):
    res = client.post("/api/compliance/sync-neo4j")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "persisted"
    assert "total_in_memory_records" in data


def test_e2e_compliance_data_exports(client):
    # Export SLA
    res_sla = client.get("/api/compliance/export?report_type=sla")
    assert res_sla.status_code == 200
    assert "remediation_id,violation_id" in res_sla.text

    # Export KPIs
    res_kpis = client.get("/api/compliance/export?report_type=kpis")
    assert res_kpis.status_code == 200
    assert "kpi_id,reporting_date" in res_kpis.text


def test_e2e_dashboard_kpis(client):
    res = client.get("/api/compliance/dashboard/kpis")
    assert res.status_code == 200
    kpis = res.json()
    assert kpis["overall_compliance_index"] >= 0.0
    assert kpis["sla_adherence_rate_pct"] >= 0.0
    assert len(kpis["executive_summary"]) > 10
