# LLD-02 — Evidence Capture

**Document:** LLD-02  
**Version:** 1.0  
**Depends on:** LLD-01 (System Overview)  
**Read next:** LLD-03 (Feedback Pipeline)

---

## 1. Purpose and Motivation

The EvidencePack is the foundational object of the entire evaluation system. It is created immediately after every response is generated and freezes the exact information state at that moment: what was retrieved, what was selected for context, which source versions were used, what citations were shown, and which compliance context applied.

**Why this matters:** Evaluation runs hours after response generation. In the interim, source documents are updated, graph edges change, embeddings are refreshed, and policy packs are versioned. Without a frozen record, an evaluator would assess the response against the current system state rather than the state that actually existed when the user received the answer. This makes root-cause attribution unreliable and audit trails meaningless.

**The governing rule:** Every evaluator, compliance checker, root-cause attributor, and repair decision must reference the same frozen EvidencePack. No component re-fetches evidence independently.

---

## 2. Four Components — D0 through D3

The EvidencePack comprises four objects created in sequence, all deterministically, with zero LLM involvement.

### 2.1 D0 — Response Finalization

Captured at the moment the response is assembled, before delivery. Records the identity and operational metadata of the response.

```
D0 ResponseFinalization
│
├── response_id                UUID v4 — immutable primary key for this response
├── interaction_id             UUID — links to the conversation turn
├── conversation_id            UUID — links to the session
├── timestamp                  ISO 8601 with milliseconds
├── response_status            delivered | held | safe_fallback | refused
│
├── model_id                   e.g. claude-3-5-sonnet-20241022
├── model_version              string — provider-supplied version tag
├── generation_config_version  UUID — links to the generation config record
├── prompt_template_version    UUID — links to the prompt template record
│
├── response_text              full UTF-8 response text
├── response_structure         json | markdown | plain
├── citations_shown            [ { citation_id, source_id, source_version, span_start, span_end } ]
├── disclosures_shown          [ { disclosure_id, template_id, template_version, position } ]
├── guardrail_state            passed | triggered | bypassed_with_disclosure
│
├── generation_latency_ms      integer
├── input_tokens               integer
├── output_tokens              integer
├── tool_calls                 [ { tool_id, tool_version, latency_ms, success } ]
├── tool_failures              [ { tool_id, error_code, error_message } ]
├── fallback_used              boolean
├── truncation_flag            boolean — response was cut short
└── response_hash              SHA-256 of response_text — tamper-evidence
```

**Deterministic responsibilities at D0 creation time:**
- Assign immutable `response_id` (UUID v4)
- Compute `response_hash` (SHA-256 of `response_text`)
- Validate output structure matches expected schema for `response_structure` type
- Capture model, config, and prompt versions from the generation context
- Detect output truncation (check generation stop reason)
- Detect presence of required disclosure template IDs in `disclosures_shown`
- Record all tool call outcomes including failures

LLM involvement: **None.**

---

### 2.2 D1 — Interaction Snapshot

Freezes the system state as it existed when the response was generated. This is the "what did the system know and how was it configured" record.

```
D1 InteractionSnapshot
│
├── interaction_id             UUID — matches D0
├── conversation_id            UUID — matches D0
├── snapshot_timestamp         ISO 8601 — same millisecond as D0
│
├── user_query                 raw user input (UTF-8, pre-sanitisation)
├── normalized_query           after stopword removal, entity resolution
├── detected_intent            taxonomy intent node ID (see T4 in taxonomy)
├── intent_confidence          float 0.0–1.0
├── intent_detection_method    rule | classifier | semantic | llm
├── secondary_intents          [ { intent_node_id, confidence } ]
├── extracted_entities         [ { name, canonical_id, entity_type, confidence, method } ]
├── ambiguity_flag             boolean — true if intent is uncertain
│
├── conversation_context_id    UUID — prior turn context object used
├── conversation_turn_count    integer — position in the conversation
│
├── retrieval_configuration    {
│                                mode: hybrid | vector_only | graph_only | bm25_only,
│                                top_k: integer,
│                                rerank_threshold: float,
│                                graph_max_depth: integer,
│                                relationship_types: [ string ]
│                              }
│
├── taxonomy_version           string — AMC taxonomy version active at query time
├── guardrail_version          string — guardrail policy version active at query time
├── prompt_version             UUID — matches D0
├── model_id                   string — matches D0
├── model_version              string — matches D0
│
└── session_metadata           {
                                 user_role: user | employee | qa_reviewer | compliance | sme,
                                 channel: chatbot | api | portal | email,
                                 jurisdiction: IN | US | EU | UK | ...,
                                 product_context: { scheme_id, plan_id, amc_id },
                                 client_segment: retail | hni | institutional
                               }
```

**Privacy note:** `user_query` is considered conversation content and subject to PII redaction after 30 days. Do not store PII in the `extracted_entities` array; store only canonical IDs. The privacy boundary is:

```
Operational Telemetry  ≠  Evaluation Evidence  ≠  Conversation Content  ≠  PII
```

Each type has independent retention, encryption, redaction, and access control rules.

---

### 2.3 D2 — Evidence / Provenance Pack

The full evidence record. This is the object reused by every evaluator without re-fetching.

```
D2 EvidencePack
│
├── VECTOR RETRIEVAL
│   ├── chunk_ids[]            [ string ] — vector store chunk identifiers
│   ├── similarity_scores[]    [ float ] — cosine similarity, same order as chunk_ids
│   ├── ranks[]                [ int ] — pre-rerank position
│   ├── rerank_scores[]        [ float ] — post-rerank score (null if no reranker)
│   ├── document_ids[]         [ string ] — source document identifiers
│   └── document_versions[]    [ string ] — source version at retrieval time
│
├── GRAPH RETRIEVAL
│   ├── nodes_traversed[]      [ { node_id, node_type, label, properties{} } ]
│   ├── edges_traversed[]      [ { edge_id, type, source_node_id, target_node_id, properties{} } ]
│   ├── paths[]                [ { path_id, node_ids[], edge_ids[], path_score } ]
│   ├── relationship_types[]   [ string ] — types of edges traversed
│   └── graph_scores[]         [ float ] — relevance scores per path
│
├── BM25 RETRIEVAL
│   ├── bm25_chunk_ids[]       [ string ]
│   ├── bm25_scores[]          [ float ]
│   └── bm25_document_ids[]    [ string ]
│
├── AMC TAXONOMY MATCHES
│   ├── concepts_matched[]     [ taxonomy_node_id ] — matched domain concepts
│   ├── intent_nodes[]         [ taxonomy_node_id ]
│   ├── product_category       string — taxonomy product category node
│   ├── risk_concepts[]        [ taxonomy_node_id ]
│   └── claim_types[]          [ string ] — e.g. CURRENT_NUMERIC_FACT, PERFORMANCE_CLAIM
│
├── CONTEXT ENGINEERING
│   ├── evidence_considered[]  [ { chunk_id, reason_considered } ]
│   ├── evidence_selected[]    [ { chunk_id, position_in_context, token_count } ]
│   ├── evidence_rejected[]    [ { chunk_id, rejection_reason } ]
│   ├── context_token_count    integer — total tokens passed to LLM
│   └── truncation_state       none | partial | significant
│
└── SOURCE PROVENANCE
    ├── source_ids[]           [ string ] — canonical source document IDs
    ├── authority[]            [ regulatory | official_fund | structured_data |
    │                            approved_internal | secondary ]
    ├── publication_dates[]    [ date ]
    ├── effective_dates[]      [ date ] — when fact became valid
    ├── ingestion_dates[]      [ datetime ]
    ├── source_versions[]      [ string ] — version of source at ingestion
    └── content_hashes[]       [ string ] — SHA-256 per source
```

**Derived deterministic metrics** — computed at D2 creation time, zero LLM tokens:

| Metric | Type | Description |
|---|---|---|
| `retrieval_count` | int | Total chunks retrieved across all mechanisms |
| `citation_count` | int | Citations present in D0 response |
| `citation_coverage` | float | % of response claims with a supporting citation |
| `source_age_days` | int | Age of the oldest source used, in days |
| `highest_source_authority` | enum | Tier of most authoritative source |
| `duplicate_source_ratio` | float | % of retrieved chunks from the same source document |
| `vector_graph_overlap` | float | % of entities found by both vector and graph retrieval |
| `bm25_vector_overlap` | float | % of chunks found by both BM25 and vector search |
| `missing_expected_source` | bool | A known authoritative source was absent from retrieval |
| `context_truncation` | bool | Critical evidence was dropped due to token limit |
| `retrieval_score_min` | float | Minimum similarity score across all retrieved chunks |
| `retrieval_score_mean` | float | Mean similarity score |
| `source_version_mismatch` | bool | Vector index and Context Graph derived from different source versions |

These metrics are pre-computed because they are cheap to calculate at creation time but expensive to recompute during evaluation.

---

### 2.4 D3 — Applicability / Policy Context

Resolves which compliance control universe applies before any evaluation runs. This is a deterministic lookup against jurisdiction + role + product + channel.

```
D3 ApplicabilityContext
│
├── jurisdiction               IN | US | EU | UK | SG | ...
├── regulated_entity_role      investment_adviser | fund_company | broker_dealer |
│                              distributor | platform | other
├── product_type               mutual_fund | etf | portfolio_management |
│                              advisory_service | other
├── communication_channel      chatbot | api | email | portal | print | other
├── customer_segment           retail | hni | institutional | employee |
│                              qa_reviewer | compliance_officer
├── interaction_mode           informational | advisory | transactional | educational
├── advice_flag                boolean — has the interaction crossed into personal advice?
├── execution_flag             boolean — does this relate to a specific transaction?
├── policy_pack_id             string — e.g. INDIA_SEBI_2026_v3
├── policy_pack_version        string
├── policy_pack_effective_from date
│
├── applicable_control_set_id  UUID — resolved ApplicableControlSet record
├── mandatory_controls[]       [ control_id ] — controls that always run
├── hard_block_controls[]      [ control_id ] — controls that block delivery if failed
└── resolution_method          rule | semantic_classifier | ambiguous
```

**Resolution logic:**

```
Step 1: Extract jurisdiction, role, product, channel from session_metadata (D1)
Step 2: Look up in policy pack table — deterministic for all known combinations
Step 3: If interaction_mode is ambiguous (e.g. potentially advisory):
          → Run semantic intent classifier
          → Set advice_flag = true if classifier confidence > threshold
Step 4: Retrieve ApplicableControlSet from policy pack
Step 5: Record resolution_method
```

Semantic evaluation is used only when the **communication itself** must be interpreted — for example, whether an informational query has implicitly crossed into personalised investment advice territory.

---

## 3. Evidence Sufficiency Classification

Before any evaluator runs, the evidence state must be explicitly classified. This prevents evaluators from manufacturing verdicts when the evidence is incomplete.

```
evidence_status values:
  SUFFICIENT            all required evidence present and current
  PARTIAL               some evidence available; gaps exist but may be recoverable
  MISSING               required evidence absent from the EvidencePack
  CONFLICTING           two or more authoritative sources provide different values
  TEMPORALLY_UNCERTAIN  source exists but effective date range is unclear
```

**Decision flow by evidence state:**

```
SUFFICIENT           → proceed to evaluation
PARTIAL              → attempt bounded recovery
                           │
                     ┌─────┴──────┐
                     ▼            ▼
                 recovered    not recoverable
                     │            │
                     ▼            ▼
                 evaluate     UNVERIFIABLE → stop, log, monitor

MISSING              → deterministic recovery possible?
                           YES → recover → evaluate
                           NO  → UNVERIFIABLE → stop

CONFLICTING          → check effective dates and source hierarchy
                     → still unresolved? → human / compliance (STOP-5)
                     → do NOT ask LLM to adjudicate a source conflict

TEMPORALLY_UNCERTAIN → attempt temporal resolution (source version check)
                     → if unresolved → UNVERIFIABLE
```

**Critical rule:** An evaluator must never manufacture certainty to fill an evidence gap. `UNVERIFIABLE` is a valid and correct verdict. Do not invoke an LLM to guess.

---

## 4. Temporal Claim Model

All AMC facts must be modelled with temporal validity. A fact without a validity period is incomplete and cannot be deterministically checked for freshness.

```python
@dataclass
class Claim:
    entity_id:       str       # canonical AMC entity identifier
    product_id:      str       # scheme / plan / option identifier
    attribute:       str       # NAV | TER | benchmark | risk_classification | ...
    value:           Any       # the asserted value (str, float, date, ...)
    valid_from:      date      # when this value became valid
    valid_to:        Optional[date]  # None means currently active
    observed_at:     datetime  # when the system retrieved this value
    source_id:       str       # authoritative source document
    source_version:  str       # version of that source at observation time
    confidence:      float     # 0.0–1.0
```

**Example — TER for Axis Bluechip Fund:**
```yaml
entity_id:      scheme_axis_bluechip_direct_growth
product_id:     axis_bluechip_direct_growth
attribute:      TER
value:          "0.82%"
valid_from:     2026-04-01
valid_to:       null              # currently active
observed_at:    2026-08-19T10:23:44Z
source_id:      sebi_disclosure_2026_q2
source_version: v18
confidence:     1.0
```

This model enables:

1. **Deterministic freshness check** — compare `valid_from` against response timestamp; flag if source is stale
2. **Source version reconciliation** — compare `source_version` against current canonical version in source registry
3. **Historical replay** — reconstruct exactly what the system knew at time T, for any past T
4. **Numeric validation** — compare response value against `value` field deterministically

---

## 5. Evidence Hierarchy for Compliance Decisions

Not all retrieved evidence should be treated equally. For regulated AMC decisions:

```
Tier 1  REGULATION / RULE / FORMAL REGULATORY TEXT
            SEBI Regulations, SEC Rules, FCA Sourcebook, MiFID II

Tier 2  REGULATOR CIRCULAR / GUIDANCE / SUPERVISORY MATERIAL
            SEBI Master Circulars, SEC No-Action Letters, FCA Guidance

Tier 3  OFFICIAL FUND / AMC DISCLOSURE DOCUMENT
            SID, KIM, Annual Report, Fact Sheet

Tier 4  VERIFIED STRUCTURED AMC DATA
            Real-time NAV feed, portfolio data API

Tier 5  APPROVED INTERNAL POLICY / PROCEDURE
            Internal fund house guidelines

Tier 6  OTHER SUPPORTING SOURCE
            Market data, news, third-party research
```

The D2 `authority[]` field records which tier each source belongs to. The jurisdiction policy pack determines how each tier may be used for a specific compliance control. Lower-tier evidence cannot override higher-tier evidence.

---

## 6. EvidencePack Reuse Pattern

All four evaluator types receive the same frozen D2 object. They never re-fetch independently.

```
Frozen EvidencePack (D2)
         │
         ├──→ E1: Deterministic Rule Engine
         │         Input: D2.source_provenance, D2.derived_metrics
         │         Token cost: 0
         │
         ├──→ E3: Semantic / NLI Evaluator
         │         Input: D2.evidence_selected[], D2.bm25_chunk_ids[]
         │         Token cost: ~0 generative
         │
         ├──→ E4: Bounded LLM Judge
         │         Input: EvaluationPacket (subset — see below)
         │         Token cost: controlled (B0–B5 band)
         │
         ├──→ Compliance Control Checker
         │         Input: D3 (ApplicabilityContext), D2.citation_coverage
         │         Token cost: 0 for deterministic controls
         │
         └──→ Root-Cause Attribution Engine
                   Input: full D0–D3
                   Token cost: 0 for deterministic attribution
```

**The LLM EvaluationPacket** — the LLM never receives the full EvidencePack. It receives only the minimum required subset:

```python
@dataclass
class EvaluationPacket:
    evaluation_id:            str
    question:                 str    # the exact evaluation question
    disputed_claims:          list[Claim]
    selected_evidence:        list[dict]  # only directly relevant items
    deterministic_findings:   list[dict]  # what rules already established
    semantic_findings:        list[dict]  # what semantic model established
    evaluation_instruction:   str
    # e.g. "Given claim C and evidence E, classify as:
    #        supported | partially_supported | contradicted | unverifiable"
    token_budget:             int    # hard limit for this call
```

This constraint prevents the LLM from being distracted by irrelevant context, keeps token cost predictable, and makes the evaluation question precise.

---

## 7. Storage and Retention

| Object | Primary Store | Cache | TTL (operational) | TTL (compliance) | Access |
|---|---|---|---|---|---|
| D0 ResponseFinalization | PostgreSQL | — | 90 days | 7 years | System + compliance |
| D1 InteractionSnapshot | PostgreSQL | — | 90 days (PII redacted at 30d) | 7 years | System only |
| D2 EvidencePack | PostgreSQL | Redis (1h) | 90 days | 7 years | Evaluators only |
| D3 ApplicabilityContext | PostgreSQL | — | 90 days | 7 years | System + compliance |

**Redis cache key pattern:** `evidence:{response_id}` — 1-hour TTL, invalidated immediately if any referenced source is updated.

**PostgreSQL table:** `evidence_packs` — JSONB storage with index on `response_id` and `interaction_id`. See LLD-08 for full DDL.

---

## 8. Creation Timing and Sequencing

```python
# Pseudo-code — called immediately after response generation
async def create_evidence_pack(
    response: GeneratedResponse,
    retrieval_result: RetrievalResult,
    session: SessionContext,
) -> EvidencePack:

    # Step 1: D0 — synchronous, ~1ms
    d0 = ResponseFinalization(
        response_id=uuid4(),
        response_hash=sha256(response.text),
        ...
    )

    # Step 2: D1 — synchronous, ~1ms
    d1 = InteractionSnapshot(
        interaction_id=d0.interaction_id,
        user_query=session.raw_query,
        detected_intent=session.intent_node,
        ...
    )

    # Step 3: D2 — synchronous, ~5ms (no I/O, reads from retrieval_result)
    d2 = EvidencePack(
        vector_chunks=retrieval_result.vector_chunks,
        graph_paths=retrieval_result.graph_paths,
        source_provenance=build_provenance(retrieval_result),
        derived_metrics=compute_metrics(retrieval_result),  # zero LLM
        ...
    )

    # Step 4: D3 — synchronous, ~1ms (policy pack lookup from cache)
    d3 = ApplicabilityContext(
        jurisdiction=session.jurisdiction,
        regulated_entity_role=session.entity_role,
        policy_pack_id=policy_registry.resolve(session),
        ...
    )

    # Persist asynchronously (non-blocking)
    asyncio.create_task(persist_evidence_pack(d0, d1, d2, d3))

    # Cache D2 in Redis for fast evaluator access
    asyncio.create_task(redis.setex(
        f"evidence:{d0.response_id}",
        3600,   # 1 hour TTL
        d2.model_dump_json()
    ))

    return EvidencePack(d0=d0, d1=d1, d2=d2, d3=d3)
```

Total synchronous latency contribution: **< 10 ms**. Persistence and caching are non-blocking background tasks.

---

## 9. Integration Points

| Consumer | What it reads | When |
|---|---|---|
| Critical Deterministic Intercept | D2 `derived_metrics`, D3 `hard_block_controls[]` | Immediately, before delivery |
| Feedback Processor | D2 `source_provenance`, D1 `extracted_entities` | During hourly evaluation cycle |
| Adaptive Router | D2 `evidence_status`, D1 `detected_intent`, D3 `applicable_control_set_id` | During routing decision |
| Deterministic Rule Engine | D2 `source_provenance`, `derived_metrics` | E1 evaluation |
| Semantic Evaluator | D2 `evidence_selected[]`, D1 `detected_intent` | E3 evaluation |
| LLM Judge | EvaluationPacket (subset of D2) | E4 evaluation |
| Root-Cause Attributor | Full D0–D3 | Post-adjudication |
| Compliance Checker | D3 `applicable_control_set_id`, D2 `citation_coverage` | Compliance evaluation |

---

*Previous: [LLD-01 — System Overview](./LLD-01-SYSTEM-OVERVIEW.md)*  
*Next: [LLD-03 — Feedback Pipeline](./LLD-03-FEEDBACK-PIPELINE.md)*


---

## 10. Component Architecture Detail

> Added from AMC_COMPONENT_ARCHITECTURE.html — August 2026

### EvidencePack Creator — Sub-Component Breakdown

The EvidencePack Creator is a single synchronous call immediately after LLM synthesis. It produces all four D-objects in sequence with zero LLM involvement and a total latency contribution under 10ms.

| Step | Object | Latency | I/O | Key Outputs |
|---|---|---|---|---|
| 1 | D0 ResponseFinalization | ~1ms | None — reads from in-memory generation context | response_id (UUID v4), response_hash (SHA-256), model/config/prompt versions, citations_shown, disclosures_shown, guardrail_state |
| 2 | D1 InteractionSnapshot | ~1ms | None — reads from session context | user_query, detected_intent (taxonomy node ID), extracted_entities[], retrieval_configuration, session_metadata |
| 3 | D2 EvidencePack | ~5ms | None — reads from retrieval_result in-memory object | All vector/graph/BM25 arrays, 13 pre-computed derived metrics |
| 4 | D3 ApplicabilityContext | ~1ms | Policy pack cache lookup (Redis) | policy_pack_id, applicable_control_set_id, mandatory_controls[], hard_block_controls[] |
| Persist | Background tasks | Async | PostgreSQL INSERT + Redis SETEX | Non-blocking — fires after synchronous call returns |

### D2 Derived Metrics — Complete List

All 13 metrics are computed deterministically at D2 creation time. Zero LLM tokens. These are pre-computed because they are cheap at creation time and expensive to recompute during evaluation.

| Metric | Type | Formula / Source | Used By |
|---|---|---|---|
| `retrieval_count` | int | `len(chunk_ids) + len(bm25_chunk_ids) + len(nodes_traversed)` | E1, E2 |
| `citation_count` | int | `len(D0.citations_shown)` | C07, F06 |
| `citation_coverage` | float | `citations / response_claims` | C07, F06 |
| `source_age_days` | int | `(response_timestamp - oldest effective_date).days` | C02, F05 |
| `highest_source_authority` | enum | `min(authority[])` (lower tier = higher authority) | C02, F05 |
| `duplicate_source_ratio` | float | `duplicate_docs / total_docs` | F04, E2 |
| `vector_graph_overlap` | float | `entities_in_both / total_entities` | E2, F04 |
| `bm25_vector_overlap` | float | `chunks_in_both / total_chunks` | E2, F04 |
| `missing_expected_source` | bool | Check canonical source registry for intent | F04, F05 |
| `context_truncation` | bool | `D0.truncation_flag OR context_token_count > 0.95 * limit` | F03, F09 |
| `retrieval_score_min` | float | `min(similarity_scores[])` | E2 |
| `retrieval_score_mean` | float | `mean(similarity_scores[])` | E2 |
| `source_version_mismatch` | bool | Compare vector index source versions vs graph source versions | F05, R009 |

### Evidence Sufficiency Gate — Decision Matrix

The sufficiency gate runs before any evaluator. It prevents manufacturing verdicts from incomplete evidence.

| Evidence State | Immediate Action | Escalation Path | LLM Involved? |
|---|---|---|---|
| `SUFFICIENT` | Proceed to evaluator selection | — | Depends on evaluator |
| `PARTIAL` | Attempt bounded deterministic recovery | If not recoverable → `UNVERIFIABLE` | No for recovery attempt |
| `MISSING` | Check source registry for deterministic recovery | Not possible → `UNVERIFIABLE` | Never |
| `CONFLICTING` | Check effective dates + source hierarchy | Still unresolved → `STOP-5` (human) | Never for conflict adjudication |
| `TEMPORALLY_UNCERTAIN` | Source version resolution attempt | Not resolved → `UNVERIFIABLE` | Never |

### Integration Points — All Consumers of D2

| Consumer | Fields Read | Phase | LLM? |
|---|---|---|---|
| Critical Deterministic Intercept | `derived_metrics`, D3 `hard_block_controls[]` | Phase 1 | No |
| Feedback Processor | `source_provenance`, D1 `extracted_entities` | Phase 4 | No |
| Adaptive Router (R2 Signal Dimensions) | `evidence_status`, `derived_metrics`, `source_provenance` | Phase 4–5 | No |
| Deterministic Rule Engine (E1) | `source_provenance`, `derived_metrics` | Phase 5 | No |
| Semantic Evaluator (E3) | `evidence_selected[]`, D1 `detected_intent` | Phase 5 | ~0 generative |
| LLM Judge (E4) | EvaluationPacket (subset only — never full D2) | Phase 5 | Controlled B1–B4 |
| Root-Cause Attributor | Full D0–D3 | Phase 5 | No |
| Compliance Checker | D3 `applicable_control_set_id`, `citation_coverage` | Phase 1/5 | No |

*See [AMC_COMPONENT_ARCHITECTURE.html](../AMC_COMPONENT_ARCHITECTURE.html) — Phase 1 tab for interactive component cards.*
