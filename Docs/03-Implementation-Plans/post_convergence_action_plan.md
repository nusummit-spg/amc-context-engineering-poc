# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Post-Convergence Validation and Promotion Plan

## Decision summary

The convergence foundation has been implemented: canonical identifiers,
versioned target-corpus artifacts, ingestion ledger, v2 query/chat routes,
feature flags, and response tracing are present. The next phase is **not** an
immediate production cutover. It is an independent validation and hardening
phase that must prove the v2 path is functionally equivalent or superior on the
same corpus.

This plan supersedes the promotion claim in `Docs/convergence_report.md` until
all gates below have been independently rerun and passed.

## Evidence requiring this phase

| Finding | Evidence | Consequence |
|---|---|---|
| Runtime is not reproducible now | The checked-in `backend/.venv/Scripts/python.exe` could not start because its configured Python 3.10 executable is missing. | No current test report can be trusted until the environment is rebuilt. |
| Cache is not functionally wired in v2 | `RetrievalOrchestrator.answer()` looks up `cached_entry` but then continues through intent, retrieval, and synthesis; it reports `cache_hit=False`. | Do not claim v2 cache savings or warm-hit latency. |
| V2 history rewrite is ineffective | It reads `history[*].query`, while the API contract uses `history[*].content`. | Multi-turn semantic continuity is unproven. |
| Parity evidence is insufficient | Convergence report records 25% average source overlap and every v2 intent as `general`. | Fast responses alone do not prove retrieval, taxonomy, or domain parity. |
| V2 route tests are contract-only | `test_query_v2_contract.py` mocks LLM output and asserts response shape. | Passing tests do not validate grounded real responses. |

## Promotion rule

`QUERY_ENGINE` remains `legacy` in every shared/production environment until
the independent parity report passes. `v2` is allowed only in an isolated local
or staging environment. `shadow` is allowed only for a controlled sample and
must not double LLM traffic by default.

## Workstream order

```mermaid
flowchart LR
  A["PV-01 Rebuild reproducible runtime"] --> B["PV-02 Repair v2 behavior"]
  B --> C["PV-03 Verify target corpus + topology"]
  C --> D["PV-04 Build real parity evaluation"]
  D --> E["PV-05 Run controlled shadow pilot"]
  E --> F["PV-06 Promote or rollback"]
```

---

## PV-01 — Rebuild a reproducible validation environment

### Goal

Make it possible for any engineer to run the same tests against the same code,
dependencies, target corpus, and graph topology.

### Activities

1. Choose and document the approved CPython version. Start with Python 3.10.11
   only if all requirements and model packages support it; otherwise choose a
   supported version and update project documentation deliberately.
2. Remove only the broken virtual environment after confirming its exact path;
   do not remove indexes, corpus files, logs, or source data.
3. Recreate `backend/.venv` with the approved interpreter.
4. Install from `backend/requirements.txt` and record:
   - Python executable and version;
   - pip version;
   - requirements file SHA-256;
   - `pip freeze` output;
   - operating system and architecture.
5. Add a preflight script that fails clearly if the venv launcher points to a
   missing interpreter, required model libraries are absent, or target corpus
   files are unavailable.
6. Run and save outputs for:

   ```powershell
   python -m pytest tests/test_schemas_and_contracts.py tests/test_ingestion_units.py -q
   python -m pytest tests/test_identity_contract.py tests/test_query_v2_contract.py -q
   ```

7. Keep mocks permitted only in unit/contract tests. Mark any test that calls a
   live graph, vector index, or LLM as integration/e2e explicitly.

### Deliverables

```text
logs/post-convergence/<run-id>/environment_preflight.json
logs/post-convergence/<run-id>/requirements-freeze.txt
logs/post-convergence/<run-id>/unit-tests.log
```

### Acceptance gate PV-01

- A fresh virtual environment starts without a missing-interpreter error.
- All offline tests pass or have a recorded, reproducible failure.
- The preflight output names the target corpus version and graph endpoint.

---

## PV-02 — Close v2 functional gaps

### PV-02A. Implement cache semantics or explicitly disable v2 cache

#### Required decision

Choose one behavior for v2 before benchmarking:

1. **Implement cache:** a valid cache hit returns a cached synthesis and its
   provenance without running graph/vector/LLM stages; or
2. **Disable cache:** remove the lookup and set cache fields to
   `cache_hit=false`, `cache_kind=null`, and `tokens_saved=null`.

Do not retain an unused lookup that suggests cache optimization occurred.

#### Implementation activities if cache is enabled

1. Define a cache key containing query normalization, active corpus version,
   model/synthesis version, selected taxonomy scope, and a digest of relevant
   conversation history.
2. Store answer, citations, canonical source IDs, trace baseline, quality
   decision, and expiry metadata.
3. On a hit, return a new trace with:
   - `cache_hit=true`;
   - cache lookup wall time;
   - zero values only for stages actually skipped;
   - actual cached-response token cost; and
   - clearly labeled cold-equivalent estimate, if one exists.
4. Invalidate by corpus version, content version, taxonomy version, prompt
   version, model version, and configured TTL.
5. Add tests for miss, exact hit, history mismatch, corpus-version mismatch,
   expiry, and citation preservation.

### PV-02B. Repair multi-turn history semantics

1. Define one message model: `role`, `content`, optional timestamp, and optional
   turn identifier. Normalize legacy message forms at the API boundary.
2. Replace `history[*].query` access in the v2 orchestrator with a helper that
   reads the last user `content` safely.
3. Reuse or adapt the existing coreference-resolution policy so the rewritten
   query is visible in the trace as `effective_query` or a hash/redacted form.
4. Keep raw history out of logs unless retention/PII requirements permit it.
5. Add multi-turn fixtures that require entity carry-over, temporal follow-up,
   and a negative test that prevents history from leaking into an unrelated
   question.

### PV-02C. Guarantee corpus-version routing

1. Verify that `ACTIVE_CORPUS_VERSION` controls the physical FAISS payload and
   index location used by `VectorStore`, not only a response field.
2. Make corpus version an explicit constructor/configuration input to vector
   and graph retrieval clients.
3. Fail startup if the selected corpus manifest, vector index, graph migration
   marker, and taxonomy version do not agree.
4. Include the resolved physical corpus path/checksum in protected diagnostic
   status output; do not expose sensitive local paths publicly.
5. Add tests that two corpus versions cannot cross-return chunks.

### PV-02D. Make query mode semantics explicit

1. Document `traditional`, `contextgraph`, and `both` for v2.
2. Ensure `traditional` is an unscoped vector baseline over the same target
   corpus, with no graph-derived answer passed off as traditional output.
3. Ensure `contextgraph` alone does not execute the comparison baseline.
4. Test that `top_k` reaches both retrieval implementations and that response
   sources are canonical IDs in every mode.

### PV-02E. Stop hiding graph schema failures

1. Replace blanket `except: pass` around target Neo4j constraints/indexes with
   error handling that distinguishes “already exists” from connection or syntax
   failure.
2. Fail target corpus activation when required constraints cannot be verified.
3. Record schema version and constraint verification in the ingestion ledger.

### Acceptance gate PV-02

- Cache, history, corpus version, and query modes have one documented behavior
  and direct tests.
- `QueryTrace` accurately represents work performed.
- No target-schema setup error is silently discarded.

---

## PV-03 — Independently verify the target corpus and graph

### Goal

Prove that the target corpus—not only legacy artifacts—contains correct,
joinable, fully traced data.

### Activities

1. Take a new read-only census of the target graph and target vector store.
2. Verify the target corpus manifest against source files:
   - expected source count;
   - `source_id`, `document_id`, content SHA, and document-version ID;
   - chunk count and page/section coverage;
   - parser/extractor version; and
   - quarantine reasons for any omitted source.
3. Produce joins in both directions:

   ```text
   vector chunk -> graph Chunk -> DocumentVersion -> Document
   graph relationship -> source_chunk_id -> vector chunk
   source document -> all expected target chunks
   ```

4. Verify every imported taxonomy node includes a taxonomy version and every
   entity-to-scheme-class mapping records its match method and confidence.
5. Test that taxonomy import uses the selected target connection configuration;
   it must not rely on the legacy hard-coded 7688 builder endpoint.
6. Validate the ingestion ledger state machine on one test source:
   `parsed -> chunked -> graph_written -> vector_written -> validated -> activated`.
   Repeat ingestion of identical bytes and prove it does not duplicate data.

### Required reports

```text
target_corpus_manifest_validation.csv
target_graph_census.json
target_vector_census.json
target_integrity_report.md
target_taxonomy_link_report.csv
ingestion_idempotency_test.log
```

### Acceptance gate PV-03

- 100% of active target vector chunks join to exactly one target document version.
- 100% of target graph relationships have resolvable document and chunk
  provenance, except explicitly classified schema-only relationships.
- The target corpus/version selected by v2 is physically verified.

---

## PV-04 — Build and run an independent real parity evaluation

### Goal

Replace response-shape and document-overlap measurements with grounded,
production-equivalent evidence.

### Dataset design

Create a versioned fixture file for each scenario containing:

```json
{
  "id": "sebi_large_cap_regime",
  "history": [],
  "query": "...",
  "required_facts": ["..."],
  "expected_source_ids": ["..."],
  "minimum_source_recall": 1.0,
  "taxonomy_paths": ["..."],
  "safety_constraint": null
}
```

Cover at minimum:

- direct retrieval and cross-document synthesis;
- regulatory/taxonomy lookup;
- 2017-vs-2026 temporal comparison;
- graph aggregation;
- financial/Adani query;
- absent-answer handling;
- safety/investment-advice handling;
- multi-turn coreference; and
- cache warm/cold behavior when cache is enabled.

### Evaluation activities

1. Run legacy and v2 via HTTP, never by calling alternate Python functions.
2. Pin the same source corpus for comparable tests. If legacy cannot use the
   canonical corpus, label the result as a migration-quality comparison rather
   than a strict retrieval parity comparison.
3. Use real configured LLM/provider calls for e2e evaluation. Record model and
   provider state; do not use mocked synthesis results in this report.
4. Grade facts and source IDs separately:
   - factual correctness/relevance;
   - citation/source precision and recall;
   - source-ID resolvability;
   - taxonomy/traversal correctness;
   - safety compliance;
   - multi-turn coherence.
5. Treat any 5xx, uncaught exception, unsupported fallback, or missing citation
   on a grounded answer as a failure.
6. Measure p50/p95 per-stage latency for cold and warm states separately.
7. Investigate every `general` intent that should have a domain/taxonomy route;
   improve classifier prompts/rules/data only after recording the failure.

### Acceptance criteria

Promotion criteria must be agreed by the data owner before execution. At a
minimum, require:

- no P0/P1 safety, provenance, or availability failure;
- all required expected source IDs resolved for regulated scenarios;
- every response citation resolves to the active target corpus;
- multi-turn fixtures demonstrate history use and no cross-session leakage;
- v2’s quality score agrees with independent grading often enough to be useful;
- performance comparisons use equal model/provider and cache conditions.

**Important:** 25% top-document overlap is diagnostic only; it is not a pass
criterion. A lower overlap can be acceptable only when the expected facts and
canonical citations are independently correct.

### Acceptance gate PV-04

- A versioned, reproducible, real-service report establishes v2 quality.
- Mock-only contract tests are clearly separated from this report.

---

## PV-05 — Controlled shadow pilot

### Scope

Use a staging or internal-user environment only. Do not enable shadow execution
for all production requests because it can double LLM/provider cost.

### Activities

1. Select a small, approved internal query sample with privacy review.
2. Define a response engine and a shadow engine. Persist only redacted query
   IDs/hashes, traces, scores, canonical citations, and comparison outcomes.
3. Add sampling and rate limits, for example a feature flag plus an explicit
   allowlist—not implicit user traffic sampling.
4. Ensure a shadow failure never changes the user-visible response.
5. Compare results using the PV-04 scorer and classify disagreements:
   source mismatch, factual mismatch, taxonomy mismatch, safety mismatch,
   latency regression, or expected alternate grounding.
6. Review traces weekly/at an agreed cadence and convert recurring issues into
   regression fixtures.

### Success measures

- zero user-visible failure caused by shadow execution;
- no unresolvable v2 citations;
- no unexpected provider/cost growth beyond the approved sample;
- disagreement cases reviewed and categorized, not ignored.

### Acceptance gate PV-05

- Shadow results are stable enough for a v2 internal-default pilot.

---

## PV-06 — Feature-flag promotion, rollback, and legacy retirement

### Promotion steps

1. Pin target corpus/taxonomy/schema versions and capture a pre-promotion
   baseline.
2. Set `QUERY_ENGINE=v2` in staging/internal configuration only.
3. Run the full PV-04 suite and baseline collector against that configuration.
4. Confirm `/api/status/data-planes`, `/api/query`, `/api/chat`, and UI trace
   all report the same serving engine/corpus version.
5. Approve promotion only after PV-01 through PV-05 gates pass.
6. Promote through an allowlist or controlled percentage, with a named owner
   for each expansion step.

### Rollback procedure

1. Change `QUERY_ENGINE=legacy`.
2. Verify one traditional, one ContextGraph, one chat, and one safety fixture.
3. Preserve target corpus, graph, ledger, and traces for diagnosis; do not
   delete or rebuild data while investigating.
4. Record rollback cause, affected corpus version, request IDs, and exact trace
   fields in the incident record.

### Legacy retirement preconditions

Do not remove legacy retrieval or local Streamlit fallback until:

- v2 is the default for the agreed observation period;
- two comparable baseline reports show no provenance/safety regression;
- rollback has been exercised;
- current documentation no longer states outdated topology or metrics; and
- archive/retention approval is documented for legacy indexes and graph export.

---

## Dependency-ordered backlog

| ID | Work item | Depends on | Definition of done |
|---|---|---|---|
| PV-01 | Recreate interpreter/venv and preflight | — | Test command starts and environment is recorded. |
| PV-02 | Separate mock contract tests from real e2e | PV-01 | Reports label their execution mode accurately. |
| PV-03 | Implement/disable v2 cache correctly | PV-01 | Trace and tests reflect actual cache behavior. |
| PV-04 | Repair v2 history normalization/rewrite | PV-01 | Multi-turn semantic fixtures pass. |
| PV-05 | Bind corpus version to physical stores | PV-01 | Two corpus versions cannot cross-query. |
| PV-06 | Enforce query-mode and schema-activation contracts | PV-01 | Modes/schema failures are tested and explicit. |
| PV-07 | Produce target corpus/graph integrity reports | PV-03–PV-06 | All target records are ID-joinable. |
| PV-08 | Create real HTTP parity fixture suite | PV-07 | Fixtures use canonical expected source IDs. |
| PV-09 | Run and remediate parity evaluation | PV-08 | Independent quality gate passes. |
| PV-10 | Run restricted shadow pilot | PV-09 | Stable, cost-controlled comparison evidence exists. |
| PV-11 | Staged v2 promotion and rollback drill | PV-10 | Promotion/rollback acceptance record exists. |
| PV-12 | Legacy retirement | PV-11 | One active path remains after retention approval. |

## Definition of success

The next phase is successful when the v2 engine is not merely present and fast,
but independently proven to retrieve from the selected canonical corpus, cite
resolvable provenance, use history and cache exactly as its trace claims, pass
real HTTP evaluation, and switch/roll back safely through configuration.
