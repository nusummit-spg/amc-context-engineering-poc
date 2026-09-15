# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/fund_family_analysis.py
===============================
Pydantic schema for FundFamilyAnalysis (10 fields).
Evaluates cross-fund correlations, portfolio manager accountability, and AMC-level systemic risk.
"""

from typing import Dict, Optional
from pydantic import BaseModel, Field


class FundFamilyAnalysis(BaseModel):
    """
    Schema for FundFamilyAnalysis to aggregate compliance risk across an AMC fund family.
    Node type in Neo4j with indices on amc_id, systemic_risk_flag.
    """
    analysis_id: str = Field(..., description="Unique fund family analysis identifier")
    amc_id: str = Field(..., description="Asset Management Company identifier")
    fund_family_name: str = Field(..., description="Legal/brand name of fund family (e.g. Nippon India Mutual Fund)")
    total_funds_analyzed: int = Field(..., ge=1, description="Total count of schemes evaluated in analysis batch")
    cross_fund_correlation_score: float = Field(..., ge=0.0, le=1.0, description="Correlation score of compliance violations across funds (0-1)")
    portfolio_manager_accountability_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Map of portfolio manager ID to individual compliance accountability score (0-1)"
    )
    systemic_risk_flag: bool = Field(default=False, description="Flag indicating AMC-wide systemic compliance risk")
    dominant_violation_category: Optional[str] = Field(default=None, description="Most frequent failure category code across family")
    highest_risk_fund_id: Optional[str] = Field(default=None, description="Fund ID exhibiting greatest compliance risk exposure")
    fund_count_by_category: Dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of schemes across SEBI regulatory categories"
    )
    analyzed_at: str = Field(..., description="ISO 8601 timestamp when analysis was conducted")

