# AMC Wave 3.1 — First-Publisher Arbitration & Verified-Mode Governance Cutover

**Release verdict: BLOCKED.** This is a cumulative offline engineering overlay. It has not been committed, deployed, or tested against a real PostgreSQL/Neo4j/FAISS backend.

## Why this wave exists

Wave 2.8 introduced receipt-based authority. Wave 3.0 protected crash replays and in-flight FAISS retrieval. One remaining race was present when a tenant had **no active authority row yet**: two independent works could both prepare a graph mutation without claiming an exclusive tenant/namespace slot. `publication_scope_claim_v31` closes that gap using a database unique constraint plus row locking; it persists after worker death and is never timed out automatically.

A second gap was the existing `/api/governance/promote` bulk endpoint, which still called `PromotionService.apply_approved_proposals()` directly. The Wave 3.1 source-locked patch blocks that legacy mutation route when `AMC_VERIFIED_SERVING_MODE=enforce`. It does not attempt to invent an unreviewed bulk outbox adapter.

## Files

- `backend/amc_publication/active_authority28.py` — updated cumulative file containing `PublicationScopeClaim31`, `_claim_scope`, `_release_scope`; integrated within `suspend_before_graph`, `bind_published`, `suspend_rollback`, and `restore_after_rollback`.
- `backend/alembic/versions/014_publication_scope_claim_v31.py` — additive migration, revises `013_active_receipt_authority_v28`.
- `backend/amc_publication/scope_audit31.py` — read-only orphan/held claim anomaly report, never automatically releases ambiguous claims.
- `tools/amc_release/governance_guard31.py` — source-drift checked route patch; affects only the unsafe bulk endpoint.
- `tools/amc_release/apply_all31.py` — preflight-first, branch-local installer; never pushes or deploys.
- `tools/amc_release/qualification31.py` — read-only integrated-source qualification; always keeps live/UAT blocked until independently verified.
- `tools/amc_release/run_wave31_tests.py` — Linux/Windows-safe test runner and JUnit evidence.
- `.github/workflows/amc-wave31-durable-mutation.yml` — manual-only 3.11 Windows/Linux test workflow; never represents production acceptance.

## Installation — from an actual clean `amc-dev` checkout at SHA `2c0415c4d23a3338428c8314c869299aa0ab771f`

**Do not apply Wave 2.5 separately.** This cumulative archive supersedes prior Wave 3.0. Extract the ZIP *outside* the Git checkout, preserving its directory hierarchy.

```powershell
# In extracted bundle directory, on Windows PowerShell:
python -m tools.amc_release.apply_all31 --repo C:\path\to\amc-context-engineering-poc --bundle .
# If dry-run passes AND the reviewed SHA matches:
python -m tools.amc_release.apply_all31 --repo C:\path\to\amc-context-engineering-poc --bundle . --apply
```

The installer creates a local feature branch only after a complete source-patch preflight. Its prior Wave 3.0 path installs the revised scope-authority module. Wave 3.1 then installs revision 014, tests and governance guard. **No automatic migration, git commit, push or deployment.** An existing branch, dirty checkout, changed file, or backup collision is a hard stop.

**Review `.wave*.bak` files and move them outside Git before staging changes.** Do not commit backup/source corpus or secrets.

```powershell
# In branch checkout, after reviewing diff:
python -m tools.amc_release.run_wave31_tests --root . --out remediation/wave3_1/local-branch-tests.json
# Extra and expensive; only with full dependencies installed:
python -m tools.amc_release.run_wave31_tests --root . --full-backend --out remediation/wave3_1/full-backend-tests.json
# Alembic: run in a disposable PostgreSQL instance first. Review prior data migrations before a live upgrade.
```

## Concurrency contract

1. **First publication:** `suspend_before_graph` acquires a durable tenant/namespace reservation even if no active authority or pointer exists.
2. **Competing work:** Another work may be leased but cannot prepare an external mutation for that tenant/namespace. The conflicting transaction rolls back.
3. **Crash replay:** The *same* work can re-enter a HELD claim while its original authority preimage is still valid. Claims are not automatically expired.
4. **Publish:** `bind_published` requires the same HELD claim, verifies existing authority/receipt rules, and releases the claim **in the receipt transaction**.
5. **Rollback:** `suspend_rollback` reacquires the claim for the published work, and `restore_after_rollback` releases it only after exact rollback checks succeed.
6. **Abandoned claim:** Manual, evidence-backed operator reconciliation is required; do **not** force-release or invent a retry timeout.

## Outstanding acceptance requirements (all NOT RUN)

- Real PostgreSQL multi-session transaction stress, including two simultaneous first publications and a process kill between preimage and graph mutation.
- Real Neo4j graph preimage/CAS/readback and staged FAISS ID-mapped binary activation; loaded-reader verification.
- Full repo Python test suite, frontend integration, Windows/Linux exact-SHA CI results, end-to-end streaming/bypass review.
- Authenticated staging tests, 1-hour/24-hour SLO metrics, monitored canary and independent UAT go/no-go.

**Do not assume all graph-changing endpoints are covered:** this wave closes one known bulk-promotion bypass, not a proof that every legacy admin/task/background execution path uses the journal.
