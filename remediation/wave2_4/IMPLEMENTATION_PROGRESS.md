# AMC Context Engineering POC — Wave 2.4 Local Engineering Handover

**Date:** 2026-11-11 (Asia/Kolkata)  
**Repository:** https://github.com/nusummit-spg/amc-context-engineering-poc/tree/amc-dev  
**Reviewed baseline:** `2c0415c4d23a3338428c8314c869299aa0ab771f`  
**Connected GitHub identity:** `annapurnaagenticsolutions` (`pull=true`, `push=false`)  
**Execution mode:** Offline cumulative implementation overlay; **no branch, push, PR or deployment**.  
**Release/UAT status:** **BLOCKED** pending exact-commit full integration, infrastructure, observed staging evidence and two-person review.

## 1. Executive engineering decision

Wave 1.9 and 2.0 implement the publication journal and data-integrity reference modules. Wave 2.3 provides release evidence controls. Wave 2.4 extends them and addresses measurable correctness gaps, **without a new publication state machine**. Its content is designed to be installed into one authorized feature branch, reviewed, and then exercised against *actual* AMC runtime services. The package is cumulative: do not install Wave 2.3 first and then blindly overwrite it with Wave 2.4.

**Observed exact-commit GitHub CI:** `AMC Publication V2 Contract Tests` PASS (run `43005484510`), `AMC Quality V2 Contract Tests` PASS (run `43005484468`), AMC Assurance workflow no jobs / FAIL (run `43005482561`). There is an indent error at A05 `Run fault injection tests`; the tool `harden-assurance` addresses that exact source pattern. It also fixes silent pytest collection masking and converts fake-positive SLO/canary stubs into explicit CI blockers. This patch has **not** been run against a live GitHub Actions runner.

## 2. Delivered code — owner and acceptance

| Task | Concrete local implementation | Offline verification | Still required before UAT |
|---|---|---|---|
| GATE01 | `tools/amc_release/composition.py` read-only cross-store audit: tenant/work/receipt/effect/pointer graph readback + artifact verification; refuses fake adapters or absent real serving-reader probe | SQLite + in-memory graph/snapshot adversarial tests | Wire real Postgres/Neo4j/FAISS and actual serving reader; 2-worker fencing and crash recovery |
| GATE05 | `canary.py` safe HTTPS origin/GET whitelist, redirect prevention, unhealthy response rejection; `rollback.py` three-phase graph/vector/reader consistency validator | Mocked HTTPS and synthetic rollback tests | Real >=30m canary, independently observed rollback receipt, zero tenant bleed |
| GATE06 | Wave 2.3 hash-chained JSONL evidence ledger and external-anchor contract retained | Tamper, deletion and duplicate-event tests | Immutable external anchor and artifact-digest verification |
| GATE07 | Wave 2.3 UAT gate strengthened: includes checked rollback evidence and full CI/test identity requirements | Signed synthetic dossier, negative gate tests | Two actual reviewers + separate production change approval |
| FB05 | `slo.evaluate_pair()` computes 1h and 24h from same timestamped event stream; UAT gate rejects missing/stale/mixed-tenant/incorrectly bounded windows | Sparse/future/incorrect-time/cross-tenant tests | Real authenticated telemetry provenance, approved SLO limits, observation coverage |
| FB06 | 7 Node `api.contract.test.js` assertions against existing `api.js` when installed; Playwright suite expanded from 2 to 5 real staging scenarios | JS syntax checked; API tests require checkout | Run Node contract tests against actual app source and authenticated Chromium+Firefox Playwright on staging |
| CI07 | Windows/Linux evidence matrix extended with frontend API tests; composition audit included in opt-in full-backend job; lightweight job excludes SQLAlchemy-dependent integration test | Workflow YAML parsing and Python syntax | Dispatch full_backend=true on exact branch SHA; both platforms pass |
| E05 / GATE04 | Existing read-only GitHub Actions collector refuses missing/jobless/skipped workflows; UAT gate now requires positive run IDs and job counts | Mocked API and gate tests | Collect actual four named workflows at *new* SHA after push |
| CI08 / A09 / E06 | `counts.py` validates JUnit root/nested summary totals, hashes sorted identities, catches equal-count-but-different-test drift, requires full 2 OS × 2 suite inventory | Adversarial JUnit tests | Reconcile real immutable JUnit artifacts from CI; historical 109/112 not acceptance denominators |
| A03/A05/A06 | `assurance_ci.py` narrow non-overwriting source patch for malformed YAML, ignored collect-only failures and simulated-success placeholders | PyYAML parsing and idempotence/backup tests | Review diff and re-run real Actions; no masking failing jobs |

## 3. Precisely what was tested

- **134 Wave 2.4 cumulative offline tests passed** under Python 3.13.5 on Linux. Included 11 composition tests based on isolated Wave 1.9's actual SQLAlchemy models and worker, with simulated data. Includes the 83 older Wave 2.3 tests plus new contract/hardening cases.
- **112 historical independent Wave 1.9/2.0 Python tests** rerun in the same sandbox after extracting the earlier ZIP packages; combined result **246 passed, 16 subtests passed**. These are previous standalone implementations, **not** the latest GitHub checked-out runtime and **not** UAT evidence.
- JS API tests and Playwright scripts passed `node --check` syntax validation, **but did not execute against the actual repo `api.js` or a browser** (no live checkout/browser fixtures here).
- The new verification workflow YAML parsed using PyYAML; Python modules passed compilation.
- No real CI run, Windows runner, PostgreSQL two-worker run, Neo4j CAS, FAISS binary/reader reload, telemetry scrape, staging canary, deployed browser, or independent human signoff ran in this environment.

A test failure is never changed into a green result by dropping it from counts. The lean CI07 matrix intentionally excludes the composition test requiring the application graph/model dependencies, but the **full_backend** suite includes it and must run for UAT.

## 4. Apply all pending local code in one branch — Windows PowerShell

1. In your **authorized** checkout, ensure `amc-dev` HEAD is reviewed and you have a clean worktree. The handoff baseline SHA may no longer be HEAD, in which case review the delta before applying the overlay.

```powershell
cd C:\path\to\amc-context-engineering-poc
git fetch origin
git switch amc-dev
git pull --ff-only
git switch -c feature/amc-release-candidate-hardening
```

2. Extract the **Wave 2.4 cumulative ZIP** to a different directory. Run its `install_wave24.py` (dry-run first, then apply) with the path to your local checkout. The installer **refuses overwrites**, checks for symlink/path escapes and leaves the original assurance workflow unchanged.

```powershell
py -3.12 C:\path\to\Wave2.4\install_wave24.py --repo .
py -3.12 C:\path\to\Wave2.4\install_wave24.py --repo . --apply
```

3. Apply the **reviewed** assurance workflow change in the feature branch. The patch is intentionally fail-closed if the source no longer matches the audited anchors; it creates a `.bak` that must **not** be committed.

```powershell
py -3.12 -m tools.amc_release.cli harden-assurance .github/workflows/amc-assurance.yml
py -3.12 -m tools.amc_release.cli harden-assurance .github/workflows/amc-assurance.yml --apply
py -3.12 -m pip install pytest sqlalchemy alembic pyyaml
$env:PYTHONPATH = (Resolve-Path backend).Path
py -3.12 -m pytest -q tools/amc_release/tests
node --test mf-context-engine/src/services/api.contract.test.js
node --check mf-context-engine/tests/feedback_uat.spec.mjs
```

4. Then execute **existing repo tests** on their own and in aggregate; do not reuse the 246 sandbox total as the complete codebase total. Run actual backend requirements in a fresh virtual environment, avoid system Python package contamination, and inspect pytest collection errors/skip counts before asserting success.

5. On Unix/macOS the same commands use `python`, `PYTHONPATH=backend` and Bash. Run `git status`, `git diff --check`, inspect all changed files and confirm `.bak`, `.uat-session.json`, tokens and customer files are excluded.

6. Once authorized, push only the feature branch and open a PR targeting `amc-dev`. **Do not merge to `main`** as part of automated acceptance. Suggested commands:

```bash
git add .github/workflows/amc-assurance.yml .github/workflows/amc-release-verification.yml mf-context-engine/ tools/amc_release/ remediation/wave2_3/ remediation/wave2_4/ examples/uat_evidence_blocked.json
git commit -m "test(assurance): integrate Windows/Linux evidence, rollback and UAT safeguards"
git push -u origin feature/amc-release-candidate-hardening
```

Note that the cumulative installer still uses the Wave 2.3 package's additive path list plus Wave 2.4 additions; install in a clean feature branch. If a previous Wave 2.3 overlay is already present, **review its files and hand-merge the delta** rather than overriding edited files.

## 5. Exact-SHA release execution (after code integration)

Run `.github/workflows/amc-release-verification.yml` via **workflow_dispatch** with `full_backend=true` for actual CI07 and CI08. This consumes Windows and Linux Actions minutes; manual opt-in is deliberate. Run `AMC Assurance Pipeline` with an actual infrastructure/metrics configuration. If A05/A06 are not backed by real instrumentation, the hardened job should **fail**: that is correct. The other publication/quality workflows must also pass at the same SHA.

From a local checkout with a legitimate JUnit report per OS and suite:

```bash
python -m tools.amc_release.cli junit reports/amc_release_Linux.xml --sha EXACT_SHA --os Linux --suite amc_release
python -m tools.amc_release.cli junit reports/backend_contracts_Windows.xml --sha EXACT_SHA --os Windows --suite backend_contracts
python -m tools.amc_release.cli reconcile reports_matrix.json --sha EXACT_SHA --suite amc_release --suite backend_contracts --historical 109
python -m tools.amc_release.cli github-ci --repo nusummit-spg/amc-context-engineering-poc --sha EXACT_SHA
```

Ensure `reports_matrix.json` contains all **four** normalized reports. Test identity fingerprints must match across platforms for a given suite, not just total counts.

## 6. Staging acceptance — the non-negotiable remaining tasks

**GATE01 real systems:** Configure a disposable tenant with approved source; run real PostgreSQL migrations, concurrent worker fence/stale-owner and kill/restart tests; execute graph CAS + independent Neo4j readback; build and activate actual FAISS generation; reload the *serving* reader and prove exact tenant/IDs/checksum; resolve Feedback only after verified receipt. `composition.inspect(..., mode='live', reader_probe=<actual_reader_callback>)` additionally checks cross-store records and returns PASS only with real Neo4jGraphPort and FaissGenerationStore adapters. All other modes are simulation-only.

**GATE05 live canary & rollback:** Collect before/published/after_rollback observations, including graph hash, FAISS generation and *serving* reader generation. Run `rollback-proof <evidence.json> --sha EXACT_SHA` and separately prove ≥30-minute nontrivial canary. The validator checks consistency; authentic observations and trace/file anchors must be reviewed independently. The read-only `canary` CLI allows only `/health`, `/api/health`, `/api/status`, `/api/query/health`, and tenant-safe `/api/publication/status/<work_id>` paths on one explicit HTTPS host and cannot deploy/rollback.

**FB05 SLO:** Export immutable **live staging** request events with `tenant`, UTC `timestamp`, `latency_ms`, and `status_code`. Calculate both windows from one event file:

```bash
python -m tools.amc_release.cli slo-pair staging_events.jsonl --tenant staging-tenant --environment staging --provenance live > slo_pair.json
```

This checks measured request p95/5xx and five-minute bucket coverage; a quiet period is UNKNOWN, not proof of uptime. Compare with actual Prometheus/synthetic availability probes. Approval requires separate operator-reviewed threshold policy. Both windows must end near the UAT review time.

**FB06 browser:** Provide a staging-only authenticated storageState, URLs with current-turn and previous-turn feedback, real feedback test fixture, and run Playwright **Chromium+Firefox** without intercepting network. Five scenarios: actual submitted receipt; previous turn locked; blank feedback can't submit; taxonomy select/clear gating; 2000-character limit. Separately execute 7 Node API contract tests against the repo's real `api.js`. Ensure no secret session JSON enters CI artifacts.

**GATE06/GATE07:** Hash the actual reports into the immutable evidence ledger, anchor the final digest externally, collect exact-SHA jobs/report URLs and 2 distinct reviewer approvals, verify the `AMC_UAT_VERIFY_KEY` external HMAC and run `uat-gate`. If any gate missing, the answer must remain BLOCKED. UAT_READY is not production authorization.

## 7. Remaining hard blockers versus local completion

| Item | Status after this handoff | Owner/action |
|---|---|---|
| Release-control implementation | **LOCAL_TESTED** (not pushed) | Code package ready for authorized branch |
| Assurance A05 YAML fix | **IMPLEMENTED, PENDING_APPLY** | Run `harden-assurance`, inspect diff, execute CI |
| A03 full pytest collection | **PENDING_REAL_REPO_RUN** | Fix all import errors; keep collector fail-closed |
| CI07/E05/CI08 exact-SHA Windows/Linux/full backend | **NOT_RUN** | GitHub write access / Actions minutes |
| GATE01 real PostgreSQL+Neo4j+FAISS reader | **NOT_RUN** | Staging infrastructure and integration wiring |
| FB05 1h/24h SLOs from live telemetry | **NOT_RUN** | Observability integration and 24h data window |
| GATE05 canary, real recovery and rollback | **NOT_RUN** | Operator-controlled staging deploy |
| FB06 frontend Node against repo and browser tests | **NOT_RUN** | Checkout and staging browser fixture |
| GATE06 externally anchored ledger | **NOT_RUN** | CI artifact store / security reviewer |
| GATE07 human UAT go/no-go | **NOT_RUN** | Independent engineering & QA/security signoff |

**Do not request user UAT yet.** Keep the candidate engineering-owned until all automated and environmental gates have independent evidence on the exact new SHA. The remaining work cannot truthfully be marked complete by local simulated tests or synthetic signatures.

## 8. Codex work order once GitHub access is granted

1. Verify `git status` and SHA; create feature branch.
2. Install Wave 2.4 cumulative overlay dry-run/apply; inspect diff.
3. Apply assurance workflow hardening and lint Actions syntax (including real `actionlint`).
4. Run API Node tests and all new Python contracts; fix any latest-repo compatibility divergences.
5. Run full `pytest --collect-only` without filters or `|| true`, then the complete backend suite.
6. Wire trusted graph and FAISS reader probes through the existing `Journal`/`PublicationWorker`, without adding another worker/state machine.
7. Configure disposable PostgreSQL/Neo4j/FAISS fixtures and execute 2-worker/stale-fence/restart/rollback tests.
8. Provide real SLO event exports, browser fixture and 30-minute canary; collect actual receipts.
9. Dispatch matrix `full_backend=true`; verify Windows/Linux identity hashes and exact-SHA job results.
10. Anchor evidence, sign by 2 independent reviewers, and run UAT gate; resolve P0 findings before UAT handover.

**Hard stop:** The team must never promote a simulated graph, JSON-only FAISS artifact, a `status='approved'` patch, missing metrics, skipped CI job, or a manually asserted "PASS" into an ACTIVE serving publication or UAT-ready designation.
