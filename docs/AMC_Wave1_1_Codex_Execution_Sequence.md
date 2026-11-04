# AMC Context Engineering — Wave 1.1 Corrective Execution Sequence

**Date:** 2026-11-03  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Starting branch:** `feature/wave1-canonical-data-and-typed-queries`  
**Audited SHA:** `06cf9755f4b3dde3e9a24a430973f4bf86ed711d`  
**Status:** Architecture/implementation handoff, not evidence of completed code changes.

## 1. Read these original files in this order

All are already on the feature branch at `docs/AMC_Tasks_3_11_26/AMC_Specs/`. You do **not** need to download the old ZIP.

1. `README_START_HERE.md` — general context and non-negotiables.
2. `01_SOURCE_REVIEW_AND_ROOT_CAUSES.md` — root causes; compare with newly implemented code before changing anything.
3. `08_OPEN_DECISIONS.md` — data-steward decisions on AAUM grain, scheme IDs, closure-date semantics, cross-quarter rules, deployment topology.
4. `02_TARGET_ARCHITECTURE_AND_CONTRACTS.md` — data contracts and trust boundaries used by all subsequent changes.
5. `05_ASSURANCE_SECURITY_RELEASE_GATES.md` — mandatory release gates; start applying from first batch.
6. `03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md` — **primary implementation specification for Wave 1.1**.
7. `04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md` — **primary specification for approval/promotion fixes**.
8. `06_GOALS_AND_TASKS.md` — original 196-task backlog and original G01–G14 IDs; use as issue/task index, **not chronological execution order**.
9. `07_CODEX_EXECUTION_PLAYBOOK.md` — packaging, test and audit evidence; use for every batch.

Related task fixtures are at `docs/AMC_Tasks_3_11_26/AMC_Tasks/`. Already claimed as implemented in Wave 1: `remediation/wave1_canonical_typed_queries/WAVE1_PROGRESS.md`. Treat all checkmarks as *reported*, not automatically verified.

## 2. Implement in this sequence (not file-number order)

| Sequence | Wave/batch | Source specs | Goal mapping | W1.1 tasks | Exit gate |
|---|---|---|---|---|---|
| 0 | Freeze + reproduce | 01, 05, 06, 07, 08 | G01, G13 | Preparation for 13 | Freeze SHA/data hashes; capture ≥30 failed CSV queries + ≥15 working PDF/TXT controls + execution traces |
| 1 | **Immediate security & repair containment** | 02, 04, 05, 06, 07 | G02, G10 | **10, 11** + protective portion of 12 | No forged-header elevation, anonymous mutators, auto approval, unapproved patch serving, or unverified promotion |
| 2 | **Financial meaning & exact calculation** | 03, 05, 06, 08 | G03, G05 | **01–05** | Metric operation gate, Decimal-exact totals, canonical identities, same-row NAV date pairing and explicit periods |
| 3 | **Data ingestion, versioning & evidence** | 02, 03, 05, 06 | G04, G05, G07 | **06, 07, 09** | Valid manifest, per-field validity, safe version activation, full contributing-row proof |
| 4 | **AMC routing and API parity** | 02, 03, 05, 06 | G05, G06, G07, G08 | **08** + integration from 09 | All chat/query/stream routes fail closed on structured data errors; PDF/TXT behavior preserved |
| 5 | **Feedback → Repair publication completion** | 04, 02, 05, 06 | G09–G12 | Remaining **12** | Authenticated four-eyes approval, real mutation receipt, idempotency, compensation and rollback |
| 6 | **Independent tests & release assurance** | 05, 06, 07 | G13, G14 | **13, 14** | Clean clone, reproducible DB initialization, independent gold metrics, negative-auth tests, CI, recovery drill |

**Scheduling:** Start Batch 0 and Batch 1 immediately. Batch 2 can be engineered in parallel with the security PR, but **AAUM SUM/ranking remains BLOCKED** until a named data steward signs off on additivity/grain semantics. Merge separately: security, financial correctness, routing, and governance/reliability. Do not silently enable disputed data calculations.

## 3. Wave 1.1 — 14 precise corrective tasks

### W1.1-01 — Mandatory metric-policy enforcement (P0)
**Files:** `backend/app/tabular/{contracts,planner,executor}.py`. AAUM is marked `PENDING_APPROVAL` and allows only exact lookup, yet the planner executes SUM/AVG/rank. Add explicit operation/grain/period/approval metadata to QueryPlan. Enforce policy **inside QueryExecutor** for every caller; never rely only on `planner.validate_plan()` invoked by tests. **Acceptance:** Directly constructed unapproved plans cannot execute, and return `METRIC_POLICY_BLOCKED`.

### W1.1-02 — Exact arithmetic (P0)
**Files:** planner, executor, `backend/app/services/scheme_aggregation_service.py`. Replace `SUM(CAST(aaum_crore AS REAL))`, `ROUND`, and Python-float calculation for authoritative metrics with Decimal/integer-scale exact operations and documented rounding. **Acceptance:** independently computed high-precision values, ties and boundary cases match exactly.

### W1.1-03 — Canonical identity/grain (P0)
**Files:** `csv_excel_loader.py`, contracts, repository, planner. Stop grouping schemes solely by `scheme_display_name`. Use validated canonical AMC/scheme/plan IDs; collisions and aliases require deterministic resolution or quarantine. **Acceptance:** distinct same-name schemes cannot merge, and plan variants are not double counted.

### W1.1-04 — NAV same-observation correctness (P0)
**Files:** repository, planner, aggregation facade. `MAX(nav_per_unit)` and `MAX(nav_date)` can refer to different records; `LIMIT 1` can hide ambiguity. Implement uniquely identified plan/date observation, deterministic as-of rule, explicit ambiguity handling. **Acceptance:** same code with two plans, out-of-order dates and ties return correct observation or ambiguity, not arbitrary row.

### W1.1-05 — Period & filter policies (P0)
**Files:** planner, facade, fast-path interceptor. Remove implicit quarter or NAV category/plan narrowing, or show snapshot-defined defaults explicitly and consistently. No cross-period AAUM sum. **Acceptance:** query receipts include period, date, population and all applied filters; ambiguous scope produces a clear error/choice.

### W1.1-06 — Manifest and field validity (P0)
**Files:** `backend/app/tabular/csv_excel_loader.py`, ingestion runner, repository. Manifest fields are `original_rows` and `chunk_count`, but loader currently checks `total_rows` and `num_chunks` with hardcoded fallbacks. Verify every chunk hash, boundaries and total rows; distinguish source-row valid, NAV valid and AAUM valid; quarantine malformed observations. **Acceptance:** broken manifest, missing/duplicate chunk, malformed date/number and partial dataset block activation.

### W1.1-07 — Safe data version activation / fresh clone (P0)
**Files:** repository, loader, startup/health/deployment. Introduce `STAGED → VALIDATED → APPROVED → ACTIVE`; atomic version pointer only after all required checks; protect prior active version on failure. Initialize typed DB explicitly during deployment. **Acceptance:** fresh checkout, restart, interrupted staging, re-run and rollback work with an expected dataset hash.

### W1.1-08 — Remove silent financial fallback (P0)
**Files:** `scheme_aggregation_service.py`, `retrieval/fast_path_interceptor.py`, `retrieval/orchestrator.py`, query/chat/stream entry points. DB absence currently loads old Pandas logic; fast-path error may fall into vector/LLM synthesis. Block numeric fallback with typed error codes (`STRUCTURED_SOURCE_UNAVAILABLE`, `AMBIGUOUS_QUERY`, `METRIC_POLICY_BLOCKED`, `NO_MATCH`). **Acceptance:** forced DB outage produces a non-fabricated error in **every API path**, including streaming/multi-turn.

### W1.1-09 — Aggregate evidence provenance (P1)
**Files:** repository, planner, executor, response adapters and citations. Result-row hashes alone are not source proof; a non-grouped `source_row_id` selected with aggregates is not all contributors. Persist sorted contributing row IDs/hashes, dataset hash/version, metric-version/approval, filters, grain, exact result and calculation lineage. **Acceptance:** external verifier reproduces each gold aggregate from its contributing inputs.

### W1.1-10 — Identity-derived access (P0)
**Files:** `backend/app/compliance/security.py`, `api/routes/{admin,ingest,graph,files,query,governance}.py`, quotas, repair service. Rejecting a missing `X-User-Role` is insufficient: caller can still claim admin. Protect all sensitive routes using verified `CurrentUser`, server-scoped roles/tenant and service identity; remove known temporary password (`Welcome@2026`); bound uploads. **Acceptance:** anonymous and forged-header calls cannot list/create users, ingest, alter graph, download another tenant's document or approve repair.

### W1.1-11 — One Repair approval authority (P0)
**Files:** `backend/app/api/routes/governance.py`, `backend/app/services/repair_integration.py`, `packages/amc-repair-engine/src/amc_repair/{server,governance,patch_layer}.py`. Other batch routes still approve based on confidence; repair API accepts `approved` in caller payload. Enforce authenticated approver, separation of proposer/approver, no caller approval field, mandatory human approval for financial/regulatory changes. **Acceptance:** high-confidence, direct microservice, batch and alternative endpoints cannot bypass approval.

### W1.1-12 — Publication result integrity & rollback (P0)
**Files:** `backend/app/services/promotion_service.py`, governance, graph/vector adapters, repair linkage. No successful APPLIED state unless canonical commit actually occurred. Missing Neo4j driver must fail, not be recorded as applied. Add idempotency keys, outbox/retry, verified receipts, cache refresh and compensation. **Acceptance:** graph outage, failed reindex, duplicate event, ack lost and rollback leave consistent versioned state with no phantom success.

### W1.1-13 — Independent correctness and PDF/TXT regression (P0)
**Files:** `backend/tests/`, scripts and golden case fixtures. Existing 17 tabular tests and 36 reported overall prove some functionality, not independent accuracy. Build **≥30 reproduced CSV failures**, independently approved numerical gold (actual exact totals), ≥15 then ≥50 PDF/TXT controls, mixed-source tests, adversarial entity/period data, actual API runs. **Acceptance:** 100% agreement on curated critical financial gold and zero unsupported release-critical claims; tests assert exact values rather than only sort order/existence.

### W1.1-14 — CI, deploy and release proof (P0)
**Files:** `.github/workflows`, Docker/Compose, backend startup. No CI runs observed for reviewed SHA. Add clean-clone provisioning, unit/contract/integration tests, security negative tests, source data validation, stream non-stream parity, recovery drills and immutable SHA/data/metric-version report. **Acceptance:** reproducible CI logs, no untested release claims, documented canary and rollback, clear PASS/REVIEW/BLOCK verdict.

## 4. Non-negotiable stop rules

- Data steward must approve AAUM grain/additivity, `Closure_Date` interpretation, cross-quarter rules and identity policy; **do not invent signoff**. If unavailable, block affected metric operations while implementing other work.
- No source/user prompt/LLM confidence may grant approval. Pending repairs must never become serving truth.
- Do not update production databases, publish canonical repair patches or deploy without authorized operator action.
- No silent numerical legacy or generative fallback; preserve current healthy PDF/TXT behavior.
- No committed secrets, passwords, customer data, or unapproved proprietary source documents in test artifacts.
- No task marked DONE based only on a source file or documentation checkmark; test execution must be evidenced.

## 5. Deliverables from Codex after EACH bulk batch

Use `remediation/wave1_1/<batch-id>/` for sanitized evidence:

- `STATUS.md`: original goal/task IDs + W1.1 IDs: DONE / PARTIAL / BLOCKED + proof and dependencies.
- `CHANGES.md`: files, design decision, behavior before/after, compatibility risks.
- `TEST_COMMANDS.md` and `TEST_RESULTS.json`: exact test commands, exit status, environment, actual failures, CI IDs.
- `FINANCIAL_GOLD.csv` / sanitized proof manifest: independent expected results and row/hash anchors (store protected data privately).
- `SECURITY_ROUTE_MATRIX.json`: complete route/auth/tenant checks.
- `REPAIR_FAILURE_DRILLS.json`: approval, outage, retry, rollback outcomes.
- `RELEASE_GATE.md`: PASS / REVIEW / BLOCK, release blockers, approved version/hash/SHA.
- `ROLLBACK.md`: restoration steps actually tested.

## 6. Copy/paste Codex instruction

```text
Work on a new remediation branch based on
feature/wave1-canonical-data-and-typed-queries at SHA
06cf9755f4b3dde3e9a24a430973f4bf86ed711d.

First read docs/AMC_Tasks_3_11_26/AMC_Specs/README_START_HERE.md,
01_SOURCE_REVIEW_AND_ROOT_CAUSES.md,
08_OPEN_DECISIONS.md,
02_TARGET_ARCHITECTURE_AND_CONTRACTS.md,
05_ASSURANCE_SECURITY_RELEASE_GATES.md,
03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md,
04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md,
06_GOALS_AND_TASKS.md and
07_CODEX_EXECUTION_PLAYBOOK.md.
Then read AMC_Wave1_1_Codex_Execution_Sequence.md.

Execute BATCH <0/1/2/3/4/5/6> from section 2, implementing all listed
W1.1 tasks as a substantial, internally coherent work package.
Verify existing code before editing; reuse and harden Wave 1 typed-data
components instead of rewriting them. Maintain AMC Core → Feedback → Repair.

Rules: Never trust client role/tenant headers; never auto-approve repair;
never mark graph publication applied without a verified commit; never use
REAL/float for authoritative financial sums; never execute unapproved AAUM
aggregations; never fabricate financial answers through an LLM or legacy
fallback; preserve PDF/TXT regressions; do not deploy or mutate live data.

Run unit, contract, negative-security, exact financial gold, API/stream,
repair failure-injection and clean-start tests relevant to the batch.
Output code/tests, task-by-task evidence, commands, failed cases, risks,
rollback, and PASS/REVIEW/BLOCK classification. Do not mark unrun tests PASS.
Any unresolved business semantic decision = BLOCK affected release operations.
```

## 7. What to send for next independent CTO audit

New commit/PR link, actual CI results and logs, complete task-status matrix, active dataset hash, metric registry approval version, failure/gold dataset, PDF/TXT regressions, full role/tenant authorization matrix, and Repair governance/rollback receipts. Audit against the exact SHA; do not rely on status documents alone.

**Recommendation:** Start with Batch 0 + Batch 1 now. Continue Batch 2 code work separately, blocking AAUM SUM until data-steward approval. Do not treat G04/G05 as fully complete just because the Wave 1 report says 14/14.
