# AMC Context Engineering POC — Wave 1.7
## Principal Architect Source Re-Audit, Remediation Backlog & Local Codex Handoff

**Date:** 6 November 2026 (Asia/Kolkata)  
**Repository:** [`nusummit-spg/amc-context-engineering-poc`](https://github.com/nusummit-spg/amc-context-engineering-poc)  
**Target branch:** `amc-dev`  
**Pinned, observed HEAD:** `bea1fbd4e52fdc93fa064c47ed1377347d3852f7`  
**Previous Wave 1.6 baseline:** `4ede4338642949f0a32ee0672b4dc09616659193`  
**Observed delta:** 1 commit; 12 files modified/added.  
**Execution mode:** Local Codex/agent, substantial batches, reviewable commits, no automatic production writes.  
**Release decision:** **BLOCK / NO-GO** until the P0 acceptance gates in this document pass with real evidence.

> **Evidence boundary.** Findings below come from a GitHub source review, repository manifests, and a live GitHub Actions run/job log. Neither a clean local run nor end-to-end graph/vector/database tests were executed by this reviewer. “Code exists” is not equivalent to “runtime verified.” No benchmark or pass count is asserted without actual results.

## 1. Executive decision

The next milestone is **not another framework expansion**. It is a **functional integrity and runtime-evidence closure**, centered on the remaining V16-05–V16-14 issues. Wave 1.6 did contain some earlier defects, but critical behaviors still occur through divergent paths or depend on process memory. The order of work matters:

1. Establish a **working, non-deceptive CI quality gate** on `amc-dev` and stabilize the approval/retrieval contract.
2. Wire **one authoritative, durable publication pipeline** from human approval to outbox claim, external graph/vector effects, verification receipt, and ACTIVE pointer.
3. Make graph/vector rollback, retry, crash recovery, and Feedback status **depend on verified durable evidence**, not staging lists or intent-only receipts.
4. Harden financial correctness, ingestion provenance and query/UI parity, then run independent negative tests and migration rehearsal.
5. Keep Feedback package deletion blocked until product-owner disposition; prevent its absence from being masked as successful replacement.

### 1.1 Verified progress since the previous handoff

| Area | Current source evidence | Assessment |
|---|---|---|
| Wave 1.6 governance policy | `financial_policy_service.py` sets `aaum_crore.steward_approved=False`; enum-based metric operations are introduced | **Implemented containment**, business-steward sign-off still required for aggregation |
| Approval/lifecycle | `governance.py` now separates some patch approval and promotion functions | **Partial**, duplicated state writes/async hazards remain |
| Financial SQL | `planner.py` removes invalid ungrouped AAUM from the top-AMC query | **Partial**, a new meaning/alias mismatch remains |
| Feedback outcome | `_is_publication_published` and `_is_verification_complete` no longer blindly return `True` | **Partial**, they do not actually query durable publication records |
| Intent schema | Migration `backend/alembic/versions/009_b06_publication_intents_receipts.py` exists | **Implemented artifact**, migration has not been verified against a disposable real DB |
| CI | `.github/workflows/amc-assurance.yml` now triggers `amc-dev` | **Trigger fixed; pipeline failed** |
| Graph/vector work | New staging and postcondition services exist | **Not integrated/proven durable** |
| Feedback-loop microservice | `packages/amc-feedback-loop/` absent in observed tree | **Blocked product/compatibility decision** |

### 1.2 Actual CI evidence (important correction to V16-08)

**GitHub Actions run:** [AMC Assurance Pipeline — run 42202423962](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42202423962)  
**Branch/commit:** `amc-dev` / `bea1fbd4e52fdc93fa064c47ed1377347d3852f7`  
**Run conclusion:** `failure` on 6 November 2026. The initial `A01: Clean Checkout Audit` passed checkout, dependency dry-run and Python compilation, then failed at `Scan for secrets` because `pip install gitleaks` reported **“No matching distribution found for gitleaks.”** Migration, unit, regression, fault injection, canary, and release jobs were **skipped**. This is a scanner installation/CI configuration error, **not evidence of detected secrets**. The workflow also contains non-executing success echoes and targets missing test directories.

**Action:** change V16-08 from “CI has no `amc-dev` trigger” to **“trigger fixed, CI implementation failing.”** Do not count a skipped job as passed.

## 2. Priority risk register — source grounded

| ID | Severity | Observed defect / risk | Source | Required outcome |
|---|---|---|---|---|
| **W17-01 / V16-08** | P0 | GitHub Actions run fails installing Gitleaks with pip; downstream jobs skipped; workflow echoes fake release/SLO success | `.github/workflows/amc-assurance.yml`; Actions run `42202423962` | Pinned official scanner install/action, real assertions, `amc-dev` green gates |
| **W17-02 / V16-05** | P0 | Vector `_staging` and `_preimages` are in-process dictionaries; operations are cleared after apply, leaving no durable rollback journal | `backend/app/services/vector_staging_service.py` | Durable intent/effect ledger, exact-ID snapshot, immutable FAISS generations, verified rollback |
| **W17-03 / V16-06** | P0 | Graph postcondition path has in-memory staging; verify real deletes, pre/post values, effects after crashes and actual graph driver compatibility | `backend/app/services/graph_postconditions_service.py` | Real parameterized Neo4j mutations and committed postcondition readback |
| **W17-04 / V16-10** | P0 | Main `promotion_service.py` writes external effects synchronously while also enqueuing outbox events; outbox graph/state handlers raise `NotImplementedError`; split authority | `backend/app/services/promotion_service.py`, `outbox_processor.py` | One durable worker with idempotent effects, no dual execution |
| **W17-05 / G06** | P0 | `/governance/approve/{patch_id}` is synchronous and conditionally schedules `asyncio.create_task()` without awaiting; other branch directly edits patch/Redis; batch does a third implementation | `backend/app/api/routes/governance.py` | Single awaited, transactional approval service, version/CAS protection |
| **W17-06 / G04** | P0 | Feedback publication/receipt methods instantiate `GraphPostconditionsService()` / `VectorStagingService()` without required constructor dependencies; use staging counts, not DB rows; catch error and return false | `backend/app/services/feedback_outcome_service.py` | DB-backed, tenant-scoped verified ACTIVE/receipt causal proof |
| **W17-07 / serving** | P0 | Legacy correction injection gates on `patch.approved` rather than `ACTIVE + valid verified receipt`; fast-path selection still checks `approved` + confidence | `backend/app/graph/correction_patch_layer.py`, `backend/app/retrieval/fast_path_interceptor.py` | All serving modes share one strict eligibility predicate |
| **W17-08 / V16-09** | P0 | Fault-injection tests contain `assert result is False or result is True`, mock-only assertions, simulated worker claims | `backend/tests/test_wave15_publication_fault_injection.py` | Executable cross-store negative tests that fail on corruption/bypass |
| **W17-09 / V16-13** | P1 | Operations logged to in-memory metric lists; no durable/event-derived observability | `backend/app/services/operational_metrics_service.py` | Durable event/receipt ledger plus real metrics/SLO queries |
| **W17-10 / V16-11** | P0 | Manifest validation checks hash *format* and assumed chunks per 1,000 rows, not original-byte recomputation | `backend/app/services/financial_policy_service.py` | Byte-level cryptographic reconciliation, row counts/lineage, quarantine |
| **W17-11 / V16-12** | P1 | `source_row_ids` truncated at 50 in successful query response | `backend/app/tabular/executor.py` | Complete server-side provenance, bounded UI summary with cursor/ref |
| **W17-12 / V16-14** | P0 | Entire Feedback-loop package absent; replacement coverage unproven; maintainer decision unresolved | `remediation/wave1_6/FEEDBACK_PACKAGE_DECISION.md`; repository tree | Explicit restore/replace/deprecate decision, compatibility tests |
| **W17-13 / G03** | P0 | Top-AMC ranking now orders by `total_plans`, but plan metadata still says `metric_id=aaum_crore` and may advertise `total_aum_cr` sort; semantic mismatch | `backend/app/tabular/planner.py` | Truthful COUNT-only ranking or blocked AAUM ranking, never mislabel |
| **W17-14 / migration** | P0 | Migration 009 exists but no verified end-to-end upgrade/downgrade/data preservation/registered models | `backend/alembic/versions/009_b06_publication_intents_receipts.py`; CI | Disposable DB upgrade, schema contract verification, safe rollback |
| **W17-15 / graph security** | P0 | Some canonical Cypher paths interpolate patch attribute identifiers; graph mutation may be applied without authoritative lease or receipt | `backend/app/api/routes/governance.py` and graph services | Allowlisted attributes, parameterized values, durable intent / fencing token |
| **W17-16 / proposal state** | P0 | Proposal review sets `status='approved'` directly, while patch approval uses separate state logic; multiple ways can reach publication | `backend/app/api/routes/governance.py` | Unified authoritative proposal/patch state mapping + reviewer evidence |
| **W17-17 / broken promotion path** | P0 | `promote_patch_direct` and its graph helper call `await patch_layer.get_patch(...)`, but the monolith correction layer defines `get_patch_by_id()` instead; the route also calls `_execute_vector_activation()` without a definition in the reviewed module | `backend/app/api/routes/governance.py` (approx. lines 848, 910, 953); `backend/app/graph/correction_patch_layer.py` (line 455) | Contract-correct, callable promotion service with real graph/vector effects and end-to-end exercised route |

**Rule:** A prior status report saying “VERIFIED” is not a substitute for a successful test result against the same SHA. Reconcile stale references in `remediation/wave1_6/STATUS.md` and historical Wave 1.4/1.5 documents without rewriting history.

## 3. Target architecture — one transactionally governed pipeline

```text
User Feedback / Source Evidence
    -> tenant-scoped issue + provenance + proposal PENDING
    -> independent human reviewer (four eyes, immutable source revision)
    -> APPROVED (no graph/vector serving side effects)
    -> DB transaction: PublicationIntent + OutboxEvent + preconditions
    -> worker claims intent with lease + attempt/fence + idempotency key
    -> durable snapshot of graph preimage and vector current generation
    -> stage external mutations in non-serving targets
    -> graph commit + committed exact readback proof
    -> vector build of new immutable index generation + exact-ID/hash/query probes
    -> receipts persisted + source/version/tenant/actor chain verified
    -> ACTIVE pointer changed atomically (or fenced CAS)
    -> serving cache invalidation + version-bound reads
    -> Feedback issue RESOLVED only after ACTIVE verified receipt
    -> event-derived metrics + audit ledger
```

**Failure policy:** Any unknown/missing graph/vector effect, stale approval, mismatched tenant/source version, checksum failure, lease conflict, or unavailable verifier => **not ACTIVE**, no successful release receipt, no issue RESOLVED. Retries must reconcile previously applied external effects instead of repeating them blindly.

### 3.1 Authoritative persistence contract

Implement/reconcile these logical records using existing SQLAlchemy patterns and migration conventions:

- `publication_intents`: unique `(tenant, proposal_id, approved_revision, source_version, publication_type)` or equivalent idempotency key, approval receipt/hash, target, desired effect, lifecycle status, lease owner/time, attempt generation, timestamps.
- `publication_effects`: one row per `(intent_id, effect_kind, effect_target, effect_revision)` with immutable preimage pointer/hash, postimage pointer/hash, applied timestamp, observed readback/hash, result status, tenant, error, fencing token.
- `publication_receipts`: idempotency key, immutable content-hash, committed effect references, approval evidence, source and corpus versions, verifier identity, observed index generation, tenant.
- `active_versions`: tenant+corpus/graph namespace+version with atomic or CAS active generation pointer; keep previous version available for rollback.
- `outbox_events`: available-at, lease/heartbeat, bounded retry/backoff, terminal dead letter; unique effect key; record final result.
- `feedback_issue_links`: immutable issue -> evidence -> proposal -> approval -> intent -> receipts, persisted issue outcome, rollback reference.

**Storage requirements:** In-memory dicts may be caches of durable truth but must not be the only authoritative place for staged operations, preimages, active generations, or audit events. Encrypt/access-control preimages as necessary; avoid storing unnecessary sensitive data in logs.

### 3.2 Required state invariants

1. `PENDING` or `APPROVED` is **never** answer-serving.
2. `VERIFIED` is not automatically `ACTIVE`; ACTIVE requires success across required graph/vector effects, signed/hashable receipts and version pointer.
3. The proposer must differ from the reviewer/approver under a trusted identity; missing proposer metadata fails closed for privileged changes.
4. `tenant`, entity identity, source version, proposal revision, metric policy version, and published corpus version must agree across every receipt.
5. A retry with the same idempotency key is a logical no-op or verified continuation; never duplicate a graph mutation or vector entry.
6. Graph rollback restores only if current value/version matches the expected postimage; otherwise classify `CONFLICT` and require operator adjudication.
7. Reindex no-op, unavailable indexer, empty document set, and unverifiable output are not successful publications.
8. Feedback `RESOLVED` requires durable ACTIVE and valid evidence; rollback transitions to `NEEDS_REVIEW`/`REOPENED` and invalidates derived claims.
9. Any test that passes on both good and bad outcomes is invalid, not evidence.

## 4. Implementation batches — execute in bulk, but preserve independent verification

### Batch A — CI and governance containment (P0, execute first; 10 tasks)

| ID | Action | Principal files | Acceptance gate |
|---|---|---|---|
| A01 | Repair secret-scanner install with official pinned binary/release checksum or vetted action pinned by commit, not `pip install gitleaks`; make finding exit nonzero | `.github/workflows/amc-assurance.yml` | Gitleaks step executes; clean repo exits 0; seeded canary test secret fails in isolated fixture; no real secrets exposed |
| A02 | Replace `py_compile app/**/*.py` with full `compileall` + actual import/smoke of FastAPI app; run from clean install | workflow, `backend/scripts/audit_clean_checkout.py` | Syntax *and* imports checked, missing module reliably fails |
| A03 | Make workflow paths/dependencies valid. Install test deps for every job. Use `backend/tests/test_wave15_publication_fault_injection.py` or create real suites rather than missing `tests/regression/`, `tests/fault_injection/`; eliminate unsupported `--deterministic` unless registered | workflow | No fabricated PASS; all expected suites collected; zero unintentional skips |
| A04 | Add always-running branch quality gate on `amc-dev`; reserve canary/release only for protected release branch. Remove echo-only performance, canary and release claims | workflow | Push to `amc-dev` returns truthful red/green required check; release never approved on skipped prerequisites |
| A05 | Normalize `/approve`, `/batch-approve`, `/proposals/{id}/review`, `/promote` to a single service and role/tenant scope. Convert routes to `async def` when awaiting transitions; remove `create_task` fire-and-forget and direct Redis edits | `backend/app/api/routes/governance.py`, patch state service | Two callers cannot approve same revision inconsistently; state persists; returned result awaits commit |
| A06 | Enforce immutable proposer/reviewer/version/tenant, separation of duties, missing-data denial, CAS locking and auditable decision receipt | governance, proposal/approval schemas | Same actor or missing proposer -> 403/409; stale revision -> conflict; different valid actor -> approved state only |
| A07 | Replace every approved-only serving gate with one version-bound `can_serve` across chat, fast path, streaming, shadow graph, remote/local Repair | `backend/app/graph/correction_patch_layer.py`, `backend/app/retrieval/fast_path_interceptor.py`, `backend/app/retrieval/orchestrator.py` | PENDING, APPROVED, STAGED, VERIFIED never alter final answer or cited facts |
| A08 | Remove/disable legacy `promote_to_permanent` public shortcuts that set `approved=True` before verified publication; no independent canonical writes outside worker | governance, correction patch layer | Direct shortcuts rejected; only approved intent worker may mutate canonical truth |
| A09 | Replace placeholder “tests” with real authenticated route/DB behavior tests for approvals, four-eyes, tenant isolation, CAS, skip count; collect JUnit XML | `backend/tests/` | Assertions fail if a route silently schedules and returns success without state transition |
| A10 | Repair verified route/service API mismatch: stop awaiting nonexistent `get_patch`, remove undeclared `_execute_vector_activation` call or implement and wire the actual worker service, and exercise `/promote/{patch_id}` end-to-end | `governance.py`, `correction_patch_layer.py`, vector publication service | Route reaches a verified effect without AttributeError/NameError; no fake receipt or ACTIVE on partial failure |

**Exit criteria:** `amc-dev` CI executes and reports real failures/successes; approval creates persistent APPROVED evidence only; no unapproved answer contamination. No promotional writes until Batch B/C is verified.

### Batch B — durable graph/vector staging and exact effects (P0, 9 tasks)

| ID | Action | Principal files | Acceptance gate |
|---|---|---|---|
| B01 | Add durable SQL staging operations and effect receipts; migrate existing in-memory-only state carefully | `publication_intents_table.py`, new Alembic `010_*`, staging services | Kill/restart services: pending/staged operations recover exactly |
| B02 | Implement immutable FAISS generation build in non-serving directory/object prefix; compute manifest hash, doc/embedding counts, exact chunk IDs and mapping | `backend/app/services/vector_staging_service.py`, real vector store adapter | Old active index untouched before verification; generated index loads after restart |
| B03 | Preimage capture by **exact chunk ID**, not similarity query text `chunk_id:...`; persist snapshot/manifest pointer | vector store adapters | Correct document preimage selected with similar/conflicting content; missing ID explicitly classified |
| B04 | Verify FAISS generation with exact ID membership, chunk count, metadata/source hash and deterministic query probes; atomic pointer activation with fencing token | vector staging + index registry | Corrupt/wrong generation => no activation; old pointer preserved |
| B05 | Actual Neo4j parameterized writes for nodes AND edges: allowlist labels/property identifiers; parameterize values/identity; check expected revision | `graph_postconditions_service.py`, `governance.py` graph helper | Wrong identity/attribute/version rejected before mutation; no log-only success |
| B06 | Capture graph preimage in durable receipts; commit and read back **exact** target value, identity, version, tenant and required edges | graph service | No-node, no-op, wrong value, partial edge failure -> NOT VERIFIED |
| B07 | Implement graph rollback from persisted preimage with CAS against expected postimage; independently read back restoration | graph + rollback service | Crash/restart rollback works; competing update causes CONFLICT, not blind overwrite |
| B08 | Implement vector rollback via prior generation pointer and persisted preimage; invalidate serving cache and verify pointer/hash | vector staging + rollback service | Failure during activation restores previous generation/read behavior |
| B09 | Prove supported vector API is real: do not assume FAISS `remove_ids(fid)` accepts current ID type; use adapter-aware delete/rebuild with actual store integration | `backend/app/services/vector_staging_service.py`, vector client | Real FAISS fixture add/delete/query/serialize/reload passes; no zombie IDs |

**Exit criteria:** one graph + vector publication survives process restart and can be reverted with a verifiable receipt. A test must prove pending vectors are absent from serving search.

### Batch C — authoritative outbox/saga and Feedback causality (P0, 9 tasks)

| ID | Action | Principal files | Acceptance gate |
|---|---|---|---|
| C01 | Choose and document one orchestrator/worker. Approval writes intent+outbox in one DB transaction; remove direct simultaneous execution in `PromotionService` | `promotion_service.py`, `outbox_processor.py` | One approval yields one logical publication; no dual effect |
| C02 | Implement durable claim leases, `FOR UPDATE SKIP LOCKED` where DB supports it (or atomic compare-and-swap), lease fencing and heartbeat | outbox tables/migrations/worker | Two workers cannot both activate same intent |
| C03 | Replace `NotImplementedError` graph/state event handlers with real handlers invoking B services; do not swallow unsupported event types | outbox processor | Unknown event -> failed/dead letter, never completed |
| C04 | Make retry semantics deterministic and bounded: exponential backoff, jitter, DLQ, operator replay, exactly-once *logical* effect through idempotency | outbox schema/worker | Duplicate delivery after commit yields no second mutation |
| C05 | Crash/reconcile all boundaries: before outbox commit, after graph write, before graph receipt, after index build, before ACTIVE switch, after ACTIVE switch | worker/reconciler | Restart reaches VERIFIED ACTIVE or safe blocked recovery; never phantom success |
| C06 | Persist and validate causal approval -> intent -> effect -> receipt -> ACTIVE chain; source version and tenant assertions checked on every event | publication schema, service, governance | Stale approvals, cross-tenant writes, tampered receipt blocked |
| C07 | Replace Feedback outcome staging-count guesses with SQL queries for matching intent, immutable receipt, ACTIVE version, tenant, source revision and nonrevocation | `feedback_outcome_service.py` | Missing/forged/wrong-tenant receipt cannot resolve issue |
| C08 | On rollback/supersession, reopen linked issues and mark related citations/cache entries stale using durable event; preserve old audit history | Feedback outcomes and repair linkage | Resolved issue becomes NEEDS_REVIEW after verified rollback, even after restart |
| C09 | Resolve `amc-feedback-loop` deletion: safest technical default is restore the package to an isolated compatibility branch while auditing; do not merge/release until owner chooses restore, replacement or deprecation | `remediation/wave1_6/FEEDBACK_PACKAGE_DECISION.md`, package/tests/front end | Signed decision + import/API/schema compatibility test; unapproved deletion remains a release blocker |

**Exit criteria:** saga passes at-least-once delivery and crash recovery with logically once effects; Feedback truth follows publication truth.

### Batch D — financial, CSV, provenance and query accuracy (P0/P1, 9 tasks)

| ID | Action | Principal files | Acceptance gate |
|---|---|---|---|
| D01 | Keep AAUM SUM/AVG/RANK/period aggregation blocked until **human steward receipt** declares grain, additivity, duplicate policy, units, period and source authority | `financial_policy_service.py`, policy registry | Explicit denial without real signed stewardship decision |
| D02 | Fix top-AMC planner contract: `COUNT` ranking must use count metric/unit and count order, not `aaum_crore`, `total_aum_cr` aliases or INR_CRORE; requested AUM rank blocked | `backend/app/tabular/planner.py` | Answer label and sort actually match executed SQL; no silent metric substitution |
| D03 | End-to-end Decimal aggregate implementation after approved additivity policy (not post-hoc formatting SQL float values) | planner/executor/repository | Exact sums 0.1+0.2, duplicates, rounding, large totals match independent Decimal gold |
| D04 | Recompute SHA-256 from original bytes and each actual chunk; reconcile row counts, schema, row hashes, chunk metadata and provenance | `financial_policy_service.py`, ingestion pipeline | Single byte/row mutation => QUARANTINE not ACTIVE |
| D05 | Enforce canonical AMC/scheme/plan identities and version/time grain; preserve NAV-per-unit + exact NAV date/plan pairing | tabular schema/planner/loader | Homonyms, multiple plan options, as-of cases fail ambiguously rather than guess |
| D06 | Persist immutable dataset versions with hashes, validation issues, quarantine and human-reviewed activation | tabular loader + DB migration | Partial import cannot become active; prior version remains queryable |
| D07 | Remove `source_row_ids[:50]` silent truncation as total provenance: store full row-contributor ledger/hash, return bounded preview plus signed cursor/reference | `backend/app/tabular/executor.py` | >50-row aggregate independently reconstructs complete contributor list |
| D08 | Protect numeric intents against fallback to Pandas/LLM/vector approximations; return structured unavailable/ambiguous/no-match errors | planner, executor, `fast_path_interceptor.py`, routes | Outage, stale source or unapproved metric cannot generate confident numeric answer |
| D09 | Independent gold: at least 30 numeric cases + 15 NAV/identity/date/period controls; PDF/TXT unaffected controls and regression snapshots | `backend/tests/`, fixture manifests | Report exact expected vs actual, row set hashes and provenance at pinned SHA |

**Business decision gate:** No agent may invent AAUM policy sign-off. Technical blocks may proceed in parallel while aggregate correctness remains blocked.

### Batch E — independent verification, operations and release (P0, 8 tasks)

| ID | Action | Principal files | Acceptance gate |
|---|---|---|---|
| E01 | Replace fault-injection tautologies and mock-only assertions with real DB, disposable Neo4j, temporary FAISS generation and worker tests | `test_wave15_publication_fault_injection.py`, new integration tests | Deliberately broken implementation causes red test |
| E02 | Rehearse Alembic `upgrade head`, `downgrade` where supported and `upgrade` on disposable DB; verify migration 009 and new tables, schema metadata, constraints, indexes, non-lossy samples | migrations + `backend/scripts/migrate_rehearse.py` | Captured exit codes, test DB identity, schema fingerprints, output artifacts |
| E03 | Complete CI workflow: install actual dependencies for each job, parallel gate dependencies, artifact retention, test reports, scanner and vulnerabilities without echo fallbacks | GitHub workflow | Repeat run on `amc-dev` yields green only if tests truly pass |
| E04 | Implement event-derived audit+telemetry: latency, retries, DLQ, rollback, tenant-safe counts, queue lag, source verification, corpus generation; bounded cardinality | `operational_metrics_service.py`, worker, observability | Process restart doesn't erase audit; metrics match durable event counts |
| E05 | Check UI, REST `/query` / `/query/v2` / stream / chat / cache / fast path against single proof and authorization contract; negative controls | frontend + API routes | Same query on supported modes yields same authoritative result/citation |
| E06 | Restore/replace Feedback interface tests for classification, adjudication, diagnosis, repair linkage and issue lifecycle; check API/contracts/deployment manifests | Feedback package/module + backend/tests | No missing import/route; explicit deprecations fail predictably |
| E07 | Define executable SLO windows and canary runbook; do not declare PASS from echo. Canary only after preflight gates; rollback observed and evidenced | CI, runbook | Rehearsed rollback, observed metrics vs agreed thresholds |
| E08 | Formal independent release-gate ledger with SHA, all test counts (pass/fail/skip), migration SHA, data-version hash, stewardship receipts, security owner & reviewer | `remediation/wave1_7/` | Required gates SEC/REP/PUB/NUM/ING/E2E/OPS either PASS with links or BLOCK |

## 5. Specific source-level correction notes

### 5.1 Approval endpoint must not return success for an unawaited task

Current `approve_correction` is synchronous and has a branch that can call `asyncio.create_task(patch_layer.approve_patch(...))`; a scheduled task is truthy independently of success. The other branch writes `patch.status`, `approved`, Redis and local memory without CAS. Batch approval duplicates the logic again. Replace with `async def` and a single `ApprovalService.approve(...)` that **awaits persistence**, validates expected state/revision, writes immutable review evidence, and returns the committed state. Reject stale revisions; no TTL-to-permanent or serving activation on mere approval.

Also reconcile `review_repair_proposal`, which sets `proposal.status='approved'` directly. Proposal approval and patch approval must be mapped to one deliberate lifecycle, not independently interpreted as publication permission.

### 5.2 Fix the currently broken direct-promotion call contract

On the reviewed SHA, `governance.py` calls `await patch_layer.get_patch(patch_id)` twice, while `backend/app/graph/correction_patch_layer.py` only defines synchronous `get_patch_by_id(patch_id)` (there is no `get_patch` on that class). The same governance route references `_execute_vector_activation(patch_id)` but no such function is defined in the reviewed `governance.py`. These are concrete API/NameError risks, not just missing tests. Replace them with one validated and awaited publication service; assert live route behavior with proper dependencies, real effects, and fail-closed failures.

### 5.2 Don't mark graph/vector completion from an in-memory operation list

Graph/vector services must maintain a durable per-intent effect journal and immutable pre/post snapshots. The source reviewer observed `_staging`/`_preimages` dictionaries in both services; `apply_staged()` removes staged entries, so a later rollback that scans only staging may find nothing. Actual after-crash recovery cannot rely on the original process's memory.

Even for graph helpers that call real `upsert_entities`/`upsert_relations`, **delete/readback/driver compatibility and CAS must be tested**. An unimplemented or no-op delete cannot produce a verified receipt. Verify against disposable Neo4j instead of accepting a mocked method call.

### 5.3 Fake/weak Feedback verification must be removed, not merely changed

`FeedbackOutcomeService._is_publication_published` attempts to instantiate services with required `graph_store`/`vector_store` constructor parameters and checks hypothetical staging counts; it does not query `publication_intents`. `_is_verification_complete` similarly checks staging, not `publication_receipts`. Both may simply fail closed due to constructor errors, but that is not working positive-path semantics. Use a DB repository and external proof validation. Then persist issue-status mutations in the real Feedback issue system, not just a local `_issue_links` dict.

### 5.4 Actual CI failure and remediation

- **Observed:** `pip install gitleaks` fails: no package found; not a secrets finding.
- **Do:** Use the vendor's maintained release binary or approved GitHub Action, pin version/commit and checksum, and execute a scan that returns a meaningful exit status.
- **Next:** `pip-audit` is invoked without a preceding installation in the initial job; install and pin it or use a verified action.
- **Next:** `pytest tests/regression/ -v --deterministic` and `pytest tests/fault_injection/` refer to absent directories in the reviewed tree. Use committed actual suites or add these directories; ensure jobs install their dependencies.
- **Next:** the workflow reports canary/SLO/release PASS with shell `echo`s. Replace with operational checks and artifacts; an `if: main`-only release job may remain, but branch quality checks must run on `amc-dev`.

### 5.5 Top-AMC semantic regression is a release blocker

The current `create_top_amcs_plan()` SQL selects `COUNT(DISTINCT scheme_display_name)` and `COUNT(*)` and orders by plan count, but returns a `QueryPlan` labeled `metric_id='aaum_crore'` and `unit='INR_CRORE'`; the `sort_by` code still maps to AAUM result aliases not present in SQL. **Never represent a count as currency or call a plan-count ranking “top by AAUM”.** Split into a genuine count query (COUNT, correct unit/metadata) and an AAUM ranking that fails closed until steward-reviewed aggregation is implemented.

## 6. Mandatory adversarial and integration test matrix

Treat every case as a test that asserts both **API behavior** and **durable state**. Report exact pass/fail/skip for the pinned SHA.

| Case | Scenario | Non-negotiable assertion |
|---|---|---|
| T01 | Approver is proposer | 403; no status/write/receipt |
| T02 | Proposer metadata absent | denied or explicit separate approved exception; never implied four eyes |
| T03 | Concurrent approvals of same revision | exactly one committed approval transition |
| T04 | Approval route returns before write completes | no 200; commit awaited |
| T05 | Stale proposal version | 409; no publication |
| T06 | Pending patch via fast-path | not cited or injected |
| T07 | Approved but not ACTIVE patch via chat | not served |
| T08 | Verified but not ACTIVE via streaming | not served |
| T09 | Forged receipt or wrong tenant | blocked |
| T10 | Missing graph driver | no ACTIVE/receipt |
| T11 | Graph no-op mutation | readback mismatch -> fail |
| T12 | Graph write succeeds but receipt DB commit fails | restart reconciliation, no duplicate mutation |
| T13 | Graph rollback with changed postimage | conflict, no overwrite |
| T14 | Unknown graph property injection | rejected before Cypher |
| T15 | Exact chunk ID vs similar-content document | correct preimage only |
| T16 | Vector generation build fails | old serving index retained |
| T17 | FAISS checksum corrupted | no activation |
| T18 | Index activation crash | recover old or new generation unambiguously |
| T19 | Vector rollback after process restart | old generation restored |
| T20 | Empty vector reindex target | no phantom verified success |
| T21 | Two workers claim one event | one logical effect |
| T22 | Duplicate delivered after completed event | no second effect |
| T23 | Lease expires during external call | fence stale worker |
| T24 | Worker crashes after external write before receipt | resume by exact readback |
| T25 | Exhausted retries | durable DLQ and alert |
| T26 | Unknown event type | not completed |
| T27 | Unpublished Feedback intent | issue cannot resolve |
| T28 | Receipt not matching intent | issue cannot resolve |
| T29 | Rollback after issue resolved | issue reopened/review required |
| T30 | Feedback service restart | causal linkage recovered |
| T31 | Unapproved AAUM SUM/RANK | METRIC_POLICY_BLOCKED; no numeric fallback |
| T32 | Top-AMC count vs AAUM query | truthful metric/unit/order, or blocked |
| T33 | Decimal 0.1 + 0.2, many rows | exact reference total |
| T34 | NAV and date from differing rows | reject mixed observations |
| T35 | Duplicate plan options | no double counting |
| T36 | Mutate original source byte | SHA mismatch/quarantine |
| T37 | Invalid chunk hash/row count | no dataset activation |
| T38 | >50 source rows in aggregate | complete evidence ledger retrievable |
| T39 | Numeric repository down | structured unavailable; no LLM answer |
| T40 | PDF/TXT reference question | unaffected behavior |
| T41 | Migration 009 upgrade | exact tables/constraints/indexes exist |
| T42 | Database downgrade/re-upgrade on disposable copy | no unintended destructive loss |
| T43 | CI seeded fake secret fixture | secret scanner actually fails fixture |
| T44 | CI missing test directory | explicit failure, never green |
| T45 | Missing Feedback import/route | surfaced, no silent compatibility success |
| T46 | Canary bad latency/error rate | executable gate fails; rollback evidence exists |
| T47 | Direct promotion calls nonexistent patch-layer method | real route does not raise AttributeError; verified state enforced |
| T48 | Direct promotion calls absent vector activation function | no NameError; tested vector publication or explicit not-available denial |

**Invalid assertion patterns:** `assert True`, `assert result is False or result is True`, hard-coded state assignment then checking itself, screenshots of test code, or “mock object method called” without verifying real readback. Convert each into a test that fails for the original defect.

## 7. Required deliverables in the repository

Create `remediation/wave1_7/` and maintain the following files from the agent's actual implementation, not fabricated status:

```text
remediation/wave1_7/
  00_SOURCE_BASELINE.md              # exact refs/commit/diff/decisions
  01_FINDINGS_AND_ROOT_CAUSES.md     # W17 ids, evidence, impact, root cause
  02_TASK_MATRIX.csv                 # task/owner/status/SHA/tests/gate
  03_STATE_AND_EFFECT_CONTRACT.md    # transitions, schema, events, idempotency
  04_SCHEMA_MIGRATION_EVIDENCE.md    # disposable DB, upgrade/downgrade output
  05_CI_RUNS.md                      # actual run IDs, jobs, fail/skip counts
  06_TEST_RESULTS.md                 # commands + full stdout/exit codes
  07_FAULT_INJECTION_REPORT.md       # actual DB/graph/FAISS/worker outcomes
  08_DATA_PROVENANCE_GOLD.md         # gold dataset and metric-grain decisions
  09_FEEDBACK_COMPAT_DECISION.md     # signed owner decision or BLOCK
  10_RELEASE_GATE.md                 # SEC/REP/PUB/NUM/ING/E2E/OPS
  11_ROLLBACK_RUNBOOK.md             # operator steps, drill results, abort
  artifacts/                         # JUnit XML, logs, hashes, manifest diffs
```

Every task in `02_TASK_MATRIX.csv` must use exactly one status from **NOT_STARTED, IN_PROGRESS, IMPLEMENTED_UNVERIFIED, VERIFIED, BLOCKED, NOT_APPLICABLE**. `VERIFIED` requires a link to executable test evidence. A blocked task cannot be reported as completed for program-percentage calculations.

## 8. Bulk execution order and stop conditions

| Work unit | Bundle | Dependency | Completion criterion |
|---|---|---|---|
| **Wave 1.7–B0** | A01–A04 + A09 + E03 | Immediately | CI workflow actually executes on `amc-dev`; scanner installation fixed; no false PASS |
| **Wave 1.7–B1** | A05–A08 + A10 + C06 + E01 | Parallel to B0 (separate branch) | Approval/serving state invariant proven in real route tests |
| **Wave 1.7–B2** | B01–B09 | B1 contract | Persistent graph/vector staging, verified readback and rollback |
| **Wave 1.7–B3** | C01–C08 + E04 | B2 interfaces | One authoritative idempotent worker and Feedback causal state |
| **Wave 1.7–B4** | D01–D09 + E05 | Independent policy work starts earlier | No unsupported financial answer; full evidence ledger |
| **Wave 1.7–B5** | C09 + E02 + E06–E08 | All preceding gates | Explicit Feedback disposition and signed release decision |

**Concurrency note:** The branch may be changed by another agent. At the beginning of each batch, re-fetch `amc-dev` HEAD and compare with this pinned SHA. Work in a dedicated feature branch and refuse non-fast-forward overwrites. No destructive database change or production feature enablement without independently reviewed migration and rollback plans.

**Recommended scope for the next local Codex run:** B0 + B1 + the persistence contract/migrations from B2 as one substantial work cycle; no need to wait for the Feedback owner decision to repair unrelated CI/lifecycle bugs. Continue B2/B3 after their dependencies are verifiably green. Do not declare B2 implemented if it has only data classes and interfaces.

## 9. Test execution guidance (agent must inspect actual project layout)

```bash
# All commands are examples to adjust after verifying package layout and dependencies.
git fetch origin
git rev-parse origin/amc-dev
# Work on a fresh local branch at a pinned SHA, not the remote branch directly.

cd backend
python -m compileall -q app
python -m pytest -q tests/test_wave14_p0_containment.py
python -m pytest -q tests/test_wave15_publication_fault_injection.py
python -m pytest -q tests/test_tabular_queries.py
# Add and run new Wave 1.7 integration cases against disposable stores.
# Run alembic upgrade/downgrade/re-upgrade ONLY on a verified disposable DB.
```

CI must install package requirements in every job before using pytest; a clean `py_compile` does **not** prove importability. For a real scanner, use the documented official binary/action with a fixed version or full commit SHA and proper exit status. Ensure no sensitive values are placed in committed test fixtures or artifacts.

## 10. Required output from the agent after each batch

Provide at most 10–15 lines of executive summary followed by machine-checkable links:

1. Reviewed base SHA, new HEAD SHA, branch, diff and list of commits.
2. Actual files changed and migration IDs.
3. Tasks VERIFIED vs IMPLEMENTED_UNVERIFIED vs BLOCKED (do not blend).
4. Commands executed, `exit_code`, `passed/failed/skipped`, CI run URL, test artifacts.
5. Behavior before/after with one negative test per original P0 defect.
6. Any runtime environment constraint or pending human decision.
7. Updated release verdict **BLOCK** unless all gates have independent evidence.

## 11. Ready-to-paste local Codex execution prompt

> You are the principal engineer for `nusummit-spg/amc-context-engineering-poc`. Work on `amc-dev` but create a dedicated review branch first. Read the attached `AMC_Wave1_7_Next_Implementation_Agent_Handoff_2026-11-06.md` in full. Compare repository HEAD to pinned baseline `bea1fbd4e52fdc93fa064c47ed1377347d3852f7` and reconcile any newer commits before editing.
>
> Execute Wave 1.7 B0 and B1 as a bulk implementation: repair the actual CI failure (Gitleaks is not pip-installable; previous run 42202423962 failed at `Scan for secrets`), remove fictitious PASS paths, restore test discovery/import checks, unify and await approval transitions with persisted four-eyes evidence, fix nonexistent `get_patch()`/`_execute_vector_activation()` direct-promotion calls, remove direct Redis/manual approval shortcuts, and make every serving path require ACTIVE+verified durable publication. Include the B2 schema design and migration only where safe and directly testable. Do not rebuild completed features without reason.
>
> Then implement B2/B3 as bounded feature commits: durable graph/vector staged effects, exact-ID preimages, verified Neo4j/FAISS mutation and rollback, single outbox worker, idempotency/leases/recovery, durable publication receipts, and Feedback resolution only on matched active receipts. Do not report an external operation successful when you only appended a log, created a receipt, or populated an in-memory dictionary.
>
> Begin D financial containment in parallel: keep unapproved AAUM aggregation blocked; fix the top-AMC query/metric mismatch; implement real source-byte manifest verification and complete aggregate provenance. Do not invent human steward signoff or overwrite production data. The Feedback-loop deletion remains BLOCKED pending product-owner choice; prepare restoration/compatibility analysis but do not silently deprecate it.
>
> Replace tautological/mocked fault-injection tests with actual negative and crash/restart tests using disposable SQL, Neo4j and FAISS fixtures. Rehearse migrations in disposable environments. Create all `remediation/wave1_7/` evidence deliverables. Run tests and CI where access permits. Return succinct results, real test pass/fail/skip counts, code+commit hashes, run URLs, remaining blockers, and a BLOCK/PASS release gate matrix. **Never claim verified/ready/COMPLETE without executed evidence.**

## 12. Independent final review checklist

- [ ] Actual `amc-dev` CI run succeeds; downstream jobs are no longer skipped by scanner installation.
- [ ] No fake `echo RELEASE APPROVED` or no-op canary/SLO claims.
- [ ] No unawaited approval tasks or direct Redis lifecycle bypass.
- [ ] Direct `/promote/{patch_id}` route has no nonexistent method/function references and passes an actual API integration test.
- [ ] Proposal review/patch review/batch approval share one authoritative four-eyes contract.
- [ ] No approved-only retrieval path; all serve `ACTIVE + valid receipt`.
- [ ] Source version, tenant, reviewer identity, and lease fencing bound to each intent/effect.
- [ ] Durable vector staging/preimage survives restart; exact-ID/hash verified.
- [ ] Graph mutation and rollback execute and read back on disposable Neo4j.
- [ ] Outbox retry and duplicate handling are idempotent and observable.
- [ ] Feedback resolution/reopening uses real persisted evidence.
- [ ] Source bytes/chunk bytes are cryptographically verified; incomplete lineage blocked.
- [ ] AAUM policy remains blocked until a genuine owner/steward decision.
- [ ] Query result metrics, units and sort order match real SQL.
- [ ] >50-row provenance remains completely reconstructable.
- [ ] Deleted Feedback package has approved disposition and parity evidence.
- [ ] Migration 009 and subsequent migrations are exercised against disposable DB.
- [ ] Real pass/fail/skip + logs and review SHA captured in release ledger.

---

**Final architectural recommendation:** Stop at integrity and operational assurance. The immediate value is removing cross-store ambiguity, false-success claims, and patch/financial answer contamination. Move to new features **only after** the end-to-end publication path can be deliberately broken in a test and correctly recover without corrupting answers.
