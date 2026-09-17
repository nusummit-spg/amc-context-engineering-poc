# ---------------------------------------------------------
# Unified Evaluation Records (human-feedback-loop output)
# UPDATED: added repair / repair_target — REVISED_SUMMARY.md Gap 1
# ---------------------------------------------------------
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    JSON,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.schemas.models import (
    EntryRoute, 
    RootCause,
    Severity,
    LifecycleStatus,
    RepairTarget,
    AdjudicationVerdict,
    _now_iso,
)


class UnifiedEvaluationRecord(Base):
    __tablename__ = "unified_evaluation_records"

    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    response_id: Mapped[str] = mapped_column(String(36), nullable=False)

    entry_route: Mapped[EntryRoute] = mapped_column(String(40), nullable=False)

    feedback_ref: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("response_feedback.feedback_id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )
    evidence_snapshot_ref: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("query_evidence.response_id", ondelete="RESTRICT"),
        nullable=False,
    )

    root_cause: Mapped[RootCause] = mapped_column(String(30), nullable=False)
    severity: Mapped[Severity | None] = mapped_column(String(20), nullable=True)

    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        String(20), nullable=False, default=LifecycleStatus.OPEN
    )

    dissatisfaction_evidence_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    repair: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    repair_target: Mapped[RepairTarget | None] = mapped_column(String(10), nullable=True)

    deterministic_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gnn_plausibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    semantic_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    adjudication_verdict: Mapped[AdjudicationVerdict | None] = mapped_column(String(30), nullable=True)
    adjudication_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    created_by: Mapped[str | None] = mapped_column(
        String(60), nullable=True, default="feedback_loop_module"
    )

    __table_args__ = (
        UniqueConstraint("response_id", name="uq_unified_response_id"),
        CheckConstraint(
            "entry_route IN ('hitl','automatic','dissatisfaction_converted')",
            name="ck_unified_entry_route",
        ),
        CheckConstraint(
            "root_cause IN ('knowledge','retrieval','graph','context_engineering','model',"
            "'guardrail','compliance','presentation','feedback_invalid')",
            name="ck_unified_root_cause",
        ),
        CheckConstraint(
            "severity IN ('critical','high','medium','low') OR severity IS NULL",
            name="ck_unified_severity",
        ),
        CheckConstraint(
            "lifecycle_status IN ('open','diagnosing','resolved','monitoring')",
            name="ck_unified_lifecycle_status",
        ),
        CheckConstraint(
            "repair_target IN ('vector','graph') OR repair_target IS NULL",
            name="ck_unified_repair_target",
        ),
        CheckConstraint(
            "adjudication_verdict IN ('valid','partially_valid','invalid','subjective',"
            "'insufficient_evidence') OR adjudication_verdict IS NULL",
            name="ck_unified_adjudication_verdict",
        ),
        CheckConstraint(
            "(repair = 0 AND repair_target IS NULL) OR (repair = 1 AND repair_target IS NOT NULL)",
            name="ck_uer_repair_target_consistency",
        ),
        PrimaryKeyConstraint("session_id", "response_id", name="pk_unified_session_response"),
        Index("idx_unified_entry_route", "entry_route"),
        Index("idx_unified_root_cause", "root_cause"),
        Index("idx_unified_severity", "severity"),
        Index("idx_unified_evidence_ref", "evidence_snapshot_ref"),
        Index("idx_unified_created_at", "created_at"),
        Index("idx_unified_lifecycle", "lifecycle_status"),
        Index("idx_unified_repair_status", "repair", "lifecycle_status"),
        Index(
            "idx_unified_repair_filtered",
            "repair",
            sqlite_where=text("repair = 1"),
            postgresql_where=text("repair = true"),
        ),
    )