# Wave 1.3 Batch B Progress

**Started:** 5 November 2026  
**Branch:** `feature/wave1-3-truth-and-financial-correctness`  
**Focus:** Repair Lifecycle & Publication Integrity

## Batch B Tasks

| Task | Status | Description |
|------|--------|-------------|
| **B01** | IN_PROGRESS | Single persisted correction state machine |
| **B02** | PENDING | Remove pending content from serving vector |
| **B03** | PENDING | Graph mutation exact-value verification |
| **B04** | PENDING | Real vector reindex, commit and activation |
| **B05** | PENDING | Cross-store transactional outbox/saga |
| **B06** | PENDING | Feedback → Repair resolution integrity |
| **B07** | PENDING | Microservice/monolith/streaming parity |

---

## B01: State Machine Implementation (IN_PROGRESS)

### Design: Versioned State Flow

```
PENDING → APPROVED → STAGED → VERIFIED → ACTIVE
   ↓         ↓          ↓         ↓          ↓
REJECTED  REJECTED   FAILED   FAILED   ROLLED_BACK
                                ↓
                            SUPERSEDED
```

### State Definitions

| State | Meaning | Can Serve? | Next States |
|-------|---------|------------|-------------|
| **PENDING** | Created, awaiting approval | ❌ | APPROVED, REJECTED |
| **APPROVED** | Human approved, not published | ❌ | STAGED, REJECTED |
| **STAGED** | Queued for publication | ❌ | VERIFIED, FAILED |
| **VERIFIED** | Published and verified | ❌ | ACTIVE, FAILED |
| **ACTIVE** | Serving in answers | ✅ | ROLLED_BACK, SUPERSEDED |
| **REJECTED** | Declined by reviewer | ❌ | Terminal |
| **FAILED** | Technical failure | ❌ | Terminal (retry as new) |
| **ROLLED_BACK** | Reverted after deployment | ❌ | Terminal |
| **SUPERSEDED** | Replaced by newer version | ❌ | Terminal |

### Key Principles

1. **Approval ≠ Publication** - APPROVED means authorized, not active
2. **ACTIVE requires receipt** - Must have publication_receipt and verified_at
3. **Only ACTIVE patches serve** - All other states excluded from answers
4. **Backward compatible** - `approved` boolean computed from status

### Implementation Changes

#### Schema (`packages/amc-repair-engine/src/amc_repair/schemas.py`)

```python
class PatchStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    STAGED = "STAGED"
    VERIFIED = "VERIFIED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    SUPERSEDED = "SUPERSEDED"

class CorrectionPatch(BaseModel):
    # State machine
    status: PatchStatus = PatchStatus.PENDING
    
    # Transition tracking
    approved_at: Optional[str]
    approved_by: Optional[str]
    staged_at: Optional[str]
    verified_at: Optional[str]
    activated_at: Optional[str]
    
    # Publication evidence
    publication_receipt: Optional[Dict[str, Any]]
    active_dataset_version: Optional[str]
    active_corpus_version: Optional[str]
    
    def can_serve(self) -> bool:
        """Only ACTIVE + verified + receipt can serve."""
        return (
            self.status == PatchStatus.ACTIVE and
            self.publication_receipt is not None and
            self.verified_at is not None
        )
```

### Next Steps for B01

1. ✅ Define PatchStatus enum
2. ✅ Add state fields to CorrectionPatch
3. ✅ Add can_serve() method
4. ⏳ Update patch_layer.py for state transitions
5. ⏳ Update server.py approval to set APPROVED status
6. ⏳ Add state validation (allowed transitions)
7. ⏳ Update retrieval to filter can_serve() only
8. ⏳ Create tests for state machine

---

## Defects Targeted by Batch B

| ID | Severity | Description | Batch B Task |
|----|----------|-------------|--------------|
| **C-08** | P0 | No authoritative ACTIVE state | B01 |
| **C-09** | P0 | Unapproved content in serving vector | B02 |
| **C-10** | P0 | Phantom publication success (log-only reindex) | B04 |
| **C-11** | P0 | Graph postcondition insufficient | B03 |
| **C-06** | P0 | Feedback resolution without verification | B06 |

---

## Critical Requirements

### Publication Integrity (B01, B04, B05)

- STAGED patches queued with idempotency key
- VERIFIED requires actual index version readback
- ACTIVE requires publication_receipt with:
  - Graph mutation ID (if applicable)
  - Vector index version
  - Dataset version
  - Timestamp
  - Verifier identity

### Vector Isolation (B02)

- Remove synthetic patch insertion into serving FAISS
- Use review-only shadow index OR defer until VERIFIED
- Migrate/clean existing provisional entries
- Invalidate caches only on ACTIVE version switch

### Graph Verification (B03)

- Exact typed value comparison (not just node presence)
- Allowlisted parameterized mutations
- Store immutable receipt: old value → new value → verified value
- Fail closed on wrong value, conflict, or driver unavailable

### Saga Pattern (B05)

- One proposal per SQL transaction
- Outbox command staged before external effect
- Idempotency key: proposal_id + evidence_version + destination
- Record EXTERNAL_APPLIED and VERIFIED separately
- Handle crash between commits
- Compensating rollback without affecting unrelated commits

---

## Testing Strategy for Batch B

### B01 State Machine Tests
- Invalid transition rejected (PENDING → ACTIVE)
- Valid transition allowed (PENDING → APPROVED)
- can_serve() only true for ACTIVE + receipt + verified
- Backward compat: approved computed correctly

### B02 Vector Isolation Tests
- Pending patch not in serving vector
- APPROVED patch not in serving vector
- ACTIVE patch IS in serving vector
- Cache invalidation only on ACTIVE switch

### B03 Graph Verification Tests
- Wrong value rejected
- Node presence without value rejected
- Exact match accepted
- Conflict detected and handled

### B04 Reindex Tests
- No-job → FAILED
- Stale index → not VERIFIED
- Success → VERIFIED with receipt

### B05 Saga Tests
- Duplicate request → idempotent
- Crash after graph before SQL → recoverable
- Rollback → compensating action
- Concurrent promotions → serialized

---

## Migration Plan

### Database Changes Required

1. **Add status column** to patches table
2. **Migrate existing approved=true** → ACTIVE (if verified) or APPROVED
3. **Migrate existing approved=false** → PENDING
4. **Add transition timestamp** columns
5. **Add publication_receipt JSONB** column

### Backward Compatibility

- Keep `approved` boolean as computed field
- Existing code reading `patch.approved` works
- New code should check `patch.status` and `patch.can_serve()`

---

**Status:** B01 schema defined, implementation in progress  
**Next:** Update patch layer and server for state transitions  
**Branch:** feature/wave1-3-truth-and-financial-correctness
