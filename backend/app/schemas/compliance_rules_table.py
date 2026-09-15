# ---------------------------------------------------------
# TABLE 5: compliance_rules
# ---------------------------------------------------------
from app.core.database import Base
from sqlalchemy import (
    CheckConstraint,
    Float,
    Integer,
    JSON,
    String,
    Text,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone

from app.schemas.models import (
    ViolationCategory,
    Region,
    Severity,
    _now_iso,
)

class ComplianceRule(Base):
    __tablename__ = "compliance_rules"

    rule_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    regulation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    rule_type: Mapped[ViolationCategory] = mapped_column(String(20), nullable=False, index=True)
    region: Mapped[Region] = mapped_column(String(10), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    condition_plain_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition_code_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    applicable_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    exclusions_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    severity: Mapped[Severity] = mapped_column(String(20), nullable=False, index=True)
    enforcement_level: Mapped[str | None] = mapped_column(String(20), default="automatic")
    confidence_threshold: Mapped[float | None] = mapped_column(Float, default=0.95)

    required_evidence_types: Mapped[list | None] = mapped_column(JSON, nullable=True)

    effective_from: Mapped[str | None] = mapped_column(String(40), nullable=True)
    effective_to: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)

    regulation_section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    last_modified_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    __table_args__ = (
        UniqueConstraint("rule_id", "region", "version_number", name="uq_rule_region_version"),
        CheckConstraint(
            "rule_type IN ('portfolio','governance','kyc','risk','reporting')", name="ck_rule_type"
        ),
        CheckConstraint("region IN ('SEBI','SEC','ESMA')", name="ck_rule_region"),
        CheckConstraint("severity IN ('critical','high','medium','low')", name="ck_rule_severity"),
        CheckConstraint(
            "confidence_threshold >= 0.0 AND confidence_threshold <= 1.0",
            name="ck_rule_confidence_threshold",
        ),
    )
