# AMC Evidence Pack — Design Document

**Version:** 1.0  
**Status:** Design Baseline  
**Scope:** Response finalization, interaction snapshot, evidence capture, applicability context

---

## 1. Purpose

The EvidencePack is the **central reusable evidence object** created immediately after every AMC chatbot response is generated. It freezes the exact information state — what was retrieved, what was selected, what was cited, which source versions were used — at the moment of response generation.

Every later evaluation, compliance check, root-cause attribution, and repair decision references this frozen object. It is never re-fetched or reconstructed from current system state.

**The governing principle:**

> A later change to NAV, TER, benchmark, source document, policy, model, or taxonomy must **not** retroactively change the evidence used to judge an older response.

---

## 2. Why Freezing Matters

Without a frozen EvidencePack, the following problems arise:

| Problem | Consequence |
|---|---|
| Source updated between response and evaluation | Evaluator judges against new source, not the source the model actually used |
| Graph edge changed | Root cause misattributed — system looks healthy when evaluated, but was broken at response time |
| Model or prompt version changed | Regression analysis is unreliable |
| Chunk re-embedded | Vector similarity scores differ, retrieval diagnosis is impossible |
| Taxonomy updated | Intent classification appears correct in retrospect even if it was wrong |

**All evaluators reuse the same EvidencePack.** Benefits:
- Lower cost — no independent re-retrieval per evaluator
- Better reproducibility — identical evidence basis
- Full auditability — single frozen record per response
- Fewer conflicting evaluator results

---

## 3. Four Components — D0 through D3

### 3.1 D0 — Response Finalization

Captured immediately when the response is generated. Purely operational — no LLM required.

```
D0 ResponseFinalization
│
├── response_id                  UUID — immutable primary key
├── interaction_id               UUID — links to conversation
├── conversation_id              UUID
├── timestamp                    ISO 8601
├── response_status              delivered | held | safe_fallback | refused
│
├── model_id                     e.g. claude-3-5-sonnet-20241022
├── model_version
├── generation_config_version
├── prompt_template_version
│
├── response_text                full response text
├── response_structure           json | markdown | plain
├── citations_shown              [ {citation_id, source_id, span} ]
├── disclosures_shown            [ {disclosure_id, template_version} ]
├── guardrail_state              passed | triggered | bypassed_with_disclosure
│
├── generation_latency_ms
├── input_tokens
├── output_tokens
├── tool_calls                   [ {tool_id, latency_ms, success} ]
├── tool_failures                [ {tool_id, error_code} ]
├── fallback_used                boolean
├── truncation_flag              boolean
└── response_hash                SHA-256 of response_text
```

**Deterministic responsibilities at D0:**
- Generate immutable `response_id`
- Hash the response text
- Validate output structure matches expected schema
- Capture model/config/prompt versions
- Detect truncation
- Detect presence of required disclosure templates
- Record all tool failures

LLM/Agent involvement: **None.**

---

### 3.2 D1 — Interaction Snapshot

Freezes the system state as it existed when the response was generated.

```
D1 InteractionSnapshot
│
├── interaction_id
├── conversation_id
├── timestamp
│
├── user_query                   raw user input
├── normalized_query             after entity resolution + intent extraction
├── detected_intent              taxonomy intent node ID
├── intent_confidence            0.0 – 1.0
├── secondary_intents            [ intent_node_id ]
├── extracted_entities           [ {name, type, canonical_id, confidence} ]
├── ambiguity_flag               boolean
│
├── conversation_context_id      prior turn context used
├── retrieval_configuration      {mode, top_k, rerank_threshold}
├── graph_configuration          {max_depth, relationship_types}
├── taxonomy_version
├── guardrail_version
│
├── prompt_version
├── model_id
├── model_version
└── session_metadata             {user_role, channel, jurisdiction, product_context}
```

**Key principle:** Evaluation should reconstruct the information state at response time whenever possible. The snapshot is immutable once created.

**Privacy considerations — keep these strictly separate:**

```
Operational Telemetry     ≠    Evaluation Evidence
      ≠
Conversation Content      ≠    PII
```

Retention, encryption, redaction, and access control are governed independently for each type.

---

### 3.3 D2 — Evidence / Provenance Pack

The full evidence record. This is the object reused by all evaluators.

```
D2 EvidencePack
│
├── VECTOR RETRIEVAL
│   ├── chunk_ids[]
│   ├── similarity_scores[]
│   ├── ranks[]
│   ├── document_ids[]
│   └── document_versions[]
│
├── CONTEXT GRAPH
│   ├── nodes_traversed[]        [ {node_id, node_type, properties} ]
│   ├── edges_traversed[]        [ {edge_id, type, source, target} ]
│   ├── paths[]                  [ {path_id, nodes[], edges[]} ]
│   ├── relationship_types[]
│   └── graph_scores[]
│
├── AMC TAXONOMY
│   ├── concepts_matched[]       taxonomy node IDs
│   ├── intent_nodes[]
│   ├── product_category
│   └── risk_concepts[]
│
├── CONTEXT ENGINEERING
│   ├── evidence_considered[]    all candidate chunks/nodes
│   ├── evidence_selected[]      what was passed to the model
│   ├── evidence_rejected[]      what was filtered out (+ reason)
│   └── truncation_state         none | partial | significant
│
└── SOURCE PROVENANCE
    ├── source_id[]
    ├── authority[]              regulatory | official_fund | structured_data | secondary
    ├── publication_date[]
    ├── effective_date[]
    ├── ingestion_date[]
    ├── source_version[]
    └── content_hash[]
```

**Derived deterministic metrics** (computed at capture time, zero LLM tokens):

| Metric | Description |
|---|---|
| `retrieval_count` | Total chunks retrieved |
| `citation_count` | Citations present in response |
| `citation_coverage` | % of claims with supporting citation |
| `source_age_days` | Age of oldest source used |
| `highest_source_authority` | Tier of most authoritative source used |
| `duplicate_source_ratio` | Fraction of retrieved chunks from same source |
| `vector_graph_overlap` | % of entities found by both vector and graph |
| `missing_expected_source` | Boolean — known authoritative source absent |
| `context_truncation` | Boolean — critical evidence dropped due to token limit |
| `retrieval_score_distribution` | Min/max/mean similarity scores |
| `source_version_mismatch` | Boolean — vector and graph derived from different source versions |

---

### 3.4 D3 — Applicability / Policy Context

Resolves which control universe applies before any compliance evaluation runs.

```
D3 ApplicabilityContext
│
├── jurisdiction                 IN | US | EU | UK | ...
├── regulated_entity_role        investment_adviser | fund_company | broker_dealer | distributor | ...
├── product_type                 mutual_fund | etf | portfolio_service | ...
├── communication_channel        chatbot | api | email | portal | ...
├── customer_segment             retail | hni | institutional | employee | qa_reviewer | ...
├── interaction_mode             informational | advisory | transactional | educational
├── advice_flag                  boolean — has interaction crossed into personal advice?
├── execution_flag               boolean — does this relate to a transaction?
├── policy_pack_version          e.g. INDIA_SEBI_2026_v3
│
└── applicable_control_set_id    resolved ApplicableControlSet reference
```

**Resolution strategy:**

```
Known structured facts → rules/lookup tables → deterministic resolution
                                │
                     ┌──────────┴──────────┐
                     │                     │
             Context is clear         Communication itself
             (role/product known)     is ambiguous
                     │                     │
            Applicability resolved    Semantic classifier
            deterministically         (e.g. has this shifted
                                       from information to advice?)
```

Use semantic evaluation only when the **communication itself** must be interpreted — e.g. whether wording has crossed from factual information into a recommendation, or whether a neutral comparison is actually promotional.

---

## 4. Evidence Sufficiency States

Before any adjudication, the evidence state must be explicitly classified:

```
evidence_status =
    SUFFICIENT            — all required evidence available and current
    PARTIAL               — some evidence available, gaps exist
    MISSING               — required evidence absent
    CONFLICTING           — two or more authoritative sources disagree
    TEMPORALLY_UNCERTAIN  — source exists but temporal validity unclear
```

**Routing by evidence state:**

```
EvidencePack
     │
     ▼
Evidence Sufficiency Check
     │
     ├── SUFFICIENT ──────────────────────────────→ proceed to evaluation
     │
     ├── PARTIAL ────→ attempt bounded recovery
     │                       │
     │               ┌───────┴───────┐
     │               ▼               ▼
     │           recovered      not recoverable
     │               │               │
     │               ▼               ▼
     │          re-evaluate      UNVERIFIABLE
     │
     ├── MISSING ────→ deterministic recovery available?
     │                       │           │
     │                      YES          NO
     │                       │           │
     │                  recover      UNVERIFIABLE → STOP
     │
     ├── CONFLICTING ──→ conflict workflow → do not auto-adjudicate
     │                   check effective dates / hierarchy / supersession
     │                   still conflict? → human/compliance
     │
     └── TEMPORALLY_UNCERTAIN ──→ temporal/source-version workflow
```

> **The evaluator must never manufacture certainty to fill an evidence gap.**  
> An `UNVERIFIABLE` state is a valid and correct result. Do not ask an LLM to invent a verdict.

---

## 5. Temporal Claim Model

AMC facts must be modelled with temporal validity. A claim without a validity period is incomplete.

```
Claim
│
├── entity_id              canonical AMC entity identifier
├── product_id             scheme / plan / option identifier
├── attribute              e.g. NAV | TER | benchmark | risk_classification
├── value                  the asserted value
├── valid_from             date/time from which value is valid
├── valid_to               date/time until which value is valid (null = current)
├── observed_at            when the system retrieved this value
├── source_id              authoritative source
└── source_version         version of source at observation time
```

**Example — TER claim:**

```yaml
entity_id:      scheme_axis_bluechip_direct_growth
attribute:      TER
value:          0.82%
valid_from:     2026-04-01
valid_to:       null          # currently active
observed_at:    2026-08-19T10:23:44Z
source_id:      sebi_disclosure_2026_q2
source_version: v18
```

This is substantially more defensible than storing `TER = 0.82%` without temporal context. It enables:
- Deterministic freshness checks (`valid_from` vs response timestamp)
- Source version reconciliation (embedded version vs current canonical version)
- Historical replay (what did the system know at time T?)

---

## 6. Evidence Hierarchy for AMC Compliance Decisions

Not all retrieved evidence should be treated equally. For regulated AMC decisions:

```
Tier 1 — REGULATION / RULE / FORMAL REGULATORY TEXT
    ↓
Tier 2 — REGULATOR CIRCULAR / GUIDANCE / SUPERVISORY MATERIAL
    ↓
Tier 3 — OFFICIAL FUND / AMC DISCLOSURE DOCUMENT
    ↓
Tier 4 — VERIFIED STRUCTURED AMC DATA
    ↓
Tier 5 — APPROVED INTERNAL POLICY / PROCEDURE
    ↓
Tier 6 — OTHER SUPPORTING SOURCE
```

The jurisdiction policy pack determines how each tier may be used for a specific control. The evidence taxonomy describes source type; the policy pack decides how that source may be used.

---

## 7. EvidencePack Reuse Across Evaluators

All evaluators in the evaluation pipeline reference the same frozen D2 EvidencePack:

```
Frozen EvidencePack (D2)
         │
         ├──→ Deterministic Rule Engine    (zero LLM tokens)
         ├──→ Semantic / NLI Evaluator     (~0 generative tokens)
         ├──→ Bounded LLM Judge            (minimal EvaluationPacket only)
         ├──→ Compliance Control Checker   (policy pack lookups)
         └──→ Root-Cause Attribution       (failure graph writes)
```

The LLM judge receives a **minimal EvaluationPacket** — not the full EvidencePack:

```
EvaluationPacket (subset for LLM)
│
├── question            the exact evaluation question
├── disputed_claims[]   specific claims under dispute
├── selected_evidence[] only the directly relevant evidence items
├── deterministic_findings[]  what rules already established
├── semantic_findings[]       what semantic model already established
└── evaluation_question       "Given claim C and evidence E, classify as: 
                               supported | partially_supported | contradicted | unverifiable"
```

> Never send the full conversation or full EvidencePack to the LLM evaluator. Use the minimal EvaluationPacket.

---

## 8. Storage and Retention

| Object | Storage | TTL | Access Control |
|---|---|---|---|
| D0 ResponseFinalization | PostgreSQL | 90 days operational, 7 years audit | System + compliance |
| D1 InteractionSnapshot | PostgreSQL | 90 days, PII redacted after 30 | System only |
| D2 EvidencePack | PostgreSQL + Redis cache | PostgreSQL 90 days; Redis 1h | Evaluators only |
| D3 ApplicabilityContext | PostgreSQL | 90 days | System + compliance |
| Evidence cache (Redis) | Redis | 1 hour TTL, invalidated on source update | Evaluators only |

---

## 9. Integration with the Feedback Path

```
User Query
    │
    ▼
Response Generated
    │
    ▼
D0 + D1 + D2 + D3 created and frozen  ← all deterministic, no LLM
    │
    ▼
Critical Deterministic Intercept (uses D2 + D3)
    │
    ▼
Deliver Response (response_id returned to UI)
    │
    ▼
User provides feedback → POST /api/feedback { response_id, rating, comment }
    │
    ▼
Feedback linked to EvidencePack via response_id
    │
    ▼
Hourly evaluation cycle retrieves frozen EvidencePack for each pending feedback item
    │
    ▼
All evaluators use the same frozen D2 — never re-fetch
```

---

## 10. Key Design Decisions

| Decision | Rationale |
|---|---|
| Freeze evidence at response time, not evaluation time | Prevents retroactive state changes from contaminating evaluation |
| All evaluators share one EvidencePack | Lower cost, better reproducibility, no conflicting evidence bases |
| LLM receives minimal EvaluationPacket only | Reduces token cost, prevents the model from being distracted by irrelevant context |
| Evidence sufficiency is an explicit state | Forces the system to declare uncertainty rather than manufacture a verdict |
| Temporal claim model for all AMC facts | Enables deterministic freshness checks — the most common source of wrong answers |
| Source provenance stored per-chunk | Enables precise root-cause attribution (which source version caused the error) |

---

*This document is part of the AMC Unified Feedback, Evaluation & Self-Healing Architecture. See also: `AMC_EVALUATION_ROUTER.md`, `AMC_FAILURE_TAXONOMY.md`, `AMC_SELF_HEALING_RAG.md`, `AMC_COMPLIANCE_CONTROL_PLANE.md`.*
