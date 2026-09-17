# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# ContextGraph Convergence — Detailed Implementation Plan

## 1. Purpose and decision

This plan converts the completed baseline into one serving and ingestion path.
It is grounded in the run at
`logs/baseline/20260814T082557Z/`:

- `/api/query` and `/api/chat` currently use `app.engine.retrieval` and the
  populated legacy `amc_master` FAISS index.
- `RetrievalOrchestrator`, `IngestionPipeline`, `/api/docs`, `/api/graph`, and
  `/api/taxonomy` use the modern data plane, which is currently empty or
  schema-incompatible with the active corpus.
- The active Neo4j graph has chunk-keyed `(:Entity)` provenance; it has no
  `(:Document)` or `(:TaxonomyNode)` nodes.

**Target decision:** make the modern `IngestionPipeline` +
`RetrievalOrchestrator` the sole production ContextGraph path. The legacy engine
remains unchanged and runnable until the target path passes the stated
acceptance gates.

## 2. Non-negotiable migration rules

1. Never alter the active index or graph in place.
2. Build the target corpus and graph in a separately versioned location or
   staging deployment, then promote by configuration/feature flag.
3. Preserve raw source files, legacy FAISS artifacts, graph export, and the
   August baseline output as rollback evidence.
4. A failure must be returned, logged, and measured. Do not substitute a mock
   answer, empty source list, or legacy response without an explicit route and
   trace field saying so.
5. Canonical IDs—not source filenames, `product_name`, or `P#####` keys—are
   the only cross-store join keys after migration.
6. Do not add CKG, agent loops, autonomous feeds, or new UI claims while core
   serving, provenance, and evaluation remain split.

## 3. Workstream map and sequencing

```mermaid
flowchart LR
  S["A. Stabilize contracts"] --> I["B. Canonical identity contract"]
  I --> M["C. Build parallel corpus + graph"]
  M --> R["D. Add v2 shadow serving route"]
  R --> O["E. Observability + evaluation alignment"]
  O --> P["F. Flagged production promotion"]
  P --> D["G. Legacy decommission"]
```

Each workstream has a hard exit gate. Later work can be prepared in parallel,
but it may not be promoted before the prior gate passes.

---

## A. Stabilize the v2 contracts

### A1. Repair entity-resolution callers

**Problem:** `EntityResolver.resolve_surface_form()` returns
`(Optional[BaseEntity], float)`, while current callers treat it as a bare
entity. The baseline demonstrated a unit-test failure and the same condition in
`/api/graph/neighborhood`.

**Implementation tasks**

1. Search every caller of `resolve_surface_form()`.
2. Select one supported API shape:
   - retain the existing tuple and require callers to unpack
     `entity, confidence`; or
   - replace it with a typed `ResolutionResult` model containing `entity` and
     `confidence`.

   Prefer `ResolutionResult` if resolution rationale will be exposed in the
   trace; otherwise retain the tuple for the smallest safe repair.
3. Correct all callers, including:
   - `backend/app/retrieval/orchestrator.py`;
   - `backend/app/api/routes/graph.py`;
   - ingestion resolution paths; and
   - tests and any scripts that call the resolver directly.
4. Preserve the resolver confidence in `RetrievalResult.resolved_entities` or
   the new trace, rather than discarding it.
5. Add unit tests for exact alias, containment match, unknown entity, and a
   graph neighborhood request with a known alias.

**Files likely to change**

```text
backend/app/extraction/resolver.py
backend/app/retrieval/orchestrator.py
backend/app/api/routes/graph.py
backend/tests/test_ingestion_units.py
backend/tests/test_*resolver*.py                 (new)
```

**Acceptance gate A1**

- Offline tests have no resolver API mismatch.
- `/api/graph/neighborhood?name=Adani` either returns a valid graph response or
  a deliberate 404—never `AttributeError`/500.
- The v2 orchestrator resolves an alias before graph traversal.

### A2. Make data-plane status truthful

**Problem:** `/api/status`, `/api/docs`, and `/api/graph` describe the empty
modern store while `/api/query` answers from the populated legacy store.

**Implementation tasks**

1. Add a `data_plane` or `serving_engine` section to status responses:

   ```json
   {
     "serving_engine": "legacy_engine",
     "serving_corpus_version": "amc_master_legacy",
     "modern_corpus_version": null,
     "legacy_index": {"documents": 18},
     "modern_index": {"documents": 0}
   }
   ```

2. Keep existing response fields temporarily for frontend compatibility, but
   deprecate misleading names such as `qdrant` where the implementation is
   FAISS.
3. Add an explicit `GET /api/status/data-planes` endpoint if adding details to
   the existing health schema would break consumers.
4. Annotate `/api/docs` and `/api/graph` output with corpus/version metadata.
   An empty modern result must not appear to be an empty active corpus.
5. Update the frontend status caption to display the server-selected engine and
   corpus version, not merely the API URL.

**Acceptance gate A2**

- A user can identify the exact engine/index behind a query from the API
  response and status endpoint.
- No endpoint silently conflates legacy and target data.

### A3. Correct latency and cache accounting

**Problem:** baseline evidence shows cache pipeline time and top-level response
time can disagree by seconds.

**Implementation tasks**

1. Start one route-level monotonic timer at endpoint entry.
2. Time each stage independently: cache lookup, query rewrite, NER, graph,
   vector, rerank, context assembly, LLM generation, adapter serialization.
3. Introduce a typed `QueryTrace` schema. Minimum fields:

   ```text
   request_id, serving_engine, corpus_version, cache_hit, cache_kind,
   cache_lookup_ms, query_rewrite_ms, ner_ms, graph_ms, vector_ms,
   rerank_ms, assembly_ms, generation_ms, request_total_ms,
   input_tokens, output_tokens, cold_equivalent_tokens, tokens_saved,
   quality_score, quality_gate_passed, fallback_used, fallback_reason
   ```

4. Define semantics in code comments and API schema descriptions:
   - `request_total_ms` is wall time from route entry to response serialization;
   - `cache_lookup_ms` includes all work needed to decide a cache hit;
   - `cold_equivalent_tokens` is an estimate and must name its estimator;
   - `tokens_saved` is populated only when both actual and cold-equivalent
     values exist.
5. Include the trace in v2 responses immediately. Add it to legacy responses
   only as a compatibility/observability enhancement, not as a behavior change.
6. Add tests asserting `request_total_ms >= each individual stage` and that a
   cache hit cannot report zero latency if lookup itself was costly.

**Acceptance gate A3**

- One query response exposes a single, coherent timing model.
- Cache savings claims cannot be computed from mixed cache states.

---

## B. Define the canonical identity and provenance contract

### B1. Approve the identifier model

Use full SHA-256 values internally; truncation is display-only.

| Field | Definition | Stability |
|---|---|---|
| `source_id` | SHA-256 of canonical source URI/path and source-system namespace. | Stable for the logical source. |
| `document_id` | Stable logical document ID, derived from `source_id`. | Stable across source revisions. |
| `content_sha256` | SHA-256 of exact acquired bytes. | Changes when content changes. |
| `document_version_id` | SHA-256 of `document_id + content_sha256`. | Immutable per content version. |
| `chunk_id` | SHA-256 of `document_version_id + section/page locator + normalized chunk text`. | Deterministic per version/chunk. |
| `legacy_parent_id` | Old `P#####` parent key. | Migration-only cross-reference. |

Required provenance on every target chunk and extracted relationship:

```text
document_id, document_version_id, chunk_id, source_id, content_sha256,
source_uri_or_path, source_filename, page_start, page_end, section_locator,
ingested_at, extractor_version, taxonomy_paths
```

### B2. Implement the contract without breaking legacy data

**Implementation tasks**

1. Add a pure identity module with canonicalization and hashing functions.
2. Add Pydantic models for document version and provenance. Initially allow
   legacy records to omit fields only when `legacy=true` is explicitly set.
3. Extend `Document`, `Chunk`, `Relationship`, and vector payload schemas.
4. Change parser output to calculate a content hash immediately after file read.
5. Change chunking to generate deterministic IDs from the approved model.
6. Change graph writes and vector payload writes to use those same IDs.
7. Reject any target ingestion write missing required provenance.

**Suggested files**

```text
backend/app/contracts/identity.py                (new)
backend/app/schemas/documents.py
backend/app/schemas/relationships.py
backend/app/ingestion/parsers/base.py
backend/app/ingestion/chunker.py
backend/app/ingestion/pipeline.py
backend/app/vector/client.py
backend/app/graph/client.py
backend/tests/test_identity_contract.py          (new)
```

### B3. Produce a legacy mapping manifest

**Implementation tasks**

1. Read the active `amc_master` FAISS metadata and parent/child pickle data.
2. For each legacy source file, calculate source/document/version IDs.
3. Map every `P#####` and child record to its canonical document/version/chunk
   IDs, source file, page, and extracted text fingerprint.
4. Write a versioned immutable CSV/JSON manifest. It is an input to migration,
   not a runtime database.
5. Validate:
   - all 18 baseline sources are represented;
   - no parent/child has multiple canonical document versions;
   - source/page values are non-null where legacy artifacts supply them; and
   - duplicate byte hashes are deliberate aliases, not accidental duplicates.

**Acceptance gate B**

- New ingestion produces identical IDs for the same bytes on repeated runs.
- Every legacy source and `P#####` key has one mapping-manifest row.
- No target chunk/relationship lacks canonical provenance.

---

## C. Build a parallel canonical corpus and graph

### C1. Create a target-only persistence layout

Use a new corpus version rather than appending to the empty/legacy default:

```text
backend/data/corpora/<corpus-version>/manifest.json
backend/data/vector_store/<corpus-version>/index.faiss
backend/data/vector_store/<corpus-version>/payloads.json
backend/data/migrations/<corpus-version>/legacy_id_map.csv
```

For Neo4j, use an isolated staging deployment or an explicitly namespaced target
label/property in a dedicated migration environment. Do not run destructive
`DETACH DELETE` operations against the baseline graph.

### C2. Upgrade target graph schema

**Implementation tasks**

1. Create constraints appropriate to the new IDs:

   ```cypher
   CREATE CONSTRAINT document_id_unique IF NOT EXISTS
   FOR (d:Document) REQUIRE d.document_id IS UNIQUE;

   CREATE CONSTRAINT document_version_id_unique IF NOT EXISTS
   FOR (v:DocumentVersion) REQUIRE v.document_version_id IS UNIQUE;

   CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS
   FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE;

   CREATE CONSTRAINT taxonomy_path_unique IF NOT EXISTS
   FOR (t:TaxonomyNode) REQUIRE t.path IS UNIQUE;
   ```

2. Use this target structure:

   ```text
   (:Document)-[:HAS_VERSION]->(:DocumentVersion)
   (:DocumentVersion)-[:HAS_CHUNK]->(:Chunk)
   (:DocumentVersion)-[:MENTIONS]->(:Entity)
   (:DocumentVersion)-[:TAGGED_AS]->(:TaxonomyNode)
   (:Entity)-[relationship {source_document_id, source_chunk_id}]->(:Entity)
   ```

3. Store immutable source/version properties on `DocumentVersion`; do not copy
   large chunk text into all graph nodes if it remains in vector payloads.
4. Update graph traversal Cypher to filter by active `document_version_id` and
   target corpus version.

### C3. Make ingestion idempotent and recoverable

**Implementation tasks**

1. Add an ingestion ledger entry before processing each document version.
2. Use stages: `parsed`, `chunked`, `graph_written`, `vector_written`,
   `validated`, `activated`, `failed`.
3. Store the corpus version and content hash in both graph and vector payloads.
4. On retry, resume safely from the last validated stage or rebuild only the
   target corpus version; never append duplicate FAISS entries blindly.
5. Publish/activate the version only after integrity validation succeeds.
6. Retain enough ledger information to clean up a failed target-version build
   without affecting an active version.

### C4. Migrate the baseline corpus

**Implementation tasks**

1. Take a fresh export/checksum of the legacy index and graph.
2. Ingest the same 18 baseline sources through the modern pipeline into the
   target corpus version.
3. Reuse the approved legacy mapping manifest to verify source/page coverage.
4. Generate an integrity report comparing target vector payloads, target graph
   documents/versions/chunks, and expected manifest rows.
5. Quarantine source documents that fail parsing/extraction; do not silently
   omit them. Report them as failed corpus members.

### C5. Bring taxonomy into the target graph

**Implementation tasks**

1. Remove hard-coded taxonomy host/port values from the builder and obtain all
   connection settings from the same target configuration as the app.
2. Make taxonomy import versioned and idempotent; limit replacement/deletion to
   taxonomy nodes belonging to the target taxonomy version.
3. Import regime, scheme class, circular, amendment, and crosswalk nodes into
   the target graph.
4. Create deterministic cross-links from normalized fund/category entities to
   `SchemeClass` nodes. Store match method/confidence for review.
5. Add taxonomy regression cases: large-cap lookup, 2017-vs-2026 comparison,
   amendment traversal, and no-match behavior.

**Acceptance gate C**

- The target corpus has the full approved source count or an explicit quarantine
  record for each exception.
- 100% of target vector chunks join to one graph `DocumentVersion` by canonical
  IDs.
- 100% of extracted relationships carry `source_document_id` and
  `source_chunk_id`.
- Taxonomy and entity graph nodes coexist in the same target graph topology and
  at least the approved mapping fixtures traverse their link.

---

## D. Expose the orchestrator safely

### D1. Complete v2 orchestration capabilities

Before exposing the route, close feature gaps needed for parity:

- pass compressed conversation history to synthesis and trace the rewrite;
- retain taxonomy scoping and graph traversal paths;
- implement the approved cache behavior with canonical source provenance;
- preserve safety/PII/compliance guardrails;
- use the target corpus version in every search/filter; and
- return source snippets plus canonical IDs/page information.

Define intentionally what the traditional comparison side means. It should be
an unscoped vector baseline over the **same target corpus**, not the legacy
index or a separate corpus. If it synthesizes an answer, make that explicit in
the contract.

### D2. Add a compatibility adapter and shadow route

**Implementation tasks**

1. Implement `POST /api/query/v2` using `Container.orchestrator.answer()`.
2. Add `POST /api/chat/v2` after multi-turn history has been implemented and
   tested for the orchestrator.
3. Adapt orchestrator outputs to the existing `QueryResponse` fields:
   `answer`, `sources`, `intent`, `traversal_paths`, `taxonomy_paths`,
   `graph_highlight`, `context_debug`, and the new `trace`.
4. Put the engine selection behind an environment/config flag:

   ```text
   QUERY_ENGINE=legacy | v2 | shadow
   ACTIVE_CORPUS_VERSION=<version>
   ```

5. `legacy` continues to use existing route behavior.
6. `v2` serves the target response.
7. `shadow` serves one selected engine to the client and stores a separately
   identified comparison execution for controlled test users only. It must not
   double LLM cost for all production traffic by default.
8. Include `serving_engine`, `corpus_version`, and `fallback_used` in every
   response trace.

**Suggested files**

```text
backend/app/api/routes/query.py
backend/app/api/routes/chat.py
backend/app/api/deps.py
backend/app/retrieval/orchestrator.py
backend/app/retrieval/synthesizer.py
backend/app/schemas/api.py
backend/app/schemas/query.py
backend/app/config.py
backend/tests/test_query_v2_contract.py          (new)
backend/tests/test_chat_v2_contract.py           (new)
```

### D3. Execute parity validation

For every query fixture, run legacy and v2 against their explicitly recorded
corpus versions. Capture raw responses, traces, and cited IDs.

Score each result on:

| Dimension | Required evidence |
|---|---|
| Availability | HTTP outcome and explicit fallback field. |
| Grounding | Every material factual claim has one or more source IDs. |
| Provenance | Source IDs resolve to target document/version/chunk records. |
| Retrieval quality | Approved expected sources/facts are present. |
| Safety | Guardrails give the approved response for advice/jailbreak fixtures. |
| Conversation | Follow-up answer uses prior context without contaminating source search. |
| Performance | Stage timings compared only within the same cache state. |

**Acceptance gate D**

- V2 completes the approved fixture suite without an uncaught exception.
- No v2 answer cites an unresolvable source ID.
- V2 meets the project-approved quality/safety threshold relative to the legacy
  baseline; exceptions have explicit owner and resolution plan.
- Rollback to `QUERY_ENGINE=legacy` is tested.

---

## E. Align observability, UI, and evaluation

### E1. API and UI trace contract

**Implementation tasks**

1. Finalize `QueryTrace` as a versioned API model.
2. Add a compact UI trace panel, initially visible only in an internal/debug
   mode. It must show:
   - serving engine and corpus version;
   - query intent and selected retrieval path;
   - graph/vector candidates and selected sources;
   - quality score/gate;
   - cache status and honest token/latency accounting; and
   - confidence label plus the signals used to derive it.
3. Use declarative labels such as “estimated cold-equivalent token savings,” not
   unqualified “tokens saved,” when estimates are involved.
4. Remove/replace UI text that claims port 7688 or a dual graph unless the
   active response trace confirms it.

### E2. Align the evaluation harness

**Implementation tasks**

1. Create a versioned evaluation dataset containing query, expected source IDs,
   required facts, safety constraints, and multi-turn history.
2. Make evaluation invoke the production-equivalent HTTP endpoint, not a direct
   alternate Python function.
3. Separate test tiers:

   ```text
   unit       — contracts/IDs/no external services
   integration — target graph/vector fixture corpus
   e2e        — running API plus controlled LLM provider
   benchmark  — versioned corpus, recorded cache state, report artifact
   ```

4. Treat 5xx, empty citations, source-ID mismatches, fallback substitutions,
   and violated safety constraints as failures.
5. Report cache-hit and cache-miss results separately, including sample sizes.
6. Retire or relabel old taxonomy-v2/legacy benchmark reports so they cannot be
   presented as active-serving-path results.

**Acceptance gate E**

- UI, API, audit log, and evaluation use the same field definitions.
- Every published metric names the route, corpus version, model/provider state,
  fixture version, and cache state.

---

## F. Promote through a feature flag

### F1. Internal pilot

1. Set `QUERY_ENGINE=v2` only in an internal/staging environment.
2. Pin `ACTIVE_CORPUS_VERSION` to the validated target version.
3. Re-run the baseline collector and graph integrity checks.
4. Compare results against the August baseline using explicitly comparable
   cache/model conditions.
5. Monitor failures, no-source answers, fallback rate, p50/p95 timings, and
   citation resolution rate.

### F2. Production promotion criteria

All must hold:

- A full target corpus integrity report passes.
- V2 endpoint and multi-turn suite pass.
- No unresolved P0/P1 data/provenance/safety defect remains.
- The rollback flag has been exercised successfully.
- The data owner approves the target corpus and taxonomy version.
- The evaluator report is generated from the active API route.

### F3. Rollback procedure

1. Set `QUERY_ENGINE=legacy`.
2. Keep the target corpus/index untouched for diagnosis; do not delete it.
3. Capture affected request IDs and traces.
4. Re-run the minimal fixture set against legacy to confirm recovery.
5. Open a defect record containing source IDs, corpus version, and trace—not
   only an answer screenshot.

**Acceptance gate F**

- Promotion and rollback are configuration changes, not code edits or data
  restoration exercises.

---

## G. Decommission safely

Only begin after the v2 path has remained stable for the approved observation
period and two comparable baseline runs show no regression.

1. Freeze the legacy index and graph export as an archived artifact.
2. Remove legacy engine selection from public routes, retaining it only in a
   non-production diagnostic harness during the retention period.
3. Remove Streamlit’s local retrieval fallback or replace it with a clear API
   outage message; it must not silently answer from a different corpus.
4. Remove duplicate/inaccurate documentation and hard-coded topology claims.
5. Remove obsolete data volumes only after the retention policy and recovery
   requirements are approved.

**Acceptance gate G**

- Exactly one production retrieval engine, one active corpus version, one graph
  topology, and one document-ID contract remain.

## 4. Implementation backlog

| ID | Work item | Depends on | Done when |
|---|---|---|---|
| CV-01 | Repair resolver return-type contract | — | Resolver/API/orchestrator tests pass. |
| CV-02 | Add truthful data-plane status | CV-01 | Status identifies engine and corpus. |
| CV-03 | Add `QueryTrace` and timing definitions | CV-02 | Cache/route timing contract tested. |
| CV-04 | Implement canonical identity/provenance module | CV-01 | Repeat-ingest IDs are deterministic. |
| CV-05 | Generate legacy source/chunk mapping manifest | CV-04 | All 18 source files and P keys map. |
| CV-06 | Create target graph/vector versioned storage | CV-04 | Target writes cannot change active artifacts. |
| CV-07 | Implement idempotent target ingestion ledger | CV-06 | Retry does not duplicate data. |
| CV-08 | Ingest and validate target baseline corpus | CV-05, CV-07 | Target integrity gates pass. |
| CV-09 | Import/link taxonomy in target graph | CV-08 | Taxonomy traversal fixtures pass. |
| CV-10 | Complete v2 history/cache/safety parity | CV-01, CV-08 | API-level behavior tests pass. |
| CV-11 | Add `/api/query/v2` and `/api/chat/v2` | CV-03, CV-10 | Compatibility contracts pass. |
| CV-12 | Run shadow parity evaluation | CV-09, CV-11 | V2 meets approved comparison gates. |
| CV-13 | Align UI and evaluation harness | CV-11 | One metric/source vocabulary everywhere. |
| CV-14 | Internal flag promotion and rollback drill | CV-12, CV-13 | Promotion gates and rollback verified. |
| CV-15 | Retire legacy path | CV-14 | One active production path remains. |

## 5. Definition of complete

The convergence is complete only when a request to `/api/query` and `/api/chat`
is handled by the orchestrator against a canonical, versioned corpus; every
citation joins to graph/vector provenance by ID; taxonomy traversal shares that
graph; metrics are coherent; evaluations target that route; and rollback plus
decommission have been exercised deliberately.
