# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/realtime_monitoring.py
==============================
Pydantic schema for RealTimeMonitoringMetrics (7 fields).
Measures compliance engine operational throughput, intra-day detection, and response times.
"""

from typing import Optional
from pydantic import BaseModel, Field


class RealTimeMonitoringMetrics(BaseModel):
    """
    Schema for RealTimeMonitoringMetrics to measure live compliance monitoring telemetry.
    Node type in Neo4j with index on monitoring_window_start.
    """
    monitoring_id: str = Field(..., description="Unique monitoring window identifier")
    monitoring_window_start: str = Field(..., description="Start of intra-day monitoring window (ISO 8601)")
    intraday_detections_count: int = Field(default=0, ge=0, description="Total compliance breaches detected during intra-day window")
    active_alerts_count: int = Field(default=0, ge=0, description="Current unacknowledged active alerts count")
    avg_alert_response_time_sec: float = Field(default=0.0, ge=0.0, description="Average response latency to compliance triggers in seconds")
    system_uptime_pct: float = Field(default=99.99, ge=0.0, le=100.0, description="Operational uptime percentage of compliance engine")
    engine_throughput_qps: float = Field(default=0.0, ge=0.0, description="Compliance checks processed per second (QPS)")
    p95_latency_ms: Optional[float] = Field(default=None, ge=0.0, description="95th percentile query/check latency in milliseconds")
    p99_latency_ms: Optional[float] = Field(default=None, ge=0.0, description="99th percentile query/check latency in milliseconds")

