# AMC Context Engineering — Wave 2.6 cumulative implementation and integration handoff

**Date:** 11 November 2026 (Asia/Kolkata)  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Reviewed remote:** `amc-dev` at `2c0415c4d23a3338428c8314c869299aa0ab771f`  
**GitHub account currently connected:** `annapurnaagenticsolutions`, **pull=true / push=false**  
**Release/UAT:** **BLOCK — not approved, not deployed**.

## 1. Executive summary and engineering decision

This is the cumulative **Wave 2.3 + 2.4 + 2.5 + 2.6** release-control overlay, not a new state machine. Wave 2.6 resolves a larger set of practical barriers to release preparation: non-portable tests, incomplete source-catalog proof, stale-effect replay, unsafe publication status access, Windows FAISS staging, and an HTTP 202 response modeled as an exception. The implementation includes code, source-locked patch orchestration, a rollback-safe installer, deterministic tests, and a source-evidence checklist.

The exact remote commit was inspected through read-only GitHub. The container has no direct GitHub network access, and the connected account lacks write permission. **Full latest AMC checkout was not cloned and no source patch was actually installed into that checkout.** All `amc_publication` tests in this package run with the packaged, independently acquired historical Wave 1.9/2.0 reference implementation, SQLite and local JSON artifacts. This is not a declaration that the live FastAPI routes, running Neo4j, PostgreSQL multiworker transactions, FAISS binary, frontend, or canary succeeded.

## 2. Substantial development delivered

| Track | Wave 2.6 files | Completed capability | Boundary |
|---|---|---|---|
| Durable graph replay | `tools/amc_release/publication_patch26.py` | Prepared original graph preimage is reused for CAS after restart instead of trusting a new read as the preimage; guard against third-party changes on rollback; exact readback before compensation | Must patch reviewed source in authorized branch and run real graph fault tests |
| Generation pointer ownership | `publication_patch26.py` | PostgreSQL `SELECT ... FOR UPDATE` when pointer row exists; epoch check on same-digest replay; reject stale expected generation | Empty-row concurrent insertion and real PostgreSQL concurrency must be tested |
| Real serving effect proof | `publication_patch26.py` | Reader generation probe now precedes marking vector effect verified | Existing reader must be connected to authoritative generation pointer |
| API semantics | `publication_patch26.py` | Governance `/promote/{patch_id}` returns normal HTTP 202 JSON with work ID/status URL, not an exception | Must test through full FastAPI route |
| Source completeness gate | `backend/amc_publication/catalog26.py`, `approval_catalog26.py` | Require signed full corpus + exact source-version, tenant, ordered chunk identity/content and manifest digest; no silent tenant or unverified empty corpus | Catalog must be independently generated from canonical source, not candidate payload |
| Catalog operator CLI | `tools/amc_release/source_catalog26.py` | Deterministic catalog with exclusive output, explicit count, tenant/version; produces manifest digest for signer | Independently attest canonical source inventory completeness |
| Tenant-isolated publication status | `publication_patch26.py` patch for `backend/amc_publication/status_route.py` | JWT `CurrentUser`, tenant/reviewer role scope, tenant filter on effects and receipts, cross-tenant 404, redaction of `last_error` | Auth model must provide validated `tenant_id`, otherwise endpoint fails 403 |
| Windows FAISS durability | `publication_patch26.py` patch for `backend/amc_publication/faiss_artifacts.py` | Writable file-fsync handle, skip unsupported directory fsync on Windows, retain SHA/readback | Actual `faiss-cpu` binary run on Windows and Linux not performed |
| Test portability | `tools/amc_release/tests/conftest.py`, portable test files, `test_support/baseline/` | Removed sandbox absolute imports; isolated historical source bundled only for offline tests | `test_support/` must not be installed to application code |
| Branch-ready installation | `install_wave26.py` | Cumulative allowlisted install, refusal of unreviewed overwrites, pinned Wave 2.5 upgrades and backups | Git checkout application is not tested here |
| CI | `.github/workflows/amc-release-verification.yml` | Split lightweight evidence tests from costly full-backend matrix; include new cases, Windows/Linux, staged Playwright if configured | Not run as GitHub Actions on a new commit |

**Security decision:** A `CorrectionPatch` has no native tenant field and earlier approval code persisted the reviewer only as an un-serialized dynamic property. The Wave 2.5 adapter consequently requires a persisted tenant association and reviewer metadata; Wave 2.6 adds source-catalog binding. These controls are deliberately fail-closed. Do not bypass the checks by inventing `default` tenants, reviewer IDs, catalog signatures or empty vector snapshots.

**Open governance issue:** The current `CorrectionPatch` approval state and its provenance may be backed by Redis or memory, not an independently authoritative persisted approval record. Before a release, connect approval to a durable, auditable identity source, validate source-version authority and ensure the approved revision cannot drift. Do not treat metadata/HMAC alone as full governance proof.

## 3. Local verification matrix (completed)

- **Python release-control tests:** **236 passed** in the cumulative tools suite (including new Wave 2.6 tests).
- **Historical Wave 1.9 + 2.0 tests:** **112 passed** using bundled reference source.
- **Combined local total:** **348 passed, zero failed**, plus **16 pytest subtests**.
- **Historical baseline warning:** Those 112 tests are not run against the current GitHub application checkout; they exercise the bundled source that came with previous waves.
- **Python test host:** Linux, Python 3.13, SQLite and in-memory graph/JSON snapshots; no deployed external services.
- **Static checks:** New source patcher/module compile; release workflow parsed successfully with YAML; Playwright JS/config and frontend test file pass `node --check`.
- **Frontend API runtime test:** **NOT_RUN** in standalone ZIP because `mf-context-engine/src/services/api.js` is not included; the test imports the actual existing file in the authorized repo checkout. Never substitute a mock and report it as an actual frontend contract pass.
- **PostgreSQL two-worker, live Neo4j, live FAISS binaries, actual serving reader reload, Windows host execution, staging Chromium/Firefox, Prometheus SLO windows, canary, independent signatures:** **NOT_RUN**.

Reference: `remediation/wave2_6/TEST_EVIDENCE.json`, `LOCAL_COMBINED_PYTEST.xml`. SHA statements refer to *source reviewed*, not a successfully tested new Git commit.

## 4. Install into an authorized dedicated feature branch

1. Obtain repository write access in the correct `nusummit-spg` account, or use your local clone and credentials. Do **not** grant this connection an API token inside chat.
2. Sync and create a new branch from `amc-dev`:

```bash
git fetch origin
git switch -c feature/amc-release-candidate-hardening origin/amc-dev
git rev-parse HEAD
```

3. Extract Wave 2.6 ZIP outside the checkout. From the extracted package directory, run a dry-run first:

```bash
python install_wave26.py --repo /path/to/amc-context-engineering-poc
# Only after reviewing proposed file additions:
python install_wave26.py --repo /path/to/amc-context-engineering-poc --apply
```

If an earlier version is **already installed**, use `--upgrade-wave25` **only when** the installer confirms every replaced byte is the exact reviewed Wave 2.5 SHA. The known Wave 2.4 CI matrix may require `--upgrade-wave24`. Unknown/mixed content is blocked. **Do not manually force or delete a backup to bypass refusal.**

4. With the new overlay installed, run the source-locked patch. It prepares **five** source modifications: `worker.py`, `journal.py`, `governance.py`, `faiss_artifacts.py`, and `status_route.py`:

```bash
cd /path/to/amc-context-engineering-poc
python -m tools.amc_release.publication_patch26_cli --repo .
# If the diff and source SHA checks are correct:
python -m tools.amc_release.publication_patch26_cli --repo . --apply
```

It checks reviewed original Git blobs and rejects source drift. It creates `.wave26.bak` files that **must not** be committed. The patch combines Wave 2.5 and 2.6 in one operation; do not run the earlier patch separately first.

5. Review the *existing* `.github/workflows/amc-assurance.yml` through the narrow `tools.amc_release.assurance_ci.harden` tool; apply only after confirming the current workflow matches reviewed anchors. This repair intentionally refuses fake SLO/canary readiness. Run `git diff --check`, compile, test and inspect `git status` before pushing.

6. Never commit real signed corpora, HMAC keys, `.uat-session.json`, proprietary customer documents, database backups, or test-only historical `test_support/` fixtures. Only installed source from the allowlisted overlay should be committed.

## 5. Canonical catalog operator sequence (no automatic activation)

Obtain an independently verified canonical export with the format:

```json
{
  "tenant": "tenant_id",
  "source_version": "approved_immutable_version",
  "canonical_document_count": 2,
  "documents": [
    {"chunk_id":"a","tenant_id":"tenant_id","text":"first source"},
    {"chunk_id":"b","tenant_id":"tenant_id","text":"second source"}
  ]
}
```

Use actual canonical source IDs/counts, not a sample or an HTTP-supplied candidate snapshot. Then:

```bash
PYTHONPATH=backend python -m tools.amc_release.source_catalog26 \
  --source-export /secure/canonical-export.json \
  --output /secure/manifest.amc-source-catalog.json \
  --tenant TENANT --version SOURCE_VERSION --count VERIFIED_COUNT --apply
```

The CLI prints `catalog_sha256`. The reviewed full-corpus snapshot input to `sign_corpus25.py` must carry that **exact** digest in `source_manifest_sha256`. Sign with the external `AMC_PUBLICATION_CORPUS_SIGNING_KEY` (never paste it into ChatGPT). The application must be configured with `AMC_PUBLICATION_SOURCE_CATALOG`, `AMC_PUBLICATION_CORPUS_SNAPSHOT`, and the signing key. `approval_catalog26.queue_from_environment_26` independently verifies catalog bytes and exact document IDs/hashes before queuing to the original journal.

This proves internal correspondence between signer-approved corpus and catalog. **It cannot prove the catalog was originally complete** without upstream canonical-inventory stewardship and evidence.

## 6. Required repository and live integration gates

| Gate | Implementation/verification action | Required outcome |
|---|---|---|
| 01 Exact-source and checkout | Latest commit SHA, patcher dry run, source diff, full backend import, migrations | Pin exact SHA and no drift / startup exceptions |
| 02 App routing | Authenticated APPROVED patch with persisted proposer/reviewer/tenant, source catalog, `POST /governance/promote/{id}` | HTTP 202 with work_id; no request-time DDL; invalid input never queues |
| 03 Recoverability | PostgreSQL migration 012+ on disposable DB; two workers, expired lease, stale fence and crash after each external step | One receipt per work; no stale writer commits |
| 04 Neo4j | Actual allowlisted entity/property schema, exact postcondition readback, rollback to first durable preimage | No cross-tenant writes, no lost third-party updates |
| 05 FAISS/serving | Real binary stage/readback on Windows+Linux, reload and probe active reader, corrupt artifact | Fail closed on bytes/count/ID mismatch, restore verified prior generation |
| 06 Feedback | Durable tenant-specific issue -> receipt link, rollback reopen and serving revocation | No resolved issue without current verified publication |
| 07 Finance/CSV | Full actual source inventory, manifest source SHA, NAV exact row readback, complete contributor ledger | No silent `16245/22`, no clipped proof and no unapproved AAUM |
| 08 CI | Repair malformed AMC Assurance A05, run required PR/manual workflows and Windows/Linux backend contracts | All required jobs **success** on one exact SHA, zero jobless/hidden skips |
| 09 Browser/SLO | Authenticated Chromium+Firefox staging, 1h/24h live SLO samples, canary 30+ min | No fake metrics or sample-based acceptance |
| 10 UAT signoff | Independently anchored evidence chain, two reviewers, explicit UAT decision | Separate UAT acceptance; production release requires independent approval |

**Do not transfer incomplete technical gates to UAT testers.** Only make a UAT handoff after the exact-commit implementation, full app suite, external services, browser and release evidence are green. A green local package still means **engineering integration work remains**.

## 7. Reproducibility commands for the standalone package

```bash
# Package tests, no internet or real services needed:
python -m pytest -q tools/amc_release/tests

# Historical baseline suites shipped for independent offline retesting only:
PYTHONPATH=".:test_support/baseline/backend" python -m pytest -q \
  tools/amc_release/tests \
  test_support/baseline/backend/tests/test_wave19_*.py \
  test_support/baseline/backend/tests/test_wave20_*.py

# Validate the GitHub Actions YAML locally, without executing GitHub Actions:
python -c "import yaml; yaml.load(open('.github/workflows/amc-release-verification.yml'), Loader=yaml.BaseLoader)"
```

On Windows PowerShell, use environment syntax `$env:PYTHONPATH = '.;test_support/baseline/backend'` and explicitly enumerate test files if shell wildcard expansion does not work. In the real repo, use `$env:PYTHONPATH = 'backend'` and run the existing `backend/tests` regression suite plus Wave 2.6 release controls. Run `node --test mf-context-engine/src/services/api.contract.test.js` only when the full frontend is present.

## 8. Executive recommendation

This is no longer a useful place to add standalone governance abstractions. The next high-value action is **one integration and qualification branch** containing the five source patches and two additive catalog modules, a reviewed CI workflow fix, real database/graph/FAISS tests, and a documented deployment target. Release **BLOCK** is the correct result until that evidence exists. No GitHub write, staging mutation, email send, or UAT approval was performed in this delivery.
