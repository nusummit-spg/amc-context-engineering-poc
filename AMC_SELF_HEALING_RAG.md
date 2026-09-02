# AMC Self-Healing RAG — Design Document

**Version:** 1.0  
**Status:** Design Baseline  
**Scope:** RAG health engine, 3-level healing, repair recipe registry, shadow validation, vector/graph diagnostics

---

## 1. Core Principle

Self-healing is a **state-reconciliation and reconstruction problem** — not an agentic reasoning problem.

```
WRONG approach:
Evaluator complains → agent rewrites RAG

CORRECT approach:
Feedback / Telemetry
    ↓
Evaluation
    ↓
Diagnosis (deterministic where possible)
    ↓
RAG Health Engine
    ↓
Known failure? → Repair Recipe (deterministic)
Unknown?       → Semantic / LLM / Agent / Human
    ↓
Repair Candidate
    ↓
Shadow Environment (NEVER heal production directly)
    ↓
Regression + Compliance + Blast-Radius Validation
    ↓
Controlled Promotion or Rollback
```

The long-term objective: recurring failures convert into cheap deterministic recipes. The system heals more by running rules and less by running LLMs over time.

---

## 2. Source-of-Truth Architecture

The Vector DB and Context Graph are **reproducible derivatives** of the authoritative source plane:

```
AUTHORITATIVE SOURCE PLANE
Documents · Structured Data · APIs · Regulatory Sources
          │
          ▼
Source Registry
+ Provenance
+ Versions
+ Content Hashes
+ Effective Dates
          │
    ┌─────┴─────┐
    ▼           ▼
Vector DB   Context Graph
    │           │
    └─────┬─────┘
          ▼
    RAG Retrieval
    (Hybrid: BM25 + Vector + Graph)
```

Because they are derivatives, healing is primarily:

```
EXPECTED STATE (from source registry)
      vs
ACTUAL STATE   (from index/graph)
      ↓
DIFF
      ↓
Repair Recipe
```

---

## 3. RAG Health Ledger

Every derived object carries enough provenance for health validation:

```
SourceManifest
│
├── source_id
├── source_version
├── content_hash              SHA-256
├── authority                 tier 1–6 (see AMC_EVIDENCE_PACK.md)
├── effective_from
├── effective_to
│
├── parser_version
├── chunker_version
├── chunk_count
├── chunk_hash[]
│
├── embedding_model
├── embedding_model_version
├── embedded_chunk_count
│
├── taxonomy_version
├── graph_extractor_version
├── graph_node_count
├── graph_edge_count
└── ingestion_timestamp
```

Health validation is simply:

```
SourceManifest (expected)
    vs
Vector DB state (actual chunk count, hash spot-checks)
    vs
Context Graph state (actual node/edge counts for this source)
    ↓
Diff → Repair Recipe selection
```

---

## 4. Three Levels of Self-Healing

### Level 1 — Mechanical Healing (near-fully deterministic, LLM tokens = 0)

Operations:
- Retry failed ingestion
- Restore from backup snapshot
- Reconstruct from canonical source
- Re-embed missing or stale chunks
- Re-index missing documents
- Deduplicate chunks with same content hash
- Repair metadata mismatch (parser/chunker/version fields)

**Target:** Almost fully deterministic. Triggered by source manifest diff or health telemetry. No human involvement for standard cases.

### Level 2 — Knowledge-Structure Healing (mostly deterministic)

Operations:
- Entity canonicalization (merge duplicate entity nodes)
- Graph constraint repair (enforce cardinality, required relationships)
- Source/version reconciliation (update derived edges to reflect new source version)
- Temporal relationship management (expire stale edges, activate current)
- Taxonomy consistency enforcement (node types match taxonomy schema)

**Target:** Mostly deterministic where stable identifiers and structured sources exist. Semantic involvement only when entity disambiguation cannot be resolved by canonical IDs.

### Level 3 — Semantic Healing (cascade: rules → classifier → LLM → human)

Operations:
- Resolve ambiguous relationship type
- Reconcile conflicting narratives from multiple sources
- Map entity to missing ontology node
- Resolve unclear entity when canonical ID is absent
- Fix semantic chunking boundary problem

**Escalation:**
```
Rules
  ↓
Small semantic model / classifier
  ↓
Bounded LLM (with constrained token budget)
  ↓
Agent (when multi-step investigation required)
  ↓
Human SME (when genuinely ambiguous)
```

---

## 5. Repair Recipe Registry

Instead of letting an agent invent a repair each time, maintain explicit recipes. Every recipe is versioned, tested, and approved before production use.

```
RepairRecipe
│
├── recipe_id
├── recipe_version
├── name
├── description
├── failure_family           F01–F14 (from AMC_FAILURE_TAXONOMY.md)
├── detection_rule           what triggers this recipe
├── severity                 critical | high | medium | low
├── auto_repair_allowed      boolean
├── approval_required        boolean (R-class from repair eligibility)
│
├── repair_procedure         step-by-step instructions / code reference
├── validation_tests[]       test IDs that must pass before promotion
├── rollback_procedure       how to undo this repair
│
├── llm_required             boolean
├── human_required           boolean
├── estimated_duration_min
└── blast_radius_scope       single_chunk | document | entity | relationship | index | graph
```

### Standard Recipe Catalogue

| Recipe ID | Name | Trigger | Repair | LLM? |
|---|---|---|---|---|
| **R001** | MissingVector | `source_chunk_count ≠ vector_chunk_count` | Re-embed missing chunk, validate hash | Never |
| **R002** | StaleEmbedding | `source_content_hash ≠ embedded_content_hash` | Rechunk changed section → re-embed affected chunks only | Never |
| **R003** | DuplicateChunk | Duplicate `content_hash` found in vector index | Deduplicate, keep highest authority version | Never |
| **R004** | MetadataMismatch | Metadata fields don't match source manifest | Rebuild metadata from source registry | Never |
| **R005** | MissingSource | Known authoritative source absent from index | Re-ingest from source registry | Never |
| **R006** | RetrievalRegression | BM25/Graph find source, Vector consistently misses it | Embedding model drift investigation → selective re-embed | Never |
| **R007** | BrokenGraphEdge | Source field changed (e.g. benchmark, fund manager) | Expire old edge → create new edge with source/version/date | Never |
| **R008** | OrphanGraphNode | Entity node with no relationships | Re-run entity extraction for source document | Optional |
| **R009** | SourceVersionMismatch | Vector derived from V17, Graph derived from V18 | Selective re-embed to align versions | Never |
| **R010** | EntityDuplicate | Two nodes share canonical ID, ISIN, or scheme code | Merge nodes, consolidate relationships, update provenance | Classifier |
| **R011** | MissingProvenance | Graph edge has no `source_id` or `effective_date` | Trace from extraction logs, backfill provenance | Never |
| **R012** | TemporalConflict | Two active edges for same attribute with same entity | Expire older by `effective_date`, keep authoritative | Never |

**Key benefit:** Every known failure class has a deterministic operational recipe. An agent is never invoked for these cases.

---

## 6. Vector DB Health Checks

### 6.1 Completeness Checks

```python
# Source says 132 chunks exist for document D-42
expected_chunks = source_manifest.get_chunk_count("D-42")

# Vector DB has 131
actual_chunks = vector_store.count_chunks(source_id="D-42")

if actual_chunks < expected_chunks:
    missing = identify_missing_chunks("D-42")
    trigger_recipe("R001", missing_chunks=missing)
```

### 6.2 Freshness Checks

```python
source_hash_current   = source_registry.get_content_hash(source_id, version="latest")
source_hash_embedded  = vector_store.get_embedded_hash(source_id)

if source_hash_current != source_hash_embedded:
    changed_sections = diff_source_versions(source_id)
    trigger_recipe("R002", affected_chunks=changed_sections)
    # Only rechunk/re-embed changed sections — not the whole document
```

### 6.3 Index Health Checks

```
source_completeness:       % of expected chunks present
embedding_completeness:    % of indexed chunks with valid embeddings
version_consistency:       are all chunks derived from the same source version?
hash_integrity:            do stored content hashes match current source?
duplicate_ratio:           % of chunks with duplicate content hashes
metadata_integrity:        % of chunks with complete, valid metadata
```

---

## 7. Context Graph Health Checks

### 7.1 Entity Integrity

```
Scheme ID unique?                    → R010 if duplicate
ISIN unique where applicable?        → R010 if duplicate
Fund house node exists?              → R008 if orphan
Benchmark node valid?                → R007 if stale reference
Entity type in taxonomy?             → F01 root cause if not
```

### 7.2 Relationship Integrity

```
Scheme ──MANAGED_BY──► AMC              exists and current?
Scheme ──BENCHMARKED_AGAINST──► Index   exists and current?
Scheme ──HAS_RISK_LEVEL──► Riskometer   exists and current?
Scheme ──HAS_DOCUMENT──► SID/KIM        exists and current?
```

### 7.3 Provenance Integrity

Every factual edge should carry:
- `source_id` — which source document
- `source_version` — which version of that source
- `effective_from` — when this fact became valid
- `effective_to` — when it expired (null = currently active)
- `extraction_method` — how it was derived
- `ingestion_timestamp`

An edge without provenance is a **first-class data quality problem** (R011).

### 7.4 Temporal Integrity

```
Two active BENCHMARKED_AGAINST edges for same scheme?   → R012 TemporalConflict
Old fund manager still listed as current?               → R007 BrokenGraphEdge
NAV value with no effective_date?                       → R011 MissingProvenance
```

### 7.5 Structural Integrity

```
Orphan nodes (no relationships)?          → R008
Dangling relationships (deleted endpoint)?→ constraint enforcement
Unexpected disconnected components?       → investigation
Missing mandatory paths?                  → R008 or R007
```

---

## 8. Hybrid Retrieval as a Diagnostic Sensor

Use disagreement between retrieval mechanisms as a health signal:

```
         QUERY
           │
  ┌────────┼────────┐
  ▼        ▼        ▼
BM25     VECTOR   GRAPH
  │        │        │
  └────────┼────────┘
           ▼
    Agreement Matrix
```

**Metrics to track:**

| Metric | Healthy Signal | Degradation Signal |
|---|---|---|
| `BM25 ∩ Vector` | High overlap | Vector missing lexically clear source |
| `Vector ∩ Graph` | High overlap for entities | Graph / embedding divergence |
| `Top-K rank disagreement` | Low | Reranking degradation |
| `Expected entity coverage` | All key entities retrieved | Entity retrieval gap |
| `Authoritative source in Top-3` | Baseline % | Drift below baseline |

**Example diagnostic:**
```
BM25 retrieves authoritative source → ✓
Vector misses it                    → ✗
Graph finds entity node             → ✓

Conclusion: Vector retrieval degradation → R002 or R006 investigation
LLM tokens needed: 0
```

---

## 9. Query Cohort Health Monitoring

Build deterministic cohorts based on AMC taxonomy categories:

```
Cohort: Riskometer queries
Baseline (stable period): authoritative source in Top-3 = 98%
Current period:           authoritative source in Top-3 = 71%
    ↓
Retrieval drift alert → R002/R006 investigation
```

Define cohorts per taxonomy intent:
- `NAV_LOOKUP` — current numeric value queries
- `TER_LOOKUP` — expense ratio queries
- `PERFORMANCE_COMPARISON` — fund comparison queries
- `RISKOMETER` — risk classification queries
- `BENCHMARK` — benchmark identification queries
- `FUND_MANAGER` — fund manager queries
- `PORTFOLIO_HOLDINGS` — portfolio queries

For each cohort, track:
- Authoritative source recall (% of queries where canonical source was retrieved Top-K)
- Retrieval latency p50/p95
- Citation integrity rate
- Numeric accuracy rate (spot-checked against structured data)

---

## 10. Shadow Repair — Never Heal Production Directly

```
Production RAG
      │
      ▼
Problem detected by health check / diagnosis
      │
      ▼
Healing Candidate created
      │
      ▼
QUARANTINE / SHADOW ENVIRONMENT
      │
      ▼
Execute repair in shadow
      │
      ▼
Run Regression Query Set
(golden queries + affected cohort queries)
      │
      ▼
Before ↔ After Comparison
(retrieval quality · citation integrity · numeric accuracy · compliance routing)
      │
   ┌──┴──┐
  FAIL   PASS
   │       │
Reject    Approval Gate
   │       │
Rollback  R1/R2: Auto-promote
          R3+:   Governance sign-off required
          │
          ▼
    Atomic Promotion to Production
          │
          ▼
    Post-Change Monitoring
    (recurrence · regressions · compliance routing · tokens · latency)
```

### Shadow Validation Test Categories

| Category | Description | LLM Required? |
|---|---|---|
| Retrieval regression | Does repair change Top-K results for affected queries? | No |
| Golden dataset | Known correct Q&A pairs — do answers remain correct? | No |
| Deterministic numeric | Does repair preserve correct numeric values? | No |
| Citation integrity | Are citations still valid after repair? | No |
| Compliance routing | Does repair affect how the Router classifies interactions? | No |
| Semantic completeness | Are responses still semantically complete? | Conditional |
| Blast-radius check | Did repair unintentionally affect unrelated queries? | No |

### Blast-Radius Assessment

Before any repair, estimate blast radius:

```
single_chunk      — affects 1 chunk, low risk
document          — affects all chunks from one document
entity            — affects all nodes/edges for one entity
relationship_type — affects all edges of one relationship type
index_rebuild     — affects all retrieval, highest risk
graph_schema      — affects routing and compliance, requires R3+
```

For high blast-radius repairs, require:
1. Broader regression query set
2. Extended monitoring period
3. Compliance routing test
4. Governance approval (R3+)

---

## 11. Compliance-Safe Self-Healing Boundary

### MAY be automatically repaired (subject to repair policy and R1/R2 eligibility):

- Rebuild missing embeddings
- Restore index from canonical source
- Refresh source-derived chunks after source update
- Repair deterministic metadata (dates, versions, IDs)
- Expire clearly superseded graph edges
- Recreate known derived relationships with provenance

### Must NEVER be autonomously decided:

- New legal interpretation
- New suitability standard
- New disclosure obligation
- New jurisdiction scope
- Regulatory conflict precedence
- Whether an ambiguous statement is legally permissible

These are always **R4 Investigative** or **R5 Prohibited Auto-Repair** — human and compliance team only.

---

## 12. Post-Healing Monitoring

After every production promotion, track:

```
Monitoring window: 24h standard, 7 days for R3+ repairs

Metrics:
├── failure_recurrence_rate   — did the same failure class reappear?
├── new_failure_rate          — did the repair introduce a new failure type?
├── retrieval_quality_delta   — before vs after for affected cohort
├── compliance_routing_delta  — did any routing decisions change?
├── token_cost_delta          — did evaluation cost change?
└── latency_delta             — did response latency change?
```

If `failure_recurrence_rate > threshold` within the monitoring window → mark repair as `INEFFECTIVE` and escalate.  
If a **new failure family** appears after the repair → mark as `REPAIR_CAUSED_COLLATERAL_DAMAGE` → **rollback**.

---

## 13. Self-Healing KPIs

| KPI | Target |
|---|---|
| `repair_actions_without_llm` | > 90% target |
| `repair_recurrence_rate` | < 5% within 30 days |
| `mean_time_to_repair_hours` | < 2h for R1, < 24h for R2 |
| `shadow_validation_pass_rate` | > 95% |
| `false_repair_rate` | < 1% (repairs that caused new failures) |
| `known_recipe_coverage` | % of observed failures with matching recipe |
| `new_recipe_creation_rate` | Novel failures converted to recipes per month |
| `level_1_vs_level_3_ratio` | Mechanical repairs vs semantic repairs (target: increase L1) |

---

## 14. Integration with Existing HITL Implementation

The self-healing layer builds on the existing implementation:

```
Existing (Phase 1 — complete):
  feedback_collector.py      → captures user signals
  feedback_processor.py      → batches and deduplicates
  batch_evaluation.py        → LLM batch evaluation
  graph_corrector.py         → applies Neo4j corrections (R1/R2 scope)
  cache_manager.py           → invalidates FAISS, Redis, entity resolver caches
  evaluation_orchestrator.py → APScheduler coordination

Phase 3 additions:
  rag_health_engine.py       → source manifest diff, health checks
  vector_health_checker.py   → completeness, freshness, hash integrity
  graph_health_checker.py    → entity/edge/provenance integrity
  repair_recipe_registry.py  → R001–R012 and custom recipes
  shadow_environment.py      → shadow repair execution + regression runner
  promotion_gate.py          → approval workflow + atomic promotion
  post_heal_monitor.py       → recurrence and collateral tracking
```

---

*This document is part of the AMC Unified Feedback, Evaluation & Self-Healing Architecture. See also: `AMC_EVIDENCE_PACK.md`, `AMC_EVALUATION_ROUTER.md`, `AMC_FAILURE_TAXONOMY.md`, `AMC_COMPLIANCE_CONTROL_PLANE.md`.*
