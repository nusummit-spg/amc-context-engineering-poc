# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
metrics_enrichment.py
=====================
Enriches skeleton ResponseFeedback records with automated metrics, telemetry from
QueryEvidence, and implicit satisfaction signals (e.g. dwell time).
"""

import logging
from app.core.logging import log_step_info, log_step_error
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.query_evidence_table import QueryEvidence

logger = logging.getLogger("app.feedback.metrics_enrichment")


class MetricsEnricher:
    """
    Enriches skeleton ResponseFeedback records with telemetry and implicit signals.
    """

    def _categorize_quality(
        self,
        quality_score: Optional[float],
        compliance_severity: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[float]]:
        """Maps telemetry quality_score and compliance severity to automated_category
        and automated_confidence.

        Args:
            quality_score (Optional[float]): The quality score.
            compliance_severity (Optional[str]): The compliance severity.

        Returns:
            Tuple[Optional[str], Optional[float]]: Matching object or record if found, None otherwise.
        """
        if compliance_severity and str(compliance_severity).upper() in ("HIGH", "CRITICAL"):
            return "auto_compliance_issue", 0.90

        if quality_score is not None:
            confidence = round(min(max(float(quality_score) / 10.0, 0.0), 1.0), 2)
            if quality_score >= 8.0:
                return "auto_high_quality", confidence
            elif quality_score >= 5.0:
                return "auto_medium_quality", confidence
            else:
                return "auto_low_quality", confidence

        return None, None

    async def enrich_response(
        self,
        session_id: str,
        response_id: str,
        db: Optional[Session] = None,
    ) -> bool:
        """Enriches a skeleton ResponseFeedback record.
        Idempotent: skips if already human-reviewed or enriched.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            db (Optional[Session]): Database session instance.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            # 1. Fetch ResponseFeedback (skeleton)
            feedback = (
                db.query(ResponseFeedback)
                .filter(
                    ResponseFeedback.response_id == response_id,
                    ResponseFeedback.session_id == session_id,
                )
                .first()
            )

            if not feedback:
                # Try fallback matching by response_id only
                feedback = (
                    db.query(ResponseFeedback)
                    .filter(ResponseFeedback.response_id == response_id)
                    .first()
                )

            if not feedback:
                logger.debug(
                    "No ResponseFeedback record found for session=%s, response=%s",
                    session_id,
                    response_id,
                )
                return False

            # 2. Check if already reviewed by human or already enriched
            if feedback.actor_id or feedback.automated_category:
                logger.debug(
                    "ResponseFeedback %s already enriched/reviewed (actor=%s, cat=%s)",
                    feedback.feedback_id,
                    feedback.actor_id,
                    feedback.automated_category,
                )
                return True

            # 3. Fetch QueryEvidence (telemetry)
            evidence = (
                db.query(QueryEvidence)
                .filter(QueryEvidence.response_id == response_id)
                .first()
            )

            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()

            # 4. Extract telemetry and response text from QueryEvidence if available
            if evidence:
                # Extract text
                resp_text = None
                if isinstance(evidence.synthesis_output_json, dict):
                    resp_text = evidence.synthesis_output_json.get("answer") or evidence.synthesis_output_json.get("response_text")
                elif isinstance(evidence.synthesis_output_json, str):
                    resp_text = evidence.synthesis_output_json

                if resp_text and not feedback.response_text:
                    feedback.response_text = str(resp_text)

                # Quality mapping
                cat, conf = self._categorize_quality(
                    evidence.quality_score,
                    getattr(evidence, "severity", None),
                )
                if cat:
                    feedback.automated_category = cat
                    feedback.automated_confidence = conf

                # Copy reverse reference if already set on evidence
                if getattr(evidence, "unified_record_ref", None) and not feedback.unified_record_ref:
                    feedback.unified_record_ref = evidence.unified_record_ref

                if getattr(evidence, "root_cause", None) and not feedback.root_cause:
                    feedback.root_cause = evidence.root_cause

            # 5. Dwell time & implicit signals
            try:
                created_str = feedback.created_at
                created_dt = datetime.fromisoformat(created_str)
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                dwell_seconds = (now - created_dt).total_seconds()
            except Exception:
                dwell_seconds = 0.0

            # If no automated category assigned yet, assign category based on dwell time or mark as evaluated
            # Only if no explicit human feedback or category was provided
            selected_cats = feedback.selected_categories
            has_explicit_cats = False
            if isinstance(selected_cats, list):
                has_explicit_cats = len(selected_cats) > 0
            elif isinstance(selected_cats, str):
                has_explicit_cats = selected_cats.strip() not in ("[]", "")

            has_explicit = bool(
                (feedback.feedback_text and str(feedback.feedback_text).strip())
                or has_explicit_cats
            )
            if not feedback.automated_category and not has_explicit:
                if dwell_seconds >= 180.0:
    
                    feedback.automated_category = "implicit_positive"
                    feedback.automated_confidence = 0.70
    
                else:
                    feedback.automated_category = "auto_evaluated"
                    feedback.automated_confidence = 1.0
            elif not feedback.automated_category:
                feedback.automated_category = "auto_evaluated"
                feedback.automated_confidence = 1.0



            feedback.updated_at = now_iso
            db.commit()

            try:
                from app.core.metrics import (
                    passive_feedback_enrichments_completed,
                    passive_feedback_enrichment_latency,
                )
                passive_feedback_enrichments_completed.inc()
                passive_feedback_enrichment_latency.observe(dwell_seconds)
            except Exception:
                pass

            log_step_info(
                logger,
                "METRICS_ENRICHED",
                "Step 1: Enriched telemetry metrics for response %s: category=%s (confidence=%.2f)",
                feedback.response_id,
                feedback.automated_category,
                feedback.automated_confidence or 0.0,
            )
            return True

        except Exception as exc:
            db.rollback()
            logger.error("Failed to enrich response %s: %s", response_id, exc, exc_info=True)
            return False
        finally:
            if close_db:
                db.close()


# Global singleton
_metrics_enricher: Optional[MetricsEnricher] = None


def get_metrics_enricher() -> MetricsEnricher:
    """Retrieve or create the global MetricsEnricher singleton.

    Returns:
        MetricsEnricher: Resulting MetricsEnricher instance.
    """
    global _metrics_enricher
    if _metrics_enricher is None:
        _metrics_enricher = MetricsEnricher()
    return _metrics_enricher
