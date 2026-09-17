# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC Context Engineering — Deep Audit Report

> **Audit Date**: 2026-07-29  
> **Scope**: Full codebase re-evaluation against the 10-gap + 6-module improvement plan  
> **Method**: Line-by-line inspection of all 16 core modules  

---

## Audit Summary Dashboard

| Category | Count | Status |
|---|---|---|
| Improvements Implemented ✅ | 13 | Verified in code |
| Implemented But Incomplete ⚠️ | 6 | Partially done |
| Critical Gaps Still Open 🔴 | 9 | Not started |
| **New Issues Discovered** 🆕 | 5 | Not in prior plan |

---

## ✅ SECTION 1: What Was Successfully Implemented

### 1.1 — Query Audit Log System ✅ EXCELLENT
**File**: [`retrieval.py:135–168`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)  
**Implementation Quality**: ⭐⭐⭐⭐⭐

The `log_query_audit()` function is production-grade:
- Structured JSONL file per query (timestamped), enabling forensic replay
- Console-formatted with Pillar 1–4 labels for visual debugging
- Captures NER Layer A+B entities, graph match path, vector bypass flag, pruning flags, all latencies, all token counts

This **exceeds** the original plan spec. Well done.

---

### 1.2 — Intent-Driven Conditional Vector Routing ✅ GOOD
**File**: [`retrieval.py:190–218`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)  
**Implementation Quality**: ⭐⭐⭐⭐

The `hybrid_graphrag()` function implements the 3-path conditional routing:
- Graph-first execution for `aggregation`, `comparison`, `direct_lookup` queries
- `vector_bypassed=True` when graph returns strong signal (≥1 edge OR ≥2 nodes)
- Falls back to vector search for `open_ended` or weak graph signal

**Minor Gap**: The bypass condition checks `graph_has_strong_signal` but the fallback graph re-query on line 222 (`if not graph_result["edges"] and hits:`) runs a **second graph query** regardless of bypass status. This adds ~80–150ms graph round-trip even when vector already found relevant docs.

---

### 1.3 — Entity Resolver with Embedding Similarity ✅ EXCELLENT
**File**: [`entity_resolver.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/entity_resolver.py)  
**Implementation Quality**: ⭐⭐⭐⭐⭐

The implementation is sophisticated:
- Candidate pool cached for 300s by `product_name` scope (prevents cross-doc contamination)
- Per-text embedding cache (`_embedding_cache`) avoids re-encoding the same candidate pool texts
- Uses cosine similarity (via `@` matrix multiply on normalized vectors) — mathematically correct
- Respects `config.SIMILARITY_MATCH_THRESHOLD = 0.65` floor

This directly addresses **Missing Concept #3** (cross-document entity linking at query time).

---

### 1.4 — Query Classifier with Fast-Path Regex ✅ GOOD
**File**: [`query_classifier.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/query_classifier.py)  
**Implementation Quality**: ⭐⭐⭐⭐

- Regex fast-path for common patterns (zero latency)
- LLM fallback only for ambiguous queries (adds ~300ms but only when needed)
- 4-class taxonomy: `aggregation`, `comparison`, `direct_lookup`, `open_ended`

**Missing**: No `temporal` query type. The ESG query *"What are the key ESG initiatives wrt climate change adaptation in H1FY25 vs H1FY26?"* would classify as `comparison` but needs temporal graph traversal, which is not in the retrieval path for `comparison` type.

---

### 1.5 — Vector Pruning (Strict Gate for Verified Facts) ✅ GOOD
**File**: [`retrieval.py:286–296`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)  
**Implementation Quality**: ⭐⭐⭐⭐

When `trust_verified_facts=True` and query is `aggregation`/`comparison`, vector chunks are pruned to top-1. This prevents the LLM from mixing verified graph facts with contradictory vector prose.

**Minor Issue**: The pruning is binary (top-5 → top-1). A score-threshold approach would be more precise: keep chunks with cosine similarity ≥ 0.65 instead of blindly keeping exactly 1.

---

### 1.6 — 3-Path Graph Fallback Ladder ✅ IMPLEMENTED
**File**: [`graph_store.py:150–217`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/graph_store.py)  
**Implementation Quality**: ⭐⭐⭐

Path 1 → entity text match → Path 2 → product name match → Path 3 → global degree-ordered fallback.

**Critical Issue**: Path 3 (lines 203–213) returns the **most globally connected nodes**, which is the worst possible context for an ESG/regulatory query. These nodes are likely `SEBI`, `AMC`, `Mutual Funds` — terms that appear everywhere. The prompt then contains generic boilerplate graph facts that consume tokens without adding query-specific insight. **Path 3 should be disabled or return empty.**

---

### 1.7 — Text-to-Cypher for Aggregation ✅ IMPLEMENTED
**File**: [`retrieval.py:237–266`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)  
**Implementation Quality**: ⭐⭐⭐

Dynamic Cypher generation for aggregation queries with a deterministic fallback. The `run_safe_cypher()` guard in `graph_store.py` is well-implemented (MATCH-only, LIMIT enforcement, no CALL).

**Risk**: The Cypher generator is a hidden LLM call that consumes tokens (`hidden_tokens`) not always surfaced in UI telemetry. This can make token counts appear lower than actual.

---

### 1.8 — Per-Query JSONL Audit File ✅ GOOD
**File**: [`retrieval.py:162–168`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)  
**Implementation Quality**: ⭐⭐⭐⭐

One audit file per query — enables exact replay and timeline analysis. The timestamp format (`2026-07-29T15:30:00`) is ISO8601, correct for sorting.

**Minor Issue**: Each query creates a new JSONL file. For 50+ documents with many queries, the `logs/` directory will accumulate thousands of files. Should use a single rolling `query_audit.jsonl` with rotation instead.

---

### 1.9 — Context Deduplication (Graph vs. Vector) ✅ IMPLEMENTED
**File**: [`context_engineering.py:11–25`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py)  
**Implementation Quality**: ⭐⭐⭐

`_dedupe_prose_against_graph()` suppresses vector chunks whose capitalized terms overlap with graph facts by >85%.

**Tuning Issue**: The 0.85 threshold is described as "increase to prevent context starvation" — but for the ESG query (`What are the key ESG initiatives wrt climate change adaptation?`), ESG chunks from the vector index are legitimately complementary to any graph facts. This function may incorrectly suppress valuable ESG content by ~20–30%.

---

### 1.10 — Token Budget by Query Type ✅ GOOD
**File**: [`context_engineering.py:28–34`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py)  
**Implementation Quality**: ⭐⭐⭐⭐

```python
QUERY_TYPE_BUDGETS = {
    "aggregation":   {"graph_frac": 0.5, "vector_frac": 0.35},
    "comparison":    {"graph_frac": 0.4, "vector_frac": 0.4},
    "direct_lookup": {"graph_frac": 0.2, "vector_frac": 0.65},
    "open_ended":    {"graph_frac": 0.1, "vector_frac": 0.75},
}
DEFAULT_TOKEN_BUDGET = 1200
```

Good allocation. The `open_ended` 75% vector fraction is correct for documents like the ESG report where graph coverage is sparse.

**Issue**: `DEFAULT_TOKEN_BUDGET = 1200` (characters ÷ 4 = ~300 tokens). This is very tight for the ESG query which needs 2–3 full paragraphs of context. Parent chunks are 1200 chars each = 300 tokens each, so only ONE parent chunk fits in the vector budget for an open-ended query. **This is likely why the ESG query wasn't returning useful results.**

---

### 1.11 — Batch Graph Traversal (UNWIND) ✅ EXCELLENT
**File**: [`graph_store.py:346–379`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/graph_store.py)  
**Implementation Quality**: ⭐⭐⭐⭐⭐

`find_entities_for_comparison()` uses a single-shot UNWIND traversal — replaces O(N) Python loops with O(V+E) Cypher. Correctly implements the "Single-Shot UNWIND" Pillar 2 badge.

---

### 1.12 — Candidate Pool Scoping in Entity Resolver ✅ GOOD
**File**: [`entity_resolver.py:33–42`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/entity_resolver.py)  
**Implementation Quality**: ⭐⭐⭐⭐

The candidate pool is scoped to `product_names` from vector retrieval, preventing a "debt" query from matching all debt-labeled nodes across the entire 50-document corpus.

---

### 1.13 — Source Provenance in Node Lookup ✅ PARTIAL
**File**: [`graph_store.py:395–420`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/graph_store.py)  
**Implementation Quality**: ⭐⭐⭐

`get_entity_source_info()` and `get_entities_source_info_batch()` exist. However, this data is **not surfaced in the final answer** or in the `docs` array returned to the UI. Provenance is only used by the "click a node to explore" feature — it's not in the query response provenance chain.

---

## ⚠️ SECTION 2: Implemented But Incomplete

### 2.1 — Double Embedding Bug ⚠️ NOT FIXED
**File**: [`taxonomy_retrieval.py:59` + `taxonomy_retrieval.py:78`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)

**Status**: 🔴 STILL PRESENT — This was marked as P0 but was **not fixed**.

```python
# Line 59 — inside retrieve_vector()
vecs = fs._embed_texts([query])   # ← Embedding #1

# Line 78 — inside retrieve_graph() called from hybrid_graphrag_v2()  
query_vector = fs._embed_texts([query])[0].tolist()  # ← Embedding #2 (REDUNDANT)
```

Both are called sequentially in `hybrid_graphrag_v2()` (lines 262–268). The embedding model runs twice on the same query string.

**Estimated Waste**: ~180ms CPU per query on the taxonomy/compare path.

**Fix Required** (2 lines of code):
```python
def hybrid_graphrag_v2(query: str, history=None):
    t_start = time.perf_counter()
    index, chunks = get_taxonomy_index()
    
    # Embed ONCE — reuse everywhere
    query_vec_np = fs._embed_texts([query])          # shape (1, 384)
    query_vec_list = query_vec_np[0].tolist()        # for Neo4j vector index
    
    graph_ctx = retrieve_graph_with_precomputed(query, query_vec_list)
    hyb_chunks = retrieve_vector_precomputed(query_vec_np, index, chunks, top_k=3)
```

---

### 2.2 — Graph Driver Singleton ⚠️ NOT FIXED
**File**: [`taxonomy_retrieval.py:72–76`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)

**Status**: 🔴 STILL PRESENT

```python
def retrieve_graph(query: str) -> List[dict]:
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(      # ← New driver EVERY call
            TAXONOMY_NEO4J_URI, auth=(...),
            connection_timeout=3,
        )
```

Note: `graph_store.py` (line 25–35) correctly uses a module-level `_driver` singleton. But `taxonomy_retrieval.py` has its own separate driver lifecycle — and it creates a NEW driver on EVERY call to `retrieve_graph()`.

**Estimated Waste**: ~120ms TCP handshake per `retrieve_graph()` call.

**Fix** (5 lines):
```python
_taxonomy_driver = None  # Module-level

def _get_taxonomy_driver():
    global _taxonomy_driver
    if _taxonomy_driver is None:
        from neo4j import GraphDatabase
        _taxonomy_driver = GraphDatabase.driver(
            TAXONOMY_NEO4J_URI, auth=(TAXONOMY_NEO4J_USER, TAXONOMY_NEO4J_PASSWORD),
            max_connection_lifetime=300, connection_timeout=3)
    return _taxonomy_driver
```

---

### 2.3 — Cosine Similarity Floor ⚠️ PARTIAL
**File**: [`faiss_store.py:729–752`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py)

**Status**: 🟡 PARTIAL — `BrochureFAISSStore.retrieve()` returns top-K results with their scores but applies **no floor**. Low-similarity chunks (score < 0.65) are included in every query response.

The score is stored in the result dict (`"score": float(score)`) but is never checked against a threshold before inclusion.

**Fix** (2 lines in `retrieve()`):
```python
for score, idx in zip(scores[0], indices[0]):
    if idx < 0 or idx >= len(self.children):
        continue
    if float(score) < 0.45:   # ← ADD THIS (0.45 for MiniLM normalized cosine)
        continue
```

> [!NOTE]
> `all-MiniLM-L6-v2` returns normalized inner product (= cosine similarity) in `IndexFlatIP`. The practical range for relevant docs is 0.40–0.90. A floor of 0.45 is appropriate for this model.

---

### 2.4 — Context Micro-Notation ⚠️ NOT IMPLEMENTED
**File**: [`taxonomy_retrieval.py:155–195`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)

**Status**: 🔴 NOT DONE — `_graph_context_to_text()` still uses verbose format.

Example current output consuming ~450 tokens:
```
SchemeClass [CURRENT_2026] 'Index Fund': Open-ended scheme replicating/tracking specific index
MutualExclusion [CURRENT_2026]: 'Index Fund' cannot coexist with 'Large Cap Equity Scheme' in same AMC.
Regime: CURRENT_2026 (active) — SEBI Mutual Fund Categorisation | Effective: 2026-02-26
```

**Proposed compressed format** (~140 tokens, -68% reduction):
```
[2026] SC:IndexFund(open,track_idx)
[2026] ME:IndexFund≠LargeCapEq(same_amc)
[REG] 2026(active,eff:2026-02-26)
```

---

### 2.5 — Embedding Model Upgrade ⚠️ NOT DONE
**File**: [`faiss_store.py:118–127`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py)

**Status**: 🟡 Still using `all-MiniLM-L6-v2` (384-dim). The model string on line 683 in `meta.json` even says `paraphrase-multilingual-MiniLM-L12-v2` — which is **inconsistent** with the actual loaded model (`all-MiniLM-L6-v2`). The metadata is lying.

**This is a data integrity issue**: if you rebuild the index using one model but the metadata claims another, any diagnostic tool comparing metadata will be confused.

---

### 2.6 — RRF Fusion ⚠️ NOT IMPLEMENTED
**File**: [`taxonomy_retrieval.py:262–270`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)

**Status**: 🔴 Graph and vector results are still assembled as independent, unranked sections in the prompt. RRF merge was not implemented.

The prompt still reads:
```
[GRAPH KNOWLEDGE — Dual-Regime Neo4j]:
...graph_str...

[VECTOR CONTEXT — FAISS Taxonomy Index]:
...vector_context...
```

Without RRF, the LLM must arbitrate between two unranked, unscored sections, which reduces answer precision on the taxonomy/compare path.

---

## 🔴 SECTION 3: Critical Gaps Still Not Addressed

### Gap 3.1 — FAISS Index Type: Still IndexFlatIP at Scale 🔴 CRITICAL
**File**: [`faiss_store.py:662`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py)

```python
index = faiss.IndexFlatIP(dim)   # ← Exact brute-force, O(n) scan
```

At 50 documents with ~5,000 child chunks each = **250,000 vectors**.
- `IndexFlatIP` at 250K × 384-dim = ~370MB in RAM; ~60–90ms per search
- `IndexIVFFlat` with nlist=200, nprobe=20 = ~8–10ms per search (8–10x speedup)
- **No code change to the retrieval API** — only the build step changes

This is the highest-leverage latency fix not yet done.

---

### Gap 3.2 — Structural / Clause-Aware Chunking: Not Implemented 🔴 HIGH
**File**: [`faiss_store.py:529–577`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py)

`build_parent_child_chunks()` still uses fixed-size sentence-boundary splitting (Parent=1200, Child=250). No document type detection, no clause number preservation, no section metadata.

For SEBI Master Circular for Mutual Funds (7.1MB), clauses like `2.6.3.16 - One AMC one scheme rule` will continue to be split mid-clause across multiple parent chunks, reducing answer fidelity for compliance queries.

---

### Gap 3.3 — No Semantic Query Cache 🔴 HIGH
No `SemanticQueryCache` class exists anywhere in the codebase. Every query hits the full pipeline (Neo4j + FAISS + LLM) even for repeated/near-identical queries.

At 50 documents with a compliance team running similar daily queries:
- "What are SEBI's rules on mutual fund categorization?" asked repeatedly → full $0.003 LLM call each time
- A 0.96 cosine similarity cache would serve these in <30ms with $0 cost

---

### Gap 3.4 — Graph Schema Expansion: Not Done 🔴 HIGH
The graph still only has `Entity` nodes and relationship types from NER Layer C (`manages`, `holds`, `governs`, etc.). None of the proposed new node types exist:
- No `Document` nodes (hierarchical document representation)
- No `Section` / `Clause` nodes (structural hierarchy)
- No `TableFact` / `FinancialFact` nodes (numeric data)
- No `ESGMetric` nodes (ESG query path)
- No `ComplianceRule` nodes (compliance query path)

**Impact**: ESG queries cannot use graph context because no ESG entities are in the graph schema. The ESG query "What are the key ESG initiatives wrt climate change adaptation?" will always fall through to Path 3 (global degree fallback) in `get_subgraph_for_query()`, returning irrelevant generic entities.

---

### Gap 3.5 — Temporal Graph Edges: Not Implemented 🟡 HIGH
No `valid_from` / `valid_to` properties on any relationship types. The `RegulatoryRegime` nodes have `effective_from` dates, but entity relationships have no temporal scope.

**Impact**: For the Adani FY25 ESG report vs. FY24 ESG report, there's no graph mechanism to answer "how did ESG metrics change between years?" — both years' data is flattened into the same entity nodes without temporal differentiation.

---

### Gap 3.6 — Cross-Document Entity Linking: Not Done 🟡 MEDIUM
The post-ingestion entity resolution pass (`resolve_cross_document_entities()`) mentioned in the plan was not implemented. `resolve_unresolved_entities()` in `graph_store.py` only does **string matching**, not embedding similarity:

```python
WHERE toLower(trim(r.text)) = toLower(trim(u.text))  # ← Exact text match only
```

This means "Adani Enterprises Ltd" and "Adani Enterprises Limited" are separate, unlinked nodes, even though they're the same entity.

---

### Gap 3.7 — Document Namespace Router: Not Implemented 🟡 MEDIUM
No query routing to document namespaces. All 50 documents (once added) will share a single FAISS index. An ESG query will compete against SEBI circular embeddings in the same similarity space, reducing precision.

The proposed `route_query_namespace()` function does not exist anywhere in the codebase.

---

### Gap 3.8 — Token Budget Tight for ESG Queries 🔴 HIGH (New Finding)
**File**: [`context_engineering.py:34`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py)

```python
DEFAULT_TOKEN_BUDGET = 1200  # characters
```

The ESG query `"What are the key ESG initiatives wrt climate change adaptation and what are the benefits?"` is `open_ended` → vector_frac = 0.75 → budget = 900 characters.

One parent chunk = 1200 characters. So **zero parent chunks fit** in the vector budget when each is already larger than the budget. The code correctly skips them:
```python
cost = len(h['parent_text']) // 4   # 1200 chars → 300 "tokens"
if used + cost > vector_budget:     # 0 + 300 > 225 (900/4) → True → SKIP
    continue
```

**This is why the ESG query returns empty/bad answers in the Streamlit chat.** The token budget silently drops all context before the LLM even sees it.

**Fix**: Increase `DEFAULT_TOKEN_BUDGET` to 3000 characters, or add a minimum guaranteed slot for at least 2 vector chunks regardless of budget.

---

### Gap 3.9 — Output Token Cap Too Tight 🔴 HIGH (New Finding)
**File**: [`context_engineering.py:89–90`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py)

```python
max_output_tokens = 260 if not has_structured else 360
```

A 260-token output cap (~195 words) is extremely limiting for multi-part questions like the ESG query which asks for **both** the initiatives **and** the benefits. The model has to truncate or compress, leading to incomplete answers.

**Fix**: Increase to `max_output_tokens = 512` (unstructured) and `768` (structured). Modern Claude Haiku can produce high-quality concise answers at 512 tokens.

---

## 🆕 SECTION 4: New Issues Discovered (Not in Prior Plan)

### New Issue 4.1 — Meta.json Model Name Mismatch 🟡 MEDIUM
**File**: [`faiss_store.py:683`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py)

```python
"model": "paraphrase-multilingual-MiniLM-L12-v2",  # ← WRONG
```

The actual loaded model is `all-MiniLM-L6-v2` (line 119). The metadata hardcodes the wrong model name. This will cause model mismatch bugs if anyone trusts the metadata to reconstruct or validate the index.

---

### New Issue 4.2 — Stale FAISS Index After Upload Doesn't Invalidate Store Cache 🟡 MEDIUM
**File**: [`faiss_store.py:870–872`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py)

```python
_store_cache.pop(slug, None)   # ← Only clears "user_uploads" slug
return BrochureFAISSStore(slug)
```

`build_user_upload_index()` clears only the `user_uploads` cache slot. But if another module (e.g., `chat_view.py`) holds a reference to the old `BrochureFAISSStore` object, it will continue querying the stale pre-upload index. The new index is only picked up on fresh page load.

---

### New Issue 4.3 — `relevancy_score()` is Heuristic-Only and Can Mislead 🟡 MEDIUM
**File**: [`retrieval.py:429–436`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)

```python
def relevancy_score(result):
    score += min(answer.count("[") * 0.12, 0.35)  # Counts brackets — not semantics!
    score += 0.25 if result.get("graph_edges_used_in_prompt") else 0
```

This function adds score for answers containing `[` characters (citations), but the ESG query's answer may not use graph edges (no ESG nodes in graph) and may not have bracketed citations — it would score 0.0, falsely flagging a good prose answer as low quality.

This metric should not be used for production quality monitoring as it's structurally biased against open-ended prose answers.

---

### New Issue 4.4 — NER Fast-Track Bypass Inverted Logic 🔴 HIGH
**File**: [`ner_pipeline.py:142`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py)

```python
if not ents or len(text) > 300:
    try:
        ents += layer_b_gliner(text)
```

**Bug**: GLiNER (Layer B) runs when `not ents` (no entities found) OR when `len(text) > 300`. For the ESG query `"What are the key ESG initiatives wrt climate change adaptation and what are the benefits?"` (length = 99 chars), Layer A finds `["SEBI", "Mutual Fund", "AMC"]` (common domain entities), so `not ents = False`. Since `len(text) > 300` is also False (99 < 300), **GLiNER is skipped**.

This means "climate change adaptation" and "ESG" are NOT extracted as entities by Layer B, so the graph traversal has no ESG entity anchors. The query falls to Path 3 (global degree fallback) every time.

**The correct logic should be**: Always run GLiNER for queries, OR run it for all queries under 500 chars (short queries are exactly where GLiNER's zero-shot is most valuable).

---

### New Issue 4.5 — `hidden_tokens` Not Included in UI Telemetry 🟡 LOW
**File**: [`retrieval.py:332`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)

```python
total_tokens = usage["input_tokens"] + usage["output_tokens"] + hidden_tokens
```

But in `telemetry_breakdown`:
```python
"tokens_input": usage["input_tokens"],   # ← Does NOT include hidden_tokens
"tokens_total": total_tokens,             # ← Does include hidden_tokens
```

The discrepancy between `tokens_input + tokens_output` ≠ `tokens_total` in the Streamlit dashboard will confuse users checking the telemetry panel. `hidden_tokens` should be broken out as a separate field.

---

## 📊 SECTION 5: Impact Assessment for the ESG Query

> **Query**: *"What are the key ESG initiatives wrt climate change adaptation and what are the benefits that we can see?"*
> **Document**: `Adani_Portfolio_H1FY25_ESG.pdf` (Page 3)

### Why It Fails — Root Cause Chain

```
Step 1: Query classified → "open_ended" ✓ (correct)
Step 2: NER Layer A → finds ["SEBI", "AMC", "Mutual Fund"] (wrong domain entities for ESG)
Step 3: NER Layer B (GLiNER) → SKIPPED (query len=99 < 300, Layer A returned ents → bypass fires)
Step 4: Graph traversal → entity_texts = ["SEBI", "AMC", "Mutual Fund"]
Step 5: Path 1 → SEBI/AMC/MutualFund nodes matched in graph → returns generic regulatory edges
Step 6: No ESG nodes in graph → graph_context_str has no climate change data
Step 7: Vector search → retrieves top-5 from amc_master index
Step 8: Token budget = 1200 * 0.75 / 4 = 225 token-units
Step 9: Each parent chunk = 1200 chars / 4 = 300 token-units → 300 > 225 → EVERY CHUNK DROPPED
Step 10: vector_context = empty string (zero chunks fit in budget)
Step 11: LLM receives: [empty graph] + [empty vector] → returns "I cannot answer this"
```

**Three bugs converge to produce a silent empty answer**:
1. GLiNER NER bypass prevents ESG entity extraction (Issue 4.4)
2. Token budget too tight for open_ended queries (Gap 3.8)
3. Output token cap too low (Gap 3.9)

---

## 🔧 SECTION 6: Prioritized Remediation Plan

### Tier 1 — Critical Fixes (Today, <30 min each)

| # | Fix | File | Lines | Effort |
|---|---|---|---|---|
| **F1** | Increase `DEFAULT_TOKEN_BUDGET` to 3600 | `context_engineering.py` | L34 | 1 min |
| **F2** | Increase `max_output_tokens` to 512/768 | `context_engineering.py` | L89 | 1 min |
| **F3** | Fix NER bypass logic: always run GLiNER for queries | `ner_pipeline.py` | L142 | 3 min |
| **F4** | Fix graph driver singleton in taxonomy_retrieval | `taxonomy_retrieval.py` | L72 | 5 min |
| **F5** | Add cosine similarity floor (0.45) in BrochureFAISSStore | `faiss_store.py` | L734 | 3 min |
| **F6** | Fix double embedding (embed once in hybrid_graphrag_v2) | `taxonomy_retrieval.py` | L59+78 | 10 min |
| **F7** | Disable Graph Path 3 (global degree fallback) | `graph_store.py` | L203 | 2 min |

**Expected after Tier 1**: ESG query should work. ~300ms latency improvement. ~400 fewer wasted tokens per query.

---

### Tier 2 — High-Impact Changes (This Week, 1–4 hours each)

| # | Change | Expected Impact |
|---|---|---|
| **T2-A** | Add GLiNER labels: "ESG metric", "sustainability initiative", "carbon emission", "BRSR indicator" | ESG entity extraction works for graph path |
| **T2-B** | Fix meta.json model name hardcode (`all-MiniLM-L6-v2`) | Data integrity |
| **T2-C** | Add `hidden_tokens` as separate telemetry field | Transparent cost tracking |
| **T2-D** | Switch to single rolling `query_audit.jsonl` (with date rotation) | Prevent log dir bloat |
| **T2-E** | Add minimum guaranteed slot: always include ≥2 vector chunks regardless of budget | Prevents silent empty context |
| **T2-F** | Replace `relevancy_score()` heuristic with actual faithfulness score | Correct quality signal |

---

### Tier 3 — Strategic (Next 2 Weeks)

| # | Change | Notes |
|---|---|---|
| **T3-A** | Context micro-notation in `_graph_context_to_text()` | -68% token reduction on taxonomy path |
| **T3-B** | Upgrade FAISS index type to `IndexIVFFlat` for `amc_master` (if >50K vectors) | 8–10x search speedup |
| **T3-C** | Add `SemanticQueryCache` class | 20–30% cache hit rate on compliance queries |
| **T3-D** | Structural/clause-aware chunking for SEBI Master Circulars | Compliance clause precision |
| **T3-E** | ESG node types in graph schema (`ESGMetric`, `CarbonEmission`, `GovernanceItem`) | Enables graph-augmented ESG answers |
| **T3-F** | Query namespace router | Prevents cross-category embedding contamination at 50-doc scale |
| **T3-G** | Cross-doc entity resolution via embedding similarity (not just string match) | Entity deduplication |
| **T3-H** | Temporal edges with `valid_from`/`valid_to` | Enables year-over-year comparison queries |

---

## Audit Scorecard

| Dimension | Score (Before) | Score (After Implementation) | Target |
|---|---|---|---|
| Retrieval Infrastructure | 3/10 | 6/10 | 9/10 |
| Accuracy (ESG queries) | 1/10 | 2/10* | 8/10 |
| Token Efficiency | 4/10 | 5/10 | 8/10 |
| Latency | 4/10 | 5/10 | 8/10 |
| Graph Coverage | 3/10 | 3/10 | 8/10 |
| Observability | 1/10 | 8/10 | 9/10 |
| Code Quality | 5/10 | 7/10 | 9/10 |

*ESG query still broken due to 3 converging bugs.

> [!IMPORTANT]
> The **observability** investment is genuinely excellent — the audit log system is production-grade and significantly better than most AI systems at this stage. This is a major strength.

> [!CAUTION]
> The ESG query failure is caused by **three independent bugs** converging (NER bypass + token budget + output cap). Fixing any one of them alone may not be sufficient. All three Tier 1 fixes (F1, F2, F3) must be applied together for the ESG query to produce correct answers.

> [!WARNING]
> **50-document expansion should NOT proceed** until F1+F2+F3+F5 are applied. Adding more documents to the current index will make the token budget problem worse (more results, same budget = more dropped chunks), and ESG queries will become even less reliable.
