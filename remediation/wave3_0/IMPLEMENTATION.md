# AMC Wave 3.0 — Source Integration, Recovery-Race Closure and CI Stabilization

**Reviewed repository:** `nusummit-spg/amc-context-engineering-poc`, branch `amc-dev`  
**Exact source baseline:** `2c0415c4d23a3338428c8314c869299aa0ab771f`  
**Prepared:** 11 November 2026  
**Stage:** Local implementation COMPLETE; full repository integration and production acceptance **NOT RUN**.  
**Release decision:** **BLOCK**. No GitHub write, deployment, live-service acceptance, or UAT authorization was performed.

## 1. High-impact changes completed

| ID | Area | Change | Evidence and limitation |
|---|---|---|---|
| R30-01 | Durable publication replay | Existing authority-preimage replay now requires ownership of the original suspended work and matching previous receipt. Rejects ACTIVE or third-party suspension, missing prior authority and unrelated pointer drift. | SQLite-backed adversarial tests; actual PostgreSQL concurrency not run. |
| R30-02 | Loaded FAISS readback | FAISS search checks ACTIVE receipt sidecar after the physical index search, not only the pointer and receipt. Rejects suspension or receipt substitution during search. | Mock physical FAISS search plus real resolver contract; live FAISS not run. |
| R30-03 | Vector bridge race | Pins tenant authority before retrieval and again after all filtering. Detects rollback or replacement occurring between FAISS read and result delivery. | Async adversarial tests; real network delivery race not eliminated. |
| R30-04 | Atomic integration preflight | Rehearses source-locked combined 2.5/2.6 → 2.7 → 2.8 → 2.9 → CI30 sequence in a disposable shadow tree, before any branch creation. Refuses dirty checkout, incorrect commit, changed source blobs, unsafe paths and existing target branches. | Standalone fail-closed tests; full real checkout not mounted. |
| R30-05 | Assurance workflow repair | Source-locked fix for invalid A05 YAML indentation; removes masked `pytest --collect-only`; converts placeholder SLO and canary checks to hard failures. | YAML validation and functional transformation tests, no GitHub Actions execution. |
| R30-06 | Reviewable integration bootstrap | `apply_all30` adds mandatory preflight, runs the existing cumulative patch chain once, adds Wave 3.0 files, and tests on the local branch without committing or pushing. Reports partial application honestly. | Dry-run/negative tests; no full repo branch created. |
| R30-07 | Read-only release inspection | `qualification30` audits required source markers, migration, workflow, uncommitted backups and real branch identity. No synthetic green gate for live services. | Fail-closed local tests. |
| R30-08 | Cross-platform qualification definition | Manual-only GitHub workflow with Windows/Linux tests, SHA check and optional full backend. Avoids automatic Actions-minute use. | YAML validated; no workflow run. |

## 2. Package composition

This is a **cumulative** source/test overlay: Waves 2.3–3.0, plus the historical 1.9/2.0 reference test fixtures. The three existing additive-source modules upgraded by Wave 3.0 are:

- `backend/amc_publication/active_authority28.py`
- `backend/amc_publication/faiss_reader27.py`
- `backend/amc_publication/vector_bridge28.py`

The cumulative installers copy the latest versions from this archive. **Do not apply a Wave 2.5 patch independently before the Wave 2.6 combined patch.**

New branch-integration utilities:

- `tools/amc_release/preflight30.py`: no-write rehearsal of source locks and cumulative source edits.
- `tools/amc_release/apply_all30.py`: gated local branch bootstrap, without commit/push/deploy.
- `tools/amc_release/assurance30.py`: reviewed exact-blob CI repair.
- `tools/amc_release/qualification30.py`: source and release-evidence audit.
- `install_wave30.py`: additive-only cumulative installer.

## 3. Local execution on the **actual** AMC checkout

**Prerequisites:** Python 3.11, Git, a clean checkout at exactly `2c0415c4...`, the complete cumulative archive extracted **outside** the repo, and required Python dependencies for the backend tests. Do not activate verified serving on live traffic at this stage.

Linux/macOS:

```bash
# In the extracted Wave 3.0 archive:
python -m tools.amc_release.apply_all30 --repo /path/to/amc-context-engineering-poc --bundle .
# Review dry-run; it must say ALL_SOURCE_PATCHES_REHEARSED_NO_WRITES.
python -m tools.amc_release.apply_all30 --repo /path/to/amc-context-engineering-poc --bundle . --apply

# From your real checkout, after reviewing the changes:
python -m tools.amc_release.qualification30 --repo . --out wave30_qualification.json
python -m pytest backend/tests/ --collect-only -q
python -m pytest backend/tests/ -q --junitxml=wave30_full_backend.xml
```

Windows PowerShell:

```powershell
# Run from the extracted Wave 3.0 archive, NOT from the existing AMC repo.
python -m tools.amc_release.apply_all30 --repo C:\path\to\amc-context-engineering-poc --bundle .
python -m tools.amc_release.apply_all30 --repo C:\path\to\amc-context-engineering-poc --bundle . --apply

# In the real checkout:
python -m tools.amc_release.qualification30 --repo . --out wave30_qualification.json
python -m pytest backend/tests/ --collect-only -q
python -m pytest backend/tests/ -q --junitxml=wave30_full_backend.xml
```

**Important:** `apply_all30` creates a **new local feature branch** only after all source transformations successfully pass the no-write preflight. It does not stage, commit, push or deploy. The previous patchers may write `.wave*.bak` backups; these must be reviewed and moved out of the repository before committing. A failure leaves a blocked branch for manual inspection. Do not run it twice blindly.

**Do not re-run `install_wave25.py`, `install_wave26.py` or another prior patcher separately after this command.** Do not commit backup files, generated fixtures, private data or local credentials.

## 4. Offline validation in this archive

```bash
# Linux/macOS from extracted package root
PYTHONPATH=test_support/wave30_fixture/backend:.:backend python -m pytest -q \
    tools/amc_release/tests_wave28 tools/amc_release/tests_wave29 tools/amc_release/tests_wave30
PYTHONPATH=.:test_support/baseline/backend python -m pytest -q \
    tools/amc_release/tests \
    test_support/baseline/backend/tests/test_wave19_*.py \
    test_support/baseline/backend/tests/test_wave20_*.py
```

Two processes are intentional: the fixture distributions model different source phases and must not share Python module state. These commands exercise a **synthetic local fixture** rather than the complete current application.

## 5. No-go gates still owned by engineering, not UAT

1. **Full checkout integration:** First execute Wave 3.0 on the real repo's exact source commit. Review actual diffs, clear backup files, run import/collection and full tests. No result inferred from local historical fixtures.
2. **Real PostgreSQL:** Execute Alembic `upgrade`, `current`, `downgrade` and re-upgrade on disposable PostgreSQL; test concurrency and crash recovery under multiple workers.
3. **Real Neo4j/FAISS:** Validate immutable binary construction, graph CAS and independent readback, artifact activation, reader reload, rollback, stale receipt revocation and tenant separation.
4. **Frontend:** Run npm clean install, lint/build, API contract tests and authenticated Playwright scenarios against staging.
5. **CI:** Collect exact-SHA Windows/Linux JUnit evidence from a deliberately triggered manual workflow. The existing assurance CI has a source-locked repair, not a simulated run.
6. **Live observability:** Capture measured 1-hour and 24-hour SLO windows, canary/rollback proof, source-linked telemetry and a verifiable evidence anchor.
7. **Approval:** Obtain security/privacy signoff and an independent, explicit go/no-go decision **before** UAT.

The user currently controls a **different GitHub account** from the connected `annapurnaagenticsolutions` account; the connector reports pull permission but **push=false**. Until repository write access or a full checkout is supplied, no branch or PR can be created in GitHub by this agent.

## 6. Key technical caveats

- A readback check after FAISS search reduces a race; it cannot guarantee that rollback will never occur between the last check and a network write without a coordinated read lease / fencing protocol. Exact UAT acceptance must measure this behavior with concurrent requests.
- The original FAISS reader is still an in-process index. Verified serving and ingestion must remain separated; the Wave 2.9 quarantine does **not** constitute an approved, complete corpus.
- The authoritative generation sidecar is only effective when every answer path, cache, streaming path and direct read is routed through the verified bridge/fence.
- The source-pinned patch chain may intentionally refuse if `amc-dev` changes. Do not bypass checks or use `skip_reviewed_sha` to force deployment.

## 7. Acceptance and handover

**Locally implemented:** Wave 3.0 race fixes, CI hardening, integrated source preflight, additive installer, branch bootstrap and read-only qualification tooling.

**Locally verified:** Wave 3.0 and previous offline suites; see `TEST_EVIDENCE.json` and ZIP checksums.

**Not accomplished:** Actual repository patching, GitHub push/PR, full app integration tests, live multi-store qualification, production canary, signed approval and UAT release.

**Decision:** Keep release and UAT **BLOCKED** until the gates above are all evidenced on one exact feature-branch commit.
