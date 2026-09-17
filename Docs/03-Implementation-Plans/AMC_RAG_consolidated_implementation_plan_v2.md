# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC RAG System — Consolidated Implementation Plan

Implement the 8-phase consolidated roadmap combining Audit Report v2, Intent-Aware Architecture Plan, and Latency Reduction Plan without merge collisions, incorporating all user feedback items.

---

## User Review Required

> [!IMPORTANT]
> **P0-C Prompt Engineering Wiring**: Phase 1c wires `context_engineering.build_prompt()` directly into `retrieval.py::hybrid_graphrag()`. This replaces the unbudgeted inline prompt string with a 3,600-character budgeted prompt and dynamic output caps (512–768 tokens). Golden query evaluations will run before and after to verify zero answer regressions.

> [!IMPORTANT]
> **Intent-Aware Caching & Correctness Guards**: Phase 5 introduces `IntentAwareCache` in `intent_cache.py` with per-intent similarity thresholds (`CACHE_THRESHOLD_BY_INTENT`), date-entity cache collision guards for `direct_lookup` queries, domain bucket invalidation on reindex, and shadow mode logging prior to live substitution.

> [!NOTE]
> **Confidence Calibration UI Badges**: Phase 7 ensures that confidence calibration reasons (e.g., `"medium confidence (limited graph coverage)"`) are explicitly surfaced in `chat_view.py` and `compare_view.py` badges so users understand graph coverage constraints.

---

## Proposed Changes

### Configuration & Pre-Flight (Phase 0)

#### [NEW] [golden_query_eval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/scratch/golden_query_eval.py)
- Create baseline evaluation script with 15 benchmark queries across regulatory, ESG, financial, and compliance domains to capture answer accuracy and latency before/after each phase.

#### [MODIFY] [config.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/config.py)
- Add feature flags: `ENABLE_CONTEXT_BUDGET`, `ENABLE_INTENT_CACHE`, `ENABLE_PARALLEL_RETRIEVAL`, `ENABLE_STREAMING`, `ENABLE_ONNX_GLINER`.
- Add `GLINER_LABELS_BY_DOMAIN` dictionary for domain-routed zero-shot entity extraction.

---

### Core Fixes & Performance Optimization (Phases 1 – 4)

#### [MODIFY] [faiss_store.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py)
- Define `EMBED_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"` & `EMBED_MODEL_NAME = "all-MiniLM-L6-v2"`. Use in `_get_embedder()`.
- Add `faiss.IO_FLAG_MMAP` support for local index loading.
- Wire `IntentAwareCache.invalidate_domain()` upon index build completion.

#### [MODIFY] [taxonomy_retrieval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)
- Remove redundant `driver.close()` call inside `retrieve_graph()`.
- Add `faiss.IO_FLAG_MMAP` for taxonomy FAISS index loading.
- Parallelize `retrieve_graph` and `retrieve_vector` inside `hybrid_graphrag_v2()` using `ThreadPoolExecutor(max_workers=2)`.
- Apply history compression (`compress_history_for_intent()`) to Compare tab taxonomy retrieval path.

#### [MODIFY] [llm_text_client.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/llm_text_client.py)
- Cap retry delay: `wait = min(CLAUDE_RETRY_DELAY * 2**attempt, 10)`, `CLAUDE_MAX_RETRIES = 2`.
- Configure `httpx.Client(http2=True, keepalive_expiry=30)`.
- Implement `call_llm_streaming()` generator for token-by-token streaming.

#### [MODIFY] [query_classifier.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/query_classifier.py)
- Set `max_tokens=10` on LLM fallback classifier call.
- Add `OPEN_ENDED_PATTERNS` regex to fast-path ~85% of queries without LLM invocation.

#### [MODIFY] [ner_pipeline.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py)
- Implement `_query_ner_cache` with `_NER_CACHE_MAX = 2000` and LRU eviction. Scope cache lookup to `is_query=True` to prevent chunk indexing pollution.
- Add support for ONNX quantized GLiNER model (`models/gliner_quantized.onnx`) with seamless PyTorch fallback.
- Add `skip_gliner` parameter to bypass GLiNER on `direct_lookup` queries with existing Layer A matches.

#### [MODIFY] [graph_store.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/graph_store.py)
- Ensure indexes exist on Neo4j startup for both port 7687 and 7688 instances.

#### [MODIFY] [app.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/app.py)
- Add `@st.cache_resource` startup warm-up function for embedder, GLiNER, and Neo4j connection pool.

---

### Intent Routing, Parallel Engine & Caching (Phases 5 – 7)

#### [NEW] [intent_cache.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/intent_cache.py)
- Create `IntentAwareCache`, `DOMAIN_PATTERNS`, `classify_domain_intent()`, domain-specific TTLs, and `CACHE_THRESHOLD_BY_INTENT` dict.
- Implement date-entity matching guard on `direct_lookup` queries: force cache miss if date entities in query vs cached query differ (preventing "15 July" vs "16 July" collision).
- Implement `invalidate_domain(domain_intent)` and `clear_all()` for reindex events.

#### [MODIFY] [context_engineering.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py)
- Add domain-routed prompt templates (`PROMPT_TEMPLATES` and `get_prompt_template()`).
- Support history text injection in `build_prompt()`.

#### [MODIFY] [retrieval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)
- **Phase 1c**: Wire `context_engineering.build_prompt()` into `hybrid_graphrag()`.
- **Phase 3**: Add `not vector_bypassed` check to secondary graph re-query (`if not graph_result["edges"] and hits and not vector_bypassed:`).
- **Phase 3**: Switch audit log from one file per query to single appending `query_audit.jsonl` file and include `tokens_hidden_cypher`.
- **Phase 6 (Unified Engine Rewrite)**:
  - Cache short-circuit at top (`cache.lookup()`).
  - Domain-routed GLiNER labels via `config.get_gliner_labels(domain_intent)`.
  - Intent-driven retrieval parameters: `GRAPH_HOPS_BY_INTENT`, `GRAPH_LIMIT_BY_INTENT`, and `VECTOR_TOPK_BY_INTENT`.
  - Parallel graph + vector retrieval using `ThreadPoolExecutor(max_workers=2)` using the intent parameters.
  - Template selection in `context_engineering.build_prompt(..., domain_intent=domain_intent)`.
  - Streaming output support for `chat_view.py`.
  - Cache storage on success.
  - Consolidated single audit log write.
- **Phase 7**: Add `calibrate_confidence()` and attach human-readable `confidence_reason` string (e.g., `"(limited graph coverage)"`).

#### [MODIFY] [chat_view.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/chat_view.py) & [compare_view.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/compare_view.py)
- Render streaming responses using `st.write_stream()` while preserving non-streaming full text for Compare tab.
- Render explicit `confidence_label` and `confidence_reason` badges in the UI (e.g. `⚡ Medium Confidence (limited graph coverage)`).

---

### Deferred Work (Phase 8 — Future Scale-Up)
- **Context Micro-Notation**: Compress graph context string format (-68% token cost on compare path).
- **`IndexIVFFlat` Upgrade**: Switch from exact brute-force `IndexFlatIP` to `IndexIVFFlat` at 50K+ vectors (8–10x search speedup).
- **ESG Graph Schema Expansion**: Add `:ESGMetric`, `:CarbonEmission`, and `:GovernanceItem` graph nodes to raise ESG graph coverage from 0.15 to >0.85 (reversing the Phase 7 confidence downgrade).
- **Cross-Document Entity Resolution**: Post-ingestion embedding-similarity clustering across multi-year annual reports.
- **Namespace Router**: Scoped vector search across document categories.
- **Structural Clause Chunking**: Preserve clause section boundaries for SEBI master circulars.

---

## Verification Plan

### Automated Verification & Benchmark Harness
1. **Golden Query Benchmark Harness**:
   - Run `scratch/golden_query_eval.py` to evaluate 15 queries across all domains before and after each phase.
   - Verify p50 / p95 latencies and answer citation correctness.

2. **NER Cache Isolation Test**:
   - Index two documents with identical boilerplate headers; verify entity cache entries stay strictly isolated by `is_query=True` and `(text, doc_id)`.

3. **Retry-Cap Simulation Test**:
   - Simulate a 3x-failing LLM API response and confirm retry wait duration caps at 10s max (preventing 35s worst-case hangs).

4. **ONNX Quantization Accuracy Test**:
   - Verify zero-shot confidence score retention for ESG GLiNER labels (`'ESG initiatives'`, `'climate change adaptation'`) post-INT8 quantization, ensuring score threshold > `GLINER_THRESHOLD`.

5. **Parallel Retrieval & Streaming Verification**:
   - Verify concurrent execution of graph and vector threads via execution breakdown logs.
   - Confirm token streaming in Streamlit UI using `st.write_stream()`.
