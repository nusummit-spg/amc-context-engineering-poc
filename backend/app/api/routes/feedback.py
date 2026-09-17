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
from app.models.feedback_quality import FeedbackQualityMetrics
from app.models.feedback_analytics import FeedbackCategoryAnalytics
from app.models.response_quality import ResponseQualityMetrics
from app.models.compliance_models import Role
from app.models.feedback import FeedbackIn, FeedbackOut
from app.compliance.metrics_store import get_metrics_store
from app.compliance.security import get_client_role, require_roles

logger = logging.getLogger("app.api.feedback")

router = APIRouter(prefix="/feedback", tags=["feedback"])



@router.get("/taxonomy", response_model=Dict[str, Any])
def get_failure_taxonomy() -> Dict[str, Any]:
    """Retrieve the failure taxonomy categories with simple user-friendly labels and tooltips."""
    return {"categories": FAILURE_TAXONOMY}

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
    feedback_text_clean = (payload.feedback_text or "").strip()
    if not payload.selected_categories and not feedback_text_clean:
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
            feedback_text=feedback_text_clean if feedback_text_clean else None,
            client_timestamp=payload.client_timestamp,
        )

        # Automatically score feedback quality and assign priority tier
        metrics_store = get_metrics_store()
        quality_eval = metrics_store.evaluate_feedback_quality(
            feedback_id=result["feedback_id"],
            response_id=payload.response_id,
            feedback_text=feedback_text_clean,
            selected_categories=payload.selected_categories,
            actor_role=payload.actor_role,
        )
        result["priority_tier"] = quality_eval.priority_tier
        result["signal_quality_score"] = quality_eval.signal_quality_score

        # Track 8 + Track 6: Extract structured claims and register shadow patch
        if free_text_clean:
            try:
                from app.feedback import get_ner_pipeline
                from app.graph.correction_patch_layer import get_correction_patch_layer
                ner = get_ner_pipeline()
                claim = ner.extract_structured_claim(
                    feedback_text=free_text_clean,
                    original_query=payload.query_text
                )
                if claim and claim.resolved_entity_id and claim.attribute and claim.asserted_value:
                    patch_layer = get_correction_patch_layer()
                    patch_layer.add_correction(
                        entity_id=claim.resolved_entity_id,
                        attribute=claim.attribute,
                        canonical_value=claim.rejected_value or "canonical",
                        corrected_value=claim.asserted_value,
                        confidence=claim.confidence,
                        provenance={
                            "feedback_id": result["feedback_id"],
                            "actor_id": payload.actor_id,
                            "source": "User Feedback Submission"
                        },
                        approved=False
                    )
                    logger.info("Auto-registered correction patch for %s.%s = %s",
                                claim.resolved_entity_id, claim.attribute, claim.asserted_value)
            except Exception as claim_exc:
                logger.debug("Structured claim extraction notice: %s", claim_exc)

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


class FollowUpDetectionIn(BaseModel):
    session_id: str = Field(..., description="Session identifier")
    previous_response_id: str = Field(..., description="Response ID being corrected")
    follow_up_query: str = Field(..., min_length=1, description="User's follow-up query text")
    original_response: Optional[str] = Field(None, description="Original response text if available")
    original_query: Optional[str] = Field(None, description="Original query text if available")


_dissatisfaction_detector = None


def get_dissatisfaction_detector():
    global _dissatisfaction_detector
    if _dissatisfaction_detector is None:
        from app.feedback.dissatisfaction_detector import DissatisfactionDetector
        _dissatisfaction_detector = DissatisfactionDetector()
    return _dissatisfaction_detector


@router.post("/follow-up-detection", response_model=Dict[str, Any])
def detect_follow_up_correction(
    payload: FollowUpDetectionIn,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Detect if a follow-up query is actually an implicit correction attempt.
    If detected, auto-creates structured feedback in the feedback store.
    """
    store = get_feedback_store()
    prev_interaction = store.get_interaction(payload.session_id, payload.previous_response_id)

    original_query = payload.original_query or (prev_interaction.get("query_text") if prev_interaction else "") or ""
    original_response = payload.original_response or (prev_interaction.get("free_text") if prev_interaction else "") or ""

    detector = get_dissatisfaction_detector()
    try:
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query=payload.follow_up_query,
            original_response=original_response,
            original_query=original_query
        )
    except Exception as exc:
        logger.error("Dissatisfaction detection failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Dissatisfaction detection service error"
        )

    if is_correction and claim:
        claim_dict = {
            "entity_id": claim.entity_id,
            "entity_name": claim.entity_name,
            "attribute": claim.attribute,
            "asserted_value": claim.asserted_value,
            "rejected_value": claim.rejected_value,
            "raw_text": claim.raw_text,
            "confidence": claim.confidence
        }
        try:
            feedback_result = store.update_interaction_feedback(
                session_id=payload.session_id,
                response_id=payload.previous_response_id,
                feedback_data={
                    "feedback_type": "dissatisfaction_followup",
                    "feedback_text": claim.raw_text,
                    "selected_categories": ["F08"],
                    "structured_claim": claim_dict,
                    "actor_id": current_role.value,
                    "actor_role": current_role.value,
                    "query_text": original_query
                }
            )
            return {
                "correction_detected": True,
                "feedback_created": True,
                "feedback_id": feedback_result.get("feedback_id"),
                "claim": claim_dict
            }
        except Exception as exc:
            logger.error("Failed to auto-create feedback record: %s", exc, exc_info=True)
            return {
                "correction_detected": True,
                "feedback_created": False,
                "claim": claim_dict,
                "error": str(exc)
            }

    return {
        "correction_detected": False,
        "feedback_created": False,
        "claim": None
    }



