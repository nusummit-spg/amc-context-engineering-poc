# NuSummit AMC Context Engineering — Wave 1.2
## CTO Re-Audit, Prioritized Implementation Roadmap and Codex Agent Handoff

**Prepared:** 2026-11-04 (India)  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Source branch:** `amc-dev`  
**Pinned source HEAD:** `af35d86b836884e6527f35b334e14848906e9f57`  
**Comparison baseline:** `910bae72030cbf641badbdb6e2c6fe82b78a9479` (prior Wave 1.1 audit)  
**Observed comparison:** `amc-dev` ahead by 2 commits; 37 changed paths.  
**Review basis:** Read-only GitHub source inspection and committed test/report artifacts; no local Python/DB/service test execution or production verification by this reviewer.  
**Current recommendation:** **BLOCK production/release promotion; PROCEED with a controlled Wave 1.2 remediation branch.**

> **Agent instruction:** This document is the implementation contract. Execute concrete code changes and actual tests, not just an updated checklist. The earlier 196-task blueprint remains the design reference. This file supersedes prior *execution sequencing* where current source demonstrates completed work or previously missed defects.

## 0. Source links and existing artifacts

- [Source branch `amc-dev`](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/amc-dev)
- [Pinned source commit](https://github.com/nusummit-spg/amc-context-engineering-poc/commit/af35d86b836884e6527f35b334e14848906e9f57)
- [Wave 1.1 P0 handoff (in repository)](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/amc-dev/docs/AMC_Wave1_1_P0_Closure_Agent_Handoff.md)
- [Wave 1.1 P0 reports](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/amc-dev/remediation/wave1_1/p0_closure)
- [CTO original specifications](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/amc-dev/docs/AMC_Tasks_3_11_26/AMC_Specs)
- [Existing Wave 1 financial progress](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/amc-dev/remediation/wave1_canonical_typed_queries/WAVE1_PROGRESS.md)

Read these original documents at the start of work, without treating their earlier DONE assertions as audit evidence:

1. `docs/AMC_Tasks_3_11_26/AMC_Specs/README_START_HERE.md` — program context.
2. `01_SOURCE_REVIEW_AND_ROOT_CAUSES.md` — observed prior failures.
3. `02_TARGET_ARCHITECTURE_AND_CONTRACTS.md` — target contracts and topology.
4. `03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md` — primary quantitative correctness design.
5. `04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md` — governance and state transitions.
6. `05_ASSURANCE_SECURITY_RELEASE_GATES.md` — acceptance, safety and rollback.
7. `06_GOALS_AND_TASKS.md` — original 14 goals / 196 task IDs.
8. `07_CODEX_EXECUTION_PLAYBOOK.md` — execution and evidence requirements.
9. `08_OPEN_DECISIONS.md` — unresolved business/data-steward questions.

**Do not roll back valuable completed improvements.** Preserve the new JWT `CurrentUser` route enforcement, invitation lifecycle, missing promotion-exception definitions, security tests, and confidence-only batch-promotion disabling **after verifying them against actual behavior**.

## 1. Confirmed branch delta and revised assessment

### Changes observed in `amc-dev` since the prior audit

- `backend/app/api/routes/admin.py` substantially rewritten for authenticated user CRUD, secure invitation enrollment and selected ingestion/cache controls.
- `backend/app/api/routes/governance.py` now uses JWT-derived `CurrentUser` instead of `Depends(get_client_role)` and its `/run-batch` path categorizes proposals for review rather than approving based on confidence.
- `backend/app/api/routes/ingest.py`, `files.py` and `graph.py` have mandatory user dependencies on their route handlers.
- `backend/app/api/routes/auth.py` adds an invitation acceptance endpoint and `backend/app/schemas/invitation_token.py` adds persistent enrollment state.
- `backend/app/exceptions/__init__.py` now defines `PromotionFailedError` / `PromotionVerificationError`, fixing the missing import path previously observed.
- `packages/amc-repair-engine/src/amc_repair/governance.py` now recommends human review for high-confidence patches rather than auto-approving them.
- `backend/tests/test_sec01_universal_auth.py` and `backend/tests/test_sec01_remaining_routes_and_flow.py` are actually present. A committed progress log reports **24 + 9 = 33 passing tests**, but no associated branch GitHub Actions runs or commit status checks were found; reviewer did not reproduce those results.

### Outstanding source-verified gaps

| Severity | ID | Evidence at pinned HEAD | Why it matters |
|---|---|---|---|
| **P0** | COMP-01 | New Admin router has **8** route declarations versus **24** in prior commit; **18 prior route patterns removed**. React `mf-context-engine/src/services/api.js` still calls several deleted routes. | Significant UI/API regression. Existing dashboards/admin work can break silently even though auth tests pass. |
| **P0** | REP-10 | Independent Repair microservice `server.py` still exposes create/approve/batch-approve/promote endpoints without authenticated principal dependencies in the route signatures. | Main-app JWT alone does not ensure microservice governance identity. Check network reachability separately; source permits direct calls if reachable. |
| **P0** | REP-11 | Governance main endpoints `/approve/{patch_id}`, `/batch-approve`, `/promote/{patch_id}`, and proposal review require authorized role but do not establish independent proposer-vs-approver separation in reviewed handlers. | Four-eyes remains unproven; approval may be promoted immediately rather than staged and verified. |
| **P0** | REP-12 | `CorrectionPatch` microservice model has `approved` but no persisted, authoritative `ACTIVE` status; orchestrator checks `status == ACTIVE` on one path but fallback patch layers filter only `approved`. | Contradictory serving eligibility; can silently suppress intended corrections or allow approved-but-not-published corrections. |
| **P0** | REP-13 | `repair_integration.py` still creates synthetic patch vector chunks before human approval. | Pending/corrected claims could contaminate retrieval unless vector isolation is proven. |
| **P0** | PUB-10 | `promotion_service.py::_trigger_reindex()` logs only, yet vector proposal is marked `applied`; graph postcondition verifies existence rather than exact expected value. | False publication success and wrong canonical facts. |
| **P0** | PUB-11 | `apply_approved_proposals()` performs external graph commits while sharing one SQLAlchemy session for multiple proposals; a later `db.rollback()` can roll back SQL metadata for earlier committed external changes. | State divergence, duplicate retries and partial-failure data loss. |
| **P0** | FIN-10 | `tabular/contracts.py` marks AAUM summation pending approval; `planner.py` still executes sums/averages; `executor.py` does not enforce comprehensive metric policy. | Wrong/semantically unapproved financial totals can be returned as authoritative. |
| **P0** | FIN-11 | `planner.py` and compatibility service use `CAST(... AS REAL)` and Python `float`; `GROUP BY scheme_display_name`; mixed NAV `MAX` expressions. | Precision, identity and date-pairing errors persist. |
| **P0** | FIN-12 | `SchemeAggregationService` still offers legacy CSV/Pandas fallback; fast-path misses/exceptions can return to general retrieval. | Original CSV numeric-hallucination failure mode remains open end-to-end. |
| **P1** | ING-10 | `csv_excel_loader.py` uses declared `total_rows`/`num_chunks` fallbacks where actual manifest schema and hashes require stricter binding; activation checks row count primarily. | Source integrity and completeness may not be proved by a 16,245-row count alone. |
| **P1** | SEC-10 | Enrollment stores invitation token verbatim and returns it to admin; tenant selection and authorization need role/ownership audit. | Token theft/replay and tenant-scoping risks; hash tokens and constrain issuance. |
| **P0** | OPS-10 | No GitHub Actions runs for `amc-dev` found; no `.github/workflows` directory observed in current tree. Docs contain inconsistent `VERIFIED/PASS`, `PARTIAL`, and `TESTING PENDING` statuses. | Insufficient independent release evidence. |

**Interpretation:** fixes are **partially completed**. No unconditional claims of “all P0 issues solved,” “financial accuracy achieved,” or “production ready” are supported by this read-only audit.

### Admin-route compatibility regression — exact analysis

The following **18 prior `admin` route patterns** are absent from the rewritten router (verify whether intentionally moved elsewhere; do not assume so):

```text
POST /api/admin/users/sync
GET  /api/admin/rbac
GET  /api/admin/audit
POST /api/admin/ingestion/staleness
GET  /api/admin/ingestion/tasks
GET  /api/admin/ingestion/tasks/active
GET  /api/admin/ingestion/notifications
POST /api/admin/ingestion/notifications/{task_id}/read
POST /api/admin/ingestion/notifications/read-all
GET  /api/admin/ingestion/proposed-edges
POST /api/admin/ingestion/edges/{edge_id}/confirm
POST /api/admin/ingestion/edges/{edge_id}/reject
GET  /api/admin/ingestion/compliance-report
GET  /api/admin/intent-cache/stats
GET  /api/admin/cache/stats
POST /api/admin/intent-cache/invalidate-domain
POST /api/admin/intent-cache/clear
GET  /api/admin/feedback/issues
```

**Observed still-active frontend callers** in `mf-context-engine/src/services/api.js` include `/admin/users/sync`, `/admin/rbac`, `/admin/audit`, `/admin/intent-cache/{clear,stats,invalidate-domain}`, `/admin/ingestion/staleness`, `/admin/ingestion/tasks`, `/admin/ingestion/proposed-edges`, `/admin/ingestion/edges/...`, and `/admin/ingestion/compliance-report`.

**Do not simply recreate all old routes insecurely.** For each, choose *restore with authenticated role/tenant policy*; *migrate to a verified replacement and update frontend*; or *retire intentionally with an explicit UX change and regression tests*. Flag unresolved public APIs as BREAKING and fail the compatibility gate.

## 2. Proposed execution order — bulk, reviewable PRs

| Order | PR/batch | Work scope | Original goals | Exit gate |
|---|---|---|---|---|
| **0** | **W1.2-R0 — Freeze / contract regression** | Pin HEAD, capture route diff, frontend consumers, active data and failing queries, create missing assurance harness foundation | G01, G08, G13 | Exact baseline and API compatibility matrix recorded; no release claim |
| **1** | **W1.2-R1 — Residual trust & Repair P0** | Restore/migrate Admin routes securely; microservice identity; proposer-approver separation; Repair state and vector isolation; publication recovery | G02, G09–G11 | SEC, REP and PUB gates pass on actual tests |
| **2** | **W1.2-F1 — Financial semantics and metric policy** | AAUM policy enforcement, exact Decimal aggregation, identity hierarchy, NAV/date semantics | G03, G05 | Disallowed calculations blocked; approved gold exact |
| **3** | **W1.2-F2 — Ingestion and versioned source proof** | Source manifest/hash checks, field-level validity, immutable dataset snapshots, atomic activation and startup health | G04, G07 | Clean ingestion, recovery and complete provenance pass |
| **4** | **W1.2-F3 — Typed routing, AMC contract & PDF/TXT parity** | All numeric surfaces fail closed; eliminate generative/legacy fallback; preserve API/frontend contracts | G05–G08 | End-to-end user queries and streaming/nonstreaming parity pass |
| **5** | **W1.2-Q1 — Feedback/Repair assurance and operations** | Evidence-linked feedback, idempotency, audit, CI, failure drills, release rubric | G09–G14 | Measured test/CI evidence; final release verdict |

**Concurrency:** R0 immediately; R1 is **release blocking**. F1 can start in a separate branch after writing fail-closed unapproved-AAUM policy, without waiting for a data steward to make all interpretations. Do not ship F1–F3 without R1 P0 closure. Use short, cohesive PRs within a bulk agent slot; preserve rollback boundaries.

---
## 3. W1.2-R0 — Freeze baseline, dependencies and observable regressions

### R0-01 — Reproducible baseline manifest
**Priority:** P0 prerequisite. **Code/outputs:** `remediation/wave1_2/R0/SOURCE_BASELINE.md`, `scripts/`, Docker/requirements, database/index manifests.

**Implement:** Record pinned code SHA; exact API version; Python/runtime/dependencies; deterministic and LLM path flags; active source-data, graph, FAISS, financial DB and cache version/hash. Treat actual dataset version as runtime information, not the code's hardcoded default. Freeze sanitized source-query traces and already-correct PDF/TXT controls. Do not copy proprietary source data into new public artifacts without authorization.

**Acceptance:** Fresh checkout can reconstruct an isolated test environment; an auditor can identify every active data/source/model revision behind any numeric response.

### R0-02 — Route and frontend contract reconciliation
**Priority:** P0. **Code:** `backend/app/main.py`, `backend/app/api/routes/admin.py`, `mf-context-engine/src/services/api.js`, other clients.

**Implement:** Generate OpenAPI/mounted route inventory for previous `910bae7` and current `af35d86`; list methods/path, payload/response schemas, authentication/tenant rules, all frontend references, and API removal decisions. Write browser-level and API contract tests for each active UI capability. Prefer compatibility adapters or coordinated frontend migration; never retain an insecure older implementation merely to satisfy the client.

**Acceptance:** Every still-used frontend endpoint resolves successfully and respects permissions; intended removals have updated UX and tests. **18 removed Admin route patterns must each have a documented disposition.** Do not silently drop ingestion lifecycle, audit logs, regulatory edge review, cache telemetry or feedback issue administration.

### R0-03 — Independent financial incident/golden baseline
**Priority:** P0. **Source:** original `G01-T04..T14`, `G13`. **Code:** `backend/tests`, `remediation/wave1_2/R0/`.

**Implement:** Freeze ≥30 observed incorrect CSV questions (including actual, expected, trace, dataset version, precise filter/time/metric), ≥15 existing correct PDF/TXT queries (expand to ≥50 before release), and quantitative expected results approved independently of the service under test. Do not generate expected numbers from the same planner being evaluated. Include negative/ambiguous/out-of-scope questions.

**Acceptance:** Gold is source-row/metric/version anchored; failures are independently reproducible, and every test has an owner and reason code. If historical incidents are unavailable, record **BLOCKED** rather than substituting synthetic observations without labelling them.

## 4. W1.2-R1 — Remaining P0 trust, Repair governance and publication

### R1-01 — Universal principal, role and tenant enforcement
**Priority:** P0. **Code:** `backend/app/api/deps.py`, `api/routes/{admin,audit,governance,ingest,files,graph,query,chat}.py`, `auth/service.py`, resource stores.

**Implement:** Confirm the user derived from a bearer session is immutable and authorized for the specific endpoint, entity, and tenant. Inventory all non-authenticated state-changing and sensitive reads, including deprecated/hidden routes. Use server-derived permissions, deny spoofed `X-User-Role`, `X-User-ID`, `X-User-Tier`, `tenant_id` and `authorized_by`. Inspect query/evidence/feedback item-level filtering and account enrolment for cross-tenant privilege elevation. Do not infer tenant identity from a department string or a shared `default` namespace in a real multi-tenant deployment.

**Tests:** Anonymous 401; bearer without scope 403; forged headers ignored; cross-tenant ID query denied; admin restrictions verified; allowed same-tenant requests succeed; no sensitive file/download leakage. Include test cases for newly reintroduced compatibility routes.

### R1-02 — Repair service-to-service authentication
**Priority:** P0. **Code:** `packages/amc-repair-engine/src/amc_repair/server.py`, main service clients, deployment/ingress manifests.

**Implement:** Protect create/get/list/approve/batch/reject/promote and governance APIs with an authenticated service principal and authorization scopes; pass verified end-user approver identity/audit context for human approvals. Adopt workload token or mTLS as appropriate; ensure service failure does not fall back to anonymous mutation. Health endpoint may remain explicitly public if appropriate. Do not count a private port/firewall as authorization without proof.

**Tests:** Direct unauthenticated Repair HTTP calls fail; forged service token fails; wrong service scope denied; signed service request succeeds only for intended operation; no bypass through batch or direct promote. **Do not claim SEC-04 complete until tests run against the separately started Repair service.**

### R1-03 — Explicit human authorization and four-eyes integrity
**Priority:** P0. **Code:** `backend/app/api/routes/governance.py` approval, batch, review and direct-promote endpoints; Repair microservice; SQL approval tables.

**Implement:** Separate `PENDING` proposal creation, `APPROVED` review, `STAGED` mutation, verified `ACTIVE` publication. Store `proposer_id`, `reviewer_id`, `approver_id`, immutable source/evidence version, approved values, time and role/tenant policy. Enforce `approver_id != proposer_id`. Reject self-approval, stale/revoked approvals, guessed patch IDs, an approver changing the approved data, and direct promotion of unapproved patches. Protect all routes through the same service-layer state-machine policy, not only handler checks. Main and independent microservice must be consistent. Auto-triage may recommend but may not approve; also avoid automatically **rejecting/deleting** a pending patch solely because confidence is low (currently independent Repair `run_batch` calls `reject_patch` when confidence < 0.5).

**Tests:** Self-approval forbidden; `confidence=1.0` stays pending; `approved=true` caller parameter cannot authorize; low confidence doesn't silently delete without an explicit policy; batch/direct/background routes share the same result; approval mutation has a verified audit event and cannot be replayed across tenants.

### R1-04 — Single Repair patch state and serving-eligibility contract
**Priority:** P0. **Code:** `packages/amc-repair-engine/src/amc_repair/{schemas,patch_layer}.py`, `backend/app/graph/correction_patch_layer.py`, `backend/app/retrieval/orchestrator.py`, caches and response adapters.

**Implement:** Persist states `PENDING`, `APPROVED`, `STAGED`, `ACTIVE`, `REJECTED`, `FAILED`, `ROLLED_BACK`, `SUPERSEDED`; define allowable transitions and actor permissions. Make `approved` an invariant of the persisted state, not a user-supplied setting. Implement one shared policy `is_serving_eligible(patch, principal, active_dataset, as_of)` used by all stores, local fallback, microservice, cache and query/stream. A missing/unknown status is **not ACTIVE**. Do not pass an unfiltered list to `apply_patches_to_context` after pre-filtering it merely for logging.

**Tests:** Direct cache/patch-layer retrieval; microservice and fallback mode; unknown status; outdated version; mismatched tenant; old approved patch without publication; rollback; stream and follow-up. Only verified ACTIVE patches can change answers.

### R1-05 — Pending correction contamination/poisoning prevention
**Priority:** P0. **Code:** `backend/app/services/repair_integration.py`, vector-store ingestion/retrieval, graph shadow overlays, fast-path and context assembler.

**Implement:** Stop immediate `ingest_synthetic_patch_chunk` for pending correction candidates unless it writes to a physically or namespace-isolated review-only index with default-deny serving. Publish verified corrections with versioned, source-backed structured claims—not imperative prompt injection such as “supersedes prior context.” Preserve review artifact/evidence visibility for authorized reviewers only. Invalidate answer caches only after successful publication receipt; retire stale provisional entries safely.

**Tests:** Adversarial pending patch with invented NAV/AAUM or regulatory value cannot appear in vector hits, graph context, fast-path, streaming output, citations, cached answers or PDF/TXT responses. Check both microservice and monolith.

### R1-06 — Real graph/vector effect, no phantom APPLIED
**Priority:** P0. **Code:** `backend/app/services/promotion_service.py`, Graph adapter, vector ingestion/index-management service, `GraphMutation`/`RepairProposal` records.

**Implement:** `backend/app/exceptions/__init__.py` now exists—retain it and test a clean import. Reject missing/empty `mutation_cypher`. Avoid free-form unreviewed mutation statements: compile from approved typed operation with allowlisted fields and bound values. Verify exact postcondition (`actual == approved expected new value`, entity identity/version and affected-row count), not node existence alone. Implement `_trigger_reindex()` as a real queued/observed reindex with index-version readiness receipt; do **not** mark vector proposal APPLIED on log-only activity. Distinguish request accepted, work started, work completed, verified, activated.

**Tests:** No driver; no mutation; zero nodes changed; wrong attribute; conflicting entity version; graph write succeeded but readback failed; vector reindex not executed or failed; corrupted index; retry after restart. None may return completed/APPLIED without independently observed effect.

### R1-07 — Idempotent publication saga and compensation
**Priority:** P0. **Code:** `promotion_service.py`, approval/outbox schemas, event/retry jobs, caches, rollback logic.

**Implement:** One proposal-level unit of SQL work and a durable outbox/inbox with idempotency key `(proposal_id, approved_revision, target_version)`. Do not let rollback of later proposal B erase SQL receipt for graph-applied proposal A. Persist attempts, external transaction receipt, verified postcondition, activation pointer, compensation/recovery actions and terminal states. Define explicit behavior for crash after graph commit/before SQL ack; no blind double mutation. Preserve prior active version until new version fully published. Authorize production activation/rollback separately.

**Tests:** At-least-once delivery, duplicate events, concurrent approvers, lost ACK, SQL rollback after external commit, vector failure after graph success, restore previous index/graph value, stale cache and partial worker outage. Verify eventual convergence and no false RESOLVED feedback issue.

### R1-08 — Enrollment and operational security hardening
**Priority:** P1 before production. **Code:** `admin.py`, `auth.py`, `schemas/invitation_token.py`, migrations, auth tests.

**Implement:** Store a hash/HMAC of invitation token rather than the bearer token plaintext. Ensure atomic single-use consumption under concurrent requests and expiry/revocation. Avoid exposing invitation secret repeatedly in admin pages/logs/response persistence; issue via controlled delivery channel. Constrain tenant/role assignment to authorized admin scope and verify pending users cannot log in. Add explicit migration and secret-rotation/recovery steps. Avoid database/schema initialization that only works on a developer's existing DB.

**Tests:** Reused, expired, revoked, concurrent, stolen-token, cross-tenant invite; disabled user; admin creating higher authority than allowed; migration/restart and password reset.

### R1-09 — API compatibility restoration/migration
**Priority:** P0 for release. **Code:** `admin.py`, `mf-context-engine/src/services/api.js`, frontend admin views, route tests.

**Implement:** Inventory the 18 missing route patterns from section 1. For each active feature choose a secure compatibility route OR verified alternative endpoint and change the frontend. Preserve request and response semantics, pagination, role and tenant permissions, and error handling. Restore user sync only if it remains a required supported behavior. Constrain source URL ingestion and file uploads (size/content type/network access) and avoid user-provided authority assertions.

**Tests:** Contract tests of all frontend API service methods used by UI, role matrix for each endpoint, frontend build/smoke for admin dashboard, ingest tasks, regulatory proposed edges, cache management, audit and feedback issues. Record deliberate removals and UI migration in one compatibility ledger.

### R1-10 — Release-evidence gate and docs reconciliation
**Priority:** P0. **Code:** `.github/workflows/`, `backend/tests`, `packages/amc-repair-engine/tests`, `remediation/wave1_2/R1/`.

**Implement:** Retain and run two existing SEC test modules; add independent Repair service auth, state-machine/approval, publication recovery, vector isolation, and API compatibility tests. Set up CI for the pinned/updated branch; on every PR run real tests with isolated test stores and sanitized artifacts. Reconcile conflicting older `TASK_STATUS.md` (“VERIFIED & PASSING”), `README.md` (“TESTING PENDING”), and `IMPLEMENTATION_SUMMARY.md` (“BLOCK” / partial). Do not claim 33/33 reverified unless re-executed for the new SHA.

**Acceptance:** Automated, not just documented, SEC/REP/PUB/COMP gates and CI evidence. No unclassified P0 failure or skipped negative test allowed in release gate.

---
## 5. W1.2-F1 — Canonical financial policy and deterministic calculation

The G03/G04/G05 foundations are valuable, but **the source-level business-correctness defects were not changed by the two latest `amc-dev` commits**. This is the next substantive product implementation after R1 release blockers are safely contained.

### F1-01 — Metric dictionary is an executable control (W1.1-01; G03-T05/G05)
**Priority:** P0. **Code:** `backend/app/tabular/contracts.py`, `planner.py`, `executor.py`, all bypassing service routes.

**Implement:** Explicit `MetricDefinition` registry with metric ID, source column, unit, observation grain, valid operations, period policy, null policy, approved metric version, authorized steward and allowed aggregation. `QueryPlan` must carry typed `operation`, not infer it loosely from a SQL string or intent label. Executor must validate every plan **immediately before execution** against trusted, server-side policy. Do not let crafted `compiled_sql` or caller-supplied `steward_approved` bypass policy. No direct SQL execution outside this control for authoritative financial answers. The current AAUM registry marks SUM/AVG as pending; reject affected plans with `METRIC_POLICY_BLOCKED` until approved and signed off.

**Acceptance:** Constructed malicious plans, requests through facade, top AMC, top schemes, category AUM, dataset summary, and aggregation distribution cannot run unapproved AAUM SUM. Approved narrow exact lookups continue working. Changing a metric version invalidates stale receipts.

### F1-02 — Exact arithmetic; end-to-end decimal fidelity (W1.1-02)
**Priority:** P0. **Code:** planner, executor, financial repository and `scheme_aggregation_service.py`.

**Implement:** Replace all authoritative SQLite `CAST(aaum_crore AS REAL)`, `AVG(REAL)`, float-only accumulation and Python `float(...)` in financial pipelines with approved scaled-integer or Decimal-safe operations. Define precision, scale, rounding policy, overflow behavior, negative/null handling and human display formatting. Stored Decimal TEXT alone is insufficient if calculations then use floating point. Do not use `Decimal(str(float_result))` as proof of exactness.

**Acceptance:** Independent `Decimal` reference exact gold for very small values, large values, ties, repeated additions, cancellation, nulls, wrong units and rounding boundaries. Check source sum, grouped sum, rankings and returned API values.

### F1-03 — Canonical AMC/scheme/plan-option identities (W1.1-03; G03)
**Priority:** P0. **Code:** `contracts.py`, `csv_excel_loader.py`, `repository.py`, `planner.py`.

**Implement:** Replace `GROUP BY scheme_display_name` and ambiguous slug-only entity identity with steward-reviewed hierarchy and collision handling; Scheme_Code, ISIN, AMC and plan/option need distinct identities. Require resolved canonical keys or explicit ambiguity when collision exists. Track source alias and confidence, but never silently merge schemes across AMCs or aggregate across incomparable variants.

**Acceptance:** Same-name two-AMC dataset, plan variation, direct-vs-regular, growth-vs-IDCW and data-version changes produce correct canonical grouping and no double count; ambiguous identities block affected aggregates.

### F1-04 — NAV observation key and as-of selection (W1.1-04)
**Priority:** P0. **Code:** `repository.py`, `planner.py`, `scheme_aggregation_service.py`.

**Implement:** NAV observation must bind scheme, plan/option, actual NAV date and source row together. Eliminate `MAX(NAV)` paired with unrelated `MAX(nav_date)`. Avoid `LIMIT 1` selecting arbitrary record for same scheme/date where multiple plans exist. Query user for plan/date when material ambiguity exists, or return enumerated candidates. Comparison across dates requires explicit, disclosed as-of policy.

**Acceptance:** Same code/date with several plans -> distinct result or `AMBIGUOUS_QUERY`; latest NAV picks the proper dated observation; no invented mixing; cross-date ranking flagged or disallowed per policy.

### F1-05 — AAUM period, additivity, and count semantics (W1.1-05; G03)
**Priority:** P0. **Code:** financial dictionary, planner, facade, response schemas.

**Implement:** Remove silent quarter defaulting (e.g. January–March 2026 when user did not ask), unless a documented dataset snapshot provides explicitly surfaced period semantics. Disallow cross-quarter AAUM addition without approved comparability rules; do not add scheme/plan AAUM with incompatible grains. **Do not label 16,245 source rows as 16,245 folios** unless the source actually contains distinct investor folio IDs. Distinguish source records, scheme count, plan count, fund count and investor folio count; return `UNSUPPORTED_METRIC` where unavailable. Specify fund closure/date/status policy; never infer live status simply from a non-null `Closure_Date` without steward sign-off.

**Acceptance:** Period/type/count labels match source and business definitions; no mix of AAUM quarters; source-row count never masquerades as investor folio count; all defaults shown in receipt or rejected as ambiguous.

### F1-06 — Independent audited finance gold set (G13)
**Priority:** P0. **Code:** `backend/tests/test_tabular_queries.py` and new gold-driven tests.

**Implement:** Extend beyond “the top five are sorted” assertions. For each approved financial metric, compare **exact expected values**, canonical keys, dates, units, filters, data version, row evidence and NO_MATCH/AMBIGUITY behavior against an independently computed/approved fixture. Preserve the known exact NAV case (scheme code 100033, 2026-06-29, 922.67) as a regression fixture, but do not let one fixture certify the entire pipeline. The previously reported ingestion (16,245 rows, 22 chunks, NAV 14,208, AAUM 8,178) is a local historical artifact, not automatically current active-state proof.

**Acceptance:** 100% critical exact-number tests pass; source and expected-output calculation independently reviewed. Unapproved AAUM totals are tested as BLOCKED until human signoff; no invented expected values.

## 6. W1.2-F2 — Dataset integrity, versioning and provenance

### F2-01 — Correct manifest schema and prove all source bytes (W1.1-06)
**Priority:** P0/P1. **Code:** `csv_excel_loader.py`, data manifest parser, `run_tabular_ingestion.py`.

**Implement:** Parse actual source manifest names (including `original_rows` and `chunk_count` if those are the source format); reject missing/unknown required keys. Never silently substitute hardcoded 16,245/22 expectations when source claims differ. Validate original source hash, per-chunk hash, exact chunk order, row ranges, column signatures, duplicate/overlap/gap and encoding. Allow deterministic repair/retry only in a quarantined staging version. CSV and XLSX capability claims must correspond to real parsers and tests; defer unsupported formats explicitly.

**Acceptance:** Wrong manifest, truncated chunk, reordered chunks, missing/extra rows, altered header, duplicate file and corrupt decimal/date lead to verified quarantine or failed publication, not a valid-looking ACTIVE snapshot.

### F2-02 — Field-level validity and quarantine policy
**Priority:** P1. **Code:** row validation, metrics table, ingestion reports.

**Implement:** Track `source_row_valid`, `nav_observation_valid`, `aaum_observation_valid`, field errors and quarantine reason separately. An entity row may be valid while an AAUM number is invalid; do not report 0 quarantine as evidence every metric is usable. Specify null, zero, dash/NA, missing date, negative metric and precision behavior per data contract. Require completeness thresholds for each intended publishable metric, not just overall source rows.

**Acceptance:** Reports reconcile total/valid/quarantined for rows and each metric; invalid financial values cannot enter approved analytics; reason counts and source-row IDs are auditable.

### F2-03 — Immutable staging and atomic activation (W1.1-07)
**Priority:** P0. **Code:** `FinancialDataRepository`, ingestion pipeline, app startup/deployment.

**Implement:** Define `STAGED → VALIDATED → STEWARD_APPROVED → ACTIVE`; enforce version/hash and checks before activation. Protect previously ACTIVE snapshot during load, failure, restart, rollback and simultaneous writers. Do not `INSERT OR REPLACE` into active source rows without preserving immutable/versioned evidence semantics. Make active-version promotion an authorized operation. Provide explicit clean-environment ingestion/bootstrap + readiness check; no silent switch to legacy finance calculations when DB missing.

**Acceptance:** Fresh clone and ephemeral DB pass staging and activation; interrupted ingestion and bad verification leave previous ACTIVE snapshot intact; repeat ingestion idempotent; no mixed-version query output.

### F2-04 — Complete aggregate contributor evidence (W1.1-09)
**Priority:** P0. **Code:** executor, repository, provenance contract and API response serializers.

**Implement:** For each number produce source dataset hash, query plan hash, metric dictionary/approval version, normalized filters, grain, period, transformation formula, exact result, complete contributor row-ID set or paginated signed manifest, and a stable result-set hash. Do not attach a random nonaggregated `source_row_id` from a `GROUP BY` as proof of all contributing rows. Avoid huge response payloads; store secure immutable manifests and return a bounded receipt plus reference.

**Acceptance:** Independent reconstruction from receipt yields identical result; deliberate source modification invalidates receipt; missing contributor evidence blocks authoritative answer; contributor references honor tenant access.

## 7. W1.2-F3 — Query routing, compatibility and explainability

### F3-01 — One structured numeric-intent gateway (W1.1-08; G05/G06)
**Priority:** P0. **Code:** `retrieval/fast_path_interceptor.py`, `retrieval/orchestrator.py`, query/chat routes and `scheme_aggregation_service.py`.

**Implement:** Detect exact numeric, ranking, count, distribution and mixed financial questions before LLM generation; route to trusted typed planner/executor. Classification misses must not silently synthesize a number from vector chunks, especially when typed SQL is unavailable or fails. Maintain explicit errors: `STRUCTURED_SOURCE_UNAVAILABLE`, `NO_MATCH`, `AMBIGUOUS_QUERY`, `METRIC_POLICY_BLOCKED`, `UNSUPPORTED_METRIC`, `INCOMPLETE_DATA`, `STALE_DATASET`. Do not substitute legacy Pandas/CSV fallback for authoritative numeric results. Permit retrieval/LLM only for qualitative explanation grounded on an already verified numeric receipt or clearly nonnumeric queries.

**Acceptance:** Force DB outage, planner exception, unknown scheme, misspelling, ambiguous filters and query decomposition; all returns safe error/clarification and **zero fabricated amounts**.

### F3-02 — API and streaming parity
**Priority:** P0. **Code:** `/query`, `/query/v2`, `/query/stream`, `/chat`, `/chat/stream`, fast path, cache and frontend adapters.

**Implement:** Query and stream share identical intent, policy, dataset, tenant and receipts. Preserve API payload shape/UX while distinguishing authoritative metric values from context text. Avoid bypassing correct typed logic in streaming/follow-ups. Ensure cached answers are invalidated with dataset/metric/correction version changes.

**Acceptance:** Same question/permissions/versions yields same financial facts and safe failures in streaming and nonstreaming; multi-turn entity/date references preserved; no source cross-tenant leak.

### F3-03 — Claim-level citations, confidence and time labels (G07)
**Priority:** P1. **Code:** `models/query`, `retrieval/synthesis`, `api/routes/query.py`, source references.

**Implement:** Link every factual numeric claim to actual row/evidence proof, appropriate source and as-of date. Do not report cryptographic output hash alone as independent business-truth proof. Confidence must reflect completeness, metric approval, ambiguity and data recency, not be fixed to high merely because the result was obtained by SQL. Expose canonical metric units and coverage transparently.

**Acceptance:** Broken/missing citation or unsupported numeric claim leads to low confidence/block; exact number/date/plan/quarter can be verified from returned evidence.

### F3-04 — PDF/TXT and UI regression safety (G08/G13)
**Priority:** P1. **Code:** frontend API clients, orchestrator, existing PDF/TXT control test suite.

**Implement:** Preserve established PDF/TXT quality, citation links, file download/auth, UI modules and correction overlays while switching financial calculations. Run comparative tests for source selection, factual completeness, latency and errors. Ensure 18 retired Admin endpoints have no remaining active UI callers or working replacements exist.

**Acceptance:** Previously correct control responses remain valid; frontend build and key user journeys pass; no contradictory financial values from document-context fallback.

## 8. W1.2-Q1 — Feedback/Repair, operations and release assurance

### Q1-01 — Evidence-based Feedback → Repair → activation workflow (G09/G10/G11)
**Implement:** Feedback observations must link to immutable query/result/evidence receipts. Deduplicate by canonical issue and observation fingerprint, keep user feedback distinct from adjudicated fact, authorize human decision, stage candidate patch, run regressions, publish/verify/activate, then close issue; no `RESOLVED` on failed graph/vector changes. Retries, outbox and rollback do not duplicate or silently change status. Test domain-neutral feedback flows and compliance-specific controls.

### Q1-02 — CI/security/reliability gate (G13/G14)
**Implement:** Add GitHub Actions CI (or approved equivalent, with traceable evidence) for cold imports, FastAPI startup, backend unit tests, independent microservice tests, auth/tenant negative cases, data contract, finance gold, PDF/TXT controls, Repair failure-injection and frontend build. Use isolated repositories/fixtures; protect secrets and proprietary data. Collect runtime query-trace metrics (SQL latency, evidence coverage, failed/blocked queries, stale data, publish failures, repair approval age), actual values rather than fabricated throughput claims.

### Q1-03 — Final release evidence and safe rollout
**Implement:** Evidence bundle includes exact SHA, dependency lock/versions, source/hash and approved metric registry, 401/403 matrix, repair approval audit/rollback trial, finance gold and sanitized query-trace logs, missing features disposition, CI run ID and responsible sign-off. Gate outcomes: `PASS`, `REVIEW`, or `BLOCK`. Only PASS + approved operational change request allows canary, and only measured canary evidence permits broad rollout. A canary is **not** authorization to change live financial facts.

---
## 9. Test matrix — required observable outcomes

All tests require **actual execution**. “Test module created,” “syntax check,” and “expected result” do not equal passing evidence. Use disposable SQL DB, test graph/vector stores or isolated staging authorized by owner. Avoid modifying production data.

| Test ID | Scenario | Expected invariant |
|---|---|---|
| SEC-T01 | Unauthenticated `/api/admin`, `/api/ingest`, `/api/files`, `/api/graph`, `/api/governance` sensitive routes | 401 or documented public exception |
| SEC-T02 | Authenticated analyst for admin-only mutations | 403 |
| SEC-T03 | `X-User-Role: admin` with no bearer; valid analyst bearer with spoofed admin header | No privilege elevation |
| SEC-T04 | Wrong tenant resource ID; forged tenant/header/user ID | No cross-tenant disclosure or mutation |
| SEC-T05 | Direct unsigned HTTP to independent Repair `approve`, `promote`, `run-batch`, `create` | Authz rejection, no side effects |
| SEC-T06 | Invitation expiry, replay, double-submit concurrency, disabled user, role escalation | Single use, secure enrollment, no tenant/role escalation |
| COMP-T01 | All frontend Admin API client methods and missing 18 historical routes | Protected compatible endpoint or intentional migrated/retired client |
| REP-T01 | Confidence=1.0 pending financial/regulatory correction | Not approved or served |
| REP-T02 | Direct `approved=true`, direct promote or batch-review without valid approver | Not ACTIVE |
| REP-T03 | Proposer is approver | Denied; audit preserved |
| REP-T04 | Approved but not published patch | Not in query, cache, vector, graph, stream or fast path |
| REP-T05 | Shadow patch missing state or stale version | Not served |
| REP-T06 | Low-confidence candidate in Repair scheduler | Review recommendation only, no automatic destructive rejection without approved policy |
| PUB-T01 | Neo4j driver missing or empty Cypher | Not APPLIED; retryable failure evidence |
| PUB-T02 | Graph target node exists, but attribute unchanged or wrong value | Verification fails; not APPLIED |
| PUB-T03 | Vector reindex only logged, failed, cancelled, or index not active | Not APPLIED |
| PUB-T04 | Proposal A graph-committed, proposal B fails, SQL rollback | A's receipt survives/reconciles; B not APPLIED |
| PUB-T05 | Duplicate event, crash after external commit, lost ACK, concurrent approvals | Idempotent completion, no double mutation |
| FIN-T01 | AAUM SUM before signed additivity approval | `METRIC_POLICY_BLOCKED` |
| FIN-T02 | Numeric query when `financial.db`/active snapshot missing | `STRUCTURED_SOURCE_UNAVAILABLE`, never fabricated result |
| FIN-T03 | Exact NAV on known code/date/plan | Decimal value, correct date/plan and source proof |
| FIN-T04 | Duplicate name across AMCs; growth and IDCW variants | No merged scheme, no double count |
| FIN-T05 | NAV value from date A, latest date B | Correct same-row pairing or ambiguity |
| FIN-T06 | Very large/small monetary values, precision, ties and rounding | Exact `Decimal`/scaled-integer gold |
| FIN-T07 | User asks for investor folio count from scheme metadata rows | `UNSUPPORTED_METRIC` if folio identities absent |
| ING-T01 | Wrong manifest key/row count/hash/duplicate chunk | Staged dataset rejected/quarantined |
| ING-T02 | Invalid AAUM but valid source identity | Correct field-level metric validity and no invalid aggregate |
| ING-T03 | Interrupted ingestion / repeated activation / version rollback | Prior active snapshot intact |
| E2E-T01 | `/query`, `/chat`, streaming, follow-up, cache across failures | Same safe financial policy and receipts |
| E2E-T02 | ≥15 baseline PDF/TXT controls initially; expand to ≥50 | No factual/citation regression |
| OPS-T01 | Clean checkout + all CI checks + frontend build | Reproducible green run on exact commit SHA |

**Critical test policy:** Security, Repair state, publication, and finance truth tests must all pass or be explicitly BLOCKED. No skipped critical negative test is acceptable evidence of PASS. Noncritical performance regressions can receive REVIEW with documented remediation and owner; data-integrity failures cannot.

### Suggested local commands (from the `backend/` directory)

```bash
# Run only in an isolated environment; verify test DB/graph/vector settings first.
python -m pytest -q tests/test_sec01_universal_auth.py
python -m pytest -q tests/test_sec01_remaining_routes_and_flow.py
python -m pytest -q tests/test_tabular_queries.py
python -m pytest -q tests/test_wave0_verification.py
python -m pytest -q tests/test_authentication_enforcement.py
python -m pytest -q tests/test_repair_linkage.py

# New test suites to create in Wave 1.2 (these are not claimed to exist):
python -m pytest -q tests/test_wave12_route_compatibility.py
python -m pytest -q tests/test_wave12_repair_authority.py
python -m pytest -q tests/test_wave12_publication_saga.py
python -m pytest -q tests/test_wave12_financial_exactness.py
python -m pytest -q tests/test_wave12_ingestion_versions.py
python -m pytest -q tests/test_wave12_query_parity.py
```

`python -m pytest` output must be accompanied by active environment, SHA, time, pass/fail/skip counts, coverage limitations and real failing logs. Agent should fix broken imports/setup before proceeding; do not automatically interpret test setup failures as unrelated.

## 10. Definition of Done and evidence output

Deliver one comprehensive evidence directory per batch, preferably inside `remediation/wave1_2/` with confidential data excluded from Git:

```text
remediation/wave1_2/
  BASELINE_AND_DECISIONS.md
  R0/
    ROUTE_COMPATIBILITY_MATRIX.csv
    FRONTEND_CONTRACT_REGRESSION.md
    GOLD_BASELINE_MANIFEST.md
  R1/
    AUTH_ROUTE_MATRIX.csv
    REPAIR_STATE_AND_APPROVAL_POLICY.md
    SERVICE_AUTH_VERIFICATION.md
    PUBLICATION_SAGA_AND_COMPENSATION.md
    FAILED_PUBLICATION_TRIALS.md
  F1/
    METRIC_DICTIONARY_AND_STEWARD_DECISIONS.md
    FINANCIAL_GOLD_RESULTS.md
  F2/
    DATA_RECONCILIATION.json
    DATASET_VERSION_ACTIVATION.md
    SOURCE_PROVENANCE_CONTRACT.md
  F3/
    ROUTING_AND_ERROR_MATRIX.md
    PDF_TXT_REGRESSION.md
    FRONTEND_SMOKE.md
  Q1/
    TEST_RESULTS.json
    CI_RUN_EVIDENCE.md
    SECURITY_AND_GOVERNANCE_GATES.md
    ROLLBACK_DRILLS.md
    RELEASE_VERDICT.md
  TASK_LEDGER.csv
  README.md
```

Each TASK_LEDGER row must contain: stable task ID, priority, source paths, owner, status (`DONE/PARTIAL/BLOCKED/NOT_STARTED`), code commit, test case/CI run and evidence link, data-steward decision if needed, residual risk and rollback notes. A task cannot become DONE merely because code is present.

### Required independent decisions / stop rules

- **Financial data steward:** approve or reject AAUM grain, whether AAUM is additive across plan variants and AMC/category, quarter/date comparisons, identity hierarchy, `Closure_Date`, and count/folio definitions. Keep unapproved calculation routes blocked; do not synthesize authority.
- **Security owner:** authorize service-to-service trust method, endpoint allowlist and production credential migration.
- **Product owner/frontend:** decide route restoration vs intentional deprecation for each removed Admin endpoint.
- **Operational owner:** authorize production deployments, graph/data mutation, use of customer datasets and rollback drills. No agent may self-authorize them.
- **Privacy/security:** do not leak customer PDFs, tokens, auth fixtures, full financial data, production logs or secrets into reports or public CI.
- No unsafe fix by reverting to client role headers, predictable passwords, auto-approved corrections, or unconditional numeric LLM fallback.
- Preserve open regression evidence; do not delete previous audit artifacts merely to make the progress report look cleaner.

## 11. Copy/paste primary Codex execution instruction

> Save this Markdown file in the repository, e.g. `docs/AMC_Wave1_2_Next_Implementation_Agent_Handoff_2026-11-04.md`, or provide its full path to Codex. The prior 196-task blueprint and Wave 1.1 handoff are already in `amc-dev`.

```text
ROLE: Lead full-stack principal engineer, financial data architect, AI runtime
integrity specialist and release assurance auditor for the NuSummit AMC project.

REPOSITORY: nusummit-spg/amc-context-engineering-poc
BASE: amc-dev, pin initial HEAD af35d86b836884e6527f35b334e14848906e9f57
Create a new feature/remediation branch from this SHA; do not force push or
rewrite amc-dev/main/release. Before running, verify actual HEAD and current
git working tree. If branch advanced, calculate and document delta before
implementing rather than overwriting concurrent code.

READ IN FULL:
- docs/AMC_Wave1_2_Next_Implementation_Agent_Handoff_2026-11-04.md
  (this handoff, supplied locally)
- docs/AMC_Wave1_1_P0_Closure_Agent_Handoff.md
- docs/AMC_Tasks_3_11_26/AMC_Specs/README_START_HERE.md
- 01_SOURCE_REVIEW_AND_ROOT_CAUSES.md
- 02_TARGET_ARCHITECTURE_AND_CONTRACTS.md
- 03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md
- 04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md
- 05_ASSURANCE_SECURITY_RELEASE_GATES.md
- 06_GOALS_AND_TASKS.md
- 07_CODEX_EXECUTION_PLAYBOOK.md
- 08_OPEN_DECISIONS.md
- remediation/wave1_1/p0_closure/ documentation and current code/tests.

THIS IS A BULK EXECUTION ASSIGNMENT. Do not work as isolated microtasks;
complete cohesive batches autonomously. Use reviewable logical commits / PRs,
separate authentication+Repair safety, financial data, and query routing.

IMPLEMENT IN ORDER:
R0-01..03: freeze baseline, record 18 disappeared Admin routes and frontend
          callers, create independent quantitative/PDF controls.
R1-01..10: finish service authentication, four-eyes approval, typed Repair
           state and serving eligibility, isolate pending vector patches,
           verify graph + vector effects, build idempotent publication saga,
           restore/migrate frontend API contracts, commit and RUN tests.
F1-01..06: enforce metric approval in executor; no unapproved AAUM SUM/AVG;
           exact decimal arithmetic; correct canonical identity; NAV/date;
           quarter/folio semantics; independent gold.
F2-01..04: real manifest integrity, field validity, immutable staged dataset,
           atomic activation/rollback and proof of aggregate contributor rows.
F3-01..04: one typed numeric gateway and fail-closed paths across normal,
           streaming/chat/followup; evidence/citations; frontend and PDF/TXT.
Q1-01..03: feedback/repair lifecycle, CI, failure injection and strict release.

PRIORITY RULES:
- R1 contains P0 release blockers and should be finished before recommending
  a merge or production rollout.
- F1 may be developed separately with AAUM calculations initially BLOCKED
  pending authoritative data-steward signoff.
- Do not remove existing usable security or authentication functionality.
- Restore 18 removed Admin route contracts safely or explicitly migrate callers.
- No authorization via caller-supplied role/tenant/approval flags.
- No auto-approval or automatic canonical rejection just from LLM confidence.
- PENDING/APPROVED/STAGED patches never become serving truth without verified
  ACTIVE state, correct tenant/version and publication receipt.
- Actual graph mutation and real vector index rebuild required before APPLIED.
- Never mark feedback issue RESOLVED before publication verified.
- No float-based monetary sum, name-only fund grouping, mixed NAV dates,
  fake folio count, unapproved AAUM grain, or silent financial Pandas/LLM fallback.
- Maintain valid PDF/TXT citations and source access after auth changes.
- Never deploy or alter production data/secrets without explicit authorization.

PROVE WITH ACTUAL EXECUTION:
- Real route inventory, frontend contract tests, auth/tenant negative matrix.
- Direct separate Repair service unauthorized/forged requests.
- Four-eyes, patch-state, no pending vector contamination.
- Neo4j mismatch, absent driver, absent Cypher, no-op vector reindex,
  duplicate/retry/crash-after-commit, transaction rollback failure injection.
- Independently correct quantitative gold, manifest corruption tests,
  clean-clone dataset version activation, stream/chat/query parity,
  PDF/TXT baseline controls and frontend build/smoke.
- CI run ID and exact SHA where CI is available; record truthful statuses
  where infrastructure or signed steward decisions are unavailable.

DELIVER:
1. Source diffs + actual working tests, split into reviewable PRs.
2. Stable task ID → DONE/PARTIAL/BLOCKED/NOT_STARTED matrix with evidence.
3. Real test commands, pass/fail/skip results, exact source SHA, data hashes.
4. Approved metric dictionary/decisions or explicit blocking policy.
5. Security matrix, publication receipts, recovery/rollback evidence.
6. Explicit API compatibility ledger for removed 18 Admin route patterns.
7. Security/Repair/Publication/Financial/Operations release gates = PASS,
   REVIEW or BLOCK with reasons and owner. Never replace BLOCK with optimism.

Stop only at external authorization or unresolvable business semantics; still
complete safe code and tests and record the obstacle. Do not fabricate results.
```

## 12. Handoff review and final go/no-go gates

| Gate | PASS requires | BLOCK if |
|---|---|---|
| **COMP** | All used frontend admin contracts valid or formally migrated | Removed route still called by UI or untested breaking response |
| **SEC** | Authenticated identity, role and tenant for all sensitive APIs, including independent service; secure invitation lifecycle | Role spoofing, anonymous mutation, cross-tenant exposure |
| **REP** | Verified independent approval, persisted states and review-only isolation for pending patches | Self/confidence approval, approved-but-not-active content served |
| **PUB** | Exact value read-back, real reindex, durable idempotent receipts, recoverable partial failure | Phantom APPLIED, no-op vector publication, unsafe rollback |
| **NUM** | Steward-approved metric semantics, precise arithmetic, canonical identity/date/period and complete evidence | Unapproved AAUM sum, float drift, wrong NAV, invented folio counts |
| **ING** | Manifest/hash/per-field reconciliation, versioned active-pointer safety | Truncated/incomplete data activated |
| **E2E** | Query/chat/stream and PDF/TXT controls pass with correct source proof | LLM/Pandas numeric fallback or baseline PDF/TXT degradation |
| **OPS** | Fresh checkout, CI/test artifacts, exact SHA, rollback drill, authorized signoff | No reproducible evidence or production change without authorization |

### CTO recommendation

1. **Next immediate bulk:** R0 + R1. Focus on the newly discovered Admin API compatibility regression and residual P0 microservice/Repair publication safety before starting a large new build.
2. **Next functional bulk:** F1 + F2, implementing financial correctness with blocked unapproved AAUM metrics instead of guessing business semantics.
3. **Then:** F3 + Q1, completing end-to-end numeric routing, answer evidence, Feedback/Repair integration and CI/release proof.
4. **Re-audit only against a new code SHA and actual test evidence.** Code presence and committed progress prose are not equivalent to operational verification.

**Final verdict on `af35d86`:** improvements retained; **release BLOCK** pending COMP/SEC/REP/PUB/NUM/OPS gates. This is a source-level engineering assessment, not a penetration test or production certification.
