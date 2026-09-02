# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/root_cause_analysis.py
==============================
Pydantic schema for RootCauseAnalysis (15 fields).
Classifies compliance failure origins and tracks systemic vs. isolated issues.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class RootCauseAnalysis(BaseModel):
    """
    Schema for RootCauseAnalysis to determine underlying drivers of compliance breaches.
    Node type in Neo4j with indices on violation_id, primary_category, is_systemic.
    """
    rca_id: str = Field(..., description="Unique Root Cause Analysis identifier")
    violation_id: str = Field(..., description="Foreign key linking to specific ComplianceViolation ID")
    primary_category: str = Field(
        ...,
        description="Primary cause category: operational_error, market_volatility, policy_change, system_failure, data_quality"
    )
    secondary_categories: List[str] = Field(
        default_factory=list,
        description="Secondary or compounding failure categories"
    )
    root_cause_description: str = Field(..., description="Detailed narrative explaining root cause mechanics")
    is_systemic: bool = Field(default=False, description="Whether failure represents a systemic multi-fund vulnerability vs isolated anomaly")
    repeat_violation_count: int = Field(default=0, ge=0, description="Number of historical recurring violations of this pattern")
    cluster_id: Optional[str] = Field(default=None, description="Optional cluster ID if grouped into a systemic violation cluster")
    market_context: Optional[str] = Field(default=None, description="Macroeconomic or market volatility context active during breach")
    contributing_factors: List[str] = Field(default_factory=list, description="List of operational or technological contributing factors")
    detection_mechanism: str = Field(default="rules_engine", description="Mechanism that caught the issue: rules_engine, domain_agent, audit_sampling")
    preventability_score: float = Field(..., ge=0.0, le=1.0, description="Estimated score indicating how preventable the breach was (0-1)")
    recommended_remedy_type: str = Field(
        default="GUARDRAIL_UPDATE",
        description="Prescribed remedy: GUARDRAIL_UPDATE, KNOWLEDGE_PATCH, PROCESS_CHANGE, POLICY_OVERLAY"
    )
    estimated_remediation_cost_hours: Optional[float] = Field(default=None, ge=0.0, description="Estimated engineering/compliance person-hours to apply remedy")
    implementation_timeline_days: Optional[int] = Field(default=None, ge=0, description="Estimated implementation timeline in business days")
    investigated_by: str = Field(default="compliance_investigator", description="Officer or agent who completed root cause analysis")
    analyzed_at: str = Field(..., description="ISO 8601 timestamp when RCA was completed")

