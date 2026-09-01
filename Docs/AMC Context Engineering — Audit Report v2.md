# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC Context Engineering — Audit Report v2
### Post-Fix Re-Evaluation · 2026-07-30

> **Method**: Every claim in `audit_report_fixed_29_07_26.md` verified line-by-line against current source.  
> **Scope**: All 7 fixes (F1–F7) + new issues introduced during patching.

---

## F1–F7 Verification Matrix

| Fix | Claim | Code Status | Verdict |
|---|---|---|---|
| **F1** Token Budget 1200→3600 | `context_engineering.py:34` | `DEFAULT_TOKEN_BUDGET = 3600` ✅ | **Applied** |
| **F1b** Guaranteed top-2 chunks | `context_engineering.py:70` | `if used + cost > vector_budget and idx >= 2` ✅ | **Applied** |
| **F2** Output cap 260→512/768 | `context_engineering.py:90` | `max_output_tokens = 512 if not has_structured else 768` ✅ | **Applied** |
| **F3** GLiNER bypass fix | `ner_pipeline.py:143` | `if not ents or len(text) <= 500 or "esg" in text.lower() or "climate" in text.lower()` ✅ | **Applied** |
| **F3b** ESG GLiNER labels | `config.py:77–79` | `"ESG metric", "sustainability initiative", "climate change adaptation", "carbon emission", "BRSR indicator"` ✅ | **Applied** |
| **F4** Driver singleton | `taxonomy_retrieval.py:57–67` | `_taxonomy_driver` singleton + `_get_taxonomy_driver()` ✅ | **Applied but broken** ⚠️ |
| **F5** Cosine floor 0.45 | `faiss_store.py:737–738` | `if float(score) < 0.45: continue` ✅ | **Applied** |
| **F6** Single-pass embedding | `taxonomy_retrieval.py:269–281` | `query_vec_np` computed once, passed to both retrievers ✅ | **Applied** |
| **F7** Path 3 disabled | `graph_store.py:199–202` | `if not edges: pass` ✅ | **Applied** |

---

## 🔴 SECTION 1: Critical Bugs Introduced During Patching

### Bug 1 — `EMBED_MODEL_NAME` is Undefined → `NameError` on Next Index Build
**File**: [`faiss_store.py:683`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py#L683)  
**Severity**: 🔴 CRITICAL

```python
# Line 683 — in build_faiss_index_for_pdf():
"model": EMBED_MODEL_NAME,   # ← NameError: name 'EMBED_MODEL_NAME' is not defined
```

The fix for the metadata mismatch (audit issue from v1) replaced the hardcoded string `"paraphrase-multilingual-MiniLM-L12-v2"` with a constant `EMBED_MODEL_NAME` — but this constant is **never defined anywhere** in `faiss_store.py`. The loader code at lines 119/125 still contains the correct model string (`"sentence-transformers/all-MiniLM-L6-v2"`) but it's hardcoded inside the function, not assigned to a module-level constant.

**Impact**: The next time `build_faiss_index_for_pdf()` runs (e.g., rebuilding the 50-doc index), it will **crash with a NameError on line 683**. All existing cached indexes still work; only new index builds are broken.

**Fix** (2 lines — add above `_get_embedder()`):
```python
# Add at module level, near the top of faiss_store.py
EMBED_MODEL_ID   = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"   # short name stored in meta.json
```
And update `_get_embedder()` to use `EMBED_MODEL_ID` instead of the hardcoded string.

---

### Bug 2 — `driver.close()` Defeats the Singleton (F4 Partially Broken)
**File**: [`taxonomy_retrieval.py:158`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L158)  
**Severity**: 🔴 HIGH

The singleton pattern was correctly created:
```python
_taxonomy_driver = None  # L57

def _get_taxonomy_driver():           # L59
    global _taxonomy_driver
    if _taxonomy_driver is None:
        ...create driver...
    return _taxonomy_driver           # returns singleton ✅
```

But inside `retrieve_graph()`:
```python
    except Exception as exc:
        print(...)
    return graph_context

# ← LOOK AT LINE 158:
driver.close()    # ← CLOSES the singleton after every successful call!
```

**Sequence of events**:
1. Call 1: `_get_taxonomy_driver()` → creates driver, stores in `_taxonomy_driver`
2. `retrieve_graph()` uses it successfully
3. `driver.close()` → **closes the pooled connection**
4. Call 2: `_get_taxonomy_driver()` → `_taxonomy_driver is not None` → returns the **closed driver**
5. Next `driver.session()` call → `ServiceUnavailable` or silent failure

**Net effect**: F4 saves the ~120ms on the very first call after startup, then breaks graph connectivity from the second query onward.

**Fix** (delete 1 line — remove `driver.close()` at line 158):
```python
    except Exception as exc:
        print(f"  [taxonomy] Graph DB offline...", flush=True)
    return graph_context
    # driver.close() ← DELETE THIS LINE
```
The driver lifecycle is now owned by the module. It will be GC'd on process exit.

---

### Bug 3 — `context_engineering.py` is Dead Code for the Main RAG Path
**File**: [`retrieval.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py) (no import of `context_engineering`)  
**Severity**: 🔴 HIGH

**Critical finding**: `context_engineering.py` is **never imported by any other module** in the codebase. A full scan confirms zero imports:

```
Scan result: context_engineering imports in all .py files → 0 results
```

The `build_prompt()` function (which contains the F1 budget logic and F2 output cap) is defined in `context_engineering.py` but **`retrieval.py` builds its prompt inline** at lines 315–327 without calling `build_prompt()`. The inline prompt has no token budget logic at all — it passes the full `vector_context` string directly to the LLM:

```python
# retrieval.py:315–327 — inline prompt, no budget enforcement
prompt = f"""Sources below are ranked by reliability...
{extra_sections}{graph_section}
DOCUMENT PROSE:
{vector_context}

QUESTION: {query}

ANSWER:"""
```

**Impact**: For the main Streamlit chat path (`hybrid_graphrag()` in `retrieval.py`):
- F1 (3600 char budget) → **NOT ACTIVE** — prompt uses all vector context without a budget limit
- F2 (512/768 output cap) → **NOT ACTIVE** — `call_llm_with_usage()` defaults to `max_tokens=4096`
- The only path where F1/F2 work is if something explicitly calls `context_engineering.build_prompt()` — which nothing does

**Fix**: Wire `context_engineering` into `retrieval.py`:
```python
# retrieval.py — add import at top
import context_engineering

# In hybrid_graphrag(), replace the inline prompt building (lines 315-327) with:
prompt, max_output_tokens = context_engineering.build_prompt(
    query=query,
    verified_facts=verified_facts,
    comparison_blocks=comparison_blocks,
    top_edges=top_edges,
    hits=effective_hits,
    query_type=query_type,
    trust_verified_facts=trust_verified_facts,
)

# Then pass max_output_tokens to the LLM call:
answer, usage = llm_text_client.call_llm_with_usage(
    prompt, model_id=config.CLAUDE_MODEL_LIGHT, max_tokens=max_output_tokens
)
```

---

### Bug 4 — NER Query Cache Key Collision Risk
**File**: [`ner_pipeline.py:136–158`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L136)  
**Severity**: 🟡 MEDIUM

```python
_query_ner_cache: Dict[str, List[Dict[str, Any]]] = {}   # L58

def run_layers_ab(text: str):
    if text in _query_ner_cache:          # L136 — cache lookup
        return _query_ner_cache[text]

    ents = layer_a_rule_ner(text)
    if not ents or len(text) <= 500 or "esg" in ...:
        ...
    ...
    if len(text) <= 500:                  # L157 — cache WRITE (only for short texts)
        _query_ner_cache[text] = deduped
    return deduped
```

**Issue**: The cache is read for ALL texts (line 136) but only written for texts with `len <= 500` (line 157). This is correct for query-level caching. However, `run_layers_ab()` is also called for **document chunks during indexing** (`run_full_ner_for_chunk_set()` at line 211). Chunk texts are usually 200–250 chars, so they will be cached.

If two chunks from different documents happen to have identical text (e.g., a boilerplate header like `"Management Discussion and Analysis"`), the cache will return entities tagged with the first document's `child_id`/`parent_id` for the second document's chunk — corrupting entity provenance.

**Fix**: Use the cache only for query-path calls. Either:
1. Add a `is_query=False` parameter and only cache when `is_query=True`
2. Keep a separate `_chunk_ner_cache` with a size limit (LRU of 1000 entries)

---

## ⚠️ SECTION 2: Remaining Open Issues (Not Yet Fixed)

### Open 2.1 — `retrieval.py` Secondary Graph Re-Query Still Fires
**File**: [`retrieval.py:220–226`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L220)  
**Severity**: 🟡 MEDIUM

```python
if not graph_result["edges"] and hits:     # ← Re-query after vector search
    product_names = {h["product_name"] for h in hits}
    graph_result = graph_store.get_subgraph_for_query(
        query, product_names=product_names, hops=1, limit=15,
        query_entities=query_entities)
```

This second graph call runs even when vector bypass is active (`vector_bypassed=True`). When graph is strong, vector search is bypassed (no `hits`), so this particular branch won't fire. But when graph is weak AND vector returns hits, this fires a second graph round-trip using product names from vector results. Since Path 3 is now disabled (F7), this secondary query may return empty too — wasting ~80ms on a guaranteed empty result for ESG/climate queries.

**Fix**: Add `not vector_bypassed` to the condition:
```python
if not graph_result["edges"] and hits and not vector_bypassed:
```

---

### Open 2.2 — `_graph_context_to_text()` Still Verbose (Micro-Notation Not Done)
**File**: [`taxonomy_retrieval.py:164–204`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L164)  
**Severity**: 🟡 MEDIUM

The verbose format remains unchanged. Each `SchemeClass` entry still consumes ~35 tokens. With 5 matched scheme classes + 2 regimes + 3 mutual exclusion rules, graph context is ~450 tokens on the taxonomy/compare path.

The compressed micro-notation proposed in v1 audit (`[2026] SC:IndexFund(open,track_idx)`) would reduce this to ~140 tokens — a **68% reduction** directly translatable to latency and cost savings.

---

### Open 2.3 — `hidden_tokens` Not Exposed in Telemetry Breakdown
**File**: [`retrieval.py:390–407`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L390)  
**Severity**: 🟡 LOW

The Cypher generation LLM call accumulates into `hidden_tokens`, which is added to `total_tokens` but is **not broken out** in `telemetry_breakdown`. The UI shows `tokens_input + tokens_output ≠ tokens_total` without explanation. Add `"tokens_hidden_cypher": hidden_tokens` to the telemetry dict.

---

### Open 2.4 — Query Audit Log: One File Per Query (Log Dir Bloat)
**File**: [`retrieval.py:162–168`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L162)

Still creates one JSONL file per query. For a team running 100 queries/day against 50 documents, this generates 3,000+ files/month in `logs/`. Switch to a single appending `query_audit.jsonl`:
```python
log_file = config.LOG_DIR / "query_audit.jsonl"
with open(log_file, "a", encoding="utf-8") as f:  # ← "a" not "w"
    f.write(json.dumps(audit_data) + "\n")
```

---

### Open 2.5 — RRF Fusion Still Not Implemented (Taxonomy Path)
**File**: [`taxonomy_retrieval.py:296–300`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L296)

Graph and vector results still assembled as two independent unranked sections in the prompt. For the Compare View (taxonomy path), this remains a source of imprecision. Lower priority now that the main ESG query path is through `retrieval.py`, not the taxonomy path.

---

### Open 2.6 — 50-Doc Expansion Prerequisites (Still Pending)
These architectural items from the original plan remain unstarted:
- ❌ `IndexIVFFlat` upgrade (critical above 50K vectors)
- ❌ Structural/clause-aware chunking (SEBI Master Circulars)
- ❌ Semantic query cache (`SemanticQueryCache` class)
- ❌ ESG node types in graph schema (`ESGMetric`, `CarbonEmission`)
- ❌ Cross-doc entity resolution via embedding (currently only exact string match)
- ❌ Query namespace router (prevents cross-category embedding contamination)

---

## 📊 Updated Fix Status Dashboard

| Fix | Status | Effective? | Action Required |
|---|---|---|---|
| F1 Token Budget (3600) | ✅ Code changed | ❌ Dead code — not imported | Wire `context_engineering` into `retrieval.py` |
| F2 Output Cap (512/768) | ✅ Code changed | ❌ Dead code — not imported | Same as F1 |
| F3 GLiNER bypass corrected | ✅ Applied | ✅ Effective | None |
| F3b ESG GLiNER labels | ✅ Applied | ✅ Effective | None |
| F4 Driver singleton | ✅ Created | ⚠️ Broken by `driver.close()` | Remove `driver.close()` at line 158 |
| F5 Cosine floor 0.45 | ✅ Applied | ✅ Effective | None |
| F6 Single-pass embedding | ✅ Applied | ✅ Effective | None |
| F7 Path 3 disabled | ✅ Applied | ✅ Effective | None |
| Meta model name fix | ⚠️ Partial | ❌ `EMBED_MODEL_NAME` undefined → NameError | Define constant at module level |

---

## 🔧 Prioritized Remediation Checklist

### P0 — Fix Now (Before Any Index Rebuild or 50-Doc Expansion)

**[P0-A]** Add `EMBED_MODEL_NAME` constant in [`faiss_store.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/faiss_store.py):
```python
# Add near line 65, after the os.environ.setdefault calls
EMBED_MODEL_ID   = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
```
Then replace the hardcoded strings in `_get_embedder()` with `EMBED_MODEL_ID`.

**[P0-B]** Remove `driver.close()` from [`taxonomy_retrieval.py:158`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L158):
```python
# DELETE this line:
driver.close()
```

**[P0-C]** Wire `context_engineering` into [`retrieval.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py):
```python
# Add to imports (top of file):
import context_engineering

# In hybrid_graphrag(), replace inline prompt block (lines ~315-327) with:
prompt, max_output_tokens = context_engineering.build_prompt(
    query=query,
    verified_facts=verified_facts,
    comparison_blocks=comparison_blocks,
    top_edges=top_edges,
    hits=effective_hits,
    query_type=query_type,
    trust_verified_facts=trust_verified_facts,
)
answer, usage = llm_text_client.call_llm_with_usage(
    prompt, model_id=config.CLAUDE_MODEL_LIGHT, max_tokens=max_output_tokens
)
```

---

### P1 — Fix This Week

**[P1-A]** Fix secondary graph re-query condition in [`retrieval.py:220`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L220):
```python
if not graph_result["edges"] and hits and not vector_bypassed:
```

**[P1-B]** Fix NER cache key collision in [`ner_pipeline.py:136`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L136):
Add an `is_query` parameter to `run_layers_ab()`, or limit cache to an LRU with 500 entry cap.

**[P1-C]** Switch audit log to append mode in [`retrieval.py:165`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L165):
```python
with open(log_file, "a", encoding="utf-8") as f:
    f.write(json.dumps(audit_data, ensure_ascii=False) + "\n")
```
Use a single `query_audit.jsonl` with date suffix for rotation.

**[P1-D]** Expose `hidden_tokens` in telemetry breakdown in [`retrieval.py:390`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/retrieval.py#L390):
```python
"tokens_hidden_cypher": hidden_tokens,
"tokens_input": usage["input_tokens"],   # main LLM call only
```

---

### P2 — Architecture (50-Doc Expansion Gating Items)

| Item | File | Complexity | Impact |
|---|---|---|---|
| Context micro-notation | `taxonomy_retrieval.py:_graph_context_to_text()` | Low | -68% token cost on compare path |
| `IndexIVFFlat` upgrade | `faiss_store.py:662` | Medium | 8–10× search speedup at 50K+ vectors |
| Semantic cache class | New: `semantic_cache.py` | Medium | 20–30% query cost elimination |
| ESG graph schema | `graph_store.py` + Neo4j | High | Graph-augmented ESG answers |
| Cross-doc entity resolution | `graph_store.py:resolve_unresolved_entities()` | Medium | Deduplication across 50 docs |
| Namespace router | New: `namespace_router.py` | Low | Prevents category embedding contamination |

---

## ESG Query — Updated Root Cause Status

| Root Cause | Previous Status | After F1–F7 | After P0 Fixes |
|---|---|---|---|
| GLiNER skips "ESG"/"climate" | 🔴 Bug active | ✅ Fixed (F3) | ✅ Fixed |
| Token budget drops all chunks | 🔴 Bug active | ⚠️ Fixed in dead code | ✅ Fixed (after P0-C) |
| Output truncated at 260 tokens | 🔴 Bug active | ⚠️ Fixed in dead code | ✅ Fixed (after P0-C) |
| Graph driver closes per call | 🟡 Not yet introduced | 🔴 New bug (F4 broken) | ✅ Fixed (after P0-B) |

> [!CAUTION]
> **The ESG query is still not fully fixed.** F3 (GLiNER labels) works, but F1 and F2 (token budget + output cap) are in `context_engineering.py` which is never imported by `retrieval.py`. The ESG query will now extract the right entities via GLiNER, but the prompt context may still be over-trimmed and the output still capped at 4096 tokens (default) rather than 512/768. Apply **P0-C** to make F1+F2 live.

> [!IMPORTANT]
> **P0-A must be done before any index rebuild.** If you run `build_index.py` with 50 documents, it will crash at line 683 with `NameError: name 'EMBED_MODEL_NAME' is not defined`. This would waste all extraction time and Claude vision API calls.

> [!NOTE]
> **P0-B has a positive side effect**: Once `driver.close()` is removed, the taxonomy retrieval path gains proper connection pooling. Combined with F6 (single-pass embedding), each taxonomy/compare query saves ~300ms: ~120ms (no TCP handshake) + ~180ms (no second embedding call).
