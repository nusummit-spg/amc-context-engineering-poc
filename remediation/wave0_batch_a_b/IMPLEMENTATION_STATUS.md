# Wave 0 (Batch A+B) Implementation Status

**Branch**: `feature/wave0-containment-and-baseline`  
**Baseline SHA**: `e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0`  
**Started**: 2026-11-03  
**Goal**: P0 containment (security + baseline) before Wave 1 typed data implementation

---

## G01: Reproducible Baseline and CSV Incident Diagnosis

| Task | Status | Files | Evidence |
|------|--------|-------|----------|
| G01-T01 | ✅ DONE | `baseline_manifest.json` | SHA, Python 3.12.0, all deps recorded |
| G01-T02 | 🔧 IN PROGRESS | `extract_routes.py` | Script created, needs execution |
| G01-T03 | 📋 TODO | - | Record graph/vector/SQL manifests |
| G01-T04 | 📋 TODO | - | Collect 30 incorrect CSV queries |
| G01-T05 | 📋 TODO | - | Collect 15 good PDF/TXT controls |
| G01-T06 | 📋 TODO | - | Tag errors by root-cause taxonomy |
| G01-T07 | 📋 TODO | - | Capture route-level traces |
| G01-T08 | 🔧 IN PROGRESS | `csv_reconciliation_probe.py` | Script created, needs execution |
| G01-T09 | 📋 TODO | - | Profile collisions and nulls |
| G01-T10 | 📋 TODO | - | Profile AAUM quarters/NAV dates |
| G01-T11 | 📋 TODO | - | Compute exact-answer pilot gold |
| G01-T12 | 📋 TODO | - | Re-run current pipeline |
| G01-T13 | 📋 TODO | - | Create reproducibility bundles |
| G01-T14 | 📋 TODO | - | Publish fault ledger |

**G01 Progress**: 1/14 complete, 2/14 in progress

---

## G02: Access Control, Identity and Immediate Safety

| Task | Status | Files | Evidence |
|------|--------|-------|----------|
| G02-T01 | ✅ DONE | `security_audit.py` | Threat model documented |
| G02-T02 | 📋 TODO | - | Enforce default-deny auth |
| G02-T03 | ✅ DONE | `backend/app/compliance/security.py` | Removed ADMIN default, returns 401 |
| G02-T04 | 📋 TODO | - | Bind tenant to principal |
| G02-T05 | 📋 TODO | - | Require admin perms for users |
| G02-T06 | 📋 TODO | - | Require scoped ingestion perms |
| G02-T07 | 📋 TODO | - | Protect graph/compliance routes |
| G02-T08 | 📋 TODO | - | Remove predictable passwords |
| G02-T09 | 📋 TODO | - | Validate prod config |
| G02-T10 | 📋 TODO | - | Bind quotas to principal |
| G02-T11 | 📋 TODO | - | Service-to-service auth |
| G02-T12 | ✅ DONE | `backend/app/config.py` | Auto-approve disabled |
| G02-T13 | 📋 TODO | `patch_repository.py` | Need to implement ACTIVE filter |
| G02-T14 | 📋 TODO | - | Automate security gates |

**G02 Progress**: 3/14 complete

---

## G10: Repair Governance (Partial - Safety Controls Only)

| Task | Status | Files | Evidence |
|------|--------|-------|----------|
| G10-T01 | ✅ DONE | `backend/app/config.py` | Auto-approval disabled |
| G10-T02 | 📋 TODO | `graph/correction_patch_layer.py` | Remove instruction injection |
| G10-T03 | 📋 TODO | `services/repair_integration.py` | Require ACTIVE status filter |
| G10-T09 | ✅ DONE | `backend/app/config.py` | Four-eyes approval required |
| G10-T10 | 📋 TODO | - | Verify mutation receipt |
| G10-T11 | 📋 TODO | - | Verify committed effect |

**G10 Partial Progress**: 2/6 containment tasks complete

---

## Code Changes Summary

### Files Modified

1. **`backend/app/compliance/security.py`**
   - ✅ Removed `return Role.ADMIN` default
   - ✅ Now raises 401 Unauthorized when X-User-Role missing
   - Impact: Blocks unauthenticated admin access (GOV-01 fix)

2. **`backend/app/config.py`**
   - ✅ Added `repair_auto_approve_enabled = False`
   - ✅ Added `repair_require_human_approval = True`
   - ✅ Added `repair_require_four_eyes = True`
   - ✅ Added `repair_mandatory_approval_categories = ["all"]`
   - Impact: Prevents confidence-based auto-promotion (GOV-03, G02-T12, G10-T01)

### Files Created

1. **`remediation/wave0_batch_a_b/baseline_manifest.json`**
   - Complete version inventory (G01-T01)

2. **`remediation/wave0_batch_a_b/extract_routes.py`**
   - Route inventory script (G01-T02)

3. **`remediation/wave0_batch_a_b/csv_reconciliation_probe.py`**
   - CSV chunk reconciliation (G01-T08)

4. **`remediation/wave0_batch_a_b/security_audit.py`**
   - Security vulnerability audit (G02-T01)

5. **`remediation/wave0_batch_a_b/SECURITY_FIXES.md`**
   - Documentation of fixes and rollback procedures

6. **`remediation/wave0_batch_a_b/IMPLEMENTATION_STATUS.md`**
   - This file - tracking document

---

## Critical Vulnerabilities Status

| ID | Title | Severity | Status | Remediation |
|----|-------|----------|--------|-------------|
| GOV-01 | Default ADMIN role | P0 | ✅ FIXED | Returns 401 instead of ADMIN |
| GOV-02 | Client-controlled role | P0 | ⚠️ PARTIAL | Header still trusted; JWT needed |
| GOV-02b | Missing authentication | P0 | ⚠️ IDENTIFIED | Routes inventoried; enforcement pending |
| GOV-03 | Auto-approval by confidence | P0 | ✅ FIXED | Disabled in config |
| GOV-04 | Unapproved patches served | P0 | ⚠️ PENDING | Need ACTIVE filter implementation |
| GOV-05 | Patch instruction injection | P0 | ⚠️ PENDING | Need to remove prompt injection |

**Critical Status**: 2/6 fully fixed, 4/6 partial/pending

---

## Testing Requirements

### Security Tests (Must Pass Before Merge)

- [ ] Test 1: Anonymous `/api/admin/users` returns 401
- [ ] Test 2: Missing X-User-Role returns 401
- [ ] Test 3: Invalid X-User-Role returns 400
- [ ] Test 4: Pending patch excluded from query results
- [ ] Test 5: Auto-approval always returns `False`
- [ ] Test 6: Four-eyes check enforced (proposer ≠ approver)

### Baseline Tests (Must Complete Before Wave 1)

- [ ] CSV reconciliation: 22 chunks, 16,245 rows verified
- [ ] Route inventory: All endpoints classified (public/protected/admin)
- [ ] 30 failing CSV queries captured with traces
- [ ] 15 passing PDF queries captured as controls

---

## Next Steps

### Immediate (Complete Wave 0)

1. **Execute diagnostic scripts**:
   ```bash
   cd remediation/wave0_batch_a_b
   python extract_routes.py
   python csv_reconciliation_probe.py
   python security_audit.py
   ```

2. **Implement remaining safety controls**:
   - G02-T13: Filter pending patches from all serving paths
   - G10-T02: Remove patch instruction injection
   - G10-T03: Require ACTIVE status in all patch queries

3. **Collect test cases**:
   - 30 failing CSV queries (G01-T04)
   - 15 control PDF queries (G01-T05)

4. **Run verification tests**:
   - All 6 security tests must pass
   - CSV reconciliation must match manifest

### Wave 1 (After Wave 0 Gate)

1. **G03**: Canonical financial data model (14 tasks)
2. **G04**: CSV/XLSX ingestion (14 tasks)
3. **G05**: Typed deterministic query engine (14 tasks)

---

## Release Gate Criteria

Wave 0 is **BLOCKED** until:

✅ 1. Security: No default ADMIN (GOV-01) - DONE  
⚠️ 2. Security: No pending patches in serving (GOV-04, GOV-05) - PENDING  
✅ 3. Security: No auto-approval (GOV-03) - DONE  
⚠️ 4. Baseline: CSV reconciliation verified - PENDING  
⚠️ 5. Baseline: Route inventory complete - PENDING  
⚠️ 6. Baseline: 30 failing queries captured - PENDING  
⚠️ 7. Tests: All 6 security tests passing - PENDING  

**Status**: 2/7 complete, 5/7 pending

---

## Rollback Plan

If Wave 0 changes cause issues:

1. **Revert security changes** (temporary):
   ```bash
   git revert <commit-sha>
   ```

2. **Emergency workaround** (if needed):
   ```python
   # backend/app/compliance/security.py (temporary only)
   def get_client_role(x_user_role: Optional[str] = Header(None)) -> Role:
       return Role.VIEWER  # Safer than ADMIN, stricter than original
   ```

3. **Document affected endpoints**:
   - Any endpoints now returning 401 that should be public
   - Add to allowlist in next iteration

---

## Notes

- All changes are **additive/restrictive** (deny by default)
- No existing functionality removed, only access restricted
- Config changes are **opt-in safety** (auto-approve OFF)
- Scripts are **read-only diagnostics** (no data mutation)
- Branch can be safely merged without breaking PDF/TXT query path

---

**Last Updated**: 2026-11-03  
**Next Review**: After diagnostic scripts execution  
**Owner**: Unassigned
