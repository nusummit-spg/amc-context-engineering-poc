# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/fund_metadata.py
========================
Pydantic schema for FundAuditMetadata (18 fields).
Provides fund profile, concentration, and performance metrics for AMC audit segmentation.
"""

from typing import Optional
from pydantic import BaseModel, Field


class FundAuditMetadata(BaseModel):
    """
    Schema for FundAuditMetadata used to segment funds for compliance and audit analysis.
    Node type in Neo4j with indices on fund_category, amc_id, fund_manager_id.
    """
    fund_id: str = Field(..., description="Unique fund identifier (e.g., FUND_001 or ISIN)")
    fund_name: str = Field(..., description="Full legal name of the mutual fund scheme")
    fund_category: str = Field(..., description="SEBI Category: Large Cap, Flexi Cap, Liquid, etc.")
    fund_type: str = Field(..., description="Open-ended, Close-ended, Interval, ETF")
    aum_cr: float = Field(..., ge=0.0, description="Assets Under Management in INR Crores")
    fund_manager_id: str = Field(..., description="Identifier for designated primary fund manager")
    fund_manager_experience_years: float = Field(..., ge=0.0, description="Fund manager industry experience in years")
    fund_creation_date: str = Field(..., description="Scheme inception date (YYYY-MM-DD)")
    benchmark_index: str = Field(..., description="Designated benchmark index (e.g. NIFTY 50 TRI)")
    ytd_return_pct: float = Field(..., description="Year-To-Date return percentage")
    expense_ratio_pct: float = Field(..., ge=0.0, description="Total Expense Ratio (TER) in percentage")
    portfolio_turnover_pct: float = Field(..., ge=0.0, description="Portfolio turnover ratio percentage")
    sharpe_ratio: float = Field(..., description="Risk-adjusted return Sharpe ratio")
    top_holding_concentration_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage of AUM in top single holding")
    sector_concentration_max_pct: float = Field(..., ge=0.0, le=100.0, description="Highest exposure percentage in any single sector")
    amc_id: str = Field(..., description="Asset Management Company identifier")
    regulatory_status: str = Field(default="ACTIVE", description="Regulatory status: ACTIVE, UNDER_REVIEW, MERGED, CLOSED")
    last_rebalance_date: Optional[str] = Field(default=None, description="Date of last asset allocation rebalance (YYYY-MM-DD)")
    last_audit_date: Optional[str] = Field(default=None, description="Date of most recent statutory or internal audit (YYYY-MM-DD)")
    created_at: str = Field(..., description="ISO 8601 timestamp when fund audit record was created")

