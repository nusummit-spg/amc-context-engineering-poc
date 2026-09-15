# ---------------------------------------------------------
# TABLE 3: response_feedback
# UPDATED — added response_text, response_summary,
# feedback_text, feedback_span, classification_json,
# root_cause, unified_record_ref (MISSING_SCHEMA_DEFINITIONS.md,
# "Enhanced Table 2"). query_text already existed — not duplicated.
# ---------------------------------------------------------

import uuid
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.models import _now_iso


class ResponseFeedback(Base):
    __tablename__ = "response_feedback"

    feedback_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    response_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    interaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)

    selected_categories: Mapped[list] = mapped_column(JSON, nullable=False)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    answer_relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completeness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    automated_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    automated_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    client_timestamp: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)

    audit_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("audit_metadata.audit_id"), nullable=True, index=True
    )
    violation_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("violations.violation_id"), nullable=True
    )

    # --- NEW: response context (MD "Enhanced Table 2") ---
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- NEW: user feedback detail ---
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_span: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- NEW: Step 1 classification output ---
    classification_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    # --- NEW: copied from unified_evaluation_records.root_cause ---
    root_cause: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)

    # --- NEW: link back to unified_evaluation_records ---
    # NOTE: MD's own SQL FKs this to unified_evaluation_records(session_id),
    # but session_id is not unique once (session_id, response_id) is the
    # composite PK there. Pointed at response_id instead — see chat note.
    unified_record_ref: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("unified_evaluation_records.response_id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("response_id", "actor_id", name="uq_feedback_response_actor"),
        CheckConstraint(
            "answer_relevance_score IS NULL OR (answer_relevance_score BETWEEN 1 AND 5)",
            name="ck_feedback_relevance_score",
        ),
        CheckConstraint(
            "source_quality_score IS NULL OR (source_quality_score BETWEEN 1 AND 5)",
            name="ck_feedback_source_score",
        ),
        CheckConstraint(
            "completeness_score IS NULL OR (completeness_score BETWEEN 1 AND 5)",
            name="ck_feedback_completeness_score",
        ),
        CheckConstraint(
            "automated_confidence IS NULL OR (automated_confidence BETWEEN 0.0 AND 1.0)",
            name="ck_feedback_automated_confidence",
        ),
        Index("idx_response_feedback_unified_ref", "unified_record_ref"),
        Index("idx_response_feedback_root_cause", "root_cause"),
        Index("idx_response_feedback_response_text_len", func.length(response_text)),
    )
