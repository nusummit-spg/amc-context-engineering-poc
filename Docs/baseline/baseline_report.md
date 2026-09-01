# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Evidence-Based Baseline Report

**Run ID**: `baseline-local-dev-20260814-20260814T082557Z`  
**Execution Window**: 2026-08-14T08:25:57Z – 2026-08-14T08:38:48Z  
**Environment**: `local-dev-20260814`  
**Host**: `WINDOWS` / `NUTGLP-1476`  
**Python Runtime**: Python 3.10.11 (`backend/.venv/Scripts/python.exe`)  
**Evidence Directory**: `logs/baseline/20260814T082557Z/`  

---

## 1. Executive Summary

This report establishes the empirical, auditable baseline for the context-engineering system prior to any convergence, rerouting, or schema refactoring. All measurements and findings were collected under strict **zero-mutation constraints** (no re-indexing, no graph reseeding, no document ingestion).

### Core Audit Outcomes:
1. **Serving Path Divergence**: Live queries (`/api/query`, `/api/chat`) execute against `backend/app/engine/retrieval.py` using `app/engine/faiss_indexes/amc_master` (18 PDFs, 669 entities). The modern `RetrievalOrchestrator` container pipeline is **dormant and uncalled**.
2. **Document & Provenance Mismatch**: Active Neo4j nodes are 100% flat `(:Entity)` records (669 nodes). There are 0 `(:Document)` nodes and 0 `(:TaxonomyNode)` nodes in Neo4j. Provenance is maintained via `source_chunk_id` (`P#####`) mapping to the FAISS store rather than canonical `document_id` foreign keys.
3. **Offline Test Health**: 11 of 12 unit/contract tests passed. 1 test failed due to a tuple-return mismatch in `EntityResolver.resolve_surface_form` (`(entity, confidence)` returned vs expected entity object).
4. **Live API Fixture Verification**: 100% (11/11) HTTP probes succeeded across status, docs, taxonomy, graph, single-turn queries, and multi-turn chat scenarios.

---

## 2. Serving Path Architecture Map

```text
======================= ACTIVE SERVING PATH =======================
Streamlit UI (Port 8501)
   │
   ▼ HTTP (Port 8000)
FastAPI Routes:
   ├── /api/query ────► app.engine.retrieval (traditional_rag / hybrid_graphrag)
   │                      ├── FAISS: app/engine/faiss_indexes/amc_master (18 docs)
   │                      ├── Neo4j: bolt://localhost:7687 (669 (:Entity) nodes)
   │                      └── Models: BAAI/bge-small-en-v1.5 + ms-marco-MiniLM-L-6-v2 + GLiNER
   │
   └── /api/chat  ────► app.engine.context_memory + app.engine.retrieval
                          └── Semantic Response Cache (SQLite / in-memory)

===================== DORMANT CONTAINER PATH =====================
FastAPI Routes:
   ├── /api/docs      ────► Container.vector (app.vector.VectorStore) -> 0 indexed docs
   ├── /api/taxonomy  ────► Container.taxonomy (data/taxonomy_v2.json)
   ├── /api/graph     ────► Container.graph (GraphClient)
   └── /api/ingest    ────► IngestionPipeline (Dormant)
   └── Orchestrator   ────► RetrievalOrchestrator (Container.orchestrator) -> UNUSED
```

---

## 3. Data Store & Index Census

| Component | Physical Path / Connection | Current Content Count | Primary Consumer | Active Status |
| :--- | :--- | :--- | :--- | :--- |
| **Active FAISS Index** | `backend/app/engine/faiss_indexes/amc_master/` | 18 Source PDFs, 400+ Parent Chunks, 1200+ Child Chunks | `app.engine.retrieval` (`/api/query`, `/api/chat`) | **Active** |
| **Modern Vector Store** | `backend/data/vector_store/` | 0 Documents, 0 Chunks | `app.vector.VectorStore` (`/api/docs`, `/api/status`) | **Active (Empty)** |
| **Neo4j Active DB** | `bolt://localhost:7687` (HTTP 7474) | 669 `(:Entity)` nodes, 633 relationships | `app.engine.graph_store`, `app.graph.client` | **Active** |
| **Taxonomy Definition** | `backend/data/taxonomy_v2.json` | 4 Levels, 1 Domain, 4 Roots, 8 Sub-roots | `app.api.deps.load_taxonomy` (`/api/taxonomy`) | **Active** |

---

## 4. Test Suite Execution & Defect Register

### 4.1 Offline Unit & Contract Tests
* **Command**: `python -m pytest tests/test_schemas_and_contracts.py tests/test_ingestion_units.py -v`
* **Result**: **11 PASSED, 1 FAILED** in 21.74s
* **Log Location**: `logs/baseline/20260814T082557Z/offline_tests.log`

### 4.2 Defect Register

| Defect ID | Component | Severity | Description | Evidence Path |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-01** | `app/extraction/resolver.py` | Medium | `resolve_surface_form()` returns `(BaseEntity, float)` tuple, but caller `test_ingestion_units.py` and `app/api/routes/graph.py` expect `BaseEntity` object directly, causing `AttributeError: 'tuple' object has no attribute 'name'`. | `offline_tests.log:66` |
| **DEF-02** | `/api/docs` vs `/api/query` | High | `/api/docs` inspects empty `app.vector.VectorStore` (`0 docs`), while `/api/query` searches populated `amc_master` FAISS store (`18 docs`). | `manifest.json`, `documents.json` |
| **DEF-03** | Graph Schema Dissonance | High | Active Neo4j database uses flat `(:Entity)` labels with `source_chunk_id` edges, while modern schema expects `(:Document)` and `(:TaxonomyNode)` nodes with `source_document_id`. | `neo4j_census.json`, `integrity_report.md` |
| **DEF-04** | Latency Telemetry Accounting | Low | Semantic Cache hits report pipeline duration (e.g. 71.6ms), but top-level HTTP response `latency_ms` includes pre-cache vector search overhead (8095ms). | `query_safety_advice.json` |

---

## 5. Live API Baseline Fixture Results

Collected via `backend/scripts/collect_baseline.ps1` against `http://127.0.0.1:8000` (`logs/baseline/20260814T082557Z/20260814T083526Z/`):

| Probe ID | Method & Route | HTTP Status | Elapsed (ms) | Observed Behavior & Findings |
| :--- | :--- | :--- | :--- | :--- |
| `status` | `GET /api/status` | 200 OK | 217.1 ms | Neo4j: ok, Qdrant: ok, LLM: error (fallback active), docs: 0. |
| `documents` | `GET /api/docs` | 200 OK | 12.2 ms | Returns `[]` (modern vector store empty). |
| `taxonomy` | `GET /api/taxonomy` | 200 OK | 257.3 ms | Returns 4-level taxonomy tree hierarchy. |
| `graph` | `GET /api/graph?limit=100` | 200 OK | 229.2 ms | Returns `{nodes: [], edges: []}` because GraphClient queries specific labels. |
| `query_adani_exposure` | `POST /api/query` | 200 OK | 63123.8 ms | Hybrid RAG traverses 8 graph nodes; Traditional RAG retrieves 5 passages from 2 PDFs. NER stage took 40.5s. |
| `query_sebi_compliance` | `POST /api/query` | 200 OK | 13073.4 ms | Hybrid RAG matches SEBI entities; retrieves 5 documents. |
| `query_nbfc_synthesis` | `POST /api/query` | 200 OK | 20846.5 ms | Hybrid RAG matches `'NBFCs'`, traverses graph nodes; Vector bypassed (Pillar 1). |
| `query_taxonomy_regime` | `POST /api/query` | 200 OK | 8304.8 ms | Flat query executes, stores query in Semantic Cache (ID=3). |
| `query_safety_advice` | `POST /api/query` | 200 OK | 104.9 ms | Semantic Cache HIT (`Score=0.524 >= 0.45`). |
| `chat_regime_turn1` | `POST /api/chat` | 200 OK | 98.3 ms | Semantic Cache HIT (`Score=0.832 >= 0.45`). |
| `chat_regime_turn2` | `POST /api/chat` | 200 OK | 8636.9 ms | Cache MISS; 2-turn history evaluated, product matched, 8 graph nodes traversed. |

---

## 6. Document & Provenance Join Matrix

* **Active FAISS Documents**: 18 PDFs
* **API Vector `/api/docs` Count**: 0
* **Neo4j `(:Document)` Node Count**: 0
* **Relationship Provenance**: 633 / 633 relationships (100%) carry `source_chunk_id` (`P#####`) mapping to `amc_master` parent chunks. 0 relationships carry `source_document_id`.

---

## 7. Claim Classification

| Claim in Repository Documentation | Observed Evidence Classification | Evidence Summary |
| :--- | :--- | :--- |
| "FastAPI `/api/query` routes to `RetrievalOrchestrator`" | **Contradicted by Evidence** | `routes/query.py` explicitly routes to `app.engine.retrieval`. `RetrievalOrchestrator` is unused. |
| "Graph contains `Document` and `TaxonomyNode` nodes" | **Contradicted by Evidence** | Graph contains 669 flat `(:Entity)` nodes. 0 `Document` or `TaxonomyNode` nodes exist. |
| "Every relationship has provenance to source documents" | **Live & Verified (Chunk-Keyed)** | Provenance exists at chunk granularity (`source_chunk_id: "P#####"`), but not document ID. |
| "Multi-turn chat preserves history and resolves coreferences" | **Live & Verified** | `/api/chat` resolves coreferences via `context_memory` and maintains session history across turns. |
| "Semantic caching accelerates repeat/similar queries" | **Live & Verified** | Cache hits demonstrated sub-105ms latencies on repeat queries vs 8.3s–63.1s cold queries. |
| "Taxonomy tree serves 4 levels of fund categorization" | **Live & Verified** | `/api/taxonomy` serves complete 4-level taxonomy hierarchy from `taxonomy_v2.json`. |

---

## 8. Go / No-Go Decision Gates for Downstream Convergence

| Gate | Criterion | Status | Findings / Evidence |
| :--- | :--- | :--- | :--- |
| **Gate 1** | Active query route unambiguously identified | **PASSED** | Confirmed: `/api/query` $\rightarrow$ `app.engine.retrieval`. |
| **Gate 2** | Exact document-ID mismatch quantified | **PASSED** | Quantified: 18 FAISS documents chunk-linked; 0 modern `document_id` joins. |
| **Gate 3** | Active graph topology and schema confirmed | **PASSED** | Confirmed: 669 `(:Entity)` nodes, 633 relationships with `source_chunk_id`. |
| **Gate 4** | Baseline failure modes captured | **PASSED** | DEF-01 to DEF-04 documented in gap register and defect table. |
| **Gate 5** | Test environment made reproducible | **PASSED** | Python 3.10.11 venv locked, preflight verified, collector script validated. |
| **Gate 6** | Metric producers classified and reconciled | **PASSED** | Metric dictionary completed; cache latency discrepancy documented. |

### Convergence Decision: **GO (Approved to Proceed)**

The baseline audit is complete, fully reproducible, and backed by immutable evidence in `logs/baseline/20260814T082557Z/`. Downstream architectural convergence may proceed according to the ordered sequence:
1. Unified Serving Path (`/api/query` $\rightarrow$ `RetrievalOrchestrator` migration).
2. Canonical Document ID and Provenance Contract Unification.
3. Unified Graph Schema Migration (`(:Document)`, `(:TaxonomyNode)`, and `(:Entity)` integration).
4. Telemetry and UI Tracing Harmonization.
5. Evaluation Harness Alignment.
