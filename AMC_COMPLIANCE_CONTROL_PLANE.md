# AMC Compliance Control Plane — Design Document

**Version:** 1.0  
**Status:** Design Baseline  
**Scope:** Control families, jurisdiction rule packs, regulatory anchors, compliance-safe boundaries, data lineage

> **Important:** This is an architecture reference document. Jurisdiction-specific rule packs require approved legal/compliance interpretation and versioned regulatory sources before production use. This document does not constitute legal advice.

---

## 1. Purpose

The Compliance Control Plane ensures that every AMC chatbot response path can distinguish and independently assess:

```
INFORMATIONAL CORRECTNESS
    +
INVESTOR / CLIENT COMMUNICATION QUALITY
    +
DISCLOSURE COMPLETENESS
    +
ADVICE / SUITABILITY BOUNDARY
    +
SOURCE / DOCUMENT CURRENCY
    +
SUPERVISION / APPROVAL
    +
RECORDKEEPING / AUDITABILITY
    +
PRIVACY / DATA HANDLING
    +
JURISDICTION / PRODUCT APPLICABILITY
```

These are **not globally identical** across jurisdictions, products, channels, or customer types. The architecture therefore separates:

```
GLOBAL AMC CONTROL MODEL (this document)
    ↓
Jurisdiction Policy Pack (independently versioned per regulator)
    ↓
Entity / Product / Channel / User Context
    ↓
Applicable Control Set (resolved at runtime)
```

---

## 2. Critical Architectural Boundaries

### 2.1 Three Layers That Must Stay Separate

| Layer | Answers | Examples |
|---|---|---|
| **AMC Taxonomy** | What does this mean? | Entity type · Intent node · Claim type · Evidence class |
| **Jurisdiction Rule Pack** | What must we do about it? | Which controls apply · Which disclosure is required · Is human approval needed |
| **Failure-Attribution Graph** | What actually went wrong? | Root cause · Incident · Repair eligibility |

**Why separation matters:**  
If suitability rules are embedded inside the taxonomy, a regulatory update silently changes domain semantics. If the taxonomy encodes legal obligations, multiple jurisdictions cannot map different controls to the same AMC concept. Keeping them separate means:
- Taxonomy can evolve without silently changing legal obligations
- Regulations can change without restructuring core domain semantics
- Multiple jurisdictions map different controls to the same AMC concept
- Compliance teams can approve rule packs independently
- Audit can show exactly which policy version created a specific decision

### 2.2 Jurisdiction Is Not Enough

Do not select controls from country alone:

```
"jurisdiction = US"   is INSUFFICIENT

The system must resolve:
  jurisdiction
  + legal entity type
  + regulated capacity / role
  + product type
  + activity type
  + communication channel
  + client / investor category
  + advice vs information mode
  + distribution arrangement
  + policy effective date
```

**US example — must distinguish:**
- SEC-registered investment adviser context
- Investment company / fund context
- Broker-dealer / FINRA member context
- Distributor / intermediary context
- Pure educational information
- Personalised investment advice

**EU example — must distinguish:**
- Investment service subject to MiFID II
- Portfolio management activity
- Investment advice vs execution
- Distribution vs manufacturing

---

## 3. Compliance Failure ≠ Factual Failure

These must be independently scored and adjudicated:

```
Factually correct response
+ correctly cited
+ current source
BUT overly promotional / unsuitable / missing required risk context
    = COMPLIANCE FAILURE, factuality = PASS

Compliant wording
+ proper disclosures
BUT wrong NAV / benchmark / expense data
    = FACTUAL FAILURE, compliance = PASS
```

The evaluation architecture maintains separate dimension scores — never collapses them into one overall score before adjudication.

---

## 4. The 14 AMC Compliance Control Families

Each family is an **architecture category**. Actual legal/regulatory requirements map into these families via jurisdiction-specific policy packs.

### C01 — Communication Fairness / No Misleading Statement

**What it covers:** Fair, balanced presentation; no unsubstantiated claims; no misleading omissions.

**Primary evaluator:** Deterministic hard-term rules + semantic promotional/misleading classifier.  
**LLM involvement:** Only for nuanced cases where wording is ambiguous.  
**Failure family:** F11 (Communication/Tone), F07 (Grounding)

---

### C02 — Source / Disclosure Currency

**What it covers:** Mandatory temporal and provenance checks — is the information current? Does the disclosure reference the current document version?

**Primary evaluator:** Deterministic temporal rule + source version check (from EvidencePack).  
**LLM involvement:** Never for freshness check itself.  
**Failure family:** F05 (Source/Freshness)

---

### C03 — Factual & Numerical Accuracy

**What it covers:** NAV, TER, exit load, AUM, benchmark, performance figures — are they correct and current?

**Primary evaluator:** Structured data comparison (canonical value vs response value) — deterministic.  
**LLM involvement:** Never for numeric reconciliation itself.  
**Failure family:** F08 (Factual/Numerical Accuracy)

---

### C04 — Performance / Comparison Presentation

**What it covers:** Performance claims must use consistent periods, correct basis, include required context (risk, benchmark, expense).

**Primary evaluator:** Period/basis normalisation rules + structural completeness check (taxonomy template).  
**LLM involvement:** Only if unsupported inference remains after structural checks.  
**Failure family:** F09 (Completeness), F10 (Reasoning)

---

### C05 — Advice / Recommendation Boundary

**What it covers:** Has the response crossed from factual information into a personalised recommendation or implicit suitability advice?

**Primary evaluator:** Intent taxonomy + semantic advice-boundary classifier + jurisdiction policy pack.  
**LLM involvement:** Only if genuinely ambiguous after classifier.  
**Default when ambiguous:** Safe policy response / fallback, not blocking LLM chain.  
**Failure family:** F12 (Governance/Compliance)

---

### C06 — Suitability / Best-Interest Sensitive Interaction

**What it covers:** When an interaction is suitability-sensitive (personal circumstances, investment horizon, risk tolerance mentioned), mandatory policy path applies.

**Primary evaluator:** Mandatory jurisdiction-specific policy path. Human required where policy specifies.  
**LLM involvement:** Summary assistance only — never replaces the required human decision.  
**Failure family:** F12 (Governance/Compliance)

---

### C07 — Required Disclosure / Risk Communication

**What it covers:** Presence, placement, and completeness of mandatory risk warnings, regulatory notices, and required disclaimers.

**Primary evaluator:** Deterministic presence and placement rules — does the required disclosure template appear? Is it in the correct position?  
**LLM involvement:** Never for disclosure presence check.  
**Failure family:** F12 (Governance/Compliance), F09 (Completeness)

---

### C08 — Product / Client / Jurisdiction Eligibility

**What it covers:** Hard eligibility rules — product restrictions, investor category gates, jurisdiction flags, distribution restrictions.

**Primary evaluator:** Hard deterministic applicability rules from policy pack.  
**LLM involvement:** Never.  
**Failure family:** F12 (Governance/Compliance)

---

### C09 — Supervision / Approval / Human Escalation

**What it covers:** Cases that require human review, compliance sign-off, or supervisory approval before or after delivery.

**Primary evaluator:** Explicit HITL/approval routing rules. Mandatory audit trail for all escalated cases.  
**LLM involvement:** Summary assistance only.  
**Failure family:** F12 (Governance/Compliance)

---

### C10 — Recordkeeping / Audit Trail

**What it covers:** Every response must have a reconstructable audit record — interaction snapshot, evidence pack, router decision, evaluation findings, corrections applied.

**Primary evaluator:** Mandatory — check that D0/D1/D2/D3 objects were created and persisted.  
**LLM involvement:** Never.  
**Failure family:** F13 (Infrastructure), F14 (Evaluation Integrity)

---

### C11 — Privacy / Data Protection / Sensitive Data

**What it covers:** PII in responses, personal data in evaluation logs, data minimisation, redaction requirements.

**Primary evaluator:** Deterministic PII detection rules before any LLM path.  
**LLM involvement:** Never for PII detection itself — rule-based only.  
**Failure family:** F12 (Governance/Compliance)

---

### C12 — Conflict / Promotion / Bias

**What it covers:** Promotional language, implied guarantees, persuasive framing, undue emphasis on performance, potential conflicts of interest.

**Primary evaluator:** Explicit phrase/pattern rules + semantic promotional classifier.  
**LLM involvement:** Only for nuanced promotional-language cases.  
**Failure family:** F11 (Communication/Tone), F12 (Governance/Compliance)

---

### C13 — Model / Evaluator Governance

**What it covers:** Version control for models, prompts, and evaluators; regression testing; evaluator calibration; model drift monitoring.

**Primary evaluator:** Version cohort monitoring + golden regression set + evaluator calibration metrics.  
**LLM involvement:** Sampled subset for quality checks on new model versions.  
**Failure family:** F14 (Evaluation/Feedback Integrity)

---

### C14 — Operational Resilience / Third-Party / System Failure

**What it covers:** Service health, fallback routing, dependency monitoring, incident detection, business continuity.

**Primary evaluator:** Deterministic telemetry and health-state inspection.  
**LLM involvement:** Never.  
**Failure family:** F13 (System/Infrastructure)

---

## 5. Compliance Control → Router Behaviour Map

| Control Family | Router Behaviour |
|---|---|
| C01 Fair / non-misleading communication | Deterministic hard terms + semantic classifier |
| C02 Source/disclosure currency | Mandatory temporal/provenance checks from EvidencePack |
| C03 Factual/numerical accuracy | Structured canonical comparison before semantic evaluation |
| C04 Performance/comparison presentation | Period/basis normalisation + completeness template |
| C05 Advice/recommendation boundary | Intent + semantic policy classifier + jurisdiction pack |
| C06 Suitability/best-interest sensitivity | Mandatory policy path; human where required |
| C07 Required disclosure/risk communication | Deterministic presence/placement rules first |
| C08 Product/client/jurisdiction eligibility | Hard deterministic applicability rules |
| C09 Supervision/approval | Explicit HITL/approval routes, audit trail mandatory |
| C10 Recordkeeping/audit | Mandatory D0–D3 capture and router decision logging |
| C11 Privacy/data protection | Data minimisation/redaction/PII rules before LLM |
| C12 Conflict/promotion/bias | Rule + semantic detection |
| C13 Model/evaluator governance | Version cohort monitoring + golden regression |
| C14 Operational resilience | Service health/fallback/incident routing |

---

## 6. Jurisdiction Rule Pack Architecture

### 6.1 Governance Pipeline

```
OFFICIAL REGULATORY / LEGAL SOURCE
    ↓
Source Registry + Version
    ↓
Approved Legal / Compliance Interpretation
    ↓
Control Mapping
    ↓
Machine-Executable Rule / Policy
    ↓
Static Validation + Tests
    ↓
Approval / Compliance Signature
    ↓
Jurisdiction Rule Pack
    ↓
Runtime Applicability Resolver
```

**Prohibited shortcut:**
```
Regulatory PDF → LLM → production rule automatically updated
```

LLMs may assist **offline** with extraction, diff summarisation, and test-case suggestion. They must not autonomously create binding runtime controls.

### 6.2 Rule Pack Object Model

```
JurisdictionRulePack
│
├── pack_id
├── jurisdiction
├── regulated_role
├── regulator_scope[]
├── legal_entity_scope[]
├── product_scope[]
├── client_scope[]
├── channel_scope[]
├── activity_scope[]
│
├── effective_from
├── effective_to
├── pack_version
├── approval_status          draft | under_review | approved | deprecated
├── approver
├── source_versions[]
│
└── controls[]               list of ControlRule objects
```

Each `ControlRule`:

```
ControlRule
│
├── control_id
├── control_family           C01–C14
├── description
│
├── applicability_predicate  when this control fires
├── trigger_taxonomy_nodes[] AMC taxonomy nodes that activate this control
├── trigger_claim_types[]    claim types that activate this control
│
├── evaluation_type
│   ├── HARD_RULE            blocks delivery if fails
│   ├── DETERMINISTIC_CHECK  records finding, may block
│   ├── SEMANTIC_CHECK       records finding
│   ├── HUMAN_REQUIRED       routes to HITL
│   └── MONITOR_ONLY         logs, no action
│
├── evidence_requirements[]
├── required_disclosures[]
├── severity                 critical | high | medium | low
├── action_on_fail           BLOCK | SAFE_FALLBACK | ALLOW_WITH_DISCLOSURE | HOLD | LOG
├── escalation_path
│
├── source_reference[]       official regulatory source IDs
├── interpretation_reference approved compliance interpretation document
├── effective_from
├── effective_to
└── rule_version
```

### 6.3 Control Action Types

Runtime actions must be explicit and finite:

```
ALLOW
ALLOW_WITH_DISCLOSURE
REWRITE_REQUIRED
SAFE_FALLBACK
BLOCK
REFUSE
HOLD_FOR_REVIEW
HUMAN_REVIEW_REQUIRED
LOG_ONLY
MONITOR
```

Never: `"Do whatever the LLM thinks is safest"`

### 6.4 Regulatory Source vs Internal Policy

The pack distinguishes:

```
REGULATORY_REQUIREMENT
APPROVED_LEGAL_INTERPRETATION
INTERNAL_RISK_POLICY
PRODUCT_POLICY
OPERATIONAL_CONTROL
```

An AMC may implement a **stricter internal control** than the minimum regulatory requirement. The system must be able to explain:

```
Response blocked because:
  InternalPolicy P-102
  mapped to ControlFamily C05

Rather than incorrectly claiming:
  "Regulator prohibits this exact sentence"
```

### 6.5 Rule Pack States

```
APPLICABLE
NOT_APPLICABLE
AMBIGUOUS_APPLICABILITY
CONFLICTING_CONTROLS
MISSING_POLICY_PACK
STALE_POLICY_PACK
HUMAN_INTERPRETATION_REQUIRED
```

High-impact ambiguity must not silently degrade into a generic LLM answer.

### 6.6 Policy Pack Change Classification

| Class | Description | Automated Deployment? | Human Approval? |
|---|---|---|---|
| **P0** | Metadata only | Possible (policy-defined) | Policy-defined |
| **P1** | Deterministic technical control | Shadow + regression | Usually controlled |
| **P2** | Disclosure/text template update | Controlled | Compliance review |
| **P3** | Applicability change | No direct self-deploy | Required |
| **P4** | Advice/suitability/control-boundary change | No | Required |
| **P5** | Regulatory interpretation / conflict resolution | **Prohibited autonomous** | Required |

### 6.7 Policy Pack Update Workflow

```
Regulatory / policy source update
    ↓
Source diff (LLM may assist offline with summarisation)
    ↓
Potential control impact assessment
    ↓
Compliance review
    ↓
Candidate Rule Pack vNext
    ↓
Static validation
    ↓
Historical replay against interaction corpus
    ↓
AMC scenario regression (15 standard scenarios + AMC-specific)
    ↓
Semantic edge-case tests
    ↓
Approval + compliance signature
    ↓
Canary / controlled activation
    ↓
Post-activation monitoring
```

---

## 7. Regulatory Anchors — August 2026

### 7.1 India — SEBI

**Current frameworks:**
- Securities and Exchange Board of India (Mutual Funds) Regulations, 2026 (last amended 7 July 2026)
- Master Circular for Mutual Funds, 20 March 2026

**Official sources:**
```
https://www.sebi.gov.in/legal/regulations/jul-2026/securities-and-exchange-board-of-india-mutual-funds-regulations-2026-last-amended-on-july-7-2026-_102780.html
https://www.sebi.gov.in/legal/master-circulars/mar-2026/master-circular-for-mutual-funds_100491.html
```

**Architecture implication:**  
The 2026 framework emphasises investor protection, transparency, governance, and compliance architecture for mutual funds. These feed an approved, versioned India policy pack — not one immutable India prompt embedded in the system.

Key AMC control areas activated: C02 (source currency), C03 (numerical accuracy), C04 (performance presentation), C07 (disclosures), C10 (recordkeeping).

### 7.2 United States — SEC / FINRA

**Current frameworks:**
- SEC Division of Examinations 2026 Priorities: fiduciary duty, standards of conduct, custody/privacy controls
- FINRA 2026 Annual Regulatory Oversight Report, GenAI section: supervision, communications, recordkeeping, fair dealing, HITL, testing/monitoring

**Official sources:**
```
https://www.sec.gov/newsroom/press-releases/2025-132-sec-division-examinations-announces-2026-priorities
https://www.finra.org/rules-guidance/guidance/reports/2026-finra-annual-regulatory-oversight-report/gen-ai
```

**Architecture implication:**  
SEC and FINRA applicability must not be assumed solely from `jurisdiction = US`. The regulated capacity and deployment context determine which rules apply. A single US policy pack is insufficient — separate packs for adviser, fund, broker-dealer, and distributor roles.

Key AMC control areas activated: C01 (fair communication), C05 (advice boundary), C06 (suitability), C09 (supervision), C10 (recordkeeping), C13 (model governance).

### 7.3 European Union — ESMA / MiFID II

**Current frameworks:**
- ESMA guidance on AI in investment services: MiFID II organisational requirements, conduct of business, client best interests, data quality, bias, opacity, over-reliance, privacy, security

**Official source:**
```
https://www.esma.europa.eu/press-news/esma-news/esma-provides-guidance-firms-using-artificial-intelligence-investment-services
```

**Architecture implication:**  
Relevant MiFID II obligations continue to apply. The runtime mapping depends on the actual regulated activity and entity role — not geography alone.

Key AMC control areas activated: C01, C02, C05, C06, C07, C10, C11.

### 7.4 United Kingdom — FCA

**Current frameworks:**
- FCA AI Approach (last updated 13 February 2026): relies on existing frameworks (Consumer Duty, SM&CR, governance/control expectations), testing, monitoring, fair treatment, explainability

**Official source:**
```
https://www.fca.org.uk/firms/innovation/ai-approach
```

**Architecture implication:**  
Consumer Duty creates a separate control dimension: communication quality and user outcome are independently assessed from pure factuality. The FCA expectation that firms "communicate in a way that meets customers' information needs" directly maps to C01, C07, and C11.

Key AMC control areas activated: C01, C05, C06, C07, C11, C13.

---

## 8. Compliance-Safe Self-Healing Boundary

### Permitted autonomous operations (subject to R1/R2 eligibility and repair policy):

```
✅ Rebuild missing embeddings
✅ Restore index from canonical source
✅ Refresh source-derived chunks after document update
✅ Repair deterministic metadata (dates, versions, canonical IDs)
✅ Expire clearly superseded graph edges (source-provable, effective_date available)
✅ Recreate known derived relationships with full provenance
```

### Prohibited autonomous operations — always R4/R5:

```
🚫 New legal interpretation
🚫 New suitability standard
🚫 New disclosure obligation
🚫 New jurisdiction scope
🚫 Regulatory conflict precedence
🚫 Whether an ambiguous statement is legally permissible
🚫 Policy pack changes of class P3, P4, P5
```

These remain **governed compliance/legal decisions** — human and compliance team only.

---

## 9. Full Data Lineage Chain

Every interaction should permit reconstruction of the complete decision path:

```
Interaction I-12345
    ↓ uses
Taxonomy v42 → Intent T4.7 → Entity E-99 (Axis Bluechip Fund)
    ↓ resolves
ApplicableControlSet ACS-22 (India · Investment Adviser · Retail · Informational)
    ↓ references
PolicyPack INDIA_SEBI_2026_v3 → Control C07 (Required Disclosure)
    ↓ evaluated by
Evaluator EV_DISC_003 (v2.1)
    ↓ produced
Finding F-201 (disclosure_missing, confidence=0.98)
    ↓ triggered
FailureObservation FO-91 (F12 · Governance/Compliance)
    ↓ attributed to
RootCause RC-12 (context_engineering_failure · disclosure_template_omitted)
    ↓ generated
RepairCandidate RP-31 (R2 · update context assembly rule)
    ↓ validated by
ValidationRun VR-88 (regression_pass · blast_radius_low)
    ↓ promoted as
DeploymentChange DC-09 (2026-08-20 · approved_by: compliance_team)
```

Every link is versioned. This answers any audit question with a traceable chain — not "an agent decided to update the RAG."

---

## 10. Compliance KPIs

| KPI | Target |
|---|---|
| `applicable_control_resolution_rate` | > 95% on supported deployment contexts |
| `mandatory_control_coverage` | 100% |
| `mandatory_control_bypass_count` | **0** (hard target) |
| `policy_pack_version_mismatch_rate` | 0% |
| `policy_pack_version_traceability` | 100% |
| `ambiguous_applicability_rate` | tracked; high rate = rule pack gap |
| `control_conflict_rate` | tracked; conflicts route to human |
| `high_risk_unresolved_rate` | < 0.1% |
| `human_required_bypass_rate` | **0** (hard target) |
| `record_reconstruction_success_rate` | 100% |
| `unapproved_autonomous_legal_rule_change` | **0** (hard target) |
| `failure_graph_to_answer_leakage` | **0** (hard target) |

---

## 11. Taxonomy-to-Control Coverage Gap Detection

Future enhancement — create a coverage view:

```
Taxonomy Node
    ↓
Which control families cover it?
    ↓
Which jurisdictions?
    ↓
Which evaluators?
    ↓
Which regression test cases?
```

**Gap detection:**
```
New taxonomy node (e.g. new product type)
    +
No mapped controls
    =
CONTROL_COVERAGE_GAP alert

→ Compliance team review required before the new node is used in production
→ No LLM needed to detect this gap
```

---

*This document is part of the AMC Unified Feedback, Evaluation & Self-Healing Architecture. See also: `AMC_EVIDENCE_PACK.md`, `AMC_EVALUATION_ROUTER.md`, `AMC_FAILURE_TAXONOMY.md`, `AMC_SELF_HEALING_RAG.md`.*
