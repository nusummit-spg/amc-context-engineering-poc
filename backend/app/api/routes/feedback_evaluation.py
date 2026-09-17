# """
# feedback_evaluation.py
# =======================
# API router for the human-feedback-loop pipeline: FeedbackRecord ingestion
# and UnifiedEvaluationRecord retrieval (Steps 1-6).

# Separate from app/api/routes/feedback.py, which targets the response_feedback
# audit table through a different store — not FeedbackRecord/UnifiedEvaluationRecord.

# Endpoints:
#   POST /api/feedback-evaluation                -> create FeedbackRecord + run pipeline
#   GET  /api/feedback-evaluation/records         -> list raw FeedbackRecords
#   GET  /api/feedback-evaluation/{response_id}   -> list evaluations for a response
# """

# import logging
# from datetime import datetime, timezone
# from typing import List
# from uuid import UUID

# from fastapi import APIRouter, Depends, HTTPException, Query, status
# from sqlalchemy.orm import Session

# from app.core.database import get_db
# from app.core.models import FeedbackRecord, UnifiedEvaluationRecord
# from app.schemas.feedback import (
#     FeedbackRequest,
#     FeedbackWithEvaluationResponse,
#     EvaluationSummary,
# )
# from app.services.feedback import trigger_feedback_loop

# logger = logging.getLogger("app.api.feedback_evaluation")

# router = APIRouter(prefix="/feedback-evaluation", tags=["feedback-evaluation"])


# @router.post("", response_model=FeedbackWithEvaluationResponse, status_code=status.HTTP_201_CREATED)
# def submit_feedback_and_evaluate(
#     payload: FeedbackRequest,
#     db: Session = Depends(get_db),
# ) -> FeedbackWithEvaluationResponse:
#     """Create a FeedbackRecord and run it through Steps 1-6, producing a UnifiedEvaluationRecord."""
#     try:
#         feedback = FeedbackRecord(
#             response_id=str(payload.response_id),
#             session_id=str(payload.session_id),
#             user_id=str(payload.user_id) if payload.user_id else None,
#             rating=payload.rating.value,
#             feedback_type=payload.feedback_type.value,
#             entity_name=payload.entity_name,
#             entity_type=payload.entity_type,
#             notes=payload.notes,
#             corrections=payload.corrections,
#             timestamp=payload.timestamp or datetime.now(timezone.utc),
#         )
#         db.add(feedback)
#         db.commit()
#         db.refresh(feedback)

#         evaluation = trigger_feedback_loop(db=db, feedback=feedback)

#         return FeedbackWithEvaluationResponse(
#             feedback_id=UUID(feedback.feedback_id),
#             response_id=UUID(feedback.response_id),
#             session_id=UUID(feedback.session_id),
#             message="Feedback recorded and evaluated.",
#             evaluation=EvaluationSummary.model_validate(evaluation),
#         )
#     except Exception as exc:
#         db.rollback()
#         logger.error("Failed to process feedback: %s", exc, exc_info=True)
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to record feedback and run evaluation pipeline.",
#         )


# @router.get("/records", response_model=List[dict])
# def list_feedback_records(
#     limit: int = Query(50, ge=1, le=500),
#     db: Session = Depends(get_db),
# ):
#     """Raw FeedbackRecord rows, most recent first."""
#     rows = (
#         db.query(FeedbackRecord)
#         .order_by(FeedbackRecord.timestamp.desc())
#         .limit(limit)
#         .all()
#     )
#     return [
#         {
#             "feedback_id": r.feedback_id,
#             "response_id": r.response_id,
#             "session_id": r.session_id,
#             "rating": r.rating,
#             "feedback_type": r.feedback_type,
#             "entity_name": r.entity_name,
#             "notes": r.notes,
#             "timestamp": r.timestamp.isoformat() if r.timestamp else None,
#         }
#         for r in rows
#     ]


# @router.get("/{response_id}", response_model=List[EvaluationSummary])
# def get_evaluations_for_response(
#     response_id: str,
#     db: Session = Depends(get_db),
# ):
#     """All UnifiedEvaluationRecord rows produced for a given response_id."""
#     rows = (
#         db.query(UnifiedEvaluationRecord)
#         .filter(UnifiedEvaluationRecord.response_id == response_id)
#         .all()
#     )
#     if not rows:
#         raise HTTPException(status_code=404, detail="No evaluations found for this response_id.")
#     return [EvaluationSummary.model_validate(r) for r in rows]