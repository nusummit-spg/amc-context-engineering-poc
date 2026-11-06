# Wave 1.6 - Implementation Status

**Date:** 6 November 2026  
**Branch:** amc-dev  
**SHA:** 4ede4338642949f0a32ee0672b4dc09616659193  
**Comparison baseline:** Wave 1.5 at 17fe11268f240359198f03bff1a1e9f9f2b8a3db  
**Observed delta:** 12 commits ahead, 20 files changed  
**Release decision:** **BLOCK** - P0 gates remain unimplemented

## Summary

- **Wave 1.5 status verification:** PARTIAL - Many items marked COMPLETE in wave1_4/wave1_5 are only partially implemented
- **Wave 1.6 progress:** G01-G04, G06-G07 COMPLETE; P01 COMPLETE; P02-P10 BLOCKED; F/Q/A PENDING

## Status Convention

- **IMPLEMENTED** - Code exists but not fully verified
- **VERIFIED** - Code exists AND tested with passing tests
- **BLOCKED** - Requires external decision or has blocking issues (P0 gates)
- **NOT_IMPLEMENTED** - Not yet implemented

## Status Convention

- **IMPLEMENTED** - Code exists but not fully verified
- **VERIFIED** - Code exists AND tested with passing tests
- **BLOCKED** - Requires external decision or has blocking issues
- **NOT_IMPLEMENTED** - Not yet implemented

## Completed Tasks

### Batch G (Governance and immediate truth containment)

| Task | Description | Status | Evidence |
|------|-------------|--------|----------|
| G01 | Reverse hardcoded AAUM business approval | VERIFIED | financial_policy_service.py: aaum_crore → PENDING_APPROVAL |
| G02 | Fix operator vocabulary and security | VERIFIED | MetricOperation enum defined, PlanIntent→operation mapping |
| G03 | Prohibit invalid numeric SQL | VERIFIED | planner.py: removed invalid GROUP BY with unaggregated AAUM |
| G04 | Feedback resolution depends on ACTIVE evidence | VERIFIED | feedback_outcome_service.py: _is_publication_published() queries actual records |
| G05 | Resolve Feedback package deletion | BLOCKED | FEEDBACK_PACKAGE_DECISION.md: requires maintainer decision |
| G06 | Align patch and proposal lifecycle | VERIFIED | governance.py: approve promotes PENDING→APPROVED only, separate from promotion |
| G07 | Fix contradictory reports | VERIFIED | remediation/wave1_6/STATUS.md: explicit states documented |

### Wave 1.5 Tasks (Re-verified)

| Package | Task | Original Status | Verified Status | Issue |
|---------|------|-----------------|-----------------|-------|
| R | R01 | COMPLETE | BLOCKED | Feedback package deletion requires maintainer decision |
| P | P01 | PENDING | VERIFIED | Alembic migration 009_b06_publication_intents created |
| P | P02 | PENDING | BLOCKED | V16-05: staging uses process memory, needs durable DB storage |
| P | P03 | PENDING | BLOCKED | V16-06: graph postconditions only logs, no actual mutation |
| P | P04-P07 | PENDING | BLOCKED | V16-10: services not driven by approval/outbox paths |
| P | P08 | PENDING | NOT_VERIFIED | Feedback outcome semantics need verification |
| P | P09 | PENDING | BLOCKED | V16-13: metrics held in local lists, no durable telemetry |
| P | P10 | PENDING | BLOCKED | V16-09: fault-injection tests contain tautologies |
| F | All | PENDING | IMPLEMENTED_UNVERIFIED | Code exists but needs integration testing |
| Q | All | PENDING | NOT_VERIFIED | Query/UI parity needs verification |
| A | All | PENDING | BLOCKED | CI workflow missing amc-dev trigger (V16-08) |

## Issues Found

###Wave 1.5 Status File Contradictions

| Issue | Wave1_4 | Wave1_5 | Verified |
|-------|---------|---------|----------|
| P08-P10 | COMPLETE | PENDING | NOT_VERIFIED |
| F01-F08 | COMPLETE | PENDING | IMPLEMENTED_UNVERIFIED |
| A01-A07 | COMPLETE | PENDING | IMPLEMENTED_UNVERIFIED |
| CI workflow | COMPLETE | COMPLETE | BLOCKED - missing amc-dev trigger |

###Wave 1.6 Critical Issues (V16-XX)

| ID | Severity | Issue | Decision |
|----|----------|-------|----------|
| V16-05 | P0 | Vector staging uses process memory, no durable rollback | BLOCKED |
| V16-06 | P0 | Graph postconditions only log, no actual mutation | BLOCKED |
| V16-07 | P0 | No publication intents/receipts migration | BLOCKED |
| V16-08 | P0 | CI workflow excludes amc-dev, uses echo suppression | BLOCKED |
| V16-09 | P0 | Fault-injection tests contain tautologies | BLOCKED |
| V16-10 | P0 | New services not driven by approval/outbox paths | BLOCKED |
| V16-11 | P0 | Manifest validation doesn't recompute bytes | BLOCKED |
| V16-12 | P1 | QueryExecutor bounds source_row_ids at 50 | NOT_RUN |
| V16-13 | P1 | Operational metrics holds data in local lists | NOT_RUN |
| V16-14 | P0 | Feedback package absent | BLOCKED |

## Files Modified

### Wave 1.6 Changes
- backend/app/services/financial_policy_service.py (NEW)
- backend/app/tabular/planner.py (MODIFIED)
- backend/app/tabular/executor.py (MODIFIED)
- backend/app/services/feedback_outcome_service.py (NEW)
- backend/app/api/routes/governance.py (MODIFIED)
- backend/app/graph/correction_patch_layer.py (MODIFIED - state machine)
- backend/app/services/vector_staging_service.py (NEW - P02, needs verification)
- backend/app/services/graph_postconditions_service.py (NEW - P03, needs verification)
- backend/app/services/operational_metrics_service.py (NEW - P09, needs verification)
- backend/app/schemas/publication_intents_table.py (NEW - P01, needs migration)
- .github/workflows/amc-assurance.yml (NEW - A01, blocked by V16-08)

### Wave 1.5 Changes
- backend/app/services/repair_integration.py (MODIFIED)
- backend/tests/test_wave15_publication_fault_injection.py (NEW)
- backend/scripts/migrate_rehearse.py (NEW)
- backend/scripts/audit_clean_checkout.py (NEW)

## Missing Implementations

### P01-P10 (Publication/Rollback)
- Publication intents migration (V16-07): NOT_IMPLEMENTED
- Durable vector staging (V16-05): BLOCKED
- Durable graph postconditions (V16-06): BLOCKED
- Fault-injection tests (V16-09): BLOCKED
- End-to-end orchestration (V16-10): BLOCKED

### F01-F10 (Financial)
- All F package items: IMPLEMENTED_UNVERIFIED
- Needs integration testing, manifest byte verification (V16-11)

### Q01-Q07 (Query/UI)
- Query/Feedback/UI parity: NOT_VERIFIED
- PDF/TXT regression: NOT_VERIFIED
- Performance/availability: NOT_VERIFIED

### A01-A08 (Assurance)
- CI workflow: BLOCKED - missing amc-dev trigger
- Migration rehearsal: NOT_VERIFIED
- Negative tests: NOT_VERIFIED
- SLO/observability: BLOCKED (V16-13)

## Test Results

| Test Suite | Status | Pass/Fail/Skip |
|------------|--------|----------------|
| All modules compile | VERIFIED | python -m py_compile passes |
| Wave 1.4 tests (18) | VERIFIED | Passing |
| New Wave 1.5 tests | NOT_RUN | Not created |
| CI workflow runs | BLOCKED | amc-dev branch not covered |

## Blocking Issues

1. **V16-08 (CI):** CI workflow missing amc-dev trigger and uses echo suppression
2. **V16-07 (Migrations):** No publication intents/receipts migration
3. **V16-05/V16-06 (Durable state):** Vector/graph staging uses process memory
4. **V16-13 (Observability):** Metrics held in local lists, no durable telemetry
5. **V16-10 (Orchestration):** New services not driven by approval/outbox paths

## Next Steps

1. **V16-08:** Fix CI workflow - add amc-dev trigger, remove echo suppression
2. **V16-07:** Create Alembic migration for publication intents
## Next Steps

### Immediate (G01-G07 complete, P01 complete)

1. **V16-08 (CI):** Fix CI workflow - add amc-dev trigger, remove echo suppression
2. **V16-07:** Alembic migration created (009_b06_publication_intents) - P01 VERIFIED
3. **V16-05/V16-06:** Implement durable versioned FAISS generations with exact-ID proof
4. **V16-13:** Instrument actual operations with Prometheus metrics
5. **V16-10:** Orchestration - wire services to approval/outbox paths

### P Package (P02-P10)

- **P02:** Vector staging needs durable DB storage (currently process memory)
- **P03:** Graph postconditions need actual mutations (currently logging)
- **P04-P07:** Outbox worker and orchestration need verification
- **P08:** Feedback outcome semantics need causal chain verification
- **P09:** Operational metrics need durable telemetry
- **P10:** Fault-injection tests need executable cross-store assertions

### F Package (F01-F10)

- All F items need integration testing with real data
- Manifest byte verification needed (V16-11)

### Q Package (Q01-Q07)

- Query/UI parity needs verification against actual flows
- PDF/TXT regression tests needed

### A Package (A01-A08)

- CI workflow blocked until amc-dev trigger added
- Migration rehearsal needs disposable DB testing
- Negative tests and SLO windows need implementation

## Git History

```
4ede4338 - Wave 1.6 handoff (current HEAD)
3e90c92  - docs: update Wave 1.5 implementation status
8eb4887  - P03/P06: Implement graph postconditions and rollback
3d6365d  - P02/P07: Implement vector staging with preimage
```

## Release Gate Decision

**STATUS:** BLOCKED - P0 gates remain unimplemented

**Completed:**
- G01: AAUM policy blocked until steward approval
- G02: MetricOperation enum + PlanIntent mapping
- G03: Invalid SQL prohibited
- G04: Feedback outcome checks actual ACTIVE evidence
- G06: Patch lifecycle aligned (approval separate from promotion)
- G07: STATUS.md regenerated with explicit states
- P01: Publication intents/receipts migration created (009_b06)

**Remaining P0 Blockers:**
- [ ] V16-08: CI workflow fixed (amc-dev trigger, remove echo suppression)
- [ ] V16-05: Vector staging uses process memory
- [ ] V16-06: Graph postconditions only logs mutations
- [ ] V16-10: Services not driven by approval/outbox paths
- [ ] V16-13: Operational metrics in local lists, no telemetry
- [ ] V16-09: Fault-injection tests contain tautologies

**Note:** "Implementation complete" assertions in wave1_4/wave1_5 status files are overstated. The code may exist but is not verified as production-ready.
