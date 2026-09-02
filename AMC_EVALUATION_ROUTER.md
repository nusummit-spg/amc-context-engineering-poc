# AMC Adaptive Evaluation Router — Design Document

**Version:** 1.0  
**Status:** Design Baseline  
**Scope:** Evaluation orchestration, depth ladder, stop rules, token budget control, scenario stress test

---

## 1. Purpose

The Adaptive Evaluation Router is a **deterministic, policy-driven orchestration engine**. It decides:

> What needs to be evaluated, by which mechanism, at what depth, under which AMC/regulatory context, and within what cost/latency budget.

The Router is **not** a factual judge, compliance judge, LLM agent, or repair engine. It is a policy engine that selects the minimum sufficient evaluator and stops as soon as a decisive result is available.

### What the Router is NOT

Avoid this anti-pattern:

```
LLM decides what to evaluate
    ↓
LLM decides which agents to call
    ↓
Agents decide whether more agents are needed
```

This creates unnecessary nondeterminism, token multiplication, latency, and audit difficulty.

### What the Router IS

```
Deterministic Policy / State Engine
    +
Calibrated Statistical Signals
    +
Optional Semantic Signals (where genuinely needed)
    ↓
EvaluationPlan
```

---

## 2. Six Core Design Principles

### P1 — Mandatory controls cannot be sampled away

Cost optimisation may reduce evaluation depth for quality checks, but must **never bypass** an applicable hard AMC/regulatory control.

```
Applicable Mandatory Control
    >
Cost Optimisation
    >
Sampling Policy
```

Examples of mandatory controls (jurisdiction/policy pack dependent):
- Mandatory disclosure presence
- Hard product eligibility restrictions
- Deterministic numeric reconciliation (NAV, TER, exit load)
- Required source/current-document validation
- Privacy/data handling hard rules
- Advice/suitability escalation requirements
- Recordkeeping/evidence capture requirements

### P2 — Adaptation means minimum sufficient evaluation

```
Rule can prove it?          → use rule, STOP
Rule cannot, semantic can?  → use semantic classifier, STOP
Material ambiguity remains? → bounded LLM
Multi-step investigation?   → Agent
High-impact regulatory?     → Human / Compliance
```

### P3 — Evidence sufficiency precedes reasoning

If required evidence is missing, prefer `UNVERIFIABLE` over asking an LLM to infer truth from incomplete evidence.

### P4 — Regulatory applicability is part of routing context

The same sentence may have different significance depending on jurisdiction, regulated entity, product, customer type, channel, advice mode, and policy-pack version. Applicability is resolved **before** evaluator selection.

### P5 — Active incidents short-circuit repeated diagnosis

```
New failure observation
    ↓
Incident match (same causal signature)?
    ↓  YES
Attach to incident → reuse root cause → SKIP expensive re-diagnosis
```

### P6 — Every routing decision is auditable

The Router persists why it selected each evaluator, why it skipped others, why it stopped, why it escalated, and what budget was used.

---

## 3. Router Input Model

```
EvaluationRoutingContext
│
├── INTERACTION
│   ├── interaction_id
│   ├── intent                       taxonomy intent node
│   ├── secondary_intents[]
│   ├── intent_confidence
│   ├── entities[]                   extracted canonical entities
│   ├── conversation_state
│   └── response_type                factual | comparative | advisory | procedural
│
├── AMC CONTEXT
│   ├── amc_id                       fund house identifier
│   ├── scheme_id
│   ├── plan_option
│   ├── interaction_mode             informational | advisory | transactional
│   ├── client_segment               retail | hni | institutional | employee
│   └── channel                      chatbot | api | portal | email
│
├── REGULATORY CONTEXT
│   ├── jurisdiction
│   ├── regulated_entity_role
│   ├── policy_pack_version
│   ├── applicable_controls[]
│   └── mandatory_controls[]
│
├── EVIDENCE (from frozen EvidencePack)
│   ├── evidence_status              SUFFICIENT | PARTIAL | MISSING | CONFLICTING
│   ├── source_authority
│   ├── source_freshness_days
│   ├── temporal_validity
│   ├── retrieval_confidence
│   ├── vector_graph_agreement
│   ├── citation_state               present | broken | missing
│   └── conflict_state               none | intra_source | inter_source
│
├── RESPONSE SIGNALS
│   ├── contains_numbers             boolean
│   ├── performance_statement        boolean
│   ├── comparison_statement         boolean
│   ├── forward_looking_statement    boolean
│   ├── recommendation_language      boolean
│   └── disclosure_state             present | absent | partial
│
├── SYSTEM
│   ├── model_version
│   ├── prompt_version
│   ├── vector_index_version
│   ├── graph_version
│   ├── embedding_model_version
│   ├── policy_pack_version
│   ├── service_health               all_healthy | degraded | partial_outage
│   └── active_incident_ids[]
│
├── EVENT
│   ├── feedback_present             boolean
│   ├── feedback_categories[]
│   ├── actor_role                   user | employee | qa | compliance | sme
│   ├── anomaly_flags[]
│   └── sampling_reason              none | random | targeted | elevated
│
└── ECONOMIC BUDGET
    ├── max_sync_latency_ms          added latency budget for synchronous path
    ├── max_async_latency_ms
    ├── max_llm_tokens
    ├── max_model_cost
    ├── max_tool_calls
    ├── max_retrieval_rounds
    ├── agent_allowed                boolean
    └── human_escalation_allowed     boolean
```

The majority of these fields are populated from existing telemetry and the frozen EvidencePack — not reconstructed through an LLM.

---

## 4. Nine Decision Stages

```
R0 — Resolve Applicability
 ↓
R1 — Enforce Mandatory Controls
 ↓
R2 — Classify Signal Dimensions
 ↓
R3 — Check Evidence Sufficiency
 ↓
R4 — Check Active Incident / Known Failure
 ↓
R5 — Select Minimum Evaluation Depth
 ↓
R6 — Apply Cost / Latency Budget
 ↓
R7 — Execute Evaluators
 ↓
R8 — Apply Stop / Escalation Rules
 ↓
R9 — Emit EvaluationPlan + Decision Log
```

### R0 — Resolve Applicability

Inputs: jurisdiction, entity type, product, client category, channel, interaction mode, policy version  
Output: `ApplicableControlSet`  
Mechanism: **Rules / lookup tables / policy-as-code** — not LLM.  
Semantic evaluation only when the communication type itself is ambiguous (e.g. has the interaction shifted from information into personal advice?).

### R1 — Mandatory Controls

Execute regardless of sampling policy. Failure may result in:
- `BLOCK` — response not delivered
- `SAFE_FALLBACK` — alternative safe response substituted
- `REFUSE` — explicit refusal with reason
- `HOLD_FOR_REVIEW` — queued for human review
- `ALLOW_WITH_DISCLOSURE` — delivered with mandatory disclosure added

### R2 — Signal Dimensions

Maintain separate dimensions — do not collapse into one opaque score:

```
intent_risk            HIGH | MEDIUM | LOW | UNKNOWN
regulatory_risk        HIGH | MEDIUM | LOW | UNKNOWN
factual_risk           HIGH | MEDIUM | LOW | UNKNOWN
evidence_risk          HIGH | MEDIUM | LOW | UNKNOWN
temporal_risk          HIGH | MEDIUM | LOW | UNKNOWN
citation_risk          HIGH | MEDIUM | LOW | UNKNOWN
response_risk          HIGH | MEDIUM | LOW | UNKNOWN
system_risk            HIGH | MEDIUM | LOW | UNKNOWN
feedback_signal        PRESENT | ABSENT
incident_signal        MATCHED | NO_MATCH
```

### R3 — Evidence Sufficiency

| Evidence State | Router Response |
|---|---|
| `SUFFICIENT` | Proceed to evaluator selection |
| `PARTIAL` | Attempt bounded recovery, then proceed |
| `MISSING` | Recover or return `UNVERIFIABLE` |
| `CONFLICTING` | Conflict workflow — do not auto-adjudicate |
| `TEMPORALLY_UNCERTAIN` | Temporal/source-version workflow |

### R4 — Active Incident Match

Correlation keys checked:
- `source_id` / `source_version`
- `scheme_id` / `product_id`
- `taxonomy_node_id`
- `model_version` / `prompt_version`
- `vector_index_version` / `graph_build_version`
- `policy_pack_version`
- `jurisdiction`
- Time window (rolling 24h / 7d)

If confident match: attach observation to incident, skip diagnosis, return known root cause.

### R5 — Select Minimum Evaluation Depth

Uses the **Evaluation Depth Ladder** (Section 5). The Router selects capabilities from the **Evaluator Capability Registry** (Section 7), not named agents.

### R6 — Apply Budget

Select the smallest budget band compatible with the task. See Section 8.

### R7–R8 — Execute + Stop Rules

Fire selected evaluators sequentially or in parallel where independent. Apply stop rules after each result (Section 6).

### R9 — Emit Decision Log

See Section 9.

---

## 5. Evaluation Depth Ladder

| Level | Mechanism | Generative Tokens | Typical % Traffic | Typical Purpose |
|---|---|---|---|---|
| **E0** | Telemetry only | 0 | ~100% | Healthy low-risk monitoring, infrastructure health |
| **E1** | Deterministic rules | 0 | ~100% | IDs, dates, numbers, citations, versions, disclosures |
| **E2** | Statistical / cohort checks | 0 | broad | Drift, anomaly, retrieval-channel disagreement |
| **E3** | Semantic / NLI / classifier | ~0 generative | 10–20% | Intent, entailment, tone, relevance, advice boundary |
| **E4** | Bounded LLM judge | controlled | 2–5% | Nuanced ambiguity unresolved by E3 |
| **E5** | Agent / Human | highest | 0.1–0.8% | Multi-step investigation, regulatory ambiguity |

**Preferred cascade:**

```
E0 / E1
   ↓  unresolved?
E2 / E3
   ↓  unresolved and material?
E4
   ↓  actions / evidence investigation required?
E5
```

The sequence is not always linear. The Router may skip irrelevant levels.

**Example — infrastructure outage:**
```
E1 telemetry → health check fail → STOP
No semantic or LLM evaluation is useful here.
```

---

## 6. Five Explicit Stop Rules

### STOP-1 — Deterministic Proof

```
Authoritative structured source
+ exact entity match
+ exact temporal context
+ deterministic mismatch confirmed
    →  verdict established → STOP
```
No semantic model, LLM, or agent required.

### STOP-2 — Evidence Absent

```
Required evidence missing
+ deterministic recovery unavailable
    →  UNVERIFIABLE → STOP factual adjudication
```
Do not ask an LLM to manufacture a verdict.

### STOP-3 — Known Incident

```
Observation matches active confirmed incident
+ same causal signature
    →  attach observation → STOP repeated root-cause investigation
```
Avoids hundreds of duplicate LLM diagnoses during systemic failures.

### STOP-4 — Semantic Model Resolves

```
Semantic/NLI output
+ within validated domain
+ confidence ≥ approved threshold
    →  STOP
```

### STOP-5 — Compliance Requires Human

```
Policy says HUMAN_REQUIRED
    →  STOP automated adjudication → route to compliance/HITL
```
LLM may assist with evidence summarisation but must not replace the required human decision.

---

## 7. Evaluator Capability Registry

The Router selects **capabilities**, not named agents.

```
EvaluatorCapability
│
├── evaluator_id             e.g. EV_NAV_001
├── evaluator_version
├── capabilities[]           what this evaluator can assess
├── failure_families[]       which failure families it covers
├── control_families[]       which compliance controls it covers
├── jurisdictions[]          where it is calibrated
├── product_types[]
│
├── evaluator_type
│   ├── RULE
│   ├── STATISTICAL
│   ├── SEMANTIC
│   ├── LLM
│   └── AGENT
│
├── calibrated_precision
├── calibrated_recall
├── threshold_version
├── evidence_requirements[]
│
├── p50_latency_ms
├── p95_latency_ms
├── average_tokens
├── average_cost_usd
└── lifecycle_status         active | deprecated | experimental
```

**Examples:**

| Evaluator ID | Capability | Type | Tokens |
|---|---|---|---|
| `EV_NAV_001` | Current NAV validation | RULE | 0 |
| `EV_TER_002` | TER / expense reconciliation | RULE | 0 |
| `EV_CITE_003` | Citation integrity + entailment | RULE + NLI | ~0 generative |
| `EV_INTENT_004` | Intent classification | SEMANTIC | ~0 generative |
| `EV_PERF_005` | Performance comparison completeness | RULE + SEMANTIC | ~0 generative |
| `EV_ADV_006` | Advice/recommendation boundary | SEMANTIC + LLM | bounded |
| `EV_SUIT_007` | Suitability assessment | LLM + HUMAN | bounded |

Every evaluator finding retains: `finding · confidence · evaluator_id · evaluator_version · evidence_ids[]`

An evaluator regression is a **first-class failure** (F14), not an invisible assumption.

---

## 8. Token Budget Bands

| Band | Token Limit | Typical Use | AMC Example |
|---|---|---|---|
| **B0** | 0 generative | Rules, telemetry, numeric checks | NAV mismatch, TER lookup, citation integrity |
| **B1** | ≤ 250 | Entity disambiguation fallback | Direct vs Regular plan ambiguity |
| **B2** | ≤ 500 | Unresolved citation entailment | Citation does not clearly support claim |
| **B3** | ≤ 800 | Conflict evidence summarisation | Two authoritative sources conflict — summarise only, no verdict |
| **B4** | ≤ 1,500 | Agent investigation | Multi-step root-cause with tool calls |
| **B5** | Exception | Human-approved only | Regulatory interpretation, compliance sign-off |

The Router chooses the **smallest band compatible with the task**.

**Budget examples:**

```
NAV mismatch confirmed by rule     → B0
Ambiguous entity wording           → B0; escalate to B1 only if semantic model insufficient
Citation entailment unresolved     → B0 semantic first; B2 only if unresolved
Conflicting authoritative sources  → no LLM decision budget; optional B3 summarisation
Agent investigation                → B4/B5 only
```

### Latency Budget Targets

Separate user-response latency from evaluation completion latency:

| Path | Added User-Facing Latency Target |
|---|---|
| Telemetry / evidence capture | Minimal (async) |
| Deterministic critical intercept | ~5–40 ms target |
| Semantic hard-control classifier | ~50–150 ms where justified |
| LLM judge | Normally asynchronous |
| Agent investigation | Asynchronous |
| Human / compliance | Workflow latency, not chatbot response latency |

Where an unresolved high-risk issue remains, prefer **safe fallback / hold / escalation** rather than adding an uncontrolled multi-second LLM chain to the response path.

---

## 9. Router Decision Log

Every Router execution emits:

```
RouterDecision
│
├── router_decision_id
├── interaction_id
├── router_version
├── policy_pack_version
│
├── applicability_inputs
├── applicable_controls[]
├── mandatory_controls[]
├── signal_dimensions            {intent_risk, factual_risk, ...}
├── evidence_status
├── active_incident_matches[]
│
├── selected_evaluators[]        [{evaluator_id, version, reason}]
├── skipped_evaluators[]         [{evaluator_id, skip_reason}]
├── stop_reason                  STOP-1 | STOP-2 | ... | BUDGET_EXHAUSTED
├── escalation_reason            null | HUMAN_REQUIRED | AGENT_REQUIRED
│
├── token_budget_band            B0 | B1 | ... | B5
├── actual_tokens_used
├── actual_sync_latency_ms
└── decision_timestamp
```

This answers audit questions such as:
- *"Why did interaction X receive LLM evaluation while interaction Y did not?"*
- *"Which mandatory control caused this response to be held?"*
- *"How many tokens did the evaluation consume for this incident cluster?"*

---

## 10. Router KPIs

### 10.1 Operational KPIs

| KPI | Target |
|---|---|
| `deterministic_resolution_rate` | > 80% |
| `semantic_escalation_rate` | 10–20% |
| `llm_escalation_rate` | 2–5% |
| `agent_escalation_rate` | 0.2–0.8% |
| `human_escalation_rate` | 0.1–0.5% |
| `mandatory_control_execution_rate` | 100% |
| `mandatory_control_bypass_count` | **0** (hard target) |
| `incident_match_rate` | tracked per cycle |
| `evidence_insufficient_rate` | tracked — high rate indicates ingestion problems |

### 10.2 Economic KPIs

| KPI | Meaning |
|---|---|
| `evaluation_tokens_per_interaction` | Average token cost per evaluated interaction |
| `cost_per_true_failure_detected` | Primary cost effectiveness metric |
| `cost_per_prevented_recurrence` | Long-term ROI metric |
| `tokens_per_confirmed_root_cause` | Diagnosis efficiency |
| `escalation_yield` | Material additional findings / cases escalated |
| `deterministic_conversion_rate` | Novel failures converted to rules over time |

### 10.3 Escalation Yield

```
Escalation Yield = material additional findings / cases escalated
```

Calculate separately at each level:

```
Rule → Semantic Yield
Semantic → LLM Yield
LLM → Agent Yield
Agent → Human Yield
```

A **low yield** at any level indicates unnecessary escalation — the Router policy should be tightened.

### 10.4 Deterministic Conversion Rate

```
Deterministic Conversion Rate =
    novel recurring failure patterns converted to rules / repair recipes
    ────────────────────────────────────────────────────────────────────
    novel recurring failure patterns identified
```

The architecture should become **less generative-token dependent** as it matures, not more.

---

## 11. Fifteen-Scenario Stress Test

*An engineering design stress test. Jurisdiction policy packs determine actual mandatory controls.*

| # | AMC Scenario | Primary Evaluators | LLM? | Expected Stop | Token Budget |
|---|---|---|---|---|---|
| 1 | Current NAV factual lookup | EntityValidator + NAVNumericValidator + SourceFreshness + CitationIntegrity | Never | E1 | B0 |
| 2 | TER / exit-load factual lookup | EntityValidator + TemporalSourceValidator + FieldReconciliation | Never | E1 | B0 |
| 3 | 5-year performance comparison | Period/basis normalisation + arithmetic + structural completeness check | Only if unsupported inference remains | E1 or E3 | B0 default; ≤B2 contingency |
| 4 | Current risk classification / Riskometer | SchemeID + effective-date + current classification rule | Never | E1 | B0 |
| 5 | "I retire next year; which fund?" | Applicability + advice/suitability hard controls + intent classifier | Only if ambiguous; human where policy requires | E3 / E5 | ≤B2 if LLM; safe fallback preferred |
| 6 | Direct vs Regular / Growth vs IDCW ambiguity | Canonical IDs + alias resolver | Exceptionally | E1 or E3 | B0 default; ≤B1 contingency |
| 7 | User: "citation doesn't support this" | Citation integrity rule + NLI entailment | Only on semantic disagreement | E3 | B0 default; ≤B2 contingency |
| 8 | Stale vector/graph after source update | Source hash diff → manifest vs index → repair recipe | Never | E1 → RAG Health | B0 |
| 9 | Two authoritative sources conflict | Effective-date + hierarchy + supersession rules | Summarise only — no verdict | E5 (human) | B3 optional summary |
| 10 | Repeated invalid "hallucination" feedback | Canonical evidence check + actor-pattern statistics | Never | E1/E2 | B0 |
| 11 | New model version deployed | Version cohort monitoring + golden set + elevated sampling | Small sampled subset | E2/E3; E4 sampled | Cohort budget only |
| 12 | Graph unavailable / index partial | Service health + index build state + fallback rules | Never | E1 | B0 |
| 13 | New jurisdiction policy-pack version | Checksum + mandatory control conformance + regression suite | Sampled ambiguous tests | E1/E3/E5 | ≤B2 per ambiguous test |
| 14 | "Guaranteed best fund" wording | Hard phrase rules + disclosure rules + persuasive classifier | Only if nuanced | E1/E3 | B0 default; ≤B1 contingency |
| 15 | Multi-jurisdiction applicability conflict | Jurisdiction/entity/product/channel resolution + conflict rule | Summarise only | E5 (human) | B3 optional summary |

---

## 12. Router Failure Modes (F14 subtypes)

The Router itself is a governed component that can fail:

| Failure Subtype | Description |
|---|---|
| `wrong_applicability` | Wrong jurisdiction or entity role resolved |
| `mandatory_control_skipped` | Applicable hard control not executed |
| `wrong_evaluator_selected` | Incorrect evaluator chosen for failure family |
| `unnecessary_evaluator_selected` | More expensive evaluator used when cheaper sufficed |
| `premature_stop` | Stopped before decisive result established |
| `failure_to_stop` | Escalated unnecessarily beyond decisive result |
| `budget_overrun` | Token or latency budget exceeded silently |
| `wrong_incident_match` | Attached to wrong incident |
| `missed_incident_match` | Failed to match active incident |
| `stale_policy_pack` | Policy pack version not current |
| `audit_log_missing` | Router decision not persisted |

These must be covered by Router regression tests. The Router regression suite must include all 15 scenario types above plus: new model version, new policy pack, feedback abuse case, and high-risk human-required case.

---

## 13. Router Learning — Without Self-Rewriting

The Router must not autonomously rewrite its own production policy:

```
Routing telemetry
    ↓
Inefficient path discovered
    ↓
Candidate routing-rule change proposed
    ↓
Offline replay against historical interactions
    ↓
Compare: failure detection · false negatives · compliance coverage · tokens · latency · human escalation
    ↓
Approval by engineering + compliance
    ↓
RouterPolicy vNext deployed via normal change process
```

This maintains traceability and avoids hidden behavioural drift.

---

*This document is part of the AMC Unified Feedback, Evaluation & Self-Healing Architecture. See also: `AMC_EVIDENCE_PACK.md`, `AMC_FAILURE_TAXONOMY.md`, `AMC_SELF_HEALING_RAG.md`, `AMC_COMPLIANCE_CONTROL_PLANE.md`.*
