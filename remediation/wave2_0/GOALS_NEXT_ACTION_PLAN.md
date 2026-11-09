# AMC Context Engineering — Wave 2.0

**Actual code implementation · Independent data-truth / Feedback assurance track · Codex handoff**  
**Date:** 6 November 2026  
**Repository:** `nusummit-spg/amc-context-engineering-poc` → `amc-dev`  
**Pinned source baseline reviewed:** `91af9fa4eaa8abdb66c55b04fdee484ea0343a3c`  
**Delivery:** non-destructive ZIP overlay; the connected GitHub account has `pull=true`, `push=false`. **Nothing has been pushed.**  
**Release verdict:** **BLOCK**. Local contract tests are evidence for these isolated modules, **not** live Neo4j/FAISS/PostgreSQL or customer data acceptance.

## 1. Executive decision

**Continue independent development in parallel with integrating Wave 1.9**. Do not create yet another publication saga or bypass the existing verified-publication design. Wave 2.0 adds a read-only quality/evidence layer and concrete tests that can be incorporated without moving canonical graph/vector state. Local Codex owns production integration and live service testing.

**Executed evidence:** **112 tests passed** in the combined Wave 1.9 + Wave 2.0 suites (77 new Wave 2.0 tests, 35 inherited Wave 1.9 tests); a separate deterministic offline Wave 2.0 smoke command passed. Tests used synthetic data, disposable SQLite and a simulated graph. Neither production PostgreSQL nor Neo4j nor real FAISS was exercised for Wave 2.0.

### Goals

1. Detect CSV tampering, skipped/reordered chunks, missing source files, inaccurate row counts and silent ingestion fallback **before database activation**.
2. Preserve **all** contributing `source_row_id` values in verifiable, externally anchored JSONL instead of `[:50]`.
3. Deliver unambiguous, exact NAV and count-only AMC queries; maintain **AAUM aggregation refusal** until an independent, durable steward approval exists.
4. Show when a Feedback issue's customer-visible `resolved` state disagrees with Wave 1.9 verified publication or rollback.
5. Read operational counters from persisted publication tables, labeling unknown latency/uptime **UNKNOWN**, not green.
6. Provide a safe local installer, CI test workflow, repeatable smoke and an audit scanner identifying legacy bypasses.

## 2. Delivered code — actual files

| Module | What is implemented | Scope and limitations |
|---|---|---|
| `backend/amc_quality/manifest.py` | Build immutable-ish chunk manifest; SHA-256 original file and *every actual chunk*; verify UTF-8 CSV header, count, ordered row content; path traversal, symlink, sequence checks; attest existing `mutual_fund_data_chunk_N.csv` without overwriting files; optional external manifest-hash anchor | Integrity verifier; not a digital signature, not an approval |
| `backend/amc_quality/ingestion_gate.py` | `guarded_ingest`: pre-validate source/chunks, check legacy importer glob and declared counts, invoke existing loader with activation disabled, revalidate afterward, reject quarantined or unreconciled imports | Existing importer may still stage rows before post-check; lock immutable source and add transactional/quarantine recovery before production |
| `backend/amc_quality/provenance.py` | Atomic JSONL contributor ledger with header, every contributor ID, indexed records, footer and SHA-256 verification | Digest must be pinned independently; no 50-row truncation |
| `backend/amc_quality/financial.py` | Read-only SQLite typed-repo exact NAV with source-row/plan/date matching; version-scoped validated record count; canonical `amc_id` scheme-count ranking with deterministic ties; complete ledger and result digest | **Reference query engine only**; does not replace every live query route; AAUM additive calculations explicitly blocked |
| `backend/amc_quality/feedback_audit.py` | Cross-check actual Feedback issue status, tenant, Wave 1.9 durable publication receipt/link and active vector generation; flag stale `resolved` states after rollback | Read-only auditor; does not mutate live Feedback records |
| `backend/amc_quality/assurance.py` | Tenant-scoped durable work/effect/receipt/Feedback counts with explicit `UNKNOWN_NO_SLO_WINDOWS` and `BLOCK` release gate | Not a Prometheus collector or latency SLO implementation |
| `backend/amc_quality/cli.py` | `manifest-build`, `legacy-attest`, `manifest-check`, `financial-count`, `financial-nav`, `financial-top-count`, `ledger-check` with JSON output and fail-closed exit status | Manual invoke; production integration via Codex |
| `tools/install_wave20_overlay.py` | Dry-run by default, branch check, refusal to overwrite existing repo files | Run from extracted ZIP against local `amc-dev` or feature branch |
| `tools/audit_legacy_quality_bypasses.py` | Read-only scan for known truncation, magic CSV totals, fallback and legacy publication patterns | Static *known-pattern* scan, not exhaustive security audit |
| `tools/demo_wave20_offline.py` | Build tiny source manifest + SQLite NAV, exact query and full contributor ledger | Simulation only, no services |
| `backend/tests/test_wave20_*.py` | 77 implemented tests across manifest, typed queries, ingestion guard, legacy scanner, Wave 1.9 Feedback/assurance integration | Synthetic and simulated test environments |
| `.github/workflows/amc-quality-v2.yml` | Independent job + Wave 1.9 contract job; required tests fail if files missing | Authored but **not run in GitHub Actions** |

**Packaging contract:** The ZIP excludes `__pycache__`, `.pytest_cache`, credentials, model weights, database contents and customer records. It does **not** replace `PromotionService`, `QueryExecutor`, `IngestionPipeline`, graph stores or frontend files automatically.

## 3. Source-level facts and boundaries

At the pinned `amc-dev` commit:

- `backend/app/tabular/csv_excel_loader.py::ingest_chunks_directory` defaults to `declared_total_rows = 16245` and `declared_chunks = 22` if a trusted manifest is absent. It validates count only and can activate on reconciliation. **Wave 2.0 refuses this implicit trust.**
- `backend/app/tabular/executor.py` still truncates `source_row_ids[:50]`; aggregates without row IDs need a separate contributor query/ledger rather than pretending the displayed rows prove their inputs.
- `backend/app/tabular/contracts.py` identifies AAUM aggregation as `PENDING_APPROVAL`, and `financial_policy_service.py` marks `aaum_crore.steward_approved=False`. **Do not manufacture a steward receipt.**
- Some planner methods still expose old financial aggregation paths. `FinancialQualityReadModel` provides safe independent *count-only* and exact-value reference operations until the legacy planner is fully reconciled.
- `backend/app/services/feedback_outcome_service.py` still uses placeholder/staging-based checks; Wave 2.0 audits against the **actual Wave 1.9 journal**, but production routes still require replacing legacy resolution handling.
- The previously reviewed `amc-dev` GitHub Actions run `42219020259` failed in secret scanning because the organization-owned repository requires a license for `gitleaks/gitleaks-action@v3`; downstream jobs were skipped. **Wave 2.0 does not claim this CI is green.**
- Wave 1.9's publication code already includes its own integrity verifier for raw byte ranges. Wave 2.0 deliberately adds **CSV row-level chunk correspondence** and full query provenance, rather than replacing Wave 1.9's publication engine.

## 4. How to install locally (Windows 11, PowerShell)

### Prerequisites

- Your local Git checkout on `amc-dev` or a `feature/...` branch.
- **Wave 1.9 implementation package already installed** if you want the combined 112-test suite. The standalone 63 Wave 2.0 tests can run without Wave 1.9.
- Python 3.11+ and `pytest`, `SQLAlchemy`; use your local virtual environment.
- ZIP extracted under a location outside the repository, e.g. `C:\temp\amc-wave20`.

```powershell
# 1. Preview and copy only NEW Wave 2.0 files. Never overwrites current AMC code.
python C:\temp\amc-wave20\tools\install_wave20_overlay.py --repo C:\path\to\amc-context-engineering-poc
python C:\temp\amc-wave20\tools\install_wave20_overlay.py --repo C:\path\to\amc-context-engineering-poc --apply

# 2. Execute exact test files. No production database needed.
cd C:\path\to\amc-context-engineering-poc
python -m pip install "pytest>=8,<10" "SQLAlchemy>=2,<3" "alembic>=1.13,<2"
$env:PYTHONPATH = "backend"
python -m pytest -q backend/tests/test_wave20_independent.py backend/tests/test_wave20_ingestion.py backend/tests/test_wave20_audit.py
# Requires Wave 1.9: 
python -m pytest -q backend/tests/test_wave20_wave19_contract.py
# If Wave 1.9 was installed, also run its three test_wave19_*.py files.

# 3. Run a completely synthetic smoke.
python tools/demo_wave20_offline.py

# 4. Scan existing source for known integration bypasses (exit 1 when findings exist).
python tools/audit_legacy_quality_bypasses.py --repo .
```

**Real input commands (do not use actual customer data until approved):**

```powershell
cd backend
# A. Create *new* chunks and verified manifest for a COPY of the original CSV.
python -m amc_quality.cli manifest-build C:\data\source.csv C:\temp\new_chunks --rows-per-chunk 1000
python -m amc_quality.cli manifest-check C:\data\source.csv C:\temp\new_chunks\manifest.amc-v2.json

# B. Or attest EXISTING AMC named chunks without rewriting them.
python -m amc_quality.cli legacy-attest C:\data\source.csv C:\data\existing_chunks
python -m amc_quality.cli manifest-check C:\data\source.csv C:\data\existing_chunks\manifest.amc-v2.json

# C. Reference typed queries against a disposable copy of the AMC SQLite DB.
python -m amc_quality.cli financial-count C:\temp\typed_demo.db C:\temp\ledger_count.jsonl
python -m amc_quality.cli financial-nav C:\temp\typed_demo.db C:\temp\ledger_nav.jsonl --scheme-code 100033 --nav-date 2026-06-29 --plan-option-id <actual-plan-id>
python -m amc_quality.cli financial-top-count C:\temp\typed_demo.db C:\temp\ledger_top.jsonl --limit 10
```

For tamper-resistant audits, **pin the displayed manifest SHA-256 and contributor ledger SHA-256 separately** (e.g. in an append-only evidence table), then pass the pinned value back to `manifest-check --expected-manifest-sha256 HEX` or `ledger-check ledger.jsonl HEX`. A digest stored only beside the file does not prevent an attacker replacing both.

### Important integration constraint

`manifest-build` outputs `chunk_000000.csv` files, appropriate for independent verification. The **existing** AMC loader expects `mutual_fund_data_chunk_N.csv`. For the current AMC importer, use `legacy-attest` against a pre-existing correctly ordered legacy chunk set, then `guarded_ingest`. Do not rename chunks without accounting for exact row order and source identity.

## 5. Immediate bulk Codex plan — complete locally in reviewable commits

| ID | Priority | Implementation action | Acceptance evidence |
|---|---|---|---|
| W20-I01 | P0 | Install Wave 1.9 then Wave 2.0 overlays in feature branch; freeze original HEAD and inputs | No pre-existing file overwritten; source/README diff |
| W20-I02 | P0 | Wire `guarded_ingest` into existing `run_tabular_ingestion.py`/API **before** any staging; require real source + v2 manifest and fail if absent | Missing source, tampered original/chunk, missing/reordered chunks all block activation |
| W20-I03 | P0 | Remove implicit `16245`/`22` defaults; require verified manifest and its external digest; freeze immutable source while ingesting | Source digest captured before/after ingest, matches result; fail no manifest |
| W20-I04 | P0 | Make typed dataset import staging transactional; on integrity or DB failure quarantine staged version without changing active pointer | Crash/restart and partial insert never expose new version |
| W20-I05 | P0 | Add full query contributor ledger to `QueryExecutor` and every supported numeric/aggregate service; preserve `[:50]` only as **UI preview** labeled truncated, not proof | 100+ contributors count/digest match and ledger independently verifies |
| W20-I06 | P0 | Reconcile planner/MetricRegistry operation semantics; use COUNT for scheme/AMC-count and refuse AAUM SUM/AVG/rank without independently verifiable steward authorization | 30+ independent SQL golden tests; no fallback to model-generated numbers |
| W20-I07 | P0 | Replace source/version ambiguous NAV `LIMIT 1`; require plan/option or explicit ambiguity with same-row NAV/date readback | Two plan variants refuse unqualified lookup; source drift detected |
| W20-I08 | P0 | Wire Feedback auditor against persisted issue and Wave 1.9 receipt; replace legacy pseudo-verified outcomes | Resolution only after tenant-matched, active, verified generation; rollback flags reopen |
| W20-I09 | P1 | Expose durable state counts and actual time-stamped SLO samples; define availability UNKNOWN without evidence | No success-only placeholder; SLO window fixtures include missing data |
| W20-I10 | P0 | Integrate Wave 1.9 Worker as **only** publication executor; close legacy `promote_to_permanent`, approved-only readers and old outbox handlers | Publication cannot be double executed; 202 only after durable queued work ID |
| W20-I11 | P0 | Run PostgreSQL two-worker race, lease/fencing, Neo4j readback and real immutable FAISS generation swap/rollback | Crash-point tests and actual data readback, no stale-worker effects |
| W20-I12 | P0 | Fix org Gitleaks scanner per Wave 1.9 script, rerun full GitHub CI and require mandatory quality jobs | Fresh pipeline for new SHA green, no skipped required jobs |
| W20-I13 | P0 | Restore or formally replace missing `packages/amc-feedback-loop/` with approved migration/API parity | Maintainer decision + endpoint/contract regression evidence |
| W20-I14 | P0 | Produce a signed/approved independent release gate after canary and rollback drills | **BLOCK** until independent approval and all listed gates pass |

**Parallelization:** W20-I01–I04 and W20-I05–I07 can run as distinct reviewable workstreams. W20-I08–I09 can run independently against Wave 1.9 journal. W20-I10–I11 depend on the local publication integration track. W20-I12–I14 are exit gates.

## 6. Ready-to-paste local Codex execution prompt

> You are the senior engineer integrating AMC Wave 2.0. Repository: `nusummit-spg/amc-context-engineering-poc`, local branch `amc-dev`, reviewed baseline `91af9fa4eaa8abdb66c55b04fdee484ea0343a3c`. First reconcile HEAD; if advanced, rebase safely before modifications. Read the extracted `AMC_Wave2_0_Code_Implementation_Goals_Next_Actions_2026-11-06.md` and the Wave 1.9 implementation README. Install the Wave 2.0 overlay without overwrites. Implement W20-I01–I09 as one bulk sprint, using multiple reviewable commits, and close any directly related security/functional bypasses found during integration. Wave 1.9 publication remains the only target authoritative engine; do not write a second worker or state machine. Require actual source/chunk hashes and exact row agreement before any financial dataset activation. Block AAUM additive/ranked answers until independent steward approval is supplied and verified. Implement full source-row evidence for all aggregates, not just a 50-ID preview. Wire Feedback issue transitions only to verified durable receipt+tenant+ACTIVE generation. Run all Wave 1.9 + Wave 2.0 tests and actual existing app regressions. Report test commands, exact exit codes, negative test proof, revised files, release blockers, and rollback steps. Do not deploy, approve production changes, fabricate statuses, bypass CI, or mutate customer data. Track W20-I10–I14 as release prerequisites. Preserve existing source and history; avoid destructive downgrades and migration changes to production.

## 7. Verification evidence and limitations

**Local test commands executed in this isolated environment:**

```bash
PYTHONPATH=/mnt/data/amc_wave20_impl/backend:/mnt/data/amc_wave19_impl/backend \
  pytest -q /mnt/data/amc_wave20_impl/backend/tests/test_wave20_*.py \
  /mnt/data/amc_wave19_impl/backend/tests/test_wave19_*.py
# Result: 112 passed
python /mnt/data/amc_wave20_impl/tools/demo_wave20_offline.py
# Result: PASS_SIMULATED
```

| Verification area | Result | Boundary |
|---|---|---|
| New standalone quality/integrity/ingestion source tests | **PASS** | 63 tests, synthetic fixtures |
| New Feedback/assurance bridge tests requiring Wave 1.9 | **PASS** | 14 tests, SQLite / simulated graph |
| Existing Wave 1.9 publication tests | **PASS** | 35 tests from earlier package |
| Combined suite | **PASS** | **112 tests total**, local only |
| Real AMC `IngestionPipeline` with full 16,245-row corpus | **NOT RUN** | Requires actual original CSV/chunks and validated schema |
| Existing full AMC backend/frontend regression suite | **NOT RUN** | Requires local project checkout, dependencies, fixtures |
| Real PostgreSQL/Neo4j/FAISS concurrency and rollback | **NOT RUN** | Wave 1.9 local integration workstream |
| Current GitHub Actions quality job | **NOT RUN** | New workflow not committed; prior branch CI failed |
| Production canary, operational SLOs, privacy review | **NOT RUN** | Release gates remain BLOCKED |

**Known limitations / deliberately conservative choices**:

- `guarded_ingest` can stop activation but cannot guarantee rollback of partially inserted rows inside the existing loader; **add transactionally staged/quarantined versions** before production use.
- Byte/SHA integrity is **not source authenticity** unless the manifest digest is anchored independently in an access-controlled audit store.
- SLO uptime/latency remains `UNKNOWN` without real time-series samples.
- The read model is SQLite-only because the existing typed financial repository uses SQLite. The separate durable publication engine's target production persistence and concurrency must be verified independently.
- No real AAUM additivity semantics or steward approval has been assumed. Query formulas for AAUM should be finalized by business/data stewards before enablement.
- `FeedbackEvidenceAuditor` is a **read-only consistency gate**. Codex must wire actual transitions and avoid split-brain between Feedback issue tables and Wave 1.9 journal.

## 8. Release criteria — non-negotiable

No production release until: (1) one authoritative publication executor, (2) verified Neo4j mutations and FAISS generation switch, (3) crash recovery and rollback readback, (4) verified source bytes, chunk rows and full contributor ledger, (5) AAUM policy/steward enforcement across all routes, (6) Feedback issue causal consistency, (7) independent security/privacy and SLO evidence, (8) green non-suppressed GitHub CI for the new SHA, and (9) documented rollback plan and signed decision.

**Current decision: BLOCK. Continue implementation and local verification.**
