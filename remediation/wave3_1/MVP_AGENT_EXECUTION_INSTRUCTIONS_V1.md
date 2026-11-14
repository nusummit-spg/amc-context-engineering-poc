# AMC Wave 3.1 — Local Agent Master Execution Instructions (AEI-31 v1)

**Give this file to the team's local coding agent as its master task.** Read [Action Plan](MVP_REMAINING_ACTION_PLAN_V1.md) and [Technical Spec](MVP_TECHNICAL_DESIGN_SPEC_V1.md) entirely before edits. Work on the existing GitHub branch, not a ZIP. This instruction supersedes ambiguous prior handoffs, but preserves every valid security/release gate.

## 1. Agent mission

Operate as a senior backend/integration engineer, SRE and release test lead. Implement **WP00–WP09 as far as local dependencies permit in one consolidated run**, with small coherent commits, observed verification and explicit blockers. Correct actual root causes, don't add optional features. No need to ask user for routine architecture approvals; use the approved **controlled read-only pilot** default. Stop and request explicit human authority only for real customer data, destructive or production operations, paid resources, release/merge, or access control change.

**Strict prohibitions:** No production access/data, no extra spending, no GitHub Actions, no force push/rebase, no unauthorized PR merge, no fabricated logs/tests, no suppressing security failures, no rerunning `install_wave31.py`/`apply_all31.py` over integrated source. No false `MVP ready` statement. Don't make verified-mode tests pass by setting `AMC_VERIFIED_SERVING_MODE=off`.

## 2. Verify GitHub checkout before any action

Target repo: `https://github.com/nusummit-spg/amc-context-engineering-poc`  
Working branch: `feature/amc-wave31-integration`  
Pull request: `https://github.com/nusummit-spg/amc-context-engineering-poc/pull/13` into `amc-dev`  
Plan-preparation baseline at 2026-11-14: `75680052d3660645dd9e929b7c61ab234ed06d28`; this is an **audit anchor**, not a permanent HEAD lock. Later plan commit(s) intentionally advance SHA; always work from freshly fetched HEAD.

### Windows PowerShell, checkout root

`git fetch origin --prune`  
`git switch feature/amc-wave31-integration`  
`git pull --ff-only origin feature/amc-wave31-integration`  
`git status --short`  
`git rev-parse HEAD`  
`git log -7 --oneline`

If working tree is dirty, inspect it and preserve it safely; do not run collector until clean. If branch diverges, **stop instead of force/rebase**. Record current HEAD and compare with PR #13.

Write concise `WP00_SCOPE_NOTE.md` (later commitable) naming the read-only verified Q&A scope, which endpoints remain denied, two synthetic test tenants, operating limitations and sign-off still needed.

## 3. Environment isolation and dependency strategy

Use Python **3.11**, Node LTS compatible with Vite, Git, local Docker Desktop if available; no services outside localhost. On Windows create venv adjacent to checkout:

`py -3.11 -m venv ..\.venv-amc-wave31`  
`$py = (Resolve-Path ..\.venv-amc-wave31\Scripts\python.exe).Path`  
`& $py -m pip install --upgrade pip`  
`& $py -m pip install -r backend\requirements.txt`

If pip fails, record complete resolver error, identify minimal version conflict and fix on feature branch with tests. Avoid broad version upgrades, especially Python 3.14 workaround. Prefer a clean environment over stale site-packages. For Linux use `python3.11 -m venv ../.venv-amc-wave31` and activate or point directly to `../.venv-amc-wave31/bin/python`.

**Secrets and evidence:** Store temporary test credentials only in session environment/local encrypted config, never Git. Evidence directory is a sibling outside repository; preserve JUnit/log checksums and redact any connection URL with password. Don't commit binary FAISS or corpus data.

## 4. Batch A — source/build and unit integration (no Docker needed)

Run this from checkout root **after dependencies install**:

`& $py -m tools.amc_release.collect_local_evidence31 --repo . --full-backend --frontend`

This invokes current source compilation, targeted pilot/DB/bypass/evidence tests, Wave28–31 source tests, broad backend collection/regression, frontend npm dependency/test/build. Inspect the output at `../amc-wave31-evidence-<sha>/local-handoff-summary.json`; ensure exact SHA, Python 3.11, all invoked stages and exit codes are recorded. Collector may run time-consuming tests and write a `node_modules` tree; it does **not** run real PG/graph/FAISS or certify MVP.

**Supplementary checks:**

`& $py -m tools.amc_release.qualification31 --repo . --out ../mvp-qualification/source-audit.json`  
`Push-Location backend; & $py scripts/alembic_dag_preflight.py; Pop-Location`  
`git diff --check`

Do not treat successful `--collect-only` as executed tests. Distinguish backend full-collection from executed regression and protected-mode true HTTP integration. If provider-dependent tests can't run, capture exact cases; continue with independent work. If Windows symlink privilege failures recur, prove they are environmental vs logic failures; do not remove cases from release denominator.

**Repair protocol:** For each reproducible failure: write test ID, expected/actual behavior, impacted WP/FR/NFR; fix smallest source area; add tests; re-run failed section, then consolidated suite on final commit. When encountering actual design mismatch, preserve safety and update spec with ADR/rationale.

## 5. Batch B — actual database and graph using *disposable* Docker

Only execute with local Docker and explicit confirmation the volumes contain no useful data. **Do not run repository-root `docker-compose.yml`.** It has AWS logging and demo settings.

Create strong test-only passwords (≥8 characters for Neo4j); set environment variables without committing:

`$env:AMC_TEST_PG_PASSWORD = Read-Host 'Disposable PostgreSQL password'`  
`$env:AMC_TEST_NEO4J_PASSWORD = Read-Host 'Disposable Neo4j password'`  
`docker compose -p amc31-qa -f ops/validation/compose.wave31.local.yml up -d`  
`docker compose -p amc31-qa -f ops/validation/compose.wave31.local.yml ps`

Target ports: PostgreSQL `127.0.0.1:55432`, Neo4j Bolt `127.0.0.1:57687`, browser `127.0.0.1:57474`. If those ports collide, alter *only* isolated validation Compose and document. Use alphanumeric test passwords to avoid URL encoding mistakes, or URL-encode correctly.

Export **the same PG URL** for both runtime and migrations. Do not print the raw URL to logs:

`$env:DATABASE_URL = 'postgresql+psycopg://amc_qa:<URL-ENCODED-PASSWORD>@127.0.0.1:55432/amc_qa'`  
`$env:AMC_MIGRATION_DATABASE_URL = $env:DATABASE_URL`  
`$env:NEO4J_URI = 'bolt://127.0.0.1:57687'`  
`$env:NEO4J_USER = 'neo4j'`  
`$env:NEO4J_PASSWORD = $env:AMC_TEST_NEO4J_PASSWORD`

The password placeholder above **must be replaced locally in process memory**, never saved. Check using SQLAlchemy `make_url` and masked output that app engine DB and Alembic same. Then:

`Push-Location backend`  
`& $py scripts/alembic_dag_preflight.py`  
`& $py -m alembic -c alembic.ini upgrade head`  
`& $py -m alembic -c alembic.ini current`  
`Pop-Location`

Require `014_publication_scope_claim_v31`, inspect status/PK/FK/unique scope claim constraints with SQLAlchemy inspector/read-only SQL, rerun upgrade and test duplicate insert denial. **Never downgrade non-disposable database.** Recreate disposable database for failing migration rather than manually inventing schema.

**Use actual independent SQL connections** and two publisher processes to test first-claim race, losing writer denial, idempotent same-work replay and crash/retry. Mock-only tests do not count. Supply worker fault injections, observed SQL effects and pending terminal reconciliation result.

For Neo4j use synthetic graph entities. Inject crash after graph mutate and before FAISS receipt, prove readback and compensation. Validate that enforced-mode app startup does not mutate graph or start legacy background processors. Reject any test outcome where graph data from tenant_alpha appears to tenant_beta.

For FAISS build a small **real** CPU index with synthetic documents and a locally generated disposable signing key. Prove receipt generation binding, index hash tamper denial, tenant mismatch denial, stale cache denial, rollback revocation, and no legacy vector fallback. If model embeddings require download, use deterministic offline compatible fixture when supported, but real FAISS binary read remains required for G5.

Use `AMC_VERIFIED_SERVING_MODE=enforce` and `QUERY_ENGINE=v2` for security/positive tests. Off-mode regression runs **separately**. Verified mode is a read-only HTTP pilot; CLI/operator publication is not exposed through unreviewed admin APIs.

## 6. Batch C — authenticated full-stack HTTP/SSE and frontend

Launch app from root/backend with tested env and synthetic corpus/tenant. Run actual authenticated positive `/api/auth/login`, `/api/auth/me`, `/api/query`, `/api/query/v2`, `/api/query/stream`, `/api/chat`, `/api/chat/stream` and `/api/publication/status/<work_id>`. Verify corpus/receipt IDs, citation provenance and tenant ownership; assert all expected legacy/raw/aggregation/admin/mutation routes deny.

**Required negative probes:** missing/wrong/expired token, missing tenant, payload tenant mismatch, cross-user session, overlapping document IDs, invalid serving mode, canary/shadow flags, source-document aliases `/files` and `/api/files`, unknown method, malformed path, percent-encoding, WebSocket, mid-stream authority revocation.

Record HTTP status, sanitized response signature, relevant authority epoch before/after, graph/index/durable work effect, and proof of absence of leaked answer chunk. Don't use health 200 as proof a tenant can query.

Frontend: run `npm ci`, `npm test`, `npm run build` from `mf-context-engine/` (collector also covers them); serve app and execute real browser test on desktop/mobile viewports with clean fixtures. Verify reading mode, disabled ingestion/repair actions, actionable but safe error UX, citation card when `/api/files` denied, no broken links or stale text after rollback. Browser test may require `npx playwright install` first; if blocked by browser download, report that category BLOCKED rather than silently skip.

## 7. Batch D — security, operations, recovery and release dossier

Run restart/shutdown and kill/replay at first claim, after graph effect, before receipt, after active switch, during SSE, and during rollback. Rehearse DB backup/restore only inside disposable test volumes, retain receipts/authority digest. Measure per-stage latency and memory footprint; never invent 1h/24h SLO or staging canary results.

Before any commit: check secret scanning, no customer docs or model/index binary, no local URL with real password in docs. Create `remediation/wave3_1/LOCAL_VALIDATION_SUMMARY.md` (sanitized); include exact tested SHA, environment versions, WP and gate matrix, tests totals, fail IDs, actual DB/graph/index proof, latency observed (if real), blocked prerequisites and proposal. **Raw evidence remains outside Git.**

Evidence intake tool:

`& $py -m tools.amc_release.mvp_evidence_gate31 --checkout . --evidence-dir ../mvp-qualification --out ../mvp-qualification/mvp-gate.json`

This reports `BLOCKED` until all required *actual* SHA-bound evidence exists. Never fabricate `PASS` JSON merely to satisfy checker. A passing evidence schema means “independent review required,” not automatic MVP approval.

### Final commit SHA and evidence ordering

1. Finish code changes, tests and documentation; commit. 
2. Ensure `git status --porcelain` is empty; record `git rev-parse HEAD`.
3. **Rerun** critical qualification on this exact clean final SHA; raw logs/JUnit outside repository. A subsequent code/documentation commit changes SHA, so rerun and update evidence accordingly.
4. Push `git push origin feature/amc-wave31-integration` only; do not change `amc-dev` or `main` or PR review status.
5. Add PR #13 comment: workstreams completed, tested SHA, observed counts, failures, untested gates, sanitized evidence identifiers and acceptance recommendation.
6. Respond here with **`AMC Wave 3.1 integrated validation pushed; SHA <40-char>; PASS/FAIL/BLOCKED summary`**.

## 8. Completion format (mandatory)

Include a compact matrix in the PR comment, and copy to chat:

| Gate | State | Repro command + artifact | Defect / blocker |
|---|---|---|---|
| G0 Pilot scope | PASS/BLOCKED | Scope decision | Product sign-off |
| G1 Build+source | PASS/FAIL | JUnit, checksum | Exact cases |
| G2 PostgreSQL | PASS/FAIL/BLOCKED | Alembic, DDL checks | Constraints/URL |
| G3 First publisher | PASS/FAIL/BLOCKED | Two-worker traces | Race/replay |
| G4 Neo4j | PASS/FAIL/BLOCKED | Readback/fault | Effect mismatch |
| G5 FAISS | PASS/FAIL/BLOCKED | Signed index test | Stale/tenant |
| G6 Auth/API/SSE | PASS/FAIL/BLOCKED | HTTP matrix | Leakage/auth |
| G7 Frontend | PASS/FAIL/BLOCKED | Browser/build | Citation/UI |
| G8 Operations | PASS/FAIL/BLOCKED | Restart/rollback | Restore/SLO |
| G9 Release review | BLOCKED until acceptance | Independent owner | Missing staging/signoff |

## 9. Deliberate stopping conditions

Stop the **unsafe action** and report, but continue independent work if you encounter: real/shared database path; non-test secrets; unapproved production deployment; transaction/receipt invariant violation; cross-tenant leak; data loss; inability to distinguish test vs customer data; branch divergence or force-push requirement. Reconsider release scope rather than adding an unsafe bypass.

**Expected handoff result:** one consolidated feature-branch update with verified code fixes and honest tests. If Docker isn't available, finish Batch A and the static parts of C/D, report B/G2–G5 and runtime parts as blocked. **Do not describe this as a release-ready MVP.**
