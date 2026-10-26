"""
domain_models.py
================
Pydantic domain models used by the Human Feedback Loop pipeline.

These are deliberately separate from the SQLAlchemy ORM models in models.py
so that the pipeline (services, adapters, orchestrator) has zero dependency
on SQLAlchemy. The SQLite adapters translate between the two layers.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class RatingType(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNRATED  = "unrated"


class FeedbackType(str, Enum):
    HALLUCINATION = "hallucination"
    INACCURATE    = "inaccurate"
    INCOMPLETE    = "incomplete"
    IRRELEVANT    = "irrelevant"
    OUTDATED      = "outdated"
    OTHER         = "other"
    SILENT_ACCEPT = "silent_accept"
    COMPLAINT     = "complaint"
    CORRECTION    = "correction"


class FeedbackSource(str, Enum):
    ACTIVE  = "active"
    PASSIVE = "passive"


class IngestionStatus(str, Enum):
    PENDING = "pending"
    SENT    = "sent"
    FAILED  = "failed"


class EntryRoute(str, Enum):
    HITL                      = "hitl"
    AUTOMATIC                 = "automatic"
    DISSATISFACTION_CONVERTED = "dissatisfaction_converted"


class RootCause(str, Enum):
    KNOWLEDGE           = "knowledge"
    RETRIEVAL           = "retrieval"
    GRAPH               = "graph"
    CONTEXT_ENGINEERING = "context_engineering"
    MODEL               = "model"
    GUARDRAIL           = "guardrail"
    COMPLIANCE          = "compliance"
    PRESENTATION        = "presentation"
    FEEDBACK_INVALID    = "feedback_invalid"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class LifecycleStatus(str, Enum):
    OPEN       = "open"
    DIAGNOSING = "diagnosing"
    RESOLVED   = "resolved"
    MONITORING = "monitoring"


class AdjudicationVerdict(str, Enum):
    VALID                 = "valid"
    PARTIALLY_VALID       = "partially_valid"
    INVALID               = "invalid"
    SUBJECTIVE            = "subjective"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EntityType(str, Enum):
    FUND      = "FUND"
    SCHEME    = "SCHEME"
    BENCHMARK = "BENCHMARK"
    MANAGER   = "MANAGER"
    OTHER     = "OTHER"


class StackLayer(str, Enum):
    KNOWLEDGE           = "knowledge"
    RETRIEVAL           = "retrieval"
    GRAPH               = "graph"
    CONTEXT_ENGINEERING = "context_engineering"
    MODEL               = "model"
    GUARDRAIL           = "guardrail"
    COMPLIANCE          = "compliance"
    PRESENTATION        = "presentation"
    FEEDBACK_INVALID    = "feedback_invalid"
    UNKNOWN             = "unknown"


class RepairTarget(str, Enum):
    VECTOR = "vector"
    GRAPH  = "graph"


# ── Primary pipeline models ────────────────────────────────────────────────────

class FeedbackRecord(BaseModel):
    """Pydantic representation of one response_feedback row for the pipeline."""
    feedback_id:      str              = Field(default_factory=lambda: str(uuid4()))
    source:           FeedbackSource
    received_at:      datetime
    ingestion_status: IngestionStatus  = IngestionStatus.PENDING

    response_id:      str
    session_id:       str
    rating:           RatingType
    feedback_type:    FeedbackType

    user_id:          Optional[str]   = None
    entity_name:      Optional[str]   = None
    entity_type:      Optional[str]   = None
    notes:            Optional[str]   = Field(default=None, max_length=2000)
    corrections:      Optional[dict]  = None
    timestamp:        Optional[datetime] = None

    model_config = {"use_enum_values": True}


class UnifiedEvaluationRecord(BaseModel):
    """
    Pydantic representation written to unified_evaluation_records.
    First 8 fields set by this module; the rest stay None until the
    Evaluation Layer updates the same row.
    """
    # Set by this module
    session_id:             str
    response_id:            str
    entry_route:            EntryRoute
    feedback_ref:           Optional[str]          = None
    evidence_snapshot_ref:  str
    root_cause:             Optional[RootCause]    = None
    severity:               Optional[Severity]     = None
    lifecycle_status:       LifecycleStatus        = LifecycleStatus.OPEN
    dissatisfaction_evidence: Optional[dict]       = None

    # Repair fields (Steps 5 & 6)
    repair:                  bool                   = False
    repair_target:           Optional[RepairTarget] = None

    # Set later by the Evaluation Layer
    deterministic_results:   Optional[dict]  = None
    gnn_plausibility_score:  Optional[float] = None
    semantic_results:        Optional[dict]  = None
    llm_evaluation:          Optional[dict]  = None
    adjudication_verdict:    Optional[AdjudicationVerdict] = None
    adjudication_confidence: Optional[float] = None

    model_config = {"use_enum_values": True}


class DiagnosisResult(BaseModel):
    stack_layer: StackLayer
    confidence:  float
    evidence:    str


class RepairAnalysis(BaseModel):
    repair:        bool
    repair_target: Optional[RepairTarget] = None
    reason:        str                    = ""


# ── Intermediate value objects ─────────────────────────────────────────────────

class ClassificationResult(BaseModel):
    entity_extracted:   Optional[str]   = None
    entity_type:        Optional[str]   = None
    value_mentioned:    Optional[str]   = None
    sentiment_compound: float           = 0.0
    intent:             Optional[str]   = None


class EvidenceChunk(BaseModel):
    chunk_id:       str
    value:          Optional[str]   = None
    source_version: Optional[str]   = None
    content:        Optional[str]   = None


class EvidenceSnapshot(BaseModel):
    response_id:       str
    original_query:    str
    response_text:     str
    entity_name:       Optional[str]         = None
    evidence_selected: list[EvidenceChunk]   = Field(default_factory=list)


class FollowUpQuery(BaseModel):
    query_id:   str
    text:       str
    created_at: datetime


class DissatisfactionSignal(BaseModel):
    triggers:    list[str]
    source_text: str
    confidence:  float


class EnrichmentResult(BaseModel):
    evidence_snapshot_ref:  str
    evidence_snapshot:      EvidenceSnapshot
    is_duplicate:           bool                           = False
    cluster_id:             Optional[str]                  = None
    entry_route:            EntryRoute
    dissatisfaction_signal: Optional[DissatisfactionSignal] = None


class RuleFinding(BaseModel):
    rule:           str
    result:         str
    response_value: Optional[Any] = None
    evidence_value: Optional[Any] = None
    delta_pct:      Optional[float] = None
    detail:         Optional[str]   = None


class RouterResult(BaseModel):
    rules_fired: list[RuleFinding]
    severity:    Optional[Severity]


class AdjudicationResult(BaseModel):
    root_cause: Optional[RootCause]
