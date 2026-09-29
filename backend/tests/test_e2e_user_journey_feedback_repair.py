# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
End-to-End User Journey Integration Test
=========================================
Tests the complete closed loop:
  1. Query execution & QueryEvidence recording
  2. Follow-up passive correction detection
  3. Structured claim extraction & Entity Resolution via FundNameMatcher
  4. Automatic provisional patch generation in CorrectionPatchLayer
  5. Multi-tier evaluation verification via EvaluationRouter
  6. Governance approval & patch activation
  7. Verification of self-healing context injection on subsequent retrieval
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.response_feedback_table import ResponseFeedback
from app.graph.correction_patch_layer import get_correction_patch_layer
from app.evaluation.evaluation_router import EvaluationRouter
from app import config

client = TestClient(app)


def test_full_e2e_user_journey_self_healing_loop():
    """Validates the full AMC lifecycle from query to self-healing repair."""
    db = SessionLocal()
    patch_layer = get_correction_patch_layer()
    patch_layer.clear_all()  # Clean test isolation

    unique_suffix = uuid.uuid4().hex[:8]
    session_id = f"e2e_sess_{unique_suffix}"
    response_id = f"e2e_resp_{unique_suffix}"
    original_query = "What is the TER of Axis Bluechip Fund?"
    original_response = "The Total Expense Ratio (TER) of Axis Bluechip Fund is 0.79%."

    try:
        # ── Step 1: Record initial QueryEvidence ────────────────────────
        qe = QueryEvidence(
            response_id=response_id,
            session_id=session_id,
            query_text=original_query,
            assembled_context_json=[
                {
                    "chunk_id": f"chk_{unique_suffix}",
                    "content": "Axis Bluechip Fund Regular Plan has a Total Expense Ratio of 0.79% according to last fact sheet.",
                    "entity_id": "INF846K01DP5",
                }
            ],
            synthesis_output_json={"answer": original_response},
            retrieval_mode="hybrid",
            created_at="2026-09-25T10:00:00Z",
        )
        db.add(qe)
        db.commit()

        # ── Step 2: User provides follow-up correction ──────────────────
        follow_up_query = "No, Axis Bluechip Fund TER is actually 0.82%, please check updated AMC factsheet."
        payload = {
            "session_id": session_id,
            "previous_response_id": response_id,
            "original_query": original_query,
            "original_response": original_response,
            "follow_up_query": follow_up_query,
            "session_history": [original_query],
        }

        det_res = client.post("/api/feedback/follow-up-detection", json=payload)
        assert det_res.status_code == 200, f"Detection failed: {det_res.text}"
        det_data = det_res.json()

        # Verify detection
        assert det_data["is_correction"] is True
        assert det_data["confidence"] >= 0.65
        assert det_data["structured_claim"] is not None
        claim = det_data["structured_claim"]
        assert claim["attribute"] == "TER"
        assert claim["asserted_value"] == "0.82"

        # ── Step 3: Verify provisional patch in CorrectionPatchLayer ────
        pending_patches = patch_layer.get_all_pending()
        assert len(pending_patches) >= 1
        created_patch = next(
            p for p in pending_patches 
            if p.attribute == "TER" and str(p.corrected_value) == "0.82"
        )
        assert created_patch.approved is False
        assert created_patch.entity_id == "INF846K01DP5"
        patch_id = created_patch.patch_id

        # ── Step 4: Verify Evaluation Router processes evidence pack ─────
        router = EvaluationRouter()
        evidence_pack = {
            "response_id": response_id,
            "response_text": original_response,
            "retrieved_context": "Axis Bluechip Fund Regular Plan TER is 0.79%",
            "query": original_query,
            "claimed_value": "0.82",
        }
        eval_result = router.evaluate(response_id=response_id, evidence_pack=evidence_pack)
        assert "verdict" in eval_result
        assert "tier" in eval_result
        assert "llm_tokens_used" in eval_result

        # ── Step 5: Governance Approval of the provisional patch ─────────
        approval_success = patch_layer.approve_patch(patch_id)
        assert approval_success is True

        approved_patches = patch_layer.get_active_patches(entity_id="INF846K01DP5")
        assert len(approved_patches) >= 1
        assert any(p.patch_id == patch_id and p.approved is True for p in approved_patches)

        # ── Step 6: Verify Self-Healing Context Injection ───────────────
        subsequent_raw_context = (
            "Fund Overview: Axis Bluechip Fund is a large cap equity fund. "
            "The expense ratio is 0.79% per the historic factsheet."
        )
        healed_context = patch_layer.apply_patches_to_context(
            entities=["INF846K01DP5"],
            retrieval_context=subsequent_raw_context,
        )

        assert "0.82" in healed_context, "Healed context should contain the corrected TER 0.82"
        assert "[CORRECTION PATCH APPLIED" in healed_context or "0.82" in healed_context

    finally:
        db.close()
        patch_layer.clear_all()
