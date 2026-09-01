# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

---

# **Implementation Plan – Enterprise-Grade AMC Compliance Auditing System with Agentic AI**

## **Problem Statement**

Asset Management Companies operate under complex, multi-regional regulatory frameworks (SEBI/India, SEC/US, ESMA/Europe) with overlapping and sometimes conflicting requirements. Manual compliance auditing is resource-intensive, error-prone, and reactive. You need an **autonomous, intelligent auditing system** that:
- Monitors all AMC operations (portfolio, governance, risk, reporting) in real-time
- Identifies violations against regulatory norms across multiple jurisdictions
- Provides actionable audit reports with remediation guidance
- Adapts to regulatory changes without code rewrites
- Escalates based on violation severity and regional impact

---

## **Requirements Summary** (from your answers)

| Aspect | Decision |
|--------|----------|
| **Scope** | Holistic: portfolio, operational, governance, risk, reporting compliance |
| **Data** | Both structured (DBs/APIs) and unstructured (docs, SOPs, reports) |
| **Output** | Continuous real-time scorecards + detailed audit reports + escalation alerts |
| **Frameworks** | Multi-region with equal priority (India/SEBI, US/SEC, Europe/ESMA) |
| **Integration** | Hybrid: existing legacy + modern systems via middleware |
| **Timeline** | Enterprise 12+ months with full ML anomaly detection |
| **Agentic Model** | Domain specialists (portfolio/governance/risk/reporting agents) + shared compliance graph + central orchestrator |
| **Violation Handling** | Per-violation risk-based thresholds (fraud = strict; minor = lenient) |
| **Regulatory Integration** | Hybrid: graph-stored structures + LLM interpretation for edge cases |

---

## **Background Research & Findings**

### **A. Regulatory Landscape**

**SEBI (India) – Key Compliance Domains:**
1. **Portfolio Compliance**: Fund scheme objectives, asset allocation limits, concentration limits, sector caps, diversification mandates
2. **Governance**: Board composition, fund manager qualifications, disclosure schedules, related-party transactions, conflict of interest
3. **KYC/AML**: Customer identity verification, beneficial ownership, politically exposed persons (PEPs), enhanced due diligence
4. **Risk Management**: Value-at-Risk (VaR), stress testing, liquidity risk, operational risk frameworks
5. **Reporting**: Net Asset Value (NAV) calculations, quarterly/annual disclosures, material event reporting

**SEC (US) – Key Compliance Domains:**
1. **Form N-1A/N-1**: Prospectus filings, fund characteristics, risk disclosures, fund manager info
2. **Advertising Compliance**: Performance advertising, advertising review, fund ratings
3. **Custody & Operations**: Asset custody, valuation procedures, expense caps, fee arrangements
4. **Rule 10b-5 Compliance**: Insider trading policy, trading ahead restrictions
5. **Liquidity Risk Management**: Redemption policies, swing pricing, fair valuation procedures

**ESMA/Europe – Key Compliance Domains:**
1. **MiFID II**: Investor protection, suitability rules, best execution, transaction reporting
2. **UCITS Directive**: Fund structures, eligible assets, borrowing limits, diversification
3. **AIFMD**: Alternative fund manager rules, leverage limits, depositary oversight
4. **ESMA Q&A**: Latest ESMA guidance on implementation questions

### **B. Your Existing ContextGraph Infrastructure**

- **Graph DB (Neo4j)**: Can store AMC entities (funds, fund managers, products, transactions, regulations, violations)
- **Vector DB (Qdrant)**: Can index regulatory documents, SOPs, audit evidence, past violations
- **LLM (Groq)**: Can interpret regulations, classify violations, generate audit narratives
- **Ingestion Pipeline**: Already parses documents, extracts entities, tags with taxonomy—**reusable for compliance docs**

### **C. Agentic AI Paradigm for Compliance**

Your **domain-specialist + shared-graph + orchestrator** model aligns with:
- **Agent Specialization**: Portfolio Agent (asset rules), Governance Agent (structure), KYC Agent (identity), Risk Agent (metrics), Reporting Agent (disclosures)
- **Shared Compliance Graph**: Stores regulations, fund structures, violation templates, evidence trails
- **Central Policy Store**: Master registry of all active rules (SEBI/SEC/ESMA) with thresholds
- **Escalation Protocol**: Route violations to appropriate human reviewers based on severity + region

---

## **Proposed Solution**

### **High-Level Architecture**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AMC COMPLIANCE AUDITING SYSTEM                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────── AGENTIC LAYER ──────────────────────┐        │
│  │                                                          │        │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │        │
│  │  │  Portfolio   │  │ Governance   │  │ KYC/AML      │ │        │
│  │  │  Agent       │  │ Agent        │  │ Agent        │ │        │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │        │
│  │         │                  │                  │         │        │
│  │  ┌──────────────┐  ┌──────────────┐         │         │        │
│  │  │ Risk Agent   │  │ Reporting    │         │         │        │
│  │  │              │  │ Agent        │         │         │        │
│  │  └──────┬───────┘  └──────┬───────┘         │         │        │
│  │         │                  │                  │         │        │
│  │         └──────────────────┼──────────────────┘         │        │
│  │                            │                            │        │
│  │                  ┌─────────▼──────────┐                │        │
│  │                  │ ORCHESTRATOR       │                │        │
│  │                  │ (Violation routing,│                │        │
│  │                  │  escalation logic) │                │        │
│  │                  └────────┬───────────┘                │        │
│  └───────────────────────────┼────────────────────────────┘        │
│                              │                                      │
│  ┌──────────────── COMPLIANCE KNOWLEDGE LAYER ──────────┐          │
│  │                                                       │          │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │          │
│  │  │ Regulations  │  │ Fund Schema  │  │ Violation  │ │          │
│  │  │ (SEBI/SEC/   │  │ (products,   │  │ Evidence   │ │          │
│  │  │ ESMA Graph)  │  │ managers)    │  │ Trail      │ │          │
│  │  └──────────────┘  └──────────────┘  └────────────┘ │          │
│  │                    NEO4J GRAPH DB                     │          │
│  └───────────────────────────────────────────────────────┘          │
│                                                                       │
│  ┌──────────────── DATA LAYER ──────────────────────────┐          │
│  │                                                       │          │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │          │
│  │  │ Regulatory   │  │ Audit        │  │ Operations│ │          │
│  │  │ Docs (Vector)│  │ Logs (Vector)│  │ Data (SQL)│ │          │
│  │  └──────────────┘  └──────────────┘  └────────────┘ │          │
│  │  Qdrant (vectors)  PostgreSQL/APIs                   │          │
│  └───────────────────────────────────────────────────────┘          │
│                                                                       │
│  ┌──────────────── OUTPUT LAYER ────────────────────────┐          │
│  │                                                       │          │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │          │
│  │  │ Real-time    │  │ Audit        │  │ Escalation│ │          │
│  │  │ Compliance   │  │ Reports      │  │ Alerts    │ │          │
│  │  │ Scorecard    │  │              │  │           │ │          │
│  │  └──────────────┘  └──────────────┘  └────────────┘ │          │
│  │  Dashboard API / Webhooks                           │          │
│  └───────────────────────────────────────────────────────┘          │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### **Core Design Decisions**

1. **Regulatory Knowledge Graph** (Neo4j):
   - Store SEBI/SEC/ESMA regulations as semantic graph (Rule → Condition → Threshold → Violation)
   - Fund structures (schemes, asset classes, mandates) as entities with relationships
   - Violation templates (what constitutes a breach)
   - Evidence trails (which documents/data support a violation flag)

2. **Domain Specialist Agents** (LLM-powered, orchestrated):
   - Each agent owns a compliance domain (portfolio, governance, KYC, risk, reporting)
   - Agents query compliance graph for applicable rules
   - Agents retrieve evidence from Qdrant (unstructured) + SQL databases (structured)
   - Agents classify findings per violation-type thresholds
   - Escalation routing based on severity

3. **Per-Violation Risk-Based Scoring**:
   - High-risk violations (fraud, unapproved transactions): confidence ≥ 0.95 required to flag
   - Medium-risk (policy breaches): confidence ≥ 0.80
   - Low-risk (late disclosures): confidence ≥ 0.60
   - Configurable per region and fund scheme

4. **Regulatory Integration** (Hybrid):
   - Graph stores canonical regulation interpretations (SEBI circular 2024-Q1, SEC FAQ 2024)
   - LLM used for edge-case interpretation when new/ambiguous rules surface
   - Caching for LLM interpretations (e.g., "Does this violation trigger mandatory disclosure?")

5. **Real-Time Monitoring**:
   - Continuous data ingestion from AMC systems (NAV feeds, trade logs, KYC updates)
   - Periodic compliance sweeps (hourly for high-risk checks, daily for standard)
   - Anomaly detection via graph patterns (e.g., related-party transactions exceeding 10%)

---

## **Task Breakdown: Test-Driven, Incremental Implementation**

Convert the design into a series of tasks that will build each component in a test-driven manner following agile best practices. Each task must result in a working, demoable increment of functionality. Prioritize best practices, incremental progress, and early testing, ensuring no big jumps in complexity at any stage.

---

### **Phase 1: Foundation (Weeks 1-4) – Compliance Graph & Single-Agent Proof-of-Concept**

**Task 1: Set Up Compliance Regulatory Graph Schema in Neo4j**

- **Objective**: Design and deploy Neo4j schema for storing SEBI/SEC/ESMA regulations, fund structures, and violation templates
- **Guidance**: 
  - Create node types: `Regulation`, `Rule`, `Condition`, `Violation`, `Fund`, `FundManager`, `Transaction`, `Evidence`
  - Define relationships: `hasRule`, `requires`, `triggers`, `violates`, `references`, `documents`
  - Index on frequently queried properties (regulation ID, fund ISIN, rule severity)
  - Build initial seed data: ~20-30 representative SEBI rules (portfolio limits, KYC requirements)
  - Document graph schema in Markdown with visual Entity-Relationship diagram
- **Testing**: 
  - Unit test: Cypher queries to retrieve all rules for a given fund type (equity, debt, balanced)
  - Unit test: Verify rule inheritance (SEBI rule applies unless overridden by specific fund scheme)
  - Contract test: GraphQL/API endpoint returns correct schema without error
- **Demo**: Query Neo4j to show "All portfolio concentration rules for Adani Growth Fund" with thresholds and evidence sources

---

**Task 2: Build Portfolio Compliance Agent (First Domain Specialist)**

- **Objective**: Create first domain-specialist agent that audits fund portfolios against asset allocation rules
- **Guidance**:
  - Agent responsibilities: Parse fund mandate → Retrieve applicable portfolio rules from graph → Fetch current portfolio data from SQL/API → Compare holdings vs. limits → Generate violation findings
  - Use existing LLM (Groq) via context-engineering's llm_text_client
  - Implement agent as class with methods: `get_rules_for_fund()`, `fetch_portfolio_data()`, `check_concentration_limits()`, `check_sector_caps()`, `report_violations()`
  - Integrate with existing NER/entity resolver to identify fund names, ISIN codes, security names
  - Store findings in new Neo4j node: `ComplianceViolation` with fields: `agent`, `rule_id`, `severity`, `confidence`, `timestamp`, `evidence_docs`
  - Threshold example: If portfolio NAV >15% in single sector, flag with medium confidence if not explicitly permitted
- **Testing**:
  - Unit test: Mock portfolio data; verify agent correctly identifies concentration breach (e.g., 20% in one sector when limit is 15%)
  - Unit test: Verify agent correctly handles fund schemes with relaxed limits (e.g., sector fund with 50% limit)
  - Integration test: End-to-end with real fund data from test database
  - Test coverage: ≥80% for agent methods
- **Demo**: Run agent on sample Adani Growth Fund portfolio; show report: "Detected 2 violations: (1) Debt allocation 35% exceeds limit 30% [severity: medium, confidence: 0.92], (2) Cash position 8% below minimum 5% [severity: low, confidence: 0.75]"

---

**Task 3: Extend Compliance Graph with SEBI Regulation Library (Phase 1 Set)**

- **Objective**: Populate compliance graph with ~50 SEBI regulations covering portfolio, governance, KYC basics
- **Guidance**:
  - Curate key SEBI circulars: 
    - Portfolio limits (concentration, sector, asset class caps)
    - Fund manager disqualification criteria
    - Disclosure timelines (NAV, performance, material events)
    - Related-party transaction approvals
  - Create Python script to ingest regulations (CSV → Neo4j): `scripts/ingest_regulations.py`
  - Store regulation text snippets in Qdrant for semantic search (e.g., "What rules apply to debt fund concentration?")
  - Map each regulation to enforcement mechanism (automatic flag vs. audit review vs. escalation to compliance officer)
  - Version regulation nodes (e.g., `Regulation_SEBI_MF_2024_Q1`) to allow regulatory updates without overwriting old rules
- **Testing**:
  - Unit test: Query graph for all regulations affecting "Equity Fund" category; verify ≥10 returned
  - Unit test: Semantic search in Qdrant for "debt concentration limits"; verify top result is SEBI regulation
  - Data validation: No orphaned rules (every rule has ≥1 associated fund type)
  - Regression test: Portfolio agent still works after adding 50 new regulations
- **Demo**: Query dashboard showing "Applied Regulations for Adani Growth Fund (Equity): 27 active rules | Last updated 2024-Q1"

---

**Task 4: Build Orchestrator Service with Violation Routing & Escalation Protocol**

- **Objective**: Create central orchestrator that coordinates agents, routes violations, and escalates per severity
- **Guidance**:
  - Orchestrator responsibilities:
    - Trigger compliance agents (portfolio, governance, KYC, risk, reporting) on schedule or on-demand
    - Aggregate violations from all agents into single audit event
    - Apply region-specific thresholds (e.g., SEBI violations escalate to India Compliance Officer, SEC violations to US team)
    - Route by severity: High-risk violations → immediate escalation + alert; medium → audit queue; low → dashboard log
    - Track violation lifecycle (detected → reviewed → remediated → closed)
  - Implement as async task orchestrator (use existing asyncio/Redis from context-engineering)
  - Define routing rules in compliance graph: `Violation → [escalation_path, human_review_required, sla_hours]`
  - Create webhook integration to notify compliance team (email, Slack, dashboard)
- **Testing**:
  - Unit test: High-risk violation (fraud indicator) routes to immediate escalation; medium routes to queue
  - Unit test: Regional routing: SEBI violations don't route to US team
  - Integration test: Agent produces violation → orchestrator routes → webhook triggered
  - Load test: 100 concurrent violations → all routed within 2 seconds
- **Demo**: Dashboard showing violation inbox: "5 new violations detected | 2 high-risk (escalated) | 3 medium (audit queue) | Last scan: 2 hrs ago"

---

### **Phase 2: Multi-Agent Expansion & Governance Compliance (Weeks 5-8) – 2 More Agents + Risk-Based Thresholds**

**Task 5: Build Governance Compliance Agent**

- **Objective**: Create governance domain specialist auditing board structure, related-party transactions, fund manager qualifications
- **Guidance**:
  - Agent checks:
    - Board composition (independent directors %, board size per fund guidelines)
    - Fund manager certificates (qualifications, regulatory certifications)
    - Related-party transaction approvals (board approval, valuation, >1% of AUM exceptions)
    - Conflict of interest disclosures
  - Data sources: AMC master data (fund managers DB), board minutes (vectorized in Qdrant), transaction logs
  - Threshold example: Related-party transaction >5% AUM without board approval = high-risk violation (confidence ≥0.95 required)
  - Reuse Portfolio Agent code structure for consistency
- **Testing**:
  - Unit test: Detect unapproved related-party transaction exceeding threshold
  - Unit test: Allow related-party transaction with documented board approval
  - Unit test: Flag new fund manager without required certifications
  - Integration test: Governance agent + Portfolio agent both run, no conflicts
- **Demo**: "Governance Audit for Adani Growth: 1 violation detected | Related-party transaction (HDFC Securities brokerage 6.2% AUM) lacks board approval [severity: high, confidence: 0.98]"

---

**Task 6: Build KYC/AML Compliance Agent**

- **Objective**: Audit customer identification, beneficial ownership, PEP screening, enhanced due diligence
- **Guidance**:
  - Agent checks:
    - KYC documents current (identity proof, address proof dated <1 year)
    - Beneficial ownership disclosed for corporate investors (ultimate individuals identified)
    - PEP screening against SEBI/RBI/FATF lists (integrate external PEP database or mock for testing)
    - Enhanced due diligence for high-value accounts (>₹1 crore)
    - Periodic KYC updates performed per regulation
  - Data source: Customer KYC database (SQL), PEP screening API (or mock), transaction logs (anomaly detection)
  - Threshold: Customer with >6 months-old KYC + new transaction = flag for KYC update (medium risk, confidence ≥0.85)
  - Violation example: PEP on FATF list making transaction = high-risk (immediate block, confidence ≥0.99)
- **Testing**:
  - Unit test: Detect outdated KYC (>365 days) on active customer
  - Unit test: Allow customer with current KYC making transaction
  - Unit test: Flag PEP customer against FATF mock list
  - Integration test: KYC agent integrates with external PEP API (mock for testing)
  - Data privacy test: KYC agent doesn't log sensitive PII in compliance reports
- **Demo**: "KYC Audit for ABC Investor: 2 issues detected | (1) KYC expired 45 days [severity: medium, confidence: 1.0] | (2) Account qualifies for EDD (6-month transaction >₹1.5 crores) [status: under review]"

---

**Task 7: Implement Risk-Based Violation Scoring & Threshold Configuration**

- **Objective**: Parameterize violation detection thresholds per risk level, rule type, and region
- **Guidance**:
  - Create config structure in compliance graph:
    ```
    Violation.thresholds = {
      "fraud_indicators": {confidence_min: 0.99, escalation: "immediate", sla: "1 hour"},
      "policy_breach": {confidence_min: 0.80, escalation: "audit_queue", sla: "1 week"},
      "disclosure_delay": {confidence_min: 0.60, escalation: "log", sla: "2 weeks"},
      "region_override": {
        "SEBI": {fraud_indicators: {confidence_min: 0.98}},
        "SEC": {fraud_indicators: {confidence_min: 0.99}}
      }
    }
    ```
  - Allow compliance team to adjust thresholds via API: `PATCH /api/compliance/thresholds`
  - Log all threshold changes with audit trail
  - Agents use these thresholds when deciding to flag violations
- **Testing**:
  - Unit test: Agent with fraud indicator (98.5% confidence) not flagged under SEC rules (99% required), flagged under SEBI
  - Unit test: Update threshold; verify agent uses new value on next run
  - Unit test: Threshold adjustment logged to audit trail
  - Regression test: All agents respect updated thresholds
- **Demo**: Compliance dashboard settings: "Violation Thresholds | fraud_indicators: 0.99 (SEBI) / 0.99 (SEC) | policy_breach: 0.80 (default) | Last updated: 2 hrs ago by alice@amc.com"

---

**Task 8: Build Real-Time Compliance Scorecard Dashboard (Backend API)**

- **Objective**: Create REST API endpoints serving compliance health metrics and violation summaries
- **Guidance**:
  - API endpoints:
    - `GET /api/compliance/scorecard` → Overall compliance health (% rules passing, top 5 violations)
    - `GET /api/compliance/violations?region=SEBI&severity=high` → Filtered violation list
    - `GET /api/compliance/fund/{fund_id}/audit` → Fund-specific compliance report
    - `POST /api/compliance/violations/{id}/resolve` → Mark violation as remediated
  - Response format:
    ```json
    {
      "scorecard": {
        "overall_compliance_score": 0.87,
        "rules_passing": 47/50,
        "critical_violations": 2,
        "regions": {
          "SEBI": {"score": 0.85, "violations": 3},
          "SEC": {"score": 0.90, "violations": 1},
          "ESMA": {"score": 0.88, "violations": 2}
        }
      },
      "violations": [
        {"id": "V001", "rule": "portfolio_concentration", "severity": "high", "fund": "Adani Growth", "detected_at": "2024-01-15T10:30Z"}
      ]
    }
    ```
  - Reuse existing FastAPI structure from context-engineering; add `/compliance` routes
- **Testing**:
  - Unit test: Scorecard calculation (47 passing / 50 rules = 0.94 score)
  - Integration test: API returns aggregated violations from all agents
  - Load test: Dashboard API handles 100 concurrent requests
  - Contract test: API response schema matches OpenAPI spec
- **Demo**: Visit `http://localhost:8000/api/compliance/scorecard` → Returns compliance scorecard with 87% overall score, 3 SEBI violations, 2 SEC violations

---

### **Phase 3: Risk & Reporting Agents + SEC/ESMA Support (Weeks 9-12)**

**Task 9: Build Risk Management Compliance Agent**

- **Objective**: Audit Value-at-Risk (VaR) calculations, stress testing execution, liquidity risk management
- **Guidance**:
  - Agent checks:
    - VaR computed daily at specified confidence level (95% or 99% per mandate)
    - VaR limits enforced (absolute or % of AUM per scheme)
    - Stress test scenarios executed (interest rate shock, market crash, currency move)
    - Liquidity stress test: Fund can meet redemptions within stated period (T+1, T+2)
    - Options/derivatives usage within scheme limits
  - Data source: Risk analytics DB (or compute VaR from portfolio), fund mandate document (risk budget)
  - Threshold: VaR exceeds limit by >10% → medium violation; exceeds limit by >20% → high violation
  - Violation: "VaR for Fund XYZ: 12% of AUM [limit: 10%] | Status: escalate to risk committee"
- **Testing**:
  - Unit test: Compute VaR from mock portfolio; flag if exceeds limit
  - Unit test: Verify stress test results are current (within 24 hours)
  - Unit test: Detect missing stress test execution
  - Integration test: Risk agent integrates with risk analytics backend
- **Demo**: "Risk Audit for Balanced Fund: VaR Monitoring | Current: 8.2% of AUM [limit: 10%] ✓ | Last stress test: 2024-01-14 ✓ | Liquidity: Can meet redemptions in T+1 ✓"

---

**Task 10: Build Reporting Compliance Agent**

- **Objective**: Audit NAV calculations, fund performance reporting, disclosure timeliness, regulatory filings
- **Guidance**:
  - Agent checks:
    - NAV calculated and published on schedule (e.g., daily by 7 PM)
    - NAV calculation includes all assets/liabilities, correct valuation method
    - Performance reporting (1Y, 3Y, 5Y returns) vs. index/benchmark accuracy
    - Disclosures filed on time: annual report, semi-annual, material events
    - Advertising claims verified (performance, fund manager credentials)
  - Data source: Fund website (NAV publication logs), disclosure filing system (SQL), historical performance data
  - Threshold: NAV delayed >2 hours after deadline → violation (medium); incorrect valuation >2% → violation (high)
  - Violation: "NAV for Debt Fund delayed 3.5 hours beyond scheduled 7 PM publish time [severity: medium, confidence: 1.0]"
- **Testing**:
  - Unit test: Check NAV publication timestamp vs. schedule
  - Unit test: Verify annual report filed within regulatory timeline (e.g., 60 days post-FY)
  - Unit test: Flag advertising claim not supported by performance data
  - Integration test: Reporting agent queries disclosure filing system
- **Demo**: "Reporting Audit for Equity Fund | NAV Publication: ✓ on-time | Filings: ✓ all current | Performance: ✓ verified | Advertising: ✓ compliant | Overall: PASS"

---

**Task 11: Extend Compliance Graph with SEC & ESMA Regulatory Libraries**

- **Objective**: Add US and European regulations to compliance graph; expand from ~50 SEBI rules to ~150 total (50 SEBI + 50 SEC + 50 ESMA)
- **Guidance**:
  - Curate SEC key rules:
    - Form N-1A/N-1 filing requirements and timelines
    - Rule 10b-5 trading restrictions, blackout periods
    - Expense ratio caps per fund type
    - Performance advertising rules (past performance disclaimers)
    - Liquidity risk management (swing pricing, fair valuation)
  - Curate ESMA key rules:
    - MiFID II suitability, best execution, investor categorization
    - UCITS diversification limits, borrowing caps, eligible assets
    - AIFMD leverage limits, depositary requirements
    - Transaction reporting, trade reporting requirements
  - Store rules with region tags: `Regulation.region = ["SEBI"]` or `["SEC"]` or `["ESMA"]` or `["SEBI", "SEC"]` (for global rules)
  - Vectorize all regulation texts in Qdrant for semantic search
  - Map region-specific thresholds: same rule may have different limits per region
- **Testing**:
  - Unit test: Query graph for all SEC regulations; verify ≥50 returned
  - Unit test: Query graph for ESMA rules affecting "Liquid funds"; verify results
  - Data validation: No duplicate regulations across regions
  - Semantic search test: Qdrant correctly retrieves "expense ratio regulations" from all three regions
- **Demo**: Compliance graph: "Total regulations: 157 | SEBI: 52 | SEC: 52 | ESMA: 53 | Coverage: Portfolio (42), Governance (31), KYC (24), Risk (35), Reporting (25)"

---

**Task 12: Implement Multi-Region Audit Mode & Hybrid Threshold Logic**

- **Objective**: Enable agents to audit across all three regions with configurable enforcement strategy (strictest-rule-wins, region-specific, weighted composite)
- **Guidance**:
  - New config parameter: `threshold_strategy = "strictest_rule_wins" | "region_specific" | "weighted"`
    - **Strictest rule wins**: Fund must comply with most stringent rule across all regions (conservative, likely highest false positives)
    - **Region specific**: Audit per region independently, flag violations per region (flexible, local compliance focus)
    - **Weighted**: Composite score across regions (e.g., 40% SEBI + 40% SEC + 20% ESBA for global AMC) (balanced, requires calibration)
  - Agents fetch applicable rules from all regions, apply chosen strategy
  - Violation reports show which region rule triggered the flag
  - Example: "Fund A has 12% in single stock. SEBI limit: 10% (violation). SEC limit: 5% (violation). Strategy=strictest → high violation (confidence 0.95)"
  - Allow fund-level override: "Fund X targets SEBI only, ignore SEC/ESMA rules"
- **Testing**:
  - Unit test: Same violation triggers across all regions; `strictest_rule_wins` flags it once (not 3x); `region_specific` flags 3x
  - Unit test: Fund with region override (SEBI only) ignores SEC/ESMA rules
  - Unit test: Weighted strategy produces composite score between 0-1
  - Integration test: Orchestrator applies chosen strategy across all agents
- **Demo**: "Multi-Region Audit for Global Fund | Strategy: strictest_rule_wins | SEBI: 3 violations | SEC: 2 violations (all covered by SEBI) | ESMA: 1 new violation | Total: 4 unique violations flagged"

---

### **Phase 4: ML Anomaly Detection & Advanced Features (Weeks 13-16)**

**Task 13: Implement Graph-Based Anomaly Detection for Related-Party Transactions**

- **Objective**: Use graph traversal to detect unusual related-party transaction patterns (potential fraud indicators)
- **Guidance**:
  - Anomalies to detect:
    - Circular transactions (A → B → C → A) increasing fund fees artificially
    - Related-party transactions with entities not in governance disclosure (hidden relationships)
    - Transaction patterns deviating from 6-month baseline (sudden spike in related-party allocation)
    - Concentration of trades with single related-party entity over time threshold
  - Build graph of: `Fund → Transaction → Counterparty → RelatedPartyNetwork`
  - Use Neo4j graph algorithms (APOC): `apoc.path.subgraphAll()`, `apoc.stats.degree()`, `apoc.path.betweenness()`
  - Compare current transaction pattern to baseline (compute 6-month moving average)
  - Trigger anomaly if >3 sigma deviation from baseline
  - Anomaly confidence = 1 - (p-value), capped at 0.99
- **Testing**:
  - Unit test: Detect circular transaction pattern (A→B→C→A) as anomaly
  - Unit test: Detect new related-party not in governance disclosure
  - Unit test: Normal transaction spike (e.g., monthly rebalancing) not flagged as anomaly
  - Integration test: Real transaction data; identify historical related-party anomalies
- **Demo**: "Anomaly Detection: Related-Party Transactions | Baseline (6-month avg): 2.1% of trades | Current: 8.7% of trades (4.1σ deviation) | Anomaly confidence: 0.98 | Flag: High-risk [review recommended]"

---

**Task 14: Build Regulatory Change Detection & Automatic Rule Updates**

- **Objective**: Monitor regulatory sources (SEBI circulars, SEC releases, ESMA Q&A) for changes; ingest and apply new rules autonomously
- **Guidance**:
  - Ingestion sources:
    - SEBI website (circulars feed, RSS if available or manual weekly download)
    - SEC EDGAR filings, SEC.gov news releases
    - ESMA website (news, Q&A updates, guidelines)
  - Pipeline: Download → Extract key changes → Classify regulation type (portfolio, governance, KYC, risk, reporting) → Update compliance graph → Notify compliance team
  - Implement `scripts/fetch_regulatory_updates.py` running weekly
  - New regulations marked with `:new` tag; compliance team reviews within 2 weeks before enforcement
  - Generates alert: "2 new SEBI regulations detected | Effective date: 2024-02-01 | Review by: 2024-01-25"
  - Reuses existing NER + extraction pipeline to identify entities (fund types, limits, dates)
- **Testing**:
  - Unit test: Parse mock SEBI circular; extract rule changes correctly
  - Unit test: Classify regulation type correctly (portfolio vs. governance)
  - Unit test: Graph update persists new rule; agents pick it up on next run
  - Integration test: End-to-end: download → extract → graph update → agent uses new rule
- **Demo**: "Regulatory Updates | New SEBI Circular 2024-02-01: 'Equity fund concentration limit reduced from 15% to 12%' | Status: imported, review pending | Effective: 2024-03-01"

---

**Task 15: Build Audit Evidence Trace & Explainability Layer**

- **Objective**: For each violation flagged, provide complete audit trail: which data, which rules, which LLM reasoning led to the finding
- **Guidance**:
  - Evidence structure:
    ```
    Violation {
      id: "V001",
      rule: "portfolio_concentration",
      finding: "Adani Growth Fund has 18% in single sector (limit 15%)",
      evidence: [
        {source: "NAV feed", date: "2024-01-15", data: "sector_allocation.csv", excerpt: "Technology sector: 18%"},
        {source: "Fund mandate", doc: "Adani_Growth_Prospectus_2024.pdf", excerpt: "max sector concentration: 15%"},
        {source: "LLM reasoning", reasoning: "18% > 15% threshold → violation"}
      ],
      confidence: 0.95,
      audit_path: "Portfolio Agent → Rule portfolio_concentration → Violation Evidence → Orchestrator → Escalation"
    }
    ```
  - Store evidence documents in Qdrant with violation reference
  - Generate explainability report: "Why was this violation flagged?" → Show evidence chain
  - Allow compliance team to mark evidence as "invalid" if data was outdated/incorrect; agent learns
- **Testing**:
  - Unit test: Violation includes ≥2 evidence sources; each traceable to original data
  - Unit test: Evidence is current (timestamp <24 hours for NAV data, <1 year for regulatory docs)
  - Integration test: Compliance team can trace violation back to source data
  - Regression test: Agents produce violations with evidence on every run
- **Demo**: Click violation "Portfolio Concentration" → Explainability panel shows: "18% Technology sector [from NAV 2024-01-15] exceeds 15% limit [from Fund Mandate] = High Risk violation [confidence 0.95]"

---

**Task 16: Build Compliance Integration Points for Downstream Systems**

- **Objective**: Enable compliance findings to flow into: (1) AMC risk system, (2) compliance operations (case management), (3) external auditors (audit trail)
- **Guidance**:
  - API webhook to risk system: `POST /amc-risk/violations` with detected risk violations
  - Integration with compliance case management: Export violations as audit cases; compliance officer reviews, resolves, closes
  - Audit evidence export: Package findings + evidence as PDF/XBRL for external auditors (SOX/MiFID II audit trail)
  - Data lineage: Every violation query-able: "Show me all violations from Portfolio Agent affecting Fund X in Q4 2024"
  - Implement: Webhooks, CSV export, PDF report generation, audit log API
  - Reuse existing audit_results.json structure from context-engineering
- **Testing**:
  - Unit test: Webhook payload correctly formatted; risk system can parse
  - Integration test: Violation created → webhook triggered → risk system updates
  - Integration test: Export violations as PDF; content complete and audit-traceable
  - Data validation: Audit logs capture all compliance operations (agent run, violation detected, escalated, resolved)
- **Demo**: "Compliance Audit Export | Q4 2024 Summary | Total violations: 12 | Exported to: external_auditors/Q4_2024_Compliance_Report.pdf | Audit trail: 47 events logged"

---

### **Phase 5: Production Hardening & Optimization (Weeks 17-20)**

**Task 17: Implement Caching, Performance Optimization & Latency SLA**

- **Objective**: Ensure compliance audit cycle completes within SLA (scorecard in <5s, full audit in <60s)
- **Guidance**:
  - Caching layers:
    - Fund schema (metadata: mandate, limits): Redis TTL 24 hours
    - Regulation rules (SEBI/SEC/ESMA graph): Redis TTL 7 days (invalidate on regulatory update)
    - LLM regulation interpretations: Vector DB cache for edge-case rules, TTL 30 days
  - Query optimization:
    - Batch agent calls: Run all 5 agents in parallel (not sequentially)
    - Lazy violation scoring: Calculate confidence scores only for violations that exceed threshold
    - Pre-compute baseline metrics (6-month avg for anomaly detection) nightly
  - Monitoring:
    - Track SLA: scorecard latency, audit latency, cache hit rate
    - Alert if latency exceeds SLA (e.g., scorecard >10s)
  - Reuses existing context-engineering caching patterns (Redis, FAISS)
- **Testing**:
  - Load test: Run audit on 50 concurrent funds; all complete within SLA
  - Latency test: Scorecard endpoint <5s, full audit <60s
  - Cache hit rate test: ≥70% cache hits after warm-up
  - Regression test: Optimization doesn't reduce violation detection accuracy
- **Demo**: "Compliance Audit Performance | Scorecard: 2.3s (target <5s ✓) | Full audit: 42s (target <60s ✓) | Cache hit rate: 78% | Agents running in parallel: 5 concurrent"

---

**Task 18: Implement Compliance Audit Logging & Regulatory Audit Trail**

- **Objective**: Maintain tamper-proof audit log for regulatory compliance (SOX, MiFID II, SEBI audit trail requirements)
- **Guidance**:
  - Log every compliance operation:
    - Agent run (start, end, violations detected)
    - Threshold configuration change (who, when, old value, new value)
    - Violation escalation (who, reason, action taken)
    - Evidence review (marked as valid/invalid, reason)
    - Remediation action (documented, approval)
  - Storage: Append-only log (SQL with immutable schema, no updates/deletes)
  - Signing: Each log entry signed with cryptographic hash (chain of custody)
  - Query: Audit trail API: `GET /api/compliance/audit_log?entity=fund_id&start_date&end_date`
  - Retention: 7 years per regulation
- **Testing**:
  - Unit test: Log entry created for every compliance operation
  - Unit test: Log entry cannot be modified (immutable storage)
  - Unit test: Audit trail query returns complete chain for a given violation
  - Integration test: Regulatory auditor can verify compliance operations via API
- **Demo**: "Audit Trail for Violation V001 | Agent run: 2024-01-15 10:30 UTC | Detected: portfolio_concentration | Escalated: 2024-01-15 10:32 (by: alice@amc.com) | Marked resolved: 2024-01-20 14:15 (evidence valid, fund rebalanced)"

---

**Task 19: Build Compliance Training & Feedback Loop for LLM Agents**

- **Objective**: Improve agent accuracy over time via compliance team feedback; capture false positives/negatives
- **Guidance**:
  - Feedback loop:
    - Compliance officer reviews violation → marks as "correct finding" / "false positive" / "needs clarification"
    - Feedback stored: `{violation_id, agent, feedback, corrected_confidence}`
    - Periodically: Analyze feedback patterns; identify agents with high false-positive rates
    - For high-variance violations: Create few-shot examples from feedback; inject into agent prompt (prompt engineering)
    - Track agent accuracy metrics: precision, recall, F1 score per agent, per rule type
  - Implement: Feedback API endpoint, accuracy dashboard, prompt versioning system
  - Example: "Portfolio Agent accuracy on concentration_limit rule: Precision 0.92, Recall 0.88, F1 0.90 (target: 0.95) → Add 2 new negative examples to prompt"
- **Testing**:
  - Unit test: Feedback endpoint accepts feedback; updates violation record
  - Unit test: Accuracy metrics calculated correctly (precision = TP / (TP+FP))
  - Integration test: Agent accuracy improved after adding few-shot examples to prompt
  - Regression test: Feedback loop doesn't degrade performance on other rule types
- **Demo**: "Agent Performance Dashboard | Portfolio Agent: Accuracy 0.90 (target: 0.95) | Top feedback: 'False positives on sector rounding (18.0% marked as >15%)' | Recommendation: Refine threshold precision"

---

**Task 20: Deploy to Production & Documentation**

- **Objective**: Deploy compliance system to production; document architecture, operations, troubleshooting
- **Guidance**:
  - Deployment:
    - Containerize compliance service (Docker, reuse context-engineering compose)
    - Deploy to Kubernetes or cloud (AWS/GCP/Azure) with auto-scaling
    - Set up monitoring: Prometheus metrics for audit latency, violation count, agent health
    - Set up alerting: PagerDuty for SLA breaches, high-risk violations
  - Documentation:
    - Architecture document (system design, data flows, agent responsibilities)
    - Operations runbook (how to run audit, troubleshoot failures, update regulations)
    - API documentation (OpenAPI spec, endpoint descriptions, error codes)
    - Compliance officer guide (how to review violations, escalate, provide feedback)
    - Troubleshooting guide (common issues, debug logs, performance tuning)
  - Knowledge base: FAQ, video tutorials, training materials
- **Testing**:
  - Smoke test: Core endpoints respond (scorecard, violations, audit)
  - End-to-end test: Full audit cycle works in production environment
  - Rollback test: Can revert to previous version if issues detected
  - Documentation review: All operations documented and tested by ops team
- **Demo**: "Compliance System Live | Endpoints: /api/compliance/* all operational | Last audit: 2024-01-20 15:00 UTC (47 violations, 2 high-risk) | Documentation: https://docs.internalcompany.com/compliance-audit"

---

## **Task Summary Table**

| Phase | Task | Focus | Deliverable | Demo |
|-------|------|-------|-------------|------|
| **1** | 1 | Graph Schema | Neo4j schema + seed data | Query rules by fund type |
| **1** | 2 | Portfolio Agent | 1st domain specialist | Portfolio violations report |
| **1** | 3 | SEBI Rules | 50 SEBI regulations | "27 rules for Adani Growth" |
| **1** | 4 | Orchestrator | Central routing + escalation | Violation inbox with routing |
| **2** | 5 | Governance Agent | Board, related-party audits | Related-party violation report |
| **2** | 6 | KYC Agent | Customer identity compliance | KYC expiration alert |
| **2** | 7 | Risk-Based Thresholds | Parameterized detection | Threshold config dashboard |
| **2** | 8 | Scorecard API | Real-time compliance metrics | `/api/compliance/scorecard` endpoint |
| **3** | 9 | Risk Agent | VaR, stress testing | Risk audit report |
| **3** | 10 | Reporting Agent | NAV, filing timeliness | Reporting compliance report |
| **3** | 11 | SEC + ESMA Rules | 150 total regulations | Multi-region rule count |
| **3** | 12 | Multi-Region Mode | Strictest/region-specific/weighted | Multi-region audit result |
| **4** | 13 | Graph Anomalies | Related-party pattern detection | Circular transaction flag |
| **4** | 14 | Regulatory Updates | Auto-ingest new rules | Weekly regulatory update alert |
| **4** | 15 | Evidence Trace | Explainability + audit trail | "Why was this flagged?" report |
| **4** | 16 | Integration Points | Risk system, case mgmt, auditors | Webhook + PDF export |
| **5** | 17 | Performance Optimization | SLA caching + parallelization | Latency under 60s |
| **5** | 18 | Audit Logging | Tamper-proof compliance log | 7-year audit trail |
| **5** | 19 | Feedback Loop | Agent learning from corrections | Agent accuracy dashboard |
| **5** | 20 | Production Deploy | Live system + docs | Live dashboard, full runbook |

---

## **Success Criteria & Acceptance**

1. **Functional**: All 5 agents (portfolio, governance, KYC, risk, reporting) detect violations correctly (≥90% accuracy per agent)
2. **Multi-Region**: System audits against SEBI, SEC, ESMA simultaneously with configurable enforcement strategy
3. **Explainability**: Every violation flagged traces back to supporting evidence; compliance team understands reasoning
4. **Performance**: Compliance scorecard <5s, full audit <60s (SLA met for 99% of requests)
5. **Scalability**: System handles 100+ concurrent compliance audits (1 per fund)
6. **Audit Trail**: All operations logged for 7-year regulatory retention; no data loss
7. **Operational**: Compliance officers can run audits, review violations, provide feedback via dashboard (no engineering support needed)
8. **Documentation**: Complete runbook, API docs, troubleshooting guide; new ops team can deploy independently
