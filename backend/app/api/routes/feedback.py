# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================
#app/api/routes/feedback.py
"""
feedback.py
===========
API router for per-response human feedback capture and retrieval.
Endpoints:
  POST /api/feedback
  GET  /api/feedback
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.compliance.failure_taxonomy import FAILURE_TAXONOMY, VALID_CODES
from app.db.feedback import get_feedback_store
from app.schemas.feedback_quality import FeedbackQualityMetrics
from app.schemas.feedback_analytics import FeedbackCategoryAnalytics
from app.schemas.response_quality import ResponseQualityMetrics
from app.schemas.compliance_models import Role
from app.compliance.metrics_store import get_metrics_store
from app.compliance.security import get_client_role, require_roles

logger = logging.getLogger("app.api.feedback")

router = APIRouter(prefix="/feedback", tags=["feedback"])



@router.get("/taxonomy", response_model=Dict[str, Any])
def get_failure_taxonomy() -> Dict[str, Any]:
    """Retrieve the failure taxonomy categories with simple user-friendly labels and tooltips."""
    return {"categories": FAILURE_TAXONOMY}


class FeedbackIn(BaseModel):
    response_id: str = Field(..., min_length=1, description="Ties feedback to exact ContextGraph answer")
    interaction_id: str = Field(..., min_length=1, description="Interaction or conversation ID")
    session_id: str = Field(..., min_length=1, description="Session ID")
    turn_number: int = Field(..., ge=1, description="1-indexed turn number in session")
    query_text: Optional[str] = Field(default=None, max_length=2000, description="Question asked by user")
    actor_id: Optional[str] = Field(default=None, max_length=200, description="Reviewer / user identifier")
    actor_role: Optional[str] = Field(default="Compliance & Regulatory Officer", max_length=200)
    selected_categories: list[str] = Field(default_factory=list, description="Array of failure taxonomy codes F01-F12")
    free_text: Optional[str] = Field(default=None, max_length=2000, description="Reviewer commentary")
    client_timestamp: Optional[str] = Field(default=None, description="ISO timestamp from client")

    @field_validator("selected_categories")
    @classmethod
    def validate_codes(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip().upper() for c in v if c and c.strip()]
        bad = set(cleaned) - VALID_CODES
        if bad:
            raise ValueError(f"Unknown failure category codes: {sorted(bad)}. Allowed: {sorted(VALID_CODES)}")
        return cleaned


class FeedbackOut(BaseModel):
    feedback_id: str
    response_id: str
    stored_at: str
    status: str = "recorded"
    priority_tier: Optional[str] = None
    signal_quality_score: Optional[float] = None


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
@require_roles([Role.REVIEWER, Role.COMPLIANCE_OFFICER, Role.ADMIN])
def submit_feedback(
    payload: FeedbackIn,
    current_role: Role = Depends(get_client_role),
) -> Dict[str, Any]:

    """
    Record or update human failure taxonomy feedback for an LLM response.
    Requires at least one failure code OR non-empty commentary.
    Upserts by (response_id, actor_id) and evaluates signal quality.
    """
    free_text_clean = (payload.free_text or "").strip()
    if not payload.selected_categories and not free_text_clean:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Submit at least one category or a comment.",
        )

    try:
        store = get_feedback_store()
        result = store.upsert_feedback(
            response_id=payload.response_id,
            interaction_id=payload.interaction_id,
            session_id=payload.session_id,
            turn_number=payload.turn_number,
            selected_categories=payload.selected_categories,
            query_text=payload.query_text,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            free_text=free_text_clean if free_text_clean else None,
            client_timestamp=payload.client_timestamp,
        )

        # Automatically score feedback quality and assign priority tier
        metrics_store = get_metrics_store()
        quality_eval = metrics_store.evaluate_feedback_quality(
            feedback_id=result["feedback_id"],
            response_id=payload.response_id,
            free_text=free_text_clean,
            selected_categories=payload.selected_categories,
            actor_role=payload.actor_role,
        )
        result["priority_tier"] = quality_eval.priority_tier
        result["signal_quality_score"] = quality_eval.signal_quality_score

        return result
    except Exception as exc:
        logger.error("Failed to store response feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback in database. Please retry.",
        )


@router.get("", response_model=List[Dict[str, Any]])
def get_feedback(
    response_id: Optional[str] = Query(None, description="Filter by response ID"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    limit: int = Query(50, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """
    Retrieve stored feedback records, optionally filtered by response_id or session_id.
    """
    try:
        store = get_feedback_store()
        if response_id:
            return store.get_by_response_id(response_id)
        if session_id:
            return store.get_by_session_id(session_id)
        return store.list_all(limit=limit)
    except Exception as exc:
        logger.error("Failed to query feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve feedback records.",
        )


# =============================================================================
# Phase 1 Foundation Layer Feedback Metrics Endpoints
# =============================================================================

@router.get("/category-analytics", response_model=List[FeedbackCategoryAnalytics])
def get_feedback_category_analytics(
    period: str = Query(default="2024-09", description="Reporting period (e.g. 2024-09, 2024-09-week-1)")
) -> List[FeedbackCategoryAnalytics]:
    """
    Retrieve F01-F12 category frequency, trend, and velocity analytics for a reporting period.
    """
    metrics_store = get_metrics_store()
    return metrics_store.get_category_analytics(period=period)


@router.post("/category-analytics/refresh", response_model=List[FeedbackCategoryAnalytics])
@require_roles([Role.ADMIN, Role.COMPLIANCE_OFFICER])
def refresh_feedback_category_analytics(
    period: str = Query(default="2024-09", description="Reporting period to recalculate"),
    current_role: Role = Depends(get_client_role),
) -> List[FeedbackCategoryAnalytics]:
    """
    Trigger on-demand recalculation and aggregation of category analytics.
    """
    metrics_store = get_metrics_store()
    return metrics_store.refresh_category_analytics(period=period)


@router.get("/high-priority", response_model=List[FeedbackQualityMetrics])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN])
def get_high_priority_feedback(
    limit: int = Query(default=20, ge=1, le=100, description="Max high-priority items to return"),
    current_role: Role = Depends(get_client_role),
) -> List[FeedbackQualityMetrics]:
    """
    Fetch prioritized P0 (Critical/Regulatory) and P1 (High) feedback items for immediate triage.
    """
    metrics_store = get_metrics_store()
    return metrics_store.get_high_priority_feedback(limit=limit)


@router.get("/responses/{response_id}/quality-score", response_model=ResponseQualityMetrics)
def get_response_quality_metrics(response_id: str) -> ResponseQualityMetrics:
    """
    Fetch composite ResponseQualityMetrics and Traditional vs ContextGraph delta for a response.
    """
    metrics_store = get_metrics_store()
    return metrics_store.get_response_quality(response_id=response_id)


@router.get("/{feedback_id}/quality-metrics", response_model=FeedbackQualityMetrics)
def get_feedback_quality_metrics(feedback_id: str) -> FeedbackQualityMetrics:
    """
    Fetch detail score, clarity, credibility, actionability, and priority tier for a specific feedback ID.
    """
    metrics_store = get_metrics_store()
    metrics = metrics_store.get_feedback_quality(feedback_id=feedback_id)
    if not metrics:
        raise HTTPException(
            status_code=404,
            detail=f"Feedback quality metrics not found for feedback ID: {feedback_id}"
        )
    return metrics


class FeedbackQualityUpdateIn(BaseModel):
    priority_tier: Optional[str] = Field(None, description="P0, P1, P2, P3")
    action_difficulty: Optional[str] = Field(None, description="LOW, MEDIUM, HIGH")
    is_actionable: Optional[bool] = Field(None, description="Whether actionable")
    review_confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence rating")


@router.patch("/{feedback_id}/quality-metrics", response_model=FeedbackQualityMetrics)
@require_roles([Role.REVIEWER, Role.COMPLIANCE_OFFICER, Role.ADMIN])
def update_feedback_quality_assessment(
    feedback_id: str,
    update_in: FeedbackQualityUpdateIn,
    current_role: Role = Depends(get_client_role),
) -> FeedbackQualityMetrics:
    """
    Update feedback quality scoring or priority tier assignment.
    """
    metrics_store = get_metrics_store()
    updated = metrics_store.update_feedback_quality(
        feedback_id=feedback_id,
        update_data=update_in.model_dump(exclude_unset=True)
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Feedback quality record not found for feedback ID: {feedback_id}"
        )
    return updated



