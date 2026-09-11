"""Pydantic request schemas for the AMC audit & compliance evidence tables."""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.models import (
    Region,
    AuditType,
    AuditStatus,
    ComplianceTrend,
    ViolationCategory,
    ViolationStatus,
    Severity,
    ConfidenceLevel,
)


class AuditMetadataCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    audit_id: Optional[str] = Field(default=None, description="Auto-generated if omitted")
    region: Region
    audit_type: AuditType
    funds_audited_count: int = 0
    funds_passed_count: int = 0
    funds_with_violations_count: int = 0
    total_rules_evaluated: int = 0
    total_violations_detected: int = 0
    critical_violations: int = 0
    high_violations: int = 0
    medium_violations: int = 0
    low_violations: int = 0
    audit_duration_ms: Optional[int] = 0
    overall_compliance_score: Optional[float] = 0.0
    compliance_trend: Optional[ComplianceTrend] = ComplianceTrend.STABLE
    status: AuditStatus = AuditStatus.STARTED
    triggered_by: Optional[str] = None
    triggering_action: Optional[str] = None
    report_id: Optional[str] = None
    escalation_triggered: bool = False
    evidence_pack_id: Optional[str] = None
    evidence_manifest_json: Optional[dict[str, Any] | list] = None


class ViolationCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    violation_id: Optional[str] = None
    audit_id: str = Field(..., description="Must match an existing audit_metadata.audit_id")
    rule_id: str
    fund_id: str
    severity: Severity
    violation_type: ViolationCategory
    region: Region
    description: str
    actual_value: Optional[str] = None
    threshold_value: Optional[str] = None
    gap_percentage: Optional[float] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    evidence_count: Optional[int] = 0
    status: ViolationStatus = ViolationStatus.DETECTED
    detected_at: Optional[str] = Field(default=None, description="ISO timestamp; defaults to now")
    resolution_action: Optional[str] = None
    resolved_by_user_id: Optional[str] = None
    resolution_notes: Optional[str] = None
    evidence_docs_json: Optional[list | dict] = None
    audit_trail_json: Optional[list | dict] = None
    escalation_level: Optional[int] = 0
    created_by: Optional[str] = None


class ResponseFeedbackCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    feedback_id: Optional[str] = None
    response_id: str
    interaction_id: Optional[str] = None  # auto-generated if omitted
    session_id: Optional[str] = None      # backfilled from query_evidence if omitted
    turn_number: int = 1
    query_text: Optional[str] = None      # backfilled from query_evidence if omitted
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    selected_categories: list[str] = Field(default_factory=list)
    free_text: Optional[str] = None
    answer_relevance_score: Optional[int] = Field(default=None, ge=1, le=5)
    source_quality_score: Optional[int] = Field(default=None, ge=1, le=5)
    completeness_score: Optional[int] = Field(default=None, ge=1, le=5)
    automated_category: Optional[str] = None
    automated_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    client_timestamp: Optional[str] = None
    audit_id: Optional[str] = None
    violation_id: Optional[str] = None

    # --- MISSING_SCHEMA_DEFINITIONS.md "Enhanced Table 2" ---
    response_text: Optional[str] = None       # backfilled from query_evidence if omitted
    response_summary: Optional[str] = None
    feedback_text: Optional[str] = None
    feedback_span: Optional[str] = None
    classification_json: Optional[dict[str, Any] | list] = None
    root_cause: Optional[str] = None


class QueryEvidenceCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    response_id: str
    session_id: str
    request_id: Optional[str] = None
    query_text: str
    query_type: Optional[str] = None
    query_intent: Optional[str] = None
    retrieval_mode: str = "contextgraph"
    serving_engine: Optional[str] = None
    assembled_context_json: dict[str, Any] | list
    synthesis_output_json: dict[str, Any] | list
    graph_highlight_json: Optional[dict[str, Any] | list] = None
    traditional_result_json: Optional[dict[str, Any] | list] = None
    latency_ms: Optional[int] = None
    retrieval_latency_ms: Optional[int] = None
    synthesis_latency_ms: Optional[int] = None
    quality_score: Optional[float] = None
    confidence_level: Optional[ConfidenceLevel] = None
    audit_id: Optional[str] = None
    linked_violations_json: Optional[list] = None
    has_feedback: bool = False
    feedback_summary_json: Optional[dict[str, Any]] = None

    # --- MISSING_SCHEMA_DEFINITIONS.md "Enhanced Table 3" ---
    entry_route: Optional[str] = None
    root_cause: Optional[str] = None
    severity: Optional[str] = None
    dissatisfaction_evidence_json: Optional[dict[str, Any] | list] = None


class ComplianceRuleCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    rule_id: str
    regulation_id: Optional[str] = None
    rule_type: ViolationCategory
    region: Region
    title: str
    description: Optional[str] = None
    condition_plain_text: Optional[str] = None
    condition_code_json: Optional[dict[str, Any]] = None
    applicable_categories: Optional[list[str]] = None
    exclusions_json: Optional[dict[str, Any] | list] = None
    severity: Severity
    enforcement_level: Optional[str] = "automatic"
    confidence_threshold: Optional[float] = Field(default=0.95, ge=0.0, le=1.0)
    required_evidence_types: Optional[list[str]] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    is_active: bool = True
    version_number: int = 1
    regulation_section: Optional[str] = None
    document_url: Optional[str] = None
    last_modified_by: Optional[str] = None


class FundSchemeCreate(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    fund_id: str
    isin: Optional[str] = None
    name: str
    fund_house: str
    category: Optional[str] = None
    mandate: Optional[str] = None
    risk_profile: Optional[str] = None
    aum_crores: Optional[float] = None
    nav_per_unit: Optional[float] = None
    region: Region
    applicable_rules_json: Optional[list[str]] = None


class ChatSessionCreate(BaseModel):
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    audit_id: Optional[str] = Field(default=None, description="Must match audit_metadata.audit_id if set")