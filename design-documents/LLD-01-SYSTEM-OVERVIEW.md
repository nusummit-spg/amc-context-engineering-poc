# LLD-01 — System Overview

**Document:** LLD-01  
**Version:** 1.0  
**Depends on:** LLD-00 (index, glossary)  
**Read next:** LLD-02 (Evidence Capture)

---

## 1. Problem Statement

The AMC chatbot answers questions about mutual funds — NAV, TER, performance, risk classification, benchmarks, fund managers. These answers must be:

1. **Factually accurate** — numeric values match authoritative sources at the time of the query
2. **Evidentially grounded** — every claim has a traceable source
3. **Compliance-aware** — advice boundaries, disclosure requirements, and jurisdiction rules are respected
4. **Self-improving** — user corrections feed back into the knowledge graph without requiring manual engineering for routine fixes

The core engineering challenge is that a naive implementation either:
- Burns excessive LLM tokens evaluating every response individually (unaffordable at scale), or
- Lets user feedback directly mutate the knowledge graph without validation (unsafe)

This design resolves both by separating concerns into four cooperating control planes, with deterministic processing handling the majority of cases cheaply.

---

## 2. Design Philosophy

The governing hierarchy, in priority order:

```
PREVENT     — deterministic invariants catch problems before they reach users
    ↓
DETECT      — cheap telemetry and rules identify issues at zero token cost
    ↓
CONTAIN     — evidence sufficiency check blocks premature adjudication
    ↓
DIAGNOSE    — structured root-cause attribution, deterministic where possible
    ↓
REPAIR ELIGIBILITY — not every confirmed defect is automatically fixable
    ↓
VALIDATE    — shadow environment before any production change
    ↓
CONTROLLED HEAL — atomic promotion with blast-radius bounds
```

**The system should become less LLM-dependent over time, not more.** Every novel failure that is understood gets converted into a deterministic rule or repair recipe. The token cost per interaction decreases as the rule library grows.

---

## 3. Four Control Planes

The system is structured as four cooperating planes. Each has a single, well-defined responsibility. They must not be collapsed into one component.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AMC CHATBOT / PLATFORM                              │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ INTERACTION EVENT
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                  ▼
    ┌──────────────────┐ ┌──────────────┐ ┌─────────────────┐
    │  DOMAIN /        │ │  COMPLIANCE  │ │  EVALUATION     │
    │  TAXONOMY        │ │  CONTROL     │ │  CONTROL        │
    │  INTELLIGENCE    │ │  PLANE       │ │  PLANE          │
    │                  │ │              │ │                  │
    │  AMC Taxonomy    │ │  Jurisdiction│ │  Adaptive Router │
    │  entity · intent │ │  Policy Packs│ │  E0–E5 ladder   │
    │  claim · evidence│ │  C01–C14     │ │  Evaluator      │
    │  failure · repair│ │  controls    │ │  Registry       │
    └────────┬─────────┘ └──────┬───────┘ └────────┬────────┘
             └──────────────────┼──────────────────┘
                                ▼
                        EVALUATION PLAN
                                │
                                ▼
                           FINDINGS
                                │
                                ▼
                       FAILURE ATTRIBUTION
                                │
                    ┌───────────┼───────────┐
                    ▼                       ▼
          ┌──────────────────┐    ┌──────────────────┐
          │  RAG HEALTH /    │    │  FAILURE-         │
          │  REPAIR PLANE    │    │  ATTRIBUTION      │
          │                  │    │  GRAPH            │
          │  Health Engine   │    │  (separate from   │
          │  Recipe Registry │    │   Context Graph)  │
          │  Shadow Env      │    │                   │
          └──────────────────┘    └──────────────────┘
```

### Plane 1 — Domain / Taxonomy Intelligence

**Answers:** What does this interaction mean? What type of entity, intent, claim, or failure is this?  
**Components:** AMC Taxonomy layers T1–T10 (entity, product, attribute, intent, claim, evidence, interaction-risk, compliance-control-mapping, failure, repair)  
**Must not contain:** Mutable legal obligations or jurisdiction-specific rules (those go in Plane 2)

### Plane 2 — Compliance Control Plane

**Answers:** Which approved controls apply? What must happen before or after delivery?  
**Components:** Jurisdiction Rule Packs (INDIA_SEBI, US_SEC, EU_ESMA, UK_FCA), C01–C14 control families, Applicability Resolver  
**Must not contain:** Domain meaning or system diagnostics

### Plane 3 — Evaluation Control Plane

**Answers:** What needs to be evaluated, how deeply, and at what cost?  
**Components:** Adaptive Evaluation Router, EvidencePack (D0–D3), Evaluator Capability Registry, Failure-Attribution Graph  
**Must not contain:** Production repair logic or compliance rule decisions

### Plane 4 — RAG Health / Repair Plane

**Answers:** Is there a knowledge or retrieval defect? Can it be safely repaired?  
**Components:** RAG Health Engine, Vector Health, Graph Health, Repair Recipe Registry, Shadow Environment, Promotion Gate  
**Must not contain:** User-facing answer serving or compliance decision-making

---

## 4. End-to-End Request Flow

### 4.1 Synchronous Path (user-facing, < 100 ms feedback confirmation)

```
User Query
    │
    ▼
AMC Chatbot — existing retrieval + LLM pipeline
    │
    ▼
Response Generated
    │
    ▼
D0 Response Finalization          ← deterministic, no LLM, ~1ms
    │
    ▼
D1 Interaction Snapshot           ← deterministic, no LLM, ~1ms
    │
    ▼
D2 EvidencePack (frozen)          ← deterministic, no LLM, ~5ms
    │
    ▼
D3 Applicability Context          ← rules/lookup, no LLM, ~1ms
    │
    ▼
Critical Deterministic Intercept  ← hard controls only, ~5–40ms
    │
    ├── PASS  →  Deliver Response (response_id embedded)
    │
    └── FAIL  →  Safe Action / Hold / Refuse
                         │
                         ▼
                    Event Bus (async from here)
```

After delivery, the user can submit feedback. Feedback capture is also synchronous but the pre-classification runs as a background task — HTTP response returns < 100 ms regardless.

### 4.2 Asynchronous Evaluation Path (hourly, no user-facing latency impact)

```
Hourly Orchestrator Trigger
    │
    ▼
Fetch pending feedback from PostgreSQL
    │
    ▼
Evidence Sufficiency Check (per item, from frozen EvidencePack)
    │
    ▼
Adaptive Evaluation Router
    │  R0: Resolve applicability
    │  R1: Mandatory controls
    │  R2: Signal classification
    │  R3: Evidence sufficiency
    │  R4: Incident match check → short-circuit if matched
    │  R5: Select minimum evaluator depth
    │  R6: Apply token/latency budget
    │  R7: Execute evaluators
    │  R8: Apply stop rules
    │  R9: Emit decision log
    │
    ▼
Adjudication
    │
    ▼
Failure Observation → Failure-Attribution Graph
    │
    ▼
Root Cause Attribution
    │
    ▼
Repair Eligibility Assessment (R0–R5)
    │
    ├── R0       → Close and monitor
    ├── R1/R2    → Shadow repair → regression → promote
    ├── R3       → Governance approval queue
    ├── R4       → Agent / SME investigation
    └── R5       → Human / compliance only
```

### 4.3 RAG Health Path (continuous background, triggered by health ledger diff)

```
SourceManifest (expected)
    vs
Vector DB state (actual)
    vs
Context Graph state (actual)
    │
    ▼
Diff detected → Repair Recipe lookup
    │
    ▼
Shadow repair execution
    │
    ▼
Regression + compliance + blast-radius tests
    │
    ▼
Atomic promotion or rollback
    │
    ▼
Post-heal monitoring (24h / 7d window)
```

---

## 5. Key Boundaries and Non-Goals

### 5.1 What this system IS

- A governed feedback loop that improves the knowledge graph from user corrections
- A compliance-aware evaluation control plane for a regulated AMC context
- A self-healing RAG system where known failures map to deterministic recipes
- An audit trail for all evaluation, repair, and promotion decisions

### 5.2 What this system IS NOT

- A real-time answer quality filter (the Critical Intercept is the only synchronous gate)
- A replacement for human compliance review (R4/R5 always require humans)
- A generic RAG evaluation framework (it is AMC-domain-specific)
- A self-learning model training pipeline (feedback improves rules and graph; it does not fine-tune the LLM)
- An autonomous agent that rewrites the RAG based on LLM reasoning alone

### 5.3 Hard limits

| Limit | Value | Reason |
|---|---|---|
| Feedback HTTP response | < 100 ms | User experience |
| Synchronous critical intercept | < 40 ms | Response latency budget |
| Evaluation cycle | ~3 min for 500 items | Hourly batch feasibility |
| LLM invocation rate | 2–5% of evaluated interactions | Token cost control |
| Mandatory control bypass | 0 (hard) | Regulatory requirement |
| Human-required bypass | 0 (hard) | Regulatory requirement |
| Feedback → direct graph write | Prohibited | Feedback poisoning prevention |
| Failure graph → answer retrieval | Prohibited | Contamination prevention |

---

## 6. Component Inventory

### Existing (Phase 1 — implemented)

| Module | Responsibility |
|---|---|
| `feedback_collector.py` | HTTP endpoint, NER, sentiment, intent classification, async PostgreSQL write |
| `feedback_processor.py` | Aggregation, semantic deduplication, batch preparation |
| `batch_evaluation.py` | LLM batch evaluation, 25 items/call, structured JSON output |
| `graph_corrector.py` | Neo4j atomic transactions, R1/R2 corrections |
| `cache_manager.py` | FAISS, Redis, entity resolver, Neo4j traversal cache invalidation |
| `evaluation_orchestrator.py` | APScheduler cron, 6-step cycle coordination |
| `postgres_client.py` | PostgreSQL connection pool, DDL, query helpers |
| `api/routes/feedback.py` | FastAPI router, POST /feedback, GET /feedback/stats |

### Phase 2 additions (designed)

| Module | Responsibility |
|---|---|
| `adaptive_router.py` | 9-stage routing engine, evaluator selection, decision log |
| `evaluator_registry.py` | Capability registry, evaluator lookup by failure family |
| `evidence_pack.py` | D0–D3 creation, freezing, Redis cache, retrieval |
| `failure_attribution.py` | Failure graph writes, incident correlation, root cause |
| `compliance_resolver.py` | Applicability resolution, policy pack lookup, control enforcement |

### Phase 3 additions (designed)

| Module | Responsibility |
|---|---|
| `rag_health_engine.py` | Source manifest diff, health check orchestration |
| `vector_health_checker.py` | Completeness, freshness, hash integrity checks |
| `graph_health_checker.py` | Entity, edge, provenance, temporal integrity checks |
| `repair_recipe_registry.py` | Recipe lookup, triggering, execution |
| `shadow_environment.py` | Shadow repair execution, regression test runner |
| `promotion_gate.py` | Blast-radius assessment, approval workflow, atomic promotion |
| `post_heal_monitor.py` | Recurrence, collateral, delta tracking |

---

## 7. Technology Decisions

| Layer | Technology | Rationale |
|---|---|---|
| API | FastAPI | Async-native, BackgroundTasks, Pydantic validation |
| Feedback buffer | PostgreSQL | ACID transactions, JSON support, mature ecosystem |
| Response cache | Redis | Sub-millisecond TTL-based EvidencePack caching |
| Knowledge graph | Neo4j | Property graph, Cypher queries, provenance edges |
| Vector index | FAISS | Local embedding search, surgical chunk invalidation |
| Pre-classification | spaCy + VADER | Lightweight, no LLM tokens, runs synchronously |
| Batch evaluation | Anthropic Claude | Structured output, 25-item batching |
| Scheduling | APScheduler | In-process async cron, no separate queue infrastructure |
| Embeddings | Sentence Transformers | Local semantic deduplication, no API cost |

---

## 8. Data Persistence Summary

| Store | What lives there | Retention |
|---|---|---|
| PostgreSQL | Feedback records, EvidencePack D0–D3, evaluation jobs, correction history, audit trail | 90 days operational; 7 years compliance |
| Redis | EvidencePack D2 hot cache, few-shot example cache, graph context snapshots | 1h TTL (invalidated on source update) |
| Neo4j (Context) | Entities, relationships, source provenance — user-facing answers | Permanent (versioned edges) |
| Neo4j (Failure) | Failure observations, root causes, incidents, repair history | 2 years |
| FAISS | Vector embeddings, chunk metadata | Rebuilt on source change |
| File system / S3 | Source documents, shadow environment snapshots, golden query sets | Indefinite |

---

*Next: [LLD-02 — Evidence Capture](./LLD-02-EVIDENCE-CAPTURE.md)*


---

## 9. Component Architecture Cross-Reference

> Added from AMC_COMPONENT_ARCHITECTURE.html — August 2026

This section maps every major sub-component identified in the in-depth component architecture to its phase, source file, and control plane membership.

### Phase-to-Component Map

| Phase | Component | Source File | Control Plane | Token Cost |
|---|---|---|---|---|
| 1 | Intent Resolver | `app/engine/context_engineering.py` | Plane 1 — Taxonomy | 0 |
| 1 | FAISS Retrieval Engine | `app/engine/faiss_store.py` | Plane 4 — RAG Health | 0 |
| 1 | Neo4j Graph Context | `app/engine/entity_resolver.py` | Plane 4 — RAG Health | 0 |
| 1 | Context Assembly / Reranker | `app/engine/context_engineering.py` | Plane 4 — RAG Health | 0 |
| 1 | LLM Synthesis | `app/core/llm.py` | Plane 3 — Evaluation | Variable |
| 1 | EvidencePack Creator (D0–D3) | `app/engine/evidence_pack.py` | Plane 3 — Evaluation | 0 |
| 1 | Critical Deterministic Intercept | Inline in query route | Plane 2 — Compliance | 0 |
| 1 | Response ID Anchor | UUID in D0.response_id | Plane 3 — Evaluation | 0 |
| 2 | Feedback API Endpoint | `app/api/routes/feedback.py` | Plane 3 — Evaluation | 0 |
| 2 | Input Validator | `app/api/routes/feedback.py` | Plane 3 — Evaluation | 0 |
| 2 | NER Tagger | `app/engine/feedback_collector.py` | Plane 1 — Taxonomy | 0 |
| 2 | Sentiment Scorer (VADER) | `app/engine/feedback_collector.py` | Plane 1 — Taxonomy | 0 |
| 2 | Intent Classifier | `app/engine/feedback_collector.py` | Plane 1 — Taxonomy | 0 |
| 2 | Quality Score Engine | `app/engine/feedback_collector.py` | Plane 3 — Evaluation | 0 |
| 3 | PostgreSQL Buffer (18 tables) | `postgres_client.py` | All planes | 0 |
| 3 | Redis Cache Layer | `app/engine/cache_manager.py` | Plane 3 — Evaluation | 0 |
| 4 | APScheduler Trigger | `app/engine/feedback_processor.py` | Plane 3 — Evaluation | 0 |
| 4 | Aggregation Engine | `app/engine/feedback_processor.py` | Plane 3 — Evaluation | 0 |
| 4 | Semantic Deduplicator | `app/engine/feedback_processor.py` | Plane 3 — Evaluation | 0 |
| 4 | Conditional Router | `app/engine/feedback_processor.py` | Plane 3 — Evaluation | 0 |
| 4 | Batch Builder | `app/engine/feedback_processor.py` | Plane 3 — Evaluation | 0 |
| 5 | Batch Evaluator | `app/engine/batch_evaluation.py` | Plane 3 — Evaluation | Controlled B1–B4 |
| 5 | Graph Context Fetcher | `app/engine/cache_manager.py` | Plane 4 — RAG Health | 0 |
| 5 | Few-Shot Cache | `app/engine/cache_manager.py` | Plane 3 — Evaluation | 0 |
| 5 | Prompt Builder | `app/engine/batch_evaluation.py` | Plane 3 — Evaluation | 0 |
| 5 | Response Parser + Confidence Gate | `app/engine/batch_evaluation.py` | Plane 3 — Evaluation | 0 |
| 6 | Cypher Validator | `app/engine/graph_corrector.py` | Plane 4 — RAG Health | 0 |
| 6 | Neo4j Transaction Manager | `app/engine/graph_corrector.py` | Plane 4 — RAG Health | 0 |
| 6 | Audit Trail Writer | `app/engine/graph_corrector.py` | Plane 2 — Compliance | 0 |
| 6 | Rollback Engine | `app/engine/graph_corrector.py` | Plane 2 — Compliance | 0 |
| 7 | FAISS Chunk Invalidator | `app/engine/cache_manager.py` | Plane 4 — RAG Health | 0 |
| 7 | Redis EvidencePack Invalidator | `app/engine/cache_manager.py` | Plane 3 — Evaluation | 0 |
| 7 | Entity Resolver Cache Invalidator | `app/engine/entity_resolver.py` | Plane 1 — Taxonomy | 0 |
| 7 | Neo4j Traversal Cache Invalidator | `app/engine/cache_manager.py` | Plane 4 — RAG Health | 0 |
| 8 | Post-Heal Monitor | `post_heal_monitor.py` (Phase 3) | Plane 4 — RAG Health | 0 |

### Latency Budget by Phase

| Phase | Max Latency | Latency Type | Notes |
|---|---|---|---|
| Phase 1 — EvidencePack creation | < 10ms | Synchronous | D0–D3 creation, no I/O beyond policy pack lookup |
| Phase 1 — Critical Intercept | < 40ms | Synchronous | Hard compliance controls only |
| Phase 2 — HTTP response | < 100ms | Synchronous | NLP runs as BackgroundTask after response |
| Phase 3 — PostgreSQL write | < 5ms | Async (non-blocking) | INSERT to feedback_records |
| Phase 4–8 — Full evaluation cycle | ~3 min for 500 items | Async | Zero user-facing impact |

### Implementation Status

| Phase | Status | Modules |
|---|---|---|
| Phase 1 — Query path | Complete (existing) | `query.py`, `faiss_store.py`, `entity_resolver.py`, `context_engineering.py`, `llm.py` |
| Phase 1 — EvidencePack | Phase 2 design (pending) | `evidence_pack.py` |
| Phase 2 — Feedback capture | Complete | `feedback_collector.py`, `feedback.py` route |
| Phase 3 — PostgreSQL buffer | Complete | `postgres_client.py` + schema |
| Phase 4 — Orchestration | Complete | `feedback_processor.py` |
| Phase 5 — LLM evaluation | Complete | `batch_evaluation.py` |
| Phase 6 — Graph correction | Complete | `graph_corrector.py` |
| Phase 7 — Cache invalidation | Complete | `cache_manager.py` |
| Phase 8 — Post-heal monitor | Phase 3 design (pending) | `post_heal_monitor.py` |

*See [AMC_COMPONENT_ARCHITECTURE.html](../AMC_COMPONENT_ARCHITECTURE.html) for the full interactive component reference.*
