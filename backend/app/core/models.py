# app/core/models.py
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    cast,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ---------------------------------------------------------
# Enums — human-feedback-loop module (existing)
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


# NEW — Step 6 (RepairAnalysisService), per REVISED_SUMMARY.md Gap 1
class RepairTarget(str, enum.Enum):
    VECTOR = "vector"
    GRAPH = "graph"


# ---------------------------------------------------------
# Enums — AMC audit/compliance schema (new, from SQL file)
# ---------------------------------------------------------

class Region(str, enum.Enum):
    SEBI = "SEBI"
    SEC = "SEC"
    ESMA = "ESMA"


class AuditType(str, enum.Enum):
    FULL_CORPUS = "full_corpus"
    SINGLE_FUND = "single_fund"
    BATCH = "batch"
    CONTINUOUS = "continuous"


class AuditStatus(str, enum.Enum):
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ComplianceTrend(str, enum.Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


class ViolationCategory(str, enum.Enum):
    PORTFOLIO = "portfolio"
    GOVERNANCE = "governance"
    KYC = "kyc"
    RISK = "risk"
    REPORTING = "reporting"


class ViolationStatus(str, enum.Enum):
    DETECTED = "detected"
    REVIEWED = "reviewed"
    REMEDIATED = "remediated"
    CLOSED = "closed"
    WAIVED = "waived"


class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def _now_iso() -> str:
    """Matches SQL's TEXT columns with DEFAULT (datetime('now')) as an app-side default,
    since 'now()' functions aren't portable between SQLite and Postgres."""
    return datetime.now(timezone.utc).isoformat()


# # ---------------------------------------------------------
# # Feedback Records (human-feedback-loop input — unchanged)
# # ---------------------------------------------------------

# class FeedbackRecord(Base):
#     __tablename__ = "feedback_records"

#     id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     feedback_id: Mapped[str] = mapped_column(
#         String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4())
#     )
#     response_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
#     session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
#     user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
#     rating: Mapped[RatingType] = mapped_column(String(20), nullable=False)
#     feedback_type: Mapped[FeedbackType] = mapped_column(String(30), nullable=False)
#     entity_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
#     entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
#     notes: Mapped[str | None] = mapped_column(Text, nullable=True)
#     corrections: Mapped[dict | None] = mapped_column(JSON, nullable=True)
#     timestamp: Mapped[datetime] = mapped_column(
#         DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
#     )



# ===========================================================
# AMC Audit & Compliance Evidence schema (new — from SQL file)
# ===========================================================

# ---------------------------------------------------------
# TABLE 1: audit_metadata
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# TABLE 2: violations
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# TABLE 3: response_feedback
# UPDATED — added response_text, response_summary,
# feedback_text, feedback_span, classification_json,
# root_cause, unified_record_ref (MISSING_SCHEMA_DEFINITIONS.md,
# "Enhanced Table 2"). query_text already existed — not duplicated.
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# TABLE 4: query_evidence
# UPDATED — added entry_route, root_cause, severity,
# dissatisfaction_evidence_json, unified_record_ref
# (MISSING_SCHEMA_DEFINITIONS.md, "Enhanced Table 3").
# ---------------------------------------------------------

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
# ---------------------------------------------------------
# TABLE 5: compliance_rules
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# TABLE 6: fund_schemes
# ---------------------------------------------------------

class FundScheme(Base):
    __tablename__ = "fund_schemes"

    fund_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    isin: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fund_house: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    mandate: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_profile: Mapped[str | None] = mapped_column(String(40), nullable=True)

    aum_crores: Mapped[float | None] = mapped_column(Float, nullable=True)
    nav_per_unit: Mapped[float | None] = mapped_column(Float, nullable=True)

    region: Mapped[Region] = mapped_column(String(10), nullable=False, index=True)
    applicable_rules_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)

    __table_args__ = (
        UniqueConstraint("fund_id", "region", name="uq_fund_region"),
        CheckConstraint("region IN ('SEBI','SEC','ESMA')", name="ck_fund_region"),
    )


# ---------------------------------------------------------
# TABLE 7: sessions
# Named ChatSession in Python to avoid clashing with
# sqlalchemy.orm.Session; table name stays "sessions".
# ---------------------------------------------------------

class ChatSession(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    ended_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    audit_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("audit_metadata.audit_id"), nullable=True, index=True
    )


# ---------------------------------------------------------
# Unified Evaluation Records (human-feedback-loop output)
# UPDATED: added repair / repair_target — REVISED_SUMMARY.md Gap 1
# ---------------------------------------------------------

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