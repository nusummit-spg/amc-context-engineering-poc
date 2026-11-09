# AMC Context Engineering POC — Wave 2.1
## CTO Source Re-Audit, Runtime Cutover, CI Stabilization and Evidence-Driven Release Handoff

**Audit date:** 9 November 2026 (Asia/Kolkata)  
**Repository:** [`nusummit-spg/amc-context-engineering-poc`](https://github.com/nusummit-spg/amc-context-engineering-poc)  
**Target branch:** `amc-dev`  
**Source HEAD reviewed:** `fe28ca6844ae170fcdcf434e0b65dde237738b90`  
**Comparison base:** `91af9fa4eaa8abdb66c55b04fdee484ea0343a3c`  
**GitHub delta:** 5 commits ahead, **51 changed files**; Wave 1.9/2.0 source and tests added to repository.  
**Connector repository privileges:** `pull=true`, `push=false`; this deliverable is an **offline handoff**, not an applied commit or PR.  
**Release verdict:** **BLOCK** until exact-SHA CI, fail-closed application cutover, real Neo4j/FAISS/PostgreSQL verification, and full regression evidence pass.  
**Scope:** Use and harden existing `amc_publication` and `amc_quality`. **Do not create a third publication state machine, another journal, or an independent replacement financial service.**

> **Evidence discipline:** This audit inspected the committed source, GitHub Actions outcomes, and relevant job logs. It **did not execute** the repository's tests, deploy the application, connect to a live Neo4j/FAISS/PostgreSQL environment, or run a customer-data canary. The user reports **109 local passing tests**. The committed `remediation/wave2_0/TEST_EVIDENCE.json` records **112 local tests** from 6 November (77 Wave 2.0 + 35 Wave 1.9) on an earlier baseline. Do not reconcile these different counts by assumption; regenerate exact-SHA test evidence and report selected/deselected/skipped tests.

---

## 1. Executive decision

The architecture packages now exist in `amc-dev`; this is no longer a design-from-zero problem. The highest-value implementation is **one authoritative execution path**:

`Authenticated, four-eyes-approved proposal → transactional outbox / publication work → fenced lease → durable preimage → real Neo4j compare-and-set → independently observed graph readback → immutable FAISS generation + readback → atomic active-generation switch → durable verified receipt → tenant-scoped answer eligibility and Feedback resolution → verified rollback/reopen if needed`.

**Current state:** Pieces exist, but the chain is not authoritative, its external effects are not proven in CI, and some legacy paths bypass or contradict the v2 contract. Prioritize **correctness and safe cutover** over adding user-facing capabilities. Do not equate a local contract test with release readiness. Readiness should require an executable evidence matrix on the exact SHA and test environment.

### Verified repo and CI facts

| Observation | Finding | Interpretation |
|---|---|---|
| `amc_publication/*`, migration `012`, Wave 1.9 tests | Present | Substantial code committed, not merely a ZIP |
| `amc_quality/*`, Wave 2.0 tests and workflow | Present | Independent financial/manifest controls committed |
| [Publication V2 run 42602341495](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42602341495) | **FAIL** at pytest collection: `ModuleNotFoundError: httpx` | The minimal CI dependency set omits an import reached via package initialization |
| [Quality V2 run 42602341554](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42602341554) | Independent quality job **PASS**; Wave1.9 bridge **FAIL** at `httpx` import | Quality controls have promising isolated CI evidence; cross-package quality gate has not passed |
| [Assurance run 42602341697](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42602341697) | **FAIL** at `pip-audit` | Reported 3 advisories for `setuptools 79.0.1`; fixes reported at 83.0.0 and 84.1.0. Downstream jobs SKIPPED |
| `.github/workflows/amc-assurance.yml` | Gitleaks scanning block commented out; missing required test directories can be suppressed in one job; canary/SLO still placeholders | Not an enforceable release gate |
| GitHub branch | No push permission via current connector | Codex should make reviewable local commits/PR, not expect this session to modify repo |

**Immediate CI recovery:** Fix the *import chain* rather than only appending `httpx` to a test job. `backend/amc_publication/__init__.py` eagerly imports `.worker`; `worker.py` imports `app.services.publication_metrics`; `app.services.__init__` imports `client_base`, which needs `httpx`. Use explicit/lazy exports (no side-effectful app imports on package initialization) **and** specify real test dependencies in a pinned/locked CI environment. Adding `httpx` alone might expose subsequent imports. Separately resolve the `setuptools` vulnerability with audited upgrades, retaining a fatal secret/vulnerability scan.

---

## 2. Source-backed finding register (severity and disposition)

Each path is from the pinned SHA unless marked otherwise. "Candidate defect" means source is inconsistent or insufficient; prove with a targeted test before labeling it fixed.

| ID | Severity | Source / observation | Impact | Closure |
|---|---|---|---|---|
| W21-01 | P0 | `backend/amc_publication/__init__.py` eager worker import; Wave1.9+bridge CI logs | `httpx` import cascade prevents tests from collecting | Lightweight import boundaries, pinned contract deps, CI green |
| W21-02 | P0 | `backend/amc_publication/worker.py::_process_publication` passes desired `postimage` to `journal.verified` immediately after `compare_and_set` | **No independent graph readback** before saying VERIFIED | Call `graph.read` post-write, compare tenant/entity/attr/type/value/version/fence; negative test |
| W21-03 | P0 | `worker.py::_process_rollback` and `journal.py::switch_back` | Rollback currently deletes pointer rather than restoring prior verified generation; it constructs `before` from **current** pointer | Persist pre-pointer, CAS restore previous generation; first-generation deactivation explicit and verified |
| W21-04 | P0 | `backend/amc_publication/worker.py::DurableWorker.execute_work` | Alternative worker constructs placeholder effect and marks work `published` without Neo4j/FAISS proof | Remove/disable this execution path or convert to pure outbox-to-Journal bridge only; cannot publish |
| W21-05 | P0 | `backend/app/api/routes/governance.py::promote_patch_direct` | Legacy endpoint mutates graph and marks VERIFIED before raising `HTTPException(202)`; broad `except Exception` catches that 202 and converts it to **500** | Transactional enqueue-only, **return** `202` with persisted `work_id` and `Location`/status endpoint; no side effects |
| W21-06 | P0 | `backend/app/graph/correction_patch_layer.py::approve_patch` legacy alias to `promote_to_permanent`; `get_active_patches` filters on `approved` | Legacy direct write / merely approved patches may become eligible | Remove direct mutation, deprecate alias, unify ACTIVE+verified receipt+tenant gate; adversarial route tests |
| W21-07 | P0 | `backend/app/services/outbox_processor.py` still has `NotImplementedError` for graph/state transitions; `PromotionService` enqueues legacy events | End-to-end approval-to-v2 worker bridge incomplete | Single owner of commits; deterministic translation, idempotent event acknowledgement, no phantom completion |
| W21-08 | P0 | `backend/app/services/feedback_outcome_service.py` still uses staging counts and memory links; `amc_publication/feedback.py` uses durable receipts | Feedback can be misresolved or remain inconsistent across two models | Replace legacy resolution with persisted tenant-scoped causal join; transaction/outbox for issue status; rollback reopen |
| W21-09 | P0 | `backend/app/retrieval/fast_path_interceptor.py::_is_serving_eligible_patch` trusts fields from patch dict, including `can_serve`; v2 `serving.py` uses SQL receipt+pointer | Multiple, inconsistent serving gates; stale receipt/tenant risk | One authoritative predicate queried by every retrieval, streaming and UI answer path |
| W21-10 | P0 | `backend/app/tabular/executor.py` returns `source_row_ids[:50]` | Incomplete provenance of larger query results | Full ledger and paginated proof endpoint; no false completeness claim |
| W21-11 | P0 | `backend/app/tabular/csv_excel_loader.py` uses 16,245/22 manifest defaults and `activate_upon_completion=True` | Legacy path can ingest without independent byte attestation or activate with weak evidence | Mandatory `amc_quality` pre/post-check, explicit zero-quarantine/steward activation, no fallback |
| W21-12 | P0 | `amc_quality/financial.py` safely refuses AAUM aggregation, but legacy financial query/planner routes still exist | Policy may be bypassed by older query variants | Gate every numeric route, classify actual operation, preserve NAV plan/date pairing, independent golden dataset |
| W21-13 | P0 | `Journal.switch_pointer` / `PublicationWorker` / active FAISS reader | DB pointer is not evidence that deployed serving reader actually loaded exact generation | Physical FAISS binary verify, explicit reload/reader ack and probe after activation |
| W21-14 | P0 | `PublicationWorker.run_once` hardcodes owner `worker_default`; `DurableWorker.claim_work` passes `worker_id` to `claim_with_fence(work_id, tenant)` | Worker identity and tenant confused; stale-worker protection not demonstrated | Stable distinct worker IDs; concurrent real Postgres test, expiry/reclaim/fencing validation |
| W21-15 | P1 | `faiss_artifacts.py` uses POSIX-like directory `os.open`/`os.fsync` on stage parent | Windows staging may fail even though `artifacts.py` was adapted | Windows-specific binary staging/restore test, conditional portable directory durability mechanism |
| W21-16 | P1 | `worker.py` `failpoint` annotated as dict, then invoked as a callable | Nonempty dict failpoints cause unexpected TypeError; failure injection semantics ambiguous | Typed fault injector protocol; stage-accurate deterministic kill points |
| W21-17 | P1 | `backend/app/core/database.py` hardcodes SQLite; Alembic v2 assumes its own migration chain; local system mentions PostgreSQL | Backend/worker can end up using divergent DB state | Decide authoritative database for each environment; one DSN configuration; tested migrations and isolation |
| W21-18 | P0 | `amc-assurance.yml`: disabled secret scan, placeholder canary/SLO and missing suite behavior | Release workflow can say “checked” without exercising gates | Required named CI checks with real evidence and explicit BLOCK for unsupported stages |
| W21-19 | P1 | `.github/workflows/amc-publication-v2.yml` installs broad latest SQLAlchemy/Pytest rather than app-validated pins | CI vs local dependency drift and possible hidden runtime failures | Lock actual app/test env, Python matrix only where supported; provenance of lock digest |
| W21-20 | P1 | `packages/amc-feedback-loop` removal documented previously; UI/tests retain Feedback flows | API/classifier/repair event compatibility unresolved | Maintainer-signed restore/replace decision, contract migration and event compatibility tests |
| W21-21 | P1 | Wave 1.9/2.0 test counts differ: user reports 109; stored evidence 112 on old SHA | Test-selection drift; risk of green local set hiding skipped cases | Exact SHA `pytest --collect-only`, full pass/fail/skip ledger and platform matrix |
| W21-22 | P1 | `amc_publication` `PublicationWorker` accepts `ImmutableSnapshotStore` for simulation, and production guard checks only nonempty snapshot root | Mere nonempty directory does not prove FAISS binary or active reader readiness | Require `FaissGenerationStore` + verified manifest/index & reader acknowledgment in prod |
| W21-23 | P0 | `.github/workflows/amc-assurance.yml` dependency audit logs | 3 advisories in `setuptools 79.0.1`; not a Gitleaks failure this run | Upgrade to safe compatible release (at least the reported `84.1.0` for all listed fixes), re-run `pip-audit`, verify application compatibility |

**Important nuance:** `Neo4jGraphPort.compare_and_set()` does use conditional Cypher and returns a `RETURN` field within the mutation statement; that is stronger than logging alone. However, Wave2.1 requires an independently issued post-write readback (and second reader if feasible) plus a durable receipt matching the exact graph and vector generation. Do not describe current source as having no graph write.

---

## 3. Architecture freeze and safety contracts

### 3.1 Single-writer invariant

- **Trusted authorization:** authenticated actor, four-eyes approval, immutable approved revision, scoped tenant and entity, nonrevoked authority, exact source version.
- **Transaction boundary:** commit approved state + outbox/publication intent together. If business and publication schemas occupy different databases, define and test transactional outbox ownership and reliable relay; **never claim distributed atomicity**.
- **One publication execution service:** use `Journal` + `PublicationWorker` for effectful publication. `DurableWorker` may only translate committed legacy outbox events to new jobs, with transactional deduplication; it must not publish or invent receipts. Existing `OutboxProcessor`, `PromotionService`, direct graph helper, and patch-layer legacy aliases must not effect canonical writes.
- **Every external effect** has a persisted preimage and desired postimage before the call, plus an observed postimage after the call. Unknown outcome after timeout is reconciled by readback before retry; do not blindly apply again.
- **Tenant isolation:** tenant is required at the API, source records, SQL, graph node, vector payload, generation directory and receipt. Do not silently substitute `default` for missing tenant in user-facing paths.

### 3.2 Publication state contract

`APPROVED → QUEUED → LEASED → GRAPH_PREPARED → GRAPH_APPLIED → GRAPH_VERIFIED → VECTOR_PREPARED → VECTOR_VERIFIED → POINTER_ACTIVE_AND_ACKED → PUBLISHED`.

A minimal database may internally represent effects using `prepared/verified`; preserve a **separate stage/event audit trace** so partially completed effects cannot be interpreted as all verified. No `PUBLISHED` without a readback-backed graph effect, physically verified FAISS binary and payloads, active reader acknowledgment, tenant-scoped pointer, and immutable receipt. A job with only a graph operation must have an **explicit graph-only publication contract**, not be forced to fabricate a vector receipt or silently mark published.

### 3.3 Rollback contract

Persist original graph value, original authoritative pointer ID + digest + epoch, and original immutable generation. On rollback, fence the worker, compare current graph to expected published postimage, restore exactly the original value, CAS the pointer to the **original verified generation**, force serving-reader reload and verify, and only then mark each effect compensated. If there was **no previous generation**, execute an explicit, authorized deactivation state—not a generic DELETE that leaves stale in-memory readers. If concurrent changes are detected, enter **CONFLICT / NEEDS_HUMAN_RECONCILIATION**, not a reported success.

### 3.4 Financial and Feedback contracts

- **Financial:** NAV exact lookup keyed by scheme/plan/date/version/source row; no unsafe SUM/AVG of per-unit NAV; AAUM aggregation disallowed without canonical grain + steward approval and receipt; all numeric results bound to source dataset, complete contributor ledger, external digest and exact query operation.
- **Ingestion:** preserve original source bytes and declared chunk hash/order; no auto-activation; atomic dataset activation only after full attestation, zero quarantine or approved exceptions, signed dataset decision, and rollback anchor.
- **Feedback:** issue `RESOLVED` only when current, unrevoked `PUBLISHED` work, receipt, tenant, graph effect and active vector pointer all agree; rollback must reopen the actual issue row and update all dependent links durably.
- **Assurance:** UNKNOWN is not PASS; all evidence linked to a commit SHA, job ID, environment, test run, artifact digest and reviewer.

---

## 4. Implementation packages: execute in bulk, keep reviewable PR boundaries

Recommended **five coherent PRs**. Dependency-order work inside PRs is permitted. No release merge until every critical gate passes. Avoid fragmenting into one PR per function.

### Package CI — deterministic and enforceable assurance (CI01–CI08)

| Task | Implementation instruction | Acceptance evidence |
|---|---|---|
| **CI01 P0** | Break package import side effects: avoid eagerly importing `DurableWorker`/`PublicationWorker` from `amc_publication.__init__`; make worker imports explicit and isolate `app.services` metrics behind optional runtime adapter. Preserve public API compatibility via explicit tests. | Import `amc_publication.models`, `journal`, `quality` with only contract deps; no `httpx` cascade. |
| **CI02 P0** | Reproduce and fix Wave1.9/bridge collection failures. Define pinned test extra/requirements with `SQLAlchemy`, `alembic`, `pytest`, `httpx` if needed and genuine transitive deps. | Both V2 workflows on exact SHA collect **and run** the full test set; zero ERROR and zero surprise SKIP. |
| **CI03 P0** | Resolve `setuptools` advisories using a compatible patched version (CI report indicates at least `84.1.0`); audit pinned backend and build dependencies, not just installed runner packages. | `pip-audit` green or explicit independent waiver with expiry (waived vulnerabilities remain release-blocking unless risk acceptance signed). |
| **CI04 P0** | Restore a real, license-independent secret scan using pinned Gitleaks OSS CLI/verified official binary with checksum; remove comments and no-op success. | Negative test with harmless canary secret fixture fails job; no secret values printed. |
| **CI05 P0** | Ensure unit/regression/fault suites all exist and are required; replace `exit 0` on missing suite and placeholder echo checks. | Checks run actual assertions; absent required directory exits nonzero. |
| **CI06 P0** | Replace fake canary/release job with explicit NON_RELEASE status unless real deployment, probe and rollback evidence exists. | No “approved” artifact from a non-deployed run; gate state includes BLOCK with reasons. |
| **CI07 P1** | Matrix for Windows local and Linux CI: path handling, filesystem sync, FAISS binaries, SQLite/PostgreSQL variants where applicable; keep CI hardware requirements CPU-only and optional GPU tests separate. | Pinned environment and expected platform results, no untracked skips. |
| **CI08 P1** | Reconcile 109 vs 112 local tests; generate `pytest --collect-only` report and `JUnit XML`, include test hash/source SHA and exact commands. | Deterministic collected, passed, failed, skipped counts in committed test-evidence JSON. |

**First unblock:** CI01–CI05; rerun all checks before interpreting further failures. `httpx` is the current first import failure, not necessarily the only missing dependency.

### Package PUB — authoritative approval/outbox/publication cutover (PUB01–PUB08)

| Task | Implementation instruction | Acceptance evidence |
|---|---|---|
| **PUB01 P0** | Wire `governance.py` approval and proposal-review routes to persist authorized approval and enqueue an immutable v2 publication job; map proposal ID, revision, tenant, target entity, source version, current pointer, and actor. | Authenticated 202 response contains persisted `work_id` and URL; no external write on approval. |
| **PUB02 P0** | Fix `/promote/{patch_id}` catching its own `HTTPException(202)` as 500; remove graph mutation inside endpoint. | Verified 202 (not 500), actual queued job; no graph/vector modification until worker claims. |
| **PUB03 P0** | Consolidate `PromotionService`, `OutboxProcessor`, `DurableWorker` relay with one job submission API and unique idempotency. Remove placeholder `execute_work` published behavior. | One event produces one work record and at most one receipt after real effects; duplicate delivery unchanged. |
| **PUB04 P0** | Disable `promote_to_permanent`/legacy `approve_patch` direct-write alias and route-level bypass. Build static inventory of every write path (`MATCH SET`, `promote`, `PATCH`, reindex, state transitions). | Negative tests demonstrate all unsupported paths fail closed; no direct canonical writes outside worker. |
| **PUB05 P0** | Make `PublicationWorker` use unique `self.owner`, durable renewal, TTL expiry and fencing, and fix tenant/worker argument mistakes in `DurableWorker.claim_work`. | Two-worker Postgres contest, stale fence cannot commit effects/receipt. |
| **PUB06 P0** | Implement observation-based graph proof after CAS, including the exact node identity, attribute, canonical normalized value, source revision, tenant and fencing receipt. | A write no-op, wrong node, stale read, graph outage, wrong tenant or mismatched value cannot mark VERIFIED. |
| **PUB07 P0** | Persist and verify previous vector pointer and physically loaded FAISS binary on publication; activate only after independent reader reload and consistency probe. | Multiple reader processes observe new generation; failed reload blocks PUBLISHED. |
| **PUB08 P0** | Add read-only status/reconciliation route (`QUEUED`, `LEASED`, `VERIFYING`, `PUBLISHED`, `FAILED`, `ROLLBACK_PENDING`, `ROLLED_BACK`, `CONFLICT`), stable error contracts, correlation and no raw secret/data leakage. | API/frontend Contract snapshot and replay-safe idempotency; documented state semantics. |

### Package REC — crash consistency, real FAISS/Neo4j, rollback (REC01–REC08)

| Task | Implementation instruction | Acceptance evidence |
|---|---|---|
| **REC01 P0** | Migrate `012` and preceding chain on disposable PostgreSQL and SQLite variants; validate SQL dialect, indexes, unique keys, FK and timestamp semantics. | Schema contract and upgrade/downgrade rehearsal **only on disposable DB**; production migration backup/recovery plan. |
| **REC02 P0** | Preserve immutable original graph preimage *and* previous vector `generation_id`, digest, pointer epoch in durable effect/journal. | After process restart original anchors remain retrievable; no reliance on in-memory dicts. |
| **REC03 P0** | Fix rollback to restore prior generation using CAS and positive verified reader ack, not deleting pointer unconditionally. Separate null baseline deactivation. | Source generation reappears after rollback, reader results equal prior sample; stale competing pointer rejected. |
| **REC04 P0** | Handle graph write success followed by DB exception, vector stage success followed by restart, pointer switch success followed by receipt failure. Use readback-driven idempotent resume, not blind retry. | Inject kill at every side-effect boundary; exactly one logical published result or recoverable failure, never phantom receipt. |
| **REC05 P0** | Implement a real FAISS `IndexIDMap2` smoke: source bytes/embedding dimension/normalized vectors, exact IDs/count, payload hash, index digest, reload and search probe; encrypted or tenant-isolated storage as required. | All physical artifact identities match; corrupt binary or payload prevents activation. |
| **REC06 P0** | Neo4j graph-schema alignment: real labels and entity identifiers, allowlist, tenant and source revision, index/constraint, transaction boundaries and independent readbacks. | Real ephemeral Neo4j fixture verifies CAS and permission errors; no arbitrary Cypher interpolation. |
| **REC07 P0** | Make partial-effect and rollback conflicts explicit in durable journal; compensation verifies effect still matches intended postimage and observed preimage restored. | Cross-store fault matrix, conflict remains quarantined for human reconciliation; no false `ROLLED_BACK`. |
| **REC08 P1** | Fix Windows `FaissGenerationStore.stage` directory fsync/rename behavior; fail if atomicity/durability cannot be guaranteed; use copy/atomic replacement with documented semantics, not blanket exception swallowing. | Windows filesystem tests + Linux CI; recover from interruption with no mixed generation files. |

### Package DATA — verified CSV, numeric truth and provenance cutover (DATA01–DATA07)

| Task | Implementation instruction | Acceptance evidence |
|---|---|---|
| **DATA01 P0** | Wire `amc_quality.ingestion_gate.guarded_ingest()` into actual CSV ingestion entrypoints (`run_tabular_ingestion`, API/queue/jobs); prohibit legacy fallback activation and hardcoded 16,245/22 default acceptance. | Tampered source/chunk and missing manifest stop ingestion before ACTIVE; no hidden bypass. |
| **DATA02 P0** | Distinguish staged/quarantined/validated/active dataset state, provenance and steward authorization; ensure post-ingest reconciliation and transactional activation with immutable previous version anchor. | Restart/partial failure leaves previous active dataset untouched. |
| **DATA03 P0** | Replace legacy `source_row_ids[:50]` with complete contributor ledger reference and digest; optionally include capped preview clearly labeled non-exhaustive. | Query with >50 contributors shows full, independently verifiable ledger; no truncated proof called complete. |
| **DATA04 P0** | Make the validated `FinancialQualityReadModel` authoritative for supported count/exact NAV; fail-closed for unsupported AAUM operation or ambiguous plan identity. | Every numeric answer path, stream, and fallback receives same result/error; ≥50 independent gold cases. |
| **DATA05 P0** | Reconcile all `QueryPlanner` plans (AAUM rank/count, scheme count/distribution, NAV date+plan) with metric vocabulary/units/grain; avoid presenting `COUNT` as AAUM. | Unit/metric/operation correctness and deterministic tie-breaking. |
| **DATA06 P1** | Validate full source corpus where permitted; preserve byte SHA-256, ordered chunk hashes, row completeness, zero silent quarantine, consistent `source_row_id` and historical dataset isolation. | Signed reconciliation report and selected redacted proofs; no customer data in public CI artifacts. |
| **DATA07 P1** | Regression for PDFs/TXT and hybrid retrieval; ensure financial enforcement does not degrade non-CSV answers, citation or relevance. | Independent PDF/TXT golden corpus and latency profile vs baseline; no unsafe numeric fallback. |

### Package FB — issue outcomes, parity and observability (FB01–FB06)

| Task | Implementation instruction | Acceptance evidence |
|---|---|---|
| **FB01 P0** | Replace staging-count checks in legacy `FeedbackOutcomeService`; join tenant-scoped actual `PublicationWork`, `PublicationReceipt`, effects, pointer and issue. | Cannot resolve with staged-only, old receipt, wrong tenant, revoked job or no pointer. |
| **FB02 P0** | Transactionally/reliably reflect `FeedbackPublicationLink` outcome into actual `feedback_issues.status`; handle separate DBs with durable event relay and deduplication. | Issue row, UI and linked receipt converge after restart, never misleading RESOLVED. |
| **FB03 P0** | Rollback reopens the specific issue and dependent issues, invalidates stale serving eligibility, preserves human audit history. | Graph/vector rollback causes correct issue status + UI update; no false completion. |
| **FB04 P1** | Restore or replace deleted `packages/amc-feedback-loop` via explicit maintainer choice, with compatibility mapping for classification/adjudication/repair/frontend. | Signed migration/retirement decision; old API contract tests green or approved sunset. |
| **FB05 P1** | Actual durable SLO windows: queue age, failure rate, publish latency, rollback latency, receipt verification, active-reader lag, cost. Distinguish no samples from zero latency. | Grafana/Prometheus or low-cost local metrics with time-windowed queries; UNKNOWN remains blocking. |
| **FB06 P1** | Frontend state transitions and user experience: pending approval, queued, processing, published, failed, rollback conflict and retry; do not imply instant approval. | Browser and API integration tests, session/auth, error accessibility and timeouts. |

### Package GATE — independent evidence, tests and release (GATE01–GATE07)

| Task | Implementation instruction | Acceptance evidence |
|---|---|---|
| **GATE01 P0** | Create disposable-service integration composition with PostgreSQL, Neo4j, real FAISS, app/worker, synthetic CSV and Feedback fixtures; use open-source/low-cost local test containers. | One command starts isolated environment; destructive tests cannot target production DSNs. |
| **GATE02 P0** | Full end-to-end scenario: Feedback → diagnostic proposal → four-eyes approval → outbox → real graph+vector → receipt → answer/UI → rollback → issue reopened. | Video/JSON trace, exact source and receipt hashes, no invented pass. |
| **GATE03 P0** | Execute ≥50 concrete negative/fault cases in §5, including two-worker fence contention and every persistence crash boundary. | Machine-readable observed outcomes vs expected; zero tautology assertions. |
| **GATE04 P0** | Run full backend/frontend regression, dedicated Wave1.9/2.0 contracts, auth/RBAC/tenant isolation and security scans on identical SHA and lockfile. | Green required CI checks with test counts and artifact links. |
| **GATE05 P0** | Perform staging canary only after preceding gates; fixed safe rollback plan and realistic observation window. | Actual deployment/check URL, healthy requests, negative probes, rollback drill, cost telemetry. |
| **GATE06 P1** | Generate `remediation/wave2_1/` evidence ledger and source baseline per PR: state/owner/test/commit/time/environment/review. | Reproducible release manifest with hashes and signed decision. |
| **GATE07 P0** | Independent go/no-go with P0 blocker count, security/privacy signoff, data steward approval for any financial aggregation and rollback authorization. | No release without explicit owner approval and all mandatory gate evidence. |

**Total: 44 scoped tasks** across six implementation packages (CI 8 + PUB 8 + REC 8 + DATA 7 + FB 6 + GATE 7). Use 5 reviewable PRs (CI, PUB, REC, DATA+FB, GATE); tasks are acceptance criteria, not instructions to create 44 tiny PRs.

---

## 5. Required adversarial and deterministic test matrix

Below are **56 concrete tests**; implement using parameterized cases wherever possible. Every test must assert a materially observable state and receipt, **not** `assert True` or `assert result in (True, False)`.

### Approval, outbox and authority (T01–T10)
1. Proposer attempts self-approval → 403, no work queued.
2. Wrong role calls approve/promote → 403, no side effects.
3. Unknown tenant/blank tenant → reject; no `default` substitution.
4. Same approved revision/idempotency submitted twice → one work/receipt.
5. Same idempotency key, changed payload → deterministic conflict.
6. Revision revoked between approval and lease → stop before effects.
7. `/promote` returns 202 with persisted work and no direct graph mutation.
8. Legacy `promote_to_permanent` invocation fails closed.
9. Legacy `OutboxProcessor` replay cannot mark completed without v2 work acknowledgment.
10. `DurableWorker.execute_work` cannot fabricate `published` state or receipt.

### PostgreSQL fencing / concurrent workers (T11–T20)
11. Two workers claim same job concurrently → one valid lease/fence.
12. Expired lease is reclaimable with incremented epoch/fence.
13. Stale owner cannot mark prepared/verified/published.
14. Worker's own ID retained, no hardcoded common owner.
15. Fence-claim parameter uses tenant, not worker ID.
16. Lost DB connection after graph write → recover by independent graph readback.
17. Worker crash just before durable preimage → no external side effect.
18. Worker crash just after durable preimage → safe resumption.
19. Idempotent outbox relay after ACK crash → one logical job.
20. Worker failure after max retries → dead-letter/quarantine, not phantom success.

### Graph, vector and rollback (T21–T34)
21. Neo4j wrong-node match → fail without receipt.
22. Missing tenant property → fail closed.
23. Arbitrary graph property/label injection rejected by allowlist.
24. Graph conditional write success but readback stale/wrong → not VERIFIED.
25. Graph write success, DB receipt write fails → reconcile on restart.
26. FAISS physical index missing → no activation.
27. FAISS binary checksum altered → no activation.
28. FAISS payload ID map/count corrupted → no activation.
29. FAISS embedding dimension mismatch → no activation.
30. Vector pointer swapped but serving reader still old → no PUBLISHED.
31. Stale generation-pointer CAS rejected without corrupting current pointer.
32. Rollback restores exact **previous** generation (not `NULL`).
33. First-generation rollback executes explicit verified deactivation.
34. Concurrent new publication after old job → old rollback reports conflict, does not erase newer generation.

### CSV, financial and provenance (T35–T46)
35. Source file byte changed while CSV rows appear same → SHA detects.
36. Chunk file reordered/removed/duplicated → reject.
37. Manifest count is correct but chunk bytes changed → reject.
38. Source changes during ingestion → old active version retained.
39. Quarantined row exists → no automatic activation.
40. Duplicate scheme-code with different plan/date NAV → ambiguity, not arbitrary `LIMIT 1`.
41. NAV SUM/AVG attempted → metric policy blocked.
42. AAUM rank/total without steward approval → blocked.
43. COUNT output mislabeled AAUM → rejected by metric/unit contract.
44. >50 contributor rows → complete ledger contains every contributing row.
45. Contributor ledger tampered after answer → external anchor verification fails.
46. PDF/TXT control answers unchanged by CSV integrity guards.

### Feedback, serving, security and release (T47–T56)
47. Issue resolved with only staging count → denied.
48. Valid receipt but wrong tenant → denied.
49. Verified old receipt after pointer changed → denied.
50. Approved (not ACTIVE) patch in fast-path → not served.
51. Rollback after verified issue resolution → actual issue reopened.
52. Frontend reload after worker crash → durable correct state, not optimistic “resolved”.
53. Missing required CI test directory → workflow fails.
54. Known vulnerable dependency in pip-audit → workflow fails, no successful release gate.
55. Secret-scan canary fixture → scanner produces failing status without exposing secret.
56. No measured SLO window or no real canary → release remains BLOCK.

Supplement with full network/interruption, database isolation, browser and performance tests. Report actual collected/pass/fail/skip counts per environment; this list is an acceptance target, **not tests executed by this audit**.

---

## 6. Implementation sequence and dependencies

| Stage | Bulk execution target | Unblocks | Stop condition |
|---|---|---|---|
| **S0 — CI diagnostic recovery** | CI01–CI05 + CI08; exact-SHA import, dependency and scan fixes | Reliable pass/fail signal for subsequent work | New failure must be investigated, never bypassed |
| **S1 — safety containment** | PUB02–PUB04 and PUB08; disable invalid publishing paths; stop fake status transitions | Safe baseline for live wiring | Legacy write route still reachable |
| **S2 — authoritative integration** | PUB01, PUB05–PUB07, REC01–REC02; transaction/outbox and graph readback | Real verified publication attempt | Multiple writers or missing preimages |
| **S3 — real effects/recovery** | REC03–REC08 + GATE01/03; real Neo4j and FAISS, stale worker and rollback | Recoverability proof | Pointer/graph mismatch or unverified reader |
| **S4 — data and Feedback** | DATA01–DATA07 + FB01–FB06 in parallel where safe | Reliable user answer semantics | Legacy CSV numeric bypass or false Feedback resolution |
| **S5 — integrated release evidence** | GATE02/04–GATE07; full regression, canary, audit | Release review only | Any P0 RED/UNKNOWN |

The bulk execution strategy is **S0+S1 together**, then **S2+S3 together**, with DATA and FB modules in parallel; finish with S5. Do not promote experimental fixes to production while the gates are red.

---

## 7. Precise repository implementation map

| Existing file/subsystem | Minimal required change |
|---|---|
| `.github/workflows/amc-publication-v2.yml` | Reproducible deps; no eager import cascade; pytest collection and contract execution |
| `.github/workflows/amc-quality-v2.yml` | Contract-bridge dependencies and full exact-SHA tests; preserve successful independent job |
| `.github/workflows/amc-assurance.yml` | Restore real Gitleaks CLI, upgrade vulnerable setuptools, fail on missing suites, remove fake SLO/canary success |
| `backend/amc_publication/__init__.py` | Side-effect-free exports or lazy imports |
| `backend/amc_publication/worker.py` | Unique owner; real graph readback; previous-generation rollback; disable `DurableWorker.execute_work` fake status |
| `backend/amc_publication/journal.py` | Original pointer preimage, fenced CAS restore and durable crash stage tracking |
| `backend/amc_publication/repository.py` | Consolidate with Journal or restrict to relay; fix `claim_with_fence(tenant)` API usage |
| `backend/amc_publication/graph.py` | Adapt tenant/entity schema, exact post-write readback, revision/fence/allowlists |
| `backend/amc_publication/faiss_artifacts.py` | Real FAISS build/reload/manifest verification, Windows portability, reader probe |
| `backend/amc_publication/feedback.py` | Durable link, actual issue status update, rollback reopen; atomicity/relay contract |
| `backend/amc_publication/serving.py` | One authoritative serving eligibility API used everywhere |
| `backend/app/api/routes/governance.py` | Safe 202+work ID; remove route-time graph effects and `202→500` exception conversion |
| `backend/app/services/promotion_service.py` | Enqueue-only, explicit new work status and proper ACK; never prematurely mark applied |
| `backend/app/services/outbox_processor.py` | Single relay or retire, not a second external effects executor |
| `backend/app/graph/correction_patch_layer.py` | Remove direct promote alias; active patches require DB receipt and tenant |
| `backend/app/services/feedback_outcome_service.py` | Replace `_get_staged_count()` placeholders, persistent actual issue state |
| `backend/app/retrieval/fast_path_interceptor.py` | Shared tenant-scoped DB-backed predicate, not dict-local booleans |
| `backend/app/tabular/csv_excel_loader.py` and ingest entrypoints | Use Wave 2.0 manifest gate, no magic defaults or auto activation |
| `backend/app/tabular/executor.py` | Remove truncated provenance assertion; complete ledger reference and proof hash |
| `backend/amc_quality/financial.py`, `manifest.py`, `provenance.py`, `ingestion_gate.py` | Reuse as existing vetted components, wire into production flow rather than rewrite |
| `backend/tests/test_wave19_*.py`, `test_wave20_*.py` | Preserve existing local tests; add full end-to-end and adversarial suites |
| `backend/alembic/versions/012_wave19_durable_publication.py` | Test complete upgrade chain on truly disposable target; no unapproved live downgrade |
| `mf-context-engine/src/components/feedback/*` | Real async status, in-review, failed, rolled back and citation/causality states |

### Additional audit requests for Codex before modification

1. Create a machine-readable import graph and exact callback map (`app` routes → services → SQL/Neo4j/FAISS) with the old and new publication paths.
2. Locate all native Neo4j `MATCH/SET/DELETE`, raw FAISS `_index` mutations, `activate_*` and Redis patch overrides; flag writes outside the designated worker.
3. Check Python 3.11 + local Windows/Python compatibility, actual dependency lock and correct `fastembed` embedder API.
4. Confirm the backend's `app.core.database` remains hardcoded SQLite; do not assume a `DATABASE_URL` environment variable controls it. Verify *which* DB receives migration `012` and which DB the worker uses.
5. Identify caller behavior for `get_active_patches` and `_is_serving_eligible_patch`, including event-stream and generative answer fallbacks.
6. Establish steward approval source and a read-only policy for AAUM until approval is explicit.

---

## 8. Expected evidence artifacts (`remediation/wave2_1/`)

The following are **deliverables to generate after execution**; they do not currently exist as verified test outputs in this handoff.

```text
remediation/wave2_1/
  SOURCE_BASELINE.md
  FINDINGS_REGISTER.csv
  ENTRYPOINTS_WRITERS_MAP.csv
  TASK_MATRIX.csv
  CONTRACT_DIFFERENCES.md
  CI_FAILURE_ROOT_CAUSES.md
  CI_EXACT_SHA_EVIDENCE.json
  PYTEST_JUNIT.xml
  DEPENDENCY_LOCK_SHA256.txt
  DEPENDENCY_VULNERABILITY_REPORT.json
  SECRET_SCAN_REPORT.json
  MIGRATION_REHEARSAL_REPORT.md
  POSTGRES_MULTI_WORKER_TRACE.json
  NEO4J_GRAPH_READBACK_RECEIPTS.json
  FAISS_GENERATION_MANIFESTS.json
  ROLLBACK_FAULT_MATRIX.json
  FINANCIAL_GOLDEN_RESULTS.json
  CSV_SOURCE_ATTESTATION.json
  FEEDBACK_CAUSALITY_MATRIX.json
  FULL_REGRESSION_MATRIX.json
  SLO_WINDOW_EVIDENCE.json
  CANARY_ROLLBACK_DRILL.md
  RELEASE_GATE_MATRIX.md
  FINAL_SIGNOFF.md
```

Each artifact must contain exact SHA, environment, command, timestamp, owner, result, proof pointer and unexpected skips. Keep secrets, raw customer records and PII out of public/PR artifacts.

---

## 9. Practical Codex commands (templates; **not executed here**)

Run from a **clean checkout of the actual repo**. Use a feature branch rooted at the pinned SHA; if branch has moved, reconcile and repin before patching. Replace the environment-specific DB/service values with **disposable** test instances only.

```powershell
# Windows PowerShell
cd path\to\amc-context-engineering-poc
git fetch origin
git checkout amc-dev
git pull --ff-only
git rev-parse HEAD
# Confirm the SHA against this handoff, then create a feature branch:
git switch -c fix/wave21-integrate-release-gates

# Preserve an evidence copy before changes
New-Item -ItemType Directory -Force remediation\wave2_1 | Out-Null
python -m compileall -q backend\amc_publication backend\amc_quality

# Exact isolated contract discovery and execution (enable venv; install lock/test extra first)
$env:PYTHONPATH = "backend"
python -m pytest --collect-only -q backend\tests\test_wave19_*.py backend\tests\test_wave20_*.py
python -m pytest -q backend\tests\test_wave19_*.py backend\tests\test_wave20_*.py --junitxml=remediation\wave2_1\PYTEST_JUNIT.xml
```

For GitHub Actions, run the already registered workflows against this new branch/PR using actual dispatch/normal push trigger, and inspect the resulting job logs and test XML. **Do not mark CI green from local output.**

For database migration, use a **throwaway** PostgreSQL/Neo4j/SQLite environment with a test-only DSN; verify the connected `DATABASE_URL` is actually honored by the database configuration. Never run `alembic downgrade base` against an existing working database. Build real FAISS binary locally with `faiss-cpu`, and keep the test artifact directory outside production data.

### Minimal acceptance report template

```text
Source SHA: <git rev-parse HEAD>
Environment: <OS/Python/Postgres/Neo4j/FAISS versions>
Unit/contract: collected=?, passed=?, failed=?, skipped=?, xfail=?
Full backend: collected=?, passed=?, failed=?, skipped=?
Frontend: suite=?, pass=?, fail=?
Critical functional workflow: PASS | FAIL | NOT_RUN
Postgres 2-worker fence test: PASS | FAIL | NOT_RUN
Neo4j independent readback: PASS | FAIL | NOT_RUN
FAISS binary/serving pointer: PASS | FAIL | NOT_RUN
Rollback restore prior generation: PASS | FAIL | NOT_RUN
CSV + PDF/TXT gold: PASS | FAIL | NOT_RUN
Feedback issue lifecycle: PASS | FAIL | NOT_RUN
Secret/vulnerability scan: PASS | FAIL | NOT_RUN
Release: BLOCK | CONDITIONAL_REVIEW | APPROVED
Evidence links/hashes: ...
```

---

## 10. Single copy/paste Codex instruction — bulk implementation

> **ROLE:** Senior/principal software architect and implementation engineer for AMC Context Engineering POC. Work autonomously in bulk while maintaining reviewable commits. Do not stop after creating planning files.
>
> **REPO:** `nusummit-spg/amc-context-engineering-poc`, branch `amc-dev`; audit SHA `fe28ca6844ae170fcdcf434e0b65dde237738b90` as source baseline. Inspect the current HEAD/diff; repin if changed. Never force-push or overwrite unrelated work.
>
> **ALREADY EXISTS:** `backend/amc_publication`, `backend/amc_quality`, migrations 009–012, Wave1.9/2.0 tests. User reports 109 local passing tests. Existing repo evidence records 112 from earlier execution. **Do not build a competing engine or discard working code.**
>
> **MISSION:** Implement all feasible Wave2.1 tasks in **five bulk PR boundaries**: (1) CI/import/dependency/secret/vulnerability gates; (2) application approval/outbox/single-writer publication cutover; (3) graph/vector readback, fenced replay and true prior-generation rollback; (4) guarded CSV/financial provenance/Feedback runtime integration; (5) full independent test/observability/release evidence. Prefer zero-cost local services, open source, CPU-compatible CI and Windows local parity.
>
> **FIRST:** Fix Wave1.9 CI `ModuleNotFoundError: httpx` import cascade and reproduce complete contract suite. Fix `pip-audit` finding on `setuptools 79.0.1` without suppressing audit. Restore real Gitleaks OSS CLI (the `gitleaks-action@v3` organization-license variant had previously blocked CI). Investigate every new failure rather than adding skips.
>
> **CRITICAL RUNTIME FIXES:** `PublicationWorker` MUST independently read back the Neo4j graph after CAS; `DurableWorker.execute_work` MUST NOT manufacture `published`; `Journal.switch_back` MUST restore previous verified FAISS generation via CAS, not delete active pointer by default; `/promote` must queue work and return actual 202 instead of performing graph writes then catching its own 202 as 500; disable legacy `promote_to_permanent`/approved patch serving; bridge approved proposal → durable outbox → one authoritative worker. Ensure unique worker owners, correct tenant/fencing parameter passing and exact cross-store receipts. Do not mark ACTIVE/PUBLISHED on unsupported paths.
>
> **DATA/FEEDBACK:** Wire existing `amc_quality` manifest verification and staging-only guarded ingestion into every CSV entrypoint; never auto-activate. Wire complete provenance (do not truncate IDs at 50). Reconcile metric operations/count vs AAUM and keep AAUM unapproved until steward receipt. Replace Feedback staging-count placeholders with durable tenant-scoped receipt joins and actual issue state changes; rollback reopens issues. Preserve PDF/TXT behavior.
>
> **VERIFY:** Run full existing and new tests; disposable PostgreSQL + Neo4j + real FAISS, two worker fencing, crash/retry/rollback at each side-effect boundary, precise source hash/manifest attestation, CSV/PDF/TXT golden corpus, frontend contract tests. Generate `remediation/wave2_1/` evidence files specified in this handoff, and update task states based solely on observed results. Stop release if any P0 failure or missing critical measurement; produce a concise summary with exact SHA, passes/fails/skips, changed files, unresolved blockers, and next owner actions.
>
> **SAFETY:** Never connect destructive migration/fault tests to production; no unverified secrets/PII in artifacts. Do not fake CI status, canary evidence, user approval, steward signoff or release completion. Fail closed if external services are unavailable.

---

## 11. Final CTO recommendation / release gates

| Gate | Required success criteria | Observed in this audit |
|---|---|---|
| **CI** | Exact SHA CI green, pinned deps, real scans | **FAIL** — `httpx` collection and `setuptools` vulnerability |
| **AUTH/GOV** | Four-eyes + tenant + single writer, no bypass | **UNVERIFIED / source risks** |
| **PUB** | Durable lease, exact pre/post effects, real graph/FAISS readback and receipt | **UNVERIFIED / gaps identified** |
| **ROLLBACK** | CAS restore previous real generation and graph, reader ack, Feedback reopen | **FAIL BY SOURCE CONTRACT** for previous-generation restore |
| **DATA** | Mandatory byte-verified CSV gate; complete provenance, gold | **PARTIAL** — independent quality CI PASS, runtime cutover unverified |
| **FEEDBACK** | Actual issue rows and UI follow tenant-scoped durable receipt | **UNVERIFIED / legacy placeholders remain** |
| **E2E** | Real-service functional and adversarial suite PASS | **NOT_RUN here** |
| **OPS** | Real SLO windows, secret/dependency scans, safe canary, signed go/no-go | **FAIL/UNKNOWN** |

### Priority and stopping rule

1. **Immediately** fix CI and contain legacy writers/serving bypasses. These are smaller changes with disproportionate safety benefit.
2. **Next** correct graph readback and previous-generation rollback, then demonstrate two-worker fenced publish and rollback with real services.
3. **In parallel** integrate the existing financial manifest, provenance and Feedback assurance modules into actual application routes; do not rewrite already tested packages.
4. **Only then** run a staging canary and independent go/no-go. Until passing evidence exists, the release is **BLOCKED**.

The measure of progress for Wave2.1 is **not how many more modules exist**, but whether one end-to-end Feedback repair transaction can publish, serve and roll back safely while every state is externally observable and the exact GitHub SHA has green required checks.

---

### Source references

- [Reviewed source at pinned commit](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/fe28ca6844ae170fcdcf434e0b65dde237738b90)
- [Publication worker](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/fe28ca6844ae170fcdcf434e0b65dde237738b90/backend/amc_publication/worker.py)
- [Journal and rollback pointer](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/fe28ca6844ae170fcdcf434e0b65dde237738b90/backend/amc_publication/journal.py)
- [Existing governance endpoints](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/fe28ca6844ae170fcdcf434e0b65dde237738b90/backend/app/api/routes/governance.py)
- [Wave 2.0 test evidence (prior baseline)](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/fe28ca6844ae170fcdcf434e0b65dde237738b90/remediation/wave2_0/TEST_EVIDENCE.json)
- [Publication CI run](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42602341495)
- [Quality CI run](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42602341554)
- [Overall assurance CI run](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42602341697)

**This handoff is an authored plan based on a remote source audit. No Wave 2.1 code was committed or tests run as part of preparing this file.**
