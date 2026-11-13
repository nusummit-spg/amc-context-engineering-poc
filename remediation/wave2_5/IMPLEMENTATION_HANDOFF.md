# AMC Context Engineering — Wave 2.5 implementation handoff

**Review date:** 2026-11-11 (IST)  
**Source branch:** `nusummit-spg/amc-context-engineering-poc` / `amc-dev`  
**Source HEAD:** `2c0415c4d23a3338428c8314c869299aa0ab771f`  
**GitHub permissions:** `pull=true`, `push=false` for the connected `annapurnaagenticsolutions` account. No branch, commit or PR was created.  
**Delivery:** Cumulative Wave 2.3 + 2.4 + 2.5 offline ZIP, code/tests and non-overwriting installer.  
**UAT decision:** **BLOCK**, not production-ready; detailed external gates below.

## 1. Executive engineering findings

Source inspection identified a broken governance-to-publication connection beyond the existing CI and release-assurance gaps:

1. **Invalid runtime adapter call:** `backend/app/api/routes/governance.py::promote_patch_direct` passes keyword arguments `sessions`, `proposal_id`, `tenant`, `full_vector_snapshot=[]` to `queue_verified_approval`. The actual function in `backend/amc_publication/integration.py` accepts `(journal: Journal, proposal: ApprovedProposal, complete_corpus_snapshot: list[dict])`. The route's `PubBase.metadata.create_all()` on every request also bypasses migration discipline. The requested empty corpus cannot produce the verified graph/vector effects required for publication.
2. **Lost reviewer identity:** Both governance approval handlers assign `patch.approved_by`, a dynamic attribute not serialized by `CorrectionPatch.to_dict()`. They must write `approver_username` to persisted patch provenance before serializing the approval.
3. **Missing tenant identity:** `CorrectionPatch` has no first-class `tenant_id` field. The new adapter accepts explicit tenant identity only from a persisted `tenant_id` field or `provenance['tenant_id']`; it will **not** guess `default`. Upstream patch-creation paths must attach tenant from a trusted server-side mapping. Existing unscoped patches remain blocked.
4. **Vector publication and rollback race:** The current worker persists an empty vector preimage for later publications, refreshes the expected generation pointer after graph mutation, and reads a potentially newer pointer as the rollback target. The Wave 2.5 patch freezes the original pointer, uses durable preimages, prevents stale-generation rollback, and binds pointer reversion to vector-effect compensation in one SQL transaction.

These are **source-grounded defects**; the provided source patch has been tested against reviewed *anchor fixtures*, not applied to the complete latest repository checkout. Its default Git blob pins reject source drift.

## 2. Delivered implementation

| File | Purpose | Local status |
|---|---|---|
| `backend/amc_publication/approval_adapter.py` | Validates persisted four-eyes approval, explicit tenant/revision, externally HMAC-signed *complete* corpus; invokes existing `Journal` + `queue_verified_approval` rather than building a new engine | TESTED against real Wave 1.9 SQLite journal |
| `tools/amc_release/publication_patch25.py` | SHA-pinned, source-aware patches to existing `worker.py`, `journal.py`, `governance.py`; fail-closed on any source drift | SOURCE TRANSFORMATION TESTED; pending real checkout |
| `tools/amc_release/publication_patch25_cli.py` | Review-only dry run and explicit `--apply`; prints source hashes for review | TESTED |
| `tools/amc_release/sign_corpus25.py` | Operator-controlled, overwrite-refusing HMAC signer of a previously reviewed tenant corpus; signing key stays external | TESTED, synthetic source data |
| `tools/amc_release/tests/test_wave25_*.py` | Invalid approval, cross-tenant, HMAC tampering, empty corpus, two-publication rollback, atomic crash/replay, source drift and installer checks | TESTED on Linux/SQLite |
| `install_wave25.py` | Cumulative safe installer with explicit pinned Wave 2.4 workflow upgrade; does not change existing worker/governance automatically | TESTED offline |
| `.github/workflows/amc-release-verification.yml` | Existing Windows/Linux and UAT matrix extended to include Wave 2.5 tests in full backend, without burdening lightweight evidence job | YAML validated; actual Actions NOT RUN |

### Source-patch design decisions

- **Publication:** reject an empty vector corpus **at submission**, before any graph mutation or queued job. Freeze the original pointer before staging, persist it as the vector effect's immutable preimage, and CAS only that preimage. Check independent artifact and pointer readbacks. In production require `Neo4jGraphPort`, `FaissGenerationStore` and an actual loaded-serving-reader generation probe.
- **Rollback:** require the **published generation recorded in the vector effect** to match the active pointer, not the pointer value observed at rollback time. Restore the recorded prior generation, first verifying its bytes. SQL pointer swap and `vector effect = compensated` are a single transaction; a crash replay can recognize this durable checkpoint and continue graph compensation.
- **Approval:** existing `ApprovedProposal` and `queue_verified_approval` remain authoritative. Serialized approver identity and server-trusted tenant are required. If verified completeness is not available, the API returns 503 instead of returning a false 202 publication intent.
- **Source integrity:** HMAC proves authenticated bytes, **not** full source catalog completeness. An independent steward must still reconcile source version, all source rows, canonical IDs, source-manifest checksum and tenant boundary before signing.

## 3. Local test scope

See `remediation/wave2_5/TEST_EVIDENCE.json` for the exact final counts. Tests execute SQLAlchemy and the historical Wave 1.9 journal with a disposable SQLite DB, in-memory graph and immutable JSON snapshots. Some patcher tests intentionally operate on synthetic source excerpts. The tests do **not** certify real PostgreSQL 2-worker fencing, Neo4j CAS, FAISS binary/serving reload, the complete 2026-11-11 GitHub backend or staging browser/observability.

**Do not report historical test counts as exact-commit CI evidence.** Rerun the current repository after patch application, record full collection totals, skips, JUnit identities, SHA, OS and environment.

## 4. Apply on a local feature branch (Windows PowerShell)

**Preconditions:** Authorized *clean* checkout with the reviewed `amc-dev` SHA and an intentionally created feature branch. Extract ZIP to a separate directory.

```powershell
cd C:\path\to\amc-context-engineering-poc
git fetch origin
git switch amc-dev
git pull --ff-only
git rev-parse HEAD
git status --short
git switch -c feature/amc-release-candidate-hardening

# Fresh installation: dry run first.
py -3.12 C:\path\to\Wave25\install_wave25.py --repo .
py -3.12 C:\path\to\Wave25\install_wave25.py --repo . --apply

# Only if Wave 2.4 was previously installed and has *exactly* the known workflow hash:
# py -3.12 C:\path\to\Wave25\install_wave25.py --repo . --upgrade-wave24 --apply

# Reviewed source changes: default dry run; apply only after inspection.
py -3.12 -m tools.amc_release.publication_patch25_cli --repo .
py -3.12 -m tools.amc_release.publication_patch25_cli --repo . --apply

# Existing assurance workflow fix from Wave 2.4, inspect before applying.
py -3.12 -m tools.amc_release.cli harden-assurance .github/workflows/amc-assurance.yml
py -3.12 -m tools.amc_release.cli harden-assurance .github/workflows/amc-assurance.yml --apply

git diff --check
git diff --stat
git diff -- backend/amc_publication/worker.py backend/amc_publication/journal.py backend/app/api/routes/governance.py
```

The patcher **verifies exact Git blob SHA-1s** for all three files before modifying anything. If the source changed, STOP and review the new code instead of bypassing the pin. Patcher backups end in `.wave25.bak`; remove them from the checkout *before committing*, and never commit auth secrets, signed source files, `.env`, browser sessions or customer data.

```powershell
$env:PYTHONPATH = (Resolve-Path backend).Path
py -3.12 -m pip install pytest sqlalchemy alembic pyyaml
py -3.12 -m pytest -q tools/amc_release/tests
node --test mf-context-engine/src/services/api.contract.test.js
py -3.12 -m pytest --collect-only -q backend/tests
# Install requirements in an isolated venv and execute the full current backend suite:
py -3.12 -m pytest -q backend/tests
```

## 5. Source-corpus signing contract

A trusted operator must assemble all the tenant's canonical documents from an authoritative catalog, reconcile source rows/versions, and separately review the manifest. **No HTTP caller gets to supply corpus bytes or a filesystem path.** Operator-reviewed input has this exact schema:

```json
{
  "tenant": "verified-tenant-id",
  "proposal_id": "actual-patch-id",
  "approved_revision": 1,
  "source_version": "versioned-canonical-catalog",
  "source_manifest_sha256": "64_lowercase_hexadecimal_digits_go_here_replace_with_real_value",
  "complete": true,
  "documents": [
    {"chunk_id": "canonical-source-id", "tenant_id": "verified-tenant-id", "text": "Verified source text"}
  ]
}
```

With out-of-band `AMC_PUBLICATION_CORPUS_SIGNING_KEY` set on the trusted operator host:

```powershell
py -3.12 -m tools.amc_release.sign_corpus25 --input C:\secure\corpus.reviewed.json --output C:\secure\corpus.signed.json --manifest-sha256 REAL_MANIFEST_SHA256
py -3.12 -m tools.amc_release.sign_corpus25 --input C:\secure\corpus.reviewed.json --output C:\secure\corpus.signed.json --manifest-sha256 REAL_MANIFEST_SHA256 --apply
```

The application consumes only the operator-side `AMC_PUBLICATION_CORPUS_SNAPSHOT` path and matching signing key. **External source completeness and trusted tenant mapping are still required** and not invented by these tools.

## 6. Completion gates before UAT

1. Trusted tenant ID persisted at patch creation and verified on readback, including Redis and the approval audit log.
2. Authoritative full corpus snapshot assembled and reconciled to source manifest; independently approved and signed outside the repo.
3. Real worker bound to Neo4j graph port, FAISS binary generation store and loaded serving reader; no simulated production path.
4. PostgreSQL simultaneous workers and crash injection across graph write, vector pointer, receipt and rollback checkpoint; stale workers must never succeed.
5. Real Neo4j and FAISS readback, tenant isolation, first and second generation rollback, and Feedback reopen after receipt revocation.
6. Complete current backend/frontend tests, exact-SHA Linux/Windows CI, JUnit test identity parity and linted Actions YAML.
7. Authenticated Chromium/Firefox staging UAT, measured 1h/24h SLO and >=30-minute controlled canary/rollback, raw telemetry anchors.
8. Externally anchored ledger, independent engineering/QA reviewers, signed UAT go/no-go; UAT_READY is never asserted without evidence.

**Status:** Code is ready for feature-branch review, **not** yet ready for UAT. No GitHub write, deployment, email, or user-facing system change was performed.
