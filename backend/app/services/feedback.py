# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
feedback.py
===========
Service layer connecting AMC feedback submissions to the human-feedback-loop module.
"""

from __future__ import annotations

import logging
from typing import Optional
from sqlalchemy.orm import Session

from feedback_loop import FeedbackLoopConfig, start_feedback_loop
from app.adapters.feedback_adapters import AMCDatabaseAdapter, AMCEvidenceAdapter
from app.core.database import SessionLocal
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.services.repair_service import process_unified_record_for_repair_sync
from app.core.logging import (
    log_step_info,
    log_step_warning,
    log_step_error,
    log_step_debug,
)

logger = logging.getLogger("app.services.feedback")

_config = FeedbackLoopConfig()
_db_adapter = AMCDatabaseAdapter(session_factory=SessionLocal)
_evidence_adapter = AMCEvidenceAdapter(session_factory=SessionLocal)


def trigger_feedback_loop(
    feedback_id: str,
    session_id: str,
    response_id: str,
    source: str = "active",
    db: Optional[Session] = None,
    process_repair: bool = True,
) -> Optional[UnifiedEvaluationRecord]:
    """
    Executes the human-feedback-loop pipeline (Steps 1–4) for a feedback record.

    Uses AMC's AMCDatabaseAdapter and AMCEvidenceAdapter to read from
    response_feedback and query_evidence, and write the adjudicated
    result to unified_evaluation_records.
    
    Args:
        feedback_id: Primary key of the feedback record
        session_id: User session ID
        response_id: Response being evaluated
        source: 'active' or 'passive' feedback source
        db: Optional database session
        process_repair: Whether to automatically process repairs (default: True)
    
    Returns:
        UnifiedEvaluationRecord if created, else None
    """
    log_step_info(
        logger,
        "FEEDBACK_LOOP_START",
        "Step 1: Starting feedback loop for response %s (source=%s, feedback_id=%s)",
        response_id,
        source,
        feedback_id,
    )

    try:
        # Verify QueryEvidence exists before starting feedback loop
        check_db = db or SessionLocal()
        try:
            from app.schemas.query_evidence_table import QueryEvidence
            has_evidence = (
                check_db.query(QueryEvidence)
                .filter(QueryEvidence.response_id == response_id)
                .first()
            )
            if not has_evidence:
                log_step_info(logger, "FEEDBACK_LOOP_SKIP", "Skipping feedback loop: Query evidence not found for response %s", response_id)
                return None
        finally:
            if db is None:
                check_db.close()

        log_step_info(logger, "FEEDBACK_LOOP_EXEC", "Step 2: Running 4-tier evaluation pipeline (Enrichment -> Routing -> Adjudication -> Diagnosis)...")
        success = start_feedback_loop(
            feedback_id=feedback_id,
            session_id=session_id,
            response_id=response_id,
            source=source,
            config=_config,
            db=_db_adapter,
            evidence_adapter=_evidence_adapter,
        )
        log_step_info(logger, "FEEDBACK_LOOP_COMPLETE", "Step 3: Feedback evaluation pipeline finished (success=%s)", success)

        # Retrieve the generated UnifiedEvaluationRecord
        local_db = db or SessionLocal()
        try:
            record = (
                local_db.query(UnifiedEvaluationRecord)
                .filter(UnifiedEvaluationRecord.response_id == response_id)
                .first()
            )
            
            if not record:
                log_step_warning(logger, "NO_UNIFIED_RECORD", "No UnifiedEvaluationRecord created for response_id=%s", response_id)
                return None
            
            log_step_info(
                logger,
                "UNIFIED_RECORD_CREATED",
                "Step 4: Created Unified Evaluation Record: route=%s, root_cause=%s, severity=%s, repair_needed=%s",
                record.entry_route, record.root_cause, record.severity, record.repair
            )

            # Ensure ResponseFeedback reverse reference is set to prevent repetitive retries
            try:
                from app.schemas.response_feedback_table import ResponseFeedback
                fb = local_db.query(ResponseFeedback).filter(
                    (ResponseFeedback.feedback_id == feedback_id) |
                    (ResponseFeedback.response_id == response_id)
                ).first()
                if fb and not fb.unified_record_ref:
                    fb.unified_record_ref = record.response_id
                    rc_val = record.root_cause.value if hasattr(record.root_cause, "value") else str(record.root_cause)
                    fb.root_cause = rc_val
                    local_db.commit()
            except Exception as fb_sync_err:
                logger.debug("ResponseFeedback reverse reference sync notice: %s", fb_sync_err)
            
            # NEW: If repair is flagged, trigger repair engine microservice
            if process_repair and record.repair:
                log_step_info(
                    logger,
                    "REPAIR_FLAGGED",
                    "Step 5: Repair required for response %s: target=%s, root_cause=%s",
                    response_id, record.repair_target, record.root_cause
                )
                try:
                    # Import here to avoid circular imports
                    import asyncio
                    from app.services.repair_integration import trigger_repair_on_feedback
                    
                    # Run async repair trigger safely
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        # Schedule on existing loop with error logging to prevent nested loop / threadpool deadlock
                        from app.core.async_utils import create_task_with_logging
                        create_task_with_logging(
                            trigger_repair_on_feedback(record, db=local_db),
                            task_name=f"trigger_repair_{response_id}",
                            custom_logger=logger,
                        )
                        log_step_info(
                            logger,
                            "REPAIR_INTEGRATION_SCHEDULED",
                            "Step 6: Scheduled background repair engine task for response %s",
                            response_id,
                        )
                    else:
                        repair_result = asyncio.run(trigger_repair_on_feedback(record, db=local_db))
                        log_step_info(
                            logger,
                            "REPAIR_INTEGRATION_RESULT",
                            "Step 6b: Repair engine completed: success=%s, %d patches created",
                            repair_result.get("success"),
                            len(repair_result.get("patches_created", []))
                        )
                        if repair_result.get("patches_created"):
                            log_step_info(
                                logger,
                                "PATCHES_CREATED",
                                "Step 6c: Patches created via repair engine: %s",
                                repair_result["patches_created"]
                            )
                
                except Exception as repair_exc:
                    log_step_error(
                        logger,
                        "REPAIR_INTEGRATION_ERROR",
                        "Repair engine error: %s",
                        repair_exc,
                    )
            
            return record
        finally:
            if db is None:
                local_db.close()

    except Exception as exc:
        log_step_error(
            logger,
            "FEEDBACK_LOOP_FAILED",
            "Feedback loop failed for feedback_id=%s: %s",
            feedback_id,
            exc,
        )
        raise