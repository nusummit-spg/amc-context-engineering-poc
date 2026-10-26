"""
AMC Application Adapters for human-feedback-loop module.

Bridges the human-feedback-loop module interfaces (AbstractDatabaseAdapter,
AbstractEvidenceAdapter) directly to AMC's database models and session factory:
  - app.schemas.response_feedback_table.ResponseFeedback
  - app.schemas.query_evidence_table.QueryEvidence
  - app.schemas.unified_evaluation_records_table.UnifiedEvaluationRecord
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

import feedback_loop.domain_models as dm
from feedback_loop.adapters.db import AbstractDatabaseAdapter
from feedback_loop.adapters.evidence import AbstractEvidenceAdapter

from app.core.database import SessionLocal
from app.schemas.models import _now_iso
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord

logger = logging.getLogger("app.adapters.feedback")


def _parse_dt(value: str | None) -> datetime:
    """Parse ISO timestamp string or return current UTC datetime.

    Args:
        value (str | None): The value.

    Returns:
        datetime: Resulting datetime instance.
    """
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _extract_response_text(synthesis_output_json: Any) -> str:
    """Extract string response text from JSON or string synthesis output.

    Args:
        synthesis_output_json (Any): The synthesis output json.

    Returns:
        str: Resulting str instance.
    """
    if not synthesis_output_json:
        return ""
    if isinstance(synthesis_output_json, str):
        return synthesis_output_json
    if isinstance(synthesis_output_json, dict):
        return (
            synthesis_output_json.get("answer")
            or synthesis_output_json.get("response")
            or synthesis_output_json.get("response_text")
            or synthesis_output_json.get("text")
            or json.dumps(synthesis_output_json)
        )
    return str(synthesis_output_json)


def _extract_chunks(assembled_context_json: Any) -> List[dm.EvidenceChunk]:
    """Parse context chunks into domain EvidenceChunk objects.

    Args:
        assembled_context_json (Any): The assembled context json.

    Returns:
        List[dm.EvidenceChunk]: List of resulting items or records.
    """
    if not assembled_context_json:
        return []

    items = []
    if isinstance(assembled_context_json, list):
        items = assembled_context_json
    elif isinstance(assembled_context_json, dict):
        items = (
            assembled_context_json.get("chunks")
            or assembled_context_json.get("context_items")
            or assembled_context_json.get("sources")
            or [assembled_context_json]
        )

    chunks = []
    for idx, item in enumerate(items):
        if isinstance(item, dict):
            chunk_id = str(item.get("chunk_id") or item.get("id") or f"chk_{idx}")
            val = item.get("value") or item.get("val") or item.get("extracted_value")
            content = (
                item.get("content")
                or item.get("text")
                or item.get("snippet")
                or item.get("body")
                or (json.dumps(item) if not val else None)
            )
            version = str(item.get("source_version") or item.get("version") or "v1")
            chunks.append(
                dm.EvidenceChunk(
                    chunk_id=chunk_id,
                    value=str(val) if val is not None else None,
                    content=str(content) if content is not None else None,
                    source_version=version,
                )
            )
        elif isinstance(item, str):
            chunks.append(
                dm.EvidenceChunk(
                    chunk_id=f"chk_{idx}",
                    value=None,
                    content=item,
                    source_version="v1",
                )
            )
    return chunks


class AMCDatabaseAdapter(AbstractDatabaseAdapter):
    """Concrete DatabaseAdapter connecting human-feedback-loop to AMC's SQLite data.db."""

    def __init__(self, session_factory: sessionmaker = SessionLocal) -> None:
        """Initialize a new instance of AMCDatabaseAdapter.

        Args:
            session_factory (sessionmaker): The session factory.
        """
        self._session_factory = session_factory

    def fetch_feedback_record(self, feedback_id: str) -> dm.FeedbackRecord:
        """Fetch feedback record.

        Args:
            feedback_id (str): Unique identifier of the feedback.

        Returns:
            dm.FeedbackRecord: Resulting dm.FeedbackRecord instance.
        """
        with self._session_factory() as session:
            row = (
                session.query(ResponseFeedback)
                .filter(ResponseFeedback.feedback_id == feedback_id)
                .first()
            )
            if row is None:
                raise KeyError(f"feedback_record not found: {feedback_id!r}")

            # Derive source and rating
            source = dm.FeedbackSource.ACTIVE
            rating = dm.RatingType.NEGATIVE
            if not row.actor_id and not row.feedback_text:
                source = dm.FeedbackSource.PASSIVE
                rating = dm.RatingType.UNRATED
            elif row.answer_relevance_score and row.answer_relevance_score >= 4:
                rating = dm.RatingType.POSITIVE

            # Derive feedback type
            feedback_type = dm.FeedbackType.COMPLAINT
            if source == dm.FeedbackSource.PASSIVE:
                feedback_type = dm.FeedbackType.SILENT_ACCEPT
            else:
                correction_signals = {"F01", "F02", "F03", "F04"}
                has_corr_cat = bool(row.selected_categories and any(c in correction_signals for c in row.selected_categories))
                text_lower = (row.feedback_text or "").lower()
                has_corr_text = any(w in text_lower for w in ["should be", "is actually", "instead of", "not", "wrong", "incorrect", "correction"])

                if has_corr_cat or has_corr_text:
                    feedback_type = dm.FeedbackType.CORRECTION

            entity_name = None
            corrections = None
            if feedback_type == dm.FeedbackType.CORRECTION and row.feedback_text:
                try:
                    from app.feedback.correction_extractor import CorrectionExtractor
                    extractor = CorrectionExtractor()
                    claim = extractor.extract_claim(
                        feedback_text=row.feedback_text,
                        original_response=row.response_text or "",
                        original_query=row.query_text or "",
                    )
                    if claim:
                        entity_name = claim.entity_name
                        corrections = {
                            "entity_id": claim.entity_id,
                            "entity_name": claim.entity_name,
                            "attribute": claim.attribute,
                            "asserted_value": claim.asserted_value,
                            "rejected_value": claim.rejected_value,
                            "confidence": claim.confidence,
                        }
                    else:
                        corrections = {
                            "feedback_text": row.feedback_text,
                            "categories": row.selected_categories or [],
                        }
                except Exception as ex:
                    logger.warning("Failed to extract correction claim: %s", ex)
                    corrections = {"feedback_text": row.feedback_text}

            # If corrections not yet set, but active user provided categories or text
            if corrections is None and (row.selected_categories or row.feedback_text):
                corrections = {
                    "feedback_text": row.feedback_text,
                    "categories": row.selected_categories or [],
                }

            if not entity_name and row.query_text:
                try:
                    from app.feedback.correction_extractor import CorrectionExtractor
                    extractor = CorrectionExtractor()
                    entity_name = extractor._extract_entity(row.query_text)
                except Exception:
                    pass

            return dm.FeedbackRecord(
                feedback_id=row.feedback_id,
                response_id=row.response_id,
                session_id=row.session_id,
                user_id=row.actor_id,
                rating=rating,
                feedback_type=feedback_type,
                source=source,
                received_at=_parse_dt(row.created_at),
                notes=(row.feedback_text or "")[:2000] if row.feedback_text else None,
                entity_name=entity_name,
                corrections=corrections,
                ingestion_status=dm.IngestionStatus.PENDING,
            )

    def update_ingestion_status(self, feedback_id: str, status: dm.IngestionStatus) -> None:
        """Update ingestion status.

        Args:
            feedback_id (str): Unique identifier of the feedback.
            status (dm.IngestionStatus): Target status value.
        """
        with self._session_factory() as session:
            row = (
                session.query(ResponseFeedback)
                .filter(ResponseFeedback.feedback_id == feedback_id)
                .first()
            )
            if row:
                row.updated_at = _now_iso()
                session.commit()

    def fetch_pending_feedback_records(self, older_than_minutes: int = 5) -> list[dm.FeedbackRecord]:
        """Fetch pending feedback records.

        Args:
            older_than_minutes (int): Collection or list of older than minutes.

        Returns:
            list[dm.FeedbackRecord]: List of resulting items or records.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        with self._session_factory() as session:
            rows = (
                session.query(ResponseFeedback)
                .filter(ResponseFeedback.unified_record_ref.is_(None))
                .all()
            )
            results = []
            for r in rows:
                dt = _parse_dt(r.created_at)
                if dt <= cutoff:
                    try:
                        results.append(self.fetch_feedback_record(r.feedback_id))
                    except Exception as e:
                        logger.warning("Error loading pending feedback row %s: %s", r.feedback_id, e)
            return results

    def write_unified_record(self, record: dm.UnifiedEvaluationRecord) -> None:
        """Write unified record.

        Args:
            record (dm.UnifiedEvaluationRecord): The record.
        """
        # Determine repair target consistent with constraint:
        # ck_uer_repair_target_consistency: (repair = 0 AND target is NULL) OR (repair = 1 AND target IS NOT NULL)
        root_cause_str = record.root_cause.value if hasattr(record.root_cause, "value") else str(record.root_cause) if record.root_cause else "model"
        
        repair = getattr(record, "repair", False)
        repair_target = None
        if repair:
            target_val = getattr(record, "repair_target", None)
            if target_val:
                repair_target = target_val.value if hasattr(target_val, "value") else str(target_val)
            else:
                repair_target = "graph" if root_cause_str in {"knowledge", "retrieval", "graph"} else "vector"
        else:
            repair_target = None

        with self._session_factory() as session:
            # Check if record already exists for response_id
            existing = (
                session.query(UnifiedEvaluationRecord)
                .filter(UnifiedEvaluationRecord.response_id == record.response_id)
                .first()
            )
            if existing:
                logger.info("UnifiedEvaluationRecord already exists for response_id=%s, skipping insert", record.response_id)
                return

            entry_route_val = record.entry_route.value if hasattr(record.entry_route, "value") else str(record.entry_route)
            severity_val = record.severity.value if hasattr(record.severity, "value") else (str(record.severity) if record.severity else None)
            status_val = record.lifecycle_status.value if hasattr(record.lifecycle_status, "value") else str(record.lifecycle_status or "open")

            raw_verdict = record.adjudication_verdict.value if hasattr(record.adjudication_verdict, "value") else (str(record.adjudication_verdict) if record.adjudication_verdict else None)
            verdict_val = None
            if raw_verdict:
                norm_verdict = raw_verdict.lower().strip()
                valid_verdicts = {"valid", "partially_valid", "invalid", "subjective", "insufficient_evidence"}
                if norm_verdict in valid_verdicts:
                    verdict_val = norm_verdict
                elif "human" in norm_verdict or "review" in norm_verdict or "inconclusive" in norm_verdict:
                    verdict_val = "insufficient_evidence"
                elif "partial" in norm_verdict:
                    verdict_val = "partially_valid"
                elif "invalid" in norm_verdict:
                    verdict_val = "invalid"
                elif "valid" in norm_verdict:
                    verdict_val = "valid"

            uer = UnifiedEvaluationRecord(
                session_id=record.session_id,
                response_id=record.response_id,
                entry_route=entry_route_val,
                feedback_ref=record.feedback_ref,
                evidence_snapshot_ref=record.evidence_snapshot_ref or record.response_id,
                root_cause=root_cause_str,
                severity=severity_val,
                lifecycle_status=status_val,
                dissatisfaction_evidence_json=record.dissatisfaction_evidence,
                repair=repair,
                repair_target=repair_target,
                deterministic_results=record.deterministic_results,
                gnn_plausibility_score=record.gnn_plausibility_score,
                semantic_results=record.semantic_results,
                llm_evaluation=record.llm_evaluation,
                adjudication_verdict=verdict_val,
                adjudication_confidence=record.adjudication_confidence,
                created_at=_now_iso(),
                updated_at=_now_iso(),
                created_by="feedback_loop_module",
            )
            session.add(uer)
            session.flush()

            # Back-populate reverse foreign key on response_feedback if present
            if record.feedback_ref:
                fb = session.query(ResponseFeedback).filter(ResponseFeedback.feedback_id == record.feedback_ref).first()
                if fb:
                    fb.unified_record_ref = record.response_id
                    fb.root_cause = root_cause_str

            # Update query_evidence reverse reference and flag
            qe = session.query(QueryEvidence).filter(QueryEvidence.response_id == record.response_id).first()
            if qe:
                qe.unified_record_ref = record.response_id
                qe.has_feedback = True
                qe.root_cause = root_cause_str
                if severity_val:
                    qe.severity = severity_val
                qe.entry_route = entry_route_val

            session.commit()
            logger.info("Successfully persisted UnifiedEvaluationRecord for response_id=%s", record.response_id)

    def find_open_cluster(self, response_id: str, entity_name: Optional[str]) -> Optional[dm.UnifiedEvaluationRecord]:
        """Find open cluster.

        Args:
            response_id (str): Unique identifier of the response.
            entity_name (Optional[str]): Name of the entity.

        Returns:
            Optional[dm.UnifiedEvaluationRecord]: Matching object or record if found, None otherwise.
        """
        with self._session_factory() as session:
            row = (
                session.query(UnifiedEvaluationRecord)
                .filter(
                    UnifiedEvaluationRecord.response_id == response_id,
                    UnifiedEvaluationRecord.lifecycle_status == "open",
                )
                .first()
            )
            if not row:
                return None

            return dm.UnifiedEvaluationRecord(
                session_id=row.session_id,
                response_id=row.response_id,
                entry_route=row.entry_route,
                feedback_ref=row.feedback_ref,
                evidence_snapshot_ref=row.evidence_snapshot_ref,
                root_cause=row.root_cause,
                severity=row.severity,
                lifecycle_status=row.lifecycle_status,
                dissatisfaction_evidence=row.dissatisfaction_evidence_json,
                deterministic_results=row.deterministic_results,
                gnn_plausibility_score=row.gnn_plausibility_score,
                semantic_results=row.semantic_results,
                llm_evaluation=row.llm_evaluation,
                adjudication_verdict=row.adjudication_verdict,
                adjudication_confidence=row.adjudication_confidence,
            )

    def unified_record_exists(self, response_id: str) -> bool:
        """Unified record exists.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        with self._session_factory() as session:
            count = (
                session.query(UnifiedEvaluationRecord)
                .filter(UnifiedEvaluationRecord.response_id == response_id)
                .count()
            )
            return count > 0


class AMCEvidenceAdapter(AbstractEvidenceAdapter):
    """Concrete EvidenceAdapter reading frozen D0-D3 context from QueryEvidence with user scoping."""

    def __init__(self, session_factory: sessionmaker = SessionLocal) -> None:
        """Initialize a new instance of AMCEvidenceAdapter.

        Args:
            session_factory (sessionmaker): The session factory.
        """
        self._session_factory = session_factory

    def get_evidence_snapshot(
        self,
        response_id: str,
        requesting_user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> dm.EvidenceSnapshot:
        """Retrieve evidence snapshot.

        Args:
            response_id (str): Unique identifier of the response.
            requesting_user_id (Optional[str]): Unique identifier of the requesting user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            dm.EvidenceSnapshot: Resulting dm.EvidenceSnapshot instance.
        """
        with self._session_factory() as session:
            row = (
                session.query(QueryEvidence)
                .filter(QueryEvidence.response_id == response_id)
                .first()
            )
            if row is None:
                raise KeyError(f"No query_evidence row found for response_id={response_id}")

            # SECURITY: Verify ownership if requesting_user_id is provided
            if requesting_user_id and row.user_id != requesting_user_id:
                logger.warning(
                    "User %s attempted to access evidence owned by %s (response_id=%s)",
                    requesting_user_id, row.user_id, response_id
                )
                raise KeyError(f"No query_evidence row found for response_id={response_id}")

            # SECURITY: Verify tenant boundary if tenant_id is provided
            if tenant_id and row.tenant_id != tenant_id:
                logger.warning(
                    "Tenant %s attempted to access evidence in tenant %s (response_id=%s)",
                    tenant_id, row.tenant_id, response_id
                )
                raise KeyError(f"No query_evidence row found for response_id={response_id}")

            return dm.EvidenceSnapshot(
                response_id=row.response_id,
                original_query=row.query_text,
                response_text=_extract_response_text(row.synthesis_output_json),
                entity_name=None,
                evidence_selected=_extract_chunks(row.assembled_context_json),
            )

    def get_followup_activity(
        self,
        session_id: str,
        response_id: str,
        window_minutes: int = 30,
        requesting_user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> list[dm.FollowUpQuery]:
        """Retrieve followup activity.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            window_minutes (int): Collection or list of window minutes.
            requesting_user_id (Optional[str]): Unique identifier of the requesting user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            list[dm.FollowUpQuery]: List of resulting items or records.
        """
        with self._session_factory() as session:
            anchor_query = session.query(QueryEvidence).filter(QueryEvidence.response_id == response_id)
            if requesting_user_id:
                anchor_query = anchor_query.filter(QueryEvidence.user_id == requesting_user_id)
            if tenant_id:
                anchor_query = anchor_query.filter(QueryEvidence.tenant_id == tenant_id)
            anchor = anchor_query.first()
            if not anchor:
                return []

            anchor_dt = _parse_dt(anchor.created_at)
            cutoff_dt = anchor_dt + timedelta(minutes=window_minutes)

            sub_query = session.query(QueryEvidence).filter(
                QueryEvidence.session_id == session_id,
                QueryEvidence.response_id != response_id,
            )
            if requesting_user_id:
                sub_query = sub_query.filter(QueryEvidence.user_id == requesting_user_id)
            if tenant_id:
                sub_query = sub_query.filter(QueryEvidence.tenant_id == tenant_id)

            subsequent = sub_query.all()

            followups = []
            for qe in subsequent:
                dt = _parse_dt(qe.created_at)
                if anchor_dt < dt <= cutoff_dt:
                    followups.append(
                        dm.FollowUpQuery(
                            query_id=qe.response_id,
                            text=qe.query_text,
                            created_at=dt,
                        )
                    )
            return followups

    def validate_response_exists(
        self,
        response_id: str,
        requesting_user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Validate response exists.

        Args:
            response_id (str): Unique identifier of the response.
            requesting_user_id (Optional[str]): Unique identifier of the requesting user.
            tenant_id (Optional[str]): Unique identifier of the tenant.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        with self._session_factory() as session:
            query = session.query(QueryEvidence).filter(QueryEvidence.response_id == response_id)
            if requesting_user_id:
                query = query.filter(QueryEvidence.user_id == requesting_user_id)
            if tenant_id:
                query = query.filter(QueryEvidence.tenant_id == tenant_id)
            return query.count() > 0
