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
) -> Optional[UnifiedEvaluationRecord]:
    """
    Executes the human-feedback-loop pipeline (Steps 1–4) for a feedback record.

    Uses AMC's AMCDatabaseAdapter and AMCEvidenceAdapter to read from
    response_feedback and query_evidence, and write the adjudicated
    result to unified_evaluation_records.
    """
    logger.info(
        "trigger_feedback_loop started: feedback_id=%s, response_id=%s, session_id=%s, source=%s",
        feedback_id,
        response_id,
        session_id,
        source,
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
                logger.info("trigger_feedback_loop: QueryEvidence not present for response_id=%s, skipping deep loop", response_id)
                return None
        finally:
            if db is None:
                check_db.close()

        success = start_feedback_loop(
            feedback_id=feedback_id,
            session_id=session_id,
            response_id=response_id,
            source=source,
            config=_config,
            db=_db_adapter,
            evidence_adapter=_evidence_adapter,
        )
        logger.info("start_feedback_loop returned %s for response_id=%s", success, response_id)

        # Retrieve the generated UnifiedEvaluationRecord
        local_db = db or SessionLocal()
        try:
            record = (
                local_db.query(UnifiedEvaluationRecord)
                .filter(UnifiedEvaluationRecord.response_id == response_id)
                .first()
            )
            return record
        finally:
            if db is None:
                local_db.close()

    except Exception as exc:
        logger.error(
            "trigger_feedback_loop failed for feedback_id=%s: %s",
            feedback_id,
            exc,
            exc_info=True,
        )
        raise