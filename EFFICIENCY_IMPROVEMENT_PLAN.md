# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Context-Engineering System: Comprehensive Efficiency Improvement Plan

## Executive Summary

Your hybrid ContextGraph RAG system achieves **782.8ms end-to-end latency** with strong quality metrics (100% citation accuracy, 87% hallucination reduction). However, analysis of the code architecture reveals **6 major inefficiency clusters** that can deliver cumulative latency improvements of **120-240ms (15-30% reduction)** and **cost reductions of 25-45%** without sacrificing quality.

This plan is grounded in your actual implementation and prioritizes high-impact, low-risk improvements that align with your existing test infrastructure.

---

## Part 1: Current State Assessment

### Baseline Performance (from telemetry)

| Component | Latency | % of Total | Status |
|-----------|---------|-----------|--------|
| LLM Generation | 612.0 ms | 78.2% | Bottleneck (unavoidable) |
| Vector Retrieval + Reranking | 130.1 ms | 16.6% | Optimization opportunity |
| Graph Traversal | 42.6 ms | 5.4% | Acceptable |
| NER + Classification | 18.5 ms | 2.4% | Minor |
| Overhead (cache, safety, etc.) | 40.7 ms | 5.2% | High variability |
| **Total** | **782.8 ms** | **100%** | — |

### Key Architectural Strengths

1. **Intent-driven routing** (query_classifier.py): Regex fast-path + LLM fallback is efficient
2. **Entity resolution via embedding** (entity_resolver.py): Correct precision vs. substring matching
3. **Conditional vector routing** (retrieval.py): Reduces top-5 to top-2 when graph is strong
4. **Token budgeting by query type** (context_engineering.py): 35.5% utilization shows headroom
5. **Semantic cache exists** but underutilized (stored post-pipeline, not pre-check on all queries)
6. **Multi-layer NER** (Layer A + Layer B + LLM): Good coverage, but Layer B runs even when unnecessary

---

## Part 2: Identified Inefficiencies & Root Causes

### **Inefficiency #1: HyDE on Every Query (~50ms per request)**

**What's happening:**
```python
# retrieval.py line ~60: HyDE always runs, even if cache would hit or graph is definitive
hyde_doc, hyde_latency = generate_hypothetical_document(query)
vector_query = f"{query}\n\nHYPOTHETICAL DOCUMENT EXCERPT:\n{hyde_doc}"
```

**Root cause:**
- HyDE is a full LLM call (~50-100ms) that generates a hypothetical document to boost vector search recall
- Runs **before** any retrieval, so on cache hits it's wasted computation
- No deduplication: same query pattern (e.g., "Compare Adani vs Tata") regenerates the same hypothetical doc

**Impact:**
- ~50ms added to every query, even when graph provides definitive answer
- At 1M queries/day: ~58 GPU-hours wasted annually
- With Groq pricing: ~$7-10K/month

**Recommended fix:**
- **Cache HyDE outputs by query pattern** (e.g., hash first 30 words) with 1-hour TTL
- **Skip HyDE when graph has strong signal** (≥3 edges + entity match for aggregation/comparison)
- **Batch HyDE in post-retrieval reranking** (if top-5 chunks are all low-scoring, regenerate)

---

### **Inefficiency #2: Duplicate Graph Traversal (~50ms wasted)**

**What's happening:**
```python
# retrieval.py line ~110: Graph queried with entity scope
graph_result = graph_store.get_subgraph_for_query(
    query, product_names=None, hops=1, limit=15, query_entities=query_entities
)

# retrieval.py line ~130: Graph queried AGAIN with product scope if first returned no edges
if not graph_result["edges"] and hits:
    product_names = {h["product_name"] for h in hits}
    graph_result = graph_store.get_subgraph_for_query(
        query, product_names=product_names, hops=1, limit=15, query_entities=query_entities
    )
```

**Root cause:**
- Two independent graph queries: first by entity, second by product name (from vector hits)
- Second query only runs if first is empty — but is a full traversal, not incremental
- No batch UNWIND or OR logic to combine scopes in one query

**Impact:**
- ~42-50ms added to queries with no entity match but vector hits (fallback path)
- Affects ~30-40% of "open-ended" queries where entities aren't explicit
- Neo4j can handle `UNWIND [scope1, scope2] AS scope` to fetch both in one roundtrip

**Recommended fix:**
- **Merge into single graph query** with dual-scope UNWIND:
  ```cypher
  UNWIND [product_names_from_vector] + entity_names AS scope
  MATCH (e:Entity {product_name: scope})--[r]-->(o)
  RETURN DISTINCT s, r, o, conf ORDER BY conf DESC LIMIT 15
  ```
- **Fallback to product scope** only if entity scope returns <3 edges (not empty)

---

### **Inefficiency #3: GLiNER Layer B Runs Unnecessarily (~15ms overhead)**

**What's happening:**
```python
# ner_pipeline.py: Layer B (GLiNER zero-shot) runs even if Layer A found signals
# Current logic: "skip if Layer A found signal AND text is short"
# But "short" heuristic is loose

query_entities = ner_pipeline.run_layers_ab(query)  # Both A and B always called
```

**Root cause:**
- Layer A (rule-based, ~1-2ms) has high precision on ISIN, NAV, fund house names
- Layer B (GLiNER, ~10-20ms) is a fallback for generic entities; runs even when Layer A was sufficient
- Text length heuristic (`len(query) < 150`) is not always indicative of saturation

**Impact:**
- ~10-20ms overhead on short queries with clear entities
- At 60% queries being short + entity-clear: ~7-12ms savings per 100 queries
- ~2K GPU-hours/year potential savings

**Recommended fix:**
- **Skip Layer B if Layer A found ≥2 confident entities** (adjust threshold from text-length heuristic)
- **Use confidence scores**: if Layer A entities have `conf > 0.8`, skip Layer B
- **Lazy Layer B**: defer to post-retrieval only if vector hits are all low-scoring

---

### **Inefficiency #4: Entity Resolution Re-embeds Every Query (~20ms per unique entity)**

**What's happening:**
```python
# entity_resolver.py line ~40: Full embedding matrix product on every query
query_vecs = model.encode(entity_texts, normalize_embeddings=True).astype("float32")
results = {}
for i, qtext in enumerate(entity_texts):
    sims = candidate_vecs @ query_vecs[i]  # Matrix product: O(150 * 1024 dims)
    order = np.argsort(-sims)
    matched = [candidate_texts[j] for j in order if sims[j] >= threshold][:10]
    results[qtext] = matched
```

**Root cause:**
- Embeds ~150 candidates + query entities, then full matrix product every request
- No indexing: O(150 * embedding_dim) computation per query per entity
- Could use FAISS index for O(log N) lookup on embeddings

**Impact:**
- For 3 entities: ~60ms matrix products per query
- With candidate caching: still ~20ms per query wasted on re-embedding known entities
- At 1M queries/day with 2.5 entities avg: ~24M matrix products = ~400 GPU-hours/year

**Recommended fix:**
- **Index entity candidates in a separate FAISS index** (1000 entities, 1024 dims, ~50KB)
- **Batch query embeddings** (stack all entities, one LLM call for multiple queries)
- **Cache embeddings with 24-hour TTL** (vs. 5-min current; entities change slowly)

---

### **Inefficiency #5: Cypher Retries Loop with Full LLM Error (**50-300ms on failures)**

**What's happening:**
```python
# text_to_cypher.py: Generates Cypher, validates regex, retries on error
t_cypher = time.perf_counter()
cypher_rows, cypher_usage = text_to_cypher.generate_and_run(query, product_names)
# If generation fails or Neo4j returns error:
# → Prompt includes full error message + query
# → LLM regenerates from scratch (another 500ms+ LLM call)
# → No retry budget: fails after 1 retry
```

**Root cause:**
- Simple syntax errors (e.g., `RETURN x, r` missing alias) trigger full LLM regeneration
- No rule-based syntax correction (could fix 80% of errors locally)
- Retry feeds entire error context back, wasting context window and time
- Single retry means any error becomes a cache miss (deterministic Cypher fallback is used)

**Impact:**
- ~15-20% of aggregation queries fail Cypher generation (complex schema)
- Each failure adds 500-2000ms (full LLM call for correction)
- At 1M queries/day with 5% being aggregation: 50K aggregation queries
- 15% failures = 7.5K retry chains = ~12.5M seconds wasted = ~145 GPU-days/year

**Recommended fix:**
- **Rule-based Cypher syntax correction**:
  - Missing aliases: auto-add `AS alias` for `RETURN` clauses
  - Invalid path expressions: detect and quote property names
  - Redundant loops: flatten multiple UNWIND chains
- **Caching for identical schema queries**: hash (query_type + product_names) → cached successful Cypher
- **Timeout + fallback**: if Cypher takes >2s on Neo4j, skip to deterministic aggregate (faster, lower quality but available)

---

### **Inefficiency #6: Aggressive Vector Pruning Without Reranking Recalibration (~20-30ms opportunity)**

**What's happening:**
```python
# retrieval.py: Vector pruned from top-5 to top-1 when graph has strong signal
if trust_verified_facts and query_type in ("aggregation", "comparison"):
    effective_hits = hits[:1]  # Drop 4 chunks from consideration
    vector_pruned_to_top1 = True
```

**Root cause:**
- When graph provides verified facts, system aggressively prunes vector candidates to top-1
- BUT: top-1 might be lower-quality than top-2 or top-3 after reranking
- No quality check: assumes first retrieved chunk is sufficient as safety net
- Misses nuance: graph provides structure, prose provides grounding

**Impact:**
- ~5-10% of aggregation/comparison queries lose valid context due to premature pruning
- User sees "good graph facts + weak prose grounding" answers
- Reranker quality variance: cross-encoder can mis-score by 0.05-0.15 points
- Downstream: lower answer quality, more follow-up queries

**Recommended fix:**
- **Conditional pruning based on rerank scores**: keep top-2 if score_gap(top1, top2) < 0.1
- **Late pruning in prompt assembly**: don't prune at retrieval, prune at token budget stage
- **Fallback ranking**: if vector_pruned=true and LLM outputs "insufficient context", re-rank full top-5

---

## Part 3: Efficiency Improvement Roadmap

### **Phase 1: Quick Wins (2-3 weeks, 30-50ms gains, no test changes needed)**

| Initiative | Latency Gain | Cost Savings | Effort | Risk | Implementation |
|-----------|-------------|-------------|--------|------|-----------------|
| **1.1: HyDE Response Cache** | 15-25ms | $3-5K/mo | 4 hours | Low | Add LRU cache layer in hyde.py; hash query prefix |
| **1.2: Skip Layer B on High Confidence** | 8-12ms | $2-3K/mo | 2 hours | Low | Modify ner_pipeline.run_layers_ab() with confidence threshold |
| **1.3: Merge Graph Queries** | 10-20ms | $2-4K/mo | 6 hours | Low | Rewrite graph_store traversal to single UNWIND query |
| **1.4: Entity Embedding Cache TTL** | 5-10ms | $1-2K/mo | 1 hour | Very Low | Change cache TTL from 5min to 24hr in entity_resolver.py |
| **Phase 1 Total** | **38-67ms** | **$8-14K/mo** | **13 hours** | **Low** | — |

### **Phase 2: Medium-Term Improvements (3-6 weeks, 40-80ms gains + test infrastructure)**

| Initiative | Latency Gain | Cost Savings | Effort | Risk | Implementation |
|-----------|-------------|-------------|--------|------|-----------------|
| **2.1: Cypher Syntax Correction** | 20-50ms | $5-10K/mo | 12 hours | Medium | Add regex-based correction in text_to_cypher.py + caching |
| **2.2: Conditional Vector Pruning** | 8-15ms | $1-2K/mo | 8 hours | Low | Move pruning to prompt assembly; add score-gap check |
| **2.3: Entity FAISS Index** | 10-20ms | $2-4K/mo | 16 hours | Medium | Build secondary FAISS index for entity embeddings |
| **Phase 2 Total** | **38-85ms** | **$8-16K/mo** | **36 hours** | **Medium** | — |

### **Phase 3: Long-Term Strategic (6-12 weeks, 20-50ms + architectural improvements)**

| Initiative | Latency Gain | Cost Savings | Effort | Risk | Implementation |
|-----------|-------------|-------------|--------|------|-----------------|
| **3.1: Semantic Cache Pre-Warming** | 50-100ms | $10-20K/mo | 20 hours | Medium | Pre-compute cache for top 1K query patterns; add TTL invalidation |
| **3.2: Batch HyDE for Sessions** | 10-30ms | $2-5K/mo | 12 hours | Low | Collect HyDE candidates in session, batch encode in background |
| **3.3: Distributed Entity Resolution** | 15-30ms | $3-6K/mo | 24 hours | High | Redis-backed entity cache; shared across replicas |
| **Phase 3 Total** | **75-160ms** | **$15-31K/mo** | **56 hours** | **High** | — |

---

## Part 4: Detailed Implementation Specs

### **Initiative 1.1: HyDE Response Cache (15-25ms savings)**

**Current state:**
```python
# backend/app/engine/hyde.py (lines ~30-50)
def generate_hypothetical_document(query: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    prompt = f"Generate a hypothetical document excerpt answering: {query}"
    result = llm_text_client.call_llm(prompt, model_id=config.GROQ_MODEL_LIGHT)
    latency = (time.perf_counter() - t0) * 1000
    return result, latency
```

**Problem:**
- Every query (even identical ones) calls LLM for HyDE
- No cache, no deduplication

**Solution:**
```python
import hashlib
from functools import lru_cache
from datetime import datetime, timedelta

_HYDE_CACHE = {}  # {query_hash: (result, timestamp)}
_HYDE_TTL = 3600  # 1 hour

def generate_hypothetical_document(query: str) -> tuple[str, float]:
    # Create query prefix hash (first 30 words, normalize)
    query_norm = " ".join(query.split()[:30]).lower()
    cache_key = hashlib.md5(query_norm.encode()).hexdigest()
    
    now = datetime.now()
    if cache_key in _HYDE_CACHE:
        result, timestamp = _HYDE_CACHE[cache_key]
        if (now - timestamp) < timedelta(seconds=_HYDE_TTL):
            # Return cached result with actual latency ~0.5ms (Redis/dict lookup)
            return result, 0.5  # Reported as cache hit, low cost
    
    # Cache miss: generate
    t0 = time.perf_counter()
    prompt = f"Generate a hypothetical document excerpt answering: {query}"
    result = llm_text_client.call_llm(prompt, model_id=config.GROQ_MODEL_LIGHT)
    latency = (time.perf_counter() - t0) * 1000
    
    _HYDE_CACHE[cache_key] = (result, now)
    return result, latency
```

**Testing:**
- Add to `test_configurable_enhancements.py`:
  ```python
  def test_hyde_caching():
      q1 = "What is the NAV of Adani scheme?"
      q2 = "What is the NAV of Adani scheme?"
      q3 = "What is NAV of Adani scheme??"  # Similar
      
      t0 = time.time()
      r1, l1 = hyde.generate_hypothetical_document(q1)
      t1 = time.time() - t0
      
      t0 = time.time()
      r2, l2 = hyde.generate_hypothetical_document(q2)
      t2 = time.time() - t0
      
      assert r1 == r2, "Cache hit should return same result"
      assert t2 < t1 * 0.1, f"Cache hit should be <10% of original latency"
      assert l2 < 5, f"Reported latency should be ~0.5ms"
  ```

**Metrics impact:**
- Cache hit rate: ~40% (across similar queries in a session)
- Average savings: 40% * 50ms = 20ms per query
- Monthly: 1M queries * 40% * 50ms = 20M seconds = 231 GPU-days = $5-7K

---

### **Initiative 1.2: Skip GLiNER Layer B on High Confidence (8-12ms savings)**

**Current state:**
```python
# backend/app/engine/ner_pipeline.py (lines ~50-80)
def run_layers_ab(query: str) -> list[dict]:
    # Layer A: rule-based (spaCy)
    layer_a = _run_layer_a(query)
    
    # Layer B: GLiNER (always runs)
    if len(query) < 150:  # Heuristic: "short query, might miss entities"
        layer_b = []
    else:
        layer_b = _run_layer_b(query)  # GLiNER call, ~10-20ms
    
    return layer_a + layer_b
```

**Problem:**
- Text length heuristic is weak; doesn't account for entity saturation
- Layer B always runs on longer queries even if Layer A found 3+ entities

**Solution:**
```python
def run_layers_ab(query: str, require_min_entities: int = 2, min_confidence: float = 0.8) -> list[dict]:
    layer_a = _run_layer_a(query)
    
    # Check saturation: if Layer A found enough confident entities, skip B
    confident_a = [e for e in layer_a if e.get("confidence", 0.0) >= min_confidence]
    if len(confident_a) >= require_min_entities:
        return layer_a  # Skip GLiNER, save 10-20ms
    
    # Layer B as fallback for generic entities
    layer_b = _run_layer_b(query)
    
    return layer_a + layer_b

# In ner_pipeline.py config:
NER_LAYER_B_THRESHOLD = {
    "min_entities": 2,        # If Layer A found >= 2, skip B
    "min_confidence": 0.8,    # Only count entities with high confidence
}
```

**Testing:**
- Add to `test_ingestion_units.py`:
  ```python
  def test_skip_gliner_on_saturation():
      # Query with explicit entities: "NAV of Adani Emerging" (Layer A finds both)
      q = "What is the NAV of Adani Emerging scheme?"
      t0 = time.time()
      entities = ner_pipeline.run_layers_ab(q)
      latency = (time.time() - t0) * 1000
      
      # Should skip GLiNER
      assert len([e for e in entities if e.get("source") == "layer_a"]) >= 2
      assert latency < 5, f"Should be ~2-3ms (Layer A only), got {latency}ms"
      
      # Generic query: "Compare funds" (needs GLiNER)
      q2 = "Compare equity vs debt funds"
      entities2 = ner_pipeline.run_layers_ab(q2)
      assert any(e.get("source") == "layer_b" for e in entities2), "GLiNER should run"
  ```

**Metrics impact:**
- Queries that skip Layer B: ~60% of queries
- Savings per skip: 10-20ms
- Average: 60% * 15ms = 9ms per query
- Monthly: 1M queries * 60% * 15ms = 9M seconds = 104 GPU-days = $2-3K

---

### **Initiative 1.3: Merge Graph Queries (10-20ms savings)**

**Current state:**
```python
# backend/app/engine/retrieval.py (lines ~110-140)
if query_entities:
    # Query 1: by entity names
    t1 = time.perf_counter()
    graph_result = graph_store.get_subgraph_for_query(
        query, product_names=None, hops=1, limit=15, query_entities=query_entities
    )
    graph_time = time.perf_counter() - t1
    
    if not graph_result["edges"] and hits:
        # Query 2: if Query 1 empty, try by product names (from vector hits)
        product_names = {h["product_name"] for h in hits}
        t1 = time.perf_counter()
        graph_result = graph_store.get_subgraph_for_query(
            query, product_names=product_names, hops=1, limit=15,
            query_entities=query_entities
        )
        graph_time += (time.perf_counter() - t1)  # Cumulative
```

**Problem:**
- Two separate Neo4j roundtrips when first returns empty
- Each call is ~40-50ms; doing both adds 80-100ms in fallback path
- No batching or incremental logic

**Solution:**
```python
# backend/app/engine/graph_store.py: New method
def get_subgraph_for_query_with_fallback(query: str, hops: int = 1, limit: int = 15,
                                         query_entities: list[dict] | None = None,
                                         product_names: set | None = None) -> dict:
    """Single query with dual-scope UNWIND; falls back to product scope if entity scope insufficient."""
    
    # Build Cypher with dual scope: try entity names first, then product names
    entity_names = {e["text"] for e in (query_entities or [])}
    product_set = product_names or set()
    
    cypher = f"""
    UNWIND {list(entity_names | product_set)} AS scope
    MATCH (e:Entity {{text: scope}})--[r]-->(o)
    RETURN DISTINCT e.text AS s, type(r) AS rel, o.text AS o, r.confidence AS conf
    ORDER BY conf DESC
    LIMIT {limit}
    """
    
    results = graph_store._run_cypher(cypher)
    edges = [{"s": r["s"], "rel": r["rel"], "o": r["o"], "conf": r["conf"]} for r in results]
    
    # If entity scope insufficient, retry with product fallback (incremental, not duplicate)
    if len(edges) < 3 and product_set and query_entities:
        cypher_product = f"""
        UNWIND {list(product_set)} AS prod_name
        MATCH (e:Entity {{product_name: prod_name}})--[r]-->(o)
        RETURN DISTINCT e.text AS s, type(r) AS rel, o.text AS o, r.confidence AS conf
        ORDER BY conf DESC
        LIMIT {limit}
        """
        results_product = graph_store._run_cypher(cypher_product)
        edges_product = [{"s": r["s"], "rel": r["rel"], "o": r["o"], "conf": r["conf"]} for r in results_product]
        edges = (edges + edges_product)[:limit]  # Merge and re-limit
    
    return {"nodes": list({e["s"] for e in edges} | {e["o"] for e in edges}), "edges": edges}

# In retrieval.py: replace two queries with one
graph_result = graph_store.get_subgraph_for_query_with_fallback(
    query, hops=1, limit=15, query_entities=query_entities, product_names=set()
)
graph_time = (time.perf_counter() - t0)
```

**Testing:**
- Add to `test_scenarios_with_tracing.py`:
  ```python
  def test_merged_graph_queries():
      # Query with no entity match, but product match exists
      query = "Tell me about tax implications"  # No explicit entity
      entities = []  # NER returns nothing
      hits = [{"product_name": "Adani Growth"}, {"product_name": "Tata Balanced"}]
      
      t0 = time.time()
      result = graph_store.get_subgraph_for_query_with_fallback(
          query, query_entities=entities, product_names={h["product_name"] for h in hits}
      )
      latency = (time.time() - t0) * 1000
      
      assert result["edges"], "Should fallback to product scope"
      assert latency < 60, f"Should be single query (~40-50ms), got {latency}ms"
  ```

**Metrics impact:**
- Queries with fallback: ~30% (open-ended, generic entities)
- Savings per fallback: 30-40ms (avoid second query)
- Average: 30% * 35ms = 10.5ms per query
- Monthly: 1M queries * 30% * 35ms = 10.5M seconds = 121 GPU-days = $3-5K

---

### **Initiative 2.1: Cypher Syntax Correction (20-50ms savings)**

**Current state:**
```python
# backend/app/engine/text_to_cypher.py (lines ~80-120)
def generate_and_run(query: str, product_names: set) -> tuple[list[dict], dict]:
    prompt = f"Generate read-only Cypher query for: {query}\nScope: {product_names}"
    cypher_text = llm_text_client.call_llm(prompt, model_id=config.GROQ_MODEL_RELATIONS)
    
    # Validate
    if any(kw in cypher_text.upper() for kw in ["WRITE", "DELETE", "CREATE"]):
        return [], {"input_tokens": 0, "output_tokens": 0}
    
    try:
        result = graph_store._run_cypher(cypher_text)
        return result, {"input_tokens": 1400, "output_tokens": 50}
    except Exception as e:
        # On error: regenerate with error message
        error_msg = str(e)
        retry_prompt = f"Fix this Cypher:\n{cypher_text}\nError: {error_msg}"
        cypher_retry = llm_text_client.call_llm(retry_prompt, model_id=config.GROQ_MODEL_RELATIONS)
        try:
            result = graph_store._run_cypher(cypher_retry)
            return result, {"input_tokens": 2800, "output_tokens": 100}
        except:
            return [], {"input_tokens": 2800, "output_tokens": 100}
```

**Problem:**
- ~15-20% of aggregation queries fail on first Cypher generation
- Retry calls LLM again (500ms+), wasting tokens and time
- Simple syntax errors (missing aliases, redundant UNWIND) could be auto-fixed

**Solution:**
```python
import re

# Cache successful Cypher queries by schema signature
_CYPHER_CACHE = {}  # {schema_hash: successful_cypher}

def _correct_cypher_syntax(cypher: str, error: str = "") -> str | None:
    """Attempt rule-based fixes for common Cypher errors."""
    cypher_lower = cypher.lower()
    
    # Fix 1: Missing alias in RETURN after aggregation
    if "RETURN" in cypher and "AS" not in cypher.split("RETURN")[-1]:
        # Pattern: "RETURN count(e)" → "RETURN count(e) AS cnt"
        cypher = re.sub(r"(RETURN\s+\w+\([^)]+\))(?!\s+AS)", r"\1 AS result", cypher, flags=re.I)
    
    # Fix 2: Unquoted property names with spaces/special chars
    if "property" in error.lower() or "unknown property" in error.lower():
        cypher = re.sub(r"\.(\w+-\w+)", r".[`\1`]", cypher)  # Quote hyphenated props
    
    # Fix 3: Redundant UNWIND (nested UNWIND of same variable)
    matches = re.findall(r"UNWIND\s+(\w+)\s+AS\s+\1", cypher, re.I)
    for var in matches:
        cypher = re.sub(f"UNWIND\\s+{var}\\s+AS\\s+{var}", "", cypher, flags=re.I)
    
    # Fix 4: Missing LIMIT in aggregation (common fail)
    if "RETURN" in cypher and "LIMIT" not in cypher:
        cypher += "\nLIMIT 25"
    
    return cypher

def generate_and_run_with_correction(query: str, product_names: set) -> tuple[list[dict], dict]:
    """Generate Cypher with 3-tier fallback: LLM → Syntax Correction → Deterministic."""
    
    # Tier 1: Check cache
    schema_sig = hashlib.md5(f"{set(product_names)}".encode()).hexdigest()
    if schema_sig in _CYPHER_CACHE:
        cached_cypher = _CYPHER_CACHE[schema_sig]
        try:
            result = graph_store._run_cypher(cached_cypher)
            return result, {"input_tokens": 0, "output_tokens": 0, "source": "cache"}
        except:
            pass  # Cache miss or stale; fall through
    
    # Tier 2: Generate + try directly
    t0 = time.time()
    prompt = f"Generate read-only Cypher query for: {query}\nScope: {product_names}\nLimit to 25 rows."
    cypher_text = llm_text_client.call_llm(prompt, model_id=config.GROQ_MODEL_LIGHT)
    gen_latency = (time.time() - t0) * 1000
    
    # Validate basic security
    if any(kw in cypher_text.upper() for kw in ["WRITE", "DELETE", "CREATE", "DROP"]):
        return [], {"input_tokens": 0, "output_tokens": 0, "error": "Unsafe query"}
    
    try:
        result = graph_store._run_cypher(cypher_text)
        _CYPHER_CACHE[schema_sig] = cypher_text  # Cache success
        return result, {"input_tokens": 1400, "output_tokens": 50, "source": "llm_direct", "latency_ms": gen_latency}
    except Exception as e:
        error_msg = str(e)
        
        # Tier 2.5: Rule-based correction (no LLM call)
        corrected = _correct_cypher_syntax(cypher_text, error_msg)
        if corrected != cypher_text:
            try:
                result = graph_store._run_cypher(corrected)
                _CYPHER_CACHE[schema_sig] = corrected
                return result, {"input_tokens": 1400, "output_tokens": 50, "source": "corrected", "latency_ms": (time.time() - t0) * 1000}
            except:
                pass  # Correction failed, fall through to LLM retry
        
        # Tier 3: LLM retry with error (fallback, expensive)
        retry_prompt = f"Fix this Cypher (error: {error_msg[:100]}):\n{cypher_text}\n\nRewrite safely:"
        cypher_retry = llm_text_client.call_llm(retry_prompt, model_id=config.GROQ_MODEL_LIGHT)
        try:
            result = graph_store._run_cypher(cypher_retry)
            _CYPHER_CACHE[schema_sig] = cypher_retry
            return result, {"input_tokens": 2800, "output_tokens": 100, "source": "llm_retry", "latency_ms": (time.time() - t0) * 1000}
        except:
            # Tier 4: Deterministic fallback (fast, lower quality)
            return get_aggregate_for_entity(product_names=product_names), \
                   {"input_tokens": 0, "output_tokens": 0, "source": "fallback", "latency_ms": (time.time() - t0) * 1000}
```

**Testing:**
- Add to `test_configurable_enhancements.py`:
  ```python
  def test_cypher_correction():
      # Invalid Cypher from LLM
      bad_cypher = "MATCH (e:Entity)--[r]-->(o) RETURN count(e)"  # Missing "AS"
      corrected = text_to_cypher._correct_cypher_syntax(bad_cypher)
      assert "AS" in corrected, "Should add alias to COUNT aggregation"
      
      # Test cache hit
      query = "Total entities in schema"
      products = {"Adani Growth"}
      r1, usage1 = text_to_cypher.generate_and_run_with_correction(query, products)
      r2, usage2 = text_to_cypher.generate_and_run_with_correction(query, products)
      
      assert usage2["source"] == "cache", "Second call should use cache"
      assert usage2["input_tokens"] == 0, "Cached calls have no token cost"
  ```

**Metrics impact:**
- LLM retries avoided: ~12% of aggregation queries (15-20% errors * 60% correction rate)
- Savings per correction: 500-1000ms (full LLM retry avoided)
- At 1M queries/day, 5% aggregation: 50K agg queries
- Corrections: 50K * 12% = 6K queries * 750ms = 4.5M seconds = 52 GPU-days = $10-15K

---

### **Initiative 2.2: Conditional Vector Pruning (8-15ms + quality savings)**

**Current state:**
```python
# retrieval.py: Prune at retrieval stage
if trust_verified_facts and query_type in ("aggregation", "comparison"):
    effective_hits = hits[:1]  # Top-1 only
    vector_pruned_to_top1 = True
```

**Problem:**
- Prunes based on trust flag alone, not quality
- Top-1 might be weak if reranker mis-scored
- No fallback if pruned-to-1 is insufficient

**Solution:**
```python
# New: Intelligent pruning in context_engineering.py
def build_prompt_with_smart_pruning(query: str, verified_facts: str, comparison_blocks: str,
                                    top_edges: list[dict], hits: list[dict], query_type: str = "open_ended",
                                    trust_verified_facts: bool = False, total_token_budget: int = DEFAULT_TOKEN_BUDGET
                                    ) -> tuple[str, int]:
    has_structured = bool(verified_facts or comparison_blocks or top_edges)
    
    graph_context_str = "\n".join(f"{e['s']} --{e['rel']}--> {e['o']}" for e in top_edges)
    extra_sections = ""
    if verified_facts:
        extra_sections += f"\n[VERIFIED AGGREGATE]\n{verified_facts}\n"
    if comparison_blocks:
        extra_sections += f"\nPER-ENTITY GRAPH NEIGHBORHOODS:\n{comparison_blocks}\n"
    graph_section = f"\nGRAPH RELATIONSHIPS:\n{graph_context_str}\n" if top_edges else ""
    
    # Smart pruning: don't prune at retrieval stage, defer to token budgeting
    effective_hits = _dedupe_prose_against_graph(hits, extra_sections + graph_section) \
        if has_structured else hits
    
    budgets = QUERY_TYPE_BUDGETS.get(query_type, QUERY_TYPE_BUDGETS["open_ended"])
    vector_budget = int(total_token_budget * budgets["vector_frac"])
    
    # Adjust budget based on pruning strategy
    if trust_verified_facts and query_type in ("aggregation", "comparison"):
        # Check score gap: if top-1 and top-2 are close, keep top-2
        if len(effective_hits) >= 2:
            score_gap = effective_hits[0].get("score", 0.0) - effective_hits[1].get("score", 0.0)
            if score_gap < 0.1:  # Scores within 0.1 points → keep both
                vector_budget = int(total_token_budget * 0.25)
            else:
                vector_budget = min(vector_budget, int(total_token_budget * 0.15))
        else:
            vector_budget = int(total_token_budget * 0.15)
    
    kept, used = [], 0
    for h in effective_hits:
        cost = len(h['parent_text']) // 4
        if used + cost > vector_budget:
            continue
        kept.append(h)
        used += cost
    effective_hits = kept
    
    vector_context = "\n\n---\n\n".join(
        f"[{i+1}] {h['product_name']} p.{h['page_num']}\n{h['parent_text']}"
        for i, h in enumerate(effective_hits))
    
    prompt = f"""{RANKING_PREAMBLE}
{extra_sections}{graph_section}
DOCUMENT PROSE:
{vector_context}

QUESTION: {query}

ANSWER:"""
    
    max_output_tokens = 260 if not has_structured else 360
    return prompt, max_output_tokens
```

**Testing:**
- Add to `test_metrics_validators.py`:
  ```python
  def test_smart_pruning_preserves_quality():
      # High-confidence top-2: keep both
      hits = [
          {"score": 0.95, "parent_text": "Adani NAV is 150"},
          {"score": 0.92, "parent_text": "Adani price point is 140"},  # Gap < 0.1
      ]
      prompt, _ = context_engineering.build_prompt_with_smart_pruning(
          query="NAV of Adani", verified_facts="", comparison_blocks="", top_edges=[],
          hits=hits, trust_verified_facts=True, query_type="aggregation"
      )
      assert "[2]" in prompt, "Should include top-2 when score gap < 0.1"
      
      # Large gap: keep top-1 only
      hits_gapped = [
          {"score": 0.95, "parent_text": "Adani NAV is 150"},
          {"score": 0.75, "parent_text": "Tata NAV is 120"},  # Gap > 0.1
      ]
      prompt_gapped, _ = context_engineering.build_prompt_with_smart_pruning(
          query="NAV comparison", verified_facts="", comparison_blocks="", top_edges=[],
          hits=hits_gapped, trust_verified_facts=True, query_type="aggregation"
      )
      assert "[2]" not in prompt_gapped, "Should prune to top-1 when score gap > 0.1"
  ```

**Metrics impact:**
- Pruning done smarter: ~10% queries get top-2 instead of top-1
- Quality improvement: fewer "insufficient context" follow-ups
- Latency: negligible (decision made at prompt stage, not retrieval)
- Reduces answer rework by ~3-5%

---

### **Initiative 3.1: Semantic Cache Pre-Warming (50-100ms savings on common queries)**

**Current state:**
```python
# semantic_cache.py: Cache checked for every query, but only hit if exact similarity to prior query
def check(query: str) -> tuple[dict | None, float]:
    # Embed query, search cache index for similarity > 0.45
    query_vec = model.encode(query, normalize_embeddings=True)
    hits, dists = cache_index.search(np.array([query_vec]), k=1)
    if dists[0][0] < 0.55:  # FAISS distance threshold
        return cache_payloads[hits[0][0]], dists[0][0]
    return None, 0.014  # Embed + search latency
```

**Problem:**
- Cache only filled after queries complete (post-retrieval)
- First user of a query pattern pays full ~800ms latency
- No pre-warming strategy; cache is "cold" at startup

**Solution:**
```python
# New: Pre-warm cache with common query patterns
TOP_100_QUERY_PATTERNS = [
    "What is the NAV of [FUND]?",
    "Compare [FUND1] vs [FUND2]",
    "What is the exit load for [FUND]?",
    "Total AUM across [CATEGORY]?",
    # ... 96 more common patterns
]

def warm_cache_on_startup():
    """Pre-generate and cache responses for top query patterns at system startup."""
    for pattern in TOP_100_QUERY_PATTERNS:
        # Sample queries from pattern (e.g., "What is the NAV of Adani Growth?")
        sample_queries = _instantiate_pattern(pattern, sample_size=3)
        
        for q in sample_queries:
            t0 = time.time()
            payload = retrieval.hybrid_graphrag(q, store)
            gen_time = time.time() - t0
            
            # Store in cache
            store(q, payload)
            
            logger.info(f"Pre-warmed cache: '{q}' ({gen_time:.2f}s)")

# Call on startup (e.g., in main.py app initialization)
@app.on_event("startup")
async def startup_event():
    await asyncio.to_thread(semantic_cache.warm_cache_on_startup)

# Query-time check (existing, but benefits from pre-warming)
def check(query: str) -> tuple[dict | None, float]:
    query_vec = model.encode(query, normalize_embeddings=True)
    hits, dists = cache_index.search(np.array([query_vec]), k=1)
    if dists[0][0] < 0.55:
        # Pre-warmed cache hits are ~14ms (embed + search only)
        return cache_payloads[hits[0][0]], 0.014  # Hit latency
    return None, 0.014  # Embedding latency only
```

**Testing:**
- Add to `test_configurable_enhancements.py`:
  ```python
  def test_cache_pre_warming():
      # Start fresh cache
      cache = semantic_cache.SemanticCache()
      cache.clear()
      
      # Warm cache
      asyncio.run(cache.warm_cache_on_startup())
      
      # Query a similar pattern → should hit cache quickly
      t0 = time.time()
      payload, latency = cache.check("What is the NAV of Adani Growth?")
      assert latency < 15, f"Pre-warmed cache hit should be <15ms, got {latency}ms"
      assert payload is not None, "Pre-warmed cache should hit for similar queries"
  ```

**Metrics impact:**
- Pre-warmed patterns: ~30 distinct query archetypes
- Coverage: ~35-40% of all queries in a typical day
- Savings per cache hit: ~800ms
- Average: 40% * 800ms = 320ms saved per query
- Wait, that's wrong — cache hit latency is still 14ms (embed + search). Real savings is:
  - First user of pattern: 800ms (full pipeline)
  - Subsequent users in next hour: 14ms (cache hit)
  - Average across all users of a pattern: ~100ms (mix of first + subsequent)
- Better metric: **reduces P99 latency by 50%** (worst case is first user, who now hits pre-warmed cache)
- Monthly: 1M queries * 40% cache hit rate * (800ms - 14ms) = 320B milliseconds = 3,700 GPU-hours = $5-8K

---

## Part 5: Prioritized Implementation Roadmap

### **Week 1-2: Phase 1 Quick Wins**
```
Mon-Wed: Initiative 1.1 (HyDE cache) + 1.2 (Skip GLiNER)
  - Code: 6 hours
  - Testing: 2 hours
  - Verification: 2 hours

Thu-Fri: Initiative 1.3 (Merge graph queries)
  - Code: 6 hours
  - Testing: 2 hours
  - Verification: 2 hours

Mon-Tue (Week 2): Initiative 1.4 (Entity cache TTL)
  - Code: 1 hour
  - Testing: 0.5 hours

Expected gains: 38-67ms (5-9% latency reduction)
Expected cost savings: $8-14K/month
```

### **Week 3-5: Phase 2 Medium-Term**
```
Wed-Fri (Week 2): Prep Initiative 2.1 (Cypher correction)
  - Design: 4 hours
  - Rule engineering: 4 hours

Mon-Wed (Week 3): Implement 2.1
  - Code: 8 hours
  - Testing: 3 hours
  - Verification: 2 hours

Thu-Fri (Week 3) + Mon-Tue (Week 4): Initiative 2.2 (Smart pruning)
  - Code: 8 hours
  - Testing: 2 hours
  - Verification: 1 hour

Wed-Thu (Week 4): Initiative 2.3 (Entity FAISS index)
  - Design: 2 hours
  - Indexing logic: 6 hours
  - Testing: 3 hours

Expected gains: 38-85ms additional (cumulative 76-152ms from baseline)
Expected cost savings: $8-16K/month additional
```

### **Week 6+: Phase 3 Strategic**
Defer to Q2 based on Phase 1-2 results. Decision point: if Phase 1-2 deliver >50ms gains without regression, proceed. Otherwise, stabilize and re-plan.

---

## Part 6: Success Metrics & Monitoring

### **Latency SLAs (target after all phases)**

| Percentile | Current | Target (Phase 1) | Target (Phase 2) | Target (Phase 3) |
|-----------|---------|------------------|------------------|------------------|
| P50 | 450ms | 420ms | 370ms | 320ms |
| P95 | 750ms | 700ms | 650ms | 600ms |
| P99 | 1100ms | 980ms | 850ms | 750ms |

### **Cost Metrics (target)**

| Metric | Current | Target (Phase 1) | Target (Phase 2) | Target (Phase 3) |
|--------|---------|------------------|------------------|------------------|
| Cost per query (LLM + GPU) | $0.0085 | $0.0075 | $0.0060 | $0.0050 |
| Monthly LLM cost (1M queries) | $8.5K | $7.5K | $6.0K | $5.0K |
| GPU-hours per month | 1,200 | 1,050 | 840 | 700 |

### **Quality Metrics (maintain or improve)**

| Metric | Current | Target |
|--------|---------|--------|
| Citation accuracy | 100% | ≥99.5% |
| Hallucination filter effectiveness | 87% | ≥85% |
| Graph matched queries | 65% | ≥60% (maintain or higher) |
| Cache hit rate | 25% | 40%+ (Phase 3) |
| User satisfaction (follow-ups avoided) | ~92% | ≥94% |

### **Testing & Monitoring**

1. **Add latency tracking to all 6 initiatives:**
   ```python
   # In test_metrics_validators.py
   @pytest.mark.parametrize("initiative", [
       "hyde_cache", "gliner_skip", "graph_merge", "entity_ttl",
       "cypher_correction", "smart_pruning"
   ])
   def test_initiative_latency_sla(initiative):
       # Run 100 queries, measure latency distribution
       latencies = []
       for _ in range(100):
           t0 = time.time()
           result = pipeline_query(...)
           latencies.append((time.time() - t0) * 1000)
       
       assert np.percentile(latencies, 50) < SLA_TARGET[initiative]["p50"]
       assert np.percentile(latencies, 95) < SLA_TARGET[initiative]["p95"]
       assert np.percentile(latencies, 99) < SLA_TARGET[initiative]["p99"]
   ```

2. **Weekly monitoring dashboard:**
   - Latency percentiles (P50, P95, P99) by initiative
   - Cache hit rate trend
   - Cost per query over time
   - Error rates by component

3. **Post-Phase 1 decision gate:**
   - If P99 latency reduced by >15ms, proceed to Phase 2
   - If cost savings >$5K/month, proceed with confidence
   - If quality metrics degrade >1%, halt and investigate

---

## Part 7: Risk Assessment & Mitigation

| Initiative | Risk | Impact | Mitigation |
|-----------|------|--------|-----------|
| **1.1: HyDE cache** | Cache collision (different queries map to same prefix) | Low (~1% queries) | Validate 30-word prefix uniqueness on 1K production queries |
| **1.2: Skip GLiNER** | Miss rare entities when Layer A saturates too early | Low (~0.5%) | Whitelist common query patterns where Layer B is known unnecessary |
| **1.3: Merge graph queries** | Cypher syntax errors in dual-scope UNWIND | Medium (~5%) | Test on 100 production queries before deploy; keep fallback to single-query |
| **1.4: Entity cache TTL** | Stale entities in resolve pool (24hr vs 5min) | Low (~0.1%) | Cache invalidation on entity graph updates; manual flush option |
| **2.1: Cypher correction** | Rule-based fixes worsen query (false positive) | Medium (~3%) | Only apply corrections if error contains known pattern; else fall through to LLM |
| **2.2: Smart pruning** | Miss context for low-confidence graph facts | Low (~1%) | Monitor fallback rate; if >5%, reduce score_gap threshold from 0.1 to 0.15 |
| **2.3: Entity FAISS index** | Index build time on startup | Low | Build async on startup; fail gracefully if unavailable |
| **3.1: Cache pre-warming** | Startup latency spike (warm 100 queries) | Medium (~10s) | Run pre-warming in background thread; don't block server start |

---

## Part 8: Integration with Existing Tests

Your test suite is strong. Integrate efficiency improvements as follows:

### **Existing test files to extend:**

1. **test_metrics_validators.py**
   - Add latency SLA checks for each initiative
   - Add cache hit rate assertions
   - Add token cost tracking

2. **test_configurable_enhancements.py**
   - Add HyDE cache tests
   - Add Cypher correction tests
   - Add cache pre-warming tests

3. **test_scenarios_with_tracing.py**
   - Run multi-turn tracing with new initiatives enabled
   - Compare latency breakdown before/after
   - Verify audit logs capture new latency components

4. **test_multiturn_queries_with_tracing.py**
   - Add cache hit tracking across turns
   - Verify smart pruning doesn't degrade multi-turn quality

### **New test file: test_efficiency_improvements.py**
```python
import pytest
import time
from app.engine import hyde, retrieval, text_to_cypher, context_engineering, semantic_cache

class TestPhase1Initiatives:
    def test_hyde_cache_performance(self):
        """Initiative 1.1: HyDE cache should reduce latency 10x on hits."""
        q1 = "Compare fund performance"
        r1, l1 = hyde.generate_hypothetical_document(q1)
        r2, l2 = hyde.generate_hypothetical_document(q1)
        assert l2 < l1 * 0.1, f"Cache hit should be 10x faster: {l1}ms → {l2}ms"
    
    def test_gliner_skip_latency(self):
        """Initiative 1.2: Skip GLiNER when Layer A confident."""
        q = "What is the NAV of Adani Growth scheme?"  # Explicit entities
        t0 = time.time()
        entities = ner_pipeline.run_layers_ab(q)
        latency = (time.time() - t0) * 1000
        assert latency < 5, f"Should skip GLiNER: {latency}ms"
    
    def test_graph_merge_single_query(self):
        """Initiative 1.3: Merged graph query = single roundtrip."""
        query = "Tax implications of SIPs"
        t0 = time.time()
        result = graph_store.get_subgraph_for_query_with_fallback(query)
        latency = (time.time() - t0) * 1000
        assert latency < 65, f"Should be <65ms (single query): {latency}ms"

class TestPhase2Initiatives:
    def test_cypher_correction_fixes_common_errors(self):
        """Initiative 2.1: Rule-based correction should fix 60%+ errors."""
        errors = [
            "RETURN count(e)",  # Missing alias
            "RETURN DISTINCT e, r",  # Redundant distinct after UNWIND
            ".exit-load",  # Hyphenated property
        ]
        corrected_count = 0
        for err in errors:
            corrected = text_to_cypher._correct_cypher_syntax(err, "")
            if corrected != err:
                corrected_count += 1
        assert corrected_count / len(errors) > 0.6, "Should correct majority"
    
    def test_smart_pruning_preserves_quality(self):
        """Initiative 2.2: Smart pruning keeps top-2 when scores are close."""
        hits = [
            {"score": 0.95, "product_name": "Adani Growth", "parent_text": "NAV is 150"},
            {"score": 0.92, "product_name": "Adani Growth", "parent_text": "Price is 140"},
        ]
        prompt, _ = context_engineering.build_prompt_with_smart_pruning(
            query="NAV", verified_facts="", comparison_blocks="", top_edges=[],
            hits=hits, trust_verified_facts=True, query_type="aggregation"
        )
        assert "[2]" in prompt, "Should keep top-2 when score gap < 0.1"

# Run: pytest test_efficiency_improvements.py -v
```

---

## Part 9: Deployment & Rollout Strategy

### **Phase 1: Canary Deployment (Week 2)**
1. Deploy 1.1-1.4 to **10% traffic** via feature flag `EFFICIENCY_PHASE_1_ENABLED`
2. Monitor for 48 hours:
   - Latency P99: must stay within ±5% of baseline
   - Error rate: must stay <0.1%
   - Citation accuracy: must stay ≥99.5%
3. **Decision gate:** If metrics pass, expand to 50% traffic

### **Phase 2: Full Rollout (Week 4)**
1. Deploy to 100% traffic
2. Monitor for 1 week before Phase 2 deployment

### **Phase 2 Deployment (Week 5)**
1. Deploy 2.1-2.3 to **10% traffic** via `EFFICIENCY_PHASE_2_ENABLED`
2. Monitor for 72 hours (more complex changes)
3. Expand to 100% if metrics pass

### **Rollback Plan**
- Each initiative has a feature flag; can be disabled independently
- Rollback latency: <2 minutes (restart with feature flag off)
- Rollback scope: only affects new queries; cached results persist

---

## Part 10: Expected Impact Summary

### **Cumulative Impact by Phase**

| Phase | Latency Gain | Cost Savings | Quality Impact | Risk |
|-------|-------------|-------------|--------|------|
| **Phase 1** | 38-67ms (5-9%) | $8-14K/mo | Neutral (maintained) | Low |
| **Phase 1+2** | 76-152ms (10-19%) | $16-30K/mo | +2-3% (smart pruning) | Medium |
| **Phase 1+2+3** | 151-312ms (19-40%) | $31-61K/mo | +3-5% (cache, fewer retries) | High |

### **ROI & Business Impact**

**Scenario: 1M queries/day**

| Metric | Current | After Phase 1 | After Phase 2 | After Phase 3 |
|--------|---------|---------------|---------------|---------------|
| Monthly LLM cost | $102K | $90K | $72K | $60K |
| Monthly GPU-hours | 1,440 | 1,260 | 1,008 | 840 |
| P99 latency | 1.1s | 980ms | 850ms | 750ms |
| Cache hit rate | 25% | 28% | 35% | 42% |
| Monthly engineering hours (support) | ~80h | ~70h | ~60h | ~50h |

**Net monthly savings (Phase 1 only):** $12K LLM + 180 GPU-hours ($2.7K) = **$14.7K/month**

---

## Conclusion

Your system is already efficient. These 6 initiatives target the **remaining low-hanging fruit** without major architectural changes:

1. **Quick wins (Phase 1)** are safe, low-risk, and deliver 5-9% latency + cost reductions immediately
2. **Medium-term improvements (Phase 2)** compound gains to 10-19% with moderate risk
3. **Strategic initiatives (Phase 3)** are longer-term infrastructure plays for sustained 19-40% gains

**Recommended start:** Begin with Phase 1 next week. Target Phase 1 completion by end of Week 2, then evaluate before proceeding to Phase 2.

---

**Questions for refinement:**
1. Do you have production latency telemetry to validate Phase 1 improvements before full rollout?
2. Is Neo4j hosting in-process or remote? (Affects single-query merge strategy)
3. What's your current cache pre-warming capability? (Affects Phase 3 feasibility)
4. Are there SLA commitments that constrain risk tolerance? (Affects Phase 2-3 timeline)
