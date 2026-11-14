# AMC Wave 3.1 — One-shot local validation and repair handoff

**For:** Team's local coding agent (Windows 11 / PowerShell; Linux equivalents are straightforward)  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Sole working branch:** `feature/amc-wave31-integration`  
**Draft review:** [PR #13](https://github.com/nusummit-spg/amc-context-engineering-poc/pull/13) → `amc-dev`  
**Scope:** Integrate, repair, test and report the **current HEAD**, not a ZIP overlay. **Do NOT re-run installers or merge the PR.**

## Agent mission and constraints

Execute as a *single consolidated engineering pass*. Start with the current feature HEAD, establish the exact baseline SHA, run the tests, fix failures, and rerun on your final committed SHA. Continue on other validation categories if one environment dependency is unavailable. The final handoff must contain a commit, passing/failed/blocked evidence, and an explicit residual release-risk list. Do not mark UAT/MVP complete simply because source tests pass.

- **No GitHub Actions**: run locally and avoid consuming remaining Actions minutes; do not merge, force-push, rebase published commits, or touch `amc-dev`/`main`.
- **No production or shared resources**: use a disposable PostgreSQL database and Neo4j graph, synthetic/test-only tenants and documents, and local FAISS fixtures. Do not run root `docker-compose.yml`; it includes AWS logging and shared demo settings. Use the isolated Compose file in `ops/validation/` below.
- **No credentials or proprietary corpus in Git**: never commit `.env`, databases, model caches, PDFs, FAISS binary indexes, API keys, connection strings, large logs, or raw customer content. Scrub exception traces and screenshots before sharing. Keep raw evidence outside the repository.
- **Fail closed**: retain `AMC_VERIFIED_SERVING_MODE=enforce` for security acceptance; never set it to `off` merely to make a verified-mode test pass. Off-mode regression is a separate test category.
- **No hidden skips**: log missing prerequisites, `xfail`, and skipped or failed tests. Do not change acceptance denominators or fabricate passing evidence.

## Phase A — Exact checkout and deterministic offline tests

Run from a normal terminal with Git, Python **3.11**, Node/npm and optionally Docker Desktop. For PowerShell:

```powershell
# If cloning fresh:
# git clone https://github.com/nusummit-spg/amc-context-engineering-poc.git
cd <YOUR_EXISTING_AMC_CHECKOUT>
git fetch origin
git switch feature/amc-wave31-integration
git pull --ff-only origin feature/amc-wave31-integration
git status --short
git rev-parse HEAD

# Create a virtual environment outside the Git checkout.
py -3.11 -m venv ..\.venv-amc-wave31
..\.venv-amc-wave31\Scripts\python.exe -m pip install --upgrade pip
..\.venv-amc-wave31\Scripts\python.exe -m pip install -r backend\requirements.txt

# One-shot locally observed source/backend/frontend evidence; evidence stays outside Git.
..\.venv-amc-wave31\Scripts\python.exe -m tools.amc_release.collect_local_evidence31 `
  --repo . --full-backend --frontend
```

If your operating system uses Bash, replace `py -3.11` with `python3.11`, use `../.venv-amc-wave31/bin/python`, and omit the PowerShell continuation backticks. **Do not run this against Python 3.14** and claim it meets canonical Python 3.11 qualification.

The collector performs full backend source compilation, targeted Wave 3.1 security and DB tests, source qualification, Wave 2.8–3.1 regression and full backend collection/regression, then Node dependency install, frontend tests and production build. Each subprocess gets its own `.log` and source SHA in `../amc-wave31-evidence-<sha>/local-handoff-summary.json`. Failure does **not** mean it may be silently ignored. Review and fix root causes, commit fixes, then rerun on the new SHA. The collector does **not** perform infrastructure mutations or approve an MVP.

**If pip dependency resolution fails:** capture its output and repair *minimal* compatible constraints with Python 3.11; do not blindly upgrade the entire stack. If broad tests require optional integrations unavailable locally, record precisely which tests are blocked and continue the other categories.

## Phase B — Disposable PostgreSQL and Neo4j (only if Docker is available)

Use the dedicated file `ops/validation/compose.wave31.local.yml`. It is isolated from the existing root Compose stack, uses different loopback ports, and holds only local test data. Set strong **test-only** secrets using your terminal's secure local mechanism; do not check them in:

```powershell
$env:AMC_TEST_PG_PASSWORD = Read-Host 'Temporary local PostgreSQL test password'
$env:AMC_TEST_NEO4J_PASSWORD = Read-Host 'Temporary local Neo4j test password (at least 8 chars)'
docker compose -p amc31-qa -f ops/validation/compose.wave31.local.yml up -d
# Verify both services are ready, without printing passwords.
docker compose -p amc31-qa -f ops/validation/compose.wave31.local.yml ps
```

Use an alphanumeric local password (or URL-encode special characters when building a SQLAlchemy URL). **Confirm this is disposable**, then point the app AND Alembic to the same database, which defaults to `127.0.0.1:55432` in this test stack:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://amc_qa:$($env:AMC_TEST_PG_PASSWORD)@127.0.0.1:55432/amc_qa"
$env:AMC_MIGRATION_DATABASE_URL = $env:DATABASE_URL
$env:NEO4J_URI = 'bolt://127.0.0.1:57687'
$env:NEO4J_USER = 'neo4j'
$env:NEO4J_PASSWORD = $env:AMC_TEST_NEO4J_PASSWORD
$env:QUERY_ENGINE = 'v2'
$env:AMC_VERIFIED_SERVING_MODE = 'enforce'

Push-Location backend
..\..\.venv-amc-wave31\Scripts\python.exe scripts\alembic_dag_preflight.py
..\..\.venv-amc-wave31\Scripts\python.exe -m alembic -c alembic.ini upgrade head
..\..\.venv-amc-wave31\Scripts\python.exe -m alembic -c alembic.ini current
Pop-Location
```

**Important**: The `..\..\.venv-amc-wave31` Python path assumes the virtual environment is adjacent to the checkout, as in Phase A. If your checkout is in a different layout, resolve the absolute venv path instead. Do not `downgrade` any non-disposable database, and never run migrations against staging or production without separate authorization. If migration history has a missing ancestor, SQL incompatibility, or model/schema drift, fix the actual defect in the feature branch and re-run on a newly created disposable database.

### Runtime checks for the local agent

1. **Database**: prove the application's SQLAlchemy engine and Alembic use the same PostgreSQL database and have applied exact revision `014_publication_scope_claim_v31`; no SQLite fallback when enforced. Run two concurrent first-publishers for the same tenant/namespace, assert one winner, and test crash/replay without duplicate scope ownership.
2. **Neo4j**: synthetic test-only graph mutation → readback → failure injection → compensation. Verify no graph changes occur from legacy startup paths in enforced mode.
3. **FAISS**: use a newly created small synthetic corpus and signed publication receipt; prove invalid/missing receipt, tenant mismatch and rollback revocation refuse answers. `AMC_VERIFIED_FAISS_ROOT` must point to that disposable material. Do not repurpose real AMC indexes.
4. **HTTP and SSE**: test authenticated user/tenant isolation, valid verified v2 Q&A + citations, and denial of `/api/query/traditional`, legacy/canary fallbacks, `/api/admin/ingestion/*`, `/api/graph`, `/api/files`, `/api/docs`, `/api/taxonomy`, aggregation and unreviewed mutation routes. Test `off` mode separately for backward compatibility. Verify no SSE answer chunk leaks after authority revocation.
5. **Frontend**: Node tests and production build from Phase A, followed by browser smoke against the disposable API. Only run Playwright UAT when legitimate credentials, browser dependencies and synthetic fixtures are available; do not count unexecuted browser tests as passes.
6. **Operations**: verify local startup/shutdown, retry/recovery telemetry, failure injection, rollback and SLO evidence; never label a local smoke test as a staging canary or 24-hour observation.

The existing `mvp_evidence_gate31.py` expects SHA-bound reports for backend, authenticated negative routes, PostgreSQL migration, publisher race, Neo4j compensation, FAISS rollback, browser, staging, and canary/SLO; it will **correctly remain BLOCKED** until all actual evidence exists. Do not create placeholder `PASS` JSONs. Actual local evidence only may be supplied, and staging-specific gates stay blocked if no staging was available.

When finished, shut down only the disposable Compose project. `docker compose -p amc31-qa -f ops/validation/compose.wave31.local.yml down` stops it but retains test volumes. `down -v` **deletes the local test database and graph volumes**; run it only after verifying no evidence is needed.

## Phase C — Commit, preserve evidence and hand back

1. Fix and test in `feature/amc-wave31-integration` only. Commit changes in a small number of **coherent commits** with exact test explanations. Do not commit enormous evidence archives, credentials or full model/data directories.
2. Keep sensitive/raw evidence locally or in a company-approved private artifact store. Add a *sanitized* report under `remediation/wave3_1/LOCAL_VALIDATION_SUMMARY.md` containing: tested commit SHA, OS/Python/Node versions, pass/fail/skipped counts, reproducible commands, exact failing test IDs and causes, migrations/current revision, infra availability, unresolved safety issues, and whether data fixtures were synthetic. Do not mislabel missing gates as PASS.
3. After fixes, **commit before the final validation** so `git status --porcelain` is clean. Rerun the collector against the final commit; attach the summary and JUnit SHA hashes, not fake evidence. If the report file is committed later, run against the new HEAD to preserve exact-SHA evidence (or keep all evidence outside Git and report in PR).
4. Push without forcing history:

```powershell
git status --short
git push origin feature/amc-wave31-integration
git rev-parse HEAD
```

5. Update existing [draft PR #13](https://github.com/nusummit-spg/amc-context-engineering-poc/pull/13) with the final commit hash, sanitized results and **blocked** gates. Do not open a duplicate PR. Do not mark it ready or merge.
6. Return here simply: **`AMC Wave 3.1 local validation pushed; commit <40-character SHA>`**. I will independently compare the new head, inspect patches and evidence, fix any remaining issues possible through GitHub, and decide whether another local test pass is required.

## Success criteria for this handoff

- Latest branch code compiled, test failures repaired where the environment permits, no suppressed errors.
- Disposable real PostgreSQL/Neo4j and synthetic FAISS validation if available; otherwise a precise blocker and source-only evidence.
- A consolidated, reviewable push with SHA-bound **observed** results.
- **No claim of MVP/UAT approval** without independently verified backend, data-integrity, security, frontend and operations acceptance.