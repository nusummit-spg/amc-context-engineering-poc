# LLD-08 — Data Models

**Document:** LLD-08  
**Version:** 1.0  
**Depends on:** All preceding LLD documents  
**Purpose:** Single reference for all schemas — PostgreSQL DDL, Python dataclasses, API contracts, event schemas

---

## 1. PostgreSQL Schema

Full DDL for the feedback buffer and evaluation pipeline. All tables use UUID primary keys, JSONB for structured payloads, and `TIMESTAMPTZ` for all timestamps.

### 1.1 evidence_packs

Stores the frozen D0–D3 EvidencePack for every response.

```sql
CREATE TABLE evidence_packs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    response_id             UUID NOT NULL UNIQUE,
    interaction_id          UUID NOT NULL,
    conversation_id         UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- D0: Response Finalization
    d0_response_status      VARCHAR(30) NOT NULL,
    d0_model_id             VARCHAR(100) NOT NULL,
    d0_model_version        VARCHAR(100),
    d0_generation_config_version UUID,
    d0_prompt_template_version   UUID,
    d0_response_text        TEXT NOT NULL,
    d0_response_structure   VARCHAR(20) DEFAULT 'markdown',
    d0_citations_shown      JSONB DEFAULT '[]',
    d0_disclosures_shown    JSONB DEFAULT '[]',
    d0_guardrail_state      VARCHAR(30),
    d0_generation_latency_ms INTEGER,
    d0_input_tokens         INTEGER,
    d0_output_tokens        INTEGER,
    d0_tool_calls           JSONB DEFAULT '[]',
    d0_tool_failures        JSONB DEFAULT '[]',
    d0_fallback_used        BOOLEAN DEFAULT FALSE,
    d0_truncation_flag      BOOLEAN DEFAULT FALSE,
    d0_response_hash        VARCHAR(64) NOT NULL,

    -- D1: Interaction Snapshot
    d1_user_query           TEXT NOT NULL,
    d1_normalized_query     TEXT,
    d1_detected_intent      VARCHAR(100),
    d1_intent_confidence    FLOAT,
    d1_intent_method        VARCHAR(30),
    d1_secondary_intents    JSONB DEFAULT '[]',
    d1_extracted_entities   JSONB DEFAULT '[]',
    d1_ambiguity_flag       BOOLEAN DEFAULT FALSE,
    d1_conversation_context_id UUID,
    d1_retrieval_config     JSONB,
    d1_taxonomy_version     VARCHAR(50),
    d1_guardrail_version    VARCHAR(50),
    d1_session_metadata     JSONB,

    -- D2: Evidence Pack (full payload stored as JSONB for flexibility)
    d2_vector_retrieval     JSONB DEFAULT '{}',
    d2_graph_retrieval      JSONB DEFAULT '{}',
    d2_bm25_retrieval       JSONB DEFAULT '{}',
    d2_taxonomy_matches     JSONB DEFAULT '{}',
    d2_context_engineering  JSONB DEFAULT '{}',
    d2_source_provenance    JSONB DEFAULT '{}',
    d2_derived_metrics      JSONB DEFAULT '{}',

    -- D3: Applicability Context
    d3_jurisdiction         VARCHAR(10),
    d3_regulated_entity_role VARCHAR(60),
    d3_product_type         VARCHAR(60),
    d3_channel              VARCHAR(40),
    d3_customer_segment     VARCHAR(40),
    d3_interaction_mode     VARCHAR(30),
    d3_advice_flag          BOOLEAN DEFAULT FALSE,
    d3_policy_pack_id       VARCHAR(80),
    d3_policy_pack_version  VARCHAR(40),
    d3_applicable_control_set_id UUID,
    d3_mandatory_controls   JSONB DEFAULT '[]',
    d3_hard_block_controls  JSONB DEFAULT '[]',
    d3_resolution_method    VARCHAR(30)
);

CREATE INDEX idx_ep_response_id      ON evidence_packs (response_id);
CREATE INDEX idx_ep_interaction_id   ON evidence_packs (interaction_id);
CREATE INDEX idx_ep_created_at       ON evidence_packs (created_at);
CREATE INDEX idx_ep_jurisdiction     ON evidence_packs (d3_jurisdiction);
CREATE INDEX idx_ep_intent           ON evidence_packs (d1_detected_intent);
```

### 1.2 feedback_records

Raw feedback submissions from users. Linked to `evidence_packs` via `response_id`.

```sql
CREATE TABLE feedback_records (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    response_id             UUID NOT NULL REFERENCES evidence_packs(response_id),
    interaction_id          UUID NOT NULL,
    session_id              UUID,

    -- Raw input
    rating                  SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    feedback_type           VARCHAR(50),
    entity_name             VARCHAR(255),
    comment                 TEXT CHECK (LENGTH(comment) <= 2000),
    highlighted_span        JSONB,
    correction              TEXT,

    -- Pre-classification (populated by BackgroundTask)
    ner_tags                JSONB DEFAULT '[]',
    sentiment               JSONB,
    intent                  VARCHAR(50),
    quality_score           FLOAT CHECK (quality_score BETWEEN 0 AND 1),
    classification_status   VARCHAR(20) DEFAULT 'pending',

    -- Actor
    actor_role              VARCHAR(50) DEFAULT 'user',

    -- Lifecycle
    status                  VARCHAR(20) DEFAULT 'pending'
                                CHECK (status IN (
                                    'pending','evaluating','applied','rejected','archived'
                                )),
    evaluation_job_id       UUID,
    correction_id           UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evaluated_at            TIMESTAMPTZ,
    applied_at              TIMESTAMPTZ,
    archived_at             TIMESTAMPTZ
);

CREATE INDEX idx_fr_response_id       ON feedback_records (response_id);
CREATE INDEX idx_fr_status_created    ON feedback_records (status, created_at);
CREATE INDEX idx_fr_quality           ON feedback_records (quality_score) WHERE status = 'pending';
CREATE INDEX idx_fr_entity            ON feedback_records (entity_name)    WHERE entity_name IS NOT NULL;
CREATE INDEX idx_fr_intent            ON feedback_records (intent);
```

### 1.3 evaluation_jobs

Tracks each hourly batch evaluation cycle.

```sql
CREATE TABLE evaluation_jobs (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id                 UUID NOT NULL UNIQUE,

    -- Counts
    items_fetched            INTEGER DEFAULT 0,
    items_deduplicated       INTEGER DEFAULT 0,
    items_auto_applied       INTEGER DEFAULT 0,
    items_auto_rejected      INTEGER DEFAULT 0,
    items_llm_evaluated      INTEGER DEFAULT 0,
    corrections_generated    INTEGER DEFAULT 0,
    corrections_applied      INTEGER DEFAULT 0,

    -- Status
    status                   VARCHAR(20) DEFAULT 'pending'
                                 CHECK (status IN ('pending','running','completed','failed')),
    started_at               TIMESTAMPTZ,
    completed_at             TIMESTAMPTZ,
    error_message            TEXT,

    -- Economics
    llm_tokens_used          INTEGER DEFAULT 0,
    llm_tokens_saved         INTEGER DEFAULT 0,
    llm_calls_made           INTEGER DEFAULT 0,

    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ej_status_created ON evaluation_jobs (status, created_at);
```

### 1.4 correction_recommendations

Proposed graph mutations generated by LLM evaluation or auto-routing.

```sql
CREATE TABLE correction_recommendations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id         UUID REFERENCES feedback_records(id),
    evaluation_job_id   UUID REFERENCES evaluation_jobs(id),

    correction_type     VARCHAR(50) NOT NULL,
    target_entity       VARCHAR(255),
    target_entity_id    VARCHAR(255),
    target_type         VARCHAR(50),

    cypher_mutation     TEXT NOT NULL,
    confidence_score    FLOAT NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    reasoning           TEXT,

    repair_class        VARCHAR(5),
    status              VARCHAR(20) DEFAULT 'pending'
                            CHECK (status IN (
                                'pending','approved','applied','rejected','rolled_back'
                            )),

    applied_at          TIMESTAMPTZ,
    applied_by          VARCHAR(100),
    rolled_back_at      TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cr_feedback_id   ON correction_recommendations (feedback_id);
CREATE INDEX idx_cr_status        ON correction_recommendations (status);
CREATE INDEX idx_cr_confidence    ON correction_recommendations (confidence_score);
CREATE INDEX idx_cr_entity        ON correction_recommendations (target_entity_id);
```

### 1.5 correction_audit_trail

Immutable audit record for every graph change. Never deleted — 7-year retention.

```sql
CREATE TABLE correction_audit_trail (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    correction_id    UUID NOT NULL REFERENCES correction_recommendations(id),

    action           VARCHAR(30) NOT NULL,
    cypher_executed  TEXT NOT NULL,
    before_state     JSONB,
    after_state      JSONB,
    entities_affected JSONB DEFAULT '[]',

    operator         VARCHAR(100) NOT NULL,
    performed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata         JSONB DEFAULT '{}'
);

CREATE INDEX idx_cat_correction_id ON correction_audit_trail (correction_id);
CREATE INDEX idx_cat_performed_at  ON correction_audit_trail (performed_at);
CREATE INDEX idx_cat_operator      ON correction_audit_trail (operator);
```

### 1.6 router_decisions

Audit log for every Adaptive Router execution.

```sql
CREATE TABLE router_decisions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_id          UUID NOT NULL,
    router_version          VARCHAR(40) NOT NULL,
    policy_pack_version     VARCHAR(40),
    decision_timestamp      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    applicability_inputs    JSONB DEFAULT '{}',
    applicable_controls     JSONB DEFAULT '[]',
    mandatory_controls      JSONB DEFAULT '[]',
    signal_dimensions       JSONB DEFAULT '{}',
    evidence_status         VARCHAR(30),
    active_incident_matches JSONB DEFAULT '[]',

    selected_evaluators     JSONB DEFAULT '[]',
    skipped_evaluators      JSONB DEFAULT '[]',
    stop_reason             VARCHAR(30),
    escalation_reason       VARCHAR(60),

    token_budget_band       VARCHAR(5),
    actual_tokens_used      INTEGER DEFAULT 0,
    actual_sync_latency_ms  INTEGER,
    actual_async_latency_ms INTEGER
);

CREATE INDEX idx_rd_interaction_id ON router_decisions (interaction_id);
CREATE INDEX idx_rd_timestamp      ON router_decisions (decision_timestamp);
CREATE INDEX idx_rd_stop_reason    ON router_decisions (stop_reason);
```

### 1.7 source_manifests

Health ledger for all source documents in the RAG pipeline.

```sql
CREATE TABLE source_manifests (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id                VARCHAR(255) NOT NULL,
    source_version           VARCHAR(100) NOT NULL,
    content_hash             VARCHAR(64) NOT NULL,
    authority_tier           SMALLINT NOT NULL CHECK (authority_tier BETWEEN 1 AND 6),
    effective_from           DATE NOT NULL,
    effective_to             DATE,

    parser_version           VARCHAR(40),
    chunker_version          VARCHAR(40),
    expected_chunk_count     INTEGER NOT NULL,
    chunk_hashes             JSONB DEFAULT '[]',

    embedding_model          VARCHAR(100),
    embedding_model_version  VARCHAR(40),
    embedded_chunk_count     INTEGER DEFAULT 0,

    taxonomy_version         VARCHAR(40),
    graph_extractor_version  VARCHAR(40),
    expected_node_count      INTEGER DEFAULT 0,
    expected_edge_count      INTEGER DEFAULT 0,

    ingestion_timestamp      TIMESTAMPTZ NOT NULL,
    last_health_check        TIMESTAMPTZ,
    health_status            VARCHAR(20) DEFAULT 'unknown',

    UNIQUE (source_id, source_version)
);

CREATE INDEX idx_sm_source_id    ON source_manifests (source_id);
CREATE INDEX idx_sm_health       ON source_manifests (health_status);
CREATE INDEX idx_sm_effective    ON source_manifests (effective_from, effective_to);
```

---

## 2. Python Dataclass Schemas

Key domain objects used across all pipeline modules.

```python
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import date, datetime
from uuid import UUID


# ── Feedback ────────────────────────────────────────────────────────────────

@dataclass
class FeedbackRequest:
    response_id:       str
    rating:            int           # 1–5
    feedback_type:     Optional[str] = None
    entity_name:       Optional[str] = None
    comment:           Optional[str] = None
    highlighted_span:  Optional[dict] = None
    correction:        Optional[str] = None


@dataclass
class FeedbackRecord:
    id:                str
    response_id:       str
    interaction_id:    str
    rating:            int
    feedback_type:     Optional[str]
    entity_name:       Optional[str]
    comment:           Optional[str]
    ner_tags:          list[dict]    = field(default_factory=list)
    sentiment:         Optional[dict] = None
    intent:            Optional[str] = None
    quality_score:     Optional[float] = None
    status:            str           = "pending"
    actor_role:        str           = "user"
    created_at:        datetime      = field(default_factory=datetime.utcnow)


# ── Evidence Pack ────────────────────────────────────────────────────────────

@dataclass
class D0ResponseFinalization:
    response_id:               str
    interaction_id:            str
    conversation_id:           str
    timestamp:                 datetime
    response_status:           str
    model_id:                  str
    model_version:             str
    generation_config_version: str
    prompt_template_version:   str
    response_text:             str
    response_structure:        str
    citations_shown:           list[dict]
    disclosures_shown:         list[dict]
    guardrail_state:           str
    generation_latency_ms:     int
    input_tokens:              int
    output_tokens:             int
    tool_calls:                list[dict]
    tool_failures:             list[dict]
    fallback_used:             bool
    truncation_flag:           bool
    response_hash:             str


@dataclass
class D2DerivedMetrics:
    retrieval_count:           int
    citation_count:            int
    citation_coverage:         float
    source_age_days:           int
    highest_source_authority:  str
    duplicate_source_ratio:    float
    vector_graph_overlap:      float
    bm25_vector_overlap:       float
    missing_expected_source:   bool
    context_truncation:        bool
    source_version_mismatch:   bool
    retrieval_score_min:       float
    retrieval_score_mean:      float


@dataclass
class Claim:
    entity_id:      str
    product_id:     str
    attribute:      str
    value:          Any
    valid_from:     date
    valid_to:       Optional[date]
    observed_at:    datetime
    source_id:      str
    source_version: str
    confidence:     float = 1.0


# ── Evaluation ───────────────────────────────────────────────────────────────

@dataclass
class EvaluationPacket:
    """Minimal evidence packet sent to LLM judge (E4). Never the full EvidencePack."""
    evaluation_id:          str
    question:               str
    disputed_claims:        list[Claim]
    selected_evidence:      list[dict]
    deterministic_findings: list[dict]
    semantic_findings:      list[dict]
    evaluation_instruction: str
    token_budget:           int


@dataclass
class RouterDecision:
    router_decision_id:      str
    interaction_id:          str
    router_version:          str
    policy_pack_version:     str
    decision_timestamp:      datetime
    applicability_inputs:    dict
    applicable_controls:     list[str]
    mandatory_controls:      list[str]
    signal_dimensions:       dict
    evidence_status:         str
    active_incident_matches: list[str]
    selected_evaluators:     list[dict]
    skipped_evaluators:      list[dict]
    stop_reason:             str
    escalation_reason:       Optional[str]
    token_budget_band:       str
    actual_tokens_used:      int
    actual_sync_latency_ms:  int


# ── Failure & Repair ─────────────────────────────────────────────────────────

@dataclass
class FailureObservation:
    id:                 str
    interaction_id:     str
    response_id:        str
    failure_family:     str       # F01–F14
    subtype:            str
    axis_a_what:        str
    axis_b_how:         str
    axis_c_origin:      str
    axis_d_heal:        str
    confidence:         float
    evidence_ids:       list[str]
    evaluator_id:       str
    evaluator_version:  str
    incident_id:        Optional[str]
    created_at:         datetime


@dataclass
class RepairCandidate:
    id:                  str
    failure_observation_ids: list[str]
    root_cause_id:       str
    recipe_id:           str
    affected_entities:   list[str]
    proposed_changes:    list[dict]
    repair_class:        str       # R0–R5
    blast_radius_scope:  str
    validation_plan:     str
    rollback_plan:       str
    approval_required:   bool
    status:              str       = "pending"
```

---

## 3. API Contracts

### 3.1 POST /api/feedback

```
Request:
  Content-Type: application/json
  Body: FeedbackRequest (see §2)

Response 202:
  {
    "feedback_id": "uuid",
    "status":      "recorded",
    "evaluation_status": "pending"
  }

Response 400:
  { "error": "validation_error", "detail": "..." }

Response 404:
  { "error": "response_not_found", "detail": "response_id does not exist" }

Latency SLA: p99 < 100ms
```

### 3.2 GET /api/feedback/{feedback_id}

```
Response 200:
  {
    "feedback_id":        "uuid",
    "response_id":        "uuid",
    "rating":             4,
    "status":             "applied",
    "quality_score":      0.82,
    "intent":             "correction",
    "created_at":         "2026-08-19T10:23:44Z",
    "evaluated_at":       "2026-08-19T11:00:12Z",
    "correction_id":      "uuid"   // null if not yet applied
  }
```

### 3.3 GET /api/feedback/stats

```
Response 200:
  {
    "period_hours":       24,
    "total_received":     342,
    "pending":            18,
    "applied":            89,
    "rejected":           211,
    "auto_applied":       34,
    "llm_evaluated":      97,
    "avg_quality_score":  0.61,
    "avg_confidence":     0.83,
    "tokens_used":        87420,
    "tokens_saved":       712000,
    "last_cycle_at":      "2026-08-19T11:00:00Z",
    "last_cycle_duration_sec": 187
  }
```

### 3.4 POST /api/corrections/{id}/rollback

```
Request:
  { "reason": "string" }

Response 200:
  { "correction_id": "uuid", "status": "rolled_back", "rolled_back_at": "..." }

Response 409:
  { "error": "cannot_rollback", "detail": "correction not in applied state" }
```

### 3.5 GET /api/health

```
Response 200:
  {
    "status":           "healthy",
    "components": {
      "postgresql":     "healthy",
      "redis":          "healthy",
      "neo4j_context":  "healthy",
      "neo4j_failure":  "healthy",
      "faiss":          "healthy",
      "scheduler":      "running",
      "last_cycle_at":  "2026-08-19T11:00:00Z"
    },
    "pending_feedback": 18,
    "active_incidents": 0
  }
```

---

## 4. Event Schemas

Internal events published to the event bus after key lifecycle points.

### 4.1 FeedbackRecorded

```python
@dataclass
class FeedbackRecordedEvent:
    event_type:    str = "feedback.recorded"
    feedback_id:   str
    response_id:   str
    rating:        int
    quality_score: float
    intent:        str
    timestamp:     datetime
```

### 4.2 EvidencePackCreated

```python
@dataclass
class EvidencePackCreatedEvent:
    event_type:       str = "evidence_pack.created"
    response_id:      str
    interaction_id:   str
    evidence_status:  str   # SUFFICIENT | PARTIAL | MISSING | CONFLICTING
    source_count:     int
    truncation_flag:  bool
    timestamp:        datetime
```

### 4.3 CorrectionApplied

```python
@dataclass
class CorrectionAppliedEvent:
    event_type:       str = "correction.applied"
    correction_id:    str
    feedback_id:      str
    correction_type:  str
    target_entity_id: str
    confidence_score: float
    repair_class:     str
    operator:         str   # "system" or user_id
    timestamp:        datetime
```

### 4.4 EvaluationCycleCompleted

```python
@dataclass
class EvaluationCycleCompletedEvent:
    event_type:           str = "evaluation_cycle.completed"
    job_id:               str
    items_fetched:        int
    corrections_applied:  int
    llm_tokens_used:      int
    llm_tokens_saved:     int
    duration_sec:         int
    timestamp:            datetime
```

### 4.5 HealthAlertRaised

```python
@dataclass
class HealthAlertEvent:
    event_type:    str = "health.alert"
    source_id:     str
    alert_type:    str   # STALE | MISSING_CHUNKS | VERSION_MISMATCH | ...
    recipe_id:     str   # suggested repair recipe
    severity:      str   # critical | high | medium | low
    timestamp:     datetime
```

---

## 5. Neo4j Schema

### 5.1 Context Graph (production serving)

**Node labels and key properties:**

```cypher
// AMC entity nodes
(:Scheme { id, name, isin, scheme_code, amc_id, category, sub_category })
(:Plan   { id, scheme_id, plan_type, option_type })
(:AMC    { id, name, sebi_reg_no, country })
(:Index  { id, name, provider, asset_class })
(:FundManager { id, name, amc_id, sebi_reg_no })
(:Document    { id, source_id, source_version, doc_type, effective_from, effective_to })

// Factual edges — all carry provenance
(s:Scheme)-[:MANAGED_BY {
    source_id, source_version, effective_from, effective_to,
    extraction_method, ingestion_timestamp
}]->(a:AMC)

(s:Scheme)-[:BENCHMARKED_AGAINST {
    source_id, source_version, effective_from, effective_to
}]->(i:Index)

(s:Scheme)-[:HAS_RISK_LEVEL {
    value,              // e.g. "Very High"
    source_id, source_version, effective_from, effective_to
}]->(riskometer)

(s:Scheme)-[:HAS_FACT {
    attribute,          // NAV | TER | AUM | exit_load | ...
    value,
    unit,
    valid_from, valid_to,
    source_id, source_version,
    observed_at
}]->(s)   // self-referential for scalar facts
```

### 5.2 Failure-Attribution Graph (separate instance)

```cypher
// Failure nodes
(:Interaction { id, timestamp })
(:Response    { id, interaction_id, model_version })
(:Claim       { id, response_id, attribute, value, claim_type })
(:Feedback    { id, response_id, rating, intent, quality_score })
(:FailureObservation { id, failure_family, subtype, confidence, axis_a, axis_b, axis_c, axis_d })
(:RootCause   { id, attribution_status, attribution_method, confidence })
(:Incident    { id, first_seen, last_seen, status, frequency, severity })
(:RepairCandidate { id, repair_class, blast_radius, status })
(:DeploymentChange { id, deployed_at, deployed_by })

// Key relationships
(:Response)-[:CONTAINS]->(:Claim)
(:Feedback)-[:REPORTS]->(:FailureObservation)
(:FailureObservation)-[:CORRELATED_WITH]->(:Incident)
(:Incident)-[:HAS_ROOT_CAUSE]->(:RootCause)
(:RepairCandidate)-[:ADDRESSES]->(:RootCause)
(:DeploymentChange)-[:IMPLEMENTS]->(:RepairCandidate)
```

---

## 6. Redis Key Patterns

| Key Pattern | Value | TTL | Invalidated By |
|---|---|---|---|
| `evidence:{response_id}` | D2 JSON payload | 3600s | Source update affecting any referenced source |
| `graph_ctx:{hash(entity_ids)}` | Neo4j subgraph snapshot | 3600s | Any correction applied to affected entities |
| `few_shot:{feedback_type}` | Few-shot example list | 86400s | Manual invalidation on example update |
| `eval_result:{interaction_id}` | Cached evaluator finding | 1800s | Not invalidated — used for deduplication only |
| `incident_active` | Set of active incident IDs | No TTL | Incident resolution event |

---

*Previous: [LLD-07 — Compliance Plane](./LLD-07-COMPLIANCE-PLANE.md)*  
*This is the final LLD document. For the visual presentation, see [AMC-LLD-PRESENTATION.html](../AMC-LLD-PRESENTATION.html).*


---

## 7. Component Architecture Cross-Reference

> Added from AMC_COMPONENT_ARCHITECTURE.html — August 2026

### Table-to-Phase Mapping

Every PostgreSQL table is written and read by specific pipeline phases. This matrix shows the data flow across the 8 phases.

| Table | Written By (Phase) | Read By (Phase) | Primary Key | FK Dependencies | Retention |
|---|---|---|---|---|---|
| `evidence_packs` | Phase 1 (D0–D3 async persist) | Phase 2 (validation), Phase 4 (enrichment), Phase 5 (evaluation) | `id` UUID | None | 90d operational / 7yr compliance |
| `feedback_records` | Phase 2 (sync INSERT + background UPDATE) | Phase 4 (fetch pending), Phase 8 (archive) | `id` UUID | `response_id → evidence_packs.response_id` | 90d rolling |
| `evaluation_jobs` | Phase 4 (create at cycle start) | Phase 4 (update progress), Phase 8 (read metrics) | `id` UUID | None | 90d |
| `correction_recommendations` | Phase 5 (LLM eval output) | Phase 6 (apply corrections) | `id` UUID | `feedback_id → feedback_records.id` | 90d |
| `correction_audit_trail` | Phase 6 (inside Neo4j transaction) | Phase 6 (rollback), compliance review | `id` UUID | `correction_id → correction_recommendations.id` | **7yr (never deleted)** |
| `router_decisions` | Phase 4–5 (async, post-routing) | Compliance audit, operations review | `id` UUID | None | 90d |
| `source_manifests` | Ingestion pipeline (pre-Phase 1) | Phase 4 (health check), Phase 7 (diff) | `id` UUID | None | Indefinite |

### Redis Key Lifecycle

| Key Pattern | Created By | Read By | Invalidated By | TTL |
|---|---|---|---|---|
| `evidence:{response_id}` | Phase 1 (D2 async cache) | Phase 5 (evaluator access) | Phase 7 (post-correction) | 3600s |
| `graph_ctx:{hash}` | Phase 5 (batch builder, on miss) | Phase 5 (batch builder, on hit) | Phase 7 (per corrected entity) | 3600s |
| `few_shot:{feedback_type}` | Pre-computed (manual trigger) | Phase 5 (batch builder) | Manual invalidation only | 86400s |
| `incident_active` | Failure-Attribution Graph service | Phase 4 (incident matcher R4) | Incident resolution event | No TTL |
| `eval_result:{interaction_id}` | Phase 5 (evaluator cache) | Phase 5 (deduplication check) | Not invalidated | 1800s |

### Event Schema → Consumer Map

| Event | Emitted By | Consumer(s) | Phase |
|---|---|---|---|
| `feedback.recorded` | Phase 2 (feedback endpoint) | Monitoring dashboard, webhook subscribers | 2 |
| `evidence_pack.created` | Phase 1 (EvidencePack Creator) | Monitoring, compliance health check | 1 |
| `correction.applied` | Phase 6 (graph corrector) | Phase 7 trigger (cache invalidation), monitoring | 6→7 |
| `evaluation_cycle.completed` | Phase 8 (orchestrator cleanup) | Monitoring dashboards, cost tracking | 8 |
| `health.alert` | Phase 8 (source manifest health check) | RAG Health Engine, operations | 8 |

### Neo4j Schema — Provenance Edge Properties (Required on Every Factual Edge)

All factual edges in the Context Graph **must** carry these properties. Missing any field is a first-class data quality failure (F13/R011 MissingProvenance).

| Property | Type | Required | Description |
|---|---|---|---|
| `source_id` | string | **Yes** | Canonical source document ID |
| `source_version` | string | **Yes** | Version of that source at extraction time |
| `effective_from` | date | **Yes** | When this fact became valid |
| `effective_to` | date or null | **Yes** | When it expired; null = currently active |
| `extraction_method` | string | **Yes** | rule / extractor / llm / correction |
| `ingestion_timestamp` | datetime | **Yes** | When the edge was written to the graph |
| `confidence` | float [0,1] | Recommended | Extraction confidence |

### API Response SLAs

| Endpoint | p50 Target | p99 Target | Error Handling |
|---|---|---|---|
| `POST /api/feedback` | < 20ms | < 100ms | 400 (validation), 404 (response_not_found) |
| `GET /api/feedback/{id}` | < 30ms | < 200ms | 404 (not found) |
| `GET /api/feedback/stats` | < 50ms | < 500ms | 200 with stale data if PG slow |
| `POST /api/corrections/{id}/rollback` | < 100ms | < 1s | 409 (not in applied state) |
| `GET /api/health` | < 20ms | < 100ms | 503 on critical component failure |
| `POST /api/query` (full query) | < 2s | < 5s | 503 on retrieval failure, safe fallback |

*See [AMC_COMPONENT_ARCHITECTURE.html](../AMC_COMPONENT_ARCHITECTURE.html) — Phase 3 (PostgreSQL Buffer) tab for the full interactive table reference.*
