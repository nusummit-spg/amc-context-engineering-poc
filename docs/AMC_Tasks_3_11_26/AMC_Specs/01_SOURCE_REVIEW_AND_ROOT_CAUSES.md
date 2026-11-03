# 01 — Source Review, Root Causes and Prioritized Diagnosis

**Review pin**: `e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0` (`amc-dev`). GitHub file references below are for review provenance. The full live pipeline was not executed.

## A. CSV findings: grounded in examined source

| ID | Severity | Observed code behavior | Failure mechanism / remediation |
|---|---|---|---|
| CSV-01 | P0 | `engine/document_extractors.py::extract_csv_text_full` defaults to `CSV_MAX_PAGES` (50 × 25 rows) and stops once the page limit is reached. | In that extractor path, a 16,245-row file can be truncated to 1,250 records. A warning does not prevent incomplete publication. Use an explicit completeness check; canonical tabular ingest must process all rows. |
| CSV-02 | P1 | `ingestion/parsers/csv.py` groups several CSV rows as text sections; `scripts/ingest_csv.py` separately serializes individual rows to a vector store. | Competing ingestion representations make corpus parity and exact row addressing difficult. Consolidate one structured ingest pipeline; keep semantic row summaries as secondary retrieval artifacts. |
| CSV-03 | P0 | `services/scheme_aggregation_service.py::_aggregate_schemes` groups on `Scheme_Name`, and multiple methods calculate `SUM(Average_AUM_Cr)` directly over raw row variants. | Cross-AMC collisions, duplicates, mixed dates, repeated plan/option observations and incompatible AUM grains may yield incorrect financial totals. Define canonical identity, unit, time window, and metric rules with data steward. |
| CSV-04 | P1 | `get_top_schemes` emits `total_unique_schemes=len(top_schemes)`, hardcoded `data_completeness=0.98`, and per-scheme `plan_data_completeness=1.0` after dropping missing AUM rows. | Results contain misleading totals/completeness. Compute from source snapshot, using numerator, denominator, null count, and excluded records. |
| CSV-05 | P1 | `get_top_nav_schemes` defaults to `Open Ended`, `Equity`, `Growth`, and IDCW exclusion; the fast-path chooses filters via regex. | An unspecified question may silently become a filtered question. Use explicit filter parsing and echo applied filters in every result. |
| CSV-06 | P1 | The NAV ranking sorts numeric NAV without an explicit as-of-date requirement or same-date comparability rule. | Values from different dates can be compared as if simultaneous. Require `as_of` or a documented cutoff/comparability policy; disclose exclusions. |
| CSV-07 | P0 | Fast-path aggregation catches exceptions and returns `None`, causing ordinary vector/LLM retrieval to continue. | An exact numeric question can become an approximate generative response when its authority fails. Return `STRUCTURED_SOURCE_UNAVAILABLE`, not a false numeric answer. |
| CSV-08 | P1 | The fast-path constructs synthetic citation objects, quality_score=1.0, and fixed timing values (e.g. 2 ms in one trace). | Citations and telemetry are not independently anchored to actual source rows or measured execution. Build proof objects and instrument timings around actual operations. |
| CSV-09 | P1 | Several fast paths are keyword/regex based and the route definitions for scheme aggregation are absent from `main.py`'s central router registration list. | Misrouting and mismatched source links/API contracts are possible. Replace with a typed intent plan; mount and test intentionally supported routes. |
| CSV-10 | P1 | `backend/data/source_docs/chunks/manifest.json` declares 22 chunks covering 16,245 rows; there is no demonstrated end-to-end activation guarantee that all chunks are query-visible in graph and vector stores. | A manifest is not a reconciled materialization report. Compare raw row counts, unique row IDs, indexes, measures, and active data-plane versions before publish. |
| CSV-11 | P1 | Sample rows in chunk 001 have identical Launch_Date and Closure_Date; `is_active=pd.isna(Closure_Date)` in aggregation code. | The column's operational meaning is not established; active-state inference may be wrong. Validate source semantics and define closure state as explicit nullable, audited status. |
| CSV-12 | P1 | `get_dataset_summary()` returns a hardcoded `January - March 2026` string in some paths. | Can misstate the relevant reporting period when data changes. Derive reporting period from selected snapshot and reject mixed-period aggregation unless policy permits. |

## B. AMC, Feedback and Repair findings

| ID | Severity | Observed code behavior | Recommended control |
|---|---|---|---|
| GOV-01 | P0 | `compliance/security.py::get_client_role` derives role from `X-User-Role` and uses `Role.ADMIN` when absent. | Resolve authorization from authenticated server-managed principal and tenant; deny unauthenticated or ambiguous identity. |
| GOV-02 | P0 | Some `admin`, `ingest`, `graph`, `files`, and `query` endpoints declare no mandatory `CurrentUser` dependency. | Global deny-by-default auth plus per-route policy tests; limit public endpoints to documented health/static routes. |
| GOV-03 | P0 | `services/repair_integration.py` sets `approved=(confidence>=.95 and risk==LOW)` and can automatically promote patches. | Disable automatic publication of finance/regulatory changes. Confidence is never sufficient authorization. Require source proof, deterministic tests, reviewer approval and release. |
| GOV-04 | P0 | `retrieval/orchestrator.py::_apply_correction_patches` applies returned patches at confidence>=0.70 without requiring explicit published state in the shown branch. | Filter solely to `ACTIVE` approved, version-valid patches; quarantine pending patches and never present them as trusted source. |
| GOV-05 | P0 | `graph/correction_patch_layer.py::apply_patches_to_context` inserts an imperative instruction to use a pending correction where confidence>=0.70. | Never turn untrusted feedback into instructions; structured advisory annotation, not prompt content or truth override. |
| GOV-06 | P0 | `services/promotion_service.py::_execute_graph_mutation` may return when the Neo4j driver is unavailable; caller proceeds to mark proposal as applied. | Require mutation receipt/transaction ID and postcondition verification before SQL status becomes `APPLIED`; otherwise `RETRYABLE_FAILED`. |
| GOV-07 | P1 | Multiple local/HTTP repair adapters, graph patch layer, service client, feedback package and DB records coexist. | Select a single authoritative state store; adapters may cache read models but not invent independent truth. |
| GOV-08 | P1 | Feedback lifecycle has passive detectors, timeouts, issue matching, batch evaluation and approval paths. | Treat silence and abandonment as `UNKNOWN`; introduce evidence completeness, triage, conflicts, duplicate suppression and SLA rules. |
| GOV-09 | P1 | Repair task created through remote service before local DB `repair_task_id` commit. | Use transactional outbox and idempotency keys to recover from remote success/local commit failure. |
| GOV-10 | P1 | Graph and vector ingest are not jointly transactional; `ingestion/pipeline.py` catches partial graph-write failures and still proceeds to activation. | Stage, validate, atomically move active manifest pointer; degrade/read-only only when required data planes have consistent published version. |

## C. Assurance, operations, reporting findings

- The 25-case `run_phase5_evaluation_benchmark.py` embeds ground truth into both mock context and mock answer. Its result is **not** live RAG performance evidence. `app/evaluation/scorer.py` implements keyword-overlap heuristics, text-length-based recall, and derived relevance, not independently measured RAGAS. Its report marks 24.5% recall `PASSED` against >80%.
- `evaluation_metrics_report.json` (dated 2026-08-31) includes unrelated queries answered with borrowing-limit text and approximately 16.9-second average query durations. Historical evidence, **not** proof the exact failure persists at the reviewed branch head.
- `docker-compose.yml` references absent Dockerfiles, and a missing Streamlit service directory; no `.github/workflows` directory appears in the reviewed tree. It should not be assumed deployment-ready.
- Existing tests cover meaningful segments (authentication, session isolation, cache isolation, repairs, financial intent) but do not establish full cross-endpoint authorization or the live benchmark outcomes.
- The shared repo contains source documents, chunked CSV and vector/index artifacts; verify access rights, privacy classification, licensing and artifact retention before release.

## D. Root-cause tree for incorrect CSV answers

1. **Row coverage**: selected extractor truncation; inconsistent ingestion generations; non-atomic activation; index drift.
2. **Business semantics**: grain errors; wrong composite identity; period mismatch; NAV vs quarterly AAUM confusion; duplicates; null handling; unverified closure meaning.
3. **Query planning**: regex misrouting; ambiguous `average`/`top`; implicit default filters; wrong fallback to LLM.
4. **Computation**: direct sum of per-row AUM with unspecified additivity; raw floats; unnormalized units; group-by scheme display name.
5. **Explanation**: unverified citations; high confidence hardcoded; patched pending facts override documents; arbitrary narrative introduced.
6. **Measurement**: unit tests assert shape or keywords; simulated benchmark; no independent live golden-answer bank; dashboards overclaim performance.

## E. Bounded diagnosis workflow (do before coding)

1. Lock the branch SHA, active corpus version, data manifest, provider versions and local config; hash all inputs.
2. Capture at least 30 failing/ambiguous CSV queries and 15 correct PDF control queries, with actual response, trace, intended interpretation and expected answer.
3. For each CSV request persist plan (`intent`, `metric`, `filters`, `grouping`, `as_of`, `dataset_version`) and whether fast path, SQL, graph, vector or patch was involved.
4. Run source-row checksum reconciliation: 16,245 declared vs parsed vs validated vs staged vs published; check row-key collisions and all 22 chunk boundaries.
5. Recompute gold using direct SQL over a steward-approved canonical snapshot. Do not use LLM answers as labels.
6. Compare public API output to exact gold and inspect unsupported claims, missing evidence and source-period errors separately.
7. Failure categories must be mutually distinguishable (`ROUTING`, `ENTITY`, `ROW_COVERAGE`, `PERIOD`, `METRIC`, `AGGREGATION`, `CITATION`, `PATCH_CONTAMINATION`, `AUTH`, `UNKNOWN`).

## F. Source links (stable branch snapshot)

- https://github.com/nusummit-spg/amc-context-engineering-poc/blob/e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0/backend/app/engine/document_extractors.py
- https://github.com/nusummit-spg/amc-context-engineering-poc/blob/e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0/backend/app/ingestion/parsers/csv.py
- https://github.com/nusummit-spg/amc-context-engineering-poc/blob/e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0/backend/app/services/scheme_aggregation_service.py
- https://github.com/nusummit-spg/amc-context-engineering-poc/blob/e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0/backend/app/retrieval/fast_path_interceptor.py
- https://github.com/nusummit-spg/amc-context-engineering-poc/blob/e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0/backend/app/services/repair_integration.py
- https://github.com/nusummit-spg/amc-context-engineering-poc/blob/e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0/backend/app/graph/correction_patch_layer.py
- https://github.com/nusummit-spg/amc-context-engineering-poc/blob/e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0/backend/app/services/promotion_service.py
- https://github.com/nusummit-spg/amc-context-engineering-poc/blob/e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0/backend/scripts/run_phase5_evaluation_benchmark.py
- https://github.com/nusummit-spg/amc-context-engineering-poc/blob/e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0/backend/app/evaluation/scorer.py
