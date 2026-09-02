# LLD-07 — Compliance Control Plane

**Document:** LLD-07  
**Version:** 1.0  
**Depends on:** LLD-04 (Evaluation Router), LLD-02 (Evidence Capture)  
**Read next:** LLD-08 (Data Models)

---

## 1. Purpose

The Compliance Control Plane ensures that every AMC chatbot response path can independently assess and satisfy its regulatory and policy obligations. Compliance is a **first-class design dimension** — it is not a post-processing filter bolted onto a generic RAG system.

The plane separates three concerns that must never be collapsed:

| Layer | Responsibility | Example |
|---|---|---|
| **AMC Taxonomy** | Domain meaning — what does this interaction mean? | Intent = SUITABILITY_SENSITIVE |
| **Jurisdiction Policy Pack** | Approved obligations — what must happen? | India pack: C07 disclosure required |
| **Failure-Attribution Graph** | Operational causality — what actually went wrong? | F12 advice_boundary triggered |

Keeping these separate means: taxonomy can evolve without silently changing legal obligations; regulations can change without restructuring domain semantics; multiple jurisdictions can map different controls to the same AMC concept; compliance teams can approve policy packs independently of engineering changes.

---

## 2. Critical Design Constraint — Jurisdiction Is Not Enough

The most common compliance architecture mistake is selecting controls from country alone:

```
❌ Wrong:  jurisdiction = "US"  →  apply US rules
✅ Correct: jurisdiction + regulated_entity_role + product_type +
            channel + customer_segment + interaction_mode +
            distribution_arrangement + policy_effective_date
                ↓
            ApplicableControlSet
```

**US example — must distinguish:**

| Context | Applicable Framework |
|---|---|
| SEC-registered investment adviser | SEC fiduciary duty + standards of conduct |
| Investment company / mutual fund | Investment Company Act obligations |
| Broker-dealer / FINRA member | FINRA supervision + communications rules |
| Distributor / intermediary | Distribution-specific controls |
| Pure educational information | Informational controls only |
| Personalised investment advice | Full suitability + advice-boundary controls |

A single `jurisdiction = US` policy pack is therefore insufficient. The architecture requires separate packs per role or a multidimensional applicability predicate.

---

## 3. Compliance Failure ≠ Factual Failure

These must be independently scored and adjudicated. They may point to completely different root causes and require different repairs.

```
Case 1: Factually PASS, Compliance FAIL
  ─────────────────────────────────────
  Response: "The 5-year CAGR of Axis Bluechip Fund is 14.3%"
  Factual check: ✓ value correct, source current
  Compliance check: ✗ no mandatory risk disclosure (C07)
  Root cause: context engineering omitted disclosure template
  Repair: CONTEXT_RULE — include disclosure template for performance claims

Case 2: Compliance PASS, Factual FAIL
  ─────────────────────────────────────
  Response: "The TER is 0.79%" (with all required disclosures)
  Factual check: ✗ TER is actually 0.82% per current source
  Compliance check: ✓ all required disclosures present
  Root cause: SOURCE_FRESHNESS (F05) — embedded value from stale source
  Repair: R002 StaleEmbedding
```

The evaluation system maintains separate dimension scores per response. These are never collapsed into a single pass/fail before adjudication.

---

## 4. The 14 AMC Compliance Control Families

These are architecture control categories. Each jurisdiction policy pack maps its actual legal/regulatory requirements into these families via `ControlRule` objects.

---

### C01 — Communication Fairness / No Misleading Statement

**What it covers:** Fair and balanced presentation; no unsubstantiated claims; no misleading omissions; no overstatement of returns or benefits.

**Primary evaluator:** Deterministic prohibited-phrase rules + semantic promotional/misleading classifier.  
**LLM involvement:** Only when wording is genuinely ambiguous after the classifier.  
**Failure families:** F11 (Communication/Tone), F07 (Grounding)  
**Example trigger:** Response uses "guaranteed returns" or "risk-free" without qualification.

---

### C02 — Source / Disclosure Currency

**What it covers:** All factual claims must be sourced from current, effective documents. Disclosure documents must reference the current version.

**Primary evaluator:** Deterministic temporal rule — compare `source_effective_date` from D2 against response timestamp.  
**LLM involvement:** Never for the freshness check itself.  
**Failure families:** F05 (Source/Freshness)  
**Example trigger:** NAV value sourced from a document that is more than 1 business day old.

---

### C03 — Factual and Numerical Accuracy

**What it covers:** NAV, TER, exit load, AUM, benchmark, performance figures — must match the authoritative structured source.

**Primary evaluator:** Structured canonical comparison — response value vs source value, deterministic.  
**LLM involvement:** Never for numeric reconciliation.  
**Failure families:** F08 (Factual/Numerical Accuracy)  
**Example trigger:** Response TER = 0.79%; canonical TER = 0.82% → FAIL at E1.

---

### C04 — Performance / Comparison Presentation

**What it covers:** Performance claims must use consistent periods, the same comparison basis, and include required contextual information (risk, benchmark, expense ratio).

**Primary evaluator:** Period/basis normalisation rules + structural completeness check via taxonomy template.  
**LLM involvement:** Only if an unsupported inference remains after structural checks.  
**Failure families:** F09 (Completeness), F10 (Reasoning)  
**Example trigger:** Comparing Fund A vs Fund B using different benchmark periods without disclosure.

---

### C05 — Advice / Recommendation Boundary

**What it covers:** Has the response crossed from factual information into a personalised recommendation or implicit suitability advice?

**Primary evaluator:** Intent taxonomy node + semantic advice-boundary classifier + jurisdiction policy pack.  
**LLM involvement:** Only when genuinely ambiguous after the classifier.  
**Default when ambiguous:** Safe policy response / fallback — never add a blocking LLM chain.  
**Failure families:** F12 (Governance/Compliance), F01 (Intent)  
**Example trigger:** Response to "which fund should I choose for my retirement?" provides a specific recommendation without required suitability process.

---

### C06 — Suitability / Best-Interest Sensitive Interaction

**What it covers:** When a user discloses personal financial circumstances, risk tolerance, or investment horizon — a mandatory policy path applies. Human review required where policy specifies.

**Primary evaluator:** Mandatory jurisdiction policy path. Human required where policy specifies — never automated.  
**LLM involvement:** Evidence summarisation only; never replaces the required human decision.  
**Failure families:** F12 (Governance/Compliance)  
**Example trigger:** User mentions investment timeline, risk appetite, or retirement plans in the same query.

---

### C07 — Required Disclosure / Risk Communication

**What it covers:** Mandatory risk warnings, regulatory notices, and required disclaimers must be present, correctly placed, and use approved wording.

**Primary evaluator:** Deterministic presence and placement rules — does required disclosure template ID appear in D0 `disclosures_shown[]`?  
**LLM involvement:** Never for presence check.  
**Failure families:** F12 (Governance/Compliance), F09 (Completeness)  
**Example trigger:** Performance claim response missing the mandatory mutual fund performance disclaimer.

---

### C08 — Product / Client / Jurisdiction Eligibility

**What it covers:** Hard eligibility gates — product restrictions for certain investor categories, jurisdiction-based product availability, distribution channel restrictions.

**Primary evaluator:** Hard deterministic applicability rules from policy pack.  
**LLM involvement:** Never.  
**Failure families:** F12 (Governance/Compliance)  
**Example trigger:** Response discusses a product not available to retail investors in the user's jurisdiction.

---

### C09 — Supervision / Approval / Human Escalation

**What it covers:** Cases requiring human review, compliance sign-off, or supervisory approval before or after response delivery. Full audit trail mandatory for all escalated cases.

**Primary evaluator:** Explicit HITL/approval routing rules from policy pack.  
**LLM involvement:** Evidence summarisation only.  
**Failure families:** F12 (Governance/Compliance)

---

### C10 — Recordkeeping / Audit Trail

**What it covers:** Every response must produce a reconstructable audit record. D0–D3 must be captured and persisted. RouterDecision must be logged. All corrections must have an audit trail.

**Primary evaluator:** Mandatory completeness check — were D0/D1/D2/D3 created and persisted for this response?  
**LLM involvement:** Never.  
**Failure families:** F13 (Infrastructure), F14 (Evaluation Integrity)  
**Non-negotiable:** `mandatory_control_bypass_count = 0` is a hard target.

---

### C11 — Privacy / Data Protection / Sensitive Data

**What it covers:** PII in responses, personal data in evaluation logs, data minimisation, redaction requirements, GDPR/local privacy law compliance.

**Primary evaluator:** Deterministic PII detection rules before any LLM path. LLM must never receive unredacted PII.  
**LLM involvement:** Never for PII detection.  
**Failure families:** F12 (Governance/Compliance)  
**Example trigger:** Response echoes user's account number or personal financial details.

---

### C12 — Conflict / Promotion / Bias

**What it covers:** Promotional language, implied guarantees, persuasive framing, undue emphasis on past performance, undisclosed conflicts of interest.

**Primary evaluator:** Deterministic phrase/pattern rules + semantic promotional classifier.  
**LLM involvement:** For nuanced promotional language only.  
**Failure families:** F11 (Communication/Tone), F12 (Governance/Compliance)

---

### C13 — Model / Evaluator Governance

**What it covers:** Version control for models, prompts, and evaluators; regression testing against golden sets; evaluator calibration tracking; model drift monitoring.

**Primary evaluator:** EV_GOLDEN_015 (version cohort monitoring + golden regression).  
**LLM involvement:** Sampled subset on new model version deployments.  
**Failure families:** F14 (Evaluation/Feedback Integrity)  
**Critical point:** An evaluator regression is a first-class failure, not an invisible assumption.

---

### C14 — Operational Resilience / Third-Party Dependency

**What it covers:** Service health, fallback routing, dependency monitoring, incident detection, business continuity for the evaluation and healing pipelines.

**Primary evaluator:** Deterministic telemetry and health-state inspection.  
**LLM involvement:** Never.  
**Failure families:** F13 (System/Infrastructure)

---

## 5. Compliance Control → Router Behaviour Map

| Control Family | Router Behaviour at R1 (Mandatory Controls Stage) |
|---|---|
| C01 Fair communication | Hard prohibited-phrase rules + semantic classifier (E1/E3) |
| C02 Source currency | Mandatory temporal/provenance check from D2 (E1) |
| C03 Numerical accuracy | Structured canonical comparison before semantic (E1) |
| C04 Performance comparison | Period/basis normalisation + completeness template (E1/E3) |
| C05 Advice boundary | Intent taxonomy + semantic classifier + jurisdiction pack (E3/E4) |
| C06 Suitability | Mandatory policy path; human required where specified (E5) |
| C07 Required disclosure | Deterministic presence/placement rules first (E1) |
| C08 Eligibility | Hard deterministic applicability rules (E1) |
| C09 Supervision | HITL routing rules; audit trail mandatory (E5) |
| C10 Recordkeeping | Mandatory D0–D3 capture + RouterDecision logging (E0) |
| C11 Privacy/PII | Deterministic PII rules before any LLM path (E1) |
| C12 Promotion/bias | Rule + semantic classifier (E1/E3) |
| C13 Model governance | Version cohort monitoring + golden regression (E2) |
| C14 Operational resilience | Service health/fallback/incident routing (E0) |

---

## 6. Jurisdiction Rule Pack Architecture

### 6.1 Governance Pipeline

The authoritative source → production rule path must never bypass human approval:

```
OFFICIAL REGULATORY / LEGAL SOURCE
    ↓
Source Registry + Version Control
    ↓
Approved Legal / Compliance Interpretation
    ↓
Control Mapping (C01–C14)
    ↓
Machine-Executable Rule / Policy (DSL or code)
    ↓
Static Validation + Test Cases
    ↓
Approval Signature (compliance team)
    ↓
Jurisdiction Policy Pack (versioned artefact)
    ↓
Runtime Applicability Resolver
```

**Explicitly prohibited shortcut:**
```
Regulatory PDF → LLM → production rule (no human in loop)
```

LLMs may assist **offline** with diff summarisation, candidate control extraction, and test-case suggestion. They must not autonomously publish binding runtime controls.

### 6.2 Policy Pack Data Model

```python
@dataclass
class JurisdictionPolicyPack:
    pack_id:                str
    jurisdiction:           str
    regulated_entity_role:  str
    regulator_scope:        list[str]
    legal_entity_scope:     list[str]
    product_scope:          list[str]
    client_scope:           list[str]
    channel_scope:          list[str]
    activity_scope:         list[str]

    effective_from:         date
    effective_to:           Optional[date]
    pack_version:           str
    approval_status:        str   # draft | under_review | approved | deprecated
    approver:               str
    source_versions:        list[str]   # regulatory source IDs used

    controls:               list[ControlRule]


@dataclass
class ControlRule:
    control_id:             str
    control_family:         str   # C01–C14
    description:            str

    applicability_predicate:str   # DSL expression: when this control fires
    trigger_taxonomy_nodes: list[str]   # AMC taxonomy nodes that activate it
    trigger_claim_types:    list[str]   # claim types that activate it

    evaluation_type:        str
    # HARD_RULE         — blocks delivery if fails
    # DETERMINISTIC_CHECK — records finding, may block
    # SEMANTIC_CHECK    — records finding, no block
    # HUMAN_REQUIRED    — routes to HITL queue
    # MONITOR_ONLY      — logs, no action

    evidence_requirements:  list[str]
    required_disclosures:   list[str]   # disclosure template IDs
    severity:               str   # critical | high | medium | low

    action_on_fail:         str
    # BLOCK | SAFE_FALLBACK | ALLOW_WITH_DISCLOSURE |
    # HOLD_FOR_REVIEW | REFUSE | LOG_ONLY

    escalation_path:        str
    source_references:      list[str]   # official source document IDs
    interpretation_reference: str       # approved compliance interpretation doc
    effective_from:         date
    effective_to:           Optional[date]
    rule_version:           str
```

### 6.3 Policy Pack Change Classification

Every change to a policy pack is classified before it can be deployed. Higher classes require stronger governance.

| Class | Description | Automated Deployment? | Human Approval? |
|---|---|---|---|
| **P0** | Metadata only (description, notes) | Possible | Policy-defined |
| **P1** | Deterministic technical control (new rule check) | Shadow + regression | Usually controlled |
| **P2** | Disclosure / text template update | Controlled | Compliance review |
| **P3** | Applicability change (new scope or condition) | No direct self-deploy | Required |
| **P4** | Advice/suitability/control-boundary change | No | Required |
| **P5** | Regulatory interpretation / conflict resolution | **Prohibited autonomous** | Required |

### 6.4 Policy Pack Update Workflow

```
Regulatory / policy source update detected
    ↓
Automated source diff (delta between old and new source version)
LLM may assist here with offline summarisation
    ↓
Potential control impact assessment (which C01–C14 families are affected?)
    ↓
Compliance team review
    ↓
Candidate Rule Pack vNext (draft status)
    ↓
Static validation (schema check, applicability predicate syntax)
    ↓
Historical replay (run vNext against last 30 days of interactions)
    ↓
AMC scenario regression (15 standard scenarios + domain-specific cases)
    ↓
Semantic edge-case tests (ambiguous advice-boundary and tone scenarios)
    ↓
Approval + compliance signature (pack_status → approved)
    ↓
Canary activation (5% traffic, 24h observation)
    ↓
Full activation
    ↓
Post-activation monitoring (7-day window)
```

### 6.5 Conflict Resolution Between Policy Packs

When two applicable controls conflict, the resolution must follow an approved decision procedure — never an LLM auto-verdict:

```
Candidate controls identified
    ↓
Check applicability scope (is each control actually applicable here?)
    ↓
Check effective dates (which version is current?)
    ↓
Check supersession metadata (does one rule explicitly supersede the other?)
    ↓
Check legal / policy hierarchy (encoded by compliance team)
    ↓
Still conflicting?
    ↓
CONFLICTING_CONTROL_STATE
    ↓
Route to Human / Compliance (STOP-5 in the Router)
```

Valid pack states:

```
APPLICABLE
NOT_APPLICABLE
AMBIGUOUS_APPLICABILITY
CONFLICTING_CONTROLS
MISSING_POLICY_PACK
STALE_POLICY_PACK
HUMAN_INTERPRETATION_REQUIRED
```

High-impact ambiguity must never silently degrade into a generic LLM answer.

---

## 7. Regulatory Anchors — August 2026

> **Important:** This section references current public regulatory materials as design anchors. These feed versioned jurisdiction policy packs after approved compliance interpretation. They are not embedded as prompts. This document does not constitute legal advice.

### India — SEBI

| Source | Description |
|---|---|
| SEBI (Mutual Funds) Regulations, 2026 | Last amended 7 July 2026. Core regulatory framework for mutual funds. |
| SEBI Master Circular for Mutual Funds | 20 March 2026. Operational guidance consolidating circular instructions. |

**Architecture implication:** The 2026 framework emphasises investor protection, transparency, governance, and compliance architecture. Key controls activated: C02 (source currency), C03 (numerical accuracy), C04 (performance presentation), C07 (mandatory disclosures), C10 (recordkeeping).

**What this means in practice:** Every response touching a SEBI-regulated fund must have its NAV/TER sourced from a current, effective disclosure document. Missing disclosures are a hard block (C07). Performance comparisons require consistent period and benchmark disclosure (C04).

### United States — SEC / FINRA

| Source | Description |
|---|---|
| SEC Division of Examinations 2026 Priorities | Fiduciary duty, standards of conduct, custody, compliance programs. |
| FINRA 2026 Annual Regulatory Oversight Report (GenAI) | Supervision, communications, recordkeeping, fair dealing, HITL, testing, monitoring, version tracking. |

**Architecture implication:** Applicability depends on regulated capacity — SEC and FINRA controls must not be assumed solely from `jurisdiction = US`. The FINRA GenAI section directly informs C13 (model governance) and C09 (supervision/HITL) control design.

### European Union — ESMA / MiFID II

| Source | Description |
|---|---|
| ESMA AI guidance for investment services | MiFID II organisational requirements, conduct of business, client best interests, data quality, bias, opacity, over-reliance. |

**Architecture implication:** Relevant MiFID II obligations apply regardless of AI involvement. The regulated activity and entity role determine which specific obligations apply, not geography alone. C05 (advice boundary) and C06 (suitability) are particularly prominent.

### United Kingdom — FCA

| Source | Description |
|---|---|
| FCA AI Approach (13 February 2026) | Relies on Consumer Duty, SM&CR, governance/control expectations, testing, monitoring, fair treatment, explainability. |

**Architecture implication:** Consumer Duty creates an independent dimension — communication quality and positive user outcomes are assessed separately from pure factuality. C01, C07, and C11 map directly to Consumer Duty obligations.

---

## 8. Full Data Lineage Chain

Every production change must be traceable from the original interaction through to the deployed fix. This chain is the primary audit artefact for regulatory examination.

```
Interaction I-12345
    │ uses
    ▼
Taxonomy v42  →  Intent T4.7  →  Entity E-99 (Axis Bluechip Fund Direct Growth)
    │ resolves
    ▼
ApplicableControlSet ACS-22
  (India · Investment Adviser · Retail · Informational · INDIA_SEBI_2026_v3)
    │ references
    ▼
PolicyPack INDIA_SEBI_2026_v3  →  Control C07 (Required Disclosure)
  Rule: disclosure_id=PERF_DISC_001 must appear for PERFORMANCE_CLAIM intents
    │ evaluated by
    ▼
Evaluator EV_DISC_011 (v2.1)
  Type: DETERMINISTIC_CHECK
  Result: disclosure_id=PERF_DISC_001 absent from D0.disclosures_shown
    │ produced
    ▼
Finding F-201
  (disclosure_missing · confidence=1.0 · evidence=D0.disclosures_shown[])
    │ triggered
    ▼
FailureObservation FO-91  (F12 · Governance/Compliance · action=ALLOW_WITH_DISCLOSURE)
    │ attributed to
    ▼
RootCause RC-12
  (context_engineering_failure · disclosure_template_not_injected)
  confidence=CONFIRMED · method=RULE
    │ generated
    ▼
RepairCandidate RP-31
  (R2 · update context assembly rule for PERFORMANCE_CLAIM + INDIA jurisdiction)
    │ validated by
    ▼
ValidationRun VR-88
  (regression_pass · blast_radius=document · compliance_routing_pass)
    │ approved by
    ▼
HumanDecision HD-14  (compliance_team · approved · 2026-08-20T14:23:00Z)
    │ promoted as
    ▼
DeploymentChange DC-09
  (context_assembly_rule_v3 · 2026-08-20T15:00:00Z)
```

Every link in this chain is versioned. This answers any audit question with a traceable chain — not "an agent updated the RAG".

---

## 9. Compliance KPIs

| KPI | Target | Hard Limit? |
|---|---|---|
| `applicable_control_resolution_rate` | > 95% on supported contexts | No |
| `mandatory_control_coverage` | 100% | **Yes** |
| `mandatory_control_bypass_count` | 0 | **Yes** |
| `policy_pack_version_mismatch_rate` | 0% | **Yes** |
| `policy_pack_version_traceability` | 100% | **Yes** |
| `ambiguous_applicability_rate` | tracked (high rate = pack gap) | No |
| `control_conflict_rate` | tracked (conflicts route to human) | No |
| `high_risk_unresolved_rate` | < 0.1% | No |
| `human_required_bypass_rate` | 0 | **Yes** |
| `record_reconstruction_success_rate` | 100% | **Yes** |
| `unapproved_autonomous_legal_rule_change` | 0 | **Yes** |
| `failure_graph_to_answer_leakage` | 0 | **Yes** |

All items marked **Yes** are contractual targets — they are never traded off against performance or cost.

---

## 10. Taxonomy-to-Control Coverage Gap Detection

A structural safeguard ensuring every new AMC product type or interaction pattern is mapped to at least one compliance control before it reaches production.

```python
def detect_coverage_gaps(taxonomy_version: str, pack_id: str) -> list[CoverageGap]:
    """
    Identifies taxonomy nodes that have no mapped compliance controls.
    Runs automatically when taxonomy or policy pack is updated.
    """
    all_nodes = taxonomy.get_all_nodes(version=taxonomy_version)
    covered_nodes = set()

    for control in policy_pack.get_controls(pack_id):
        covered_nodes.update(control.trigger_taxonomy_nodes)

    uncovered = [n for n in all_nodes if n.node_id not in covered_nodes
                 and n.requires_compliance_mapping]

    return [CoverageGap(
        taxonomy_node=node,
        severity="HIGH" if node.node_type in ["ADVICE_SENSITIVE", "PRODUCT"] else "MEDIUM",
        action_required="compliance_team_review_before_production",
    ) for node in uncovered]
```

A new taxonomy node with no mapped controls generates a `CONTROL_COVERAGE_GAP` alert. The node cannot be used in production until the compliance team maps it to at least one control. No LLM is needed to detect this gap.

---

*Previous: [LLD-06 — Self-Healing RAG](./LLD-06-SELF-HEALING-RAG.md)*  
*Next: [LLD-08 — Data Models](./LLD-08-DATA-MODELS.md)*


---

## 11. Component Architecture Detail

> Added from AMC_COMPONENT_ARCHITECTURE.html — August 2026

### Compliance Control → Phase Execution Map

Each control family executes at a specific point in the 8-phase flow. The table below maps every C-family to its execution phase, the specific sub-component that runs it, and the fail action.

| Control | Phase Execution | Sub-Component | D-Object Used | Fail Action |
|---|---|---|---|---|
| C01 Fair Communication | Phase 1 (Critical Intercept) + Phase 5 (E1/E3) | Phrase rules + EV_TONE_013 | D0.response_text | BLOCK / SAFE_FALLBACK |
| C02 Source Currency | Phase 1 (Critical Intercept) | EV_SRC_009 | D2.source_age_days, D2.source_version_mismatch | BLOCK |
| C03 Numerical Accuracy | Phase 1 (Critical Intercept) | EV_NAV_001, EV_TER_002, EV_NUM_010 | D2.source_provenance, D1.extracted_entities | BLOCK |
| C04 Performance Comparison | Phase 5 (E1/E3) | EV_PERF_006 + taxonomy template | D2.taxonomy_matches, D0.response_text | ALLOW_WITH_DISCLOSURE |
| C05 Advice Boundary | Phase 1 (intercept) + Phase 5 (E3/E4) | EV_ADV_007, EV_INTENT_005 | D1.detected_intent, D3.interaction_mode | SAFE_FALLBACK |
| C06 Suitability | Phase 5 (E5 escalation) | EV_SUIT_008 → human queue | D1.session_metadata, D3.advice_flag | HOLD_FOR_REVIEW |
| C07 Required Disclosures | Phase 1 (Critical Intercept) | EV_DISC_011 | D0.disclosures_shown[] | ALLOW_WITH_DISCLOSURE / BLOCK |
| C08 Eligibility | Phase 1 (Critical Intercept) | Applicability resolver | D3.applicable_control_set_id | BLOCK / REFUSE |
| C09 Supervision/HITL | Phase 5 (E5 escalation) | HITL routing rules | D3.mandatory_controls[] | HOLD_FOR_REVIEW |
| C10 Recordkeeping | Phase 1 (immediately post-generation) | EvidencePack Creator (D0–D3) | All D-objects | DO_NOT_DELIVER without record |
| C11 Privacy/PII | Phase 1 (before any LLM path) | PII detector (deterministic) | D0.response_text, D1.user_query | BLOCK / REDACT |
| C12 Promotion/Bias | Phase 1 (intercept) + Phase 5 (E3) | EV_TONE_013 + phrase rules | D0.response_text | BLOCK / SAFE_FALLBACK |
| C13 Model Governance | Continuous (E2 monitoring) | EV_GOLDEN_015 | RouterDecision logs, golden set | ROLLBACK evaluator |
| C14 Operational Resilience | Phase 1 (E0 telemetry) | EV_INFRA_014 + health checks | D0.tool_failures, service_health | FALLBACK / INCIDENT |

### Compliance Sub-Components in the Query Pipeline

| Sub-Component | Phase | What It Checks | Token Cost | Blocking? |
|---|---|---|---|---|
| D3 ApplicabilityContext Creator | Phase 1 | Resolves jurisdiction + role + product + channel → ApplicableControlSet | 0 | No (record only) |
| Critical Deterministic Intercept | Phase 1 | Hard controls: C01, C02, C03, C07, C08, C11, C12 | 0 | Yes — can BLOCK delivery |
| Advice Boundary Classifier | Phase 1 (conditional) | C05: has the interaction crossed into personal advice? | ~0 generative | Yes if threshold crossed |
| Disclosure Template Injector | Phase 1 (context assembly) | Adds required disclosure text to context before LLM synthesis | 0 | No — preventive |
| RouterDecision Audit Logger | Phase 4–5 | C10: records every routing decision with full context | 0 | No — record only |
| Compliance Routing Tester | Phase 6 shadow | C07/C08: does repair change control applicability? | 0 | Yes — blocks promotion on change |
| Post-Heal Compliance Monitor | Phase 8 | All: does repair affect compliance routing over 7-day window? | 0 | Triggers rollback if drift detected |

### Coverage Gap Detection — Implementation

Every time the AMC taxonomy is updated or a new policy pack is deployed, this check runs automatically:

```python
def detect_coverage_gaps(taxonomy_version: str, pack_id: str) -> list[CoverageGap]:
    all_nodes = taxonomy.get_nodes_requiring_compliance_mapping(version=taxonomy_version)
    covered = set()
    for control in policy_pack.get_controls(pack_id):
        covered.update(control.trigger_taxonomy_nodes)

    uncovered = [n for n in all_nodes if n.node_id not in covered]

    # Severity by node type
    for node in uncovered:
        severity = "HIGH" if node.node_type in ["ADVICE_SENSITIVE", "PRODUCT"] else "MEDIUM"
        # Action: compliance_team_review_before_production
        # Node CANNOT be used in production until mapped to at least one control

    return [CoverageGap(node, severity) for node in uncovered]
```

A `CONTROL_COVERAGE_GAP` alert blocks any taxonomy node from reaching production without at least one mapped C01–C14 control. No LLM involvement.

### Jurisdiction Pack Deployment States

| State | Meaning | Production Eligible? |
|---|---|---|
| `draft` | Under construction — compliance team authoring | No |
| `under_review` | Submitted for compliance sign-off | No |
| `approved` | Compliance team has signed. Canary-eligible. | Canary only |
| `active` | Full traffic. Monitoring window open. | Yes |
| `deprecated` | Superseded by newer version. Grace period. | No (new interactions) |
| `AMBIGUOUS_APPLICABILITY` | Runtime state — context doesn't match any pack predicate | Routes to human |
| `CONFLICTING_CONTROLS` | Runtime state — two controls conflict on same interaction | Routes to human |
| `STALE_POLICY_PACK` | Current pack version ≠ production pack version | Alert, do not auto-switch |

*See [AMC_COMPONENT_ARCHITECTURE.html](../AMC_COMPONENT_ARCHITECTURE.html) — Compliance Plane tab for interactive C01–C14 control table and jurisdiction pack governance flow.*
