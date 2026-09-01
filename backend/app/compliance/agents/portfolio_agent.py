# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
portfolio_agent.py
==================
Autonomous compliance auditing agent for Portfolio Concentration, Sector Limits,
and Related-Party Sponsor Holdings.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.compliance.rules_engine import ComplianceViolation, RulesEngine
from app.graph.client import GraphClient, get_graph_client

logger = logging.getLogger("compliance.agents.portfolio")


@dataclass
class PortfolioAuditResult:
    fund_id: str
    fund_name: str
    agent_type: str = "portfolio"
    audit_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    violations: List[ComplianceViolation] = field(default_factory=list)
    checks_performed: List[str] = field(default_factory=list)
    compliance_status: str = "compliant"
    summary: Dict[str, Any] = field(default_factory=dict)


class PortfolioAgent:
    """Audits fund portfolio allocations against statutory limits."""

    def __init__(
        self,
        graph_client: Optional[GraphClient] = None,
        rules_engine: Optional[RulesEngine] = None
    ):
        self.graph = graph_client or get_graph_client()
        self.rules_engine = rules_engine or RulesEngine(self.graph)
        self.agent_type = "portfolio"

    async def audit_fund(
        self,
        fund_id: str,
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> PortfolioAuditResult:
        if fund_data is not None:
            fund_data = dict(fund_data)
            reg = region if region != "SEBI" else (fund_data.get("region") or region)
        else:
            reg = region
        logger.info("[PortfolioAgent] Starting portfolio audit for %s (region=%s)", fund_id, reg)
        if not self.rules_engine._rule_cache:
            await self.rules_engine.load_rules()

        if fund_data is None:
            fund_data = {
                "fund_id": fund_id,
                "fund_name": fund_id.replace("_", " "),
                "category": "equity_fund",
                "region": reg,
                "holdings": {
                    "max_single_holding": 0.18,
                    "max_sector_holding": 0.34,
                    "sponsor_group_exposure": 0.12,
                },
                "evidence_docs": ["Portfolio_Holdings_2024.pdf"],
            }
        else:
            fund_data["region"] = reg


        # Normalize holdings if provided as list
        if "holdings" in fund_data and isinstance(fund_data["holdings"], list):
            max_holding = max((h.get("pct", 0) / 100.0 if h.get("pct", 0) > 1 else h.get("pct", 0) for h in fund_data["holdings"]), default=0)
            fund_data["holdings"] = {"max_single_holding": max_holding}
        if "sector_exposure" in fund_data and isinstance(fund_data["sector_exposure"], dict):
            max_sector = max((v / 100.0 if v > 1 else v for v in fund_data["sector_exposure"].values()), default=0)
            if isinstance(fund_data.get("holdings"), dict):
                fund_data["holdings"]["max_sector_holding"] = max_sector
            fund_data["sector_exposure"] = {"max_sector_pct": max_sector * 100.0 if max_sector <= 1.0 else max_sector}

        checks = [
            "Single Security Concentration",
            "Sector Concentration Limit",
            "Sponsor Group Related-Party Exposure",
        ]

        applicable_rules = await self.rules_engine.get_applicable_rules(
            rule_type="portfolio",
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
        return PortfolioAuditResult(
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

    async def audit_portfolio(
        self,
        fund_id: str = "DEFAULT",
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> List[ComplianceViolation]:
        """Convenience helper returning violations list directly."""
        result = await self.audit_fund(fund_id=fund_id, fund_data=fund_data, region=region)
        return result.violations

