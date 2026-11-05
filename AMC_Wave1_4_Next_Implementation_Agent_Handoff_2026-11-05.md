# AMC Context Engineering — Wave 1.4 CTO Re-Audit & Bulk Codex Handoff

**Prepared:** 5 November 2026  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Target:** `amc-dev`  
**Pinned reviewed SHA:** `73cb485af2f2057f8ee181c7ad9d63130e43b8d0`  
**Comparison baseline:** `c7aa9203819d21da20f2ad92223ccc4ff32778af`  
**Change set:** 9 commits ahead, 0 behind; 34 files changed.  
**Assessment:** Remote static GitHub source review. Code was inspected; no tests were independently run and no production/staging behavior was observed. The repository reports some local test passes, but GitHub Actions and commit status checks returned none for this SHA.  
**CTO decision:** **BLOCK** for production release; safe to continue implementation on an isolated branch.

> **INSTRUCTIONS FOR LOCAL CODEX AGENT:** This is an executable implementation contract. Read it fully, inspect the latest repository state, implement each assigned batch in code (not only Markdown), execute tests with actual evidence, and retain all blocked items. This plan supplements—not supersedes—the original AMC 196-task remediation blueprint and prior Wave 1.1/1.2/1.3 handoffs. Do not reimplement existing features unless actual behavior fails contract tests.

## 1. Sources and handoff chain

- [Reviewed amc-dev source at pinned SHA](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/73cb485af2f2057f8ee181c7ad9d63130e43b8d0)
- [Wave 1.3 previous handoff](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/73cb485af2f2057f8ee181c7ad9d63130e43b8d0/docs/AMC_Wave1_3_Next_Actions_Agent_Handoff_2026-11-04.md)
- [Original CTO specifications](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/73cb485af2f2057f8ee181c7ad9d63130e43b8d0/docs/AMC_Tasks_3_11_26/AMC_Specs)
- [Wave 1.3 status report](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/73cb485af2f2057f8ee181c7ad9d63130e43b8d0/WAVE_1.3_FINAL_STATUS.md)
- [Wave 1.3 detailed test log](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/73cb485af2f2057f8ee181c7ad9d63130e43b8d0/remediation/wave1_3/TEST_RESULTS.md)

**Read first in this order:** (1) this document; (2) Wave 1.3 handoff; (3) original `02_TARGET_ARCHITECTURE_AND_CONTRACTS.md`; (4) `04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md`; (5) `03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md`; (6) `05_ASSURANCE_SECURITY_RELEASE_GATES.md`; (7) `06_GOALS_AND_TASKS.md`; (8) `07_CODEX_EXECUTION_PLAYBOOK.md`; (9) `08_OPEN_DECISIONS.md`. Read the actual source files, not just summaries, before modifying anything.

## 2. What the latest push genuinely added

The implementation significantly expanded since Wave 1.3: 

- **Security:** authenticated Repair read paths and stricter service-token validation, scope checks, and tenant-related tests (`packages/amc-repair-engine/src/amc_repair/{auth.py,server.py}`; `test_wave13_auth_hardening.py`).
- **Repair lifecycle:** a typed `PatchStatus` state machine and ACTIVE-only serving helper in the package's patch layer (`schemas.py`, `patch_layer.py`); tests for state-based serving and non-serving conditions.
- **Graph mutations:** additional read-back validation and receipt storage (`backend/app/services/promotion_service.py`, migration `004`/`005`; `test_wave13_graph_verification.py`).
- **Publication foundations:** reindex job table, outbox events, rollback service, Prometheus metrics and migrations `006`–`008`, plus test files.
- **Administrative workflows:** token hashing during account invitation creation, more guarded mutation routes and explicit error responses for some unavailable integrations.
- **Evidence:** `WAVE_1.3_FINAL_STATUS.md`, remediation progress documents, new unit tests. The committed `remediation/wave1_3/TEST_RESULTS.md` records **31 passing** Repair authentication tests on Windows/Python 3.12; these results were **not** rerun by this reviewer.

**DO NOT ACCEPT:** “B01–B07 COMPLETE” or “verified reindex/rollback/outbox” merely because schemas, logs, receipt dictionaries, or mocked unit tests exist. A verified operation must produce an observable external effect and a reproducible postcondition. The status report itself says some items are design-only, while its headline calls Batch B complete; reconcile this contradiction.

### Current gate snapshot

| Gate | Source observation | Current review |
|---|---|---|
| Identity / Repair authentication | New authenticated reads and tests; integration/tenant claims still need full exercised routes | PARTIAL / verify |
| Invitation onboarding | Creation stores HMAC hash, redemption queries now-removed plaintext field | **BLOCK** |
| Synchronous-to-async promotion | Synchronous governance endpoint calls async `apply_approved_proposals()` with no `await` | **BLOCK** |
| Patch state policy | Typed states and can_serve exist in package; legacy and vector paths remain | PARTIAL / BLOCK |
| Graph mutation verification | Readback compares values; loose float tolerance and post-commit failure handling remain | PARTIAL / BLOCK |
| Reindex verification | Records `completed`, `verified=True` without executing actual FAISS reindex | **BLOCK** |
| Outbox | Graph/state handlers are log-only yet processor can mark event completed | **BLOCK** |
| Rollback | Graph/vector rollback handlers are log-only; proposal can be marked rolled_back | **BLOCK** |
| Financial accuracy | AAUM safety bypass, floats, grouping and routing unchanged | **BLOCK** |
| CI, independent gold, release | No Actions runs/statuses for reviewed head, significant mocking | **BLOCK** |

## 3. Critical source findings: severity, proof, remediation

### P0-01 — Invitation creation/redemption schema mismatch; onboarding broken

**Source:** `backend/app/api/routes/admin.py` (create_user, now stores `InvitationToken.token_hash`); `backend/app/api/routes/auth.py` (`accept_invitation` still filters `InvitationToken.token == payload.invitation_token`); `backend/app/schemas/invitation_token.py` (declares `token_hash`, not `token`); `backend/app/auth/invitation_tokens.py`.

**Observed:** The create path hashes the invitation token but the redemption path still filters on `InvitationToken.token`. On the reviewed model, that attribute is absent. This can raise an exception before any redemption, making new-account enrollment fail. The rate-limit and single-use helpers introduced in the same push are not wired into redemption.

**Fix:** Calculate the HMAC hash from the incoming token and query by `token_hash`. Enforce expiration, attempt limit, atomic one-time redemption with race control, replay rejection, and consistent error semantics. Use an environment-backed strong secret; verify Alembic migration compatibility for pre-existing invite records. Do not expose token/hash in logs. Test a real admin-create → invite redemption → login flow and double-redemption race using an isolated database.

**Acceptance:** Newly generated invitations redeem exactly once, concurrent double redemption activates only once, expired/rate-limited tokens fail, no plaintext is stored, no backend 500 on valid invite.

### P0-02 — Governance promote handler calls coroutine without awaiting

**Source:** `backend/app/api/routes/governance.py::promote_approved_proposals` (regular `def`, calls `result = service.apply_approved_proposals(...)`); `backend/app/services/promotion_service.py` (`async def apply_approved_proposals`).

**Observed:** The route calls an async function without awaiting it. This creates a coroutine rather than applying proposals. The framework may fail serializing that coroutine or otherwise fail to execute mutations. A logged `status: success` is not evidence of publication.

**Fix:** Use `async def` endpoint and `await` service invocation, with explicit error mapping and response model. Audit all other call sites of `apply_approved_proposals()` and `_trigger_reindex()` for sync/async mismatch. Require an integration test via FastAPI that asserts actual persisted effects and explicitly awaits the path.

**Acceptance:** End-to-end authorized promotion actually invokes the service, returns a serializable result and commits only after postcondition/receipt; no coroutine warnings.

### P0-03 — Reindex completion receipt fabricated without vector index update

**Source:** `backend/app/services/promotion_service.py::_trigger_reindex` (lines around 328–420).

**Observed:** The function says it *would* trigger an actual FAISS rebuild, calculates `document_count`, and writes `status="completed"`, `verified=True` in a receipt and `ReindexJob`. It does **not** call a vector indexer, stage an index, activate one, or verify a changed corpus/version. Existing tests assert the recorded job, not vector results; one test treats a zero-document reindex as verified success.

**Fix:** Integrate the real existing indexing manager/vector store under controlled staging; produce a content/index manifest hash, counts, source version and query probe; atomically activate only verified index versions. A no-op, unavailable indexer, zero expected matched docs, or hash mismatch must fail unless a separate explicit `NO_CHANGE_VERIFIED` policy is justified and audited. Never turn an intent receipt into a verified receipt.

**Acceptance:** For a controlled fixture, index version/hash changes as intended, post-reindex query sees the expected revised facts and unauthorized versions remain unseen; indexer failure results in FAILED / retryable, never APPLIED.

### P0-04 — Outbox can report completion for operations that never occurred

**Source:** `backend/app/services/outbox_processor.py` (`_execute_graph_mutation`: “Would execute graph mutation”; `_execute_state_transition`: “Would transition patch”; `process_pending_events`: marks any handler return `completed`).

**Observed:** Two handlers log intended actions but perform no graph mutation or patch transition. They can therefore produce **completed events without effects**. More seriously, `PromotionService.apply_approved_proposals` writes an outbox event and performs graph/vector work inline; a later processor could replay that same command if implemented naively. The outbox has no demonstrated durable lease, deduplication key or crash recovery from PROCESSING.

**Fix:** Choose one authoritative command-execution path: transactional outbox + worker, not outbox **and** inline execution. Implement real handlers, idempotency keys, observable postconditions, optimistic concurrency/claiming, lease expiration, retries/backoff/dead-letter, atomic state transitions and operator recovery for crash after effect/before acknowledgment. Unknown event types must fail/quarantine, not be silently completed. Preserve exact approval/evidence references.

**Acceptance:** An event marked completed always has external operation receipt and verified effect; duplicate/replayed message never applies twice; worker crash and concurrent workers converge without false completion.

### P0-05 — Rollback reports success but does not restore graph or index

**Source:** `backend/app/services/rollback_service.py::_rollback_graph_mutation`, `_rollback_vector_reindex`, `rollback_proposal`.

**Observed:** Graph and vector rollback functions explicitly log that they *would* restore previous values/rebuild original vectors and return. Caller then marks `proposal.status="rolled_back"` and returns `success=True`. Missing mutation receipts can also return early without failure.

**Fix:** Preserve immutable previous-value and prior-active-index receipts at publication; implement actual graph reversal and index pointer restoration/rebuild, postcondition readback, and scoped cache invalidation. If any mandatory rollback step is incomplete, emit `ROLLBACK_FAILED` / `MANUAL_REVIEW` or equivalent, keep accurate status, and never claim success. Make rollback idempotent.

**Acceptance:** Test original → modified → rolled-back graph value and vector query, including injected partial failures. `rolled_back` status must be supported by verified restoration of external state.

### P0-06 — Repair truth still has competing authorities and premature vector ingestion

**Source:** `packages/amc-repair-engine/src/amc_repair/{schemas.py,patch_layer.py}`; `backend/app/graph/correction_patch_layer.py`; `backend/app/retrieval/orchestrator.py` (fallback); `backend/app/services/repair_integration.py` (synthetic patch chunks ingested before approval).

**Observed:** Package patch layer now has states and `can_serve()`, but older backend shadow-patch layer and fallback retrieval still rely primarily on `approved` rather than the same persisted ACTIVE/receipt policy. The feedback pipeline can insert proposed values into the normal serving vector store before independent human approval. Existing state tests check the package patch-layer context, not all production retrieval and streaming paths.

**Fix:** Define **one authoritative persisted patch lifecycle** for all services and caches. Use the same server-derived `is_serving_eligible(patch, active_snapshot, tenant)` contract everywhere. Do not put PENDING/APPROVED/STAGED/FAILED content into the serving FAISS index. Move proposals to review-only storage or a shadow index that normal searches physically exclude. Purge/repair previously injected synthetic chunks under an approved migration plan. Retire unsafe fallback injection or make it use the central gate.

**Acceptance:** Contradictory pending correction never appears in query, chat, stream, vector search, graph answer, cache, citation or follow-up; only published ACTIVE+verified receipts can serve.

### P0-07 — State transitions accept unverified receipts and no authoritative actor

**Source:** `packages/amc-repair-engine/src/amc_repair/patch_layer.py::transition_patch`; `schemas.py::can_serve`.

**Observed:** Transition checks allowed edges but accepts arbitrary `actor` and optional caller-supplied `receipt`; VERIFIED and ACTIVE are not conditioned on a verifier-signed, dataset-bound success receipt. `can_serve()` checks status ACTIVE, non-null `publication_receipt` and `verified_at`, not authenticity, expected version, tenant or graph/vector postcondition. `approved` is derived true for APPROVED/STAGED/VERIFIED even though these cannot serve, creating compatibility pitfalls.

**Fix:** Protect transition entrypoint behind server-only policy. Require distinct authorized approver; require stored signed/hashed verifier result, matched proposal/source/version, actor authorization and checked postcondition before VERIFIED→ACTIVE. Atomic snapshot pointer, compare-and-swap, tenant and expiration checks. Consider rename of `approved` compatibility flag or ensure no consumer interprets it as serving eligibility.

**Acceptance:** Constructing a patch with arbitrary receipt/actor cannot activate it. Test forged receipts, mismatched dataset hash, stale evidence, reverted approvals, version races, and self-approval.

### P0-08 — Main governance approval and application are not consistently four-eyes and evidence-bound

**Source:** `backend/app/api/routes/governance.py` (`approve_correction`, `batch_approve_corrections`, `review_repair_proposal`, `promote_patch_direct`), `backend/app/api/routes/admin.py::confirm_proposed_edge`.

**Observed:** New four-eyes checks have been added to some shadow-patch routes, but other SQL proposal approval transitions still update status based primarily on user role. Some routes promote directly to permanent canonical status as part of approval, rather than distinguishing APPROVED from VERIFIED/ACTIVE. Edge-confirmation behavior references missing/unavailable staging integration. Tests do not establish that **every** route enforces the same separation, tenant, evidence and publication rules.

**Fix:** Centralize governance service with explicit proposer/reviewer/approver/promoter identity, separation-of-duties policy, immutable evidence pack, version pin and status transitions. Route admin edges, SQL proposals, Repair microservice, scheduled jobs and direct endpoints through it. If staging storage is absent, return explicit unavailable rather than fabricated confirmation. Record role and tenant from verified principal only.

**Acceptance:** All paths reject self-approval and wrong-tenant changes; approval does not mutate canonical graph; only separately verified publication activates.

### P0-09 — Financial metric policy not enforced at execution, numeric precision not exact

**Source:** `backend/app/tabular/planner.py`, `executor.py`, `contracts.py`, `scheme_aggregation_service.py`.

**Observed:** AAUM metric registry is marked pending approval while planner builds SUM/AVG/rank plans; some plans claim `steward_approved=True`/SUMMABLE without matching the registry. `QueryExecutor.execute()` does not run a mandatory authoritative metric-policy check on the effective plan. SQL still uses `CAST(aaum_crore AS REAL)` and floating-point `ROUND/SUM/AVG`; grouping by scheme display name can collide; NAV/date and plan associations can mismatch. Financial result correctness cannot be inferred from 16,245/22 source-row reconciliation.

**Fix:** Short term, fail closed every unapproved AAUM aggregate. Then implement policy registry enforcement in executor, approved metric grain, exact Decimal/scaled-integer aggregation, canonical entity/plan identity, explicit as-of and quarter semantics and independently sourced gold answers. Never convert an imprecise float back into Decimal and call it exact. Steward-approved additivity must be a signed business decision, not an agent assumption.

**Acceptance:** Unsafe AAUM operations return `METRIC_POLICY_BLOCKED`; independent exact expected sums/rankings and dates pass. No numeric claim without traceable contributing source rows.

### P1-10 — Stream, chat and fallbacks can bypass typed numeric failure semantics

**Source:** `backend/app/retrieval/fast_path_interceptor.py`, `orchestrator.py`, `scheme_aggregation_service.py`, query/chat routes.

**Observed:** Failed fast-path lookup can continue to generative retrieval, and service fallback may load legacy Pandas when typed DB is missing. Multiple query entrypoints are not proven to share one numeric fail-closed contract.

**Fix:** Return explicit errors for unavailable typed data, ambiguity and unsupported metric across standard, streaming, follow-up and cached modes. Preserve verified PDF/TXT control answers.

**Acceptance:** Forced DB outage, off-period question, missing NAV key, unapproved AAUM, invalid plan and stream query never produce fabricated numbers.

### P1-11 — Invitation/migration/CI regressions remain unverified

**Source:** `backend/alembic/versions/004_*`–`008_*`, invitation-related migrations, tests, `.github/workflows/` (no workflow detected in reviewed tree), `WAVE_1.3_FINAL_STATUS.md`.

**Observed:** New migrations and tests are present; the review has not executed upgrades/rollback on a fresh clone. The 31 recorded passes cover one Repair auth test module; Batch B tests depend heavily on mocks and some explicitly assert synthetic receipts and fabricated rollback success. No GitHub Actions workflow runs/commit statuses were returned for this SHA. The status report says both “Batch B complete” and that some B defects are design-only; its internal “Latest SHA” predates the reviewed HEAD.

**Fix:** Integrate real services in disposable environments, exercise Alembic upgrade/downgrade and existing-data migration, supply genuine action logs, and correct all documentation claims to match observed behavior. Add CI.

**Acceptance:** Fresh-clone build, migrations, tests and app boot run with commands+logs; no unintended skip, no claimed PASS based solely on mocks or documentation.

### P1-12 — Admin endpoints can return simulated operational facts

**Source:** `backend/app/api/routes/admin.py`, `remediation/wave1_3/ADMIN_EFFECTS_AUDIT.md`.

**Observed:** Some mock-success cases now properly return 503. Other restored endpoints still expose hardcoded ingestion tasks, placeholder data freshness, empty proposed-edge views and compliance indicators that have not been established from source systems. “No data” and “not implemented” must be distinguishable.

**Fix:** Wire actual task/index, graph staging and compliance providers. Where absent, return `503 DEPENDENCY_UNAVAILABLE` / explicit unsupported contract—not plausible fabricated operational metrics. Preserve frontend API response compatibility with honest state.

**Acceptance:** Admin dashboard cannot show fake successful jobs or false zero backlog. Real integration fixtures verify counts, freshness and authorization.

---

## 4. Recommended execution order — five large, reviewable batches

This wave should favor **bulk execution with coherent PR boundaries**, not endless incremental prompts. Each batch has 8–10 concrete tasks. A later batch may be developed in parallel only where it cannot violate blocked trust/financial gates.

| Priority | Batch | Tasks | Source of truth | Exit criterion |
|---|---|---:|---|---|
| **1 / P0** | **A — Stop false success and restore broken APIs** | A01–A09 | Admin/auth, governance, promotion, outbox, rollback | No unawaited promotion, broken invitation, fake reindex/rollback/outbox success; negative test proof |
| **2 / P0** | **B — One Repair truth and real publication saga** | B01–B10 | Repair models, shadow/vector graph, governance, outbox, Neo4j | No pending truth, genuine VERIFIED/ACTIVE, replay and compensation verified |
| **3 / P0** | **C — Financial correctness and source contracts** | C01–C10 | Tabular contracts/planner/executor/repository/ingestion | Typed fail-closed financial results + independent exact gold; steward-dependent operations blocked |
| **4 / P1** | **D — End-to-end routing and user compatibility** | D01–D08 | Orchestrator, API adapters, frontend, feedback | Same secure truth in normal/stream/chat/cached UI and PDF/TXT regression PASS |
| **5 / release** | **E — Assurance and operational readiness** | E01–E09 | CI, migrations, evidence, rollback, performance | Reproducible clean checkout, fault-injection PASS, approved release gates |

**Important:** Security containment cannot be deferred behind financial work. Batch C can begin *in a separate branch* once unapproved AAUM aggregate calls have been blocked, even as Batch B continues. Do not merge the whole system into production until every applicable gate passes.

## 5. Batch A — P0 truth, fail-closed effects, authentication (9 tasks)

**A01 — Fix invitation redemption.** Update `backend/app/api/routes/auth.py` to hash incoming token and query `InvitationToken.token_hash`; use `verify_invitation_token`, lock/atomic redemption, rate-limit/expiry, constant-time verification where applicable, and tested migration. Tests: admin create → redeem → login; duplicate redemption; concurrent two-client race; wrong/expired token; no storage/log plaintext.

**A02 — Fix async promotion route.** Convert `backend/app/api/routes/governance.py::promote_approved_proposals` to async + await. Audit all service callers; return real result/receipt. Tests must hit FastAPI handler with actual stubbed external operations and SQL assertion, not just call coroutine manually.

**A03 — Disable fabricated vector success immediately.** In `_trigger_reindex`, if real indexer unavailable, raise `PromotionVerificationError` and keep non-APPLIED. Reject `document_count=0` as success without an explicit independently verified no-change policy. Remove `verified=True` placeholders. Tests: indexer missing, no docs, failed index, stale hash.

**A04 — Disable fabricated outbox completion.** Make `GRAPH_MUTATION_REQUIRED`, `PATCH_STATE_TRANSITION`, unknown event handlers fail closed until real implementations are attached. Do not mark an event completed when handler only logs. Test no-op handler cannot emit completed.

**A05 — Disable fabricated rollback success.** Graph/vector rollback operations must raise `RollbackNotImplemented`/`ROLLBACK_UNVERIFIED` until real recovery exists. Never mark rolled_back solely from logging. Test prior canonical value unchanged results in explicit failure, not success.

**A06 — Seal pending synthetic-vector ingestion.** Disable `ingest_synthetic_patch_chunk` from normal serving index on patch creation; stage proposals in review-only store. Add a retrieval probe confirming no unapproved correction is visible.

**A07 — Close obvious approval bypasses.** Main governance SQL proposal review and direct promotion must verify independent proposer/approver, tenant, evidence and version; no status-only shortcut. Audit all endpoints including background scheduler and microservice.

**A08 — Fail closed Admin operational placeholders.** Hardcoded task records, invented freshness zeros and compliance placeholders must not be presented as actual data. Wire real providers where available; otherwise return explicit unavailable with stable contract/error code. Include frontend behavior check.

**A09 — Add cross-system regression tests and baseline.** Create `test_wave14_p0_containment.py` (or naming-equivalent) with negative cases for A01–A08, pin SHA, route map and data manifests. Commit evidence for actual commands; DO NOT claim production readiness at A exit.

**Batch A PASS:** No false success on invitation, promotion, index, outbox, rollback, Admin telemetry; no unapproved vector contamination; tests actually executed.

## 6. Batch B — Authoritative Repair lifecycle, real external publication (10 tasks)

**B01 — One stored lifecycle.** Move all paths to shared typed `PENDING → APPROVED → STAGED → VERIFIED → ACTIVE`, terminal failed/rejected/rolled_back/superseded. Centralize versioned schema and migration for legacy patches; no implicit ACTIVE for old `approved=True` records.

**B02 — Approval evidence and four-eyes.** Persist proposal creator, reviewer, approver, immutable source version, risk and independent approval receipt. Ensure distinct identities and scopes in both monolith and Repair microservice. Prevent stale/revoked approvals, service-actor privilege escalation and cross-tenant promotion.

**B03 — Real vector index staging.** Use actual indexing-manager/FAISS integration with staging generation, expected documents, source hash, vector count, query probes, and read-only activation switch. Never mark verified when index work was not run.

**B04 — Exact graph postconditions.** Parameterize allowlisted mutations, record preimage, check target/updates, transaction commit, read-back against type-correct value. For financial decimals use Decimal/metric scale, **not float epsilon**. Hash and persist proof; no success without expected version.

**B05 — One authoritative worker.** Choose outbox worker as execution owner. Persist intent and state transition in same SQL transaction; worker claims with concurrency-safe lock/lease, runs exactly one external side effect, records verified outcome and advances state. Eliminate duplicate inline work.

**B06 — Retry/recovery/deduplication.** Idempotency key `(proposal_id, approval_version, target, desired_state)`, capped retry/backoff, dead-letter, crashed PROCESSING recovery, concurrent workers and replay handling. No permanent inconsistent half-applied status.

**B07 — Real graph rollback.** Capture preimage and version at application. On rollback, restore original value with conflict/version checks and read-back proof; avoid clobbering later legitimate updates. Reconcile state accurately on failure.

**B08 — Real vector rollback.** Restore prior active vector snapshot or rebuild from frozen source, verify count/hash/query results, invalidate affected caches. No “would rebuild” placeholders.

**B09 — Unified serving authorization.** All patch lookup modes and legacy fallback use shared `is_serving_eligible()` with ACTIVE, verified receipt, tenant, content/index version and non-expiry. Physically prevent pending shadow chunks in serving FAISS; provenance/audit must match active facts.

**B10 — End-to-end failure injection.** Test graph outage, wrong readback, vector failure, crash after external effect/before SQL ack, duplicate events, concurrent workers, forced rollback, tenant conflict and shadow-index pollution. Include real external-backed disposable Neo4j/vector integration or mark blocked.

**Batch B PASS:** A patch cannot become ACTIVE without verified external effects. Rollback restores previous truth. No working path can bypass shared policy. Audit receipt is reconstructible.

## 7. Batch C — Financial metric and tabular correctness (10 tasks)

**C01 — Emergency metric gate.** Disallow AAUM SUM/AVG/rank/market totals pending signed steward approval. Executor must enforce policy, irrespective of mutable `QueryPlan` flags. Policy must include metric ID, grain, operation, approval ID, snapshot version and time scope.

**C02 — Exact arithmetic.** Eliminate SQL `REAL` conversions and Python float financial computation. Use scaled integers or Decimal-aware deterministic aggregation, documented rounding, test tiny/huge/tie/boundary values against independent Decimal fixture.

**C03 — Canonical identity hierarchy.** Distinguish AMC / scheme / plan-option / ISIN / scheme code / source row. Group on approved IDs, not display name; detect alias collisions and double counting.

**C04 — NAV date/plan semantics.** Select NAV and NAV date from same observation using unambiguous keys and deterministic ordering. Reject mixed-date ranking and underspecified plan with explicit choice/ambiguity.

**C05 — AAUM grain and quarter policy.** Obtain human data steward approval for AAUM summability, holdings duplication, closure-date semantics and cross-quarter comparisons. If not approved, keep operations blocked while independently implementing safe NAV exact lookup.

**C06 — Manifest/chunk reconciliation.** Parse actual manifest keys, verify per-chunk SHA and counts, deduplicate row anchors, stage each dataset version. Distinguish `row_valid`, `nav_valid`, `aaum_valid`. Reject source data corruption without quiet assumptions.

**C07 — Atomic dataset publication.** `STAGED → VALIDATED → APPROVED → ACTIVE`; no activation on partial failures or missing approval. Use active pointer CAS and cold-start readiness, preserve old version on interrupted ingest.

**C08 — Complete financial receipts.** Every numeric answer records dataset hash/version, metric policy version, filters, grain/time, all contributor row IDs, source hashes and exact result set. Aggregate receipts reconstruct exactly.

**C09 — Deterministic query engine.** Validate plans in executor; bound/whitelist SQL templates; no arbitrary caller SQL; fixed tenant and active-version scope. Outage/ambiguity/unsupported metric returns structured error without generative fallback.

**C10 — Independent gold suite.** Freeze ≥30 observed CSV failure examples with real correct values from independent spreadsheet/Decimal review and ≥15 PDF/TXT controls initially (extend to ≥50). Test cross-quarter, collisions, NAV dates, unsupported metrics, rounding and row-proof completeness. Report actual executed results.

**Batch C PASS:** Exact, steward-approved numeric results; unauthorized operations fail closed; independent gold + data proof PASS. No fabricated sum treated as authoritative.

## 8. Batch D — Routing, Feedback and frontend/API parity (8 tasks)

**D01 — Unified numeric router.** Every normal/stream/chat/follow-up financial query uses typed execution and shared error semantics: `METRIC_POLICY_BLOCKED`, `AMBIGUOUS_QUERY`, `STRUCTURED_SOURCE_UNAVAILABLE`, `NO_MATCH`, `UNSUPPORTED_METRIC`.

**D02 — No numeric legacy fallback.** Disable legacy Pandas loading and retrieval/LLM-based number synthesis when deterministic financial engine fails. Preserve safe PDF/TXT narrative fallback separately.

**D03 — Stream/caching parity.** Assert same value, provenance, error and ACTIVE-patch policy across query v1/v2, chat, streaming, follow-up and cached replay. Never cache unapproved facts as valid answers.

**D04 — Real frontend contracts.** Compare `mf-context-engine/src/services/api.js` with live FastAPI routes; cover Admin task, RBAC, edge, cache and report operations; avoid claiming completion on mock data/HTTP 200 alone. Return explicit unavailable where backend missing.

**D05 — Feedback-to-Repair evidence.** Record user feedback, adjudication, issue lifecycle, candidate correction, approval, publication and final resolution with immutable links; don't resolve on proposal creation.

**D06 — Citation/claim audit.** For every financial value and repaired claim, emit supporting source-row or document evidence and approved active receipt, not a verbal overlay that says “supersedes prior context.”

**D07 — Multi-tenant and role controls.** Verify tenant-specific index/graph/audit response partitions and role matrix in both modes; no leakage via direct Repair endpoint, cache or admin report.

**D08 — UI regression and accessibility smoke.** Test login/invite/admin views, upload/index monitor, correction review, error surface, accepted/rejected feedback and chat answer modes. No silent empty success for unavailable data.

**Batch D PASS:** Frontend/API behavior represents truthful, authorized underlying state and healthy PDF/TXT answers are not degraded.

## 9. Batch E — Independent assurance and deployment gates (9 tasks)

**E01 — Fresh clone bootstrap.** Reproduce from exact SHA with pinned Python/JS dependencies and documented sample data. No reliance on uncommitted local SQLite/FAISS state.

**E02 — Migration matrix.** Run all Alembic revisions from scratch and against a copy of prior schema; check invitation hashes, proposal column, graph receipts, reindex, outbox and rollback constraints, SQLite/Postgres behavior. Downgrade/restore rehearsal and schema ownership.

**E03 — CI workflow.** Create `.github/workflows/` jobs for import/lint/unit/auth/security, Repair integration, finance gold, API/stream parity, fresh migrations and artifacts. Require non-skipped P0 tests.

**E04 — Actual integration infrastructure.** Disposable SQL, Neo4j, FAISS/vector fixtures and optional Redis; 401/403/tenant tests, real graph mutation/read-back and index version verification. Explicitly distinguish mocked unit tests from real integration tests.

**E05 — Fault-injection suite.** Outbox at-least-once, crash after graph commit, stale writer, index failure, rollback failure, duplicate review, token replay, corrupted manifest, wrong quarter, stale cache.

**E06 — Security assurance.** Secrets scan, route inventory including hidden aliases, service token audience/issuer/scope separation, zero exposed pending data, role/tenant negative matrix and vulnerable-flow review.

**E07 — Performance and cost telemetry.** Measure request p50/p95/p99, 429/500 failures, graph/index/LLM cost and latency, retried tasks and patch publication lag with real observed datasets. No synthetic success metrics presented as production data.

**E08 — Deployment/rollback runbook.** Version-pinned canary, backups, feature flags, read-only failover, isolation gates, active snapshot rollback, incident response and who can authorize publication. Do not execute deployment without operator approval.

**E09 — Independent audit and truthful summary.** Reconcile `WAVE_1.3_FINAL_STATUS.md` and older task ledgers to code/tests. Include PASS / REVIEW / BLOCK per gate with run URLs, commit, active dataset hash, approval IDs, release owner and unresolved risks. **Overall PASS only if every applicable gate is proven.**

**Batch E PASS:** Clean build + real integration/fault evidence, all non-negotiable gates pass, steward/operator approvals recorded. Until then overall status BLOCK.

---

## 10. Precise mandatory test matrix

For all tests below, write executable automated assertions against isolated fixtures. Test a real endpoint when the defect involves routing, and a real external storage effect when the claim involves publication.

| Test ID | Scenario | Expected result |
|---|---|---|
| T01 | Admin creates invite; user redeems token | Hash lookup, account active, login succeeds |
| T02 | Two concurrent redemptions / same token replay | Exactly one redemption; one denied |
| T03 | Invite expired, wrong token, throttled brute force | No account activation; controlled error |
| T04 | Governance promotion over HTTP | Async awaited; durable result, no coroutine serialization error |
| T05 | Missing indexer / zero target docs | Not verified or applied |
| T06 | Indexer returns stale manifest | Fail publication; old pointer preserved |
| T07 | Outbox GRAPH handler with no graph effect | Event not COMPLETED |
| T08 | Outbox transition handler no state change | Event not COMPLETED |
| T09 | Unknown event type | Quarantined/failed, not completed |
| T10 | Replayed event / two workers | One effective mutation, idempotent receipt |
| T11 | Worker crash after external effect before ack | Recovery converges correctly |
| T12 | Graph rollback | Preimage restored and read-back matches |
| T13 | Vector rollback | Prior active index restored, query verifies |
| T14 | Rollback side effect unavailable | Status not ROLLED_BACK; alert and retry/manual review |
| T15 | PENDING/APPROVED patch in normal FAISS | Never appears in user answer/search |
| T16 | Fallback layer and streaming patch retrieval | Same ACTIVE/receipt policy as primary |
| T17 | Forged ACTIVE/VERIFIED receipt | Rejected by authoritative verifier |
| T18 | Self-approval via direct, batch, SQL and microservice routes | Denied in all modes |
| T19 | Cross-tenant patch/evidence access | Denied or filtered, no existence leak |
| T20 | Wrong graph value after commit | Publication rejected + recovery invoked |
| T21 | Large/small AUM Decimal gold | Exact expected results (after steward approval) |
| T22 | Unapproved AAUM total/rank | `METRIC_POLICY_BLOCKED` |
| T23 | Scheme-name collision / multiple plan NAV | Correct identity or ambiguity |
| T24 | Manifest corrupt/missing chunk | Reject activation, keep previous active version |
| T25 | Typed DB missing, query/stream/chat | Structured error, no generated numeric fallback |
| T26 | PDF/TXT regression controls | Pre-fix quality maintained |
| T27 | Admin mock task/compliance endpoint | Real provider data or explicit unavailable |
| T28 | Fresh clone and Alembic chain | Import/startup/upgrade clean |
| T29 | Runtime route scan and negative auth | All sensitive routes protected |
| T30 | CI run on exact SHA | Real green logs, no critical skips |

**Test independence:** The gold answer must be calculated outside the implementation under test. A mocked `db.commit()` call or a receipt dictionary with `verified=True` is *not* an independent verification of Neo4j, FAISS, or rollback effects.

### Suggested commands (adapt for actual package/project configuration)

From `backend/`:

```bash
python -m pytest -q tests/test_sec01_universal_auth.py tests/test_sec01_remaining_routes_and_flow.py
python -m pytest -q tests/test_wave13_graph_verification.py tests/test_wave13_batch_b_complete.py
python -m pytest -q tests/test_tabular_queries.py tests/test_wave0_verification.py
python -m pytest -q tests/test_wave14_p0_containment.py tests/test_wave14_saga_integration.py tests/test_wave14_financial_gold.py
python -m alembic upgrade head
python -m alembic current
```

From `packages/amc-repair-engine/`:

```bash
python -m pytest -q tests/test_wave13_auth_hardening.py tests/test_wave13_vector_isolation.py
python -m pytest -q tests/test_repair_service_auth.py tests/test_wave14_publication_parity.py
```

The `test_wave14_*` files are **required deliverables to create**, not claimed existing files. Run tests with a local disposable DB/graph/vector and actual project installation instructions. Never run migrations against production without approval.

## 11. Artifacts required from the local agent

Create `remediation/wave1_4/` and maintain **real machine-verifiable** evidence:

```text
remediation/wave1_4/
  SOURCE_REVIEW.md              # pinned SHA, comparison, path/line anchors
  PLAN_AND_DECISIONS.md         # approved design, business gate decisions, ADRs
  TASK_MATRIX.csv               # A01..E09, DONE/PARTIAL/BLOCKED, commit/test proof
  API_AUTH_MATRIX.csv           # route/method/role/tenant, anon/forged/access cases
  STATE_CONTRACT.md             # patch/proposal/publication states and valid transitions
  FINANCIAL_METRIC_POLICY.md    # metric registry, steward decisions, allowed operations
  DATA_RECONCILIATION.json      # per-chunk hashes, counts, quarantines, active version
  VERIFICATION_RUNS.json       # actual command, timestamp, env, SHA, exit code, results
  EXTERNAL_EFFECT_PROOFS.md    # graph/index before/after, source/index hashes and probes
  FAILURE_INJECTION.md         # crash/retry/rollback trials, observed effects
  COMPATIBILITY_MATRIX.csv     # backend/frontend expected/actual route contracts
  RELEASE_GATE.md              # SEC/REP/PUB/NUM/ING/E2E/OPS, PASS/REVIEW/BLOCK
  ROLLBACK_RUNBOOK.md          # verified restoration and operator requirements
  OPEN_DECISIONS.md            # human steward or deployment approval blockers
```

- Store sanitized logs; do not commit secrets, raw customer files, access tokens, unapproved external material or confidential rows.
- For each task: include code file, tests run, actual exit status, input corpus hash, observed failure or success, rollback/compensation plan.
- A markdown checkbox or 100%-passing mocked test set **does not** make a release gate pass.
- Reconcile older status documents rather than deleting their audit history; mark them superseded with references where appropriate.

## 12. Codex-ready master instruction — paste as one bulk request

```text
ACT AS: Principal engineer, financial data architect, security architect,
agentic governance lead and independent release assurance engineer.

REPOSITORY: nusummit-spg/amc-context-engineering-poc
BASE BRANCH: amc-dev
REVIEWED PINNED SHA: 73cb485af2f2057f8ee181c7ad9d63130e43b8d0

Before changes, fetch amc-dev and verify SHA. If HEAD has advanced, compare
against the reviewed SHA and merge only nonconflicting authorized work. Create
an isolated remediation branch; do not force-push or deploy production.

READ FIRST:
1. AMC_Wave1_4_Next_Implementation_Agent_Handoff_2026-11-05.md
2. docs/AMC_Wave1_3_Next_Actions_Agent_Handoff_2026-11-04.md
3. docs/AMC_Tasks_3_11_26/AMC_Specs/{README_START_HERE.md,
   02_TARGET_ARCHITECTURE_AND_CONTRACTS.md,
   03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md,
   04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md,
   05_ASSURANCE_SECURITY_RELEASE_GATES.md,
   06_GOALS_AND_TASKS.md,07_CODEX_EXECUTION_PLAYBOOK.md,08_OPEN_DECISIONS.md}
4. WAVE_1.3_FINAL_STATUS.md and remediation/wave1_3/TEST_RESULTS.md

CURRENT BULK ASSIGNMENT:
- Execute ALL of Batch A (A01-A09) and Batch B (B01-B10) as one substantial
  autonomous run, using separate reviewable PRs/commits. Prioritize eliminating
  false success and repair truth contamination before any new product scope.
- Build/execute a real integration harness with disposable SQL + Neo4j +
  vector index, and show postcondition evidence rather than mocking all effects.
- Produce task-by-task proofs and fix any regression introduced by changes.
- If source/business decisions are missing, implement safe fail-closed gates
  and log BLOCKED; do not fabricate steward or operator approval.

NEXT BULK ASSIGNMENT (independent follow-up branch after A/B gates):
- Batch C (C01-C10) exact financial computation/ingestion/provenance;
  block unapproved AAUM aggregates until steward authorization.
- Batch D (D01-D08) query/chat/stream/UI/Feedback parity.
- Batch E (E01-E09) CI, migrations, failure injection, benchmark and release.

NON-NEGOTIABLES:
- No reported APPLIED/VERIFIED/COMPLETED/ROLLED_BACK state without real
  observable external side effect, exact postcondition and durable receipt.
- Do not allow raw user patches, client flags, confidence thresholds,
  generic service identity, or unverified actor labels to authorize canonical
  truth changes. Require independent review and active dataset/corpus version.
- No proposed/shadow patch content in serving FAISS, cached answers, or graph.
- No unapproved AUM aggregation; no float arithmetic for exact financial sums.
- No LLM/Pandas numeric fallback after typed-query failure.
- Every endpoint, including alternate microservice/scheduler/fallback route,
  must enforce verified identity, scope, tenant and consistent truth state.
- Do not add dependencies/services unless justified by an actual gap; use
  existing code and open-source tools when suitable.
- Do not claim a test PASSED if not executed. Label mocks UNIT-only.
- Do not alter production facts, externally accessible datasets, secrets,
  service credentials or deployment without explicit authorized approval.

REQUIRED OUTPUT:
1. Implemented code and test commits with path/line references.
2. A01..E09 task ledger with DONE/PARTIAL/BLOCKED and reasons.
3. Actual tests and CI logs with commands, pass/fail/skip, environment and SHA.
4. Graph and vector effect receipts, pre/post hashes and rollback proofs.
5. Complete route/security, provenance and financial error matrix.
6. Explicit RELEASE_GATE (SEC/REP/PUB/NUM/ING/E2E/OPS) and open decisions.
7. Preserve healthy PDF/TXT accuracy and frontend contracts; include regressions.

STOP RULES:
- Refuse irreversible live action or unpublished financial semantics.
- If external integration cannot run locally, demonstrate safe blocking
  behavior, record UNVERIFIED and leave overall release BLOCK rather than
  replacing evidence with an artificial passing test.

DO THE SAFE IMPLEMENTATION WORK NOW. Do not stop at planning/documentation.
```

## 13. CTO review gates and handoff to next session

| Gate | Mandatory proof | Verdict at reviewed SHA |
|---|---|---|
| **SEC** | Secure invitation redemption, auth, tenant and service scopes | **BLOCK** — invite mismatch, incomplete parity verification |
| **REP** | One four-eyes lifecycle, ACTIVE+verified serving, no provisional vector truth | **BLOCK** |
| **PUB** | Real verified graph/vector effects, durable outbox, tested recovery and rollback | **BLOCK** — log-only external effects |
| **NUM** | Approved metric policies, exact arithmetic, independent gold | **BLOCK** |
| **ING** | Reconciled/hashed chunks, field validity, guarded activation | **BLOCK** |
| **E2E** | Query/chat/stream/UI parity, PDF/TXT unaffected | **BLOCK** |
| **OPS** | Green CI, migration rehearsal, monitored canary and rollback | **BLOCK** — no GitHub Actions evidence |

**Next independent audit inputs:** new branch/PR URL, exact head SHA, actual CI run, test logs, fixture manifest, graph and vector before/after proof, repair approval receipts, financial metric decisions, P0 failure-injection report and deployment notes. A later source review must verify *effects and evidence* rather than accepting “complete” labels.

**Final architectural guidance:** A working assurance engine is a chain of independently verifiable state transitions—not a collection of status tables and success-shaped receipts. First make the truthful failure behavior and publication invariants demonstrably correct; only then widen financial analytics and UI scope.
