# Repair Authentication and State Management

**Wave 1.3 Batch A** - Security Hardening Implementation  
**Date:** 5 November 2026  
**Tasks:** A02 (Read Access Control) + A03 (Token Trust Boundaries)

## A02: Close Repair Read Access (DONE ✓)

### Problem (C-03)
Two Repair endpoints allowed unauthenticated access to patch data including pending corrections and provenance:
- `GET /api/patches/for-entities`
- `GET /api/patches/{patch_id}`

This created a data disclosure risk if the service was network-reachable.

### Solution Implemented

**File:** `packages/amc-repair-engine/src/amc_repair/server.py`

#### Changes to `get_patches_for_entities`:
```python
async def get_patches_for_entities(
    entity_ids: str,
    user: RepairUser = Depends(get_current_user)  # ✓ Added authentication
):
```

- Added `user: RepairUser = Depends(get_current_user)` dependency
- Requires `reviewer` or `admin` role for human users
- Service tokens allowed with `patch_read` scope
- Tenant filtering: filters patches to user's tenant unless service has `tenant:all` scope
- Returns 401 for unauthenticated, 403 for wrong scope/cross-tenant

#### Changes to `get_patch_by_id`:
```python
async def get_patch_by_id(
    patch_id: str,
    user: RepairUser = Depends(get_current_user)  # ✓ Added authentication
):
```

- Added authentication dependency
- Requires `reviewer` or `admin` role
- Tenant isolation: returns 404 for cross-tenant access (not 403 to avoid tenant enumeration)
- Logs access attempts with user and tenant context

### Tests Created

**File:** `packages/amc-repair-engine/tests/test_wave13_auth_hardening.py`

- `TestA02GetPatchesByEntity` (5 tests)
  - ✓ Unauthenticated → 401
  - ✓ Authenticated reviewer → allowed
  - ✓ Authenticated admin → allowed
  - ✓ Analyst without reviewer → 403
  - ✓ Service with patch_read → allowed

- `TestA02GetPatchById` (3 tests)
  - ✓ Unauthenticated → 401
  - ✓ Authenticated reviewer → allowed
  - ✓ Analyst without reviewer → 403

- `TestA02TenantIsolation` (1 test)
  - ✓ Verifies tenant scoping logic

**Test Results:** All A02 tests **PASSED** (9/9)

---

## A03: Token Trust Boundaries (DONE ✓)

### Problems (C-04, C-05, C-06)

**C-04:** `RepairUser.can_approve()` allowed any `is_service` to approve without explicit scope  
**C-05:** Token validation accepted missing `exp`, no issuer/audience enforcement, development secret default  
**C-06:** Main app / Repair service token interoperability unclear

### Solution Implemented

**File:** `packages/amc-repair-engine/src/amc_repair/auth.py`

#### 1. Production Secret Validation
```python
def _validate_production_secret():
    """Validate that production environments use strong secrets."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env in ["production", "prod", "staging"]:
        if SERVICE_SECRET == "development-secret-change-in-production":
            raise RuntimeError(
                f"FATAL: Repair service cannot start in {env} environment..."
            )
```

- Module-level validation runs at import time
- **Blocks startup** in production/staging with default secret
- Warns if secret is weak (< 32 characters)

#### 2. Mandatory Token Fields
```python
# Configuration
EXPECTED_ISSUER = os.getenv("REPAIR_TOKEN_ISSUER", "amc-context-engine")
EXPECTED_AUDIENCE = os.getenv("REPAIR_TOKEN_AUDIENCE", "repair-service")
ALLOW_MISSING_EXP = os.getenv("REPAIR_ALLOW_MISSING_EXP", "false").lower() == "true"
```

**Enhanced `verify_token_signature`:**
- ✓ Requires `exp` field (unless `ALLOW_MISSING_EXP=true` for backward compat)
- ✓ Validates expiration strictly
- ✓ Validates issuer (`iss`) matches `EXPECTED_ISSUER`
- ✓ Validates audience (`aud`) matches `EXPECTED_AUDIENCE`
- ✓ Requires `token_type` field presence
- ✓ Validates token_type is one of: `service`, `user`, `delegation`

#### 3. Service Scope Enforcement (C-04 FIX)
```python
def can_approve(self) -> bool:
    """Check if user can approve patches.
    
    A03 FIX (C-04): Service identity alone does NOT constitute approval authority.
    Service tokens must have explicit 'patch_approve' scope.
    """
    if self.is_service:
        return "patch_approve" in self.roles  # ✓ Explicit scope required
    return self.has_role("reviewer") or self.has_role("admin")

def can_promote(self) -> bool:
    """Check if user can promote patches to production.
    
    A03 FIX: Service needs explicit patch_promote scope.
    """
    if self.is_service:
        return "patch_promote" in self.roles  # ✓ Explicit scope required
    return self.has_role("admin")
```

**Before:** Any `is_service=True` could approve  
**After:** Service must have `patch_approve` in scopes list

#### 4. Enhanced Service Token Issuance
```python
def issue_service_token(
    service_name: str,
    scopes: list[str],
    tenant_id: Optional[str] = None,  # ✓ Added tenant scoping
    secret: str = SERVICE_SECRET,
    ttl_minutes: int = 60
) -> tuple[str, int]:
```

**Enhancements:**
- ✓ Validates scopes against allowlist: `patch_read`, `patch_create`, `patch_approve`, `patch_promote`, `tenant:all`
- ✓ Raises `ValueError` for invalid scopes
- ✓ Includes `iss`, `aud`, `token_type` in payload
- ✓ Supports optional `tenant_id` for tenant-scoped service operations
- ✓ All tokens have mandatory `exp` field

### Allowed Service Scopes

| Scope | Purpose | Risk Level |
|-------|---------|------------|
| `patch_read` | Read patch data | Low |
| `patch_create` | Create new patches | Medium |
| `patch_approve` | Approve patches (explicit grant) | **High** |
| `patch_promote` | Promote to production | **High** |
| `tenant:all` | Cross-tenant access | **Very High** |

### Tests Created

**File:** `packages/amc-repair-engine/tests/test_wave13_auth_hardening.py`

- `TestA03TokenValidation` (8 tests)
  - ✓ Valid token accepted
  - ✓ Missing exp → rejected
  - ✓ Expired token → rejected
  - ✓ Wrong issuer → rejected
  - ✓ Wrong audience → rejected
  - ✓ Missing token_type → rejected
  - ✓ Tampered signature → rejected
  - ✓ Wrong secret → rejected

- `TestA03ServiceScopeEnforcement` (8 tests)
  - ✓ Service with patch_approve can approve
  - ✓ Service without patch_approve **cannot** approve (C-04 FIX)
  - ✓ Generic service cannot approve
  - ✓ Human reviewer can approve
  - ✓ Human admin can approve
  - ✓ Human analyst cannot approve
  - ✓ Service with patch_promote can promote
  - ✓ Service without patch_promote cannot promote

- `TestA03IssueServiceToken` (3 tests)
  - ✓ Valid service token issuance
  - ✓ Invalid scope → ValueError
  - ✓ Service token has required fields

- `TestA02A03Integration` (3 tests)
  - ✓ Expired token cannot read
  - ✓ Service without approve scope cannot approve
  - ✓ Tampered token universally rejected

**Test Results:** All A03 tests **PASSED** (22/22)

---

## Environment Configuration

### Required Environment Variables

**Repair Service:**
```bash
# Required in production/staging
REPAIR_SERVICE_SECRET=<strong-32+-char-secret>
ENVIRONMENT=production

# Token validation (optional, defaults shown)
REPAIR_TOKEN_ISSUER=amc-context-engine
REPAIR_TOKEN_AUDIENCE=repair-service
REPAIR_ALLOW_MISSING_EXP=false  # Set true only for migration period

# Neo4j and Redis (unchanged)
NEO4J_URI=bolt://localhost:7687
USE_REDIS=true
```

**Main Application:**
Should issue tokens with matching issuer/audience when calling Repair service.

---

## Security Improvements Summary

| Defect ID | Status | Fix |
|-----------|--------|-----|
| **C-03** | ✅ FIXED | Repair read endpoints now require authentication and tenant filtering |
| **C-04** | ✅ FIXED | Service identity alone cannot approve; explicit `patch_approve` scope required |
| **C-05** | ✅ FIXED | Mandatory exp/iss/aud/token_type validation; production secret enforcement |
| **C-06** | 🔄 PARTIAL | Token structure documented; main app must include iss/aud/token_type fields |

---

## Integration Requirements

### For Main Application → Repair Service Calls

When main application calls Repair service, it must:

1. **Issue tokens with required fields:**
   ```json
   {
     "token_type": "service",
     "service_name": "amc-main-app",
     "scopes": ["patch_read", "patch_create"],
     "tenant_id": "tenant1",
     "iat": 1730822400,
     "exp": 1730826000,
     "iss": "amc-context-engine",
     "aud": "repair-service"
   }
   ```

2. **Use same REPAIR_SERVICE_SECRET** for signing

3. **Request only necessary scopes:**
   - Feedback → Repair: `["patch_create"]`
   - Admin → Repair read: `["patch_read"]`
   - Governance → Repair approve: `["patch_approve"]` (requires explicit authorization)

### For User Sessions → Repair Service

Options:
1. **Token exchange:** Main app exchanges user session for Repair-specific delegated token
2. **Dual-signed tokens:** User token includes both main and repair claims
3. **Service proxy:** Main app proxies all Repair calls with service token

**Recommended:** Token exchange with short-lived delegation tokens (5-15 minutes).

---

## Test Evidence

**Command:**
```powershell
cd packages/amc-repair-engine
python -m pytest tests/test_wave13_auth_hardening.py -v
```

**Result:**
```
======================= 31 passed, 5 warnings in 6.34s ========================
```

**Breakdown:**
- A02 tests: 9 passed
- A03 tests: 22 passed
- Total: 31 passed, 0 failed, 0 skipped

**SHA:** (To be recorded on commit)

---

## Rollback Plan

If these changes cause integration issues:

1. **Emergency:** Set `REPAIR_ALLOW_MISSING_EXP=true` for backward compatibility
2. **Revert auth.py changes** to previous version
3. **Keep read endpoint auth** (A02) - this is a pure security improvement
4. **Update main app tokens** to include required fields before re-enabling

**Rollback risk:** Low - changes are additive security hardening, not functional changes.

---

## Next Steps (Batch A Remaining)

- **A01:** Replace mock Admin success responses with real effects
- **A04:** Enforce four-eyes across all approval paths (main + microservice)
- **A05:** Harden invitation tokens (hash storage, single-use)
- **A06:** Remove skipped tests, add real JWT fixtures

**Status:** A02 ✅ DONE | A03 ✅ DONE | A01 ⏳ NEXT | A04 ⏳ PENDING | A05 ⏳ PENDING | A06 ⏳ PENDING
