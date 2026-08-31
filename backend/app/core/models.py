import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ---------------------------------------------------------
# Enums
# ---------------------------------------------------------

class RatingType(str, enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class FeedbackType(str, enum.Enum):
    COMPLAINT = "complaint"
    CORRECTION = "correction"


class EntryRoute(str, enum.Enum):
    HITL = "hitl"
    AUTOMATIC = "automatic"
    DISSATISFACTION_CONVERTED = "dissatisfaction_converted"


class AdjudicationVerdict(str, enum.Enum):
    VALID = "valid"
    PARTIALLY_VALID = "partially_valid"
    INVALID = "invalid"
    SUBJECTIVE = "subjective"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class RootCause(str, enum.Enum):
    KNOWLEDGE = "knowledge"
    RETRIEVAL = "retrieval"
    GRAPH = "graph"
    CONTEXT_ENGINEERING = "context_engineering"
    MODEL = "model"
    GUARDRAIL = "guardrail"
    COMPLIANCE = "compliance"
    PRESENTATION = "presentation"
    FEEDBACK_INVALID = "feedback_invalid"


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LifecycleStatus(str, enum.Enum):
    OPEN = "open"
    DIAGNOSING = "diagnosing"
    RESOLVED = "resolved"
    MONITORING = "monitoring"


# ---------------------------------------------------------
# Feedback Records
# ---------------------------------------------------------

class FeedbackRecord(Base):
    __tablename__ = "feedback_records"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    feedback_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )

    response_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    session_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    user_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    rating: Mapped[RatingType] = mapped_column(
        String(20),
        nullable=False,
    )

    feedback_type: Mapped[FeedbackType] = mapped_column(
        String(30),
        nullable=False,
    )

    entity_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    entity_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    corrections: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------
# Unified Evaluation Records
# ---------------------------------------------------------

class UnifiedEvaluationRecord(Base):
    __tablename__ = "unified_evaluation_records"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    session_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    response_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    entry_route: Mapped[EntryRoute] = mapped_column(
        String(40),
        nullable=False,
    )

    feedback_ref: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("feedback_records.feedback_id"),
        nullable=True,
        index=True,
    )

    evidence_snapshot_ref: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    deterministic_results: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    gnn_plausibility_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    semantic_results: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    llm_evaluation: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    adjudication_verdict: Mapped[AdjudicationVerdict] = mapped_column(
        String(30),
        nullable=False,
    )

    adjudication_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    root_cause: Mapped[RootCause | None] = mapped_column(
        String(30),
        nullable=True,
    )

    severity: Mapped[Severity | None] = mapped_column(
        String(20),
        nullable=True,
    )

    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        String(20),
        nullable=False,
        default=LifecycleStatus.OPEN,
    )
