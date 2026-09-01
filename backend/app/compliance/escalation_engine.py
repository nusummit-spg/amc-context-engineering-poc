# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
escalation_engine.py
====================
Violation escalation routing, SLA assignment, and multi-region routing policies.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.compliance.rules_engine import ComplianceViolation

logger = logging.getLogger("compliance.escalation")


@dataclass
class EscalationAssignment:
    violation_id: str
    region: str
    severity: str
    assigned_roles: List[str]
    notification_channels: List[str]
    sla_deadline: str
    requires_board_approval: bool
    status: str = "open"


class EscalationEngine:
    """Routes compliance breaches according to regulatory severity and SLAs."""

    ROUTING_POLICIES = {
        "critical": {
            "SEBI": {
                "roles": ["chief_compliance_officer", "risk_committee", "board_of_trustees"],
                "channels": ["email_urgent", "slack_alerts", "sms_pager"],
                "sla_hours": 1,
                "requires_board_approval": True,
            },
            "SEC": {
                "roles": ["chief_compliance_officer", "general_counsel", "board_audit_committee"],
                "channels": ["email_urgent", "compliance_portal"],
                "sla_hours": 1,
                "requires_board_approval": True,
            },
            "ESMA": {
                "roles": ["compliance_director", "risk_management_function", "management_body"],
                "channels": ["email_urgent", "regulatory_portal"],
                "sla_hours": 2,
                "requires_board_approval": True,
            },
        },
        "high": {
            "DEFAULT": {
                "roles": ["compliance_officer", "fund_operations_lead"],
                "channels": ["email", "slack_alerts"],
                "sla_hours": 4,
                "requires_board_approval": False,
            }
        },
        "medium": {
            "DEFAULT": {
                "roles": ["compliance_analyst", "fund_accountant"],
                "channels": ["email", "internal_dashboard"],
                "sla_hours": 24,
                "requires_board_approval": False,
            }
        },
        "low": {
            "DEFAULT": {
                "roles": ["compliance_analyst"],
                "channels": ["internal_dashboard"],
                "sla_hours": 72,
                "requires_board_approval": False,
            }
        },
    }

    def route_violation(self, violation: ComplianceViolation) -> EscalationAssignment:
        """Route violation to appropriate teams and calculate SLA deadline."""
        sev = violation.severity.lower()
        region = violation.region.upper()

        policy_group = self.ROUTING_POLICIES.get(sev, self.ROUTING_POLICIES["low"])
        policy = policy_group.get(region) or policy_group.get("DEFAULT") or self.ROUTING_POLICIES["low"]["DEFAULT"]

        sla_hrs = policy.get("sla_hours", 24)
        deadline = (datetime.now() + timedelta(hours=sla_hrs)).isoformat()

        assignment = EscalationAssignment(
            violation_id=violation.violation_id,
            region=region,
            severity=sev,
            assigned_roles=policy.get("roles", ["compliance_analyst"]),
            notification_channels=policy.get("channels", ["internal_dashboard"]),
            sla_deadline=deadline,
            requires_board_approval=policy.get("requires_board_approval", False),
        )

        logger.info(
            "Routed violation %s (%s, %s) -> Roles: %s, SLA: %dh",
            violation.violation_id,
            region,
            sev,
            assignment.assigned_roles,
            sla_hrs,
        )
        return assignment
