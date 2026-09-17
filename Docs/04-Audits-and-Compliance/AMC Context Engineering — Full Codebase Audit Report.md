# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC Context Engineering — Full Codebase Audit Report
> **Date**: 2026-07-31 | **Scope**: All 40 files in `streamlit_app/` | **Method**: 4-parallel subagent + manual cross-module scan

---

## Severity Legend
| Level | Meaning |
|---|---|
| 🔴 **P0 — Critical** | Will crash in production / produces wrong answers silently |
| 🟠 **P1 — High** | Significant correctness or performance degradation |
| 🟡 **P2 — Medium** | Design gap, technical debt, suboptimal logic |
| 🔵 **P3 — Low** | Minor clean-up, unused code, cosmetic |

**Total Issues Found: 47**

---

## Part 1: CRITICAL BUGS (P0) — Fix Before Any Production Use

---

### 🔴 P0-1 · `intent_cache.py:122` — Asymmetric Date-Entity Cache Guard (Wrong Answers)

**File**: [`intent_cache.py:117–125`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/intent_cache.py#L117)

**Bug**: The date-entity guard that prevents stale time-sensitive answers from being served from cache is logically inverted. The current condition is:
```python
if query_type == "direct_lookup" and query_dates:
    if query_dates != entry.date_entities:
        continue
```
If the **incoming query has NO dates** (empty `query_dates`), the outer `if` is `False` — the guard is skipped entirely. A generic query like `"What is the revenue?"` will hit the cache of a specific dated query like `"What is the revenue for Q3 FY24?"` (similarity ≥ 0.95) and return the **wrong quarterly-specific answer as if it were a general answer**.

**Fix**:
```python
# Symmetric check — dates must match exactly on BOTH sides
if query_type == "direct_lookup":
    if query_dates != entry.date_entities:
        continue
```

---

### 🔴 P0-2 · `intent_cache.py:124` — Cached Vector Normalized on Every Lookup (Per-Loop Overhead + Correctness Risk)

**File**: [`intent_cache.py:124`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/intent_cache.py#L124)

**Bug**: Inside the inner loop over all candidates, `entry.query_vec` is re-normalized on every iteration:
```python
e_norm = entry.query_vec / (np.linalg.norm(entry.query_vec) + 1e-9)
```
This is O(N × D) unnecessary work where N = number of cache entries and D = 384 dimensions. If a vector was stored non-normalized (e.g., from a provider with different normalization), repeated in-loop division produces correct results but wastes CPU. The vector should be **normalized once at `store()` time** and stored pre-normalized.

**Fix**: In `store()`, add `query_vec = query_vec / (np.linalg.norm(query_vec) + 1e-9)` before creating the `CacheEntry`. In `lookup()`, only normalize the incoming query once, and use `np.dot` directly without re-normalizing cached entries.

---

### 🔴 P0-3 · `ner_pipeline.py:274-275` — Cache Object Mutation (Corrupted State)

**File**: [`ner_pipeline.py:274`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L274)

**Bug**: `run_full_ner_for_chunk_set` mutates entity dicts returned by `run_layers_ab()`:
```python
e["child_id"] = child_id   # ← mutates the dict in-place
e["parent_id"] = parent_id
```
When `run_layers_ab()` serves results from `_query_ner_cache`, these are the **same dict objects stored in cache**. Mutating them writes `child_id`/`parent_id` into the cache, so the next query that gets a cache hit receives entities pre-loaded with a different document's `child_id`. This causes graph nodes to be attached to wrong document chunks.

**Fix**: Always copy: `e = dict(e); e["child_id"] = child_id`

---

### 🔴 P0-4 · `taxonomy_retrieval.py:391` — `vec_time_ms` NameError Crash

**File**: [`taxonomy_retrieval.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)

**Bug**: When `ENABLE_PARALLEL_RETRIEVAL=True` (the default), graph and vector retrieval run together inside the `ThreadPoolExecutor` block. The variable `vec_time_ms` is never assigned — only `graph_time_ms` is set (line 298 captures both combined). When the telemetry dict is built, it references `vec_time_ms` → `NameError` → every ContextGraph query in the Compare tab crashes.

**Fix**: After the parallel block, add:
```python
vec_time_ms = 0.0   # absorbed into graph_time_ms in parallel mode
```

---

### 🔴 P0-5 · `taxonomy_retrieval.py:74` — `_taxonomy_driver.close()` Destroys Singleton

**File**: [`taxonomy_retrieval.py:74`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L74)

**Bug**: The taxonomy graph driver singleton is closed at line 74 inside a connection cleanup block. After the first query, `_taxonomy_driver` is `None`-equivalent (closed). Every subsequent query attempt to get the driver opens a new connection (adds 120–300ms) or fails silently. Combined with parallel retrieval, this causes race conditions where a concurrent query finds a closed driver.

**Fix**: Remove `_taxonomy_driver.close()`. Connection pooling is handled by the Neo4j driver internally.

---

### 🔴 P0-6 · `context_engineering.py:111-112` — KeyError on Missing Chunk Fields

**File**: [`context_engineering.py:111`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py#L111)

**Bug**: The vector context formatter assumes all retrieved chunks have `product_name` and `page_num`:
```python
f"[{i+1}] {h['product_name']} p.{h['page_num']}\n{h['parent_text']}"
```
In two real scenarios this crashes: (1) taxonomy index chunks that use `"name"` not `"product_name"`, (2) any fallback chunk assembled without these keys. This is a `KeyError` that propagates as an unhanded exception to the Streamlit UI.

**Fix**: Use `.get()` with defaults: `h.get('product_name', 'Unknown')`, `h.get('page_num', '?')`.

---

### 🔴 P0-7 · `graph_store.py:214` — False `matched_by="entity"` When Falling Back to Product Match

**File**: [`graph_store.py:214`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/graph_store.py#L214)

**Bug**: The `get_subgraph_for_query()` return sets `matched_by="entity"` whenever `entity_texts` is non-empty — even when Path 1 (entity match) returned zero results and Path 2 (product match) was used instead. Downstream logic in `retrieval.py:200-201` checks `matched_by == "entity"` to determine whether to trust graph signal and bypass vector search. This means vector search gets **incorrectly bypassed** when only a product-level graph match was found, causing missed context.

**Fix**: Track which path succeeded and set `matched_by` accordingly: `"entity"` only when Path 1 returns edges, `"product"` when Path 2 is used.

---

## Part 2: HIGH SEVERITY (P1)

---

### 🟠 P1-1 · `entity_resolver.py:31` — Unbounded `_embedding_cache` → OOM at 50 Docs

**File**: [`entity_resolver.py:31`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/entity_resolver.py#L31)

`_embedding_cache` is a plain dict with no eviction policy, no TTL, and no max size. Every distinct entity string encountered is cached forever. At 50 documents with thousands of unique entities, this dict grows unboundedly. In a long-running Streamlit session (days/weeks), this will cause memory exhaustion. **Fix**: Convert to `functools.lru_cache(maxsize=4096)` or add `if len(_embedding_cache) > 4000: _embedding_cache.clear()`.

---

### 🟠 P1-2 · `retrieval.py:488` — `enrichment_time` Never Defined → Telemetry Always 0

**File**: [`retrieval.py:488`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L488)

`telemetry_breakdown` references `enrichment_time if 'enrichment_time' in locals() else 0.0`. The variable `enrichment_time` is never assigned anywhere in `hybrid_graphrag()`. All audit logs show `enrichment_time=0.0` forever — this is a missing timing capture that makes the audit log misleading.

---

### 🟠 P1-3 · `context_engineering.py:28-32` — Token Budget Fractions Don't Sum to 1.0

**File**: [`context_engineering.py:28`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py#L28)

`QUERY_TYPE_BUDGETS` fractions leave 15–20% of the budget unused:
```python
"aggregation": {"graph": 0.50, "vector": 0.35}  # leaves 0.15 unused
"comparison":  {"graph": 0.55, "vector": 0.30}  # leaves 0.15 unused
```
At a `DEFAULT_TOKEN_BUDGET=3600`, this wastes 540 tokens per aggregation query — enough for 1–2 additional retrieved chunks that could improve answer quality. Fractions should sum to `≤ 1.0` intentionally (for prompt overhead) but should be documented.

---

### 🟠 P1-4 · `ner_pipeline.py:200-201` — Hardcoded ESG Domain Trigger

**File**: [`ner_pipeline.py:200`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L200)

```python
or "esg" in text.lower() or "climate" in text.lower()
```
This is a hardcoded domain-specific bypass that was supposed to be removed when the dynamic `domain_intent` parameter was introduced. It means GLiNER is triggered for ESG/climate regardless of cache or domain intent, but **not** triggered for governance, financial performance, or other domains with long text — completely violating the intent-routing architecture.

---

### 🟠 P1-5 · `text_to_cypher.py:91` — Fragile `NO_QUERY` Check

**File**: [`text_to_cypher.py:91`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/text_to_cypher.py#L91)

```python
cypher.upper() == "NO_QUERY"
```
Claude/Groq frequently returns `"NO_QUERY."` or `"NO_QUERY\n"` or `"The answer is: NO_QUERY"`. The exact-match check fails silently, passing through a non-Cypher string to Neo4j which then throws a parse error. **Fix**: `"NO_QUERY" in cypher.upper()`.

---

### 🟠 P1-6 · `retrieval.py:322` — Secondary Graph Fallback Can `KeyError` on `product_name`

**File**: [`retrieval.py:322`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L322)

```python
product_names = {h["product_name"] for h in hits}
```
If `hits` contains a chunk without `product_name` (e.g., from a taxonomy index or an older index built before the field was added), this raises `KeyError`. **Fix**: `product_names = {h.get("product_name") for h in hits if h.get("product_name")}`.

---

### 🟠 P1-7 · `taxonomy_retrieval.py:305` — History Compression Hardcodes ESG Domain

**File**: [`taxonomy_retrieval.py:305`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L305)

```python
turns = 2 if domain_intent != "esg_sustainability" else 3
```
This is the exact anti-pattern flagged in the dynamic domain architecture plan. Now that `domain_intent` is properly classified by `intent_cache.classify_domain_intent()`, the turn count should come from a config dict, not an ESG-specific hardcode.

---

### 🟠 P1-8 · `requirements.txt` — Missing `litellm` Dependency

**File**: [`requirements.txt`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/requirements.txt)

`llm_text_client.py` imports `litellm` at module level, but `litellm` is **not listed in `requirements.txt`**. Any fresh `pip install -r requirements.txt` will result in an `ImportError` on startup. Additionally missing: `httpx[http2]` (required for HTTP/2 keep-alive), `flashrank` (used in `flashrank_reranker.py`), `langdetect` (used in `language_detector.py`).

---

### 🟠 P1-9 · `graph_store.py:283,292` — Cypher Guard Rejects Valid Read Queries

**File**: [`graph_store.py:283`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/graph_store.py#L283)

The write-keyword and semicolon guards for safety block legitimate patterns:
- `CALL { MATCH ... }` (valid read subquery) is blocked by the `CALL` prohibition
- Any node property containing the literal string `"CREATE"` would block the query

---

### 🟠 P1-10 · `taxonomy_retrieval.py` — Not Using `context_engineering.build_prompt()`

**File**: [`taxonomy_retrieval.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)

The taxonomy path (Compare tab + ContextGraph results) builds its LLM prompt via manual string concatenation, bypassing `context_engineering.py` entirely. This means the token budget, deduplication, and preamble guarantees in `context_engineering.py` only apply to the Chat tab's `retrieval.py` path — not to the Compare tab. Users get inconsistent quality between the two tabs.

---

### 🟠 P1-11 · `claude_vision_client.py` — Not Using LiteLLM (Bypasses Provider Abstraction)

**File**: [`claude_vision_client.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/claude_vision_client.py)

This file imports `anthropic` directly and always uses Claude for vision extraction. It completely bypasses the new LiteLLM abstraction, meaning:
- Vision extraction is permanently locked to Anthropic even if `PRIMARY_LLM_PROVIDER=groq`
- No retry abstraction — Claude API failures during PDF indexing are not handled uniformly
- Adds a direct `anthropic` SDK dependency that technically doesn't need to be in `requirements.txt` separately from `litellm`

---

## Part 3: MEDIUM SEVERITY (P2)

---

### 🟡 P2-1 · `query_classifier.py:18-19` — `LOOKUP_PATTERNS` Too Narrow

**File**: [`query_classifier.py:18`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/query_classifier.py#L18)

Only matches: `who manages`, `who holds`, `who is`, `what is the benchmark/exit load/isin`. Misses: `"How much is the AUM?"`, `"When was this fund launched?"`, `"What is the TER?"`, `"Which fund house manages?"`. These fall through to an LLM call (300–800ms) instead of being classified immediately as `direct_lookup`.

---

### 🟡 P2-2 · `query_classifier.py:49` — LLM Response Not Structurally Enforced

**File**: [`query_classifier.py:49`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/query_classifier.py#L49)

If the LLM responds with `"I believe this is an aggregation query"` instead of bare `"aggregation"`, the string match fails and defaults to `"open_ended"`. This happens more frequently with Groq/Llama models which are more verbose. **Fix**: Use `max_tokens=5` (already a suggestion but not applied) and strip common prefixes.

---

### 🟡 P2-3 · `context_engineering.py:23` — Deduplication 85% Overlap Threshold is Too High

**File**: [`context_engineering.py:23`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/context_engineering.py#L23)

The prose/graph deduplication threshold is set at `overlap < 0.85`. Since the overlap calculation includes stop-words like "the", "is", "a", this threshold is effectively never triggered — prose chunks that partially repeat graph facts are always both included, wasting tokens and potentially confusing the LLM with conflicting signals.

---

### 🟡 P2-4 · `ner_pipeline.py:58 and L113` — `_query_ner_cache` Defined Twice

**File**: [`ner_pipeline.py:58,113`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py)

`_query_ner_cache: dict[str, list] = {}` appears twice. The second declaration at L113 would reset the cache to empty if the module were somehow reloaded. While harmless in normal operation, it signals incomplete refactoring.

---

### 🟡 P2-5 · `ner_pipeline.py:12` — `import json` Never Used

**File**: [`ner_pipeline.py:12`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L12)

Unused import — minor but contributes to startup overhead and suggests code was partially cleaned up.

---

### 🟡 P2-6 · `taxonomy_retrieval.py:101-135` — Three Serial Cypher Queries in Single Session

**File**: [`taxonomy_retrieval.py:101`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L101)

Three separate Cypher queries run sequentially in `retrieve_graph()`. Each incurs a network round-trip to Neo4j. These could be batched into a single `CALL { ... } UNION` query or run via `session.run()` concurrently using async Neo4j driver.

---

### 🟡 P2-7 · `taxonomy_retrieval.py:402` — Badge Hardcodes "SEBI TAXONOMY" Label

**File**: [`taxonomy_retrieval.py:402`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L402)

```python
{"label": "Intent: SEBI TAXONOMY", "desc": "Domain: sebi_regulation", ...}
```
This hardcoded string appears regardless of the actual `domain_intent` value. When a user queries about ESG, the badge shows "SEBI TAXONOMY" — factually wrong and misleading in demos.

**Fix**: `{"label": f"Intent: {domain_intent.upper()}", "desc": f"Domain: {domain_intent}"}`

---

### 🟡 P2-8 · `retrieval.py:236-238` — Dynamic Imports in Hot Path

**File**: [`retrieval.py:236`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L236)

```python
import pii_scrub
import language_detector
import compliance_guardrails
```
These are inside `hybrid_graphrag()`, the hot path called on every query. Python caches module imports after the first call (no re-execution), but the lookup overhead and the fact these are inside a function is an anti-pattern. Move to top-level imports.

---

### 🟡 P2-9 · `text_to_cypher.py:82-83` — Schema Context Truncated at 30 Labels

**File**: [`text_to_cypher.py:82`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/text_to_cypher.py#L82)

`", ".join(entity_labels[:30])` arbitrarily caps schema context. At 50 documents with 6 domain types, the graph schema will have more than 30 distinct entity label types. The LLM generating Cypher won't know about labels beyond index 30 and will hallucinate or fail.

---

### 🟡 P2-10 · `faiss_store.py:113-131` — FastEmbed Uses Different Model (`bge-small`) than FAISS Index (`all-MiniLM`)

**File**: [`faiss_store.py:113-131`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py#L113)

The FAISS index is built with `all-MiniLM-L6-v2` (384 dimensions). If `HAS_FASTEMBED=True`, the embedder switches to `BAAI/bge-small-en-v1.5` (also 384 dimensions but **different vector space**). Queries embedded with FastEmbed would be compared against an index built with all-MiniLM — producing semantically incoherent cosine similarities. The FAISS index records `model=EMBED_MODEL_NAME` in meta.json, but there's no runtime check to verify the loaded embedder matches the stored model.

---

### 🟡 P2-11 · `retrieval.py:347` — Unused `t2 = time.perf_counter()`

**File**: [`retrieval.py:347`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L347)

Timer `t2` is set but `enrichment_time = time.perf_counter() - t2` is never computed. This is the root cause of P1-2.

---

### 🟡 P2-12 · `language_detector.py` — Not Connected to `retrieval.py` Normalization

**File**: [`language_detector.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/language_detector.py)

`detect_query_language()` returns a `normalized_query` after Hinglish term substitution. `retrieval.py:244` calls this and assigns `lang_info`, but `lang_info["normalized_query"]` is never used — the original `query_for_retrieval` remains untouched. Hindi/Hinglish query normalization is a dead code path.

---

### 🟡 P2-13 · `compliance_guardrails.py` — Output Guard Not Applied in Taxonomy Path

**File**: [`taxonomy_retrieval.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py)

`retrieval.py:404` calls `compliance_guardrails.validate_llm_output()` on the final LLM answer. The taxonomy path (`taxonomy_retrieval.py`) skips this check entirely — answers from the Compare tab are not compliance-validated.

---

### 🟡 P2-14 · `pii_scrub.py` — No Metrics Exposed to Audit Log from Taxonomy Path

`retrieval.py:241` calls `pii_scrub.scrub_text_with_metrics()` and logs `pii_count/pii_types`. `taxonomy_retrieval.py` calls nothing from `pii_scrub` — PII scrubbing and audit for the Compare tab is missing.

---

### 🟡 P2-15 · `flashrank_reranker.py` — `flashrank` Not in `requirements.txt`

`flashrank_reranker.py` is imported and used in `retrieval.py:317`. `flashrank` is not listed in `requirements.txt`. Any fresh environment install will silently fall back to heuristic score sorting, reducing retrieval precision without any log warning.

---

### 🟡 P2-16 · `language_detector.py:90` — Hinglish Detection Triggers on Financial Terms

**File**: [`language_detector.py:90`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/language_detector.py#L90)

`HINGLISH_KEYWORDS` includes `"fund"` and `"rule"` — common English financial terms. Any English query containing `"fund"` (e.g., "Compare HDFC fund vs SBI fund") will be incorrectly flagged as `is_hinglish=True`. This triggers the Hinglish normalization path, which may substitute terms unnecessarily.

---

## Part 4: LOW SEVERITY (P3)

---

### 🔵 P3-1 · `ner_pipeline.py` — GLiNER Not Using Batch Prediction

GLiNER's `predict_entities()` is called per-chunk sequentially during indexing. The GLiNER API supports batch prediction (`model.predict_entities_batch(texts, labels)`), which would reduce indexing time by 3–5× for large documents.

---

### 🔵 P3-2 · `entity_resolver.py:14-15` — Unused `Optional`, `Any` Imports

`from typing import Optional` — `Optional` is never used in type hints in `entity_resolver.py`.

---

### 🔵 P3-3 · `taxonomy_retrieval.py:131` — Misleading Variable Name `res1b`

`res1b` appears to be a copy-paste remnant (`res`, `res_me`, `res2` are the pattern). Rename for clarity.

---

### 🔵 P3-4 · `export_neo4j_dump.py:142` — `driver.close()` at Script End

This is correct for a script (closes at script termination), but is inconsistent with production module pattern where drivers are kept open. No runtime impact but creates confusion during code review.

---

### 🔵 P3-5 · `llm_text_client.py` — `HAS_LITELLM` Flag Not Used in `call_llm_streaming()`

`llm_text_client.py` defines `HAS_LITELLM` (line 17-25), checks it in `call_llm_with_usage` (line 131), but `call_llm_streaming()` calls `litellm.completion()` directly without checking `HAS_LITELLM`. If litellm fails to import, streaming crashes with `NameError`.

---

### 🔵 P3-6 · `config.py:86` — `ENABLE_LANGDETECT` Flag Defined but Never Checked

`config.py:86` defines `ENABLE_LANGDETECT = ...` but `language_detector.py` doesn't read it — it uses its own `HAS_LANGDETECT` import-time check. The config flag is dead.

---

### 🔵 P3-7 · `.env` — API Keys in Plain Text File

The `.env` file is present in the source directory. While `.gitignore` should exclude it, it is loaded at startup with no validation that keys are non-empty before first use — silent failures occur when keys are absent.

---

## Part 5: CROSS-MODULE ARCHITECTURE GAPS

---

### GAP-1 · Dual Pipeline Inconsistency (Chat vs Compare Tab)

| Feature | `retrieval.py` (Chat) | `taxonomy_retrieval.py` (Compare) |
|---|---|---|
| `context_engineering.build_prompt()` | ✅ Used | ❌ Manual string |
| `pii_scrub` | ✅ Applied | ❌ Not applied |
| `compliance_guardrails` (output) | ✅ Applied | ❌ Not applied |
| `language_detector` normalization | ✅ Called (but result unused) | ❌ Not called |
| `flashrank_reranker` | ✅ Applied | ❌ Not applied |
| `intent_cache` lookup/store | ✅ Applied | ⚠️ classify only, no lookup/store |

**Impact**: Users get different quality, safety, and token efficiency depending on which tab they use.

---

### GAP-2 · `language_detector` Normalization Never Reaches Graph/Vector Retrieval

`retrieval.py:244-248` calls `detect_query_language()` and stores `lang_info`, but `query_for_retrieval` is never replaced with `lang_info["normalized_query"]`. Hinglish queries like "kaunsa fund accha hai?" are sent to Neo4j/FAISS as-is, producing zero matches instead of the normalized "which fund best performing?"

---

### GAP-3 · `intent_cache` Not Wired for Lookup/Store in Taxonomy Path

`taxonomy_retrieval.py:285` calls `intent_cache.classify_domain_intent(query)` for domain classification only. It never calls `cache.lookup()` or `cache.store()`. Repeated queries via the Compare tab never benefit from caching — only Chat tab queries are cached.

---

### GAP-4 · No Index Rebuild Notification to Cache

When `build_index.py` completes indexing a new document, `intent_cache.invalidate_domain()` is never called. Stale cached answers from the old corpus may be served even after a reindex. The `invalidate_domain()` method exists in `intent_cache.py` but nothing calls it.

---

### GAP-5 · `fastembed` Model Mismatch with FAISS Index

As documented in P2-10, `faiss_store.py` uses `all-MiniLM-L6-v2` for indexing but silently switches to `bge-small-en-v1.5` at query time if FastEmbed is installed. No model version is checked against `meta.json["model"]` before retrieval. This is a silent accuracy degradation.

---

### GAP-6 · `build_index.py` Uses `EMBED_MODEL_NAME` from `faiss_store` (Line 136) — Now Works

✅ `EMBED_MODEL_NAME = "all-MiniLM-L6-v2"` is correctly defined in `faiss_store.py:111`. **Previously reported as P0 — now resolved.**

---

## Full Issue Registry

| ID | Severity | File | Description |
|---|---|---|---|
| P0-1 | 🔴 Critical | `intent_cache.py:122` | Asymmetric date-entity guard → wrong cached answers |
| P0-2 | 🔴 Critical | `intent_cache.py:124` | Cached vectors re-normalized per lookup iteration |
| P0-3 | 🔴 Critical | `ner_pipeline.py:274` | Cache dict mutation → corrupted NER state |
| P0-4 | 🔴 Critical | `taxonomy_retrieval.py:391` | `vec_time_ms` NameError crashes Compare tab |
| P0-5 | 🔴 Critical | `taxonomy_retrieval.py:74` | `_taxonomy_driver.close()` destroys singleton |
| P0-6 | 🔴 Critical | `context_engineering.py:111` | KeyError on missing chunk fields |
| P0-7 | 🔴 Critical | `graph_store.py:214` | `matched_by` set wrong → incorrect vector bypass |
| P1-1 | 🟠 High | `entity_resolver.py:31` | Unbounded `_embedding_cache` → OOM |
| P1-2 | 🟠 High | `retrieval.py:488` | `enrichment_time` never defined → telemetry broken |
| P1-3 | 🟠 High | `context_engineering.py:28` | Token budget fractions don't sum to 1.0 |
| P1-4 | 🟠 High | `ner_pipeline.py:200` | Hardcoded ESG domain trigger breaks domain routing |
| P1-5 | 🟠 High | `text_to_cypher.py:91` | Fragile `NO_QUERY` exact-match check |
| P1-6 | 🟠 High | `retrieval.py:322` | `h["product_name"]` KeyError on unkeyed chunks |
| P1-7 | 🟠 High | `taxonomy_retrieval.py:305` | History turns hardcoded to ESG |
| P1-8 | 🟠 High | `requirements.txt` | Missing `litellm`, `httpx[http2]`, `flashrank`, `langdetect` |
| P1-9 | 🟠 High | `graph_store.py:283` | Cypher guard rejects valid `CALL {}` subqueries |
| P1-10 | 🟠 High | `taxonomy_retrieval.py` | Not using `context_engineering.build_prompt()` |
| P1-11 | 🟠 High | `claude_vision_client.py` | Bypasses LiteLLM — locked to Anthropic |
| P2-1 | 🟡 Med | `query_classifier.py:18` | `LOOKUP_PATTERNS` too narrow |
| P2-2 | 🟡 Med | `query_classifier.py:49` | LLM response not structurally enforced |
| P2-3 | 🟡 Med | `context_engineering.py:23` | Deduplication threshold too high (no-op) |
| P2-4 | 🟡 Med | `ner_pipeline.py:58,113` | `_query_ner_cache` defined twice |
| P2-5 | 🟡 Med | `ner_pipeline.py:12` | `import json` unused |
| P2-6 | 🟡 Med | `taxonomy_retrieval.py:101` | Three serial Cypher queries per graph lookup |
| P2-7 | 🟡 Med | `taxonomy_retrieval.py:402` | Intent badge hardcodes "SEBI TAXONOMY" |
| P2-8 | 🟡 Med | `retrieval.py:236` | Dynamic imports inside hot path |
| P2-9 | 🟡 Med | `text_to_cypher.py:82` | Schema context capped at 30 labels |
| P2-10 | 🟡 Med | `faiss_store.py:113` | FastEmbed uses different model than FAISS index |
| P2-11 | 🟡 Med | `retrieval.py:347` | `t2` assigned but `enrichment_time` never computed |
| P2-12 | 🟡 Med | `language_detector.py` | `normalized_query` result never used |
| P2-13 | 🟡 Med | `taxonomy_retrieval.py` | Output compliance guard not applied |
| P2-14 | 🟡 Med | `taxonomy_retrieval.py` | PII scrub not applied |
| P2-15 | 🟡 Med | `requirements.txt` | `flashrank` not listed |
| P2-16 | 🟡 Med | `language_detector.py:90` | "fund"/"rule" trigger false Hinglish detection |
| P3-1 | 🔵 Low | `ner_pipeline.py` | GLiNER not using batch prediction API |
| P3-2 | 🔵 Low | `entity_resolver.py:14` | Unused `Optional` import |
| P3-3 | 🔵 Low | `taxonomy_retrieval.py:131` | Misleading `res1b` variable name |
| P3-4 | 🔵 Low | `export_neo4j_dump.py:142` | `driver.close()` inconsistent pattern |
| P3-5 | 🔵 Low | `llm_text_client.py` | `call_llm_streaming()` skips `HAS_LITELLM` check |
| P3-6 | 🔵 Low | `config.py:86` | `ENABLE_LANGDETECT` flag defined but never checked |
| P3-7 | 🔵 Low | `.env` | API key validation absent at startup |
| GAP-1 | 🟠 High | Architecture | Chat vs Compare tab pipeline feature inconsistency |
| GAP-2 | 🟠 High | Architecture | Language normalization dead code path |
| GAP-3 | 🟠 High | Architecture | `intent_cache` lookup/store missing from taxonomy path |
| GAP-4 | 🟡 Med | Architecture | No cache invalidation on reindex |
| GAP-5 | 🟡 Med | Architecture | FastEmbed/all-MiniLM model mismatch |
| GAP-6 | ✅ Resolved | `faiss_store.py` | `EMBED_MODEL_NAME` now defined correctly |
| P2-17 | 🟡 Med | `faiss_store.py:125-148` | FastEmbed `_fastembed_instance` initialized but **never returned** — dead code |
| P2-18 | 🟡 Med | `faiss_store.py:633` | `gc.collect()` inside embedding batch loop — triggers full GC per 32 texts |
| P2-19 | 🟡 Med | `faiss_store.py:764` | FAISS queried for exact `top_k` before deduplication — can return <`top_k` parents |
| P2-20 | 🟡 Med | `compliance_guardrails.py:100` | Regex `\b` after optional `%` fails — percentage values silently dropped |
| P2-21 | 🟡 Med | `compliance_guardrails.py:11` | `HAS_GUARDRAILS_AI` defined but never used — dead flag |
| P2-22 | 🟡 Med | `requirements.txt:1-3` | Comment says "no torch/faiss/gliner" but file includes all three — contradictory |
| P2-23 | 🟡 Med | `llm_text_client.py:66` | `_resolve_model_and_fallbacks` prepends `groq/` to any model_id unconditionally — breaks OpenAI/Gemini routing |
| P3-8 | 🔵 Low | `app.py:157` | `compliance_note` and `confidence` both assigned `confidence_label` — copy-paste bug |
| P3-9 | 🔵 Low | `app.py:317` | `is_running=False` not in `finally` — UI can lock on exception |
| P3-10 | 🔵 Low | `app.py:257` | `active_tab` session state key initialized but never used |
| P3-11 | 🔵 Low | `analytics_view.py:170` | `store` parameter accepted but always passed `None` — dead parameter |
| P3-12 | 🔵 Low | `compare_view.py:140` | `entity_summary` iterated without `None` guard — `TypeError` if API omits field |
| P3-13 | 🔵 Low | `build_index.py:112` | No empty-children guard — `vecs.shape[1]` crashes on zero-text documents |

---

## Recommended Fix Order

```
Week 1 — P0 Critical (7 fixes, ~4 hours):
  ├── P0-1: Fix asymmetric date-entity cache guard
  ├── P0-2: Pre-normalize vectors in cache store()
  ├── P0-3: Copy entity dicts before mutation in NER pipeline  
  ├── P0-4: Add vec_time_ms=0.0 after parallel block
  ├── P0-5: Remove _taxonomy_driver.close()
  ├── P0-6: Use .get() for chunk fields in context_engineering
  └── P0-7: Track matched_by path correctly in graph_store

Week 1 — P1 High (11 fixes, ~8 hours):
  ├── P1-1: Add LRU eviction to _embedding_cache
  ├── P1-2+P2-11: Add enrichment_time timing capture
  ├── P1-4: Remove hardcoded ESG trigger from ner_pipeline
  ├── P1-5: Fix NO_QUERY check to use 'in' not '=='
  ├── P1-6: Use .get() for product_name in retrieval.py
  ├── P1-7: Use config dict for history turns
  ├── P1-8: Add litellm, flashrank, langdetect, httpx[h2] to requirements.txt
  ├── P1-9: Narrow Cypher guard to exclude CALL {} subqueries
  ├── P1-10: Wire taxonomy path through context_engineering.build_prompt()
  ├── GAP-1: Apply pii_scrub + compliance_guardrails to taxonomy path
  └── GAP-3: Wire intent_cache lookup/store into taxonomy_retrieval

Week 2 — P2 Medium (15 fixes, ~6 hours):
  ├── P2-7: Fix hardcoded SEBI TAXONOMY badge to use domain_intent
  ├── P2-10: Add model mismatch check (FastEmbed vs all-MiniLM)
  ├── GAP-2: Use lang_info["normalized_query"] in retrieval.py
  ├── GAP-4: Call intent_cache.invalidate_domain() from build_index.py
  ├── P2-7: Fix hardcoded SEBI TAXONOMY badge to use domain_intent
  ├── P2-10: Add model mismatch check (FastEmbed vs all-MiniLM)
  ├── P2-17: Fix FastEmbed dead code in _get_embedder()
  ├── P2-19: Query FAISS for top_k * 3 before parent deduplication
  ├── P2-20: Fix compliance_guardrails percentage regex
  ├── P2-23: Fix unconditional groq/ prefix in _resolve_model_and_fallbacks
  ├── GAP-2: Use lang_info["normalized_query"] in retrieval.py
  ├── GAP-4: Call intent_cache.invalidate_domain() from build_index.py
  └── ... remaining P2 items

Week 2 — P3 Low (13 fixes, ~2 hours):
  ├── P3-5: Add HAS_LITELLM check in call_llm_streaming()
  ├── P3-8: Fix app.py compliance_note copy-paste bug
  ├── P3-9: Wrap is_running=False in finally block
  ├── P3-12: Add None guard for entity_summary iteration
  ├── P3-13: Add empty-children guard in build_index.py
  └── ... remaining P3 items
```

---

## Summary Scorecard

| Category | Count | Status |
|---|---|---|
| P0 Critical bugs | 7 | 🔴 Fix immediately |
| P1 High severity | 11 | 🟠 Fix this week |
| P2 Medium severity | 23 | 🟡 Fix next week |
| P3 Low severity | 13 | 🔵 Backlog |
| Architecture gaps | 5 active + 1 resolved | |
| **Total issues** | **59** | |

> **Overall Assessment**: The system is **Beta-quality**. The 7 P0 bugs include 2 that produce wrong answers silently (P0-1: cache date-guard, P0-7: matched_by false signal), 2 that crash in production (P0-3: NER cache mutation, P0-4: NameError), and 1 that silently degrades reliability over time (P0-5: driver closed). Fix all P0s before any user-facing deployment.
