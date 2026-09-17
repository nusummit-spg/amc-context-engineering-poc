# ---------------------------------------------------------
# TABLE 4: query_evidence
# UPDATED — added entry_route, root_cause, severity,
# dissatisfaction_evidence_json, unified_record_ref
# (MISSING_SCHEMA_DEFINITIONS.md, "Enhanced Table 3").
# ---------------------------------------------------------
from app.core.database import Base
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Boolean,
    func,
    cast,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.schemas.models import (
    ConfidenceLevel,
    _now_iso,
)

class QueryEvidence(Base):
    __tablename__ = "query_evidence"

    response_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    query_intent: Mapped[str | None] = mapped_column(String(120), nullable=True)

    retrieval_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="contextgraph")
    serving_engine: Mapped[str | None] = mapped_column(String(60), nullable=True)

    assembled_context_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    synthesis_output_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    graph_highlight_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    traditional_result_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synthesis_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_level: Mapped[ConfidenceLevel | None] = mapped_column(
        String(10), nullable=True, index=True
    )

    audit_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("audit_metadata.audit_id"), nullable=True, index=True
    )
    linked_violations_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    has_feedback: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    feedback_summary_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- NEW: feedback-loop routing/classification (MD "Enhanced Table 3") ---
    entry_route: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    root_cause: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dissatisfaction_evidence_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    # --- NEW: link back to unified_evaluation_records ---
    # Same session_id -> response_id correction as response_feedback above.
    unified_record_ref: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("unified_evaluation_records.response_id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "confidence_level IN ('high','medium','low') OR confidence_level IS NULL",
            name="ck_query_confidence_level",
        ),
        Index("idx_query_evidence_entry_route", "entry_route"),
        Index("idx_query_evidence_root_cause", "root_cause"),
        Index("idx_query_evidence_unified_ref", "unified_record_ref"),
        Index(
            "idx_query_evidence_dissatisfaction",
            func.length(cast(dissatisfaction_evidence_json, Text)) > 0,
        ),
    )