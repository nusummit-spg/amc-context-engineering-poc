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
    """Parse ISO timestamp string or return current UTC datetime."""
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _extract_response_text(synthesis_output_json: Any) -> str:
    """Extract string response text from JSON or string synthesis output."""
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
    """Parse context chunks into domain EvidenceChunk objects."""
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
        self._session_factory = session_factory

    def fetch_feedback_record(self, feedback_id: str) -> dm.FeedbackRecord:
        with self._session_factory() as session:
            row = (
                session.query(ResponseFeedback)
                .filter(ResponseFeedback.feedback_id == feedback_id)
                .first()
            )
            if row is None:
                raise KeyError(f"feedback_record not found: {feedback_id!r}")

            # Derive rating
            rating = dm.RatingType.NEGATIVE
            if row.answer_relevance_score and row.answer_relevance_score >= 4:
                rating = dm.RatingType.POSITIVE

            # Derive feedback type
            feedback_type = dm.FeedbackType.COMPLAINT
            correction_signals = {"F01", "F02", "F03", "F04"}
            has_corr_cat = bool(row.selected_categories and any(c in correction_signals for c in row.selected_categories))
            text_lower = (row.feedback_text or "").lower()
            has_corr_text = any(w in text_lower for w in ["should be", "is actually", "instead of", "not", "wrong", "incorrect", "correction"])

            if has_corr_cat or has_corr_text:
                feedback_type = dm.FeedbackType.CORRECTION

            return dm.FeedbackRecord(
                feedback_id=row.feedback_id,
                response_id=row.response_id,
                session_id=row.session_id,
                user_id=row.actor_id,
                rating=rating,
                feedback_type=feedback_type,
                source=dm.FeedbackSource.ACTIVE,
                received_at=_parse_dt(row.created_at),
                notes=(row.feedback_text or "")[:2000] if row.feedback_text else None,
                entity_name=None,
                ingestion_status=dm.IngestionStatus.PENDING,
            )

    def update_ingestion_status(self, feedback_id: str, status: dm.IngestionStatus) -> None:
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
        # Determine repair target consistent with constraint:
        # ck_uer_repair_target_consistency: (repair = 0 AND target is NULL) OR (repair = 1 AND target IS NOT NULL)
        root_cause_str = record.root_cause.value if hasattr(record.root_cause, "value") else str(record.root_cause) if record.root_cause else "model"
        
        repair = False
        repair_target = None
        if root_cause_str in {"knowledge", "retrieval", "graph"}:
            repair = True
            repair_target = "graph"
        elif root_cause_str == "model":
            repair = True
            repair_target = "vector"

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
                adjudication_verdict=record.adjudication_verdict.value if hasattr(record.adjudication_verdict, "value") else (str(record.adjudication_verdict) if record.adjudication_verdict else None),
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
        with self._session_factory() as session:
            count = (
                session.query(UnifiedEvaluationRecord)
                .filter(UnifiedEvaluationRecord.response_id == response_id)
                .count()
            )
            return count > 0


class AMCEvidenceAdapter(AbstractEvidenceAdapter):
    """Concrete EvidenceAdapter reading frozen D0-D3 context from QueryEvidence."""

    def __init__(self, session_factory: sessionmaker = SessionLocal) -> None:
        self._session_factory = session_factory

    def get_evidence_snapshot(self, response_id: str) -> dm.EvidenceSnapshot:
        with self._session_factory() as session:
            row = (
                session.query(QueryEvidence)
                .filter(QueryEvidence.response_id == response_id)
                .first()
            )
            if row is None:
                raise KeyError(f"No query_evidence row found for response_id={response_id}")

            return dm.EvidenceSnapshot(
                response_id=row.response_id,
                original_query=row.query_text,
                response_text=_extract_response_text(row.synthesis_output_json),
                entity_name=None,
                evidence_selected=_extract_chunks(row.assembled_context_json),
            )

    def get_followup_activity(
        self, session_id: str, response_id: str, window_minutes: int = 30
    ) -> list[dm.FollowUpQuery]:
        with self._session_factory() as session:
            anchor = (
                session.query(QueryEvidence)
                .filter(QueryEvidence.response_id == response_id)
                .first()
            )
            if not anchor:
                return []

            anchor_dt = _parse_dt(anchor.created_at)
            cutoff_dt = anchor_dt + timedelta(minutes=window_minutes)

            subsequent = (
                session.query(QueryEvidence)
                .filter(
                    QueryEvidence.session_id == session_id,
                    QueryEvidence.response_id != response_id,
                )
                .all()
            )

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

    def validate_response_exists(self, response_id: str) -> bool:
        with self._session_factory() as session:
            count = (
                session.query(QueryEvidence)
                .filter(QueryEvidence.response_id == response_id)
                .count()
            )
            return count > 0
