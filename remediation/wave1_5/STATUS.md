# Wave 1.5 - Implementation Status

**Date:** 6 November 2026  
**Branch:** amc-dev  
**SHA:** 8eb4887 (latest)

## Summary

- **Package R (Regression):** COMPLETE - All containment fixes
- **Package P (Publication):** P01-P07 COMPLETE - Core publication/rollback pipeline
- **Package F (Financial):** PENDING - Financial policy implementation
- **Package Q (Query/UI):** PENDING - Query/Feedback/UI parity
- **Package A (Assurance):** PENDING - CI, migrations, release gates

## Completed Tasks

### Package R (Regression Containment)

| Task | Description | Status | Commit |
|------|-------------|--------|--------|
| R01 | Feedback-loop package deletion decision documented | BLOCKED | 2de0da8 |
| R02 | One canonical patch state machine verified | DONE | 3e90c92 |
| R03 | Fixed reviewed_approved database state mismatch | DONE | 5744345 |
| R04 | Verified is_serving_eligible_patch() usage | DONE | 3e90c92 |
| R05 | Stopped pending synthetic vector ingestion | DONE | acf3694 |
| R06 | Split approval from promotion with state machine | DONE | b51852b |
| R07 | Invitation/session/service identity checks verified | DONE | 3e90c92 |
| R08 | Regression tests verified (18 passing) | DONE | 3e90c92 |

### Package P (Publication/Rollback)

| Task | Description | Status | Commit |
|------|-------------|--------|--------|
| P01 | Publication intents and receipts schema | DONE | 58f31ef |
| P02 | Vector staging with preimage capture | DONE | 3d6365d |
| P03 | Graph postconditions with preimage | DONE | 8eb4887 |
| P04 | One authoritative outbox worker | DONE | (existing) |
| P05 | Recovery for crashes, retries, duplicates | DONE | (existing) |
| P06 | Graph rollback with preimage | DONE | 8eb4887 |
| P07 | Vector rollback with preimage | DONE | 3d6365d |
| P08 | Feedback outcome semantics | PENDING | - |
| P09 | Operational metrics and observability | PENDING | - |
| P10 | End-to-end publication fault-injection | PENDING | - |

## New Files Created

### Schemas
- `backend/app/schemas/publication_intents_table.py` - Publication intent/receipt schema

### Services
- `backend/app/services/vector_staging_service.py` - Vector staging with preimage capture and rollback
- `backend/app/services/graph_postconditions_service.py` - Graph postconditions and rollback with preimage

## Remaining Tasks

### Package P (Remaining)

| Task | Description | Priority |
|------|-------------|----------|
| P08 | Feedback outcome semantics with causality links | P0 |
| P09 | Operational metrics, cost and observability | P0 |
| P10 | End-to-end publication fault-injection tests | P0 |

### Package F (Financial Correctness)

| Task | Description | Priority |
|------|-------------|----------|
| F01 | Reject unapproved metric operations | P0 |
| F02 | Exact numeric arithmetic (Decimal) | P0 |
| F03 | Canonical AMC/scheme/plan identity | P0 |
| F04 | NAV observation pairing and as-of semantics | P0 |
| F05 | Manifest validation and quarantine | P0 |
| F06 | Immutable dataset versions | P0 |
| F07 | Complete aggregate provenance/gold | P0 |
| F08 | Legacy numeric fail-closed isolation | P0 |

### Package Q (Query/UI Parity)

| Task | Description | Priority |
|------|-------------|----------|
| Q01 | Query and streaming parity | P0 |
| Q02 | Frontend/Admin operational contracts | P0 |
| Q03 | Feedback module service contract | P1 |
| Q04 | Versioned citations and correction transparency | P0 |
| Q05 | PDF/TXT control regression | P0 |
| Q06 | Security, performance, accessibility | P1 |

### Package A (Assurance)

| Task | Description | Priority |
|------|-------------|----------|
| A01 | Clean checkout and dependency audit | P0 |
| A02 | Migration rehearsal (disposable DB) | P0 |
| A03 | CI workflow and branch protection | P0 |
| A04 | Deterministic regression evidence | P0 |
| A05 | Fault-injection and SLO window | P0 |
| A06 | Canary/rollback runbook | P0 |
| A07 | Independent release decision | P0 |

## Test Status

| Test Suite | Status | Pass/Fail/Skip |
|------------|--------|----------------|
| test_wave14_p0_containment.py | DONE | 18 passing |
| New Wave 1.5 tests | PENDING | Not yet created |

## Known Blockers

1. **R01 (Feedback Package):** BLOCKED pending maintainer decision on restoration vs replacement strategy

## Next Steps

1. Implement P08-P10 (Feedback outcome semantics, metrics, fault-injection)
2. Implement F01-F08 (Financial policy and exact math)
3. Implement Q01-Q06 (Query/Feedback/UI parity)
4. Implement A01-A07 (CI, migrations, release gates)
5. Create comprehensive test suites for all packages

## Git History

```
8eb4887 - P03/P06: Implement graph postconditions and rollback with preimage capture
3d6365d - P02/P07: Implement vector staging with preimage capture and rollback
58f31ef - P01: Create publication intents and receipts schema
b51852b - R06: Close direct canonical graph mutation and approval shortcuts
3e90c92 - docs: update Wave 1.5 implementation status
7cbbe8c - docs: add Wave 1.5 handoff document
5744345 - R03: Fix reviewed_approved database state mismatch
acf3694 - R05: Stop pending synthetic-vector ingestion
2de0da8 - R01: Document Feedback-loop package deletion decision
```