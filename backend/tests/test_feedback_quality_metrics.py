# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_feedback_quality_metrics.py
======================================
Comprehensive unit & integration tests for FeedbackQualityMetrics and RBAC enforcement:
- Scoring: detail, clarity, actionability, completeness (0-1 scale)
- Reviewer credibility weighting
- Priority tier classification (P0, P1, P2, P3)
- P0 regulatory breach detection (F12 or statutory keywords)
- Reproduction steps detection
- PATCH mutation for priority and action difficulty
- RBAC role enforcement (viewer blocked from write operations, compliance_officer allowed)
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.compliance.metrics_store import get_metrics_store


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_evaluate_feedback_p0_regulatory_tier():
    store = get_metrics_store()
    metrics = store.evaluate_feedback_quality(
        feedback_id="FB_P0_TEST",
        response_id="RESP_P0_TEST",
        free_text="SEBI statutory breach: Response advised a guaranteed annual return of 12% in scheme prospectus.",
        selected_categories=["F12"],
        actor_role="Chief Compliance Officer",
    )
    assert metrics.priority_tier == "P0"
    assert metrics.reviewer_credibility_score == 1.0
    assert metrics.is_actionable is True
    assert metrics.signal_quality_score >= 0.70


def test_evaluate_feedback_p1_accuracy_tier():
    store = get_metrics_store()
    metrics = store.evaluate_feedback_quality(
        feedback_id="FB_P1_TEST",
        response_id="RESP_P1_TEST",
        free_text="Expense ratio shows 1.25% but latest SID table on page 42 shows 1.45%. Expected 1.45% instead.",
        selected_categories=["F08"],
        actor_role="Research Analyst",
    )
    assert metrics.priority_tier == "P1"
    assert metrics.has_reproduction_steps is True
    assert metrics.actionability_score >= 0.8


def test_evaluate_feedback_p3_minor_tier():
    store = get_metrics_store()
    metrics = store.evaluate_feedback_quality(
        feedback_id="FB_P3_TEST",
        response_id="RESP_P3_TEST",
        free_text="Font formatting was slightly difficult to read.",
        selected_categories=[],
        actor_role="Client",
    )
    assert metrics.priority_tier == "P3"
    assert metrics.detail_score <= 0.3


def test_feedback_rbac_viewer_blocked_from_submit(client):
    """A user with Role 'viewer' is blocked from submitting feedback (HTTP 403)."""
    fb_payload = {
        "response_id": "RESP_RBAC_001",
        "interaction_id": "INT_RBAC_001",
        "session_id": "SESS_RBAC_001",
        "turn_number": 1,
        "query_text": "Test query",
        "actor_id": "viewer_user",
        "actor_role": "Viewer",
        "selected_categories": ["F01"],
        "free_text": "Viewer commentary",
    }
    # Pass viewer role header
    res = client.post("/api/feedback", json=fb_payload, headers={"X-User-Role": "viewer"})
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]


def test_feedback_rbac_compliance_officer_allowed_to_submit(client):
    """A user with Role 'compliance_officer' can submit feedback (HTTP 201)."""
    fb_payload = {
        "response_id": "RESP_RBAC_002",
        "interaction_id": "INT_RBAC_002",
        "session_id": "SESS_RBAC_002",
        "turn_number": 1,
        "query_text": "Is this circular active?",
        "actor_id": "compliance_user",
        "actor_role": "Compliance Officer",
        "selected_categories": ["F05"],
        "free_text": "Outdated circular version referenced in answer.",
    }
    res = client.post("/api/feedback", json=fb_payload, headers={"X-User-Role": "compliance_officer"})
    assert res.status_code == 201
    assert res.json()["status"] == "recorded"


def test_feedback_rbac_viewer_blocked_from_refresh_analytics(client):
    """A user with Role 'viewer' is blocked from refreshing category analytics."""
    res = client.post("/api/feedback/category-analytics/refresh", headers={"X-User-Role": "viewer"})
    assert res.status_code == 403


def test_feedback_rbac_admin_allowed_to_refresh_analytics(client):
    """A user with Role 'admin' or 'compliance_officer' can refresh category analytics."""
    res = client.post("/api/feedback/category-analytics/refresh", headers={"X-User-Role": "admin"})
    assert res.status_code == 200
    assert isinstance(res.json(), list)
