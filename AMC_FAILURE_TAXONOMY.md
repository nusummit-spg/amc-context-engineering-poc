# AMC Failure Taxonomy & Root-Cause Attribution — Design Document

**Version:** 1.0  
**Status:** Design Baseline  
**Scope:** Failure families, four-axis classification, repair eligibility, root-cause strategy, Failure-Attribution Graph

---

## 1. Core Principle: Symptom ≠ Root Cause ≠ Repair

The most important design decision in this document:

> **"Hallucination" is not a root cause. It is a symptom.**

The underlying defect for a "wrong answer" may be any of:
- Stale source (source freshness failure — LLM correctly copied old data)
- Wrong entity resolved (entity resolution failure — perfectly grounded against the wrong entity)
- Missing retrieval (vector/graph miss — correct knowledge exists but was never retrieved)
- Context selection failure (correct chunk retrieved but filtered out before the model saw it)
- Generation error (correct evidence in context but model transcribed or reasoned incorrectly)
- Evaluator regression (the answer is actually correct but the evaluator flagged it)

These have completely different repair actions. Labelling everything "hallucination" wastes LLM tokens on misdiagnosis and creates incorrect repairs.

**The separation that must always hold:**

```
Observable symptom
      ≠
Technical origin
      ≠
Repair action

Example:
User symptom      → "Hallucination"
System diagnosis  → Stale source
Root cause        → Ingestion lag
Repair            → Source refresh + selective re-embedding
LLM tokens for diagnosis → 0
```

---

## 2. Four Classification Axes

Every confirmed or suspected failure records all four dimensions:

### Axis A — What Failed?
Intent · Entity · Context · Retrieval · Source · Citation · Grounding · Accuracy · Completeness · Reasoning · Communication · Governance · Infrastructure · Evaluation

### Axis B — How Was It Detected?
`RULE` · `STATISTICAL` · `SEMANTIC` · `LLM` · `AGENT` · `HUMAN`

### Axis C — Where Did It Originate?
Query Understanding · Taxonomy · Source Ingestion · Vector DB · Context Graph · Retrieval Pipeline · Reranking · Context Engineering · Generation · Guardrail · UI · User Feedback Interpretation

### Axis D — What Should Heal It?
`NO_ACTION` · `RULE_FIX` · `SOURCE_REFRESH` · `REINDEX` · `REEMBED` · `GRAPH_REPAIR` · `TAXONOMY_UPDATE` · `CONTEXT_RULE` · `PROMPT_CHANGE` · `MODEL_CHANGE` · `HUMAN_REVIEW`

**Example classification:**

```
Axis A — What:    F06 Citation — citation does not support claim
Axis B — How:     SEMANTIC (NLI entailment model)
Axis C — Origin:  Context Engineering — wrong chunk selected
Axis D — Heal:    CONTEXT_RULE — update chunk selection/reranking rule
```

---

## 3. Failure Analysis Matrix

| Failure Type | Deterministic | Semantic | LLM | Typical Origin |
|---|---|---|---|---|
| Explicit intent | High | Low | Rare | Query understanding |
| Implicit intent | Low | High | Conditional | Intent classifier |
| Wrong entity | High | Medium | Rare | Entity resolution |
| Missing retrieval | High | None | None | Vector/graph/index |
| Stale source | High | None | None | Ingestion pipeline |
| Broken citation | High | None | None | Citation pipeline |
| Citation support | Low | High | Conditional | Context/generation |
| Numeric error | High | Low | Rare | Generation/calculation |
| Unsupported claim | Low | High | Conditional | Generation |
| Completeness | Medium | High | Conditional | Context/generation |
| Tone | Medium | High | Conditional | Generation |
| Advice boundary | Medium | High | Conditional | Policy/generation |

---

## 4. The 14 Primary Failure Families

### F01 — Intent / Understanding

**Subtypes:**
`wrong_primary_intent` · `missed_secondary_intent` · `multi_intent_not_detected` · `ambiguity_not_detected` · `wrong_taxonomy_mapping` · `temporal_intent_wrong` · `comparison_intent_wrong` · `recommendation_intent_missed` · `informational_vs_advisory_confusion` · `conversation_intent_drift`

**Deterministic examples:**
```
Query: "What is the NAV of Axis Bluechip Fund today?"
Extract:
  ENTITY_TYPE = Scheme
  ENTITY      = Axis Bluechip Fund
  ATTRIBUTE   = NAV
  TEMPORAL    = current
  QUERY_TYPE  = factual_lookup

Rules validate: known scheme? · NAV taxonomy node? · current date intent? · correct data source?
```

**Semantic escalation path:**
```
CLEAR INTENT         → deterministic
AMBIGUOUS / IMPLICIT → classifier / semantic model
MULTI-INTENT / ADVICE-SENSITIVE → semantic + policy evaluation
UNRESOLVED           → bounded LLM
```

**Persist:** `intent_detected · intent_confidence · intent_method · intent_taxonomy_node · secondary_intents[] · ambiguity_flag`

---

### F02 — Entity Resolution

**Subtypes:**
`entity_not_detected` · `wrong_entity` · `entity_collision` · `alias_resolution_failure` · `plan_option_confusion` · `direct_regular_confusion` · `growth_IDCW_confusion` · `stale_entity_mapping`

**Resolution priority:**
1. ISIN / canonical scheme ID
2. AMC master data identifier
3. Alias registry lookup
4. Semantic resolution (only when stable IDs cannot disambiguate)

**Critical distinction:**
> A response can be **perfectly grounded** against the **wrong entity**. This is an entity resolution failure, not hallucination.

---

### F03 — Context / Conversation State

**Subtypes:**
`previous_turn_ignored` · `stale_turn_used` · `wrong_reference` · `context_overflow` · `critical_evidence_truncated` · `irrelevant_context_injected` · `contradictory_context` · `user_constraint_forgotten`

**Deterministic checks:** required_context_id present? · selected_product consistent? · context_limit_reached? · critical_chunk_omitted?

**Semantic checks:** follow-up interpretation, pronoun/reference resolution, whether user correction was respected across turns.

---

### F04 — Retrieval

**Subtypes:**
`no_retrieval` · `wrong_document` · `wrong_entity` · `low_recall` · `low_precision` · `missing_authoritative_source` · `vector_miss` · `lexical_miss` · `graph_miss` · `rank_failure` · `filter_failure` · `metadata_filter_failure` · `query_rewrite_failure`

**Deterministic diagnosis flow:**
```
Expected canonical source exists in registry?
    ↓
Was it indexed?
    ↓
Was it retrieved?
    ↓
Was it in Top-K?
    ↓
Was it removed by reranking/filtering?
```

> Most retrieval diagnosis requires **zero LLM tokens**.

---

### F05 — Source / Freshness

**Subtypes:**
`stale_source` · `expired_source` · `superseded_document` · `wrong_effective_date` · `low_authority_source` · `missing_source` · `source_version_conflict` · `ingestion_lag`

**Critical distinction:**
```
Model correctly copied stale source
    ≠
Generation hallucination

Primary root cause = SOURCE_FRESHNESS_FAILURE
Repair = source refresh + selective re-embedding
LLM diagnosis tokens = 0
```

---

### F06 — Citation / Attribution

**Subtypes:**
`citation_missing` · `citation_broken` · `citation_wrong_document` · `citation_wrong_span` · `citation_does_not_support_claim` · `citation_partial_support` · `citation_stale` · `claim_without_citation` · `citation_overstatement`

**Detection split:**
```
Citation Integrity      → deterministic (citation exists, resolves, points to retrieved source)
Citation Entailment     → semantic NLI (does source actually support the claim?)
Citation Interpretation → bounded LLM only when ambiguous
```

---

### F07 — Grounding / Unsupported Generation

**Subtypes:**
`unsupported_claim` · `fabricated_fact` · `fabricated_entity` · `fabricated_number` · `fabricated_source` · `evidence_overextension` · `unsupported_synthesis` · `contradiction_with_evidence` · `unverifiable_claim`

**Important:** Do not use "hallucination" as the parent label for all wrong answers. Most wrong answers have a more specific, cheaper-to-diagnose cause (F04, F05, F06).

```
Wrong fact ≠ Hallucination

Stale retrieved evidence   → source failure (F05) — deterministic diagnosis
Model invents number       → generation hallucination (F07) — semantic/LLM needed
```

---

### F08 — Factual / Numerical Accuracy

**Subtypes:**
`numeric_mismatch` · `date_mismatch` · `percentage_error` · `currency_error` · `unit_error` · `calculation_error` · `entity_attribute_error` · `comparative_fact_error` · `temporal_fact_error`

**Many financial checks are deterministic:**
```
Response TER = 0.79%
Canonical TER = 0.82%
    → deterministic FAIL, zero LLM tokens
```

---

### F09 — Completeness / Relevance

**Subtypes:**
`omitted_required_fact` · `omitted_risk_information` · `omitted_constraint` · `incomplete_comparison` · `question_part_unanswered` · `excessive_information` · `irrelevant_information`

**Split:**
- Structural completeness → taxonomy templates + rules
- Semantic completeness → semantic model / bounded LLM

**Example — performance comparison template must include:**
scheme category · benchmark · risk classification · expense ratio · exit load · return period basis

---

### F10 — Reasoning / Consistency

**Subtypes:**
`internal_contradiction` · `evidence_contradiction` · `unsupported_inference` · `wrong_comparison` · `causal_leap` · `conclusion_not_supported` · `mathematical_reasoning_error`

**Rules handle:** arithmetic, dates, structured attribute contradictions, ordering errors.  
**Semantic/LLM needed for:** inference validity, unsupported conclusions, causal reasoning.

---

### F11 — Communication / Tone

**Subtypes:**
`inappropriate_tone` · `excessive_jargon` · `verbosity` · `unclear_answer` · `misleading_certainty` · `aggressive_or_persuasive_language` · `poor_structure` · `language_mismatch`

**Deterministic:** requested language, response length, prohibited absolute wording, required formatting, disclosure placement.  
**Semantic:** condescending, overly persuasive, confusing, alarmist, evasive.

---

### F12 — Governance / Compliance / Safety

**Subtypes:**
`advice_boundary` · `suitability` · `prohibited_claim` · `missing_disclosure` · `unfair_or_promotional_language` · `privacy_or_PII` · `recordkeeping` · `jurisdiction_mismatch` · `product_restriction` · `escalation_required`

**Deterministic:** explicit prohibited patterns, policy tables, mandatory disclosure presence, product restrictions, PII rules, jurisdiction flags.  
**Semantic:** implicit recommendation, implied guarantee, nuanced suitability statement, misleading promotional framing.

---

### F13 — System / Infrastructure

**Subtypes:**
`vector_unavailable` · `graph_unavailable` · `partial_index` · `ingestion_failed` · `index_build_in_progress` · `timeout` · `rate_limit` · `tool_failure` · `cache_corruption` · `replica_lag` · `dependency_unavailable`

Distinguishes operational failure from semantic/knowledge failure.  
**Detection: deterministic telemetry only. LLM use = 0.**  
Typical healing: retry · fallback · restore · rebuild · traffic shift.

---

### F14 — Evaluation / Feedback Integrity

**Subtypes:**
`evaluator_false_positive` · `evaluator_false_negative` · `threshold_miscalibration` · `evaluator_version_regression` · `judge_disagreement` · `feedback_abuse` · `feedback_poisoning_attempt` · `duplicate_feedback` · `feedback_misclassification` · `evidence_leakage_to_evaluator` · `evaluation_pipeline_failure`

**Critical example:**
```
Production model remains stable
    ↓
New evaluator version deployed
    ↓
"Hallucination rate" doubles
    ↓
Golden-set behaviour unchanged
    ↓
EVALUATOR REGRESSION (F14)
    ↓
Do NOT modify the RAG because an evaluator is wrong
```

---

## 5. Repair Eligibility Classes — R0 through R5

A confirmed defect is **not** automatically eligible for self-healing:

```
Confirmed Root Cause
    ↓
REPAIR ELIGIBILITY CHECK
    │
    ├── source-provable?
    ├── deterministic?
    ├── reversible?
    ├── bounded blast radius?
    ├── validation available?
    ├── provenance preserved?
    ├── compliance impact understood?
    └── policy permits automatic change?
```

| Class | Meaning | Example | Default Action |
|---|---|---|---|
| **R0** | No repair | Invalid/noisy feedback | Close & monitor |
| **R1** | Auto-safe mechanical | Missing embedding, broken index chunk | Automatic repair + verify |
| **R2** | Auto + shadow | Stale graph edge with authoritative replacement available | Repair in shadow → promote if regression passes |
| **R3** | Approval required | Taxonomy or policy structural change | Governance approval gate |
| **R4** | Investigative | Conflicting authoritative sources | Agent / SME investigation |
| **R5** | Prohibited auto-repair | Ambiguous regulatory interpretation | Human / Compliance only — **never automated** |

---

## 6. Root-Cause Attribution Strategy

**Preferred hierarchy:**

```
1. Deterministic causal evidence               (strongest)
2. Strong structural / provenance evidence
3. Statistical correlation
4. Semantic explanation
5. LLM hypothesis
6. Human adjudication where required           (weakest machine, required for legal ambiguity)
```

An LLM-generated root-cause hypothesis is represented as `POSSIBLE_CAUSE (confidence=X, method=LLM)` — **not** `CONFIRMED_CAUSE` — unless corroborated by stronger evidence.

### Attribution Confidence Model

```
attribution_status =
    CONFIRMED
    HIGH_CONFIDENCE
    PROBABLE
    POSSIBLE
    UNKNOWN
    CONFLICTING
```

Do not force every failure into a single root cause. Multiple contributing factors may exist:

```
Example — multi-cause failure:
outdated product source
    +
weak retrieval ranking
    +
model overstates evidence

PRIMARY_CAUSE   = SOURCE_FRESHNESS
CONTRIBUTOR_1   = RETRIEVAL_RANKING
CONTRIBUTOR_2   = GENERATION_OVEREXTENSION

Repair order: fix source first → retest → only then decide if retrieval/model changes are needed
```

### Deterministic Root-Cause Diagnosis Flow

```
Wrong response observed
    │
    ▼
Was correct knowledge available in source plane?
    NO  → Knowledge Gap (F04/F05) — check ingestion
    YES ↓
Was it retrieved?
    NO  → Retrieval Failure (F04) — check vector/graph/index
    YES ↓
Was it selected into context?
    NO  → Context Engineering Failure (F03/F09) — check reranking/filtering
    YES ↓
Did the model use it correctly?
    NO  → Generation / Reasoning Failure (F07/F10) — check prompt/model
    YES ↓
Was citation incorrect?
    YES → Citation Failure (F06) — check citation pipeline
```

---

## 7. Failure-Attribution Graph

### 7.1 Why It Must Be Separate from the Context Graph

If failure/evaluator data is inserted directly into the production context graph:
- Operational noise leaks into retrieval results
- User responses may retrieve internal diagnostic conclusions
- Unverified failure hypotheses contaminate domain knowledge
- Feedback poisoning could affect answer generation
- Retention/access-control requirements differ (compliance vs serving)

**The rule:**
> Failure intelligence informs routing and healing. It never becomes answer evidence by default.

They share **canonical IDs** (`source_id`, `scheme_id`, `taxonomy_node_id`) but have separate graphs, access policies, and serving behaviour.

### 7.2 Node Types

```
Interaction · Response · Claim · Feedback · FailureObservation
EvaluationFinding · EvidenceItem · SourceVersion · TaxonomyNode
ControlRule · Evaluator · SystemComponent · ConfigurationVersion
RootCause · Incident · RepairCandidate · RepairRecipe
ValidationRun · DeploymentChange · HumanDecision
```

### 7.3 Key Relationships

```
Interaction     ──PRODUCED──►      Response
Response        ──CONTAINS──►      Claim
Claim           ──SUPPORTED_BY──►  EvidenceItem
Claim           ──SUBJECT_TO──►    ControlRule
Feedback        ──REPORTS──►       FailureObservation
EvaluationFinding ──EVALUATES──►   Claim
EvaluationFinding ──PRODUCED_BY──► Evaluator
FailureObservation ──MAPS_TO──►    FailureFamily
FailureObservation ──CORRELATED_WITH──► Incident
RootCause       ──ATTRIBUTED_TO──► SystemComponent
RootCause       ──EXPLAINS──►      FailureObservation
Incident        ──AGGREGATES──►    FailureObservation
Incident        ──AFFECTS──►       SourceVersion
RepairCandidate ──ADDRESSES──►     RootCause
RepairCandidate ──VALIDATED_BY──►  ValidationRun
DeploymentChange ──IMPLEMENTS──►   RepairCandidate
```

### 7.4 Incident Correlation

The graph enables powerful incident correlation:

```
120 FailureObservations
    └── all DEPEND_ON → SourceVersion V17
    └── all occurred after IngestionJob J44 failed
            ↓
    Create: Incident I-044
    root_cause = ingestion_failure
    affected_cohort = all queries using source V17
            ↓
    Future matching observations → attach to I-044
    Skip repeated LLM investigation for all subsequent matches
```

**Without incident correlation:**
```
600 failures × repeated semantic/LLM diagnosis = unnecessary cost
```

**With incident correlation:**
```
First failure → root cause confirmed → Incident I-123 active
New matching events → attach to I-123 → skip diagnosis
Savings tracked: diagnostic_calls_avoided · tokens_avoided · time_to_containment
```

### 7.5 Feedback Trust Model

```
Raw human feedback
    ↓
Feedback.REPORTS → FailureObservation
    ↓ (adjudication required)
    ↓ (NOT directly)
RootCause
```

The graph preserves: who reported · what was reported · which response span · which evidence adjudicated it · whether it was supported/unsupported/unverifiable.

This prevents feedback poisoning from becoming domain truth.

### 7.6 Correlation Must Not Be Treated as Causation

The graph distinguishes:
- `CORRELATED_WITH` — statistical co-occurrence
- `POSSIBLE_CAUSE` — hypothesis, not confirmed
- `CONFIRMED_CAUSE` — evidence-backed
- `CONTRIBUTING_FACTOR` — partial contributor

```
model_version = V2 AND hallucination_rate increased
    ≠
V2 CAUSED hallucinations

Causal confirmation requires:
  regression replay + controlled comparison + evidence tracing + rollback observation
```

---

## 8. Failure Taxonomy KPIs

| KPI | Description |
|---|---|
| `confirmed_root_cause_rate` | % failures with confirmed (not hypothetical) root cause |
| `unknown_root_cause_rate` | % failures where root cause remains unknown |
| `multi_cause_rate` | % failures with multiple contributing causes |
| `incident_reuse_rate` | % new failures attached to existing incidents |
| `duplicate_diagnosis_rate` | % repeat diagnoses that should have matched an incident |
| `llm_root_cause_dependency` | % root causes requiring LLM (target: decrease over time) |
| `repair_recurrence_rate` | % repairs where same failure reappears within 30 days |
| `false_attribution_rate` | % root causes later found to be misattributed |
| `failure_family_distribution` | Volume by F01–F14 over time |

---

## 9. Novel Failure → Rule Conversion

The intended learning mechanism:

```
Novel failure
    ↓
Investigation (may require LLM/agent/human)
    ↓
Root cause understood
    ↓
Convert into deterministic rule / repair recipe
    ↓
Future recurrences handled cheaply (E0/E1, zero LLM tokens)
```

**Deterministic Conversion Rate:**
```
= novel recurring failure patterns converted to rules or repair recipes
  ─────────────────────────────────────────────────────────────────────
  novel recurring failure patterns identified
```

The architecture should become **less LLM-dependent** as this rate improves.

---

*This document is part of the AMC Unified Feedback, Evaluation & Self-Healing Architecture. See also: `AMC_EVIDENCE_PACK.md`, `AMC_EVALUATION_ROUTER.md`, `AMC_SELF_HEALING_RAG.md`, `AMC_COMPLIANCE_CONTROL_PLANE.md`.*
