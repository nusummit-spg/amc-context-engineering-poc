# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/remediation_metrics.py
==============================
Pydantic schema for RemediationMetrics (25 fields).
Critical for SLA compliance and regulatory penalty tracking across AMC violations.
"""

from typing import Optional
from pydantic import BaseModel, Field


class RemediationMetrics(BaseModel):
    """
    Schema for RemediationMetrics to track SLA compliance and resolution efficacy.
    Node type in Neo4j with indices on violation_id, sla_adherence, remediation_effectiveness.
    """
    remediation_id: str = Field(..., description="Unique remediation record identifier")
    violation_id: str = Field(..., description="Foreign key linking to specific ComplianceViolation ID")
    severity_level: str = Field(..., description="Violation severity: CRITICAL, HIGH, MEDIUM, LOW")
    sla_target_hours: float = Field(..., ge=0.0, description="Mandated SLA resolution window in hours")
    sla_target_date: str = Field(..., description="Calculated statutory deadline for remediation (ISO 8601)")
    detected_at: str = Field(..., description="Timestamp when violation was detected (ISO 8601)")
    remediation_initiated_at: Optional[str] = Field(default=None, description="Timestamp when remediation was begun (ISO 8601)")
    remediation_action: str = Field(..., description="Summary description of remediation action taken or planned")
    remediation_owner_user_id: str = Field(..., description="User ID or role of the assigned remediation owner")
    remediation_actual_completion_at: Optional[str] = Field(default=None, description="Timestamp when remediation was completed")
    resolution_time_hours: Optional[float] = Field(default=None, ge=0.0, description="Total elapsed resolution duration in hours")
    sla_adherence: str = Field(default="PENDING", description="SLA adherence status: WITHIN_SLA, BREACHED, PENDING")
    sla_variance_hours: Optional[float] = Field(default=None, description="Difference between actual and target SLA (positive = breached, negative = early)")
    remediation_effectiveness: str = Field(default="PENDING_VERIFICATION", description="Effectiveness outcome: EFFECTIVE, PARTIAL, INEFFECTIVE, PENDING_VERIFICATION")
    verification_date: Optional[str] = Field(default=None, description="Timestamp when compliance team verified the fix")
    verified_by_user_id: Optional[str] = Field(default=None, description="User ID of compliance officer who verified the resolution")
    re_violation_within_7d: bool = Field(default=False, description="Whether identical violation reoccurred within 7 days")
    re_violation_within_30d: bool = Field(default=False, description="Whether identical violation reoccurred within 30 days")
    root_cause_addressed: bool = Field(default=False, description="Whether fundamental root cause was eliminated")
    systemic_fix_applied: bool = Field(default=False, description="Whether systemic guardrail/rule update was deployed")
    escalated: bool = Field(default=False, description="Whether issue was escalated to Chief Compliance Officer / Board")
    escalation_reason: Optional[str] = Field(default=None, description="Reason for escalation if applicable")
    remediation_cost_hours: float = Field(default=0.0, ge=0.0, description="Person-hours expended to resolve violation")
    remediation_root_cause_id: Optional[str] = Field(default=None, description="Foreign key linking directly to RootCauseAnalysis ID")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")

