# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/compliance_dashboard_kpis.py
====================================
Pydantic schema for ComplianceDashboardKPIs (10 fields).
C-suite visibility into compliance posture, trends, velocity, and peer benchmarking.
"""

from typing import Optional
from pydantic import BaseModel, Field


class ComplianceDashboardKPIs(BaseModel):
    """
    Schema for ComplianceDashboardKPIs synthesizing executive compliance metrics.
    Node type in Neo4j with index on reporting_date.
    """
    kpi_id: str = Field(..., description="Unique KPI snapshot identifier")
    reporting_date: str = Field(..., description="Date of KPI evaluation snapshot (YYYY-MM-DD)")
    overall_compliance_index: float = Field(..., ge=0.0, le=100.0, description="Composite regulatory compliance score (0-100)")
    open_violations_count: int = Field(..., ge=0, description="Total active unresolved compliance breaches")
    critical_violations_count: int = Field(..., ge=0, description="Count of open breaches classified as CRITICAL severity")
    sla_adherence_rate_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage of remediations resolved within statutory SLA window")
    violation_velocity_period_pct: float = Field(default=0.0, description="Period-over-period change percentage in violation frequency")
    peer_benchmarking_percentile: float = Field(..., ge=0.0, le=100.0, description="Standing relative to industry peer AMCs (percentile 0-100)")
    systemic_risk_exposure_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Estimated percentage of total AUM exposed to open systemic issues")
    violations_resolved_this_month: Optional[int] = Field(default=None, ge=0, description="Count of violations fully closed and verified within current calendar month")
    average_resolution_days: Optional[float] = Field(default=None, ge=0.0, description="Rolling average turnaround duration in days across remediated violations")
    executive_summary: str = Field(..., description="C-suite narrative summary highlighting compliance standing and focal areas")

