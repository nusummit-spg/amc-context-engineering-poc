# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Latency Reduction Implementation Plan
### Target: Sub-5s Total Response · 1.5s Time-To-First-Token

> **Based on**: `latency_info.md` + `query_execution_audit.jsonl` + codebase audit  
> **Constraint**: No backend server — all ML runs in-process in Streamlit  

---

## Latency Reality Map (Current State)

```
QUERY ARRIVES
     │
     ▼  (0ms)
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: NER Layer A (Regex + spaCy)           ← 10–50 ms       │
│ Step 2: NER Layer B (GLiNER CPU, unquantized) ← 9,000–157,000ms│ ← 🔴 KILL THIS
│ Step 3: Query Classifier (Haiku LLM call)     ← 300–800ms      │
│ Step 4: Graph Traversal (Neo4j full scan)     ← 2,300–9,300ms  │ ← 🟠 IMPROVE
│ Step 5: FAISS Vector Search                   ← 30–300ms       │ ← ✅ FAST
│ Step 6: Text-to-Cypher (hidden LLM call)      ← 400–2,000ms    │ ← 🟠 CACHE
│ Step 7: LLM Generation (blocking call)        ← 3,400–8,200ms  │ ← 🟡 STREAM
│ Step 8: SSL Retry on Network Failure          ← up to 8,200ms  │ ← 🟠 CAP
└─────────────────────────────────────────────────────────────────┘
     │
ANSWER RENDERED (22s–45s+ currently)
```

**Key insight from the audit logs**: Steps 1–6 all happen BEFORE the LLM call, so the user sees a blank spinner for the entire retrieval phase. Streaming (Step 7) helps perceived latency only if Steps 1–6 are fast. **Both must be fixed together.**

---

## What the `latency_info.md` Document Got Right

| Item | Assessment |
|---|---|
| GLiNER CPU as #1 bottleneck (65–85% of latency) | ✅ Confirmed by logs |
| ONNX INT8 quantization as primary fix | ✅ Correct approach |
| Neo4j indexing proposal | ✅ Valid, specific Cypher given |
| LLM streaming (SSE) for TTFT improvement | ✅ Critical |
| Async parallel execution (asyncio.gather) | ✅ Correct direction |
| FAISS mmap already fast (<300ms) | ✅ Confirmed |

---

## 🆕 What the Document Is Missing (8 Critical Gaps)

### Missing Gap 1 — Quantized Model Caching Strategy
The document says "export GLiNER to ONNX" but doesn't address **where the quantized model is stored** and how warm/cold starts differ. On cold start (first Streamlit run), ONNX loading still takes ~3–5s. Without explicit `@st.cache_resource` wrapping, Streamlit will re-load the model on every page refresh/session.

**Gap**: Add `@st.cache_resource` for the ONNX GLiNER model so it's loaded once across all Streamlit sessions.

### Missing Gap 2 — `st.write_stream` Integration (Streamlit-Native Streaming)
The document recommends "SSE streaming" but doesn't account for the fact that this is a **Streamlit app**. Streamlit has a native `st.write_stream()` API (Streamlit ≥ 1.31) that accepts a Python generator. The correct integration is **not SSE endpoints** — it's passing Claude's streaming iterator directly to `st.write_stream()` in `chat_view.py`.

**Gap**: The document's streaming proposal assumes a web server context. The actual fix is a `call_llm_streaming()` generator function in `llm_text_client.py` that yields text deltas, consumed by `st.write_stream()`.

### Missing Gap 3 — HTTP/2 Keep-Alive Pool for Anthropic Client
The document mentions "persistent HTTP/2 connection pool" but the `anthropic.Anthropic` Python SDK internally uses `httpx`. You can pass a custom `httpx.Client` with `http2=True` and `keepalive_expiry=30` to the Anthropic constructor directly — no separate pool setup needed.

**Gap**: The fix is one line in `llm_text_client.py`, not a separate pool infrastructure.

### Missing Gap 4 — Query Classifier Can Skip GLiNER Entirely
The document doesn't mention that if the **query classifier** (fast regex in `query_classifier.py`) already identifies a query as `direct_lookup`, then GLiNER is unlikely to find entities that Layer A missed. Direct lookup queries (`"what is the exit load of..."`) are fully covered by Layer A regex + spaCy EntityRuler.

**Gap**: Add `skip_gliner` flag when `query_type == "direct_lookup"` and `len(layer_a_entities) >= 1`.

### Missing Gap 5 — Exponential Retry Delay is Unbounded
`llm_text_client.py` has: `wait = CLAUDE_RETRY_DELAY * (2 ** attempt)` → for attempt=2 that's `5 * 4 = 20s`. With 3 retries, worst-case retry adds **35s** to latency before giving up. The document notes "8.2s SSL failures" but doesn't fix the unbounded retry.

**Gap**: Cap the retry delay at 10s and reduce `CLAUDE_MAX_RETRIES` from 3 to 2 for query serving (keep 3 for indexing/extraction).

### Missing Gap 6 — FAISS Index Memory-Mapped Loading
The document mentions "in-memory MMap FAISS index" as a target for 0.02–0.05s vector search. But the current code uses `faiss.read_index()` which loads fully into RAM. For 50 docs (~200–370MB), switching to `faiss.read_index(..., io_flags=faiss.IO_FLAG_MMAP)` allows the OS page cache to handle the index without a full RAM copy, reducing startup time and memory pressure.

**Gap**: `faiss.read_index()` → `faiss.read_index(path, faiss.IO_FLAG_MMAP)` in `faiss_store.py` and `taxonomy_retrieval.py`.

### Missing Gap 7 — LRU Cache Invalidation Policy
The document proposes `lru_cache(maxsize=4096)` for NER results. But the current `_query_ner_cache` in `ner_pipeline.py` is an **unbounded dict** — it never evicts entries. At 50 documents with many diverse queries, this cache can grow to hundreds of MB. The fix should use `functools.lru_cache` or a size-limited dict.

**Gap**: The `_query_ner_cache` dict needs a max-size policy (e.g., evict when `len > 2000`).

### Missing Gap 8 — No Observability on Cache Hit Rate
The document proposes all these caches but doesn't include any instrumentation to verify they're working. Without tracking cache hits vs. misses, you can't know if the LRU cache is actually saving time. The audit log already exists (`query_execution_audit.jsonl`) — extend it with `ner_cache_hit: bool` and `embed_cache_hit_count: int`.

**Gap**: Add cache telemetry fields to `log_query_audit()` in `retrieval.py`.

---

## Implementation Plan — 6 Optimization Tracks

---

### Track 1: GLiNER ONNX Quantization (Highest Impact: -65% Total Latency)

**Mechanism**: Export `urchade/gliner_medium-v2.1` → ONNX → INT8 quantize → load with `onnxruntime` (4–8× faster CPU inference)

#### 1a. Export Script (one-time, run offline)
**New file**: `streamlit_app/scripts/export_gliner_onnx.py`
```python
"""
Run ONCE to export GLiNER to quantized ONNX.
Output: streamlit_app/models/gliner_quantized.onnx (~95MB, was ~380MB)
"""
from gliner import GLiNER
from gliner.onnx import export_to_onnx
from onnxruntime.quantization import quantize_dynamic, QuantType

model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
export_to_onnx(model, "models/gliner_medium_fp32.onnx")
quantize_dynamic(
    "models/gliner_medium_fp32.onnx",
    "models/gliner_quantized.onnx",
    weight_type=QuantType.QInt8,
)
print("Done. gliner_quantized.onnx is ready.")
```

#### 1b. ONNX GLiNER Loader in `ner_pipeline.py`
**Modify**: [`ner_pipeline.py:112–131`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L112)

```python
ONNX_MODEL_PATH = Path(__file__).resolve().parent / "models" / "gliner_quantized.onnx"

def _get_gliner():
    global _gliner_model
    if _gliner_model is None:
        if ONNX_MODEL_PATH.exists():
            # Fast path: use quantized ONNX (4–8× faster CPU)
            from gliner import GLiNER
            print("  [ner-b] Loading quantized GLiNER ONNX…", flush=True)
            _gliner_model = GLiNER.from_pretrained(
                config.GLINER_MODEL_ID,
                onnx_model_file=str(ONNX_MODEL_PATH),
                local_files_only=True,
            )
        else:
            # Fallback: standard PyTorch (slow)
            print("  [ner-b] ONNX not found — loading PyTorch GLiNER (slow)…", flush=True)
            from gliner import GLiNER
            _gliner_model = GLiNER.from_pretrained(config.GLINER_MODEL_ID)
    return _gliner_model
```

#### 1c. NER LRU Cache with Eviction + Cache Telemetry
**Modify**: [`ner_pipeline.py:58–60`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L58)

```python
# Replace unbounded dict with size-limited LRU cache
_NER_CACHE_MAX = 2000
_query_ner_cache: dict[str, list] = {}
_ner_cache_hits = 0
_ner_cache_misses = 0

def _ner_cache_get(text: str) -> list | None:
    global _ner_cache_hits
    if text in _query_ner_cache:
        _ner_cache_hits += 1
        return _query_ner_cache[text]
    return None

def _ner_cache_set(text: str, result: list) -> None:
    global _ner_cache_misses
    _ner_cache_misses += 1
    if len(_query_ner_cache) >= _NER_CACHE_MAX:
        # Evict oldest 10% of entries
        keys_to_evict = list(_query_ner_cache.keys())[:_NER_CACHE_MAX // 10]
        for k in keys_to_evict:
            del _query_ner_cache[k]
    _query_ner_cache[text] = result

def get_ner_cache_stats() -> dict:
    total = _ner_cache_hits + _ner_cache_misses
    return {
        "hits": _ner_cache_hits,
        "misses": _ner_cache_misses,
        "hit_rate": round(_ner_cache_hits / max(total, 1), 3),
        "cache_size": len(_query_ner_cache),
    }
```

#### 1d. Direct-Lookup GLiNER Skip
**Modify**: [`ner_pipeline.py:134–159`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L134)

```python
def run_layers_ab(text: str, skip_gliner: bool = False) -> list:
    cached = _ner_cache_get(text)
    if cached is not None:
        return cached

    ents = layer_a_rule_ner(text)

    # Skip GLiNER if: (a) forced skip (direct_lookup), (b) Layer A found entities
    # AND text is long (indexing chunks — GLiNER is never worth it on 200-char chunks
    # already handled by Layer A patterns)
    should_run_gliner = (
        not skip_gliner and (
            not ents
            or len(text) <= 500
            or "esg" in text.lower()
            or "climate" in text.lower()
        )
    )

    if should_run_gliner:
        try:
            ents += layer_b_gliner(text)
        except Exception as e:
            print(f"  [NER] GLiNER skipped: {e}", flush=True)

    # dedup ...
    result = _deduplicate(ents)
    if len(text) <= 500:   # only cache query-length texts
        _ner_cache_set(text, result)
    return result
```

**Estimated NER latency**: 9,000–157,000ms → **80–400ms** (ONNX + cache)

---

### Track 2: Parallel Retrieval with ThreadPoolExecutor (Already Partially Done in Compare)

**Current State**: The Compare tab (`app.py:261–266`) already runs traditional + hybrid in parallel via `ThreadPoolExecutor`. The Chat tab (`chat_view.py`) does the same. **However**, within each retrieval call, the sub-steps (NER → Graph → Vector → LLM) are **sequential**.

#### 2a. Parallelize Graph + Vector Retrieval
**Modify**: [`retrieval.py:184–218`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L184)

```python
import concurrent.futures

def hybrid_graphrag(query: str, store) -> dict:
    t_start = time.perf_counter()

    # Step 1: NER (must be first — graph uses entities, vector uses query directly)
    query_entities = ner_pipeline.run_layers_ab(query)
    query_type = query_classifier.classify_query(query)

    # Skip GLiNER for direct_lookup when Layer A found entities (saves 2–5s)
    if query_type == "direct_lookup" and query_entities:
        query_entities = [e for e in query_entities if e.get("layer") == "A"]

    entity_texts = [e["text"] for e in query_entities]

    # Step 2: Graph + Vector IN PARALLEL (saves whichever is slower)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        graph_future = pool.submit(
            graph_store.get_subgraph_for_query,
            query, None, 1, 15, query_entities
        )
        vector_future = pool.submit(store.retrieve, query, top_k_children=5)

        graph_result = graph_future.result()
        hits = vector_future.result()

    # ... rest of enrichment + prompt assembly
```

**Estimated savings**: Graph (4s) and Vector (0.2s) overlap → saves up to **4s** on graph-heavy queries.

#### 2b. Parallelize Taxonomy Path (Compare Tab)
**Modify**: [`taxonomy_retrieval.py:273–283`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L273)

```python
# In hybrid_graphrag_v2() — after embedding once:
query_vec_np = fs._embed_texts([query])
query_vec_list = query_vec_np[0].tolist()

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    graph_future = pool.submit(retrieve_graph, query, query_vec_list)
    vector_future = pool.submit(retrieve_vector, query, index, chunks, 3, query_vec_np)
    graph_ctx = graph_future.result()
    hyb_chunks = vector_future.result()
```

---

### Track 3: LLM Streaming for Perceived Latency (1.5s TTFT)

This is the most impactful UX change — users see characters appearing immediately instead of waiting for the full response.

#### 3a. Streaming Generator in `llm_text_client.py`
**New function**: Add to [`llm_text_client.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/llm_text_client.py)

```python
def call_llm_streaming(
    prompt: str,
    model_id: str = None,
    max_tokens: int = 512,
) -> Generator[str, None, dict]:
    """
    Yields text delta strings as they stream from Claude.
    Final yield is a dict {"input_tokens": N, "output_tokens": N}.

    Usage in Streamlit:
        streamer = llm_text_client.call_llm_streaming(prompt)
        full_text = st.write_stream(streamer)
    """
    client = _get_client()
    if client is None:
        yield ""
        return

    model = model_id or config.CLAUDE_MODEL_LIGHT
    input_tokens = output_tokens = 0

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
        # Capture usage from the final message
        msg = stream.get_final_message()
        input_tokens = msg.usage.input_tokens
        output_tokens = msg.usage.output_tokens

    yield {"input_tokens": input_tokens, "output_tokens": output_tokens}
```

#### 3b. HTTP/2 Keep-Alive Pool (One-Line Fix)
**Modify**: [`llm_text_client.py:28`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/llm_text_client.py#L28)

```python
import httpx

def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=config.CLAUDE_API_KEY,
            http_client=httpx.Client(
                http2=True,
                timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0),
                limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=30),
            )
        )
    return _client
```

**Eliminates**: ~200–400ms TCP+TLS handshake on every non-first LLM call.

#### 3c. Cap Retry Delay
**Modify**: [`llm_text_client.py:89`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/llm_text_client.py#L89)

```python
# Current (unbounded — can add 35s):
wait = CLAUDE_RETRY_DELAY * (2 ** attempt)

# Fixed (max 10s):
wait = min(CLAUDE_RETRY_DELAY * (2 ** attempt), 10)
CLAUDE_MAX_RETRIES = 2   # for query serving; indexing can keep 3
```

#### 3d. `st.write_stream` in `chat_view.py`
**Modify**: Chat response rendering in [`chat_view.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/chat_view.py)

The key change: instead of `st.markdown(answer)` after full response, use:
```python
# In the chat rendering block — hybrid answer display:
with st.chat_message("assistant"):
    # Show retrieval metadata first (graph nodes, telemetry) — instant
    st.caption(f"⚡ Graph: {graph_time_ms:.0f}ms | Vector: {vec_time_ms:.0f}ms")

    # Stream the LLM answer as it generates
    stream_gen = llm_text_client.call_llm_streaming(
        prompt, model_id=config.CLAUDE_MODEL_LIGHT, max_tokens=512
    )
    answer = st.write_stream(stream_gen)
```

**Note**: Streaming requires the retrieval phase to complete before LLM starts. With Track 2 parallelism, retrieval drops from ~15s to ~2–4s, making streaming meaningful.

---

### Track 4: Neo4j Index Creation (70% Graph Latency Reduction)

Run these Cypher statements once against the live Neo4j instance (port 7687 for `retrieval.py`, port 7688 for `taxonomy_retrieval.py`):

#### 4a. For Port 7687 (`retrieval.py` / main graph)
```cypher
-- Entity lookup index (Path 1 of get_subgraph_for_query)
CREATE INDEX entity_text_idx IF NOT EXISTS FOR (n:Entity) ON (n.text);

-- Product name index (Path 2 of get_subgraph_for_query)
CREATE INDEX entity_product_idx IF NOT EXISTS FOR (n:Entity) ON (n.product_name);

-- Source document index (for scoped aggregations)
CREATE INDEX entity_source_idx IF NOT EXISTS FOR (n:Entity) ON (n.source);

-- Entity label + text composite (for get_entity_type_summary)
CREATE INDEX entity_label_idx IF NOT EXISTS FOR (n:Entity) ON (n.label);
```

#### 4b. For Port 7688 (`taxonomy_retrieval.py` / taxonomy graph)
```cypher
-- SchemeClass lookup
CREATE INDEX scheme_code_idx IF NOT EXISTS FOR (n:SchemeClass) ON (n.code);
CREATE INDEX scheme_regime_idx IF NOT EXISTS FOR (n:SchemeClass) ON (n.regime_id);

-- RegulatoryRegime status
CREATE INDEX regime_status_idx IF NOT EXISTS FOR (n:RegulatoryRegime) ON (n.status);

-- CircularAmendment date-based traversal
CREATE INDEX circular_id_idx IF NOT EXISTS FOR (n:RegulatoryCircular) ON (n.circular_id);
```

#### 4c. New: `graph_store.create_indexes()` Utility
**New function** in [`graph_store.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/graph_store.py):

```python
def create_indexes():
    """Run once at startup to ensure all query-critical indexes exist."""
    index_statements = [
        "CREATE INDEX entity_text_idx IF NOT EXISTS FOR (n:Entity) ON (n.text)",
        "CREATE INDEX entity_product_idx IF NOT EXISTS FOR (n:Entity) ON (n.product_name)",
        "CREATE INDEX entity_source_idx IF NOT EXISTS FOR (n:Entity) ON (n.source)",
        "CREATE INDEX entity_label_idx IF NOT EXISTS FOR (n:Entity) ON (n.label)",
    ]
    with get_driver().session(database=config.NEO4J_DATABASE) as session:
        for stmt in index_statements:
            try:
                session.run(stmt)
            except Exception as e:
                print(f"  [graph] Index creation skipped: {e}", flush=True)
    print("  [graph] Neo4j indexes verified.", flush=True)
```

Call `graph_store.create_indexes()` once on Streamlit startup (in `app.py` startup block, wrapped in try/except for offline-Neo4j resilience).

**Estimated savings**: Path 1 graph lookup 2.3–9.3s → **0.3–0.6s** with indexes.

---

### Track 5: FAISS Memory-Map Loading + Warm-Up

#### 5a. Memory-Mapped Index Load
**Modify**: [`faiss_store.py:714`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py#L714) and [`taxonomy_retrieval.py:49`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L49)

```python
import faiss

# Replace:
self.index = faiss.read_index(str(faiss_path))

# With:
self.index = faiss.read_index(str(faiss_path), faiss.IO_FLAG_MMAP)
```

At 50 docs (~200–370MB index), mmap lets the OS lazily page in only needed portions. **First query after startup**: slightly slower (page faults). Subsequent queries: same speed as RAM-loaded, with much lower startup memory pressure.

#### 5b. In-Process Warm-Up on Streamlit Start
**Modify**: [`app.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/app.py) — add at module level (runs once per worker process):

```python
@st.cache_resource(show_spinner="🔥 Warming up retrieval pipeline…")
def _warm_up():
    """
    Pre-load all heavy models so the first user query doesn't pay cold-start cost.
    Returns a status dict for the UI.
    """
    import faiss_store, ner_pipeline, graph_store
    status = {}

    # 1. Embedding model (sentence-transformer, ~1s)
    faiss_store._get_embedder()
    status["embedder"] = "ready"

    # 2. GLiNER ONNX (3–5s first load, then cached)
    try:
        ner_pipeline._get_gliner()
        status["gliner"] = "ready"
    except Exception as e:
        status["gliner"] = f"unavailable: {e}"

    # 3. Neo4j indexes (idempotent — safe to run every startup)
    try:
        graph_store.create_indexes()
        status["neo4j_indexes"] = "verified"
    except Exception as e:
        status["neo4j_indexes"] = f"offline: {e}"

    # 4. Warm FAISS: touch the index with a dummy vector
    try:
        from faiss_store import list_available_products, get_store
        products = list_available_products()
        if products:
            store = get_store(products[0]["slug"])
            store.retrieve("warm up query", top_k_children=1)
        status["faiss"] = f"{len(products)} indexes ready"
    except Exception as e:
        status["faiss"] = f"error: {e}"

    return status

_warm_up_status = _warm_up()
```

**Estimated savings on first user query**: 5–15s cold-start eliminated.

---

### Track 6: Query Classifier Fast-Path Bypass

The query classifier currently makes a **Haiku LLM call** for ambiguous queries. This adds 300–800ms even before retrieval starts.

**Modify**: [`query_classifier.py:34–49`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/query_classifier.py#L34)

```python
# Expanded regex patterns — covers 80%+ of queries without LLM call
OPEN_ENDED_PATTERNS = re.compile(
    r"\b(what|explain|describe|how does|tell me about|summarize|overview|"
    r"key|main|important|esg|climate|sustainability|benefit|initiative|"
    r"highlight|discuss|elaborate)\b", re.I
)

def classify_query(query: str) -> str:
    """Fast path: regex covers 80%+ of queries. LLM only for genuinely ambiguous."""
    if AGGREGATION_PATTERNS.search(query):
        return "aggregation"
    if COMPARISON_PATTERNS.search(query) or TEMPORAL_COMPARISON_PATTERNS.search(query):
        return "comparison"
    if LOOKUP_PATTERNS.search(query):
        return "direct_lookup"
    if OPEN_ENDED_PATTERNS.search(query):
        return "open_ended"   # ← NEW: avoid LLM call for clearly descriptive queries

    # Only truly ambiguous queries reach here — maybe 10-15% of traffic
    result = llm_text_client.call_llm(
        _CLASSIFY_PROMPT.format(query=query),
        model_id=config.CLAUDE_MODEL_LIGHT,
        max_tokens=10,   # ← Limit to 10 tokens — we need ONE word
    )
    ...
```

**Estimated savings**: 300–800ms eliminated for ~85% of queries that are clearly descriptive.

---

## Implementation Sequence (Ordered by Impact/Risk)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ PHASE A — Zero-Risk Quick Wins (Today, <2 hours)                                │
│                                                                                 │
│  A1. Add OPEN_ENDED_PATTERNS to query_classifier.py          [-800ms]          │
│  A2. Cap retry delay: min(..., 10) in llm_text_client.py     [-25s worst case] │
│  A3. Add HTTP/2 keep-alive pool to llm_text_client.py        [-400ms/call]     │
│  A4. Add max_tokens=10 to classifier LLM call                [-300ms]          │
│  A5. Parallel graph+vector in hybrid_graphrag_v2()           [-4s taxonomy]    │
│  A6. Create Neo4j indexes (run Cypher statements)            [-3–8s graph]     │
│  A7. Add st.cache_resource warm-up in app.py                 [-15s first query]│
└─────────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ PHASE B — GLiNER ONNX Quantization (1–2 days, highest impact)                  │
│                                                                                 │
│  B1. Run export_gliner_onnx.py script (offline, one-time)                      │
│  B2. Update _get_gliner() to prefer ONNX model               [-12s avg NER]   │
│  B3. Add NER LRU cache with eviction + hit/miss telemetry    [-100% on repeat] │
│  B4. Add skip_gliner flag for direct_lookup queries           [-2–5s/query]    │
│  B5. Add FAISS IO_FLAG_MMAP loading                          [-memory pressure]│
└─────────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ PHASE C — LLM Streaming (3–4 days, best UX impact)                             │
│                                                                                 │
│  C1. Add call_llm_streaming() generator to llm_text_client.py                  │
│  C2. Refactor hybrid_graphrag() to separate retrieval from generation           │
│      (retrieval returns context_package; generation is a separate step)         │
│  C3. Update chat_view.py to use st.write_stream()                               │
│  C4. Keep non-streaming path for Compare tab (needs full text for rendering)    │
└─────────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ PHASE D — Parallel Hybrid Retrieval in retrieval.py (3 hours)                  │
│                                                                                 │
│  D1. Parallelize graph + vector with ThreadPoolExecutor       [-4s max]        │
│  D2. Add graph_store.create_indexes() call on startup         [idempotent]     │
│  D3. Add cache_hit telemetry to log_query_audit()                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Expected Latency After All Phases

| Pipeline Step | Current | After Phase A | After Phase B | After Phase C+D |
|---|---|---|---|---|
| NER Layer B (GLiNER) | 9,000–157,000ms | 9,000ms (unchanged) | **80–400ms** | **0ms (cached)** |
| Query Classifier | 300–800ms | **0–50ms** (regex) | 0–50ms | 0–50ms |
| Graph Traversal (Neo4j) | 2,300–9,300ms | **300–600ms** (indexes) | 300–600ms | **150–300ms** (parallel) |
| FAISS Vector Search | 30–300ms | 30–300ms | **20–100ms** (mmap) | **20–100ms** (parallel) |
| LLM Generation (TTFT) | 3,400–8,200ms | 3,200–8,000ms | 3,200–8,000ms | **1,200–1,500ms** (streaming) |
| SSL/TCP Overhead | 200–400ms/call | **<10ms** (HTTP/2 pool) | <10ms | <10ms |
| Retry Worst Case | 35,000ms | **10,000ms** (capped) | 10,000ms | 10,000ms |
| **Total (typical)** | **22s–45s+** | **~8–10s** | **~3–5s** | **1.5s TTFT / 3.5s full** |

---

## Risk Matrix

| Change | Complexity | Risk | Mitigation |
|---|---|---|---|
| ONNX export (B1–B2) | Medium | GLiNER ONNX API may differ across gliner versions | Test with `gliner >= 0.2.0`; keep PyTorch fallback |
| Parallel ThreadPool in retrieval.py (D1) | Low | Thread safety of `graph_store.get_driver()` singleton | Neo4j Python driver is thread-safe; no issue |
| `st.write_stream` (C3) | Medium | Streamlit version must be ≥ 1.31 | Check `streamlit.__version__`; fallback to `st.markdown` |
| FAISS mmap (B5) | Low | mmap may not work on network drives | Use `IO_FLAG_MMAP` only for local paths; detect and fallback |
| HTTP/2 pool (A3) | Low | Requires `httpx[http2]` (`pip install httpx[h2]`) | Add to `requirements.txt` |
| Neo4j indexes (A6) | Very Low | `IF NOT EXISTS` makes it idempotent | Safe to run any number of times |

---

## Open Questions for User Review

1. **GLiNER ONNX**: Does your environment have `onnxruntime` and `onnxruntime.quantization` installed? If not, which do you prefer — ONNX quantization or simply switching to a lighter model (`gliner_small` is 4× faster than `gliner_medium`)?

2. **Streaming in Chat**: The `st.write_stream()` approach requires the retrieval phase to finish before streaming begins. Is a 2–4s "Retrieving…" spinner followed by instant token streaming acceptable UX? Or should we also show partial retrieval progress (e.g., "Graph matched 5 nodes…")?

3. **ONNX vs. lighter model**: Alternatively, `gliner_small-v2.1` (80MB) runs 4–6× faster on CPU than `gliner_medium` with ~5% accuracy drop. Would you prefer this as a faster path vs. ONNX quantization?

4. **Phase priority**: Should Phase C (streaming UX) be prioritized over Phase B (ONNX)? The streaming change is lower-risk but delivers UX improvement; ONNX is higher-impact but more complex.
