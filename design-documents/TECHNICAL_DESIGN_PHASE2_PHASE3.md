# Technical Design — Phase 2 & Phase 3 Enhancements
## AMC Context Engineering PoC — Feedback, Evaluation & Self-Correction Architecture

**Document status:** Design only — no code to be added until architect approval  
**Reference flows:** AMC_REALTIME_SCENARIOS_LLD.html · AMC_FEEDBACK_LOOP_ARCHITECTURE_v2.html  
**Prepared against:** Full repo inventory (August 2026)

---

## 1. Executive Context

### What Phase 1 Already Provides

Phase 1 is fully operational in `streamlit_app/` and `backend/app/`. It delivers:

| Capability | Status | Key files |
|---|---|---|
| Hybrid GraphRAG query pipeline | ✅ Complete | `engine/retrieval.py`, `engine/context_engineering.py` |
| Neo4j knowledge graph | ✅ Complete | `engine/graph_store.py`, `graph/client.py` |
| FAISS vector store (dual instance) | ✅ Complete | `engine/faiss_store.py`, `vector/client.py` |
| Two-layer NER (rule + GLiNER) | ✅ Complete | `engine/ner_pipeline.py` |
| Intent-driven retrieval routing | ✅ Complete | `engine/query_classifier.py`, `retrieval/orchestrator.py` |
| Text-to-Cypher aggregation | ✅ Complete | `engine/text_to_cypher.py` |
| Streamlit UI with RBAC | ✅ Complete | `streamlit_app/app.py`, `rbac.py` |
| Compliance guardrails | ✅ Complete | `streamlit_app/compliance_guardrails.py` |
| Feedback API routes (4 endpoints) | ⚠️ Code written, not wired | `api/routes/feedback.py` |
| FeedbackCollector class | ⚠️ Code written, blocked | `engine/feedback_collector.py` |
| FeedbackProcessor class | ⚠️ Code written, blocked | `engine/feedback_processor.py` |
| GraphCorrectionEngine class | ⚠️ Code written, blocked | `engine/graph_corrector.py` |
| CacheManager class | ⚠️ Code written, blocked | `engine/cache_manager.py` |
| EvaluationOrchestrator class | ⚠️ Code written, blocked | `tasks/evaluation_orchestrator.py` |

### What Phase 1 Is Missing (the critical gap)

All feedback/evaluation code is written but blocked by five missing pieces:

1. `app/schemas/feedback.py` — Pydantic models referenced by every feedback module
2. `app/engine/postgres_client.py` — PostgreSQLFeedbackClient referenced by all 4 feedback modules
3. `app/engine/batch_evaluation.py` — BatchEvaluationEngine (complete gap — not written)
4. PostgreSQL schema + migrations — tables do not exist
5. Wiring in `app/api/deps.py` + startup in `app/main.py`

---

## 2. Scope of This Design

This document defines the technical design for:

**Phase 2 — Feedback Intelligence & Evaluation Pipeline**
The Active path (user provides explicit feedback) and the Passive path (system captures metrics automatically). Connects all the already-written modules into a working pipeline.

**Phase 3 — Self-Correcting Knowledge Graph & Governed Deployment**
The Detection → Evaluation → Resolution 3-stage KG correction pipeline, GNN structural plausibility scoring, the Correction Patch Layer, and the governed weekly deployment cycle.

Both phases map directly to the flows documented in:
- `AMC_REALTIME_SCENARIOS_LLD.html` — Active (user feedback) and Passive (auto-metrics) scenarios
- `AMC_FEEDBACK_LOOP_ARCHITECTURE_v2.html` — the full E2E Mermaid diagram

---

## 3. Phase 2 — Feedback Intelligence & Evaluation Pipeline

### 3.1 Overview

Phase 2 implements two parallel signal paths that both feed the same Unified Evaluation Record:

- **Active path** — user submits explicit feedback (thumbs-down, correction text, entity name). Maps to the HITL path in the architecture diagram.
- **Passive path** — system captures metrics on every response automatically, regardless of user action. Maps to the Automatic Evaluation Trigger path.

Both paths converge at the Unified Evaluation Record → Failure Diagnosis → Severity Scoring before the KG correction decision.

---

### 3.2 Component: `app/schemas/feedback.py` (New)

**Purpose:** Pydantic models that define the contract for all feedback data flowing through the system. Currently missing — blocks every downstream module from even importing.

**Design:**

`RatingType` enum: `positive` | `negative` | `neutral`

`FeedbackType` enum: `entity_incorrect` | `relationship_missing` | `information_outdated` | `hallucination` | `missing_context` | `citation_wrong` | `tone` | `compliance_concern` | `other`

`FeedbackRequest` model fields:
- `response_id: str` — links to the original query response (validated against ResponseMetadataCache)
- `session_id: str` — user session identifier
- `user_id: Optional[str]` — nullable for anonymous feedback
- `rating: RatingType`
- `feedback_type: FeedbackType`
- `entity_name: Optional[str]` — which entity the user is correcting
- `entity_type: Optional[str]` — taxonomy label of that entity
- `notes: Optional[str]` — free-text from user (max 2000 chars)
- `corrections: Optional[dict]` — proposed_entity, proposed_relationship fields
- `device_type: Optional[str]`
- `timestamp: Optional[datetime]`

`FeedbackResponse` model fields:
- `feedback_id: str`
- `status: str` (recorded | invalid | duplicate)
- `evaluation_status: str` (pending | evaluating | evaluated | applied | rejected)
- `recorded_at: datetime`
- `quality_score: float` (0.0–1.0 — from pre-classification)

`DissatisfactionSignal` model (new — for the passive follow-up path):
- `session_id: str`
- `turn_index: int`
- `query: str` (the follow-up query that reads as dissatisfaction)
- `original_response_id: str`
- `similarity_to_prior: float` (embedding cosine — confirms same-referent)
- `frustration_score: float` (from intent classifier)
- `converted_to_feedback: bool`

`EvaluationRecord` model (the unified schema):
- `interaction_id: str`
- `response_id: str`
- `entry_route: str` (hitl | automatic | dissatisfaction_converted)
- `feedback_ref: Optional[str]` (feedback_id if HITL)
- `raw_feedback: Optional[dict]`
- `categories: Optional[list[str]]`
- `evidence_snapshot_ref: str` (FK to interaction evidence record)
- `deterministic_results: list[dict]` (by rule category)
- `gnn_plausibility_score: Optional[float]`
- `semantic_results: Optional[dict]`
- `llm_evaluation: Optional[dict]`
- `adjudication_verdict: str` (valid | partially_valid | invalid | subjective | insufficient_evidence)
- `adjudication_confidence: float`
- `root_cause: Optional[str]`
- `severity: Optional[str]`
- `improvement_candidate_ref: Optional[str]`
- `lifecycle_status: str` (open | diagnosing | resolved | monitoring)

**Design decision:** All enums are string-backed so they serialize cleanly to/from PostgreSQL VARCHAR columns without needing a PG ENUM type.

---

### 3.3 Component: `app/engine/postgres_client.py` (New)

**Purpose:** The single PostgreSQL client used by all feedback/evaluation modules. Currently missing — the most critical gap in the entire pipeline.

**Design:**

Class: `PostgreSQLFeedbackClient`

Initialization:
- Accepts a connection string (from `Settings.postgres_dsn`)
- Uses `asyncpg` connection pool (min=2, max=20 connections)
- Pool is created lazily on first use; the class is safe to construct before the pool is open

Key method signatures (design only — no implementation):

`store_feedback(feedback_id, response_id, session_id, user_id, query, response_text, rating, feedback_type, entity_name, entity_type, notes, corrections, device_type, timestamp, classifications) → str`
- Writes one row to `feedback_records`
- Writes one row to `feedback_classifications` (linked by feedback_id)
- Returns the feedback_id on success
- Raises `DuplicateFeedbackError` if (session_id + response_id) already exists within 5 minutes

`fetch_pending_feedback(limit, hours_back) → list[dict]`
- SELECT from `feedback_records` where `evaluation_status = 'pending'` and `created_at >= NOW() - hours_back * interval '1 hour'`
- Joins with `feedback_classifications` for quality_score
- Ordered by quality_score DESC (highest-value items first)
- Returns at most `limit` rows

`update_evaluation_status(feedback_ids: list[str], status: str) → int`
- Batch UPDATE `feedback_records` SET evaluation_status = status WHERE id = ANY($1)
- Returns count of rows updated

`store_evaluation_record(record: EvaluationRecord) → str`
- Writes to `evaluation_records` table
- Returns evaluation_record_id

`store_recommendation(recommendation: dict) → str`
- Writes to `correction_recommendations` table
- Returns recommendation_id

`fetch_recommendations(confidence_threshold: float, status: str) → list[dict]`
- SELECT from `correction_recommendations` WHERE confidence_score >= threshold AND status = 'pending'
- Used by GraphCorrectionEngine

`update_recommendation_status(recommendation_id: str, status: str, applied_at: Optional[datetime], applied_by: Optional[str]) → bool`

`record_audit_entry(correction_id, action, cypher_executed, entities_affected, before_state, after_state, operator) → str`
- Writes to `correction_execution_history`

`get_daily_stats(date: date) → dict`
- Returns aggregated metrics for the feedback_metrics table

`archive_old_feedback(retention_days: int) → int`
- Deletes rows from `feedback_records` where `created_at < NOW() - retention_days * interval '1 day'`
- Preserves `correction_execution_history` rows regardless (they use a separate 365-day retention)

**Design decision:** All methods are `async def` using asyncpg directly (not SQLAlchemy) to keep dependencies minimal and avoid ORM overhead in a hot path. The client is stateless and can be pooled freely.

---

### 3.4 Component: PostgreSQL Schema (New)

**Purpose:** The persistent store for the feedback buffer, evaluation records, recommendations, and audit trail.

**Table: `feedback_records`**
```
id                  UUID PRIMARY KEY
response_id         UUID NOT NULL
session_id          UUID NOT NULL
user_id             VARCHAR(255)
query               TEXT NOT NULL
response_text       TEXT NOT NULL
rating              VARCHAR(20)
feedback_type       VARCHAR(50)
entity_name         VARCHAR(255)
entity_type         VARCHAR(50)
notes               TEXT
corrections         JSONB
device_type         VARCHAR(50)
evaluation_status   VARCHAR(20) DEFAULT 'pending'
created_at          TIMESTAMP DEFAULT NOW()
INDEXES: (evaluation_status, created_at), (response_id), (session_id)
```

**Table: `feedback_classifications`**
```
id                          UUID PRIMARY KEY
feedback_id                 UUID REFERENCES feedback_records(id)
extracted_entities          JSONB
sentiment                   VARCHAR(20)
intent_score                FLOAT
feedback_quality_score      FLOAT
should_evaluate             BOOLEAN
classification_timestamp    TIMESTAMP
```

**Table: `evaluation_records`**
```
id                          UUID PRIMARY KEY
response_id                 UUID NOT NULL
feedback_id                 UUID REFERENCES feedback_records(id)
entry_route                 VARCHAR(30)
deterministic_results       JSONB
gnn_plausibility_score      FLOAT
semantic_results            JSONB
llm_evaluation              JSONB
adjudication_verdict        VARCHAR(30)
adjudication_confidence     FLOAT
root_cause                  VARCHAR(100)
severity                    VARCHAR(20)
lifecycle_status            VARCHAR(20)
created_at                  TIMESTAMP DEFAULT NOW()
```

**Table: `correction_recommendations`**
```
id                  UUID PRIMARY KEY
feedback_id         UUID REFERENCES feedback_records(id)
evaluation_id       UUID REFERENCES evaluation_records(id)
correction_type     VARCHAR(50)
target_entity       VARCHAR(255)
target_type         VARCHAR(50)
cypher_mutation     TEXT NOT NULL
confidence_score    FLOAT NOT NULL
reasoning           TEXT
status              VARCHAR(20) DEFAULT 'pending'
applied_at          TIMESTAMP
applied_by          VARCHAR(255)
created_at          TIMESTAMP DEFAULT NOW()
INDEXES: (status, confidence_score DESC), (target_entity)
```

**Table: `correction_execution_history`** (audit trail — never deleted)
```
id                  UUID PRIMARY KEY
correction_id       UUID REFERENCES correction_recommendations(id)
action              VARCHAR(30)
cypher_executed     TEXT
before_state        JSONB
after_state         JSONB
entities_affected   JSONB
operator            VARCHAR(255)
timestamp           TIMESTAMP DEFAULT NOW()
```

**Table: `feedback_metrics`** (daily rollup)
```
id                          UUID PRIMARY KEY
date                        DATE UNIQUE NOT NULL
total_feedback              INT
positive_feedback           INT
negative_feedback           INT
entity_corrections          INT
relationship_corrections    INT
avg_confidence_score        FLOAT
tokens_used                 INT
tokens_saved                INT
created_at                  TIMESTAMP DEFAULT NOW()
```

**Retention policy:**
- `feedback_records`: 90 days (configurable)
- `correction_execution_history`: 365 days (compliance requirement)
- `evaluation_records`: 90 days
- `feedback_metrics`: indefinite (aggregated, small footprint)

---

### 3.5 Component: Response Metadata & Evidence Capture

**Purpose:** Every response must produce an immutable evidence snapshot the moment it is generated — before any feedback exists. This is the `Capture Interaction Evidence` node in the architecture diagram. Without this, feedback has nothing stable to point at.

**Design: `ResponseMetadataCache` (extend existing in `feedback_collector.py`)**

The class already exists with an in-memory fallback. The design extends it to:

1. On every response delivery (in `api/routes/query.py`), write a `ResponseMetadata` record with:
   - `response_id` (UUID v4 — already generated)
   - `query` (the original user query)
   - `response_text` (the full LLM answer)
   - `retrieved_evidence`: list of `{source, page, score, snippet}` — the FAISS hits used
   - `graph_paths`: top edges used from Neo4j traversal
   - `taxonomy_nodes`: matched taxonomy path
   - `citations`: citation markers in the response text
   - `guardrail_state`: whether any guardrail triggered
   - `model_id`, `prompt_version` (from `engine/config.py`)
   - `input_tokens`, `output_tokens`, `total_tokens`
   - `latency_ms_total`, `latency_ms_graph`, `latency_ms_vector`, `latency_ms_llm`
   - `query_type`: from `query_classifier.classify_query()`
   - `session_id`, `turn_index`
   - `mode`: traditional | contextgraph
   - `created_at`

2. This record is stored:
   - In-memory cache (TTL 24h) — for immediate feedback validation
   - PostgreSQL `interaction_evidence` table (permanent) — for retroactive analysis

3. The record is **immutable after creation**. No field is ever updated. All later evaluation references this snapshot.

**Design: Dissatisfaction Follow-up Detection (new, passive Active path)**

When a user sends a follow-up message in chat (`chat_view.py`), an intent classifier determines if it is dissatisfaction-triggered:

Signals that indicate dissatisfaction:
- Frustration keywords: "that's wrong", "that's not right", "incorrect", "outdated", "that's not what I asked"
- Short negative follow-ups after a response (≤15 words)
- Repeated rephrasing of the same question within 3 turns

If a follow-up exceeds a frustration threshold (0.65), a same-referent check runs:
- Embed the follow-up query and the prior response
- If cosine similarity ≥ 0.70 → same topic → convert to a `DissatisfactionSignal`
- The signal is passed through the same feedback pre-classification pipeline as explicit feedback
- It enters the evaluation queue with `entry_route = 'dissatisfaction_converted'`

This implements the `FD — Dissatisfaction Follow-up Handling` node from the architecture diagram without requiring the user to click a thumbs-down button.

---

### 3.6 Component: `app/engine/batch_evaluation.py` (New — Complete Gap)

**Purpose:** The LLM evaluation step that assigns confidence scores to feedback items and generates Cypher correction recommendations. Currently the biggest functional gap in the pipeline.

**Design:**

Class: `BatchEvaluationEngine`

Dependencies:
- `LLMClient` (from `app/core/llm.py`) — for the Claude API call
- `PostgreSQLFeedbackClient` — for storing recommendations
- Neo4j graph client — for fetching graph context (affected entity neighbourhood)
- Redis client (optional) — for caching graph snapshots and few-shot examples

**Method: `evaluate_batch(batch: list[dict]) → dict`**

The method executes a single LLM call for up to 25 feedback items. The design for the call structure:

**Token optimisation strategy (7 layers, matching the architecture):**

1. **System prompt amortisation** — one system prompt for all 25 items, not repeated per item. Saves ~70% of prompt tokens.
2. **Shared graph context** — fetch the Neo4j subgraph for all affected entities in the batch once. Only 1-hop neighbours, not the full graph. Cache result in Redis (key: `graph_ctx:{hash(entity_names)}`, TTL 1 hour).
3. **Few-shot examples** — pre-computed examples for each `FeedbackType`, stored in Redis (key: `few_shot:{feedback_type}`, TTL 24h). Not regenerated per call.
4. **Structured JSON output** — use `LLMClient.complete_structured()` with a JSON schema. No markdown, no explanation text in output. Saves ~30% of output tokens.
5. **Conditional routing** — items with inter-annotator agreement > 0.95 do NOT reach this method (auto-applied by FeedbackProcessor). Items with quality_score < 0.20 do NOT reach this method (auto-rejected). ~60% of items bypass LLM.
6. **Semantic deduplication** — already done by FeedbackProcessor before batches are formed. Cluster representatives carry vote weights.
7. **Graph snapshot caching** — same snapshot reused across all batches in one evaluation cycle.

**Prompt structure (design):**

```
SYSTEM: You are an expert knowledge graph curator for an AMC (Asset Management Company) 
chatbot. Evaluate the following user feedback items and determine whether each represents 
a genuine knowledge graph correction need. For each item that does, generate a safe, 
targeted Cypher mutation.

OUTPUT FORMAT: Return a JSON array with one object per feedback_id:
{
  "feedback_id": "...",
  "verdict": "correction_needed | no_action | insufficient_evidence",
  "confidence": 0.0-1.0,
  "correction_type": "add_entity|update_property|add_relationship|remove_relationship|null",
  "target_entity": "...",
  "cypher_mutation": "MATCH ... SET/MERGE/DELETE ...",
  "reasoning": "one sentence"
}

GRAPH CONTEXT (current state for affected entities):
{graph_snapshot}

FEW-SHOT EXAMPLES:
{few_shot_examples}

FEEDBACK ITEMS:
{batch_as_json_array}
```

**Output parsing:**
- Parse JSON response
- For each item: validate cypher_mutation safety (no DROP, no schema changes, no DELETE without MATCH)
- Assign final confidence (LLM confidence × inter-annotator agreement from FeedbackProcessor)
- Store each as a row in `correction_recommendations`

**Token budget bands (B0–B5 from the architecture):**
- B0 (0 tokens): items routed to auto-apply or auto-reject — never reach this method
- B1 (≤250 tokens/item after amortisation): standard correction request
- B2 (≤500): complex multi-entity correction
- B3 (≤800): escalation with extended graph context
- B4/B5: reserved for human escalation (not this component)

---

### 3.7 Component: Tiered Evaluation Engine (HITL Path)

**Purpose:** The `Feedback Validation Layer` from the architecture diagram. Routes a feedback claim to the cheapest evaluation tier that can resolve it before escalating to more expensive tiers.

**Design: Tier 1 — Rule Categories**

Nine rule category evaluators, each emitting `{category, rule_id, verdict: pass|fail|score, threshold, evidence_ref}`:

| Category | What it checks | Key check |
|---|---|---|
| Schema/Type | Entity type in feedback matches taxonomy | `entity_type in taxonomy.valid_types` |
| Cardinality | Relationship arity is valid | No fund has >1 active benchmark of same type |
| Referential | Target entity exists in Neo4j | `MATCH (n) WHERE n.name = entity_name RETURN n` |
| Temporal | Date claims are consistent | `valid_from < valid_to`, no future-dated facts |
| Numeric | Numbers in feedback are within plausible range | NAV > 0, TER 0–10%, AUM > 0 |
| Cross-Source | Same fact from two sources agrees | Compare AMFI vs SID values |
| Duplicate | Entity is not a duplicate of an existing node | `entity_resolver.resolve_entities_for_query()` |
| Hierarchy | Taxonomy path is valid | Fund category within allowed parent category |
| Jurisdiction | Entity applies in the correct regulatory scope | SEBI vs SEC scope check |

Each rule category evaluator already has the data to run deterministically using the existing `graph_store.py` and `entity_resolver.py`. No new infrastructure needed for rules — just the wrapper and schema.

**Design: Tier 1 — GNN Structural Plausibility**

A frozen graph neural network that scores the structural plausibility of a proposed correction triple (subject, predicate, object) against the learned structural patterns of the existing graph.

Architecture choice: **R-GCN (Relational Graph Convolutional Network)** or **CompGCN**
- Takes as input: the candidate triple + 2-hop neighbourhood subgraph
- Outputs: plausibility score 0.0–1.0 + anomaly flags for neighbourhood patterns that deviate from training distribution

Key design constraints (from the architecture document):
- **Frozen at inference time** — the model is called with a fixed weights file, fixed threshold. Zero non-determinism at evaluation time.
- **No LLM tokens** — this tier costs only graph traversal + matrix ops
- **Separate training cadence** — the GNN is retrained as a governed batch job (see Phase 3 §5.4), never as a reaction to individual interactions

At Phase 2, this can start as a **stub returning 0.5 (neutral)** until the GNN training pipeline is ready. The interface contract is fixed so downstream tiers work regardless.

Interface: `GNNPlausibilityScorer.score(subject: str, predicate: str, object: str, subgraph: dict) → float`

**Design: Tier 2 — Semantic Evaluation**

NLI (Natural Language Inference) model checks whether the user's claim is entailed by, contradicted by, or neutral to the existing evidence.

Model choice: `cross-encoder/nli-deberta-v3-small` or similar (local, no API cost)

Input:
- Premise: the text of the relevant source document chunks (from the frozen evidence snapshot)
- Hypothesis: the user's feedback claim converted to a statement

Output: `{entailment: float, contradiction: float, neutral: float}`

Routing logic:
- If entailment > 0.7 → claim is supported → verdict: PARTIALLY_VALID (the claim agrees with evidence)
- If contradiction > 0.7 → claim conflicts with evidence → needs Tier 3 or human
- If neutral > 0.7 → evidence doesn't address the claim → forward to Tier 3

**Design: Tier 3 — LLM / Agent Evaluator**

Only reached when Tier 1 rules + GNN + Tier 2 NLI together cannot resolve the claim.

Uses `LLMClient.complete_structured()` with a minimal `EvaluationPacket` — not the full conversation, not the full evidence. Only:
- The disputed claim
- The 2 most relevant evidence chunks
- The rule findings that were inconclusive
- The NLI score and the reason it didn't resolve

Output: verdict + confidence + one-line reasoning

This is the same LLM call as `batch_evaluation.py` but single-item and with extended context.

---

### 3.8 Component: Passive Evaluation Path (No-Feedback)

**Purpose:** Implements the `Automatic Evaluation Trigger → Tier 0/1 → suspicious/sampled check` path. Runs on 100% of responses without requiring any user action.

**Design: Auto-Signal Emission (new, in `api/routes/query.py`)**

After every response delivery, an async background task fires and computes:

| Signal | How computed | Source |
|---|---|---|
| `numeric_mismatch` | Extract all numbers from response; compare against FAISS chunk numbers | `response_text` vs `retrieved_evidence` |
| `citation_coverage` | Count citation markers in response vs number of sources used | `response_text`, `retrieved_evidence` |
| `source_version_mismatch` | Compare source version in evidence snapshot vs current source registry | `interaction_evidence`, `graph_store` |
| `retrieval_confidence_low` | Min FAISS score in retrieved hits | `retrieved_evidence` scores |
| `guardrail_triggered` | Whether any compliance guardrail fired | `guardrail_state` in evidence snapshot |
| `context_truncated` | Whether token budget was hit | `latency_ms_total`, `input_tokens` vs budget |
| `schema_violation` | Whether response follows expected format | Regex/template check |
| `cost_anomaly` | Token usage > 2× expected for query type | `total_tokens` vs `query_type` baseline |

Each signal has a severity: `LOW` | `MEDIUM` | `HIGH`

**Routing decision (the `suspicious / sampled / high-value?` diamond):**

- If any signal is HIGH → immediate E1 evaluation queued
- If multiple MEDIUM signals → queued for E2 semantic evaluation
- If sampled (configurable % by query type, e.g. 5% of all responses) → queued for E1
- If HIGH-VALUE query (compliance-sensitive intent detected) → always queued
- Otherwise → store metrics only (E0)

The auto-signal record is stored in PostgreSQL as an `auto_evaluation_trigger` linked to the `interaction_evidence`.

**Design: Cohort Health Monitoring (new)**

A daily background job computes per-cohort health metrics grouped by:
- Query type × feedback_type (e.g. all `direct_lookup` × `entity_incorrect` feedback this week)
- Entity × date (correction frequency per entity over time)
- Source version × response count (how many responses used a source version before an update)

Alerts fire when:
- Correction rate for an entity > 3× the 30-day baseline
- Source version in use is > 7 days older than the current version in the registry
- Average retrieval confidence for a query cohort drops by > 15% week-over-week

These alerts create `auto_evaluation_trigger` records that feed into the same evaluation pipeline as explicit user feedback.

---

### 3.9 Evaluation Orchestrator — Connecting the Pieces

**Purpose:** The `EvaluationOrchestrator` class already exists in `tasks/evaluation_orchestrator.py`. This section designs how it wires to the new components.

**Updated 7-step cycle:**

1. **Fetch** — `PostgreSQLFeedbackClient.fetch_pending_feedback(limit=500, hours_back=24)` — both HITL and auto-triggered items, ordered by quality_score DESC
2. **Aggregate** — `FeedbackProcessor.prepare_evaluation_batches()` — group by entity+type, consensus scoring, semantic deduplication
3. **Route** — Split into three lanes:
   - `auto_apply` lane: quality_score ≥ 0.95 AND inter-annotator agreement ≥ 0.90 → skip LLM
   - `auto_reject` lane: quality_score < 0.20 → close without evaluation
   - `evaluate` lane: everything else → proceed to Tier 1 → Tier 2 → Tier 3 as needed
4. **Evaluate (Tier 1/2/3)** — Tiered evaluation engine (§3.7) for the HITL path; `BatchEvaluationEngine` for the automatic path
5. **Store** — All verdicts written to `evaluation_records` and `correction_recommendations`
6. **Apply** — `GraphCorrectionEngine.apply_high_confidence_corrections()` for items confidence ≥ 0.85
7. **Invalidate caches** — `CacheManager.invalidate_entity_caches()` for all corrected entities

**APScheduler configuration:**
- Default: cron `0 * * * *` (every hour)
- Configurable via `Settings.evaluation_cron_schedule`
- Max 500 items per cycle (configurable)
- On failure: cycle is logged and retried next hour; items stay in `pending` state

---

### 3.10 Dependency Wiring (`app/api/deps.py` update)

**Purpose:** The `Container` class must be extended to wire all feedback components at startup. Currently none of the feedback components are initialized.

**New attributes to add to `Container`:**

```
Container.feedback_db          → PostgreSQLFeedbackClient
Container.feedback_collector   → FeedbackCollector(feedback_db, ner_pipeline, response_cache)
Container.feedback_processor   → FeedbackProcessor(feedback_db)
Container.batch_evaluator      → BatchEvaluationEngine(llm, feedback_db, graph)
Container.graph_corrector      → GraphCorrectionEngine(graph, feedback_db)
Container.cache_manager        → CacheManager(vector_store, graph, redis_client)
Container.orchestrator         → EvaluationOrchestrator(...all above...)
Container.response_cache       → ResponseMetadataCache (Redis or in-memory)
```

**`app/main.py` lifespan addition:**
- After Container initialization: call `SchedulerManager.start()` to start the APScheduler
- On shutdown: call `SchedulerManager.shutdown()`
- Register the feedback router: `app.include_router(feedback_router, prefix="/api/feedback")`

---

## 4. Phase 3 — Self-Correcting Knowledge Graph & Governed Deployment

### 4.1 Overview

Phase 3 implements the three-stage KG correction pipeline shown as the `DET → EVAL → RES` subgraphs in `AMC_FEEDBACK_LOOP_ARCHITECTURE_v2.html`. Phase 2 feeds candidates into Phase 3. Phase 3 executes them safely.

The three stages are deliberately separated because they have different trust levels and different failure modes:
- **Detection** — finding and localising — cannot cause damage
- **Evaluation** — judging — can produce wrong verdicts but cannot change the graph
- **Resolution** — acting — the only stage that writes to production

---

### 4.2 Stage 1 — Detection (Localise the Candidate Correction)

**Purpose:** Find the exact disputed node/edge/triple. Does not judge anything. Just identifies what needs evaluation.

**Three entry points (design):**

**Entry Point 1: HITL-confirmed feedback (from Phase 2)**
- A feedback item that passed Phase 2 evaluation with a `correction_needed` verdict
- The `target_entity` and `correction_type` from `correction_recommendations` identify the candidate
- Localisation: `MATCH (n) WHERE n.name = $entity_name RETURN n, [(n)-[r]-(m) | [r, m]]`

**Entry Point 2: Scheduled GNN Structural Sweep**
- Background job that runs daily, not per-interaction
- Sweeps all nodes added or modified in the last 7 days
- For each, asks the GNN: is this triple structurally plausible given its neighbourhood?
- Triples with GNN score < 0.40 (configurable) are flagged as `structural_anomaly` candidates
- This catches graph drift caused by ingestion issues, not user complaints
- Implementation: `StructuralSweepJob` — new class in `app/tasks/`

**Entry Point 3: Ingestion-time source conflict**
- During document ingestion (`app/ingestion/pipeline.py`), when a new entity is extracted, the system checks whether a conflicting node already exists with the same canonical identity
- If new source says `EntityA.TER = 0.82%` but existing graph says `EntityA.TER = 0.79%`, a `source_conflict` candidate is created
- The conflict record includes both versions + their source provenance
- No auto-resolution — goes into the same evaluation queue

**Detection output: `CorrectionCandidate`**
```
candidate_id          UUID
entry_point           hitl | structural_sweep | source_conflict
source_ref            feedback_id | sweep_run_id | ingestion_job_id
disputed_node_id      str (Neo4j internal ID)
disputed_node_name    str
disputed_edge_type    Optional[str]
disputed_object       Optional[str]
proposed_new_value    Optional[str | dict]
localised_at          datetime
status                pending_evaluation
```

---

### 4.3 Stage 2 — Evaluation (Judge It, Cheapest Signal First)

**Purpose:** Determine whether the candidate correction is confirmed, rejected, or ambiguous. This stage merges all evaluation signals before writing any verdict.

**Signal merge strategy:**

The evaluation stage runs three evaluators in order of cost and stops as soon as a confident verdict is available:

```
1. Rule Categories + GNN (Tier 1) → if confident → STOP
2. Semantic NLI (Tier 2)          → if confident → STOP
3. LLM / Agent (Tier 3) OR HITL   → verdict always
```

"Confident" threshold: combined signal confidence ≥ 0.80

**Confidence combination formula:**
`combined_confidence = max(rule_confidence, gnn_score) × semantic_weight + semantic_confidence × (1 - semantic_weight)`
where `semantic_weight = 0.6` if semantic evaluation ran, else `0.0`

**Escalation to human (HITL):**
The evaluation stage escalates to a human reviewer when:
- All three tiers return confidence < 0.60
- The candidate involves a compliance-sensitive attribute (risk category, jurisdiction, regulatory text)
- Two authoritative sources conflict with each other (not just old vs new — genuinely different sources)

Human review interface design: a new route `GET /api/corrections/pending-review` returns the candidate + evidence for a human reviewer. `POST /api/corrections/{id}/approve` and `POST /api/corrections/{id}/reject` let the reviewer decide.

**Verdict schema: `EvaluationVerdict`**
```
verdict_id              UUID
candidate_id            UUID
verdict                 confirmed | rejected | ambiguous | escalated_to_human
confidence              float
tier_that_resolved      tier1 | tier2 | tier3 | human
rule_findings           list[dict]
gnn_score               float
semantic_result         dict
llm_evaluation          Optional[dict]
human_decision          Optional[str]
decided_by              system | human_user_id
decided_at              datetime
```

---

### 4.4 Stage 3 — Resolution (Act Only on a Confirmed Verdict)

**Purpose:** Act on the verdict. Two resolution paths depending on the confirmation:

**Path A: Confirmed → Correction Patch Layer (immediate, reversible)**

The `GraphCorrectionEngine` (already written in `engine/graph_corrector.py`) applies the Cypher mutation inside a Neo4j atomic transaction.

Design extensions needed in `graph_corrector.py`:

1. **Correction Patch Store** — a separate Neo4j label `:CorrectionPatch` on the modified node/edge, storing:
   - `patch_id`
   - `original_value`
   - `patched_value`
   - `confidence`
   - `provenance` (candidate_id + verdict_id)
   - `TTL` (days until patch expires if not ratified)
   - `status` (active | ratified | reverted)
   
2. **LLM Context Override** — when the retrieval pipeline encounters an entity with active correction patches, it injects the patched value into the prompt context ahead of the raw graph fact. This is the "LLM learns from feedback" mechanism — it is a context override, NOT a weight update and NOT a permanent graph change.
   - Implementation: in `engine/retrieval.py`, `hybrid_graphrag()` checks for active patches for each entity before building the prompt. Patched values are tagged `[PATCHED - PENDING RATIFICATION]` so they are transparent.

3. **Improvement Queue** — confirmed but not-yet-ratified corrections are queued for the weekly governance batch. A `CorrectionQueueEntry` record links the verdict to the governance batch it will be reviewed in.

**Path B: Rejected → Close, no graph change**

The candidate is marked `rejected` with the rejection reason. No graph change. The candidate is linked to the original feedback_id so patterns can be analysed (e.g. "this entity is frequently complained about but all corrections are invalid — may indicate a UI misunderstanding").

---

### 4.5 Governance & Controlled Deployment

**Purpose:** The only path that can write to the canonical knowledge graph. Weekly batch, human approval required.

**Design: Offline Regression Test (before governance)**

Before any correction reaches the governance batch, it must pass regression:

1. **Golden set test** — run a set of known correct Q&A pairs for the affected entity and verify the corrected graph still answers them correctly
2. **Blast-radius check** — identify all query types that traverse the affected entity; run them against a staging copy of the graph with the correction applied; verify no regressions
3. **Compliance routing test** — verify the correction does not change which guardrails fire for the affected entity

All three must pass. Failure sends the correction to `rejected` (not just delayed — a failed regression is a signal the correction may have unintended side effects).

**Design: Human Governance Approval Interface**

New route: `GET /api/governance/pending-batch` — returns all corrections that passed regression, grouped by entity type and correction type, ready for human review

New route: `POST /api/governance/batch/{batch_id}/approve` — approves the entire batch (or individual corrections)

New route: `POST /api/governance/batch/{batch_id}/reject-item/{correction_id}` — rejects one item and sends the batch remainder to apply

**Design: Canonical KG Update**

On governance approval, `GraphCorrectionEngine.apply_canonical_update()` (new method):
1. Execute the Cypher mutation atomically in Neo4j
2. Remove the `:CorrectionPatch` overlay — the graph now has the canonical value
3. Mark the `CorrectionQueueEntry` as `ratified`
4. Write to `correction_execution_history` with `action = 'canonical_applied'`
5. Trigger reindexing of affected entities in FAISS (delete + re-embed)
6. Trigger the GNN refresh job (§4.6)
7. Post-change: the `[PATCHED - PENDING RATIFICATION]` tag disappears from future responses automatically

**Design: Rollback**

Every canonical update can be rolled back using the `before_state` snapshot in `correction_execution_history`. `GraphCorrectionEngine.rollback_correction()` already exists — it reads the audit record and generates the reverse Cypher. Rollback also restores the `:CorrectionPatch` if there was one.

---

### 4.6 GNN Training & Refresh Pipeline

**Purpose:** The GNN structural plausibility scorer must stay in sync with the knowledge graph. It is refreshed on the same governed cadence as canonical updates.

**Training data:**
- Positive examples: existing edges in the canonical graph (labelled as plausible)
- Negative examples: randomly corrupted triples (head/tail entity swapped) + confirmed-rejected corrections from Phase 3 evaluation

**Training schedule:**
- Full retrain: weekly, after the governance batch deploys
- Incremental update: daily, using only the new positive examples added since last full train
- A/B gating: new GNN version is compared against the current version on a held-out eval set before promotion

**Trigger:** The canonical KG update step (§4.5) fires a `GNNRefreshJob` event. The refresh job picks this up and schedules training for the next batch window.

**Inference only uses frozen weights:** After training, the model is serialised to disk. The `GNNPlausibilityScorer` in Tier 1 evaluation loads the frozen file at startup and never updates it mid-run. This guarantees determinism at inference time.

---

### 4.7 Post-Change Measurement & Loop Closure

**Purpose:** Verify that the correction improved outcomes and feeds back into evidence capture.

**Metrics collected post-change:**
- Did the correction rate for this entity decrease over the next 7 days?
- Did retrieval confidence scores for queries involving this entity improve?
- Did any new negative feedback appear for the same entity (correction had side effects)?

**Loop closure:** The `Measure Post-change Outcome` step writes an `outcome_record` linked to the `correction_execution_history` entry. This record is visible in the analytics dashboard. If the correction rate did not decrease, the outcome is flagged for human review — the correction may have been technically applied but did not address the underlying user issue (which may be a UI or explanation problem, not a data problem).

The outcome record feeds back into `interaction_evidence` through the cohort health monitor (§3.8), raising the baseline expectation for that entity's retrieval quality.

---

## 5. Integration Map — What Changes in Existing Files

This section lists every existing file that needs to change, and what specifically changes. No new code — just the design of what changes are needed.

### `backend/app/api/routes/query.py`

**Current state:** Returns responses with `response_id` but does not write evidence snapshots.

**Required additions:**
1. After LLM synthesis, call `ResponseMetadataCache.store()` with the full evidence snapshot (query, response, retrieved chunks, graph paths, tokens, latency, model version)
2. Launch a `BackgroundTask` to emit the auto-signal (§3.8) — checking for numeric mismatches, citation coverage, source version staleness
3. The `response_id` is already generated — it just needs to be linked to the evidence snapshot

### `backend/app/api/routes/feedback.py`

**Current state:** 4 endpoints written but dependencies not wired into Container.

**Required additions:**
1. Import and use `Container.feedback_collector` (once it is wired in `deps.py`)
2. Import `FeedbackRequest`, `FeedbackResponse` from `schemas/feedback.py` (once created)
3. The dissatisfaction detection endpoint: `POST /api/feedback/dissatisfaction` — accepts a follow-up query + session_id, runs the frustration/same-referent classifier, and converts to feedback if above threshold

### `backend/app/api/deps.py`

**Current state:** Container initialises LLM, Graph, Vector, Resolver, Classifier, Extractor, Ingestion, Retrieval. No feedback components.

**Required additions:** All 8 new attributes listed in §3.10.

### `backend/app/main.py`

**Current state:** Lifespan starts ingest queue but not the evaluation scheduler.

**Required additions:**
1. `SchedulerManager(orchestrator).start()` in the lifespan startup
2. `SchedulerManager.shutdown()` in the lifespan shutdown
3. Include the feedback router

### `backend/app/engine/retrieval.py` — `hybrid_graphrag()`

**Current state:** Does not check for active correction patches.

**Required addition (Phase 3):**
Before building the graph context section, check for active `:CorrectionPatch` nodes on any of the matched entities. If patches exist, inject the patched values ahead of raw graph facts with a `[PATCHED - PENDING RATIFICATION]` annotation.

### `backend/app/ingestion/pipeline.py`

**Current state:** Does not emit source conflict candidates.

**Required addition (Phase 3):**
After writing new entities/relationships to Neo4j, compare against existing nodes with the same canonical identity. If a value conflict is found, create a `CorrectionCandidate` record with `entry_point = source_conflict`.

---

## 6. New Files Required

| File | Type | Purpose | Phase |
|---|---|---|---|
| `app/schemas/feedback.py` | Pydantic models | FeedbackRequest, FeedbackResponse, DissatisfactionSignal, EvaluationRecord, FeedbackType enum | Phase 2 |
| `app/engine/postgres_client.py` | Async service class | All PostgreSQL operations for feedback/evaluation | Phase 2 |
| `app/engine/batch_evaluation.py` | Async service class | LLM batch evaluation, graph context caching, token optimisation | Phase 2 |
| `app/engine/gnn_plausibility.py` | ML model wrapper | GNN structural plausibility scorer (frozen at inference) | Phase 3 |
| `app/tasks/structural_sweep.py` | Background job | Daily GNN sweep of recently modified graph nodes | Phase 3 |
| `app/tasks/gnn_refresh.py` | Background job | Weekly GNN model retrain triggered after canonical KG update | Phase 3 |
| `app/tasks/regression_test.py` | Test runner | Golden set + blast-radius + compliance routing tests before governance approval | Phase 3 |
| `app/engine/migrations/001_feedback_schema.sql` | SQL | Tables: feedback_records, feedback_classifications, evaluation_records, correction_recommendations, correction_execution_history, feedback_metrics | Phase 2 |
| `app/engine/migrations/002_evidence_snapshot.sql` | SQL | Table: interaction_evidence | Phase 2 |
| `app/engine/migrations/003_correction_candidates.sql` | SQL | Tables: correction_candidates, correction_queue, governance_batches | Phase 3 |

---

## 7. Dependency Addition Requirements

The following Python packages need to be added to `backend/requirements.txt`:

| Package | Version (approx) | Purpose |
|---|---|---|
| `asyncpg` | ≥0.29 | Async PostgreSQL client for PostgreSQLFeedbackClient |
| `apscheduler` | ≥3.10 | Already referenced in evaluation_orchestrator.py — add to requirements |
| `torch` / `torch-geometric` | current stable | GNN training + inference (PyG for R-GCN/CompGCN) — Phase 3 only |
| `sentence-transformers` | ≥2.7 | NLI model for Tier 2 semantic evaluation (cross-encoder/nli-deberta-v3-small) |
| `redis[asyncio]` | ≥5.0 | Redis client for response cache + graph context caching (optional, degrades gracefully) |

**Note:** Redis and torch/torch-geometric are optional at Phase 2 — the system degrades to in-memory fallbacks. All Phase 2 components work without them.

---

## 8. Configuration Additions (`app/config.py`)

New settings to add to the `Settings` class:

```
# PostgreSQL (feedback buffer)
postgres_dsn: str = ""   # e.g. "postgresql://user:pass@localhost:5432/amc_feedback"

# Redis (optional — cache falls back to in-memory if not configured)
redis_url: str = ""      # e.g. "redis://localhost:6379/0"

# Evaluation orchestrator
evaluation_cron_schedule: str = "0 * * * *"   # hourly
max_feedback_per_cycle: int = 500
feedback_hours_back: int = 24
evaluation_batch_size: int = 25

# Confidence thresholds
auto_apply_threshold: float = 0.85
auto_reject_threshold: float = 0.20
human_review_threshold: float = 0.60
gnn_anomaly_threshold: float = 0.40

# Retention
feedback_retention_days: int = 90
audit_retention_days: int = 365

# GNN
gnn_model_path: str = "./data/models/gnn_plausibility.pt"
gnn_frozen: bool = True   # always True in production

# Governance
governance_review_day: str = "monday"   # weekly batch day
regression_test_timeout_seconds: int = 300
```

---

## 9. Risks & Constraints

| Risk | Severity | Mitigation |
|---|---|---|
| PostgreSQL adds a new infra dependency | Medium | Use existing PG instance if available; can use SQLite for dev with asyncpg → aiosqlite swap |
| GNN training requires labelled negative examples | High | Start with the stub (returns 0.5) for Phase 2; Phase 3 GNN training uses confirmed-rejected corrections as negative labels — cold start is possible with random corruptions |
| Correction Patch Layer adds latency to `hybrid_graphrag()` | Low | Patch lookup is a single indexed Neo4j query (<5ms); cache patches per session |
| Feedback poisoning — adversarial corrections | High | Confidence gating (0.85), inter-annotator agreement requirement, human governance as the only canonical write path, full audit trail |
| Duplicate evaluation of same correction candidate | Medium | Idempotency key on `correction_recommendations` using `(target_entity, correction_type, proposed_value)` composite unique constraint |
| APScheduler and asyncpg conflict in FastAPI lifespan | Low | asyncpg uses asyncio natively; APScheduler with AsyncIOScheduler is compatible with FastAPI's async lifespan |

---

## 10. Build Sequence (for architect review)

The following sequence is recommended to minimise integration risk. Each step can be reviewed and approved independently.

**Sprint 1 — Foundation (unblocks everything)**
1. Create `schemas/feedback.py` — no dependencies, unblocks all imports
2. Create PostgreSQL schema + migrations (001 + 002)
3. Create `postgres_client.py` — can be tested against PG directly
4. Wire `deps.py` + `main.py` — scheduler starts, routes register

**Sprint 2 — Active HITL Path**
5. Evidence snapshot emission in `routes/query.py`
6. `ResponseMetadataCache` integration in `feedback_collector.py`
7. Feedback API fully functional end-to-end
8. Tier 1 rule evaluators wired to `feedback_validation_layer.py`

**Sprint 3 — Passive Path + Batch Evaluation**
9. Auto-signal emission background task
10. Cohort health monitor job
11. `batch_evaluation.py` — the LLM evaluation engine
12. Full orchestration cycle runs end-to-end

**Sprint 4 — KG Correction (Phase 3 Detection + Evaluation)**
13. `correction_candidates` schema (migration 003)
14. `structural_sweep.py` (daily GNN sweep — initially with stub scorer)
15. Source conflict detection in ingestion pipeline
16. Stage 2 evaluation merge logic

**Sprint 5 — Resolution & Governance**
17. Correction Patch Layer in Neo4j + retrieval integration
18. Improvement Queue + governance batch endpoint
19. Regression test runner
20. Canonical KG update + GNN refresh trigger

**Sprint 6 — GNN Training Pipeline (Phase 3 completion)**
21. R-GCN/CompGCN training pipeline
22. GNN model versioning + A/B gating
23. Replace stub scorer with trained model
24. Post-change measurement + loop closure

---

## Appendix A — Mapping to AMC_REALTIME_SCENARIOS_LLD.html

The realtime scenarios document shows 8 phases. The table below maps each phase to the design components in this document.

| Scenario Phase | What happens | Design component |
|---|---|---|
| Phase 1: User Query → Response | Existing Phase 1 pipeline | No change to Phase 1 |
| Phase 2: Feedback Capture | User submits feedback / dissatisfaction detected | §3.5 Evidence Capture, §3.2 schemas, §3.3 postgres_client |
| Phase 3: PG Buffer | Feedback stored in PostgreSQL buffer | §3.4 Database Schema |
| Phase 4: Hourly Orchestration | APScheduler wakes, runs cycle | §3.9 Orchestrator |
| Phase 5: LLM Batch Evaluation | 25 items per call, token-optimised | §3.6 BatchEvaluationEngine |
| Phase 6: Graph Correction | Neo4j atomic transaction, audit trail | §4.4 Stage 3 Resolution |
| Phase 7: Cache Invalidation | FAISS + entity resolver + traversal cache | Existing CacheManager, wired |
| Phase 8: Loop Closes | Better retrieval → better answers | §4.7 Post-Change Measurement |

---

## Appendix B — Mapping to AMC_FEEDBACK_LOOP_ARCHITECTURE_v2.html

The architecture diagram nodes mapped to design sections:

| Diagram Node | Design Section |
|---|---|
| A: User Query → B1-B3: Pipeline | Phase 1 (existing) |
| C: Response Generated | Phase 1 (existing) |
| D → D1: Capture Interaction Evidence | §3.5 Evidence Capture |
| E: Human Feedback or follow-up? | §3.2 FeedbackType enum, §3.5 Dissatisfaction detection |
| F: Structured HITL Feedback | §3.2 FeedbackRequest, §3.3 store_feedback() |
| FD: Dissatisfaction Follow-up Handling | §3.5 DissatisfactionSignal, frustration classifier |
| F1: Category | §3.2 FeedbackType enum |
| G → G1 → G1b → G2–G5: Tiered Evaluation | §3.7 Tiered Evaluation Engine |
| H → H1: Feedback Adjudication | §3.7, verdict stored in EvaluationRecord |
| I: Automatic Evaluation Trigger | §3.8 Auto-Signal Emission |
| J → K: Tier 0/1 + suspicious check | §3.8 signal categories and routing |
| L: Store Evaluation + Metrics | §3.4 evaluation_records table |
| M → P → O: Tier 2/3 + Evaluation Finding | §3.7 Tier 2 semantic, Tier 3 LLM |
| Q: Unified Evaluation Record | §3.2 EvaluationRecord schema, §3.4 evaluation_records table |
| R → R1 → S → T: Failure Diagnosis | §3.9 orchestrator cycle step 3 |
| DET subgraph: Detection | §4.2 Stage 1 Detection |
| EVAL subgraph: Evaluation | §4.3 Stage 2 Evaluation |
| RES subgraph: Resolution | §4.4 Stage 3 Resolution, Correction Patch Layer |
| X → Y: Regression Test | §4.5 Offline Regression Test |
| AA: Human Governance Approval | §4.5 Governance Approval Interface |
| AB: Controlled Deployment | §4.5 Canonical KG Update |
| ABG: Scheduled GNN Refresh | §4.6 GNN Training & Refresh |
| AC → D: Measure Post-change | §4.7 Post-Change Measurement |

---

*End of technical design document.*  
*Status: Design only — awaiting architect review before any implementation begins.*
