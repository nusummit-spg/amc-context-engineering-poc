# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_follow_up_detection.py
===========================
Tests for passive follow-up correction detection and patch layer registration.
Implements Task 1.1.2 verification.
"""
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.feedback import router as feedback_router
from app.graph.correction_patch_layer import get_correction_patch_layer

app = FastAPI()
app.include_router(feedback_router, prefix="/api")
client = TestClient(app)


def test_follow_up_correction_detected_and_patched():
    """Verify that a correction follow-up query is detected, recorded, and added as a patch."""
    unique_id = uuid.uuid4().hex[:8]
    session_id = f"sess_{unique_id}"
    prev_resp_id = f"resp_{unique_id}"

    payload = {
        "session_id": session_id,
        "previous_response_id": prev_resp_id,
        "original_query": "What is the TER of Axis Bluechip Fund?",
        "original_response": "The TER of Axis Bluechip Fund is 0.70%.",
        "follow_up_query": "No, that's wrong! The TER of Axis Bluechip Fund is actually 0.82%.",
        "session_history": ["What is the TER of Axis Bluechip Fund?"]
    }

    response = client.post("/api/feedback/follow-up-detection", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["is_correction"] is True
    assert data["correction_detected"] is True
    assert data["feedback_created"] is True
    assert data["auto_created_feedback"] is True
    assert data["structured_claim"] is not None
    assert data["structured_claim"]["attribute"] == "TER"
    assert "0.82" in str(data["structured_claim"]["asserted_value"])

    # Verify that the provisional patch was added to the CorrectionPatchLayer
    patch_layer = get_correction_patch_layer()
    all_patches = patch_layer.get_all_patches()
    matching_patches = [
        p for p in all_patches
        if p.attribute == "TER" and "0.82" in str(p.corrected_value)
    ]
    assert len(matching_patches) >= 1


def test_follow_up_normal_query_not_correction():
    """Verify that a benign non-correction follow-up is not classified as a correction."""
    unique_id = uuid.uuid4().hex[:8]
    session_id = f"sess_{unique_id}"
    prev_resp_id = f"resp_{unique_id}"

    payload = {
        "session_id": session_id,
        "previous_response_id": prev_resp_id,
        "original_query": "What is the NAV of HDFC Top 100 Fund?",
        "original_response": "The current NAV of HDFC Top 100 Fund is 820.50.",
        "follow_up_query": "Thank you! Who is the fund manager for this scheme?",
        "session_history": ["What is the NAV of HDFC Top 100 Fund?"]
    }

    response = client.post("/api/feedback/follow-up-detection", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["is_correction"] is False
    assert data["correction_detected"] is False
    assert data["feedback_created"] is False
    assert data["structured_claim"] is None
