# AMC Context Engineering — CTO Remediation Handoff

**Deliverable:** Wave 1.1 P0 Closure + Financial Correctness Forward Plan  
**Date:** 4 November 2026  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Reviewed branch:** `feature/wave1-canonical-data-and-typed-queries`  
**Reviewed commit (pin for this audit):** `910bae72030cbf641badbdb6e2c6fe82b78a9479`  
**Previous review commit:** `06cf9755f4b3dde3e9a24a430973f4bf86ed711d`  
**Delta inspected:** Five commits, 18 changed files  
**Release recommendation:** **BLOCK** until independent tests establish security, Repair-governance, publication, and financial-correctness gates.

> **Instructions to local Codex/engineering agent:** This document is a self-contained, actionable remediation specification for the latest branch. It supplements, but does not erase, the existing 196-task CTO blueprint. Implement code and tests—not documentation-only checkmarks. Keep AMC Core, Feedback, and Repair as logical modules, with a shared assurance policy. Do not deploy, alter live facts, or merge into a release branch without explicit authorized approval.

## 1. GitHub context and documents to consult

- [Current feature branch](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/feature/wave1-canonical-data-and-typed-queries)
- [Existing Wave 1.1 execution instructions](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/910bae72030cbf641badbdb6e2c6fe82b78a9479/docs/AMC_Wave1_1_Codex_Execution_Sequence.md)
- [Original architectural specifications](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/910bae72030cbf641badbdb6e2c6fe82b78a9479/docs/AMC_Tasks_3_11_26/AMC_Specs)
- [Wave 1.1 reports and status](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/910bae72030cbf641badbdb6e2c6fe82b78a9479/remediation/wave1_1)

Read `README_START_HERE.md`, `02_TARGET_ARCHITECTURE_AND_CONTRACTS.md`, `04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md`, `05_ASSURANCE_SECURITY_RELEASE_GATES.md`, `03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md`, `06_GOALS_AND_TASKS.md`, `07_CODEX_EXECUTION_PLAYBOOK.md`, and `08_OPEN_DECISIONS.md` from `docs/AMC_Tasks_3_11_26/AMC_Specs/`.

**Evidence limitations:** These findings come from a static read of the pinned GitHub source, not a runtime penetration test, deployment inspection, or CI execution. No GitHub Actions runs or commit-associated status checks were found for the reviewed branch. Do not infer public exploitability if an additional private gateway restricts access; verify ingress, all mounted routes, and service exposure in integration tests.

## 2. What is already improved — preserve these changes

1. `backend/app/api/routes/admin.py`: user CRUD now uses `CurrentUser` and an admin-role check.
2. `backend/app/api/routes/audit.py`: several audit-schema handlers require an authenticated user.
3. `backend/app/services/repair_integration.py`: main feedback-triggered flow sets `claim_is_auto_approved = False`.
4. `backend/app/services/promotion_service.py`: added driver-failure intent and a graph read-back check.
5. `backend/app/retrieval/orchestrator.py`: introduced `ACTIVE` plus `approved` checks in some serving paths.

**These are partial improvements, not proof that the system is production safe.** Do not reimplement working changes unnecessarily; correct the residual gaps below and add executable tests.

## 3. Release blockers — source findings

| ID | Severity | Finding | Reviewed source / action |
|---|---|---|---|
| SEC-01 | P0 | Many non-CRUD Admin routes lack an authenticated principal, including `/admin/audit`, `/admin/ingestion/run`, `/admin/ingestion/upload`, and cache controls. The main app registers routers without a global auth dependency. | `backend/app/main.py`, `backend/app/api/routes/admin.py`; classify and protect each sensitive handler. |
| SEC-02 | P0 | Governance authorization still derives role from client-controlled `X-User-Role`; `get_client_role()` now rejects missing headers but still accepts role claims from the caller. | `api/routes/governance.py`, `app/compliance/security.py`; use verified identity, scopes, and membership. |
| SEC-03 | P0 | Sensitive standalone ingestion and source-file routes lack consistent identity/tenant enforcement; some audit-schema reads use auth without ownership filters. | `api/routes/ingest.py`, `files.py`, `graph.py`, `audit.py`; verify route inventory and tenant-specific policies. |
| SEC-04 | P0 | Predictable password `Welcome@2026` is still assigned on account creation. | `api/routes/admin.py`; use secure invitation/enrollment and remove password reflection. |
| REP-01 | P0 | Main-app governance `/run-batch` still approves/promotes by confidence/risk. | `api/routes/governance.py`; remove confidence as authorization. |
| REP-02 | P0 | Independent Repair `governance.py::run_batch()` still auto-approves pending patches above `auto_approve_confidence`. | `packages/amc-repair-engine/src/amc_repair/governance.py`; shared human authorization policy. |
| REP-03 | P0 | Standalone Repair API accepts caller `approved: bool` during patch creation and has direct approve/batch/promote handlers without verified principal dependencies visible in source. | `packages/amc-repair-engine/src/amc_repair/server.py`; reject caller authorization and authenticate service/end-user actors. |
| REP-04 | P0 | Orchestrator checks `status == ACTIVE` but underlying patch model lacks an explicit status; fallback injection filters by `approved` alone. | `amc_repair/schemas.py`, both `patch_layer.py` variants, `orchestrator.py`; one authoritative persisted state machine. |
| REP-05 | P0 | Synthetic patch chunks can be ingested into the vector store before review; retrieval-side isolation has not been demonstrated. | `services/repair_integration.py`; only stage non-serving evidence until approved and published. |
| PUB-01 | P0 | `promotion_service.py` imports exceptions from `app.exceptions`, absent from the reviewed Git tree; a claimed `app/exceptions/promotion_exceptions.py` file also was not found. | Fix actual module/import; add cold-import/failure tests. |
| PUB-02 | P0 | Empty `mutation_cypher` can still mark graph proposal APPLIED; vector `_trigger_reindex()` only logs but caller marks APPLIED. | `services/promotion_service.py`; no-op is never publication. |
| PUB-03 | P0 | Graph post-commit check only tests entity presence, not the intended attribute's actual value. | `promotion_service.py::_execute_graph_mutation()`; verify exact, typed postcondition. |
| PUB-04 | P0 | Several proposal applications share one SQLAlchemy transaction; a rollback for a later failure can discard SQL state after an earlier external Neo4j commit. | `promotion_service.py`; proposal-level saga/outbox, idempotent recovery and compensation. |
| QA-01 | P0 | Documentation claims two new security test modules, but neither exists in the reviewed `backend/tests` directory; no matching CI runs were found. | Create and execute actual tests; reconcile status reports. |
| NUM-01 | P0 | AAUM has `PENDING_APPROVAL` in the metric registry, yet `SUM(CAST(aaum_crore AS REAL))` executes; executor does not enforce metric approval. | `tabular/contracts.py`, `planner.py`, `executor.py`; block unapproved operations. |
| NUM-02 | P0 | Real/float math undermines exact Decimal financial totals. | `planner.py`, `scheme_aggregation_service.py`; use exact arithmetic. |
| NUM-03 | P0 | Legacy CSV/Pandas fallback and LLM numeric fallback can still run; typed DB absent on clean deployment. | `scheme_aggregation_service.py`, `fast_path_interceptor.py`, `orchestrator.py`; fail closed for numbers. |
| NUM-04 | P1 | Scheme grouping by display name, NAV maximum/date association, `LIMIT 1` ambiguity, temporal and manifest weaknesses remain. | Canonical tabular layer; independently verify identity, period, row provenance. |

**Documentation discrepancy:** `remediation/wave1_1/COMPLETE_IMPLEMENTATION_SUMMARY.md` claims universal security/test success, while other status/release files still mark critical tasks partial or pending. Reconcile reports only after running actual tests, and avoid writing `PASS` based on the presence of a code comment or a test command.

## 4. Bulk execution plan and dependency order

Implement a **single P0 closure program** with separate reviewable PRs/commits:

| Order | PR / batch | Task IDs | Minimum exit condition |
|---|---|---|---|
| 1 | **Security boundary** | SEC-01..SEC-04 | No unauthenticated sensitive operations, forged roles, tenant bypass, or default credentials. |
| 2 | **Repair governance and serving isolation** | REP-01..REP-05 | No confidence-only approval or pending/staged evidence in user answers, graph, or authoritative vectors. |
| 3 | **Publication correctness and recovery** | PUB-01..PUB-04 | Successful mutations verified; failed/partial operations not APPLIED; retries/rollback safe. |
| 4 | **Runnable assurance** | QA-01..QA-03 | Source + tests + real logs + clean-run CI and accurate gate report. |
| 5 | **Financial correctness next** | NUM-01..NUM-04, W1.1-01..09, W1.1-13..14 | Approved metric semantics, exact values, complete evidence, no numeric hallucination. |

Security and Repair test design can run in parallel, but **do not publish a shared `ACTIVE` state until its approval, version and publication semantics are implemented**. Use a new remediation branch from pinned commit. No force-push to existing feature/release branches.

## 5. Implementation details and acceptance contracts

### SEC-01 — Complete authentication and endpoint matrix

- Build a **runtime FastAPI route inventory** from `app.routes`: method/path, public designation, auth dependency, required role/scope, tenant binding, document class and data exposure. Include aliases, deprecated and undocumented routes; include standalone Repair service.
- Use an explicit, minimal public allowlist; all other sensitive reads/writes must require mandatory `CurrentUser` or authenticated workload identity. Account creation/deletion, audit stream, ingestion triggers/uploads, file downloads, graph endpoints, cache-clear, edge approval and Repair operations must be covered.
- Add 401/403 negative tests for all sensitive operations, not just user CRUD. Ensure fresh-authenticated valid use cases still work.
- **Gate:** no unclassified sensitive endpoint in the mounted API; protection validated through `TestClient`/httpx, not just function signatures.

### SEC-02 — Server-authoritative role and tenant

- Remove `Depends(get_client_role)` from security-sensitive governance routes, or refactor to a server-authoritative verified principal; never treat `X-User-Role`, `X-User-ID`, `X-User-Tier`, `authorized_by`, or JSON role/tenant fields as grants.
- Require explicit authorized tenant membership; `get_tenant_id(user)` fallback to department/`default` is not a suitable boundary for multiple tenants. Filter every tenant-owned read/write and by-ID retrieval.
- **Gate:** unsigned `X-User-Role: admin` => 401; valid low-privilege bearer plus forged admin role => 403; cross-tenant objects not returned or mutated; correct tenant reads succeed.

### SEC-03 — Secure enrollment and credentials

- Remove predictable `Welcome@2026` defaults and any plaintext credential reflection. Implement single-use expiring invite/reset or secure enrollment, role-change audit and production-secret validation.
- **Gate:** no known common password for new accounts; admin bootstrapping cannot elevate untrusted users.

### SEC-04 — Service-to-service authorization

- Protect direct Repair microservice requests with verified workload/service identity and require real human approver identity for governance actions. Restrict network ingress as defense in depth, not sole authorization.
- **Gate:** unauthenticated external calls to create, approve, batch-approve, promote, reject or retrieve sensitive patches cannot succeed.

### REP-01 — Unified human approval policy

- Disable main `governance.py::run_governance_batch()` confidence-based promotion and independent `amc_repair/governance.py::run_batch()` confidence-only approval. Enforce the same policy for direct and background/cron calls.
- Remove authorization semantics from `CreatePatchRequest.approved`: reject supplied `approved=true`, or ignore it and force pending; do not accept client claims of `ACTIVE`.
- Enforce independent human authorization: `approver_id != proposer_id`, verified role, explicit evidence/version, timestamp, reason and review decision. Confidence is a risk/triage signal only.
- **Gate:** even confidence `1.0`, low risk and caller `approved=true` never independently promote a patch.

### REP-02 — Patch state machine as one source of truth

- Introduce persisted `PENDING`, `APPROVED`, `STAGED`, `ACTIVE`, `REJECTED`, `FAILED`, `ROLLED_BACK`, `SUPERSEDED`; define legal transitions and actors. Human approval is not equivalent to activation.
- Centralize `is_serving_eligible(patch, principal, active_version)` and apply it to local/microservice/Redis/graph/vector/caches and streaming/non-streaming retrieval. Unknown/missing state fails closed, not `ACTIVE`.
- **Gate:** pending, approved-but-unpublished and unversioned corrections are absent from all answer context and evidence paths.

### REP-03 — Isolate synthetic pending evidence

- Stop `repair_integration.py` inserting synthetic correction chunks into the normal vector serving index before human approval. Store provisional material in isolated staging/shadow index, inaccessible to user retrieval.
- Publish into serving graph/vector only with verified receipt and correct version; invalidate caches after activation, not after merely creating a patch. Replace imperative natural-language overrides with structured claim-level correction receipts.
- **Gate:** adversarial pending correction cannot contaminate FAISS/vector, graph, cached answer, streamed answer or follow-up.

### REP-04 — Audit and four-eyes transitions

- Persist reviewer, proposer, approved version, source evidence, authorization and subject/tenant, plus revocation and stale-evidence handling. Reject self-approval and conflicting concurrent approvals.
- **Gate:** tests for cross-tenant approval, self-approval, stale evidence, double approve, and revoked authorization pass.

### REP-05 — Ensure module parity

- The main orchestrator now checks `status=ACTIVE` in some branches, yet `amc_repair.schemas.CorrectionPatch` only declares `approved`, and `app/graph/correction_patch_layer.py` fallback only checks `approved`. Fix both or remove unsafe fallbacks.
- **Gate:** same answer/evidence behavior for monolith and microservice modes; do not treat a status check performed by a caller as sufficient if the callee independently re-evaluates a broader set.

### PUB-01 — Fix import, no-op and reindex failures

- Resolve `from app.exceptions import PromotionFailedError, PromotionVerificationError` against a real committed module. Validate cold imports with tests.
- If graph `mutation_cypher` is absent, fail; do not mark APPLIED. `_trigger_reindex()` currently only logs: implement real vector index change, verification and activation, otherwise return NOT_APPLIED.
- **Gate:** missing import/driver/mutation or no-op vector reindex cannot produce APPLIED status.

### PUB-02 — Strong graph mutation postconditions

- Use scoped, parameterized and allowlisted graph mutation operations. Confirm the approved entity/attribute is exactly updated; a node merely existing after commit is insufficient. Record expected old/new values, normalized type, source version and read-back receipt.
- **Gate:** graph property unchanged/wrong value => failure; exact correct value => verified receipt. Avoid misleading 'verified' logs when only entity existence was tested.

### PUB-03 — Transactional recovery across data planes

- Avoid applying many proposals with one SQLAlchemy transaction while external graph/vector mutations commit independently. Use per-proposal durable saga/outbox, idempotency key (`proposal_id`, approval version, target), external receipt and final activation after verification.
- Handle crash-after-graph-commit-before-SQL-commit, duplicate event, concurrent retry, vector failure after graph success, and cache activation failure. Preserve prior active version; support tested compensation/rollback.
- **Gate:** no phantom APPLIED, no unintended duplicate mutation, and consistent final status after retries and partial failures.

### PUB-04 — Publication state and direct API correctness

- `APPLIED` or `ACTIVE` must require matching approved evidence, an actual graph/vector effect and an auditable receipt. Never assume internal log message or non-throwing method is evidence of mutation.
- Recheck API status responses, event transitions, and `RepairProposal`/`GraphMutation` persistence. Do not auto-resolve Feedback solely on patch creation.
- **Gate:** correct `PENDING → APPROVED → STAGED → VERIFIED → ACTIVE` progression, or explicit failure/compensation.

### QA-01 — Create the test files claimed by documentation

The reviewed branch did **not** contain the claimed:

- `backend/tests/test_wave1_1_batch0_batch1_security.py`
- `backend/tests/test_sec01_universal_auth.py`

Create and actually run these (or update documentation with equivalent **existing, executed** tests). Add purpose-built tests for governance bypass, provenance contamination and publication recovery. The absence is a verified source-tree observation, **not** evidence that no other security tests exist.

### QA-02 — Minimum adversarial test suite

1. Anonymous Admin audit/ingestion/cache/mutation => 401.
2. Forged admin role header without token => 401; non-admin JWT + forged header => 403.
3. Wrong-tenant reads/writes/approvals => denied.
4. Predictable account password cannot be used after new-user creation.
5. Caller `approved=true` rejected; `confidence=1.0` remains pending.
6. Direct microservice, main governance, batch scheduler all enforce four-eyes.
7. Missing driver, no mutation, wrong property, empty reindex => never APPLIED.
8. One success then one failure in same batch => SQL/Neo4j consistency retained.
9. Crash after graph commit, concurrent retries and duplicate events converge idempotently.
10. Pending patch in synthetic vector chunk cannot influence standard/streaming/cached answers.
11. Unauthorized status transitions and stale evidence fail closed.
12. Working PDF/TXT responses do not regress.

Run in both monolith and microservices deployment modes if both are supported; otherwise explicitly disable and test the unsupported mode.

### QA-03 — Real CI and truthful implementation reporting

- Create CI for import/startup, full auth matrix, repair approval safety, failure injection, tabular and PDF/TXT regression. Run from a clean checkout with isolated test DB and temporary graph/vector fixtures.
- Record actual command, exit code, passed/failed/skipped, SHA, dataset/source manifest, environment and CI run ID. No `expected PASS` presented as executed results.
- Reconcile `COMPLETE_IMPLEMENTATION_SUMMARY.md`, `BATCH_0_1_SUMMARY.md`, `batch0_batch1/STATUS.md` and `RELEASE_GATE.md`; claim DONE only when code and tests prove it.

## 6. Financial correctness tasks remaining after P0 closure

The latest push did not change the key tabular implementation. Preserve and execute the earlier Wave 1.1 financial backlog:

| Existing ID | Requirement | Acceptance |
|---|---|---|
| W1.1-01 | Validate metric/operation approval inside executor; no AAUM aggregation while `PENDING_APPROVAL` | Explicit `METRIC_POLICY_BLOCKED` |
| W1.1-02 | Remove `CAST(... AS REAL)`/float financial computation; exact Decimal or scaled-integer arithmetic | Independent numeric golden totals exact |
| W1.1-03 | Use approved canonical scheme/plan IDs; no display-name-only grouping | Collision and double-count tests pass |
| W1.1-04 | Choose NAV value and NAV date from same plan observation; reject non-unique exact lookup | Correct row or ambiguity |
| W1.1-05 | Explicit quarter, NAV as-of and user filters; no undocumented defaults | Correct time/population scope |
| W1.1-06 | Validate actual manifest keys, chunk checksums and per-field validity | Incomplete/corrupt input blocks activation |
| W1.1-07 | Stage, validate, approve and atomically activate version; fail cold-start safely | Clean-clone + rollback tests pass |
| W1.1-08 | No Pandas/LLM fallback after typed financial errors | Structured fail-closed response |
| W1.1-09 | Every aggregate returns complete contributing row evidence and hash | Independent reconstruction passes |
| W1.1-13 | Build independently approved financial gold, ≥30 bad CSV cases and ≥15 then ≥50 PDF/TXT controls | Critical numeric correctness 100% |
| W1.1-14 | CI, cold-deploy, release assurance | Reproducible evidence, signed gate |

**Business decision:** AAUM grain/additivity, `Closure_Date` semantics, scheme identity and cross-quarter policy require approval from an appropriate AMC data steward. Codex must not infer these from sorting or apparent output plausibility. Until signed off, affected authoritative sums must fail closed.

## 7. Expected artifacts, test commands and final release gate

### Evidence directory in the repository

Use `remediation/wave1_1/p0_closure/` for the sanitized handoff artifacts:

```
SOURCE_BASELINE.md          # exact SHA, component/data versions, route inventory
TASK_STATUS.md             # each SEC/REP/PUB/QA task: DONE/PARTIAL/BLOCKED
AUTH_MATRIX.csv             # route x role x tenant x expected result
REPAIR_STATE_CONTRACT.md    # state diagram, transitions, actors, caches
PUBLICATION_RECOVERY.md    # idempotency, saga, receipts, rollback
TEST_RESULTS.md            # commands, actual results, missing/failing tests
FAILURE_INJECTION.md       # retry/crash/partial-commit tests
RELEASE_GATE.md            # PASS/REVIEW/BLOCK with evidence and signoff
ROLLBACK.md                # tested non-destructive restore strategy
```

Recommended commands to execute *after files are actually created* (from `backend/`):

```bash
python -m pytest -q tests/test_wave0_verification.py tests/test_tabular_queries.py
python -m pytest -q tests/test_wave1_1_batch0_batch1_security.py tests/test_sec01_universal_auth.py
python -m pytest -q tests/test_authentication_enforcement.py tests/test_repair_linkage.py tests/test_e2e_user_journey_feedback_repair.py
python -m pytest -q tests/test_repair_governance_invariants.py tests/test_publication_recovery.py
```

The last two test modules are proposed new tests. None of these commands is represented here as already run. Use temporary databases and fake/isolated graph and vector services; do not run destructive tests on production.

**Mandatory gates:**

- `SEC`: all sensitive routes/auth/tenant/credentials proven safe.
- `REP`: human approval and active-state serving isolated across all modules.
- `PUB`: verified graph/vector operations, replay and rollback proven.
- `NUM`: business-approved exact financial calculations with contributing evidence.
- `OPS`: actual CI, clean deployment, rollback and PDF/TXT parity.

Any critical gate failure yields overall **BLOCK**. An internal `REVIEW` is *not* authorization to deploy. Only owner-approved operational release with evidence can change this.

## 8. Ready-to-paste local Codex prompt

```text
You are the principal engineer implementing CTO P0 remediation for
nusummit-spg/amc-context-engineering-poc.

BASE COMMIT: 910bae72030cbf641badbdb6e2c6fe82b78a9479
SOURCE BRANCH: feature/wave1-canonical-data-and-typed-queries
Create a new remediation branch. Do not force push, mutate production, or deploy.

READ FIRST: AMC_Wave1_1_P0_Closure_Agent_Handoff.md (this file),
docs/AMC_Wave1_1_Codex_Execution_Sequence.md, and
all CTO blueprint specifications under docs/AMC_Tasks_3_11_26/AMC_Specs/.

EXECUTE A SINGLE BULK P0 CLOSURE PROGRAM IN AUDITABLE PRs:
PR-A SEC-01..SEC-04 (universal authenticated route/tenant protection).
PR-B REP-01..REP-05 (shared human approval, patch states, isolation).
PR-C PUB-01..PUB-04 and QA-01..QA-03 (publication, recovery, tests/CI).

NON-NEGOTIABLES:
- No client header, role field, or 'approved=true' can elevate trust.
- No automatic canonical approval based on confidence.
- Four-eyes: approver != proposer; approval is not publication.
- Pending/staged data never enters the authoritative answer/graph/vector path.
- No APPLIED status for absent graph mutation, unverified graph value,
  no-op vector index, missing driver, or partial SQL rollback.
- Reproduce alternate routes, microservice paths and streaming/cached paths.
- Add and RUN the claimed missing test modules and negative tests.
- Record actual test outputs and SHA; do not assert unsupported success.
- Preserve PDF/TXT functionality and source fidelity.
- Prevent fallback from authoritative numeric errors to LLM/Pandas.
- Stop and mark BLOCKED for unknown data steward policy or irrecoverable
  external mutations. Do not invent business approval.

DELIVER: code diffs, executable tests, full route auth matrix, unified repair
state-machine, publication receipts/rollback, real CI/test results,
DONE/PARTIAL/BLOCKED task matrix, and PASS/REVIEW/BLOCK per gate.

NEXT BATCH (separate PR): W1.1-01..09 financial correctness, W1.1-13..14
independent assurance. Keep unapproved AAUM sums blocked until authorized.
```

## 9. Evidence requested for CTO re-audit

Provide the resulting PR/branch URL, HEAD SHA, source/data version hashes, committed test files, CI run link or exact local test log, endpoint permission matrix, Repair approval and failure-injection results, financial gold results, outstanding data-steward decisions, and rollback receipt. I will compare source behavior and independent evidence rather than optimistic summary status.

**Current audited state:** `BLOCK` at `910bae72030cbf641badbdb6e2c6fe82b78a9479` (static source review).
