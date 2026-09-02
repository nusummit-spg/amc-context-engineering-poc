# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/feedback_analytics.py
=============================
Pydantic schema for FeedbackCategoryAnalytics (16 fields).
Tracks F01–F12 failure taxonomy trending, velocity, and resolution across reporting periods.
"""

from pydantic import BaseModel, Field


class FeedbackCategoryAnalytics(BaseModel):
    """
    Schema for FeedbackCategoryAnalytics to monitor taxonomy distribution and trends over time.
    Node type in Neo4j with indices on reporting_period, category_id, trend.
    """
    analytics_id: str = Field(..., description="Unique category analytics identifier")
    reporting_period: str = Field(..., description="Reporting window identifier (e.g. 2024-09, 2024-09-week-1)")
    category_id: str = Field(..., description="Failure taxonomy category code (F01-F14)")
    category_name: str = Field(..., description="Human-readable category name")
    frequency_count: int = Field(..., ge=0, description="Total occurrences of this category in reporting period")
    frequency_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage share of total feedback occurrences")
    trend: str = Field(default="STABLE", description="Directional trend: INCREASING, DECREASING, STABLE")
    prior_period_count: int = Field(default=0, ge=0, description="Occurrences in previous equivalent reporting period")
    category_velocity_pct: float = Field(default=0.0, description="Period-over-period percentage change in frequency")
    median_response_severity: str = Field(default="MEDIUM", description="Median severity level: CRITICAL, HIGH, MEDIUM, LOW")
    avg_resolution_time_days: float = Field(default=0.0, ge=0.0, description="Average duration in days to diagnose and resolve category issues")
    top_query_pattern: str = Field(default="", description="Most representative query pattern triggering this failure category")
    top_fund_with_category: str = Field(default="", description="Fund ID or category most frequently associated with this issue")
    recommended_action: str = Field(default="", description="Prescribed engineering or compliance remediation action")
    action_type: str = Field(default="GUARDRAIL_UPDATE", description="Standardized action type: GUARDRAIL_UPDATE, RETRAIN_MODEL, DOCUMENTATION_FIX, PROCESS_CHANGE, ACKNOWLEDGE_LIMITATION")
    estimated_effort_hours: float = Field(default=0.0, ge=0.0, description="Estimated engineering/compliance person-hours to clear category backlog")
    period_start_date: str = Field(..., description="Start date of analytics period (YYYY-MM-DD)")

