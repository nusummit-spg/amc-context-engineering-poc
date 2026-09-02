# LLD-04 — Adaptive Evaluation Router

**Document:** LLD-04  
**Version:** 1.0  
**Depends on:** LLD-02 (Evidence Capture), LLD-03 (Feedback Pipeline)  
**Read next:** LLD-05 (Failure Taxonomy)

---

## 1. Purpose

The Adaptive Evaluation Router is a **deterministic, policy-driven orchestration engine**. It answers one question per interaction:

> What needs to be evaluated, by which mechanism, at what depth, under which compliance context, and within what cost/latency budget?

The Router is not a judge, not an LLM, and not an agent. It selects the minimum sufficient evaluator and stops as soon as a decisive result is available. Every decision is fully auditable.

**What the Router is not:**
```
LLM decides what to evaluate  →  Anti-pattern: nondeterministic, expensive, hard to audit
    ↓
LLM decides which agents to call
    ↓
Agents decide whether more agents are needed
```

**What the Router is:**
```
Deterministic Policy Engine
    +  Calibrated Statistical Signals (E2)
    +  Optional Semantic Signals (E3, only when needed)
    ─────────────────────────────────────────
    =  EvaluationPlan (versioned, logged)
```

---

## 2. Six Design Principles

### P1 — Mandatory controls are never sampled away

Cost optimisation reduces depth for quality evaluations. It never bypasses a hard compliance control. The order of precedence is:

```
Applicable Mandatory Control > Cost Optimisation > Sampling Policy
```

### P2 — Minimum sufficient evaluation

The Router selects the cheapest mechanism that can resolve the question:
- Rule proves it → stop
- Semantic classifier resolves it → stop
- Material ambiguity remains → bounded LLM
- Multi-step evidence acquisition needed → agent
- High-impact regulatory issue → human/compliance

### P3 — Evidence sufficiency precedes reasoning

If evidence is missing, return `UNVERIFIABLE`. Do not ask an LLM to infer truth from an incomplete record.

### P4 — Regulatory applicability is resolved first

Jurisdiction alone is not enough. The applicability key is multidimensional: `jurisdiction + regulated_entity_role + product_type + channel + customer_segment + interaction_mode + policy_pack_version`. See LLD-07 for details.

### P5 — Active incidents short-circuit repeated diagnosis

If a new failure observation matches a confirmed active incident, attach it to the incident and stop. Do not repeat the diagnosis.

### P6 — Every routing decision is auditable

The Router emits a `RouterDecision` record for every execution containing: selected evaluators, skipped evaluators, stop reason, token budget used, actual latency.

---

## 3. Router Input Model

The `EvaluationRoutingContext` is assembled from the frozen EvidencePack (D0–D3), event metadata, and system health state. Most fields come from existing telemetry — no LLM required to build it.

```python
@dataclass
class EvaluationRoutingContext:

    # From D0 + D1
    interaction_id:         str
    intent:                 str         # taxonomy intent node ID
    secondary_intents:      list[str]
    intent_confidence:      float
    entities:               list[dict]
    response_type:          str         # factual | comparative | advisory | procedural
    conversation_state:     str         # fresh | continuation | multi_turn

    # From D1 session_metadata
    amc_id:                 str
    scheme_id:              Optional[str]
    interaction_mode:       str         # informational | advisory | transactional
    client_segment:         str
    channel:                str

    # From D3
    jurisdiction:           str
    regulated_entity_role:  str
    policy_pack_version:    str
    applicable_controls:    list[str]
    mandatory_controls:     list[str]   # must execute regardless of budget

    # From D2 derived_metrics
    evidence_status:        str         # SUFFICIENT | PARTIAL | MISSING | CONFLICTING
    source_authority:       str         # highest tier present
    source_freshness_days:  int         # age of oldest source
    retrieval_confidence:   float
    vector_graph_agreement: float       # % overlap between vector and graph results
    citation_state:         str         # present | broken | missing
    conflict_state:         str         # none | intra_source | inter_source

    # From D0
    contains_numbers:       bool        # response contains numeric values
    performance_statement:  bool        # response makes a performance claim
    comparison_statement:   bool        # response compares two entities
    recommendation_language:bool        # response uses recommendation-like wording
    disclosure_state:       str         # present | absent | partial

    # System state
    model_version:          str
    vector_index_version:   str
    graph_version:          str
    service_health:         str         # all_healthy | degraded | partial_outage
    active_incident_ids:    list[str]   # current open incidents

    # Event
    feedback_present:       bool
    feedback_categories:    list[str]
    actor_role:             str
    anomaly_flags:          list[str]
    sampling_reason:        str         # none | random | targeted | elevated

    # Budget
    max_sync_latency_ms:    int
    max_async_latency_ms:   int
    max_llm_tokens:         int
    agent_allowed:          bool
    human_escalation_allowed: bool
```

---

## 4. Nine Decision Stages

The Router executes these stages in sequence. Each stage may terminate the routing with a final plan.

```
R0  Resolve Applicability        → determine which controls apply
R1  Enforce Mandatory Controls   → these always run
R2  Classify Signal Dimensions   → build risk profile across 10 dimensions
R3  Check Evidence Sufficiency   → block premature adjudication
R4  Check Active Incident Match  → short-circuit if known incident matches
R5  Select Minimum Evaluation Depth → choose E0–E5 level
R6  Apply Token/Latency Budget   → select B0–B5 band
R7  Execute Evaluators           → fire selected evaluators
R8  Apply Stop Rules             → check decisiveness after each result
R9  Emit EvaluationPlan + Decision Log
```

### R0 — Resolve Applicability

**Input:** D1 `session_metadata`, D3 `jurisdiction`  
**Output:** `ApplicableControlSet` with `mandatory_controls[]` and `hard_block_controls[]`  
**Mechanism:** Rule lookup table (policy-as-code) — not LLM  
**Semantic escalation only if:** the communication type itself is ambiguous (e.g. has it crossed into personal advice?)

### R1 — Mandatory Controls

Execute regardless of sampling or budget settings. Failure produces one of:
- `BLOCK` — response withheld
- `SAFE_FALLBACK` — substitute a generic safe response
- `REFUSE` — explicit refusal returned to user
- `HOLD_FOR_REVIEW` — queued for human review
- `ALLOW_WITH_DISCLOSURE` — delivered with mandatory disclosure appended

Examples of mandatory controls (jurisdiction-dependent):
- Mandatory disclosure presence check (C07)
- Hard product eligibility restriction (C08)
- Deterministic numeric reconciliation for NAV/TER (C03)
- Privacy/PII rule (C11)
- Advice/suitability escalation trigger (C06)
- Recordkeeping capture confirmation (C10)

### R2 — Signal Dimensions

Separate risk dimensions — do not collapse into a single opaque score. A composite score is acceptable for dashboards, but hard controls must remain explicit per dimension.

```
intent_risk:         HIGH | MEDIUM | LOW | UNKNOWN
regulatory_risk:     HIGH | MEDIUM | LOW | UNKNOWN
factual_risk:        HIGH | MEDIUM | LOW | UNKNOWN
evidence_risk:       HIGH | MEDIUM | LOW | UNKNOWN
temporal_risk:       HIGH | MEDIUM | LOW | UNKNOWN
citation_risk:       HIGH | MEDIUM | LOW | UNKNOWN
response_risk:       HIGH | MEDIUM | LOW | UNKNOWN
system_risk:         HIGH | MEDIUM | LOW | UNKNOWN
feedback_signal:     PRESENT | ABSENT
incident_signal:     MATCHED | NO_MATCH
```

**Examples:**
- `contains_numbers=True AND source_freshness_days>7` → `temporal_risk=HIGH`
- `performance_statement=True AND comparison_statement=True` → `regulatory_risk=MEDIUM`
- `recommendation_language=True` → `regulatory_risk=HIGH, intent_risk=HIGH`
- `service_health=degraded` → `system_risk=HIGH`

### R3 — Evidence Sufficiency

| Evidence State | Router Action |
|---|---|
| `SUFFICIENT` | Proceed to evaluator selection |
| `PARTIAL` | Attempt bounded evidence recovery first |
| `MISSING` | Recover deterministically or return `UNVERIFIABLE` |
| `CONFLICTING` | Run conflict workflow; do not auto-adjudicate |
| `TEMPORALLY_UNCERTAIN` | Run temporal/source-version resolution |

### R4 — Active Incident Match

Correlation keys checked against the Failure-Attribution Graph:
- `source_id` / `source_version`
- `scheme_id` / `product_id`
- `taxonomy_node_id`
- `model_version` / `prompt_version`
- `vector_index_version` / `graph_build_version`
- `policy_pack_version`
- `jurisdiction`
- Time window (rolling 24h / 7d)

If a confident match is found: attach the new observation to the existing incident, return the known root cause, skip remaining stages.

### R5 — Select Minimum Evaluation Depth

Uses the Evaluation Depth Ladder (Section 5). The Router selects capabilities from the Evaluator Capability Registry (Section 7) by failure family, not by named agent.

### R6 — Apply Token/Latency Budget

Select the smallest band compatible with the task. See Section 8 for the budget band table.

### R7–R8 — Execute and Stop

Fire selected evaluators. After each result, check stop rules (Section 6). If a rule fires, terminate the evaluation plan at the current level.

### R9 — Emit Decision Log

See Section 9 for the full schema.

---

## 5. Evaluation Depth Ladder

The cascade ensures cheap mechanisms always run before expensive ones.

| Level | Mechanism | Generative Tokens | Target % Traffic | Purpose |
|---|---|---|---|---|
| **E0** | Telemetry only | 0 | ~100% | Infrastructure health, tool failures, latency anomalies, token anomalies, schema violations |
| **E1** | Deterministic rules | 0 | ~100% | Entity IDs, dates, numbers, citation integrity, source versions, disclosure presence, NAV/TER reconciliation |
| **E2** | Statistical / cohort | 0 | broad | Retrieval drift, anomaly detection, BM25/vector/graph disagreement, inter-annotator agreement, feedback clustering |
| **E3** | Semantic / NLI / classifier | ~0 generative | 10–20% | Intent classification, claim-evidence entailment, tone, advice boundary detection, context completeness |
| **E4** | Bounded LLM judge | controlled | 2–5% | Nuanced factual ambiguity unresolved by E3; implicit claims; complex multi-document synthesis |
| **E5** | Agent / Human | highest | 0.1–0.8% | Multi-step evidence acquisition requiring tool calls; regulatory ambiguity requiring compliance sign-off |

**Cascade rule:**
```
E0/E1 → unresolved? → E2/E3 → unresolved AND material? → E4
→ actions/investigation required? → E5
```

The sequence is not always linear. The Router may skip levels when they are irrelevant:
```
Example: infrastructure outage detected
→ E0 telemetry confirms graph is unavailable
→ STOP. No semantic or LLM evaluation is useful here.
```

---

## 6. Five Explicit Stop Rules

Stop rules gate escalation to the next level. They are checked after every evaluator result.

### STOP-1 — Deterministic Proof

```
Authoritative structured source
+ exact entity match
+ exact temporal context
+ deterministic mismatch confirmed
    → verdict established → STOP
```
No semantic model, LLM, or agent is needed when a rule has established the answer.

### STOP-2 — Evidence Absent

```
Required evidence missing
+ deterministic recovery unavailable
    → UNVERIFIABLE → STOP factual adjudication
```
Do not ask an LLM to manufacture a verdict from incomplete evidence. `UNVERIFIABLE` is a valid, correct result.

### STOP-3 — Known Incident

```
Observation matches active confirmed incident
+ same causal signature
    → attach observation to incident → STOP repeated root-cause investigation
```
This rule prevents hundreds of duplicate LLM diagnoses during systemic failures such as a failed ingestion job.

### STOP-4 — Semantic Model Resolves

```
Semantic/NLI output
+ within validated calibration domain
+ confidence ≥ approved threshold
    → STOP
```
No LLM needed if the calibrated classifier is decisive.

### STOP-5 — Compliance Requires Human Decision

```
Policy says HUMAN_REQUIRED for this control
    → STOP automated adjudication
    → Route to compliance/HITL queue
```
An LLM may assist with evidence summarisation but must not replace the required human decision.

---

## 7. Evaluator Capability Registry

The Router selects **capabilities**, not named agents or specific models. This decouples routing logic from evaluator implementation.

```python
@dataclass
class EvaluatorCapability:
    evaluator_id:          str       # e.g. EV_NAV_001
    evaluator_version:     str
    capabilities:          list[str] # what it can assess
    failure_families:      list[str] # F01–F14 it covers
    control_families:      list[str] # C01–C14 it covers
    jurisdictions:         list[str] # where it is calibrated

    evaluator_type:        str       # RULE | STATISTICAL | SEMANTIC | LLM | AGENT

    calibrated_precision:  float
    calibrated_recall:     float
    threshold_version:     str
    evidence_requirements: list[str] # what D2 fields it needs

    p50_latency_ms:        int
    p95_latency_ms:        int
    average_tokens:        int       # 0 for RULE and STATISTICAL
    average_cost_usd:      float
    lifecycle_status:      str       # active | deprecated | experimental
```

**Standard evaluator catalogue:**

| ID | Capability | Type | Token Cost | Failure Families |
|---|---|---|---|---|
| `EV_NAV_001` | Current NAV validation against structured source | RULE | 0 | F05, F08 |
| `EV_TER_002` | TER / expense ratio reconciliation | RULE | 0 | F05, F08 |
| `EV_CITE_003` | Citation integrity + NLI entailment | RULE + NLI | ~0 gen. | F06 |
| `EV_ENT_004` | Entity resolution + alias check | RULE | 0 | F02 |
| `EV_INTENT_005` | Intent classification | SEMANTIC | ~0 gen. | F01 |
| `EV_PERF_006` | Performance comparison completeness | RULE + SEMANTIC | ~0 gen. | F09 |
| `EV_ADV_007` | Advice/recommendation boundary | SEMANTIC + LLM | bounded | F12 |
| `EV_SUIT_008` | Suitability assessment | LLM + HUMAN | bounded | F12 |
| `EV_SRC_009` | Source freshness + effective date | RULE | 0 | F05 |
| `EV_NUM_010` | General numeric/date/unit reconciliation | RULE | 0 | F08 |
| `EV_DISC_011` | Required disclosure presence + placement | RULE | 0 | F12 |
| `EV_COMP_012` | Semantic completeness check | SEMANTIC | ~0 gen. | F09 |
| `EV_TONE_013` | Communication tone classifier | SEMANTIC | ~0 gen. | F11 |
| `EV_INFRA_014` | Infrastructure / service health | RULE | 0 | F13 |
| `EV_GOLDEN_015` | Golden-set regression | STATISTICAL | 0 | F14 |

Every evaluator finding retains: `finding`, `confidence`, `evaluator_id`, `evaluator_version`, `evidence_ids[]`.

An evaluator regression (EV_GOLDEN_015 detecting the evaluator itself is wrong) is a **first-class failure** (F14), not an invisible assumption.

---

## 8. Token Budget Bands

| Band | Token Limit | Typical Use Case | AMC Example |
|---|---|---|---|
| **B0** | 0 generative | Rules, telemetry, numeric checks | NAV mismatch · TER reconciliation · citation presence |
| **B1** | ≤ 250 | Entity disambiguation fallback only | Direct vs Regular plan ambiguity |
| **B2** | ≤ 500 | Unresolved citation entailment | Citation does not clearly support claim |
| **B3** | ≤ 800 | Evidence conflict summarisation | Two authoritative sources conflict — summarise only, no verdict |
| **B4** | ≤ 1,500 | Agent investigation | Multi-step root cause requiring tool calls |
| **B5** | Exception (explicit approval) | Human-approved investigation | Regulatory interpretation · compliance sign-off |

**Decision examples:**
```
NAV mismatch confirmed by rule                → B0
Ambiguous entity wording                      → B0; escalate to B1 if classifier insufficient
Citation entailment unresolved at E3          → B2
Two authoritative sources conflict            → no LLM decision; B3 summarisation only
Multi-step root-cause requiring agent tools   → B4
Regulatory interpretation (R5 repair class)  → B5
```

**Latency budget targets** — separate from token budget:

| Path | Added User-Facing Latency |
|---|---|
| Evidence capture + critical intercept | < 40 ms total |
| Semantic hard-control classifier | < 150 ms where justified |
| LLM judge | Asynchronous — no user-facing impact |
| Agent investigation | Asynchronous |
| Human/compliance review | Workflow SLA, not chatbot response |

---

## 9. Router Decision Log Schema

Every Router execution emits one `RouterDecision` record. This record is the primary audit artifact.

```python
@dataclass
class RouterDecision:
    router_decision_id:     str      # UUID
    interaction_id:         str
    router_version:         str
    policy_pack_version:    str
    decision_timestamp:     datetime

    # Inputs
    applicability_inputs:   dict     # jurisdiction, role, product, channel
    applicable_controls:    list[str]
    mandatory_controls:     list[str]
    signal_dimensions:      dict     # {intent_risk, factual_risk, ...}
    evidence_status:        str
    active_incident_matches:list[str]

    # Decisions
    selected_evaluators:    list[dict]  # [{evaluator_id, version, reason_for_selection}]
    skipped_evaluators:     list[dict]  # [{evaluator_id, reason_for_skip}]
    stop_reason:            str      # STOP-1 | STOP-2 | STOP-3 | STOP-4 | STOP-5 | BUDGET_EXHAUSTED
    escalation_reason:      Optional[str]  # HUMAN_REQUIRED | AGENT_REQUIRED | null

    # Economics
    token_budget_band:      str      # B0–B5
    actual_tokens_used:     int
    actual_sync_latency_ms: int
    actual_async_latency_ms:int
```

This record answers:
- *"Why did interaction X receive LLM evaluation while Y did not?"*
- *"Which mandatory control caused this response to be held?"*
- *"How many tokens did this incident cluster consume in total?"*
- *"Why was this escalated to a human?"*

---

## 10. Fifteen-Scenario Stress Test

Engineering validation. Jurisdiction policy packs determine actual mandatory controls in production.

| # | Scenario | Primary Evaluators | LLM? | Expected Stop | Budget |
|---|---|---|---|---|---|
| 1 | Current NAV factual lookup | EV_ENT_004 + EV_NAV_001 + EV_SRC_009 + EV_CITE_003 | Never | E1 | B0 |
| 2 | TER / exit-load factual lookup | EV_ENT_004 + EV_TER_002 + EV_SRC_009 | Never | E1 | B0 |
| 3 | 5-year performance comparison | EV_NUM_010 + EV_PERF_006 | Only if unsupported inference | E1/E3 | B0 default; B2 contingency |
| 4 | Riskometer classification | EV_ENT_004 + EV_SRC_009 + custom risk rule | Never | E1 | B0 |
| 5 | "I retire next year; which fund?" | EV_INTENT_005 + EV_ADV_007 + EV_SUIT_008 | Only if ambiguous; human if required | E3/E5 | B2 if LLM; safe fallback preferred |
| 6 | Direct vs Regular / Growth vs IDCW | EV_ENT_004 + alias resolver | Exceptionally | E1/E3 | B0 default; B1 contingency |
| 7 | User: "citation doesn't support this" | EV_CITE_003 | Only on semantic disagreement | E3 | B0 default; B2 contingency |
| 8 | Stale vector/graph after source update | EV_SRC_009 + source manifest diff | Never | E1 → RAG Health | B0 |
| 9 | Two authoritative sources conflict | EV_SRC_009 + hierarchy check | Summarise only — no verdict | E5 (human) | B3 summary only |
| 10 | Repeated invalid "hallucination" feedback | EV_NUM_010 + EV_GOLDEN_015 | Never | E1/E2 | B0 |
| 11 | New model version deployed | EV_GOLDEN_015 + elevated sampling | Small sampled subset | E2/E3; E4 sampled | Cohort budget only |
| 12 | Graph / index unavailable | EV_INFRA_014 | Never | E0 | B0 |
| 13 | New jurisdiction policy pack | EV_DISC_011 + regression suite | Sampled ambiguous tests | E1/E3/E5 | B2 per ambiguous |
| 14 | "Guaranteed best fund" wording | EV_DISC_011 + EV_TONE_013 + EV_ADV_007 | Only if nuanced | E1/E3 | B0 default; B1 contingency |
| 15 | Multi-jurisdiction conflict | Applicability resolver + conflict rule | Summarise only | E5 (human) | B3 summary only |

---

## 11. Router Failure Modes

The Router is itself a governed component subject to the same failure taxonomy. These subtypes belong to F14 (Evaluation/Feedback Integrity):

| Failure | Description | Detection |
|---|---|---|
| `wrong_applicability` | Wrong jurisdiction or entity role resolved | RouterDecision audit + golden regression |
| `mandatory_control_skipped` | Applicable hard control not executed | RouterDecision mandatory_controls diff |
| `wrong_evaluator_selected` | Incorrect evaluator for the failure family | Escalation yield analysis |
| `unnecessary_evaluator_selected` | More expensive evaluator when cheaper sufficed | Token cost per resolution |
| `premature_stop` | Stopped before decisive result | False negative rate on golden set |
| `failure_to_stop` | Escalated past decisive result | Escalation yield < threshold |
| `budget_overrun` | Token/latency budget silently exceeded | RouterDecision economics fields |
| `stale_policy_pack` | Policy pack version not current | Policy pack version mismatch monitor |
| `audit_log_missing` | RouterDecision not persisted | Completeness check on decision log |

---

## 12. Router KPIs

### Operational

| KPI | Target |
|---|---|
| `deterministic_resolution_rate` | > 80% |
| `semantic_escalation_rate` | 10–20% |
| `llm_escalation_rate` | 2–5% |
| `agent_escalation_rate` | 0.2–0.8% |
| `human_escalation_rate` | 0.1–0.5% (+ all policy-mandated cases) |
| `mandatory_control_execution_rate` | 100% |
| `mandatory_control_bypass_count` | 0 (hard target) |

### Economic

| KPI | Description |
|---|---|
| `cost_per_true_failure_detected` | Primary cost-effectiveness metric |
| `cost_per_prevented_recurrence` | Long-term ROI |
| `escalation_yield` | Material findings / cases escalated at each level |
| `deterministic_conversion_rate` | Novel failures converted to rules or recipes over time |

### Escalation Yield Detail

```
Escalation Yield = material additional findings / cases escalated

Measure at each transition:
  Rule     → Semantic Yield
  Semantic → LLM Yield
  LLM      → Agent Yield
  Agent    → Human Yield

Low yield at any level = Router policy needs tightening
```

---

*Previous: [LLD-03 — Feedback Pipeline](./LLD-03-FEEDBACK-PIPELINE.md)*  
*Next: [LLD-05 — Failure Taxonomy](./LLD-05-FAILURE-TAXONOMY.md)*


---

## 13. Component Architecture Detail

> Added from AMC_COMPONENT_ARCHITECTURE.html — August 2026

### Router Stage Sub-Component Internals

| Stage | Component | Mechanism | Latency | LLM? | Output |
|---|---|---|---|---|---|
| R0 | Applicability Resolver | Multidimensional lookup: jurisdiction + role + product + channel + segment + mode + pack version | ~1ms | No | ApplicableControlSet |
| R1 | Mandatory Control Executor | Execute all controls in mandatory_controls[]; fail → BLOCK/SAFE_FALLBACK/REFUSE/HOLD/ALLOW_WITH_DISC | ~5–40ms | Only if C05/C06 ambiguous | Per-control finding + action |
| R2 | Signal Dimension Calculator | 10 independent rules mapping D1/D2/D3 fields to risk levels | ~2ms | No | 10-dimensional risk profile |
| R3 | Evidence Sufficiency Gate | Check D2.derived_metrics.source_version_mismatch, missing_expected_source, citation_coverage | ~1ms | No | SUFFICIENT/PARTIAL/MISSING/CONFLICTING/TEMPORALLY_UNCERTAIN |
| R4 | Incident Matcher | Redis lookup: source_id + taxonomy_node_id + model_version + time window vs `incident_active` set | ~2ms | No | Matched incident ID or no_match |
| R5 | Evaluator Selector | Capability Registry lookup by failure_family + signal dimensions + applicable_controls | ~1ms | No | Selected evaluator list |
| R6 | Budget Assigner | Map selected evaluators to B0–B5 band based on evaluator type + signal severity | ~1ms | No | token_budget_band |
| R7–R8 | Evaluator Executor + Stop Rule Checker | Fire evaluators; check STOP-1 through STOP-5 after each result | Variable | Only E4/E5 evaluators | EvaluatorFindings + stop_reason |
| R9 | Decision Logger | Async INSERT to router_decisions table | ~5ms async | No | RouterDecision record |

### Signal Dimension Rules — Full Mapping

| Signal | HIGH Condition | MEDIUM Condition | LOW Condition |
|---|---|---|---|
| `intent_risk` | recommendation_language=True | comparison_statement=True | factual_lookup only |
| `regulatory_risk` | performance_statement AND comparison OR advice threshold crossed | performance_claim present | purely informational |
| `factual_risk` | contains_numbers=True AND source_age_days > 7 | contains_numbers=True AND source_age_days ≤ 7 | no numeric values |
| `evidence_risk` | evidence_status = MISSING or CONFLICTING | evidence_status = PARTIAL | evidence_status = SUFFICIENT |
| `temporal_risk` | source_age_days > threshold (jurisdiction-specific) | source_age_days within warning band | source current |
| `citation_risk` | citation_state = MISSING or BROKEN | citation_state = PARTIAL | citation_state = PRESENT |
| `response_risk` | truncation_flag = True OR guardrail_state = TRIGGERED | retrieval_score_min < 0.5 | all nominal |
| `system_risk` | service_health = PARTIAL_OUTAGE | service_health = DEGRADED | service_health = ALL_HEALTHY |
| `feedback_signal` | PRESENT (feedback submitted for this interaction) | — | ABSENT |
| `incident_signal` | MATCHED (active incident confirmed) | — | NO_MATCH |

### Five Stop Rules — Implementation Logic

```python
def check_stop_rules(findings: list[EvaluatorFinding], context: EvaluationRoutingContext) -> Optional[str]:
    """
    Returns stop_reason if any rule fires, else None (continue evaluation).
    Called after every evaluator result.
    """
    # STOP-1: Deterministic proof
    for f in findings:
        if f.confidence == 1.0 and f.method == "RULE" and f.verdict in ("PASS", "FAIL"):
            return "STOP-1"

    # STOP-2: Evidence absent — UNVERIFIABLE is correct
    if context.evidence_status in ("MISSING", "UNVERIFIABLE"):
        return "STOP-2"

    # STOP-3: Known incident — attach and stop
    if context.active_incident_ids:
        return "STOP-3"

    # STOP-4: Semantic model resolves with sufficient confidence
    for f in findings:
        if f.method in ("SEMANTIC", "NLI") and f.confidence >= f.evaluator.threshold_version:
            return "STOP-4"

    # STOP-5: Compliance policy requires human decision
    for control in context.mandatory_controls:
        if control.evaluation_type == "HUMAN_REQUIRED":
            return "STOP-5"

    return None  # continue
```

### 15-Scenario Validation Matrix — AMC-Specific

The following table shows what a correct Router execution looks like for each standard AMC scenario. Engineering tests must verify these outcomes.

| Scenario | Expected E-Level | Expected Stop | Expected Budget | LLM Invoked? |
|---|---|---|---|---|
| Current NAV lookup | E1 | STOP-1 | B0 | No |
| TER / exit-load lookup | E1 | STOP-1 | B0 | No |
| 5-year performance comparison | E1, E3 contingency | STOP-1 or STOP-4 | B0, B2 contingency | Only if unsupported inference |
| Riskometer classification | E1 | STOP-1 | B0 | No |
| Retirement fund recommendation | E3–E5 | STOP-5 (human required) | B2 or SAFE_FALLBACK | Only if ambiguous |
| Direct vs Regular confusion | E1, E3 contingency | STOP-1 or STOP-4 | B0, B1 contingency | Exceptionally |
| Citation dispute | E1/E3 | STOP-1 or STOP-4 | B0, B2 contingency | Only on semantic disagreement |
| Stale vector/graph | E1 → RAG Health | STOP-1 | B0 | No |
| Two conflicting authoritative sources | E5 (human) | STOP-5 | B3 summary only | No verdict |
| Graph/index unavailable | E0 | E0 telemetry | B0 | No |

*See [AMC_COMPONENT_ARCHITECTURE.html](../AMC_COMPONENT_ARCHITECTURE.html) — Eval Router tab for interactive component cards and the full E0–E5 table.*
