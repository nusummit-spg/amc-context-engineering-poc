# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Codebase Issues Analysis & Recommendations

## Executive Summary

Deep audit of the context-engineering codebase reveals **5 structural / critical issues** and **6 observability / showcase gaps** across the ingestion pipeline, dual-store consistency, metrics capture, and paradigm-value demonstration.

---

## 🔴 Issue 1 — Vector DB ↔ Context Graph Mismatch (Your #1)

### Root Cause: Two Completely Separate Ingestion Pipelines

The codebase runs **two parallel, disconnected ingestion flows** that write to the same stores from different entry points with different document sets and different metadata schemas:

| Dimension | FAISS Engine Path | Context Graph Path |
|---|---|---|
| Entry point | `backend/app/engine/faiss_store.py` → `BrochureFAISSStore` | `backend/app/engine/graph_store.py` → `upsert_entities()` |
| Build script | `build_50doc_faiss_index.py` | `build_taxonomy_graph.py` + `seed_neo4j.py` |
| Documents indexed | 50-doc matrix (Tier 1-4 + Baseline), `selected_source_documents` | Only `taxonomy` nodes + NER-extracted entity mentions per doc |
| Metadata written | `doc_name`, `page_num`, `category`, `tier` | `dedup_key`, `label`, `product_name`, `source`, `chunk_id` |
| `document_id` linkage | ❌ Not stored — only `source` (filename string) | ❌ Not stored — `source` key carries different value format |

**Concrete consequence:** When `retrieval.py → hybrid_graphrag()` runs the graph traversal fallback and then tries to match graph edges back to vector chunks (via `graph_fact_products`), the join key is `product_name` — but FAISS payloads from the 50-doc build script store `doc_name` (raw PDF filename) while the graph stores `product_name` from the NER pipeline. **The RRF fusion boost at line 354-360 of `retrieval.py` silently finds zero matches for most queries.**

### Additional Mismatches Found
1. **`selected_source_documents`** is ingested into FAISS (Baseline tier) via `build_50doc_faiss_index.py` but **never seeded into Neo4j** — graph has no nodes for those 14 docs.
2. **Taxonomy graph** (`build_taxonomy_graph.py`) writes `SchemeClass`, `RegulatoryRegime` nodes to port 7688, but the main ingestion pipeline (`ingestion/pipeline.py`) writes `Entity`, `Document`, `TaxonomyNode` nodes to the URI in `.env` — potentially different databases.
3. **`ingestion/pipeline.py` (WS5e)** correctly links `Document → MENTIONS → Entity` and `Document → TAGGED_AS → TaxonomyNode`, but the offline `build_taxonomy_graph.py` creates `SchemeClass → BELONGS_TO → SchemeSection` — **these schema types are never queried by `traversal.py`**, which only queries `Scheme`, `Issuer`, `IssuerGroup`, `Sector` labels.

---

## 🔴 Issue 2 — Missing Step-Level Metrics (Your #2)

### What's Captured Today (Partial)
`retrieval.py → telemetry_breakdown` captures timing for: NER, graph DB, vector DB, rerank, Cypher generation, LLM, total. Token counts are present.

### What's Missing Across Every Step

| Pipeline Step | Missing Metrics |
|---|---|
| **Document Ingestion** | Per-doc chunk count, entity count, relationship count, taxonomy tags assigned, PII tokens redacted, time per stage |
| **Intent Classification** | Classification confidence score, fallback triggers, which taxonomy paths were selected, model used |
| **Entity Resolution** | Resolution rate (matched / total), alias hits vs. embedding hits, unresolved entity count |
| **Graph Traversal** | Which Cypher template fired, traversal depth actually used, rows returned per template, fallback stage reached (1/2/3) |
| **Vector Search** | Raw candidates before post-filter, after taxonomy scope filter, scope filter hit/miss rate |
| **Context Assembly** | Token budget utilization (graph section vs vector section vs overhead), facts dropped due to budget, chunks dropped, quality gate score + threshold used |
| **Synthesis** | Prompt character count, output confidence score, citation count in answer |
| **Cache** | Cache hit rate (per session, global), semantic similarity score of the cache match |
| **End-to-End** | Per-paradigm cost attribution (which paradigm saved how many tokens/ms) |

### Specific Code Gaps
- `context.py → assemble()` computes `quality_score` and `chunks_dropped` but these **never surface in the API response** (`/query` endpoint only returns `telemetry_breakdown` from the engine, not from the WS5 orchestrator).
- `traversal.py` logs which strategy fired but doesn't report **which fallback stage** was reached or how many rows each Cypher template returned.
- `retrieval/cache.py` exists but cache hit/miss counts and semantic similarity scores are not emitted to any telemetry output.

---

## 🟡 Issue 3 — Context Engineering Layer Value Not Demonstrable (Your #3)

### The Problem
The current architecture has no **side-by-side measurable delta** between:
- Plain vector RAG output
- Graph-augmented output
- Context-engineered output (HyDE + intent routing + token budget + quality gate)

The UI has a "Traditional vs ContextGraph" panel, but it only shows the final answer — not **why** the context-engineered path produced a better answer. There is no attribution of which paradigm contributed which fact.

### What Each Paradigm Currently Contributes (undocumented)

| Paradigm | Code Location | Value Produced | Currently Surfaced? |
|---|---|---|---|
| HyDE (Hypothetical Document Embedding) | `engine/hyde.py` | Improves recall for vague queries | ❌ No metric |
| Intent-Driven Routing | `engine/query_classifier.py` | Selects graph vs vector path | ✅ `query_type` in response |
| Dual NER (Layer A rule + Layer B ML) | `engine/ner_pipeline.py` | Entity precision | ✅ In audit log only |
| Graph Traversal (3-path ladder) | `engine/graph_store.py` | Verified facts | ✅ Partial in UI |
| Vector Pruning (Pillar 3) | `retrieval.py` L335-338 | Prevents LLM confusion | ✅ `vector_pruned_to_top1` badge |
| Semantic Cache | `engine/semantic_cache.py` | Latency reduction | ✅ Badge only, no hit rate |
| Token Budget Management | `engine/context_engineering.py` | Prevents hallucination | ❌ No metric exposed |
| Quality Gate | `retrieval/context.py` | Guards low-quality answers | ❌ Never surfaced |
| RRF Fusion | `retrieval.py` L354-360 | Aligns prose + graph | ❌ Never surfaced (also broken — see Issue 1) |
| Taxonomy Scoping | `vector/client.py` | Reduces noise chunks | ❌ No before/after count |

---

## 🟡 Issue 4 — Dual Engine Architecture Inconsistency

Two completely separate execution paths exist in production:

```
Path A (API route /query → query.py):
  engine/faiss_store.BrochureFAISSStore → engine/retrieval.hybrid_graphrag()
  Uses: BAAI/bge-small-en-v1.5 (sentence_transformers), engine/graph_store.py

Path B (app/retrieval/ orchestrator — WS5 layer):
  app/vector/client.VectorStore → app/retrieval/orchestrator.RetrievalOrchestrator
  Uses: fastembed (TextEmbedding), app/graph/client.GraphClient
```

**These two paths use different:**
- Embedding models and libraries (`sentence_transformers` vs `fastembed`)
- FAISS index locations (`engine/faiss_indexes/amc_master/` vs `backend/faiss_indexes/`)
- Graph clients (direct neo4j driver vs `GraphClient` wrapper with Cypher library)
- Query schemas (`Dict[str, Any]` vs typed Pydantic `RetrievalResult`)

The WS5 orchestrator (`app/retrieval/`) represents the architecturally superior path (typed schemas, intent classification, quality gate, token budget) but **the API routes bypass it entirely** in favor of the legacy engine.

---

## 🟡 Issue 5 — Missing Cross-Store Integrity Validation

There is no utility or check that verifies:
1. Every document ingested into FAISS also has a `Document` node in Neo4j
2. Every entity extracted by NER has a corresponding chunk in FAISS that mentions it
3. Graph relationships reference source document IDs that exist in the vector store
4. Taxonomy paths assigned to chunks match taxonomy nodes in the graph

Without this, silent drift accumulates every time a new document is ingested through only one pipeline.

---

## 🟢 Additional Issues Found

### A. HyDE Latency Not Isolated
HyDE's latency is baked into `retrieve_time` (`retrieve_time = ... + (hyde_latency / 1000.0)`, line 244). When HyDE fails or is slow, it's invisible in telemetry — appears as vector search latency.

### B. Semantic Cache TTL / Invalidation Missing
`engine/semantic_cache.py` stores responses with no TTL or invalidation on new ingestion. A user could get a stale cached response after new documents are added.

### C. `selected_source_documents` Category Assignments Inconsistent
In `build_50doc_faiss_index.py`, `AEL_Earnings_Call_Q1_FY19.pdf` is categorized as `adani_corporate` but `April 2024.pdf`, `May 2024.pdf` are categorized as `fund_performance`. However, the graph's NER pipeline would assign different labels based on text content — diverging from the hardcoded categories.

### D. Context Engineering Prompt Hardcoded Budget
`context_engineering.py` has `DEFAULT_TOKEN_BUDGET = 1200` as a constant — never adapted to the specific LLM being called (Claude Haiku vs Sonnet have different optimal context lengths) and never surfaced as a metric.

---

## 📋 Recommended Fixes — Priority Order

### P0 (Fix First — Correctness)
1. **Unified ingestion ID contract**: All ingestion paths must write the same `document_id` format to both FAISS payload and Neo4j, enabling reliable cross-store joins.
2. **Single canonical ingestion pipeline**: Route all document ingestion through `app/ingestion/pipeline.py` (or make engine path write equivalent graph nodes). Retire the parallel `build_50doc_faiss_index.py` / `build_taxonomy_graph.py` paths for production.
3. **Graph schema alignment**: Ensure `traversal.py` Cypher queries match the node labels actually written by the ingestion pipeline (`Entity`, `Document`, `TaxonomyNode`) vs the taxonomy graph (`SchemeClass`, `RegulatoryRegime`).

### P1 (Metrics — Capture Everything)
4. **Step-level `MetricsCollector`**: Thread a `MetricsCollector` dataclass through every pipeline stage that records: per-step latency, input/output counts, quality scores, and paradigm attribution flags. Emit in API response as `pipeline_trace`.
5. **Expose WS5 quality gate score** in the API response so the UI can show when a low-quality context triggered a degraded answer.
6. **Cache metrics**: Add `cache_hit`, `cache_similarity_score`, `cache_ttl_remaining` to telemetry.

### P2 (Showcase Value)
7. **Paradigm attribution panel**: For each query, show a breakdown card: "HyDE improved recall by X chunks", "Token budget saved Y tokens", "Graph facts replaced Z vector chunks", "Quality gate threshold: A, score: B".
8. **Cross-store integrity check script**: Add `scripts/validate_store_consistency.py` that counts and reports mismatches between FAISS and Neo4j for each document.
9. **Activate WS5 orchestrator through API**: Wire the `/query/contextgraph` route to use `RetrievalOrchestrator` (the architecturally complete path) instead of the legacy `hybrid_graphrag()`.

---

## Summary Table

| # | Issue | Severity | Impact |
|---|---|---|---|
| 1 | Vector DB ↔ Graph mismatch (separate pipelines, incompatible keys) | 🔴 Critical | Wrong/missed answers, broken RRF fusion |
| 2 | Missing step-level metrics | 🔴 High | Cannot debug or showcase quality |
| 3 | Context engineering value not measurable/visible | 🟡 Medium | No proof of paradigm superiority |
| 4 | Dual engine architecture (API bypasses WS5 orchestrator) | 🟡 Medium | Technical debt, inconsistent behavior |
| 5 | No cross-store integrity validation | 🟡 Medium | Silent drift after every ingestion |
| A | HyDE latency hidden inside vector timing | 🟢 Low | Misleading telemetry |
| B | Cache has no TTL/invalidation | 🟢 Low | Stale answers post-ingestion |
| C | Hardcoded categories vs NER-assigned labels diverge | 🟢 Low | Inconsistent metadata |
| D | Token budget constant, not adaptive | 🟢 Low | Suboptimal context for different LLMs |
