# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC RAG System — Consolidated Implementation Plan

Implement the 8-phase consolidated roadmap combining Audit Report v2, Intent-Aware Architecture Plan, and Latency Reduction Plan without merge collisions.

---

## User Review Required

> [!IMPORTANT]
> **P0-C Prompt Engineering Wiring**: Phase 1c wires `context_engineering.build_prompt()` directly into `retrieval.py::hybrid_graphrag()`. This replaces the unbudgeted inline prompt string with a 3,600-character budgeted prompt and dynamic output caps (512–768 tokens). Golden query evaluations will run before and after to verify zero answer regressions.

> [!NOTE]
> **Intent Cache Shadow Mode**: Phase 5 introduces `IntentAwareCache`. It will run in shadow mode first (computing domain intent and logging cache matches without overriding live responses) to validate domain classification accuracy before live serving.

---

## Proposed Changes

### Configuration & Pre-Flight (Phase 0)

#### [NEW] [golden_query_eval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/scratch/golden_query_eval.py)
- Create baseline evaluation script with 15 benchmark queries across regulatory, ESG, financial, and compliance domains to capture answer accuracy and latency before/after each phase.

#### [MODIFY] [config.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/config.py)
- Add feature flags: `ENABLE_CONTEXT_BUDGET`, `ENABLE_INTENT_CACHE`, `ENABLE_PARALLEL_RETRIEVAL`, `ENABLE_STREAMING`, `ENABLE_ONNX_GLINER`.
- Add `GLINER_LABELS_BY_DOMAIN` dictionary for intent-routed zero-shot entity extraction.

---

### Core Fixes & Performance Optimization (Phases 1 – 4)

#### [MODIFY] [faiss_store.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py)
- Define `EMBED_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"` & `EMBED_MODEL_NAME = "all-MiniLM-L6-v2"`. Use in `_get_embedder()`.
- Add `faiss.IO_FLAG_MMAP` support for local index loading.

#### [MODIFY] [taxonomy_retrieval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)
- Remove redundant `driver.close()` call inside `retrieve_graph()`.
- Add `faiss.IO_FLAG_MMAP` for taxonomy FAISS index loading.

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

### Intent Routing & Parallel Engine (Phases 5 – 7)

#### [NEW] [intent_cache.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/intent_cache.py)
- Create `IntentAwareCache`, `DOMAIN_PATTERNS`, `classify_domain_intent()`, domain-specific TTLs, dual-gate lookup (`lookup(query_vec, query_type, domain_intent)`), and cache storage.

#### [MODIFY] [context_engineering.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py)
- Add domain-routed prompt templates (`PROMPT_TEMPLATES` and `get_prompt_template()`).
- Support history text injection in `build_prompt()`.

#### [MODIFY] [retrieval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)
- **Phase 1c**: Wire `context_engineering.build_prompt()` into `hybrid_graphrag()`.
- **Phase 3**: Add `not vector_bypassed` check to secondary graph re-query (`if not graph_result["edges"] and hits and not vector_bypassed:`).
- **Phase 3**: Switch audit log from one file per query to single appending `query_audit.jsonl` file and include `tokens_hidden_cypher`.
- **Phase 6**: Rewrite `hybrid_graphrag()` to integrate intent cache short-circuit, `ThreadPoolExecutor(max_workers=2)` parallel graph + vector retrieval, domain-routed GLiNER labels, history compression, and calibrated confidence scoring.

#### [MODIFY] [chat_view.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/chat_view.py)
- Render streaming responses using `st.write_stream()` while preserving non-streaming full text for Compare tab.

---

## Verification Plan

### Automated Verification & Benchmark Harness
1. **Golden Query Benchmark Harness**:
   - Run `scratch/golden_query_eval.py` to evaluate 15 queries across all domains.
   - Verify p50 / p95 latencies and answer citation correctness after Phase 1, Phase 3, Phase 4, and Phase 6.

2. **NER Cache Isolation Test**:
   - Index two documents with identical boilerplate headers; verify entity cache entries stay strictly isolated by `(text, doc_id)`.

3. **Parallel Retrieval & Streaming Verification**:
   - Verify concurrent execution of graph and vector threads via execution breakdown logs.
   - Confirm token streaming in Streamlit UI using `st.write_stream()`.
