# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
reporting_agent.py
==================
Autonomous compliance auditing agent for Regulatory Disclosures, NAV Upload Timeliness,
and Portfolio Publication Deadlines.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.compliance.rules_engine import ComplianceViolation, RulesEngine
from app.graph.client import GraphClient, get_graph_client

logger = logging.getLogger("compliance.agents.reporting")


@dataclass
class ReportingAuditResult:
    fund_id: str
    fund_name: str
    agent_type: str = "reporting"
    audit_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    violations: List[ComplianceViolation] = field(default_factory=list)
    checks_performed: List[str] = field(default_factory=list)
    compliance_status: str = "compliant"
    summary: Dict[str, Any] = field(default_factory=dict)


class ReportingAgent:
    """Audits NAV upload timeliness and mandatory regulatory disclosure filings."""

    def __init__(
        self,
        graph_client: Optional[GraphClient] = None,
        rules_engine: Optional[RulesEngine] = None
    ):
        self.graph = graph_client or get_graph_client()
        self.rules_engine = rules_engine or RulesEngine(self.graph)
        self.agent_type = "reporting"

    async def audit_fund(
        self,
        fund_id: str,
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> ReportingAuditResult:
        if fund_data is not None:
            fund_data = dict(fund_data)
            reg = region if region != "SEBI" else (fund_data.get("region") or region)
        else:
            reg = region
        logger.info("[ReportingAgent] Starting reporting audit for %s (region=%s)", fund_id, reg)
        if not self.rules_engine._rule_cache:
            await self.rules_engine.load_rules()

        if fund_data is None:
            fund_data = {
                "fund_id": fund_id,
                "fund_name": fund_id.replace("_", " "),
                "category": "equity_fund",
                "region": reg,
                "nav_upload_delay_minutes": 0,
                "monthly_disclosure_days_late": 0,
                "evidence_docs": ["AMFI_Daily_NAV_Feed_Log.json"],
            }
        else:
            fund_data["region"] = reg


        # Normalize NAV publication time if provided as string
        if "nav_last_published" in fund_data:
            nav_time_str = str(fund_data["nav_last_published"])
            try:
                # E.g. "2024-01-25 21:15:00"
                if len(nav_time_str) >= 16:
                    hour = int(nav_time_str[11:13])
                    minute = int(nav_time_str[14:16])
                    if reg == "SEC":
                        # SEC 16:00 ET cutoff
                        delay = max(0, (hour - 16) * 60 + minute)
                        if "reporting" not in fund_data:
                            fund_data["reporting"] = {}
                        fund_data["reporting"]["nav_upload_hour_et"] = hour + (minute / 60.0)
                    else:
                        # SEBI 21:00 IST cutoff
                        delay = max(0, (hour - 21) * 60 + minute)
                        if "reporting" not in fund_data:
                            fund_data["reporting"] = {}
                        fund_data["reporting"]["nav_upload_hour_ist"] = hour + (minute / 60.0)
                    fund_data["nav_upload_delay_minutes"] = delay
            except Exception:
                fund_data["nav_upload_delay_minutes"] = 15

        if "filing_deadline_days" in fund_data:
            days = fund_data["filing_deadline_days"]
            if days < 0:
                fund_data["monthly_disclosure_days_late"] = abs(days)

        checks = [
            "Daily NAV Upload Cutoff",
            "Monthly Portfolio Disclosure Timeliness",
        ]

        applicable_rules = await self.rules_engine.get_applicable_rules(
            rule_type="reporting",
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
        return ReportingAuditResult(
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

    async def audit_reporting(
        self,
        fund_id: str = "DEFAULT",
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> List[ComplianceViolation]:
        """Convenience helper returning violations list directly."""
        result = await self.audit_fund(fund_id=fund_id, fund_data=fund_data, region=region)
        return result.violations

