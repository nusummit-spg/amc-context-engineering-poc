# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
compliance_alert.py
===================
Pydantic schema for real-time compliance alerting, SLA breach notification,
and multi-tier escalation tracking (L1 Analyst -> L2 Risk Manager -> L3 CCO).
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlertStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SUPPRESSED = "SUPPRESSED"
    RESOLVED = "RESOLVED"


class EscalationTier(str, Enum):
    L1_ANALYST = "L1_ANALYST"
    L2_RISK_MANAGER = "L2_RISK_MANAGER"
    L3_CCO = "L3_CCO"


class ComplianceAlert(BaseModel):
    alert_id: str = Field(..., description="Unique alert identifier (e.g. ALT_20260902_001)")
    violation_id: Optional[str] = Field(None, description="Linked compliance violation ID")
    remediation_id: Optional[str] = Field(None, description="Linked remediation metrics ID")
    severity: AlertSeverity = Field(..., description="Alert severity level")
    status: AlertStatus = Field(default=AlertStatus.ACTIVE, description="Current alert lifecycle state")
    escalation_tier: EscalationTier = Field(default=EscalationTier.L1_ANALYST, description="Active escalation level")
    title: str = Field(..., description="Summary alert headline")
    description: str = Field(..., description="Detailed explanation of breach or risk")
    sla_variance_hours: Optional[float] = Field(None, description="Hours overdue against statutory SLA")
    triggered_at: str = Field(..., description="ISO 8601 alert generation timestamp")
    acknowledged_at: Optional[str] = Field(None, description="ISO 8601 acknowledgment timestamp")
    acknowledged_by_user_id: Optional[str] = Field(None, description="User ID of acknowledging officer")
    resolved_at: Optional[str] = Field(None, description="ISO 8601 resolution timestamp")
    resolved_by_user_id: Optional[str] = Field(None, description="User ID of resolving officer")
    resolution_notes: Optional[str] = Field(None, description="Notes detailing remediation actions taken")
    suppression_window_minutes: int = Field(default=15, description="Minutes to suppress identical alerts")
