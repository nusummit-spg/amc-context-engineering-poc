# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_audit_recommendations.py
===================================
Tests verifying all audit findings and hardening implementations from Docs/audit_report_02_09_26.md:
1. Thread safety and concurrency locks in MetricsStore
2. Cryptographic SHA-256 hash chaining and tamper-evident verification
3. Remediation mutation and SLA recalculation endpoints
4. Feedback quality PATCH updates
5. Regulatory CSV export endpoint
6. Schema enhancement validation (new lifecycle, cost, and efficiency fields)
"""

import concurrent.futures
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.compliance.metrics_store import get_metrics_store
from app.schemas.audit_trail_access import AuditTrailAccessMetrics
from app.schemas.remediation_metrics import RemediationMetrics
from app.schemas.regulatory_metadata import RegulatoryMetadata
from app.schemas.fund_metadata import FundAuditMetadata
from app.schemas.realtime_monitoring import RealTimeMonitoringMetrics
from pydantic import ValidationError


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


# ===========================================================================
# 1. Thread Safety & Concurrency Tests
# ===========================================================================

def test_metrics_store_thread_safety():
    """Verify thread-safe concurrent mutations across parallel worker threads."""
    store = get_metrics_store()

    def worker_log_access(i: int):
        log = AuditTrailAccessMetrics(
            access_log_id=f"CONCURRENT_LOG_{i}",
            user_id=f"worker_{i}",
            user_role="AUDITOR",
            resource_accessed="FUND_PORTFOLIO",
            access_purpose="STATUTORY_AUDIT",
            accessed_at="2026-09-02T12:00:00Z",
        )
        return store.log_audit_access(log)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker_log_access, i) for i in range(25)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 25
    # Verify that the hash chain is still completely valid after concurrent writes
    verification = store.verify_audit_trail_integrity()
    assert verification["is_valid"] is True
    assert verification["total_records"] >= 25


# ===========================================================================
# 2. Cryptographic Audit Hash Chain & Tamper Detection Tests
# ===========================================================================

def test_audit_trail_verification_endpoint(client):
    """GET /api/compliance/audit-trail/verify-integrity returns valid verification."""
    res = client.get("/api/compliance/audit-trail/verify-integrity")
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is True
    assert "chain_head" in data
    assert data["tamper_proof"] == "SHA-256-HASH-CHAIN-VERIFIED"


def test_tamper_detection_in_audit_chain():
    """Test that modifying a historical audit record is detected immediately."""
    store = get_metrics_store()
    verification_before = store.verify_audit_trail_integrity()
    assert verification_before["is_valid"] is True

    # Intentionally corrupt a hash signature in memory
    original_hash = store._audit_access_logs[0].current_log_hash
    store._audit_access_logs[0].current_log_hash = "corrupted_tampered_hash_value_12345"

    tampered_verification = store.verify_audit_trail_integrity()
    assert tampered_verification["is_valid"] is False
    assert "tampered" in tampered_verification["reason"] or "invalid" in tampered_verification["reason"]

    # Restore original hash
    store._audit_access_logs[0].current_log_hash = original_hash
    restored_verification = store.verify_audit_trail_integrity()
    assert restored_verification["is_valid"] is True


# ===========================================================================
# 3. Remediation POST & PATCH Endpoints
# ===========================================================================

def test_record_new_remediation_endpoint(client):
    """POST /api/compliance/remediations creates a new remediation tracking record."""
    payload = {
        "remediation_id": "REM_AUDIT_TEST_001",
        "violation_id": "VIO_AUDIT_TEST_001",
        "severity_level": "HIGH",
        "sla_target_hours": 48.0,
        "sla_target_date": "2026-09-04T12:00:00Z",
        "detected_at": "2026-09-02T12:00:00Z",
        "remediation_action": "Rebalance portfolio equity allocation to comply with 65% statutory threshold",
        "remediation_owner_user_id": "pm_compliance_lead",
        "remediation_root_cause_id": "RCA_AUDIT_TEST_001",
        "created_at": "2026-09-02T12:00:00Z",
        "updated_at": "2026-09-02T12:00:00Z",
    }
    res = client.post("/api/compliance/remediations", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["remediation_id"] == "REM_AUDIT_TEST_001"
    assert data["sla_adherence"] == "PENDING"
    assert data["remediation_root_cause_id"] == "RCA_AUDIT_TEST_001"


def test_update_remediation_endpoint_recalculates_sla(client):
    """PATCH /api/compliance/violations/{id}/remediation updates and recalculates SLA."""
    patch_payload = {
        "remediation_actual_completion_at": "2026-09-03T12:00:00Z",  # 24 hours later (target was 48)
        "remediation_effectiveness": "EFFECTIVE",
        "verified_by_user_id": "compliance_head",
        "verification_date": "2026-09-03T14:00:00Z",
        "root_cause_addressed": True,
        "systemic_fix_applied": True,
    }
    res = client.patch("/api/compliance/violations/VIO_AUDIT_TEST_001/remediation", json=patch_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["resolution_time_hours"] == 24.0
    assert data["sla_variance_hours"] == -24.0  # 24h early!
    assert data["sla_adherence"] == "WITHIN_SLA"
    assert data["remediation_effectiveness"] == "EFFECTIVE"


# ===========================================================================
# 4. Feedback Quality PATCH Endpoint
# ===========================================================================

def test_update_feedback_quality_endpoint(client):
    """PATCH /api/feedback/{feedback_id}/quality-metrics updates triage priority."""
    fb_payload = {
        "response_id": "RESP_AUDIT_TEST_999",
        "interaction_id": "INT_AUDIT_999",
        "session_id": "SESS_AUDIT_999",
        "turn_number": 1,
        "query_text": "Check TER calculation",
        "actor_id": "analyst_1",
        "actor_role": "Analyst",
        "selected_categories": ["F08"],
        "free_text": "TER percentage calculation mismatch in note 4",
    }
    submit_res = client.post("/api/feedback", json=fb_payload)
    assert submit_res.status_code == 201
    feedback_id = submit_res.json()["feedback_id"]

    patch_payload = {
        "priority_tier": "P0",
        "action_difficulty": "HIGH",
        "review_confidence_score": 0.98,
    }
    res = client.patch(f"/api/feedback/{feedback_id}/quality-metrics", json=patch_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["priority_tier"] == "P0"
    assert data["action_difficulty"] == "HIGH"
    assert data["review_confidence_score"] == 0.98



# ===========================================================================
# 5. Regulatory CSV Export Endpoint
# ===========================================================================

def test_export_compliance_data_sla_csv(client):
    """GET /api/compliance/export?report_type=sla returns CSV format."""
    res = client.get("/api/compliance/export?report_type=sla")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "remediation_id,violation_id,severity_level" in res.text


def test_export_compliance_data_audit_csv(client):
    """GET /api/compliance/export?report_type=audit returns CSV format."""
    res = client.get("/api/compliance/export?report_type=audit")
    assert res.status_code == 200
    assert "access_log_id,user_id,user_role" in res.text


# ===========================================================================
# 6. Schema Enhancement Validation Tests
# ===========================================================================

def test_regulatory_metadata_enforcement_level_validation():
    """Verify enforcement_level validator rejects invalid enum strings."""
    with pytest.raises(ValidationError):
        RegulatoryMetadata(
            metadata_id="REG_BAD",
            rule_id="RULE_BAD",
            regulation_source="SEBI",
            regulation_section="Sec 1",
            effective_date="2026-01-01",
            enforcement_level="INVALID_LEVEL",
            updated_at="2026-01-01T00:00:00Z",
        )


def test_fund_audit_metadata_lifecycle_dates():
    """Verify FundAuditMetadata supports last_rebalance_date and last_audit_date."""
    fund = FundAuditMetadata(
        fund_id="FUND_LIFECYCLE_001",
        fund_name="HDFC Top 100 Fund",
        fund_category="Large Cap",
        fund_type="Open-ended",
        aum_cr=12500.0,
        fund_manager_id="MGR_RAHUL_BAIWAL",
        fund_manager_experience_years=16.5,
        fund_creation_date="2005-09-01",
        benchmark_index="NIFTY 100 TRI",
        ytd_return_pct=14.2,
        expense_ratio_pct=1.65,
        portfolio_turnover_pct=28.0,
        sharpe_ratio=1.42,
        top_holding_concentration_pct=8.5,
        sector_concentration_max_pct=24.0,
        amc_id="AMC_HDFC_MF",
        last_rebalance_date="2026-08-15",
        last_audit_date="2026-07-30",
        created_at="2026-09-02T12:00:00Z",
    )
    assert fund.last_rebalance_date == "2026-08-15"
    assert fund.last_audit_date == "2026-07-30"


def test_realtime_monitoring_latency_percentiles():
    """Verify RealTimeMonitoringMetrics supports p95 and p99 latency metrics."""
    rt = RealTimeMonitoringMetrics(
        monitoring_id="MON_LATENCY_001",
        monitoring_window_start="2026-09-02T09:00:00Z",
        p95_latency_ms=115.4,
        p99_latency_ms=250.8,
    )
    assert rt.p95_latency_ms == 115.4
    assert rt.p99_latency_ms == 250.8
