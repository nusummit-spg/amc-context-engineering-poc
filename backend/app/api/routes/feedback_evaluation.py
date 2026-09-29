# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
feedback_evaluation.py
=======================
API router for the human-feedback-loop pipeline: FeedbackRecord ingestion
and UnifiedEvaluationRecord retrieval (Steps 1-4).

Endpoints:
  POST /api/feedback-evaluation                -> create FeedbackRecord + run pipeline
  GET  /api/feedback-evaluation/records         -> list raw feedback records
  GET  /api/feedback-evaluation/{response_id}   -> list evaluations for a response
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.models import _now_iso
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.services.feedback import trigger_feedback_loop

logger = logging.getLogger("app.api.feedback_evaluation")

router = APIRouter(prefix="/feedback-evaluation", tags=["feedback-evaluation"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class FeedbackEvaluationRequest(BaseModel):
    response_id: str = Field(..., description="Response ID to evaluate")
    session_id: str = Field(..., description="Session ID")
    turn_number: int = Field(default=1, description="Turn number in session")
    query_text: Optional[str] = Field(default=None, description="Original user query")
    response_text: Optional[str] = Field(default=None, description="Original response text")
    feedback_text: Optional[str] = Field(default=None, description="Reviewer commentary")
    selected_categories: list[str] = Field(default_factory=list, description="Taxonomy categories")
    actor_id: Optional[str] = Field(default="reviewer_01", description="Actor / reviewer ID")
    actor_role: Optional[str] = Field(default="Reviewer", description="Actor role")
    answer_relevance_score: Optional[int] = Field(default=None, ge=1, le=5)


class EvaluationSummary(BaseModel):
    session_id: str
    response_id: str
    entry_route: str
    feedback_ref: Optional[str] = None
    evidence_snapshot_ref: Optional[str] = None
    root_cause: Optional[str] = None
    severity: Optional[str] = None
    lifecycle_status: Optional[str] = "open"
    repair: Optional[bool] = False
    repair_target: Optional[str] = None
    adjudication_verdict: Optional[str] = None
    adjudication_confidence: Optional[float] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class FeedbackWithEvaluationResponse(BaseModel):
    feedback_id: str
    response_id: str
    session_id: str
    message: str
    evaluation: Optional[EvaluationSummary] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=FeedbackWithEvaluationResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback_and_evaluate(
    payload: FeedbackEvaluationRequest,
    db: Session = Depends(get_db),
) -> FeedbackWithEvaluationResponse:
    """Create a feedback record and run it through the feedback loop pipeline (Steps 1-4)."""
    try:
        now_iso = _now_iso()
        feedback_id = f"fb_{uuid.uuid4().hex[:12]}"

        # 1. Ensure QueryEvidence exists (satisfies foreign key constraint)
        qe = (
            db.query(QueryEvidence)
            .filter(QueryEvidence.response_id == payload.response_id)
            .first()
        )
        if not qe:
            qe = QueryEvidence(
                response_id=payload.response_id,
                session_id=payload.session_id,
                query_text=payload.query_text or "User query",
                assembled_context_json=[
                    {
                        "chunk_id": "chk_default",
                        "value": None,
                        "content": payload.query_text or "Context chunk",
                        "source_version": "v1",
                    }
                ],
                synthesis_output_json={
                    "answer": payload.response_text or "AMC response",
                },
                retrieval_mode="contextgraph",
                created_at=now_iso,
            )
            db.add(qe)
            db.commit()

        # 2. Insert or update ResponseFeedback
        fb = (
            db.query(ResponseFeedback)
            .filter(
                ResponseFeedback.response_id == payload.response_id,
                ResponseFeedback.actor_id == payload.actor_id,
            )
            .first()
        )
        if fb:
            feedback_id = fb.feedback_id
            fb.query_text = payload.query_text or fb.query_text
            fb.feedback_text = payload.feedback_text or fb.feedback_text
            fb.selected_categories = payload.selected_categories or fb.selected_categories
            fb.updated_at = now_iso
        else:
            fb = ResponseFeedback(
                feedback_id=feedback_id,
                response_id=payload.response_id,
                interaction_id=f"int_{uuid.uuid4().hex[:12]}",
                session_id=payload.session_id,
                turn_number=payload.turn_number,
                query_text=payload.query_text,
                response_text=payload.response_text,
                actor_id=payload.actor_id,
                actor_role=payload.actor_role,
                selected_categories=payload.selected_categories,
                feedback_text=payload.feedback_text,
                answer_relevance_score=payload.answer_relevance_score,
                created_at=now_iso,
                updated_at=now_iso,
            )
            db.add(fb)

        db.commit()

        # 3. Trigger feedback loop pipeline
        evaluation = trigger_feedback_loop(
            feedback_id=feedback_id,
            session_id=payload.session_id,
            response_id=payload.response_id,
            source="active",
            db=db,
        )

        return FeedbackWithEvaluationResponse(
            feedback_id=feedback_id,
            response_id=payload.response_id,
            session_id=payload.session_id,
            message="Feedback recorded and evaluated successfully.",
            evaluation=EvaluationSummary.model_validate(evaluation) if evaluation else None,
        )

    except Exception as exc:
        db.rollback()
        logger.error("Failed to process feedback evaluation: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record feedback and run evaluation pipeline: {exc}",
        )


@router.get("/records", response_model=List[Dict[str, Any]])
def list_feedback_records(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List raw feedback records, most recent first."""
    rows = (
        db.query(ResponseFeedback)
        .order_by(ResponseFeedback.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "feedback_id": r.feedback_id,
            "response_id": r.response_id,
            "session_id": r.session_id,
            "selected_categories": r.selected_categories,
            "feedback_text": r.feedback_text,
            "root_cause": r.root_cause,
            "unified_record_ref": r.unified_record_ref,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.get("/{response_id}", response_model=List[EvaluationSummary])
def get_evaluations_for_response(
    response_id: str,
    db: Session = Depends(get_db),
) -> List[EvaluationSummary]:
    """Retrieve all UnifiedEvaluationRecord rows produced for a given response_id."""
    rows = (
        db.query(UnifiedEvaluationRecord)
        .filter(UnifiedEvaluationRecord.response_id == response_id)
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evaluations found for response_id '{response_id}'.",
        )
    return [EvaluationSummary.model_validate(r) for r in rows]