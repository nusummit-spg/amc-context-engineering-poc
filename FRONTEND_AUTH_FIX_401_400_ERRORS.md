# Frontend Authentication Fix: 401 and 400 Errors

**Date:** 2026-11-24  
**Issue:** `/api/feedback/status` endpoint returning 401 Unauthorized and 400 Bad Request  
**Status:** ✅ FIXED

---

## Problem Description

The `/api/feedback/status` endpoint was returning authentication errors when called from the frontend.

### Error 1: 401 Unauthorized
```
GET /api/feedback/status?response_id=resp_b810768f-bca&query=...&session_id=...

Status: 401 Unauthorized
Response:
{
    "detail": "Authentication required: X-User-Role header missing. 
    This endpoint requires authentication. 
    Wave 0 containment: header-based auth is temporary; JWT required in production."
}
```

### Error 2: 400 Bad Request
```
GET /api/feedback/status?response_id=resp_689a6889-8a3&query=...&session_id=...

Status: 400 Bad Request  
Response:
{
    "detail": "Invalid X-User-Role: 'Compliance & Regulatory Officer'. 
    Must be one of: ['viewer', 'reviewer', 'resolver', 'admin', 'compliance_officer']"
}
```

---

## Root Cause Analysis

### Chain of Events

1. **Step 1: Missing X-User-Role Header** (→ 401 Error)
   - The `/api/feedback/status` endpoint requires the `X-User-Role` header for authentication
   - The frontend's `getAuthHeaders()` function only included:
     - `Authorization` header (Bearer token)
     - `X-User-ID` header (username)
   - **Result:** Backend rejected the request with 401 - missing authentication header

2. **Step 2: Invalid Role Value** (→ 400 Error)
   - After fixing Step 1, the `X-User-Role` header was included but with the raw role display name
   - The frontend was storing role as `"Compliance & Regulatory Officer"` (with spaces, special chars)
   - The backend `Role` enum expects snake_case: `compliance_officer`
   - The backend's `get_client_role()` function rejected the value
   - **Result:** Backend rejected the request with 400 - invalid role format

3. **Step 3: Root Cause Discovery**
   - The frontend stores user data from the backend login response
   - The backend's `UserPublic` model includes the raw `role` field
   - The frontend was storing this raw value directly without normalization
   - The backend `Role` enum only accepts: `viewer`, `reviewer`, `resolver`, `admin`, `compliance_officer`

---

## Solution Summary

The fix involves two complementary changes:

1. **Add X-User-Role header to all API requests** by updating `getAuthHeaders()`
2. **Normalize role values** before sending to backend using a `normalizeRole()` function

---

## Implementation Details

### Backend (No Changes Required)

The backend was already correctly configured:

#### `backend/app/models/auth.py` - User Public Model
```python
class UserPublic(BaseModel):
    """Everything the frontend is allowed to see about a user."""
    username: str
    display_name: str
    role: str  # Raw role string sent to frontend
    department: str = ""
    email: str = ""
    avatar_initials: str = ""
    status: str = "Active"
    tenant_id: Optional[str] = None
```

#### `backend/app/models/compliance_models.py` - Role Enum
```python
class Role(str, Enum):
    VIEWER = "viewer"
    REVIEWER = "reviewer"
    RESOLVER = "resolver"
    ADMIN = "admin"
    COMPLIANCE_OFFICER = "compliance_officer"
```

#### `backend/app/compliance/security.py` - Role Validation
```python
def get_client_role(x_user_role: Optional[str] = Header(None)) -> Role:
    if not x_user_role:
        raise HTTPException(
            status_code=401,
            detail="Authentication required: X-User-Role header missing..."
        )
    
    role_str = x_user_role.lower().strip().replace(" ", "_")
    try:
        return Role(role_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid X-User-Role: '{x_user_role}'. Must be one of: {[r.value for r in Role]}"
        )
```

---

### Frontend Changes

#### 1. `mf-context-engine/src/services/api.js`

**Added `normalizeRole()` function:**
```javascript
/**
 * Normalize user role string to valid Role enum value
 * Converts display names like "Compliance & Regulatory Officer" to "compliance_officer"
 */
function normalizeRole(role) {
  if (!role) return null;
  const normalized = role.toLowerCase().trim().replace(/[&/\s]+/g, "_");
  
  const roleMap = {
    "compliance_officer": "compliance_officer",
    "compliance_regulatory_officer": "compliance_officer",
    "compliance_and_regulatory_officer": "compliance_officer",
    "reviewer": "reviewer",
    "resolver": "resolver",
    "viewer": "viewer",
    "admin": "admin",
    // Additional roles from users.json - mapped to appropriate base roles
    "fund_manager_portfolio_manager": "reviewer",
    "esg_sustainability_analyst": "reviewer",
    "sales_distribution_manager": "reviewer",
    "retail_investor_public_client": "viewer",
  };
  
  return roleMap[normalized] || null;
}
```

**Updated `getAuthHeaders()` function:**
```javascript
export function getAuthHeaders() {
  const headers = {};
  if (typeof window !== "undefined") {
    try {
      const stored = sessionStorage.getItem("ns_cg_auth_session_v1") || localStorage.getItem("ns_cg_auth_session_v1");
      if (stored) {
        const session = JSON.parse(stored);
        if (session?.token) {
          headers["Authorization"] = `Bearer ${session.token}`;
        }
        if (session?.authedUsername) {
          headers["X-User-ID"] = session.authedUsername;
        }
        // Include role from session (always set after login)
        if (session?.userRole) {
          headers["X-User-Role"] = normalizeRole(session.userRole);
        }
      }
    } catch {}

    // Fallback: try to get role from active user storage (for backward compatibility)
    if (!headers["X-User-ID"] || !headers["X-User-Role"]) {
      try {
        const activeUser = sessionStorage.getItem("ns_cg_active_user_v1") || localStorage.getItem("ns_cg_active_user_v1");
        if (activeUser) {
          const parsedUser = JSON.parse(activeUser);
          if (typeof parsedUser === "string") {
            // Old format: just a string username
            if (!headers["X-User-ID"]) {
              headers["X-User-ID"] = parsedUser;
            }
          } else if (parsedUser?.username) {
            // New format: object with username and role
            if (!headers["X-User-ID"]) {
              headers["X-User-ID"] = parsedUser.username;
            }
            if (!headers["X-User-Role"] && parsedUser.role) {
              headers["X-User-Role"] = normalizeRole(parsedUser.role);
            }
          }
        }
      } catch {}
    }
  }
  return headers;
}
```

**How it works:**
- All API requests via `request()` now include `X-User-Role` header
- Role values are normalized from display names to enum values
- Both sessionStorage and localStorage are checked for compatibility

#### 2. `mf-context-engine/src/state/AppState.jsx`

**Added `userRole` to session storage on login:**
```javascript
const commit = () => {
  const sessionData = {
    isAuthenticated: true,
    authedUsername: backendUser.username,
    token: response.token,
    expiresAt: response.expires_at,
    rememberMe: Boolean(rememberMe),
    userRole: backendUser.role,  // NEW: Store raw role from backend
  };
  setAuthSessionState(sessionData);
  
  // Always store in sessionStorage for current tab/window lifecycle
  try {
    sessionStorage.setItem(STORAGE_KEYS.AUTH_SESSION, JSON.stringify(sessionData));
  } catch {}

  // If rememberMe is checked, also persist in localStorage
  try {
    if (rememberMe) {
      localStorage.setItem(STORAGE_KEYS.AUTH_SESSION, JSON.stringify(sessionData));
    } else {
      localStorage.removeItem(STORAGE_KEYS.AUTH_SESSION);
    }
  } catch {}

  // Store username and role in active user storage
  setActiveUserWithRole(backendUser.username, backendUser.role);
  
  // ... rest of login flow
};
```

**Added `setActiveUserWithRole()` function:**
```javascript
const setActiveUserWithRole = useCallback((username, role) => {
  setActiveUsernameState(username);
  safeStorageSet(STORAGE_KEYS.ACTIVE_USER, { username, role });
}, []);
```

**Updated `clearAuthSession()` to clear active user:**
```javascript
const clearAuthSession = useCallback(() => {
  const sessionData = { 
    isAuthenticated: false, 
    authedUsername: null, 
    token: null, 
    expiresAt: null, 
    rememberMe: false, 
    userRole: null 
  };
  setAuthSessionState(sessionData);
  setChatSessionsState({});
  
  try {
    sessionStorage.removeItem(STORAGE_KEYS.AUTH_SESSION);
    localStorage.removeItem(STORAGE_KEYS.AUTH_SESSION);
    sessionStorage.removeItem(STORAGE_KEYS.ACTIVE_USER);
    localStorage.removeItem(STORAGE_KEYS.ACTIVE_USER);
    // ...
  } catch {}
}, []);
```

---

## Role Mapping Reference

| Display Name (from DB) | Normalized Key | Mapped Role (Enum) | Notes |
|------------------------|----------------|-------------------|-------|
| `"Compliance & Regulatory Officer"` | `compliance_regulatory_officer` | `compliance_officer` | Admin-tier access |
| `"Fund Manager / Portfolio Manager"` | `fund_manager_portfolio_manager` | `reviewer` | Portfolio managers |
| `"ESG & Sustainability Analyst"` | `esg_sustainability_analyst` | `reviewer` | Sustainability team |
| `"Sales & Distribution Manager"` | `sales_distribution_manager` | `reviewer` | Distribution team |
| `"Retail Investor / Public Client"` | `retail_investor_public_client` | `viewer` | Public client portal |
| `"compliance_officer"` | `compliance_officer` | `compliance_officer` | Direct enum match |
| `"admin"` | `admin` | `admin` | Direct enum match |

---

## Testing Instructions

### To Verify the Fix:

1. **Clear Browser Storage**
   - Open DevTools → Application → Storage
   - Click "Clear site data" OR manually clear:
     - `localStorage`
     - `sessionStorage`

2. **Login with Any User**
   - Use any account from `mf-context-engine/src/data/users.json`:
     - `sarah.compliance` / `Compliance@2026`
     - `vikram.pm` / `Portfolio@2026`
     - `ananya.esg` / `Sustainability@2026`
     - etc.

3. **Verify Session Storage**
   - Open DevTools → Application → Storage → Session Storage
   - Check `ns_cg_auth_session_v1`
   - Verify it contains `userRole: "Compliance & Regulatory Officer"` (or other role)

4. **Check API Headers**
   - Open DevTools → Network tab
   - Make a query to trigger `/api/feedback/status`
   - Click the request → Headers
   - Verify these headers are present:
     ```
     Authorization: Bearer <token>
     X-User-ID: sarah.compliance
     X-User-Role: compliance_officer  (normalized!)
     ```

5. **Expected Result**
   - Status: `200 OK`
   - Response: `{"has_existing_issue": false}` or issue data

---

## Technical Notes

### Why Header-Based Auth?
The backend currently uses header-based authentication as a Wave 0 containment fix:
> "Wave 0 containment: header-based auth is temporary; JWT required in production."

This is a temporary measure until full JWT-based authentication is implemented in Wave 1.

### Role Normalization Logic
The `normalizeRole()` function:
1. Converts to lowercase
2. Trims whitespace
3. Replaces spaces, `&`, and `/` with underscores
4. Maps normalized key to valid Role enum value

Example transformations:
```
"Compliance & Regulatory Officer"
  → "compliance_regulatory_officer"
  → "compliance_officer" ✅

"Fund Manager / Portfolio Manager"
  → "fund_manager_portfolio_manager"
  → "reviewer" ✅
```

### Backward Compatibility
- Old storage format (string username) is still supported
- New format (object with username and role) is preferred
- Both sessionStorage and localStorage are checked
- Graceful degradation if role mapping fails (returns null)

---

## Files Changed

| File | Lines Changed | Description |
|------|---------------|-------------|
| `mf-context-engine/src/services/api.js` | +38 | Added `normalizeRole()` + updated `getAuthHeaders()` |
| `mf-context-engine/src/state/AppState.jsx` | +7 | Added `userRole` storage + `setActiveUserWithRole()` |
| **Total** | **+45** | **2 files modified** |

---

## Rollback Plan

If needed, revert these changes:

```bash
# Restore api.js
git checkout HEAD -- mf-context-engine/src/services/api.js

# Restore AppState.jsx
git checkout HEAD -- mf-context-engine/src/state/AppState.jsx
```

Clear browser storage and login again.

---

## Related Documentation

- [Wave 0 Security Audit](remediation/wave0_batch_a_b/security_audit.py) - Contains role-based access control findings
- [Backend Security Hardening](backend/app/compliance/security.py) - Role validation implementation
- [RBAC Configuration](mf-context-engine/src/data/rbac.js) - Frontend role definitions and permissions
