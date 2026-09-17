# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC RAG System — Consolidated Implementation Plan
### Synthesis of: Audit Report v2 · Intent-Aware Architecture Plan · Latency Reduction Plan
### Target: Correct, fast (sub-5s / 1.5s TTFT), intent-routed retrieval — shipped without merge collisions

---

## 0. How to Read This Plan

Your three documents were written independently but **modify the same handful of files**, especially
`retrieval.py::hybrid_graphrag()`, `ner_pipeline.py`, and `context_engineering.py`. Implemented in the order
they were written, they will collide: the Latency plan's `ThreadPoolExecutor` block, the Intent plan's cache
short-circuit, and the Audit's dead-code wiring fix all rewrite the same function body.

This plan does three things the source docs don't:

1. **Orders the work by dependency, not by document.** Some items are blocking prerequisites for others
   (e.g., the Audit's P0-C fix — wiring `context_engineering.py` in — must land *before* the Intent plan's
   prompt-template hooks mean anything, since those hooks live inside `build_prompt()`).
2. **Resolves the three-way collision on `hybrid_graphrag()`** by giving you one target implementation
   (§4) instead of three sequential patches to the same function.
3. **Flags redundancy and risk the individual docs didn't surface** — see §10.

---

## 1. Dependency Map

```
                         ┌─────────────────────────────┐
                         │ PHASE 1 — P0 Bug Fixes       │  ← blocking, do first
                         │ (Audit: EMBED_MODEL_NAME,    │
                         │  driver.close(), dead code)  │
                         └───────────────┬───────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              ▼                                                     ▼
┌───────────────────────────────┐                    ┌───────────────────────────────┐
│ PHASE 2 — Zero-risk latency   │                    │ PHASE 3 — NER cache            │
│ quick wins (Latency Phase A)  │                    │ consolidation (Audit P1-B +     │
│ independent of Phase 1        │                    │ Latency Track 1c, same file)   │
└───────────────┬───────────────┘                    └───────────────┬───────────────┘
              │                                                     │
              └──────────────────────────┬──────────────────────────┘
                                         ▼
                         ┌─────────────────────────────┐
                         │ PHASE 4 — GLiNER ONNX        │
                         │ quantization (Latency Ph. B) │
                         └───────────────┬───────────────┘
                                         ▼
                         ┌─────────────────────────────┐
                         │ PHASE 5 — Intent-aware cache  │  ← needs Phase 1 (build_prompt
                         │ + classification (Intent Ph1) │     live) + Phase 3/4 (stable NER)
                         └───────────────┬───────────────┘
                                         ▼
                         ┌─────────────────────────────┐
                         │ PHASE 6 — Unified parallel    │  ← rewrites hybrid_graphrag()
                         │ retrieval + streaming         │     ONE time, incorporating
                         │ (Latency Ph. C+D + Intent     │     Phases 2–5's hooks together
                         │  Hooks 1–4)                   │
                         └───────────────┬───────────────┘
                                         ▼
                         ┌─────────────────────────────┐
                         │ PHASE 7 — Remaining Intent    │
                         │ hooks (TTL, thresholds,       │
                         │ history compression,          │
                         │ confidence calibration)       │
                         └───────────────┬───────────────┘
                                         ▼
                         ┌─────────────────────────────┐
                         │ PHASE 8 — Architecture/       │
                         │ 50-doc expansion prerequisites│
                         └───────────────────────────────┘
```

**Why this order and not "P0 → P1 → P2 → Intent → Latency" (document order):** Latency Phase A (regex
classifier expansion, retry cap, HTTP/2 pool) touches `query_classifier.py` and `llm_text_client.py` —
files nothing else in Phase 1 touches — so it can run in parallel with Phase 1 if you have two people.
Everything downstream of Phase 5, however, is strictly serial, because Phase 6 has to merge three
different plans' edits to the *same function*.

---

## 2. File-Level Change Map

| File | Touched by | Phases | Notes |
|---|---|---|---|
| `faiss_store.py` | Audit (P0-A), Latency (5a) | 1, 8 | Constant fix must land before mmap change — both edit `_get_embedder()`/index loading region |
| `taxonomy_retrieval.py` | Audit (P0-B), Latency (2b, 5a) | 1, 6 | Driver-close bug must be fixed before parallelizing this path, or you'll parallelize a call that silently breaks on the 2nd invocation |
| `retrieval.py` | Audit (P0-C, P1-A, P1-C, P1-D), Intent (cache wiring, Hooks 1–9 call sites), Latency (2a, 3d, Track 6) | 1, 3, 5, 6, 7 | **Highest collision risk** — see §4 for the unified target |
| `ner_pipeline.py` | Audit (P1-B), Latency (1b–1d), Intent (Hook 1) | 3, 4, 6 | Two independent cache rewrites (Audit + Latency) must become one cache |
| `context_engineering.py` | Audit (P0-C makes it live), Intent (Hook 4 templates) | 1, 5 | Must be wired in (Phase 1) before templates are worth adding (Phase 5) |
| `config.py` | Intent (Hook 1 GLiNER labels), Audit (F3b, already applied) | 5 | — |
| `graph_store.py` | Audit (P1-A), Latency (Track 4, 4c) | 3, 6 | Index creation is independent; the re-query condition fix lands in `retrieval.py` not here |
| `llm_text_client.py` | Latency (3a, 3b, 3c) | 2, 6 | Streaming generator (3a) only becomes useful after Phase 6 shrinks retrieval latency |
| `chat_view.py` | Latency (3d) | 6 | Depends on `call_llm_streaming()` existing (Phase 6) |
| `query_classifier.py` | Latency (Track 6) | 2 | Independent, safe to do anytime |
| `intent_cache.py` | Intent (new file) | 5 | New file — no impact on existing code until wired in |
| `app.py` | Latency (5b warm-up, Track 4 index call) | 2, 4 | — |

---

## 3. Phased Plan

### Phase 0 — Pre-Flight (before touching anything)

1. Tag current `main` / take a branch snapshot — several phases below touch the same functions repeatedly.
2. Build a **golden-query eval set**: 15–20 real queries spanning each `query_type` × `domain_intent`
   combination (especially ESG and regulatory, since those are the ones the Audit says are still broken),
   with their current answers and source citations saved as a baseline. You have no automated way to detect
   a regression from P0-C (below) without this — it changes the prompt for *every* query in the app.
3. Add a feature-flag module (even a simple `config.py` dict of booleans) so each phase can be toggled off
   independently in production: `ENABLE_CONTEXT_BUDGET`, `ENABLE_INTENT_CACHE`, `ENABLE_PARALLEL_RETRIEVAL`,
   `ENABLE_STREAMING`, `ENABLE_ONNX_GLINER`. This is cheap insurance given how much of this plan touches the
   main query path.

---

### Phase 1 — P0 Critical Bug Fixes (Audit Report, blocking)

These are the only items in any of the three documents that are *active bugs*, not optimizations. Nothing
else should ship on top of a codebase where these are still broken — in particular, Phase 5/6 build directly
on top of P0-C.

**1a. `faiss_store.py` — define `EMBED_MODEL_NAME`** (Audit P0-A)
Add near the top of the file, before `_get_embedder()`:
```python
EMBED_MODEL_ID   = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
```
Replace the hardcoded model string inside `_get_embedder()` with `EMBED_MODEL_ID`. **Do this before any
index rebuild** — this is the one item in the whole plan with a hard "will crash" consequence if skipped.

**1b. `taxonomy_retrieval.py` — remove `driver.close()`** (Audit P0-B)
Delete line 158 (the `driver.close()` call inside `retrieve_graph()`'s success path). The singleton created
at `_get_taxonomy_driver()` should live for the process lifetime and be GC'd on exit.
*Side benefit confirmed by the audit*: combined with F6 (already applied), this saves ~300ms per taxonomy
query once fixed — factor this into Phase 6's latency estimates, it's not accounted for in the Latency doc's
table.

**1c. `retrieval.py` — wire `context_engineering.build_prompt()` in** (Audit P0-C)
```python
import context_engineering
# ...
prompt, max_output_tokens = context_engineering.build_prompt(
    query=query, verified_facts=verified_facts, comparison_blocks=comparison_blocks,
    top_edges=top_edges, hits=effective_hits, query_type=query_type,
    trust_verified_facts=trust_verified_facts,
)
answer, usage = llm_text_client.call_llm_with_usage(
    prompt, model_id=config.CLAUDE_MODEL_LIGHT, max_tokens=max_output_tokens,
)
```
This replaces the inline prompt at lines ~315–327. **This is the single highest-blast-radius change in the
entire plan** — it changes the prompt shape and output-length cap for every query the app serves. Run the
full golden-query set from Phase 0 before and after; specifically check that non-ESG queries (which were
working under the old unbudgeted prompt) don't regress from the new 3600-char/512–768-token limits.

**Gate before proceeding to Phase 2+:** golden-query answers still cite the right documents; ESG query
produces a non-empty, non-truncated answer.

---

### Phase 2 — Zero-Risk Latency Quick Wins (Latency Phase A)

Independent of Phase 1's files; safe to run in parallel with Phase 1 if resourcing allows. In order of
effort:

| Item | File | Change | Est. savings |
|---|---|---|---|
| Retry delay cap | `llm_text_client.py` | `wait = min(CLAUDE_RETRY_DELAY * 2**attempt, 10)`; `CLAUDE_MAX_RETRIES = 2` for query path (keep 3 for indexing) | up to −25s worst case |
| HTTP/2 keep-alive | `llm_text_client.py` | Pass `httpx.Client(http2=True, keepalive_expiry=30, ...)` to `anthropic.Anthropic()` constructor. Add `httpx[http2]` to `requirements.txt` | −200–400ms/call |
| Classifier `max_tokens=10` | `query_classifier.py` | Cap the fallback LLM classification call | −300ms |
| Expanded regex classifier | `query_classifier.py` | Add `OPEN_ENDED_PATTERNS` so ~85% of queries never reach the LLM classifier | −300–800ms on those queries |
| Neo4j indexes | Cypher, run once + `graph_store.create_indexes()` at startup | Both port-7687 and 7688 index sets from Latency §Track 4 | −70% graph latency (2.3–9.3s → 0.3–0.6s) |
| Warm-up on startup | `app.py` | `@st.cache_resource` wrapped `_warm_up()` pre-loading embedder + GLiNER + Neo4j indexes | −5–15s on first query only |

None of these change output content (only speed and classification robustness), so they don't need the
golden-query answer comparison — just a timing check.

---

### Phase 3 — NER Cache Consolidation (merges Audit P1-B + Latency Track 1c)

Your Audit and Latency documents propose **two different fixes to the same cache** without knowing about
each other:
- Audit (Bug 4 / P1-B): the cache is polluted because chunk-indexing calls and query calls share one dict —
  identical boilerplate text from two different documents corrupts entity provenance.
- Latency (Gap 7 / Track 1c): the cache is unbounded and needs LRU eviction + hit/miss telemetry.

Implementing Latency's version alone (as literally written) would add eviction but **leave the collision bug
in place** — you'd have a cache that's now correctly bounded, but still capable of returning document A's
entity tags for document B's identical boilerplate chunk. Implement this instead — one cache, both fixes:

```python
# ner_pipeline.py
_NER_CACHE_MAX = 2000
_query_ner_cache: dict[str, list] = {}   # query-path cache ONLY — never touched by indexing
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
        for k in list(_query_ner_cache.keys())[: _NER_CACHE_MAX // 10]:
            del _query_ner_cache[k]
    _query_ner_cache[text] = result

def get_ner_cache_stats() -> dict:
    total = _ner_cache_hits + _ner_cache_misses
    return {
        "hits": _ner_cache_hits, "misses": _ner_cache_misses,
        "hit_rate": round(_ner_cache_hits / max(total, 1), 3),
        "cache_size": len(_query_ner_cache),
    }

def run_layers_ab(text: str, skip_gliner: bool = False, is_query: bool = False) -> list:
    # Fix for Audit Bug 4: cache is scoped to is_query=True calls only.
    # Chunk-indexing calls (run_full_ner_for_chunk_set) must pass is_query=False,
    # so identical boilerplate across documents never shares a cache entry.
    if is_query:
        cached = _ner_cache_get(text)
        if cached is not None:
            return cached

    ents = layer_a_rule_ner(text)
    should_run_gliner = (
        not skip_gliner and (
            not ents or len(text) <= 500
            or "esg" in text.lower() or "climate" in text.lower()
        )
    )
    if should_run_gliner:
        try:
            ents += layer_b_gliner(text)
        except Exception as e:
            print(f"  [NER] GLiNER skipped: {e}", flush=True)

    result = _deduplicate(ents)
    if is_query and len(text) <= 500:
        _ner_cache_set(text, result)
    return result
```
Update every call site: query-path callers (inside `hybrid_graphrag()`) pass `is_query=True`;
`run_full_ner_for_chunk_set()` (indexing) passes `is_query=False` and is never cached (or, if you want
indexing speed too, give it a **separate** `_chunk_ner_cache` keyed by `(text, doc_id)` — not by text alone,
which is what caused the original bug).

**Also in this phase (independent, same file area):**
- **Audit P1-A**: fix the secondary graph re-query condition in `retrieval.py:220` — add `not vector_bypassed`:
  ```python
  if not graph_result["edges"] and hits and not vector_bypassed:
  ```
- **Audit P1-C**: switch the query audit log from one-file-per-query to a single appending
  `query_audit.jsonl` (`open(log_file, "a")`).
- **Audit P1-D**: add `"tokens_hidden_cypher": hidden_tokens` to the telemetry breakdown dict.
  Do this at the same time as Phase 7's Hook 8 (Intent audit fields) so the audit-log schema only changes
  once, not twice — see the consolidated schema in §4.

---

### Phase 4 — GLiNER ONNX Quantization (Latency Phase B)

This is the single highest-impact latency fix (GLiNER CPU inference is 65–85% of total latency per the
audit logs) and is largely self-contained. Sequenced after Phase 3 because both touch `_get_gliner()` and
the NER cache function signatures — doing Phase 3 first means you're not modifying cache logic and swapping
the model backend in the same diff.

1. **Offline, one-time**: run the export script (`scripts/export_gliner_onnx.py`) to produce
   `models/gliner_quantized.onnx` (~95MB, down from ~380MB fp32).
2. **`ner_pipeline.py`**: update `_get_gliner()` to prefer the ONNX path when the file exists, falling back
   to PyTorch otherwise (keep the fallback — don't hard-require ONNX, per the Risk Matrix in §7).
3. **`ner_pipeline.py`**: add the `skip_gliner` flag (already sketched in Phase 3's `run_layers_ab`) — set it
   `True` when `query_type == "direct_lookup"` and Layer A (regex/spaCy) already found ≥1 entity. This is a
   Latency-doc item (Gap 4) that's cheap to fold in here since you're already touching this function.
4. **`faiss_store.py` + `taxonomy_retrieval.py`**: switch `faiss.read_index()` calls to
   `faiss.read_index(path, faiss.IO_FLAG_MMAP)`. Guard for local-path-only (mmap doesn't work reliably on
   network drives — detect and fall back).

**Validation**: re-run the golden-query set — ONNX INT8 quantization can shift entity-extraction confidence
scores slightly; check that no previously-extracted entity silently drops below `GLINER_THRESHOLD` post-quantization,
especially for the ESG label set (F3b), since that's the whole reason F3/F3b were added.

---

### Phase 5 — Intent-Aware Cache + Classification (Intent Plan Phase 1)

**Prerequisite check**: Phase 1c (context_engineering wired in) must be done — the cache's stored answers,
and later the prompt templates in Phase 6, are meaningless if `build_prompt()` isn't actually on the request
path.

1. **New file** `intent_cache.py` — implement exactly as specified in the Intent plan: `DOMAIN_PATTERNS`,
   `CacheEntry` dataclass, `IntentAwareCache` with `lookup()`/`store()`/`_evict_global()`, module-level
   `get_cache()` singleton. This file has zero blast radius on its own — it isn't called from anywhere yet.
2. **`query_classifier.py` or a new call site**: add `classify_domain_intent(query)` — pure regex, no LLM,
   as specified.
3. **Do not wire the cache into `hybrid_graphrag()` yet.** Wire it in Phase 6, together with the parallel
   retrieval refactor, so `hybrid_graphrag()` is rewritten once, not twice (see §4 and the collision note
   in §0).
4. **Recommended addition not in either source doc**: run the cache in **shadow mode** first. Compute
   `domain_intent` and do the `cache.lookup()` call, log what *would* have happened (hit/miss, similarity
   score), but always execute the full pipeline and ignore the cached answer for the first 1–2 weeks of
   production traffic. This is a compliance-facing tool serving SEBI/ESG answers — validate the domain
   classifier's accuracy against real query traffic before letting it silently substitute cached answers.
   See §10 for why this matters more here than a typical cache rollout.

---

### Phase 6 — Unified Parallel Retrieval + Streaming (merges Latency Phase C/D + Intent Hooks 1–4)

This is where the three-way collision on `hybrid_graphrag()` actually gets resolved. Don't implement the
Latency doc's `ThreadPoolExecutor` patch and the Intent doc's cache-wrapper patch as two separate diffs —
write the target function once. See **§4 — Unified `hybrid_graphrag()`** for the full implementation.

Sub-tasks, all landing as one coherent change to `retrieval.py`:

- **Intent Hook 0**: cache short-circuit at the top of the function (embed query, classify `query_type` +
  `domain_intent`, `cache.lookup()` — return immediately on hit).
- **Intent Hook 1**: pass `domain_intent` into `run_layers_ab()` (Phase 3/4's NER function) so
  `layer_b_gliner()` uses `config.get_gliner_labels(domain_intent)` instead of the global label list.
  (Requires the `GLINER_LABELS_BY_DOMAIN` dict added to `config.py`.)
- **Intent Hooks 2 & 3**: `GRAPH_HOPS_BY_INTENT` / `GRAPH_LIMIT_BY_INTENT` / `VECTOR_TOPK_BY_INTENT` —
  computed from `query_type` right before the parallel block, then passed as arguments into the
  `ThreadPoolExecutor` submissions (Latency Track 2a).
- **Latency Track 2a**: graph traversal and vector retrieval run in the same `ThreadPoolExecutor(max_workers=2)`
  block, now parameterized by the intent-derived hops/limit/top_k above instead of hardcoded values.
- **Intent Hook 4**: `context_engineering.build_prompt()` (now live per Phase 1c) selects its template via
  `get_prompt_template(query_type, domain_intent)` — this means `PROMPT_TEMPLATES` and `get_prompt_template()`
  need to be added to `context_engineering.py` in this phase.
- **Latency Track 3a/3d**: `call_llm_streaming()` generator added to `llm_text_client.py`; `chat_view.py`
  switches to `st.write_stream()`. Keep the non-streaming path alive for the Compare tab (needs full text
  for table rendering, per the Latency doc's own note).
- **Intent Hook 0 (store side)**: on a successful non-cached answer, `cache.store(...)`.
- **Latency Gap 8 / Intent Hook 8**: audit-log schema gets its final consolidated shape here (see §4) —
  this absorbs Phase 3's P1-D (`tokens_hidden_cypher`) and P1-C (append mode) so the schema only changes once.

**Order within Phase 6**: implement Hooks 1–4 (intent routing) and Track 2a (parallelism) together first,
validate against the golden-query set, *then* add streaming (3a/3d) as a separate sub-commit — streaming is
a pure UX/transport change and easiest to bisect if something breaks when isolated from the routing logic
change.

---

### Phase 7 — Remaining Intent Hooks (5, 6, 7, 9)

These are additive and lower-risk once Phase 6 exists.

- **Hook 5** (already built into `intent_cache.py`'s `DOMAIN_TTL` in Phase 5 — nothing new to do here except
  confirm TTLs match your answer to Open Question 3 below).
- **Hook 6** — per-intent cache similarity thresholds (`CACHE_THRESHOLD_BY_INTENT`), replacing the single
  global 0.90 in `IntentAwareCache.lookup()`.
- **Hook 7** — `compress_history_for_intent()` with `HISTORY_TURNS_BY_INTENT`, wired into both
  `hybrid_graphrag_v2()` (taxonomy) and `retrieval.py`.
- **Hook 9** — `calibrate_confidence()` using `DOMAIN_GRAPH_COVERAGE`. **Read §10's note on this hook before
  shipping it** — it will downgrade ESG confidence to "medium" immediately after all the work in Phase 1–6
  to fix ESG accuracy, which is correct behavior but needs a UX explanation alongside it (a tooltip/badge
  reason string, which the Intent doc already includes: `"(limited graph coverage)"` — make sure that string
  actually renders in the UI, not just the internal label).

---

### Phase 8 — Architecture / 50-Doc Expansion Prerequisites

From Audit's Open 2.6, with one correction (see §10): **remove "Semantic query cache" from this list** — it's
delivered by Phase 5, not a separate P2 item.

| Item | Complexity | Impact | Depends on |
|---|---|---|---|
| Context micro-notation (`_graph_context_to_text()`) | Low | −68% token cost on compare path | none |
| `IndexIVFFlat` upgrade | Medium | 8–10× search speedup at 50K+ vectors | Phase 4's mmap change (test both together) |
| ESG graph schema (`ESGMetric`, `CarbonEmission` nodes) | High | Raises `DOMAIN_GRAPH_COVERAGE["esg_sustainability"]` from 0.15 — directly un-does the confidence downgrade from Phase 7's Hook 9 | Phase 7 (so you can measure the before/after confidence-label change) |
| Cross-doc entity resolution | Medium | Dedup across 50 docs | none |
| Namespace router | Low | Prevents cross-category embedding contamination | none |
| Structural/clause-aware chunking (SEBI circulars) | Medium | Better regulatory retrieval | none |

---

## 4. Unified Target: `hybrid_graphrag()` (End State After Phase 6)

This is the single function all three documents independently patch. Below is what it looks like after
every phase above has landed — use this as the actual target to write toward in Phase 6, rather than
layering three separate diffs.

```python
import concurrent.futures
import time
import context_engineering
import intent_cache as ic
import faiss_store as fs

def hybrid_graphrag(query: str, store, history: list[dict] | None = None) -> dict:
    t_start = time.perf_counter()

    # ── Embed + classify once (shared by cache lookup, NER routing, graph/vector) ──
    query_vec = fs._embed_texts([query])
    query_type = query_classifier.classify_query(query)          # Phase 2: regex-first, 0-50ms
    domain_intent = ic.IntentAwareCache.classify_domain_intent(query)

    # ── Phase 5/6: dual-gate cache short-circuit ──
    cache = ic.get_cache()
    cached = cache.lookup(query_vec, query_type, domain_intent)
    if cached is not None:
        return _build_cached_response(cached, query, time.perf_counter() - t_start)

    # ── Phase 3/4: NER with domain-routed GLiNER labels + direct_lookup skip ──
    query_entities = ner_pipeline.run_layers_ab(
        query, is_query=True,
        skip_gliner=(query_type == "direct_lookup"),
    )
    if query_type == "direct_lookup" and query_entities:
        query_entities = [e for e in query_entities if e.get("layer") == "A"]
    entity_texts = [e["text"] for e in query_entities]

    # ── Phase 6: intent-parameterized graph + vector, run in parallel ──
    hops = GRAPH_HOPS_BY_INTENT.get(query_type, 1)
    limit = GRAPH_LIMIT_BY_INTENT.get(query_type, 15)
    top_k = VECTOR_TOPK_BY_INTENT.get(query_type, 5)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        graph_future = pool.submit(
            graph_store.get_subgraph_for_query,
            query, None, hops, limit, query_entities,
        )
        vector_future = pool.submit(store.retrieve, query, top_k_children=top_k)
        graph_result = graph_future.result()
        hits = vector_future.result()

    # Phase 3 / Audit P1-A: don't re-query graph when vector bypass is active
    vector_bypassed = bool(graph_result.get("edges")) and not hits
    if not graph_result["edges"] and hits and not vector_bypassed:
        product_names = {h["product_name"] for h in hits}
        graph_result = graph_store.get_subgraph_for_query(
            query, product_names=product_names, hops=1, limit=15,
            query_entities=query_entities,
        )

    # ── Phase 7 Hook 7: intent-aware history compression ──
    history_text = compress_history_for_intent(history or [], domain_intent)

    # ── Phase 1c + Phase 6 Hook 4: budgeted, template-selected prompt ──
    prompt, max_output_tokens = context_engineering.build_prompt(
        query=query, verified_facts=graph_result.get("verified_facts"),
        comparison_blocks=graph_result.get("comparison_blocks"),
        top_edges=graph_result.get("edges"), hits=hits,
        query_type=query_type, domain_intent=domain_intent,
        history_text=history_text,
        trust_verified_facts=graph_result.get("trust_verified_facts", False),
    )

    # ── Phase 6: streaming generation (non-streaming path retained for Compare tab) ──
    stream_gen = llm_text_client.call_llm_streaming(
        prompt, model_id=config.CLAUDE_MODEL_LIGHT, max_tokens=max_output_tokens,
    )
    answer, usage = _consume_stream_or_render(stream_gen)   # caller decides st.write_stream vs. full-text

    # ── Phase 7 Hook 9: confidence calibration by domain graph coverage ──
    confidence_label = calibrate_confidence(
        raw_confidence=_score_confidence(hits, graph_result), domain_intent=domain_intent,
    )

    total_tokens = usage["input_tokens"] + usage["output_tokens"]
    elapsed = time.perf_counter() - t_start

    # ── Phase 5/6: cache store (only successful answers) ──
    if answer:
        provenance = [{"doc": h["source"], "page": h["page_num"], "score": h["score"]} for h in hits]
        cache.store(
            query_vec=query_vec, query_type=query_type, domain_intent=domain_intent,
            query_text=query, answer=answer, provenance=provenance,
            confidence_label=confidence_label, total_tokens=total_tokens,
        )

    # ── Phase 3 (P1-C/P1-D) + Phase 6 (Hook 8): one consolidated audit-log write ──
    log_query_audit({
        "query": query, "query_type": query_type, "domain_intent": domain_intent,
        "intent_key": f"{query_type}::{domain_intent}",
        "cache_hit": False, "cache_similarity": None,
        "ner_labels_used": config.get_gliner_labels(domain_intent),
        "ner_cache_hit": ner_pipeline.get_ner_cache_stats()["hits"] > 0,
        "tokens_input": usage["input_tokens"], "tokens_output": usage["output_tokens"],
        "tokens_hidden_cypher": graph_result.get("hidden_tokens", 0),
        "tokens_total": total_tokens, "latency_total_pipeline_ms": round(elapsed * 1000, 1),
    })  # appended, not one-file-per-query (Phase 3 / P1-C)

    return {
        "mode": "hybrid", "query": query, "query_type": query_type, "domain_intent": domain_intent,
        "answer": answer, "confidence_label": confidence_label,
        "docs": [{"name": h["source"], "page": h["page_num"], "score": h["score"]} for h in hits],
        "total_tokens": total_tokens, "total_time": elapsed, "cache_hit": False,
    }
```

Note the parts that come from each source document, so you can trace every line back to its origin during
review: cache short-circuit and `intent_key`/`domain_intent` plumbing → Intent plan; `ThreadPoolExecutor`
block and streaming call → Latency plan; `is_query=True`, `not vector_bypassed`, and the `build_prompt()`
call itself → Audit report.

---

## 5. Testing & Validation Plan

| Phase | Validation |
|---|---|
| 1 | Golden-query set (Phase 0) run before/after 1c; confirm no NameError on a fresh index build (1a); confirm 2nd+ taxonomy query still returns graph data (1b) |
| 2 | Timing-only: p50/p95 latency on a fixed 20-query script before/after; confirm retry cap with a simulated 3x-failing LLM call |
| 3 | Two documents with identical boilerplate text ("Management Discussion and Analysis") indexed back-to-back; confirm each chunk's entities carry the correct `doc_id`/`parent_id` |
| 4 | Golden-query set again, specifically checking GLiNER-dependent ESG entity extraction didn't regress post-quantization; confirm PyTorch fallback works when ONNX file is absent |
| 5 | Shadow-mode cache: log hit/miss + similarity score against real traffic for 1–2 weeks; manually review a sample of "would-have-been-served" cache hits for correctness before flipping the gate live |
| 6 | Golden-query set a third time (this is the biggest single rewrite); separately time-box a streaming-only smoke test (does `st.write_stream()` render token-by-token, does the Compare tab still get full text) |
| 7 | Confirm the ESG confidence badge shows "medium (limited graph coverage)" with the reason string visible in the UI, not just internally |
| 8 | Standard perf benchmarking pre/post `IndexIVFFlat` at whatever vector count you're testing with |

Build the p50/p95 timing script once in Phase 2 and reuse it through every subsequent phase — the Latency
doc's "Expected Latency After All Phases" table (its own §, reproduced in §8 below) is an estimate; you
should have a real number to hold it against by Phase 6.

---

## 6. Rollback / Feature-Flag Strategy

Given Phase 0's flag module:

- `ENABLE_CONTEXT_BUDGET` (Phase 1c) — flip off to revert to the old inline, unbudgeted prompt if 1c causes
  unexpected answer-quality regressions.
- `ENABLE_ONNX_GLINER` (Phase 4) — falls back to PyTorch GLiNER automatically if the ONNX file is missing;
  this flag forces PyTorch even if the file is present, for A/B comparison.
- `ENABLE_INTENT_CACHE` (Phase 5/6) — disables the cache short-circuit entirely; useful if domain
  misclassification starts serving wrong cached answers in production.
- `ENABLE_PARALLEL_RETRIEVAL` (Phase 6) — falls back to sequential graph→vector if the `ThreadPoolExecutor`
  surfaces a thread-safety issue you didn't catch in testing (the Latency doc's risk matrix rates the Neo4j
  driver as thread-safe, but this is your one-line escape hatch if that assumption is wrong in your specific
  driver version).
- `ENABLE_STREAMING` (Phase 6) — falls back to `st.markdown(answer)` full-text rendering if
  `st.write_stream()` has version issues (Streamlit ≥ 1.31 required, per the Latency doc).

---

## 7. Consolidated Risk Matrix

| Change | Complexity | Risk | Mitigation |
|---|---|---|---|
| P0-C prompt wiring (1c) | Low code, high blast radius | Every query's prompt shape changes at once | Golden-query set gate before proceeding; feature flag |
| ONNX GLiNER export/load | Medium | API may differ across `gliner` versions | Test with `gliner >= 0.2.0`; PyTorch fallback retained |
| Parallel `ThreadPoolExecutor` (Phase 6) | Low | Neo4j driver thread-safety assumption | Confirmed thread-safe by Latency doc, but verify on your driver version; feature flag |
| `st.write_stream` | Medium | Requires Streamlit ≥ 1.31 | Version check + `st.markdown` fallback |
| FAISS `IO_FLAG_MMAP` | Low | Doesn't work on network drives | Detect local-vs-network path, fallback to full load |
| HTTP/2 pool | Low | Needs `httpx[http2]` | Add to `requirements.txt` |
| Neo4j indexes | Very low | None — `IF NOT EXISTS` is idempotent | — |
| **Intent cache going live (Phase 5→6)** | **Medium** | **Domain misclassification serves a semantically wrong cached answer to a compliance user** | **Shadow mode for 1–2 weeks (§10); per-intent thresholds (Hook 6) before global rollout** |
| Confidence calibration (Hook 9) | Low | Correct behavior reads as a regression if unexplained | Ship the reason string in the UI, not just internally; pair with Phase 8's ESG schema work |

---

## 8. Expected Cumulative Latency (reproduced from Latency doc, annotated)

| Pipeline Step | Current | After Phase 2 | After Phase 4 | After Phase 6 |
|---|---|---|---|---|
| NER Layer B (GLiNER) | 9,000–157,000ms | unchanged | **80–400ms** | **0ms (cached)** |
| Query Classifier | 300–800ms | **0–50ms** | 0–50ms | 0–50ms |
| Graph Traversal (Neo4j) | 2,300–9,300ms | **300–600ms** | 300–600ms | **150–300ms** (parallel) |
| FAISS Vector Search | 30–300ms | 30–300ms | **20–100ms** (mmap) | **20–100ms** (parallel) |
| LLM Generation (TTFT) | 3,400–8,200ms | unchanged | unchanged | **1,200–1,500ms** (streaming) |
| SSL/TCP Overhead | 200–400ms/call | **<10ms** | <10ms | <10ms |
| Retry Worst Case | 35,000ms | **10,000ms** | 10,000ms | 10,000ms |
| **Total (typical)** | **22s–45s+** | **~8–10s** | **~3–5s** | **1.5s TTFT / 3.5s full** |

Add: taxonomy/compare-path queries get an additional **~300ms** once Phase 1b's `driver.close()` fix lands —
this is a real saving the Latency doc's table doesn't include, since it only models the main chat path.

---

## 9. Answers to the Open Questions Raised Across the Three Documents

These are options, not decisions — flagging them here so you don't have to hunt through three documents to
find every open question before Phase 5.

1. **Cache persistence across restarts** (Intent Q1): given this serves a compliance team where "yesterday's
   ESG answer" being served today is explicitly called out as valuable, disk persistence (`.pkl` write on
   shutdown / read on startup) seems to match the stated use case better than ephemeral in-memory — but that
   also means a stale answer survives a restart, which cuts against Question 3 below. These two questions
   are in tension; resolve them together, not independently.
2. **`corporate_governance` as its own domain vs. merged into `financial_performance`** (Intent Q2): keeping
   it separate costs nothing extra in the dual-gate design (it's just another bucket key) and gives you
   Hook-9-style confidence calibration granularity later if the graph schema coverage for governance and
   financial-performance nodes diverges — recommend keeping separate.
3. **Cache invalidation on reindex** (Intent Q3): for a compliance-facing tool, recommend making this
   **mandatory, not optional** — at minimum, clear the specific domain bucket(s) affected by whatever new
   document was just indexed (e.g., a new SEBI circular clears `regulatory` only). A stale ESG or regulatory
   answer served post-reindex is a correctness problem, not just a UX one.
4. **`direct_lookup` threshold at 0.96** (Intent Q4): the doc's own example (NAV on 15 July vs. 16 July)
   shows this threshold alone isn't sufficient — recommend gating `direct_lookup` cache hits on detected date
   entities matching exactly (if a date entity is present in either the incoming query or the cached query
   and they differ, force a miss regardless of cosine similarity), on top of the 0.96 threshold.
5. **GLiNER ONNX vs. lighter model** (Latency Q1/Q3): ONNX quantization of the medium model preserves
   accuracy better than switching to `gliner_small` (~5% accuracy drop per the doc's own estimate) — given
   how much of this plan is about *fixing* ESG entity extraction accuracy (F3/F3b), don't trade that back
   away for speed; go with ONNX quantization of the medium model, not the small model swap.
6. **Streaming UX — spinner then instant stream, or partial retrieval progress** (Latency Q2): given Phase 6
   drops retrieval to an estimated 150–400ms combined (graph+vector, parallel), a 2–4s spinner is likely
   optimistic-to-outdated by the time you ship this — a simple "Retrieving…" spinner should suffice; partial
   progress messaging is probably not worth the added complexity at that latency budget.
7. **Phase priority: streaming (C) before ONNX (B)?** (Latency Q4): this plan sequences ONNX (Phase 4) before
   the parallel/streaming rewrite (Phase 6) — streaming a response that still takes 9–157s to *start*
   generating (pre-ONNX GLiNER latency) provides very little perceived benefit. Fix the bottleneck before
   polishing the UX around it.

---

## 10. Additional Suggestions Not Raised in Any Source Document

- **The "Semantic Query Cache" item in the Audit's Open 2.6 checklist is the same thing as the Intent plan's
  entire deliverable.** Once Phase 5 ships, cross that line item off rather than tracking it separately —
  otherwise you'll end up with two teams (or two future sessions) building the same cache twice.
- **P0-C (Phase 1c) and the Intent plan's prompt templates (Phase 6 Hook 4) are both large, independent
  changes to the exact same prompt-construction path.** Shipping them in the same commit will make it
  genuinely hard to tell which one caused a given answer-quality change if something regresses. This plan
  already separates them into different phases (1 vs. 6) for that reason — don't compress them back together
  under schedule pressure.
- **Confidence calibration (Hook 9) will immediately downgrade the ESG query — the exact query this whole
  effort started with fixing — to "medium confidence."** That's the *correct* signal given
  `DOMAIN_GRAPH_COVERAGE["esg_sustainability"] = 0.15`, but shipped without explanation it will look like a
  regression to whoever is watching this project's ESG-query outcome most closely. Ship the UI reason string
  in the same release as the calibration logic, not as a follow-up.
- **None of the three documents include an automated regression harness** — everything above assumes you
  build the golden-query set in Phase 0 and actually re-run it at each gate. Given how much of Phases 1 and
  6 touches the shared prompt/retrieval path, this is the difference between catching a regression in code
  review versus discovering it from a compliance team asking why an ESG answer changed.
- **Domain-intent misclassification risk compounds with caching in a way flagged in §10 above but worth
  repeating**: a `financial_performance` query about "revenue" that happens to share vocabulary with a
  cached `esg_sustainability` answer at 0.89 cosine similarity would previously just get a slightly-off
  regular answer; with the cache live, it gets served *verbatim* from the wrong domain bucket. This is why
  shadow mode (Phase 5, item 4) isn't optional polish — it's the only way to measure real-world domain
  classifier accuracy before letting it silently substitute answers for a compliance audience.
- **`IndexIVFFlat` (Phase 8) and the mmap change (Phase 4) should be tested together, not assumed additive.**
  IVFFlat changes the index structure itself; whether mmap's lazy-paging behavior helps or hurts depends on
  how IVFFlat lays out its inverted lists on disk. Benchmark the combination, not each change in isolation.
