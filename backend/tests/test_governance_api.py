# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_governance_api.py
======================
Unit & API tests for Track 7: Human Governance Review Queue endpoints.
"""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.graph.correction_patch_layer import get_correction_patch_layer
from app.models.compliance_models import Role


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def clean_patch_layer():
    patch_layer = get_correction_patch_layer()
    # Clear any existing patches in memory
    patch_layer._mem_store.clear()
    return patch_layer


def test_get_pending_corrections_empty(client, clean_patch_layer):
    response = client.get(
        "/api/governance/pending-corrections",
        headers={"X-User-Role": Role.COMPLIANCE_OFFICER.value}
    )
    assert response.status_code == 200
    assert response.json() == []


def test_get_pending_corrections_with_data(client, clean_patch_layer):
    clean_patch_layer.add_correction(
        entity_id="INF846K01DP5",
        attribute="TER",
        canonical_value="0.79%",
        corrected_value="0.82%",
        confidence=0.88,
        provenance={"source": "AMFI", "feedback_id": "fb_101"}
    )

    response = client.get(
        "/api/governance/pending-corrections",
        headers={"X-User-Role": Role.COMPLIANCE_OFFICER.value}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["entity_id"] == "INF846K01DP5"
    assert data[0]["attribute"] == "TER"
    assert data[0]["proposed_value"] == "0.82%"
    assert data[0]["risk_level"] in ("LOW", "MEDIUM", "HIGH")


def test_approve_correction(client, clean_patch_layer):
    pid = clean_patch_layer.add_correction(
        entity_id="INF846K01DP5",
        attribute="TER",
        canonical_value="0.79%",
        corrected_value="0.82%",
        confidence=0.92
    )

    response = client.post(
        f"/api/governance/approve/{pid}",
        json={"comment": "Verified against latest factsheet"},
        headers={"X-User-Role": Role.COMPLIANCE_OFFICER.value}
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "approved"
    assert res_data["patch_id"] == pid

    # Should no longer be pending
    pending_resp = client.get(
        "/api/governance/pending-corrections",
        headers={"X-User-Role": Role.COMPLIANCE_OFFICER.value}
    )
    assert pending_resp.status_code == 200
    assert len(pending_resp.json()) == 0


def test_reject_correction(client, clean_patch_layer):
    pid = clean_patch_layer.add_correction(
        entity_id="INF846K01DP5",
        attribute="TER",
        canonical_value="0.79%",
        corrected_value="0.99%",
        confidence=0.40
    )

    response = client.post(
        f"/api/governance/reject/{pid}",
        json={"reason": "Incorrect value claimed by user"},
        headers={"X-User-Role": Role.COMPLIANCE_OFFICER.value}
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "rejected"

    assert clean_patch_layer.get_correction("INF846K01DP5", "TER") is None


def test_batch_approve_corrections(client, clean_patch_layer):
    pid1 = clean_patch_layer.add_correction("E1", "TER", "0.5", "0.6", 0.9)
    pid2 = clean_patch_layer.add_correction("E2", "NAV", "10", "11", 0.9)

    response = client.post(
        "/api/governance/batch-approve",
        json={"patch_ids": [pid1, pid2], "action": "approve", "comment": "Batch approved by compliance"},
        headers={"X-User-Role": Role.COMPLIANCE_OFFICER.value}
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["succeeded_count"] == 2
    assert res_data["failed_count"] == 0


def test_unauthorized_access(client):
    response = client.get(
        "/api/governance/pending-corrections",
        headers={"X-User-Role": "viewer"}
    )
    assert response.status_code == 403
