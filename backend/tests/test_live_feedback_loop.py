"""
Integration test for human-feedback-loop wired to AMC backend.

Tests:
1. Submitting feedback via submit_feedback_and_evaluate endpoint
2. Triggering the feedback loop pipeline (Steps 1–4)
3. Persisting UnifiedEvaluationRecord in AMC SQLite data.db
4. Retrieving evaluation records via GET /api/feedback-evaluation/{response_id}
"""

import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.feedback_evaluation import router as feedback_eval_router
from app.api.routes.feedback import router as feedback_router
from app.core.database import SessionLocal
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.services.feedback import trigger_feedback_loop

test_app = FastAPI()
test_app.include_router(feedback_eval_router, prefix="/api")
test_app.include_router(feedback_router, prefix="/api")
client = TestClient(test_app)


def test_direct_trigger_feedback_loop():
    """Test calling trigger_feedback_loop with real AMC database records."""
    db: Session = SessionLocal()
    try:
        unique_id = uuid.uuid4().hex[:8]
        response_id = f"resp_test_{unique_id}"
        session_id = f"sess_test_{unique_id}"
        feedback_id = f"fb_test_{unique_id}"

        # 1. Create QueryEvidence
        qe = QueryEvidence(
            response_id=response_id,
            session_id=session_id,
            query_text="What is the exit load for HDFC Top 100 Fund?",
            assembled_context_json=[
                {
                    "chunk_id": "chk_exit_load_01",
                    "value": "1.00% if redeemed within 1 year",
                    "content": "Exit load is 1.00% if redeemed within 365 days from allotment.",
                    "source_version": "v1",
                }
            ],
            synthesis_output_json={
                "answer": "The exit load is 0% for any redemption period.",
            },
            retrieval_mode="contextgraph",
            created_at="2026-09-23T10:00:00Z",
        )
        db.add(qe)

        # 2. Create ResponseFeedback
        fb = ResponseFeedback(
            feedback_id=feedback_id,
            response_id=response_id,
            interaction_id=f"int_{unique_id}",
            session_id=session_id,
            turn_number=1,
            query_text=qe.query_text,
            actor_id="test_reviewer",
            actor_role="Compliance Officer",
            selected_categories=["F01"],
            feedback_text="Exit load is actually 1% within 1 year, not 0%. This is incorrect.",
            created_at="2026-09-23T10:05:00Z",
            updated_at="2026-09-23T10:05:00Z",
        )
        db.add(fb)
        db.commit()

        # 3. Trigger feedback loop pipeline
        evaluation = trigger_feedback_loop(
            feedback_id=feedback_id,
            session_id=session_id,
            response_id=response_id,
            source="active",
            db=db,
        )

        assert evaluation is not None, "Evaluation record should be returned"
        assert evaluation.response_id == response_id
        assert evaluation.session_id == session_id
        assert evaluation.entry_route == "hitl"
        assert evaluation.root_cause in {"model", "knowledge", "retrieval", "graph", "compliance", "context_engineering"}
        assert evaluation.severity is not None

        # 4. Verify record in database
        db_rec = (
            db.query(UnifiedEvaluationRecord)
            .filter(UnifiedEvaluationRecord.response_id == response_id)
            .first()
        )
        assert db_rec is not None
        assert db_rec.response_id == response_id
        assert db_rec.evidence_snapshot_ref == response_id

        # 5. Verify back-population on response_feedback
        db.refresh(fb)
        assert fb.unified_record_ref == response_id

    finally:
        db.close()


def test_api_feedback_evaluation_endpoint():
    """Test POST /api/feedback-evaluation and GET /api/feedback-evaluation/{response_id}."""
    unique_id = uuid.uuid4().hex[:8]
    response_id = f"resp_api_{unique_id}"
    session_id = f"sess_api_{unique_id}"

    payload = {
        "response_id": response_id,
        "session_id": session_id,
        "turn_number": 1,
        "query_text": "What is the expense ratio of SBI Small Cap Fund?",
        "response_text": "The TER is 0.72% as of last factsheet.",
        "feedback_text": "Expense ratio is wrong. TER should be 0.85% for regular plan.",
        "selected_categories": ["F01", "F03"],
        "actor_id": "reviewer_qa",
        "actor_role": "Reviewer",
    }

    # POST /api/feedback-evaluation
    res = client.post("/api/feedback-evaluation", json=payload)
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
    data = res.json()
    assert data["response_id"] == response_id
    assert data["session_id"] == session_id
    assert "evaluation" in data
    eval_data = data["evaluation"]
    assert eval_data is not None
    assert eval_data["entry_route"] == "hitl"
    assert eval_data["response_id"] == response_id

    # GET /api/feedback-evaluation/{response_id}
    get_res = client.get(f"/api/feedback-evaluation/{response_id}")
    assert get_res.status_code == 200, f"Expected 200, got {get_res.status_code}: {get_res.text}"
    get_data = get_res.json()
    assert len(get_data) >= 1
    assert get_data[0]["response_id"] == response_id


def test_ui_feedback_background_task():
    """Test POST /api/feedback (UI endpoint) queues and executes feedback loop in background."""
    db: Session = SessionLocal()
    try:
        unique_id = uuid.uuid4().hex[:8]
        response_id = f"resp_ui_{unique_id}"
        session_id = f"sess_ui_{unique_id}"

        # Ensure QueryEvidence exists for this response
        qe = QueryEvidence(
            response_id=response_id,
            session_id=session_id,
            query_text="What is the minimum SIP amount for Mirae Asset Large Cap Fund?",
            assembled_context_json=[
                {
                    "chunk_id": "chk_sip_01",
                    "value": "Rs 1000",
                    "content": "Minimum SIP amount is Rs 1000 per month.",
                    "source_version": "v1",
                }
            ],
            synthesis_output_json={
                "answer": "Minimum SIP amount is Rs 500 per month.",
            },
            retrieval_mode="contextgraph",
            created_at="2026-09-23T10:00:00Z",
        )
        db.add(qe)
        db.commit()

        payload = {
            "response_id": response_id,
            "interaction_id": f"int_ui_{unique_id}",
            "session_id": session_id,
            "turn_number": 1,
            "query_text": qe.query_text,
            "actor_id": "reviewer_ui",
            "actor_role": "Compliance Officer",
            "selected_categories": ["F01"],
            "feedback_text": "SIP amount is Rs 1000 not Rs 500.",
        }

        # Starlette TestClient runs BackgroundTasks synchronously before returning
        res = client.post("/api/feedback", json=payload, headers={"X-User-Role": "compliance_officer"})
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"

        # Verify that UnifiedEvaluationRecord was built and persisted by background task
        rec = (
            db.query(UnifiedEvaluationRecord)
            .filter(UnifiedEvaluationRecord.response_id == response_id)
            .first()
        )
        assert rec is not None, "UnifiedEvaluationRecord should have been created by background task"
        assert rec.response_id == response_id
        assert rec.entry_route == "hitl"
        assert rec.root_cause in {"model", "knowledge", "retrieval", "graph", "compliance", "context_engineering"}

    finally:
        db.close()


if __name__ == "__main__":
    test_direct_trigger_feedback_loop()
    print("test_direct_trigger_feedback_loop PASSED!")
    test_api_feedback_evaluation_endpoint()
    print("test_api_feedback_evaluation_endpoint PASSED!")
    test_ui_feedback_background_task()
    print("test_ui_feedback_background_task PASSED!")
