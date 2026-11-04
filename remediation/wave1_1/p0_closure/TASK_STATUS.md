# Task Status - Wave 1.1 P0 Closure

**Last Updated:** 2026-11-04

## Security Tasks (SEC-01 through SEC-04)

### SEC-01: Complete Authentication and Endpoint Matrix
**Status:** IN_PROGRESS

**Tasks:**
- [ ] Create missing `admin.py` with authenticated endpoints
- [ ] Build runtime route inventory
- [ ] Classify all sensitive endpoints
- [ ] Add `CurrentUser` dependency to all sensitive routes
- [ ] Add 401/403 negative tests
- [ ] Create public endpoint allowlist

**Files Modified:**
- backend/app/api/routes/admin.py (CREATE)
- backend/app/api/routes/governance.py (UPDATE)
- backend/app/api/routes/ingest.py (REVIEW)
- backend/app/api/routes/audit.py (REVIEW)
- backend/app/api/routes/files.py (REVIEW)

### SEC-02: Server-Authoritative Role and Tenant
**Status:** PENDING

**Tasks:**
- [ ] Remove `Depends(get_client_role)` from governance routes
- [ ] Use JWT-verified role from `CurrentUser`
- [ ] Implement tenant membership verification
- [ ] Add tenant filtering to all data access
- [ ] Test cross-tenant isolation

**Files Modified:**
- backend/app/compliance/security.py (UPDATE)
- backend/app/api/routes/governance.py (UPDATE)

### SEC-03: Secure Enrollment and Credentials
**Status:** PENDING

**Tasks:**
- [ ] Remove "Welcome@2026" default password
- [ ] Implement secure enrollment flow
- [ ] Add password strength validation
- [ ] Implement invitation/reset tokens
- [ ] Remove plaintext credential reflection

**Files Modified:**
- backend/app/auth/service.py (UPDATE)
- backend/app/api/routes/admin.py (UPDATE)

### SEC-04: Service-to-Service Authorization
**Status:** PENDING

**Tasks:**
- [ ] Add workload identity for Repair microservice
- [ ] Verify human approver identity in governance
- [ ] Restrict network ingress (documentation)
- [ ] Add service-to-service auth tests

**Files Modified:**
- backend/packages/amc-repair-engine/src/amc_repair/server.py (REVIEW)
- backend/app/services/repair_integration.py (UPDATE)

## Repair Governance Tasks (REP-01 through REP-05)

### REP-01: Unified Human Approval Policy
**Status:** PENDING

**Tasks:**
- [ ] Disable confidence-based auto-approval in main governance
- [ ] Disable confidence-based auto-approval in microservice
- [ ] Require explicit human authorization
- [ ] Enforce four-eyes (approver != proposer)
- [ ] Add approval audit trail

### REP-02: Patch State Machine
**Status:** PENDING

**Tasks:**
- [ ] Define complete state machine (PENDING → APPROVED → STAGED → ACTIVE)
- [ ] Implement `is_serving_eligible()` check
- [ ] Apply to all retrieval paths
- [ ] Persist state in database

### REP-03: Isolate Synthetic Pending Evidence
**Status:** PENDING

**Tasks:**
- [ ] Create staging/shadow vector index
- [ ] Prevent pending patches from entering serving index
- [ ] Only publish approved corrections
- [ ] Invalidate caches after activation

### REP-04: Audit and Four-Eyes Transitions
**Status:** PENDING

**Tasks:**
- [ ] Persist reviewer, proposer, evidence
- [ ] Reject self-approval
- [ ] Handle concurrent approvals
- [ ] Add revocation support

### REP-05: Module Parity
**Status:** PENDING

**Tasks:**
- [ ] Ensure status check consistency across modules
- [ ] Fix CorrectionPatch schema
- [ ] Update patch layer implementations

## Publication Correctness Tasks (PUB-01 through PUB-04)

### PUB-01: Fix Import and No-op Failures
**Status:** PENDING

### PUB-02: Strong Graph Mutation Postconditions
**Status:** PENDING

### PUB-03: Transactional Recovery
**Status:** PENDING

### PUB-04: Publication State Correctness
**Status:** PENDING

## Quality Assurance Tasks (QA-01 through QA-03)

### QA-01: Create Claimed Test Files
**Status:** PENDING

**Tasks:**
- [ ] Create test_wave1_1_batch0_batch1_security.py
- [ ] Create test_sec01_universal_auth.py
- [ ] Run and verify all tests pass

### QA-02: Adversarial Test Suite
**Status:** PENDING

### QA-03: Real CI and Reporting
**Status:** PENDING

## Financial Correctness Tasks (NUM-01 through NUM-04)

### NUM-01: Metric Approval Enforcement
**Status:** PENDING

### NUM-02: Exact Decimal Arithmetic
**Status:** PENDING

### NUM-03: Fail-Closed for Numbers
**Status:** PENDING

### NUM-04: Canonical Tabular Layer
**Status:** PENDING
