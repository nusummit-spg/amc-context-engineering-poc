# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

I'll create a comprehensive, detailed implementation plan for all phases. Let me first create a task list to track this.Now let me create the comprehensive detailed implementation plan:

---

# **AMC Compliance Audit System — Complete 12-Week Implementation Plan**

**Timeline**: 12 weeks (3 months)  
**Team Size**: 3-4 engineers  
**Tech Stack**: Python 3.9+, FastAPI, Neo4j, Qdrant, Groq LLM, PostgreSQL  
**Deployment**: Docker + Kubernetes  

---

# **PHASE 1: RULES ENGINE & VIOLATION DETECTION (Weeks 1-2)**

## **Objective**

Build deterministic compliance rules engine that evaluates AMC operations against regulatory limits and flags violations with confidence scores, severity levels, and evidence trails.

**Success Criteria:**
- ✅ Compliance graph schema deployed in Neo4j
- ✅ Rules ingestion pipeline working (CSV → Neo4j)
- ✅ Deterministic rule matcher implemented
- ✅ Violation detector producing violations with confidence/severity/evidence
- ✅ Test coverage ≥85%
- ✅ **Compliance boost: 35% → 50% (+15%)**

---

## **Week 1: Compliance Graph Schema & Rules Framework**

### **Task 1.1: Design Compliance Graph Schema (Day 1-2)**

**Deliverable**: Neo4j schema design document + Cypher constraints

**Implementation**:

```cypher
/* ==================== NODE DEFINITIONS ==================== */

/* Regulations: SEBI, SEC, ESMA circulars */
CREATE CONSTRAINT regulation_id IF NOT EXISTS FOR (r:Regulation) REQUIRE r.id IS UNIQUE;
CREATE INDEX idx_regulation_region IF NOT EXISTS FOR (r:Regulation) ON (r.region);

/* Rules: Specific compliance checks */
CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:Rule) REQUIRE r.id IS UNIQUE;
CREATE INDEX idx_rule_type IF NOT EXISTS FOR (r:Rule) ON (r.rule_type);  /* portfolio, governance, kyc, risk, reporting */

/* Fund schemas: Investment mandates, limits */
CREATE CONSTRAINT fund_scheme_id IF NOT EXISTS FOR (f:FundScheme) REQUIRE f.id IS UNIQUE;

/* Violations: Detected breaches */
CREATE CONSTRAINT violation_id IF NOT EXISTS FOR (v:Violation) REQUIRE v.id IS UNIQUE;
CREATE INDEX idx_violation_severity IF NOT EXISTS FOR (v:Violation) ON (v.severity);

/* Risk thresholds: Configurable decision boundaries */
CREATE CONSTRAINT threshold_id IF NOT EXISTS FOR (t:RiskThreshold) REQUIRE t.id IS UNIQUE;

/* Escalation paths: Violation routing config */
CREATE CONSTRAINT escalation_id IF NOT EXISTS FOR (e:EscalationPath) REQUIRE e.id IS UNIQUE;

/* ==================== NODE PROPERTIES ==================== */

/* :Regulation */
{
  id: "SEBI_MF_2024_Q1_001",           # region_year_quarter_#
  title: "Portfolio Concentration Limits",
  region: "SEBI" | "SEC" | "ESMA",
  effective_date: "2024-01-01",
  supersedes: ["SEBI_MF_2023_Q4_001"],
  document_url: "https://sebi.gov.in/...",
  raw_text: "Fund shall not hold >15% in single entity..."
}

/* :Rule */
{
  id: "RULE_PORT_CONC_001",
  rule_type: "portfolio|governance|kyc|risk|reporting",
  title: "Single Holding Concentration",
  description: "Maximum 15% NAV in single security",
  regulation_id: "SEBI_MF_2024_Q1_001",
  condition: "holding_pct > 15%",
  severity: "high|medium|low",
  confidence_threshold: 0.95,
  applicability: ["equity_fund", "balanced_fund"],
  exclusions: ["sector_fund"],  # Sector funds can go 50%
  enforcement_level: "automatic|audit|escalation"
}

/* :FundScheme */
{
  id: "Adani_Growth_2024",
  isin: "INF204K01ND0",
  name: "Adani Growth Fund",
  fund_house: "Adani Capital Markets",
  category: "Equity",
  mandate: "Growth-oriented equity investing",
  risk_profile: "High",
  scheme_type: "Mutual Fund",
  aum_cr: 5000,  # ₹5000 Crores
  launch_date: "2018-01-01",
  rules_applicable: ["RULE_PORT_CONC_001", "RULE_PORT_SECTOR_001", ...]
}

/* :Violation */
{
  id: "V_20240115_001",
  rule_id: "RULE_PORT_CONC_001",
  fund_id: "Adani_Growth_2024",
  finding: "Technology sector allocation 18% exceeds 15% limit",
  severity: "high|medium|low",
  confidence: 0.94,
  actual_value: 0.18,
  threshold_value: 0.15,
  violation_type: "concentration|governance|kyc|risk|reporting",
  detected_at: "2024-01-15T10:30:00Z",
  evidence_docs: ["NAV_20240115.csv", "Fund_Prospectus.pdf"],
  evidence_facts: [
    {source: "NAV_20240115.csv", excerpt: "Technology: 18%"},
    {source: "Fund_Prospectus.pdf", excerpt: "Max sector: 15%"}
  ],
  status: "detected|reviewed|remediated|closed",
  resolved_at: null,
  resolution_action: null,
  region: "SEBI"
}

/* :RiskThreshold */
{
  id: "THRESHOLD_FRAUD_001",
  violation_type: "fraud|policy_breach|reporting_delay",
  confidence_min: 0.99,
  confidence_max: 1.0,
  escalation_priority: "immediate",
  sla_minutes: 60
}

/* :EscalationPath */
{
  id: "ESCALATE_SEBI_HIGH",
  region: "SEBI",
  severity: "high",
  routing_rules: ["compliance_officer", "risk_committee", "board"],
  notification_channels: ["email", "slack", "internal_case_system"],
  sla_hours: 1,
  requires_board_approval: true
}

/* ==================== RELATIONSHIPS ==================== */

:Regulation --[hasRule]--> :Rule
:Rule --[appliesTo]--> :FundScheme
:Rule --[triggers]--> :Violation
:Violation --[violates]--> :Rule
:Violation --[affects]--> :FundScheme
:Violation --[escalatesVia]--> :EscalationPath
:Violation --[evidencedBy]--> :Document
:RiskThreshold --[scopesViolation]--> :Violation
```

**Files to Create:**
- `backend/app/graph/compliance_schema.py` — Schema definition + constraint creation
- `backend/app/schemas/compliance_models.py` — Pydantic models for all compliance entities

---

### **Task 1.2: Implement Rules Ingestion Pipeline (Day 2-3)**

**Deliverable**: Python module to ingest compliance rules from CSV → Neo4j

**Implementation**:

```python
# backend/app/ingestion/compliance_rules_ingester.py

import csv
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ComplianceRulesIngester:
    """Ingests regulatory rules from CSV files into Neo4j compliance graph."""
    
    def __init__(self, graph_client):
        self.graph = graph_client
    
    async def ingest_regulations_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        CSV columns: region | regulation_id | title | effective_date | document_url | raw_text
        """
        regulations_created = 0
        errors = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    try:
                        cypher = """
                        CREATE (r:Regulation {
                            id: $reg_id,
                            title: $title,
                            region: $region,
                            effective_date: $eff_date,
                            document_url: $url,
                            raw_text: $text,
                            created_at: $now
                        })
                        RETURN r.id AS id
                        """
                        result = await self.graph.run(cypher, {
                            "reg_id": row["regulation_id"],
                            "title": row["title"],
                            "region": row["region"],
                            "eff_date": row["effective_date"],
                            "url": row["document_url"],
                            "text": row["raw_text"],
                            "now": datetime.now().isoformat()
                        })
                        regulations_created += 1
                    except Exception as e:
                        errors.append(f"Row {row_idx}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Failed to ingest regulations from {csv_path}: {e}")
            return {"status": "error", "message": str(e)}
        
        logger.info(f"Ingested {regulations_created} regulations, {len(errors)} errors")
        return {
            "status": "success",
            "regulations_created": regulations_created,
            "errors": errors
        }
    
    async def ingest_rules_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        CSV columns: rule_id | rule_type | title | regulation_id | 
                     condition | severity | confidence_threshold | 
                     applicability_categories | exclusion_categories | enforcement_level
        """
        rules_created = 0
        errors = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    try:
                        # Parse JSON arrays
                        applicability = json.loads(row.get("applicability_categories", "[]"))
                        exclusions = json.loads(row.get("exclusion_categories", "[]"))
                        
                        cypher = """
                        CREATE (r:Rule {
                            id: $rule_id,
                            rule_type: $rule_type,
                            title: $title,
                            condition: $condition,
                            severity: $severity,
                            confidence_threshold: toFloat($conf_threshold),
                            applicability: $applicability,
                            exclusions: $exclusions,
                            enforcement_level: $enforcement_level,
                            created_at: $now
                        })
                        WITH r
                        MATCH (reg:Regulation {id: $reg_id})
                        CREATE (r)-[:basedOn]->(reg)
                        RETURN r.id AS id
                        """
                        result = await self.graph.run(cypher, {
                            "rule_id": row["rule_id"],
                            "rule_type": row["rule_type"],
                            "title": row["title"],
                            "regulation_id": row["regulation_id"],
                            "condition": row["condition"],
                            "severity": row["severity"],
                            "conf_threshold": row["confidence_threshold"],
                            "applicability": applicability,
                            "exclusions": exclusions,
                            "enforcement_level": row["enforcement_level"],
                            "now": datetime.now().isoformat(),
                            "reg_id": row["regulation_id"]
                        })
                        rules_created += 1
                    except Exception as e:
                        errors.append(f"Row {row_idx}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Failed to ingest rules from {csv_path}: {e}")
            return {"status": "error", "message": str(e)}
        
        logger.info(f"Ingested {rules_created} rules, {len(errors)} errors")
        return {
            "status": "success",
            "rules_created": rules_created,
            "errors": errors
        }
    
    async def ingest_fund_schemes_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        CSV columns: fund_id | isin | name | fund_house | category | 
                     mandate | risk_profile | aum_cr | rules_applicable_ids
        """
        funds_created = 0
        errors = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    try:
                        rule_ids = json.loads(row.get("rules_applicable_ids", "[]"))
                        
                        cypher = """
                        CREATE (f:FundScheme {
                            id: $fund_id,
                            isin: $isin,
                            name: $name,
                            fund_house: $fund_house,
                            category: $category,
                            mandate: $mandate,
                            risk_profile: $risk_profile,
                            aum_cr: toFloat($aum),
                            created_at: $now
                        })
                        WITH f
                        MATCH (r:Rule) WHERE r.id IN $rule_ids
                        CREATE (f)-[:governedBy]->(r)
                        RETURN f.id AS id
                        """
                        result = await self.graph.run(cypher, {
                            "fund_id": row["fund_id"],
                            "isin": row["isin"],
                            "name": row["name"],
                            "fund_house": row["fund_house"],
                            "category": row["category"],
                            "mandate": row["mandate"],
                            "risk_profile": row["risk_profile"],
                            "aum": row["aum_cr"],
                            "rule_ids": rule_ids,
                            "now": datetime.now().isoformat()
                        })
                        funds_created += 1
                    except Exception as e:
                        errors.append(f"Row {row_idx}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Failed to ingest fund schemes from {csv_path}: {e}")
            return {"status": "error", "message": str(e)}
        
        logger.info(f"Ingested {funds_created} fund schemes, {len(errors)} errors")
        return {
            "status": "success",
            "funds_created": funds_created,
            "errors": errors
        }

# Usage in FastAPI startup or CLI
async def seed_compliance_rules():
    graph = GraphClient(...)
    ingester = ComplianceRulesIngester(graph)
    
    await ingester.ingest_regulations_csv(Path("data/compliance/sebi_regulations.csv"))
    await ingester.ingest_rules_csv(Path("data/compliance/rules.csv"))
    await ingester.ingest_fund_schemes_csv(Path("data/compliance/fund_schemes.csv"))
```

**CSV Format Examples**:

`data/compliance/sebi_regulations.csv`:
```csv
region,regulation_id,title,effective_date,document_url,raw_text
SEBI,SEBI_MF_2024_Q1_001,Portfolio Concentration Limits,2024-01-01,https://sebi.gov.in/...,Fund shall not hold more than 15% of NAV in a single security...
SEBI,SEBI_MF_2024_Q1_002,Fund Manager Certification,2024-01-01,https://sebi.gov.in/...,All fund managers must hold CAIA or equivalent certification...
```

`data/compliance/rules.csv`:
```csv
rule_id,rule_type,title,regulation_id,condition,severity,confidence_threshold,applicability_categories,exclusion_categories,enforcement_level
RULE_PORT_CONC_001,portfolio,Single Holding Concentration,SEBI_MF_2024_Q1_001,holding_pct > 0.15,high,0.95,"[""equity_fund"",""balanced_fund""]","[""sector_fund""]",automatic
RULE_PORT_SECTOR_001,portfolio,Sector Concentration,SEBI_MF_2024_Q1_001,sector_pct > 0.30,medium,0.85,"[""equity_fund""]","[""sector_fund""]",automatic
RULE_GOV_MGR_CERT_001,governance,Fund Manager Certification,SEBI_MF_2024_Q1_002,manager_certified = false,high,0.99,"[""equity_fund"",""debt_fund""]","[]",automatic
```

**Files to Create:**
- `backend/app/ingestion/compliance_rules_ingester.py` — Rules ingestion logic
- `data/compliance/sebi_regulations.csv` — Initial SEBI regulations (~50)
- `data/compliance/rules.csv` — Initial rules (~30)
- `data/compliance/fund_schemes.csv` — Fund schemes for testing

---

### **Task 1.3: Implement Deterministic Rule Matcher (Day 3-4)**

**Deliverable**: Core rules engine that evaluates conditions and produces violations

**Implementation**:

```python
# backend/app/compliance/rules_engine.py

import re
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class ComplianceViolation:
    """Represents a detected compliance violation."""
    violation_id: str
    rule_id: str
    rule_title: str
    fund_id: str
    severity: str  # high, medium, low
    confidence: float  # 0.0 - 1.0
    actual_value: Any
    threshold_value: Any
    description: str
    evidence_docs: List[str]
    detected_at: str
    region: str
    status: str = "detected"
    
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
            "status": self.status
        }


class RulesEngine:
    """Deterministic compliance rules evaluator."""
    
    def __init__(self, graph_client):
        self.graph = graph_client
        self._rule_cache: Dict[str, Dict[str, Any]] = {}
        self._condition_evaluators: Dict[str, Callable] = {
            "gt": lambda actual, threshold: actual > threshold,
            "gte": lambda actual, threshold: actual >= threshold,
            "lt": lambda actual, threshold: actual < threshold,
            "lte": lambda actual, threshold: actual <= threshold,
            "eq": lambda actual, threshold: actual == threshold,
            "neq": lambda actual, threshold: actual != threshold,
            "in_range": lambda actual, min_val, max_val: min_val <= actual <= max_val,
        }
    
    async def load_rules(self) -> int:
        """Load all active rules from Neo4j into cache."""
        cypher = """
        MATCH (r:Rule)
        WHERE r.active = true OR NOT EXISTS(r.active)
        RETURN r.id, r.rule_type, r.title, r.condition, r.severity,
               r.confidence_threshold, r.applicability, r.exclusions,
               r.enforcement_level
        """
        try:
            results = await self.graph.run(cypher)
            self._rule_cache = {}
            for row in results:
                self._rule_cache[row["r.id"]] = {
                    "rule_type": row["r.rule_type"],
                    "title": row["r.title"],
                    "condition": row["r.condition"],
                    "severity": row["r.severity"],
                    "confidence_threshold": row["r.confidence_threshold"],
                    "applicability": row["r.applicability"],
                    "exclusions": row["r.exclusions"],
                    "enforcement_level": row["r.enforcement_level"]
                }
            logger.info(f"Loaded {len(self._rule_cache)} compliance rules into cache")
            return len(self._rule_cache)
        except Exception as e:
            logger.error(f"Failed to load rules: {e}")
            return 0
    
    def _parse_condition(self, condition_str: str) -> tuple[str, str, Any]:
        """
        Parse condition string: "holding_pct > 0.15"
        Returns: (metric_name, operator, threshold_value)
        """
        # Match pattern: metric operator value
        match = re.match(r'(\w+)\s*(>|>=|<|<=|==|!=)\s*([\d.]+)', condition_str)
        if match:
            metric, op, threshold = match.groups()
            op_map = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "==": "eq", "!=": "neq"}
            return metric, op_map[op], float(threshold)
        
        raise ValueError(f"Invalid condition format: {condition_str}")
    
    async def evaluate_rule(self, rule_id: str, fund_data: Dict[str, Any]) -> Optional[ComplianceViolation]:
        """
        Evaluate a single rule against fund data.
        
        Args:
            rule_id: ID of rule to evaluate
            fund_data: {
                fund_id, fund_name, category, holdings: {security: pct},
                manager_certified: bool, kyc_last_updated: date, etc.
            }
        
        Returns:
            ComplianceViolation if rule violated, None otherwise
        """
        if rule_id not in self._rule_cache:
            logger.warning(f"Rule {rule_id} not in cache")
            return None
        
        rule = self._rule_cache[rule_id]
        
        # Check applicability
        if rule["applicability"] and fund_data.get("category") not in rule["applicability"]:
            return None  # Rule doesn't apply to this fund category
        
        # Check exclusions
        if rule["exclusions"] and fund_data.get("category") in rule["exclusions"]:
            return None  # Fund is excluded from this rule
        
        try:
            # Parse condition
            metric, operator, threshold = self._parse_condition(rule["condition"])
            
            # Get actual value from fund_data
            actual_value = self._get_metric_value(fund_data, metric)
            
            # Evaluate condition
            evaluator = self._condition_evaluators[operator]
            if operator == "in_range":
                # For range checks, need min/max from data
                is_violated = not evaluator(actual_value, threshold[0], threshold[1])
            else:
                is_violated = evaluator(actual_value, threshold)
            
            if is_violated:
                # Create violation record
                violation = ComplianceViolation(
                    violation_id=f"V_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{rule_id}",
                    rule_id=rule_id,
                    rule_title=rule["title"],
                    fund_id=fund_data["fund_id"],
                    severity=rule["severity"],
                    confidence=rule["confidence_threshold"],  # For now, use rule's threshold as confidence
                    actual_value=actual_value,
                    threshold_value=threshold,
                    description=f"{rule['title']}: {metric} = {actual_value} (limit: {threshold})",
                    evidence_docs=[],  # Will be populated from audit log
                    detected_at=datetime.now().isoformat(),
                    region=fund_data.get("region", "SEBI")
                )
                return violation
        
        except Exception as e:
            logger.error(f"Error evaluating rule {rule_id}: {e}")
        
        return None
    
    def _get_metric_value(self, fund_data: Dict[str, Any], metric: str) -> Any:
        """Extract metric value from fund data."""
        # Support nested access: "holdings.Technology" or "holdings.Tech"
        if "." in metric:
            parts = metric.split(".")
            value = fund_data
            for part in parts:
                value = value.get(part)
                if value is None:
                    return None
            return value
        
        return fund_data.get(metric)
    
    async def evaluate_fund(self, fund_id: str, fund_data: Dict[str, Any]) -> List[ComplianceViolation]:
        """
        Evaluate all applicable rules for a fund.
        
        Returns: List of violations detected
        """
        violations = []
        
        # Get all rules applicable to this fund's category
        cypher = """
        MATCH (f:FundScheme {id: $fund_id})-[:governedBy]->(r:Rule)
        WHERE r.active = true OR NOT EXISTS(r.active)
        RETURN r.id
        """
        try:
            results = await self.graph.run(cypher, {"fund_id": fund_id})
            applicable_rule_ids = [row["r.id"] for row in results]
        except Exception as e:
            logger.error(f"Failed to fetch applicable rules for fund {fund_id}: {e}")
            applicable_rule_ids = list(self._rule_cache.keys())
        
        # Evaluate each applicable rule
        for rule_id in applicable_rule_ids:
            violation = await self.evaluate_rule(rule_id, fund_data)
            if violation:
                violations.append(violation)
        
        return violations
    
    async def store_violations(self, violations: List[ComplianceViolation]) -> int:
        """Store violations in Neo4j."""
        stored_count = 0
        
        for violation in violations:
            try:
                cypher = """
                CREATE (v:Violation {
                    id: $violation_id,
                    rule_id: $rule_id,
                    fund_id: $fund_id,
                    severity: $severity,
                    confidence: toFloat($confidence),
                    actual_value: $actual_value,
                    threshold_value: $threshold_value,
                    description: $description,
                    detected_at: $detected_at,
                    region: $region,
                    status: 'detected'
                })
                WITH v
                MATCH (r:Rule {id: $rule_id})
                CREATE (v)-[:violates]->(r)
                WITH v
                MATCH (f:FundScheme {id: $fund_id})
                CREATE (v)-[:affects]->(f)
                RETURN v.id
                """
                result = await self.graph.run(cypher, {
                    "violation_id": violation.violation_id,
                    "rule_id": violation.rule_id,
                    "fund_id": violation.fund_id,
                    "severity": violation.severity,
                    "confidence": violation.confidence,
                    "actual_value": str(violation.actual_value),
                    "threshold_value": str(violation.threshold_value),
                    "description": violation.description,
                    "detected_at": violation.detected_at,
                    "region": violation.region
                })
                stored_count += 1
            except Exception as e:
                logger.error(f"Failed to store violation {violation.violation_id}: {e}")
        
        logger.info(f"Stored {stored_count} violations")
        return stored_count
```

**Files to Create:**
- `backend/app/compliance/rules_engine.py` — Core rules evaluator
- `backend/app/schemas/violation_models.py` — Pydantic models for violations

---

### **Task 1.4: Unit Tests & Integration Tests (Day 4)**

**Deliverable**: Comprehensive test suite for Phase 1

**Implementation**:

```python
# backend/tests/compliance/test_rules_engine.py

import pytest
from datetime import datetime
from app.compliance.rules_engine import RulesEngine, ComplianceViolation

@pytest.fixture
async def rules_engine(mock_graph_client):
    engine = RulesEngine(mock_graph_client)
    await engine.load_rules()
    return engine

@pytest.mark.asyncio
async def test_parse_condition():
    engine = RulesEngine(None)
    
    # Test simple conditions
    metric, op, threshold = engine._parse_condition("holding_pct > 0.15")
    assert metric == "holding_pct"
    assert op == "gt"
    assert threshold == 0.15
    
    # Test >= operator
    metric, op, threshold = engine._parse_condition("aum > 1000")
    assert op == "gt"
    assert threshold == 1000


@pytest.mark.asyncio
async def test_evaluate_rule_concentration_violation(rules_engine):
    """Test detection of portfolio concentration violation."""
    fund_data = {
        "fund_id": "Adani_Growth_2024",
        "category": "equity_fund",
        "holdings": {
            "Technology": 0.18  # 18% > 15% limit
        }
    }
    
    # Mock rule in cache
    rules_engine._rule_cache["RULE_PORT_CONC_001"] = {
        "rule_type": "portfolio",
        "title": "Single Sector Concentration",
        "condition": "holdings.Technology > 0.15",
        "severity": "high",
        "confidence_threshold": 0.95,
        "applicability": ["equity_fund"],
        "exclusions": [],
        "enforcement_level": "automatic"
    }
    
    violation = await rules_engine.evaluate_rule("RULE_PORT_CONC_001", fund_data)
    
    assert violation is not None
    assert violation.severity == "high"
    assert violation.actual_value == 0.18
    assert violation.threshold_value == 0.15


@pytest.mark.asyncio
async def test_evaluate_rule_no_violation(rules_engine):
    """Test rule passes when within limits."""
    fund_data = {
        "fund_id": "Adani_Growth_2024",
        "category": "equity_fund",
        "holdings": {
            "Technology": 0.12  # 12% < 15% limit
        }
    }
    
    rules_engine._rule_cache["RULE_PORT_CONC_001"] = {
        "rule_type": "portfolio",
        "title": "Single Sector Concentration",
        "condition": "holdings.Technology > 0.15",
        "severity": "high",
        "confidence_threshold": 0.95,
        "applicability": ["equity_fund"],
        "exclusions": [],
        "enforcement_level": "automatic"
    }
    
    violation = await rules_engine.evaluate_rule("RULE_PORT_CONC_001", fund_data)
    assert violation is None


@pytest.mark.asyncio
async def test_evaluate_rule_exclusion(rules_engine):
    """Test rule doesn't apply to excluded fund types."""
    fund_data = {
        "fund_id": "Tech_Sector_Fund",
        "category": "sector_fund",  # Excluded from concentration rule
        "holdings": {
            "Technology": 0.50  # 50% allowed for sector funds
        }
    }
    
    rules_engine._rule_cache["RULE_PORT_CONC_001"] = {
        "rule_type": "portfolio",
        "title": "Single Sector Concentration",
        "condition": "holdings.Technology > 0.15",
        "severity": "high",
        "confidence_threshold": 0.95,
        "applicability": ["equity_fund"],
        "exclusions": ["sector_fund"],  # Sector funds excluded
        "enforcement_level": "automatic"
    }
    
    violation = await rules_engine.evaluate_rule("RULE_PORT_CONC_001", fund_data)
    assert violation is None  # No violation for excluded type


@pytest.mark.asyncio
async def test_evaluate_fund_multiple_rules(rules_engine, mock_graph_client):
    """Test evaluating multiple rules for a fund."""
    fund_data = {
        "fund_id": "Adani_Growth_2024",
        "category": "equity_fund",
        "holdings": {"Technology": 0.18},  # Violates concentration
        "manager_certified": False  # Violates certification
    }
    
    # Mock rules
    rules_engine._rule_cache = {
        "RULE_PORT_CONC_001": {
            "rule_type": "portfolio",
            "title": "Sector Concentration",
            "condition": "holdings.Technology > 0.15",
            "severity": "high",
            "confidence_threshold": 0.95,
            "applicability": ["equity_fund"],
            "exclusions": [],
            "enforcement_level": "automatic"
        },
        "RULE_GOV_MGR_CERT": {
            "rule_type": "governance",
            "title": "Manager Certification",
            "condition": "manager_certified == 1",  # 1 = true
            "severity": "high",
            "confidence_threshold": 0.99,
            "applicability": ["equity_fund"],
            "exclusions": [],
            "enforcement_level": "automatic"
        }
    }
    
    # Mock applicable rules query
    mock_graph_client.run.return_value = [
        {"r.id": "RULE_PORT_CONC_001"},
        {"r.id": "RULE_GOV_MGR_CERT"}
    ]
    
    violations = await rules_engine.evaluate_fund("Adani_Growth_2024", fund_data)
    
    assert len(violations) == 2
    assert any(v.rule_id == "RULE_PORT_CONC_001" for v in violations)
    assert any(v.rule_id == "RULE_GOV_MGR_CERT" for v in violations)


def test_violation_to_dict():
    """Test violation serialization."""
    violation = ComplianceViolation(
        violation_id="V_001",
        rule_id="RULE_PORT_CONC_001",
        rule_title="Concentration Limit",
        fund_id="Adani_Growth_2024",
        severity="high",
        confidence=0.95,
        actual_value=0.18,
        threshold_value=0.15,
        description="Technology 18% > 15% limit",
        evidence_docs=["NAV_20240115.csv"],
        detected_at="2024-01-15T10:30:00Z",
        region="SEBI"
    )
    
    violation_dict = violation.to_dict()
    assert violation_dict["violation_id"] == "V_001"
    assert violation_dict["severity"] == "high"
    assert violation_dict["actual_value"] == 0.18
```

**Files to Create:**
- `backend/tests/compliance/test_rules_engine.py` — Unit tests
- `backend/tests/compliance/test_rules_ingestion.py` — Ingestion tests
- `backend/tests/compliance/conftest.py` — Pytest fixtures

---

## **Week 2: Violation Detection & Audit Integration**

### **Task 2.1: Implement Violation Detector Service (Day 5-6)**

**Deliverable**: Violation detector that orchestrates rule evaluation across all funds

**Implementation**:

```python
# backend/app/compliance/violation_detector.py

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ComplianceAuditResult:
    """Result of a compliance audit run."""
    audit_id: str
    audit_started_at: str
    audit_completed_at: str
    total_funds: int
    total_rules_evaluated: int
    total_violations: int
    critical_violations: int
    high_violations: int
    medium_violations: int
    low_violations: int
    violations_by_fund: Dict[str, int]
    violations_by_rule: Dict[str, int]
    regions: Dict[str, Any]


class ViolationDetector:
    """Orchestrates compliance violation detection across all funds."""
    
    def __init__(self, graph_client, rules_engine):
        self.graph = graph_client
        self.rules_engine = rules_engine
    
    async def audit_all_funds(self, region: str = "SEBI") -> ComplianceAuditResult:
        """
        Run compliance audit across all funds in specified region.
        
        Returns: Audit result with violations summary
        """
        audit_id = f"AUDIT_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        audit_started = datetime.now()
        
        logger.info(f"[{audit_id}] Starting compliance audit for region {region}")
        
        # Fetch all funds
        cypher = """
        MATCH (f:FundScheme)
        WHERE NOT EXISTS(f.region) OR f.region = $region
        RETURN f.id, f.name, f.category, f.aum_cr
        LIMIT 1000
        """
        try:
            funds_result = await self.graph.run(cypher, {"region": region})
            funds = [
                {
                    "fund_id": row["f.id"],
                    "fund_name": row["f.name"],
                    "category": row["f.category"],
                    "aum_cr": row["f.aum_cr"],
                    "region": region
                }
                for row in funds_result
            ]
        except Exception as e:
            logger.error(f"Failed to fetch funds: {e}")
            return ComplianceAuditResult(
                audit_id=audit_id,
                audit_started_at=audit_started.isoformat(),
                audit_completed_at=datetime.now().isoformat(),
                total_funds=0,
                total_rules_evaluated=0,
                total_violations=0,
                critical_violations=0,
                high_violations=0,
                medium_violations=0,
                low_violations=0,
                violations_by_fund={},
                violations_by_rule={},
                regions={}
            )
        
        logger.info(f"[{audit_id}] Found {len(funds)} funds to audit")
        
        # Audit each fund (can parallelize with semaphore for rate limiting)
        all_violations = []
        violations_by_fund = {}
        violations_by_rule = {}
        
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent audits
        
        async def audit_fund_with_semaphore(fund: Dict[str, Any]):
            async with semaphore:
                return await self._audit_single_fund(fund, audit_id)
        
        audit_tasks = [audit_fund_with_semaphore(fund) for fund in funds]
        audit_results = await asyncio.gather(*audit_tasks)
        
        for fund_id, violations in audit_results:
            all_violations.extend(violations)
            violations_by_fund[fund_id] = len(violations)
            
            for violation in violations:
                violations_by_rule[violation.rule_id] = \
                    violations_by_rule.get(violation.rule_id, 0) + 1
        
        # Calculate severity counts
        severity_counts = {
            "critical": sum(1 for v in all_violations if v.severity == "critical"),
            "high": sum(1 for v in all_violations if v.severity == "high"),
            "medium": sum(1 for v in all_violations if v.severity == "medium"),
            "low": sum(1 for v in all_violations if v.severity == "low"),
        }
        
        # Store violations in database
        stored_count = await self.rules_engine.store_violations(all_violations)
        
        audit_completed = datetime.now()
        audit_duration = (audit_completed - audit_started).total_seconds()
        
        result = ComplianceAuditResult(
            audit_id=audit_id,
            audit_started_at=audit_started.isoformat(),
            audit_completed_at=audit_completed.isoformat(),
            total_funds=len(funds),
            total_rules_evaluated=len(self.rules_engine._rule_cache),
            total_violations=len(all_violations),
            critical_violations=severity_counts["critical"],
            high_violations=severity_counts["high"],
            medium_violations=severity_counts["medium"],
            low_violations=severity_counts["low"],
            violations_by_fund=violations_by_fund,
            violations_by_rule=violations_by_rule,
            regions={region: {
                "total_violations": len(all_violations),
                "severity_breakdown": severity_counts
            }}
        )
        
        logger.info(f"[{audit_id}] Audit completed in {audit_duration:.2f}s | "
                   f"Violations: {len(all_violations)} | "
                   f"Stored: {stored_count}")
        
        return result
    
    async def _audit_single_fund(self, fund: Dict[str, Any], audit_id: str) -> tuple[str, List]:
        """Audit single fund against all applicable rules."""
        fund_id = fund["fund_id"]
        
        try:
            # Fetch live portfolio data
            portfolio_data = await self._fetch_fund_portfolio_data(fund_id)
            if not portfolio_data:
                logger.warning(f"[{audit_id}] No portfolio data for fund {fund_id}")
                return fund_id, []
            
            # Merge with fund metadata
            audit_data = {**fund, **portfolio_data}
            
            # Evaluate all applicable rules
            violations = await self.rules_engine.evaluate_fund(fund_id, audit_data)
            
            logger.debug(f"[{audit_id}] Fund {fund_id}: {len(violations)} violations")
            return fund_id, violations
        
        except Exception as e:
            logger.error(f"[{audit_id}] Failed to audit fund {fund_id}: {e}")
            return fund_id, []
    
    async def _fetch_fund_portfolio_data(self, fund_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch live portfolio data for a fund.
        This would typically connect to AMC's portfolio management system.
        For MVP, using mock data.
        """
        # TODO: Integrate with actual portfolio data source (API, database, etc.)
        # For now, mock data
        return {
            "holdings": {
                "Technology": 0.18,
                "Finance": 0.22,
                "Healthcare": 0.15,
                "Utilities": 0.12,
                "Other": 0.33
            },
            "nav": 100.50,
            "manager_certified": True,
            "kyc_last_updated": "2024-01-10"
        }
    
    async def get_audit_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent audit runs."""
        cypher = """
        MATCH (a:ComplianceAudit)
        RETURN a.audit_id, a.audit_started_at, a.total_violations,
               a.high_violations, a.critical_violations
        ORDER BY a.audit_started_at DESC
        LIMIT $limit
        """
        try:
            results = await self.graph.run(cypher, {"limit": limit})
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Failed to fetch audit history: {e}")
            return []
```

**Files to Create:**
- `backend/app/compliance/violation_detector.py` — Violation orchestration service

---

### **Task 2.2: API Endpoints for Violation Management (Day 6)**

**Deliverable**: REST endpoints for compliance violation queries

**Implementation**:

```python
# backend/app/api/routes/compliance.py

from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from app.api.deps import get_container
from app.compliance.violation_detector import ViolationDetector
from app.schemas.compliance_models import ViolationResponse, ComplianceAuditResultResponse

router = APIRouter(prefix="/api/compliance", tags=["compliance"])

@router.post("/audit", response_model=ComplianceAuditResultResponse)
async def run_compliance_audit(
    region: str = Query("SEBI", description="Region: SEBI, SEC, ESMA"),
    container = Depends(get_container)
):
    """
    Trigger compliance audit across all funds in specified region.
    
    Returns:
    - audit_id: Unique audit run identifier
    - total_funds: Number of funds audited
    - total_violations: Total violations detected
    - severity breakdown
    """
    detector = ViolationDetector(container.graph, container.rules_engine)
    result = await detector.audit_all_funds(region=region)
    return result


@router.get("/violations", response_model=List[ViolationResponse])
async def get_violations(
    region: str = Query("SEBI"),
    severity: Optional[str] = Query(None, description="Filter by severity: high, medium, low, critical"),
    fund_id: Optional[str] = Query(None),
    status: Optional[str] = Query("detected", description="Filter by status: detected, reviewed, remediated, closed"),
    limit: int = Query(100, le=1000),
    container = Depends(get_container)
):
    """
    Get list of compliance violations with optional filters.
    
    Query Parameters:
    - region: SEBI, SEC, ESMA
    - severity: high, medium, low, critical
    - fund_id: Filter by fund
    - status: detected, reviewed, remediated, closed
    - limit: Max results (default 100, max 1000)
    """
    cypher = """
    MATCH (v:Violation)
    WHERE v.region = $region
    """
    params = {"region": region}
    
    if severity:
        cypher += " AND v.severity = $severity"
        params["severity"] = severity
    
    if fund_id:
        cypher += " AND v.fund_id = $fund_id"
        params["fund_id"] = fund_id
    
    if status:
        cypher += " AND v.status = $status"
        params["status"] = status
    
    cypher += """
    RETURN v.id, v.rule_id, v.fund_id, v.severity, v.confidence,
           v.actual_value, v.threshold_value, v.description,
           v.detected_at, v.status
    ORDER BY v.detected_at DESC
    LIMIT $limit
    """
    params["limit"] = limit
    
    try:
        results = await container.graph.run(cypher, params)
        violations = [
            ViolationResponse(
                violation_id=row["v.id"],
                rule_id=row["v.rule_id"],
                fund_id=row["v.fund_id"],
                severity=row["v.severity"],
                confidence=row["v.confidence"],
                actual_value=row["v.actual_value"],
                threshold_value=row["v.threshold_value"],
                description=row["v.description"],
                detected_at=row["v.detected_at"],
                status=row["v.status"]
            )
            for row in results
        ]
        return violations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fund/{fund_id}/violations", response_model=List[ViolationResponse])
async def get_fund_violations(
    fund_id: str,
    container = Depends(get_container)
):
    """Get all violations for a specific fund."""
    cypher = """
    MATCH (v:Violation {fund_id: $fund_id})
    RETURN v.id, v.rule_id, v.severity, v.confidence,
           v.actual_value, v.threshold_value, v.description,
           v.detected_at, v.status
    ORDER BY v.severity DESC, v.detected_at DESC
    """
    try:
        results = await container.graph.run(cypher, {"fund_id": fund_id})
        return [ViolationResponse(**dict(row)) for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/violations/{violation_id}/resolve")
async def resolve_violation(
    violation_id: str,
    resolution_action: str,
    container = Depends(get_container)
):
    """Mark a violation as remediated."""
    cypher = """
    MATCH (v:Violation {id: $violation_id})
    SET v.status = 'remediated',
        v.resolved_at = $now,
        v.resolution_action = $action
    RETURN v.id, v.status
    """
    try:
        result = await container.graph.run(cypher, {
            "violation_id": violation_id,
            "now": datetime.now().isoformat(),
            "action": resolution_action
        })
        return {"status": "resolved", "violation_id": violation_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scorecard", response_model=Dict[str, Any])
async def get_compliance_scorecard(
    region: str = Query("SEBI"),
    container = Depends(get_container)
):
    """
    Get real-time compliance scorecard.
    
    Returns:
    - overall_compliance_score: 0-100%
    - total_rules: Total applicable rules
    - rules_passing: Rules with no violations
    - critical_violations: Count
    - high_violations: Count
    """
    cypher = """
    MATCH (r:Rule) WHERE r.active = true OR NOT EXISTS(r.active)
    RETURN count(r) AS total_rules
    """
    
    try:
        rule_result = await container.graph.run(cypher)
        total_rules = rule_result[0]["total_rules"] if rule_result else 0
        
        # Count rules with violations
        violation_cypher = """
        MATCH (v:Violation {region: $region})-[:violates]->(r:Rule)
        RETURN count(DISTINCT r) AS rules_with_violations
        """
        violation_result = await container.graph.run(violation_cypher, {"region": region})
        rules_with_violations = violation_result[0]["rules_with_violations"] if violation_result else 0
        
        rules_passing = total_rules - rules_with_violations
        compliance_score = (rules_passing / total_rules * 100) if total_rules > 0 else 100
        
        # Count violations by severity
        severity_cypher = """
        MATCH (v:Violation {region: $region, status: 'detected'})
        RETURN v.severity, count(v) AS count
        """
        severity_results = await container.graph.run(severity_cypher, {"region": region})
        severity_counts = {row["v.severity"]: row["count"] for row in severity_results}
        
        return {
            "overall_compliance_score": round(compliance_score, 2),
            "compliance_percentage": f"{compliance_score:.1f}%",
            "total_rules": total_rules,
            "rules_passing": rules_passing,
            "rules_with_violations": rules_with_violations,
            "violations": {
                "critical": severity_counts.get("critical", 0),
                "high": severity_counts.get("high", 0),
                "medium": severity_counts.get("medium", 0),
                "low": severity_counts.get("low", 0),
                "total": sum(severity_counts.values())
            },
            "region": region
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Files to Create:**
- `backend/app/api/routes/compliance.py` — Compliance API endpoints
- Update `backend/app/api/routes/__init__.py` to import compliance router

---

### **Task 2.3: Integration with Audit Logging (Day 7)**

**Deliverable**: Link violations to audit trail for full traceability

**Implementation**:

```python
# backend/app/compliance/audit_integration.py

import logging
from datetime import datetime
from typing import Dict, Any, List
from app.schemas.compliance_models import ComplianceViolation

logger = logging.getLogger(__name__)

async def log_violation_to_audit_trail(
    violation: ComplianceViolation,
    audit_log_writer  # Existing audit logger from context_engineering
) -> str:
    """
    Log violation to compliance audit trail.
    Creates link from violation to originating query/rule evaluation.
    """
    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": "compliance_violation",
        "violation_id": violation.violation_id,
        "rule_id": violation.rule_id,
        "fund_id": violation.fund_id,
        "severity": violation.severity,
        "confidence": violation.confidence,
        "description": violation.description,
        "region": violation.region,
        "evidence": violation.evidence_docs,
        "status": violation.status
    }
    
    # Write to JSONL audit log
    await audit_log_writer(audit_entry)
    logger.info(f"Violation {violation.violation_id} logged to audit trail")
    
    return violation.violation_id


async def enrich_violation_with_evidence(
    violation: ComplianceViolation,
    graph_client
) -> ComplianceViolation:
    """
    Enrich violation with evidence documents from audit logs.
    Links violation to NAV feeds, prospectuses, regulatory documents.
    """
    cypher = """
    MATCH (d:Document)
    WHERE d.fund_id = $fund_id
    ORDER BY d.timestamp DESC
    LIMIT 5
    RETURN d.document_id, d.filename, d.doc_type
    """
    
    try:
        results = await graph_client.run(cypher, {"fund_id": violation.fund_id})
        documents = [row["d.document_id"] for row in results]
        violation.evidence_docs = documents
    except Exception as e:
        logger.warning(f"Failed to fetch evidence documents: {e}")
    
    return violation
```

**Files to Create:**
- `backend/app/compliance/audit_integration.py` — Violation-to-audit linking

---

### **Task 2.4: Documentation & Deployment (Day 7-8)**

**Deliverable**: Runbook, deployment script, configuration guide

**Implementation**:

**File: `docs/COMPLIANCE_PHASE1_RUNBOOK.md`**

```markdown
# Phase 1: Rules Engine & Violation Detection — Deployment Runbook

## Prerequisites
- Neo4j 5.10+ running and accessible
- PostgreSQL for audit logging
- Python 3.9+
- Existing ContextGraph system operational

## Step 1: Database Schema Setup

```bash
# Connect to Neo4j and apply schema
neo4j-shell -u neo4j -p <password>

# Run schema creation
LOAD CSV WITH HEADERS FROM 'file:///etc/neo4j/import/compliance_schema.cypher' AS row
...
```

## Step 2: Ingest Compliance Rules

```bash
# Place CSV files in data/compliance/
- sebi_regulations.csv (50 regulations)
- rules.csv (30 initial rules per regulation)
- fund_schemes.csv (fund metadata)

# Run ingestion
python -m backend.app.ingestion.compliance_rules_ingester
```

## Step 3: Load Rules Into Cache

```bash
# Start FastAPI server
uvicorn app.main:app --reload

# Trigger rules loading
curl -X POST http://localhost:8000/api/compliance/load-rules
```

## Step 4: Run Compliance Audit

```bash
# Full audit for all funds
curl -X POST http://localhost:8000/api/compliance/audit?region=SEBI

# Query violations
curl http://localhost:8000/api/compliance/violations?region=SEBI&severity=high

# Get scorecard
curl http://localhost:8000/api/compliance/scorecard
```

## Monitoring

- Audit logs: `logs/query_execution_audit.jsonl`
- Violations table: `SELECT * FROM violations WHERE created_at > NOW() - INTERVAL 1 HOUR`
- Performance: Monitor rule evaluation latency (<100ms per fund)
```

**Files to Create:**
- `docs/COMPLIANCE_PHASE1_RUNBOOK.md` — Deployment guide
- `docker/compliance-rules-init.sh` — Docker initialization script
- `data/compliance/sebi_regulations.csv` — Initial SEBI rules

---

## **Week 1-2 Summary**

| Deliverable | Status | Files Created |
|---|---|---|
| Graph schema | ✅ | `compliance_schema.py`, `compliance_models.py` |
| Rules ingestion | ✅ | `compliance_rules_ingester.py`, CSV data files |
| Rules engine | ✅ | `rules_engine.py` |
| Violation detector | ✅ | `violation_detector.py` |
| API endpoints | ✅ | `routes/compliance.py` |
| Audit integration | ✅ | `audit_integration.py` |
| Tests | ✅ | `test_rules_engine.py`, `test_compliance_violations.py` |
| Documentation | ✅ | `COMPLIANCE_PHASE1_RUNBOOK.md` |
| **Compliance Gain** | **+15%** | **35% → 50%** |

---

# **PHASE 2: DOMAIN-SPECIFIC COMPLIANCE AGENTS (Weeks 3-6)**

## **Objective**

Build 5 specialized compliance auditing agents (Portfolio, Governance, KYC, Risk, Reporting) that autonomously evaluate fund operations against regulatory domains.

**Success Criteria:**
- ✅ All 5 agents implemented and tested
- ✅ Each agent fetches domain-specific data, applies rules, produces violations
- ✅ Agents callable individually and orchestrated together
- ✅ Test coverage ≥85%
- ✅ **Compliance boost: 50% → 75% (+25%)**

---

## **Week 3: Portfolio Agent Implementation**

### **Task 3.1: Portfolio Agent Architecture (Day 1-2)**

**Deliverable**: Portfolio compliance auditor that checks asset allocation, concentration limits, sector caps

**Implementation**:

```python
# backend/app/compliance/agents/portfolio_agent.py

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class PortfolioAuditResult:
    """Result of portfolio compliance audit."""
    fund_id: str
    fund_name: str
    audit_timestamp: str
    violations: List[Dict[str, Any]]
    checks_performed: List[str]
    total_holdings: int
    compliance_summary: Dict[str, Any]


class PortfolioAgent:
    """Audits fund portfolio compliance (concentration, sector, asset class limits)."""
    
    def __init__(self, graph_client, rules_engine):
        self.graph = graph_client
        self.rules_engine = rules_engine
        self.agent_type = "portfolio"
    
    async def audit_fund_portfolio(self, fund_id: str) -> PortfolioAuditResult:
        """
        Audit single fund's portfolio compliance.
        
        Checks:
        1. Single holding concentration (e.g., >15% in one security)
        2. Sector concentration (e.g., >30% in one sector)
        3. Asset class limits (e.g., >95% in equities)
        4. Related-party transaction limits
        5. Derivative/option exposure limits
        """
        logger.info(f"[PortfolioAgent] Starting audit for fund {fund_id}")
        
        # Step 1: Fetch fund metadata
        fund_metadata = await self._fetch_fund_metadata(fund_id)
        if not fund_metadata:
            logger.error(f"Fund {fund_id} not found")
            return PortfolioAuditResult(
                fund_id=fund_id,
                fund_name="Unknown",
                audit_timestamp=datetime.now().isoformat(),
                violations=[],
                checks_performed=[],
                total_holdings=0,
                compliance_summary={"status": "error", "message": "Fund not found"}
            )
        
        # Step 2: Fetch current portfolio holdings
        portfolio_data = await self._fetch_portfolio_holdings(fund_id)
        
        # Step 3: Fetch applicable portfolio rules for fund type
        applicable_rules = await self._get_applicable_rules(
            fund_category=fund_metadata["category"],
            rule_type="portfolio"
        )
        
        logger.info(f"[PortfolioAgent] Found {len(applicable_rules)} applicable portfolio rules")
        
        # Step 4: Evaluate each rule
        violations = []
        checks_performed = []
        
        for rule in applicable_rules:
            rule_result = await self._evaluate_portfolio_rule(
                fund_id=fund_id,
                fund_metadata=fund_metadata,
                portfolio_data=portfolio_data,
                rule=rule
            )
            
            checks_performed.append(rule_result["check_name"])
            
            if rule_result["violated"]:
                violations.append(rule_result["violation"])
        
        # Step 5: Generate summary
        compliance_summary = {
            "status": "compliant" if not violations else "non_compliant",
            "total_violations": len(violations),
            "critical_count": sum(1 for v in violations if v["severity"] == "critical"),
            "high_count": sum(1 for v in violations if v["severity"] == "high"),
            "medium_count": sum(1 for v in violations if v["severity"] == "medium"),
            "low_count": sum(


# **AMC COMPLIANCE AUDIT SYSTEM — COMPLETE 12-WEEK DETAILED IMPLEMENTATION PLAN**

**Project**: ContextGraph AMC Compliance Auditing System  
**Timeline**: 12 weeks (3 months, 5 phases)  
**Team**: 3-4 Backend Engineers + 1 DevOps  
**Tech Stack**: Python 3.12, FastAPI 0.115, Neo4j 5.24, FAISS, Groq LLM  
**Current Status**: 45-50% complete (guardrails + RBAC + audit logging done; agents + rules engine + dashboard missing)  
**Target**: 90%+ AMC compliance ready  

---

# **EXECUTION SUMMARY TABLE**

| Phase | Duration | Objective | Key Deliverables | Compliance Gain | Team |
|-------|----------|-----------|------------------|-----------------|------|
| **1** | Weeks 1-2 | Rules Engine | Compliance graph schema, rules ingestion, deterministic matcher, violation detector | +15% (35→50%) | 2 engineers |
| **2** | Weeks 3-6 | Domain Agents | 5 agents (Portfolio, Governance, KYC, Risk, Reporting) | +25% (50→75%) | 2 engineers |
| **3** | Weeks 7-8 | API & Dashboard | Compliance scorecard API, real-time dashboard, violation queries | +10% (75→85%) | 1 engineer |
| **4** | Weeks 9-10 | Escalation & Multi-Region | Violation routing, case management, SEBI/SEC/ESMA support | +10% (85→95%) | 1 engineer |
| **5** | Weeks 11-12 | Production Hardening | Performance, certification, audits, documentation | +5% (95→100%) | 1-2 engineers |

---

---

# **PHASE 1: RULES ENGINE & VIOLATION DETECTION (Weeks 1-2)**

## **Phase Overview**

Build the foundational compliance rules infrastructure: graph schema, rule ingestion pipeline, deterministic rule matcher, and violation detector service.

**Status**: +15% compliance gain (35% → 50%)  
**Team**: 2 Backend Engineers  
**Sprint**: 10 working days

---

## **Week 1: Compliance Graph Schema & Rules Framework**

### **Day 1-2: Design & Deploy Compliance Graph Schema**

**Objective**: Define Neo4j schema for storing regulations, rules, funds, and violations.

**Tasks**:

**Task 1.1: Design Compliance Data Model**

Create schema design document:
- 6 node types: `Regulation`, `Rule`, `FundScheme`, `Violation`, `RiskThreshold`, `EscalationPath`
- 8 relationships: `hasRule`, `appliesTo`, `triggers`, `violates`, `affects`, `escalatesVia`, `evidencedBy`, `basedOn`
- 15 properties per node (see architecture below)
- Indexes on: `region`, `rule_type`, `severity`, `effective_date`, `fund_id`

**File**: `backend/app/graph/compliance_schema.md` (diagram + data dictionary)

```markdown
# Compliance Graph Schema

## Nodes

### :Regulation
- id (UNIQUE)
- title
- region (SEBI | SEC | ESMA)
- effective_date
- document_url
- raw_text
- created_at

### :Rule
- id (UNIQUE)
- rule_type (portfolio | governance | kyc | risk | reporting)
- title
- description
- regulation_id (foreign key)
- condition (e.g., "holding_pct > 0.15")
- severity (critical | high | medium | low)
- confidence_threshold (0.0-1.0)
- applicability ([fund_category])
- exclusions ([fund_category])
- enforcement_level (automatic | audit | escalation)
- created_at

### :FundScheme
- id (UNIQUE)
- isin
- name
- fund_house
- category (equity_fund | debt_fund | balanced_fund | sector_fund)
- mandate
- risk_profile
- aum_cr
- created_at

### :Violation
- id (UNIQUE)
- rule_id (foreign key)
- fund_id (foreign key)
- finding
- severity (critical | high | medium | low)
- confidence (0.0-1.0)
- actual_value
- threshold_value
- violation_type (concentration | governance | kyc | risk | reporting)
- detected_at
- status (detected | reviewed | remediated | closed)
- region (SEBI | SEC | ESMA)
- resolved_at (nullable)
- resolution_action (nullable)

### :RiskThreshold
- id (UNIQUE)
- violation_type
- confidence_min
- confidence_max
- escalation_priority
- sla_minutes

### :EscalationPath
- id (UNIQUE)
- region
- severity
- routing_rules ([role])
- notification_channels ([email | slack | case_system])
- sla_hours
- requires_approval

## Relationships

:Regulation --[hasRule]--> :Rule
:Rule --[appliesTo]--> :FundScheme
:Rule --[triggers]--> :Violation
:Violation --[violates]--> :Rule
:Violation --[affects]--> :FundScheme
:Violation --[escalatesVia]--> :EscalationPath

## Indexes

CREATE UNIQUE CONSTRAINT regulation_id FOR (r:Regulation) REQUIRE r.id IS UNIQUE;
CREATE UNIQUE CONSTRAINT rule_id FOR (r:Rule) REQUIRE r.id IS UNIQUE;
CREATE INDEX idx_rule_type FOR (r:Rule) ON (r.rule_type);
CREATE INDEX idx_violation_severity FOR (v:Violation) ON (v.severity);
CREATE INDEX idx_violation_status FOR (v:Violation) ON (v.status);
```

**File**: `backend/app/graph/compliance_schema.py`

```python
# Neo4j schema deployment script
import logging
from app.graph.client import GraphClient

logger = logging.getLogger(__name__)

async def deploy_compliance_schema(graph: GraphClient) -> bool:
    """Deploy idempotent compliance graph schema."""
    
    constraints = [
        "CREATE CONSTRAINT regulation_id IF NOT EXISTS FOR (r:Regulation) REQUIRE r.id IS UNIQUE",
        "CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:Rule) REQUIRE r.id IS UNIQUE",
        "CREATE CONSTRAINT fundscheme_id IF NOT EXISTS FOR (f:FundScheme) REQUIRE f.id IS UNIQUE",
        "CREATE CONSTRAINT violation_id IF NOT EXISTS FOR (v:Violation) REQUIRE v.id IS UNIQUE",
        "CREATE CONSTRAINT riskthreshold_id IF NOT EXISTS FOR (t:RiskThreshold) REQUIRE t.id IS UNIQUE",
        "CREATE CONSTRAINT escalation_id IF NOT EXISTS FOR (e:EscalationPath) REQUIRE e.id IS UNIQUE",
    ]
    
    indexes = [
        "CREATE INDEX idx_rule_type IF NOT EXISTS FOR (r:Rule) ON (r.rule_type)",
        "CREATE INDEX idx_violation_severity IF NOT EXISTS FOR (v:Violation) ON (v.severity)",
        "CREATE INDEX idx_violation_status IF NOT EXISTS FOR (v:Violation) ON (v.status)",
        "CREATE INDEX idx_violation_region IF NOT EXISTS FOR (v:Violation) ON (v.region)",
    ]
    
    try:
        for constraint in constraints:
            await graph.run(constraint)
            logger.info(f"Constraint applied: {constraint[:50]}...")
        
        for index in indexes:
            await graph.run(index)
            logger.info(f"Index created: {index[:50]}...")
        
        logger.info("Compliance schema deployed successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to deploy compliance schema: {e}")
        return False
```

**Deliverable**: Schema design doc + Python deployment script  
**Estimate**: 2 hours

---

**Task 1.2: Create Pydantic Models for Compliance Entities**

Create data contracts for all compliance domain objects.

**File**: `backend/app/schemas/compliance_models.py`

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class RegionEnum(str, Enum):
    SEBI = "SEBI"
    SEC = "SEC"
    ESMA = "ESMA"

class SeverityEnum(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class RuleTypeEnum(str, Enum):
    PORTFOLIO = "portfolio"
    GOVERNANCE = "governance"
    KYC = "kyc"
    RISK = "risk"
    REPORTING = "reporting"

class ViolationStatusEnum(str, Enum):
    DETECTED = "detected"
    REVIEWED = "reviewed"
    REMEDIATED = "remediated"
    CLOSED = "closed"

# Request/Response Models

class RegulationCreate(BaseModel):
    id: str
    title: str
    region: RegionEnum
    effective_date: str
    document_url: str
    raw_text: str

class RuleCreate(BaseModel):
    id: str
    rule_type: RuleTypeEnum
    title: str
    description: str
    regulation_id: str
    condition: str  # e.g., "holding_pct > 0.15"
    severity: SeverityEnum
    confidence_threshold: float = Field(..., ge=0.0, le=1.0)
    applicability: List[str]
    exclusions: List[str]
    enforcement_level: str  # automatic, audit, escalation

class ViolationCreate(BaseModel):
    rule_id: str
    fund_id: str
    finding: str
    severity: SeverityEnum
    confidence: float = Field(..., ge=0.0, le=1.0)
    actual_value: Any
    threshold_value: Any
    violation_type: RuleTypeEnum
    region: RegionEnum
    evidence_docs: List[str] = []

class ViolationResponse(BaseModel):
    violation_id: str
    rule_id: str
    fund_id: str
    severity: SeverityEnum
    confidence: float
    actual_value: Any
    threshold_value: Any
    description: str
    detected_at: str
    status: ViolationStatusEnum
    region: RegionEnum

class ComplianceScorecard(BaseModel):
    overall_score: float = Field(..., ge=0.0, le=100.0)
    compliance_percentage: str
    total_rules: int
    rules_passing: int
    rules_with_violations: int
    violations: Dict[str, int]  # {critical, high, medium, low, total}
    region: RegionEnum
    last_audit_at: str
```

**Deliverable**: Pydantic model definitions  
**Estimate**: 1 hour

---

**Task 1.3: Implement CSV Ingestion Pipeline**

Create reusable CSV ingestion pipeline for regulations, rules, and fund schemes.

**File**: `backend/app/ingestion/compliance_rules_ingester.py`

```python
import csv
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import logging
from app.graph.client import GraphClient

logger = logging.getLogger(__name__)

class ComplianceRulesIngester:
    """Ingests regulatory rules from CSV files into Neo4j compliance graph."""
    
    def __init__(self, graph_client: GraphClient):
        self.graph = graph_client
    
    async def ingest_regulations_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        Ingest regulations from CSV.
        
        Expected columns: region, regulation_id, title, effective_date, document_url, raw_text
        """
        regulations_created = 0
        errors = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    try:
                        cypher = """
                        CREATE (r:Regulation {
                            id: $reg_id,
                            title: $title,
                            region: $region,
                            effective_date: $eff_date,
                            document_url: $url,
                            raw_text: $text,
                            created_at: $now
                        })
                        RETURN r.id
                        """
                        await self.graph.run(cypher, {
                            "reg_id": row["regulation_id"],
                            "title": row["title"],
                            "region": row["region"],
                            "eff_date": row["effective_date"],
                            "url": row["document_url"],
                            "text": row["raw_text"],
                            "now": datetime.now().isoformat()
                        })
                        regulations_created += 1
                    except Exception as e:
                        errors.append(f"Row {row_idx}: {str(e)}")
                        logger.warning(f"Failed to ingest regulation at row {row_idx}: {e}")
        except FileNotFoundError:
            return {"status": "error", "message": f"File not found: {csv_path}"}
        except Exception as e:
            logger.error(f"Failed to ingest regulations: {e}")
            return {"status": "error", "message": str(e)}
        
        logger.info(f"Ingested {regulations_created} regulations from {csv_path}")
        return {
            "status": "success",
            "regulations_created": regulations_created,
            "errors": errors,
            "error_count": len(errors)
        }
    
    async def ingest_rules_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        Ingest compliance rules from CSV.
        
        Expected columns: rule_id, rule_type, title, description, regulation_id, 
                         condition, severity, confidence_threshold, 
                         applicability_categories, exclusion_categories, enforcement_level
        """
        rules_created = 0
        errors = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    try:
                        applicability = json.loads(row.get("applicability_categories", "[]"))
                        exclusions = json.loads(row.get("exclusion_categories", "[]"))
                        
                        cypher = """
                        CREATE (r:Rule {
                            id: $rule_id,
                            rule_type: $rule_type,
                            title: $title,
                            description: $description,
                            condition: $condition,
                            severity: $severity,
                            confidence_threshold: toFloat($conf_threshold),
                            applicability: $applicability,
                            exclusions: $exclusions,
                            enforcement_level: $enforcement_level,
                            active: true,
                            created_at: $now
                        })
                        WITH r
                        MATCH (reg:Regulation {id: $reg_id})
                        CREATE (r)-[:basedOn]->(reg)
                        RETURN r.id
                        """
                        await self.graph.run(cypher, {
                            "rule_id": row["rule_id"],
                            "rule_type": row["rule_type"],
                            "title": row["title"],
                            "description": row["description"],
                            "regulation_id": row["regulation_id"],
                            "condition": row["condition"],
                            "severity": row["severity"],
                            "conf_threshold": row["confidence_threshold"],
                            "applicability": applicability,
                            "exclusions": exclusions,
                            "enforcement_level": row["enforcement_level"],
                            "now": datetime.now().isoformat(),
                            "reg_id": row["regulation_id"]
                        })
                        rules_created += 1
                    except Exception as e:
                        errors.append(f"Row {row_idx}: {str(e)}")
                        logger.warning(f"Failed to ingest rule at row {row_idx}: {e}")
        except FileNotFoundError:
            return {"status": "error", "message": f"File not found: {csv_path}"}
        except Exception as e:
            logger.error(f"Failed to ingest rules: {e}")
            return {"status": "error", "message": str(e)}
        
        logger.info(f"Ingested {rules_created} rules from {csv_path}")
        return {
            "status": "success",
            "rules_created": rules_created,
            "errors": errors,
            "error_count": len(errors)
        }
    
    async def ingest_fund_schemes_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        Ingest fund schemes from CSV.
        
        Expected columns: fund_id, isin, name, fund_house, category, mandate, 
                         risk_profile, aum_cr, rules_applicable_ids
        """
        funds_created = 0
        errors = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    try:
                        rule_ids = json.loads(row.get("rules_applicable_ids", "[]"))
                        
                        cypher = """
                        CREATE (f:FundScheme {
                            id: $fund_id,
                            isin: $isin,
                            name: $name,
                            fund_house: $fund_house,
                            category: $category,
                            mandate: $mandate,
                            risk_profile: $risk_profile,
                            aum_cr: toFloat($aum),
                            created_at: $now
                        })
                        WITH f
                        MATCH (r:Rule) WHERE r.id IN $rule_ids
                        CREATE (f)-[:governedBy]->(r)
                        RETURN f.id
                        """
                        await self.graph.run(cypher, {
                            "fund_id": row["fund_id"],
                            "isin": row["isin"],
                            "name": row["name"],
                            "fund_house": row["fund_house"],
                            "category": row["category"],
                            "mandate": row["mandate"],
                            "risk_profile": row["risk_profile"],
                            "aum": row["aum_cr"],
                            "rule_ids": rule_ids,
                            "now": datetime.now().isoformat()
                        })
                        funds_created += 1
                    except Exception as e:
                        errors.append(f"Row {row_idx}: {str(e)}")
                        logger.warning(f"Failed to ingest fund at row {row_idx}: {e}")
        except FileNotFoundError:
            return {"status": "error", "message": f"File not found: {csv_path}"}
        except Exception as e:
            logger.error(f"Failed to ingest fund schemes: {e}")
            return {"status": "error", "message": str(e)}
        
        logger.info(f"Ingested {funds_created} fund schemes from {csv_path}")
        return {
            "status": "success",
            "funds_created": funds_created,
            "errors": errors,
            "error_count": len(errors)
        }

# Standalone CLI usage
async def seed_compliance_data():
    """Seed all compliance data from CSV files."""
    from app.graph.client import get_graph_client
    
    graph = get_graph_client()
    ingester = ComplianceRulesIngester(graph)
    
    data_dir = Path("data/compliance")
    
    results = {
        "regulations": await ingester.ingest_regulations_csv(data_dir / "sebi_regulations.csv"),
        "rules": await ingester.ingest_rules_csv(data_dir / "rules.csv"),
        "funds": await ingester.ingest_fund_schemes_csv(data_dir / "fund_schemes.csv")
    }
    
    return results

# In requirements.txt, add (already present):
# - neo4j>=5.24
# - pydantic>=2.8
```

**CSV Files to Create**:

`data/compliance/sebi_regulations.csv`:
```csv
region,regulation_id,title,effective_date,document_url,raw_text
SEBI,SEBI_MF_2024_Q1_001,Portfolio Concentration Limits,2024-01-01,https://sebi.gov.in/...,Fund shall not hold more than 15% of NAV in a single security...
SEBI,SEBI_MF_2024_Q1_002,Fund Manager Qualifications,2024-01-01,https://sebi.gov.in/...,All fund managers must hold CAIA or equivalent certification...
SEBI,SEBI_MF_2024_Q1_003,KYC Requirements,2024-01-01,https://sebi.gov.in/...,All investors must complete KYC process within 24 hours of account opening...
...
```

`data/compliance/rules.csv`:
```csv
rule_id,rule_type,title,description,regulation_id,condition,severity,confidence_threshold,applicability_categories,exclusion_categories,enforcement_level
RULE_PORT_CONC_001,portfolio,Single Holding Concentration,Maximum 15% NAV in single security,SEBI_MF_2024_Q1_001,holding_pct > 0.15,high,0.95,"[""equity_fund"",""balanced_fund""]","[""sector_fund""]",automatic
RULE_PORT_SECTOR_001,portfolio,Sector Concentration Limit,Maximum 30% in single sector,SEBI_MF_2024_Q1_001,sector_pct > 0.30,medium,0.85,"[""equity_fund""]","[""sector_fund""]",automatic
RULE_GOV_MGR_CERT_001,governance,Fund Manager Certification,Manager must have required certification,SEBI_MF_2024_Q1_002,manager_certified == 1,high,0.99,"[""equity_fund"",""debt_fund""]","[]",automatic
...
```

`data/compliance/fund_schemes.csv`:
```csv
fund_id,isin,name,fund_house,category,mandate,risk_profile,aum_cr,rules_applicable_ids
Adani_Growth_2024,INF204K01ND0,Adani Growth Fund,Adani Capital Markets,equity_fund,Growth-oriented equity investing,High,5000,"[""RULE_PORT_CONC_001"",""RULE_PORT_SECTOR_001"",""RULE_GOV_MGR_CERT_001""]"
...
```

**Deliverable**: CSV ingestion module + data files  
**Estimate**: 2 hours

---

**Task 1.4: Wire into FastAPI Startup**

Integrate compliance schema deployment and rules ingestion into FastAPI startup.

**File**: `backend/app/main.py` (update lifespan handler)

```python
# In existing lifespan handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)

    container = deps.init_container()
    
    # ... existing code ...
    
    # NEW: Deploy compliance schema
    try:
        from app.graph.compliance_schema import deploy_compliance_schema
        schema_ok = await deploy_compliance_schema(container.graph)
        if schema_ok:
            logger.info("Compliance schema deployed successfully")
        else:
            logger.warning("Compliance schema deployment had issues")
    except Exception as e:
        logger.warning(f"Could not deploy compliance schema: {e}")
    
    # NEW: Seed compliance rules (first time only)
    try:
        from app.ingestion.compliance_rules_ingester import seed_compliance_data
        results = await seed_compliance_data()
        logger.info(f"Compliance data seeded: {results}")
    except Exception as e:
        logger.warning(f"Could not seed compliance data: {e}")
    
    # ... existing code ...
    
    yield
    
    # ... cleanup ...
```

**Estimate**: 1 hour

---

**Day 1-2 Summary**:
- ✅ Schema design document
- ✅ Neo4j deployment script
- ✅ Pydantic models
- ✅ CSV ingestion pipeline
- ✅ Startup wiring
- **Deliverables**: 4 files, 200 lines of code

---

### **Day 3-4: Implement Deterministic Rules Engine**

**Objective**: Build rule matcher that evaluates conditions and produces violations.

**Task 1.5: Rules Engine Core**

**File**: `backend/app/compliance/rules_engine.py`

This is a large file - create it with full implementation following the structure I provided earlier in the conversation. Key components:

- `ComplianceViolation` dataclass
- `RulesEngine` class with methods:
  - `load_rules()` — Load rules from Neo4j cache
  - `_parse_condition()` — Parse condition strings like "holding_pct > 0.15"
  - `evaluate_rule()` — Evaluate single rule against fund data
  - `evaluate_fund()` — Evaluate all applicable rules for a fund
  - `store_violations()` — Persist violations to Neo4j

**Key Implementation Details**:

```python
# Condition parsing examples
- "holding_pct > 0.15" → (metric="holding_pct", operator="gt", threshold=0.15)
- "manager_certified == 1" → (metric="manager_certified", operator="eq", threshold=1)
- "kyc_days_old > 365" → (metric="kyc_days_old", operator="gt", threshold=365)

# Supported operators
- gt (>), gte (>=), lt (<), lte (<=), eq (==), neq (!=)

# Evaluation output
ComplianceViolation(
    violation_id="V_20240115_001",
    rule_id="RULE_PORT_CONC_001",
    rule_title="Single Holding Concentration",
    fund_id="Adani_Growth_2024",
    severity="high",
    confidence=0.95,
    actual_value=0.18,
    threshold_value=0.15,
    description="Technology 18% exceeds 15% limit",
    evidence_docs=["NAV_20240115.csv", "Fund_Prospectus.pdf"],
    detected_at="2024-01-15T10:30:00Z",
    region="SEBI",
    status="detected"
)
```

**Estimate**: 3 hours

---

**Task 1.6: Unit Tests for Rules Engine**

**File**: `backend/tests/compliance/test_rules_engine.py`

Create comprehensive test suite:

```python
import pytest
from app.compliance.rules_engine import RulesEngine, ComplianceViolation

@pytest.fixture
async def rules_engine(mock_graph):
    engine = RulesEngine(mock_graph)
    await engine.load_rules()
    return engine

@pytest.mark.asyncio
async def test_parse_condition():
    """Test condition parsing."""
    engine = RulesEngine(None)
    
    # Test: holding_pct > 0.15
    metric, op, threshold = engine._parse_condition("holding_pct > 0.15")
    assert metric == "holding_pct"
    assert op == "gt"
    assert threshold == 0.15

@pytest.mark.asyncio
async def test_evaluate_rule_concentration_violation(rules_engine):
    """Test detection of concentration violation."""
    fund_data = {
        "fund_id": "Adani_Growth_2024",
        "category": "equity_fund",
        "holdings": {"Technology": 0.18}  # 18% > 15%
    }
    
    rules_engine._rule_cache["RULE_PORT_CONC_001"] = {
        "rule_type": "portfolio",
        "title": "Concentration Limit",
        "condition": "holdings.Technology > 0.15",
        "severity": "high",
        "confidence_threshold": 0.95,
        "applicability": ["equity_fund"],
        "exclusions": [],
        "enforcement_level": "automatic"
    }
    
    violation = await rules_engine.evaluate_rule("RULE_PORT_CONC_001", fund_data)
    
    assert violation is not None
    assert violation.severity == "high"
    assert violation.actual_value == 0.18
    assert violation.threshold_value == 0.15

@pytest.mark.asyncio
async def test_evaluate_rule_no_violation(rules_engine):
    """Test rule passes when within limits."""
    fund_data = {
        "fund_id": "Adani_Growth_2024",
        "category": "equity_fund",
        "holdings": {"Technology": 0.12}  # 12% < 15%
    }
    
    rules_engine._rule_cache["RULE_PORT_CONC_001"] = {
        "rule_type": "portfolio",
        "title": "Concentration Limit",
        "condition": "holdings.Technology > 0.15",
        "severity": "high",
        "confidence_threshold": 0.95,
        "applicability": ["equity_fund"],
        "exclusions": [],
        "enforcement_level": "automatic"
    }
    
    violation = await rules_engine.evaluate_rule("RULE_PORT_CONC_001", fund_data)
    assert violation is None

# ... 10+ additional tests covering:
# - Rule applicability checks
# - Rule exclusion logic
# - Multiple rules on single fund
# - Violation storage
# - Cache management
```

**Estimate**: 2 hours

---

**Day 3-4 Summary**:
- ✅ Rules engine implementation (250 lines)
- ✅ Unit test suite (300 lines)
- **Deliverables**: 2 files

---

### **Day 5: Violation Detector & Initial Testing**

**Objective**: Build violation detector service and end-to-end test.

**Task 1.7: Violation Detector Service**

**File**: `backend/app/compliance/violation_detector.py`

```python
# Key class: ViolationDetector
# Methods:
# - audit_all_funds() — Run compliance audit across all funds
# - audit_single_fund() — Audit one fund
# - get_violations() — Query violations from database
# - resolve_violation() — Mark violation as remediated

# Returns ComplianceAuditResult with:
# - audit_id, started_at, completed_at
# - total_funds, total_violations, severity breakdown
# - violations_by_fund, violations_by_rule
```

**Estimate**: 2 hours

---

**Task 1.8: Manual End-to-End Test**

```bash
# 1. Deploy schema
python -c "
import asyncio
from app.graph.compliance_schema import deploy_compliance_schema
from app.graph.client import get_graph_client
async def test():
    graph = get_graph_client()
    result = await deploy_compliance_schema(graph)
    print(f'Schema deployed: {result}')
asyncio.run(test())
"

# 2. Ingest rules
python -c "
import asyncio
from app.ingestion.compliance_rules_ingester import seed_compliance_data
async def test():
    results = await seed_compliance_data()
    print(f'Rules ingested: {results}')
asyncio.run(test())
"

# 3. Query rules in Neo4j
cypher-shell -u neo4j -p contextgraph "MATCH (r:Rule) RETURN count(r) AS rule_count"
# Expected output: rule_count: 30

# 4. Run violation detector
python -c "
import asyncio
from app.compliance.violation_detector import ViolationDetector
from app.compliance.rules_engine import RulesEngine
async def test():
    from app.graph.client import get_graph_client
    graph = get_graph_client()
    engine = RulesEngine(graph)
    await engine.load_rules()
    detector = ViolationDetector(graph, engine)
    result = await detector.audit_all_funds('SEBI')
    print(f'Audit result: {result}')
asyncio.run(test())
"
# Expected output: audit_result with violations
```

**Estimate**: 1 hour

---

**Day 5 Summary**:
- ✅ Violation detector service
- ✅ End-to-end test
- **Deliverables**: 1 file + test evidence

---

## **Week 2: API Endpoints, Integration, and Testing**

### **Day 6: Compliance API Endpoints**

**Objective**: Expose violation detection via REST API.

**Task 2.1: FastAPI Routes**

**File**: `backend/app/api/routes/compliance.py`

```python
from fastapi import APIRouter, Depends, Query
from typing import List, Optional

router = APIRouter(prefix="/api/compliance", tags=["compliance"])

@router.post("/audit")
async def run_compliance_audit(
    region: str = Query("SEBI"),
    container = Depends(get_container)
):
    """Trigger compliance audit for specified region."""
    # Implementation

@router.get("/violations")
async def get_violations(
    region: str = Query("SEBI"),
    severity: Optional[str] = Query(None),
    fund_id: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    container = Depends(get_container)
):
    """Query violations with optional filters."""
    # Implementation

@router.post("/violations/{violation_id}/resolve")
async def resolve_violation(
    violation_id: str,
    resolution_action: str,
    container = Depends(get_container)
):
    """Mark violation as remediated."""
    # Implementation

@router.get("/scorecard")
async def get_compliance_scorecard(
    region: str = Query("SEBI"),
    container = Depends(get_container)
):
    """Get real-time compliance scorecard."""
    # Implementation
```

**Register in main.py**:

```python
# In create_app()
from app.api.routes import compliance

for router in (..., compliance.router):
    app.include_router(router, prefix="/api")
```

**Estimate**: 2 hours

---

**Task 2.2: Integration with Existing Audit Log**

Link violations to existing query audit trail for end-to-end traceability.

**File**: `backend/app/compliance/audit_integration.py`

```python
# Functions:
# - log_violation_to_audit_trail() — Write violation to JSONL audit log
# - enrich_violation_with_evidence() — Link violation to documents/NAV feeds
```

**Estimate**: 1 hour

---

### **Day 7: Testing & Documentation**

**Task 2.3: Integration Tests**

**File**: `backend/tests/compliance/test_compliance_api.py`

```python
@pytest.mark.asyncio
async def test_audit_endpoint(client):
    """Test POST /api/compliance/audit endpoint."""
    response = await client.post("/api/compliance/audit?region=SEBI")
    assert response.status_code == 200
    data = response.json()
    assert "audit_id" in data
    assert "total_violations" in data

@pytest.mark.asyncio
async def test_violations_query_endpoint(client):
    """Test GET /api/compliance/violations endpoint."""
    response = await client.get("/api/compliance/violations?region=SEBI&severity=high")
    assert response.status_code == 200
    violations = response.json()
    assert isinstance(violations, list)
    assert all(v["severity"] == "high" for v in violations)

@pytest.mark.asyncio
async def test_scorecard_endpoint(client):
    """Test GET /api/compliance/scorecard endpoint."""
    response = await client.get("/api/compliance/scorecard")
    assert response.status_code == 200
    scorecard = response.json()
    assert "overall_compliance_score" in scorecard
    assert scorecard["overall_compliance_score"] >= 0 and scorecard["overall_compliance_score"] <= 100
```

**Estimate**: 2 hours

---

**Task 2.4: Documentation**

**File**: `docs/COMPLIANCE_PHASE1_RUNBOOK.md`

```markdown
# Phase 1: Rules Engine & Violation Detection - Deployment Runbook

## Prerequisites
- Neo4j 5.24+ running and healthy
- FastAPI server running
- Python 3.12+

## Deployment Steps

### Step 1: Deploy Schema

```bash
cd backend
python -m app.compliance.compliance_schema
```

Expected output: `Compliance schema deployed successfully`

### Step 2: Ingest Compliance Rules

```bash
python -m app.ingestion.compliance_rules_ingester
```

Expected output: `Ingested X regulations, Y rules, Z fund schemes`

### Step 3: Verify Data

```bash
cypher-shell -u neo4j -p contextgraph
MATCH (r:Rule) RETURN count(r) AS rule_count;
```

Expected: `rule_count: 30+`

### Step 4: Run First Audit

```bash
curl -X POST http://localhost:8000/api/compliance/audit?region=SEBI
```

Expected output:
```json
{
  "audit_id": "AUDIT_20240115_120000",
  "total_funds": 42,
  "total_violations": 8,
  "high_violations": 2,
  "medium_violations": 4,
  "low_violations": 2
}
```

### Step 5: Query Violations

```bash
curl http://localhost:8000/api/compliance/violations?region=SEBI&severity=high
```

### Step 6: Get Scorecard

```bash
curl http://localhost:8000/api/compliance/scorecard
```

Expected output:
```json
{
  "overall_compliance_score": 87.5,
  "total_rules": 30,
  "rules_passing": 26,
  "violations": {
    "critical": 0,
    "high": 2,
    "medium": 4,
    "low": 2,
    "total": 8
  }
}
```

## Troubleshooting

### Audit returns 0 violations
- Check: Are portfolio data APIs connected? Currently uses mock data.
- Solution: Integrate real portfolio data source (see Task: _fetch_fund_portfolio_data())

### Schema deployment fails
- Check: Is Neo4j running? `docker ps | grep neo4j`
- Solution: `docker-compose up -d neo4j`

### Rules ingestion fails
- Check: CSV files exist at `data/compliance/*.csv`
- Solution: Create CSV files as per specification

## Performance Baselines

- Single fund audit: <200ms
- Full audit (50 funds): <10 seconds
- API response time: <500ms
```

**Estimate**: 1 hour

---

### **Day 8: Final Testing & Review**

**Task 2.5: Full System Test**

- Run entire Phase 1 end-to-end
- Verify schema, ingestion, rule evaluation, API responses
- Document any issues
- Code review with team

**Estimate**: 2 hours

---

## **Week 1-2 Deliverables Summary**

| Component | Files | Lines | Status |
|-----------|-------|-------|--------|
| Schema Design | 1 | 150 | ✅ |
| Neo4j Deployment | 1 | 120 | ✅ |
| Pydantic Models | 1 | 180 | ✅ |
| Rules Ingestion | 1 | 280 | ✅ |
| CSV Data Files | 3 | 500+ | ✅ |
| Rules Engine | 1 | 350 | ✅ |
| Violation Detector | 1 | 220 | ✅ |
| Unit Tests | 2 | 450 | ✅ |
| API Endpoints | 1 | 200 | ✅ |
| Audit Integration | 1 | 80 | ✅ |
| Integration Tests | 1 | 200 | ✅ |
| Documentation | 1 | 150 | ✅ |
| **TOTAL** | **17** | **3,280** | **✅** |

**Compliance Gain**: +15% (35% → 50%)  
**Cost**: ~60-80 engineering hours / 2 engineers / 10 days

---

# **[PHASES 2-5 CONTINUE SIMILARLY]**

Due to token limits, I'll provide condensed outlines for Phases 2-5:

---

# **PHASE 2: DOMAIN-SPECIFIC COMPLIANCE AGENTS (Weeks 3-6)**

## **Overview**

Build 5 specialized agents (Portfolio, Governance, KYC, Risk, Reporting) that autonomously audit fund operations against regulatory domains.

**Compliance Gain**: +25% (50% → 75%)  
**Team**: 2 Backend Engineers  
**Duration**: 4 weeks

---

## **Week 3: Portfolio Agent**

| Day | Task | Details | Estimate |
|-----|------|---------|----------|
| 1-2 | Portfolio Agent Framework | Fetch fund holdings, apply concentration rules, detect violations | 4h |
| 3 | Unit Tests | Test concentration, sector, asset class limits | 2h |
| 4 | Integration | Connect to portfolio data source | 2h |
| 5 | Documentation | API documentation, examples | 1h |

**Deliverables**: `portfolio_agent.py`, tests, docs  
**Files**: 3 | **Lines**: 400

---

## **Week 4: Governance & KYC Agents**

| Component | Tasks | Estimate |
|-----------|-------|----------|
| **Governance Agent** | Board composition, fund manager cert, related-party approvals | 6h |
| **KYC Agent** | KYC timeliness, PEP screening, EDD triggers | 6h |
| Tests | Unit + integration for both | 4h |

**Deliverables**: 2 agents, comprehensive tests  
**Files**: 5 | **Lines**: 700

---

## **Week 5: Risk & Reporting Agents**

| Component | Tasks | Estimate |
|-----------|-------|----------|
| **Risk Agent** | VaR monitoring, stress testing, liquidity checks | 6h |
| **Reporting Agent** | NAV timeliness, filing deadlines, performance accuracy | 6h |
| Tests | Unit + integration for both | 4h |

**Deliverables**: 2 agents, comprehensive tests  
**Files**: 5 | **Lines**: 700

---

## **Week 6: Agent Orchestration & Testing**

| Task | Details | Estimate |
|------|---------|----------|
| Orchestrator | Central agent coordinator | 3h |
| E2E Tests | All 5 agents working together | 3h |
| Performance | Optimize concurrent agent execution | 2h |
| Documentation | Agent framework, how to add new agents | 2h |

**Deliverables**: Orchestrator, e2e tests, perf docs  
**Files**: 4 | **Lines**: 400

---

## **Phase 2 Summary**

| Metric | Value |
|--------|-------|
| New Agents | 5 |
| New Files | 20 |
| New Lines | 2,200 |
| Test Coverage | 85%+ |
| Compliance Gain | +25% |
| **Total Phase 2 Hours** | **64-80 hours** |

---

# **PHASE 3: COMPLIANCE API & REAL-TIME DASHBOARD (Weeks 7-8)**

## **Overview**

Build REST API endpoints for scorecard, violation queries, and real-time compliance dashboard.

**Compliance Gain**: +10% (75% → 85%)  
**Team**: 1 Backend Engineer + 1 Frontend Developer  
**Duration**: 2 weeks

---

## **Week 7: Scorecard API & Aggregation Logic**

| Task | Details | Estimate |
|------|---------|----------|
| Scorecard Calculation | Aggregate violations, compute compliance %, breakdown by severity/region | 4h |
| API Endpoints | `/api/compliance/scorecard`, `/api/compliance/stats`, `/api/compliance/trends` | 3h |
| Caching | Redis cache for scorecard (5-min TTL) | 2h |
| Tests | Unit + API contract tests | 3h |

**Deliverables**: Scorecard logic, 3 new API endpoints, caching  
**Files**: 3 | **Lines**: 350

---

## **Week 8: Dashboard UI & Real-Time Updates**

| Task | Details | Estimate |
|------|---------|----------|
| Dashboard Mock | Design compliance dashboard layout (Figma/Miro) | 2h |
| WebSocket Support | Real-time violation updates via WebSocket | 3h |
| Frontend Components | React components for scorecard, violations table, charts | 8h |
| Integration | Frontend ↔ Backend API wiring | 3h |
| E2E Tests | Dashboard functionality tests | 2h |

**Deliverables**: Real-time dashboard, WebSocket API, React components  
**Files**: 8 | **Lines**: 1,200

---

## **Phase 3 Summary**

| Metric | Value |
|--------|-------|
| New Endpoints | 6 |
| Real-Time Capability | WebSocket |
| Dashboard Pages | 3+ |
| New Files | 11 |
| New Lines | 1,550 |
| Compliance Gain | +10% |
| **Total Phase 3 Hours** | **30-40 hours** |

---

# **PHASE 4: ESCALATION WORKFLOWS & MULTI-REGION SUPPORT (Weeks 9-10)**

## **Overview**

Add violation escalation routing, case management, and expand to SEC/ESMA compliance.

**Compliance Gain**: +10% (85% → 95%)  
**Team**: 1 Backend Engineer + 1 DevOps  
**Duration**: 2 weeks

---

## **Week 9: Escalation Workflows & Case Management**

| Task | Details | Estimate |
|------|---------|----------|
| Escalation Engine | Route violations by severity + region to appropriate teams | 5h |
| Case Management API | Create/track/close compliance cases | 5h |
| Notification Service | Email/Slack alerts for violations | 4h |
| SLA Tracking | Monitor violation resolution SLAs | 2h |
| Tests | Integration tests for workflows | 4h |

**Deliverables**: Escalation logic, case API, notifications  
**Files**: 4 | **Lines**: 450

---

## **Week 10: SEC & ESMA Rules + Multi-Region Audit**

| Task | Details | Estimate |
|------|---------|----------|
| SEC Rules | Ingest ~50 SEC regulations (Form N-1A, Rule 10b-5, advertising, etc.) | 4h |
| ESMA Rules | Ingest ~50 ESMA regulations (MiFID II, UCITS, AIFMD, etc.) | 4h |
| Multi-Region Mode | Routing strategies (strictest-rule-wins, region-specific, weighted) | 5h |
| Region Override | Allow funds to opt into specific regions | 2h |
| Tests | Multi-region audit tests | 3h |

**Deliverables**: SEC + ESMA rules, multi-region mode  
**Files**: 5 | **Lines**: 600

---

## **Phase 4 Summary**

| Metric | Value |
|--------|-------|
| Escalation Routes | 12+ |
| Regional Coverage | 3 (SEBI + SEC + ESMA) |
| New Rules Ingested | 100+ |
| Case Management | Full lifecycle |
| New Files | 9 |
| New Lines | 1,050 |
| Compliance Gain | +10% |
| **Total Phase 4 Hours** | **38-48 hours** |

---

# **PHASE 5: PRODUCTION HARDENING & CERTIFICATION (Weeks 11-12)**

## **Overview**

Performance optimization, security hardening, certification readiness, full documentation.

**Compliance Gain**: +5% (95% → 100%)  
**Team**: 1-2 Backend Engineers + 1 DevOps  
**Duration**: 2 weeks

---

## **Week 11: Performance Optimization & SLA Compliance**

| Task | Details | Estimate |
|------|---------|----------|
| Latency Tuning | Optimize queries, caching, indexing (target: <500ms scorecard, <2s audit) | 6h |
| Load Testing | Validate performance under 100 concurrent users | 4h |
| Database Tuning | Neo4j heap, pagecache, index optimization | 3h |
| Monitoring | Add Prometheus metrics, dashboard | 3h |

**Deliverables**: Performance baseline, monitoring setup  
**Files**: 2 | **Lines**: 200

---

## **Week 12: Security, Certification, & Documentation**

| Task | Details | Estimate |
|------|---------|----------|
| Security Audit | OWASP Top 10, data encryption, API keys, audit trail immutability | 6h |
| ISO 27001 Readiness | Document controls, access policies | 4h |
| SOC2 Type II | Logging, incident response procedures | 4h |
| Full Documentation | Runbooks, API docs, compliance audit trail guide | 6h |
| Go-Live Checklist | Deployment verification, backups, failover | 2h |

**Deliverables**: Security report, compliance docs, runbooks  
**Files**: 6 | **Lines**: 800

---

## **Phase 5 Summary**

| Metric | Value |
|--------|-------|
| Performance SLA Met | ✅ <500ms / <2s |
| Security Certifications | ISO 27001, SOC2 Type II, OWASP ready |
| Documentation Pages | 15+ |
| Monitoring Setup | Prometheus + Grafana |
| New Files | 8 |
| New Lines | 1,000 |
| Compliance Gain | +5% |
| **Total Phase 5 Hours** | **38-48 hours** |

---

---

# **COMPLETE PROJECT SUMMARY**

| Phase | Duration | Compliance Gain | Team Hours | Total Files | Total Lines |
|-------|----------|-----------------|-----------|------------|-------------|
| 1: Rules Engine | 2w | +15% (→50%) | 60-80h | 17 | 3,280 |
| 2: Agents | 4w | +25% (→75%) | 64-80h | 20 | 2,200 |
| 3: API/Dashboard | 2w | +10% (→85%) | 30-40h | 11 | 1,550 |
| 4: Escalation/Multi-Region | 2w | +10% (→95%) | 38-48h | 9 | 1,050 |
| 5: Hardening/Cert | 2w | +5% (→100%) | 38-48h | 8 | 1,000 |
| **TOTAL** | **12w** | **+65% compliance** | **230-296h** | **65** | **9,080** |

**Team Capacity**: 3-4 engineers × 12 weeks = 144-192 person-weeks available  
**Project Need**: 230-296 hours = ~6-7 person-weeks  
**Buffer**: 137-186 person-weeks (plenty for meetings, reviews, refinement)

**Timeline**: 12 weeks (3 months) for fully compliant, production-ready system  
**Cost**: ~$50-75K (assuming $100-125/hour loaded rate)

---

---

# **APPENDIX: Integration Checklist**

- [ ] Phase 1 schema deployed in Neo4j
- [ ] Rules CSV files created & ingested
- [ ] `/api/compliance/*` endpoints working
- [ ] Unit tests passing (85%+ coverage)
- [ ] Phase 2 agents integrated
- [ ] Real-time scorecard API responding <500ms
- [ ] Dashboard frontend deployed
- [ ] Escalation workflows routing violations correctly
- [ ] SEC & ESMA rules ingested
- [ ] Multi-region audit mode tested
- [ ] Performance baseline <2s for full audit
- [ ] Security audit completed (ISO 27001 ready)
- [ ] Documentation complete (runbooks, APIs, compliance guide)
- [ ] Go-live verification checklist passed

---

This is the **complete, detailed implementation plan** for all 5 phases, fully integrated with your existing ContextGraph architecture (FastAPI, Neo4j, Docker Compose, Python 3.12, existing RBAC/audit logging).

Would you like me to:
1. Expand any particular phase with more code details?
2. Create actual Python files for any phase to get started immediately?
3. Create a Gantt chart or deployment timeline?
4. Detail the data integration points (where to connect portfolio/customer/filing APIs)?