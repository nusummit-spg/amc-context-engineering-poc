# AMC Context Engineering POC — Wave 2.2
## Source-Verified CI Recovery, Migration-History Repair, Feedback Dependency Cutover, and Production Integration Handoff

**Audit date:** 10 November 2026 (Asia/Kolkata)  
**Repository:** https://github.com/nusummit-spg/amc-context-engineering-poc  
**Branch:** `amc-dev`  
**Pinned HEAD:** `6c2f0181538a8985fcb3f3264a0e62ebef8a2944`  
**Comparison baseline:** `fe28ca6844ae170fcdcf434e0b65dde237738b90` — **18 commits ahead, 10 changed paths**  
**GitHub access:** connected account `pull=true`, `push=false`: this document is a handoff, **not** a pushed change.  
**Release decision:** **BLOCK**. Publication V2 and Quality V2 contracts are now green on the pinned SHA, but the full AMC Assurance pipeline is red and no valid end-to-end release evidence exists.

> **Evidence standard.** This file is based on the current GitHub branch, actual GitHub Actions job logs, and inspected repository source. No new application test run, Alembic operation, graph mutation, production deployment, or release approval was performed in preparing this handoff. A passing standalone contract suite does not establish the application's runtime integration. All local Codex operations must pin and report their exact checked-out SHA.

---

## 1. Executive recommendation

**Stop introducing new feature waves until the current branch can migrate and collect the complete test suite.** The two reported failures are confirmed, but their underlying causes differ from the initial descriptions. Fix these **without weakening controls, inventing migration history, or faking a feedback implementation**. Preserve all passing Wave 1.9/2.0 contract tests. Once both jobs are green, perform the unfinished Wave 2.1 production-path cutover and real external-effect testing as one controlled bulk batch.

### Verified latest GitHub Actions outcomes

| Workflow / run | Exact-SHA status | Finding | Required action |
|---|---|---|---|
| [Publication V2 #42635584242](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42635584242) | **SUCCESS** | Standalone publication contract suite green | Preserve as mandatory required check |
| [Quality V2 #42635584515](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42635584515) | **SUCCESS** | Independent quality tests green | Preserve as mandatory required check |
| [AMC Assurance #42635584544](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/42635584544) — A01 | **SUCCESS** | Clean Checkout Audit passed at current SHA | Do not rework scanner/audit without a new failing signal |
| Same — A02 Migration Rehearsal | **FAILURE** | `KeyError: '003_invitation_token_hash'`; revision `004_b03_verification` points to absent ancestor | Restore/reconstruct authentic migration history, then exercise correct DB dialect |
| Same — Unit Tests | **FAILURE** | `ModuleNotFoundError: No module named 'feedback_loop'` at test collection | Resolve external Feedback package or add a deliberately fail-closed optional integration |
| Same — A04 Regression, A05 Fault Injection, A06 Canary, A07 Release | **SKIPPED** | Required predecessors failed; later CI has placeholder gates | Implement and exercise real gates; do not count skipped checks as success |

### Important correction to the reported unit-test root cause

The unit-test traceback begins when `tests/compliance/test_audit_report.py` imports `app.main`. The chain is:

```text
tests/compliance/test_audit_report.py:16
  -> app.main:28
  -> app.api.routes.__init__
  -> app.api.routes.feedback_evaluation:34
  -> app.services.feedback:20
  -> from feedback_loop import FeedbackLoopConfig, start_feedback_loop
  -> ModuleNotFoundError: No module named 'feedback_loop'
```

`app.api.routes.query.py:35` importing `graph_store, retrieval` creates a **DeprecationWarning**, not the fatal exception. Do not rewrite the graph/retrieval engine to fix this collection failure.

`backend/requirements.txt` currently comments out both a Git-based `feedback-loop` dependency and the editable `../packages/amc-feedback-loop` install; the latter directory is absent from `amc-dev`. The external `nusummit-spg/human-feedback-loop` repository was not accessible to the connected GitHub account (404); this does **not** prove it is unavailable to the local maintainers. Resolve package ownership explicitly.

### Migration history findings

The `backend/alembic/versions/` tree at the pinned SHA contains `004` through `012`, and no `001`, `002`, or `003` script. `004_b03_graph_verification_receipt.py` declares:

```python
revision = '004_b03_verification'
down_revision = '003_invitation_token_hash'
```

`005` → `004`, `006` → `005`, ..., `012` → `011` form a downstream chain whose initial dependency is not present. The runner fails constructing the revision graph *before* testing the migration DDL. `backend/alembic/env.py` is newly added with `target_metadata = None`; `backend/alembic.ini` has a SQLite URL. A02 provisions a PostgreSQL 15 service but sets `DATABASE_URL=sqlite:///./data.db` and rewrites `alembic.ini` accordingly. **PostgreSQL is not being tested by that job.**

**Do not create an arbitrary no-op revision named `003_invitation_token_hash`; do not change `down_revision` to `None` or use `alembic stamp head` merely to make CI green.** The legitimate prior schema and migration history must be established first.

---

## 2. Source risk register — evidence, severity, response

| ID | Severity | Source / observed evidence | Risk | Corrective response |
|---|---|---|---|---|
| W22-01 | P0 | `004_b03_graph_verification_receipt.py` references missing `003_invitation_token_hash` | Broken Alembic graph | Recover authentic historical predecessor or approved equivalent baseline |
| W22-02 | P0 | `backend/alembic/versions/` contains only `004`–`012` | Full fresh-install lineage not represented | Audit local git history, tags, branches, prior schema, and production revision IDs |
| W22-03 | P0 | A02 provisions Postgres but uses `sqlite:///./data.db` | A misleading migration smoke result could pass without PostgreSQL | Dialect-specific disposable DB jobs; `DATABASE_URL`-controlled Alembic config |
| W22-04 | P0 | `008` drops/recreates `ck_proposal_status`, `009` downgrade drops FK explicitly | SQLite cannot execute some raw constraint DDL; real upgrade/downgrade unproven | Exercise PostgreSQL and SQLite independently; batch operations where needed |
| W22-05 | P0 | `app/services/feedback.py` top-level imports `feedback_loop` | Entire app cannot import; test collection fails | Package restoration or explicit lazy, fail-closed provider boundary |
| W22-06 | P0 | `feedback_evaluation.py` commits `QueryEvidence` and `ResponseFeedback` before trigger | A downstream unavailable evaluator can leave partial writes and a 500 response | Define and test transactional/PENDING vs unavailable semantics, no false success |
| W22-07 | P0 | A03 uses `pytest -x`; stops at first collection error | Subsequent errors and tests hidden | Fix import; run `--collect-only` then full suite; preserve failure signaling |
| W22-08 | P0 | A04/A05 are currently skipped; workflow requires folders not found in the inspected tree | Test assurance not demonstrated | Create real regression/fault suites and ensure they run |
| W22-09 | P0 | A05 SLO and A06 canary are placeholders; A07 emits `CHECKED` | False-positive release signaling | Replace with measured evidence, fail-closed gate and independent decision |
| W22-10 | P0 | `amc_publication/worker.py` invokes `journal.verified(...observed=postimage)` | Desired value is mistaken for observed external readback | Re-read Neo4j/FAISS via independent APIs and validate hashes/fences |
| W22-11 | P0 | `journal.switch_back` deletes active pointer regardless of previous generation | Rollback can remove a valid previous corpus | Persist predecessor pointer and CAS restore it; empty-baseline handling explicit |
| W22-12 | P0 | `DurableWorker.execute_work` can set `status='published'` with a `prepared` effect | Alternative worker can report unsupported publication | Disable/remove phantom worker path; route outbox through one authoritative Journal worker |
| W22-13 | P0 | `app.graph.correction_patch_layer.approve_patch` legacy alias to `promote_to_permanent` | Approval can bypass journal; `get_active_patches` checks only `approved` | Retire all direct-publish paths and gate every answer source with durable proof |
| W22-14 | P0 | Legacy `feedback_outcome_service.py` still uses process-local issue links and staging counts | Feedback status can diverge after restart | Integrate `FeedbackCausality` with actual `FeedbackIssue` state and rollback |
| W22-15 | P0 | `app/tabular/executor.py` has `source_row_ids[:50]` | >50-contributor audit proof is truncated | Use Wave 2.0 complete ledger in all numeric response paths |
| W22-16 | P0 | `app/tabular/csv_excel_loader.py` defaults activation on reconciled counts | Unverified corpus can activate outside Wave 2.0 gate | Make authenticated activation explicit and attested; no count-only activation |
| W22-17 | P1 | A03 installs full requirements twice in a single run | Expensive CPU/GPU dependencies, slower failure diagnosis | One reproducible environment; slim contracts separate from full integration |
| W22-18 | P1 | `backend/alembic/env.py` has `target_metadata = None` | Autogenerate/drift checks not wired | Read reviewed metadata and prevent model-import side effects |
| W22-19 | P1 | `pytest.ini` uses `-m 'not e2e'` | Real stack tests intentionally excluded from ordinary full suite | Dedicated required integration workflow on controlled services |
| W22-20 | P1 | Gitleaks action receives parameters not documented in v3; A01 currently passed | Potential fragile scan config, not current blocker | Verify actual reports; change only if evidence shows invalid/no scan |

**Interpretation:** Current P0 blockers are not only the two visible CI errors. Once those are removed, the still-unwired publication and quality paths remain release blockers. Do not mark W22-10 through W22-16 closed because the standalone suites pass.

---

## 3. Wave 2.2 objectives and scope

**Goal G1 — Restore trustworthy test collection.** `from app.main import create_app` works on clean checkout; full `pytest --collect-only -q` completes; missing optional Feedback module never silently invents adjudication.

**Goal G2 — Restore authentic migration lineage.** `alembic heads`, `history -v`, fresh upgrade, populated-baseline upgrade, and disaster-free downgrade rehearsal pass against disposable databases. The chosen revision chain matches table existence and versions in existing deployments.

**Goal G3 — Make CI useful and efficient.** Distinguish contract, migration, backend, integration and release checks; every required job runs; no `exit 0` on missing test directories; no placeholder SLO, canary or signed decision.

**Goal G4 — Complete Wave 2.1 application integration, not redesign.** One publication worker, one trusted approval source, real external readback, generation-pointer rollback, Feedback causality and complete financial provenance.

**Goal G5 — Produce objective go/no-go evidence.** Every completion claim references exact commit, command, environment, dataset fixture, results and run URL; unknown or skipped evidence remains BLOCK.

**Out of scope for Wave 2.2:** new LLM prompting features, additional vector frameworks, new publication state machines, broad UI redesign, unreviewed real-data migrations, performance SLO claims without observed telemetry.

---

## 4. Bulk implementation task matrix

### Batch A — Immediate CI recovery (P0; execute together)

**A01 — Pin source and capture starting evidence.** Checkout `amc-dev` at `6c2f018...`; snapshot full `git status`, Alembic versions, current DB schema in a disposable clone, and three exact-SHA workflow results. Create local working branch `fix/wave22-ci-and-cutover`. Produce `remediation/wave2_2/00_SOURCE_BASELINE.md`, `CI_BEFORE.json`. Never modify production database.

**A02 — Trace migration prehistory, not just a filename.** Run `git log --all --full-history -- backend/alembic/versions`, `git branch -a`, `git tag -l`, `git ls-tree -r <historical-ref> backend/alembic/versions`; check prior schema snapshots and deployed `alembic_version` values. Search for real revision metadata matching `003_invitation_token_hash`. Record exact origin commit and checksum when found. If not found, add `MIGRATION_BASELINE_DECISION.md` containing model/schema reconstruction, explicit deployment compatibility evidence, maintainer approval and recovery plan; keep migration gate BLOCKED until reviewed.

**A03 — Restore the actual 001→003 chain or approved legacy baseline.** If authentic migrations exist, restore unchanged (or documented dialect fix with equivalent semantics) and ensure each `revision/down_revision` is unique. If unavailable, design an explicit versioned baseline capable of producing the prerequisite tables used by `004` (including `graph_mutations`, `repair_proposals`, invitation auth data); never silently stamp or create an empty bridge. For populated DBs, inventory existing revisions and compare schema before writing.

**A04 — Make Alembic use the chosen database dialect.** Change `backend/alembic/env.py` to load an explicit `AMC_MIGRATION_DATABASE_URL` (or agreed `DATABASE_URL`), validate nonempty URL, and reject suspicious defaults in CI. Do not rewrite checked-in `alembic.ini` with `sed`; instead use environment-driven config or `-x`/`-c` with a temporary config. Distinguish the application's SQLite `app.core.database` (`data.db`) from the PostgreSQL publication service. Record intended owner of each schema/table. For PostgreSQL CI use `postgresql+psycopg://postgres:postgres@127.0.0.1:5432/test_amc` **only after installing psycopg and confirming app/migration support**.

**A05 — Rehearse all migrations on disposable DBs.** Build schema from scratch, run `upgrade head`, inspect expected tables/indexes/constraints, `current`, `history`, and limited reversible downgrade/upgrade. Separately rehearse upgrades from a populated pre-004 fixture, including immutable receipt rows. Test `008` and `009` downgrade independently with relevant dialect support. Never use `downgrade base` on production or long-lived shared test databases. Rollbacks must preserve valid live data unless disposable.

**A06 — Decide Feedback package disposition.** Determine whether `nusummit-spg/human-feedback-loop` exists under a maintainer credential, is legally/commercially allowed, and matches the API (`FeedbackLoopConfig`, `start_feedback_loop`). Decision must be `RESTORE_PINNED_PACKAGE` or `REPLACE_WITH_ADAPTER` or `EXPLICITLY_DISABLE_EVALUATION`; write sign-off to `FEEDBACK_PACKAGE_DECISION.md`. Do not bring back the removed package merely to satisfy collection if unsupported. Check library/lockfile and source provenance.

**A07 — Remove unconditional Feedback import side effect.** Put `feedback_loop` import/initialization behind a provider module or inside a guarded `trigger_feedback_loop` execution path. The clean app and routers must import even if optional evaluator absent. If evaluator is mandatory, CI **must install** the pinned package and explicitly fail readiness if missing. If optional, return `503 FEEDBACK_EVALUATOR_UNAVAILABLE` on attempted evaluation (or a truthful durable `202 PENDING_EVALUATION` when queued), preserving GET/read APIs; never manufacture a successful evaluation record. Do not catch broad `ImportError` and silently continue under a success response.

**A08 — Repair Feedback transaction boundary.** Current `feedback_evaluation.py` commits QueryEvidence and ResponseFeedback before calling the evaluator; a later failure can leave data persisted despite a 500. Design explicit transaction semantics: preflight provider before writes when synchronous evaluation is required, or persist a durable `PENDING` evaluation task and return honest 202. Ensure no double feedback, no duplicate repair and no false 201 on evaluation failure. Preserve Auth/RBAC and tenant checks.

**A09 — Collect and execute all tests, not the first two.** First run `pytest --collect-only -q` to reveal remaining latent missing modules, then the full repo suite. Fix source/runtime missing dependency issues in dependency graph order, not by broad test suppression. `-x` is permissible during a diagnosis loop but not as sole success evidence. Record counts selected/collected/passed/failed/skipped/deselected. Preserve Wave 1.9 and 2.0 green workflows.

**A10 — Fix CI wiring without masking errors.** Run dependency installs once per job; preserve failure status; add a migration-lineage preflight **before** full dependency installation so missing ancestry fails in seconds; use a small package for static source validation, and separate full app integration. Ensure all required suites trigger on `amc-dev`; never mark skipped jobs passed.

### Batch B — Alembic and backend structural hardening (P0/P1)

**B01 — Add Alembic revision DAG preflight.** Use Alembic `ScriptDirectory.from_config` or a pure AST/script parser to enumerate revisions, reject unresolved ancestors, duplicate `revision`, cycles and unexpected multi-heads; emit a machine-readable revision map and SHA. Run before `alembic upgrade`, and in pre-commit.

**B02 — Create schema prerequisite matrix.** For revisions 004–012, list tables/columns/constraints each upgrade requires, produces, and removes. Check upstream consistency with ORM: `app.schemas.*`, `amc_publication.models`, invitation tokens, `repair_proposals` status. Do not trust that revision DAG resolution implies DDL success.

**B03 — Make dialect-specific DDL safe.** Review `008` check-constraint drop/create and `009` explicit FK drop; use `op.batch_alter_table` for SQLite where appropriate or mark SQLite unsupported for those migrations and test PostgreSQL only. Make both decisions explicit and test them; no broad exception handling around DDL.

**B04 — Separate legacy app SQLite and publication PostgreSQL assumptions.** The app's `app.core.database` currently hardcodes SQLite. If choosing PostgreSQL as canonical for publication, pass a clear DB session/engine into `amc_publication.Journal`; don't pretend switching `alembic.ini` also switches the API runtime engine. Document source of truth for `publication_work_v2` and `feedback_publication_link_v2`.

**B05 — Make migrations recovery-aware.** Prove behavior of a previously migrated DB, of an empty DB and a DB with revision mismatch. Never `stamp` absent scripts on a live DB. Provide a restoration procedure from backup with signatures/row counts and a migration-version history file.

**B06 — Slim CI and pin dependencies.** Separate `requirements-ci-contract.txt` from real backend integration. `python -m pip install -e .`/proper local package install if packaging exists, with isolated environment. Pin known working version constraints for SQLAlchemy, pytest-asyncio, pydantic etc after validating compatibility. One 3-minute duplicate install must not be the normal discovery path.

### Batch C — Real publication/rollback hardening (P0; after Batch A collection is green, can parallelize with B)

**C01 — Eliminate false graph verification.** In `amc_publication/worker.py`, after graph CAS call `graph.read(tenant, entity, attribute)` on the **authoritative graph store**, compare exact intended value, tenant/entity identity, source revision, and persisted fence; then call `journal.verified(observed=actual)`. If readback fails, leave job nonpublished and require compensation. Separate deterministic fake graphs from actual Neo4j integration.

**C02 — Replace placeholder production FAISS checks.** A nonempty snapshot directory is not sufficient. Demand `FaissGenerationStore.verify()` on actual `index.faiss`, `payloads.json`, manifest SHA and ID counts; reload via active serving reader, query exact chunk IDs, and prove current `publication_pointer_v2` matches visible generation. Fix any Windows directory-fsync differences in `faiss_artifacts.py` while preserving atomicity/consistency guarantees on both OS families.

**C03 — Fix pointer rollback.** Persist pointer **preimage** (`generation_id`, digest, epoch) at prepare time. On rollback, validate current pointer equals the generation created by the failing work; CAS back to the prior verified generation, not an unconditional `s.delete(row)`. If no valid previous generation exists, use an explicitly reviewed `EMPTY/INACTIVE` sentinel or a designated deactivation state with no stale reader; do not treat deletion as successful restoration.

**C04 — Disable `DurableWorker` false-publication path.** `DurableWorker.execute_work()` currently creates a prepared effect with pending hashes and marks `PublicationWork.status='published'` without external graph/vector readback. The outbox adapter may only create/claim work. The canonical `Journal` + `PublicationWorker` (after hardening) alone can issue verified publication receipts. Test that old/out-of-band worker cannot set published.

**C05 — One authenticated approval/outbox owner.** Update `governance.py`, `PromotionService`, `OutboxProcessor`, and `CorrectionPatchLayer.promote_to_permanent` so every approved request is queued to the same tenant-isolated journal. Delete, disable or fail closed on old direct Neo4j/FAISS mutation paths, async stub endpoints and `get_active_patches` that only check `approved`.

**C06 — Bind serving to durable evidence.** Apply `amc_publication.serving.is_serving_eligible` and tenant scope to every answer surface including context overlays, `fast_path_interceptor`, retrieval, exact numeric paths, and synthetic shadow patches. The result must be ACTIVE+verified receipt+actual active generation, not a local `can_serve` boolean.

**C07 — Bind Feedback to durable publication and rollback.** Replace legacy process-local links and staging counts with `FeedbackCausality` and verified `FeedbackIssue` DB state transitions. Resolve only after durable receipt plus exact serving readback; reopen on verified rollback. On failed/unavailable evaluator, do not create repair or mark issue resolved.

**C08 — Two-process crash/fence drill.** On disposable PostgreSQL + Neo4j + real FAISS test stack, run two workers on same tenant/work; inject death at preimage persisted, graph committed, readback, FAISS generation ready, pointer switched, receipt committed, rollback vector, rollback graph. Re-run both to test idempotency and no phantom receipts.

### Batch D — Complete Wave 2.0 data path (P0 after runtime stable; parallelizable)

**D01 — Replace count-only CSV activation.** Route importer through `amc_quality.ingestion_gate.guarded_ingest`, with genuine file hash/row order/manifest and no auto-activation; add explicit authenticated steward-approved activation transaction.

**D02 — Replace 50-ID truncation.** Connect `amc_quality.provenance.write_ledger/verify_ledger` to `QueryExecutor`, aggregation facade, API result and UI download. Return bounded display preview with immutable cursor/ledger digest while allowing full contributor retrieval; tests for 51/5,001 rows.

**D03 — Strengthen NAV/AAUM semantics.** Exact NAV requires source/date/scheme match and no ambiguous duplicates. Do not label scheme-count ranking as AAUM; AAUM aggregation and rank remain BLOCKED until a genuine steward decision is recorded. Never infer unsupported financial totals from prose.

**D04 — Activate data only on independent evidence.** Establish dataset version/manifest checksum/validation decision/provenance metadata, CAS active version, rollback predecessor pointer. Test tampered CSV, changed headers, partial ingestion and duplicate source rows.

### Batch E — Assurance and release gates (P0)

**E01 — Build required regression and fault-injection suites.** Existing A04 references `backend/tests/regression` and A05 references `backend/tests/fault_injection`; create meaningful tests there or explicitly change to verified existing test files. Do not create empty directories that pass. Require positive and negative cases.

**E02 — Integrate actual PostgreSQL migration and publication tests.** Use disposable PostgreSQL container with proper health check (run `pg_isready -U postgres -d test_amc`, not default `root`), actual migration URL, seeded rows, concurrency and DB reconnect. Keep standalone SQLite tests separate.

**E03 — Replace SLO echo checks with measurements.** Define real p95 request latency, end-to-end publication time, queue age, stale lease count, receipt mismatch count, rollback success and feedback resolution lag, with explicit sample/window and denominator. Missing sample => `UNKNOWN` / BLOCK, not pass.

**E04 — Make canary a real deployment exercise or a correctly skipped nonrelease gate.** No fake echo success; run repeatable staging deployment with read-only smoke, failback/rollback and evidence. If staging unavailable, outcome is NOT_RUN and release stays blocked.

**E05 — Enforce exact-SHA CI matrix and independent go/no-go.** Required: Publication V2 green, Quality V2 green, full backend collection + unit green, migration dual-dialect choice documented, regression green, fault tests green, integration recovery green, security/secret/dependency scan green, metrics/canary present, maintainer decision signed. No cherry-picking old successful commits to represent a later SHA.

**E06 — Produce independently reviewable evidence bundle.** Populate `remediation/wave2_2/{00_SOURCE_BASELINE.md,01_MIGRATION_HISTORY.md,02_ROOT_CAUSES.md,03_TASK_MATRIX.csv,04_TEST_EVIDENCE.json,05_CI_RUNS.md,06_DIALECT_MATRIX.md,07_FEEDBACK_DECISION.md,08_RELEASE_GATE.md,09_RUNTIME_CUTOVER.md}`. Include structured skips and all unresolved blockers rather than empty 'verified' checkmarks.

---

## 5. Acceptance matrix — tests that must fail when the protection is broken

**Migration / schema tests**

| Test | Required adversarial assertion |
|---|---|
| M01 | Missing `003` => static migration DAG gate fails before any DDL |
| M02 | Duplicate revision ID => gate fails |
| M03 | Unreachable/cyclic ancestor => gate fails |
| M04 | Unexpected multi-head => gate fails unless approved merge revision |
| M05 | Authentic predecessor restored => `alembic history -v` contiguous |
| M06 | Fresh *disposable* PostgreSQL upgrade to 012 creates correct tables/indexes |
| M07 | Populated pre-004 upgrade preserves primary keys/data and constraints |
| M08 | SQLite-specific `008`/`009` DDL behavior is independently validated or explicitly unsupported |
| M09 | `alembic current` corresponds to real materialized schema, not artificial stamp |
| M10 | Downgrade/upgrade on throwaway fixture round-trips important table structure |
| M11 | CI refuses staging or production DB URL in test migration job |
| M12 | Invalid/empty migration URL cannot fallback silently to local `data.db` |

**Feedback / test import tests**

| Test | Required adversarial assertion |
|---|---|
| F01 | `python -c 'from app.main import create_app'` succeeds on clean checkout |
| F02 | `pytest --collect-only` succeeds with valid dependencies; recorded full count |
| F03 | Optional evaluator absent => app import succeeds, evaluation returns documented 503/202; no false 201 |
| F04 | Required evaluator absent => readiness fails explicitly and early |
| F05 | Restored package exposes exact `FeedbackLoopConfig/start_feedback_loop` API |
| F06 | Import exception unrelated to package availability is not swallowed as 'optional dependency missing' |
| F07 | DB evaluator error cannot leave double-counted or falsely evaluated `ResponseFeedback` |
| F08 | POST retry using same `(response_id, actor_id)` is idempotent |
| F09 | GET Feedback records remains available if evaluator offline, per RBAC |
| F10 | No repair triggered or issue resolved without evaluated evidence and verified publication |
| F11 | `app.engine.retrieval` deprecation warning alone does not fail import and is not misdiagnosed |
| F12 | Full backend tests execute after collection and do not merely return collected=0 |

**Publication / rollout tests**

| Test | Required adversarial assertion |
|---|---|
| P01 | Intended graph postimage without actual matching Neo4j readback cannot be VERIFIED |
| P02 | Wrong tenant/entity/attribute or stale fence cannot mutate graph |
| P03 | Neo4j timeout after write => recovery reads exact state before retry/compensation |
| P04 | No FAISS binary, mismatched hash or missing ID => activation rejected |
| P05 | Reader reload observes pointer-selected generation only |
| P06 | Rollback of B after A restores A (not empty pointer) |
| P07 | Out-of-order rollback of A when B is active rejects safely |
| P08 | `DurableWorker.execute_work` cannot create fake published job or verified receipt |
| P09 | Legacy `promote_to_permanent` / `approve_patch` cannot bypass journal |
| P10 | 2 workers racing claim same work yield one valid published receipt |
| P11 | Worker death after graph write does not produce false verified receipt |
| P12 | Rollback reopens linked Feedback issue only after verified compensation |

**Data integrity / CI tests**

| Test | Required adversarial assertion |
|---|---|
| Q01 | Tampered CSV source/chunk hash fails prior to DB activation |
| Q02 | Changed row order/header/missing chunk fails manifest verification |
| Q03 | 51 and 5,001 contributor source IDs recoverable in ledger, no proof truncation |
| Q04 | Ledger SHA mismatch fails all numerical proof claims |
| Q05 | AAUM aggregation is blocked without steward approval, including UI/API indirect calls |
| Q06 | NAV duplicates or conflicting source versions return ambiguity, not arbitrary match |
| Q07 | A04/A05 jobs fail if no meaningful tests found |
| Q08 | CI exact-SHA complete run has no skipped required checks; SLO unknown => BLOCK |
| Q09 | Pipeline canary failure cannot write release-approved artifact |
| Q10 | Test evidence metadata includes counts, SHA, dialect, environment, scope and actual run URL |

**Total specified: 46 tests (M01–M12, F01–F12, P01–P12, Q01–Q10).** Add newly discovered issues from full test collection; do not claim any of these tests passed until executed.

---

## 6. Priority order and PR boundaries

| PR / Bulk | Tasks | Owner | Gate to merge | Priority |
|---|---|---|---|---|
| **PR-1: Migrations & startup** | A01–A05, B01–B05 | Local Codex + schema owner | Restored true DAG, migrated clean+populated fixtures, schema diff | **P0** |
| **PR-2: Feedback dependency & backend CI** | A06–A10, B06 | Local Codex + Feedback owner | Full import, test collection, backend tests and green contract suites | **P0** |
| **PR-3: Durable publication correctness** | C01–C08 | Local Codex + integration reviewer | Real graph/FAISS readback, no phantom publication, two-worker kill/restart | **P0** |
| **PR-4: CSV/numeric/Feedback runtime cutover** | D01–D04, C05–C07 | Local Codex + financial steward | Real request/response fixtures, complete proofs, effective gates | **P0** |
| **PR-5: Assurance & release evidence** | E01–E06 | Local Codex + independent reviewer | Exact-SHA required checks all green, signed rollback/canary evidence | **P0** |

**Execute PR-1 and PR-2 first (bulk, in parallel if separate working branches).** Expect the first full-suite run to reveal additional collection or functional failures currently obscured by `-x`. Do not begin data-model changes solely to solve an unverified hypothetical downstream failure. Keep PR-3 and PR-4 small enough to review and independently test, even if Codex can perform the work in a single local session.

### Exit conditions for the next session

At minimum, return (a) exact new HEAD, (b) no missing Alembic ancestors, (c) a passed fresh and populated migration rehearsal for every supported DB dialect, (d) a fully collected backend suite, (e) all full-test failures triaged with actual tracebacks, and (f) both Publication V2 / Quality V2 suites still green. **If these are not satisfied, stop before calling Wave 2.2 complete.**

---

## 7. Commands and diagnostics for local Codex

> Run from a **fresh local checkout**. The commands below are for exploration, not permission to mutate a production DB. Keep private credentials out of logs, prompt outputs and evidence artifacts. Windows PowerShell uses equivalent `py -m` and `Get-ChildItem` forms; for PostgreSQL container jobs use your locally configured Docker or CI environment.

```bash
# 1) Pin and report source
 git fetch --all --tags
 git switch amc-dev
 git pull --ff-only
 git rev-parse HEAD
 git status --short
 git switch -c fix/wave22-ci-and-cutover

# 2) Migration lineage: inspect before editing any revision
 git log --all --full-history -- backend/alembic/versions
 git branch -a
 git tag -l
 find backend/alembic/versions -maxdepth 1 -name '*.py' -print | sort
 grep -RInE '^(revision|down_revision)\s*=' backend/alembic/versions
 cd backend
 python -m alembic -c alembic.ini heads
 python -m alembic -c alembic.ini history -v
 cd ..

# 3) Isolate real app import failure
 cd backend
 python -c 'from app.main import create_app; app=create_app(); print("APP_IMPORT_OK")'
 python -m pytest --collect-only -q tests/
 python -m pytest -q tests/compliance/test_audit_report.py
 cd ..

# 4) Preserve already-passing contract suites
 python -m pytest -q backend/tests/test_wave19_*.py
 python -m pytest -q backend/tests/test_wave20_*.py

# 5) Full suite AFTER collection/import issue is fixed
 cd backend
 python -m pytest tests/ -v --tb=short
 cd ..
```

**Important:** The `*` glob in `python -m pytest backend/tests/test_wave19_*.py` is expanded on bash; on Windows PowerShell or CMD the shell may not expand wildcards. In that environment, use explicit file paths or a pytest directory/`-k` expression after verifying the discovered set.

**PostgreSQL disposable example (only once legitimate migrations are restored):**

```bash
# Deploy an isolated postgres:15 test container / GH Actions services.
# Do not use production credentials or databases.
export AMC_MIGRATION_DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:5432/test_amc'
cd backend
python -m alembic -c alembic.ini heads
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current
# On disposable fixture only and with recovery evidence:
python -m alembic -c alembic.ini downgrade -1
python -m alembic -c alembic.ini upgrade head
```

The existing Alembic `env.py` does **not yet consume** `AMC_MIGRATION_DATABASE_URL`; implement A04 first. `psycopg` is only a proposed dependency; install/pin it if PostgreSQL is the supported migration target. Avoid interpreting this shell snippet as a runnable migration on the current broken branch.

### Minimal flow of test import remediation (conceptual, not a drop-in patch)

```python
# In a provider boundary rather than module import-time initialization:
def require_feedback_provider():
    try:
        from feedback_loop import FeedbackLoopConfig, start_feedback_loop
    except ModuleNotFoundError as exc:
        if exc.name != "feedback_loop":
            raise  # A broken transitive import is not an optional-dependency condition.
        raise FeedbackProviderUnavailable("Feedback evaluator package not installed") from exc
    return FeedbackLoopConfig, start_feedback_loop
```

The API layer must map `FeedbackProviderUnavailable` to a documented 503 or explicitly durable queued 202 **and test transactional consequences**. If Feedback evaluation is mandatory, install a verified, version-pinned package and fail startup/readiness until that package works. Do not install an untrusted shadow `feedback_loop.py` or return a fake evaluation.

---

## 8. Evidence and status contract

Every task state must be one of:

- `NOT_STARTED`
- `IMPLEMENTED_UNVERIFIED`
- `LOCAL_TESTED`
- `CI_VERIFIED_EXACT_SHA`
- `LIVE_SERVICE_VERIFIED`
- `BLOCKED_OWNER_DECISION`
- `BLOCKED_EXTERNAL_INFRA`

A task cannot move from `IMPLEMENTED_UNVERIFIED` to `CI_VERIFIED_EXACT_SHA` solely because a nearby suite passed. Every test artifact must contain `commit_sha`, `command`, `start_utc`, `environment`, `database_dialect`, `fixture_version`, `collected`, `passed`, `failed`, `skipped`, `deselected`, `run_id`, `artifact_hash`, and whether external services were actually used.

**Release remains BLOCKED** even if A02 and Unit Tests pass, until crash-safe cross-store publication, full graph/vector serving readback, numeric provenance, Feedback lifecycle and real monitoring/canary are independently proven.

---

## 9. Codex-ready execution prompt

```text
You are executing Wave 2.2 for nusummit-spg/amc-context-engineering-poc on amc-dev.
Read this entire Markdown handoff and the current repo's AMC_Wave2_1_CTO_Source_Audit_Implementation_Handoff_2026-11-09.md.

SOURCE GATE:
- Start by checking HEAD; planned audit SHA is 6c2f0181538a8985fcb3f3264a0e62ebef8a2944.
- If HEAD moved, compare changes, preserve new fixes and update the evidence baseline.
- Do not cherry-pick earlier code that is already committed, and do not recreate amc_publication or amc_quality.

MISSION — EXECUTE IN BULK:
1. Triage & repair the actual Alembic DAG KeyError: missing 003_invitation_token_hash.
2. Restore authentic migration history from repo history, tags or trustworthy backed-up schema. If irrecoverable, STOP that specific migration rewrite, document a schema-baseline owner decision and proceed with independent Feedback tasks. NEVER invent a no-op 003 or stamp head without verified schema.
3. Fix Alembic's environment/database wiring; A02 currently runs SQLite despite provisioning Postgres. Run fresh + populated migration tests on disposable supported databases and test downgrade safely.
4. Fix full app import/test collection: missing feedback_loop is fatal. graph_store/retrieval is only a deprecation warning. Decide pinned package restoration vs deliberate fail-closed optional adapter. Maintain endpoint semantics, transactional behavior, RBAC and tenant isolation. No shadow module or fake success.
5. Re-run full pytest collection, full backend tests, both Wave 1.9/2.0 contract suites, then regression/fault-injection suites. Fix every new failure shown after the first blocker; do not suppress or xfail to claim green.
6. With CI unblocked, harden current publication worker for independent Neo4j readback, FAISS binary validation, predecessor-pointer rollback, disable phantom DurableWorker and legacy bypasses, and wire Feedback/provenance into real routes. Use real disposable services for crash/retry tests.
7. Replace placeholder SLO/canary/release checks with evidence-backed gates; retain release BLOCK until independently signed go/no-go.

NON-NEGOTIABLE:
- No modifications to production DB, no destructive migration on customer data.
- No invented revision ancestry; no `alembic stamp head` as a cosmetic fix.
- No bypass of human approval; no publication based only on intended postimage.
- No green reporting for skipped jobs or missing tests.
- Avoid unnecessary new libraries and huge full-dependency reinstall; run bulk tasks with limited user intervention.
- Do not push to amc-dev until individual commits are reviewable and test evidence is attached.

DELIVERABLES:
- Implement code and tests in a separate local branch.
- Produce remediation/wave2_2/00_SOURCE_BASELINE.md,
  01_MIGRATION_HISTORY.md, 02_ROOT_CAUSES.md, 03_TASK_MATRIX.csv,
  04_TEST_EVIDENCE.json, 05_CI_RUNS.md, 06_DIALECT_MATRIX.md,
  07_FEEDBACK_DECISION.md, 08_RELEASE_GATE.md, 09_RUNTIME_CUTOVER.md.
- Include exact-SHA commands/results, remaining blockers, before/after status,
  and compact next Codex integration steps.
- Preserve existing green Publication V2 and Quality V2 workflows.
- Stop only after all independent implementable tasks have been attempted;
  clearly separate owner decision / external-infra blockers.

FIRST CHECKPOINT:
Repair A01–A10 and B01–B05 together; provide actual migration and full-suite
collection evidence, then continue C/D/E where executable and safe.
```

---

## 10. Final architecture / product recommendation

Wave 2.2 should be treated as **CI and integration recovery**. A system that passes isolated financial and publication tests while its real backend cannot import is not yet fit for stakeholder demos, much less production. Conversely, a missing test dependency and incomplete migration DAG are solvable engineering defects; they do not justify discarding the Wave 1.9/2.0 implementations.

**Success criterion:** One coherent, reproducible codebase with real migration history, importable app, fully collected backend suite, deterministic financial provenance, four-eyes approval, exactly one authoritative durable publication path, verified graph/FAISS serving and rollback, persistent Feedback causality, and a release decision grounded in actual evidence.

**Audit note:** This handoff is not an executed code patch or a verified green run. GitHub account available here has read-only permissions for this repository. The Wave 2.2 artifacts are authored locally for Codex integration.
