# Wave 1.3 Task Status

**Branch:** `feature/wave1-3-truth-and-financial-correctness`  
**Updated:** 5 November 2026  
**Execution:** Kiro AI Agent

## Batch A — P0 Truth/Scope Containment

| Task | Status | Evidence | Notes |
|------|--------|----------|-------|
| **A01** | PENDING | - | Replace mock Admin success |
| **A02** | ✅ DONE | SHA: 4f1e968, 31 tests passing | Close Repair read access |
| **A03** | ✅ DONE | SHA: 4f1e968, 31 tests passing | Token trust boundaries |
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

### A02 - Close Repair Read Access (✅ DONE)
**Completed:** 5 Nov 2026  
**SHA:** 4f1e968  
**Files Modified:**
- `packages/amc-repair-engine/src/amc_repair/server.py`

**Changes Implemented:**
- ✅ Added authentication to `GET /api/patches/for-entities`
- ✅ Added authentication to `GET /api/patches/{patch_id}`
- ✅ Tenant filtering to prevent cross-tenant disclosure
- ✅ Requires reviewer/admin role or patch_read service scope
- ✅ Returns 401 unauthenticated, 403 forbidden, 404 cross-tenant

**Tests Created:** `test_wave13_auth_hardening.py`
- ✅ Unauthenticated GET → 401 (2 tests)
- ✅ Wrong scope → 403 (2 tests)
- ✅ Cross-tenant → 403/404 (1 test)
- ✅ Valid reviewer/admin gets authorized records (4 tests)
- **Result:** 9/9 tests passing

**Security Impact:** Closes C-03 (P0 unauthenticated data disclosure)

### A03 - Token Trust Boundaries (✅ DONE)
**Completed:** 5 Nov 2026  
**SHA:** 4f1e968  
**Files Modified:**
- `packages/amc-repair-engine/src/amc_repair/auth.py`

**Changes Implemented:**
- ✅ Require `exp` field (configurable ALLOW_MISSING_EXP for migration)
- ✅ Validate expiration strictly
- ✅ Add issuer (`iss`) validation against EXPECTED_ISSUER
- ✅ Add audience (`aud`) validation against EXPECTED_AUDIENCE
- ✅ Add token_type enforcement (service/user/delegation)
- ✅ Service scope allowlist validation on issuance
- ✅ Service requires explicit `patch_approve` scope to approve (C-04 fix)
- ✅ Service requires explicit `patch_promote` scope to promote
- ✅ Production startup blocks with weak/default secrets

**Tests Created:** `test_wave13_auth_hardening.py`
- ✅ Missing exp → reject (1 test)
- ✅ Expired token → reject (1 test)
- ✅ Wrong issuer → reject (1 test)
- ✅ Wrong audience → reject (1 test)
- ✅ Missing token_type → reject (1 test)
- ✅ Tampered signature → reject (1 test)
- ✅ Wrong secret → reject (1 test)
- ✅ Service scope enforcement (8 tests)
- ✅ Service token issuance validation (3 tests)
- ✅ Integration tests (3 tests)
- **Result:** 22/22 tests passing

**Security Impact:** Closes C-04 (P0 service scope escalation), C-05 (P0 weak token validation)

---

**Implementation Notes:**
- All changes on feature branch
- Tests must be run, not just written
- Evidence recorded with SHA, commands, exit codes
- Rollback plan documented per major change
