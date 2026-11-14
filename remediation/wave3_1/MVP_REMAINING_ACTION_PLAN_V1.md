# AMC Wave 3.1 — Remaining MVP Action Plan (AP-31 v1)

**Status:** Approved for engineering execution planning; **NOT** MVP approval.  
**Source baseline verified 2026-11-14:** `feature/amc-wave31-integration` at `75680052d3660645dd9e929b7c61ab234ed06d28`; draft [PR #13](https://github.com/nusummit-spg/amc-context-engineering-poc/pull/13) targets `amc-dev` (`2c0415c4d23a3338428c8314c869299aa0ab771f`).  
**Owner:** AMC integration implementer (team's local agent); reviewer: CTO/ChatGPT GitHub review; final product/release approval: authorized NuSummit owner.  
**Operating constraint:** No third-party infrastructure budget, no GitHub Actions minutes, no real customer data; use locally runnable Python 3.11, disposable Docker PostgreSQL/Neo4j, synthetic FAISS fixtures.  
**Related artifacts:** [Technical design specification](MVP_TECHNICAL_DESIGN_SPEC_V1.md), [Agent execution instructions](MVP_AGENT_EXECUTION_INSTRUCTIONS_V1.md), [Machine-readable gate manifest](MVP_GATE_MANIFEST_V1.json), [prior handoff](TEAM_LOCAL_VALIDATION_HANDOFF.md).

## 0. Executive decision / MVP boundary

The proposed first releasable product is a **controlled, single-deployment, authenticated read-only verified-publication Q&A pilot**. It allows an explicitly scoped tenant to log in, query a verified corpus through v2, view grounded citations (subject to UI verification), see limited publication status, and deny all unapproved raw/legacy/mutation endpoints. The **publication operator flow may be CLI/offline** and should not be available to ordinary users. Do not advertise customer self-service ingestion, automatic graph repair, arbitrary legacy RAG fallback, multitenant SaaS production, full feedback-lifecycle management or 24/7 SLO until separately accepted.

**Go/no-go rules:** Source and archive tests are not sufficient. No production/customer release without signed-off G0–G9, live synthetic end-to-end tests, a deployment rollback rehearsal, data handling review and explicit product scope acceptance. Local-only demonstration may precede MVP release but must be labeled `DEMO / NOT ACCEPTED`.

## 1. Confirmed current status vs unknowns

| Area | Seen in repository | Evidence category | Gap |
|---|---|---|---|
| Wave 3.1 cumulative code | Integration commit `83ee6cac`, migrations 013/014, publication and receipt modules | Present/source reviewed | Whole-repo runtime unverified |
| Legacy bypass mitigation | `31f11da7` guarded query/chat/graph/docs/files/taxonomy/aggregation | Source-reviewed only | Authenticated HTTP negative/positive E2E |
| Verified pilot perimeter | `24356a2d` plus `36f0bf56` startup restrictions | Isolated tests/source review | Full ASGI lifespan and background-process proof |
| PostgreSQL runtime selection | `f271c8f5` requiring psycopg and migration 014 in enforced mode | Isolated tests/source review | Actual PostgreSQL migration/engine/ORM compatibility |
| Documentation/evidence automation | `2d6bfb41` plus `75680052` collector and local Compose | Repo verified | Collector / Compose full execution unverified |
| Offline original release archive | 669 main tests and 16 subtests previously reported passed | **Reference-only**, not current HEAD | Exact HEAD regression, Windows/Linux |
| GitHub CI on current feature SHA | No current-SHA checks at review | Not executed | Optional; local testing prioritized |
| Business release acceptance | Not supplied | Not executed | Product, governance, operational owner sign-off |

## 2. Prioritized deliverable register

Priority legend: **P0** = indispensable release safety/function; **P1** = first-pilot operational readiness; **P2** = explicitly post-MVP. Status `TO VERIFY / IMPLEMENT` means no claim that the code is absent; first verify, then fix only demonstrated defects. Estimates are **relative engineering effort** (S/M/L), not dates or delivery commitments.

| ID | Pri | Work package and concrete result | Dependency | Effort | Gate |
|---|---|---|---|---|---|
| WP00 | P0 | Freeze pilot scope, account/tenant test contract, synthetic fixture inventory; confirm latest SHA | none | S | G0 |
| WP01 | P0 | Make Python 3.11 requirements resolvable; full import/compile/pytest collection; classify symlink issues; Node install/build | WP00 | M/L | G1 |
| WP02 | P0 | Disposable PostgreSQL migration DAG 001→014, engine and Alembic URL identity, SQLAlchemy ORM/schema mapping, idempotent upgrade | WP01 | M | G2 |
| WP03 | P0 | Same-tenant first-publication two-writer race, scope uniqueness, rollback-after-failure, crash/replay, first-active receipt, stale worker fencing | WP02 | L | G3 |
| WP04 | P0 | Neo4j synthetic graph preimage/readback/CAS, partial failure recovery and transaction/effect reconciliation | WP02–03 | L | G4 |
| WP05 | P0 | Real FAISS binary and signed corpus; tenant binding, active receipt checks before/after retrieval, rollback and stale generation denial | WP02–04 | L | G5 |
| WP06 | P0 | Authenticated HTTP v2 query/chat/SSE, citation provenance, per-tenant visibility; negative unauthorized route/mode/mutation tests | WP02–05 | L | G6 |
| WP07 | P0 | Read-only UI smoke, correct state/error/denial messaging, build and browser automation | WP01, WP06 | M | G7 |
| WP08 | P1 | Logging with no secrets, readiness/health, restart, backup/restore, performance measurement, deliberate failure injection | WP02–07 | M/L | G8 |
| WP09 | P0 | Exact-commit evidence ledger, independent security/architecture and business sign-off; release/canary/rollback decision | WP01–08 | M | G9 |
| WP10 | P2 | Self-service ingestion, feedback repair, mutation governance UI, broad multi-tenant SaaS, automatic scaling | after MVP | L | separate PR |

### Dependency / critical-path view

`WP00 → WP01 → WP02 → WP03 → WP04 → WP05 → WP06 → WP07 → WP08 → WP09`. Work on WP07 frontend static tests may begin after WP01; WP06 negative ingress tests may begin before FAISS is available; all modules must integrate at WP09. **Do not stop all work when one external dependency is missing.** Report the blocked gate; continue independent packages.

## 3. Work-package execution details

### WP00 — Source/contract freeze, synthetic fixtures

**Tasks:** Pull latest `feature/amc-wave31-integration`; record full SHA; confirm `amc-dev` base and PR #13; audit current feature contract against repository tree. Confirm one test tenant `tenant_alpha`, one adversarial tenant `tenant_beta`, two independent users, an admin/operator role, a tiny explicitly licensed synthetic corpus with two generations and controlled graph entities. Record UI paths expected to work in enforced pilot.

**Definition of done:** `PILOT_SCOPE_DECISION.md` records in/out, primary workflows and sponsor approval; `TEST_FIXTURE_MANIFEST.json` includes tenant IDs, fixture hashes, expected citations, synthetic license/source flags, never secrets. All later tests point to the exact SHA. Do not claim data fixtures exist until materialized.

### WP01 — Reproducible build, collection and baseline repair

**Tasks:** Python **3.11** venv outside checkout; lock/pin only conflicting dependencies; run compile, `backend/tests` collection and targeted/contract suites via `collect_local_evidence31.py`, then full non-e2e backend, tests 28–31; run frontend `npm ci`, `npm test`, `npm run build`. Check Windows and Linux where available. Investigate three Windows Python 3.14 symlink privilege failures from earlier handoff; do not exclude silently. Verify source test harness does not label `PASS_OFFLINE_CONTROLS_ONLY` as full integration acceptance.

**Definition of done:** dependency changes justified; no import or syntax blockers; signed result counts, zero unresolved P0 failures, exact-SHA source test log and JUnit. Tests genuinely skipped due optional providers remain labeled blocked, not pass.

### WP02 — Persistence and migration accuracy

**Tasks:** Start *disposable* PostgreSQL 16 via `ops/validation/compose.wave31.local.yml`. In the same Python process check `DATABASE_URL`, `engine.url`, `AMC_MIGRATION_DATABASE_URL`; assert they target the exact same disposable database (never print credentials). Run `backend/scripts/alembic_dag_preflight.py` and `python -m alembic -c alembic.ini upgrade head` from `backend/`, read `alembic_version`, inspect all scope/authority/receipt FK/PK/check/unique constraints. Test a second upgrade with no changes. Check SQLite off-mode regression separately. Inspect ORM model schema vs migrations; fix actual drift. Never modify shared DB.

**Definition of done:** PostgreSQL 001→014 upgrade and rerun succeed, application sees same database, authority+scope+work+receipt tables verify, no hidden `create_all` override in verified mode. Capture redacted DDL evidence and revision result.

### WP03 — Durable publication correctness

**Tasks:** Two concurrent workers start first publication with empty authority on identical (`tenant`, `namespace`) and differing work IDs: exactly one obtains HELD scope; losing worker cannot mutate graph. Repeat with second tenant (no cross-tenant contention), retry same work (idempotent), stale work replay, preimage restoration, failed graph and failed vector swaps, and live ACTIVE → SUSPENDED → ACTIVE/rollback. Use deterministic barriers/fault hooks; no “sleep until race appears” assertion.

**Definition of done:** no double owner, no mixed graph/FAISS published versions, monotonic epochs, retry/rollback receipts complete, no stranded HELD state without a documented operator recovery action. Capture transaction traces; do not falsify status by mocking out the SQL uniqueness guarantee.

### WP04 — Neo4j integrity and recovery

**Tasks:** Connect disposable Neo4j with synthetic tenant-separated nodes. Verify durable work/effects and graph preimage before mutation, apply reviewed changes, independently read back graph, inject loss of Neo4j and process crash between graph and vector commit, rerun recovery, compare effects ledger to graph. Verify no graph schema/rules seed or unreviewed worker writes during enforced startup.

**Definition of done:** only authorized work mutates graph, failure leaves serving suspended/denied, replay reaches one auditable terminal state, compensation restores prior materialized graph or produces a documented human-review BLOCK; opposite tenant untouched.

### WP05 — Signed FAISS serving, revocation and read consistency

**Tasks:** Build real small FAISS index from synthetic documents, sign/manifest with project-approved signer and known test trust key, publish gen A then gen B; test file/content hash mismatch, tampered manifest, missing receipt, wrong tenant, partial index, stale cached reader, duplicate chunk ID, rollback before/during/after v2 request. Test refusal rather than fallback to legacy `app.engine.faiss_store`. Review and test parser/metadata provenance and citation URL behavior when `/api/files` is denied.

**Definition of done:** Q&A only from matching ACTIVE generation; every emitted citation maps to authorized tenant+source+version; deliberate revocation denies new and stale answers, including SSE. Any observed stale chunk is a release P0.

### WP06 — Auth, API and streaming defense

**Tasks:** Create real synthetic user sessions; validate login/logout/me, expired/invalid token, missing tenant, role checks, cross-tenant identity, cookie/bearer behavior, CSRF/CORS in actual deployment mode. Exercise both `/api/query/v2` and default `/api/query` plus `/api/chat` and `/api/chat/stream` with `QUERY_ENGINE=v2` and enforce/off modes. Deny `/api/query/traditional`, `/api/query/contextgraph`, `/api/graph`, `/api/files`, `/api/docs`, `/api/taxonomy`, aggregation, admin/ingest/feedback mutation, alternate `/files` paths and WebSocket. Test ASGI lifespan startup, background suppression, errors, exact method/path normalization and static assets. Test revocation mid-stream and bounded response buffer.

**Definition of done:** positive paths return authenticated tenant-bound answers with grounded citations; negative paths return expected 401/403/503 without leaking content; invalid serving mode fails closed; no unauthorized database/graph writes. Off-mode regression stays isolated and is not used to pass enforce-mode tests.

### WP07 — Frontend and UX constraints

**Tasks:** Run browser smoke against real local API with authenticated synthetic tenant. Verify login, Q&A, citations, source references, empty index, publication suspended, 401/403/503 errors, broken provider, loading states, mobile viewport and accessibility keyboard navigation. Detect if UI links target intentionally disabled `/api/files` in enforce mode. Either adapt the UI to safe metadata-only citations or implement approved receipt-bound source read APIs **behind separate tests**; do not silently re-enable raw file downloads.

**Definition of done:** successful pilot user journey, reproducible browser log/screenshot artifact redacted, no P0 console errors, no misrepresentation of confidence or citation provenance, disabled features clearly marked unavailable.

### WP08 — Operability and privacy

**Tasks:** Document local startup/stop, authenticated liveness vs true readiness, handling unavailable graph/index/provider, structured traces IDs, token and latency budgets, filesystem permissions and data retention; crash/restart, rollback from gen B to A, database backup restore in disposable environment and expected audit record. Verify no passwords/PII in logs, JUnit, test reports, PR comments or artifact directory; test retention and cache controls. Measure rather than fabricate p50/p95 and request rate. Decide who runs operator-only publication flow.

**Definition of done:** repeatable operator runbook, observed rollback and failure drill, capacity and resource footprint, security review, release guard remains blocked if no real staging canary/SLO window was possible.

### WP09 — Release evidence, independent go/no-go

**Tasks:** Commit fixes, rerun on exact final clean SHA, publish redacted `LOCAL_VALIDATION_SUMMARY.md` and evidence index with JUnit/log hashes. Run `mvp_evidence_gate31.py` against real records (not placeholders); any `staging_smoke` or `canary_rollback_slo` gate impossible locally must remain BLOCKED. Independent reviewer examines migrations, real race/rollback, auth/citation demos, risk ledger and release decision. Approve pilot-only scope explicitly; keep PR draft until evidence is complete.

**Definition of done:** G0–G9 passed with traceable actual evidence, product owner and engineering reviewer sign off, rollback plan rehearsed; only then consider merge/release. An evidence schema PASS does not authorize deployment.

## 4. Non-negotiable evidence gate matrix

| Gate | Evidence required | Reject on |
|---|---|---|
| G0 | Accepted scope / fixture matrix | Undefined pilot features or unsourced data |
| G1 | Python 3.11, full collection, targeted regressions, Node build, exact-SHA JUnit | Import error, hidden skip, stale SHA |
| G2 | Fresh PG 001→014, checked constraints, matching runtime URL | SQLite in enforce, unverified revision |
| G3 | Two true PG transactions race, crash replay, idempotence | Double owner, stale writer accepted |
| G4 | Neo4j observed readback, effects and compensation | Partial graph leak, cross-tenant mutation |
| G5 | Real FAISS + signed generation & receipt revocation | Unsigned index, stale result/citation |
| G6 | Authenticated HTTP & SSE positive/negative matrix | Unauthorized path, dropped tenant, leaked chunk |
| G7 | Frontend build and live local browser result | Broken Q&A or citation, misleading UI |
| G8 | Restart/backup/rollback and observed metrics | No recovery path, secret leakage |
| G9 | Independent review and product acceptance; stage/canary evidence where required | Missing environment, unreviewed risk |

## 5. Risk register / trade-off decisions

| Risk ID | Severity | Decision / containment |
|---|---|---|
| R1 App vs Alembic DB divergence | P0 | Fail startup unless same PG URL/014 is demonstrated; inspect runtime engine; see `backend/app/core/db_runtime31.py` |
| R2 New publisher vs existing authority race | P0 | Unique (`tenant`, `namespace`) scope claim and true multi-session PG test |
| R3 Stale graph/vector after rollback | P0 | Request-lifetime fence; signed generation; before/after authority test |
| R4 Legacy endpoints or background mutation | P0 | Verified perimeter and startup containment, attack-path test |
| R5 Citation links fail when raw files denied | P0/UX | Choose metadata-only safe citations or receipt-bound source endpoint with auth |
| R6 Frontend assumes features disabled in pilot | P1 | Explicit pilot UI mode; avoid dead buttons |
| R7 Python 3.14 / symlink issue | P1 | Canonical 3.11; classify Windows privilege vs code defect |
| R8 Test-only creds/fixtures leaked to Git | P0 | Local secrets, sanitize, reject binary/corpus and log uploads |
| R9 No staging available | P0 release | Do not rebrand local smoke as staging or production acceptance |
| R10 Scope growth to self-service SaaS | P1 schedule | Defer to post-MVP; avoid architectural rewrites |

## 6. Work cadence and handoff protocol

**Batch A (no Docker):** WP00 + WP01 + static negative gate tests + frontend build. Commit fixes; retain exact-SHA logs.  
**Batch B (Docker available):** WP02–WP05 on disposable providers, actual real FAISS; isolation and failure injection.  
**Batch C (integration):** WP06–WP08 full backend + UI E2E, operational incident drills.  
**Batch D (review):** WP09 final SHA rerun, independent review, PR decision. If Docker unavailable, deliver A plus blocked B/C/D and do not claim MVP.

At the end of each batch the agent must provide: work package IDs, 40-char tested SHA, tests run/failed/skipped, meaningful source diffs, environment fingerprint, observed evidence paths/hashes, blocked gates, risk decisions, and whether it changed the feature head. Keep one PR: **#13**. Push only to `feature/amc-wave31-integration` without force; no new branch/duplicate PR/merge. Follow [agent instructions](MVP_AGENT_EXECUTION_INSTRUCTIONS_V1.md).

**Out of scope for this iteration:** production data migrations, customer deployment, security bypass to make demos pass, additional research features, expensive cloud provisioning and automatic PR merge.
