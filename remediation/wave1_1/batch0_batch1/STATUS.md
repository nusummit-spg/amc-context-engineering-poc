# Wave 1.1 Batch 0 + Batch 1: Status Report

**Branch**: `feature/wave1.1-batch0-batch1-security-containment`  
**Base SHA**: `06cf9755f4b3dde3e9a24a430973f4bf86ed711d`  
**Started**: 2026-11-04  
**Status**: IN PROGRESS

---

## Batch 0: Freeze + Reproduce (G01, G13 preparation)

### Scope
Freeze SHA/data hashes; capture ≥30 failed CSV queries + ≥15 working PDF/TXT controls + execution traces

### W1.1 Tasks Covered
- Preparation tasks for W1.1-13 (Independent correctness)

| Task | Status | Evidence | Blocker |
|------|--------|----------|---------|
| Freeze branch SHA | ✅ DONE | `06cf9755f4b3dde3e9a24a430973f4bf86ed711d` | None |
| Active dataset hash | ✅ DONE | `v1_baseline` with 16,245 rows | None |
| Capture execution traces | 🔧 IN PROGRESS | Trace collection script ready | None |
| CSV failure examples | 📋 PENDING | Need to execute failing queries | None |
| PDF/TXT control set | 📋 PENDING | Need working control queries | None |

---

## Batch 1: Immediate Security & Repair Containment (G02, G10)

### Scope
No forged-header elevation, anonymous mutators, auto approval, unapproved patch serving, or unverified promotion

### W1.1 Tasks Covered
**W1.1-10**: Identity-derived access (P0)  
**W1.1-11**: One Repair approval authority (P0)  
**W1.1-12**: Publication result integrity & rollback (Protective portion - P0)

| Task ID | Description | Status | Evidence | Blocker |
|---------|-------------|--------|----------|---------|
| **W1.1-10** | Identity-derived access | 🔧 IN PROGRESS | Security routes audit in progress | None |
| W1.1-10.1 | Remove X-User-Role trust | 📋 PENDING | Code review needed | None |
| W1.1-10.2 | Enforce CurrentUser dependency | 📋 PENDING | Route inventory needed | None |
| W1.1-10.3 | Remove default credentials | 📋 PENDING | Config audit needed | None |
| W1.1-10.4 | Bind quotas to verified identity | 📋 PENDING | Quota service review needed | None |
| **W1.1-11** | Repair approval authority | 📋 PENDING | Governance routes audit | None |
| W1.1-11.1 | Disable confidence-based approval | 📋 PENDING | repair_integration.py review | None |
| W1.1-11.2 | Enforce human approval | 📋 PENDING | Approval workflow design | None |
| W1.1-11.3 | Four-eyes separation | 📋 PENDING | Authorization policy | None |
| **W1.1-12** | Publication integrity (protective) | 📋 PENDING | Promotion service audit | None |
| W1.1-12.1 | Verify graph commit receipts | 📋 PENDING | promotion_service.py review | None |
| W1.1-12.2 | Fail-closed on driver unavailable | 📋 PENDING | Error handling hardening | None |
| W1.1-12.3 | Add idempotency keys | 📋 PENDING | Event design | None |

---

## Release Gate Status

### Security Gate (SEC)
- [ ] Anonymous sensitive API access blocked
- [ ] Header-spoof privilege elevation prevented
- [ ] Cross-tenant retrieval forbidden
- [ ] Default credentials removed
- [ ] Negative test matrix complete

### Repair Governance Gate (REP - Protective)
- [ ] Automatic approval disabled
- [ ] Pending patches excluded from serving
- [ ] Graph mutation receipt verified
- [ ] No phantom APPLIED status

---

## Dependencies

- ✅ Wave 1 typed query foundation (G03-G05) complete
- ✅ Active dataset version `v1_baseline` established
- 📋 Independent data steward approval for AAUM grain (BLOCKED for W1.1-02, not blocking security work)

---

## Next Steps

1. Complete security route inventory (W1.1-10)
2. Implement CurrentUser enforcement on all sensitive routes
3. Remove X-User-Role trust and default ADMIN
4. Audit and disable auto-approval paths (W1.1-11)
5. Harden promotion service failure handling (W1.1-12)
6. Execute test matrix and capture evidence
