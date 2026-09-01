# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
kyc_agent.py
============
Autonomous compliance auditing agent for Investor KYC, PEP Screening, and
Enhanced Due Diligence (EDD) verification.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.compliance.rules_engine import ComplianceViolation, RulesEngine
from app.graph.client import GraphClient, get_graph_client

logger = logging.getLogger("compliance.agents.kyc")


@dataclass
class KYCAuditResult:
    fund_id: str
    fund_name: str
    agent_type: str = "kyc"
    audit_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    violations: List[ComplianceViolation] = field(default_factory=list)
    checks_performed: List[str] = field(default_factory=list)
    compliance_status: str = "compliant"
    summary: Dict[str, Any] = field(default_factory=dict)


class KYCAgent:
    """Audits investor KYC records and AML/PEP screening standards."""

    def __init__(
        self,
        graph_client: Optional[GraphClient] = None,
        rules_engine: Optional[RulesEngine] = None
    ):
        self.graph = graph_client or get_graph_client()
        self.rules_engine = rules_engine or RulesEngine(self.graph)
        self.agent_type = "kyc"

    async def audit_fund(
        self,
        fund_id: str,
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> KYCAuditResult:
        if fund_data is not None:
            fund_data = dict(fund_data)
            reg = region if region != "SEBI" else (fund_data.get("region") or region)
        else:
            reg = region
        logger.info("[KYCAgent] Starting KYC audit for %s (region=%s)", fund_id, reg)
        if not self.rules_engine._rule_cache:
            await self.rules_engine.load_rules()

        if fund_data is None:
            fund_data = {
                "fund_id": fund_id,
                "fund_name": fund_id.replace("_", " "),
                "category": "equity_fund",
                "region": reg,
                "kyc_days_old": 180,
                "unverified_pep_accounts": 0,
                "evidence_docs": ["KYC_AML_Audit_Summary_2024.pdf"],
            }
        else:
            fund_data["region"] = reg


        # Normalize kyc_records list if provided
        if "kyc_records" in fund_data and isinstance(fund_data["kyc_records"], list):
            max_days = 0
            unverified_pep = 0
            for rec in fund_data["kyc_records"]:
                updated = rec.get("kyc_updated_at")
                if updated:
                    try:
                        days = (datetime.now() - datetime.fromisoformat(updated[:10])).days
                        if days > max_days:
                            max_days = days
                    except Exception:
                        max_days = 400
                if str(rec.get("pep_status", "")).upper() in ("UNVERIFIED", "PENDING", "FAIL"):
                    unverified_pep += 1
            fund_data["kyc_days_old"] = max_days
            fund_data["unverified_pep_accounts"] = unverified_pep
            if "kyc" not in fund_data:
                fund_data["kyc"] = {}
            fund_data["kyc"]["days_since_update"] = max_days
            fund_data["kyc"]["unverified_pep_count"] = unverified_pep
        elif "kyc_last_updated" in fund_data:
            try:
                days = (datetime.now() - datetime.fromisoformat(fund_data["kyc_last_updated"][:10])).days
            except Exception:
                days = 400
            fund_data["kyc_days_old"] = days
            if "kyc" not in fund_data:
                fund_data["kyc"] = {}
            fund_data["kyc"]["days_since_update"] = days

        checks = [
            "KYC Record Freshness",
            "Politically Exposed Person (PEP) EDD Verification",
        ]

        applicable_rules = await self.rules_engine.get_applicable_rules(
            rule_type="kyc",
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
        return KYCAuditResult(
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

    async def audit_kyc(
        self,
        fund_id: str = "DEFAULT",
        fund_data: Optional[Dict[str, Any]] = None,
        region: str = "SEBI",
    ) -> List[ComplianceViolation]:
        """Convenience helper returning violations list directly."""
        result = await self.audit_fund(fund_id=fund_id, fund_data=fund_data, region=region)
        return result.violations

