# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
governance_agent.py
===================
Autonomous compliance auditing agent for Board Governance, Manager Qualifications,
and Trustee Oversight Ratios.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.compliance.rules_engine import ComplianceViolation, RulesEngine
from app.graph.client import GraphClient, get_graph_client

logger = logging.getLogger("compliance.agents.governance")


@dataclass
class GovernanceAuditResult:
    fund_id: str
    fund_name: str
    agent_type: str = "governance"
    audit_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    violations: List[ComplianceViolation] = field(default_factory=list)
    checks_performed: List[str] = field(default_factory=list)
    compliance_status: str = "compliant"
    summary: Dict[str, Any] = field(default_factory=dict)


class GovernanceAgent:
    """Audits AMC governance standards, board independence, and manager certs."""

    def __init__(
        self,
        graph_client: Optional[GraphClient] = None,
        rules_engine: Optional[RulesEngine] = None
    ):
        self.graph = graph_client or get_graph_client()
        self.rules_engine = rules_engine or RulesEngine(self.graph)
        self.agent_type = "governance"

    async def audit_fund(
        self,
        fund_id: str,
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> GovernanceAuditResult:
        if fund_data is not None:
            fund_data = dict(fund_data)
            reg = region if region != "SEBI" else (fund_data.get("region") or region)
        else:
            reg = region
        logger.info("[GovernanceAgent] Starting governance audit for %s (region=%s)", fund_id, reg)
        if not self.rules_engine._rule_cache:
            await self.rules_engine.load_rules()

        if fund_data is None:
            fund_data = {
                "fund_id": fund_id,
                "fund_name": fund_id.replace("_", " "),
                "category": "equity_fund",
                "region": reg,
                "manager_certified": True,
                "independent_trustee_pct": 0.60,
                "evidence_docs": ["Trustee_Governance_Report_2024.pdf"],
            }
        else:
            fund_data["region"] = reg


        # Normalize nested manager & board structures
        if "manager" in fund_data and isinstance(fund_data["manager"], dict):
            cert = fund_data["manager"].get("certification")
            fund_data["manager_certified"] = 1 if cert and str(cert).upper() in ("CFA", "CAIA", "TRUE", "1") else 0
            fund_data["manager_certification"] = str(cert) if cert else "NONE"
        elif "manager_certified" in fund_data:
            fund_data["manager_certified"] = 1 if fund_data["manager_certified"] else 0

        if "board" in fund_data and isinstance(fund_data["board"], dict):
            total_t = fund_data["board"].get("total_trustees", 1)
            ind_t = fund_data["board"].get("independent_trustees", 0)
            fund_data["independent_trustee_pct"] = (ind_t / total_t) if total_t else 0.0
            fund_data["board_independence_pct"] = fund_data["independent_trustee_pct"] * 100.0

        checks = [
            "Fund Manager Certification",
            "Board of Trustees Independence Ratio",
        ]

        applicable_rules = await self.rules_engine.get_applicable_rules(
            rule_type="governance",
            region=reg
        )

        violations = []
        for r in applicable_rules:
            rid = r.get("id")
            if rid:
                v = await self.rules_engine.evaluate_rule(rid, fund_data)
                if v:
                    v.region = reg
                    violations.append(v)

        status = "non_compliant" if violations else "compliant"
        return GovernanceAuditResult(
            fund_id=fund_id,
            fund_name=fund_data.get("fund_name", fund_id),
            audit_timestamp=datetime.now().isoformat(),
            violations=violations,
            checks_performed=checks,
            compliance_status=status,
            summary={
                "total_checks": len(checks),
                "violations_count": len(violations),
                "critical": sum(1 for v in violations if v.severity == "critical"),
                "high": sum(1 for v in violations if v.severity == "high"),
            },
        )

    async def audit_governance(
        self,
        fund_id: str = "DEFAULT",
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> List[ComplianceViolation]:
        """Convenience helper returning violations list directly."""
        result = await self.audit_fund(fund_id=fund_id, fund_data=fund_data, region=region)
        return result.violations

