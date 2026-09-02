# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
schemas/audit_trail_access.py
=============================
Pydantic schema for AuditTrailAccessMetrics (7 fields).
Access control tracking and cryptographic audit log integrity verification.
"""

from typing import Optional
from pydantic import BaseModel, Field


class AuditTrailAccessMetrics(BaseModel):
    """
    Schema for AuditTrailAccessMetrics to record and verify access to sensitive audit records.
    Node type in Neo4j with indices on user_id, accessed_at.
    """
    access_log_id: str = Field(..., description="Unique access log record identifier")
    user_id: str = Field(..., description="User or agent identifier who accessed data")
    user_role: str = Field(..., description="Role of accessor: COMPLIANCE_OFFICER, AUDITOR, SYSTEM_AGENT, FUND_MANAGER")
    resource_accessed: str = Field(..., description="Identifier of sensitive record or entity accessed")
    access_purpose: str = Field(..., description="Stated regulatory purpose: STATUTORY_AUDIT, SEBI_INSPECTION, INCIDENT_INVESTIGATION, PORTFOLIO_REVIEW")
    is_integrity_verified: bool = Field(default=True, description="Whether cryptographic hash signature of audit log is verified")
    data_sensitivity_level: str = Field(default="CONFIDENTIAL", description="Data classification: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED")
    access_approval_id: Optional[str] = Field(default=None, description="Ticket or workflow ID granting access approval")
    previous_log_hash: Optional[str] = Field(default=None, description="Cryptographic SHA-256 hash of previous audit log for tamper-evident blockchain/chaining")
    current_log_hash: str = Field(default="", description="Cryptographic SHA-256 hash of this entry combined with previous entry")
    accessed_at: str = Field(..., description="ISO 8601 timestamp of access event")

