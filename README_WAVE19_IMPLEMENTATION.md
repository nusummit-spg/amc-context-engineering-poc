# AMC Wave 1.9 — Implementation Package (Code, Not Another Plan)

**Reviewed repository:** `nusummit-spg/amc-context-engineering-poc`, branch `amc-dev` at `91af9fa4eaa8abdb66c55b04fdee484ea0343a3c` (6 November 2026).  
**Delivery mode:** ZIP overlay for local checkout. GitHub connector reported `push: false`; nothing has been committed or deployed.  
**Release recommendation:** **BLOCK** until live Graph/FAISS/PostgreSQL and all existing app routes pass acceptance tests.

## What this package actually implements

The `backend/amc_publication/` package is an **opt-in** publication engine. It does not pretend to replace the legacy `PromotionService` yet. It contains executable implementations, not only architecture diagrams.

| Subsystem | Included code | Test level | Production gate |
|---|---|---|---|
| Durable journal | SQL work items, unique idempotency key, approved revision, pre/postimages, verified receipts | SQLite integration passing | PostgreSQL concurrency + migration rehearsal needed |
| Fencing | Monotonically increasing global fence, lease owner/epoch, stale-owner rejection | SQLite fake-worker tests passing | PostgreSQL multi-worker and Neo4j fencing tests needed |
| Crash recovery | Resume from original preimage after simulated kill at six effect boundaries | Fault-injection passing | Kill/restart on actual services |
| Generation pointer | Content-addressed immutable JSON snapshot, exact digest/count validation, DB CAS activation | SQLite/filesystem passing | Mount persistence and multi-host synchronization |
| FAISS generation | Real optional FAISS `IndexIDMap2` builder, index/payload/manifest with SHA-256, exact ID readback | Implemented; **not executed** here (faiss-cpu absent) | Actual FAISS binary and hot-swap serving probe |
| Neo4j | Allowlisted graph property adapter, tenant scope, preimage CAS, global fence | Protocol/fake graph passing; live Neo4j **not executed** | Confirm AMC node mapping, actual readbacks and concurrency |
| Verified rollback | DB pointer compensation, graph preimage restoration, replay after mid-rollback crash | SQLite/fake graph passing | Real graph, FAISS and 2-phase compensation drill |
| Feedback | SQL receipt/tenant/version-based resolution and rollback reopening | SQLite integration passing | Wire to existing Feedback API; decide deleted microservice fate |
| Financial source integrity | Real file/chunk SHA-256 byte recomputation and full coverage | Filesystem tests passing | Integrate into actual CSV/PDF/TXT ingestion paths |
| Serving authorization | `ACTIVE` + tenant + verified journal receipt + matching active pointer | SQLite integration passing | Replace ALL legacy `approved` readers with this predicate |
| Metrics | SQL-backed status counts by tenant, not local Python lists | SQLite passing | Prometheus/dashboard/SLO windows not yet integrated |
| CI | New independent test workflow; targeted scanner repair script | Workflow authored and source scanner cause verified | GitHub Actions rerun required |

### Files supplied

- `backend/amc_publication/models.py`, `types.py`, `journal.py`, `worker.py`, `artifacts.py`, `faiss_artifacts.py`, `graph.py`, `feedback.py`, `serving.py`, `metrics.py`, `integrity.py`, `integration.py`, `demo_smoke.py`
- `backend/alembic/versions/012_wave19_durable_publication.py` — **additive** v2 migration; does not delete or change existing 009–011 tables.
- `backend/tests/test_wave19_durable_publication.py`, `test_wave19_integrity_feedback_migration.py`, `test_wave19_contracts.py`
- `.github/workflows/amc-publication-v2.yml` — separate executable contract-test CI gate
- `tools/repair_ci_gitleaks.py` — safely replaces the Gitleaks *action* requiring an organization license with the free Gitleaks CLI running via Docker; makes a backup.
- `remediation/wave1_9/IMPLEMENTATION_STATUS.md` — evidence table and remaining blockers.

## Local commands — Windows 11 / PowerShell

Open the **existing local checkout on `amc-dev`**. Extract this ZIP to a separate folder and use the included installer for a dry run and then an explicit apply. The installer refuses to overwrite existing files. The overlay contains no replacements of current AMC service source files.

```powershell
# Extract ZIP, e.g. under C:\temp\amc-wave19\
python C:\temp\amc-wave19\tools\install_overlay.py --repo C:\path\to\amc-repo
python C:\temp\amc-wave19\tools\install_overlay.py --repo C:\path\to\amc-repo --apply
cd C:\path\to\amc-repo
git status --short
python -m pip install "SQLAlchemy>=2,<3" "pytest>=8,<10" "alembic>=1.13,<2"
python -m pytest -q backend/tests/test_wave19_*.py
cd backend
python -m amc_publication.demo_smoke
cd ..
```

For optional real adapters: `python -m pip install faiss-cpu numpy neo4j`. Test those on the same embedding model, graph schema and index directory as the application. **These live adapters could not be exercised in the current execution environment.**

For a disposable database migration rehearsal, configure the existing Alembic environment for a temporary database, then run `alembic upgrade head` and inspect the six new `*_v2` tables. **Never downgrade production to base.**

To fix the **existing** failing secret scan, run from the repository root (after reviewing the diff):

```powershell
python tools/repair_ci_gitleaks.py
git diff -- .github/workflows/amc-assurance.yml
```

The original file is backed up as `.github/workflows/amc-assurance.yml.wave19-backup`; remove that backup after review. The CLI runs via `ghcr.io/gitleaks/gitleaks:v8.30.1`; the previous `gitleaks/gitleaks-action@v3` requires `GITLEAKS_LICENSE` for organization repos. The existing Actions run `42219020259` failed at the scanner step; no runtime evidence should be inferred from its skipped jobs.

## Production integration steps (must happen in the real checkout)

1. **Link SQLAlchemy sessions to application:** create `Journal(SessionLocal)` using the actual target DB, run migration 012 on disposable DB. SQLite is for tests and single-worker POC; production workers should use PostgreSQL with verified transactional semantics.
2. **Replace only the authoritative publication submission:** load an existing approved `RepairProposal` from DB under authenticated tenant scope; require immutable independent proposer/reviewer identities and approved revision; collect the **complete** trusted active corpus (not a per-patch partial list). Call `queue_verified_approval` once inside the intended orchestration path. **Do not have the governance route execute graph/vector effects.**
3. **Disable competing writers:** legacy `PromotionService`, `OutboxProcessor` and `correction_patch_layer.promote_to_permanent` must not independently write canonical Neo4j or live FAISS. Keep legacy endpoints fail-closed or return **202 with an actual persisted work ID**. The current repository still contains `approve_patch` alias and `get_active_patches` filtering merely approved patches.
4. **Adapt `Neo4jGraphPort` to your actual graph:** the sample adapter requires `:Entity {tenant_id,entity_id}` and an explicit field allowlist; the AMC graph may use `dedup_key`/`isin`. Do not broaden the MATCH scope or concatenate raw user-controlled labels/properties. Enforce real, tenant-isolated CAS, readback, and stale-worker fencing.
5. **Wire real FAISS binary generations into reading:** `FaissGenerationStore` builds/reads `index.faiss`, `payloads.json`, `snapshot.json` and a verified manifest. The legacy `VectorStore` currently reads mutable in-process `index.faiss`. Build a **reader that resolves the DB active-generation pointer** and swaps an immutable verified generation before serving. Provide its synchronous `serving_probe` to `PublicationWorker`. Without this, the production constructor **refuses activation**.
6. **Feedback and serving:** replace legacy `patch.approved`/status-only retrieval with `is_serving_eligible` plus stored work/receipt IDs; wire `FeedbackCausality` to live issue records. Keep issues unresolved until the same tenant's graph/vector effects and pointer are verified; reopen after rollback.
7. **Manifests and provenance:** call `verify_source_manifest()` against the **original file bytes and chunk boundaries**, and implement a full contributor ledger in the existing query executor (it currently truncates source IDs). Keep unapproved AAUM aggregation blocked.
8. **CI and release:** scanner patch first; run new contract tests; then complete PostgreSQL/Neo4j/FAISS integration tests, real kill/restart and two-worker races, PDF/TXT/CSV regression, security audit and release gate. No canary or production switch until independent evidence exists.

## Highest-priority unresolved defects in current `amc-dev`

- `backend/app/api/routes/governance.py`: a legacy promote helper still invokes a missing `get_patch()` method; the 202 exception can be rewrapped as 500; helper also has direct Neo4j write logic. Integrate by removing this helper rather than claiming it succeeded.
- `backend/app/graph/correction_patch_layer.py`: legacy `approve_patch()` aliases `promote_to_permanent()`, and `get_active_patches()` returns approved patches, not verified `ACTIVE` patches. Replace these bypasses before serving data.
- `backend/app/services/promotion_service.py`: uses old outbox events, sets `proposal.applied_at` at queue time and reports "Successfully applied" before external effects. Replace with persisted work ID and **QUEUED** status, not applied.
- `backend/app/services/outbox_processor.py`: graph and state-transition handlers still raise `NotImplementedError`; the new worker must become the **only** executor after explicit wiring and migration.
- `backend/app/services/vector_staging_service.py` / `graph_postconditions_service.py`: in-memory staging remains unsafe for restart; use the v2 durable journal and immutable generation artifacts in the authoritative path.
- Existing CI still fails at secret scanning and skips downstream quality gates. The new dedicated workflow covers the v2 code only; it is **not** a substitute for the full release gate.

### Security/release policy

**DO NOT** deploy, merge a PR, mutate live customer data, assume steward approval, enable auto-approval, or silently fall back to LLM/Pandas financial calculations. All live integration changes must be executed and verified in a disposable local environment first.
