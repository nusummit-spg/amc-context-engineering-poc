
# ---------------------------------------------------------
# TABLE 1: audit_metadata
# ---------------------------------------------------------
from sqlalchemy import Boolean, CheckConstraint, Float, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import  Mapped, mapped_column
import uuid
from app.core.database import Base
from app.schemas.models import (
    AuditType,
    Region,
    AuditStatus,
    ComplianceTrend,
    _now_iso,
)


class AuditMetadata(Base):
    __tablename__ = "audit_metadata"

    audit_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    audit_run_timestamp: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)

    region: Mapped[Region] = mapped_column(String(10), nullable=False, index=True)
    audit_type: Mapped[AuditType] = mapped_column(String(20), nullable=False)
    funds_audited_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    funds_passed_count: Mapped[int | None] = mapped_column(Integer, default=0)
    funds_with_violations_count: Mapped[int | None] = mapped_column(Integer, default=0)

    total_rules_evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_violations_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_violations: Mapped[int | None] = mapped_column(Integer, default=0)
    high_violations: Mapped[int | None] = mapped_column(Integer, default=0)
    medium_violations: Mapped[int | None] = mapped_column(Integer, default=0)
    low_violations: Mapped[int | None] = mapped_column(Integer, default=0)

    audit_duration_ms: Mapped[int | None] = mapped_column(Integer, default=0)
    avg_rule_evaluation_ms: Mapped[float | None] = mapped_column(Float, default=0.0)
    p95_rule_evaluation_ms: Mapped[float | None] = mapped_column(Float, default=0.0)
    p99_rule_evaluation_ms: Mapped[float | None] = mapped_column(Float, default=0.0)

    status: Mapped[AuditStatus] = mapped_column(
        String(20), nullable=False, default=AuditStatus.STARTED, index=True
    )
    triggered_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    triggering_action: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    overall_compliance_score: Mapped[float | None] = mapped_column(Float, default=0.0)
    compliance_trend: Mapped[ComplianceTrend | None] = mapped_column(
        String(20), default=ComplianceTrend.STABLE
    )

    report_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    escalation_triggered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    evidence_pack_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    evidence_manifest_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("audit_run_timestamp", "region", "audit_type", name="uq_audit_run"),
        CheckConstraint("region IN ('SEBI','SEC','ESMA')", name="ck_audit_region"),
        CheckConstraint(
            "audit_type IN ('full_corpus','single_fund','batch','continuous')",
            name="ck_audit_type",
        ),
        CheckConstraint(
            "status IN ('started','in_progress','completed','failed')", name="ck_audit_status"
        ),
        CheckConstraint(
            "compliance_trend IN ('improving','stable','declining')", name="ck_audit_trend"
        ),
        Index("idx_audit_timestamp", "audit_run_timestamp"),
        Index("idx_audit_region_timestamp", "region", "audit_run_timestamp"),
    )