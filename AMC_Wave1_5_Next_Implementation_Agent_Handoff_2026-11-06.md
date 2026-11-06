# AMC Context Engineering — Wave 1.5 CTO Re-Audit & Agent Implementation Handoff

**Prepared:** 6 November 2026 (Asia/Kolkata)  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Branch reviewed:** `amc-dev`  
**PINNED reviewed HEAD:** `17fe11268f240359198f03bff1a1e9f9f2b8a3db`  
**Comparison baseline (Wave 1.4):** `73cb485af2f2057f8ee181c7ad9d63130e43b8d0`  
**Delta:** 10 commits ahead, 58 changed files; the complete `packages/amc-feedback-loop` package was deleted.  
**Audit method:** Read GitHub branch, compare, code and existing remediation reports. This is a **source-level audit only**. Reviewer did **not** run repository tests, apply migrations, deploy services, or conduct a penetration test. GitHub reported **zero branch Actions runs and zero commit status checks** at this HEAD.  
**Overall release decision:** **BLOCK** for production until independent acceptance gates are passed.

> **Agent instruction:** This is a practical, implementable handoff. Read it in full, compare the current HEAD to the pinned SHA, implement the prioritized code changes and real automated tests, and deliver evidence. Do **not** merely update completion summaries. Retain working features; do not delete or silently replace a system without a verified migration. Do not invent steward approvals, real reindex receipts, or passing test results.

## 0. Source links and authoritative reading order

- [Reviewed branch](https://github.com/nusummit-spg/amc-context-engineering-poc/tree/amc-dev)
- [Pinned commit](https://github.com/nusummit-spg/amc-context-engineering-poc/commit/17fe11268f240359198f03bff1a1e9f9f2b8a3db)
- [Wave 1.4 handoff](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/17fe11268f240359198f03bff1a1e9f9f2b8a3db/AMC_Wave1_4_Next_Implementation_Agent_Handoff_2026-11-05.md)
- [Wave 1.4 implementation status](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/17fe11268f240359198f03bff1a1e9f9f2b8a3db/remediation/wave1_4/STATUS.md)
- [Wave 1.4 release gate](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/17fe11268f240359198f03bff1a1e9f9f2b8a3db/remediation/wave1_4/RELEASE_GATE.md)
- [Original target architecture](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/17fe11268f240359198f03bff1a1e9f9f2b8a3db/docs/AMC_Tasks_3_11_26/AMC_Specs/02_TARGET_ARCHITECTURE_AND_CONTRACTS.md)
- [Financial correctness specification](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/17fe11268f240359198f03bff1a1e9f9f2b8a3db/docs/AMC_Tasks_3_11_26/AMC_Specs/03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md)
- [Feedback/Repair lifecycle specification](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/17fe11268f240359198f03bff1a1e9f9f2b8a3db/docs/AMC_Tasks_3_11_26/AMC_Specs/04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md)
- [Security and assurance specification](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/17fe11268f240359198f03bff1a1e9f9f2b8a3db/docs/AMC_Tasks_3_11_26/AMC_Specs/05_ASSURANCE_SECURITY_RELEASE_GATES.md)
- [Previously defined tasks and goals](https://github.com/nusummit-spg/amc-context-engineering-poc/blob/17fe11268f240359198f03bff1a1e9f9f2b8a3db/docs/AMC_Tasks_3_11_26/AMC_Specs/06_GOALS_AND_TASKS.md)

**Read order for Codex:** this document → Wave 1.4 status/release gate → original architecture and Repair spec → financial spec → affected code → existing tests → dependencies, migrations and frontend consumers.

---

## 1. What changed, and what should not be repeated

The new 10 commits made useful progress:

1. **Invitation redemption:** `backend/app/api/routes/auth.py` now hashes incoming invitation tokens, queries `token_hash`, and attempts row locking and rate limiting. This addresses the earlier plaintext-column mismatch. It still needs concurrency tests on the actual database engine; SQLite does not enforce `FOR UPDATE` like PostgreSQL.
2. **Async promotion route:** `backend/app/api/routes/governance.py::promote_approved_proposals()` now awaits `PromotionService.apply_approved_proposals()`.
3. **Fail-closed scaffolding:** unimplemented outbox and rollback handlers now raise instead of claiming success; several Admin operations report unavailable rather than fabricate results.
4. **Repair lifecycle:** `backend/app/graph/correction_patch_layer.py` now includes a typed state machine (`PENDING → APPROVED → STAGED → VERIFIED → ACTIVE`) and receipt/timestamp fields.
5. **Serving eligibility helper:** `backend/app/retrieval/fast_path_interceptor.py` now defines `_is_serving_eligible_patch()`.
6. **New regression file:** `backend/tests/test_wave14_p0_containment.py` was committed. Documentation claims 18 passing local tests; these were **not independently reproduced**.

**Do not rebuild these features from scratch.** Integrate and test them correctly. A fail-closed `NotImplementedError` is an appropriate containment step, **not** completion of the actual feature.

### Evidence confidence levels

- **Confirmed by source:** file added/removed, declared method, evident control flow, direct fallback, explicit stub, schema constraint, hardcoded SQL.
- **Not yet established:** a full route working through live auth, concurrent invitation safety, actual FAISS generation, actual Neo4j rollback, feedback microservice compatibility, full regression passing, production ingress posture.
- **Reported by remediation docs only:** 18 local tests passed. Some test bodies are non-operative and therefore not sufficient evidence of their stated guarantees.

---

## 2. Critical source-level findings and next actions

| ID | Priority | Observed evidence at pinned HEAD | Required disposition |
|---|---|---|---|
| **REG-01** | **P0** | Every file under `packages/amc-feedback-loop/` was removed in this update, including services, adapters, API, tests and `pyproject.toml`; only `amc-repair-engine` remains under `packages/`. | Audit all references, deployment manifests, entrypoints and frontend contracts; restore package if accidental, or provide an explicit, fully tested replacement/migration if deliberate. **No silent deletion.** |
| **REP-01** | **P0** | `fast_path_interceptor.py::intercept` still selects patches using `approved` + confidence, without calling the new `_is_serving_eligible_patch()`; `_fetch_active_patches` drops `status`/receipt. | Enforce verified ACTIVE policy before constructing any direct answer; preserve required metadata end-to-end. |
| **REP-02** | **P0** | `app.graph.correction_patch_layer.apply_patches_to_context()` and `get_active_patches()` filter on `approved`, not verified ACTIVE; `promote_to_permanent()` directly sets `approved=True`. | Remove legacy serving/promotion bypass. Separate human approval from verified publication and activation. |
| **REP-03** | **P0** | `repair_integration.py` still invokes `ingest_synthetic_patch_chunk()` when a repair patch is created (before approval). | Isolate pending data from serving indexes, ideally avoid insertion until publication. Verify actual FAISS retrieval negative cases. |
| **REP-04** | **P0** | `governance.py::review_repair_proposal()` writes `status='reviewed_approved'` but `repair_proposals.py` permits only pending/approved/rejected/applied/rolled_back. | Define separate review fields/records or formally migrate status enum; no undocumented value outside DB constraint; preserve four-eyes. |
| **REP-05** | **P0** | `CorrectionPatchLayer` defines `approve_patch()` twice, earlier synchronously as alias to canonical promotion, later asynchronously as state transition; old callers may be incompatible. | Remove duplicate/ambiguous signatures; route every caller through single approved transition contract and test in real FastAPI path. |
| **PUB-01** | **P0** | `promotion_service._trigger_reindex()` now checks `orchestrator.indexer` but remains a stub: it creates `verified=True`, `status='completed'`, `source_hash='pending_verification'` without invoking a rebuild or active-index verification. | Real versioned index staging, checksum, query probes, atomic activation and verified receipt; otherwise fail closed. |
| **PUB-02** | **P0** | Outbox graph/state handlers raise `NotImplementedError`; `apply_approved_proposals()` also mutates Neo4j/FAISS inline after queueing an outbox event, creating dual-authority and retry ambiguity. | One authoritative outbox worker; no direct+queued duplicate execution; per-proposal SQL transaction and idempotent delivery. |
| **PUB-03** | **P0** | Graph/vector rollback operations now fail closed instead of restoring prior state; rollback is not operational. | Capture preimages and versioned index snapshots, implement verified, idempotent compensation. Keep automatic release blocked until recovery is tested. |
| **PUB-04** | **P0/P1** | Legacy `promote_to_permanent()` builds Cypher property names from `patch.attribute`; Neo4j write errors are logged and execution may still set approved. Graph mutation service accepts stored raw `mutation_cypher`; exact comparisons also use float epsilon. | Schema-allowlisted property updates, parameterized values, transactional read-back, exact domain-specific numeric comparison, and fail closed. |
| **SEC-01** | **P1** | Invitation redemption uses `with_for_update`; correctness on SQLite remains unproven. Invalid hashes are not located in DB, so per-token counter cannot guard unknown-token attempts. | Implement DB-supported atomic consume, IP/user rate limit, lockout/replay tests and consistent status. |
| **TST-01** | **P0** | `test_wave14_p0_containment.py` has `pass` placeholder tests, `assert True` meta-tests, and `except RuntimeError: pass` that could suppress test execution failures. | Replace with executable assertions through real routes, storage and controlled fake external integrations. Test behavior, not presence of methods. |
| **NUM-01** | **P0** | `tabular/planner.py` still uses `CAST(aaum_crore AS REAL)`, SUM/AVG and display-name grouping; `executor.py` does not independently reject unapproved metric plans. | Block unapproved financial aggregation, exact Decimal/scaled integers, canonical grain and reproducible gold results. |
| **ING-01** | **P0** | CSV loader's activation and manifest controls remain unchanged by this push; previous reconciliation/readiness questions remain open. | Validate manifest/versions, per-metric eligibility, source hashes, staging and signed activation. |
| **OPS-01** | **P0** | No `.github/workflows` was present in the reviewed tree and GitHub returned no branch Actions runs or head statuses. | Add and run real CI, dependency/migration/contract checks and rollback drills. |

### Special note about REG-01: unexpected Feedback package deletion

The diff contains deletion of the entire `packages/amc-feedback-loop` source tree, including `src/feedback_loop/{server,orchestrator,services,adapters,models,...}.py`, several SQLite/evidence adapters, and all package-specific tests. **Do not assume that `backend/app/feedback/` is a drop-in replacement.** The agent must report the exact commit that deleted the package, whether removal was intentional, and a path-by-path replacement map with evidence. If accidental, restore from the pre-deletion commit **in a dedicated reviewable commit** and rerun the cross-service tests. If intentional, secure explicit maintainer acceptance and demonstrate equivalent behavior and schema migrations; do not reconstruct a different package without source evidence.

**Also investigate changes to** `backend/app/auth/data/users.json` and `backend/config/users_rbac.json` **as a security-sensitive diff** (credential/identity changes). Never print, copy into test logs, or publish secrets. Report only sanitized findings, and rotate exposed credentials if discovered.

---

## 3. Proposed execution architecture and dependencies

The smallest safe bulk implementation is **five PRs/commits groups**, with a clear release boundary:

| Work package | Tasks | Priority | Dependency | Completion gate |
|---|---|---|---|---|
| **W1.5-R: Stop regression and close evidence gaps** | R01–R08 | P0 | Pinned baseline | Feedback dependency proof; no premature serving or invalid SQL status; real tests |
| **W1.5-P: One authoritative publication and rollback pipeline** | P01–P10 | P0 | R shared state/identity | Real, idempotent graph/vector publication, recovery and rollback |
| **W1.5-F: Financial truth and ingestion** | F01–F08 | P0 | Metric decision/isolated branch | No unapproved AAUM sum; exact math, reconciled data, independent gold |
| **W1.5-Q: Query/Feedback/UI parity** | Q01–Q06 | P1/P0 | R + P + F as relevant | Safe query/chat/stream/feedback path parity; preserved PDF/TXT |
| **W1.5-A: Independent assurance and release** | A01–A07 | P0 release | Previous packages | Green clean-clone CI, migration/recovery evidence, signed gate |

**Execution strategy:** The local agent may implement **R + P in one large coding session** but must produce separate reviewable commits/PRs. F can be developed simultaneously only behind a policy that refuses unapproved numeric aggregates. Do not promote to production until A gates are met.

### Stop conditions

1. No direct writes to live Neo4j, active FAISS, customer data, production Redis, or actual client accounts.
2. If business data-grain semantics or authority are uncertain, refuse the affected metric and record a steward decision request.
3. If a previously existing Feedback component was intentionally deleted, request product-owner determination before migration or irreversible removal; complete all non-destructive engineering work meanwhile.
4. No fallback to LLM, Pandas, or unreviewed vectors for typed numeric failures.
5. No fabricated `SUCCESS`, `VERIFIED`, `ACTIVE`, `APPLIED`, `ROLLED_BACK` or CI PASS.

---

## 4. Work package R — regression containment and contract convergence

### R01 — Resolve Feedback-loop package deletion and dependency fallout

**Inspect:** prior `packages/amc-feedback-loop/` tree, the 10-commit diff, `packages/`, backend service clients, test imports, Docker/compose files, CI and deployment manifests, frontend Feedback APIs.

**Implement:** Inventory imports/entrypoints, transport schemas, SQLite/evidence storage, model identifiers, FeedbackIssue lifecycle, adjudication/classification/diagnosis, feedback repair triggers, and external service endpoints. Either safely restore pre-existing package or implement an accepted compatibility migration. Keep preserved data and audit IDs. No alternative design without evidence.

**Tests:** clean import/startup, Feedback submit→classify→adjudicate→repair proposal→human approval→verified outcome; all previously covered Feedback API modes; schema migration and no data loss. Provide `FEEDBACK_PACKAGE_DECISION.md`.

### R02 — One canonical patch state and explicit persisted approval evidence

**Inspect:** `backend/app/graph/correction_patch_layer.py`, `packages/amc-repair-engine/src/amc_repair/{schemas,patch_layer,server}.py`, `backend/app/api/routes/governance.py`.

**Implement:** One shared typed domain contract or a tightly versioned adapter, persisted status `PENDING/APPROVED/STAGED/VERIFIED/ACTIVE/REJECTED/FAILED/ROLLED_BACK/SUPERSEDED`. Store proposer, reviewer, approving human, source/evidence version, approved field diff, scope, tenant, timestamps, immutable approval receipt and publication receipt. A human review is not equivalent to publication. Remove duplicate `approve_patch()` method definitions; avoid sync/async ambiguity. Make `APPROVED` non-serving; prevent direct JSON setting of ACTIVE. Version and migrate old records without converting them implicitly to ACTIVE.

**Tests:** illegal transition rejected; approval cannot be skipped; self-approval rejected; absent proposer/evidence cannot be silently treated as independent approval; optimistic concurrency prevents duplicate state advance; stored records survive Redis restart.

### R03 — Fix `reviewed_approved` database state mismatch

**Inspect:** `governance.py::review_repair_proposal`, `schemas/repair_proposals.py::ck_proposal_status`, existing Alembic revisions and frontend status contract.

**Implement:** Separate reviewer decision/status from authoritative promotion state (preferred), or add a properly migrated type-safe state with explicit transition semantics and every consumer updated. Do not directly set `RepairProposal.status='reviewed_approved'` under the existing check constraint. Keep approval and publication separate, persist reviewer identity and evidence. Ensure the promotion service receives only fully authorized/approved records.

**Tests:** SQLite/Postgres constraint semantics, normal approval persists, unauthorized/self approval fails, SQL rollback does not orphan approvals, legacy rows migrate, API responses correct.

### R04 — Eliminate old approval-based retrieval and answer bypass

**Inspect:** `fast_path_interceptor.py::{intercept,_fetch_active_patches,_is_serving_eligible_patch}`, `retrieval/orchestrator.py::_apply_correction_patches`, `graph/correction_patch_layer.py::{get_active_patches,apply_patches_to_context,get_correction}`.

**Implement:** One `is_serving_eligible(patch, tenant, active_dataset_version, active_corpus_version)` used by **every** path. Conditions: verified `ACTIVE`, authenticated tenant, immutable evidence/approved subject, matching active version, real published receipt/hash, not superseded/revoked, within authorized scope. Include `status`, `publication_receipt`, `verified_at`, versions and tenant in transport responses. Remove `approved && confidence > threshold` direct-answer eligibility; confidence is never authorization. The remote service, local engine, fast path, LLM-context overlay, query/chat/stream and caches must call the same eligibility function. No fallback to legacy `approved`-only logic.

**Tests:** confidence 1.0 pending → invisible; approved without receipt → invisible; ACTIVE stale version → invisible; ACTIVE wrong tenant → invisible; revoked/rolled-back patch → invisible; valid ACTIVE with verified source → correctly applied and cited.

### R05 — Separate pending correction evidence from serving vectors

**Inspect:** `backend/app/services/repair_integration.py::trigger_repair_engine` and `backend/app/vector/client.py::ingest_synthetic_patch_chunk`.

**Implement:** Do not insert pending repair claims into the normal serving index. Use isolated review store/shadow namespace that ordinary retrieval cannot read, or postpone vector indexing until verified activation. Remove/reconcile previously written provisional synthetic chunks with targeted safe migration, not a broad index delete. Delay answer cache invalidation until verified publication. Create audit per deletion/move.

**Tests:** raw vector search + retrieval result + generated answer across all modes never contains pending patch content; verify old leaked chunks are quarantined; no regression to legitimate source documents.

### R06 — Close direct canonical graph mutation and approval shortcuts

**Inspect:** `CorrectionPatchLayer.promote_to_permanent`, `governance.py::{approve_correction,promote_patch_direct,batch_approve_corrections}`, Repair microservice `server.py`, graph mutation service.

**Implement:** Approval endpoint only records approval; promotion endpoint invokes the unified publication workflow with independent actor/role validation. Delete/retire `promote_to_permanent()` as an operational bypass or adapt it to the exact state machine/worker. Validate `attribute` against a fixed safe schema/allowlist; use parameterized values, entity label/key allowlists; require actual write counts, committed readback and matching expected values. Never set `approved=True` when Neo4j is unavailable or mutation fails. Disable free-form stored Cypher execution unless explicitly trusted/validated and bounded by an approved mutation grammar.

**Tests:** missing driver, mismatched entity, invalid attribute, Cypher injection attempt, self-approval, no-op update, stale source value, cross-tenant and conflicting concurrent proposal all fail safely.

### R07 — Invitation, session and service identity reality checks

**Inspect:** `auth.py::accept_invitation`, `auth/invitation_tokens.py`, SQLite/Postgres config, `AuthService`, `amc_repair/auth.py`, service-to-service clients.

**Implement:** Test atomic single-use redemption in the actual supported DB (including SQLite if supported), not just the presence of `with_for_update`. Ensure per-IP/account throttling for unknown token attempts, generic errors, reliable counters, expiry/replay prevention and secret validation. Verify main app session tokens and Repair service tokens have a documented issuer/audience/subject/scope strategy and that rejected session tokens cannot be replayed as service tokens. Use scoped, short-lived service credentials; avoid service-wide tenant bypass without explicit permission.

**Tests:** simultaneous redemption (exactly one winner), used/expired/missing token, brute-force attempts, invalid/missing issuer and audience, wrong tenant, absent scope, no production default secret.

### R08 — Replace misleading regression tests with behavior tests

**Inspect:** `backend/tests/test_wave14_p0_containment.py`, `test_wave12_route_compatibility.py`, Wave 1.3 tests; `remediation/wave1_4/STATUS.md`.

**Implement:** Remove `pass`-only tests, unconditional `assert True`, tests that assert method existence instead of effects, broad `except RuntimeError: pass`, and fixture-only happy-path tests. Use `pytest-asyncio`, `TestClient/httpx`, a temporary SQL database, isolated cache, fake external service contracts and a disposable real Neo4j/FAISS integration job. Tests must assert resulting DB state, actual index content and HTTP response, not just mocked `db.add()` calls. Record observed pass/fail/skip counts; prohibit skipped P0 tests on release.

**Tests:** dedicated suites for `R02`–`R07`; run old and new tests. Update evidence docs only *after* green runs; otherwise mark BLOCKED.

**R exit gate:** Feedback compatibility proven, single authoritative approval state, all serving paths fail closed on pending, no fabricated test claims, no direct mutation bypass, DB/status contract consistent.

---

## 5. Work package P — real publication, recovery and rollback

### P01 — Define immutable publication intents and receipts

Create publication event/receipt schema keyed by proposal ID + approved revision + tenant + target entity + source version. Record previous value/index generation, authorized approver, expected new value, content hash, external transaction IDs, observed readback, activated version and audit timestamps. A receipt is not valid merely because a dict was produced; it must be based on externally observed state.

### P02 — Implement true vector staging

**Source:** `backend/app/services/promotion_service.py::_trigger_reindex`, FAISS/vector-store adapters, `schemas/reindex_jobs_table.py`.

Build a new isolated index generation from vetted documents/corrections using the project's real indexer. Compute source manifest hash, index checksum, expected documents/embedding dimensions, and controlled probe queries. Persist `RUNNING → VERIFIED` only if index exists, loads and probe results match. Atomically update active-generation pointer after authorization. `indexer is not None` alone is insufficient. Zero-document request must be a typed no-op with explicit policy, not `verified=True`. Retain previous generation for recovery.

### P03 — Implement exact graph postconditions and preimage capture

**Source:** `promotion_service.py::_execute_graph_mutation`, `schemas/graph_mutations_table.py`, graph adapter.

Before changing canonical facts, capture prior value, type, version and last-writer marker. Perform approved, parameterized, bounded mutation; check number of entities changed; after commit read back **the target attribute on the intended entity**. Compare financial numbers with Decimal/typed units and explicit precision policy (not float epsilon); compare nonnumeric values with normalized rules. Receipt must include before/after and immutable evidence. Block if no matching entity, wrong value, malformed command, stale version, or inability to verify.

### P04 — One authoritative outbox worker; no duplicate inline execution

**Source:** `promotion_service.py::apply_approved_proposals`, `outbox_processor.py::{process_pending_events,_execute_graph_mutation,_execute_vector_reindex,_execute_state_transition}`.

In one SQL transaction: create an authorized publication intent and outbox event; commit before external execution. Workers claim with durable leases/claim tokens and uniqueness constraints, then perform external writes exactly once logically through idempotent requests. Stop direct mutation inside `apply_approved_proposals` when an event is also enqueued. Implement currently not-implemented graph and state handlers with real transitions and receipts; never mark an event completed without the real side effect and verification. Unknown event type must be rejected, not silently skipped as success.

### P05 — Recovery for crashes, retries, duplicates and concurrency

Implement lease timeout, retry with capped exponential backoff, dead-letter/needs-review after maximum attempts, monotonic status, dedup key, version compare-and-set and idempotent replay. Fix the multi-proposal `db.rollback()` hazard where SQL rollback can erase records for earlier already-committed external graph mutations. Use one proposal/transactional boundary and reconcile partial external success. Provide operator repair runbook and reconciliation command. Test crash after external commit but before SQL ack and two parallel workers.

### P06 — Actual graph rollback

**Source:** `rollback_service.py::_rollback_graph_mutation`.

Use stored preimage and version checks; apply compensating mutation only if current value/version still matches the expected post-publication version. Read back the restored value and record evidence. On conflict, return `MANUAL_REVIEW_REQUIRED` without overwriting later legitimate changes. Never change proposal to `rolled_back` until restoration is verified. Provide dry-run/approval for irreversible cases.

### P07 — Actual vector rollback

**Source:** `rollback_service.py::_rollback_vector_reindex`.

Atomically reactivate previous validated index generation, verify active pointer/checksum/probes, invalidate affected caches, and preserve displaced generation for analysis. Ensure a fallback response cannot continue using now-revoked chunks. If the original generation no longer exists, BLOCK and require repair; do not claim rollback.

### P08 — Cohesive Feedback outcome semantics

**Source:** `backend/app/services/repair_integration.py`, `backend/app/feedback`, restored/replaced Feedback-loop package.

Do not mark a FeedbackIssue RESOLVED solely because a proposal exists, was reviewed, or was approved. Resolve after verified ACTIVE publication and post-publication answer regression passing. Record causality links (`feedback_issue → evidence → proposal → approval → publication → verification → outcome`). Rollback reopens/flags dependent issues and invalidates stale customer-facing evidence as required.

### P09 — Operational metrics, cost and observability

Record success/failure separately for intent created, approval, indexed/staged, externally applied, readback verified, activated, rolled back, replayed and dead-lettered. Add correlation IDs, tenant-safe trace attributes, latency, index size, token/embedding cost, retry distribution and SLO/error budget. Do not equate queued intents with completed publications. Avoid user IDs or sensitive evidence in Prometheus label cardinality.

### P10 — End-to-end publication fault-injection

Disposable Neo4j, isolated FAISS, Redis + temporary SQL database (or justified supported fakes plus at least one real integration job). Assert graph outage, wrong readback, no-op mutation, vector index unavailable, corrupted checksum, worker crash after write, duplicate delivery, two workers, commit conflict, rollback conflict and service restart. Ensure no phantom `ACTIVE/APPLIED/ROLLED_BACK`; prior valid version continues serving.

**P exit gate:** Full verified graph+vector activation and rollback work in a clean, isolated environment; every transition has persisted evidence; a P0 failure cannot be confused for success.

---

## 6. Work package F — financial correctness and dataset governance (parallel implementation allowed behind refusal gate)

> **Business-decision hold:** AAUM additivity/grain, `Closure_Date` semantics, cross-quarter aggregation policy, scheme/option identity, and approved source hierarchy require explicit AMC data-steward approval. A missing decision MUST lead to `METRIC_POLICY_BLOCKED`/`AMBIGUOUS_QUERY`, not a guessed policy or numeric answer.

### F01 — Reject unapproved metric operations in the executor

**Source:** `backend/app/tabular/{contracts,planner,executor,metric_registry}.py` (confirm actual registry path), `backend/app/retrieval/fast_path_interceptor.py`.

Validate metric ID, permitted aggregation, dimensions, grain, period and steward approval at **execution time**, not just planner. No raw arbitrary SQL `compiled_sql` without typed template/allowlist. For `PENDING_APPROVAL` AAUM, block SUM/AVG/rank/market totals including dataset summary, category breakdown, distribution and legacy fast paths. Add typed error `METRIC_POLICY_BLOCKED` with no computed number.

### F02 — Exact numeric arithmetic

Replace SQLite REAL and Python float operations with decimal-text → Decimal or scaled integer in a controlled, deterministic aggregation. Define precision, currency/units, no unsafe rounding and numeric parsing. Full independent reconciliation for sums, ranking ties, negative/zero/null values and extreme magnitudes.

### F03 — Canonical AMC/scheme/plan/option identity

Never group by display name alone. Use stable AMC ID + verified scheme ID + plan/option ID + observation period. Detect aliases/collisions, repeated observations and duplicate source chunks; quarantine ambiguous identity. Distinguish fund-level vs scheme-level quantities.

### F04 — NAV observation pairing and as-of semantics

Select NAV, corresponding NAV date, plan/option and row ID from **the same observation**. Reject hidden defaults for NAV date, quarter, period or plan when ambiguous. Handle missing/late data and business-calendar `as-of` rules only if approved. Add independent same-row tests.

### F05 — Manifest validation, field validity and quarantine

**Source:** `backend/app/tabular/csv_excel_loader.py`, repository, ingestion scripts and manifests. Verify actual source/chunk hashes, row counts, lineage, duplicate chunks, encoding and malformed records; separate NAV validity from AAUM validity, rather than quarantining one because the other field is invalid. No hardcoded fallbacks presented as proof of ingestion correctness.

### F06 — Stage, approve and activate immutable dataset versions

Implement `DISCOVERED → STAGED → RECONCILED → REVIEWED → ACTIVE/QUARANTINED` with signed approvals and pointers. Active versions must survive clean checkout and restart; activation is atomic; failed migration or reconciliation keeps prior version active. Never auto-activate by mere ingestion completion.

### F07 — Complete aggregate provenance / independent gold

For each output, persist contributor observation IDs/source row IDs, version, filters, calculation rules, source hash and deterministic result hash. Use independently computed gold cases, including previously wrong CSV questions. Document 30+ CSV bad questions and PDF/TXT control corpus. Validate answer and provenance from source-of-truth files, not from the production SQL itself.

### F08 — Legacy and generative numeric fail-closed isolation

Remove/bypass legacy Pandas aggregation and LLM numeric synthesis when typed source is unavailable/blocked/ambiguous. Integrate fast path, orchestration and streaming refusal behavior. Structural missing data is never answered using a plausible sum. Preserve valid PDF/TXT citations and explanatory nonnumeric content.

**F exit gate:** All unapproved AAUM aggregates refuse; approved calculations exactly reconcile; no cross-entity/grain grouping; deterministic evidence reproducible from a clean deployment.

---

## 7. Work package Q — query surfaces, Feedback and UI parity

### Q01 — Query and streaming parity

Same typed policy, dataset version, patch eligibility, approval state, provenance and refusal codes across `/query`, `/query/v2`, `/query/stream`, `/chat`, `/chat/stream`, follow-ups, RAG, fast path and cached paths. Derive actual mounted routes from FastAPI runtime and adjust list to real code.

### Q02 — Frontend/Admin operational contracts

Audit frontend `mf-context-engine/src/services/api.js` and restored admin routes. If operation cannot execute, return typed 501/503 and display unavailable state; never show fabricated counts/approved state. Test real ingestion task monitor, proposed-edge approval, audit tenant filter and cache invalidation. Restore real functionality by connecting genuine backing services, not placeholder arrays.

### Q03 — Feedback module service contract and outcome

Preserve submit/classify/triage/adjudicate/evidence/review/repair/activate/resolve semantics after package decision. Confirm error behavior and idempotency, audit and tenant scope. Run smoke tests with service unavailable and with mocked but contract-compliant restart.

### Q04 — Versioned citations and correction transparency

Every answer involving a correction should show the accurate source/evidence and active version. A withdrawn correction must not remain in chat follow-up memory or cached response. Reject generated citations not present in the source manifest.

### Q05 — PDF/TXT control regression

Re-run a frozen set of previously correct document queries and source citations. Don't regress cross-document retrieval, normal FAQs, latency or feedback submission while hardening CSV numeric routing.

### Q06 — Security, performance and accessibility checks

Authorizations across users/tenants, service scope, oversized requests, concurrency, PII-safe logs, UI states for blocked/ambiguous requests, p95 latency and memory impact of versioned indexes.

---

## 8. Work package A — assurance, migration and release management

### A01 — Clean checkout and dependency audit

Build from scratch on a clean clone, verify Python and JS dependencies, import all modules, validate metadata and versions, check package removal fallout, scan requirements and configuration. Run static search for deleted `feedback_loop` imports and duplicated approval functions. Preserve private source/credentials.

### A02 — Migration rehearsal

Run full Alembic upgrade **and downgrade only on disposable test DBs**, including pre-existing data and schema revisions 003–008. Verify constraints, invitation tokens, reindex/outbox tables, transition data and rollback records. Ensure PostgreSQL and SQLite behavior differences are characterized.

### A03 — CI workflow, branch protection and merge gates

Create `.github/workflows/amc-assurance.yml` (or standard repo equivalent) with lint/type/import, service/unit tests, integration gates, financial gold, route compatibility, frontend build, dependency/security scan and migration smoke. Require actual GitHub Actions checks on PR/push to protected target branches; do not mistake local output pasted into MD for CI evidence.

### A04 — Deterministic regression evidence

Store `command`, environment, head SHA, dependency versions, datetime, exit code, executed/passed/failed/skipped tests, hardware-independent fixture hashes and artifact pointers. Negative/adversarial test cases are mandatory for P0, not optional.

### A05 — Fault-injection and SLO window

Exercise graph/vector/DB/service outage, timeouts, stale index, stuck outbox, replay, duplicates, admission control and recovery. Observed UNKNOWN status must not be counted as available. Record fast/slow SLO windows and resource/cost limits.

### A06 — Canary/rollback runbook

Design safe staging canary with non-production corpus, explicit rollback to prior release/index/dataset pointer and operator sign-off. Verify actually recovered values, not only logs. Protect against traffic crossing tenant or privacy boundaries.

### A07 — Independent release decision

Publish evidence-based gate matrix: `COMP/SEC/REP/PUB/NUM/ING/E2E/OPS`, each PASS/BLOCK/REVIEW. Mark overall PASS **only** when all applicable gates have independent real execution evidence and a human release authority accepts residual risk. No auto-deploy based on document completion percentage.

---

## 9. Mandatory negative and integration test matrix

All tests below must be real, with assertions on externally observed state, not unconditional `assert True`, no `pass` test bodies, no catch-and-ignore `RuntimeError`.

| # | Scenario | Expected assertion |
|---|---|---|
| 01 | `packages/amc-feedback-loop` import/startup | Compatible replacement or restored service; no missing imports |
| 02 | Old Feedback end-to-end pipeline | Same issue IDs, evidence links and semantics |
| 03 | Financial feedback raises pending patch | Normal index unchanged, no premature cache publication |
| 04 | `PENDING` patch at 1.0 confidence | Never changes direct response/context/vector results |
| 05 | `APPROVED` patch lacking publication receipt | Never serves |
| 06 | `VERIFIED` patch not yet ACTIVE | Never serves |
| 07 | `ACTIVE` patch wrong tenant/version | Never serves |
| 08 | `ACTIVE` patch with authentic matched receipt | Correctly serves with source citation |
| 09 | Rollback or revocation | Patch disappears from stream/query/chat/cache |
| 10 | Legacy `promote_to_permanent` direct call | Cannot bypass independent approval or verified ACTIVE transition |
| 11 | Legacy `get_active_patches` with APPROVED-only patch | Must not return it |
| 12 | Main governance review approval | Real DB commit succeeds under allowed schema or is correctly rejected |
| 13 | Self-approval/missing proposer | Denied / explicitly needs review |
| 14 | Same-user multi-identity attempt | Cannot approve own change |
| 15 | Numeric property injection in Cypher | Invalid property rejected before mutation |
| 16 | Graph target absent/no-op | No APPLIED; diagnostic receipt |
| 17 | Wrong graph readback | No APPLIED; mismatch logged |
| 18 | Float near-equality for precision-sensitive metric | Fails exact Decimal check when values truly differ |
| 19 | No indexer | No verified reindex receipt |
| 20 | Available indexer but no rebuild | Still no verified receipt |
| 21 | Rebuild succeeds, probe or hash fails | No activation; prior generation remains active |
| 22 | Crash after graph commit before SQL ack | Idempotent recovery, no duplicate mutation |
| 23 | Two workers claim same outbox event | Exactly one logical external effect |
| 24 | Unknown outbox type | Rejected/dead-lettered; never completed |
| 25 | Graph rollback, exact previous value | Restored and read back before rolled-back status |
| 26 | Vector rollback | Restores previous index hash and pointer |
| 27 | Concurrent edit after publication | Rollback does not overwrite newer legitimate value |
| 28 | Invite token redeemed twice concurrently | Exactly one successful activation |
| 29 | Invalid token brute force | Rate limit verified on supported DB/ingress |
| 30 | Repair-service token no scopes/wrong tenant | 401/403, no side effect |
| 31 | Unauthorized AAUM SUM via planner | `METRIC_POLICY_BLOCKED` |
| 32 | Unauthorized AAUM SUM via raw compiled executor plan | `METRIC_POLICY_BLOCKED` |
| 33 | Category/dataset summary/legacy AUM aggregate | Blocked until steward decision |
| 34 | Decimal gold independent sum | Exact result and numeric evidence |
| 35 | NAV value/date/plan pairing | Same-row as-of correct, ambiguity refusal |
| 36 | Duplicate CSV chunks, corrupt manifest | Quarantine and no activation |
| 37 | Mixed valid NAV/invalid AAUM | NAV only available where valid |
| 38 | Typed numeric source unavailable | No generative/legacy numeric fallback |
| 39 | Query/chat/stream/follow-up parity | Same truth/authorization/version/refusal |
| 40 | PDF/TXT frozen control questions | Unchanged valid answers and citations |
| 41 | Admin endpoint unavailable | Typed 501/503, no fabricated operational success |
| 42 | Fresh clone + migrations + runtime startup | Clean reproducible pipeline |
| 43 | CI actually runs P0 suites and has status checks | GitHub evidence linked to new SHA |
| 44 | Rollback runbook on disposable staging | Actual previous state restored and verified |

### Suggested actual commands (adjust to repository conventions)

```bash
# From repo root: prepare clean virtual environments per README.
python -m compileall -q backend/app
python -m compileall -q packages/amc-repair-engine/src

# From backend/ after installing its requirements:
python -m pytest -q tests/test_wave14_p0_containment.py
python -m pytest -q tests/test_wave13_graph_verification.py tests/test_wave13_batch_b_complete.py
python -m pytest -q tests/test_wave12_route_compatibility.py
python -m pytest -q tests/test_tabular_queries.py tests/test_wave0_verification.py
python -m pytest -q tests/test_e2e_user_journey_feedback_repair.py tests/test_repair_linkage.py

# From packages/amc-repair-engine/ after installing that package:
python -m pytest -q tests/test_wave13_auth_hardening.py tests/test_wave13_vector_isolation.py
python -m pytest -q tests/test_repair_service_auth.py

# Only after creating Wave 1.5 test suites, execute actual new paths:
python -m pytest -q tests/test_wave15_regression_and_governance.py
python -m pytest -q tests/test_wave15_publication_recovery.py
python -m pytest -q tests/test_wave15_financial_gold.py
python -m pytest -q tests/test_wave15_query_parity.py
```

**Disclaimer:** These commands are instructions, not evidence of execution. Wave 1.5 test files are proposed outputs and must actually be created by the agent. Use appropriate working directories and dependencies. Do not conceal import failures or skip markers.

---

## 10. Required evidence deliverables (commit under `remediation/wave1_5/`)

| File | Required content |
|---|---|
| `BASELINE.md` | HEAD, compare baseline, dependency snapshot, changed files, services, datasets, migration inventory |
| `FEEDBACK_PACKAGE_DECISION.md` | Why package disappeared; restoration/replacement matrix; compat test evidence; maintainer decision |
| `DEFECT_TO_CODE_MATRIX.csv` | Every `REG/REP/PUB/SEC/TST/NUM/ING/OPS` finding mapped to code commit, real test and status |
| `REPAIR_STATE_AND_APPROVAL_CONTRACT.md` | Schema, independent four-eyes actors, transition sequence, serving guard, legacy migration |
| `PUBLICATION_AND_ROLLBACK_SAGA.md` | Real graph/vector operations, version hashes, outbox, leases, crash/replay/compensation |
| `FINANCIAL_METRIC_POLICY.md` | Steward decisions/unknowns, metric operation policy, exact arithmetic, grain/period rules |
| `FINANCIAL_GOLD.csv` | Synthetic or authorized gold case IDs and independent expected results; no customer secrets |
| `QUERY_ROUTE_MATRIX.csv` | Every real query/chat/stream/admin route; role, tenant, source, fallback policy, evidence |
| `TEST_COMMANDS_AND_RESULTS.md` | Actual commands, observed pass/fail/skip, commit, exit codes, versions, logs |
| `FAULT_INJECTION.md` | Scenarios, observed external effects, persisted statuses, recovery proof |
| `MIGRATION_AND_RESTORE.md` | Backup and restore rehearsal results, Alembic versions, data compatibility |
| `RELEASE_GATE.md` | COMP, SEC, REP, PUB, NUM, ING, E2E, OPS with evidence and BLOCK/PASS |
| `CHANGELOG.md` | Reviewable commits, risk notes, backwards compatibility and pending decisions |

Minimum real test files recommended: `backend/tests/test_wave15_regression_and_governance.py`, `backend/tests/test_wave15_publication_recovery.py`, `backend/tests/test_wave15_financial_gold.py`, `backend/tests/test_wave15_query_parity.py`, and companion Repair service/Feedback package tests as appropriate.

**Quality threshold:** `DONE` requires actual implementation + applicable real tests + explicit evidence. `DESIGNED`/`STUBBED`/`SKIPPED` is never `DONE`.

---

## 11. Ready-to-paste local Codex / engineering agent execution prompt

```text
ROLE: Principal engineer + security and financial data architect + independent
release assurance lead. You are implementing AMC Context Engineering Wave 1.5.

REPO: nusummit-spg/amc-context-engineering-poc
CURRENT BRANCH: amc-dev
BASELINE SHA: 17fe11268f240359198f03bff1a1e9f9f2b8a3db

FIRST: read the full file AMC_Wave1_5_Next_Implementation_Agent_Handoff_2026-11-06.md,
then Wave 1.4 source/status, the AMC architecture/financial/feedback specs,
and actual implementation. Confirm HEAD and compare changes before edits.
Create new branch wave1_5/closure from pinned SHA if still appropriate.
Do not force push or deploy to production.

EXECUTE THE NEXT MAJOR BULK PROGRAM:
1. R01-R08: investigate/restore or migrate deleted Feedback package;
   unify authoritative patch status and four-eyes; resolve invalid SQL
   reviewed_approved status; remove legacy approved-only retrieval/promote
   bypass; quarantine provisional vectors; enforce secure graph writes;
   correct invitation concurrency and test false positives.
2. P01-P10: actual FAISS staging, graph postcondition/preimage,
   single authoritative outbox worker with idempotency and retry,
   real graph+vector rollback and Feedback outcome reconciliation;
   include fault-injection tests. No fake verified receipts.
3. F01-F08: financial policy enforcement in planner AND executor,
   exact Decimal math, canonical identity/grain, NAV date pairing,
   staged/hashed ingestion and independent gold. Block AAUM sums without
   documented data-steward approval.
4. Q01-Q06: query/chat/stream/fast path/Feedback/UI parity, no numeric
   fallback, safe cached retrieval and preservation of PDF/TXT behavior.
5. A01-A07: clean checkout, migrations, real CI, failures, canary and
   evidence-based release gates.

PRIORITIZATION:
- Finish R first; conduct P in large reviewable commits.
- F may progress in parallel with P only behind safe metric refusal.
- Q and A can follow dependency readiness; create CI early.

INVARIANTS:
- Never treat confidence/approved alone as authority to serve.
- Only independently approved, verified, ACTIVE, current-version patches
  with genuine publication receipts can influence answers.
- No provisional vector chunk in normal retrieval.
- Only one writer controls external publication; outbox event != completed
  write. Every retry is idempotent.
- No update to canonical graph or index without verified postcondition.
- Rollback must actually restore and verify prior state.
- Do not silently remove Feedback component or change business behavior.
- No illegal AAUM SUM/AVG/rank without steward decision.
- No float-sensitive financial amounts as authoritative numeric truth.
- No fallback LLM/Pandas numeric synthesis on structured-source failures.
- Preserve PDF/TXT and frontend contracts.
- Avoid exposing credentials; no production mutations.
- No empty tests, assert True tests, unexecuted async code, fake CI PASS,
  or tests that only validate a mocked method was called.

DELIVER:
- All real code, fixtures, migrations and relevant runnable tests.
- Reviewable PRs/commits with SHA and affected file table.
- Regression resolution for entire deleted Feedback package.
- Error, rollback, auth and numeric correctness evidence.
- Baseline, test outputs, migration rehearsal, status matrix and rollback.
- Strict RELEASE_GATE with BLOCK if any critical gate not evidenced.
- 8-12 line executive summary: implemented / tests passed / still blocked.

DO NOT STOP AT DOCUMENTATION OR STUBS. For missing external systems,
complete safe adapters/fixtures and clearly report what could not be
verified. Keep P0 operations fail closed. Request only human steward or
production authorization when it is genuinely required, not routine
technical clarifications.
```

---

## 12. Re-audit checklist and release decision

After a new push, provide its SHA and PR URLs. The independent review will verify:

1. The deleted Feedback-loop package is restored or has a documented accepted and working replacement.
2. A single serving eligibility policy is enforced inside every direct fast-path response, RAG context, microservice adapter and cache.
3. The legacy `approved`-only query and direct canonical mutation bypasses are gone.
4. SQL proposal status values, migrations and approvals agree; a normal review can persist.
5. FAISS was actually rebuilt or rolled back; receipt records active generation hash and observed probes.
6. Neo4j graph values are changed/read back, not only logged; rollback restores verified preimage.
7. Outbox can process a real event exactly once logically, even after restart and duplicate delivery.
8. Pending synthetic corrections never enter normal vector results.
9. Tests contain no `pass`-only success cases, unconditional `assert True` or swallowed event-loop exceptions.
10. Unapproved AAUM aggregate plans are rejected by executor and all query surfaces.
11. Independent CSV gold, manifests, source hashes and NAV observation semantics reconcile.
12. PDF/TXT control answers and frontend/Feedback contracts remain intact.
13. CI jobs ran for the *new* SHA; status checks and logs are accessible.
14. A clean clone can migrate/recover without touching production data.
15. All applicable gate decisions are evidence-backed with human release sign-off.

**Decision at pinned SHA `17fe112`: BLOCK.** Wave 1.4 containment reduced some false success paths but did **not** prove operational publishing, cross-system correctness, financial truth, or end-to-end safety. Continue with Wave 1.5 as above; do not claim release readiness until tests and evidence change this determination.
