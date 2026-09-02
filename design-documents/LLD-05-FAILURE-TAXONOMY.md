# LLD-05 — Failure Taxonomy & Root-Cause Attribution

**Document:** LLD-05  
**Version:** 1.0  
**Depends on:** LLD-04 (Evaluation Router), LLD-02 (Evidence Capture)  
**Read next:** LLD-06 (Self-Healing RAG)

---

## 1. The Central Design Principle

> **"Hallucination" is not a root cause. It is a symptom.**

This is the most consequential design decision in the taxonomy. When a user reports "wrong answer", the actual defect may be any of:

| User-Reported Symptom | Actual Root Cause | LLM Tokens to Diagnose | Repair |
|---|---|---|---|
| "Wrong NAV" | Source not updated in 3 days | 0 — version diff check | R001: source refresh |
| "Wrong fund mentioned" | Entity alias collision (Direct vs Regular) | 0 — canonical ID lookup | R010: entity dedup |
| "Citation is incorrect" | Context engineering selected wrong chunk | 0 — chunk ID check | Context reranking rule |
| "Response is hallucinated" | Generation error — model transcribed incorrectly | Semantic + possible LLM | Prompt/model investigation |
| "Missing risk warning" | Disclosure template not in context | 0 — template presence check | Context rule update |

Labelling everything "hallucination" wastes diagnostic tokens, triggers the wrong repair, and creates false regression signals.

**The separation that must always hold:**
```
Observable symptom  ≠  Technical origin  ≠  Repair action
```

---

## 2. Four Classification Axes

Every failure observation records all four dimensions. This is mandatory — partial classification is permitted only during initial triage.

### Axis A — What Failed?
```
Intent · Entity · Context · Retrieval · Source · Citation · Grounding
Accuracy · Completeness · Reasoning · Communication · Governance
Infrastructure · Evaluation
```

### Axis B — How Was It Detected?
```
RULE | STATISTICAL | SEMANTIC | LLM | AGENT | HUMAN
```

### Axis C — Where Did It Originate?
```
Query Understanding · Taxonomy · Source Ingestion · Vector DB · Context Graph
Retrieval Pipeline · Reranking · Context Engineering · Generation
Guardrail · UI · User Feedback Interpretation
```

### Axis D — What Should Heal It?
```
NO_ACTION | RULE_FIX | SOURCE_REFRESH | REINDEX | REEMBED
GRAPH_REPAIR | TAXONOMY_UPDATE | CONTEXT_RULE
PROMPT_CHANGE | MODEL_CHANGE | HUMAN_REVIEW
```

**Complete example:**
```
Scenario: User says "the citation doesn't support this claim about TER"

Axis A — What:    F06 Citation — citation does not support claim
Axis B — How:     SEMANTIC (NLI entailment model EV_CITE_003)
Axis C — Origin:  Context Engineering — wrong chunk ranked to top
Axis D — Heal:    CONTEXT_RULE — update reranking weight for TER queries
```

---

## 3. Failure Analysis Matrix — Detection Cost by Family

| Failure Family | Deterministic Detection | Semantic Detection | LLM Required | Typical Origin |
|---|---|---|---|---|
| F01 Explicit intent | High | Low | Rare | Query understanding |
| F01 Implicit intent | Low | High | Conditional | Intent classifier |
| F02 Entity resolution | High | Medium | Rare | Alias / ID lookup |
| F04 Missing retrieval | High | None | None | Vector/graph index |
| F05 Stale source | High | None | None | Ingestion pipeline |
| F06 Citation integrity | High | None | None | Citation pipeline |
| F06 Citation entailment | Low | High | Conditional | Context/generation |
| F08 Numeric error | High | Low | Rare | Generation/arithmetic |
| F07 Unsupported claim | Low | High | Conditional | Generation |
| F09 Completeness | Medium | High | Conditional | Context/generation |
| F11 Tone/Communication | Medium | High | Conditional | Generation |
| F12 Advice boundary | Medium | High | Conditional | Policy/generation |
| F13 Infrastructure | High | None | None | Telemetry |
| F14 Evaluator failure | High | None | None | Golden set monitoring |

The key insight: the majority of AMC failures (F02, F04, F05, F06, F08, F13) are diagnosable deterministically at zero LLM cost.

---

## 4. The 14 Primary Failure Families

### F01 — Intent / Understanding

The system misunderstood what the user asked.

**Subtypes:** `wrong_primary_intent`, `missed_secondary_intent`, `multi_intent_not_detected`, `ambiguity_not_detected`, `wrong_taxonomy_mapping`, `temporal_intent_wrong`, `comparison_intent_wrong`, `recommendation_intent_missed`, `informational_vs_advisory_confusion`, `conversation_intent_drift`

**Deterministic detection example:**
```
Query: "What is the NAV of Axis Bluechip Fund today?"

Extracted intent:
  ENTITY_TYPE  = Scheme
  ENTITY       = Axis Bluechip Fund
  ATTRIBUTE    = NAV
  TEMPORAL     = current
  QUERY_TYPE   = factual_lookup

Rule checks:
  ✓ known scheme in taxonomy?
  ✓ NAV is a valid attribute for this scheme?
  ✓ "today" resolved to current date?
  ✓ response contains NAV, not TER or AUM?
```

**Escalation path:**
```
Clear explicit intent  → deterministic rule
Ambiguous / implicit   → intent classifier (E3)
Multi-intent / advice  → semantic + policy evaluation (E3)
Unresolved             → bounded LLM (E4)
```

---

### F02 — Entity Resolution

The system answered about the wrong entity.

**Subtypes:** `entity_not_detected`, `wrong_entity`, `entity_collision`, `alias_resolution_failure`, `plan_option_confusion`, `direct_regular_confusion`, `growth_IDCW_confusion`, `stale_entity_mapping`

**Critical point:** A response can be **perfectly grounded** against the **wrong entity**. This is not hallucination — it is an entity resolution failure. The chain is:
```
correct source retrieved, correct value copied, wrong entity ID resolved
→ F02, not F07
→ repair: entity alias registry update, not prompt change
```

**Resolution priority (canonical ID first):**
```
1. ISIN
2. Canonical scheme ID (AMC master data)
3. SEBI scheme code
4. Alias registry lookup (normalised fund name variants)
5. Semantic resolution  ← only when all above fail
```

---

### F03 — Context / Conversation State

The system forgot or misused information from earlier in the conversation.

**Subtypes:** `previous_turn_ignored`, `stale_turn_used`, `wrong_reference`, `context_overflow`, `critical_evidence_truncated`, `irrelevant_context_injected`, `contradictory_context`, `user_constraint_forgotten`

**Deterministic checks:** Was required `context_id` present in D1? Was the selected product consistent across turns? Did a context truncation flag fire? Was a critical chunk omitted from D2 `evidence_rejected[]`?

---

### F04 — Retrieval

The correct knowledge existed but was not retrieved.

**Subtypes:** `no_retrieval`, `wrong_document`, `low_recall`, `missing_authoritative_source`, `vector_miss`, `lexical_miss`, `graph_miss`, `rank_failure`, `filter_failure`, `metadata_filter_failure`, `query_rewrite_failure`

**Deterministic diagnosis tree (zero LLM):**
```
Does the canonical source exist in source registry?
    NO  → Knowledge Gap (F05) — ingestion issue
    YES ↓
Was it ingested into the vector index and graph?
    NO  → Ingestion failure (F05) — reindex
    YES ↓
Was it retrieved in the retrieval call?
    NO  → Retrieval miss (F04 vector/lexical/graph miss) — embedding investigation
    YES ↓
Was it in the Top-K passed to context engineering?
    NO  → Low recall / rank failure (F04) — reranker investigation
    YES ↓
Was it selected into the final context?
    NO  → Context Engineering failure (F03) — filtering/selection rule
    YES → Passed to model. Problem is in generation (F07/F10)
```

---

### F05 — Source / Freshness

The model used correct information from a stale or wrong source version.

**Subtypes:** `stale_source`, `expired_source`, `superseded_document`, `wrong_effective_date`, `low_authority_source`, `missing_source`, `source_version_conflict`, `ingestion_lag`

**The critical distinction (zero LLM diagnosis):**
```
Response TER = 0.79%    (from source v17, ingested 6 weeks ago)
Canonical TER = 0.82%   (from source v18, current)
    ↓
Source version check: v17 ≠ v18
    ↓
PRIMARY_CAUSE = SOURCE_FRESHNESS_FAILURE (F05)
This is NOT hallucination (F07)
Repair = R002 StaleEmbedding (selective re-embed)
LLM tokens for diagnosis = 0
```

---

### F06 — Citation / Attribution

The citations shown to the user are wrong, broken, or do not support the claim they accompany.

**Subtypes:** `citation_missing`, `citation_broken`, `citation_wrong_document`, `citation_wrong_span`, `citation_does_not_support_claim`, `citation_partial_support`, `citation_stale`, `claim_without_citation`, `citation_overstatement`

**Three-level detection split:**
```
Citation Integrity      → deterministic (citation present, URL resolves, source_id matches retrieved)
Citation Entailment     → semantic NLI (does source text actually support the claim?)
Citation Interpretation → bounded LLM only when NLI result is ambiguous
```

---

### F07 — Grounding / Unsupported Generation

The model generated content not supported by the retrieved evidence.

**Subtypes:** `unsupported_claim`, `fabricated_fact`, `fabricated_entity`, `fabricated_number`, `fabricated_source`, `evidence_overextension`, `unsupported_synthesis`, `contradiction_with_evidence`, `unverifiable_claim`

**Important:** F07 is the narrowest definition of "hallucination". It applies only when:
- Correct evidence was retrieved ✓
- Correct evidence was selected into context ✓
- The model generated content inconsistent with that evidence ✗

This requires semantic detection (NLI/E3 or LLM/E4). It should not be diagnosed without first ruling out F04 and F05 deterministically.

---

### F08 — Factual / Numerical Accuracy

A specific numeric value, date, percentage, or unit in the response is wrong.

**Subtypes:** `numeric_mismatch`, `date_mismatch`, `percentage_error`, `currency_error`, `unit_error`, `calculation_error`, `entity_attribute_error`, `comparative_fact_error`, `temporal_fact_error`

**Deterministic example:**
```
Response: "The TER of Axis Bluechip Fund Direct Growth is 0.79%"
Canonical: TER = 0.82% (from structured data feed, current)
    ↓
deterministic FAIL at E1, zero LLM tokens
Root cause: generation transcription error (F07) if source had 0.82%;
            source freshness failure (F05) if source had 0.79% at ingestion time
```

---

### F09 — Completeness / Relevance

The response answered the question but omitted required information.

**Subtypes:** `omitted_required_fact`, `omitted_risk_information`, `omitted_constraint`, `incomplete_comparison`, `question_part_unanswered`, `excessive_information`, `irrelevant_information`

**Taxonomy template check (deterministic):**
For a performance comparison response, the template must include:
```
✓ scheme category (equity/debt/hybrid)
✓ benchmark used
✓ risk classification (Riskometer)
✓ expense ratio (TER)
✓ exit load
✓ return period and basis (CAGR/absolute)
```

Structural completeness is checked by template rule (E1). Semantic completeness (did the answer actually address the implicit question?) requires E3.

---

### F10 — Reasoning / Consistency

The reasoning or inference in the response is flawed.

**Subtypes:** `internal_contradiction`, `evidence_contradiction`, `unsupported_inference`, `wrong_comparison`, `causal_leap`, `conclusion_not_supported`, `mathematical_reasoning_error`

Rules handle: arithmetic, date calculations, unit conversions, ordering comparisons. Semantic/LLM needed for: inference validity, unsupported causal claims, nuanced multi-step reasoning.

---

### F11 — Communication / Tone

The factual content is correct but the presentation is problematic.

**Subtypes:** `inappropriate_tone`, `excessive_jargon`, `verbosity`, `unclear_answer`, `misleading_certainty`, `aggressive_or_persuasive_language`, `poor_structure`, `language_mismatch`

Deterministic checks: requested language, response length, prohibited absolute wording (e.g. "guaranteed", "risk-free"), required formatting, disclosure placement.

---

### F12 — Governance / Compliance / Safety

The response violates a regulatory or policy constraint.

**Subtypes:** `advice_boundary`, `suitability`, `prohibited_claim`, `missing_disclosure`, `unfair_or_promotional_language`, `privacy_or_PII`, `recordkeeping`, `jurisdiction_mismatch`, `product_restriction`, `escalation_required`

This family maps directly to the compliance control families C01–C14 in LLD-07. Detection strategy per subtype:
- `missing_disclosure` → deterministic (C07 template presence check)
- `prohibited_claim` → hard phrase rules (C01)
- `advice_boundary` → semantic classifier + policy pack (C05)
- `suitability` → LLM + human required (C06)
- `privacy_or_PII` → deterministic rule before any LLM (C11)

---

### F13 — System / Infrastructure

An operational failure, not a knowledge or reasoning failure.

**Subtypes:** `vector_unavailable`, `graph_unavailable`, `partial_index`, `ingestion_failed`, `index_build_in_progress`, `timeout`, `rate_limit`, `tool_failure`, `cache_corruption`, `replica_lag`, `dependency_unavailable`

Detection: deterministic telemetry only. LLM cost = 0. Healing: retry, fallback, restore, rebuild, traffic shift. This family exists to distinguish operational problems from knowledge problems — a common source of misdiagnosis.

---

### F14 — Evaluation / Feedback Integrity

The evaluation system itself is wrong.

**Subtypes:** `evaluator_false_positive`, `evaluator_false_negative`, `threshold_miscalibration`, `evaluator_version_regression`, `judge_disagreement`, `feedback_abuse`, `feedback_poisoning_attempt`, `duplicate_feedback`, `feedback_misclassification`, `evidence_leakage_to_evaluator`, `evaluation_pipeline_failure`

**Critical scenario:**
```
Production model remains stable (golden set passes)
New evaluator version EV_CITE_003 v2.1 deployed
"Hallucination rate" doubles in dashboard
Golden set unchanged → model output unchanged
    ↓
EVALUATOR REGRESSION (F14, not F07)
    ↓
DO NOT modify the RAG. Fix or roll back the evaluator.
```

Detection: EV_GOLDEN_015 runs on every evaluator version change. If golden set behaviour unchanged but evaluator findings change → F14 evaluator regression.

---

## 5. Repair Eligibility Classes (R0–R5)

A confirmed root cause is **not** automatically eligible for automated repair. A defect must pass all eligibility checks before a repair class is assigned.

**Eligibility checklist:**
```
Is the root cause source-provable?
Is the repair deterministic (same input → same output)?
Is it reversible?
Is the blast radius bounded?
Is a validation test available?
Is provenance preserved post-repair?
Is the compliance impact understood?
Does policy permit automatic change?
```

| Class | Name | Meaning | Example | Default Action |
|---|---|---|---|---|
| **R0** | No Repair | Defect is invalid, noisy, or user error | Feedback abuse · Unsupported complaint | Close & monitor |
| **R1** | Auto-Safe Mechanical | Mechanical fix, bounded impact, deterministic | Missing embedding · Broken index chunk | Automatic repair + verify |
| **R2** | Auto + Shadow | Source-provable fix requiring shadow validation | Stale graph edge with canonical replacement | Shadow repair → regression → promote if pass |
| **R3** | Approval Required | Structural change requiring governance | Taxonomy node change · Policy update | Governance approval gate |
| **R4** | Investigative | Ambiguous or conflicting evidence | Conflicting authoritative sources | Agent / SME investigation |
| **R5** | Prohibited Auto-Repair | Regulatory or legal ambiguity | Regulatory interpretation · Advice boundary | Human / Compliance only — never automated |

---

## 6. Root-Cause Attribution Strategy

**Preferred hierarchy — always try cheaper methods first:**
```
1. Deterministic causal evidence     (strongest — zero LLM)
2. Strong structural/provenance evidence
3. Statistical correlation
4. Semantic explanation              (E3 NLI/classifier)
5. LLM hypothesis                   (E4 — bounded, represents possibility not confirmation)
6. Human adjudication               (required for legal/regulatory ambiguity)
```

An LLM hypothesis is stored as `POSSIBLE_CAUSE (confidence=X, method=LLM)`. It requires corroboration by structural evidence or human review before becoming `CONFIRMED_CAUSE`.

### Confidence States

```
CONFIRMED         — deterministic evidence proves the cause
HIGH_CONFIDENCE   — strong structural + statistical evidence
PROBABLE          — semantic evidence + corroborating signals
POSSIBLE          — LLM hypothesis or single corroborating signal
UNKNOWN           — cannot determine cause
CONFLICTING       — multiple competing explanations, none dominant
```

### Multi-Cause Attribution

Do not force a single root cause. Multiple contributing factors may coexist:
```
Example: response contains wrong fund manager name

PRIMARY_CAUSE:    SOURCE_FRESHNESS (F05) — fund manager changed but source not updated
CONTRIBUTOR_1:    ENTITY_RESOLUTION (F02) — alias not updated in entity registry
CONTRIBUTOR_2:    CONTEXT_ENGINEERING (F03) — new manager document was retrieved but ranked low

Repair order:
  1. Update source (SOURCE_REFRESH)
  2. Update alias registry (GRAPH_REPAIR)
  3. Retest — only if still failing, adjust reranking (CONTEXT_RULE)
```

### Deterministic Diagnosis Flowchart

```
Wrong response observed
         │
         ▼
Was correct knowledge available in source registry?
    NO  → Knowledge Gap (F04/F05) — check ingestion pipeline
    YES ↓
Was it indexed (vector + graph)?
    NO  → Index completeness failure (F04/R001/R005) — reindex
    YES ↓
Was it retrieved in Top-K?
    NO  → Retrieval failure (F04 vector/graph/lexical miss)
    YES ↓
Was it selected into the final context window?
    NO  → Context Engineering failure (F03/F09) — check reranking, filter rules
    YES ↓
Did the model use it correctly?
    NO  → Generation failure (F07/F10) — check prompt, model version
    YES ↓
Was the citation correct?
    NO  → Citation failure (F06) — check citation pipeline
    YES → Re-examine: may be evaluation false positive (F14)
```

---

## 7. Failure-Attribution Graph

The Failure-Attribution Graph is a **separate Neo4j instance** from the Context Graph. This separation is architectural — see ADR-005 in LLD-00.

### 7.1 Why Separation Is Required

Merging failure data into the production graph creates:
- Retrieval noise (operational diagnostics contaminate answer context)
- Poisoning risk (unverified hypotheses influence user-facing answers)
- Retention conflicts (failure data has different access policies)
- Debugging confusion (serving and diagnostic concerns collapse)

The two graphs share canonical IDs (`source_id`, `scheme_id`, `taxonomy_node_id`) but are physically separate instances with different access controls.

### 7.2 Node Types

```
Interaction          — a single conversation turn
Response             — the generated answer
Claim                — an assertion within a response
Feedback             — raw user feedback (not ground truth)
FailureObservation   — a diagnosed failure (after adjudication)
EvaluationFinding    — output from one evaluator
EvidenceItem         — a specific retrieved chunk or graph path
SourceVersion        — a specific version of a source document
TaxonomyNode         — an AMC taxonomy concept
ControlRule          — a compliance control
Evaluator            — an evaluator with version
SystemComponent      — a pipeline component (model, index, graph, etc.)
ConfigurationVersion — a system configuration snapshot
RootCause            — a confirmed or probable cause
Incident             — a cluster of related failures
RepairCandidate      — a proposed repair
RepairRecipe         — a versioned recipe template
ValidationRun        — a shadow environment test run
DeploymentChange     — an approved and promoted repair
HumanDecision        — a governance or compliance decision
```

### 7.3 Key Relationships

```
Interaction     ──PRODUCED──────────►  Response
Response        ──CONTAINS─────────►  Claim
Claim           ──SUPPORTED_BY─────►  EvidenceItem
Claim           ──SUBJECT_TO───────►  ControlRule
Feedback        ──REPORTS──────────►  FailureObservation
EvaluationFinding ──EVALUATES──────►  Claim
EvaluationFinding ──PRODUCED_BY────►  Evaluator
FailureObservation ──MAPS_TO───────►  FailureFamily (F01–F14)
FailureObservation ──CORRELATED_WITH► Incident
RootCause       ──ATTRIBUTED_TO────►  SystemComponent
RootCause       ──EXPLAINS─────────►  FailureObservation
Incident        ──AGGREGATES───────►  FailureObservation[]
Incident        ──HAS_ROOT_CAUSE───►  RootCause
RepairCandidate ──ADDRESSES────────►  RootCause
RepairCandidate ──USES_RECIPE──────►  RepairRecipe
RepairCandidate ──VALIDATED_BY─────►  ValidationRun
DeploymentChange ──IMPLEMENTS──────►  RepairCandidate
```

### 7.4 Incident Correlation

One of the highest-value features of the failure graph — prevents re-running expensive diagnosis on observations that share a common cause.

```
Example: 120 FailureObservation nodes observed over 90 minutes

Graph query: do they share a common cause signature?
    └── all DEPEND_ON ──► SourceVersion V17
    └── all timestamp AFTER IngestionJob J44 failed

Result:
    Create Incident I-044:
        root_cause = ingestion_failure
        affected_cohort = all queries referencing source V17

    For all future matching observations:
        Attach to I-044 → skip diagnosis
        tokens_avoided += per_observation_diagnosis_cost
```

**Cost impact:**
```
Without incident correlation:
    600 failures × LLM diagnosis = expensive

With incident correlation:
    1 diagnosis (first confirmed root cause)
    599 attachments to Incident I-044 (zero LLM each)
    Total LLM cost ≈ cost of 1 diagnosis
```

### 7.5 Feedback Trust Model

```
Raw Feedback
    ↓
Feedback.REPORTS ──► FailureObservation  ← preserved as-is
    ↓
Adjudication (evidence-backed)
    ↓
Verdict: supported | partially_supported | unsupported | unverifiable
    ↓
(only if supported)
    ↓
RootCause (with confidence state)
```

Raw feedback is never promoted directly to `RootCause`. The adjudication step is mandatory. The graph preserves: who reported, what was reported, which evidence adjudicated it, the verdict, and the confidence.

---

## 8. Failure Taxonomy KPIs

| KPI | Description | Target |
|---|---|---|
| `confirmed_root_cause_rate` | % failures with confirmed (not hypothetical) root cause | > 70% |
| `unknown_root_cause_rate` | % failures where cause is unknown | < 15% |
| `multi_cause_rate` | % failures with multiple contributing causes | tracked |
| `incident_reuse_rate` | % new failures attached to existing incidents | maximise |
| `duplicate_diagnosis_rate` | % diagnoses that should have matched an incident | < 5% |
| `llm_root_cause_dependency` | % root causes requiring LLM | decreasing over time |
| `repair_recurrence_rate` | % repairs where same failure reappears within 30 days | < 5% |
| `false_attribution_rate` | % root causes later found to be misattributed | < 2% |
| `deterministic_conversion_rate` | Novel failures → rules or recipes over time | increasing |

---

## 9. Novel Failure → Rule Conversion

The learning mechanism that makes the system cheaper over time:

```
Novel failure observed
    ↓
Investigation (may require LLM/agent/human)
    ↓
Root cause understood
    ↓
Convert to deterministic rule / repair recipe
    ↓
Future recurrences: E1 detection + R001–R012 recipe
    ↓
LLM cost for this failure class = 0 from this point forward
```

**Deterministic Conversion Rate:**
```
= novel recurring failures converted to rules or recipes
  ──────────────────────────────────────────────────────
  novel recurring failures identified

Target: increase each quarter
```

---

*Previous: [LLD-04 — Evaluation Router](./LLD-04-EVALUATION-ROUTER.md)*  
*Next: [LLD-06 — Self-Healing RAG](./LLD-06-SELF-HEALING-RAG.md)*


---

## 10. Component Architecture Detail

> Added from AMC_COMPONENT_ARCHITECTURE.html — August 2026

### Failure Detection Cost — Practical Reference

The table below gives the precise detection mechanism and LLM token cost for each failure family. This is the engineering decision guide for evaluator selection.

| Family | Fastest Detection Method | LLM Tokens | Key D2 Fields Used | Repair Class Range |
|---|---|---|---|---|
| F01 Explicit intent | Rule: intent_node present in taxonomy, temporal resolved | 0 | D1.detected_intent, D1.extracted_entities | R1–R3 |
| F01 Implicit intent | Semantic classifier (E3) | ~0 generative | D1.intent_confidence, D1.ambiguity_flag | R1–R3 |
| F02 Entity resolution | Rule: canonical_id lookup, ISIN check | 0 | D1.extracted_entities, D2.nodes_traversed | R1–R2 |
| F03 Context state | Rule: context_id in D1, context_token_count | 0 | D1.conversation_context_id, D2.context_truncation | R1–R2 |
| F04 Retrieval miss | Rule: source_registry diff → index count | 0 | D2.missing_expected_source, D2.retrieval_count | R1–R2 |
| F05 Stale source | Rule: source_version in D2 vs source_registry.current | 0 | D2.source_version_mismatch, D2.source_age_days | R1–R2 |
| F06 Citation integrity | Rule: citation_id in D0.citations_shown | 0 | D0.citations_shown, D2.citation_count | R1 |
| F06 Citation entailment | Semantic NLI (E3) | ~0 generative | D2.evidence_selected, D0.response_text | R1–R2 |
| F07 Unsupported generation | Semantic NLI, then LLM if unresolved (E3/E4) | ~0–B2 | D2.evidence_selected, D0.response_text | R3–R4 |
| F08 Numeric mismatch | Rule: structured canonical comparison | 0 | D2.source_provenance, D1.extracted_entities | R1–R2 |
| F09 Completeness | Rule: taxonomy template check; Semantic for implicit | 0 + ~0 gen | D2.taxonomy_matches, D2.context_engineering | R2 |
| F10 Reasoning | Rule: arithmetic/dates; LLM for inference validity | 0 or B2 | D0.response_text, D2.evidence_selected | R2–R4 |
| F11 Tone/Communication | Rule: prohibited phrases; Semantic for nuance | 0 + ~0 gen | D0.response_text | R1–R2 |
| F12 Governance/Compliance | Varies by subtype — see C01–C14 in LLD-07 | 0 to B2 | D3.applicable_control_set_id, D0.disclosures_shown | R3–R5 |
| F13 Infrastructure | Telemetry only (E0) | 0 | D0.tool_failures, service health state | R1 |
| F14 Evaluation integrity | Golden set monitoring (E2) | 0 | EV_GOLDEN_015 output vs baseline | R1–R3 |

### Root-Cause Attribution Pipeline — Sub-Components

| Step | Component | Mechanism | LLM? | Output |
|---|---|---|---|---|
| 1 | Symptom Classifier | Maps user-reported symptom to Axis A–D using D0–D3 fields | No | Initial 4-axis classification |
| 2 | Source Registry Checker | Diffs D2.source_provenance against source_registry.current | No | F04/F05 decision |
| 3 | Entity Alias Resolver | Checks D1.extracted_entities against entity registry canonical IDs | No | F02 decision |
| 4 | Numeric Reconciler | Compares D0.response_text numbers against structured canonical data | No | F08 decision |
| 5 | Citation Integrity Checker | Validates D0.citations_shown against D2.source_provenance | No | F06-integrity decision |
| 6 | Context Engineering Auditor | Checks D2.evidence_rejected for relevant chunks | No | F03/F09 decision |
| 7 | NLI Entailment Checker | Semantic: does selected evidence support the claim? | ~0 generative | F06-entailment, F07 candidate |
| 8 | LLM Hypothesis (E4, bounded) | Only if F07 strongly suspected and NLI inconclusive | B2–B3 | F07 POSSIBLE_CAUSE (not CONFIRMED) |
| 9 | Failure Graph Writer | Writes FailureObservation to Failure-Attribution Graph with all 4 axes | No | FailureObservation node |
| 10 | Incident Correlator | Checks new observation against active incidents | No | Attach to incident or create new |

### Failure-Attribution Graph — Node Creation Sequence

```
Wrong answer detected
    ↓
Create: FailureObservation(failure_family, subtype, confidence, axis_a–d)
    ↓
Link:  FailureObservation -[REPORTS]-> (via Feedback if user-reported)
       FailureObservation -[MAPS_TO]-> FailureFamily(F01–F14)
    ↓
Check: does FailureObservation match an active Incident?
    YES → FailureObservation -[CORRELATED_WITH]-> Incident (skip diagnosis)
    NO  → run root cause attribution steps 1–10 above
    ↓
Create: RootCause(attribution_status, confidence, method)
        Incident -[HAS_ROOT_CAUSE]-> RootCause
    ↓
Assess repair eligibility (R0–R5)
    ↓
Create: RepairCandidate -[ADDRESSES]-> RootCause
        RepairCandidate -[USES_RECIPE]-> RepairRecipe (R001–R012)
```

### Confidence State Transitions

| State | What It Means | Can Trigger Auto-Repair? |
|---|---|---|
| `CONFIRMED` | Deterministic evidence proves the cause | Yes (R1/R2) |
| `HIGH_CONFIDENCE` | Strong structural + statistical evidence | Yes (R2, with shadow validation) |
| `PROBABLE` | Semantic evidence + corroborating signals | No — human review recommended |
| `POSSIBLE` | LLM hypothesis or single signal | No — must be corroborated first |
| `UNKNOWN` | Cannot determine cause | No |
| `CONFLICTING` | Multiple competing explanations, none dominant | No — R4 investigative |

*See [AMC_COMPONENT_ARCHITECTURE.html](../AMC_COMPONENT_ARCHITECTURE.html) — Failure Taxonomy tab for interactive family cards and repair class grid.*
