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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

import uuid
import json
from datetime import datetime, timezone

from app.compliance.failure_taxonomy import FAILURE_TAXONOMY, VALID_CODES
from app.models.feedback_quality import FeedbackQualityMetrics
from app.models.feedback_analytics import FeedbackCategoryAnalytics
from app.models.response_quality import ResponseQualityMetrics
from app.models.compliance_models import Role
from app.models.feedback import FeedbackIn, FeedbackOut
from app.compliance.metrics_store import get_metrics_store
from app.compliance.security import get_client_role, require_roles
from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback
from sqlalchemy.orm import Session

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
    background_tasks: BackgroundTasks,
    current_role: Role = Depends(get_client_role),
) -> Dict[str, Any]:

    """
    Record or update human failure taxonomy feedback for an LLM response.
    Requires at least one failure code OR non-empty commentary.
    Upserts by (response_id, actor_id) directly to data.db (single source of truth).
    """
    feedback_text_clean = (payload.feedback_text or "").strip()
    if not payload.selected_categories and not feedback_text_clean:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Submit at least one category or a comment.",
        )

    # Cancel active timer if one is running for this query/session
    try:
        from app.feedback.feedback_timer import get_feedback_timer_manager
        timer_mgr = get_feedback_timer_manager()
        timer_turn = timer_mgr._pending_turns.get(payload.session_id)
        if timer_turn and timer_turn.response_id == payload.response_id:
            if timer_turn.timer_task and not timer_turn.timer_task.done():
                timer_turn.timer_task.cancel()
                logger.info(
                    "[TIMER_CANCELLED] Cancelled active timer for session_id=%s, response_id=%s due to incoming feedback",
                    payload.session_id,
                    payload.response_id,
                )
            timer_turn.is_recorded = True
    except Exception as timer_err:
        logger.debug("FeedbackTimer check notice in submit_feedback: %s", timer_err)

    db = SessionLocal()
    try:
        # Check if feedback already exists for this query/session (handles timer expiration or previous query turns)
        existing = db.query(ResponseFeedback).filter(
            (ResponseFeedback.response_id == payload.response_id) |
            ((ResponseFeedback.session_id == payload.session_id) & (ResponseFeedback.interaction_id == payload.interaction_id))
        ).first()
        
        now_iso = datetime.now(timezone.utc).isoformat()
        feedback_id = existing.feedback_id if existing else f"fb_{uuid.uuid4().hex[:12]}"
        
        if existing:
            # Late or on-time feedback updating existing record without duplicate
            logger.info(
                "[LATE_FEEDBACK_HANDLED] Identified existing feedback record feedback_id=%s for session_id=%s, response_id=%s. Updating record without duplicates.",
                existing.feedback_id,
                payload.session_id,
                payload.response_id,
            )
            existing.interaction_id = payload.interaction_id or existing.interaction_id
            existing.session_id = payload.session_id
            existing.turn_number = payload.turn_number or existing.turn_number
            existing.query_text = payload.query_text or existing.query_text
            existing.selected_categories = payload.selected_categories
            existing.feedback_text = feedback_text_clean if feedback_text_clean else existing.feedback_text
            existing.actor_id = payload.actor_id or existing.actor_id
            existing.actor_role = payload.actor_role or existing.actor_role
            existing.client_timestamp = payload.client_timestamp or existing.client_timestamp
            existing.updated_at = now_iso
            db.commit()
            logger.info(
                "[RECORD_UPDATED] Updated feedback record feedback_id=%s in data.db for response_id=%s",
                existing.feedback_id,
                payload.response_id,
            )
            logger.info(
                "[DUPLICATE_PREVENTED] Prevented duplicate feedback insertion for session_id=%s, response_id=%s; record feedback_id=%s updated.",
                payload.session_id,
                payload.response_id,
                existing.feedback_id,
            )
        else:
            # Create new feedback record
            new_feedback = ResponseFeedback(
                feedback_id=feedback_id,
                response_id=payload.response_id,
                interaction_id=payload.interaction_id,
                session_id=payload.session_id,
                turn_number=payload.turn_number,
                query_text=payload.query_text,
                actor_id=payload.actor_id,
                actor_role=payload.actor_role,
                selected_categories=payload.selected_categories,
                feedback_text=feedback_text_clean if feedback_text_clean else None,
                client_timestamp=payload.client_timestamp,
                created_at=now_iso,
                updated_at=now_iso,
            )
            db.add(new_feedback)
            db.commit()
            logger.info(
                "[RECORD_INSERTED] Inserted feedback record into data.db: feedback_id=%s, response_id=%s, session_id=%s",
                feedback_id,
                payload.response_id,
                payload.session_id,
            )
        
        result = {
            "feedback_id": feedback_id,
            "response_id": payload.response_id,
            "stored_at": now_iso,
            "status": "recorded",
        }

        # Automatically score feedback quality and assign priority tier
        metrics_store = get_metrics_store()
        quality_eval = metrics_store.evaluate_feedback_quality(
            feedback_id=feedback_id,
            response_id=payload.response_id,
            feedback_text=feedback_text_clean,
            selected_categories=payload.selected_categories,
            actor_role=payload.actor_role,
        )
        result["priority_tier"] = quality_eval.priority_tier
        result["signal_quality_score"] = quality_eval.signal_quality_score

        # Track 8 + Track 6: Extract structured claims and register shadow patch
        if feedback_text_clean:
            try:
                from app.feedback import get_ner_pipeline
                from app.graph.correction_patch_layer import get_correction_patch_layer
                ner = get_ner_pipeline()
                claim = ner.extract_structured_claim(
                    feedback_text=feedback_text_clean,
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
                            "feedback_id": feedback_id,
                            "actor_id": payload.actor_id,
                            "source": "User Feedback Submission"
                        },
                        approved=False
                    )
                    logger.info("Auto-registered correction patch for %s.%s = %s",
                                claim.resolved_entity_id, claim.attribute, claim.asserted_value)
            except Exception as claim_exc:
                logger.debug("Structured claim extraction notice: %s", claim_exc)

        # Trigger human-feedback-loop in background
        try:
            from app.services.feedback import trigger_feedback_loop
            background_tasks.add_task(
                trigger_feedback_loop,
                feedback_id=feedback_id,
                session_id=payload.session_id,
                response_id=payload.response_id,
                source="active",
            )
        except Exception as fb_loop_exc:
            logger.warning("Could not queue feedback loop task: %s", fb_loop_exc)

        return result
    except Exception as exc:
        db.rollback()
        logger.error("Failed to store response feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback in database. Please retry.",
        )
    finally:
        db.close()


@router.get("", response_model=List[Dict[str, Any]])
def get_feedback(
    response_id: Optional[str] = Query(None, description="Filter by response ID"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    limit: int = Query(50, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """
    Retrieve stored feedback records from data.db, optionally filtered by response_id or session_id.
    """
    db = SessionLocal()
    try:
        query = db.query(ResponseFeedback)
        
        if response_id:
            query = query.filter(ResponseFeedback.response_id == response_id)
        elif session_id:
            query = query.filter(ResponseFeedback.session_id == session_id)
        
        results = query.order_by(ResponseFeedback.updated_at.desc()).limit(limit).all()
        
        feedback_list = []
        for fb in results:
            feedback_list.append({
                "feedback_id": fb.feedback_id,
                "response_id": fb.response_id,
                "interaction_id": fb.interaction_id,
                "session_id": fb.session_id,
                "turn_number": fb.turn_number,
                "query_text": fb.query_text,
                "actor_id": fb.actor_id,
                "actor_role": fb.actor_role,
                "selected_categories": fb.selected_categories,
                "feedback_text": fb.feedback_text,
                "client_timestamp": fb.client_timestamp,
                "created_at": fb.created_at,
                "updated_at": fb.updated_at,
            })
        
        return feedback_list
    except Exception as exc:
        logger.error("Failed to query feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve feedback records.",
        )
    finally:
        db.close()


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
    session_history: Optional[List[str]] = Field(default=None, description="Optional previous queries in session")


FollowUpDetectionRequest = FollowUpDetectionIn


_dissatisfaction_detector = None


def get_dissatisfaction_detector():
    global _dissatisfaction_detector
    if _dissatisfaction_detector is None:
        from app.feedback.dissatisfaction_detector import DissatisfactionDetector
        _dissatisfaction_detector = DissatisfactionDetector()
    return _dissatisfaction_detector


async def run_follow_up_detection_logic(
    session_id: str,
    previous_response_id: str,
    follow_up_query: str,
    original_query: Optional[str] = "",
    original_response: Optional[str] = "",
    session_history: Optional[List[str]] = None,
    current_role_value: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None,
) -> Dict[str, Any]:
    """
    Core reusable logic to detect if a follow-up query is an implicit correction attempt.
    If detected, auto-creates structured feedback in data.db and registers a provisional
    patch in CorrectionPatchLayer (passive self-healing).
    """
    db = SessionLocal()
    try:
        # Retrieve previous interaction from data.db
        prev_interaction = db.query(ResponseFeedback).filter(
            (ResponseFeedback.response_id == previous_response_id) &
            (ResponseFeedback.session_id == session_id)
        ).order_by(ResponseFeedback.updated_at.desc()).first()

        orig_query = original_query or (prev_interaction.query_text if prev_interaction else "") or ""
        orig_resp = original_response or (prev_interaction.feedback_text if prev_interaction else "") or ""

        detector = get_dissatisfaction_detector()
        try:
            is_correction, claim = detector.is_correction_attempt(
                follow_up_query=follow_up_query,
                original_response=orig_resp,
                original_query=orig_query,
                previous_queries=session_history or []
            )
        except Exception as exc:
            logger.error("Dissatisfaction detection failed: %s", exc, exc_info=True)
            return {
                "is_correction": False,
                "correction_detected": False,
                "feedback_created": False,
                "auto_created_feedback": False,
                "confidence": 0.0,
                "error": str(exc),
            }

        if is_correction and claim:
            target_entity_id = claim.entity_id
            if not target_entity_id and claim.entity_name:
                try:
                    from app.feedback.fund_name_matcher import get_fund_name_matcher
                    matcher = get_fund_name_matcher()
                    match_res = matcher.match_fund(claim.entity_name)
                    if match_res and match_res.get("isin"):
                        target_entity_id = match_res["isin"]
                except Exception as match_exc:
                    logger.debug("Fund matching notice in follow-up: %s", match_exc)
                if not target_entity_id:
                    target_entity_id = claim.entity_name

            claim_dict = {
                "entity_id": target_entity_id,
                "entity_name": claim.entity_name,
                "attribute": claim.attribute,
                "asserted_value": claim.asserted_value,
                "rejected_value": claim.rejected_value,
                "raw_text": claim.raw_text,
                "confidence": claim.confidence
            }
            try:
                role_val = current_role_value or Role.ADMIN.value
                now_iso = datetime.now(timezone.utc).isoformat()
                existing = db.query(ResponseFeedback).filter(
                    (ResponseFeedback.response_id == previous_response_id) &
                    (ResponseFeedback.session_id == session_id)
                ).order_by(ResponseFeedback.updated_at.desc()).first()

                if not existing:
                    existing = db.query(ResponseFeedback).filter(
                        (ResponseFeedback.response_id == previous_response_id) &
                        (ResponseFeedback.actor_id == role_val)
                    ).first()
                
                feedback_id = existing.feedback_id if existing else f"fb_{uuid.uuid4().hex[:12]}"
                
                if existing:
                    existing.selected_categories = ["F08"]
                    existing.feedback_text = claim.raw_text
                    existing.automated_category = "auto_correction_detected"
                    existing.automated_confidence = claim.confidence
                    if not existing.actor_id:
                        existing.actor_id = role_val
                        existing.actor_role = role_val
                    existing.updated_at = now_iso
                else:
                    new_feedback = ResponseFeedback(
                        feedback_id=feedback_id,
                        response_id=previous_response_id,
                        interaction_id=f"inter_{uuid.uuid4().hex[:8]}",
                        session_id=session_id,
                        turn_number=prev_interaction.turn_number if prev_interaction else 1,
                        query_text=orig_query,
                        actor_id=role_val,
                        actor_role=role_val,
                        selected_categories=["F08"],
                        feedback_text=claim.raw_text,
                        automated_category="auto_correction_detected",
                        automated_confidence=claim.confidence,
                        created_at=now_iso,
                        updated_at=now_iso,
                    )
                    db.add(new_feedback)
                
                db.commit()

                # Auto-register provisional correction in CorrectionPatchLayer
                patch_id = None
                if target_entity_id and claim.attribute and claim.asserted_value:
                    try:
                        from app.graph.correction_patch_layer import get_correction_patch_layer
                        patch_layer = get_correction_patch_layer()
                        patch_id = patch_layer.add_correction(
                            entity_id=target_entity_id,
                            attribute=claim.attribute,
                            canonical_value=claim.rejected_value or "canonical",
                            corrected_value=claim.asserted_value,
                            confidence=min(claim.confidence * 0.8, 0.75),
                            provenance={
                                "source": "passive_followup_detection",
                                "feedback_id": feedback_id,
                                "session_id": session_id,
                            },
                            approved=False,
                        )
                        logger.info("Auto-registered passive patch %s for %s.%s = %s",
                                    patch_id, target_entity_id, claim.attribute, claim.asserted_value)
                    except Exception as patch_exc:
                        logger.warning("Could not auto-register passive patch: %s", patch_exc)

                # Trigger background feedback loop
                try:
                    from app.services.feedback import trigger_feedback_loop
                    if background_tasks:
                        background_tasks.add_task(
                            trigger_feedback_loop,
                            feedback_id=feedback_id,
                            session_id=session_id,
                            response_id=previous_response_id,
                            source="passive_followup",
                        )
                    else:
                        import asyncio
                        asyncio.create_task(asyncio.to_thread(
                            trigger_feedback_loop,
                            feedback_id=feedback_id,
                            session_id=session_id,
                            response_id=previous_response_id,
                            source="passive_followup",
                        ))
                except Exception as fb_exc:
                    logger.debug("Could not queue feedback loop task: %s", fb_exc)

                return {
                    "is_correction": True,
                    "correction_detected": True,
                    "feedback_created": True,
                    "auto_created_feedback": True,
                    "feedback_id": feedback_id,
                    "patch_id": patch_id,
                    "confidence": claim.confidence,
                    "signals": {
                        "is_frustrated": True,
                        "same_referent": True,
                        "has_correction_lang": True,
                    },
                    "structured_claim": claim_dict,
                    "claim": claim_dict,
                }
            except Exception as exc:
                db.rollback()
                logger.error("Failed to auto-create feedback record: %s", exc, exc_info=True)
                return {
                    "is_correction": True,
                    "correction_detected": True,
                    "feedback_created": False,
                    "auto_created_feedback": False,
                    "claim": claim_dict,
                    "structured_claim": claim_dict,
                    "confidence": claim.confidence,
                    "error": str(exc),
                }

        return {
            "is_correction": False,
            "correction_detected": False,
            "feedback_created": False,
            "auto_created_feedback": False,
            "confidence": 0.0,
            "signals": {},
            "claim": None,
            "structured_claim": None,
        }
    finally:
        db.close()


@router.post("/follow-up-detection", response_model=Dict[str, Any])
async def detect_follow_up_correction(
    payload: FollowUpDetectionIn,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Detect if a follow-up query is actually an implicit correction attempt.
    If detected, auto-creates structured feedback in data.db and registers a provisional
    patch in CorrectionPatchLayer (passive self-healing).
    """
    res = await run_follow_up_detection_logic(
        session_id=payload.session_id,
        previous_response_id=payload.previous_response_id,
        follow_up_query=payload.follow_up_query,
        original_query=payload.original_query,
        original_response=payload.original_response,
        session_history=payload.session_history,
        current_role_value=current_role.value if current_role else None,
        background_tasks=background_tasks,
    )
    if res.get("error") and not res.get("is_correction"):
        raise HTTPException(
            status_code=500,
            detail="Dissatisfaction detection service error"
        )
    return res



