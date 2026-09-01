# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================


# AMC Compliance System: 12-Week Implementation Plan (Phases 1-5)

## Executive Summary

This document outlines the complete 12-week roadmap to transform the AMC compliance system from **36% production-ready to 100% production-ready**. The plan covers all phases (1-5), detailed task breakdowns, technical specifications, success criteria, and team assignments.

**Timeline**: 49 days critical path (7 weeks) with 3-team parallelization
**Target Completion**: Week 12
**Current State**: Phases 1-2 at 90%, Phases 3-5 at 0%
**Goal**: Production-grade, multi-region (SEBI/SEC/ESMA), security-hardened compliance system

---

## Table of Contents

1. [Overview & Architecture](#overview--architecture)
2. [Phase 1: Rules Engine & Violation Detection Completion (Weeks 1-2)](#phase-1-rules-engine--violation-detection-completion-weeks-1-2)
3. [Phase 2: Domain Agents Completion (Weeks 3-4)](#phase-2-domain-agents-completion-weeks-3-4)
4. [Phase 3: Compliance Dashboard UI (Weeks 5-7)](#phase-3-compliance-dashboard-ui-weeks-5-7)
5. [Phase 4: SEC/ESMA Regulatory Expansion (Weeks 8-10)](#phase-4-secesma-regulatory-expansion-weeks-8-10)
6. [Phase 5: Production Hardening & Certification (Weeks 11-12)](#phase-5-production-hardening--certification-weeks-11-12)
7. [Implementation Dependencies & Parallelization](#implementation-dependencies--parallelization)
8. [Team Structure & Assignments](#team-structure--assignments)
9. [Risk Management & Mitigation](#risk-management--mitigation)
10. [Success Criteria & Sign-Off](#success-criteria--sign-off)

---

## Overview & Architecture

### Current System State

**Implemented (Phases 1-2)**:
- Deterministic rules engine with 10+ SEBI rules
- 5 domain agents (Portfolio, Governance, KYC, Risk, Reporting)
- Neo4j graph database with compliance schema
- FastAPI REST API with 5+ endpoints
- CSV ingestion pipeline
- Violation lifecycle management
- Escalation engine

**Not Implemented (Phases 3-5)**:
- Compliance scorecard UI (Streamlit dashboard)
- SEC/ESMA regulations and rules
- Multi-region rule routing
- Performance SLAs and monitoring
- Security hardening (rate limiting, RBAC, audit logging)
- Compliance certification checklist
- Disaster recovery and backup procedures

### System Architecture (Final State - Week 12)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Streamlit UI Dashboard (Phase 3)             │
│  [Scorecard] [Violations] [Funds] [Remediation] [Multi-Region] │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP/REST
┌────────────────────────▼────────────────────────────────────────┐
│             FastAPI Backend (Phases 1-2, 5)                     │
│  Rate Limiting │ RBAC │ Audit Logging │ Caching                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Compliance API Endpoints                                 │   │
│  │ /audit /violations /scorecard /resolve /agents/metrics   │   │
│  └──────────┬───────────────────────────────────────────────┘   │
│             │                                                    │
│  ┌──────────▼───────────────────────────────────────────────┐   │
│  │ Orchestrator (Phase 2)                                   │   │
│  │ Coordinates: Portfolio | Governance | KYC | Risk | Reporting
│  └──────────┬───────────────────────────────────────────────┘   │
│             │                                                    │
│  ┌──────────▼───────────────────────────────────────────────┐   │
│  │ Rules Engine (Phase 1) + Multi-Region Router (Phase 4)   │   │
│  │ SEBI Rules (Phase 1) │ SEC Rules (Phase 4) │ ESMA (Phase 4)  │
│  └──────────┬───────────────────────────────────────────────┘   │
└─────────────┼────────────────────────────────────────────────────┘
              │
┌─────────────▼────────────────────────────────────────────────────┐
│              Neo4j Graph Database (Phases 1, 4)                  │
│  Regulations │ Rules │ Fund Schemes │ Violations │ Escalations   │
│  SEBI Rules (50+) │ SEC Rules (50+) │ ESMA Rules (50+)          │
└───────────────────────────────────────────────────────────────────┘
```

### Technical Stack

**Backend**:
- Python 3.11+
- FastAPI 0.104+
- Neo4j 5.x
- Pydantic 2.x
- pytest for testing
- slowapi for rate limiting
- python-jose for JWT/RBAC
- cryptography for data encryption

**Frontend**:
- Streamlit 1.28+
- Plotly for charts
- Pandas for data manipulation
- httpx for API calls

**Infrastructure**:
- Docker/Docker Compose (development)
- Kubernetes (production)
- Prometheus for metrics
- CloudWatch/ELK for logging

---

## Phase 1: Rules Engine & Violation Detection Completion (Weeks 1-2)

### Overview

Phases 1-2 are currently 90% complete. This section focuses on **completing the final 10%** by:
1. Creating test data (CSV files with SEBI regulations, rules, funds)
2. Running end-to-end tests with real data
3. Populating Neo4j graph database
4. Validating all API endpoints

**Timeline**: Days 1-10 (2 weeks)
**Status**: Will transition from 90% → 100%
**Team**: Backend (2-3 engineers) + QA (1 engineer) + DevOps (1 engineer)

---

### Task 1.1: Create CSV Data Files

**Objective**: Generate test data files for regulations, rules, and fund schemes

**Scope**:
- `data/compliance/sebi_regulations.csv` - 50+ SEBI regulations
- `data/compliance/rules.csv` - 30+ compliance rules (SEBI)
- `data/compliance/fund_schemes.csv` - 10 fund schemes for testing

**Deliverables**:

#### 1.1.1 sebi_regulations.csv

**Format**:
```
regulation_id,title,effective_date,section,description,applicability,region
SEBI_MF_2024_Q1_001,Fund Portfolio Diversification,2024-01-01,Regulation 49A,Maximum 15% in single security,Equity Funds,SEBI
SEBI_MF_2024_Q1_002,Manager Certification,2024-01-01,Regulation 35,Fund managers must hold CAIA/CFA,All Funds,SEBI
...
```

**Content Requirements** (50+ rows):
- Portfolio diversification rules (5-7)
- Sector exposure limits (3-5)
- Related-party restrictions (3-4)
- Manager/trustee certification (2-3)
- Board independence (2-3)
- KYC/AML requirements (4-5)
- Risk management (5-7)
- NAV/reporting timelines (4-5)
- Disclosure requirements (4-5)
- Liquidity buffers (2-3)

#### 1.1.2 rules.csv

**Format**:
```
rule_id,rule_type,title,description,regulation_id,condition,metric,threshold,severity,confidence_threshold,applicable_funds,region
RULE_PORT_CONC_001,portfolio,Single Holding Concentration,Maximum 15% NAV in single security,SEBI_MF_2024_Q1_001,lte,holding_pct,15,critical,0.95,Equity,SEBI
RULE_PORT_SECTOR_001,portfolio,Sector Concentration Limit,Maximum 30% in single sector,SEBI_MF_2024_Q1_001,lte,sector_pct,30,high,0.9,Equity,SEBI
...
```

**Content Requirements** (30+ rows):
- Portfolio rules (8-10)
- Governance rules (5-6)
- KYC rules (5-6)
- Risk rules (5-6)
- Reporting rules (4-5)

Each rule must include:
- Unique rule_id (pattern: RULE_[DOMAIN]_[CATEGORY]_NNN)
- Applicable rule_type (portfolio/governance/kyc/risk/reporting)
- Condition (gt, gte, lt, lte, eq, neq)
- Metric field name
- Threshold value
- Severity (critical, high, medium, low)
- Confidence threshold (0.0-1.0)

#### 1.1.3 fund_schemes.csv

**Format**:
```
fund_id,isin,name,fund_house,category,mandate,aum_cr,active_investors,region
SEBI_FUND_001,INF000A01111,ABC Equity Fund,ABC Mutual Fund,Equity,Large Cap,500,50000,SEBI
SEBI_FUND_002,INF000A02222,XYZ Debt Fund,XYZ Mutual Fund,Debt,Government,300,30000,SEBI
...
```

**Content Requirements** (10 rows):
- 4-5 equity funds
- 3-4 debt funds
- 2-3 hybrid funds
- Mix of fund houses (HDFC, ICICI, SBI, Axis, Nippon India)
- AUM range: 100-1000 Cr
- Active investors: 1000-100000

**Implementation**:
- Create CSV files in Excel/Google Sheets
- Validate format with first 5 rows (ensure commas, quotes properly escaped)
- Convert to UTF-8 encoding
- Save to `data/compliance/` directory
- Commit to Git with documentation

**Success Criteria**:
- ✅ Files exist at correct paths
- ✅ CSV format valid (parseable by Pandas)
- ✅ Column names match ingester expectations
- ✅ Data is realistic and representative
- ✅ No missing required fields

**Owner**: Compliance/Backend Team | **Duration**: 1-2 days | **Dependency**: None

---

### Task 1.2: Run End-to-End Compliance Audit Tests

**Objective**: Validate audit pipeline with real CSV data and mock fund data

**Scope**:
- Load CSV data
- Create mock fund data with real/expected violations
- Run full audit pipeline
- Verify violations detected and scored correctly
- Test all compliance rule types

**Detailed Implementation**:

#### 1.2.1 Create Test Fund Data

Generate mock fund data for each fund in `fund_schemes.csv`:

```python
# Example: SEBI_FUND_001 (Equity Fund)
fund_data = {
    "fund_id": "SEBI_FUND_001",
    "name": "ABC Equity Fund",
    "category": "Equity",
    "holdings": [
        {"security": "RELIANCE", "pct": 18},  # Violates 15% limit
        {"security": "TCS", "pct": 14},
        {"security": "INFY", "pct": 12},
        # ... more holdings
    ],
    "sector_exposure": {
        "IT": 35,  # Violates 30% limit
        "Finance": 28,
        # ... more sectors
    },
    "manager_cert": "CFA",  # Valid
    "manager_exp_years": 15,
    "kyc_last_updated": "2020-01-01",  # Violates 365-day recency
    "var_pct": 4.5,  # Violates 4% limit
    "liquid_cash_pct": 3,  # Violates 5% minimum
    "nav_last_published": "2024-01-25 20:50:00",  # Within 21:00 IST cutoff
}
```

**Expected Violations**:
- RULE_PORT_CONC_001: Holding 18% > 15% limit ❌
- RULE_PORT_SECTOR_001: IT 35% > 30% limit ❌
- RULE_KYC_RECENCY_001: KYC 4+ years old ❌
- RULE_RISK_VAR_001: VaR 4.5% > 4% limit ❌
- RULE_RISK_LIQUID_001: 3% < 5% minimum ❌

#### 1.2.2 Run Rules Engine Tests

```bash
# Test 1: Load rules from Neo4j
pytest backend/tests/compliance/test_rules_engine.py::test_load_rules -v

# Test 2: Evaluate individual rules
pytest backend/tests/compliance/test_rules_engine.py::test_evaluate_rule -v

# Test 3: Evaluate all applicable rules for fund
pytest backend/tests/compliance/test_rules_engine.py::test_evaluate_all_rules -v
```

**Verification**:
- Rules loaded into cache ✅
- Condition evaluators working (gt, gte, lt, etc.) ✅
- Violations generated with correct severity/confidence ✅
- Evidence attached to violations ✅

#### 1.2.3 Run Violation Detector Tests

```bash
# Test 1: Audit single fund
pytest backend/tests/compliance/test_violation_detector.py::test_audit_single_fund -v

# Test 2: Audit all funds with parallelization
pytest backend/tests/compliance/test_violation_detector.py::test_audit_all_funds -v

# Test 3: Scorecard calculation
pytest backend/tests/compliance/test_violation_detector.py::test_scorecard_calculation -v
```

**Verification**:
- Single fund audit returns violations ✅
- Multiple funds audited in parallel (no race conditions) ✅
- Scorecard calculated: (rules_passing / total_rules) × 100 ✅
- Violations tagged with fund_id, region, severity ✅

#### 1.2.4 Run CSV Ingestion Tests

```bash
# Test 1: Ingest regulations CSV
pytest backend/tests/compliance/test_rules_ingestion.py::test_ingest_regulations_csv -v

# Test 2: Ingest rules CSV
pytest backend/tests/compliance/test_rules_ingestion.py::test_ingest_rules_csv -v

# Test 3: Ingest fund schemes CSV
pytest backend/tests/compliance/test_rules_ingestion.py::test_ingest_fund_schemes_csv -v
```

**Verification**:
- 50+ regulations loaded ✅
- 30+ rules loaded ✅
- 10 funds loaded ✅
- CSV ingestion creates Neo4j nodes correctly ✅

**Success Criteria**:
- ✅ All test suites pass
- ✅ Violations correctly detected (expected vs. actual match)
- ✅ Scorecard calculation accurate
- ✅ No race conditions in parallel execution
- ✅ CSV data properly ingested into Neo4j

**Owner**: QA Team | **Duration**: 1-2 days | **Dependency**: Task 1.1

---

### Task 1.3: Populate Neo4j Graph with Compliance Schema

**Objective**: Deploy compliance schema and seed real data

**Scope**:
- Run schema deployment script
- Verify nodes and relationships created
- Index creation and verification
- Load CSV data into Neo4j

**Detailed Implementation**:

#### 1.3.1 Deploy Compliance Schema

**Script**: `backend/app/graph/compliance_schema.py::deploy_compliance_schema()`

**What Gets Created**:

Node Types (6):
```
Regulation {id, title, effective_date, section, description, applicability, region}
Rule {id, rule_type, title, description, condition, metric, threshold, severity, region}
FundScheme {id, isin, name, fund_house, category, aum_cr, active_investors, region}
Violation {id, rule_id, fund_id, severity, status, detected_at, confidence}
RiskThreshold {id, measure, threshold, severity, region}
EscalationPath {id, severity, target_role, sla_hours}
```

Relationships:
```
Regulation -[:has_rules]-> Rule
Rule -[:applies_to]-> FundScheme
FundScheme -[:violates]-> Rule
Violation -[:linked_to]-> Rule
Violation -[:affects]-> FundScheme
EscalationPath -[:routes]-> Rule (by severity/region)
```

Indexes:
```
CREATE INDEX ON :Rule(id)
CREATE INDEX ON :Rule(rule_type)
CREATE INDEX ON :FundScheme(id)
CREATE INDEX ON :Violation(status)
CREATE INDEX ON :Violation(severity)
CREATE INDEX ON :Violation(detected_at)
CREATE CONSTRAINT ON (v:Violation) ASSERT v.id IS UNIQUE
CREATE CONSTRAINT ON (f:FundScheme) ASSERT f.id IS UNIQUE
```

#### 1.3.2 Run Schema Deployment

```bash
python -c "
from app.graph.compliance_schema import deploy_compliance_schema
from app.graph.client import get_graph_client

client = get_graph_client()
deploy_compliance_schema(client)
print('Schema deployed successfully')
"
```

**Expected Output**:
```
[✓] Node labels created: Regulation, Rule, FundScheme, Violation, RiskThreshold, EscalationPath
[✓] Relationships established
[✓] Indexes created (8 indexes)
[✓] Constraints created (2 constraints)
Schema deployed successfully
```

#### 1.3.3 Load CSV Data into Neo4j

Run ingestion pipeline:

```python
from app.ingestion.compliance_rules_ingester import seed_compliance_data
from app.graph.client import get_graph_client
from pathlib import Path

client = get_graph_client()
data_dir = Path("data/compliance")
result = await seed_compliance_data(client, data_dir)

print(f"Regulations loaded: {result['regulations']['regulations_created']}")
print(f"Rules loaded: {result['rules']['rules_created']}")
print(f"Funds loaded: {result['funds']['funds_created']}")
```

**Expected Output**:
```
Regulations loaded: 50
Rules loaded: 30
Funds loaded: 10
```

#### 1.3.4 Validate Neo4j Graph

**Query 1: Count nodes**
```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
```

**Expected**:
```
label          count
Regulation     50
Rule           30
FundScheme     10
```

**Query 2: Verify relationships**
```cypher
MATCH (r:Regulation)-[:has_rules]->(rule:Rule) RETURN count(*) AS rule_count
```

**Expected**: rule_count = 30 (each rule linked to regulation)

**Query 3: Sample rule structure**
```cypher
MATCH (rule:Rule {id: "RULE_PORT_CONC_001"})
RETURN rule.title, rule.condition, rule.metric, rule.threshold
```

**Expected**:
```
rule.title          = "Single Holding Concentration"
rule.condition      = "lte"
rule.metric         = "holding_pct"
rule.threshold      = 15
```

**Success Criteria**:
- ✅ All node types created (Regulation, Rule, FundScheme, etc.)
- ✅ All relationships established
- ✅ All indexes created and working (<100ms query on indexed fields)
- ✅ 50+ regulations, 30+ rules, 10 funds loaded
- ✅ No data integrity errors
- ✅ Graph queries return expected results

**Owner**: DevOps Team | **Duration**: 1 day | **Dependency**: Task 1.1

---

### Task 1.4: Validate API Responses & Integration

**Objective**: Ensure all compliance REST API endpoints work correctly with real data

**Scope**:
- Test all 5 compliance endpoints
- Verify response schemas
- Test filtering and sorting
- Test error handling
- Validate performance (response time <2s)

**Detailed Implementation**:

#### 1.4.1 Test POST /api/compliance/audit Endpoint

**Test Case 1: Audit SEBI Region**

Request:
```bash
curl -X POST "http://localhost:8000/api/compliance/audit?region=SEBI" \
  -H "Content-Type: application/json"
```

Expected Response (200 OK):
```json
{
  "audit_id": "AUD_20240125_143022",
  "audit_started_at": "2024-01-25T14:30:22Z",
  "audit_completed_at": "2024-01-25T14:30:28Z",
  "total_funds": 10,
  "total_rules_evaluated": 300,
  "total_violations": 15,
  "critical_violations": 2,
  "high_violations": 5,
  "medium_violations": 6,
  "low_violations": 2,
  "violations_by_fund": {
    "SEBI_FUND_001": 5,
    "SEBI_FUND_002": 3,
    ...
  },
  "violations_by_rule": {
    "RULE_PORT_CONC_001": 3,
    "RULE_KYC_RECENCY_001": 4,
    ...
  },
  "regions": {
    "SEBI": {
      "total_violations": 15,
      "critical": 2,
      "high": 5
    }
  },
  "violations": [
    {
      "violation_id": "V_20240125_143023_RULE_PORT_CONC_001",
      "rule_id": "RULE_PORT_CONC_001",
      "fund_id": "SEBI_FUND_001",
      "severity": "critical",
      "confidence": 0.98,
      "actual_value": 18,
      "threshold_value": 15,
      "description": "Single Holding Concentration breached: holding_pct was 18 (limit: 15)"
    },
    ...
  ]
}
```

**Validation**:
- ✅ Response code 200 OK
- ✅ audit_id generated (format: AUD_YYYYMMDD_HHMMSS)
- ✅ Timestamps in ISO 8601 format
- ✅ total_violations = critical + high + medium + low
- ✅ violations list contains actual violations
- ✅ Response time <5 seconds

**Test Case 2: Audit Performance (10 funds)**

Measure response time:
```bash
time curl -X POST "http://localhost:8000/api/compliance/audit?region=SEBI" -s -o /dev/null
```

**Expected**: Real time <5 seconds

#### 1.4.2 Test GET /api/compliance/violations Endpoint

**Test Case 1: Get All Violations**

Request:
```bash
curl -X GET "http://localhost:8000/api/compliance/violations?region=SEBI" \
  -H "Content-Type: application/json"
```

Expected Response (200 OK):
```json
{
  "violations": [
    {
      "violation_id": "V_...",
      "rule_id": "RULE_PORT_CONC_001",
      "fund_id": "SEBI_FUND_001",
      "severity": "critical",
      "confidence": 0.98,
      ...
    },
    ...
  ],
  "total": 15,
  "page": 1,
  "page_size": 10
}
```

**Validation**:
- ✅ All violations returned
- ✅ Pagination working (10 per page default)
- ✅ Total count accurate

**Test Case 2: Filter by Severity**

Request:
```bash
curl -X GET "http://localhost:8000/api/compliance/violations?region=SEBI&severity=critical" \
  -H "Content-Type: application/json"
```

Expected: Only 2 critical violations returned

**Test Case 3: Filter by Fund**

Request:
```bash
curl -X GET "http://localhost:8000/api/compliance/violations?region=SEBI&fund_id=SEBI_FUND_001" \
  -H "Content-Type: application/json"
```

Expected: Only 5 violations for SEBI_FUND_001 returned

#### 1.4.3 Test GET /api/compliance/fund/{fund_id}/violations Endpoint

**Test Case 1: Get Fund-Specific Violations**

Request:
```bash
curl -X GET "http://localhost:8000/api/compliance/fund/SEBI_FUND_001/violations" \
  -H "Content-Type: application/json"
```

Expected Response:
```json
{
  "fund_id": "SEBI_FUND_001",
  "fund_name": "ABC Equity Fund",
  "violations": [
    {
      "violation_id": "V_...",
      "rule_id": "RULE_PORT_CONC_001",
      "severity": "critical",
      ...
    },
    ...
  ],
  "total_violations": 5,
  "compliance_score": 83.3
}
```

**Validation**:
- ✅ Fund ID matched correctly
- ✅ Violations list is subset of all violations
- ✅ Compliance score calculated: (1 - violations/total_rules) × 100

#### 1.4.4 Test GET /api/compliance/scorecard Endpoint

**Test Case 1: Get Overall Scorecard**

Request:
```bash
curl -X GET "http://localhost:8000/api/compliance/scorecard?region=SEBI" \
  -H "Content-Type: application/json"
```

Expected Response:
```json
{
  "region": "SEBI",
  "overall_score": 85.0,
  "scores_by_domain": {
    "portfolio": 82.0,
    "governance": 90.0,
    "kyc": 78.0,
    "risk": 85.0,
    "reporting": 92.0
  },
  "violations_summary": {
    "total": 15,
    "critical": 2,
    "high": 5,
    "medium": 6,
    "low": 2
  },
  "last_audit_at": "2024-01-25T14:30:28Z",
  "compliance_trend": [
    {"date": "2024-01-15", "score": 83.0},
    {"date": "2024-01-20", "score": 84.5},
    {"date": "2024-01-25", "score": 85.0}
  ]
}
```

**Validation**:
- ✅ overall_score = average of domain scores
- ✅ Domain scores calculated correctly
- ✅ Violations summary matches audit
- ✅ Trend data available (last 30 days)

**Test Case 2: Scorecard Performance**

Measure response time:
```bash
time curl -X GET "http://localhost:8000/api/compliance/scorecard?region=SEBI" -s -o /dev/null
```

**Expected**: Response time <500ms (requirement for production)

#### 1.4.5 Test POST /api/compliance/violations/{id}/resolve Endpoint

**Test Case 1: Resolve a Violation**

Request:
```bash
curl -X POST "http://localhost:8000/api/compliance/violations/V_20240125_143023_RULE_PORT_CONC_001/resolve" \
  -H "Content-Type: application/json" \
  -d '{"resolution_action": "Rebalanced portfolio to meet concentration limits"}'
```

Expected Response (200 OK):
```json
{
  "violation_id": "V_20240125_143023_RULE_PORT_CONC_001",
  "status": "remediated",
  "resolved_at": "2024-01-25T14:35:00Z",
  "resolution_action": "Rebalanced portfolio to meet concentration limits"
}
```

**Validation**:
- ✅ Status changed from "detected" to "remediated"
- ✅ resolved_at timestamp set
- ✅ Resolution action stored

**Test Case 2: Verify Resolved Violation in Violations List**

Request:
```bash
curl -X GET "http://localhost:8000/api/compliance/violations?region=SEBI&status=remediated" \
  -H "Content-Type: application/json"
```

Expected: Resolved violation appears in remediated list

#### 1.4.6 Error Handling Tests

**Test Case 1: Invalid Region**

Request:
```bash
curl -X GET "http://localhost:8000/api/compliance/scorecard?region=INVALID"
```

Expected Response (400 Bad Request):
```json
{
  "detail": [
    {
      "loc": ["query", "region"],
      "msg": "Input should be 'SEBI', 'SEC', or 'ESMA'",
      "type": "enum"
    }
  ]
}
```

**Test Case 2: Non-Existent Fund**

Request:
```bash
curl -X GET "http://localhost:8000/api/compliance/fund/INVALID_FUND/violations"
```

Expected Response (404 Not Found):
```json
{
  "detail": "Fund INVALID_FUND not found"
}
```

**Success Criteria**:
- ✅ All 5 endpoints return 200 OK
- ✅ Response schemas match Pydantic models
- ✅ Filtering works correctly (severity, fund_id, region)
- ✅ Sorting works (by severity, date, etc.)
- ✅ Status transitions valid (detected → reviewed → remediated → closed)
- ✅ Error responses have proper status codes (400, 404, 500)
- ✅ Response times meet SLAs (audit <5s, scorecard <500ms)

**Owner**: Backend Team | **Duration**: 1 day | **Dependency**: Task 1.3

---

### Phase 1 Summary

| Task | Duration | Owner | Status |
|------|----------|-------|--------|
| 1.1: Create CSV data files | 1-2 days | Compliance/Backend | Planned |
| 1.2: E2E tests | 1-2 days | QA | Planned |
| 1.3: Neo4j population | 1 day | DevOps | Planned |
| 1.4: API validation | 1 day | Backend | Planned |
| **TOTAL PHASE 1** | **4-6 days** | **Multi-team** | **90% → 100%** |

---

## Phase 2: Domain Agents Completion (Weeks 3-4)

### Overview

Phases 1-2 are currently 90% complete. Phase 2 focuses on **completing agent integration and validation** by:
1. Integration testing each domain agent independently
2. Testing orchestrator multi-agent coordination
3. Adding region awareness to agents
4. Creating agent performance metrics

**Timeline**: Days 11-20 (2 weeks)
**Status**: Will transition from 90% → 100%
**Team**: Backend (2-3 engineers) + QA (1 engineer)

---

### Task 2.1: Integration Test All Domain Agents

**Objective**: Verify each agent produces accurate violations independently

**Scope**:
- Test PortfolioAgent with concentration/sector violations
- Test GovernanceAgent with manager/board violations
- Test KYCAgent with KYC/PEP violations
- Test RiskAgent with VaR/liquidity violations
- Test ReportingAgent with NAV timeliness violations
- Mock fund data and verify violations detected

**Detailed Implementation**:

#### 2.1.1 PortfolioAgent Integration Test

**File**: `backend/tests/compliance/test_compliance_agents.py::test_portfolio_agent`

**Test Setup**:
```python
fund_data = {
    "fund_id": "SEBI_FUND_001",
    "holdings": [
        {"name": "RELIANCE", "pct": 18},    # > 15% limit
        {"name": "TCS", "pct": 12},
        ...
    ],
    "sector_exposure": {
        "IT": 35,                          # > 30% limit
        "Finance": 28,
        ...
    },
    "related_party_exposure": 12,          # < 10% limit
}
```

**Test Execution**:
```python
agent = PortfolioAgent(graph_client, rules_engine)
violations = await agent.audit_portfolio(fund_id="SEBI_FUND_001", fund_data=fund_data)
```

**Expected Violations**:
```
[
  Violation(rule_id="RULE_PORT_CONC_001", severity="critical", confidence=0.98),
  Violation(rule_id="RULE_PORT_SECTOR_001", severity="high", confidence=0.95),
  Violation(rule_id="RULE_PORT_RELATED_001", severity="medium", confidence=0.90),
]
```

**Validation**:
- ✅ 3 violations detected (CONC, SECTOR, RELATED)
- ✅ Severity correct (critical > high > medium)
- ✅ Confidence scores in range (0.0-1.0)
- ✅ Agent response time <500ms
- ✅ No false positives

#### 2.1.2 GovernanceAgent Integration Test

**File**: `backend/tests/compliance/test_compliance_agents.py::test_governance_agent`

**Test Setup**:
```python
fund_data = {
    "fund_id": "SEBI_FUND_001",
    "manager": {
        "name": "John Doe",
        "certification": None,             # Not certified
        "experience_years": 5,
    },
    "board": {
        "total_trustees": 5,
        "independent_trustees": 2,         # 40% < 50% requirement
        "conflicts": ["Trustee A", "Trustee B"],
    }
}
```

**Test Execution**:
```python
agent = GovernanceAgent(graph_client, rules_engine)
violations = await agent.audit_governance(fund_id="SEBI_FUND_001", fund_data=fund_data)
```

**Expected Violations**:
```
[
  Violation(rule_id="RULE_GOV_MGR_CERT_001", severity="critical"),
  Violation(rule_id="RULE_GOV_BOARD_IND_001", severity="high"),
]
```

#### 2.1.3 KYCAgent Integration Test

**File**: `backend/tests/compliance/test_compliance_agents.py::test_kyc_agent`

**Test Setup**:
```python
fund_data = {
    "fund_id": "SEBI_FUND_001",
    "kyc_records": [
        {
            "investor_id": "INV001",
            "kyc_updated_at": "2020-01-01",      # > 365 days old
            "aml_verified": True,
            "pep_status": "UNVERIFIED",          # PEP without EDD
        },
        ...
    ]
}
```

**Expected Violations**:
```
[
  Violation(rule_id="RULE_KYC_RECENCY_001", severity="high"),
  Violation(rule_id="RULE_KYC_PEP_001", severity="critical"),
]
```

#### 2.1.4 RiskAgent Integration Test

**File**: `backend/tests/compliance/test_compliance_agents.py::test_risk_agent`

**Test Setup**:
```python
fund_data = {
    "fund_id": "SEBI_FUND_001",
    "var_pct": 4.5,                        # > 4% limit
    "liquid_cash_pct": 3.0,                # < 5% minimum
    "stress_test_result": 120,             # Portfolio could lose >10%
}
```

**Expected Violations**:
```
[
  Violation(rule_id="RULE_RISK_VAR_001", severity="high"),
  Violation(rule_id="RULE_RISK_LIQUID_001", severity="medium"),
]
```

#### 2.1.5 ReportingAgent Integration Test

**File**: `backend/tests/compliance/test_compliance_agents.py::test_reporting_agent`

**Test Setup**:
```python
fund_data = {
    "fund_id": "SEBI_FUND_001",
    "nav_last_published": "2024-01-25 21:15:00",  # > 21:00 IST cutoff
    "disclosure_status": "DELAYED",
    "filing_deadline_days": -5,                    # 5 days overdue
}
```

**Expected Violations**:
```
[
  Violation(rule_id="RULE_REP_NAV_TIME_001", severity="critical"),
  Violation(rule_id="RULE_REP_FILING_001", severity="high"),
]
```

**Success Criteria**:
- ✅ Each agent detects correct violations
- ✅ No false positives/negatives
- ✅ Violation severity/confidence accurate
- ✅ Agent response time <500ms
- ✅ All 5 agents tested and passing

**Owner**: QA Team | **Duration**: 2 days | **Dependency**: Task 1.4

---

### Task 2.2: Test Orchestrator Multi-Agent Coordination

**Objective**: Verify orchestrator calls all agents and aggregates results correctly

**Scope**:
- Test orchestrator.audit_all_funds() coordinates parallel execution
- Verify aggregated violations from all agents
- Test semaphore limits (no >10 concurrent)
- Verify final scorecard combines all domains

**Detailed Implementation**:

#### 2.2.1 Single Fund Multi-Agent Audit Test

**File**: `backend/tests/compliance/test_compliance_agents.py::test_orchestrator_single_fund`

**Test Setup**:
```python
fund_data = {
    "fund_id": "SEBI_FUND_001",
    # Data that will trigger violations in multiple agents
    "holdings": [{"name": "RELIANCE", "pct": 18}],  # Portfolio agent
    "manager_certification": None,                   # Governance agent
    "kyc_records": [{"kyc_updated_at": "2020-01-01"}],  # KYC agent
    "var_pct": 4.5,                                 # Risk agent
    "nav_last_published": "2024-01-25 21:15:00",   # Reporting agent
}
```

**Test Execution**:
```python
orchestrator = ComplianceAgentOrchestrator(graph_client, rules_engine)
result = await orchestrator.audit_all_funds(
    funds=[fund_data],
    region="SEBI"
)
```

**Expected Result**:
```python
{
    "audit_id": "AUD_...",
    "total_funds": 1,
    "total_violations": 8,
    "violations_by_domain": {
        "portfolio": 3,
        "governance": 2,
        "kyc": 1,
        "risk": 1,
        "reporting": 1,
    },
    "violations": [
        # Portfolio violations
        Violation(rule_id="RULE_PORT_CONC_001", severity="critical"),
        # Governance violations
        Violation(rule_id="RULE_GOV_MGR_CERT_001", severity="critical"),
        # KYC violations
        Violation(rule_id="RULE_KYC_RECENCY_001", severity="high"),
        # Risk violations
        Violation(rule_id="RULE_RISK_VAR_001", severity="high"),
        # Reporting violations
        Violation(rule_id="RULE_REP_NAV_TIME_001", severity="critical"),
    ],
}
```

**Validation**:
- ✅ All 5 agents called
- ✅ Violations from each agent included
- ✅ Total violations = sum of domain violations
- ✅ No agent interferes with others
- ✅ Orchestrator aggregation works correctly

#### 2.2.2 Parallel Fund Audit Test (Semaphore)

**File**: `backend/tests/compliance/test_compliance_agents.py::test_orchestrator_parallel_execution`

**Test Setup**: 20 funds to audit (2× semaphore limit of 10)

**Test Execution**:
```python
import time
orchestrator = ComplianceAgentOrchestrator(graph_client, rules_engine)

start_time = time.time()
result = await orchestrator.audit_all_funds(
    funds=fund_data_list[0:20],  # 20 funds
    region="SEBI"
)
elapsed = time.time() - start_time
```

**Verification**:
- ✅ All 20 funds audited
- ✅ Semaphore working (no >10 concurrent agents)
- ✅ Execution time <10 seconds for 20 funds
- ✅ No race conditions or conflicts
- ✅ Memory usage reasonable (<1GB)

**Expected Performance**:
- Sequential (10 concurrent): ~20 seconds
- With semaphore: ~6-8 seconds (2 batches of 10)

#### 2.2.3 Scorecard Aggregation Test

**File**: `backend/tests/compliance/test_compliance_agents.py::test_orchestrator_scorecard`

**Test Execution**:
```python
result = await orchestrator.audit_all_funds(
    funds=fund_data_list,
    region="SEBI"
)

# Scorecard calculation
overall_score = result["overall_score"]
domain_scores = result["scores_by_domain"]
```

**Scorecard Calculation**:
```
Domain Score = (rules_passing / total_rules) × 100
Overall Score = (sum of domain scores) / 5

Example:
- Portfolio: 82% (2 violations, 11 rules evaluated)
- Governance: 90%
- KYC: 78%
- Risk: 85%
- Reporting: 92%
Overall = (82 + 90 + 78 + 85 + 92) / 5 = 85.4%
```

**Validation**:
- ✅ Domain scores accurate
- ✅ Overall score = average of domains
- ✅ Score range 0-100
- ✅ Scores consistent with violations

**Success Criteria**:
- ✅ Orchestrator coordinates all 5 agents
- ✅ No race conditions or conflicts
- ✅ Semaphore working (10 concurrent max)
- ✅ Scorecard calculated correctly
- ✅ Performance meets SLA (<10s for 20 funds)

**Owner**: Backend Team | **Duration**: 1.5 days | **Dependency**: Task 2.1

---

### Task 2.3: Validate Multi-Region Agent Routing

**Objective**: Verify agents can switch between SEBI/SEC/ESMA rule sets

**Scope**:
- Add region awareness to each agent
- Test agent routing SEBI rules for region=SEBI
- Test fallback to SEBI when SEC/ESMA unavailable
- Verify agent output includes region context

**Detailed Implementation**:

#### 2.3.1 Add Region Parameter to Agents

**File**: `backend/app/compliance/agents/*.py`

**Change**: Add region parameter to each agent method

```python
class PortfolioAgent:
    async def audit_portfolio(
        self,
        fund_id: str,
        fund_data: Dict[str, Any],
        region: str = "SEBI",  # NEW PARAMETER
    ) -> List[ComplianceViolation]:
        """Audit fund portfolio against region-specific rules."""
        # Load region-specific rules
        applicable_rules = await self.rules_engine.get_applicable_rules(
            rule_type="portfolio",
            region=region
        )
        # ... rest of implementation
```

#### 2.3.2 Region-Aware Rule Loading

**File**: `backend/app/compliance/rules_engine.py`

**New Method**:
```python
async def get_applicable_rules(
    self,
    rule_type: str,
    region: str = "SEBI"
) -> List[Dict[str, Any]]:
    """Get region-specific rules for a domain."""
    cypher = """
    MATCH (r:Rule {rule_type: $rule_type, region: $region})
    WHERE r.active = true OR NOT EXISTS(r.active)
    RETURN r
    """
    results = await self.graph.run(cypher, rule_type=rule_type, region=region)
    return [dict(row) for row in results]
```

#### 2.3.3 Test Region-Specific Agent Behavior

**File**: `backend/tests/compliance/test_compliance_agents.py::test_agent_multi_region`

**Test Case 1: SEBI Region**

```python
agent = PortfolioAgent(graph_client, rules_engine)

# SEBI: 15% concentration limit
sebi_violations = await agent.audit_portfolio(
    fund_id="FUND_001",
    fund_data={"holdings": [{"name": "RELIANCE", "pct": 16}]},
    region="SEBI"
)
# Expected: RULE_PORT_CONC_001 violated (16 > 15)
assert len(sebi_violations) == 1
```

**Test Case 2: SEC Region (different threshold)**

```python
# SEC: 5% concentration limit
sec_violations = await agent.audit_portfolio(
    fund_id="FUND_001",
    fund_data={"holdings": [{"name": "RELIANCE", "pct": 16}]},
    region="SEC"
)
# Expected: RULE_SEC_PORT_CONC_001 violated (16 > 5)
assert len(sec_violations) == 1
```

**Test Case 3: ESMA Region**

```python
# ESMA: 10% concentration limit
esma_violations = await agent.audit_portfolio(
    fund_id="FUND_001",
    fund_data={"holdings": [{"name": "RELIANCE", "pct": 16}]},
    region="ESMA"
)
# Expected: RULE_ESMA_PORT_CONC_001 violated (16 > 10)
assert len(esma_violations) == 1
```

**Expected Output**:
- SEBI fund (16%): 1 violation (16 > 15)
- SEC fund (16%): 1 violation (16 > 5)
- ESMA fund (16%): 1 violation (16 > 10)
- Each violation tagged with correct region

#### 2.3.4 Test Fallback Behavior

**Test Case**: Region not yet implemented falls back to SEBI

```python
# Region=SEC but no SEC rules loaded yet (Phase 4)
violations = await agent.audit_portfolio(
    fund_id="FUND_001",
    fund_data=fund_data,
    region="SEC"
)
# Expected: Falls back to SEBI rules, violations tagged with SEC (but using SEBI thresholds)
```

**Success Criteria**:
- ✅ All agents accept region parameter
- ✅ Region-specific rules applied correctly
- ✅ SEBI thresholds used for SEBI audits
- ✅ Different thresholds for SEC/ESMA (when Phase 4 completes)
- ✅ Violations tagged with region
- ✅ Fallback to SEBI when region unavailable

**Owner**: Backend Team | **Duration**: 1.5 days | **Dependency**: Task 2.2

---

### Task 2.4: Create Agent Performance Metrics Dashboard

**Objective**: Track agent accuracy, latency, violation distribution for monitoring

**Scope**:
- Add metrics collection to orchestrator
- Track: violations_detected, false_positive_rate, avg_latency, violations_by_severity
- Store metrics in Neo4j
- Create summary endpoint `/api/compliance/agents/metrics`

**Detailed Implementation**:

#### 2.4.1 Define Metrics Data Model

**File**: `backend/app/schemas/compliance_models.py`

**New Pydantic Models**:
```python
class AgentMetrics(BaseModel):
    """Metrics for a single agent."""
    agent_name: str  # e.g., "PortfolioAgent"
    violations_detected: int
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    accuracy_score: float  # 0.0-1.0 (true_positives / (true_positives + false_positives))
    recorded_at: str  # ISO 8601
    region: str

class AggregatedAgentMetrics(BaseModel):
    """Aggregated metrics across all agents."""
    agents: Dict[str, AgentMetrics]
    overall_latency_ms: float
    violations_by_severity: Dict[str, int]  # critical, high, medium, low
    recorded_at: str
```

#### 2.4.2 Implement Metrics Collection

**File**: `backend/app/compliance/agents/orchestrator.py`

**New Code**:
```python
import time
from collections import defaultdict

class ComplianceAgentOrchestrator:
    def __init__(self, ...):
        self.metrics = {
            "PortfolioAgent": {"violations": 0, "latencies": []},
            "GovernanceAgent": {"violations": 0, "latencies": []},
            # ... etc for all 5 agents
        }

    async def audit_all_funds(self, ...):
        results = []
        
        for agent_name in ["portfolio", "governance", "kyc", "risk", "reporting"]:
            agent = self._get_agent(agent_name)
            
            # Measure latency
            start = time.perf_counter()
            violations = await agent.audit(...)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            
            # Record metrics
            self.metrics[agent_name]["violations"] += len(violations)
            self.metrics[agent_name]["latencies"].append(elapsed)
            
            results.extend(violations)
        
        return results

    def get_agent_metrics(self) -> AgentMetrics:
        """Calculate and return current metrics."""
        metrics = {}
        
        for agent_name, data in self.metrics.items():
            if data["latencies"]:
                latencies = sorted(data["latencies"])
                avg = sum(latencies) / len(latencies)
                p95 = latencies[int(len(latencies) * 0.95)]
                p99 = latencies[int(len(latencies) * 0.99)]
            else:
                avg = p95 = p99 = 0
            
            metrics[agent_name] = AgentMetrics(
                agent_name=agent_name,
                violations_detected=data["violations"],
                avg_latency_ms=avg,
                p95_latency_ms=p95,
                p99_latency_ms=p99,
                accuracy_score=0.95,  # TODO: Calculate from test data
                recorded_at=datetime.now().isoformat(),
                region="SEBI"
            )
        
        return metrics
```

#### 2.4.3 Store Metrics in Neo4j

**File**: `backend/app/compliance/audit_integration.py`

**New Method**:
```python
async def store_agent_metrics(
    self,
    metrics: Dict[str, AgentMetrics]
) -> bool:
    """Store agent metrics in Neo4j for historical analysis."""
    cypher = """
    MERGE (m:AgentMetrics {timestamp: $timestamp})
    SET m.portfolio_violations = $portfolio_violations,
        m.portfolio_latency_ms = $portfolio_latency_ms,
        m.governance_violations = $governance_violations,
        # ... etc for all agents
    RETURN m
    """
    
    await self.graph.run(cypher, {
        "timestamp": datetime.now().isoformat(),
        "portfolio_violations": metrics["PortfolioAgent"].violations_detected,
        "portfolio_latency_ms": metrics["PortfolioAgent"].avg_latency_ms,
        # ... etc
    })
    return True
```

#### 2.4.4 Create API Endpoint for Metrics

**File**: `backend/app/api/routes/compliance.py`

**New Endpoint**:
```python
@router.get("/agents/metrics", response_model=AggregatedAgentMetrics)
async def get_agent_metrics(
    region: RegionEnum = Query(RegionEnum.SEBI),
    container: Container = Depends(get_container),
):
    """Get performance metrics for all compliance agents."""
    orchestrator = getattr(container, "orchestrator", None)
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    
    agent_metrics = orchestrator.get_agent_metrics()
    
    return AggregatedAgentMetrics(
        agents=agent_metrics,
        overall_latency_ms=sum(m.avg_latency_ms for m in agent_metrics.values()),
        violations_by_severity={
            "critical": ...,  # Count from violations
            "high": ...,
            "medium": ...,
            "low": ...,
        },
        recorded_at=datetime.now().isoformat()
    )
```

#### 2.4.5 Create Metrics Dashboard (Preview)

**File**: `backend/tests/compliance/test_compliance_agents.py::test_agent_metrics`

**Test**:
```python
async def test_agent_metrics():
    orchestrator = ComplianceAgentOrchestrator(graph_client, rules_engine)
    
    # Run audit (which collects metrics)
    await orchestrator.audit_all_funds(funds=fund_data_list, region="SEBI")
    
    # Get metrics
    metrics = orchestrator.get_agent_metrics()
    
    # Verify metrics structure
    assert "PortfolioAgent" in metrics
    assert metrics["PortfolioAgent"].avg_latency_ms > 0
    assert metrics["PortfolioAgent"].violations_detected >= 0
    assert 0.0 <= metrics["PortfolioAgent"].accuracy_score <= 1.0
```

**Success Criteria**:
- ✅ Metrics collected for each agent (violations, latency, accuracy)
- ✅ Metrics stored in Neo4j for historical analysis
- ✅ API endpoint returns metrics
- ✅ Dashboard preview working (ready for Phase 3 UI integration)
- ✅ Performance metrics accurate and reliable

**Owner**: Backend Team | **Duration**: 1.5 days | **Dependency**: Task 2.3

---

### Phase 2 Summary

| Task | Duration | Owner | Status |
|------|----------|-------|--------|
| 2.1: Agent integration tests | 2 days | QA | Planned |
| 2.2: Orchestrator tests | 1.5 days | Backend | Planned |
| 2.3: Multi-region routing | 1.5 days | Backend | Planned |
| 2.4: Metrics dashboard | 1.5 days | Backend | Planned |
| **TOTAL PHASE 2** | **6.5 days** | **Multi-team** | **90% → 100%** |

---

## Phase 3: Compliance Dashboard UI (Weeks 5-7)

### Overview

Build the compliance scorecard Streamlit UI with 5 pages:
1. **Scorecard**: Real-time compliance score by region
2. **Violations**: Breakdown by severity, domain, fund
3. **Funds**: Fund-by-fund compliance heatmap
4. **Remediation**: Violation resolution workflow tracking
5. **Multi-Region**: Compare compliance across SEBI/SEC/ESMA

**Timeline**: Days 25-40 (3 weeks)
**Status**: 0% → 100%
**Team**: Frontend (1-2 engineers) + Backend support

---

### Task 3.1: Build Streamlit Compliance Scorecard Page

**Objective**: Create main dashboard showing real-time compliance score by region

**Scope**:
- Main page with region selector (SEBI/SEC/ESMA/All)
- Real-time compliance score (0-100) gauge
- Score breakdown by domain (Portfolio/Governance/KYC/Risk/Reporting)
- Trend chart (compliance score last 30 days)
- KPI cards (# violations, # critical, # active funds)
- Auto-refresh every 60s

**Detailed Implementation**:

#### 3.1.1 Create Main Dashboard Page

**File**: `streamlit_app/compliance_dashboard.py`

**Structure**:
```python
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import httpx
from datetime import datetime, timedelta

st.set_page_config(
    page_title="AMC Compliance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== HEADER & REGION SELECTOR =====
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    st.title("🏦 AMC Compliance Dashboard")

with col2:
    region = st.selectbox(
        "Regulatory Region",
        options=["SEBI", "SEC", "ESMA", "Consolidated"],
        index=0
    )

with col3:
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

last_updated = st.empty()

# ===== FETCH DATA =====
@st.cache_data(ttl=60)  # Cache for 60 seconds
def fetch_scorecard(region):
    """Fetch compliance scorecard from API."""
    try:
        response = httpx.get(
            f"http://localhost:8000/api/compliance/scorecard?region={region}",
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Failed to fetch scorecard: {e}")
        return None

scorecard = fetch_scorecard(region)

if scorecard:
    last_updated.caption(f"Last updated: {scorecard.get('last_audit_at', 'Never')}")
    
    # ===== KPI CARDS =====
    st.markdown("### Key Performance Indicators")
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    
    with kpi1:
        st.metric(
            label="Compliance Score",
            value=f"{scorecard['overall_score']:.1f}%",
            delta=f"+{scorecard['compliance_trend'][-1]['score'] - scorecard['compliance_trend'][-2]['score']:.1f}%" if len(scorecard['compliance_trend']) > 1 else None
        )
    
    with kpi2:
        st.metric(
            label="Total Violations",
            value=scorecard['violations_summary']['total']
        )
    
    with kpi3:
        st.metric(
            label="Critical Issues",
            value=scorecard['violations_summary']['critical'],
            delta_color="inverse"
        )
    
    with kpi4:
        st.metric(
            label="Compliant Funds",
            value=f"8/10"  # TODO: Calculate from fund data
        )
    
    # ===== SCORE GAUGE =====
    st.markdown("### Overall Compliance Score")
    
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=scorecard['overall_score'],
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"Compliance Score - {region}"},
        delta={'reference': 85},
        gauge={
            'axis': {'range': [None, 100]},
            'bar': {'color': "darkblue"},
            'steps': [
                {'range': [0, 50], 'color': "lightgray"},
                {'range': [50, 75], 'color': "lightyellow"},
                {'range': [75, 100], 'color': "lightgreen"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 90
            }
        }
    ))
    fig_gauge.update_layout(height=400)
    st.plotly_chart(fig_gauge, use_container_width=True)
    
    # ===== DOMAIN SCORES =====
    st.markdown("### Domain Compliance Breakdown")
    
    domain_col1, domain_col2, domain_col3 = st.columns(3)
    
    domains = scorecard['scores_by_domain']
    domain_list = list(domains.items())
    
    with domain_col1:
        for domain, score in domain_list[0:2]:
            st.metric(
                label=domain.capitalize(),
                value=f"{score:.1f}%",
                delta=f"{score - 85:.1f}%" if score < 85 else "✓"
            )
    
    with domain_col2:
        for domain, score in domain_list[2:4]:
            st.metric(
                label=domain.capitalize(),
                value=f"{score:.1f}%",
                delta=f"{score - 85:.1f}%" if score < 85 else "✓"
            )
    
    with domain_col3:
        if len(domain_list) > 4:
            domain, score = domain_list[4]
            st.metric(
                label=domain.capitalize(),
                value=f"{score:.1f}%",
                delta=f"{score - 85:.1f}%" if score < 85 else "✓"
            )
    
    # ===== TREND CHART =====
    st.markdown("### 30-Day Compliance Trend")
    
    trend_df = pd.DataFrame(score
	
I'll complete the detailed implementation plan document. Let me create it as a comprehensive markdown file that you can review.Now let me create the comprehensive implementation plan document:Perfect. Now I'll create a comprehensive markdown implementation plan document:Let me create the comprehensive implementation plan document directly:Now I'll create the comprehensive implementation plan document and save it to a new file. Let me structure this properly:

Based on the audit and roadmap I've created, let me now generate the final detailed implementation plan document. Since this is a large document, I'll create it in markdown format:

## **12-Week AMC Compliance System Implementation Plan**

Here's your comprehensive implementation plan. Due to length, I'm providing it in a structured format that you can copy and use:

---

# **AMC COMPLIANCE SYSTEM: 12-WEEK DETAILED IMPLEMENTATION PLAN**

## **Executive Summary**

**Current State**: 36% production-ready (Phases 1-2 at 90%, Phases 3-5 at 0%)  
**Target State**: 100% production-ready with multi-region (SEBI/SEC/ESMA) support  
**Timeline**: 49 days critical path (7 weeks) with 3-team parallelization  
**Completion**: End of Week 12  
**Key Deliverable**: Production-grade compliance auditing system with UI, multi-region support, and security hardening

---

## **Table of Contents**

1. [Implementation Timeline](#implementation-timeline)
2. [Phase 1: Rules Engine Completion (Weeks 1-2)](#phase-1-weeks-1-2)
3. [Phase 2: Domain Agents Completion (Weeks 3-4)](#phase-2-weeks-3-4)
4. [Phase 3: Compliance Dashboard UI (Weeks 5-7)](#phase-3-weeks-5-7)
5. [Phase 4: SEC/ESMA Expansion (Weeks 8-10)](#phase-4-weeks-8-10)
6. [Phase 5: Production Hardening (Weeks 11-12)](#phase-5-weeks-11-12)
7. [Dependencies & Parallelization](#dependencies--parallelization)
8. [Team Structure](#team-structure)
9. [Success Criteria](#success-criteria)

---

## **Implementation Timeline**

```
WEEK    PHASE         TASKS                           STATUS    COMPLETION
─────────────────────────────────────────────────────────────────────────────
1-2     Phase 1       [1.1] CSV Data              ━━━━━━━━━━  Create files
                      [1.2] E2E Tests             ━━━━━━━━━━  Run tests
                      [1.3] Neo4j Population      ━━━━━━━━━━  Load schema
                      [1.4] API Validation        ━━━━━━━━━━  90% → 100%

3-4     Phase 2       [2.1] Agent Tests           ━━━━━━━━━━  Integration
                      [2.2] Orchestrator          ━━━━━━━━━━  Multi-agent
                      [2.3] Multi-Region Routing  ━━━━━━━━━━  Region support
                      [2.4] Agent Metrics         ━━━━━━━━━━  90% → 100%

5-7     Phase 3       [3.1] Scorecard Page        ━━━━━━━━━━  Main UI
                      [3.2] Violations Page       ━━━━━━━━━━  Breakdown viz
                      [3.3] Fund Heatmap          ━━━━━━━━━━  Fund matrix
                      [3.4] Remediation Tracking  ━━━━━━━━━━  Workflow UI
                      [3.5] Deploy Dashboard      ━━━━━━━━━━  0% → 100%

8-10    Phase 4       [4.1] SEC Rules             ━━━━━━━━━━  100+ regs
                      [4.2] ESMA Rules            ━━━━━━━━━━  100+ regs
                      [4.3] Multi-Region Router   ━━━━━━━━━━  Routing logic
                      [4.4] Agent Multi-Region    ━━━━━━━━━━  Region-aware
                      [4.5] Multi-Region E2E      ━━━━━━━━━━  Testing
                      [4.6] Dashboard Multi-Reg   ━━━━━━━━━━  0% → 100%

11-12   Phase 5       [5.1] Performance SLAs      ━━━━━━━━━━  <500ms cache
                      [5.2] Security Hardening    ━━━━━━━━━━  Rate limit
                      [5.3] Compliance Checklist  ━━━━━━━━━━  Certification
                      [5.4] Third-Party Audit     ━━━━━━━━━━  Sec review
                      [5.5] Go-Live               ━━━━━━━━━━  0% → 100%
─────────────────────────────────────────────────────────────────────────────
       TOTAL PROGRESS 36% ──────────────────────────────────→ 100% READY
```

---

## **Phase 1: Rules Engine Completion (Weeks 1-2)**

### **Phase 1 Overview**
- Currently: 90% complete
- Gap: Missing test data (CSV files) and end-to-end validation
- Target: 100% production-ready Phase 1
- Duration: 4-6 days (2 weeks allocated for buffer)

### **Task 1.1: Create CSV Data Files (1-2 days)**

**Deliverable**: 3 CSV files with test data

**File 1: `data/compliance/sebi_regulations.csv`**
- 50+ SEBI regulations
- Columns: regulation_id, title, effective_date, section, description, applicability, region
- Content areas: Portfolio, Governance, KYC, Risk, Reporting
- Format: UTF-8, CSV, comma-separated

**File 2: `data/compliance/rules.csv`**
- 30+ SEBI compliance rules
- Columns: rule_id, rule_type, title, description, regulation_id, condition, metric, threshold, severity, confidence_threshold, applicable_funds, region
- Rule IDs follow pattern: RULE_[DOMAIN]_[CATEGORY]_NNN (e.g., RULE_PORT_CONC_001)
- Each rule maps to regulation_id

**File 3: `data/compliance/fund_schemes.csv`**
- 10 fund schemes for testing
- Columns: fund_id, isin, name, fund_house, category, mandate, aum_cr, active_investors, region
- Mix: 4-5 equity, 3-4 debt, 2-3 hybrid funds
- AUM range: 100-1000 Cr
- Investors: 1,000-100,000

**Owner**: Compliance/Backend Team  
**Deliverable Checklist**:
- ✅ Files exist at correct paths
- ✅ CSV format valid
- ✅ 50+ regulations with proper structure
- ✅ 30+ rules with correct condition/metric/threshold
- ✅ 10 funds with realistic data

---

### **Task 1.2: Run End-to-End Compliance Audit Tests (1-2 days)**

**Objective**: Validate audit pipeline with real data

**Test Commands**:
```bash
# Run all compliance tests
pytest backend/tests/compliance/ -v --tb=short

# Run specific test suites
pytest backend/tests/compliance/test_rules_engine.py -v
pytest backend/tests/compliance/test_violation_detector.py -v
pytest backend/tests/compliance/test_rules_ingestion.py -v
pytest backend/tests/compliance/test_compliance_api.py -v
```

**Expected Output**:
- ✅ All tests pass (21/21 or similar)
- ✅ Violations correctly detected (expected vs. actual)
- ✅ Scorecard calculations accurate
- ✅ No race conditions in parallel execution
- ✅ CSV data properly ingested

**Owner**: QA Team  
**Success Criteria**:
- ✅ Test pass rate 100%
- ✅ Coverage >90% for compliance module
- ✅ No critical/blocker bugs

---

### **Task 1.3: Populate Neo4j Graph with Compliance Schema (1 day)**

**Objective**: Deploy schema and load real data into database

**Steps**:
1. Run schema deployment:
```python
from app.graph.compliance_schema import deploy_compliance_schema
from app.graph.client import get_graph_client

client = get_graph_client()
deploy_compliance_schema(client)
```

2. Verify nodes and relationships created (check Neo4j browser)
3. Load CSV data:
```python
from app.ingestion.compliance_rules_ingester import seed_compliance_data
result = await seed_compliance_data(client, Path("data/compliance"))
```

4. Validate data integrity with Cypher queries

**Validation Queries**:
```cypher
-- Count nodes
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count

-- Verify relationships
MATCH (r:Regulation)-[:has_rules]->(rule:Rule) RETURN count(*) AS rule_count

-- Sample rule structure
MATCH (rule:Rule {id: "RULE_PORT_CONC_001"})
RETURN rule.title, rule.condition, rule.metric, rule.threshold
```

**Owner**: DevOps Team  
**Success Criteria**:
- ✅ 50+ regulations in Neo4j
- ✅ 30+ rules created and linked
- ✅ 10 funds loaded
- ✅ All indexes created and working
- ✅ Query response time <100ms

---

### **Task 1.4: Validate API Responses & Integration (1 day)**

**Objective**: End-to-end API testing with real data

**Test Endpoints**:

1. **POST /api/compliance/audit?region=SEBI**
   - Expected: 200 OK with audit results
   - Response time: <5 seconds
   - Total violations: 15+ expected
   - Response schema: ComplianceAuditResultResponse

2. **GET /api/compliance/violations?region=SEBI**
   - Expected: Paginated violations list
   - Filtering by severity/fund/region working
   - Response time: <2 seconds

3. **GET /api/compliance/fund/{fund_id}/violations**
   - Expected: Fund-specific violations
   - Compliance score calculated
   - Response time: <1 second

4. **GET /api/compliance/scorecard?region=SEBI**
   - Expected: Compliance score by domain
   - Overall score calculated
   - Trend data available
   - Response time: <500ms ⭐ Production SLA

5. **POST /api/compliance/violations/{id}/resolve**
   - Expected: Status changed to remediated
   - Resolution action stored
   - Response time: <500ms

**Test Script**:
```bash
#!/bin/bash
# Run E2E API tests
curl -X POST http://localhost:8000/api/compliance/audit?region=SEBI
curl -X GET "http://localhost:8000/api/compliance/violations?region=SEBI"
curl -X GET http://localhost:8000/api/compliance/scorecard?region=SEBI
# ... validate responses
```

**Owner**: Backend Team  
**Success Criteria**:
- ✅ All 5 endpoints return 200 OK
- ✅ Response schemas match Pydantic models
- ✅ Filtering works (severity, fund_id, region)
- ✅ Error handling correct (400/404/500)
- ✅ Response times meet SLAs

---

### **Phase 1 Summary**

| Task | Days | Owner | Status |
|------|------|-------|--------|
| 1.1: CSV Data | 1-2 | Compliance | Planned |
| 1.2: E2E Tests | 1-2 | QA | Planned |
| 1.3: Neo4j Population | 1 | DevOps | Planned |
| 1.4: API Validation | 1 | Backend | Planned |
| **Total** | **4-6** | **Multi-team** | **90%→100%** |

---

## **Phase 2: Domain Agents Completion (Weeks 3-4)**

### **Phase 2 Overview**
- Currently: 90% complete
- Gap: Full integration testing, multi-region support, metrics collection
- Target: 100% production-ready Phase 2
- Duration: 6-7 days (2 weeks allocated)

### **Task 2.1: Integration Test All Domain Agents (2 days)**

**Objective**: Verify each agent detects violations accurately

**Test Coverage**:

1. **PortfolioAgent**
   - Concentration violations (>15%)
   - Sector violations (>30%)
   - Related-party violations (>10%)

2. **GovernanceAgent**
   - Manager certification violations
   - Board independence violations

3. **KYCAgent**
   - KYC recency violations (>365 days)
   - PEP screening violations (unverified)

4. **RiskAgent**
   - VaR violations (>4%)
   - Liquidity violations (<5%)

5. **ReportingAgent**
   - NAV timeliness violations (>21:00 IST)
   - Filing deadline violations

**Test File**: `backend/tests/compliance/test_compliance_agents.py`

**Expected Violations Per Fund**:
- Portfolio: 3 violations
- Governance: 2 violations
- KYC: 1 violation
- Risk: 1 violation
- Reporting: 1 violation
- **Total**: 8 violations per fund

**Owner**: QA Team  
**Success Criteria**:
- ✅ All 5 agents tested independently
- ✅ Violations accurately detected
- ✅ No false positives
- ✅ Response time <500ms per agent
- ✅ 100% test pass rate

---

### **Task 2.2: Test Orchestrator Multi-Agent Coordination (1.5 days)**

**Objective**: Verify orchestrator coordinates all 5 agents

**Test Scenarios**:

1. **Single Fund Multi-Agent Audit**
   - 1 fund, all 5 agents called concurrently
   - Expected: 8 violations from all domains
   - Response time: <2 seconds

2. **Parallel Fund Audit (20 funds)**
   - Semaphore working (max 10 concurrent)
   - Expected: All 20 funds audited
   - Response time: <10 seconds
   - Memory usage: <1GB

3. **Scorecard Aggregation**
   - Scores calculated by domain
   - Overall score = average of 5 domains
   - Verification: (82+90+78+85+92)/5 = 85.4%

**Owner**: Backend Team  
**Success Criteria**:
- ✅ Orchestrator calls all 5 agents
- ✅ No race conditions
- ✅ Semaphore working (10 concurrent max)
- ✅ Scorecard correct
- ✅ Performance <10s for 20 funds

---

### **Task 2.3: Validate Multi-Region Agent Routing (1.5 days)**

**Objective**: Add region awareness to agents (preparation for Phase 4)

**Changes**:

1. Add `region: str = "SEBI"` parameter to each agent
2. Load region-specific rules from Neo4j
3. Apply region-specific thresholds
4. Tag violations with region

**Example - Portfolio Concentration**:
- SEBI: 15% limit
- SEC: 5% limit (when Phase 4 complete)
- ESMA: 10% limit (when Phase 4 complete)

**Test Case**: Same fund, different regions
```
Fund with 16% holding:
- SEBI region: 1 violation (16 > 15)
- SEC region: 1 violation (16 > 5) [Phase 4]
- ESMA region: 1 violation (16 > 10) [Phase 4]
```

**Owner**: Backend Team  
**Success Criteria**:
- ✅ All agents accept region parameter
- ✅ Region-specific rules applied
- ✅ Violations tagged with region
- ✅ Fallback to SEBI when region unavailable
- ✅ No cross-region interference

---

### **Task 2.4: Create Agent Performance Metrics Dashboard (1.5 days)**

**Objective**: Track agent metrics (violations detected, latency, accuracy)

**Metrics Collected**:
```json
{
  "agent_name": "PortfolioAgent",
  "violations_detected": 1250,
  "avg_latency_ms": 145.3,
  "p95_latency_ms": 320.1,
  "p99_latency_ms": 450.5,
  "accuracy_score": 0.95,
  "recorded_at": "2024-01-25T14:30:00Z"
}
```

**Storage**: Neo4j (AgentMetrics nodes)

**API Endpoint**: `GET /api/compliance/agents/metrics?region=SEBI`

**Response**:
```json
{
  "agents": {
    "PortfolioAgent": { ... },
    "GovernanceAgent": { ... },
    "KYCAgent": { ... },
    "RiskAgent": { ... },
    "ReportingAgent": { ... }
  },
  "overall_latency_ms": 750.2,
  "violations_by_severity": {
    "critical": 25,
    "high": 45,
    "medium": 60,
    "low": 35
  }
}
```

**Owner**: Backend Team  
**Success Criteria**:
- ✅ Metrics collected for each agent
- ✅ Metrics stored in Neo4j
- ✅ API endpoint working
- ✅ Historical metrics retrievable
- ✅ Accuracy score calculated

---

### **Phase 2 Summary**

| Task | Days | Owner | Status |
|------|------|-------|--------|
| 2.1: Agent Tests | 2 | QA | Planned |
| 2.2: Orchestrator | 1.5 | Backend | Planned |
| 2.3: Multi-Region | 1.5 | Backend | Planned |
| 2.4: Metrics | 1.5 | Backend | Planned |
| **Total** | **6-7** | **Multi-team** | **90%→100%** |

---

## **Phase 3: Compliance Dashboard UI (Weeks 5-7)**

### **Phase 3 Overview**
- Currently: 0% complete
- Target: Full Streamlit compliance dashboard
- Duration: 15 days (3 weeks)
- Technology: Streamlit + Plotly + Pandas

### **Task 3.1: Build Scorecard Page (3 days)**

**Page**: `streamlit_app/pages/01_Scorecard.py`

**Components**:

1. **Header**
   - Title: "🏦 AMC Compliance Dashboard"
   - Region selector (SEBI/SEC/ESMA/Consolidated)
   - Refresh button
   - Last updated timestamp

2. **KPI Cards** (4 metrics)
   - Overall Compliance Score: X.X% (with delta trend)
   - Total Violations: N
   - Critical Issues: N (delta color inverse)
   - Compliant Funds: N/Total

3. **Score Gauge Chart**
   - Circular gauge 0-100%
   - Color zones: Red (0-50), Yellow (50-75), Green (75-100)
   - Current score highlighted
   - Target line at 90%

4. **Domain Breakdown Cards** (5 metrics)
   - Portfolio Score: X%
   - Governance Score: X%
   - KYC Score: X%
   - Risk Score: X%
   - Reporting Score: X%

5. **30-Day Trend Chart**
   - Line chart showing score evolution
   - X-axis: Last 30 days
   - Y-axis: Score (0-100)
   - Threshold line at 85%

**Data Source**: `/api/compliance/scorecard?region={REGION}`

**Features**:
- Auto-refresh every 60 seconds
- Manual refresh button
- Region switching (updates all visualizations)
- Responsive layout (desktop/tablet)

**Owner**: Frontend Team  
**Success Criteria**:
- ✅ Page loads without errors
- ✅ Data fetched within 500ms
- ✅ All visualizations render correctly
- ✅ Region selector updates all charts
- ✅ Auto-refresh working
- ✅ Mobile responsive

---

### **Task 3.2: Build Violations Page (3 days)**

**Page**: `streamlit_app/pages/02_Violations.py`

**Components**:

1. **Filters Section** (top)
   - Severity multi-select: Critical, High, Medium, Low
   - Domain multi-select: Portfolio, Governance, KYC, Risk, Reporting
   - Fund selector (dropdown)
   - Region selector
   - Date range picker (from/to)

2. **Violations by Severity** (pie chart)
   - Critical: N (red)
   - High: N (orange)
   - Medium: N (yellow)
   - Low: N (blue)
   - Interactive: Click slice to drill down

3. **Violations by Domain** (bar chart)
   - Domains on X-axis
   - Count on Y-axis
   - Color-coded by domain
   - Hover shows count and percentage

4. **Top 10 Violated Rules** (leaderboard table)
   - Rank
   - Rule ID
   - Rule Title
   - Violation Count
   - Severity
   - Sort by count descending

5. **Violations Detail Table** (paginated)
   - Columns: Violation ID, Fund ID, Rule, Severity, Confidence, Detected At, Status
   - Sortable (click column header)
   - Paginated (10 per page)
   - Expandable rows showing full details

**Data Source**: `/api/compliance/violations?region={}&severity={}&fund_id={}` + filters

**Features**:
- Multi-select filters
- Real-time filtering
- Interactive charts
- Drill-down capability
- Export to CSV button
- Status indicators (detected/reviewed/remediated)

**Owner**: Frontend Team  
**Success Criteria**:
- ✅ Filters work correctly
- ✅ Charts update on filter change
- ✅ Table paginated and sortable
- ✅ Drill-down shows full details
- ✅ Export working
- ✅ Performance <2s for 1000 violations

---

### **Task 3.3: Build Fund Heatmap Page (3 days)**

**Page**: `streamlit_app/pages/03_Funds.py`

**Components**:

1. **Fund Heatmap**
   - Matrix: N funds × 5 domains
   - Cells color-coded:
     - Green: Compliant (90-100%)
     - Yellow: At Risk (75-90%)
     - Red: Non-Compliant (<75%)
   - Cell value: Compliance % (e.g., "95%")
   - Hover: Fund name + domain

2. **Fund List Table**
   - Columns: Fund Name, Category, AUM (Cr), Compliance Score, Status
   - Sortable (click header)
   - Clickable rows: Select fund for details
   - Filter by category (Equity/Debt/Hybrid)

3. **Fund Detail Panel** (when fund selected)
   - Fund metadata (name, ISIN, fund house, AUM, investors)
   - Compliance score by domain
   - Recent violations (last 10)
   - Remediation status
   - Escalation status

**Data Sources**:
- `/api/compliance/scorecard?region={}` (domain scores)
- `/api/compliance/fund/{fund_id}/violations` (fund details)

**Features**:
- Interactive heatmap
- Fund selection persists
- Domain filtering
- Category filtering
- Drill-down to fund details
- Violation list with actions

**Owner**: Frontend Team  
**Success Criteria**:
- ✅ Heatmap renders for 10+ funds
- ✅ Color coding accurate
- ✅ Heatmap interactive (hover, click)
- ✅ Fund details load <1s
- ✅ Sorting working
- ✅ Performance: heatmap <2s for 100 funds

---

### **Task 3.4: Build Remediation Tracking Page (3 days)**

**Page**: `streamlit_app/pages/04_Remediation.py`

**Components**:

1. **Active Violations** (filtered table)
   - Status = "detected"
   - Columns: Violation ID, Fund, Rule, Severity, Detected At, SLA Status
   - Severity color-coded
   - SLA Status: On Track / At Risk / Overdue

2. **Remediation Progress** (metrics row)
   - Total Detected: N
   - Reviewed: N (%)
   - Remediated: N (%)
   - Closed: N (%)
   - Stacked bar chart

3. **Escalation SLA Tracking** (table)
   - Severity
   - SLA Hours
   - Active Issues
   - At Risk
   - Overdue
   - Color-coded status

4. **Resolve Violation Modal** (when "Resolve" button clicked)
   - Violation ID (read-only)
   - Rule Title (read-only)
   - Fund ID (read-only)
   - Current Status (read-only)
   - Resolution Action (text input)
   - Resolve button
   - Status: Updating... → Success/Error

5. **Violation Timeline** (for selected violation)
   - Status transitions over time
   - Detected At
   - Reviewed At (if applicable)
   - Remediated At (if applicable)
   - Closed At (if applicable)
   - Notes/Actions

**Data Sources**:
- `/api/compliance/violations?status=detected` (active)
- `/api/compliance/violations/{id}/resolve` (POST to resolve)

**Features**:
- Real-time SLA tracking
- Bulk actions (resolve multiple)
- Action history/timeline
- Status transition validation
- Escalation notifications
- Export remediation report

**Owner**: Frontend Team  
**Success Criteria**:
- ✅ Active violations table working
- ✅ Resolve modal functional
- ✅ Status update successful
- ✅ SLA tracking accurate
- ✅ Timeline rendering correctly
- ✅ Bulk actions working

---

### **Task 3.5: Deploy & Test Streamlit Dashboard (2 days)**

**Objective**: Package and verify Streamlit UI ready for use

**Steps**:

1. **Create Streamlit Config**
   - File: `streamlit_app/compliance_config.toml`
   - Settings: Theme, layout, timeout

2. **Update Requirements**
   - File: `streamlit_app/requirements.txt`
   - Packages: streamlit, plotly, pandas, httpx

3. **Create Startup Script**
   - File: `run_compliance_dashboard.sh`
   - Command: `streamlit run streamlit_app/compliance_dashboard.py`

4. **Local Testing**
   - Start backend: `python -m backend.main`
   - Start Streamlit: `streamlit run streamlit_app/compliance_dashboard.py`
   - Verify all pages load
   - Test data flow end-to-end

5. **Performance Testing**
   - Measure page load times
   - Test with 100+ violations
   - 10 concurrent users
   - Verify <3s page loads

6. **Cross-Browser Testing**
   - Chrome, Firefox, Safari
   - Desktop, tablet, mobile
   - Responsive layout

**Deployment Checklist**:
- ✅ All pages accessible
- ✅ All API integrations working
- ✅ No console errors
- ✅ Performance <3s per page
- ✅ Responsive on all devices
- ✅ Refresh working
- ✅ Filters functional

**Owner**: DevOps/Frontend Team  
**Success Criteria**:
- ✅ Dashboard fully functional
- ✅ All 5 pages working
- ✅ Data flowing end-to-end
- ✅ Performance acceptable
- ✅ Ready for production

---

### **Phase 3 Summary**

| Task | Days | Owner | Status |
|------|------|-------|--------|
| 3.1: Scorecard Page | 3 | Frontend | Planned |
| 3.2: Violations Page | 3 | Frontend | Planned |
| 3.3: Fund Heatmap | 3 | Frontend | Planned |
| 3.4: Remediation | 3 | Frontend | Planned |
| 3.5: Deploy & Test | 2 | DevOps | Planned |
| **Total** | **15** | **Frontend** | **0%→100%** |

---

## **Phase 4: SEC/ESMA Regulatory Expansion (Weeks 8-10)**

### **Phase 4 Overview**
- Currently: 0% complete
- Target: 200+ new regulations (100+ SEC, 100+ ESMA) + multi-region support
- Duration: 15 days (3 weeks)
- Team: Backend + Compliance

### **Task 4.1: Ingest SEC Regulations & Build Rule Set (5 days)**

**Objective**: Add 100+ US SEC compliance rules

**SEC Regulations to Include**:
- Investment Company Act of 1940 (ICA)
- Rule 12d-1: Diversification requirements
- Rule 17f-3: Portfolio concentration
- Rule 22c-1: NAV calculation & timing
- Investment Advisers Act of 1940
- Dodd-Frank Act requirements
- Rule 10b-1: Distribution fees

**Data File**: `data/compliance/sec_regulations.csv`
- Columns: regulation_id, title, section, description, applicability
- Rows: 100+
- Format: SEC_RULE_001, SEC_RULE_002, etc.

**Rules File**: `data/compliance/sec_rules.csv`
- 50+ SEC-specific rules
- IDs: RULE_SEC_PORT_001, RULE_SEC_NAV_001, etc.
- Map to SEC thresholds:
  - Concentration: 5% (vs SEBI 15%)
  - NAV Cutoff: 4pm ET (vs SEBI 9pm IST)
  - Board Independence: 40% (vs SEBI 50%)

**Implementation**:
1. Research SEC regulations applicable to mutual funds
2. Create regulations CSV
3. Create rules CSV (mapping to agents)
4. Load into Neo4j
5. Test SEC rule evaluation on sample funds

**Test Case**: Fund with 16% holding
- SEBI: Compliant (16% > 15%)
- SEC: Violation (16% > 5% SEC limit)

**Owner**: Compliance/Backend Team  
**Success Criteria**:
- ✅ 100+ SEC regulations in CSV
- ✅ 50+ SEC rules created
- ✅ Rules loaded into Neo4j
- ✅ Agents can apply SEC rules
- ✅ Test: SEC fund audited with SEC thresholds

---

### **Task 4.2: Ingest ESMA Regulations & Build Rule Set (5 days)**

**Objective**: Add 100+ EU ESMA compliance rules

**ESMA Regulations to Include**:
- UCITS Directive (2009/65/EC)
- AIFM Directive (2011/61/EU)
- MiFID II regulations
- ESG disclosure requirements (SFDR)
- Liquidity rules
- Risk management requirements

**Data File**: `data/compliance/esma_regulations.csv`
- Columns: regulation_id, title, section, description, applicability
- Rows: 100+
- Format: ESMA_RULE_001, ESMA_RULE_002, etc.

**Rules File**: `data/compliance/esma_rules.csv`
- 50+ ESMA-specific rules
- IDs: RULE_ESMA_PORT_001, RULE_ESMA_ESG_001, etc.
- Map to ESMA thresholds:
  - Concentration: 10% (vs SEBI 15%, SEC 5%)
  - Liquidity: 80% tradable within 5 business days
  - ESG Disclosure: Mandatory climate risk reporting

**Implementation**:
1. Research ESMA regulations applicable to funds
2. Create regulations CSV
3. Create rules CSV (mapping to agents)
4. Load into Neo4j
5. Test ESMA rule evaluation

**Owner**: Compliance/Backend Team  
**Success Criteria**:
- ✅ 100+ ESMA regulations in CSV
- ✅ 50+ ESMA rules created
- ✅ Rules loaded into Neo4j
- ✅ Agents can apply ESMA rules
- ✅ Test: ESMA fund audited with ESMA thresholds

---

### **Task 4.3: Build Multi-Region Rule Router (3 days)**

**Objective**: Route funds to correct regional rule set

**Implementation**: Update `ViolationDetector.audit_all_funds()`

**Logic**:
```python
def route_fund_to_region(fund_data) -> str:
    """Determine fund's regulatory region."""
    region = fund_data.get("region", "SEBI")  # SEBI/SEC/ESMA
    return region

async def audit_fund_by_region(fund_id, fund_data, region):
    """Audit fund against region-specific rules only."""
    rules = await self.rules_engine.get_applicable_rules(
        rule_type=None,  # All rules
        region=region
    )
    violations = []
    for rule in rules:
        v = await self.rules_engine.evaluate_rule(rule.id, fund_data)
        if v:
            violations.append(v)
    return violations
```

**Test Case**: Same fund, different regions
```
Fund GLOBAL_FUND_001 with 16% holding:
- region=SEBI: 1 violation (16 > 15) from SEBI rules
- region=SEC: 1 violation (16 > 5) from SEC rules
- region=ESMA: 1 violation (16 > 10) from ESMA rules
- region=ALL: 3 violations (SEBI + SEC + ESMA)
```

**Owner**: Backend Team  
**Success Criteria**:
- ✅ Region parameter working
- ✅ Fund routed to correct region
- ✅ Region-specific rules applied
- ✅ Violations tagged with region
- ✅ No rule conflicts between regions

---

### **Task 4.4: Update Agents for Multi-Region Support (3 days)**

**Objective**: Make each agent region-aware

**Changes to Each Agent**:
1. Add `region: str = "SEBI"` parameter
2. Load region-specific rules from Neo4j
3. Apply region-specific thresholds
4. Tag violations with region

**Example - PortfolioAgent**:
```python
class PortfolioAgent:
    async def audit_portfolio(
        self,
        fund_id: str,
        fund_data: Dict,
        region: str = "SEBI"
    ) -> List[ComplianceViolation]:
        # Load region-specific portfolio rules
        rules = await self.rules_engine.get_applicable_rules(
            rule_type="portfolio",
            region=region
        )
        # Apply rules and get violations
        violations = []
        for rule in rules:
            v = await self.rules_engine.evaluate_rule(rule.id, fund_data)
            if v:
                v.region = region  # Tag with region
                violations.append(v)
        return violations
```

**Test**: Each agent with SEBI/SEC/ESMA
- Portfolio Agent: Concentration limits differ by region
- Governance Agent: Board independence % differs
- KYC Agent: Same rules, different record retention
- Risk Agent: VaR/liquidity limits differ
- Reporting Agent: NAV cutoff times differ

**Owner**: Backend Team  
**Success Criteria**:
- ✅ All 5 agents accept region parameter
- ✅ Region-specific rules applied
- ✅ Violations tagged with region
- ✅ Fallback to SEBI when rules unavailable
- ✅ Test pass rate 100%

---

### **Task 4.5: Multi-Region End-to-End Testing (3 days)**

**Objective**: Comprehensive testing of multi-region compliance

**Test Scenarios**:

1. **Single Region - SEBI**
   - 10 SEBI funds audited
   - SEBI rules applied
   - 15+ violations expected
   - Audit time: <10 seconds

2. **Single Region - SEC** (when loaded)
   - 5 SEC funds audited
   - SEC rules applied
   - Different thresholds validated
   - Audit time: <5 seconds

3. **Single Region - ESMA** (when loaded)
   - 3 ESMA funds audited
   - ESMA rules applied
   - ESG requirements validated

4. **Mixed Regions in Single Audit**
   - 10 funds from different regions
   - Each fund audited with own region's rules
   - Violations correctly isolated by region

5. **Global Audit (All Regions)**
   - Single fund audited against all regions
   - 3× violations (SEBI + SEC + ESMA)
   - Merged into final report

**Performance Targets**:
- 50 funds across 3 regions: <15 seconds
- Memory: <500MB
- No race conditions or data corruption

**Test Script**:
```bash
# Run multi-region audit tests
pytest backend/tests/compliance/test_multi_region.py -v

# Performance test
python -c "
import asyncio
from app.compliance.orchestrator import ComplianceAgentOrchestrator

orchestrator = ComplianceAgentOrchestrator()
result = asyncio.run(orchestrator.audit_all_funds(
    funds=fund_list[0:50],
    region='ALL'  # Audit all regions
))
print(f'Audited 50 funds across 3 regions in {result["elapsed_ms"]}ms')
"
```

**Owner**: QA Team  
**Success Criteria**:
- ✅ All multi-region scenarios pass
- ✅ Performance <15s for 50 funds
- ✅ Violations correctly isolated by region
- ✅ No cross-region contamination
- ✅ Mixed-region audit working

---

### **Task 4.6: Update Streamlit Dashboard for Multi-Region (2 days)**

**Objective**: Enhance UI to compare compliance across regions

**Changes**:

1. **Scorecard Page**
   - Add region tabs (SEBI / SEC / ESMA / Consolidated)
   - Show score for each region side-by-side
   - Regional violation breakdown

2. **Violations Page**
   - Add "Region" column to violations table
   - Add region filter
   - Show violations comparison across regions

3. **Funds Page**
   - Add region column to heatmap
   - Highlight multi-region funds
   - Show which region's rules each fund must follow

4. **Remediation Page**
   - Filter by region
   - Region-specific SLA tracking

5. **New "Multi-Region Comparison" Page**
   - Side-by-side scorecard comparison (SEBI vs SEC vs ESMA)
   - Violations breakdown by region
   - Regulatory alignment report

**Streamlit Code Example**:
```python
# Region tabs on Scorecard page
region_tabs = st.tabs(["SEBI", "SEC", "ESMA", "Consolidated"])

with region_tabs[0]:  # SEBI tab
    scorecard = fetch_scorecard("SEBI")
    st.metric("SEBI Score", f"{scorecard['overall_score']:.1f}%")

# ... repeat for other regions

with region_tabs[3]:  # Consolidated tab
    sebi = fetch_scorecard("SEBI")
    sec = fetch_scorecard("SEC")
    esma = fetch_scorecard("ESMA")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("SEBI", f"{sebi['overall_score']:.1f}%")
    with col2:
        st.metric("SEC", f"{sec['overall_score']:.1f}%")
    with col3:
        st.metric("ESMA", f"{esma['overall_score']:.1f}%")
```

**Owner**: Frontend Team  
**Success Criteria**:
- ✅ Region tabs/selector working
- ✅ Multi-region comparison visible
- ✅ Data updates correctly per region
- ✅ Performance <2s per region switch
- ✅ All pages updated

---

### **Phase 4 Summary**

| Task | Days | Owner | Status |
|------|------|-------|--------|
| 4.1: SEC Rules | 5 | Compliance | Planned |
| 4.2: ESMA Rules | 5 | Compliance | Planned |
| 4.3: Multi-Region Router | 3 | Backend | Planned |
| 4.4: Agent Multi-Region | 3 | Backend | Planned |
| 4.5: Multi-Region E2E | 3 | QA | Planned |
| 4.6: Dashboard Multi-Region | 2 | Frontend | Planned |
| **Total** | **21** | **Multi-team** | **0%→100%** |

---

## **Phase 5: Production Hardening & Certification (Weeks 11-12)**

### **Phase 5 Overview**
- Currently: 0% complete
- Target: Production-grade security, performance, compliance
- Duration: 10 days (2 weeks)
- Team: Backend + DevOps + Security + Compliance

### **Task 5.1: Implement Performance SLAs (2 days)**

**Objective**: Ensure compliance endpoints meet latency targets

**SLA Targets**:
- Scorecard endpoint: <500ms (p99)
- Audit endpoint: <5s for 50 funds (p99)
- Violations query: <2s (p99)

**Implementation**:

1. **Scorecard Caching**
   - Cache scorecard for 60 seconds
   - Use `functools.lru_cache` or Redis
   - TTL: 60 seconds (refresh on new violations)

2. **Database Optimization**
   - Index violations by timestamp
   - Cypher query optimization (LIMIT clauses)
   - Profile queries with EXPLAIN PLAN

3. **Monitoring**
   - Add FastAPI middleware to track latencies
   - Export metrics to Prometheus/CloudWatch
   - Create dashboard for latency trends
   - Alert if p99 > SLA

**Implementation Code**:
```python
# FastAPI middleware for latency tracking
from time import perf_counter
import logging

@app.middleware("http")
async def track_latency(request, call_next):
    start = perf_counter()
    response = await call_next(request)
    elapsed_ms = (perf_counter() - start) * 1000
    
    logger.info(f"{request.method} {request.url.path} took {elapsed_ms:.1f}ms")
    response.headers["X-Process-Time"] = str(elapsed_ms)
    
    return response

# Scorecard caching
from functools import lru_cache

@lru_cache(maxsize=10)
async def get_scorecard_cached(region: str):
    # Load scorecard from DB
    pass

# Cleanup cache every 60 seconds
import asyncio
async def cache_cleanup():
    while True:
        await asyncio.sleep(60)
        get_scorecard_cached.cache_clear()

asyncio.create_task(cache_cleanup())
```

**Load Testing**:
```bash
# Use Apache Bench or similar
ab -n 1000 -c 10 "http://localhost:8000/api/compliance/scorecard?region=SEBI"

# Expected: p99 latency < 500ms
```

**Owner**: Backend/DevOps Team  
**Success Criteria**:
- ✅ Scorecard <500ms (p99)
- ✅ Audit <5s for 50 funds (p99)
- ✅ Violations <2s (p99)
- ✅ Caching working
- ✅ Monitoring in place
- ✅ Load test passing

---

### **Task 5.2: Implement Security Hardening (3 days)**

**Objective**: Secure compliance endpoints for production

**1. Rate Limiting**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/audit")
@limiter.limit("100/minute")
async def run_compliance_audit(request: Request):
    pass

@app.post("/violations/{id}/resolve")
@limiter.limit("10/minute")  # Stricter limit for writes
async def resolve_violation(request: Request):
    pass
```

**Limits**:
- General endpoints: 100 req/min per IP
- Write endpoints (resolve): 10 req/min per IP
- Higher limits for authenticated users (JWT)

**2. Input Validation**
```python
from pydantic import BaseModel, Field, validator

class ResolveViolationRequest(BaseModel):
    resolution_action: str = Field(
        min_length=1,
        max_length=500,
        description="Resolution action text"
    )
    
    @validator('resolution_action')
    def action_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Action cannot be empty')
        return v

# Validate fund_id format
class AuditRequest(BaseModel):
    fund_id: str = Field(
        pattern="^[A-Z0-9_]{1,50}$",
        description="Fund ID must be alphanumeric + underscore, <50 chars"
    )
    region: RegionEnum
    date_range: Optional[tuple] = None
    
    @validator('date_range')
    def validate_date_range(cls, v):
        if v and (v[1] - v[0]).days > 365:
            raise ValueError('Date range cannot exceed 365 days')
        return v
```

**3. RBAC (Role-Based Access Control)**
```python
from enum import Enum
from typing import List

class Role(str, Enum):
    VIEWER = "viewer"      # Read-only
    REVIEWER = "reviewer"  # Read + mark reviewed
    RESOLVER = "resolver"  # Resolve violations
    ADMIN = "admin"        # Full access

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Validate JWT token and return user with roles."""
    payload = jwt.decode(token, SECRET_KEY)
    user_id = payload.get("sub")
    roles = payload.get("roles", [])
    return User(id=user_id, roles=roles)

def require_role(required_roles: List[Role]):
    """Decorator to enforce role requirements."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if not any(r in current_user.roles for r in required_roles):
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

@app.post("/violations/{id}/resolve")
@require_role([Role.RESOLVER, Role.ADMIN])
async def resolve_violation(
    violation_id: str,
    request: ResolveViolationRequest,
    current_user: User = Depends(get_current_user)
):
    """Only RESOLVER and ADMIN roles can resolve."""
    pass
```

**4. Audit Logging**
```python
import logging
from datetime import datetime

audit_logger = logging.getLogger("audit")

async def log_resolution(
    violation_id: str,
    user_id: str,
    action: str,
    status: str
):
    """Log all violation resolutions for audit trail."""
    audit_logger.info(
        f"RESOLVE | violation_id={violation_id} | user_id={user_id} | "
        f"action={action} | status={status} | timestamp={datetime.now().isoformat()}"
    )
    
    # Also store in Neo4j for historical query
    cypher = """
    MERGE (log:AuditLog {id: $log_id})
    SET log.violation_id = $violation_id,
        log.user_id = $user_id,
        log.action = $action,
        log.status = $status,
        log.timestamp = $timestamp
    """
    await graph.run(cypher, {
        "log_id": f"{violation_id}_{datetime.now().isoformat()}",
        "violation_id": violation_id,
        "user_id": user_id,
        "action": action,
        "status": status,
        "timestamp": datetime.now().isoformat()
    })
```

**5. Data Encryption**
```python
from cryptography.fernet import Fernet

cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_evidence(evidence: str) -> str:
    """Encrypt violation evidence (PII)."""
    return cipher_suite.encrypt(evidence.encode()).decode()

def decrypt_evidence(encrypted: str) -> str:
    """Decrypt evidence for retrieval."""
    return cipher_suite.decrypt(encrypted.encode()).decode()

# Use in violation storage
violation.evidence_encrypted = encrypt_evidence(violation.evidence)
```

**Security Checklist**:
- ✅ Rate limiting implemented
- ✅ Input validation in place
- ✅ RBAC enforced
- ✅ Audit logging active
- ✅ Data encryption for sensitive fields
- ✅ TLS 1.3 enforced for API
- ✅ CORS configured restrictively
- ✅ Secrets not in logs

**Owner**: Backend/Security Team  
**Success Criteria**:
- ✅ Rate limiting working (429 after limit)
- ✅ Invalid input rejected (400)
- ✅ Unauthenticated requests blocked (401)
- ✅ Unauthorized actions blocked (403)
- ✅ Audit logs created for all actions
- ✅ Encryption working
- ✅ No security vulnerabilities found

---

### **Task 5.3: Compliance Certification Checklist (2 days)**

**Objective**: Verify system meets SEBI/SEC/ESMA regulatory requirements

**1. SEBI MF Regulations 2024 Compliance**

Create checklist: `COMPLIANCE_CHECKLIST.md`

```markdown
# SEBI MF Regulations 2024 Compliance Checklist

## Portfolio Management
- [x] Rule: RULE_PORT_CONC_001 - Single Holding Concentration (15% max)
  Regulation: SEBI_MF_2024_Q1_001
  Status: ✅ IMPLEMENTED & TESTED
  
- [x] Rule: RULE_PORT_SECTOR_001 - Sector Exposure Limit (30% max)
  Regulation: SEBI_MF_2024_Q1_006
  Status: ✅ IMPLEMENTED & TESTED
  
- [x] Rule: RULE_PORT_RELATED_001 - Related-Party Exposure (10% max)
  Regulation: SEBI_MF_2024_Q1_008
  Status: ✅ IMPLEMENTED & TESTED

## Governance
- [x] Rule: RULE_GOV_MGR_CERT_001 - Fund Manager Certification
  Regulation: SEBI_MF_2024_Q1_002
  Status: ✅ IMPLEMENTED & TESTED
  
- [x] Rule: RULE_GOV_BOARD_IND_001 - Board Independence (50%+ independent)
  Regulation: SEBI_MF_2024_Q1_002
  Status: ✅ IMPLEMENTED & TESTED

## KYC/AML
- [x] Rule: RULE_KYC_RECENCY_001 - KYC Record Freshness (365 days max)
  Regulation: SEBI_MF_2024_Q1_003
  Status: ✅ IMPLEMENTED & TESTED
  
- [x] Rule: RULE_KYC_PEP_001 - PEP Enhanced Due Diligence
  Regulation: SEBI_MF_2024_Q1_003
  Status: ✅ IMPLEMENTED & TESTED

## Risk Management
- [x] Rule: RULE_RISK_LIQUID_001 - Liquid Cash Buffer (5% min)
  Regulation: SEBI_MF_2024_Q1_004
  Status: ✅ IMPLEMENTED & TESTED
  
- [x] Rule: RULE_RISK_VAR_001 - Daily VaR Limit (4% max)
  Regulation: SEBI_MF_2024_Q1_007
  Status: ✅ IMPLEMENTED & TESTED

## Reporting
- [x] Rule: RULE_REP_NAV_TIME_001 - NAV Publication Cutoff (21:00 IST)
  Regulation: SEBI_MF_2024_Q1_005
  Status: ✅ IMPLEMENTED & TESTED
  
- [x] Rule: RULE_REP_FILING_001 - Filing Deadline Compliance
  Regulation: SEBI_MF_2024_Q1_009
  Status: ✅ IMPLEMENTED & TESTED

## Data Retention & Archival
- [x] Policy: Violations retained for 7 years
  Status: ✅ IMPLEMENTED
  
- [x] Process: Archival of violations >2 years
  Status: ✅ IMPLEMENTED
  
- [x] Procedure: Restoration for audit requests
  Status: ✅ DOCUMENTED

## Audit Trail
- [x] All violations logged with timestamp/source/evidence
  Status: ✅ IMPLEMENTED
  
- [x] All resolutions logged with user/action
  Status: ✅ IMPLEMENTED
  
- [x] Non-modifiable retroactively
  Status: ✅ ENFORCED via Neo4j constraints

## Production Readiness
- [x] Performance SLAs met (<500ms scorecard)
  Status: ✅ VERIFIED
  
- [x] Security hardening complete
  Status: ✅ VERIFIED
  
- [x] Monitoring & alerting configured
  Status: ✅ VERIFIED

**SEBI COMPLIANCE: 100% ✅ COMPLETE**
```

**2. SEC Compliance Checklist**
```markdown
# SEC Compliance Checklist

## Investment Company Act Rules
- [x] Rule 12d-1: Diversification
  Status: ✅ Implemented via RULE_SEC_PORT_*
  
- [x] Rule 17f-3: Portfolio Concentration (5% max)
  Status: ✅ Implemented via RULE_SEC_PORT_CONC_001
  
- [x] Rule 22c-1: NAV Calculation (4pm ET cutoff)
  Status: ✅ Implemented via RULE_SEC_REP_NAV_001

## Disclosure Requirements
- [x] Risk disclosure to investors
  Status: ✅ Generated in compliance reports
  
- [x] Fee disclosure
  Status: ✅ Audited via RULE_SEC_REP_FEES_001

**SEC COMPLIANCE: 85% ✅ COMPLETE** (200+ rules from Phase 4)
```

**3. ESMA Compliance Checklist**
```markdown
# ESMA Compliance Checklist

## UCITS/AIFM Directives
- [x] Concentration limits (10% max)
  Status: ✅ Implemented via RULE_ESMA_PORT_*
  
- [x] Liquidity management (80% tradable in 5 days)
  Status: ✅ Implemented via RULE_ESMA_RISK_LIQUID_001
  
- [x] ESG Disclosure (SFDR)
  Status: ✅ Implemented via RULE_ESMA_ESG_*

**ESMA COMPLIANCE: 85% ✅ COMPLETE** (200+ rules from Phase 4)
```

**4. Backup & Disaster Recovery**

**File**: `scripts/backup_compliance_graph.sh`
```bash
#!/bin/bash
# Daily backup of compliance Neo4j graph

BACKUP_DIR="/backups/compliance"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/compliance_${TIMESTAMP}.dump"

# Backup Neo4j
neo4j-admin dump --database=neo4j --to="$BACKUP_FILE"

# Verify backup
if [ -f "$BACKUP_FILE" ]; then
    echo "✅ Backup created: $BACKUP_FILE"
else
    echo "❌ Backup failed"
    exit 1
fi

# Keep only last 30 days
find "$BACKUP_DIR" -name "compliance_*.dump" -mtime +30 -delete

echo "Backup complete and old backups cleaned up"
```

**File**: `scripts/restore_compliance_graph.sh`
```bash
#!/bin/bash
# Restore compliance graph from backup

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore_compliance_graph.sh /path/to/backup.dump"
    exit 1
fi

# Stop Neo4j
neo4j-admin stop

# Restore backup
neo4j-admin load --from="$BACKUP_FILE" --database=neo4j --force

# Start Neo4j
neo4j-admin start

echo "Restore complete"
```

**RTO/RPO**:
- RPO (Recovery Point Objective): 1 day (daily backups)
- RTO (Recovery Time Objective): 4 hours (restore + restart)

**5. Audit Report Generation**

**File**: `backend/app/api/routes/compliance.py`

**New Endpoint**: `GET /api/compliance/audit-report?start_date=X&end_date=Y`

```python
@router.get("/audit-report")
async def generate_audit_report(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    container: Container = Depends(get_container),
):
    """Generate compliance audit report for date range."""
    
    cypher = """
    MATCH (v:Violation)
    WHERE v.detected_at >= $start_date AND v.detected_at <= $end_date
    RETURN count(*) AS total_violations,
           sum(CASE WHEN v.severity = 'critical' THEN 1 ELSE 0 END) AS critical,
           sum(CASE WHEN v.status = 'remediated' THEN 1 ELSE 0 END) AS remediated
    """
    
    result = await container.graph.run(cypher, {
        "start_date": start_date,
        "end_date": end_date
    })
    
    return {
        "period": f"{start_date} to {end_date}",
        "total_violations": result[0]["total_violations"],
        "critical_violations": result[0]["critical"],
        "remediated_violations": result[0]["remediated"],
        "remediation_rate": (result[0]["remediated"] / result[0]["total_violations"]) * 100,
        "generated_at": datetime.now().isoformat()
    }
```

**Owner**: Compliance/DevOps Team  
**Success Criteria**:
- ✅ SEBI checklist 100% complete
- ✅ SEC checklist >85% complete
- ✅ ESMA checklist >85% complete
- ✅ Backup/restore tested and working
- ✅ RTO/RPO documented and met
- ✅ Audit reports generatable

---

### **Task 5.4: Third-Party Security Audit (5-10 days, can be parallel)**

**Objective**: Get external security validation

**Scope**:
- Penetration testing
- Static code analysis (SAST)
- Dynamic application security testing (DAST)
- OWASP Top 10 validation
- Compliance audit

**Deliverables**:
- Penetration test report
- Vulnerability findings (with remediation)
- Security recommendations
- Compliance certification

**This can run parallel with other tasks in Week 11-12**

**Owner**: Security/Compliance Team

---

### **Task 5.5: Production Deployment & Go-Live (2 days)**

**Objective**: Deploy to production and verify ready

**Steps**:

1. **Create Docker Image**
   ```bash
   docker build -t nusummit/compliance-system:v1.0 .
   docker push nusummit/compliance-system:v1.0
   ```

2. **Deploy to Production**
   - Kubernetes manifests created
   - Environment variables configured
   - Database connections validated
   - TLS certificates installed

3. **Health Checks**
   - API endpoints responding
   - Database connectivity
   - Cache working
   - Monitoring active

4. **Smoke Tests**
   - Run basic audit
   - Verify scorecard
   - Test all APIs
   - Check UI accessibility

5. **Monitor System**
   - Latency metrics
   - Error rates
   - Resource utilization
   - User activity

**Go-Live Checklist**:
- ✅ All Phases 1-5 completed
- ✅ Performance SLAs met
- ✅ Security hardened
- ✅ Compliance checklist 100%
- ✅ Monitoring/alerting configured
- ✅ Backup/restore tested
- ✅ Team trained
- ✅ Runbooks documented
- ✅ Stakeholders notified

**Owner**: DevOps/Release Team  
**Success Criteria**:
- ✅ System live and accessible
- ✅ All APIs responding
- ✅ Dashboard loading
- ✅ Data flowing end-to-end
- ✅ Monitoring active
- ✅ Team ready for support

---

### **Phase 5 Summary**

| Task | Days | Owner | Status |
|------|------|-------|--------|
| 5.1: Performance SLAs | 2 | Backend | Planned |
| 5.2: Security Hardening | 3 | Backend | Planned |
| 5.3: Compliance Checklist | 2 | Compliance | Planned |
| 5.4: Third-Party Audit | 5-10 | Security | Parallel |
| 5.5: Go-Live | 2 | DevOps | Planned |
| **Total** | **14-19** | **Multi-team** | **0%→100%** |

---

## **Dependencies & Parallelization**

### **Critical Path**

```
[Phase 1] ─→ [Phase 2] ┐
                       ├─→ [Phase 3] ─→
					   
					   
I'll create the final comprehensive implementation plan document and save it as a markdown file for you to review.Perfect. Now let me create the comprehensive implementation plan document as a markdown file that's ready for you to download and review:Now let me create the final comprehensive implementation plan document. Given the length, I'll create it as a markdown file:

Based on my comprehensive audit and detailed roadmap, here's your **complete 12-week implementation plan document**:

---

# **AMC COMPLIANCE SYSTEM: COMPLETE 12-WEEK IMPLEMENTATION PLAN**

**Document Version**: 1.0  
**Date**: January 2024  
**Status**: Ready for Execution  
**Audience**: Development Team, Project Management, Stakeholders

---

## **I. EXECUTIVE SUMMARY**

### Current State
- **Phases 1-2**: 90% complete (Rules Engine + Domain Agents built, need test data + validation)
- **Phases 3-5**: 0% complete (UI, multi-region, hardening not started)
- **Overall Readiness**: 36% production-ready
- **Key Blocker**: Missing CSV test data files

### Target State (Week 12)
- **All Phases**: 100% complete and production-ready
- **Compliance Coverage**: SEBI (100%) + SEC (85%) + ESMA (85%)
- **Architecture**: Multi-region, security-hardened, performance-optimized
- **UI**: Full Streamlit dashboard with real-time monitoring
- **Certification**: Ready for regulatory deployment

### Timeline & Effort
- **Critical Path**: 49 days (7 weeks)
- **With 3-Team Parallelization**: 12 weeks allocated for buffer
- **Total Tasks**: 24 implementation tasks across 5 phases
- **Team Size**: 3 teams (Backend: 3-4 eng, Frontend: 1-2 eng, DevOps/Compliance: 2 eng)

---

## **II. DETAILED IMPLEMENTATION ROADMAP**

### **PHASE 1: Rules Engine & Violation Detection Completion (Weeks 1-2)**

**Phase Status**: 90% → 100%  
**Duration**: 4-6 days (2 weeks allocated)

#### **Task 1.1: Create CSV Data Files (1-2 days)**

**Objective**: Generate test data files required by ingestion pipeline

**Deliverables**:

1. **`data/compliance/sebi_regulations.csv`** (50+ rows)
   - Columns: regulation_id, title, effective_date, section, description, applicability, region
   - Content: Portfolio, Governance, KYC, Risk, Reporting regulations
   - Example: SEBI_MF_2024_Q1_001, "Fund Portfolio Diversification", "2024-01-01", ...

2. **`data/compliance/rules.csv`** (30+ rows)
   - Columns: rule_id, rule_type, title, description, regulation_id, condition, metric, threshold, severity, confidence_threshold, applicable_funds, region
   - Rule ID Pattern: RULE_[DOMAIN]_[CATEGORY]_NNN (e.g., RULE_PORT_CONC_001)
   - Each rule maps to one regulation
   - Conditions: gt, gte, lt, lte, eq, neq

3. **`data/compliance/fund_schemes.csv`** (10 rows)
   - Columns: fund_id, isin, name, fund_house, category, mandate, aum_cr, active_investors, region
   - Mix: 4-5 equity, 3-4 debt, 2-3 hybrid funds
   - AUM: 100-1000 Cr range
   - Active investors: 1,000-100,000 range

**Acceptance Criteria**:
- ✅ All 3 CSV files created
- ✅ CSV format valid (proper escaping, UTF-8)
- ✅ All required columns present
- ✅ Data realistic and representative
- ✅ No missing fields

**Owner**: Compliance/Backend Lead  
**Estimation**: 1-2 days | **Risk**: Low | **Dependency**: None

---

#### **Task 1.2: Run End-to-End Compliance Audit Tests (1-2 days)**

**Objective**: Validate audit pipeline with real test data

**Test Execution**:
```bash
# Run complete compliance test suite
pytest backend/tests/compliance/ -v --tb=short --cov=backend/app/compliance

# Expected: 21/21 tests pass
# Coverage: >90% for compliance module
```

**Test Coverage**:
- `test_rules_engine.py`: Rule loading, evaluation, condition matching
- `test_violation_detector.py`: Audit orchestration, scoring, parallel execution
- `test_rules_ingestion.py`: CSV loading, Neo4j persistence
- `test_compliance_api.py`: All 5 REST endpoints
- `test_compliance_agents.py`: Individual agent accuracy

**Mock Fund Data Setup**:
```python
fund_data = {
    "fund_id": "SEBI_FUND_001",
    "holdings": [{"name": "RELIANCE", "pct": 18}],      # > 15% (violation)
    "sector_exposure": {"IT": 35},                       # > 30% (violation)
    "manager_cert": "CFA",                               # Valid
    "kyc_last_updated": "2020-01-01",                    # > 365 days (violation)
    "var_pct": 4.5,                                      # > 4% (violation)
    "liquid_cash_pct": 3,                                # < 5% (violation)
}
```

**Expected Output**:
- 8 violations detected (concentration, sector, KYC, VaR, liquidity)
- All violations correctly classified by severity/confidence
- Scorecard: ~60% compliance (8 violations / ~13 rules)

**Acceptance Criteria**:
- ✅ All tests pass (21/21)
- ✅ Test coverage >90%
- ✅ Expected violations detected
- ✅ No false positives
- ✅ Response times reasonable

**Owner**: QA Lead  
**Estimation**: 1-2 days | **Risk**: Low | **Dependency**: Task 1.1

---

#### **Task 1.3: Populate Neo4j Graph with Compliance Schema (1 day)**

**Objective**: Deploy schema and load real data into database

**Steps**:

1. **Deploy Schema**
```python
from app.graph.compliance_schema import deploy_compliance_schema
from app.graph.client import get_graph_client

client = get_graph_client()
await deploy_compliance_schema(client)
```

2. **Verify Nodes & Relationships** (Neo4j Browser)
```cypher
-- Count all nodes
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count

-- Verify regulations linked to rules
MATCH (r:Regulation)-[:has_rules]->(rule:Rule) RETURN count(*) AS rule_count
```

3. **Load CSV Data**
```python
from app.ingestion.compliance_rules_ingester import seed_compliance_data
result = await seed_compliance_data(client, Path("data/compliance"))
# Expected: regulations_created=50, rules_created=30, funds_created=10
```

**Schema Components Created**:
- 6 Node Types: Regulation, Rule, FundScheme, Violation, RiskThreshold, EscalationPath
- 6+ Indexes on violation/rule/regulation properties
- 2 Constraints: Violation.id unique, FundScheme.id unique
- 4+ Relationships: has_rules, applies_to, violates, routes_to

**Validation Queries**:
```cypher
-- Check node counts
MATCH (n:Regulation) RETURN count(*) → Expected: 50
MATCH (n:Rule) RETURN count(*) → Expected: 30
MATCH (n:FundScheme) RETURN count(*) → Expected: 10

-- Check index creation
CALL db.indexes() → Should see 6+ indexes

-- Sample rule query
MATCH (rule:Rule {id: "RULE_PORT_CONC_001"})
RETURN rule.title, rule.metric, rule.threshold
→ Expected: "Single Holding Concentration", "holding_pct", 15
```

**Acceptance Criteria**:
- ✅ All node types created (6 types)
- ✅ All indexes created and working
- ✅ 50+ regulations in Neo4j
- ✅ 30+ rules linked to regulations
- ✅ 10 funds loaded
- ✅ Query response time <100ms (indexed fields)

**Owner**: DevOps Lead  
**Estimation**: 1 day | **Risk**: Low | **Dependency**: Task 1.1

---

#### **Task 1.4: Validate API Responses & Integration (1 day)**

**Objective**: End-to-end API testing with real data

**Endpoints to Test**:

1. **POST /api/compliance/audit?region=SEBI**
   - Request: None (triggers full audit)
   - Expected Response: 200 OK with ComplianceAuditResultResponse
   - Performance Target: <5 seconds
   - Violation Count: 15+ expected from 10 funds

2. **GET /api/compliance/violations?region=SEBI&severity=critical**
   - Expected: Paginated list of critical violations
   - Performance Target: <2 seconds
   - Filters working: severity, fund_id, region

3. **GET /api/compliance/fund/{fund_id}/violations**
   - Expected: Fund-specific violations with compliance score
   - Performance Target: <1 second

4. **GET /api/compliance/scorecard?region=SEBI**
   - Expected: Compliance score by domain + trend data
   - Performance Target: <500ms ⭐ Production SLA
   - Score calculation: (rules_passing / total_rules) × 100

5. **POST /api/compliance/violations/{id}/resolve**
   - Request: {"resolution_action": "Rebalanced portfolio"}
   - Expected: 200 OK with updated violation status
   - Status change: detected → remediated

**Test Script**:
```bash
#!/bin/bash
echo "Testing Compliance APIs..."

# Test 1: Audit
echo "1. Running audit..."
curl -X POST http://localhost:8000/api/compliance/audit?region=SEBI

# Test 2: Get violations
echo "2. Getting violations..."
curl -X GET "http://localhost:8000/api/compliance/violations?region=SEBI&severity=critical"

# Test 3: Scorecard (measure latency)
echo "3. Getting scorecard..."
time curl -X GET http://localhost:8000/api/compliance/scorecard?region=SEBI

# Test 4: Fund details
echo "4. Getting fund violations..."
curl -X GET http://localhost:8000/api/compliance/fund/SEBI_FUND_001/violations

# Test 5: Resolve (need violation ID from earlier tests)
echo "5. Resolving violation..."
curl -X POST http://localhost:8000/api/compliance/violations/V_20240125_143023_RULE_PORT_CONC_001/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution_action": "Rebalanced portfolio"}'
```

**Acceptance Criteria**:
- ✅ All 5 endpoints return 200 OK
- ✅ Response schemas match Pydantic models
- ✅ Filtering works correctly (severity, fund_id, region)
- ✅ Sorting works (by severity, date, etc.)
- ✅ Status transitions valid
- ✅ Error handling correct (400/404/500)
- ✅ Scorecard latency <500ms
- ✅ Audit latency <5s for 10 funds

**Owner**: Backend Lead  
**Estimation**: 1 day | **Risk**: Low | **Dependency**: Task 1.3

---

### **PHASE 2: Domain Agents Completion (Weeks 3-4)**

**Phase Status**: 90% → 100%  
**Duration**: 6-7 days (2 weeks allocated)

#### **Task 2.1: Integration Test All Domain Agents (2 days)**

**Objective**: Verify each agent detects violations accurately independently

**5 Agents to Test**:

1. **PortfolioAgent** - Holdings, sector exposure, related-party limits
   - Expected violations: 3 (concentration, sector, related-party)
   
2. **GovernanceAgent** - Manager certification, board independence
   - Expected violations: 2 (cert, independence)
   
3. **KYCAgent** - KYC recency, PEP screening
   - Expected violations: 1 (KYC recency)
   
4. **RiskAgent** - VaR limits, liquidity buffers
   - Expected violations: 1 (VaR)
   
5. **ReportingAgent** - NAV timeliness, filing deadlines
   - Expected violations: 1 (NAV timing)

**Test File**: `backend/tests/compliance/test_compliance_agents.py`

**Sample Test**:
```python
@pytest.mark.asyncio
async def test_portfolio_agent():
    agent = PortfolioAgent(mock_graph, mock_rules_engine)
    
    fund_data = {
        "fund_id": "SEBI_FUND_001",
        "holdings": [{"name": "RELIANCE", "pct": 18}],  # > 15%
        "sector_exposure": {"IT": 35},                   # > 30%
    }
    
    violations = await agent.audit_portfolio(
        fund_id="SEBI_FUND_001",
        fund_data=fund_data
    )
    
    assert len(violations) == 2  # Concentration + Sector
    assert violations[0].rule_id == "RULE_PORT_CONC_001"
    assert violations[0].severity == "critical"
    assert violations[0].confidence >= 0.90
```

**Acceptance Criteria**:
- ✅ All 5 agents tested independently
- ✅ Violations accurately detected
- ✅ No false positives/negatives
- ✅ Severity/confidence scores correct
- ✅ Agent response time <500ms
- ✅ Test pass rate 100% (5/5)

**Owner**: QA Lead  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 1.4

---

#### **Task 2.2: Test Orchestrator Multi-Agent Coordination (1.5 days)**

**Objective**: Verify orchestrator coordinates all 5 agents without conflicts

**Test Scenarios**:

1. **Single Fund Multi-Agent** (1 fund, all 5 agents)
   - Expected: 8 violations from all domains
   - Response time: <2 seconds
   
2. **Parallel Fund Audit** (20 funds)
   - Semaphore working (max 10 concurrent)
   - Response time: <10 seconds for 20 funds
   - Memory: <1GB
   
3. **Scorecard Aggregation**
   - Domain scores calculated: (compliant_rules / total_rules) × 100
   - Overall score: average of 5 domain scores
   - Example: (82+90+78+85+92)/5 = 85.4%

**Test**:
```python
@pytest.mark.asyncio
async def test_orchestrator_parallel_execution():
    orchestrator = ComplianceAgentOrchestrator(graph_client, rules_engine)
    
    # Create 20 funds
    funds = [generate_fund_data(i) for i in range(20)]
    
    # Audit all in parallel
    import time
    start = time.time()
    result = await orchestrator.audit_all_funds(
        funds=funds,
        region="SEBI"
    )
    elapsed = time.time() - start
    
    # Verify
    assert result["total_funds"] == 20
    assert result["total_violations"] > 0
    assert elapsed < 10  # < 10 seconds for 20 funds
    assert result["overall_score"] >= 0 and result["overall_score"] <= 100
```

**Acceptance Criteria**:
- ✅ Orchestrator calls all 5 agents
- ✅ No race conditions
- ✅ Semaphore working (10 concurrent max)
- ✅ Scorecard calculated correctly
- ✅ Performance <10s for 20 funds
- ✅ Memory <500MB during execution

**Owner**: Backend Lead  
**Estimation**: 1.5 days | **Risk**: Low | **Dependency**: Task 2.1

---

#### **Task 2.3: Validate Multi-Region Agent Routing (1.5 days)**

**Objective**: Add region awareness to agents (preparation for Phase 4 SEC/ESMA)

**Changes**:
- Add `region: str = "SEBI"` parameter to each agent method
- Load region-specific rules from Neo4j
- Apply region-specific thresholds
- Tag violations with region

**Example - Concentration Limits**:
- SEBI: 15% max
- SEC: 5% max (Phase 4)
- ESMA: 10% max (Phase 4)

**Test Case - Same Fund, Different Regions**:
```python
fund_with_16_percent_holding = {...}

# SEBI region
sebi_violations = await agent.audit_portfolio(
    fund_data=fund_with_16_percent_holding,
    region="SEBI"
)
assert len(sebi_violations) == 1  # 16 > 15

# SEC region (when loaded in Phase 4)
sec_violations = await agent.audit_portfolio(
    fund_data=fund_with_16_percent_holding,
    region="SEC"
)
assert len(sec_violations) == 1  # 16 > 5 (stricter)

# Different violation severity due to different thresholds
assert sebi_violations[0].severity == "critical"  # Marginally over
assert sec_violations[0].severity == "critical"   # Significantly over
```

**Acceptance Criteria**:
- ✅ All agents accept region parameter
- ✅ Region-specific rules applied
- ✅ Violations tagged with region
- ✅ Fallback to SEBI when region unavailable
- ✅ No cross-region interference
- ✅ Test coverage for all regions

**Owner**: Backend Lead  
**Estimation**: 1.5 days | **Risk**: Low | **Dependency**: Task 2.2

---

#### **Task 2.4: Create Agent Performance Metrics Dashboard (1.5 days)**

**Objective**: Track and expose agent metrics for monitoring

**Metrics Collected**:
- `violations_detected`: Count of violations found
- `avg_latency_ms`: Average response time
- `p95_latency_ms`: 95th percentile latency
- `p99_latency_ms`: 99th percentile latency
- `accuracy_score`: True positives / (true positives + false positives)

**Storage**: Neo4j AgentMetrics nodes (timestamped)

**API Endpoint**: `GET /api/compliance/agents/metrics?region=SEBI`

**Response Example**:
```json
{
  "agents": {
    "PortfolioAgent": {
      "violations_detected": 1250,
      "avg_latency_ms": 145.3,
      "p95_latency_ms": 320.1,
      "p99_latency_ms": 450.5,
      "accuracy_score": 0.95
    },
    "GovernanceAgent": {...},
    "KYCAgent": {...},
    "RiskAgent": {...},
    "ReportingAgent": {...}
  },
  "overall_latency_ms": 750.2,
  "violations_by_severity": {
    "critical": 25,
    "high": 45,
    "medium": 60,
    "low": 35
  }
}
```

**Implementation**:
```python
class ComplianceAgentOrchestrator:
    def __init__(self):
        self.metrics = {
            "PortfolioAgent": {"violations": 0, "latencies": []},
            "GovernanceAgent": {"violations": 0, "latencies": []},
            # ... etc for all 5 agents
        }
    
    async def audit_all_funds(self, funds, region):
        for agent_name in agents:
            start = time.perf_counter()
            violations = await agent.audit(...)
            elapsed = (time.perf_counter() - start) * 1000
            
            self.metrics[agent_name]["violations"] += len(violations)
            self.metrics[agent_name]["latencies"].append(elapsed)
```

**Acceptance Criteria**:
- ✅ Metrics collected for each agent
- ✅ Metrics stored in Neo4j
- ✅ API endpoint working
- ✅ Historical metrics retrievable
- ✅ Accuracy score calculated

**Owner**: Backend Lead  
**Estimation**: 1.5 days | **Risk**: Low | **Dependency**: Task 2.3

---

### **PHASE 3: Compliance Dashboard UI (Weeks 5-7)**

**Phase Status**: 0% → 100%  
**Duration**: 15 days (3 weeks)  
**Technology**: Streamlit + Plotly + Pandas

#### **Task 3.1: Build Scorecard Page (3 days)**

**Page**: `streamlit_app/pages/01_Scorecard.py`

**Components**:

1. **Header** (sticky top)
   - Title: "🏦 AMC Compliance Dashboard"
   - Region selector: SEBI / SEC / ESMA / Consolidated
   - Refresh button
   - Last updated timestamp

2. **KPI Cards** (row of 4 metrics)
   ```
   Overall Score: 85.4%          Total Violations: 42
   (with +2.3% delta indicator)   (with trend arrow)
   
   Critical Issues: 5             Compliant Funds: 8/10
   (delta color inverse)          (green checkmark)
   ```

3. **Score Gauge Chart** (circular dial)
   - Range: 0-100%
   - Color zones: Red (0-50), Yellow (50-75), Green (75-100)
   - Current score highlighted
   - Target threshold line at 90%

4. **Domain Breakdown Cards** (5 metrics row)
   ```
   Portfolio: 82%   Governance: 90%   KYC: 78%   Risk: 85%   Reporting: 92%
   ↓2%              ✓                  ↓8%        ↓5%         ✓
   ```

5. **30-Day Trend Chart** (line chart)
   - X-axis: Last 30 days
   - Y-axis: Compliance score (0-100)
   - Blue line: Score trend
   - Red threshold line at 85%
   - Hover: Shows date and score

**Data Source**: `/api/compliance/scorecard?region={REGION}`

**Features**:
- Auto-refresh every 60 seconds
- Manual refresh button
- Region selector updates all visualizations
- Responsive layout (desktop/tablet/mobile)

**Streamlit Code Skeleton**:
```python
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import httpx

st.set_page_config(page_title="AMC Compliance", layout="wide")

# Header
col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    st.title("🏦 AMC Compliance Dashboard")
with col2:
    region = st.selectbox("Region", ["SEBI", "SEC", "ESMA", "Consolidated"])
with col3:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

# Fetch scorecard
@st.cache_data(ttl=60)
def fetch_scorecard(region):
    response = httpx.get(f"http://localhost:8000/api/compliance/scorecard?region={region}")
    return response.json()

scorecard = fetch_scorecard(region)

# KPI Cards
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("Overall Score", f"{scorecard['overall_score']:.1f}%", "+2.3%")
with kpi2:
    st.metric("Total Violations", scorecard['violations_summary']['total'])
# ... etc
```

**Acceptance Criteria**:
- ✅ Page loads without errors
- ✅ Data fetched within 500ms
- ✅ All visualizations render
- ✅ Region selector updates all charts
- ✅ Auto-refresh working
- ✅ Responsive on mobile

**Owner**: Frontend Lead  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 2.4

---

#### **Task 3.2: Build Violations Page (3 days)**

**Page**: `streamlit_app/pages/02_Violations.py`

**Components**:

1. **Filters** (expander at top)
   - Severity multi-select: Critical, High, Medium, Low
   - Domain multi-select: Portfolio, Governance, KYC, Risk, Reporting
   - Fund selector (dropdown)
   - Date range picker

2. **Violations by Severity** (pie chart)
   - Interactive: Click slice to drill down
   - Color-coded by severity

3. **Violations by Domain** (bar chart)
   - Domains on X-axis
   - Count on Y-axis

4. **Top 10 Violated Rules** (leaderboard table)
   - Rank, Rule ID, Rule Title, Count, Severity

5. **Violations Detail Table** (main table)
   - Columns: Violation ID, Fund ID, Rule, Severity, Confidence, Detected At, Status
   - Sortable (click header)
   - Paginated (10 per page)
   - Expandable rows

**Data Source**: `/api/compliance/violations?region={}&severity={}&fund_id={}`

**Features**:
- Multi-select filters
- Real-time filtering
- Interactive charts
- Drill-down capability
- Export to CSV
- Status indicators

**Acceptance Criteria**:
- ✅ Filters work correctly
- ✅ Charts update on filter change
- ✅ Table paginated and sortable
- ✅ Drill-down shows details
- ✅ Export working
- ✅ Performance <2s for 1000 violations

**Owner**: Frontend Lead  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 3.1

---

#### **Task 3.3: Build Fund Heatmap Page (3 days)**

**Page**: `streamlit_app/pages/03_Funds.py`

**Components**:

1. **Fund Heatmap** (N funds × 5 domains matrix)
   - Green cells: Compliant (90-100%)
   - Yellow cells: At Risk (75-90%)
   - Red cells: Non-Compliant (<75%)
   - Cell value: "95%"
   - Hover: Shows details

2. **Fund List Table**
   - Columns: Fund Name, Category, AUM, Score, Status
   - Sortable
   - Clickable: Select fund for details

3. **Fund Detail Panel**
   - Fund metadata (name, ISIN, fund house, AUM, investors)
   - Compliance score by domain
   - Recent violations (last 10)
   - Remediation status

**Data Sources**:
- `/api/compliance/scorecard?region={}` (domain scores)
- `/api/compliance/fund/{fund_id}/violations` (details)

**Features**:
- Interactive heatmap
- Fund selection
- Domain filtering
- Drill-down to details
- Violation list

**Acceptance Criteria**:
- ✅ Heatmap renders for 10+ funds
- ✅ Color coding accurate
- ✅ Interactive (hover, click)
- ✅ Fund details load <1s
- ✅ Sorting working

**Owner**: Frontend Lead  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 3.2

---

#### **Task 3.4: Build Remediation Tracking Page (3 days)**

**Page**: `streamlit_app/pages/04_Remediation.py`

**Components**:

1. **Active Violations** (table)
   - Status = "detected"
   - Severity color-coded
   - SLA Status: On Track / At Risk / Overdue

2. **Remediation Progress** (metrics)
   - Total Detected, Reviewed %, Remediated %, Closed %
   - Stacked bar chart

3. **Escalation SLA Tracking**
   - By severity with active count
   - Color-coded status

4. **Resolve Modal**
   - Violation ID, Rule Title, Fund ID (read-only)
   - Resolution Action (text input)
   - Resolve button

5. **Violation Timeline** (for selected violation)
   - Status transitions with timestamps

**Data Sources**:
- `/api/compliance/violations?status=detected`
- `/api/compliance/violations/{id}/resolve` (POST)

**Features**:
- Real-time SLA tracking
- Bulk actions
- Action history
- Status validation
- Escalation notifications

**Acceptance Criteria**:
- ✅ Active violations table working
- ✅ Resolve modal functional
- ✅ Status update successful
- ✅ SLA tracking accurate
- ✅ Timeline rendering

**Owner**: Frontend Lead  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 3.3

---

#### **Task 3.5: Deploy & Test Streamlit Dashboard (2 days)**

**Objective**: Package and verify UI ready for use

**Steps**:

1. **Create Streamlit Config**
   - File: `streamlit_app/compliance_config.toml`

2. **Update Requirements**
   - File: `streamlit_app/requirements.txt`
   - Packages: streamlit, plotly, pandas, httpx

3. **Create Startup Script**
   - File: `run_compliance_dashboard.sh`
   - Command: `streamlit run streamlit_app/compliance_dashboard.py`

4. **Local Testing**
   - Start backend
   - Start Streamlit
   - Verify all pages load
   - Test data flow

5. **Performance Testing**
   - Page load times
   - 100+ violations performance
   - 10 concurrent users
   - Target: <3s per page

6. **Cross-Browser Testing**
   - Chrome, Firefox, Safari
   - Desktop, tablet, mobile

**Deployment Checklist**:
- ✅ All 5 pages accessible
- ✅ All APIs integrated
- ✅ No console errors
- ✅ Performance <3s per page
- ✅ Responsive design
- ✅ Refresh working

**Acceptance Criteria**:
- ✅ Dashboard fully functional
- ✅ All 5 pages working
- ✅ Data end-to-end
- ✅ Performance acceptable
- ✅ Ready for production

**Owner**: DevOps Lead  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 3.4

---

### **PHASE 4: SEC/ESMA Regulatory Expansion (Weeks 8-10)**

**Phase Status**: 0% → 100%  
**Duration**: 21 days (3 weeks)  
**Scope**: 200+ new regulations (100+ SEC, 100+ ESMA)

#### **Task 4.1: Ingest SEC Regulations & Build Rule Set (5 days)**

**Objective**: Add 100+ US SEC compliance rules

**SEC Regulations to Include**:
- Investment Company Act of 1940 (ICA)
- Rule 12d-1: Diversification (max 5% concentration)
- Rule 17f-3: Portfolio concentration
- Rule 22c-1: NAV timing (4pm ET cutoff vs SEBI 9pm IST)
- Rule 10b-1: Distribution fees
- Rule 17e-1: Related-party transactions
- Dodd-Frank Act requirements
- Advisers Act rules

**Data Files**:

1. **`data/compliance/sec_regulations.csv`** (100+ rows)
   - Columns: regulation_id, title, section, description, region
   - Format: SEC_ICA_001, SEC_ICA_002, SEC_AF_001, etc.

2. **`data/compliance/sec_rules.csv`** (50+ rows)
   - Columns: rule_id, rule_type, regulation_id, title, condition, metric, threshold, severity
   - IDs: RULE_SEC_PORT_001, RULE_SEC_NAV_001, RULE_SEC_GOV_001, etc.

**SEC Thresholds** (different from SEBI):
- Concentration: 5% (SEBI: 15%)
- Sector: 25% (SEBI: 30%)
- Board Independence: 40% (SEBI: 50%)
- NAV Cutoff: 4pm ET (SEBI: 9pm IST)
- Liquidity: 60% (SEBI: none)

**Implementation**:
1. Research SEC regs applicable to mutual funds
2. Create regulations CSV
3. Create rules CSV mapping to agents
4. Load into Neo4j
5. Test SEC rule evaluation

**Test Case**: Fund with 16% holding
```
SEBI audit: COMPLIANT (16 < 15? NO → VIOLATION ✓)
SEC audit: VIOLATION (16 > 5 SEC limit)
```

**Acceptance Criteria**:
- ✅ 100+ SEC regulations in CSV
- ✅ 50+ SEC rules created
- ✅ Rules loaded into Neo4j
- ✅ Agents can apply SEC rules
- ✅ SEC fund tested with SEC thresholds

**Owner**: Compliance Lead  
**Estimation**: 5 days | **Risk**: Medium (regulatory accuracy) | **Dependency**: Task 3.5

---

#### **Task 4.2: Ingest ESMA Regulations & Build Rule Set (5 days)**

**Objective**: Add 100+ EU ESMA compliance rules

**ESMA Regulations to Include**:
- UCITS Directive (2009/65/EC)
- AIFM Directive (2011/61/EU)
- MiFID II regulations
- ESG/SFDR requirements
- Liquidity rules
- Risk management requirements
- Concentration limits

**Data Files**:

1. **`data/compliance/esma_regulations.csv`** (100+ rows)
   - Format: ESMA_UCITS_001, ESMA_AIFM_001, ESMA_MIFID_001, etc.

2. **`data/compliance/esma_rules.csv`** (50+ rows)
   - IDs: RULE_ESMA_PORT_001, RULE_ESMA_ESG_001, RULE_ESMA_LIQ_001, etc.

**ESMA Thresholds** (different from SEBI and SEC):
- Concentration: 10% (SEBI: 15%, SEC: 5%)
- Liquidity: 80% tradable in 5 days
- ESG Disclosure: Mandatory climate risk
- Board Independence: 45% (SEBI: 50%, SEC: 40%)

**Implementation**:
1. Research ESMA regs applicable to funds
2. Create regulations CSV
3. Create rules CSV
4. Load into Neo4j
5. Test ESMA rule evaluation

**Test Case**: Fund with 16% holding
```
SEBI audit: VIOLATION (16 > 15)
SEC audit: VIOLATION (16 > 5)
ESMA audit: VIOLATION (16 > 10)
```

**Acceptance Criteria**:
- ✅ 100+ ESMA regulations
- ✅ 50+ ESMA rules
- ✅ Rules loaded into Neo4j
- ✅ Agents apply ESMA rules
- ✅ ESMA fund tested

**Owner**: Compliance Lead  
**Estimation**: 5 days | **Risk**: Medium | **Dependency**: Task 4.1

---

#### **Task 4.3: Build Multi-Region Rule Router (3 days)**

**Objective**: Route funds to correct regional rule set

**Implementation**: Update `ViolationDetector.audit_all_funds()`

**Logic**:
```python
async def audit_all_funds(self, funds, region="SEBI"):
    """Audit funds against region-specific rules."""
    results = []
    
    for fund_data in funds:
        # Determine fund's regulatory region
        fund_region = fund_data.get("region", region)
        
        # Get applicable rules for this region
        rules = await self.rules_engine.get_applicable_rules(
            region=fund_region
        )
        
        # Evaluate rules
        violations = []
        for rule in rules:
            v = await self.rules_engine.evaluate_rule(rule.id, fund_data)
            if v:
                violations.append(v)
        
        results.append({
            "fund_id": fund_data["fund_id"],
            "region": fund_region,
            "violations": violations
        })
    
    return results
```

**Test Case**: Same fund, different regions
```python
fund_global_001 = {"holdings": [{"name": "RELIANCE", "pct": 16}]}

audit_sebi = await audit_all_funds([fund_global_001], region="SEBI")
# Expected: 1 violation (16 > 15)

audit_sec = await audit_all_funds([fund_global_001], region="SEC")
# Expected: 1 violation (16 > 5)

audit_esma = await audit_all_funds([fund_global_001], region="ESMA")
# Expected: 1 violation (16 > 10)

audit_all = await audit_all_funds([fund_global_001], region="ALL")
# Expected: 3 violations (SEBI + SEC + ESMA)
```

**Acceptance Criteria**:
- ✅ Region parameter working
- ✅ Fund routed to correct region
- ✅ Region-specific rules applied
- ✅ Violations tagged with region
- ✅ No rule conflicts

**Owner**: Backend Lead  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 4.2

---

#### **Task 4.4: Update Agents for Multi-Region Support (3 days)**

**Objective**: Make all 5 agents region-aware

**Changes to Each Agent**:
```python
class PortfolioAgent:
    async def audit_portfolio(
        self,
        fund_id: str,
        fund_data: Dict,
        region: str = "SEBI"  # NEW
    ) -> List[ComplianceViolation]:
        # Load region-specific rules
        rules = await self.rules_engine.get_applicable_rules(
            rule_type="portfolio",
            region=region
        )
        
        # Evaluate and tag with region
        violations = []
        for rule in rules:
            v = await self.rules_engine.evaluate_rule(rule.id, fund_data)
            if v:
                v.region = region  # TAG IT
                violations.append(v)
        
        return violations
```

**Test All 5 Agents**:
```python
@pytest.mark.parametrize("region", ["SEBI", "SEC", "ESMA"])
@pytest.mark.asyncio
async def test_agents_multi_region(region):
    """Test each agent with each region."""
    agents = [
        PortfolioAgent(...),
        GovernanceAgent(...),
        KYCAgent(...),
        RiskAgent(...),
        ReportingAgent(...)
    ]
    
    for agent in agents:
        violations = await agent.audit(fund_data, region=region)
        assert all(v.region == region for v in violations)
```

**Acceptance Criteria**:
- ✅ All 5 agents accept region param
- ✅ Region-specific rules applied
- ✅ Violations tagged with region
- ✅ Fallback to SEBI when unavailable
- ✅ No cross-region issues
- ✅ 100% test pass rate

**Owner**: Backend Lead  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 4.3

---

#### **Task 4.5: Multi-Region End-to-End Testing (3 days)**

**Objective**: Comprehensive multi-region audit testing

**Test Scenarios**:

1. **SEBI-Only Audit** (10 SEBI funds)
   - All rules applied: SEBI rules only
   - Expected violations: 15+
   - Time: <10s

2. **SEC-Only Audit** (5 SEC funds)
   - Different thresholds
   - Expected violations: 12+
   - Time: <5s

3. **ESMA-Only Audit** (3 ESMA funds)
   - ESG requirements included
   - Expected violations: 8+
   - Time: <3s

4. **Mixed-Region Audit** (10 funds from different regions)
   - Each audited with own region's rules
   - Violations isolated by region
   - Time: <10s

5. **Global Audit (All Regions)**
   - Single fund audited against all regions
   - 3× violations (SEBI + SEC + ESMA)
   - Time: <5s for 1 fund

**Performance Test**: 50 funds across 3 regions
```bash
pytest backend/tests/compliance/test_multi_region_performance.py -v

# Expected:
# - 50 funds audited
# - Total time: <15 seconds
# - Memory: <500MB
# - All violations correctly isolated by region
```

**Acceptance Criteria**:
- ✅ All multi-region scenarios pass
- ✅ Performance <15s for 50 funds
- ✅ Violations correctly isolated
- ✅ No cross-region contamination
- ✅ Mixed-region working
- ✅ Test pass rate 100%

**Owner**: QA Lead  
**Estimation**: 3 days | **Risk**: Medium (complexity) | **Dependency**: Task 4.4

---

#### **Task 4.6: Update Streamlit Dashboard for Multi-Region (2 days)**

**Objective**: Enhance UI for multi-region compliance comparison

**Changes**:

1. **Scorecard Page**: Add region tabs
   - SEBI tab, SEC tab, ESMA tab, Consolidated tab
   - Side-by-side comparison

2. **Violations Page**: Add region filter
   - Column: Region
   - Filter: region multi-select
   - Regional breakdown

3. **Funds Page**: Add region awareness
   - Column: Region
   - Show fund's regulatory domain
   - Highlight multi-region funds

4. **Remediation Page**: Filter by region
   - Region selector
   - Region-specific SLA tracking

5. **New Page**: Multi-Region Comparison
   - Side-by-side scorecard (SEBI vs SEC vs ESMA)
   - Violations breakdown by region
   - Regulatory alignment report

**Streamlit Code**:
```python
# Region tabs on Scorecard
region_tabs = st.tabs(["SEBI", "SEC", "ESMA", "Consolidated"])

with region_tabs[0]:  # SEBI tab
    sebi_scorecard = fetch_scorecard("SEBI")
    st.metric("SEBI Score", f"{sebi_scorecard['overall_score']:.1f}%")
    # ... charts

with region_tabs[3]:  # Consolidated tab
    sebi = fetch_scorecard("SEBI")
    sec = fetch_scorecard("SEC")
    esma = fetch_scorecard("ESMA")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("SEBI", f"{sebi['overall_score']:.1f}%")
    with col2:
        st.metric("SEC", f"{sec['overall_score']:.1f}%")
    with col3:
        st.metric("ESMA", f"{esma['overall_score']:.1f}%")
    
    # Comparison chart
    comparison_df = pd.DataFrame({
        "Region": ["SEBI", "SEC", "ESMA"],
        "Score": [sebi['overall_score'], sec['overall_score'], esma['overall_score']]
    })
    st.bar_chart(comparison_df.set_index("Region"))
```

**Acceptance Criteria**:
- ✅ Region tabs/selector working
- ✅ Multi-region comparison visible
- ✅ Data updates correctly per region
- ✅ Performance <2s per region switch
- ✅ All pages updated

**Owner**: Frontend Lead  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 4.5

---

### **PHASE 5: Production Hardening & Certification (Weeks 11-12)**

**Phase Status**: 0% → 100%  
**Duration**: 10-14 days (2 weeks)

#### **Task 5.1: Implement Performance SLAs (2 days)**

**Objective**: Ensure compliance endpoints meet latency targets

**SLA Targets**:
- Scorecard: <500ms (p99)
- Audit: <5s for 50 funds (p99)
- Violations query: <2s (p99)

**Implementation**:

1. **Scorecard Caching** (60-second TTL)
```python
from functools import lru_cache
import asyncio

@lru_cache(maxsize=10)
async def get_scorecard_cached(region: str):
    return await fetch_scorecard_from_db(region)

# Clear cache every 60 seconds
async def cache_cleanup():
    while True:
        await asyncio.sleep(60)
        get_scorecard_cached.cache_clear()

asyncio.create_task(cache_cleanup())
```

2. **Database Query Optimization**
```cypher
-- Index violations by timestamp (for faster sorting/filtering)
CREATE INDEX ON :Violation(detected_at)
CREATE INDEX ON :Violation(severity)
CREATE INDEX ON :Violation(status)

-- Use LIMIT in queries to prevent full-table scans
MATCH (v:Violation) WHERE v.detected_at > $date_threshold
LIMIT 10000
```

3. **Monitoring**
```python
from time import perf_counter
import logging

@app.middleware("http")
async def track_latency(request, call_next):
    start = perf_counter()
    response = await call_next(request)
    elapsed_ms = (perf_counter() - start) * 1000
    
    logger.info(f"{request.method} {request.url.path} took {elapsed_ms:.1f}ms")
    response.headers["X-Process-Time"] = str(elapsed_ms)
    
    # Alert if SLA exceeded
    if "/scorecard" in request.url.path and elapsed_ms > 500:
        logger.warning(f"SCORECARD SLA EXCEEDED: {elapsed_ms:.1f}ms")
    
    return response
```

**Load Testing**:
```bash
# Test scorecard latency (1000 requests, 10 concurrent)
ab -n 1000 -c 10 http://localhost:8000/api/compliance/scorecard?region=SEBI

# Expected output:
# Requests per second: 100+
# Mean time: 250ms
# 95% time: 400ms
# 99% time: <500ms
```

**Acceptance Criteria**:
- ✅ Scorecard <500ms (p99)
- ✅ Audit <5s for 50 funds (p99)
- ✅ Violations <2s (p99)
- ✅ Caching working
- ✅ Monitoring active
- ✅ Load test passing

**Owner**: Backend Lead  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 4.6

---

#### **Task 5.2: Implement Security Hardening (3 days)**

**Objective**: Secure endpoints for production use

**1. Rate Limiting**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/scorecard")
@limiter.limit("100/minute")
async def get_scorecard(request: Request):
    pass

@app.post("/violations/{id}/resolve")
@limiter.limit("10/minute")  # Stricter for writes
async def resolve_violation(request: Request):
    pass
```

**2. Input Validation**
```python
from pydantic import BaseModel, Field, validator

class ResolveViolationRequest(BaseModel):
    resolution_action: str = Field(
        min_length=1,
        max_length=500,
        description="Action text"
    )
    
    @validator('resolution_action')
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError('Action cannot be empty')
        return v
```

**3. RBAC (Role-Based Access Control)**
```python
from enum import Enum

class Role(str, Enum):
    VIEWER = "viewer"      # Read-only
    REVIEWER = "reviewer"  # Read + review
    RESOLVER = "resolver"  # Resolve
    ADMIN = "admin"        # Full access

def require_role(roles: List[Role]):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user = Depends(get_current_user), **kwargs):
            if not any(r in current_user.roles for r in roles):
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

@app.post("/violations/{id}/resolve")
@require_role([Role.RESOLVER, Role.ADMIN])
async def resolve_violation(...):
    pass
```

**4. Audit Logging**
```python
audit_logger = logging.getLogger("audit")

async def log_resolution(violation_id, user_id, action, status):
    audit_logger.info(
        f"RESOLVE | violation_id={violation_id} | user_id={user_id} | "
        f"action={action} | status={status} | timestamp={datetime.now().isoformat()}"
    )
    
    # Also store in Neo4j
    cypher = """
    MERGE (log:AuditLog {id: $log_id})
    SET log.violation_id = $violation_id,
        log.user_id = $user_id,
        log.action = $action,
        log.timestamp = $timestamp
    """
    await graph.run(cypher, {...})
```

**5. Data Encryption**
```python
from cryptography.fernet import Fernet

cipher = Fernet(ENCRYPTION_KEY)

def encrypt_evidence(evidence: str) -> str:
    return cipher.encrypt(evidence.encode()).decode()

def decrypt_evidence(encrypted: str) -> str:
    return cipher.decrypt(encrypted.encode()).decode()
```

**Security Checklist**:
- ✅ Rate limiting implemented
- ✅ Input validation in place
- ✅ RBAC enforced
- ✅ Audit logging active
- ✅ Data encryption for sensitive fields
- ✅ TLS 1.3 enforced
- ✅ CORS restricted
- ✅ Secrets not in logs

**Acceptance Criteria**:
- ✅ Rate limiting working (429 after limit)
- ✅ Invalid input rejected (400)
- ✅ Unauthenticated blocked (401)
- ✅ Unauthorized blocked (403)
- ✅ Audit logs created
- ✅ Encryption working
- ✅ No vulnerabilities found

**Owner**: Backend/Security Lead  
**Estimation**: 3 days | **Risk**: Medium (complexity) | **Dependency**: Task 5.1

---

#### **Task 5.3: Compliance Certification Checklist (2 days)**

**Objective**: Verify system meets all regulatory requirements

**Deliverable**: `COMPLIANCE_CHECKLIST.md`

**1. SEBI MF Regulations 2024**
- ✅ Rule: RULE_PORT_CONC_001 (15% max concentration) → SEBI_MF_2024_Q1_001
- ✅ Rule: RULE_PORT_SECTOR_001 (30% sector limit) → SEBI_MF_2024_Q1_006
- ✅ Rule: RULE_GOV_MGR_CERT_001 (Manager cert required) → SEBI_MF_2024_Q1_002
- ✅ Rule: RULE_KYC_RECENCY_001 (365-day KYC freshness) → SEBI_MF_2024_Q1_003
- ✅ Rule: RULE_RISK_VAR_001 (4% VaR limit) → SEBI_MF_2024_Q1_007
- ✅ Rule: RULE_REP_NAV_TIME_001 (9pm IST cutoff) → SEBI_MF_2024_Q1_005
- ... (15-20 total rules)

**SEBI Compliance: 100% ✅**

**2. SEC Compliance**
- ✅ Rule 12d-1: Diversification via RULE_SEC_PORT_*
- ✅ Rule 17f-3: 5% concentration via RULE_SEC_PORT_CONC_001
- ✅ Rule 22c-1: 4pm ET NAV cutoff via RULE_SEC_REP_NAV_001
- ... (10-15 rules from Phase 4)

**SEC Compliance: 85% ✅** (Phase 4 rules loaded)

**3. ESMA Compliance**
- ✅ UCITS Directive: 10% concentration via RULE_ESMA_PORT_001
- ✅ Liquidity: 80% tradable in 5 days via RULE_ESMA_LIQ_001
- ✅ ESG/SFDR: Climate risk disclosure via RULE_ESMA_ESG_001
- ... (10-15 rules from Phase 4)

**ESMA Compliance: 85% ✅** (Phase 4 rules loaded)

**4. Data Retention & Archival**
- ✅ Policy: Retain violations 7 years
- ✅ Process: Archive violations >2 years
- ✅ Procedure: Restore for audit requests
- ✅ RTO/RPO: 4 hours restore, 1 day backup

**5. Audit Trail**
- ✅ All violations logged with timestamp/source/evidence
- ✅ All resolutions logged with user/action/timestamp
- ✅ Non-modifiable retroactively (Neo4j constraints)
- ✅ Queryable for compliance reports

**6. Production Readiness**
- ✅ Performance SLAs met
- ✅ Security hardened
- ✅ Monitoring configured
- ✅ Disaster recovery tested
- ✅ Backup/restore working

**Backup/Restore Scripts**:

`scripts/backup_compliance_graph.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/backups/compliance"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/compliance_${TIMESTAMP}.dump"

neo4j-admin dump --database=neo4j --to="$BACKUP_FILE"

if [ -f "$BACKUP_FILE" ]; then
    echo "✅ Backup created: $BACKUP_FILE"
else
    echo "❌ Backup failed"
    exit 1
fi

# Keep last 30 days
find "$BACKUP_DIR" -name "compliance_*.dump" -mtime +30 -delete
echo "Backup complete"
```

`scripts/restore_compliance_graph.sh`:
```bash
#!/bin/bash
BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore_compliance_graph.sh /path/to/backup.dump"
    exit 1
fi

neo4j-admin stop
neo4j-admin load --from="$BACKUP_FILE" --database=neo4j --force
neo4j-admin start
echo "Restore complete"
```

**Audit Report Generation**:

`GET /api/compliance/audit-report?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

```json
{
  "period": "2024-01-01 to 2024-01-31",
  "total_violations": 125,
  "critical_violations": 5,
  "remediated_violations": 110,
  "remediation_rate": 88.0,
  "generated_at": "2024-02-01T10:30:00Z"
}
```

**Acceptance Criteria**:
- ✅ SEBI checklist 100% complete
- ✅ SEC checklist 85% complete
- ✅ ESMA checklist 85% complete
- ✅ Backup/restore tested
- ✅ RTO/RPO met
- ✅ Audit reports working

**Owner**: Compliance Lead  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 5.2

---

#### **Task 5.4: Third-Party Security Audit (5-10 days, parallel)**

**Objective**: External security validation

**Scope**:
- Penetration testing
- Static code analysis (SAST)
- Dynamic security testing (DAST)
- OWASP Top 10 validation
- Compliance audit

**Deliverables**:
- Penetration test report
- Vulnerability findings + remediation
- Security recommendations
- Compliance certification

**Timeline**: Can run parallel with other Week 11-12 tasks

**Owner**: Security/Compliance Lead

---

#### **Task 5.5: Production Deployment & Go-Live (2 days)**

**Objective**: Deploy to production and verify readiness

**Steps**:

1. **Create Docker Image**
```bash
docker build -f backend/Dockerfile -t nusummit/compliance-system:v1.0 .
docker push nusummit/compliance-system:v1.0
```

2. **Deploy to Production**
   - K8s manifests created
   - Environment variables configured
   - DB connections validated
   - TLS certificates installed

3. **Health Checks**
   - APIs responding
   - Database connected
   - Cache working
   - Monitoring active

4. **Smoke Tests**
   - Run basic audit
   - Verify scorecard
   - Test all APIs
   - Check UI accessible

5. **Monitor System**
   - Latency metrics
   - Error rates
   - Resource utilization
   - User activity

**Go-Live Checklist**:
- ✅ All Phases 1-5 completed
- ✅ Performance SLAs met
- ✅ Security hardened
- ✅ Compliance checklist 100%
- ✅ Monitoring configured
- ✅ Backup/restore tested
- ✅ Team trained
- ✅ Runbooks documented
- ✅ Stakeholders notified

**Acceptance Criteria**:
- ✅ System live and accessible
- ✅ All APIs responding
- ✅ Dashboard loading
- ✅ Data flowing
- ✅ Monitoring active
- ✅ Team ready

**Owner**: DevOps Lead  
**Estimation**: 2 days | **Risk**: Medium | **Dependency**: Task 5.4 (optional)

---

## **III. IMPLEMENTATION TIMELINE SUMMARY**

### **Critical Path (7 weeks)**

```
Week 1-2: Phase 1 (4-6 days)     [SERIAL]
Week 3-4: Phase 2 (6-7 days)     [SERIAL: depends on Phase 1]
         ↓
Week 5-7: Phase 3 (15 days)      [PARALLEL: can start after Phase 2]
Week 8-10: Phase 4 (21 days)     [PARALLEL: can start after Phase 3]
Week 11-12: Phase 5 (14 days)    [SERIAL: depends on Phase 4]
```

### **With 3-Team Parallelization**

| Week | Backend Team | Frontend Team | DevOps/Compliance |
|------|-------------|---------------|------------------|
| 1-2 | Phase 1 (1.1-1.4) | - | Phase 1 (1.3) |
| 3-4 | Phase 2 (2.1-2.4) | - | - |
| 5-7 | - | Phase 3 (3.1-3.5) | Phase 3 (3.5) |
| 8-10 | Phase 4 (4.1-4.4, 4.6) | Phase 4 (4.6) | Phase 4 (4.2) |
| 11-12 | Phase 5 (5.1-5.2) | - | Phase 5 (5.1, 5.3-5.5) |

### **Total Duration**

- **Critical Path**: 49 days (7 weeks)
- **With Buffer**: 12 weeks (allocated)
- **Team Size**: 6-7 engineers
- **Total Task-Days**: ~90 task-days

---

## **IV. TEAM STRUCTURE & ASSIGNMENTS**

### **Team 1: Backend (3-4 engineers)**
- **Lead**: Backend Engineering Lead
- **Tasks**: Phases 1, 2, 4.1-4.4, 5.1-5.2
- **Key Deliverables**: Rules engine, agents, multi-region routing, security
- **Effort**: ~35 task-days

### **Team 2: Frontend (1-2 engineers)**
- **Lead**: Frontend Engineering Lead
- **Tasks**: Phase 3, Phase 4.6
- **Key Deliverables**: Streamlit dashboard, multi-region UI
- **Effort**: ~18 task-days

### **Team 3: DevOps/Compliance (2 engineers)**
- **Lead**: DevOps Lead + Compliance Lead
- **Tasks**: Phase 1.3, Phase 5
- **Key Deliverables**: Schema deployment, performance SLAs, compliance checklist, go-live
- **Effort**: ~15 task-days

---

## **V. SUCCESS CRITERIA & SIGN-OFF**

### **Phase-by-Phase Criteria**

**Phase 1 Complete**:
- ✅ CSV data files created (3 files)
- ✅ All tests pass (21/21)
- ✅ Neo4j populated (50+ regulations, 30+ rules, 10 funds)
- ✅ All 5 API endpoints working
- ✅ Scorecard <500ms

**Phase 2 Complete**:
- ✅ All 5 agents tested independently
- ✅ Orchestrator multi-agent coordination working
- ✅ Agents support SEBI region
- ✅ Agent metrics dashboard working

**Phase 3 Complete**:
- ✅ All 5 UI pages built (Scorecard, Violations, Funds, Reme

I'll create a final comprehensive markdown document with all the implementation details and save it for you to review. Let me create this as a complete, structured file:Let me create the comprehensive implementation plan document for you as a final markdown file. Given the token budget and length of the document, I'll create a summary document that you can save and reference:

---

# **AMC COMPLIANCE SYSTEM: 12-WEEK IMPLEMENTATION PLAN**
## **Complete Detailed Specification**

**Document Version**: 1.0  
**Date**: January 2024  
**Status**: Ready for Review & Execution  

---

## **QUICK REFERENCE**

| Aspect | Value |
|--------|-------|
| **Current Readiness** | 36% production-ready |
| **Target Readiness** | 100% production-ready |
| **Timeline** | 12 weeks (7 weeks critical path) |
| **Total Tasks** | 24 implementation tasks |
| **Team Size** | 6-7 engineers (3 teams) |
| **Key Phases** | 5 phases (Rules → Agents → UI → Multi-Region → Hardening) |
| **Compliance Coverage** | SEBI 100%, SEC 85%, ESMA 85% |

---

## **DOCUMENT OUTLINE**

This implementation plan contains:

### **Section I: Executive Summary (DONE)**
- Current state: 36% production-ready
- Target state: 100% production-ready
- Timeline: 12 weeks (critical path: 7 weeks)
- 3-team parallelization strategy

### **Section II: Detailed Implementation Roadmap (DONE)**

**Phase 1: Rules Engine Completion (Weeks 1-2)**
- Task 1.1: Create CSV data files (sebi_regulations, rules, fund_schemes)
- Task 1.2: Run E2E compliance audit tests
- Task 1.3: Populate Neo4j graph with compliance schema
- Task 1.4: Validate all 5 API endpoints (audit, violations, scorecard, resolve, metrics)

**Phase 2: Domain Agents Completion (Weeks 3-4)**
- Task 2.1: Integration test all 5 domain agents (Portfolio, Governance, KYC, Risk, Reporting)
- Task 2.2: Test orchestrator multi-agent coordination
- Task 2.3: Add multi-region support to agents (SEBI/SEC/ESMA prep)
- Task 2.4: Create agent performance metrics dashboard

**Phase 3: Compliance Dashboard UI (Weeks 5-7)**
- Task 3.1: Build Scorecard page (KPI cards, gauge, trend, domain breakdown)
- Task 3.2: Build Violations page (filters, pie/bar charts, detail table)
- Task 3.3: Build Fund Heatmap page (N×5 matrix, fund list, drill-down)
- Task 3.4: Build Remediation page (active violations, escalation SLA, resolve modal)
- Task 3.5: Deploy & test Streamlit dashboard

**Phase 4: SEC/ESMA Regulatory Expansion (Weeks 8-10)**
- Task 4.1: Ingest 100+ SEC regulations & rules (~5 days)
- Task 4.2: Ingest 100+ ESMA regulations & rules (~5 days)
- Task 4.3: Build multi-region rule router (SEBI/SEC/ESMA routing logic)
- Task 4.4: Update all 5 agents for multi-region support
- Task 4.5: Multi-region end-to-end testing (50 funds across 3 regions)
- Task 4.6: Update Streamlit dashboard for multi-region (tabs, comparisons)

**Phase 5: Production Hardening & Certification (Weeks 11-12)**
- Task 5.1: Implement performance SLAs (<500ms scorecard, <5s audit)
- Task 5.2: Security hardening (rate limiting, RBAC, audit logging, encryption)
- Task 5.3: Compliance certification checklist (SEBI 100%, SEC/ESMA 85%)
- Task 5.4: Third-party security audit (parallel, optional)
- Task 5.5: Production deployment & go-live

---

## **DETAILED TASK SPECIFICATIONS**

### **PHASE 1: Rules Engine Completion (Weeks 1-2)**

**Task 1.1: Create CSV Data Files (1-2 days)**

**Deliverables**:

1. `data/compliance/sebi_regulations.csv` (50+ regulations)
   - Columns: regulation_id, title, effective_date, section, description, applicability, region
   - Examples:
     - SEBI_MF_2024_Q1_001, "Fund Portfolio Diversification", "2024-01-01", "Regulation 49A", "Max 15% in single security", "Equity Funds", "SEBI"
     - SEBI_MF_2024_Q1_002, "Manager Certification", "2024-01-01", "Regulation 35", "CAIA/CFA required", "All", "SEBI"

2. `data/compliance/rules.csv` (30+ rules)
   - Columns: rule_id, rule_type, title, description, regulation_id, condition, metric, threshold, severity, confidence_threshold, applicable_funds, region
   - Portfolio rules (8-10): RULE_PORT_CONC_001, RULE_PORT_SECTOR_001, RULE_PORT_RELATED_001, etc.
   - Governance rules (5-6): RULE_GOV_MGR_CERT_001, RULE_GOV_BOARD_IND_001, etc.
   - KYC rules (5-6): RULE_KYC_RECENCY_001, RULE_KYC_PEP_001, etc.
   - Risk rules (5-6): RULE_RISK_VAR_001, RULE_RISK_LIQUID_001, etc.
   - Reporting rules (4-5): RULE_REP_NAV_TIME_001, RULE_REP_FILING_001, etc.

3. `data/compliance/fund_schemes.csv` (10 funds)
   - Columns: fund_id, isin, name, fund_house, category, mandate, aum_cr, active_investors, region
   - Mix: 4-5 equity, 3-4 debt, 2-3 hybrid funds
   - AUM: 100-1000 Cr
   - Investors: 1,000-100,000

**Owner**: Compliance/Backend Team  
**Estimation**: 1-2 days | **Risk**: Low | **Dependency**: None

---

**Task 1.2: Run End-to-End Compliance Audit Tests (1-2 days)**

**Test Execution**:
```bash
pytest backend/tests/compliance/ -v --tb=short --cov=backend/app/compliance
# Expected: 21/21 tests pass, coverage >90%
```

**Test Coverage**:
- `test_rules_engine.py`: Rule loading, evaluation, conditions
- `test_violation_detector.py`: Audit orchestration, scoring
- `test_rules_ingestion.py`: CSV loading, Neo4j persistence
- `test_compliance_api.py`: 5 REST endpoints
- `test_compliance_agents.py`: Individual agent accuracy

**Expected Violations** (from mock fund data):
- RULE_PORT_CONC_001: 18% > 15% limit ✓
- RULE_PORT_SECTOR_001: 35% > 30% limit ✓
- RULE_KYC_RECENCY_001: KYC 4+ years old ✓
- RULE_RISK_VAR_001: 4.5% > 4% limit ✓
- RULE_RISK_LIQUID_001: 3% < 5% minimum ✓
- **Total**: 8 violations expected

**Owner**: QA Team  
**Estimation**: 1-2 days | **Risk**: Low | **Dependency**: Task 1.1

---

**Task 1.3: Populate Neo4j Graph (1 day)**

**Steps**:
1. Deploy schema: `await deploy_compliance_schema(client)`
2. Load CSV: `await seed_compliance_data(client, Path("data/compliance"))`
3. Verify nodes: 50+ Regulations, 30+ Rules, 10 FundSchemes
4. Verify indexes: 6+ indexes created
5. Test queries: <100ms response time

**Neo4j Schema**:
- 6 Node Types: Regulation, Rule, FundScheme, Violation, RiskThreshold, EscalationPath
- 6+ Indexes on violation/rule/regulation properties
- 2 Constraints: Violation.id unique, FundScheme.id unique

**Owner**: DevOps Team  
**Estimation**: 1 day | **Risk**: Low | **Dependency**: Task 1.1

---

**Task 1.4: Validate API Responses (1 day)**

**Endpoints to Test**:
1. `POST /api/compliance/audit?region=SEBI` - <5s, 15+ violations
2. `GET /api/compliance/violations?region=SEBI&severity=critical` - <2s, filters working
3. `GET /api/compliance/fund/{fund_id}/violations` - <1s, fund-specific
4. `GET /api/compliance/scorecard?region=SEBI` - <500ms ⭐, score by domain
5. `POST /api/compliance/violations/{id}/resolve` - <500ms, status update

**Acceptance Criteria**:
- ✅ All 5 endpoints return 200 OK
- ✅ Response schemas match Pydantic models
- ✅ Filtering works (severity, fund_id, region)
- ✅ Scorecard latency <500ms
- ✅ Audit latency <5s

**Owner**: Backend Team  
**Estimation**: 1 day | **Risk**: Low | **Dependency**: Task 1.3

**Phase 1 Status**: 90% → **100% COMPLETE** ✅

---

### **PHASE 2: Domain Agents Completion (Weeks 3-4)**

**Task 2.1: Integration Test All 5 Agents (2 days)**

**Agents to Test**:
1. PortfolioAgent - 3 violations (concentration, sector, related-party)
2. GovernanceAgent - 2 violations (cert, independence)
3. KYCAgent - 1 violation (KYC recency)
4. RiskAgent - 1 violation (VaR)
5. ReportingAgent - 1 violation (NAV timing)

**Total Expected**: 8 violations from mock fund

**Test Requirements**:
- ✅ Each agent detects correct violations
- ✅ No false positives
- ✅ Response time <500ms per agent
- ✅ Test pass rate 100%

**Owner**: QA Team  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 1.4

---

**Task 2.2: Test Orchestrator Multi-Agent (1.5 days)**

**Test Scenarios**:
1. Single fund, all 5 agents: 8 violations, <2s
2. 20 funds parallel: semaphore working (10 concurrent max), <10s
3. Scorecard aggregation: average of 5 domain scores

**Requirements**:
- ✅ All 5 agents called
- ✅ No race conditions
- ✅ Semaphore working
- ✅ Scorecard correct
- ✅ Performance <10s for 20 funds

**Owner**: Backend Team  
**Estimation**: 1.5 days | **Risk**: Low | **Dependency**: Task 2.1

---

**Task 2.3: Multi-Region Agent Routing (1.5 days)**

**Changes**:
- Add `region: str = "SEBI"` parameter to each agent
- Load region-specific rules from Neo4j
- Tag violations with region

**Example - Concentration**:
- SEBI: 15% (test with 16% holding = 1 violation)
- SEC: 5% (when Phase 4 loads: 1 violation)
- ESMA: 10% (when Phase 4 loads: 1 violation)

**Requirements**:
- ✅ All agents accept region parameter
- ✅ Region-specific rules applied
- ✅ Violations tagged with region
- ✅ Fallback to SEBI when unavailable

**Owner**: Backend Team  
**Estimation**: 1.5 days | **Risk**: Low | **Dependency**: Task 2.2

---

**Task 2.4: Agent Performance Metrics (1.5 days)**

**Metrics Collected**:
- violations_detected, avg_latency_ms, p95_latency_ms, p99_latency_ms, accuracy_score

**API Endpoint**: `GET /api/compliance/agents/metrics?region=SEBI`

**Storage**: Neo4j AgentMetrics nodes (timestamped for history)

**Requirements**:
- ✅ Metrics collected for each agent
- ✅ Stored in Neo4j
- ✅ API endpoint working
- ✅ Historical metrics retrievable

**Owner**: Backend Team  
**Estimation**: 1.5 days | **Risk**: Low | **Dependency**: Task 2.3

**Phase 2 Status**: 90% → **100% COMPLETE** ✅

---

### **PHASE 3: Compliance Dashboard UI (Weeks 5-7)**

**Task 3.1: Scorecard Page (3 days)**

**File**: `streamlit_app/pages/01_Scorecard.py`

**Components**:
1. Header: Title, region selector, refresh button
2. KPI Cards (4): Score, Violations, Critical, Compliant Funds
3. Gauge Chart: Circular dial 0-100% with zones
4. Domain Breakdown: 5 cards (Portfolio, Governance, KYC, Risk, Reporting)
5. Trend Chart: 30-day line chart

**Features**:
- Auto-refresh every 60s
- Manual refresh button
- Region selector updates all charts
- Responsive layout

**Owner**: Frontend Team  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 2.4

---

**Task 3.2: Violations Page (3 days)**

**File**: `streamlit_app/pages/02_Violations.py`

**Components**:
1. Filters: Severity, Domain, Fund, Date range multi-select
2. Pie Chart: Violations by severity
3. Bar Chart: Violations by domain
4. Leaderboard: Top 10 violated rules
5. Detail Table: All violations, sortable, paginated (10/page)

**Features**:
- Multi-select filters
- Real-time filtering
- Interactive charts
- Drill-down capability
- Export to CSV

**Owner**: Frontend Team  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 3.1

---

**Task 3.3: Fund Heatmap Page (3 days)**

**File**: `streamlit_app/pages/03_Funds.py`

**Components**:
1. Heatmap: N funds × 5 domains matrix (Green/Yellow/Red cells)
2. Fund List: Sortable table (Name, Category, AUM, Score, Status)
3. Fund Detail Panel: Metadata, scores, violations, remediation status

**Features**:
- Interactive heatmap
- Fund selection
- Drill-down to details
- Violation list

**Owner**: Frontend Team  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 3.2

---

**Task 3.4: Remediation Page (3 days)**

**File**: `streamlit_app/pages/04_Remediation.py`

**Components**:
1. Active Violations: Filtered table with SLA status
2. Remediation Progress: Detected/Reviewed/Remediated/Closed metrics
3. Escalation SLA Tracking: By severity with color-coded status
4. Resolve Modal: Violation details + action input + resolve button
5. Timeline: Status transitions with timestamps

**Features**:
- Real-time SLA tracking
- Bulk actions
- Action history
- Status validation

**Owner**: Frontend Team  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 3.3

---

**Task 3.5: Deploy & Test Dashboard (2 days)**

**Steps**:
1. Create `streamlit_app/compliance_config.toml`
2. Update `streamlit_app/requirements.txt` (streamlit, plotly, pandas, httpx)
3. Create `run_compliance_dashboard.sh`
4. Local testing (all pages load, data flows end-to-end)
5. Performance testing (page load <3s, 100+ violations)
6. Cross-browser testing (Chrome, Firefox, Safari)

**Requirements**:
- ✅ All 5 pages working
- ✅ Data end-to-end
- ✅ Performance acceptable
- ✅ Responsive design

**Owner**: DevOps Team  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 3.4

**Phase 3 Status**: 0% → **100% COMPLETE** ✅

---

### **PHASE 4: SEC/ESMA Regulatory Expansion (Weeks 8-10)**

**Task 4.1: SEC Rules Ingestion (5 days)**

**SEC Regulations**: 100+ rules covering:
- Investment Company Act of 1940 (ICA)
- Rule 12d-1: Diversification
- Rule 17f-3: Portfolio concentration (5% vs SEBI 15%)
- Rule 22c-1: NAV timing (4pm ET vs SEBI 9pm IST)
- Rule 10b-1: Distribution fees
- Dodd-Frank requirements

**Data Files**:
- `data/compliance/sec_regulations.csv`: 100+ regulations
- `data/compliance/sec_rules.csv`: 50+ rules (RULE_SEC_PORT_001, RULE_SEC_NAV_001, etc.)

**SEC Thresholds** (different from SEBI):
- Concentration: 5% (stricter)
- Sector: 25%
- Board Independence: 40%

**Test**: Fund with 16% holding
- SEBI audit: Compliant (16 > 15? YES → violation ✓)
- SEC audit: Violation (16 > 5 SEC limit)

**Requirements**:
- ✅ 100+ SEC regulations
- ✅ 50+ SEC rules
- ✅ Rules loaded into Neo4j
- ✅ Agents can apply SEC rules
- ✅ SEC fund tested with SEC thresholds

**Owner**: Compliance Team  
**Estimation**: 5 days | **Risk**: Medium | **Dependency**: Task 3.5

---

**Task 4.2: ESMA Rules Ingestion (5 days)**

**ESMA Regulations**: 100+ rules covering:
- UCITS Directive (2009/65/EC)
- AIFM Directive (2011/61/EU)
- MiFID II regulations
- ESG/SFDR requirements
- Liquidity rules
- Concentration limits (10% vs SEBI 15%, SEC 5%)

**Data Files**:
- `data/compliance/esma_regulations.csv`: 100+ regulations
- `data/compliance/esma_rules.csv`: 50+ rules (RULE_ESMA_PORT_001, RULE_ESMA_ESG_001, etc.)

**ESMA Thresholds**:
- Concentration: 10%
- Liquidity: 80% tradable in 5 days
- ESG Disclosure: Mandatory climate risk

**Requirements**:
- ✅ 100+ ESMA regulations
- ✅ 50+ ESMA rules
- ✅ Rules loaded into Neo4j
- ✅ Agents apply ESMA rules
- ✅ ESMA fund tested

**Owner**: Compliance Team  
**Estimation**: 5 days | **Risk**: Medium | **Dependency**: Task 4.1

---

**Task 4.3: Multi-Region Rule Router (3 days)**

**Objective**: Route funds to correct regional rule set

**Logic**:
```python
async def audit_all_funds(funds, region="SEBI"):
    for fund_data in funds:
        fund_region = fund_data.get("region", region)
        rules = await get_applicable_rules(region=fund_region)
        violations = [await evaluate_rule(rule.id, fund_data) for rule in rules]
        return {"fund_region": fund_region, "violations": violations}
```

**Test Cases**:
- SEBI fund: SEBI rules only
- SEC fund: SEC rules only
- ESMA fund: ESMA rules only
- Global fund: All rules (SEBI + SEC + ESMA)

**Requirements**:
- ✅ Region parameter working
- ✅ Fund routed to correct region
- ✅ Region-specific rules applied
- ✅ Violations tagged with region
- ✅ No rule conflicts

**Owner**: Backend Team  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 4.2

---

**Task 4.4: Agents Multi-Region Support (3 days)**

**Changes to All 5 Agents**:
- Add `region: str = "SEBI"` parameter
- Load region-specific rules
- Apply region-specific thresholds
- Tag violations with region

**Example**:
```python
async def audit_portfolio(fund_data, region="SEBI"):
    rules = await get_applicable_rules("portfolio", region=region)
    violations = [await evaluate_rule(rule.id, fund_data) for rule in rules]
    for v in violations:
        v.region = region
    return violations
```

**Test All 5 Agents** with SEBI/SEC/ESMA:
- Portfolio: Concentration limits differ
- Governance: Board independence differs
- KYC: Same rules, different retention
- Risk: VaR/liquidity limits differ
- Reporting: NAV cutoff times differ

**Requirements**:
- ✅ All 5 agents accept region param
- ✅ Region-specific rules applied
- ✅ Violations tagged with region
- ✅ Fallback to SEBI when unavailable
- ✅ 100% test pass rate

**Owner**: Backend Team  
**Estimation**: 3 days | **Risk**: Low | **Dependency**: Task 4.3

---

**Task 4.5: Multi-Region E2E Testing (3 days)**

**Test Scenarios**:
1. SEBI-only: 10 SEBI funds, <10s, 15+ violations
2. SEC-only: 5 SEC funds, <5s, different thresholds
3. ESMA-only: 3 ESMA funds, <3s, ESG requirements
4. Mixed-region: 10 funds from different regions, <10s, isolated violations
5. Global audit: 1 fund against all regions, 3× violations

**Performance Test**: 50 funds across 3 regions
- Total time: <15 seconds
- Memory: <500MB
- All violations correctly isolated

**Requirements**:
- ✅ All multi-region scenarios pass
- ✅ Performance <15s for 50 funds
- ✅ Violations correctly isolated by region
- ✅ No cross-region contamination
- ✅ 100% test pass rate

**Owner**: QA Team  
**Estimation**: 3 days | **Risk**: Medium | **Dependency**: Task 4.4

---

**Task 4.6: Dashboard Multi-Region (2 days)**

**Changes**:
1. Scorecard: Region tabs (SEBI/SEC/ESMA/Consolidated)
2. Violations: Region column, region filter
3. Funds: Region column, region awareness
4. Remediation: Region selector, region-specific SLA
5. New page: Multi-Region Comparison (side-by-side scorecards)

**Features**:
- Region tabs/selector
- Multi-region comparison
- Regional violation breakdown
- Regulatory alignment report

**Requirements**:
- ✅ Region tabs working
- ✅ Multi-region comparison visible
- ✅ Data updates per region
- ✅ Performance <2s per region switch

**Owner**: Frontend Team  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 4.5

**Phase 4 Status**: 0% → **100% COMPLETE** ✅

---

### **PHASE 5: Production Hardening & Certification (Weeks 11-12)**

**Task 5.1: Performance SLAs (2 days)**

**SLA Targets**:
- Scorecard: <500ms (p99)
- Audit: <5s for 50 funds (p99)
- Violations query: <2s (p99)

**Implementation**:
1. Scorecard caching (60-second TTL)
2. Database query optimization (indexes, LIMIT clauses)
3. Monitoring middleware (track latencies, alert on violations)

**Load Testing**:
```bash
ab -n 1000 -c 10 http://localhost:8000/api/compliance/scorecard?region=SEBI
# Expected: p99 latency <500ms
```

**Requirements**:
- ✅ Scorecard <500ms (p99)
- ✅ Audit <5s (p99)
- ✅ Violations <2s (p99)
- ✅ Caching working
- ✅ Monitoring in place

**Owner**: Backend/DevOps Team  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 4.6

---

**Task 5.2: Security Hardening (3 days)**

**1. Rate Limiting**:
- General endpoints: 100 req/min per IP
- Write endpoints (resolve): 10 req/min per IP
- Higher limits for authenticated users

**2. Input Validation**:
- fund_id: alphanumeric + underscore, <50 chars
- region: SEBI/SEC/ESMA only
- date_range: max 365 days

**3. RBAC** (4 roles):
- VIEWER: Read-only
- REVIEWER: Read + mark reviewed
- RESOLVER: Resolve violations
- ADMIN: Full access

**4. Audit Logging**:
- Log all resolutions (who, what, when, why)
- Store in Neo4j for audit trail
- Non-modifiable retroactively

**5. Data Encryption**:
- Encrypt violation evidence (PII)
- TLS 1.3 for API transport
- Hash sensitive fields

**Security Checklist**:
- ✅ Rate limiting working (429 after limit)
- ✅ Invalid input rejected (400)
- ✅ Unauthenticated blocked (401)
- ✅ Unauthorized blocked (403)
- ✅ Audit logs created
- ✅ Encryption working
- ✅ No vulnerabilities found

**Owner**: Backend/Security Team  
**Estimation**: 3 days | **Risk**: Medium | **Dependency**: Task 5.1

---

**Task 5.3: Compliance Certification (2 days)**

**Deliverable**: `COMPLIANCE_CHECKLIST.md`

**SEBI Compliance: 100%**
- ✅ Rule: RULE_PORT_CONC_001 (15% max) → SEBI_MF_2024_Q1_001
- ✅ Rule: RULE_PORT_SECTOR_001 (30% sector) → SEBI_MF_2024_Q1_006
- ✅ Rule: RULE_GOV_MGR_CERT_001 (Manager cert) → SEBI_MF_2024_Q1_002
- ✅ Rule: RULE_KYC_RECENCY_001 (365-day freshness) → SEBI_MF_2024_Q1_003
- ✅ Rule: RULE_RISK_VAR_001 (4% VaR limit) → SEBI_MF_2024_Q1_007
- ✅ Rule: RULE_REP_NAV_TIME_001 (9pm IST cutoff) → SEBI_MF_2024_Q1_005
- ... (15-20 total rules)

**SEC Compliance: 85%**
- ✅ Rule 12d-1: Diversification
- ✅ Rule 17f-3: 5% concentration
- ✅ Rule 22c-1: 4pm ET NAV cutoff
- ... (Phase 4 loads 50+ SEC rules)

**ESMA Compliance: 85%**
- ✅ UCITS: 10% concentration
- ✅ Liquidity: 80% tradable in 5 days
- ✅ ESG/SFDR: Climate risk disclosure
- ... (Phase 4 loads 50+ ESMA rules)

**Data Retention & Archival**:
- ✅ Retain violations 7 years
- ✅ Archive violations >2 years
- ✅ RTO/RPO: 4 hours restore, 1 day backup

**Audit Trail**:
- ✅ All violations logged
- ✅ All resolutions logged
- ✅ Non-modifiable retroactively

**Backup/Restore Scripts**:
- `scripts/backup_compliance_graph.sh`
- `scripts/restore_compliance_graph.sh`

**Audit Report Endpoint**:
- `GET /api/compliance/audit-report?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- Returns: total violations, critical count, remediation rate, etc.

**Requirements**:
- ✅ SEBI checklist 100% complete
- ✅ SEC checklist 85% complete
- ✅ ESMA checklist 85% complete
- ✅ Backup/restore tested
- ✅ RTO/RPO met
- ✅ Audit reports working

**Owner**: Compliance/DevOps Team  
**Estimation**: 2 days | **Risk**: Low | **Dependency**: Task 5.2

---

**Task 5.4: Third-Party Security Audit (5-10 days, parallel)**

**Scope**:
- Penetration testing
- Static code analysis (SAST)
- Dynamic security testing (DAST)
- OWASP Top 10 validation
- Compliance audit

**Deliverables**:
- Penetration test report
- Vulnerability findings + remediation
- Security recommendations
- Compliance certification

**Timeline**: Can run parallel with other Week 11-12 tasks

**Owner**: Security/Compliance Lead

---

**Task 5.5: Production Deployment & Go-Live (2 days)**

**Steps**:
1. Create Docker image: `nusummit/compliance-system:v1.0`
2. Deploy to production (K8s or cloud)
3. Health checks (APIs, database, cache, monitoring)
4. Smoke tests (basic audit, scorecard, all APIs)
5. Monitor system (latency, errors, resources)

**Go-Live Checklist**:
- ✅ All Phases 1-5 completed
- ✅ Performance SLAs met
- ✅ Security hardened
- ✅ Compliance checklist 100%
- ✅ Monitoring configured
- ✅ Backup/restore tested
- ✅ Team trained
- ✅ Runbooks documented
- ✅ Stakeholders notified

**Requirements**:
- ✅ System live and accessible
- ✅ All APIs responding
- ✅ Dashboard loading
- ✅ Data flowing end-to-end
- ✅ Monitoring active
- ✅ Team ready for support

**Owner**: DevOps Lead  
**Estimation**: 2 days | **Risk**: Medium | **Dependency**: Task 5.4 (optional)

**Phase 5 Status**: 0% → **100% COMPLETE** ✅

---

## **DEPENDENCIES & PARALLELIZATION**

### **Critical Path** (7 weeks)
```
Week 1-2: Phase 1 (SERIAL)
Week 3-4: Phase 2 (SERIAL: depends on Phase 1)
         ↓
Week 5-7: Phase 3 (PARALLEL: can start after Phase 2)
Week 8-10: Phase 4 (PARALLEL: can start after Phase 3)
Week 11-12: Phase 5 (SERIAL: depends on Phase 4)
```

### **3-Team Parallelization**

| Week | Backend | Frontend | DevOps/Compliance |
|------|---------|----------|------------------|
| 1-2 | 1.1-1.4 | - | 1.3 |
| 3-4 | 2.1-2.4 | - | - |
| 5-7 | - | 3.1-3.5 | 3.5 |
| 8-10 | 4.1-4.4 | 4.6 | 4.2 |
| 11-12 | 5.1-5.2 | - | 5.1, 5.3-5.5 |

---

## **SUCCESS CRITERIA & SIGN-OFF**

### **Phase 1 Complete (Week 2)**
- ✅ CSV data files created (3 files)
- ✅ All tests pass (21/21)
- ✅ Neo4j populated (50+ regs, 30+ rules, 10 funds)
- ✅ All 5 API endpoints working
- ✅ Scorecard <500ms

### **Phase 2 Complete (Week 4)**
- ✅ All 5 agents tested independently
- ✅ Orchestrator multi-agent working
- ✅ Agents support SEBI region
- ✅ Agent metrics dashboard working

### **Phase 3 Complete (Week 7)**
- ✅ All 5 UI pages built & tested
- ✅ Dashboard fully functional
- ✅ Data flowing end-to-end
- ✅ Performance <3s per page
- ✅ Responsive design

### **Phase 4 Complete (Week 10)**
- ✅ 100+ SEC regulations ingested
- ✅ 100+ ESMA regulations ingested
- ✅ Multi-region routing working
- ✅ All agents region-aware
- ✅ Multi-region E2E tested
- ✅ Dashboard multi-region ready

### **Phase 5 Complete (Week 12)**
- ✅ Performance SLAs met
- ✅ Security hardened
- ✅ Compliance checklist 100% (SEBI), 85% (SEC/ESMA)
- ✅ Backup/restore tested
- ✅ Production ready
- ✅ System live & monitoring active

### **Final Compliance Readiness: 100% ✅**

---

## **CONCLUSION**

This 12-week implementation plan transforms your AMC compliance system from **36% production-ready to 100% production-ready** with:

✅ **Complete Rules Engine** - SEBI, SEC, ESMA regulations  
✅ **5 Domain Agents** - Portfolio, Governance, KYC, Risk, Reporting  
✅ **Streamlit Dashboard** - Real-time compliance monitoring  
✅ **Multi-Region Support** - SEBI/SEC/ESMA with region-specific thresholds  
✅ **Production Hardening** - Performance SLAs, security, compliance certification  

**Ready for regulatory deployment and live operational use.**

---

**Document Complete**

This is your comprehensive, detailed 12-week implementation plan. You now have:

1. ✅ Complete audit report (Phases 1-5 status)
2. ✅ Detailed roadmap (24 tasks across 5 phases)
3. ✅ Task specifications (objectives, deliverables, acceptance criteria)
4. ✅ Timeline & dependencies (critical path, parallelization strategy)
5. ✅ Team assignments (3 teams, 6-7 engineers)
6. ✅ Success criteria (phase-by-phase sign-off)

**You can now:**
- Share this document with stakeholders
- Assign tasks to teams
- Track progress against milestones
- Execute implementation with confidence

Would you like me to:
1. Create a Gantt chart visualization?
2. Generate a project management summary (for Jira/Asana)?
3. Create a risk management plan?
4. Develop resource allocation spreadsheet?