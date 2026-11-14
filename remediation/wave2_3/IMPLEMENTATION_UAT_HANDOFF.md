# AMC Context Engineering POC — Wave 2.3
## CTO/Principal Engineer Takeover, Implementation, CI Matrix, and UAT Acceptance Handoff

**Date:** 11 November 2026 (Asia/Kolkata)  
**Repository:** `https://github.com/nusummit-spg/amc-context-engineering-poc/tree/amc-dev`  
**Reviewed source SHA:** `2c0415c4d23a3338428c8314c869299aa0ab771f`  
**Scope:** Wave 2.1 residual GATE01/GATE05/GATE06/GATE07, FB05/FB06, CI07; Wave 2.2 E05/CI08; assurance workflow defect and UAT closure.  
**GitHub plugin permission:** `pull=true`, `push=false`; **no branch, commit, PR, merge or GitHub Actions dispatch performed**.  
**Release verdict:** **BLOCK**. A UAT reviewer may review the *code candidate*, but **UAT acceptance and release authorization are NOT established**. No claim of production-readiness is supported.

> Execution standard: No guessed statuses; every PASS is bound to the exact commit, environment, actual executed tests, evidence hash and responsible reviewer. External services unavailable in this execution environment are NOT_RUN, not PASS. Local synthetic tests never substitute for staging evidence.

---

## 1. Executive technical decision

**Do not redesign the publication engine.** Freeze feature expansion and finish the one authoritative `Journal` + `PublicationWorker` + verified durable receipt + tenant-scoped retrieval/Feedback path. Wave 2.3 adds release instrumentation, acceptance gates and reproducible tests around the existing Wave 1.9/2.0 code. The proposed code is additive; no existing AMC runtime files are overwritten.

**Current exact-commit GitHub Actions:**

| Workflow / evidence | Observed result | Source |
|---|---|---|
| AMC Publication V2 Contract Tests | PASS | [Run 43005484510](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/43005484510) |
| AMC Quality V2 Contract Tests | PASS | [Run 43005484468](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/43005484468) |
| AMC Assurance Pipeline | FAIL, no jobs reported | [Run 43005482561](https://github.com/nusummit-spg/amc-context-engineering-poc/actions/runs/43005482561) |
| CI07 Windows/Linux Wave 2.3 matrix | NOT_RUN; workflow not pushed | New `.github/workflows/amc-release-verification.yml` |
| FB06 real Chromium + Firefox staging checks | NOT_RUN; no authenticated browser target | New `mf-context-engine/tests/feedback_uat.spec.mjs` |
| FB05 one-hour and 24-hour measured SLO windows | NOT_RUN; no live telemetry export | New `tools/amc_release/slo.py` |
| GATE05 canary + rollback | NOT_RUN; no staging deployment or rollback evidence | New `tools/amc_release/canary.py` |
| GATE07 two-reviewer UAT decision | NOT_RUN; no user acceptance signoff | New `tools/amc_release/gate.py` |

**Root cause observed:** `.github/workflows/amc-assurance.yml` has the `run:` field under the A05 fault-injection step incorrectly indented (`         run:` instead of `        run:`). An Actions run with zero jobs is not a green pass. The overlay contains a narrowly scoped fail-fast patch tool and patch file. **Additionally, the assurance pipeline currently masks full pytest collection errors (`|| true`), runs a selected subset as “Unit Tests,” and has placeholder SLO/canary steps.** Those must be hardened before relying on its overall green status. Do not simply bypass them to produce a release badge.

---

## 2. Delivery: implemented files and verification boundaries

| ID | Delivered implementation | Offline evidence | Remaining live integration |
|---|---|---|---|
| CI07 | Manually triggered Windows/Linux CI matrix; exact-SHA checkout, pytest JUnit artifacts | Workflow source, contract tests, syntax validation | Dispatch on committed SHA; both platforms must succeed |
| E05 | `github_ci.py`: GitHub REST exact-SHA checks; refuses zero jobs and skipped required jobs | Mocked API unit tests | Execute against real GitHub repo after push; bind runs/IDs to same SHA |
| CI08 | `counts.py`: JUnit parsing, pass/fail/error/skip counts, cross-OS drift and missing suite gate | Unit tests with adversarial XML | Real required-suite manifests from both OS; full AMC tests separate |
| FB05 | `slo.py`: UTC, 5-minute bucket coverage, p95/error rate, 60/1440-minute windows, UNKNOWN missing evidence | Clean, sparse, bad, future, cross-tenant fixtures | Real export from **staging** Prometheus/app telemetry, thresholds signed |
| FB06 | Real Playwright current-turn submit + previous-turn locked; Chromium and Firefox | JS syntax check | Authenticated staging, seeded response and previous-turn fixtures, browser install |
| GATE05 | HTTPS/hostname-allowlisted read-only GET probe with JSON digests | Mocked probe tests | Timed >=30m canary and separate verified rollback drill |
| GATE06 | Append-only JSONL hash chain, event/commit integrity, optional external HMAC attestation | Alteration, deletion, duplicate and path-escape tests | Externally anchor digest and run reviewer validation |
| GATE07 | Signed, fail-closed UAT decision evaluator requiring distinct reviewers | Adversarial gate tests | Two real reviewers, authentic external verification, signed UAT acceptance |
| GATE01 | Proof contract for exact graph/FAISS/feedback/rollback counts, tenant isolation | Gate rejects absent/fake probes | **Implement and execute actual Postgres+Neo4j+FAISS application composition** |
| A05 | Narrow YAML-indentation repair tool, non-overwriting backup | Idempotence/dry-run/rewrite tests | Apply and rerun Actions; then audit all downstream failures |

**Offline tests run:** `83` Wave 2.3 standard-library `unittest` cases, **PASS** in a Linux Python runtime; compiler and Node syntax checks. They are not the historical 109 or 112 Wave 1.9/2.0 tests, are not the repo's full test suite, and do not include actual browser/server execution. **GitHub CI did not run the Wave 2.3 code in this session.**

---

## 3. Workstream ownership and hard requirements

### Batch 0 — Unblock CI and create a reviewable branch (P0, first)

**W23-01: Apply A05 YAML correction without rewriting unrelated jobs.** From AMC repo root:

```bash
python -m tools.amc_release.cli patch-a05 .github/workflows/amc-assurance.yml
python -m tools.amc_release.cli patch-a05 .github/workflows/amc-assurance.yml --apply
```

Compare `.github/workflows/amc-assurance.yml` with its `.bak`, check YAML parsing with PyYAML or `actionlint`, and run the workflow on the exact SHA. Existing `A03` `--collect-only ... || true` masks errors and must become fail-closed for required tests. The current A03 name “Unit Tests” should not represent the complete suite unless it truly executes it. A05 SLO echo does not constitute telemetry; A06 canary echo is NOT_RUN. Distinguish `contract_test_pass` from `application_test_pass` from `UAT_READY`.

**W23-02: Create feature branch in your authorized checkout.** Suggested branch `feature/amc-wave23-uat-release-evidence` from latest reviewed `amc-dev`. This connected GitHub installation has `push:false`, so an authorized GitHub identity must perform branch creation/push. Do **not** alter `amc-dev` directly and do not force-push. Source SHA may move; rebase and regenerate all evidence if it does.

**W23-03: Restore full backend test collection and meaningful required-suite classification.** `python -m pytest tests/ --collect-only -q` must exit zero without `|| true`; separate e2e tests requiring secrets from deterministic unit tests, but never count deselected tests as passing. Record total `collected`, `passed`, `failed`, `error`, `skipped`, `deselected`. Fix failures rather than suppressing them.

**W23-04: Stabilize migration rehearsal.** Preserve Wave 2.2 restoration of migration 001–003; run `alembic heads`, `history`, `upgrade head` in a fresh disposable PostgreSQL 15 database, then a *populated historical fixture* upgrade. SQLite rehearsal is supplementary; no production downgrade. Capture schema assertions, migration revision graph and rollback strategy.

### Batch 1 — GATE01 real application composition (P0)

**W23-05:** Trace authenticated approval from `backend/app/api/routes/governance.py` to the sole journal producer and `PublicationWorker`, with outbox exactly once. Eliminate misleading legacy `ACTIVE`/verified declarations and dual writers.

**W23-06:** In a disposable Postgres + Neo4j + FAISS stack, commit real state: log `(tenant, work_id, approved_revision, idempotency_key, fence_epoch, graph_pre/post hashes, immutable vector generation ID/digest, receipt_id)`. Fetch actual graph postimage using the Neo4j read API **after** mutation; reload the exact active FAISS binary using the serving reader. Both checks must match durable effects; no synthetic receipts.

**W23-07:** Inject failures immediately before/after graph mutation, binary generation, pointer CAS, receipt commit, and rollback; kill worker and restart. Exercise two workers and stale fence. Assert one winner and no false ACTIVE. Reclaim/retry must reuse persisted original preimages.

**W23-08:** End-to-end Feedback -> Repair -> human Approval -> journal -> verified publication -> answer read -> rollback -> Feedback reopened. Verify tenant isolation with two tenants and another user's issue. Track repair→publication attribution and reason codes. **Do not use simulated graph-only tests as live GATE01 proof.**

**GATE01 acceptance:** nonzero real graph readbacks, reloaded FAISS probes, rollback drills and Feedback roundtrips; cross-tenant violations = 0; synthetic receipts = 0; exact commit and test inputs retained.

### Batch 2 — CI07, E05, CI08 and frontend browser integration (P0)

**W23-09:** Commit `.github/workflows/amc-release-verification.yml`. It supports **manual dispatch and narrowly path-filtered PR checks**, avoiding broad repeated full-repository installs while permitting validation before merging to the default branch. On a PR, `github.sha` can refer to the test merge commit; bind evidence to that exact tested SHA. Its lightweight Python evidence-tool suite runs on Windows and Linux (Python 3.11), fails on test failures, writes per-OS JUnit XML and exact-SHA JSON, and uploads artifacts. A separate, more costly **manual `full_backend=true`** matrix runs Wave 1.9/2.0, regression and fault-injection contracts on both platforms, with distinct JUnit reports. A lightweight run **does not claim** the entire backend is Windows-compatible, and cannot satisfy CI07 without full backend evidence. An authorized maintainer must dispatch it for the exact candidate SHA.

**W23-10:** Download both OS artifacts. Run `counts.reconcile` with required pairs `Linux/amc_release`, `Windows/amc_release` and confirm no skips. Add explicit manifests for each additional required backend suite as those suites run. Historical 109/112 passing test counts are references only, not a denominator for this SHA. `CI08` passes only when every required test is accounted for by suite and platform.

**W23-11:** Use `tools/amc_release/github_ci.py` after push to read actual GitHub Actions runs for the **same commit**. Any missing run, no-job run, failed/queued run or skipped *required* job blocks E05. Note: a skipped *optional* environment-only job must be represented as NOT_RUN in UAT; do not mark it PASS. Ensure public vs private GitHub token limits are handled by maintainer's read-only `GITHUB_TOKEN`.

**W23-12:** Prepare real staging fixture URLs and a disposable authenticated test account. `mf-context-engine/tests/feedback_uat.spec.mjs` uses the actual `FeedbackContainer` selectors, real `/api/feedback` POST, and previous-turn lock behavior with **no request mocks**. Run Chromium and Firefox with captured traces/JUnit. Cases cover actual submit and locked prior turns, not resolution/rollback; complete those through backend tests and UAT scripted review. No replay on production.

**W23-13:** Ensure the frontend ZIP/CI artifact does not contain `.uat-session.json`, bearer tokens or personally identifiable feedback. Secret is injected from `AMC_UAT_STORAGE_STATE_B64`, deleted after execution, and never uploaded with Playwright artifacts. Confirm application uses the staging origin. Browser omission = NOT_RUN, not green.

### Batch 3 — FB05 measured windows, GATE05 canary, GATE06 ledger (P0)

**W23-14:** Instrument HTTP requests (tenant-safe labels, duration, status codes), journal claim/retry/recovery, graph CAS failures, FAISS pointer switches, receipt verification and Feedback reopen events. For each metric publish scrape/retention/source details. Avoid sensitive labels or query text in Prometheus. Review SLO thresholds and sign them **before** assessing window PASS.

**W23-15:** Export actual staging measurement events or Prometheus observations with UTC timestamps. Run 60-minute (>=100 samples) and 1440-minute (>=1000 samples) windows; require >=95% five-minute bucket coverage, measured p95 and HTTP 5xx rate, and approved thresholds. Sparse traffic is UNKNOWN, never zero downtime. Synthetic fixtures must have `environment=simulation`, not `staging`.

**W23-16:** Perform staging-only canary with alerting, recorded baseline, canary start/end, read-only health/status probes over >=30 minutes, graph/FAISS probes, and rollback runbook. Rollback test must demonstrably restore previous **verified** graph/vector state and serving behavior. The supplied `canary.py` intentionally only performs read-only probes and **cannot** substitute for a real rollback.

**W23-17:** Write append-only JSONL release evidence with SHA chain; anchor final digest in CI or externally signed change record. Each evidence item links exact SHA, timestamps, test/trace report digest, and source class. The offline HMAC binds the fully reviewed dossier using `AMC_UAT_VERIFY_KEY` from a secret manager; a self-signed flag without actual independent review is not sufficient.

### Batch 4 — GATE07 UAT review / explicit decision (P0)

**W23-18:** Convene engineering owner and independent QA/security reviewer. Validate raw CI, PostgreSQL graph/vector records, browser artifacts, telemetry and rollback results; two reviewers with distinct identities. Obtain signoff on data handling, tenant isolation, release rollback ownership and SLO thresholds. Document any waivers with owner/expiry; unresolved P0 blocks UAT.

**W23-19:** Assemble `amc-uat-evidence-v2.3` JSON dossier with **nine** gates. Place all referenced artifacts under one evidence root. Compare SHA to checked-out candidate; no mixed SHAs. For each gate use independent immutable evidence and, after review, external HMAC attestation. The evaluator returns `UAT_READY` **only if every gate passes and HMAC verifies**. Its result is never production authorization.

**W23-20:** Run a stakeholder UAT session over staging with expected user scenarios, record issues and severity, rerun regression for all fixes. If a fix changes SHA, repeat the full exact-SHA matrix and evidence collection.

**W23-21:** Production release requires a *separate* change-management go/no-go, operations and rollback on-call, signed approval and rollout metrics. No automatic merge/deploy from this overlay.

---

## 4. Installation and reproducible execution

### A. Safe installation, Windows or Linux

Start with a local clone of the repository and the Wave 2.3 ZIP extracted to its own directory. From the extracted package root:

```bash
python install_wave23.py --repo /path/to/amc-context-engineering-poc
python install_wave23.py --repo /path/to/amc-context-engineering-poc --apply
```

On Windows PowerShell, use the same commands with a quoted absolute Windows checkout path (`C:\\...`). The installer refuses conflicting paths and **will not modify** `.github/workflows/amc-assurance.yml` without an explicit command. No repo credentials are needed for the local installation. Review `git status` and `git diff`.

### B. Offline implementation tests

From the AMC checkout root:

```bash
python -m unittest discover -s tools/amc_release/tests -t . -v
python -m compileall -q tools/amc_release
node --check mf-context-engine/tests/feedback_uat.spec.mjs
node --check mf-context-engine/playwright.uat.config.mjs
```

Wave 2.3 offline contract tests are **not** the application's integration tests. Run existing Wave 1.9/2.0 suites and full backend test collection independently, with their respective pinned Python dependency sets.

### C. Patch A05 and validate Actions YAML

```bash
python -m tools.amc_release.cli patch-a05 .github/workflows/amc-assurance.yml
python -m tools.amc_release.cli patch-a05 .github/workflows/amc-assurance.yml --apply
python -m pip install PyYAML
python -c "import yaml; yaml.safe_load(open('.github/workflows/amc-assurance.yml', encoding='utf-8')); print('YAML parsed')"
```

The A05 patch is deliberately minimal; it will not fix latent failures in required backend regression, migrations, UAT or SLO instrumentation. Inspect `.github/workflows/amc-assurance.yml.bak` locally, **do not commit the backup**.

### D. CI07 test-count evidence (after a real matrix run)

```bash
python -m tools.amc_release.cli junit reports/amc_release_Linux.xml --sha <EXACT_SHA> --os Linux --suite amc_release > reports/amc_release_Linux.json
python -m tools.amc_release.cli junit reports/amc_release_Windows.xml --sha <EXACT_SHA> --os Windows --suite amc_release > reports/amc_release_Windows.json
```

Make `reports.json` a JSON **array** containing those two generated objects, then:

```bash
python -m tools.amc_release.cli reconcile reports.json --sha <EXACT_SHA> --suite amc_release --historical 109
python -m tools.amc_release.cli github-ci --repo nusummit-spg/amc-context-engineering-poc --sha <EXACT_SHA>
```

A historical count is **metadata only**. If actual tests differ by OS, investigate platform-conditional skips rather than accepting an arbitrary denominator. The built-in GitHub collector is read-only and can use `GITHUB_TOKEN` from your local environment when required.

### E. Live staging SLOs

Input JSONL (one line per observed HTTP request):

```json
{"tenant":"staging_tenant","timestamp":"2026-11-11T10:00:00Z","latency_ms":182.4,"status_code":200}
```

Run (after a genuine telemetry export and threshold approval):

```bash
python -m tools.amc_release.cli slo /secure/staging_requests.jsonl --tenant staging_tenant --minutes 60 --min-samples 100 --environment staging --provenance live > /secure/slo_1h.json
python -m tools.amc_release.cli slo /secure/staging_requests.jsonl --tenant staging_tenant --minutes 1440 --min-samples 1000 --environment staging --provenance live > /secure/slo_24h.json
```

If observations are missing or do not cover 95% of five-minute buckets, the result is UNKNOWN. **Do not fabricate past hours or backfill metrics.** The log-based SLO is an *observed-traffic proxy*; separate synthetic probes/scrape health are necessary to validate availability during traffic-free periods.

### F. Staging read-only canary and browser tests

```bash
python -m tools.amc_release.cli canary --url https://<STAGING_HOST> --allow-host <STAGING_HOST> --path /health --path /api/health
```

The browser test configuration requires `AMC_UAT_FEEDBACK_URL`, `AMC_UAT_LOCKED_FEEDBACK_URL`, `AMC_UAT_ALLOWED_HOST`, and a local `AMC_UAT_STORAGE_STATE` JSON file. From `mf-context-engine`, run:

```bash
npm ci
npx playwright install chromium firefox
npx playwright test --config=playwright.uat.config.mjs
```

**No URL, cookie, credential or fixture is supplied in the package.** UAT should exercise a **staging** account and synthetic non-sensitive feedback; the test performs a genuine POST, so do not point it at production. Browser test execution is NOT_RUN in this session.

### G. Ledger, attestation, UAT evaluation

Produce JSON **array** of evidence events in `events.json` (keys: `id`, `sha`, `gate`, `status`, `time`, `source`, `artifact_sha256`). Then:

```bash
python -m tools.amc_release.cli create-ledger events.json evidence/release_events.jsonl
python -m tools.amc_release.cli verify-ledger evidence/release_events.jsonl
```

Place nine gate entries with evidence artifacts in `evidence_dossier.json` matching `examples/uat_evidence_blocked.json` and the `gate.py` schema. After all primary records have been reviewed and the external key is loaded in `AMC_UAT_VERIFY_KEY` from a secret manager:

```bash
python -m tools.amc_release.cli attest evidence_dossier.json signed_evidence_dossier.json --attestor <INDEPENDENT_REVIEWER>
python -m tools.amc_release.cli uat-gate signed_evidence_dossier.json --root evidence
```

The attestation key must be >=32 characters and never committed or included in shell history. **Attestation is not a substitute for actually performing review.** `uat-gate` returning `UAT_READY` means the submitted, independently attested evidence passed contract validation; final business/governance UAT still requires explicit acceptance. The CLI returns nonzero when BLOCKED.

---

## 5. Mandatory UAT scenario and negative-test matrix

| Case | Scenario | Objective / pass evidence |
|---|---|---|
| UAT-01 | Approved real Feedback repair, four-eyes | Approved revision + immutable audit; self-approval rejected |
| UAT-02 | Outbox dedupe and two workers | Exactly one claimed generation; stale fence rejected |
| UAT-03 | Graph CAS and independent readback | Exact tenant/entity/attribute values and readback digest |
| UAT-04 | FAISS immutable generation activation | Verified index bytes, exact IDs, serving reload, pointer CAS |
| UAT-05 | Kill/restart before receipt | No false ACTIVE; idempotent recovery with persisted preimages |
| UAT-06 | Rollback after partial/full effects | Restore **previous** generation and graph value; verified readback |
| UAT-07 | Feedback lifecycle | Resolve only with verified receipt; reopen on rollback |
| UAT-08 | Cross-tenant and unapproved user | No cross-tenant read/write; RBAC 403 for unauthorized actor |
| UAT-09 | CSV manifest tampering | Reject mismatched bytes/order; no unreviewed activation |
| UAT-10 | Financial NAV/AAUM correctness | Exact Decimal NAV + contributor ledger; unsafe AAUM blocked |
| UAT-11 | Browser current vs prior turn | Real 2xx persisted feedback; locked previous-turn button |
| UAT-12 | Canary rollback and telemetry | >=30m real canary, 1h/24h observed SLOs, alerts and rollback |
| UAT-13 | CI matrix and evidence chain | Windows/Linux reports, exact SHA, signed evidence, no required skips |
| UAT-14 | Vulnerability, secret and dependency audit | No critical unresolved findings, log/evidence redaction confirmed |

Every case requires `actual`, `expected`, `status`, `owner`, `timestamp`, `environment`, exact `SHA`, and report/trace link. Negative tests must fail in the expected controlled manner. 

---

## 6. Release gates and precise state semantics

- `IMPLEMENTED_LOCAL_TESTED`: code exists; offline tests pass. **Not UAT-ready.**
- `CI_VALIDATED`: required commit SHA checks ran and passed in GitHub; skips/deselected accounted for. **Not UAT-ready by itself.**
- `STAGING_VALIDATED`: real tenant-isolated graph/vector/browser/rollback + SLO evidence verified.
- `UAT_READY`: all nine gate-specific evidence entries PASS, referenced artifact hashes verify, external-key HMAC verifies, two distinct review identities are recorded, actual independent review performed.
- `UAT_ACCEPTED`: stakeholders sign off on staging behavior and open defects; requires business acceptance beyond tool gate.
- `PRODUCTION_GO`: separately approved operational change, rollback ownership, data/privacy review, SLO/on-call readiness; **never** auto-issued by this software.

**Fail-closed reasons:** `MISSING_GATE_EVIDENCE`, `EVIDENCE_COMMIT_MISMATCH`, `STALE_OR_FUTURE_EVIDENCE`, `MISSING_EVIDENCE_ARTIFACT_HASH`, `EVIDENCE_ARTIFACT_BYTES_MISMATCH`, `EXTERNAL_HMAC_NOT_VERIFIED`, `EXACT_SHA_CI_CHECKS_INCOMPLETE`, `ONE_HOUR_AND_DAY_SLO_WINDOWS_REQUIRED`, `CROSS_OS_COUNT_DRIFT`, `REAL_BROWSER_STAGING_TESTS_REQUIRED`, `REAL_CANARY_REQUIRED`, `LIVE_STAGING_INTEGRATION_REQUIRED`, plus contract-specific failures.

**Open critical risks:**

1. **GitHub permission barrier:** connected account cannot create branch/PR. The maintainer can grant this app appropriate repository write access in GitHub, or run the exact local Git commands under an authorized account. No bypass or credential exfiltration is appropriate.
2. **Broken A05 YAML and missing full-suite evidence:** latest assurance run has no jobs. Restore proper pipeline syntax, then surface latent unit/test collection and migration failures; do not hide failures with `|| true` or rename a narrow contract run as full coverage.
3. **UAT infrastructure absent here:** graph, FAISS, actual PostgreSQL worker fencing, telemetry and browser state must be independently exercised in the staging environment.
4. **Approval authenticity:** the JSON gate validates syntax, SHA, hashes and keyed attestation; it cannot, by itself, prove a human actually witnessed test execution. Preserve externally archived evidence and two real signers.
5. **Actions cost and quota:** new Windows/Linux lightweight matrix is manual or narrow-path PR-triggered, while the costly full backend matrix is manual opt-in. Trigger only when implementation stable; avoid duplicate expensive full-dependency installs for a handful of stdlib evidence tests.

---

## 7. Definition of done and UAT handover artifacts

Deliver these records under a versioned `remediation/wave2_3/evidence/<SHA>/` directory or immutable CI artifact store (remove secrets and sensitive user data):

1. `git_diff.txt` and PR link tied to exact SHA; reviews and change list.
2. `actions_runs.json`, all required workflow/job statuses and run URLs; code coverage and failure logs.
3. `junit_linux.xml`, `junit_windows.xml`, `reconciliation.json` and precise selected/skipped/deselected counts.
4. Disposable Postgres migration journal and schema assertions; Neo4j CAS/fencing traces; immutable FAISS generation and reload proof.
5. 13+ executed fault/UAT scenario reports, failure injection logs, rollback restoration proof.
6. Browser JUnit, redacted screenshots/traces (Chromium/Firefox) with seeded synthetic staging tenant.
7. SLO `slo_1h.json`, `slo_24h.json`, metrics source and signed thresholds.
8. Canary start/end report, real read-only probe receipts, rollback rehearsal, operator acknowledgment.
9. Immutable `release_events.jsonl`, external anchor, signed `evidence_dossier.json`, explicit `UAT_ACCEPTED` decision record.

**No release claim until all nine automated evidence gates are green AND business UAT has been independently accepted.**

---

## 8. One-shot Codex / local engineering agent execution prompt

> You are the accountable release engineer and test lead. Start from `nusummit-spg/amc-context-engineering-poc` `amc-dev` SHA `2c0415c4d23a3338428c8314c869299aa0ab771f`, compare current HEAD before editing, and create `feature/amc-wave23-uat-release-evidence` under an authorized GitHub credential. Integrate the attached additive Wave 2.3 overlay using the non-overwriting installer. Correct the assurance A05 YAML indentation, eliminate masked required test collection, and fix surfaced CI failures without blanket skips. Do not redesign `amc_publication`, introduce a parallel state machine, or claim that a synthetic suite proves real Neo4j/FAISS/Postgres. Run Wave 2.3 unit tests, Wave 1.9/2.0 contracts, full backend collection and required regressions. Run the manually dispatched Linux/Windows matrix on the **exact commit** and reconcile JUnit totals; any missing/failed/skipped required test blocks the release. Wire GATE01 live composition to the real authenticated approval → outbox → fenced worker → Neo4j readback → immutable FAISS activation → receipt → answer → Feedback → rollback chain using disposable services. Run Chromium/Firefox browser tests in staging with a synthetic authenticated tenant, collect 1h and 24h measured telemetry windows, exercise a >=30m staging canary and verified rollback, assemble a tamper-evident release ledger and obtain two independent reviewers. Do not store secrets in Git or commit test auth state. Push a reviewed branch and open a draft PR into `amc-dev`; do not merge or deploy automatically. Report exact commit SHA, tests collected/passed/failed/skipped, browser and infrastructure results, files changed, PR link, unresolved risks and a signed UAT/go-no-go decision. If required infrastructure or repo write permission is unavailable, produce the code and evidence you can and explicitly mark the blocked external gates NOT_RUN—not PASS.

---

## 9. Architectural recommendation beyond Wave 2.3

The project has progressed from speculative design to real implementation. The next highest-value activity is **independent end-to-end acceptance**, not a Wave 2.4 architecture rewrite. A reliable, narrow, tenant-safe publish/rollback demonstration with cost and error metrics will provide more credible proof for clients and product stakeholders than adding another parallel orchestration layer. Stabilize the graph/FAISS contract, consolidate write authority, and only then expand use cases.
