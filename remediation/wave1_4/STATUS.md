# Wave 1.4 - Batch A & B Implementation Status

**Date:** 5 November 2026  
**Branch:** amc-dev  
**SHA:** af4dfcc (B01) + eccc075 (Batch A)

## Summary

- **Batch A (A01-A09):** COMPLETE - P0 truth/fail-closed containment fixes
- **Batch B (B01-B10):** B01 COMPLETE - One stored lifecycle state machine

## Completed Tasks

### Batch A (P0 Truth/Fail-Closed)

| Task | Description | Status | Commit |
|------|-------------|--------|--------|
| A01 | Fixed invitation redemption with hash lookup, row locking, rate-limiting | DONE | 9ecc54e |
| A02 | Fixed async promotion route with proper await | DONE | 9ecc54e |
| A03 | Fixed _trigger_reindex with indexer availability check | DONE | 5da8c1e |
| A04 | Fixed outbox handlers to raise NotImplementedError | DONE | 5da8c1e |
| A05 | Fixed rollback handlers to raise RollbackNotImplementedError | DONE | 5da8c1e |
| A06 | Added _is_serving_eligible_patch() for strict ACTIVE check | DONE | e102709 |
| A07 | Added four-eyes check in review_repair_proposal | DONE | 28e14f9 |
| A08 | Admin endpoints return 503 instead of mock data | DONE | eb1999e |
| A09 | Created 18 regression tests | DONE | 136f648 |

### Batch B (Authoritative Repair Lifecycle)

| Task | Description | Status | Commit |
|------|-------------|--------|--------|
| B01 | Implemented PatchStatus state machine with PENDING→APPROVED→STAGED→VERIFIED→ACTIVE | DONE | af4dfcc |

## State Machine Implementation (B01)

### PatchStatus Enum
- PENDING → APPROVED/REJECTED
- APPROVED → STAGED/REJECTED
- STAGED → VERIFIED/FAILED
- VERIFIED → ACTIVE/FAILED
- ACTIVE → ROLLED_BACK/SUPERSEDED
- REJECTED/FAILED/ROLLED_BACK/SUPERSEDED (terminal)

### CorrectionPatch Updates
- Added status field (PatchStatus enum)
- Added transition timestamps: approved_at, staged_at, verified_at, activated_at
- Added publication receipts: publication_receipt, active_dataset_version, active_corpus_version
- Added can_serve() method checking ACTIVE + verified receipt
- Added to_dict() for storage serialization

### New Async Methods
- transition_patch() - validate and apply state transitions
- approve_patch() - PENDING → APPROVED
- reject_patch() - PENDING/APPROVED → REJECTED
- stage_patch() - APPROVED → STAGED
- verify_patch() - STAGED → VERIFIED
- activate_patch() - VERIFIED → ACTIVE
- rollback_patch() - ACTIVE → ROLLED_BACK

## Remaining Tasks

### Batch B (Remaining)

| Task | Description | Priority |
|------|-------------|----------|
| B02 | Approval evidence and four-eyes | High |
| B03 | Real vector index staging | High |
| B04 | Exact graph postconditions | High |
| B05 | One authoritative worker | Medium |
| B06 | Retry/recovery/deduplication | Medium |
| B07 | Real graph rollback | Medium |
| B08 | Real vector rollback | Medium |
| B09 | Unified serving authorization | Medium |
| B10 | End-to-end failure injection | Low |

## Files Modified

- backend/app/api/routes/admin.py (A08)
- backend/app/api/routes/auth.py (A01)
- backend/app/api/routes/governance.py (A02, A07)
- backend/app/exceptions/__init__.py (A05)
- backend/app/retrieval/fast_path_interceptor.py (A06, A09)
- backend/app/services/outbox_processor.py (A04)
- backend/app/services/promotion_service.py (A03)
- backend/app/services/rollback_service.py (A05)
- backend/tests/test_wave14_p0_containment.py (A09)
- backend/app/graph/correction_patch_layer.py (B01)

## Test Results

- test_wave14_p0_containment.py: 18 passing tests
- All commits: Pushed to amc-dev branch

## Next Steps

1. Continue with B02-B10 tasks from Batch B
2. Create integration tests for state machine transitions
3. Update governance endpoints to use new state machine
4. Implement real vector index staging (B03)
5. Implement real graph postconditions (B04)
