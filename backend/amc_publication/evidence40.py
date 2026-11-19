"""Wave 4.0 (TDS-40 E9/E7): audit-grade query evidence and pilot feedback, append-only, in PostgreSQL.

query_evidence_v40  one row per released verified answer, written by VerifiedOrchestratorFence29 AFTER its final
                    authority re-check and BEFORE the answer is released (AMC_QE_POSTGRES=on). If the row cannot
                    be written the answer is not released: an audit trail with silent gaps is not an audit trail.
                    It records what is needed to reproduce the answer: active FAISS generation and receipt, fin
                    dataset version and receipt, answer kind, abstention code, cited chunk ids, the structured
                    result hash, provider/model, and the PII-scrubbed question. Answer text is stored as a hash.
pilot_feedback_v40  one rating per user per request, bound to that user's own evidence row (AMC_PILOT_FEEDBACK=on).
                    Nothing reads it online: no detector, no repair, no patch. It is exported offline for triage.

Both tables are append-only by design: no update or delete path exists in code, and the migration revokes
UPDATE/DELETE from PUBLIC (grant INSERT/SELECT to the app role explicitly in deployment).
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .models import Base, utcnow

FLAG_QE = "AMC_QE_POSTGRES"
FLAG_FEEDBACK = "AMC_PILOT_FEEDBACK"
RATINGS = ("UP", "DOWN")
REASONS = ("WRONG_NUMBER", "WRONG_CITATION", "OUTDATED", "INCOMPLETE", "NOT_RELEVANT", "HELPFUL", "OTHER")
MAX_COMMENT = 1000


def _flag(name: str) -> bool:
    value = os.environ.get(name, "off").strip().lower()
    if value not in ("on", "off"):
        raise ValueError(f"{name} must be 'on' or 'off'")
    return os.environ.get("AMC_VERIFIED_SERVING_MODE", "off") == "enforce" and value == "on"


def evidence_enabled() -> bool:
    return _flag(FLAG_QE)


def feedback_enabled() -> bool:
    return _flag(FLAG_FEEDBACK)


class QueryEvidence40(Base):
    __tablename__ = "query_evidence_v40"
    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(128))
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    answer_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    abstention_code: Mapped[str | None] = mapped_column(String(64))
    serving_engine: Mapped[str | None] = mapped_column(String(64))
    faiss_generation_id: Mapped[str | None] = mapped_column(String(64))
    faiss_receipt_id: Mapped[str | None] = mapped_column(String(64))
    fin_dataset_version: Mapped[str | None] = mapped_column(String(64))
    fin_receipt_id: Mapped[str | None] = mapped_column(String(64))
    structured_result_hash: Mapped[str | None] = mapped_column(String(80))
    citations: Mapped[list] = mapped_column(JSON, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    question_scrubbed: Mapped[str] = mapped_column(Text(), nullable=False)
    answer_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    __table_args__ = (
        CheckConstraint("answer_kind IN ('STRUCTURED','DOCUMENT','MIXED','ABSTAIN','CLARIFY')",
                        name="ck_query_evidence_v40_kind"),
        CheckConstraint("channel IN ('answer','stream')", name="ck_query_evidence_v40_channel"),
        Index("idx_query_evidence_v40_tenant_time", "tenant", "created_at"),
    )


class PilotFeedback40(Base):
    __tablename__ = "pilot_feedback_v40"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), ForeignKey("query_evidence_v40.request_id"), nullable=False)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    comment_scrubbed: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    __table_args__ = (
        UniqueConstraint("request_id", "user_id", name="uq_pilot_feedback_v40_once"),
        CheckConstraint("rating IN ('UP','DOWN')", name="ck_pilot_feedback_v40_rating"),
        CheckConstraint("reason IN ('WRONG_NUMBER','WRONG_CITATION','OUTDATED','INCOMPLETE','NOT_RELEVANT',"
                        "'HELPFUL','OTHER')", name="ck_pilot_feedback_v40_reason"),
    )


EVIDENCE_TABLES = (QueryEvidence40.__table__, PilotFeedback40.__table__)


class FeedbackRefused(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _scrub(text: str | None) -> str | None:
    if text is None:
        return None
    from app.engine.pii_scrub import scrub_text
    return scrub_text(text)


def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def evidence_row(*, tenant: str, user_id: str | None, channel: str, generation_key: tuple, question: str,
                 synthesis, trace) -> QueryEvidence40:
    """Build the row from what was actually released. generation_key = fence pin (tenant, gen, digest, epoch,
    work, receipt)."""
    structured = _get(synthesis, "structured_result") or {}
    abstention = _get(synthesis, "abstention") or {}
    kind = _get(synthesis, "answer_kind") or "DOCUMENT"
    citations = []
    for c in _get(synthesis, "citations", []) or []:
        src = _get(c, "source") or c
        cid = _get(src, "chunk_id")
        if cid:
            citations.append(str(cid))
    for p in _get(synthesis, "provenance", []) or []:
        cid = _get(p, "chunk_id") or _get(p, "source_id")
        if cid and str(cid) not in citations:
            citations.append(str(cid))
    request_id = _get(trace, "request_id") or str(uuid.uuid4())
    latency = _get(trace, "request_total_ms")
    answer = _get(synthesis, "answer", "") or ""
    from app.config import get_settings
    settings = get_settings()
    return QueryEvidence40(
        request_id=str(request_id)[:64], tenant=tenant, user_id=user_id, channel=channel, answer_kind=kind,
        abstention_code=abstention.get("code") if isinstance(abstention, dict) else None,
        serving_engine=_get(trace, "serving_engine"),
        faiss_generation_id=generation_key[1] if generation_key else None,
        faiss_receipt_id=generation_key[5] if generation_key else None,
        fin_dataset_version=structured.get("dataset_version"), fin_receipt_id=structured.get("receipt_id"),
        structured_result_hash=structured.get("result_set_hash"), citations=citations[:50],
        provider=str(getattr(settings, "llm_provider", "") or "") or None,
        model=str(getattr(settings, "llm_model", "") or "") or None,
        question_scrubbed=_scrub(question or "")[:4000],
        answer_sha256=hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        latency_ms=int(latency) if isinstance(latency, (int, float)) else None)


def record(sessions, row: QueryEvidence40) -> None:
    with sessions.begin() as s:
        s.add(row)


def submit_feedback(session: Session, *, tenant: str, user_id: str, request_id: str, rating: str, reason: str,
                    comment: str | None) -> PilotFeedback40:
    if rating not in RATINGS:
        raise FeedbackRefused(422, f"rating must be one of {RATINGS}")
    if reason not in REASONS:
        raise FeedbackRefused(422, f"reason must be one of {REASONS}")
    if comment is not None and len(comment) > MAX_COMMENT:
        raise FeedbackRefused(422, f"comment is limited to {MAX_COMMENT} characters")
    ev = session.get(QueryEvidence40, request_id)
    # Same 404 for "missing", "another user's" and "another tenant's": never confirm another request exists.
    if ev is None or ev.tenant != tenant or ev.user_id != user_id:
        raise FeedbackRefused(404, "request not found")
    row = PilotFeedback40(id=uuid.uuid4().hex, request_id=request_id, tenant=tenant, user_id=user_id, rating=rating,
                          reason=reason, comment_scrubbed=_scrub(comment))
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as exc:
        raise FeedbackRefused(409, "feedback for this answer was already recorded") from exc
    return row


def export_feedback(session: Session, tenant: str) -> list[dict]:
    """Offline triage pack (operator CLI). Joins feedback with its evidence; never mutates anything."""
    rows = session.execute(select(PilotFeedback40, QueryEvidence40)
                           .join(QueryEvidence40, QueryEvidence40.request_id == PilotFeedback40.request_id)
                           .where(PilotFeedback40.tenant == tenant)
                           .order_by(PilotFeedback40.created_at)).all()
    return [{"request_id": f.request_id, "rating": f.rating, "reason": f.reason, "comment": f.comment_scrubbed,
             "created_at": f.created_at.isoformat(), "question": e.question_scrubbed, "answer_kind": e.answer_kind,
             "abstention_code": e.abstention_code, "citations": e.citations,
             "fin_dataset_version": e.fin_dataset_version, "faiss_generation_id": e.faiss_generation_id}
            for f, e in rows]


__all__ = ["QueryEvidence40", "PilotFeedback40", "EVIDENCE_TABLES", "evidence_enabled", "feedback_enabled",
           "evidence_row", "record", "submit_feedback", "export_feedback", "FeedbackRefused", "RATINGS", "REASONS"]
