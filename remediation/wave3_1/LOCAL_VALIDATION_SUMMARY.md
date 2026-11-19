# AMC Wave 3.1 — Local Validation Summary

**Decision: NOT RELEASE-READY. MVP is not accepted.** This is a sanitized record of what was run on one Windows
development machine against disposable local services, what it found, and what is still unproven. Raw logs, JUnit
files and the measurements are kept outside Git; this file carries their hashes and counts, never credentials.

- **Tested code SHA:** `71e6d80f519db6891f5f3c37e9dee1733e8d8b40` (live suite). Later commits are documentation and
  tooling only: `e056c03` (scope document), then this summary. Batch A below was rerun on `e056c03`.
- **Branch:** `amc-dev-wave31-integration`. Nothing was pushed, merged or deployed by this work; `main`, `amc-dev` and
  `feature/amc-wave31-integration` are untouched.
- **Environment:** Windows 11 Pro (build 26200), Python 3.11.18, Node 24.14, PostgreSQL 16.2, Neo4j 5.24.2 Community on
  Temurin 17.0.21, faiss-cpu 1.16.0, torch 2.15.0 (CPU). No Docker. All services on `127.0.0.1`, disposable, synthetic data.
- **Not real:** the LLM provider (a grounded local stand-in) and the query-embedding model (a deterministic hash embedder)
  were stubbed. Answer quality, provider latency and real-model retrieval quality were **not** evaluated.

## 1. Gate matrix

States use the design vocabulary: `PASS_RUNTIME_LOCAL` = real disposable local services, not staging or UAT.

| Gate | State | Evidence | What is still missing |
|---|---|---|---|
| G0 Pilot scope | **BLOCKED (sign-off)** | `PILOT_SCOPE_DECISION.md` (proposed), hash-pinned fixtures | Product, engineering and release owners must decide; sign-off lines are empty |
| G1 Build and source | **NOT PASSED** | Batch A on `e056c03`, Python 3.11: compile, 54 targeted tests, source qualification, `npm ci`, frontend tests and build all PASS; the Wave 3.1 runner covers 271 cases: 267 passed, 3 failed (symlink `WinError 1314`), 1 skipped | 3 Windows symlink tests need Developer Mode (a system setting); 336 backend tests fail identically on `amc-dev` (see §4) and have not been triaged to zero |
| G2 PostgreSQL | **PASS_RUNTIME_LOCAL** | 17 tests + 1 pinned expected failure (`test_pg_migration31.py`) | Linux and a non-embedded PostgreSQL; the Alembic chain does not run on SQLite (pre-existing) |
| G3 First publisher | **PASS_RUNTIME_LOCAL** | 29 tests: 8-round two-worker race, stale lease/fence, crash at 6 failpoints, rollback | Independent review of the ordering fix in §3; multi-machine workers |
| G4 Neo4j | **PASS_RUNTIME_LOCAL** | CAS, fence, readback, compensation, tenant isolation, outage and recovery | Neo4j under load and cluster behaviour |
| G5 FAISS | **PASS_RUNTIME_LOCAL (Ed25519-signed generations)** | Real-index tests: tamper, missing files, stale cache, revocation, tenant, bad/untrusted/revoked signature, startup refusal without public keys | Key custody and rotation process; real-model embeddings |
| G6 Auth, API, SSE | **PASS_RUNTIME_LOCAL** | 114 tests over real HTTP/SSE/WebSocket against the real app | Real LLM provider; cross-site cookie/CSRF testing in a real deployment |
| G7 Frontend | **PARTIAL** | 35 node tests, both builds, one manual browser walkthrough | No automated browser test, one browser engine, no stored screenshots, accessibility only spot-checked |
| G8 Operations | **PARTIAL** | 10 drills + 8 operator-CLI tests (restart, hard kill, PostgreSQL/Neo4j outage, backup/restore, measurements) | No staging canary, no SLO window, no named operator, no readiness probe |
| G9 Release review | **BLOCKED** | — | Independent security/architecture review, product acceptance, staging |

`mvp_evidence_gate31` on this evidence: **BLOCKED**. Five gates have records generated from the real JUnit file
(sha256 `38e0968735478f8881bcb808eeea399f81e709b0a24d9da7f68b5dbf75c5f447`); missing by design:
`backend_integration`, `frontend_build_browser`, `staging_smoke`, `canary_rollback_slo`. No record was fabricated.

## 2. What was run

| Suite | Result |
|---|---|
| Live suite `backend/tests/live31` (real PostgreSQL + Neo4j + FAISS + real app) | **261 passed, 1 expected failure, 0 failed, 0 skipped** after the P0 review fixes. This is two runs, not one: the full run gave 259 passed, 1 expected failure, 2 failed. One failure was a stale test (restored-database check built without verification keys, fixed); the other was a 180 s CLI subprocess timeout on a run that took 15 h 39 min wall clock (the machine was evidently suspended or starved). Both passed on re-run. No single clean full run exists for this commit. |
| ... migration/schema/startup guard | 17 passed, 1 xfail |
| ... publication race, crash, rollback | 29 passed |
| ... verified FAISS serving | 37 passed |
| ... real HTTP/SSE matrix | 114 passed |
| ... operator CLI | 8 passed |
| ... operational drills | 10 passed |
| Wave 2.8–3.1 tool suites (Batch A runner) | 267 passed, 3 failed (Windows symlink privilege), 1 skipped, of 271 |
| Frontend `node --test` and production build (normal and pilot mode) | 35 passed; both builds succeed |
| Full backend suite vs `amc-dev` baseline | 780 passed / 221 failed / 117 errors vs baseline 725 / 224 / 117; see §4 |

Without the live environment variables the live tests **skip as `LIVE31_BLOCKED`**; they are never reported as passing.

## 3. Defects found by running the real thing, and fixed

Each was invisible to the earlier unit and AST tests. **Items 1–4 change publication, request handling or
authentication and need independent security review before any merge.**

1. **Tenant wedged after two close publications.** The worker read graph and pointer preimages before taking the scope
   claim; if another publication completed in between, the stale preimage made every retry fail and left serving denied
   until an operator intervened (hit in 1 of 8 race rounds, then reproduced deterministically). Fix: stage first, take
   the scope, then read preimages (`Journal.acquire_scope`).
2. **`/api/chat*` returned HTTP 500 in enforce mode.** The second ("traditional") retrieval did not forward the tenant, so
   the verified fence refused it. Fix: forward user and tenant, as `/query` already did.
3. **Token revocation failed open.** Any error reading the revocation table accepted the token (and every database migrated
   only to 014 lacked the table); a token without a `jti` was never checked; logout reported success when revocation
   failed. In enforce mode these now refuse, and logout returns 503 on failure.
4. **A database outage took 130 seconds to fail.** No connect timeout. Now 3 seconds to a clean denial, with automatic
   recovery when PostgreSQL returns.
5. **Schema drift:** six model tables (including `revoked_tokens`) and several columns (`chat_sessions`, `response_feedback`)
   had no migration, so chat and revocation broke on a migrated PostgreSQL database. Migration `015` adds them.
6. **Pilot UI showed fabricated data and dead features.** Every denied page was offered; the Compliance Scorecard rendered
   built-in sample figures as "Real-Time" after its call returned 503; four denied admin calls fired at every login.
   The pilot build now shows Chat only and refuses denied calls itself.
7. **No operator publication entry point existed.** Added `amc_publication.operator_cli` (independent approval enforced).
8. **Test-harness faults that would have produced false evidence:** a launcher-only process kill (the "hard kill" did not
   kill the server), a launcher-only memory reading (17 MB instead of 805 MB), and a pipe-inherited hang. All corrected.

## 4. Pre-existing and unrelated failures (not caused by this work)

- The full backend suite fails 336 tests that fail identically on the `amc-dev` baseline: missing `GROQ_API_KEY` (95), tests that need a
  live server on port 8000 (20), Prometheus duplicate-registry errors, a missing `feedback_loop` package (5 files), stale tests
  that import names no longer in the source (11 files fail to collect), and similar. **They have not been fixed.**
- 5 tests that fail on the baseline pass here; 4 earlier-wave tests that asserted behavior Wave 3.1 intentionally changed were
  updated (with reasons) in `b7edea1`.
- Two tests differ between the runs and are flaky on **both** trees: the throughput benchmark (`ZeroDivisionError` from a zero
  elapsed time on Windows; failed 3 of 6 on this code and 1 of 6 on the baseline) and one enrollment test that fails only after
  other tests exhaust the shared login rate limiter (passes 6 of 6 in isolation on both).
- 3 Wave 2.9 symlink tests fail with `WinError 1314` (privilege). They need Windows Developer Mode, a system setting not changed here.

## 5. Measurements (one run, this machine, stubbed LLM and embedder)

| Measure | Value |
|---|---|
| First query after start (cold) | 17.4–19.1 s (model-backed NER warm-up) |
| Warm sequential, 40 requests | p50 0.40 s, p95 0.43–0.64 s, max 0.90 s |
| 6 concurrent clients, 36 requests | 36/36 ok, 3.1–3.3 req/s, p95 2.1–2.6 s |
| Server memory (launcher + server) | 805 MB |
| Request with PostgreSQL down | 3.0 s to a clean denial (was 130 s) |

These describe this run only. No threshold was set from them, and an SLO needs a real host and provider.

## 6. Open findings (recorded, not fixed)

1. **Backend fills `page = 1`** when a chunk has no page, so the Evidence panel shows "p. 1" for sources without pages.
2. **Signing and approval keys are organizationally controlled.** Generations are now Ed25519-signed and approvals carry two
   Ed25519 signatures (review fixes P0-1/P0-2). Software proves that holders of trusted keys signed; it cannot prove who holds a
   key, that approvers read the corpus, or that a key was not shared. Enrollment, custody, rotation and lost-key procedures are
   unowned; the operator CLI is the only enforcement point for approvals (the worker re-verifies the stored record).
3. **A permanently failed publication that holds the scope has no reconciliation procedure.** Serving stays denied by design;
   `operator_cli status` says operator review is required; no force-release exists, deliberately.
4. **Tampered artifacts raise `VerificationFailed`** (not `ServingDenied`) out of the serving path. Nothing is served, but callers
   must handle both.
5. **The rollback error text is internal** ("no valid active receipt authority"), and the suggested prompts are generic SEBI
   examples unrelated to the corpus.
6. **Non-pilot pages fall back to sample figures** when their API fails. They are hidden in the pilot build but still exist.
7. **`audit_metadata`** (compliance audit) still differs from its model; a few server-defaulted nullability differences remain.
   Both are pinned in the live tests and out of pilot scope.
8. **`/health` is liveness only;** readiness (can a tenant be served?) is undefined. Publication status is reviewer-role only.
9. **The Alembic chain does not run on SQLite** (migration 008 uses `drop_constraint`); pinned as a strict expected failure.
10. **Browser coverage is one manual session** in one engine; no Firefox/Safari, no automated test, no stored screenshots.

## 7. What this does not establish

No staging deployment, canary, rollback rehearsal on a release candidate, 1h/24h SLO, real LLM or embedding model, Linux run,
independent UAT, penetration test, data-handling or privacy review, or product sign-off. A passing evidence schema is not an
approval. **Do not describe this branch as a release-ready MVP.**

## 8. Reproduce

`ops/validation/local_services31.ps1 -Action Start`, set `AMC_LIVE_PG_URL`, `NEO4J_*`, `AMC_LOCAL_SERVICES_SCRIPT`, `AMC_PG_BIN`
(see the script for setup), then from `backend/`: `python -m pytest tests/live31`. Evidence builder:
`python -m tools.amc_release.make_evidence31 --junit <junit.xml> --checkout . --out <dir>`, then
`python -m tools.amc_release.mvp_evidence_gate31 --checkout . --evidence-dir <dir>`.
