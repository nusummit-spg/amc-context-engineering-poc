# AMC Context Engineering — Wave 3.1 Local-Agent Integration Runbook

**Version:** 1.0 · **Prepared:** 12 November 2026 · **Audience:** NuSummit engineering team / local coding agent  
**Repository:** https://github.com/nusummit-spg/amc-context-engineering-poc  
**Protected integration target:** `amc-dev` — **do not commit, push, merge or deploy directly to this branch**  
**Pre-created remote feature branch:** `feature/amc-wave31-integration`  
**Required source baseline:** `2c0415c4d23a3338428c8314c869299aa0ab771f`  
**Approved cumulative archive:** `AMC_Wave3_1_Cumulative_Release_Integration_2026-11-11.zip`  
**Required archive SHA-256:** `d1a75cf4f4343a0fb2abac3f24ac7abaa09b500117180d7e3329f202777327e3`  
**End state:** source-integrated **feature branch + reproducible test evidence + draft PR (if authorized)**; **not** MVP/UAT/production signoff.

## 1. Assignment to the local agent

**Objective:** Integrate the *existing* complete Wave 3.1 cumulative overlay into the *actual* AMC application checkout. Repair source, test, migration and frontend incompatibilities discovered in the real application; run the acceptance matrix; push the approved result to **only** `feature/amc-wave31-integration`; create a **draft** PR targeting `amc-dev` if permitted. Avoid additional architecture waves or unrelated refactoring.

**Ownership:** The agent performs engineering and produces evidence. A human reviewer approves destructive steps and the final push. No automatic deployment, production migration, customer-traffic change, PR merge or UAT declaration.

**Hard rules:**

1. Never push or merge into `main` or `amc-dev`. Never force-push, reset a shared branch, or rewrite remote history.
2. Do not disable security, tenancy, authorization, governance, CI jobs or assertion failures to make tests green. Do not silently omit failing tests or mark unexecuted tests as passed.
3. Do not run prior wave installers separately. **Wave 3.1 is cumulative**. In particular, do **not** run the Wave 2.5 installer before the combined 2.5/2.6 source patch.
4. Do not run live PostgreSQL/Neo4j/FAISS mutations or Alembic migrations against production. Use disposable isolated services and synthetic/non-sensitive test data.
5. Never stage `.env`, secrets, tokens, credentials, backups (`*.wave*.bak` / `.wave*.bak`), local data/corpus, test databases, large model files or unreviewed generated outputs.
6. On a preflight mismatch, SHA drift, unexpected destination collision, partial installer result, migration divergence or new remote commits: **stop and report**, preserve evidence and do not bypass the check.
7. Do not consume GitHub Actions repeatedly. Consolidate and validate fixes locally and aim for **one reviewed push**; existing workflows may trigger automatically on feature-branch pushes.

## 2. Inputs and prerequisites

- Windows 11 PowerShell examples below; adapt paths for your workstation. **Python 3.11**, Git, Node/npm and available isolated test services. Prefer a disposable Python virtual environment.
- GitHub authorization to read the repository and push to `feature/amc-wave31-integration`; `amc-dev` remains read-only for this exercise.
- Exact cumulative ZIP above (or the companion `.zip.b64.txt` transfer file described in §3). Extract it **outside** the checkout.
- Local PostgreSQL, Neo4j and FAISS for real integration tests; if unavailable, record **NOT_RUN** explicitly and do not claim MVP readiness.
- Frontend directory is `mf-context-engine`; backend directory is `backend`.
- Keep test outputs and service logs in a sibling **evidence directory outside the repository**.

Use the following Windows PowerShell setup, adjusting only the root directory:

```powershell
$Root        = 'C:\amc-work'
$Repo        = Join-Path $Root 'amc-context-engineering-poc'
$Bundle      = Join-Path $Root 'AMC-Wave31-extracted'
$Zip         = Join-Path $Root 'AMC_Wave3_1_Cumulative_Release_Integration_2026-11-11.zip'
$Evidence    = Join-Path $Root 'evidence'
$BaseSHA     = '2c0415c4d23a3338428c8314c869299aa0ab771f'
$Feature     = 'feature/amc-wave31-integration'
$InstallerLocalBranch = 'feature/amc-release-candidate-hardening'
New-Item -ItemType Directory -Force -Path $Root,$Bundle,$Evidence | Out-Null
python --version        # Must use Python 3.11 for the release workflow
node --version
npm --version
git --version
```

If `python` is not 3.11, use an installed `py -3.11` or a Python 3.11 virtual environment consistently for **all** remaining Python commands.

## 3. Get and verify the cumulative ZIP

**Preferred:** Download the named cumulative archive from the project handoff/ChatGPT Library (not the *review* ZIP; the outer review ZIP merely contains it). Because ZIP downloads have failed in ChatGPT, a byte-for-byte Base64 **text** alternative is supplied separately: `AMC_Wave3_1_Cumulative_Release_Integration_2026-11-11.zip.b64.txt`.

If using the text alternative, put it in `$Root`, then reconstruct the original ZIP:

```powershell
$B64 = Join-Path $Root 'AMC_Wave3_1_Cumulative_Release_Integration_2026-11-11.zip.b64.txt'
[IO.File]::WriteAllBytes($Zip, [Convert]::FromBase64String([IO.File]::ReadAllText($B64).Trim()))
```

Verify SHA-256 **before extraction**:

```powershell
$Actual = (Get-FileHash -Algorithm SHA256 $Zip).Hash.ToLowerInvariant()
$Expected = 'd1a75cf4f4343a0fb2abac3f24ac7abaa09b500117180d7e3329f202777327e3'
if ($Actual -ne $Expected) { throw "ZIP SHA-256 mismatch. STOP. Actual: $Actual" }
# Bundle must be extracted only into an empty, outside-repository destination.
if (@(Get-ChildItem $Bundle -Force).Count -ne 0) { throw 'Bundle destination is not empty. STOP.' }
Expand-Archive -Path $Zip -DestinationPath $Bundle -Force
Test-Path (Join-Path $Bundle 'tools\amc_release\apply_all31.py')   # True
Test-Path (Join-Path $Bundle 'remediation\wave3_1\IMPLEMENTATION.md') # True
```

**Archive contents expected:** installer `install_wave31.py`; `tools/amc_release/apply_all31.py`; migrations 013 and 014; governance guard; release tests and manual-only CI workflows. Do not cherry-pick individual Wave ZIPs.

## 4. Clone exact repository baseline and revalidate remote feature branch

**Do not start on the pre-created remote feature branch.** The cumulative installer requires an exact, **clean `amc-dev` checkout** and creates its own *different* local branch automatically. We reconcile that local branch with the existing remote branch **after integration**, without force-push.

```powershell
Set-Location $Root
git clone --branch amc-dev --single-branch https://github.com/nusummit-spg/amc-context-engineering-poc.git $Repo
Set-Location $Repo
$Head = (git rev-parse HEAD).Trim()
if ($Head -ne $BaseSHA) { throw "amc-dev SHA drift: $Head. STOP and re-audit." }
if ((git status --porcelain).Length -ne 0) { throw 'Checkout is dirty. STOP.' }
# Remote feature branch already exists, initially based on amc-dev.
$RemoteLine = git ls-remote origin 'refs/heads/feature/amc-wave31-integration'
if (-not $RemoteLine) { throw 'Expected remote feature branch is missing. STOP.' }
$RemoteSHA = ($RemoteLine -split '\s+')[0].Trim()
if ($RemoteSHA -ne $BaseSHA) { throw "Remote feature has new commits ($RemoteSHA). STOP: reconcile, never overwrite." }
if (git branch --list $InstallerLocalBranch) { throw 'Installer branch already exists locally. STOP.' }
```

Capture `git rev-parse HEAD`, `git status --porcelain`, remote SHA and Git version in the evidence report. Never use `git reset --hard` or `git clean -fdx` on a working tree containing someone else's work.

## 5. Python environment; local dry-run before any modifications

In the new checkout, create an isolated Python 3.11 venv and install **deterministic minimum preflight dependencies first**. The complete backend requirements are larger and may need extra native dependencies and hardware; install them deliberately for the full regression stage.

```powershell
Set-Location $Repo
# Keep the virtual environment OUTSIDE the repository: preflight requires a clean Git worktree.
py -3.11 -m venv (Join-Path $Root '.venv-amc')
& (Join-Path $Root '.venv-amc\Scripts\Activate.ps1')
python -m pip install --upgrade pip
python -m pip install 'pytest>=8,<10' 'SQLAlchemy>=2,<3' 'alembic>=1.13,<2' 'PyYAML>=6' 'fastapi>=0.115'
# Run these commands FROM THE EXTRACTED BUNDLE ROOT (not checkout):
Set-Location $Bundle
python -m tools.amc_release.apply_all31 --repo $Repo --bundle $Bundle
```

**Required dry-run JSON:** `status = ALL_SOURCE_PATCHES_REHEARSED_NO_WRITES`, `sha = $BaseSHA`, source patches rehearsed, no overwrite/collision error. Save the stdout to the external evidence directory. A passing dry-run **does not** imply app integration passed.

If dry-run fails: capture the exact error and stop. Do not modify source-lock hashes or preflight rules to force it through. Investigate missing dependencies, expected source drift or safety-check failure and seek review.

## 6. Apply the cumulative package — exactly once

Run only after the no-write preflight is accepted:

```powershell
Set-Location $Bundle
python -m tools.amc_release.apply_all31 --repo $Repo --bundle $Bundle --apply
```

**Important implementation detail confirmed from the bundled source:** `apply_all31` calls Wave 3.0/2.9 bootstrap and **creates `feature/amc-release-candidate-hardening` locally**, not `feature/amc-wave31-integration`. It does **not** accept a `--branch` flag. Do not add a fictitious flag or run `apply_all29.py` separately.

After applying:

```powershell
Set-Location $Repo
git branch --show-current             # expected: feature/amc-release-candidate-hardening
git status --short
git diff --stat
git diff --check
```

Expected successful apply status: `LOCAL_BRANCH_UNCOMMITTED_OFFLINE_TESTED_ONLY`. A result beginning `BLOCKED`, a nonzero exit, or `BLOCKED_PARTIAL_BRANCH` means **incomplete installation**; leave the tree in place for forensic review. Do not rerun the installer blindly on the dirty/partial branch.

Inspect and relocate/delete only the generated `.wave*.bak` backups **after** comparing them with source patches; do not stage those files. Inspect every modified original file against the baseline and verify all additions, including governance, ingestion, journal, status routes, request fences, FAISS reader and Alembic chain.

**Branch reconciliation:** Once application fixes and checks are complete and before committing, rename the *local* installer branch to the existing *remote* feature branch name:

```powershell
Set-Location $Repo
if ((git branch --show-current).Trim() -ne $InstallerLocalBranch) { throw 'Unexpected local branch. STOP.' }
git branch -m $Feature
# This renames only the LOCAL branch; the remote branch is not modified.
```

## 7. Required tests and engineering remediation

Do not stop after the bundled tests. The agent must run application-wide verification in phases and **fix legitimate code defects** in the integration branch, preserving the intended publication/receipt/authority design.

**A. Source inspection and Wave 3.1 regression:**

```powershell
Set-Location $Repo
python -m compileall -q backend
python -m tools.amc_release.qualification31 --repo . --out (Join-Path $Evidence 'wave31_source_qualification.json')
python -m tools.amc_release.run_wave31_tests --root . --out (Join-Path $Evidence 'wave31_release_controls.json')
python -m tools.amc_release.run_wave31_tests --root . --full-backend --out (Join-Path $Evidence 'wave31_full_backend.json')
```

The runner's status `PASS_OFFLINE_CONTROLS_ONLY` is an unfortunately broad label even for its `actual_checkout` mode. Inspect `mode`, each stage's `exit_code`, nonzero test-case counts and JUnit files. **Never interpret that label as deployment/UAT acceptance.** `--full-backend` includes test collection and `backend/tests -m 'not e2e'`; execute the excluded real e2e suites separately in a suitable environment.

For full dependencies, use the checked-out `backend/requirements.txt` in the isolated environment and record installation conflicts rather than hiding or rewriting constraints without justification. Known possible blockers include Python/native-library compatibility and historical `feedback_loop` import failures.

**B. Frontend contracts and build:**

```powershell
Set-Location (Join-Path $Repo 'mf-context-engine')
# Use npm ci ONLY if a lockfile is committed; otherwise use npm install and review any lockfile changes.
if (Test-Path '.\package-lock.json') { npm ci } else { npm install }
npm test
npm run build
npm run lint
# Browser UAT requires a reachable, isolated test backend and valid fixtures:
# npx playwright test --config playwright.uat.config.mjs
```

If the existing repository has no usable lockfile, use `npm install`, record that change and review it. Report Playwright as `NOT_RUN` when backend/fixtures are unavailable; syntax/build success is not a browser pass.

**C. Alembic and database correctness (disposable environments only):**

- Inspect migration DAG from `001` through `012`, then new `013_active_receipt_authority_v28` and `014_publication_scope_claim_v31`. Check `revision`/`down_revision` links and obtain **one correct head**.
- Run `python -m alembic -c alembic.ini heads`, `history`, `current`, then `upgrade head` **inside `backend/`** against a brand-new **disposable SQLite DB** and a **disposable PostgreSQL DB** using the project's verified Alembic configuration. Record schema diffs and errors. Review `.env`/`alembic/env.py` settings so the CLI cannot point to production by accident.
- Do not stamp missing revisions, rewrite historical migrations, auto-backfill ambiguous publication receipts or downgrade production. Missing ancestor errors must be repaired correctly and tested from a clean database.

**D. Runtime/backend matrix — run with real disposable PostgreSQL, Neo4j and FAISS:**

| Area | Minimum acceptance cases | Evidence |
| --- | --- | --- |
| Publication and first-publisher claim | Two simultaneous publishers, first-ever tenant authority, same-work replay, competing-work rejection, crash between preimage and graph mutation, durable HELD claim, safe compensation | Repeatable multi-connection test and DB state before/after |
| Graph/FAISS consistency | Neo4j preimage and CAS/readback, real persisted FAISS index reload, vector ID mapping, receipt and pointer race, rollback/suspension between read and delivery | Test logs, immutable generation/receipt identifiers |
| Legacy mutation denial | `/api/governance/promote`, file/batch ingestion, pipeline and direct VectorStore methods blocked when `AMC_VERIFIED_SERVING_MODE=enforce`; test alternate admin/background routes | Negative tests: no unauthorized graph/vector effects |
| Verified serving | Every traditional, graph, RAG, cached and streaming route verifies tenant/work/receipt/generation authority; streaming revocation and cache invalidation | Route inventory + deny/succeed tests |
| Human feedback and repair | Approval ledger, four-eyes review, correction/review provenance, idempotent replay, negative permission cases | API/e2e test IDs and audit receipts |
| CSV/PDF/TXT question answering | Grounded answers, row citations, schema-aware aggregation, malformed CSV, cross-tenant leakage, no hallucinated source | Golden dataset with pass/fail examples, accuracy and provenance metrics |
| Security/economics/operations | Tenant isolation, JWT roles, injection resistance, bounded resource usage, failure recovery, latency, cost/token metrics | Security tests and measured baseline |

Use `AMC_VERIFIED_SERVING_MODE=off` for legacy compatibility tests, then activate `enforce` **only in isolated staging** after migrations, write boundaries and negative tests pass. Every failure should generate a minimal reproduction and a targeted regression test; fix code, not evidence.

**E. GitHub Actions review:** The baseline `amc-assurance.yml` failed with **zero jobs** while Publication V2 and Quality V2 contracts passed. Ensure Wave 3.1's source-locked assurance YAML repair results in parsable workflows with actual jobs and fail-closed test commands. Current workflows have `push` triggers for feature branches; avoid repeated trial pushes. Once pushed, collect *real* Actions run IDs and passing/non-skipped job counts for the feature commit. Some added workflows are `workflow_dispatch` only and should not be invoked without a deliberate test-budget decision.

## 8. Commit and push safely (one reviewed push)

**Prerequisites:** clean code diff review; all available local tests completed; failed/NOT_RUN gates identified; no secrets/backups; the existing remote feature branch must **still equal `$BaseSHA`** before pushing. A feature-branch push is allowed with outstanding **documented** live-service blockers, but it must not be represented as UAT-ready.

```powershell
Set-Location $Repo
$RemoteLine = git ls-remote origin 'refs/heads/feature/amc-wave31-integration'
if (-not $RemoteLine) { throw 'Remote feature branch disappeared. STOP.' }
$RemoteSHA = ($RemoteLine -split '\s+')[0].Trim()
if ($RemoteSHA -ne $BaseSHA) { throw "Remote branch advanced to $RemoteSHA. STOP; review changes." }
if ((git branch --show-current).Trim() -ne $Feature) { throw 'Wrong local branch. STOP.' }
git status --short
# Remove generated backup, local environment and accidental data files BEFORE staging.
# Only after manual allowlist review:
git add -A
git diff --cached --name-status
git diff --cached --check
# STOP if staged paths include secrets, backups, customer documents, model/cache weights or unreviewed test evidence.
git commit -m "Integrate Wave 3.1 publication authority and verified serving controls"
git push --set-upstream origin feature/amc-wave31-integration
```

Never use `--force` or `--force-with-lease` to mask branch drift. A non-fast-forward error is a review event, not a reason to retry forcefully. `git push` can start several automatically configured Actions workflows; obtain any required organization approval before consuming GitHub Actions minutes.

If authorized and integration is reviewable, create a **draft**, never auto-merged PR:

```powershell
# Requires GitHub CLI `gh` authenticated with the authorized org account:
gh pr create --draft --base amc-dev --head feature/amc-wave31-integration `
  --title 'AMC Wave 3.1: cumulative integration and runtime assurance' `
  --body 'Engineering source integration. Full service/staging UAT remains blocked until evidence gates pass.'
```

If `gh` is unavailable, provide the branch URL and request a draft PR via GitHub UI. No merge or deployment.

## 9. Required deliverables from the local team

Return a **single final handoff**, not many incremental partial packages:

1. Feature branch URL, **full commit SHA**, draft PR URL (if created), base SHA, who approved the push, and exact source ZIP checksum.
2. Integration changes: changed-file list and short summaries grouped by source/CI/migrations/frontend; all unexpected source edits and resolved merge/collision issues.
3. Test inventory: test commands, environment/versions, test counts, JUnit/JSON evidence and per-gate `PASS`, `FAIL`, `BLOCKED` or `NOT_RUN` with failure logs. **No numeric claims without artifacts.**
4. Alembic DAG and disposable SQLite/PostgreSQL migration reports; Neo4j/FAISS/streaming and first-publisher concurrency results; explicit missing-service blockers.
5. CSV/PDF/TXT golden examples with grounded answer/source-quality results, plus security and governance negative-case evidence.
6. GitHub Actions run URLs, workflow job counts and specific outstanding failures; no masked or skipped required jobs counted as pass.
7. `P0/P1/P2` issue register: ID, reproduced symptom, root cause, affected component, resolution commit or **remaining blocker**, acceptance test and owner.
8. CTO decision: **ENGINEERING_INTEGRATED / INTEGRATION_BLOCKED** and independent **MVP_READY / NOT_READY**; preserve **UAT_BLOCKED** unless separate live-service and staging acceptance is formally completed.

### Suggested compact handoff summary

```text
Repository:
Baseline SHA:
Integration branch / commit:
PR URL:
Wave ZIP SHA-256:
Cumulative preflight status:
Installer result:
Full backend tests: PASS/FAIL/NOT_RUN (counts + artifact)
Frontend tests: PASS/FAIL/NOT_RUN (counts + artifact)
Migration DAG SQLite / PostgreSQL:
Neo4j + FAISS + concurrent publication:
CSV/PDF/TXT golden answers:
Security, tenancy, approval and bypass tests:
GitHub Actions status / run URLs:
P0 blockers remaining:
P1 blockers remaining:
Deployment/UAT actions performed: NONE unless separately approved
CTO decision:
```

## 10. Stop conditions and handoff escalation

Stop and request CTO review if any condition occurs: archive SHA mismatch; `amc-dev` or remote feature branch SHA drift; unexpected Git overwrites; dry-run not `ALL_SOURCE_PATCHES_REHEARSED_NO_WRITES`; partial installer branch; failed Alembic lineage; ungoverned graph/FAISS writes; cross-tenant leakage; unverified active publication/receipt or streaming revocation; broad failing backend test collection; secrets in staged files; unexpected Actions spending; any live/production configuration or data implicated.

**Success criterion for this task:** feature branch contains source-reviewed, application-integrated Wave 3.1 code plus reproducible test evidence and an explicit list of any outstanding infrastructure/UAT gates. **A pushed branch is not evidence that the AMC MVP is ready.**