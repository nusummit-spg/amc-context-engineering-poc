# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
compliance_models.py
====================
Pydantic data models and enums for the AMC Compliance Auditing System.
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RegionEnum(str, Enum):
    SEBI = "SEBI"
    SEC = "SEC"
    ESMA = "ESMA"


class SeverityEnum(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RuleTypeEnum(str, Enum):
    PORTFOLIO = "portfolio"
    GOVERNANCE = "governance"
    KYC = "kyc"
    RISK = "risk"
    REPORTING = "reporting"


class ViolationStatusEnum(str, Enum):
    DETECTED = "detected"
    REVIEWED = "reviewed"
    REMEDIATED = "remediated"
    CLOSED = "closed"


# ── Request / Response Models ──────────────────────────────────────────

class RegulationCreate(BaseModel):
    id: str
    title: str
    region: RegionEnum = RegionEnum.SEBI
    effective_date: str
    document_url: str
    raw_text: str


class RegulationResponse(BaseModel):
    id: str
    title: str
    region: RegionEnum
    effective_date: str
    document_url: str
    raw_text: str
    created_at: Optional[str] = None


class RuleCreate(BaseModel):
    id: str
    rule_type: RuleTypeEnum
    title: str
    description: str
    regulation_id: str
    condition: str
    severity: SeverityEnum
    confidence_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    applicability: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    enforcement_level: str = "automatic"


class RuleResponse(BaseModel):
    id: str
    rule_type: RuleTypeEnum
    title: str
    description: str
    regulation_id: Optional[str] = None
    condition: str
    severity: SeverityEnum
    confidence_threshold: float
    applicability: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    enforcement_level: str
    active: bool = True


class FundSchemeCreate(BaseModel):
    id: str
    isin: str
    name: str
    fund_house: str
    category: str
    mandate: str
    risk_profile: str
    aum_cr: float
    region: RegionEnum = RegionEnum.SEBI
    rules_applicable_ids: List[str] = Field(default_factory=list)


class FundSchemeResponse(BaseModel):
    id: str
    isin: str
    name: str
    fund_house: str
    category: str
    mandate: str
    risk_profile: str
    aum_cr: float
    region: RegionEnum = RegionEnum.SEBI


class ViolationCreate(BaseModel):
    rule_id: str
    fund_id: str
    finding: str
    severity: SeverityEnum
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    actual_value: Any
    threshold_value: Any
    violation_type: RuleTypeEnum
    region: RegionEnum = RegionEnum.SEBI
    evidence_docs: List[str] = Field(default_factory=list)


class ViolationResponse(BaseModel):
    violation_id: str
    rule_id: str
    fund_id: str
    severity: SeverityEnum
    confidence: float
    actual_value: Any
    threshold_value: Any
    description: str
    detected_at: str
    status: ViolationStatusEnum = ViolationStatusEnum.DETECTED
    region: RegionEnum = RegionEnum.SEBI
    evidence_docs: List[str] = Field(default_factory=list)
    resolved_at: Optional[str] = None
    resolution_action: Optional[str] = None


class ComplianceScorecard(BaseModel):
    overall_compliance_score: float = Field(..., ge=0.0, le=100.0)
    compliance_percentage: str
    total_rules: int
    rules_passing: int
    rules_with_violations: int
    violations: Dict[str, int]
    region: RegionEnum
    last_audit_at: Optional[str] = None


class ComplianceAuditResultResponse(BaseModel):
    audit_id: str
    audit_started_at: str
    audit_completed_at: str
    total_funds: int
    total_rules_evaluated: int
    total_violations: int
    critical_violations: int
    high_violations: int
    medium_violations: int
    low_violations: int
    violations_by_fund: Dict[str, int]
    violations_by_rule: Dict[str, int]
    regions: Dict[str, Any]
    violations: List[ViolationResponse] = Field(default_factory=list)


class EscalationPathModel(BaseModel):
    id: str
    region: RegionEnum
    severity: SeverityEnum
    routing_rules: List[str]
    notification_channels: List[str]
    sla_hours: int
    requires_board_approval: bool = False


class AgentMetrics(BaseModel):
    """Metrics for an individual compliance domain agent."""
    agent_name: str
    violations_detected: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    accuracy_score: float = Field(default=0.95, ge=0.0, le=1.0)
    recorded_at: str
    region: RegionEnum = RegionEnum.SEBI


class AggregatedAgentMetrics(BaseModel):
    """Aggregated performance and accuracy metrics across all domain agents."""
    agents: Dict[str, AgentMetrics]
    overall_latency_ms: float = 0.0
    violations_by_severity: Dict[str, int] = Field(default_factory=dict)
    recorded_at: str
    region: RegionEnum = RegionEnum.SEBI


class AuditReportResponse(BaseModel):
    """Compliance audit report summary for a historical period."""
    period: str
    total_violations: int
    critical_violations: int
    remediated_violations: int
    remediation_rate: float
    generated_at: str
    region: Optional[RegionEnum] = None


from pydantic import BaseModel, Field, field_validator
import re
from datetime import date


class Role(str, Enum):
    VIEWER = "viewer"
    REVIEWER = "reviewer"
    RESOLVER = "resolver"
    ADMIN = "admin"


class ResolveViolationRequest(BaseModel):
    resolution_action: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Resolution action description",
    )

    @field_validator("resolution_action")
    @classmethod
    def validate_action_not_empty(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 3:
            raise ValueError("resolution_action must contain at least 3 non-whitespace characters")
        return s


class AuditFundRequest(BaseModel):
    """Request payload for triggering an audit on a single fund."""
    fund_id: str = Field(..., min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    fund_data: Optional[Dict[str, Any]] = None
    region: RegionEnum = RegionEnum.SEBI


class AuditBatchRequest(BaseModel):
    """Request payload for triggering concurrent batch audits."""
    funds: List[Dict[str, Any]] = Field(..., min_length=1, max_length=500)
    region: RegionEnum = RegionEnum.SEBI
    concurrency: int = Field(default=10, ge=1, le=50)


class HealthCheckResponse(BaseModel):
    """Comprehensive health diagnostic probe response."""
    status: str
    service: str = "amc-compliance-engine"
    version: str = "3.0.0"
    neo4j_connected: bool
    rules_cached_count: int
    rule_breakdown_by_region: Dict[str, int]
    active_agents: List[str]
    scorecard_cache_entries: int
    uptime_seconds: float
    timestamp: str


