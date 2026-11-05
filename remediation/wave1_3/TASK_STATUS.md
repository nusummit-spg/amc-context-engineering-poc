# Wave 1.3 Task Status

**Branch:** `feature/wave1-3-truth-and-financial-correctness`  
**Updated:** 5 November 2026  
**Execution:** Kiro AI Agent

## Batch A — P0 Truth/Scope Containment

| Task | Status | Evidence | Notes |
|------|--------|----------|-------|
| **A01** | PENDING | - | Replace mock Admin success |
| **A02** | IN_PROGRESS | - | Close Repair read access |
| **A03** | IN_PROGRESS | - | Token trust boundaries |
| **A04** | PENDING | - | Four-eyes enforcement |
| **A05** | PENDING | - | Harden invitations |
| **A06** | PENDING | - | Remove skipped tests |

## Batch B — Repair Lifecycle & Publication

| Task | Status | Evidence | Notes |
|------|--------|----------|-------|
| **B01-B07** | BLOCKED | Requires Batch A | Authoritative state machine |

## Batch C — Financial Correctness

| Task | Status | Evidence | Notes |
|------|--------|----------|-------|
| **C01-C08** | BLOCKED | Requires Batch B | Metric authority, exact arithmetic |

## Batch D — Query Routing & UI

| Task | Status | Evidence | Notes |
|------|--------|----------|-------|
| **D01-D05** | BLOCKED | Requires Batch C | Fail-closed routing |

## Batch E — Independent Assurance

| Task | Status | Evidence | Notes |
|------|--------|----------|-------|
| **E01-E06** | BLOCKED | Requires Batch D | Fresh clone, CI, release gates |

---

## Task Detail Log

### A02 - Close Repair Read Access (IN_PROGRESS)
**Started:** 5 Nov 2026  
**Files Modified:**
- `packages/amc-repair-engine/src/amc_repair/server.py`

**Changes:**
- Adding authentication to `GET /api/patches/for-entities`
- Adding authentication to `GET /api/patches/{patch_id}`
- Adding tenant filtering to prevent cross-tenant disclosure
- Distinguishing serving API from reviewer endpoints

**Tests Required:**
- Unauthenticated GET → 401
- Wrong scope → 403
- Cross-tenant → 403/404
- Valid reviewer gets authorized review records only

### A03 - Token Trust Boundaries (IN_PROGRESS)
**Started:** 5 Nov 2026  
**Files Modified:**
- `packages/amc-repair-engine/src/amc_repair/auth.py`

**Changes:**
- Require `exp` field and validate expiration strictly
- Add issuer (`iss`), audience (`aud`), token type validation
- Separate service scopes from approval authority
- Service identity cannot constitute human approval alone
- Production startup validation for strong secrets

**Tests Required:**
- Missing exp → reject
- Expired token → reject
- Wrong issuer/audience → reject
- Service token with only `patch_read` attempting approve → reject
- Tampered signature → reject

---

**Implementation Notes:**
- All changes on feature branch
- Tests must be run, not just written
- Evidence recorded with SHA, commands, exit codes
- Rollback plan documented per major change
