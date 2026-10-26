# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_phase2_endpoints.py
==============================
Integration tests for the 8 Phase 2 Analysis Layer API endpoints:
1. Root Cause Analysis (GET & POST)
2. Violation Clusters (GET list, GET details, POST)
3. AMC Fund Family Analysis (GET & POST run)
4. Evidence Metadata (GET & POST)
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
# 1. Root Cause Analysis Endpoint Tests
# ===========================================================================

def test_get_root_cause_analysis_success(client):
    """GET /api/compliance/violations/{violation_id}/root-cause returns 200."""
    res = client.get("/api/compliance/violations/VIO_SEBI_001/root-cause")
    assert res.status_code == 200
    data = res.json()
    assert data["violation_id"] == "VIO_SEBI_001"
    assert data["primary_category"] == "operational_error"
    assert data["is_systemic"] is True
    assert data["preventability_score"] > 0.8


def test_get_root_cause_analysis_not_found(client):
    """GET /api/compliance/violations/{violation_id}/root-cause returns 404 for unknown violation."""
    res = client.get("/api/compliance/violations/UNKNOWN_VIO_999/root-cause")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_create_or_update_root_cause(client):
    """POST /api/compliance/violations/{violation_id}/root-cause records RCA findings."""
    payload = {
        "rca_id": "RCA_NEW_001",
        "violation_id": "VIO_NEW_001",
        "primary_category": "market_volatility",
        "secondary_categories": ["data_quality"],
        "root_cause_description": "Flash crash induced temporary breach of liquid asset ratio.",
        "is_systemic": False,
        "repeat_violation_count": 0,
        "cluster_id": None,
        "market_context": "Intraday 4% index drop",
        "contributing_factors": ["High volume selloff"],
        "detection_mechanism": "rules_engine",
        "preventability_score": 0.55,
        "recommended_remedy_type": "POLICY_OVERLAY",
        "investigated_by": "market_risk_analyst",
        "analyzed_at": "2026-08-17T14:00:00Z",
    }
    res = client.post("/api/compliance/violations/VIO_NEW_001/root-cause", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["violation_id"] == "VIO_NEW_001"
    assert data["primary_category"] == "market_volatility"

    # Verify retrieval
    verify_res = client.get("/api/compliance/violations/VIO_NEW_001/root-cause")
    assert verify_res.status_code == 200
    assert verify_res.json()["rca_id"] == "RCA_NEW_001"


# ===========================================================================
# 2. Violation Clusters Endpoint Tests
# ===========================================================================

def test_list_violation_clusters(client):
    """GET /api/compliance/violation-clusters returns list of clusters."""
    res = client.get("/api/compliance/violation-clusters")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["cluster_id"] == "CLUSTER_001"


def test_list_violation_clusters_filtered(client):
    """GET /api/compliance/violation-clusters with query filters."""
    res = client.get("/api/compliance/violation-clusters?amc_id=AMC_NIPPON_INDIA&severity=CRITICAL")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["affected_amc_id"] == "AMC_NIPPON_INDIA"
    assert data[0]["severity"] == "CRITICAL"


def test_get_violation_cluster_details(client):
    """GET /api/compliance/violation-clusters/{cluster_id} returns 200."""
    res = client.get("/api/compliance/violation-clusters/CLUSTER_001")
    assert res.status_code == 200
    data = res.json()
    assert data["cluster_id"] == "CLUSTER_001"
    assert "Single Issuer" in data["cluster_name"]
    assert data["is_systemic_risk"] is True


def test_get_violation_cluster_not_found(client):
    """GET /api/compliance/violation-clusters/{cluster_id} returns 404."""
    res = client.get("/api/compliance/violation-clusters/UNKNOWN_CLUSTER")
    assert res.status_code == 404


def test_create_violation_cluster(client):
    """POST /api/compliance/violation-clusters creates a new cluster."""
    payload = {
        "cluster_id": "CLUSTER_TEST_002",
        "cluster_name": "TER Disclosure Discrepancies",
        "violation_ids": ["VIO_SEBI_002"],
        "common_rule_ids": ["SEBI_TER_LIMIT_002"],
        "affected_fund_ids": ["FUND_002"],
        "affected_amc_id": "AMC_HDFC_MF",
        "severity": "HIGH",
        "cluster_density_score": 0.75,
        "is_systemic_risk": False,
        "created_at": "2026-08-17T15:00:00Z",
    }
    res = client.post("/api/compliance/violation-clusters", json=payload)
    assert res.status_code == 201
    assert res.json()["cluster_id"] == "CLUSTER_TEST_002"


# ===========================================================================
# 3. Fund Family Analysis Endpoint Tests
# ===========================================================================

def test_get_amc_family_analysis(client):
    """GET /api/compliance/amc/{amc_id}/family-analysis returns family analysis."""
    res = client.get("/api/compliance/amc/AMC_NIPPON_INDIA/family-analysis")
    assert res.status_code == 200
    data = res.json()
    assert data["amc_id"] == "AMC_NIPPON_INDIA"
    assert data["total_funds_analyzed"] >= 1
    assert "portfolio_manager_accountability_scores" in data


def test_run_amc_family_analysis(client):
    """POST /api/compliance/amc/{amc_id}/family-analysis/run recalculates correlation."""
    res = client.post("/api/compliance/amc/AMC_HDFC_MF/family-analysis/run")
    assert res.status_code == 200
    data = res.json()
    assert data["amc_id"] == "AMC_HDFC_MF"
    assert data["cross_fund_correlation_score"] >= 0.0
    assert "portfolio_manager_accountability_scores" in data


# ===========================================================================
# 4. Evidence Metadata Endpoint Tests
# ===========================================================================

def test_get_evidence_metadata_success(client):
    """GET /api/compliance/evidence/{evidence_id} returns 200."""
    res = client.get("/api/compliance/evidence/EVID_001")
    assert res.status_code == 200
    data = res.json()
    assert data["evidence_id"] == "EVID_001"
    assert data["document_hash"] != ""
    assert data["is_tamper_evident"] is True
    assert data["source_authority_tier"] == "TIER_1_REGULATOR"


def test_get_evidence_metadata_not_found(client):
    """GET /api/compliance/evidence/{evidence_id} returns 404."""
    res = client.get("/api/compliance/evidence/UNKNOWN_EVID")
    assert res.status_code == 404


def test_record_evidence_metadata(client):
    """POST /api/compliance/evidence registers tamper-evident evidence."""
    payload = {
        "evidence_id": "EVID_NEW_001",
        "document_id": "DOC_PORTFOLIO_DUMP_001",
        "document_hash": "a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
        "collected_at": "2026-08-17T16:00:00Z",
        "retention_expiry_date": "2034-08-17",
        "relevance_score": 0.99,
        "chain_of_custody_signoff": "CUSTODY_KEY_SECURE_999",
        "source_authority_tier": "TIER_2_OFFICIAL_FILING",
        "is_tamper_evident": True,
    }
    res = client.post("/api/compliance/evidence", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["evidence_id"] == "EVID_NEW_001"
    assert data["document_hash"] == payload["document_hash"]
