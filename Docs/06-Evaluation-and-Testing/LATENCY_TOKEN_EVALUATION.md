# Latency & Token Consumption Evaluation — Chat Query Pipeline

**Scope:** Why a single chat/query request is slower and more token-hungry than it needs to be.
**Method:** Traced the live request path end-to-end in the current codebase (not the older
`EFFICIENCY_IMPROVEMENT_PLAN.md` / `PHASE_4_EFFICIENCY_METRICS.md` docs, which benchmark the
compliance rules engine — a separate `/compliance/*` route not used during chat answering).

**Path traced:** `api/routes/chat.py` → `retrieval/orchestrator.py::answer()` →
`retrieval/intent.py` → `retrieval/traversal.py` + vector search → `retrieval/context.py` →
`retrieval/synthesizer.py` → `core/llm.py`.

## Good news first

The pipeline is already lean on the LLM-call count: **one query = 2 LLM calls when uncached**:

1. `IntentClassifier.classify` — `retrieval/intent.py:48`, small fast model (`openai/gpt-oss-20b`)
2. `Synthesizer.synthesize` — `retrieval/synthesizer.py:86`, full model (`openai/gpt-oss-120b`, `max_tokens=2048`)

There is **no** HyDE expansion, query decomposition, self-critique/reflection pass, or per-query
compliance LLM call on this path — those modules (`engine/hyde.py`, `engine/query_classifier.py`,
`engine/cross_validation.py`, `engine/text_to_cypher.py`, `engine/semantic_cache.py`,
`engine/intent_cache.py`) exist in the repo but are **not imported by the orchestrator** — they're
dead code for chat answering and cost nothing today. Prompt sizes are also reasonably bounded
(`context_token_budget=4000`, `config.py:74`; chunk snippets capped ~200-250 chars in `context.py`).

So the extra latency/tokens are not coming from "too many LLM calls" — they're coming from
**structural inefficiencies around** those two calls.

## Root causes, ranked by impact

### 1. Graph traversal and vector search run sequentially, but are independent
`retrieval/orchestrator.py:248-277` — Step 4 (`self._traversal.traverse(...)`, a Neo4j round-trip)
and Steps 5-6 (`self._vector.search(...)`, a FAISS lookup) both depend only on `intent` /
`resolved_entities`, not on each other's output, yet are `await`ed back-to-back.

**Fix:** run them concurrently — `graph_res, vector_res = await asyncio.gather(self._traversal.traverse(...), self._vector.search(...))`.
This is the single biggest fixable latency item: it currently pays Neo4j latency + FAISS latency
serially instead of `max(Neo4j, FAISS)`.

### 2. Default `mode="both"` runs a redundant second retrieval pass every request
`schemas/api.py:93` defaults `mode` to `"both"`. In `api/routes/chat.py:194-205`, when
`mode in ("traditional", "both")` **and** `mode in ("contextgraph", "both")` both fire, the
request does a full `orchestrator.answer()` pass *and* a separate `traditional_search()` pass that
re-embeds the same query and re-runs FAISS search just to populate a "traditional" comparison
panel. Since `"both"` is the schema default, this effectively **doubles vector-search + embedding
cost on nearly every request** unless the caller explicitly overrides `mode`.

**Fix:** default `mode` to `"contextgraph"` (the actual production answer path), or have the
traditional pass reuse chunks already fetched by the main retrieval instead of re-searching.

### 3. Semantic cache does blocking, duplicate, separately-loaded embedding
`retrieval/cache.py:40` — `SemanticQueryCache` loads its own `fastembed.TextEmbedding` instance
independent of the one `VectorStore` already uses for FAISS search, so **every query is embedded
twice** by two separately-loaded models (extra memory + startup cost). Worse,
`SemanticQueryCache._to_vector` (`cache.py:47-60`) calls the embedder's synchronous `.embed()`
directly on the asyncio event loop — unlike `VectorStore.embed_async`, which correctly offloads to
a thread. Under concurrent traffic this **serializes every request through blocking CPU-bound
embedding work on the event loop**, hurting throughput and tail latency for all users, not just the
one query.

**Fix:** wrap the cache's embed call in `asyncio.to_thread(...)`, and share a single embedder
instance between the cache and `VectorStore` instead of instantiating two.

### 4. Per-entity graph lookups loop sequentially
`retrieval/traversal.py` — `_exposure` (lines ~72-104) and `_entity_lookup` (lines ~240-260) issue
one Cypher query per resolved entity (up to ~3) inside a loop of sequential `await`s. For
multi-entity queries this serializes N Neo4j round-trips that don't depend on each other.

**Fix:** `asyncio.gather` the per-entity Cypher calls. Modest impact (queries rarely mention >3
entities) but cheap to fix.

### 5. Concurrency ceiling + retry backoff can stack multi-second delays under load
`core/llm.py:28` caps concurrent LLM calls repo-wide at `llm_max_concurrency=4`
(`config.py:56`), and `llm_max_retries=3` (`config.py:55`) with exponential backoff
`[1, 2, 4, 8]` seconds (`core/llm.py:22`) on rate-limit errors. Not a bug in a single request, but
under any real concurrent load this becomes a throughput ceiling — a burst of requests queues
behind the semaphore, and any rate-limited call adds seconds of backoff on top.

**Fix:** raise `llm_max_concurrency` in line with the actual Groq rate-limit tier, and consider a
separate (higher) concurrency limit for the small/fast intent-classification model vs. the
synthesis model, since they have very different cost profiles.

## Not the problem (verified, ruled out)

- **Prompt bloat:** context budget is capped and enforced (`context.py`), few-shots are small.
- **Entity resolution:** in-memory dict lookup, no LLM/DB call — negligible cost.
- **Compliance guardrails:** run on a separate `/compliance/*` route, not invoked per chat query.
- **"Dead" advanced-RAG modules** (HyDE, decomposition, cross-validation, semantic/intent cache
  variants under `engine/`): not wired into the live path, so they add zero runtime cost — but
  their presence is worth flagging for cleanup since it's easy to assume they're active.

## Recommended priority order

1. Parallelize graph traversal + vector search (#1) — biggest, cheapest win.
2. Change default `mode` away from `"both"` or dedupe the traditional-search pass (#2) — removes
   an entire redundant embedding + FAISS search from most requests.
3. Fix the cache's blocking/duplicate embedding (#3) — protects tail latency under concurrent load.
4. Parallelize per-entity traversal calls (#4).
5. Tune concurrency/retry settings for real traffic (#5).

None of these require reducing the 2-LLM-call design — the model-call count and prompt sizing are
already close to minimal; the wins are in removing serialized I/O and a redundant retrieval pass.
