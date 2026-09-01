# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
risk_agent.py
=============
Autonomous compliance auditing agent for Value-at-Risk (VaR), Liquidity Buffer,
and Stress Testing parameters.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.compliance.rules_engine import ComplianceViolation, RulesEngine
from app.graph.client import GraphClient, get_graph_client

logger = logging.getLogger("compliance.agents.risk")


@dataclass
class RiskAuditResult:
    fund_id: str
    fund_name: str
    agent_type: str = "risk"
    audit_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    violations: List[ComplianceViolation] = field(default_factory=list)
    checks_performed: List[str] = field(default_factory=list)
    compliance_status: str = "compliant"
    summary: Dict[str, Any] = field(default_factory=dict)


class RiskAgent:
    """Audits market risk boundaries, liquidity buffers, and stress resilience."""

    def __init__(
        self,
        graph_client: Optional[GraphClient] = None,
        rules_engine: Optional[RulesEngine] = None
    ):
        self.graph = graph_client or get_graph_client()
        self.rules_engine = rules_engine or RulesEngine(self.graph)
        self.agent_type = "risk"

    async def audit_fund(
        self,
        fund_id: str,
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> RiskAuditResult:
        if fund_data is not None:
            fund_data = dict(fund_data)
            reg = region if region != "SEBI" else (fund_data.get("region") or region)
        else:
            reg = region
        logger.info("[RiskAgent] Starting risk audit for %s (region=%s)", fund_id, reg)
        if not self.rules_engine._rule_cache:
            await self.rules_engine.load_rules()

        if fund_data is None:
            fund_data = {
                "fund_id": fund_id,
                "fund_name": fund_id.replace("_", " "),
                "category": "equity_fund",
                "region": reg,
                "cash_buffer_pct": 0.06,
                "daily_var_99": 0.032,
                "evidence_docs": ["Risk_VaR_Report_2024.pdf"],
            }
        else:
            fund_data["region"] = reg


        # Normalize risk metrics
        if "var_pct" in fund_data:
            val = float(fund_data["var_pct"])
            fund_data["daily_var_99"] = val / 100.0 if val > 1.0 else val
            if "risk" not in fund_data:
                fund_data["risk"] = {}
            fund_data["risk"]["var_99_daily_pct"] = val if val > 1.0 else val * 100.0

        if "liquid_cash_pct" in fund_data:
            val = float(fund_data["liquid_cash_pct"])
            fund_data["cash_buffer_pct"] = val / 100.0 if val > 1.0 else val
            if "risk" not in fund_data:
                fund_data["risk"] = {}
            fund_data["risk"]["liquid_cash_pct"] = val if val > 1.0 else val * 100.0

        checks = [
            "Mandatory Liquid Cash Buffer",
            "99% 1-Day Value at Risk",
        ]

        applicable_rules = await self.rules_engine.get_applicable_rules(
            rule_type="risk",
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
        return RiskAuditResult(
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

    async def audit_risk(
        self,
        fund_id: str = "DEFAULT",
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> List[ComplianceViolation]:
        """Convenience helper returning violations list directly."""
        result = await self.audit_fund(fund_id=fund_id, fund_data=fund_data, region=region)
        return result.violations

