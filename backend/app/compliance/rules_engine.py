# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
rules_engine.py
===============
Deterministic compliance rules engine that evaluates fund operations against
regulatory limits and produces violations with confidence, severity, and evidence.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.graph.client import GraphClient, get_graph_client

logger = logging.getLogger("compliance.rules_engine")


@dataclass
class CompiledRule:
    """Pre-compiled rule with parsed metric path and operator for fast evaluation."""
    id: str
    title: str
    description: str
    metric: str  # e.g. "holdings.max_single_holding"
    metric_parts: List[str]  # pre-split path: ["holdings", "max_single_holding"]
    operator: str  # e.g. "gt", "gte", "lt", etc.
    threshold: float
    severity: str
    confidence_threshold: float
    applicability: List[str]
    exclusions: List[str]
    enforcement_level: str
    regulation_id: str
    region: str


@dataclass
class ComplianceViolation:
    """Represents a detected compliance violation."""
    violation_id: str
    rule_id: str
    rule_title: str
    fund_id: str
    severity: str  # critical, high, medium, low
    confidence: float  # 0.0 - 1.0
    actual_value: Any
    threshold_value: Any
    description: str
    evidence_docs: List[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    region: str = "SEBI"
    status: str = "detected"  # detected, reviewed, remediated, closed
    resolved_at: Optional[str] = None
    resolution_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "rule_id": self.rule_id,
            "rule_title": self.rule_title,
            "fund_id": self.fund_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "actual_value": self.actual_value,
            "threshold_value": self.threshold_value,
            "description": self.description,
            "evidence_docs": self.evidence_docs,
            "detected_at": self.detected_at,
            "region": self.region,
            "status": self.status,
            "resolved_at": self.resolved_at,
            "resolution_action": self.resolution_action,
        }


class RulesEngine:
    """Deterministic compliance rules evaluator."""

    def __init__(self, graph_client: Optional[GraphClient] = None):
        self.graph = graph_client or get_graph_client()
        self._rule_cache: Dict[str, Dict[str, Any]] = {}
        self._compiled_rules: Dict[str, CompiledRule] = {}  # Pre-compiled rules for fast eval
        self._violations_cache: Dict[str, ComplianceViolation] = {}
        self._load_default_rules()

    def _compile_rule(self, rule_id: str, rule_data: Dict[str, Any]) -> Optional[CompiledRule]:
        """Pre-compile a rule: parse condition, split metric path, extract operator/threshold."""
        condition_str = rule_data.get("condition", "")
        if not condition_str:
            return None
        
        try:
            metric, op, threshold = self._parse_condition(condition_str)
            metric_parts = metric.split(".")  # Pre-split path for fast lookup
            
            # Convert threshold to float if numeric
            if isinstance(threshold, (int, float)):
                thresh_val = float(threshold)
            else:
                thresh_val = float(threshold) if threshold.replace(".", "", 1).isdigit() else threshold
            
            return CompiledRule(
                id=rule_id,
                title=rule_data.get("title", ""),
                description=rule_data.get("description", ""),
                metric=metric,
                metric_parts=metric_parts,
                operator=op,
                threshold=thresh_val,
                severity=rule_data.get("severity", "high"),
                confidence_threshold=float(rule_data.get("confidence_threshold", 0.95)),
                applicability=rule_data.get("applicability") or [],
                exclusions=rule_data.get("exclusions") or [],
                enforcement_level=rule_data.get("enforcement_level", "automatic"),
                regulation_id=rule_data.get("regulation_id", ""),
                region=rule_data.get("region", "SEBI"),
            )
        except Exception as exc:
            logger.warning("Failed to compile rule %s: %s", rule_id, exc)
            return None

    async def load_rules(self) -> int:
        """Load all active rules from Neo4j into cache, falling back gracefully if offline or empty."""
        cypher = """
        MATCH (r:Rule)
        WHERE r.active = true OR r.active IS NULL
        RETURN r.id AS id, r.rule_type AS rule_type, r.title AS title,
               r.description AS description, r.condition AS condition,
               r.severity AS severity, r.confidence_threshold AS confidence_threshold,
               r.applicability AS applicability, r.exclusions AS exclusions,
               r.enforcement_level AS enforcement_level, r.regulation_id AS regulation_id
        """
        try:
            results = await self.graph.run(cypher)
            if results:
                self._rule_cache = {}
                for row in results:
                    rule_id = row["id"]
                    self._rule_cache[rule_id] = {
                        "rule_type": row.get("rule_type", "portfolio"),
                        "title": row.get("title", ""),
                        "description": row.get("description", ""),
                        "condition": row.get("condition", ""),
                        "severity": row.get("severity", "high"),
                        "confidence_threshold": float(row.get("confidence_threshold", 0.95)),
                        "applicability": row.get("applicability") or [],
                        "exclusions": row.get("exclusions") or [],
                        "enforcement_level": row.get("enforcement_level", "automatic"),
                        "regulation_id": row.get("regulation_id", ""),
                    }
                    # Pre-compile rule for fast evaluation
                    compiled = self._compile_rule(rule_id, self._rule_cache[rule_id])
                    if compiled:
                        self._compiled_rules[rule_id] = compiled
                logger.info("Loaded %d compliance rules from Neo4j into memory", len(self._rule_cache))
            else:
                self._load_default_rules()
            return len(self._rule_cache)
        except Exception as exc:
            logger.warning("Could not load rules from Neo4j (%s); loading default rule fixtures", exc)
            self._load_default_rules()
            return len(self._rule_cache)


    def _load_default_rules(self) -> None:
        """Fallback built-in rules for offline execution / local testing."""
        self._rule_cache = {
            "RULE_PORT_CONC_001": {
                "rule_type": "portfolio",
                "title": "Single Holding Concentration",
                "description": "Maximum 15% NAV in single security",
                "condition": "holdings.max_single_holding > 0.15",
                "severity": "high",
                "confidence_threshold": 0.95,
                "applicability": ["equity_fund", "balanced_fund"],
                "exclusions": ["sector_fund"],
                "enforcement_level": "automatic",
                "regulation_id": "SEBI_MF_2024_Q1_001",
                "region": "SEBI",
            },
            "RULE_PORT_SECTOR_001": {
                "rule_type": "portfolio",
                "title": "Sector Concentration Limit",
                "description": "Maximum 30% in single sector",
                "condition": "holdings.max_sector_holding > 0.30",
                "severity": "medium",
                "confidence_threshold": 0.85,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund"],
                "exclusions": ["sector_fund"],
                "enforcement_level": "automatic",
                "regulation_id": "SEBI_MF_2024_Q1_006",
                "region": "SEBI",
            },
            "RULE_PORT_RELATED_001": {
                "rule_type": "portfolio",
                "title": "Sponsor Group Exposure Limit",
                "description": "Maximum 10% in sponsor group companies",
                "condition": "holdings.sponsor_group_exposure > 0.10",
                "severity": "critical",
                "confidence_threshold": 0.99,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund", "sector_fund"],
                "exclusions": [],
                "enforcement_level": "escalation",
                "regulation_id": "SEBI_MF_2024_Q1_008",
                "region": "SEBI",
            },
            "RULE_GOV_MGR_CERT_001": {
                "rule_type": "governance",
                "title": "Fund Manager Certification",
                "description": "Manager must hold active CAIA/CFA certification",
                "condition": "manager_certified != 1",
                "severity": "high",
                "confidence_threshold": 0.99,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund", "sector_fund"],
                "exclusions": [],
                "enforcement_level": "automatic",
                "regulation_id": "SEBI_MF_2024_Q1_002",
                "region": "SEBI",
            },
            "RULE_GOV_BOARD_IND_001": {
                "rule_type": "governance",
                "title": "Board Independence Ratio",
                "description": "At least 50% independent trustees required",
                "condition": "independent_trustee_pct < 0.50",
                "severity": "high",
                "confidence_threshold": 0.95,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund", "sector_fund"],
                "exclusions": [],
                "enforcement_level": "escalation",
                "regulation_id": "SEBI_MF_2024_Q1_002",
                "region": "SEBI",
            },
            "RULE_KYC_RECENCY_001": {
                "rule_type": "kyc",
                "title": "KYC Record Freshness",
                "description": "Investor KYC records must be updated within 365 days",
                "condition": "kyc_days_old > 365",
                "severity": "medium",
                "confidence_threshold": 0.90,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund", "sector_fund"],
                "exclusions": [],
                "enforcement_level": "automatic",
                "regulation_id": "SEBI_MF_2024_Q1_003",
                "region": "SEBI",
            },
            "RULE_KYC_PEP_001": {
                "rule_type": "kyc",
                "title": "Politically Exposed Person EDD",
                "description": "Unverified PEP accounts require Enhanced Due Diligence",
                "condition": "unverified_pep_accounts > 0",
                "severity": "critical",
                "confidence_threshold": 0.98,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund", "sector_fund"],
                "exclusions": [],
                "enforcement_level": "escalation",
                "regulation_id": "SEBI_MF_2024_Q1_003",
                "region": "SEBI",
            },
            "RULE_RISK_LIQUID_001": {
                "rule_type": "risk",
                "title": "Mandatory Liquid Cash Buffer",
                "description": "Open-ended schemes must keep at least 5% liquid cash",
                "condition": "cash_buffer_pct < 0.05",
                "severity": "high",
                "confidence_threshold": 0.95,
                "applicability": ["equity_fund", "balanced_fund"],
                "exclusions": ["close_ended"],
                "enforcement_level": "automatic",
                "regulation_id": "SEBI_MF_2024_Q1_004",
                "region": "SEBI",
            },
            "RULE_RISK_VAR_001": {
                "rule_type": "risk",
                "title": "Daily Value at Risk Limit",
                "description": "99% 1-day VaR must not exceed 4% of portfolio NAV",
                "condition": "daily_var_99 > 0.04",
                "severity": "critical",
                "confidence_threshold": 0.95,
                "applicability": ["equity_fund", "sector_fund"],
                "exclusions": [],
                "enforcement_level": "escalation",
                "regulation_id": "SEBI_MF_2024_Q1_007",
                "region": "SEBI",
            },
            "RULE_REP_NAV_TIME_001": {
                "rule_type": "reporting",
                "title": "Daily NAV Upload Cutoff",
                "description": "NAV must be published by 21:00 IST cutoff",
                "condition": "nav_upload_delay_minutes > 0",
                "severity": "medium",
                "confidence_threshold": 0.90,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund", "sector_fund"],
                "exclusions": [],
                "enforcement_level": "automatic",
                "regulation_id": "SEBI_MF_2024_Q1_005",
                "region": "SEBI",
            },
            # SEC Rule Fixtures
            "RULE_SEC_PORT_CONC_001": {
                "rule_type": "portfolio",
                "title": "SEC 5% Single Holding Cap",
                "description": "Maximum 5% total assets in single security",
                "condition": "holdings.max_single_holding > 0.05",
                "severity": "critical",
                "confidence_threshold": 0.98,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund"],
                "exclusions": [],
                "enforcement_level": "automatic",
                "regulation_id": "SEC_ICA_1940_001",
                "region": "SEC",
            },
            "RULE_SEC_PORT_SECTOR_001": {
                "rule_type": "portfolio",
                "title": "SEC 25% Sector Concentration Limit",
                "description": "Maximum 25% exposure in single industry",
                "condition": "holdings.max_sector_holding > 0.25",
                "severity": "high",
                "confidence_threshold": 0.95,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund"],
                "exclusions": [],
                "enforcement_level": "automatic",
                "regulation_id": "SEC_ICA_1940_002",
                "region": "SEC",
            },
            "RULE_SEC_GOV_BOARD_IND_001": {
                "rule_type": "governance",
                "title": "SEC Board Independence Threshold",
                "description": "Minimum 40% independent interested directors",
                "condition": "independent_trustee_pct < 0.40",
                "severity": "high",
                "confidence_threshold": 0.90,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund"],
                "exclusions": [],
                "enforcement_level": "escalation",
                "regulation_id": "SEC_ICA_1940_010",
                "region": "SEC",
            },
            "RULE_SEC_REP_NAV_001": {
                "rule_type": "reporting",
                "title": "SEC 4:00 PM Eastern NAV Cutoff",
                "description": "NAV pricing deadline 16:00 ET",
                "condition": "nav_upload_delay_minutes > 0",
                "severity": "critical",
                "confidence_threshold": 0.99,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund"],
                "exclusions": [],
                "enforcement_level": "automatic",
                "regulation_id": "SEC_ICA_1940_041",
                "region": "SEC",
            },
            # ESMA Rule Fixtures
            "RULE_ESMA_PORT_CONC_001": {
                "rule_type": "portfolio",
                "title": "ESMA 10% UCITS Concentration Cap",
                "description": "Max 10% in securities of single issuer (5/10/40 rule)",
                "condition": "holdings.max_single_holding > 0.10",
                "severity": "critical",
                "confidence_threshold": 0.98,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund"],
                "exclusions": [],
                "enforcement_level": "automatic",
                "regulation_id": "ESMA_UCITS_2024_001",
                "region": "ESMA",
            },
            "RULE_ESMA_RISK_LIQUID_001": {
                "rule_type": "risk",
                "title": "ESMA 80% 5-Day Liquidity Buffer",
                "description": "Minimum 80% assets tradable within 5 business days",
                "condition": "tradable_5_day_liquidity_pct < 0.80",
                "severity": "critical",
                "confidence_threshold": 0.95,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund"],
                "exclusions": [],
                "enforcement_level": "automatic",
                "regulation_id": "ESMA_UCITS_2024_026",
                "region": "ESMA",
            },
            "RULE_ESMA_REP_SFDR_ESG_001": {
                "rule_type": "reporting",
                "title": "ESMA SFDR Article 8/9 Disclosure",
                "description": "100% sustainability indicators disclosed quarterly",
                "condition": "sfdr_esg_disclosure_pct < 1.0",
                "severity": "critical",
                "confidence_threshold": 0.95,
                "applicability": ["equity_fund", "debt_fund", "balanced_fund"],
                "exclusions": [],
                "enforcement_level": "automatic",
                "regulation_id": "ESMA_UCITS_2024_076",
                "region": "ESMA",
            },
        }
        # Pre-compile all default rules
        self._compiled_rules = {}
        for rule_id, rule_data in self._rule_cache.items():
            compiled = self._compile_rule(rule_id, rule_data)
            if compiled:
                self._compiled_rules[rule_id] = compiled

    async def get_applicable_rules(
        self,
        rule_type: Optional[str] = None,
        region: str = "SEBI"
    ) -> List[Dict[str, Any]]:
        """Get rules filtered by domain and regulatory region."""
        if not self._rule_cache:
            await self.load_rules()

        cypher = """
        MATCH (r:Rule)
        WHERE (r.active = true OR r.active IS NULL)
          AND ($rule_type IS NULL OR r.rule_type = $rule_type)
          AND ($region = 'ALL' OR r.region = $region)
        RETURN r.id AS id, r.rule_type AS rule_type, r.title AS title,
               r.description AS description, r.condition AS condition,
               r.severity AS severity, r.confidence_threshold AS confidence_threshold,
               r.region AS region
        """
        try:
            results = await self.graph.run(cypher, rule_type=rule_type, region=region)
            if results:
                return [dict(row) for row in results]
        except Exception:
            pass

        # Fallback in-memory cache lookup
        filtered = []
        for rid, rdata in self._rule_cache.items():
            r_region = rdata.get("region", "SEBI")
            r_type = rdata.get("rule_type")

            if region != "ALL" and r_region != region:
                continue
            if rule_type and r_type != rule_type:
                continue

            entry = dict(rdata)
            entry["id"] = rid
            filtered.append(entry)

        return filtered



    def _parse_condition(self, condition_str: str) -> Tuple[str, str, Any]:
        """
        Parse condition string: e.g. "holding_pct > 0.15" or "manager_certified != 1".
        Returns: (metric_name, operator_key, threshold_value)
        """
        match = re.match(r'([\w\.]+)\s*(>=|<=|>|<|==|!=|=)\s*([a-zA-Z0-9_\.\-]+)', condition_str.strip())
        if match:
            metric, raw_op, val_str = match.groups()
            op_map = {
                ">": "gt", ">=": "gte", "<": "lt", "<=": "lte",
                "==": "eq", "=": "eq", "!=": "neq"
            }
            op = op_map.get(raw_op, "eq")

            # Parse threshold value type
            if val_str.lower() in ("true", "1"):
                threshold = 1
            elif val_str.lower() in ("false", "0"):
                threshold = 0
            else:
                try:
                    threshold = float(val_str)
                except ValueError:
                    threshold = val_str

            return metric, op, threshold

        raise ValueError(f"Invalid condition format: '{condition_str}'")

    def _get_metric_value(self, fund_data: Dict[str, Any], metric_parts: List[str]) -> Any:
        """Extract nested metric value from fund data dictionary using pre-split path."""
        curr = fund_data
        for part in metric_parts:
            if isinstance(curr, dict):
                curr = curr.get(part)
            else:
                return None
        
        # Normalize boolean to int for numeric equality/inequality
        if isinstance(curr, bool):
            return 1 if curr else 0
        return curr

    def _compare(self, actual: Any, operator: str, threshold: Any) -> bool:
        """Direct comparison without lambda dispatch (faster than dict lookup + call)."""
        # Type conversion for numeric comparison
        if isinstance(threshold, (int, float)) and isinstance(actual, (int, float)):
            actual = float(actual)
            threshold = float(threshold)
        
        if operator == "gt":
            return actual > threshold
        elif operator == "gte":
            return actual >= threshold
        elif operator == "lt":
            return actual < threshold
        elif operator == "lte":
            return actual <= threshold
        elif operator == "eq":
            return actual == threshold
        elif operator == "neq":
            return actual != threshold
        return False

    async def evaluate_rule(
        self,
        rule_id: str,
        fund_data: Dict[str, Any]
    ) -> Optional[ComplianceViolation]:
        """
        Evaluate a single compliance rule against fund data using pre-compiled rule.
        Returns ComplianceViolation if violated, otherwise None.
        """
        # Use compiled rule if available (faster path)
        compiled = self._compiled_rules.get(rule_id)
        if not compiled:
            return None

        category = fund_data.get("category", "")

        # 1. Applicability Check
        if compiled.applicability and category and category not in compiled.applicability:
            return None

        # 2. Exclusion Check
        if compiled.exclusions and category and category in compiled.exclusions:
            return None

        try:
            # Use pre-split metric path for fast lookup
            actual_value = self._get_metric_value(fund_data, compiled.metric_parts)

            if actual_value is None:
                logger.debug(
                    "Metric '%s' not present in fund data for '%s'; skipping rule %s",
                    compiled.metric, fund_data.get("fund_id"), rule_id
                )
                return None

            # Direct comparison (no lambda dispatch)
            is_violated = self._compare(actual_value, compiled.operator, compiled.threshold)

            if is_violated:
                now_str = datetime.now().isoformat()
                v_id = f"V_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{rule_id}"
                desc = (
                    f"{compiled.title} breached: "
                    f"{compiled.metric} was {actual_value} (limit: {compiled.threshold})"
                )
                evidence = fund_data.get("evidence_docs") or ["Portfolio_Holdings.json"]

                violation = ComplianceViolation(
                    violation_id=v_id,
                    rule_id=rule_id,
                    rule_title=compiled.title,
                    fund_id=fund_data.get("fund_id", "UNKNOWN"),
                    severity=compiled.severity,
                    confidence=compiled.confidence_threshold,
                    actual_value=actual_value,
                    threshold_value=compiled.threshold,
                    description=desc,
                    evidence_docs=evidence,
                    detected_at=now_str,
                    region=fund_data.get("region", "SEBI"),
                    status="detected",
                )
                return violation

        except Exception as exc:
            logger.error("Error evaluating rule %s against fund %s: %s", rule_id, fund_data.get("fund_id"), exc)

        return None

    async def evaluate_fund(
        self,
        fund_id: str,
        fund_data: Dict[str, Any]
    ) -> List[ComplianceViolation]:
        """Evaluate all applicable rules for a given fund."""
        if not self._rule_cache:
            await self.load_rules()

        applicable_rule_ids = []
        cypher = """
        MATCH (f:FundScheme {id: $fund_id})-[:governedBy]->(r:Rule)
        WHERE r.active = true OR r.active IS NULL
        RETURN r.id AS id
        """
        try:
            results = await self.graph.run(cypher, fund_id=fund_id)
            applicable_rule_ids = [row["id"] for row in results if row.get("id")]
        except Exception:
            applicable_rule_ids = list(self._rule_cache.keys())

        if not applicable_rule_ids:
            applicable_rule_ids = list(self._rule_cache.keys())

        violations = []
        for rid in applicable_rule_ids:
            v = await self.evaluate_rule(rid, fund_data)
            if v:
                violations.append(v)
                self._violations_cache[v.violation_id] = v

        return violations

    async def store_violations(self, violations: List[ComplianceViolation]) -> int:
        """Persist violations to Neo4j and cache in memory."""
        stored_count = 0
        for v in violations:
            self._violations_cache[v.violation_id] = v
            try:
                cypher = """
                MERGE (v:Violation {id: $violation_id})
                SET v.rule_id = $rule_id,
                    v.fund_id = $fund_id,
                    v.severity = $severity,
                    v.confidence = toFloat($confidence),
                    v.actual_value = $actual_value,
                    v.threshold_value = $threshold_value,
                    v.description = $description,
                    v.detected_at = $detected_at,
                    v.region = $region,
                    v.status = $status
                WITH v
                OPTIONAL MATCH (r:Rule {id: $rule_id})
                FOREACH (_ IN CASE WHEN r IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (v)-[:violates]->(r)
                )
                WITH v
                OPTIONAL MATCH (f:FundScheme {id: $fund_id})
                FOREACH (_ IN CASE WHEN f IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (v)-[:affects]->(f)
                )
                RETURN v.id AS id
                """
                await self.graph.run(
                    cypher,
                    violation_id=v.violation_id,
                    rule_id=v.rule_id,
                    fund_id=v.fund_id,
                    severity=v.severity,
                    confidence=v.confidence,
                    actual_value=str(v.actual_value),
                    threshold_value=str(v.threshold_value),
                    description=v.description,
                    detected_at=v.detected_at,
                    region=v.region,
                    status=v.status,
                )
                stored_count += 1
            except Exception as exc:
                logger.debug("Neo4j offline; stored violation in memory cache (%s)", exc)
                stored_count += 1

        return stored_count

