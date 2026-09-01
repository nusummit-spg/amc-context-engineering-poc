# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

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

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.compliance.failure_taxonomy import FAILURE_TAXONOMY, VALID_CODES
from app.db.feedback import get_feedback_store

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


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def submit_feedback(payload: FeedbackIn) -> Dict[str, Any]:
    """
    Record or update human failure taxonomy feedback for an LLM response.
    Requires at least one failure code OR non-empty commentary.
    Upserts by (response_id, actor_id).
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
