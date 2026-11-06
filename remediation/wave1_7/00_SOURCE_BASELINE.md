# Wave 1.7 Source Baseline

**Date:** 6 November 2026  
**Repository:** `nusummit-spg/amc-context-engineering-poc`  
**Branch:** `amc-dev`  
**Pinned baseline SHA:** `bea1fbd4e52fdc93fa064c47ed1377347d3852f7`  
**Previous Wave 1.6 SHA:** `4ede4338642949f0a32ee0672b4dc09616659193`  
**Observed delta:** 1 commit ahead (Wave 1.6 codebase)

## Current State

### Wave 1.6 Completed
- G01: AAUM policy uses PENDING_APPROVAL (verified)
- G02: MetricOperation enum + PlanIntent mapping (verified)
- G03: Invalid SQL prohibited (verified)
- G04: Feedback outcome checks ACTIVE evidence (partially - needs DB queries)
- G06: Patch lifecycle aligned (verified)
- G07: STATUS.md regenerated (verified)
- P01: Publication intents migration 009_b06 created (artifact only, not verified)

### CI Evidence (Wave 1.7 Finding: W17-01 / V16-08)
- GitHub Actions run 42202423962 failed at `Scan for secrets` due to `pip install gitleaks` returning "No matching distribution found for gitleaks"
- All downstream jobs skipped (migration, unit, regression, fault injection, canary, release)
- No real secrets exposed; this is a scanner installation error, not a finding

### Critical Issues (Wave 1.7)
- W17-01: Gitleaks pip install fails (CI broken)
- W17-02/W16-05: Vector staging uses process memory
- W17-03/W16-06: Graph postconditions only logs
- W17-04/W16-10: Dual execution in promotion_service
- W17-05: Approval routes have async hazards (create_task without await)
- W17-06: Feedback outcome uses staging counts, not DB
- W17-07: Serving gates check `approved` not `ACTIVE + receipt`
- W17-08: Fault-injection tests have tautologies
- W17-09/W16-13: Metrics in local lists
- W17-10/W16-11: Manifest validation doesn't recompute bytes
- W17-11/W16-12: source_row_ids truncated at 50
- W17-12/W16-14: Feedback package absent
- W17-13: Top-AMC semantic mismatch
- W17-14: Migration 009 not verified
- W17-15: Graph Cypher path interpolation security
- W17-16: Proposal/patch state mismatch
- W17-17: Broken promotion route (get_patch, _execute_vector_activation missing)

## Decision Log

| ID | Decision | Status |
|------|----------|--------|
| R01/Feedback-package | Restore to compatibility branch until owner decision | BLOCKED |
| G05 | Fix approval routes (async hazards, missing methods) | IN_PROGRESS |
| CI-fix | Use official gitleaks binary or GitHub Action | IN_PROGRESS |

## Implementation Plan

1. **Batch A (CI + Governance)** - Fix CI workflow, normalize approval endpoints, fix promotion route
2. **Batch B (Durable Publication)** - Durable staging, FAISS generations, graph rollback
3. **Batch C (Outbox + Feedback)** - Authoritative worker, causal state
4. **Batch D (Financial)** - AAUM policy, Decimal math, provenance
5. **Batch E (Verification)** - Fault-injection tests, migration rehearsal, release ledger
