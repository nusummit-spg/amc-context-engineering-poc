# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Implementation Plan — Resolution of 59 Audit Defects across AMC Context Engineering Codebase

This implementation plan details the technical fixes for all 59 defects identified in [`Docs/AMC Context Engineering — Full Codebase Audit Report.md`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/Docs/AMC%20Context%20Engineering%20%E2%80%94%20Full%20Codebase%20Audit%20Report.md), prioritized by severity (P0 Critical -> P1 High -> P2 Medium -> P3 Low & Architecture Gaps).

---

## User Review Required

> [!IMPORTANT]
> **Key Structural Unification (GAP-1)**:
> Currently, `retrieval.py` (Chat tab) and `taxonomy_retrieval.py` (Compare tab) use separate execution pipelines. We will unify them so that the Compare tab also benefits from:
> 1. Budgeted prompt building via `context_engineering.build_prompt()`
> 2. PII Scrubbing with audit metrics (`pii_scrub.py`)
> 3. Compliance & Safety Guardrails (`compliance_guardrails.py`)
> 4. Intent Cache lookup and storage (`intent_cache.py`)
> 5. Sub-15ms FlashRank Reranking (`flashrank_reranker.py`)

---

## Proposed Changes

### Core System Engine Fixes (P0 Critical & P1 High)

---

#### [MODIFY] [intent_cache.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/intent_cache.py)
- **Fix P0-1**: Make date-entity guard symmetric (`if query_type == "direct_lookup": if query_dates != entry.date_entities: continue`). Prevents non-dated queries from hitting dated cache entries.
- **Fix P0-2**: Pre-normalize vectors once in `store()`, avoiding $O(N \times D)$ normalization operations during every lookup loop iteration.

---

#### [MODIFY] [ner_pipeline.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py)
- **Fix P0-3**: Copy entity dictionary before writing `child_id`/`parent_id` (`e = dict(e); e["child_id"] = child_id`). Prevents NER cache state corruption.
- **Fix P1-4**: Remove hardcoded `"esg"`/`"climate"` string triggers, delegating domain routing to `domain_intent`.
- **Fix P2-4**: Remove duplicate `_query_ner_cache` definition.

---

#### [MODIFY] [graph_store.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/graph_store.py)
- **Fix P0-7**: Set `matched_by="entity"` ONLY when Path 1 (entity match) produces edges; set `matched_by="product"` when falling back to Path 2. Prevents incorrect vector search bypass.
- **Fix P1-9**: Update Cypher guard regex to allow valid `CALL { MATCH ... }` read subqueries while keeping write prohibitions intact.

---

#### [MODIFY] [context_engineering.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py)
- **Fix P0-6**: Use `.get("product_name", "Unknown Document")` and `.get("page_num", 1)` when formatting chunks to prevent `KeyError` crashes on unkeyed or taxonomy chunks.
- **Fix P1-3**: Adjust query type token budget fractions to sum cleanly to 1.0.

---

#### [MODIFY] [taxonomy_retrieval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)
- **Fix P0-4**: Initialize `vec_time_ms = 0.0` after parallel retrieval block to prevent `NameError` crash.
- **Fix P0-5**: Remove `_taxonomy_driver.close()` call to preserve connection pool singleton.
- **Fix P1-7**: Replace hardcoded ESG history turns with dynamic config lookup.
- **Fix P1-10 & GAP-1 & GAP-3**: Wire `context_engineering.build_prompt()`, `pii_scrub`, `compliance_guardrails`, `flashrank_reranker`, and `intent_cache` lookup/store into the Compare tab pipeline.
- **Fix P2-7**: Dynamically set telemetry badge label to `f"Intent: {domain_intent.upper()}"`.

---

#### [MODIFY] [retrieval.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py)
- **Fix P1-2 & P2-11**: Calculate and record `enrichment_time = (time.perf_counter() - t2) * 1000.0` in telemetry breakdown.
- **Fix P1-6**: Use `.get("product_name")` safely when building secondary graph fallback scope.
- **Fix GAP-2**: Assign `query_for_retrieval = lang_info.get("normalized_query", query)` so regional Hinglish translations are passed to vector and graph search.
- **Fix P2-8**: Move dynamic `pii_scrub` and `language_detector` imports to top-level module scope.

---

#### [MODIFY] [entity_resolver.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/entity_resolver.py)
- **Fix P1-1**: Wrap `_embedding_cache` lookup with a maximum size check (`if len(_embedding_cache) > 4000: _embedding_cache.clear()`) to prevent unbounded memory growth and OOM errors.

---

#### [MODIFY] [text_to_cypher.py](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/text_to_cypher.py)
- **Fix P1-5**: Replace exact match `cypher.upper() == "NO_QUERY"` with substring check `"NO_QUERY" in cypher.upper()`.

---

#### [MODIFY] [requirements.txt](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/requirements.txt)
- **Fix P1-8**: Add missing dependencies: `litellm`, `httpx[http2]`, `flashrank`, `langdetect`.

---

## Verification Plan

### Automated Tests
Run the comprehensive test suite to verify all fixes pass clean:
1. `scratch/test_compliance_observability.py` (Verify PII metrics, language detection, safety guardrails, SHA-256 hashes, Triple Notation).
2. `scratch/test_phase2_performance.py` (Verify FlashRank reranking, FastEmbed loader, Docling layout parser).
3. `scratch/test_consolidated_features.py` (Verify IntentCache date entity guard, cache invalidation, rate limiter retry cap, safe Cypher check).
4. Create `scratch/test_audit_fixes_verification.py` specifically targeting P0-1 through P0-7, P1-1 through P1-11, and GAP-1 through GAP-5.

### Manual Verification
- Launch Streamlit application (`streamlit run app.py`).
- Test Chat tab and Compare tab with dated queries, Hinglish queries, and multi-entity comparison queries.
- Verify telemetry badges render correctly without `NameError` or `KeyError` crashes.
