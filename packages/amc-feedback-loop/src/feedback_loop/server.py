"""
FastAPI server for AMC Human Feedback Loop Service.
Standalone microservice for feedback ingestion, 7-step pipeline execution, and evaluation.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from feedback_loop.adapters.db import InMemoryDatabaseAdapter, AbstractDatabaseAdapter
from feedback_loop.adapters.evidence import InMemoryEvidenceAdapter, AbstractEvidenceAdapter
from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.domain_models import (
    EvidenceChunk,
    EvidenceSnapshot,
    FeedbackRecord,
    FeedbackSource,
    FeedbackType,
    RatingType,
)
from feedback_loop.orchestrator import RecordBuilder
from feedback_loop.logging import (
    setup_feedback_logging,
    get_feedback_logger,
    log_step_info,
    log_step_warning,
    log_step_error,
)

setup_feedback_logging()
logger = get_feedback_logger("server")

app = FastAPI(
    title="AMC Feedback Loop Service",
    description="Microservice for human feedback ingestion and evaluation pipeline",
    version="0.1.2",
)

# Global in-memory storage for standalone microservice runs
_config = FeedbackLoopConfig()
_db_adapter = InMemoryDatabaseAdapter()
_evidence_adapter = InMemoryEvidenceAdapter()

_builder = RecordBuilder(_config, _db_adapter, _evidence_adapter)
_recent_records: List[Dict[str, Any]] = []


# ── Schemas ───────────────────────────────────────────────────────────────────

class FeedbackSubmissionIn(BaseModel):
    session_id: str
    response_id: str
    feedback_text: str
    original_query: Optional[str] = ""
    original_response: Optional[str] = ""
    issue_types: Optional[List[str]] = Field(default_factory=lambda: ["general"])
    source: str = "web_interface"
    entity_name: Optional[str] = None
    rating: Optional[str] = "negative"


class FollowUpDetectionIn(BaseModel):
    session_id: str
    previous_response_id: str
    original_query: str
    original_response: str
    follow_up_query: str
    session_history: Optional[List[str]] = Field(default_factory=list)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Health check endpoint for service monitoring and circuit breakers.

    Returns:
        Result of the operation.
    """
    log_step_info(logger, "HEALTH_CHECK", "Health check queried")
    return {
        "status": "ok",
        "service": "feedback-loop",
        "version": "0.1.2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/feedback")
async def submit_feedback(payload: FeedbackSubmissionIn):
    """Ingest user feedback, construct an evidence snapshot, and execute
    the 7-step evaluation pipeline (Classification, Enrichment, Router, Adjudication,
    Diagnosis, Repair Analysis, Tiered Evaluation).

    Args:
        payload (FeedbackSubmissionIn): Request or event payload.

    Returns:
        Result of the operation.
    """
    feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    log_step_info(
        logger,
        "SUBMIT_FEEDBACK_REQUEST",
        "Received feedback submission: feedback_id=%s, session_id=%s, response_id=%s, rating=%s",
        feedback_id,
        payload.session_id,
        payload.response_id,
        payload.rating,
    )

    try:
        # 1. Seed or link evidence snapshot in evidence adapter
        if isinstance(_evidence_adapter, InMemoryEvidenceAdapter):
            snapshot = EvidenceSnapshot(
                response_id=payload.response_id,
                original_query=payload.original_query or "Query",
                response_text=payload.original_response or "",
                entity_name=payload.entity_name,
                evidence_selected=[
                    EvidenceChunk(
                        chunk_id=f"chunk_{uuid.uuid4().hex[:6]}",
                        content=payload.original_response[:300] if payload.original_response else "",
                    )
                ],
            )
            _evidence_adapter.seed_snapshot(snapshot)

        # 2. Build domain feedback record
        record = FeedbackRecord(
            feedback_id=feedback_id,
            session_id=payload.session_id,
            response_id=payload.response_id,
            user_id="microservice_client",
            feedback_type=FeedbackType.CORRECTION,
            rating=RatingType.NEGATIVE if payload.rating == "negative" else RatingType.POSITIVE,
            notes=payload.feedback_text,
            entity_name=payload.entity_name,
            source=FeedbackSource.ACTIVE,
            received_at=now,
        )

        # 3. Store record if in-memory
        if isinstance(_db_adapter, InMemoryDatabaseAdapter):
            _db_adapter.seed_feedback(record)

        # 4. Run pipeline
        unified = _builder.build(record)

        result_data = {
            "status": "recorded",
            "feedback_id": feedback_id,
            "response_id": payload.response_id,
            "session_id": payload.session_id,
            "timestamp": now.isoformat(),
            "unified_evaluation": {
                "root_cause": str(unified.root_cause) if unified and unified.root_cause else "knowledge",
                "severity": str(unified.severity) if unified and unified.severity else "medium",
                "needs_repair": unified.repair if unified else False,
                "repair_target": str(unified.repair_target) if unified and unified.repair_target else None,
                "lifecycle_status": str(unified.lifecycle_status) if unified else "open",
            } if unified else None,
        }

        _recent_records.insert(0, result_data)
        if len(_recent_records) > 100:
            _recent_records.pop()

        eval_summary = result_data["unified_evaluation"]
        log_step_info(
            logger,
            "SUBMIT_FEEDBACK_SUCCESS",
            "Feedback %s evaluated: root_cause=%s, severity=%s, repair=%s, repair_target=%s",
            feedback_id,
            eval_summary.get("root_cause") if eval_summary else "none",
            eval_summary.get("severity") if eval_summary else "none",
            eval_summary.get("needs_repair") if eval_summary else False,
            eval_summary.get("repair_target") if eval_summary else None,
        )
        return result_data
    except Exception as exc:
        log_step_error(logger, "SUBMIT_FEEDBACK_ERROR", "Feedback submission failed for %s: %s", feedback_id, exc)
        raise


@app.post("/api/feedback/follow-up-detection")
async def detect_follow_up_correction(payload: FollowUpDetectionIn):
    """Detect if a user follow-up query represents an implicit correction.

    Args:
        payload (FollowUpDetectionIn): Request or event payload.

    Returns:
        Result of the operation.
    """
    log_step_info(
        logger,
        "FOLLOW_UP_DETECTION_REQUEST",
        "Evaluating follow-up for correction: session_id=%s, prev_resp=%s",
        payload.session_id,
        payload.previous_response_id,
    )
    followup_lower = (payload.follow_up_query or "").lower().strip()
    correction_cues = ["no", "actually", "wrong", "not", "meant", "instead", "incorrect", "correction", "should be"]
    is_correction = any(cue in followup_lower.split() or followup_lower.startswith(cue) for cue in correction_cues)
    confidence = 0.85 if is_correction else 0.15

    log_step_info(
        logger,
        "FOLLOW_UP_DETECTION_SUCCESS",
        "Follow-up detection evaluated: is_correction=%s, confidence=%.2f",
        is_correction,
        confidence,
    )

    return {
        "is_correction": is_correction,
        "confidence": confidence,
        "follow_up_query": payload.follow_up_query,
        "previous_response_id": payload.previous_response_id,
    }


@app.get("/api/feedback/{feedback_id}")
async def get_feedback(feedback_id: str):
    """Retrieve feedback evaluation record by ID.

    Args:
        feedback_id (str): Unique identifier of the feedback.

    Returns:
        The requested feedback.
    """
    log_step_info(logger, "GET_FEEDBACK_REQUEST", "Retrieving feedback record %s", feedback_id)
    for r in _recent_records:
        if r.get("feedback_id") == feedback_id:
            return r
    log_step_warning(logger, "GET_FEEDBACK_NOT_FOUND", "Feedback record %s not found", feedback_id)
    raise HTTPException(status_code=404, detail=f"Feedback record {feedback_id} not found")


@app.get("/api/feedback/recent")
async def get_recent_feedback(limit: int = Query(20, ge=1, le=100)):
    """List recent feedback evaluations.

    Args:
        limit (int): Maximum number of records to return.

    Returns:
        The requested recent feedback.
    """
    log_step_info(logger, "GET_RECENT_FEEDBACK", "Listing recent feedback records (limit=%d)", limit)
    return {"feedback": _recent_records[:limit]}
