# Wave 2.0 — Implemented source vs verified behavior

Pinned upstream baseline: `91af9fa4eaa8abdb66c55b04fdee484ea0343a3c`.
Code is an additive ZIP overlay, **not pushed**. Release decision **BLOCK**.

| Deliverable | Code | Tests | Status |
|---|---|---|---|
| CSV byte + ordered row manifest, legacy attestation | `amc_quality/manifest.py` | test_wave20_independent, test_wave20_ingestion | LOCAL_TESTED |
| Fail-closed staging-only adapter to AMC ingestion | `amc_quality/ingestion_gate.py` | test_wave20_ingestion | MOCK_INTEGRATION_TESTED |
| Complete contributor ledger / external digest anchor | `amc_quality/provenance.py` | test_wave20_independent | LOCAL_TESTED |
| Typed exact NAV, valid-row & scheme count reference | `amc_quality/financial.py` | test_wave20_independent | SQLITE_FIXTURE_TESTED |
| Wave 1.9 Feedback issue consistency | `amc_quality/feedback_audit.py` | test_wave20_wave19_contract | SQLITE_SIMULATED_TESTED |
| Durable-count read / unknown SLO exposure | `amc_quality/assurance.py` | test_wave20_wave19_contract | SQLITE_SIMULATED_TESTED |
| CLI, offline demo, static scanner, safe installer | `cli.py`, `tools/` | local CLI + test_wave20_audit | LOCAL_TESTED |
| Dedicated Actions workflow | `.github/workflows/amc-quality-v2.yml` | not pushed | IMPLEMENTED_UNVERIFIED |
| Runtime wiring to actual AMC backend | **not included** | not run | BLOCKED_LOCAL_INTEGRATION |
| Postgres, Neo4j, FAISS, canary/release assurance | **outside standalone package** | not run | BLOCKED_EXTERNAL |

**Local evidence**: 77 targeted Wave 2.0 tests + 35 Wave 1.9 tests = **112 passed**; synthetic smoke passed. No real customer/production systems were used.
