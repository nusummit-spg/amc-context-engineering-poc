# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
models/scheme_aggregation.py
============================
Pydantic schemas for scheme-level aggregation data.
Materializes aggregated metrics across multiple plan variants of a single scheme.
Used for comprehensive "top 10 schemes" queries without Cypher row limit constraints.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class SchemeAggregationMetrics(BaseModel):
    """
    Aggregated metrics for a single mutual fund scheme across all plan types/variants.
    Materializes the following aggregations from plan-level data in mutual_fund_data.csv:
    
    For each scheme name, this model contains:
    - Aggregated AUM metrics (maximum, minimum, average)
    - Plan variant count
    - Latest NAV and date
    - Scheme classification and metadata
    """
    
    # Scheme Identification
    scheme_name: str = Field(..., description="Unique scheme name (aggregated across all plan types)")
    scheme_code: Optional[str] = Field(None, description="Primary SEBI scheme code")
    amc: str = Field(..., description="Asset Management Company name")
    amc_short_code: Optional[str] = Field(None, description="AMC short code for internal reference")
    
    # Scheme Classification
    scheme_type: str = Field(..., description="Open Ended / Close Ended / Interval / ETF")
    scheme_category: str = Field(..., description="SEBI Category: Large Cap, Small Cap, Liquid, Debt, Hybrid, etc.")
    
    # AUM Metrics (Aggregated)
    max_aum_cr: float = Field(..., ge=0.0, description="Maximum Average AUM in ₹ Crores across all plan types")
    min_aum_cr: float = Field(..., ge=0.0, description="Minimum Average AUM in ₹ Crores across plan types")
    avg_aum_cr: float = Field(..., ge=0.0, description="Average AUM in ₹ Crores across all plan types")
    total_aum_cr: float = Field(..., ge=0.0, description="Sum of all plan AUM in ₹ Crores (for blended view)")
    
    # Plan Variant Information
    plan_count: int = Field(..., ge=1, description="Number of distinct plan variants (Regular, Direct, Institutional, etc.)")
    plan_variants: List[str] = Field(default_factory=list, description="List of plan names/types available")
    
    # NAV and Pricing
    latest_nav: Optional[float] = Field(None, ge=0.0, description="Latest NAV per unit")
    latest_nav_date: Optional[str] = Field(None, description="Date of latest NAV (YYYY-MM-DD)")
    
    # Minimum Investment
    scheme_min_amt: Optional[str] = Field(None, description="Minimum investment amount (text, may vary by plan)")
    
    # Launch Information
    launch_date: Optional[str] = Field(None, description="Scheme inception date (YYYY-MM-DD)")
    closure_date: Optional[str] = Field(None, description="Scheme closure date if applicable (YYYY-MM-DD)")
    is_active: bool = Field(default=True, description="True if scheme is active (no closure date)")
    
    # Data Quality & Timestamp
    data_quarter: str = Field(..., description="Data quarter period (e.g., 'January - March 2026')")
    last_aggregated_at: str = Field(..., description="ISO 8601 timestamp of last aggregation")
    plan_data_completeness: float = Field(..., ge=0.0, le=1.0, description="Fraction of plan variants with valid AUM data")
    
    # Rankings (for ease of sorting)
    rank_by_max_aum: Optional[int] = Field(None, description="Rank position when sorted by max_aum_cr descending")
    rank_by_avg_aum: Optional[int] = Field(None, description="Rank position when sorted by avg_aum_cr descending")
    rank_by_total_aum: Optional[int] = Field(None, description="Rank position when sorted by total_aum_cr descending")
    
    class Config:
        json_schema_extra = {
            "example": {
                "scheme_name": "SBI Nifty 50 ETF",
                "scheme_code": "INF200K01T28",
                "amc": "SBI Funds Management Limited",
                "amc_short_code": "SBI",
                "scheme_type": "Open Ended",
                "scheme_category": "Equity Scheme - Index Fund",
                "max_aum_cr": 210783.07,
                "min_aum_cr": 85429.33,
                "avg_aum_cr": 148106.20,
                "total_aum_cr": 296212.40,
                "plan_count": 2,
                "plan_variants": ["Regular Growth", "Institutional"],
                "latest_nav": 177.89,
                "latest_nav_date": "2026-06-29",
                "launch_date": "2009-07-27",
                "is_active": True,
                "data_quarter": "January - March 2026",
                "plan_data_completeness": 1.0,
                "rank_by_max_aum": 1
            }
        }


class DualViewAUMResponse(BaseModel):
    """
    Dual-view response for mutual fund scheme AUM rankings.
    Provides both plan-level and scheme-level aggregation for AMC managers/analysts.
    
    Use Case: When querying "Top 10 schemes by Average AUM", this response includes:
    1. Plan-Level View: Individual plan variants with their specific AUM values
    2. Scheme-Level View: Aggregated scheme metrics for easier comparison and decision-making
    """
    
    # Metadata
    query: str = Field(..., description="Original user query")
    query_intent: str = Field(..., description="Detected query intent: 'ranking', 'comparison', 'aggregation', etc.")
    generated_at: str = Field(..., description="ISO 8601 timestamp when response was generated")
    data_period: str = Field(..., description="Data period covered: 'January - March 2026'")
    
    # Scheme-Level Rankings (Primary View)
    scheme_level_rankings: List[SchemeAggregationMetrics] = Field(
        ..., 
        description="Top N schemes ranked by aggregated AUM (scheme-level deduplication)"
    )
    
    # Plan-Level Rankings (Detailed View)
    plan_level_rankings: List[dict] = Field(
        ...,
        description="Top N individual plan variants with specific AUM values (before aggregation)"
    )
    
    # Statistics
    total_unique_schemes: int = Field(..., ge=0, description="Total number of unique schemes in result set")
    total_plan_variants: int = Field(..., ge=0, description="Total number of plan variants across all result schemes")
    scheme_level_count: int = Field(..., ge=0, description="Number of schemes in scheme-level rankings")
    plan_level_count: int = Field(..., ge=0, description="Number of plan variants in plan-level rankings")
    
    # Data Quality
    data_completeness: float = Field(..., ge=0.0, le=1.0, description="Overall data completeness (0-1)")
    schemes_with_multiple_plans: int = Field(..., ge=0, description="Count of schemes with 2+ plan variants")
    
    # Guidance for Interpretation
    interpretation_guide: str = Field(
        ...,
        description="Human-readable guidance on interpreting both views for decision-making"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "Top 10 schemes by Average AUM",
                "query_intent": "ranking",
                "generated_at": "2026-10-26T15:30:00Z",
                "data_period": "January - March 2026",
                "scheme_level_rankings": [
                    {
                        "scheme_name": "SBI Nifty 50 ETF",
                        "amc": "SBI Funds Management Limited",
                        "max_aum_cr": 210783.07,
                        "avg_aum_cr": 148106.20,
                        "plan_count": 2,
                        "rank_by_max_aum": 1
                    }
                ],
                "plan_level_rankings": [
                    {
                        "scheme_name": "SBI Nifty 50 ETF",
                        "plan_name": "Regular Growth",
                        "auc": 210783.07,
                        "rank": 1
                    }
                ],
                "total_unique_schemes": 10,
                "total_plan_variants": 22,
                "scheme_level_count": 10,
                "plan_level_count": 22,
                "data_completeness": 0.98,
                "schemes_with_multiple_plans": 7,
                "interpretation_guide": "Use scheme-level rankings for high-level comparison of schemes. Use plan-level rankings to understand which specific plan variants drive AUM concentration."
            }
        }


class SchemeAggregationRequest(BaseModel):
    """Request payload for scheme-level aggregation query."""
    
    limit: int = Field(default=10, ge=1, le=100, description="Number of top schemes to return")
    sort_by: str = Field(
        default="max_aum",
        description="Sorting criteria: 'max_aum', 'avg_aum', 'total_aum', 'plan_count'"
    )
    include_plan_details: bool = Field(
        default=True,
        description="Include detailed plan-level breakdowns in response"
    )
    include_inactive: bool = Field(
        default=False,
        description="Include closed/inactive schemes in results"
    )
    min_plan_count: int = Field(
        default=1,
        ge=1,
        description="Minimum number of plan variants to include scheme in results"
    )
    amc_filter: Optional[str] = Field(
        None,
        description="Optional AMC name filter to restrict results to single AMC"
    )
    category_filter: Optional[str] = Field(
        None,
        description="Optional scheme category filter (e.g., 'Equity Scheme - Large Cap Fund')"
    )


class AMCAggregationMetrics(BaseModel):
    """
    Aggregated metrics for an Asset Management Company (AMC).
    Materialized across all schemes and plan variants managed by the AMC.
    """
    amc: str = Field(..., description="Asset Management Company name")
    total_aum_cr: float = Field(..., ge=0.0, description="Total AUM in ₹ Crores across all schemes/plans")
    avg_aum_cr: float = Field(..., ge=0.0, description="Average AUM in ₹ Crores per plan variant")
    distinct_schemes: int = Field(..., ge=0, description="Number of distinct schemes offered by this AMC")
    total_plans: int = Field(..., ge=0, description="Total number of plan variants across all schemes")
    rank: Optional[int] = Field(None, description="Ranking position")

    class Config:
        json_schema_extra = {
            "example": {
                "amc": "SBI Funds Management Limited",
                "total_aum_cr": 1260906.03,
                "avg_aum_cr": 2491.91,
                "distinct_schemes": 127,
                "total_plans": 506,
                "rank": 1,
            }
        }


class AMCAggregationResponse(BaseModel):
    """
    Response model for AMC-level aggregation and ranking queries.
    """
    query: str = Field(..., description="Original user query")
    query_intent: str = Field(default="amc_ranking", description="Detected query intent")
    generated_at: str = Field(..., description="ISO 8601 timestamp when response was generated")
    data_period: str = Field(..., description="Data period covered (e.g., 'January - March 2026')")
    amc_rankings: List[AMCAggregationMetrics] = Field(..., description="Ranked list of AMCs")
    total_unique_amcs: int = Field(..., ge=0, description="Total number of unique AMCs analyzed")
    interpretation_guide: str = Field(..., description="Human-readable guidance on interpreting AMC metrics")


class NAVAggregationMetrics(BaseModel):
    """
    Metrics for mutual fund schemes ranked by NAV.
    """
    scheme_name: str = Field(..., description="Scheme name")
    plan_name: str = Field(..., description="Scheme NAV / plan variant name")
    amc: str = Field(..., description="Managing Asset Management Company")
    nav: float = Field(..., description="Net Asset Value in ₹")
    latest_nav_date: Optional[str] = Field(None, description="Date of latest NAV (YYYY-MM-DD)")
    scheme_type: str = Field(..., description="Open Ended / Close Ended / Interval")
    scheme_category: str = Field(..., description="SEBI category")
    rank: Optional[int] = Field(None, description="Ranking position")


class NAVAggregationResponse(BaseModel):
    """
    Response model for NAV ranking queries.
    """
    query: str = Field(..., description="Original user query")
    query_intent: str = Field(default="nav_ranking", description="Detected query intent")
    generated_at: str = Field(..., description="ISO 8601 timestamp when response was generated")
    data_period: str = Field(..., description="Data period or latest date")
    schemes: List[NAVAggregationMetrics] = Field(..., description="Ranked list of schemes by NAV")
    total_matching: int = Field(..., ge=0, description="Total schemes matching filter criteria")
    applied_filters: dict = Field(default_factory=dict, description="Filters applied (scheme_type, category, plan)")
    interpretation_guide: str = Field(..., description="Interpretation guidance")


class CategoryAggregationMetrics(BaseModel):
    category: str = Field(..., description="Mutual fund category name")
    distinct_schemes: int = Field(..., ge=0, description="Number of distinct scheme families in this category")
    total_folios: int = Field(..., ge=0, description="Total number of plan folios/variants")
    total_aum_cr: float = Field(..., ge=0.0, description="Total AUM in ₹ Crores across all schemes in category")
    pct_of_total_aum: float = Field(..., ge=0.0, le=100.0, description="Percentage of overall mutual fund market AUM")
    avg_aum_per_scheme_cr: float = Field(..., ge=0.0, description="Average AUM per scheme family in ₹ Crores")
    rank: Optional[int] = Field(None, description="Category ranking position by total AUM")


class CategoryAggregationResponse(BaseModel):
    query: str = Field(..., description="Original user query")
    query_intent: str = Field(default="category_aggregation", description="Detected query intent")
    generated_at: str = Field(..., description="ISO 8601 timestamp when response was generated")
    data_period: str = Field(..., description="Data period covered (e.g., 'January - March 2026')")
    categories: List[CategoryAggregationMetrics] = Field(..., description="Ranked list of categories by AUM")
    total_market_aum_cr: float = Field(..., ge=0.0, description="Total mutual fund market AUM in ₹ Crores")
    total_distinct_schemes: int = Field(..., ge=0, description="Total distinct scheme families across all categories")
    total_folios: int = Field(..., ge=0, description="Total plan folios in dataset")
    interpretation_guide: str = Field(..., description="Human-readable interpretation guide")
