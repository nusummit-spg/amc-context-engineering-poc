# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_phase1_endpoints.py
==============================
Integration tests for the 10 Phase 1 Foundation Layer API endpoints:
- 5 Compliance Metrics Endpoints
- 5 Feedback Metrics Endpoints
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.compliance.metrics_store import get_metrics_store


@pytest.fixture(scope="module")
def client():
    """TestClient fixture initializing FastAPI application."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


# ===========================================================================
# 1. Compliance Metrics Endpoint Tests
# ===========================================================================

def test_get_regulatory_metadata_success(client):
    """GET /api/compliance/rules/{rule_id}/regulatory-metadata returns valid 200."""
    res = client.get("/api/compliance/rules/SEBI_EQUITY_ALLOC_001/regulatory-metadata")
    assert res.status_code == 200
    data = res.json()
    assert data["rule_id"] == "SEBI_EQUITY_ALLOC_001"
    assert data["regulation_source"] == "SEBI"
    assert data["is_mandatory"] is True
    assert "SEBI" in data["jurisdiction_hierarchy"]


def test_get_regulatory_metadata_not_found(client):
    """GET /api/compliance/rules/{rule_id}/regulatory-metadata returns 404 for unknown rule."""
    res = client.get("/api/compliance/rules/UNKNOWN_RULE_999/regulatory-metadata")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_get_fund_audit_metadata_success(client):
    """GET /api/compliance/funds/{fund_id}/audit-metadata returns valid 200."""
    res = client.get("/api/compliance/funds/FUND_001/audit-metadata")
    assert res.status_code == 200
    data = res.json()
    assert data["fund_id"] == "FUND_001"
    assert data["fund_name"] == "Nippon India Large Cap Fund"
    assert data["aum_cr"] > 0
    assert data["expense_ratio_pct"] == 0.82
    assert data["amc_id"] == "AMC_NIPPON_INDIA"


def test_get_fund_audit_metadata_not_found(client):
    """GET /api/compliance/funds/{fund_id}/audit-metadata returns 404 for unknown fund."""
    res = client.get("/api/compliance/funds/NON_EXISTENT_FUND/audit-metadata")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_get_remediation_metrics_success(client):
    """GET /api/compliance/violations/{violation_id}/remediation-metrics returns valid 200."""
    res = client.get("/api/compliance/violations/VIO_SEBI_001/remediation-metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["violation_id"] == "VIO_SEBI_001"
    assert data["sla_target_hours"] == 24.0
    assert data["sla_adherence"] in ["WITHIN_SLA", "PENDING", "BREACHED"]
    assert data["root_cause_addressed"] is True


def test_get_remediation_metrics_not_found(client):
    """GET /api/compliance/violations/{violation_id}/remediation-metrics returns 404."""
    res = client.get("/api/compliance/violations/UNKNOWN_VIO/remediation-metrics")
    assert res.status_code == 404


def test_get_remediation_sla_report(client):
    """GET /api/compliance/remediation-sla-report returns valid SLA breakdown."""
    res = client.get("/api/compliance/remediation-sla-report?period=2024-09")
    assert res.status_code == 200
    data = res.json()
    assert "total_remediations" in data
    assert data["total_remediations"] >= 1
    assert "sla_adherence_pct" in data
    assert "remediations" in data


def test_filter_compliance_violations(client):
    """GET /api/compliance/violations/filter returns filtered violations."""
    res = client.get("/api/compliance/violations/filter?severity=critical&region=SEBI")
    assert res.status_code == 200
    data = res.json()
    assert "total_matches" in data
    assert "filter_applied" in data
    assert data["filter_applied"]["severity"] == "critical"
    assert data["filter_applied"]["region"] == "SEBI"


# ===========================================================================
# 2. Feedback Metrics Endpoint Tests
# ===========================================================================

def test_get_feedback_category_analytics(client):
    """GET /api/feedback/category-analytics returns list of F01-F12 category metrics."""
    res = client.get("/api/feedback/category-analytics?period=2024-09")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    cat_ids = [item["category_id"] for item in data]
    assert "F08" in cat_ids
    assert "F05" in cat_ids
    assert data[0]["reporting_period"] == "2024-09"


def test_refresh_feedback_category_analytics(client):
    """POST /api/feedback/category-analytics/refresh triggers recalculation."""
    res = client.post("/api/feedback/category-analytics/refresh?period=2024-09")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_high_priority_feedback(client):
    """GET /api/feedback/high-priority returns P0/P1 feedback."""
    # First submit a regulatory feedback to trigger a P0
    fb_payload = {
        "response_id": "RESP_SEBI_TEST_001",
        "interaction_id": "INT_TEST_001",
        "session_id": "SESS_TEST_001",
        "turn_number": 1,
        "query_text": "Is there a guaranteed return for this scheme?",
        "actor_id": "auditor_test",
        "actor_role": "Chief Compliance Officer",
        "selected_categories": ["F12"],
        "free_text": "SEBI violation: The response suggested an assured return which is prohibited under mutual fund regulations.",
    }
    submit_res = client.post("/api/feedback", json=fb_payload)
    assert submit_res.status_code == 201
    submit_data = submit_res.json()
    assert submit_data["priority_tier"] == "P0"

    # Query high priority endpoint
    res = client.get("/api/feedback/high-priority?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["priority_tier"] in ("P0", "P1")


def test_get_response_quality_metrics(client):
    """GET /api/feedback/responses/{response_id}/quality-score and alias return quality metrics."""
    res = client.get("/api/feedback/responses/RESP_TEST_001/quality-score")
    assert res.status_code == 200
    data = res.json()
    assert data["response_id"] == "RESP_TEST_001"
    assert data["overall_quality_score"] > 0
    assert "mode_performance_delta" in data
    assert data["retrieval_mode"] == "contextgraph"

    # Test direct alias /api/responses/{response_id}/quality-score
    alias_res = client.get("/api/responses/RESP_TEST_001/quality-score")
    assert alias_res.status_code == 200
    assert alias_res.json()["response_id"] == "RESP_TEST_001"


def test_get_feedback_quality_metrics(client):
    """GET /api/feedback/{feedback_id}/quality-metrics returns quality evaluation."""
    # First submit feedback to get a feedback_id
    fb_payload = {
        "response_id": "RESP_NUM_TEST_002",
        "interaction_id": "INT_TEST_002",
        "session_id": "SESS_TEST_002",
        "turn_number": 1,
        "selected_categories": ["F08"],
        "free_text": "The actual expense ratio is 0.82% instead of 1.20% shown on page 4 of the factsheet.",
    }
    submit_res = client.post("/api/feedback", json=fb_payload)
    assert submit_res.status_code == 201
    fb_id = submit_res.json()["feedback_id"]

    # Now get feedback quality metrics
    res = client.get(f"/api/feedback/{fb_id}/quality-metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["feedback_id"] == fb_id
    assert data["detail_score"] > 0
    assert data["actionability_score"] > 0
    assert data["priority_tier"] == "P1"
    assert data["is_actionable"] is True
