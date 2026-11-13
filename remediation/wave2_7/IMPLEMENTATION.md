# AMC Wave 2.7 — Consolidated Serving Integrity and Engineering Integration

**Baseline:** `amc-dev` reviewed at `2c0415c4d23a3338428c8314c869299aa0ab771f` on 11 November 2026.  
**Mode:** locally built, cumulative Wave 2.3–2.7, offline tests with real SQLAlchemy/SQLite and historical Wave 1.9/2.0 journal fixtures.  
**GitHub:** read-only. **Actual AMC checkout:** NOT AVAILABLE locally; GitHub archive cannot be cloned in this environment.  
**Production release / UAT:** **BLOCK**. No claim of end-to-end app, live Neo4j, PostgreSQL concurrency, FAISS binaries, Windows, browser, SLO, or canary success.

## Executive architecture decision

Wave 1.9/2.0 introduced a durable publication journal and immutable snapshots. Waves 2.5/2.6 harden approval, retry, rollback, source manifest and status controls. The **remaining runtime defect** is that the existing AMC retrieval stack is not yet *demonstrably* bound to the active `publication_pointer_v2` plus a unique verified publication receipt. A pointer alone is insufficient: it can be switched before a receipt exists, or reverted during a query.

Wave 2.7 adds a **read-only generation resolver and opt-in FAISS serving adapter**. It explicitly separates:

1. **Pre-publication activation probe**: immutable bytes + actual loaded-reader check, used by `PublicationWorker` before receipt creation. Not permission to serve.
2. **Request-serving check**: pointer, single published verified receipt, two verified graph/vector effects, effect hashes, intact artifact, actual loaded reader; repeat after retrieval to detect revocation/drift.
3. **Read-only reconciliation**: independently reports incomplete work, dangling feedback, orphan receipts, invalid hashes, ambiguous pointer ownership. Never changes production data.

This solves a major missing boundary, but it is **not wired into the existing request retrieval orchestrator**. An authorized engineer must explicitly route every retrieval call through this adapter after real FAISS and tenant-schema acceptance. Do not assume import or file installation alone enforces serving integrity.

## Implemented source and controls

| Component | Task | Local proof |
|---|---|---|
| `backend/amc_publication/serving27.py` | Tenant-scoped verified pointer/work/receipt/graph+vector-effect eligibility; recheck after load; reject ambiguous same-generation receipts | SQLAlchemy/SQLite tests with durable journal |
| `backend/amc_publication/faiss_reader27.py` | Opt-in pointer-bound FAISS index loader and checked search; reject nonfinite/dimension/ID issues and pointer drift | Fake index contract tests only; **real faiss-cpu NOT_RUN** |
| `backend/amc_publication/reconcile27.py` | Read-only receipt/effect/Feedback reconciliation and bounded inventory | SQLite fault-mutation tests |
| `tools/amc_release/app_wiring27.py`, CLI | Source-Git-blob-locked registration of `/api/publication/status/{work_id}` in actual FastAPI `create_app()` | Source-fragment tests; source SHA verified from GitHub; **not applied to full checkout** |
| `tools/amc_release/preflight27.py` | Read-only branch SHA, source markers, repository changes and missing-implementation assessment; refuses UAT approval | Temporary real Git repo tests |
| `.github/workflows/amc-wave27-integration.yml` | Manual/opt-in Linux/Windows exact-SHA checks; expensive installs explicitly gated | YAML syntax validation; **GitHub Actions NOT_RUN** |
| `install_wave27.py` | Cumulative allowlisted copy; dry-run default; refuse unreviewed overwrites; no automatic main-app patches | Installer tests with synthetic Git checkout |
| `tools/amc_release/pytest_matrix27.py` | Deterministic Windows/Linux glob expansion and required test-suite discovery | Cross-platform selection tests; remote matrix NOT_RUN |
| `tools/amc_release/demo27.py` | Disposable SQL journal composition: graph/vector/receipt → eligible → rollback → revoke → Feedback reopen | Local simulation only; never UAT or actual worker proof |

### Important source audit discoveries

- `backend/app/main.py` does **not** register the existing `amc_publication.status_route.router`. Wave 2.7 supplies a narrow source-locked patch to make the authenticated endpoint accessible.
- `backend/app/api/routes/governance.py` at the reviewed source has a `queue_verified_approval(...)` signature mismatch and empty corpus path. Prior Waves 2.5/2.6 include source-locked patches for the audited SHA; until applied, this route is **not safe to consider integrated**.
- The legacy reader must be replaced or delegated to `VerifiedFaissRetriever`; simply adding a module leaves the old unverified read path exposed. The FAISS adapter now independently checks the **loaded binary's** manifest SHA, dimensions and entire ID map, and detects a file change during read.
- The *historical* Wave 1.9 test worker uses a vector-effect postcondition without a document `count`. Wave 2.7 deliberately rejects that incomplete evidence. The current `amc-dev` worker reviewed from GitHub includes `count` already; confirm the **post-patch** worker still emits this exact field after repo integration.
- Duplicate published receipts for the same content-addressed generation are **ambiguous without an active receipt ID**. Wave 2.7 fails closed. Future schema should bind active receipt/work ID to pointer atomically rather than guessing by timestamp.
- Existing `CorrectionPatch` approval is Redis/memory-backed. Persisted four-eyes approval and immutable revision proof need an authoritative database-backed review record for release acceptance.
- The latest GitHub Assurance workflow had no valid jobs; Publication/Quality contract workflows pass on `2c0415c4`. CI needs an actual clean new commit and no skipped required jobs.

## Branch installation, in one batch

**First:** open the complete `nusummit-spg/amc-context-engineering-poc` checkout, with `amc-dev` at the reviewed SHA, in an account that can create a feature branch. Use a fresh branch (not `main` or `amc-dev`).

```bash
git fetch origin
git switch -c feature/amc-release-candidate-hardening origin/amc-dev
git rev-parse HEAD
```

Extract this ZIP **outside** the repository, preserve directory structure, then run:

```bash
python install_wave27.py --repo /path/to/amc-context-engineering-poc
python install_wave27.py --repo /path/to/amc-context-engineering-poc --apply
```

Existing Wave 2.4/2.5 overlays require explicit audited `--upgrade-wave24/--upgrade-wave25`; unknown/mixed files are refused. Run existing Wave 2.6 source patches **separately**:

```bash
cd /path/to/amc-context-engineering-poc
python -m tools.amc_release.publication_patch26_cli --repo .
python -m tools.amc_release.publication_patch26_cli --repo . --apply
python -m tools.amc_release.app_wiring27_cli --repo .
python -m tools.amc_release.app_wiring27_cli --repo . --apply
python -m tools.amc_release.preflight27 --repo .
```

The source patchers require original reviewed Git-blob SHA values, refuse drift, and create `.wave26.bak` or `.wave27.bak`. Do not commit backups, secrets or `test_support/`. Run full backend, frontend, migration and security tests. Stage and commit only reviewed files.

## Offline reproducibility (no real infrastructure)

From the **extracted package directory** with the included reference test fixtures:

```bash
# Linux/macOS:
PYTHONPATH='.:test_support/baseline/backend' python -m pytest -q tools/amc_release/tests test_support/baseline/backend/tests/test_wave19_*.py test_support/baseline/backend/tests/test_wave20_*.py
PYTHONPATH='.:test_support/baseline/backend' python -m tools.amc_release.demo27
```

Windows PowerShell: `$env:PYTHONPATH='.;test_support/baseline/backend'`; discover test files with Python `Path.glob(...)` rather than shell wildcard literals. **In the actual repository** run `python -m tools.amc_release.pytest_matrix27 --repo . --report wave27-matrix.xml` after full backend dependencies are installed. Use the new GitHub workflow manually in `integration` mode for the authorized, expensive Windows/Linux run; the default `lightweight` mode is explicitly **not** integration acceptance.

## Required next technical acceptance before UAT

| Priority | Required proof / action | State |
|---|---|---|
| P0 | Apply source-locked Wave 2.6 changes to actual checkout and run route/approval tests | NOT_RUN |
| P0 | Apply `app.main` source-locked router wiring; JWT tenant role tests | NOT_RUN |
| P0 | Wire **every production retrieval path** to generation resolver; prohibit legacy direct FAISS/patch bypass | NOT_RUN |
| P0 | Add authoritative active receipt/work pointer binding or enforce explicit unambiguous receipt lookup | FAIL_CLOSED / DESIGN NEEDED |
| P0 | Resolve approval record persistence and immutable review revision | DESIGN NEEDED |
| P0 | PostgreSQL migration 012+, concurrent workers/fencing, crash recovery | NOT_RUN |
| P0 | Real Neo4j allowlist, CAS, readback and rollback | NOT_RUN |
| P0 | Real FAISS binary stage/load/search/rollback on Linux and Windows | NOT_RUN |
| P0 | Full backend and frontend regression on exact commit; one Windows/Linux test matrix | NOT_RUN |
| P1 | 1h/24h SLO samples, staged canary and browser acceptance | NOT_RUN |
| P1 | Externally anchored ledger, UAT reviewers and signed decision | NOT_RUN |

## Execution strategy

No further detachable architecture streams should be created. Use the cumulative ZIP as the working branch baseline, then close the explicit integration gates. Keep the release decision **BLOCK** until authenticated application tests and all real infrastructure evidence are green. If a connector or environment cannot support a particular check, report `NOT_RUN`, never `PASS`.

## Final local verification — 11 November 2026

| Suite | Passed | Result |
|---|---:|---|
| New Wave 2.7 tests | 102 | PASS, disposable SQLite/journal and mocked FAISS-reader contracts |
| Prior Wave 2.3–2.6 release controls | 236 | PASS |
| Historical Wave 1.9/2.0 reference contracts | 112 | PASS, historical test fixture, **not current GitHub checkout** |
| **Total pytest tests** | **450** | **0 failed; 16 additional subtests passed** |
| Clean-extracted ZIP retest | 338 + 112 | PASS; all checksums verified |

The disposable `demo27.py` composes through real Journal methods rather than the older historical worker, which did not persist document count in its vector postcondition. **No test above substitutes for end-to-end verification of the currently deployed/committed AMC worker and retrieval orchestrator.**
