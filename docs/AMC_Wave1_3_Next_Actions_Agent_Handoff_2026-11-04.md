# NuSummit AMC Context Engineering — Wave 1.3 Agent Execution Handoff

**Prepared:** 4 November 2026  
**Repo:** [`nusummit-spg/amc-context-engineering-poc`](https://github.com/nusummit-spg/amc-context-engineering-poc)  
**Reviewed branch:** `amc-dev`  
**Reviewed HEAD:** `c7aa9203819d21da20f2ad92223ccc4ff32778af`  
**Previous audited baseline:** `af35d86b836884e6527f35b334e14848906e9f57`  
**Difference:** one new commit, 15 changed files.  
**Audit basis:** read-only GitHub source/code and committed reports. **No application, infrastructure, or test execution was performed by this reviewer.** No GitHub Actions runs or combined commit statuses were found for this head.  
**Release recommendation:** **BLOCK** for production. Continue controlled development using the ordered batches below.

> **Purpose:** A single, executable handoff for local Codex. Implement real code, tests, evidence and reversible changes. Do **not** interpret restored HTTP routes, written implementation summaries, tests that were created but skipped, or demo/mock data as production readiness. Retain the AMC Core → Feedback → Repair architecture. Avoid restarting already implemented changes without verifying them first.

## 1. Executive review: what the latest push actually delivered

**Confirmed code changes** (compared with `af35d86`):

1. `backend/app/api/routes/admin.py` adds back many Admin and ingestion/edge/cache endpoints removed during Wave 1.1. Authentication checks are present on those restored handlers.
2. `packages/amc-repair-engine/src/amc_repair/auth.py` introduces signed service tokens, an HTTP bearer dependency and role/tenant checks; `server.py` adds enforcement to several mutation/read handlers.
3. `backend/app/clients/repair_client.py` adds optional bearer headers to some Repair client calls.
4. `backend/tests/test_wave12_route_compatibility.py` (new) and `packages/amc-repair-engine/tests/test_repair_service_auth.py` (new) add test modules.
5. Reports in `remediation/wave1_2/` capture implementation scope and acknowledge significant pending work.

**Documented test status is not independently verified:** the new reports claim **20/20** Repair-authentication tests passed locally, while the Admin compatibility report indicates only **18/54** related tests passed and **36** were skipped pending real JWT fixtures. No branch-associated GitHub Actions runs or commit status checks were found. The new Repair test module heavily tests authentication helpers and comparison conditions; these are not substitutes for HTTP route security, end-to-end state transition, concurrency or deployment tests.

### Release-critical concerns confirmed by source

| Key | Severity | Observation at reviewed SHA | Current interpretation |
|---|---|---|---|
| C-01 | P0 | Restored Admin handlers return mock/task data, empty proposed edges, or success without actual actions, for example `/users/sync`, `/ingestion/tasks`, `/ingestion/edges/{id}/confirm`, `/intent-cache/clear` | **API shape restored; real behavior not proven/implemented** |
| C-02 | P0 | Edge confirmation says four-eyes is enforced, but proposer lookup/check is commented out; handler returns `status=confirmed` | **False governance-success risk** |
| C-03 | P0 | Independent Repair `GET /api/patches/for-entities` and `GET /api/patches/{patch_id}` still lack auth dependencies; they expose pending patch values/provenance | **Protected-data disclosure risk if service reachable** |
| C-04 | P0 | `RepairUser.can_approve()` allows any `is_service` principal to approve, without requiring `patch_approve` scope | **Service scope escalation risk** |
| C-05 | P0 | Repair service-token validator accepts missing `exp`; has a default development secret; no enforced issuer/audience/token-type separation is apparent | **Token trust-boundary hardening required** |
| C-06 | P0 | Main application's signed user session token only contains `sub`, `iat`, `exp`, `jti`; Repair parser expects `roles`, `tenant_id` in the signed payload. Repair verifies `REPAIR_SERVICE_SECRET`, main issues with its auth secret. | **End-user token interoperability and authorization cannot be assumed** |
| C-07 | P0 | Main governance approval (`/approve/{patch_id}`, proposal review, direct promotion) does not check that proposer differs from approver | **Four-eyes inconsistent across modules** |
| C-08 | P0 | Repair patch store/serving lacks one authoritative persisted `ACTIVE` state; local context application filters `approved` but not universally the same status | **Approved-but-not-published content may enter answers** |
| C-09 | P0 | `repair_integration.py` ingests synthetic patch chunks into serving vector layer before human approval | **Unapproved evidence contamination risk** |
| C-10 | P0 | `promotion_service.py::_trigger_reindex()` logs only; vector proposals can be marked `applied` | **Phantom publication success** |
| C-11 | P0 | Graph postcondition verifies node presence, not exact attribute value; shared SQLAlchemy session spans external graph changes | **Wrong-value and partial-commit recovery risks** |
| C-12 | P0 | Financial planner executes AAUM SUM/AVG using `CAST(... AS REAL)` while AAUM metric is `PENDING_APPROVAL`; name-only grouping, NAV date/value mismatch and legacy Pandas fallback remain | **Financial correctness still unproven** |
| C-13 | P1 | Restored Admin audit retrieval contains placeholder tenant filtering (`pass`) for non-admin users | **Cross-tenant audit disclosure risk** |
| C-14 | P1 | Invitation tokens are stored/queried as plaintext and returned in API response; invitation status is not a substitute for a secure delivery process | **Credential-enrollment hardening required** |
| C-15 | P1 | Admin compatibility suite has placeholder JWT fixtures and many `@pytest.mark.skip` cases; mock endpoints may satisfy schema tests without exercising effects | **Confidence in compatibility is overstated** |

The repo reports themselves still mark Repair state machine, vector isolation, publication verification/saga, financial semantics, ingestion, numeric routing and operational assurance as pending. The following plan treats them as **open until validated by running code and independent evidence**.

---

## 2. Execution order and dependencies — bulk, not scattered microtasks

Implement in **four reviewable PRs plus assurance**, not a single unreviewable security/data migration. Codex may implement multiple related tasks in one execution slot, but every PR requires runnable tests and rollback documentation.

| Order | Batch | Tasks | Outcome / release gate |
|---|---|---|---|
| **A — first** | **Wave 1.3 P0 truth/scope containment** | A01–A06 | No unauthorized Repair reads, service-token scope bypass, false Admin success, or approval bypass; integration tests real and unskipped |
| **B — second** | **Repair state, vector isolation and publication recovery** | B01–B07 | `ACTIVE` requires human approval + verified publication; no pending truth; no phantom graph/vector APPLIED; idempotent recoverable transitions |
| **C — third** | **Financial model, exact execution, data activation** | C01–C08 | Steward-governed metrics, exact arithmetic, correct identity/time grain, reconciled immutable data, comprehensive provenance |
| **D — fourth** | **Fail-closed AMC routing, contract parity and Feedback wiring** | D01–D05 | Chat/stream/query share typed truth; no LLM/legacy numeric fallback; frontend Admin workflows operate on real sources; PDF/TXT parity |
| **E — final** | **Independent harness, CI and release gate** | E01–E06 | Fresh clone reproducible, actual passing test evidence, failed/blocked items transparent, tested rollback/canary, release decision |

**Parallelism:** C01/C02 (financial policy, steward data dictionary) can be specified while B is developed, but affected unapproved metrics must remain blocked. **Stop and record a blocker** if a financial interpretation requires steward approval or if an operation would change live data/production infrastructure.

### Source specifications to reuse

- `docs/AMC_Wave1_2_Next_Implementation_Agent_Handoff_2026-11-04.md` (the preceding 553-line implementation plan).
- `docs/AMC_Wave1_1_P0_Closure_Agent_Handoff.md`.
- `docs/AMC_Tasks_3_11_26/AMC_Specs/README_START_HERE.md` and `01_SOURCE_REVIEW_AND_ROOT_CAUSES.md` through `08_OPEN_DECISIONS.md`.
- `remediation/wave1_2/R0/ROUTE_COMPATIBILITY_MATRIX.csv` **as a historical pre-restoration inventory**. Do not use its old "missing" status as current fact; regenerate the current route inventory.
- `remediation/wave1_2/R1/R1-02_REPAIR_SERVICE_AUTH_COMPLETE.md` as implementation notes, not audit certification.

---

## 3. Batch A — truthful API compatibility, identity and human authorization

### A01 — Replace mock Administrative success with real effects or explicit unavailable responses (P0)

**Source:** `backend/app/api/routes/admin.py`, real indexing manager/queue, cache adapters, audit store, graph proposed-edge repository, frontend `mf-context-engine/src/services/api.js`.

- Generate route and **frontend-contract** inventory for all `/api/admin/*` paths and calling components. Record response shape, actual side effect and permission.
- `POST /users/sync`: either implement an actual authorized sync/reconciliation from supported identity store or return an explicit **501 Not Implemented** / **503 Unavailable**, not `completed` with `users_synced=0` and mock note.
- `GET /ingestion/tasks` and `/active`: return real queue/job state and truthful counts, or an explicit availability error; remove hardcoded example task claiming 16,245 records processed.
- `GET /ingestion/proposed-edges`: read real staged evidence-backed proposals; do not return empty list as if no proposals exist when storage is unconnected.
- `POST /ingestion/edges/{edge_id}/confirm` and `/reject`: lookup staged edge, validate current status/evidence/tenant/proposer, require authorized independent reviewer, perform durable state transition; **never report confirmed/rejected without storage mutation receipt**.
- `GET /audit`: enforce actual tenant scoping and pagination; absence of tenant on log entries must not authorize visibility. Ensure only allowed roles can access sensitive evidence.
- `POST /intent-cache/invalidate-domain`, `/intent-cache/clear`, `/cache/clear`: invoke the real cache engines; verify invalidation and response counts. Report failure rather than claiming cleared/invalidated when nothing ran.
- `GET /ingestion/compliance-report`, `/ingestion/staleness`, cache stats and notifications: use actual services/observations; explicit unavailable status if backend not yet wired. **Never fabricate operational/financial metrics**.
- Preserve intentional compatibility contracts by adapting actual data, not manufacturing plausible data. If an endpoint is intentionally retired, update frontend and document a migration.

**Acceptance:** for each path, either *real observable effect supported by persisted evidence* or explicit documented 501/503; **zero fabricated status, count, approval or audit results**. Contract tests exercise frontend-visible behavior using authenticated fixtures.

### A02 — Close remaining Repair read access and tenant filtering (P0)

**Source:** `packages/amc-repair-engine/src/amc_repair/server.py::get_patches_for_entities`, `get_patch_by_id`, `auth.py`, client callers.

- Require authenticated `patch_read` scope or verified user permission for both endpoints.
- Filter to verified tenant; service access requires explicit tenant authority rather than unrestricted `is_service` bypass.
- Only serve eligible published patches through answer-serving APIs. A dedicated reviewer endpoint may expose pending evidence to authorized reviewers, separately from the serving interface.
- Do not return pending corrected values or private provenance to public callers.

**Acceptance:** unauthenticated GET -> 401; wrong scope -> 403; wrong tenant -> 403/404/no records; serving API excludes PENDING/APPROVED/STAGED; valid reviewer gets only authorized review records.

### A03 — Correct token trust boundaries and service scopes (P0)

**Source:** `packages/amc-repair-engine/src/amc_repair/auth.py`, `backend/app/auth/security.py`, `backend/app/auth/service.py`, `backend/app/clients/repair_client.py`, config/deployment files.

**Observed specifics:** Repair tokens are custom two-part HMAC tokens (`payload.signature`), not standard three-part JWTs. `can_approve()` grants any `is_service` principal approval permission. Missing `exp` does not automatically fail. The default service secret is development text. Main-app session tokens contain username/iat/exp/jti only; Repair expects embedded role/tenant fields and verifies a potentially different secret.

- Implement a **clearly separated user delegation or token exchange** into a Repair-specific, narrowly scoped credential. Server resolves live user identity and tenant membership from its trusted auth store; do not trust roles/tenant read from arbitrary caller payload.
- Restrict service identities to explicit scope allowlists: `patch_read`, `patch_create`, and operational scopes; **service identity alone must never constitute a human governance approval**.
- Validate required `exp`, `iat`, `iss`, `aud`, token type, signature, key ID/version and permitted algorithm; choose a maintained standards-based JWT library or well-reviewed workload identity implementation when justified. Support key rotation and revocation as appropriate.
- Fail production/staging startup when `REPAIR_SERVICE_SECRET` is missing/default/weak. Separate human signing keys from workload credentials and least-privilege service grants.
- For privileged HTTP actions, pass a short-lived signed, scope-limited delegation naming the authenticated human approver in addition to the calling service identity.

**Acceptance:** wrong secret/audience/issuer/type; no expiration; expired; tampered; service with `patch_read` requesting approve; cross-tenant; revoked user; stale role; wrong actor -> all denied. Main/Repair integration with valid delegated identities passes using real issue/resolve paths.

### A04 — Enforce four-eyes across every main and microservice approval/promotion (P0)

**Source:** `backend/app/api/routes/governance.py`, `backend/app/api/routes/admin.py` regulatory edge approval, `packages/amc-repair-engine/src/amc_repair/server.py`, repair proposal schemas.

- Read proposer from a server-side immutable proposal/evidence record; require reviewer identity distinct from proposer by stable principal ID, not editable username/JSON provenance.
- Require correct role/tenant, approved evidence version, non-expired authorization and explicit review action. Service-initiated operations cannot satisfy a required human approver on their own.
- Main `/approve/{patch_id}`, `/batch-approve`, `/proposals/{proposal_id}/review`, `/promote/{patch_id}`, and regulatory edge confirmation must call the same policy. **Approve != Activate**.
- Remove any fast path that directly promotes without a valid independent approval receipt. Add concurrency/duplicate/revocation tests.

**Acceptance:** self-approval rejected in all paths, including an admin proposer; forged proposer fails; service token cannot impersonate a second human; changed evidence invalidates old approval.

### A05 — Harden invitations and account lifecycle (P1, do in Batch A)

**Source:** `backend/app/api/routes/admin.py`, `backend/app/api/routes/auth.py`, `backend/app/schemas/invitation_token.py`, DB migrations and auth tests.

- Store only a salted/keyed hash of invitation secrets, not plaintext token; use constant-time comparison or safe equivalent. Deliver token via authorized secure channel; do not put it into routine logs, audit exports or untrusted frontend responses.
- Ensure atomic single-use consumption under concurrent requests (row lock or conditional update) and robust UTC expiry; add replay, brute-force/rate-limit and invitation rollback tests.
- Validate that admin cannot arbitrarily assign tenant/privileged roles beyond authorized scope; remove implicit `"default"` tenant for restricted operations.
- Add an actual migration for invitation table and verify bootstrap/login using a fresh database, not only a pre-existing local DB.

**Acceptance:** replay and concurrent redemption permit exactly one success; no plaintext persisted; invalid or expired token denied; no cross-tenant enrollment or role escalation.

### A06 — Remove skipped authentication/contract tests and test against real effects (P0)

**Source:** `backend/tests/test_wave12_route_compatibility.py`, `backend/tests/test_sec01_universal_auth.py`, `packages/amc-repair-engine/tests/test_repair_service_auth.py`, integration test fixtures.

- Replace `test_admin_token_placeholder` and similar fixtures with actual signed, persisted test users/roles/tenants in an isolated database. Use HTTP TestClient/httpx; no production secrets.
- Remove `@pytest.mark.skip("Requires working JWT")` for required cases. Tests must validate response payload AND persistent effect, not merely 200/401 or fixture string comparisons.
- Add tests for all restored Admin routes (including failure behavior), Repair read endpoints, cross-tenant access, self-approval, trust-boundary token cases, reviewer/steward roles.
- Fail the **release** pipeline if critical security tests are skipped. Test report must list pass/fail/skip counts explicitly.

**Acceptance:** no critical skipped tests; full frontend compatibility flows pass with real JWT/session, real backend stores or explicit unsupported responses.

---

## 4. Batch B — authoritative Repair lifecycle and publication integrity

### B01 — Single persisted correction state machine (P0)

**Source:** `packages/amc-repair-engine/src/amc_repair/schemas.py`, `patch_layer.py`, `backend/app/graph/correction_patch_layer.py`, `backend/app/retrieval/orchestrator.py`.

Define versioned states: `PENDING -> APPROVED -> STAGED -> VERIFIED -> ACTIVE`, plus `REJECTED`, `FAILED`, `ROLLED_BACK`, `SUPERSEDED`, with explicitly permitted transition actors. Model approval as authorization, not publication. Store state, tenant, evidence hash, proposer, independent approver, publication receipt, timestamps and active dataset/corpus version. Reject unknown/legacy status as non-serving until migrated/verified.

**Acceptance:** invalid transition rejected; only `ACTIVE` plus valid receipt/evidence/tenant can influence answers; all path/mode implementations use the same predicate.

### B02 — Remove pending Repair content from serving vector and cache (P0)

**Source:** `backend/app/services/repair_integration.py` synthetic patch insertion, vector client, retrieval/cache clients and event consumer.

Stop inserting provisional correction chunks into ordinary serving FAISS. Use a review-only shadow index, or defer indexing until approved + verified publication; migrate/clean existing provisional entries with a dry-run report. Invalidate relevant serving caches only upon active-version switch. Never let a prompt-like correction notice override authoritative source rules.

**Acceptance:** a fabricated, high-confidence pending correction cannot be retrieved, cited, synthesized or cached as authoritative through standard, streaming or follow-up paths.

### B03 — Graph mutation exact-value verification (P0)

**Source:** `backend/app/services/promotion_service.py`, graph adapter, mutation schema.

- Reject missing mutation Cypher (currently can be marked `applied`), invalid target and unsupported mutations.
- Use allowlisted parameterized mutations; check affected records and expected old/new entity version.
- Read back actual changed field, compare exact typed value to approved expected new value, store immutable receipt. Node presence alone is insufficient.
- Fail closed on driver unavailable, no records, wrong value or graph version conflict.

**Acceptance:** tests for missing driver, no-op Cypher, wrong attribute, wrong value, competing update and successful verified mutation.

### B04 — Real vector reindex, commit and activation (P0)

**Source:** `PromotionService._trigger_reindex` and vector/index manager.

Replace logging-only stub with a real async reindex command + durable job/operation ID and verified index-version readback. Do not mark vector proposals APPLIED until searchable committed index version is known. Support retry, timeout, staging and old active index preservation.

**Acceptance:** fail reindex / no-job / stale active index / restarted worker -> proposal not APPLIED. Positive case -> verified index/hash receipt.

### B05 — Cross-store transactional outbox/saga (P0)

**Source:** RepairProposal/GraphMutation tables, `promotion_service.py`, Feedback-to-Repair linkage, event consumers.

- One proposal per SQL transaction; stage outbox command before external effect.
- Idempotency key from proposal ID + approved evidence version + destination; retry state transitions safely.
- Record `EXTERNAL_APPLIED` and `VERIFIED` separately from active pointer switch; handle crash after Neo4j commit before SQL ack and vice versa.
- Verify compensating rollback and cache/index restoration; no SQL rollback of unrelated earlier external commits.

**Acceptance:** duplicates, concurrent promoters, service timeout, split commit, partial SQL rollback and message replay converge without phantom applied or wrong active state.

### B06 — Feedback → Repair authorization and issue resolution integrity (P1)

**Source:** `backend/app/services/repair_integration.py`, `backend/app/feedback/repair_linkage.py`, review queue, unified feedback records.

`RESOLVED` may only follow verified active patch/superseding evidence and optional independent regression. Failure or missing evidence stays `IN_REPAIR` / `NEEDS_REVIEW`; issue and proposal transitions idempotently correlated. Record receipt and source-diff path in audit.

**Acceptance:** no feedback issue resolves simply because a patch/proposal was created or a cache was cleared.

### B07 — Microservice/monolith/streaming parity and rollout kill switches (P1)

Use the same eligibility rules in all direct query, RAG context, graph, vector, caching, multi-turn and SSE paths. Provide tenant-scoped feature flag to disable Repair application without disabling feedback capture. Test fast-path patch injection as well as fallback path.

**Acceptance:** identical allowed/blocked values and evidence in each mode; emergency switch prevents all patch-driven serving changes.

---

## 5. Batch C — financial correctness, canonical data, reconciliation

The reviewed commit did **not** change core `backend/app/tabular/{planner,executor,repository,csv_excel_loader}.py` or `backend/app/services/scheme_aggregation_service.py`. The earlier financial P0 defects therefore remain open. Reuse G03/G04/G05 and W1.1-01..09, not a new competing stack.

| Task | Required change | Independent gate |
|---|---|---|
| **C01 Metric authority** | `METRIC_REGISTRY_V1`: AAUM is `PENDING_APPROVAL`, but planners still SUM/AVG it. Enforce `metric_id + operation + grain + period + steward_approved` in the **executor**, not only an optional planner validator; audit precompiled SQL. | Unapproved AAUM ranking/SUM/AVG fails `METRIC_POLICY_BLOCKED`, never with a warning plus result. |
| **C02 Exact arithmetic** | Remove SQLite `CAST(aaum_crore AS REAL)` and float conversions for authoritative amounts. Use exact scaled integers or Decimal-safe aggregation/rounding. | Python Decimal independent results exactly match edge-case and production fixture totals. |
| **C03 Scheme identity** | Use canonical AMC/scheme/plan/option keys rather than name-only `GROUP BY scheme_display_name`; create collision registry and explicit unresolved state. | Same-name schemes across AMCs stay distinct; no plan-level double counting. |
| **C04 NAV and time** | Retrieve NAV value and as-of date from the same observation; resolve multiple plan/option matches, date semantics and implicit default filters. | Ambiguity is reported, not arbitrary `LIMIT 1`; comparisons use documented same-date policy. |
| **C05 Source manifest integrity** | Read actual manifest keys (`original_rows`, `chunk_count` where present), verify per-chunk hash, total count, ordering, duplicate coverage and column-level NAV vs AAUM validity. | Corrupted/missing/duplicate chunk prevents activation; separate metric-validity counts shown. |
| **C06 Staged publication** | Stage → validate → steward approve → atomically activate dataset; include source hash, registry version and rollback. No silent switch on row-count reconciliation only. | Clean bootstrap/readiness knows exact active dataset; failed activation leaves prior version untouched. |
| **C07 Contributor evidence** | Record all input-row IDs for aggregates (hash/paginated manifest), exact metric definitions, filters and dataset version. A hash of output rows is insufficient. | Independent recomputation from receipt matches result; stale source invalidates receipt. |
| **C08 Independent gold** | Build 30+ observed CSV failures, deterministic AAUM/NAV/aggregation gold with human steward approvals; preserve 15 then 50+ correct PDF/TXT control cases. | 100% pass on safety-critical financial gold, no fabricated numbers; no synthetic self-grading. |

**Hard rule:** no authoritative AAUM sums, scheme rankings or cross-quarter totals until data steward approves additivity/grain/temporal conventions. If business approval is absent, implement the error path and mark the task BLOCKED rather than inventing a metric definition.

---

## 6. Batch D — query routing, AMC interfaces and real UI behavior

### D01 — Deterministic financial-intent router with fail-closed contracts

Route all financial quantitative intents to approved typed execution for **every** entry point: `/query`, `/query/v2`, `/query/stream`, `/chat`, `/chat/stream`, multi-turn follow-up and service-level direct callers. On unavailable dataset, unapproved metric, ambiguity, no-match or SQL failure, return structured machine-readable errors (`STRUCTURED_SOURCE_UNAVAILABLE`, `METRIC_POLICY_BLOCKED`, `AMBIGUOUS_QUERY`, `NO_MATCH`, `UNSUPPORTED_METRIC`), never RAG/LLM/legacy Pandas numeric guess. Narrative PDF/TXT queries may still use RAG where appropriate.

### D02 — Strict API compatibility and real response effects

Use the generated OpenAPI and frontend `mf-context-engine/src/services/api.js`. Validate that restored endpoints are invoked with the correct verbs, request bodies and shapes. Replace placeholder source data/operation success with actual calls. If backend unavailable, surface explicit error state in the frontend; do not silently pretend the feature worked. Test user CRUD, ingestion status, regulatory edge review, audit stream, cache stats/invalidation and feedback issue dashboards.

### D03 — Feedback and Repair response provenance

Attach source-row and document/page-level citations that support each specific quantitative/narrative claim. Repaired claims carry reviewer and active-version receipts, but never leak confidential reviewer metadata to unauthorized users. UI shows unavailable/needs-review distinctly from confidently correct data.

### D04 — PDF/TXT regression parity

Re-run frozen good document-control questions, source-click navigation, confidence and RAG quality checks. No architecture-only claim; test actual nonstreaming/streaming outputs against independently curated evidence.

### D05 — Operational SLOs and monitoring

Track query route selected, typed-policy decision, dataset version, Repair state, cache invalidations, failed approval attempts, publication receipt and user-facing structured errors. No fabricated quality scores or fixed latency values. Scope logs by tenant and redact sensitive data.

---

## 7. Batch E — independent assurance and release acceptance

### E01 — Fresh-clone reproducibility

Test clean checkout using pinned SHA and isolated dependencies. Set up auth DB, invitation schema/migration, canonical data ingestion, graph/vector fixtures, environment validation and manifests. A developer laptop's existing DB is **not** a reproducible build.

### E02 — Fully executed tests

Run and record the actual commands. Initial suggested targets (adapt dependencies; do not claim success merely because the file exists):

```bash
# From backend/ with isolated test configuration
python -m pytest -q tests/test_sec01_universal_auth.py tests/test_sec01_remaining_routes_and_flow.py
python -m pytest -q tests/test_wave12_route_compatibility.py
python -m pytest -q tests/test_tabular_queries.py tests/test_aggregation_integration.py
python -m pytest -q tests/test_repair_linkage.py tests/test_e2e_user_journey_feedback_repair.py

# From packages/amc-repair-engine/ (with package installed in a venv)
python -m pytest -q tests/test_repair_service_auth.py tests/test_repair_engine.py
```

Additionally create `test_wave13_admin_effects.py`, `test_repair_api_policy.py`, `test_repair_state_machine.py`, `test_publication_saga.py`, `test_financial_gold.py`, `test_numeric_no_fallback.py`, `test_frontend_contract_e2e.py` (names flexible). Tests require real auth principals and dependency fakes/ephemeral services; don't use static assertions like `assert proposer != approver` as proof that the endpoint enforces it.

### E03 — Required adversarial matrix

1. Unauthenticated repair GET/POST/approve/promote → deny; reviewer reads scoped evidence only.
2. Service with only `patch_read` attempting `patch_approve` or `patch_promotion` → deny.
3. Forged header role/tenant and a token with missing exp/wrong audience/issuer/secret → deny.
4. Main-app user token exchange/delegation across actual HTTP service boundary → authorized normal flow works.
5. Caller-created approved patch and proposer self-approval via **main and Repair microservice** → deny.
6. Edge confirmation without actual pending edge, without independent reviewer, or with stale evidence → no `confirmed` result.
7. Cache invalidation while cache backend unavailable → explicit failed/unavailable outcome, not fabricated `cleared`.
8. Unapproved synthetic financial correction → absent from all vector/graph/synthesis/stream/cached answers.
9. Missing mutation, wrong graph value, failed vector reindex, lost acknowledgment and duplicate job → not APPLIED; recovery predictable.
10. Cross-tenant read by ID or broad list → deny/no disclosure.
11. AAUM unapproved SUM and numerical source outage → structured error, never LLM approximation.
12. Legitimate tenant-scoped user/admin flows and PDF/TXT control queries → unchanged or improved.

### E04 — CI / truthful release evidence

Create GitHub Actions or equivalent connected CI for full test sets, static analysis, secure dependencies, secret scans, live route matrix and smoke deployment. Record SHA, environment/data hashes, executed count, passes/failures/skips, link to run and concrete logs. **Do not mark a gate PASS if a critical test is skipped.** The reviewed SHA has no discovered GitHub Actions runs or combined status checks.

### E05 — Versioned rollback and controlled canary

Produce an operator-reviewed migration/backup plan; safe old dataset/index/graph state; automated verification before/after rollback; feature flags and canary rollback signals. No automatic live mutation without explicit authorized operation.

### E06 — Unified release verdict

Report each gate separately: `COMP`, `SEC`, `REP`, `PUB`, `NUM`, `ING`, `E2E`, `OPS`, `PDF/TXT`. `PASS` requires demonstrated evidence; otherwise `REVIEW` or `BLOCK`. Production launch requires all applicable gates passing plus authorized human sign-off.

---

## 8. Codex deliverables — concrete files to create/maintain

Put sanitized results under `remediation/wave1_3/` (folder new; do not delete prior historical records):

```text
remediation/wave1_3/
  SOURCE_BASELINE.md          # exact pinned starting SHA, updated SHA, observed runtime/data config
  CURRENT_ROUTE_MATRIX.csv    # actual app.routes/method, caller, real handler, auth, effect, status
  TASK_STATUS.md              # each A01..E06: DONE/PARTIAL/BLOCKED, links + evidence
  ADMIN_EFFECTS_AUDIT.md      # restore/retire decisions and effect verification
  REPAIR_AUTH_AND_STATES.md   # identity, scopes, tenant, 4-eyes, transitions, active eligibility
  PUBLICATION_SAGA.md         # precise graph/vector receipts, outbox, retries, rollback
  FINANCIAL_POLICY.md         # steward questions, exact grain, metric version, blocked ops
  GOLDEN_RESULTS.md          # only independently approved expected answers (no sensitive dump)
  TEST_RESULTS.md            # commands, environment, timestamps, actual counts, failing cases
  CI_RUNS.md                 # workflow links or explicitly 'NOT_RUN'
  RELEASE_GATE.md            # PASS/REVIEW/BLOCK per gate and overall, no unverified PASS
  ROLLBACK.md                # tested and authorized recovery actions
```

Do not commit secrets, private dataset copies, customer records or full sensitive operational traces to GitHub. Store sensitive evidence in controlled systems and cite hashes/IDs in repo.

**Evidence checklist per task:** inspected behavior → changed code paths → targeted tests → negative tests → cross-module test → reproducible log → failure modes → rollback note → reviewer-required decisions. A new Markdown document alone is **not** implementation.

---

## 9. Ready-to-paste local Codex bulk instruction

```text
ACT AS principal engineer, financial-data architect, security architect and
release-assurance reviewer for NuSummit AMC Context Engineering.

REPOSITORY: nusummit-spg/amc-context-engineering-poc
SOURCE BRANCH: amc-dev
PINNED START SHA: c7aa9203819d21da20f2ad92223ccc4ff32778af
WORKING BRANCH: create feature/wave1-3-truth-and-financial-correctness (or similarly named)

READ this file completely:
AMC_Wave1_3_Next_Actions_Agent_Handoff_2026-11-04.md
Then read the existing Wave 1.2 handoff and original CTO specs in the repo.
Verify latest code and the stated defects before changing anything; do not re-create
what is already correctly implemented.

EXECUTION: take BULK BATCH A (A01-A06) first, with complete runnable tests.
Then B (B01-B07), C (C01-C08), D (D01-D05), E (E01-E06), with separate,
reviewable logical changes and truthful evidence. Safe financial policy work
may proceed in parallel, but never serve unapproved AAUM aggregation.

NON-NEGOTIABLE:
1. No fake/placeholder 'success', 'completed', 'cleared', 'confirmed' or metrics.
2. No public untrusted Repair reads or caller/service-token permission escalation.
3. No service actor qualifies as an independent human approver by itself.
4. Every approval requires authorized human actor distinct from proposer,
   evidence version, correct tenant and durable receipt.
5. Only verified ACTIVE patches with publication receipt enter serving/graph/vector.
6. No false APPLIED from missing mutation, no-op reindex, wrong graph readback,
   partial SQL rollback or duplicate command.
7. Exact, steward-approved deterministic financial metrics only; fail closed
   on unapproved operation, data absence, ambiguity or SQL error.
8. Preserve original PDF/TXT working paths and frontend workflows.
9. No production deployment or live data mutation. No forced branch rewrites.
10. Tests must be RUN, not only written; critical skip counts must be zero.

FOR EACH BATCH DELIVER:
- Code changes and committed executable tests.
- DONE/PARTIAL/BLOCKED by task ID with actual evidence.
- SHA, commands, exit codes, pass/fail/skip counts and real CI IDs when available.
- Reproducible financial gold; auth/tenant/repair adversarial matrix.
- Precise rollback and unresolved steward/operator decisions.
- Gate verdict PASS/REVIEW/BLOCK; overall BLOCK until full validation.

After Batch A, if another batch is blocked, continue all safe independent tasks,
record the blocker, and never manufacture authorization or success. Do not ask
for microtask-by-microtask approval; execute bulk work inside a safe feature branch.
```

---

## 10. CTO re-audit checklist and decision

**Before requesting the next re-audit**, share branch/PR URL, latest SHA, actual test and CI run links, current route matrix, actual Admin effect verification, Repair service auth integration tests, state-machine/rollback receipts, financial golden outputs (or restricted proof), dataset/corpus hash and outstanding business sign-offs.

**At reviewed `c7aa920`**: compatibility routes and service-auth infrastructure are **partial foundations**, not a complete implementation. Keep the production gate **BLOCK**. The next code changes must remove false-success paths and the remaining trust-boundary issues, then complete Repair publication and independently verified financial correctness.
