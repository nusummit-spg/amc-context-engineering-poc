# Wave 1.8 Implementation Status

**Date:** 6 November 2026  
**Branch:** amc-dev  
**SHA:** 763c1ec9e57517d97d6880ea79ff9c2ce5c42d36  
**Previous baseline:** bea1fbd4e52fdc93fa064c47ed1377347d3852f7 (Wave 1.7)

## Summary

**Wave 1.8 Progress:** R0-01 to R0-06 complete; R0-07 documentation complete; D1-D2/Q/A batches BLOCKED

## Task Status

| Batch | Tasks | Status |
|-------|-------|--------|
| R0 (CI/Governance) | R0-01 to R0-07 | 6/7 IMPLEMENTED_UNVERIFIED |
| D1 (Durable Foundation) | D1-01 to D1-07 | BLOCKED |
| D2 (External Effects) | D2-01 to D2-08 | BLOCKED |
| Q (Feedback/UI) | Q-01 to Q-05 | BLOCKED |
| A (Assurance) | A-01 to A-05 | BLOCKED |

## Completed Tasks

### R0-01: CI Gitleaks Action
- Changed `gitleaks/gitleaks-action@v8.22.0` to `gitleaks/gitleaks-action@v3`
- Status: IMPLEMENTED_UNVERIFIED - action reference fixed

### R0-02: Required Test Jobs
- Removed `|| exit 0` from test jobs
- Added `exit 1` when test directories missing
- Status: IMPLEMENTED_UNVERIFIED - CI now fails on missing tests

### R0-03: Disable Synthetic Patch Activation
- Changed `/promote/{patch_id}` to return 202 Accepted instead of fake verified=True
- Status: IMPLEMENTED_UNVERIFIED - no ACTIVE state without worker

### R0-04: Seal Every Answer Path
- Added `is_serving_eligible(patch, tenant)` to `correction_patch_layer.py`
- Updated `apply_patches_to_context` to use new function
- Status: IMPLEMENTED_UNVERIFIED - shared eligibility predicate created

### R0-05: Stop Dual Execution
- Removed direct `_execute_graph_mutation` and `_trigger_reindex` from `PromotionService`
- Now creates outbox events only; worker handles execution
- Status: IMPLEMENTED_UNVERIFIED - single authoritative path established

### R0-06: VectorStore Deletion Consistency
- Fixed `delete_by_chunk_id` to remove from both `_payloads` and `_index`
- Added count verification after delete
- Status: IMPLEMENTED_UNVERIFIED - FAISS/consistency maintained

### R0-07: Evidence Reconciliation
- Created `remediation/wave1_8/02_TASK_MATRIX.csv`
- Created `remediation/wave1_8/03_STATUS.md`
- Status: IMPLEMENTED_UNVERIFIED - documentation complete

## Blocked Tasks

### D1-01 to D1-07
- Migration history verification requires disposable PostgreSQL
- Durable repository, idempotency, fencing, leases require implementation
- No test infrastructure to verify

### D2-01 to D2-08
- Exact vector lookup requires new API implementation
- Generation builder, verification, CAS pointer switch require full implementation
- Graph parameterized writes need allowlists and readback verification
- Durable compensation/rollback requires persisted preimages

### Q-01 to Q-05
- Feedback causality requires DB-backed publication receipt queries
- Operational telemetry requires Prometheus metrics integration
- Financial containment needs validation testing
- Data integrity requires byte-level hash verification
- Feedback package requires product-owner decision

### A-01 to A-05
- CI requires verified action run on amc-dev
- Disposable services require Docker/Test containers
- Failure injection requires test suites
- Release evidence requires all preceding tasks
- Canary requires deployment environment

## Files Modified

- `.github/workflows/amc-assurance.yml` - CI fixes
- `backend/app/api/routes/governance.py` - 202 instead of fake ACTIVE
- `backend/app/graph/correction_patch_layer.py` - is_serving_eligible() function
- `backend/app/services/promotion_service.py` - outbox-only execution
- `backend/app/vector/client.py` - fixed delete_by_chunk_id

## Release Gate Decision

**STATUS:** BLOCKED

**Completed:**
- CI workflow fixed (scanner reference, test discovery)
- Governance endpoints normalized (202, shared eligibility)
- Dual execution stopped (outbox-only path)

**Remaining P0 Blockers:**
- D1: Durable foundation (repository, leases, CAS, idempotency)
- D2: Real external effects (exact lookup, generation builder, graph write with readback)
- Q: Feedback causality, telemetry, financial, data integrity
- A: CI evidence, disposable services, failure injection, release gates

**Required before deploy:**
1. D1-01 to D1-07: Durable journal, leases, CAS, idempotency
2. D2-01 to D2-08: Exact vector lookup, generation builder, CAS pointer
3. Q-01 to Q-05: Feedback, telemetry, financial, integrity
4. A-01 to A-05: CI evidence, disposable services, release gates
