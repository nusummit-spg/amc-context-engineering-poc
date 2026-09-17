# ---------------------------------------------------------
# TABLE 2: violations
# ---------------------------------------------------------

from __future__ import annotations
import uuid
from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.schemas.models import (
    Region,
    ViolationCategory,
    Severity,
    ViolationStatus,
    _now_iso,
)

class Violation(Base):
    __tablename__ = "violations"

    violation_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    audit_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("audit_metadata.audit_id"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    fund_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    severity: Mapped[Severity] = mapped_column(String(20), nullable=False, index=True)
    violation_type: Mapped[ViolationCategory] = mapped_column(String(20), nullable=False)
    region: Mapped[Region] = mapped_column(String(10), nullable=False, index=True)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    actual_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    threshold_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gap_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)

    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_count: Mapped[int | None] = mapped_column(Integer, default=0)

    status: Mapped[ViolationStatus] = mapped_column(
        String(20), nullable=False, default=ViolationStatus.DETECTED, index=True
    )

    detected_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reviewed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    resolution_action: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_docs_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    audit_trail_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    escalation_level: Mapped[int | None] = mapped_column(Integer, default=0, index=True)
    escalation_triggered_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    escalation_path_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    __table_args__ = (
        UniqueConstraint("audit_id", "rule_id", "fund_id", name="uq_violation_audit_rule_fund"),
        CheckConstraint("severity IN ('critical','high','medium','low')", name="ck_violation_severity"),
        CheckConstraint(
            "violation_type IN ('portfolio','governance','kyc','risk','reporting')",
            name="ck_violation_type",
        ),
        CheckConstraint("region IN ('SEBI','SEC','ESMA')", name="ck_violation_region"),
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0", name="ck_violation_confidence"
        ),
        CheckConstraint(
            "status IN ('detected','reviewed','remediated','closed','waived')",
            name="ck_violation_status",
        ),
        Index("idx_violation_region_severity", "region", "severity"),
        Index("idx_violation_fund_status", "fund_id", "status"),
    )