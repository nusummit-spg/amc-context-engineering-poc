# app/schemas/models.py
import enum
from datetime import datetime, timezone
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
