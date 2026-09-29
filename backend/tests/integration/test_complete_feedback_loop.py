"""
Integration test: Complete feedback loop from query to Neo4j correction.
Validates the user journey:
  1. Submit initial query & record evidence
  2. Submit feedback / follow-up correction
  3. Verify patch created in CorrectionPatchLayer
  4. Evaluate via EvaluationRouter & Governance batch
  5. Verify healed context injection on subsequent retrieval
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.schemas.query_evidence_table import QueryEvidence
from app.graph.correction_patch_layer import get_correction_patch_layer
from app.evaluation.evaluation_router import EvaluationRouter
from app.tasks.governance_batch import GovernanceBatch

client = TestClient(app)

@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_feedback_loop():
    db = SessionLocal()
    patch_layer = get_correction_patch_layer()
    patch_layer.clear_all()

    unique_id = uuid.uuid4().hex[:8]
    session_id = f"sess_loop_{unique_id}"
    response_id = f"resp_loop_{unique_id}"
    query = "What is the TER of Axis Bluechip Fund?"
    original_answer = "The Total Expense Ratio (TER) of Axis Bluechip Fund is 0.79%."

    try:
        # Step 1: Record initial QueryEvidence
        qe = QueryEvidence(
            response_id=response_id,
            session_id=session_id,
            query_text=query,
            assembled_context_json=[
                {
                    "chunk_id": f"chk_{unique_id}",
                    "content": "Axis Bluechip Fund Regular Plan has a Total Expense Ratio of 0.79%.",
                    "entity_id": "INF846K01DP5",
                }
            ],
            synthesis_output_json={"answer": original_answer},
            retrieval_mode="hybrid",
            created_at="2026-09-25T10:00:00Z",
        )
        db.add(qe)
        db.commit()
        print(f"✓ Step 1: Recorded QueryEvidence for {response_id}")

        # Step 2: Submit correction feedback via follow-up detection API
        follow_up_query = "The TER of Axis Bluechip Fund is actually 0.82%, not 0.79%."
        payload = {
            "session_id": session_id,
            "previous_response_id": response_id,
            "original_query": query,
            "original_response": original_answer,
            "follow_up_query": follow_up_query,
            "session_history": [query],
        }

        res = client.post("/api/feedback/follow-up-detection", json=payload)
        assert res.status_code == 200, f"Detection API returned {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("is_correction") is True
        print(f"✓ Step 2: Follow-up correction detected with confidence={data.get('confidence')}")

        # Step 3: Verify patch was created in CorrectionPatchLayer
        pending = patch_layer.get_all_pending()
        assert len(pending) > 0, "Expected at least one pending patch"
        target_patch = next((p for p in pending if p.attribute == "TER"), None)
        assert target_patch is not None, "TER correction patch not found"
        print(f"✓ Step 3: Pending patch generated: {target_patch.patch_id} -> {target_patch.corrected_value}")

        # Step 4: Evaluate with EvaluationRouter
        router = EvaluationRouter()
        eval_result = router.evaluate(
            response_id=response_id,
            evidence_pack={
                "response_id": response_id,
                "response_text": original_answer,
                "retrieved_context": "Axis Bluechip Fund TER is 0.79%",
                "query": query,
                "claimed_value": "0.82",
            }
        )
        assert "verdict" in eval_result
        print(f"✓ Step 4: Evaluation verdict={eval_result['verdict']}, tier={eval_result['tier']}")

        # Step 5: Run Governance batch
        batch = GovernanceBatch()
        gov_report = await batch.process(lookback_days=7)
        assert isinstance(gov_report, dict)
        print(f"✓ Step 5: Governance batch processed successfully: {gov_report}")

        # Step 6: Verify context healing on retrieval
        patch_layer.approve_patch(target_patch.patch_id)
        raw_retrieved_context = "Axis Bluechip Fund has an expense ratio of 0.79%."
        healed_context = patch_layer.apply_patches_to_context(
            entities=["INF846K01DP5"],
            retrieval_context=raw_retrieved_context,
        )
        assert "0.82" in healed_context
        print(f"✓ Step 6: Self-healing context verified: {healed_context}")

        print("\n✅ COMPLETE FEEDBACK LOOP VALIDATED SUCCESSFULLY")

    finally:
        db.close()
        patch_layer.clear_all()
