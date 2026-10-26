# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/violation_cluster.py
============================
Pydantic schema for ViolationCluster (10 fields).
Groups related compliance violations across funds, rules, and AMCs to identify systemic clusters.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ViolationCluster(BaseModel):
    """
    Schema for ViolationCluster grouping correlated violations across funds and portfolio managers.
    Node type in Neo4j with indices on affected_amc_id, severity.
    """
    cluster_id: str = Field(..., description="Unique identifier for violation cluster")
    cluster_name: str = Field(..., description="Descriptive label for violation cluster")
    violation_ids: List[str] = Field(..., min_length=1, description="List of grouped ComplianceViolation IDs")
    common_rule_ids: List[str] = Field(default_factory=list, description="Common compliance rule IDs shared across cluster")
    affected_fund_ids: List[str] = Field(default_factory=list, description="Fund IDs impacted by this systemic cluster")
    affected_amc_id: str = Field(..., description="Asset Management Company identifier")
    severity: str = Field(default="HIGH", description="Composite cluster severity: CRITICAL, HIGH, MEDIUM, LOW")
    cluster_density_score: float = Field(..., ge=0.0, le=1.0, description="Correlation density/proximity score (0-1)")
    is_systemic_risk: bool = Field(default=True, description="Whether cluster poses broader systemic regulatory risk")
    cluster_category: Optional[str] = Field(
        default=None,
        description="Standard cluster category: market_crisis, portfolio_concentration, kyc_gap, disclosure_mismatch, execution_delay"
    )
    created_at: str = Field(..., description="ISO 8601 timestamp when cluster was identified")

