# LLD-06 — Self-Healing RAG

**Document:** LLD-06  
**Version:** 1.0  
**Depends on:** LLD-05 (Failure Taxonomy), LLD-02 (Evidence Capture)  
**Read next:** LLD-07 (Compliance Plane)

---

## 1. Design Principle

Self-healing is a **state-reconciliation and reconstruction problem**, not an agentic reasoning problem.

The Vector DB and Context Graph are reproducible derivatives of the authoritative source plane. When they diverge from their source, the correct action is to recompute the derivative deterministically — not to ask an LLM to reason about what the correct state should be.

```
WRONG mental model:
  Evaluator flags a problem → agent rewrites the RAG

CORRECT mental model:
  Source manifest (expected state)
      vs
  Index / graph (actual state)
      ↓
  Diff → select matching Repair Recipe
      ↓
  Execute in shadow → regression tests
      ↓
  Atomic promotion or rollback
```

The long-term objective: as the Repair Recipe Registry grows, a higher fraction of repairs execute deterministically at zero LLM cost. Level 1 and Level 2 repairs should handle > 90% of cases at maturity.

---

## 2. Source-of-Truth Architecture

```
AUTHORITATIVE SOURCE PLANE
  Regulatory documents · Fund disclosure documents (SID, KIM)
  Structured data feeds (NAV, TER, portfolio) · Internal policies
              │
              ▼
    SOURCE REGISTRY + PROVENANCE
    source_id · source_version · content_hash
    effective_date · authority_tier · ingestion_timestamp
              │
        ┌─────┴──────┐
        ▼            ▼
    VECTOR DB    CONTEXT GRAPH
    (chunks +    (entities +
     embeddings)  relationships)
        │            │
        └─────┬──────┘
              ▼
      HYBRID RAG RETRIEVAL
      BM25 + Vector + Graph
```

Because both serving structures are derivatives, healing always begins with comparing the source registry against the actual index / graph state. This produces a deterministic diff that drives recipe selection.

---

## 3. RAG Health Ledger

Every derived object carries a `SourceManifest` record that enables health validation without LLM involvement.

```python
@dataclass
class SourceManifest:
    # Identity
    source_id:              str       # canonical source document ID
    source_version:         str       # version tag from source registry
    content_hash:           str       # SHA-256 of raw source content
    authority_tier:         int       # 1 (regulatory) → 6 (secondary)
    effective_from:         date
    effective_to:           Optional[date]   # None = currently active

    # Chunking
    parser_version:         str
    chunker_version:        str
    expected_chunk_count:   int
    chunk_hashes:           list[str]        # SHA-256 per chunk

    # Embeddings
    embedding_model:        str
    embedding_model_version:str
    embedded_chunk_count:   int

    # Graph extraction
    taxonomy_version:       str
    graph_extractor_version:str
    expected_node_count:    int
    expected_edge_count:    int

    ingestion_timestamp:    datetime
    last_health_check:      datetime
    health_status:          str       # healthy | stale | partial | missing
```

**Health validation is a diff operation:**

```python
def check_source_health(manifest: SourceManifest) -> HealthReport:
    # Vector completeness
    actual_chunks = vector_store.count_chunks(manifest.source_id)
    missing_chunks = manifest.expected_chunk_count - actual_chunks

    # Embedding freshness
    embedded_hash = vector_store.get_content_hash(manifest.source_id)
    hash_mismatch = embedded_hash != manifest.content_hash

    # Graph completeness
    actual_nodes = graph.count_nodes(manifest.source_id)
    actual_edges = graph.count_edges(manifest.source_id)

    return HealthReport(
        source_id=manifest.source_id,
        missing_chunks=missing_chunks,
        hash_mismatch=hash_mismatch,
        node_deficit=manifest.expected_node_count - actual_nodes,
        edge_deficit=manifest.expected_edge_count - actual_edges,
        recommended_recipes=select_recipes(missing_chunks, hash_mismatch, ...)
    )
```

---

## 4. Three Levels of Self-Healing

### Level 1 — Mechanical Healing (target: near-fully deterministic, LLM = 0 tokens)

Operations at this level are purely operational. They restore the system to a known correct state without any semantic interpretation.

| Operation | Trigger | LLM Required |
|---|---|---|
| Retry failed ingestion | Ingestion job exit code ≠ 0 | No |
| Restore from backup snapshot | Index unavailable or corrupt | No |
| Re-embed missing chunks | `missing_chunks > 0` in health check | No |
| Re-index missing documents | Source in registry, absent from index | No |
| Deduplicate chunks | `duplicate_source_ratio > threshold` | No |
| Repair metadata fields | Manifest vs index metadata diff | No |
| Expire stale embeddings | `source_hash != embedded_hash` | No |

### Level 2 — Knowledge-Structure Healing (target: mostly deterministic)

Operations that require understanding of the AMC domain structure but can still be resolved using canonical identifiers and structured sources.

| Operation | Trigger | LLM Required |
|---|---|---|
| Entity canonicalization | Duplicate canonical ID detected | No (rule-based merge) |
| Graph constraint repair | Missing mandatory relationship | No (known pattern) |
| Source version reconciliation | Vector at v17, graph at v18 | No (manifest diff) |
| Temporal relationship management | Two active edges for same attribute | No (effective_date comparison) |
| Expire superseded graph edges | New source version ingested | No (effective_date rule) |
| Recreate known derived relationships | Orphan node detected | No (extraction rule replay) |

### Level 3 — Semantic Healing (escalation cascade)

Used only when deterministic resolution is not possible. Always cascades through cheaper options first.

```
Rules (domain constraint check)
    ↓  not resolved?
Small semantic classifier (local model, ~0 generative tokens)
    ↓  not resolved?
Bounded LLM (B2–B3 token budget)
    ↓  not resolved?
Agent (B4, multi-step tool use)
    ↓  not resolved?
Human SME
```

Examples requiring Level 3:
- Ambiguous relationship type between two entities
- Conflicting narratives from two authoritative sources
- Entity that doesn't map to any existing taxonomy node
- Semantic chunking boundary problem

---

## 5. Repair Recipe Registry

Every known failure class has a versioned, tested, and approved `RepairRecipe`. Agents are invoked only when no recipe matches.

```python
@dataclass
class RepairRecipe:
    recipe_id:              str       # e.g. R001
    recipe_version:         str
    name:                   str
    description:            str

    failure_families:       list[str] # F01–F14 this recipe addresses
    detection_rule:         str       # condition that triggers this recipe
    severity:               str       # critical | high | medium | low

    auto_repair_allowed:    bool      # can execute without human approval
    approval_required:      bool      # requires governance sign-off
    repair_class:           str       # R0–R5 (from LLD-05)

    repair_procedure:       str       # step-by-step description / code reference
    validation_tests:       list[str] # test IDs that must pass before promotion
    rollback_procedure:     str       # how to undo

    llm_required:           bool
    human_required:         bool
    estimated_duration_min: int
    blast_radius_scope:     str       # single_chunk | document | entity |
                                      # relationship_type | index | graph_schema
```

### Standard Recipe Catalogue

| ID | Name | Trigger | Procedure | LLM? | Repair Class |
|---|---|---|---|---|---|
| **R001** | MissingVector | `source_chunk_count ≠ vector_chunk_count` | Identify missing chunk IDs from manifest diff; re-parse from source; re-embed; insert with provenance | No | R1 |
| **R002** | StaleEmbedding | `source_content_hash ≠ embedded_content_hash` | Diff source versions; identify changed sections only; rechunk changed sections; re-embed affected chunks only | No | R2 |
| **R003** | DuplicateChunk | Duplicate `content_hash` in vector index | Identify duplicates; keep highest-authority version; remove others; update metadata | No | R1 |
| **R004** | MetadataMismatch | Manifest metadata ≠ index metadata | Rebuild metadata fields from source manifest; update in-place | No | R1 |
| **R005** | MissingSource | Known authoritative source absent from index | Re-ingest from source registry; full parse → chunk → embed → index | No | R2 |
| **R006** | RetrievalRegression | BM25/Graph find source; Vector consistently misses it across ≥ 3 queries | Investigate embedding model drift; selective re-embed affected document family | No | R2 |
| **R007** | BrokenGraphEdge | Source field changed (e.g. benchmark, fund manager, risk level) | Identify changed field from source diff; expire old edge (set `effective_to`); create new edge with new value + source_version + effective_date | No | R2 |
| **R008** | OrphanGraphNode | Entity node exists with no relationships | Re-run entity extraction for the source document; recreate relationships | Optional classifier | R2 |
| **R009** | SourceVersionMismatch | Vector index at source v17, Graph at source v18 | Identify lagging structure; re-process lagging structure from source registry to align versions | No | R2 |
| **R010** | EntityDuplicate | Two nodes share ISIN, canonical scheme code, or AMC master ID | Merge nodes; transfer all relationships to canonical node; update provenance on all edges; remove duplicate | Classifier only | R2 |
| **R011** | MissingProvenance | Graph edge has no `source_id`, `source_version`, or `effective_date` | Trace from extraction logs; backfill provenance fields from manifest; flag if unresolvable | No | R1 |
| **R012** | TemporalConflict | Two active edges for the same `(entity, attribute)` pair | Compare `effective_from` dates; expire the older; validate the newer has source provenance | No | R1 |

---

## 6. Vector DB Health Checks

### 6.1 Completeness

```python
def check_vector_completeness(source_id: str) -> dict:
    manifest = source_registry.get_manifest(source_id)
    actual   = vector_store.count_chunks(source_id)

    if actual < manifest.expected_chunk_count:
        missing_ids = vector_store.find_missing_chunks(source_id, manifest.chunk_hashes)
        return {
            "status": "INCOMPLETE",
            "missing_count": manifest.expected_chunk_count - actual,
            "missing_chunk_ids": missing_ids,
            "recipe": "R001"
        }
    return {"status": "COMPLETE"}
```

### 6.2 Freshness

```python
def check_vector_freshness(source_id: str) -> dict:
    manifest      = source_registry.get_manifest(source_id)
    embedded_hash = vector_store.get_content_hash(source_id)

    if embedded_hash != manifest.content_hash:
        changed_sections = diff_source_versions(
            old_hash=embedded_hash,
            new_hash=manifest.content_hash
        )
        return {
            "status": "STALE",
            "changed_sections": changed_sections,
            "recipe": "R002"
            # Only rechunk/re-embed changed sections — not the whole document
        }
    return {"status": "FRESH"}
```

### 6.3 Index Health Metrics

| Metric | Description | Threshold |
|---|---|---|
| `source_completeness` | % of expected chunks present | < 100% → R001 |
| `embedding_completeness` | % of indexed chunks with valid embeddings | < 100% → R001 |
| `version_consistency` | All chunks from same source version? | Mismatch → R009 |
| `hash_integrity` | Stored content hashes match current source? | Mismatch → R002 |
| `duplicate_ratio` | % of chunks with duplicate content hash | > 1% → R003 |
| `metadata_completeness` | % of chunks with complete metadata | < 100% → R004 |

---

## 7. Context Graph Health Checks

### 7.1 Entity Integrity

```
Scheme ID unique?                  → R010 EntityDuplicate if not
ISIN unique (where applicable)?    → R010 EntityDuplicate if not
Fund house node exists?            → R008 OrphanGraphNode if missing
Benchmark node is a known entity?  → R007 BrokenGraphEdge if stale reference
Entity type matches taxonomy?      → F01 root cause if not
```

### 7.2 Relationship Integrity

Every mandatory relationship must exist and be current:

```
Scheme  ──MANAGED_BY──►         AMC entity
Scheme  ──BENCHMARKED_AGAINST──► Index entity
Scheme  ──HAS_RISK_LEVEL──►     Riskometer entity
Scheme  ──HAS_DOCUMENT──►       SID/KIM document
Scheme  ──HAS_PLAN──►           Plan/Option entities (Direct, Regular, Growth, IDCW)
```

Any missing mandatory relationship triggers **R008 OrphanGraphNode**.

### 7.3 Provenance Integrity

Every factual edge must carry:

| Field | Description |
|---|---|
| `source_id` | Which source document asserts this fact |
| `source_version` | Which version of that source |
| `effective_from` | When this fact became valid |
| `effective_to` | When it expired (null = currently active) |
| `extraction_method` | How the edge was derived (rule / extractor / llm) |
| `ingestion_timestamp` | When it was written to the graph |

An edge missing any of these fields is a first-class data quality problem — **R011 MissingProvenance**.

### 7.4 Temporal Integrity

```
Two active BENCHMARKED_AGAINST edges for same scheme?   → R012 TemporalConflict
Old fund manager still listed as CURRENTLY_MANAGED_BY?  → R007 BrokenGraphEdge
NAV edge with no effective_date?                        → R011 MissingProvenance
Expired relationship without effective_to set?          → R007 BrokenGraphEdge
```

### 7.5 Structural Integrity

```
Orphan nodes (no relationships)?          → R008
Dangling relationship (endpoint deleted)? → constraint enforcement
Unexpected disconnected components?       → investigation queue
Missing mandatory paths?                  → R007 or R008
```

---

## 8. Hybrid Retrieval as a Diagnostic Sensor

Disagreement between the three retrieval mechanisms is a leading indicator of health problems — detectable at zero LLM cost.

```
              QUERY
                │
  ┌─────────────┼─────────────┐
  ▼             ▼             ▼
BM25          VECTOR        GRAPH
  │             │             │
  └─────────────┼─────────────┘
                ▼
        AGREEMENT MATRIX
```

| Signal | Interpretation | Recipe |
|---|---|---|
| BM25 finds source; Vector misses | Embedding model drift or missing chunk | R002 or R006 |
| Graph finds entity; Vector misses | Source indexed but entity chunks stale | R002 |
| BM25 + Vector agree; Graph misses | Graph extraction lag | R007 or R008 |
| All three disagree | Multiple simultaneous issues | Prioritise by authority tier |
| BM25 rank ≠ Vector rank significantly | Reranker miscalibration | Configuration review |

### Query Cohort Health Monitoring

Build deterministic cohorts per AMC taxonomy intent. Track the retrieval baseline per cohort. Alert when current-period performance drops below baseline.

```
Cohort: NAV_LOOKUP queries
Baseline: authoritative NAV source in Top-3 = 99.2%
Current:  authoritative NAV source in Top-3 = 84.1%
    ↓
Alert: retrieval drift for NAV_LOOKUP cohort
    ↓
Trigger: R002 freshness check on all NAV-related sources
LLM tokens: 0
```

Cohorts to monitor: `NAV_LOOKUP` · `TER_LOOKUP` · `PERFORMANCE_COMPARISON` · `RISKOMETER` · `BENCHMARK` · `FUND_MANAGER` · `PORTFOLIO_HOLDINGS` · `EXIT_LOAD`

---

## 9. Shadow Repair — Never Heal Production Directly

This is the most important safety constraint in the self-healing design. Every repair, regardless of size, executes in an isolated shadow environment first.

```
Production RAG
      │
      ▼
Problem detected (health check or failure diagnosis)
      │
      ▼
RepairCandidate created (links to RepairRecipe + RootCause)
      │
      ▼
SHADOW ENVIRONMENT
  ├── Shadow Vector Index   (copy of production, isolated)
  └── Shadow Context Graph  (copy of production, isolated)
      │
      ▼
Execute repair in shadow
      │
      ▼
Run Regression Query Set
  ├── Golden queries (known correct Q&A pairs)
  ├── Affected cohort queries (NAV, TER, etc. for affected entities)
  ├── Compliance routing test (does repair change control applicability?)
  └── Blast-radius queries  (adjacent entities not targeted by repair)
      │
      ▼
Before ↔ After Comparison
  ├── Retrieval quality delta
  ├── Citation integrity delta
  ├── Numeric accuracy delta
  └── Compliance routing delta
      │
   ┌──┴──┐
  FAIL   PASS
   │       │
Reject   Approval Gate
   │       │
Rollback  R1/R2: auto-promote
   │      R3+:  governance sign-off
   │       │
   └───────┴──► ATOMIC PROMOTION TO PRODUCTION
                      │
                      ▼
              POST-CHANGE MONITORING
```

### Shadow Environment Implementation

```python
class ShadowEnvironment:
    """
    An isolated copy of the production vector index and graph,
    used to execute and validate repairs before promotion.
    """

    async def create_snapshot(self, affected_entities: list[str]) -> str:
        """
        Create a partial snapshot covering only the affected scope.
        Returns snapshot_id.
        Full index copy only for graph_schema repairs (R3+).
        """
        snapshot_id = str(uuid4())

        # Copy affected chunks to shadow vector store
        await self.shadow_vector.copy_from_production(
            entity_ids=affected_entities,
            snapshot_id=snapshot_id,
        )

        # Copy affected subgraph to shadow graph
        await self.shadow_graph.copy_subgraph(
            entity_ids=affected_entities,
            depth=2,
            snapshot_id=snapshot_id,
        )

        return snapshot_id

    async def execute_repair(self, recipe: RepairRecipe, snapshot_id: str) -> RepairResult:
        """
        Run the repair procedure against the shadow environment.
        Captures before/after state for diff.
        """
        before = await self.capture_state(snapshot_id)
        await recipe.execute(shadow_env=self, snapshot_id=snapshot_id)
        after = await self.capture_state(snapshot_id)
        return RepairResult(before=before, after=after, snapshot_id=snapshot_id)

    async def run_regression(self, snapshot_id: str, affected_entities: list[str]) -> RegressionReport:
        """
        Run the standard regression suite against the shadow environment.
        Returns pass/fail per test category.
        """
        return RegressionReport(
            golden_queries=await self.run_golden_set(snapshot_id),
            cohort_queries=await self.run_cohort_queries(snapshot_id, affected_entities),
            blast_radius=await self.run_blast_radius_check(snapshot_id, affected_entities),
            compliance_routing=await self.run_compliance_routing_test(snapshot_id),
        )
```

---

## 10. Blast-Radius Assessment

Before promoting a repair, its potential side-effects must be bounded.

| Scope | Description | Default Regression Requirement |
|---|---|---|
| `single_chunk` | One embedding chunk affected | Golden set + cohort sample |
| `document` | All chunks from one source document | Golden set + full cohort |
| `entity` | All nodes/edges for one AMC entity | Golden set + full cohort + adjacent entity sample |
| `relationship_type` | All edges of one relationship type | Full cohort + compliance routing test |
| `index` | Significant portion of the vector index | Full golden set + all cohorts + extended monitoring |
| `graph_schema` | Structural change to graph schema | Full regression suite + compliance routing + governance approval (R3+) |

**Blast-radius estimation:**

```python
def estimate_blast_radius(recipe: RepairRecipe, affected_entities: list[str]) -> BlastRadiusReport:
    # Estimate downstream query impact
    affected_queries = query_log.count_queries_using_entities(
        affected_entities, lookback_days=7
    )

    # Check if repair touches compliance-sensitive attributes
    compliance_sensitive = any(
        entity_registry.is_compliance_sensitive(e) for e in affected_entities
    )

    return BlastRadiusReport(
        scope=recipe.blast_radius_scope,
        estimated_affected_queries=affected_queries,
        compliance_sensitive=compliance_sensitive,
        requires_governance_approval=(
            recipe.repair_class in ["R3", "R4", "R5"] or
            compliance_sensitive and recipe.blast_radius_scope in ["index", "graph_schema"]
        )
    )
```

---

## 11. Post-Heal Monitoring

After every production promotion, the system enters a monitoring window to detect two failure modes:

1. **Recurrence** — the same failure reappears (repair was insufficient)
2. **Collateral damage** — a new failure type appears in the affected cohort (repair introduced a regression)

```python
@dataclass
class PostHealMonitor:
    deployment_change_id:    str
    affected_entities:       list[str]
    baseline_metrics:        dict     # captured before repair
    monitoring_window_hours: int      # 24h standard; 168h (7 days) for R3+

    async def check(self) -> MonitorReport:
        current = await self.capture_current_metrics()

        return MonitorReport(
            failure_recurrence=self.detect_recurrence(current),
            new_failure_rate=self.detect_new_failures(current),
            retrieval_quality_delta=self.compare_retrieval(current),
            compliance_routing_delta=self.compare_routing(current),
            token_cost_delta=self.compare_token_cost(current),
            verdict=self.determine_verdict(current),
        )

    def determine_verdict(self, current: dict) -> str:
        if self.detect_recurrence(current):
            return "REPAIR_INEFFECTIVE"          # → escalate to R4
        if self.detect_new_failures(current):
            return "REPAIR_CAUSED_COLLATERAL"    # → rollback
        if self.compare_retrieval(current)["delta"] < -0.05:
            return "REPAIR_CAUSED_REGRESSION"    # → rollback
        return "REPAIR_SUCCESSFUL"
```

---

## 12. Compliance-Safe Self-Healing Boundary

This boundary is absolute. It defines what the automated system may and may not decide independently.

### Permitted without human approval (R1/R2):

```
✓ Rebuild missing embeddings from canonical source
✓ Restore index from source registry
✓ Refresh source-derived chunks after document update
✓ Repair deterministic metadata (dates, versions, canonical IDs)
✓ Expire superseded graph edges (source-provable, effective_date available)
✓ Recreate known derived relationships with full provenance
✓ Deduplicate entities with matching canonical IDs
```

### Requires human/compliance approval (R3–R5):

```
✗ New legal interpretation of regulatory text
✗ New suitability standard or threshold
✗ New disclosure obligation
✗ Change to jurisdiction scope of a policy pack
✗ Regulatory conflict resolution between two authoritative sources
✗ Any change to a compliance control rule (C01–C14)
✗ Taxonomy restructuring that affects control applicability
```

---

## 13. Self-Healing KPIs

| KPI | Target | Notes |
|---|---|---|
| `repair_actions_without_llm` | > 90% | Measures recipe coverage maturity |
| `repair_recurrence_rate_30d` | < 5% | Repairs that re-break within 30 days |
| `mean_time_to_repair_r1_hours` | < 2h | R1 auto-safe repairs |
| `mean_time_to_repair_r2_hours` | < 24h | R2 shadow + promote |
| `shadow_validation_pass_rate` | > 95% | Repairs that survive regression |
| `false_repair_rate` | < 1% | Repairs that caused new failures |
| `known_recipe_coverage` | tracked | % of observed failures with a matching recipe |
| `new_recipe_creation_rate` | tracked | Novel failures → recipes per month (should increase) |
| `level_1_repair_share` | tracked | Mechanical repairs vs semantic repairs (should increase) |
| `blast_radius_bounded_rate` | > 99% | Repairs with bounded scope that passed blast-radius check |

---

## 14. Integration with Phase 1 Implementation

The Phase 1 `graph_corrector.py` and `cache_manager.py` implement the simplest cases of Level 1 and Level 2 healing — Neo4j atomic corrections and FAISS/Redis invalidation. Phase 3 extends this with the full recipe registry, shadow environment, and post-heal monitoring.

```
Phase 1 (complete):
  graph_corrector.py      — applies Neo4j corrections (R1/R2 scope, confidence ≥ 0.85)
  cache_manager.py        — FAISS, Redis, entity resolver, Neo4j traversal invalidation

Phase 3 additions (designed):
  rag_health_engine.py    — source manifest diff, health check orchestration
  vector_health_checker.py — R001–R006 triggers and procedures
  graph_health_checker.py  — R007–R012 triggers and procedures
  repair_recipe_registry.py — recipe lookup, versioning, execution
  shadow_environment.py   — snapshot creation, repair execution, regression runner
  promotion_gate.py       — blast-radius assessment, approval workflow, atomic promotion
  post_heal_monitor.py    — recurrence, collateral, delta tracking
```

---

*Previous: [LLD-05 — Failure Taxonomy](./LLD-05-FAILURE-TAXONOMY.md)*  
*Next: [LLD-07 — Compliance Plane](./LLD-07-COMPLIANCE-PLANE.md)*


---

## 15. Component Architecture Detail

> Added from AMC_COMPONENT_ARCHITECTURE.html — August 2026

### Phase 6 — Graph Correction Sub-Components

Phase 6 implements the Level 1 and Level 2 healing described in this document, executed as Neo4j atomic transactions triggered by high-confidence LLM evaluation results.

| Sub-Component | File | Responsibility | Recipe Coverage |
|---|---|---|---|
| Cypher Validator | `graph_corrector.py` | Syntax check, permitted operation types, schema constraints | All recipes before execution |
| Neo4j Transaction Manager | `graph_corrector.py` | ACID transaction: before-state capture → execute → after-state capture → audit write | R007, R008, R010, R011, R012 |
| Add Entity Operation | `graph_corrector.py` | CREATE node with full provenance (conf ≥ 0.85) | R008 OrphanGraphNode |
| Update Property Operation | `graph_corrector.py` | SET property + update provenance edge (conf ≥ 0.80) | R007 BrokenGraphEdge |
| Add Relationship Operation | `graph_corrector.py` | CREATE edge with full provenance props (conf ≥ 0.75) | R007 BrokenGraphEdge |
| Remove Relationship (soft) | `graph_corrector.py` | SET effective_to on edge — soft expiry, not DELETE (conf ≥ 0.85) | R007 BrokenGraphEdge, R012 TemporalConflict |
| Audit Trail Writer | `graph_corrector.py` | Immutable before+after state record in correction_audit_trail | All operations |
| Rollback Engine | `graph_corrector.py` | Read before_state → generate reverse Cypher → execute in new transaction | All operations |

### Phase 7 — Cache Invalidation Sub-Components

Phase 7 implements the post-correction cache cleanup that makes healed knowledge immediately available to the next query.

| Sub-Component | File | Cache Layer | What Gets Cleared | Recipe Trigger |
|---|---|---|---|---|
| FAISS Chunk Invalidator | `cache_manager.py` | FAISS vector index | Chunks for affected entity_ids | R001, R002, R003, R005, R006 |
| Redis EvidencePack Invalidator | `cache_manager.py` | Redis: `evidence:{response_id}` keys | Evidence caches for responses using affected entities | All corrections |
| Redis Graph Context Invalidator | `cache_manager.py` | Redis: `graph_ctx:{hash}` keys | Graph snapshots for affected entity ID hashes | All corrections |
| Entity Resolver Cache Invalidator | `entity_resolver.py` | In-memory + Redis alias maps | Canonical ID → alias mappings for affected entities | R010 EntityDuplicate, R007 |
| Neo4j Traversal Cache Invalidator | `cache_manager.py` | Neo4j query cache | Cached traversal paths through affected nodes | R007, R008, R009, R012 |
| Invalidation Scope Calculator | `cache_manager.py` | — | Calculates blast radius before invalidating; alerts if > 500 affected response_ids | Pre-invalidation guard |
| Invalidation Event Emitter | `cache_manager.py` | Event bus | CorrectionAppliedEvent after all DELs complete | Post-invalidation notification |

### Repair Recipe → Phase Mapping

| Recipe | Phase 6 (Graph Correction) | Phase 7 (Cache Invalidation) | Shadow Required? |
|---|---|---|---|
| R001 MissingVector | No (FAISS-only repair) | FAISS: re-embed new chunks | No (R1) |
| R002 StaleEmbedding | No (FAISS-only repair) | FAISS: re-embed changed sections | Yes (R2) |
| R003 DuplicateChunk | No (FAISS-only repair) | FAISS: remove duplicates | No (R1) |
| R004 MetadataMismatch | No (FAISS metadata only) | FAISS: metadata rebuild | No (R1) |
| R005 MissingSource | Full re-ingest: FAISS + graph | FAISS + Redis + Neo4j paths | Yes (R2) |
| R006 RetrievalRegression | Selective re-embed | FAISS: affected document family | Yes (R2) |
| R007 BrokenGraphEdge | Yes: SET effective_to + CREATE new edge | Redis graph_ctx + FAISS + Neo4j paths | Yes (R2) |
| R008 OrphanGraphNode | Yes: recreate relationships | Redis graph_ctx + FAISS + Neo4j paths | Yes (R2) |
| R009 SourceVersionMismatch | Yes: re-process lagging structure | Redis graph_ctx + FAISS + Neo4j paths | Yes (R2) |
| R010 EntityDuplicate | Yes: MERGE nodes, transfer relationships | Redis graph_ctx + resolver cache + FAISS + Neo4j | Yes (R2) |
| R011 MissingProvenance | Yes: SET missing edge properties | Redis graph_ctx only | No (R1) |
| R012 TemporalConflict | Yes: SET effective_to on older edge | Redis graph_ctx + Neo4j paths | No (R1) |

### Shadow Environment Validation Sequence

```
RepairCandidate created
    ↓
ShadowEnvironment.create_snapshot(affected_entities)
  → Copy affected chunks to shadow FAISS (partial copy only for R1/R2)
  → Copy affected subgraph to shadow Neo4j (depth=2)
    ↓
ShadowEnvironment.execute_repair(recipe, snapshot_id)
  → Capture before state
  → Execute recipe procedure
  → Capture after state
    ↓
ShadowEnvironment.run_regression(snapshot_id, affected_entities)
  → Golden queries: known correct Q&A pairs
  → Cohort queries: NAV, TER, etc. for affected entities
  → Blast-radius queries: adjacent entities NOT targeted
  → Compliance routing test: does repair change control applicability?
    ↓
Before ↔ After Comparison
  → retrieval_quality_delta > -0.05?   → PASS
  → citation_integrity_delta > -0.02?  → PASS
  → numeric_accuracy_delta > -0.01?    → PASS
  → compliance_routing_delta = 0?      → PASS (must be exact)
    ↓
  PASS → Approval Gate (auto for R1/R2; governance for R3+)
  FAIL → Reject RepairCandidate, log reason, escalate
```

*See [AMC_COMPONENT_ARCHITECTURE.html](../AMC_COMPONENT_ARCHITECTURE.html) — Phase 6, Phase 7, and Self-Healing RAG tabs for interactive component cards.*
