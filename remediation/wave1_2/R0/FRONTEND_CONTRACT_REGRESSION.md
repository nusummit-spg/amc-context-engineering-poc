# Frontend Contract Regression Analysis

**Date:** 2026-11-04  
**Scope:** Admin Dashboard and Management UI  
**Severity:** P0 - CRITICAL BREAKING CHANGES  
**Impact:** Multiple admin features non-functional

## Executive Summary

The Wave 1.1 security fixes removed **18 admin endpoints** to implement proper authentication. While this improved security, it broke multiple frontend features that depend on these endpoints. This document analyzes the impact and provides restoration guidance.

## Breaking Changes by Feature Area

### 1. User Management (PARTIALLY WORKING)

**Status:** 5/6 endpoints working

**Working:**
- ✅ List users: `GET /api/admin/users`
- ✅ Create user: `POST /api/admin/users`  
- ✅ Get user: `GET /api/admin/users/{username}`
- ✅ Update user: `PATCH /api/admin/users/{username}`
- ✅ Delete user: `DELETE /api/admin/users/{username}`

**Missing:**
- ❌ Sync users: `POST /api/admin/users/sync`

**Frontend Impact:**
- Basic CRUD operations work
- User sync button non-functional
- May affect bulk user operations

**Restoration Priority:** P0

### 2. Audit & RBAC (COMPLETELY BROKEN)

**Status:** 0/2 endpoints working

**Missing:**
- ❌ Fetch audit logs: `GET /api/admin/audit`
- ❌ Fetch RBAC matrix: `GET /api/admin/rbac`

**Frontend Impact:**
- Audit log viewer completely broken
- Cannot view system activity
- Cannot review role permissions
- Security monitoring disabled

**Restoration Priority:** P0 (Security monitoring critical)

### 3. Ingestion Management (SEVERELY BROKEN)

**Status:** 2/10 endpoints working

**Working:**
- ✅ Trigger ingestion: `POST /api/admin/ingestion/run`
- ✅ Upload file: `POST /api/admin/ingestion/upload`

**Missing:**
- ❌ Check staleness: `POST /api/admin/ingestion/staleness`
- ❌ List tasks: `GET /api/admin/ingestion/tasks`
- ❌ Get active tasks: `GET /api/admin/ingestion/tasks/active`
- ❌ Get proposed edges: `GET /api/admin/ingestion/proposed-edges`
- ❌ Confirm edge: `POST /api/admin/ingestion/edges/{id}/confirm`
- ❌ Reject edge: `POST /api/admin/ingestion/edges/{id}/reject`
- ❌ Compliance report: `GET /api/admin/ingestion/compliance-report`
- ❌ Notifications (3 endpoints)

**Frontend Impact:**
- Cannot monitor ingestion progress
- Cannot review proposed graph edges
- Cannot approve/reject regulatory relationships
- Compliance reporting unavailable
- Task notifications broken

**Restoration Priority:** P0 (Core admin workflow)

### 4. Cache Management (PARTIALLY BROKEN)

**Status:** 1/5 endpoints working

**Working:**
- ✅ Clear general cache: `POST /api/admin/cache/clear`

**Missing:**
- ❌ Intent cache stats: `GET /api/admin/intent-cache/stats`
- ❌ General cache stats: `GET /api/admin/cache/stats`
- ❌ Invalidate domain: `POST /api/admin/intent-cache/invalidate-domain`
- ❌ Clear intent cache: `POST /api/admin/intent-cache/clear`

**Frontend Impact:**
- Basic cache clearing works
- Cannot view cache statistics
- Cannot do targeted cache invalidation
- Performance monitoring limited

**Restoration Priority:** P1 (Operations impact)

### 5. Feedback Issues Admin View (UNCLEAR)

**Status:** May be duplicate of existing endpoint

**Missing:**
- ❌ Admin feedback view: `GET /api/admin/feedback/issues`

**Analysis:**
- May duplicate `/api/feedback/issues` endpoint
- Need to check if admin view has different permissions/scope
- May need tenant-wide view vs user-specific view

**Restoration Priority:** P1 (After confirming need)

## API Contract Analysis

### Frontend Service Methods Affected

From `mf-context-engine/src/services/api.js`:

```javascript
// BROKEN - No backend handler
export async function syncUsersWithDb(options = {})
export async function fetchRbacMatrix()
export async function fetchAuditLogs(limit = 30)
export async function checkStaleness()
export async function fetchIndexingTasks(limit = 10)
export async function fetchProposedEdges()
export async function confirmProposedEdge(edgeId, authorizedBy)
export async function rejectProposedEdge(edgeId)
export async function fetchComplianceReport()
export async function fetchIntentCacheStats()
export async function invalidateIntentCacheDomain(domain)
export async function clearIntentCache()

// WORKING - Backend handlers exist
export async function fetchUsers(options = {})
export async function saveUser(user)
export async function deleteUser(username)
export async function runIngestPipeline()
export async function uploadDocument(formData)
// Note: General cache clear exists as /admin/cache/clear
```

### Error Behavior

When frontend calls missing endpoints:
```
API Error (404): Not Found
// Or
API Error (405): Method Not Allowed  
```

User sees:
- Broken UI components
- Error toasts/messages
- Failed actions
- Incomplete dashboards

## Frontend Components Likely Affected

### Admin Dashboard (`/admin` routes)

**User Management Page:**
- ✅ User list/CRUD works
- ❌ Sync button broken
- Impact: Moderate

**Audit Log Page:**
- ❌ Completely non-functional
- ❌ Cannot view any logs
- Impact: Critical

**System Health Page:**
- ❌ Cannot view cache statistics
- ❌ Limited performance monitoring
- Impact: High

### Ingestion Management (`/admin/ingestion` routes)

**Task Monitor:**
- ❌ Cannot see running tasks
- ❌ Cannot see task history
- ❌ Cannot monitor progress
- Impact: Critical

**Edge Review Queue:**
- ❌ Cannot see proposed relationships
- ❌ Cannot approve/reject edges
- ❌ Regulatory review workflow blocked
- Impact: Critical (Compliance)

**Compliance Dashboard:**
- ❌ No compliance reports
- ❌ Cannot verify regulatory adherence
- Impact: Critical (Regulatory)

### Cache Management

**Cache Statistics:**
- ❌ No cache hit/miss metrics
- ❌ Cannot see cache size
- Impact: High

**Cache Operations:**
- ✅ Basic clear works
- ❌ Targeted invalidation broken
- Impact: Moderate

## Restoration Strategy

### Phase 1: Critical P0 Routes (R1-09a)

**Must restore immediately for basic admin functionality:**

1. **Audit & Monitoring:**
   ```python
   @router.get("/audit")
   async def get_audit_logs(
       limit: int = 50,
       offset: int = 0,
       current_user: CurrentUser = Depends()
   ):
       require_role(current_user, ["admin", "compliance_officer"])
       # Return audit events with tenant filtering
   ```

2. **Ingestion Task Management:**
   ```python
   @router.get("/ingestion/tasks")
   async def list_ingestion_tasks(
       limit: int = 10,
       current_user: CurrentUser = Depends()
   ):
       require_role(current_user, ["admin", "compliance_officer"])
       # Return task status with auth
   ```

3. **Edge Review Workflow:**
   ```python
   @router.get("/ingestion/proposed-edges")
   async def list_proposed_edges(current_user: CurrentUser):
       require_role(current_user, ["admin", "compliance_officer", "reviewer"])
       # Return pending edges

   @router.post("/ingestion/edges/{edge_id}/confirm")
   async def confirm_edge(
       edge_id: str,
       current_user: CurrentUser
   ):
       require_role(current_user, ["admin", "compliance_officer"])
       # Four-eyes check: approver != proposer
       # Record approval with user identity
   
   @router.post("/ingestion/edges/{edge_id}/reject")  
   async def reject_edge(
       edge_id: str,
       current_user: CurrentUser
   ):
       require_role(current_user, ["admin", "compliance_officer"])
       # Record rejection with reason
   ```

4. **Compliance Reporting:**
   ```python
   @router.get("/ingestion/compliance-report")
   async def get_compliance_report(current_user: CurrentUser):
       require_role(current_user, ["admin", "compliance_officer", "reviewer"])
       # Return regulatory compliance metrics
   ```

5. **User Sync:**
   ```python
   @router.post("/users/sync")
   async def sync_users(current_user: CurrentUser):
       require_role(current_user, ["admin"])
       # Sync from external source if applicable
   ```

### Phase 2: High Priority P1 Routes (R1-09b)

6. **RBAC Matrix:**
   ```python
   @router.get("/rbac")
   async def get_rbac_matrix(current_user: CurrentUser):
       require_role(current_user, ["admin", "compliance_officer"])
       # Return role-permission matrix
   ```

7. **Cache Statistics:**
   ```python
   @router.get("/intent-cache/stats")
   async def get_intent_cache_stats(current_user: CurrentUser):
       require_role(current_user, ["admin"])
       # Return cache metrics

   @router.get("/cache/stats")
   async def get_cache_stats(current_user: CurrentUser):
       require_role(current_user, ["admin"])
       # Return all cache statistics
   ```

8. **Cache Operations:**
   ```python
   @router.post("/intent-cache/clear")
   async def clear_intent_cache(current_user: CurrentUser):
       require_role(current_user, ["admin"])
       # Clear intent cache
   
   @router.post("/intent-cache/invalidate-domain")
   async def invalidate_cache_domain(
       domain: str,
       current_user: CurrentUser
   ):
       require_role(current_user, ["admin"])
       # Targeted cache invalidation
   ```

9. **Ingestion Staleness:**
   ```python
   @router.post("/ingestion/staleness")
   async def check_staleness(current_user: CurrentUser):
       require_role(current_user, ["admin", "compliance_officer"])
       # Check data freshness
   ```

### Phase 3: Optional P2 Routes (R1-09c)

10. **Task Notifications** (if still needed):
    ```python
    @router.get("/ingestion/notifications")
    @router.post("/ingestion/notifications/{task_id}/read")
    @router.post("/ingestion/notifications/read-all")
    ```
    
    **Decision needed:** Are these still required, or has notification system changed?

### Phase 4: Evaluation & Deprecation (R1-09d)

11. **Feedback Issues Admin:**
    - Check if `/api/feedback/issues` already provides admin view
    - If duplicate, update frontend to use existing endpoint
    - If different scope needed, restore with proper auth

## Security Requirements for All Restored Routes

### Mandatory for Every Endpoint

1. **Authentication:**
   ```python
   current_user: CurrentUser = Depends()
   ```
   - JWT bearer token required
   - No X-User-Role header acceptance
   - No anonymous access

2. **Authorization:**
   ```python
   def require_role(user: CurrentUser, allowed_roles: List[str]):
       if user.role not in allowed_roles:
           raise HTTPException(403, "Insufficient privileges")
   ```
   - Server-authoritative role checking
   - No client-supplied role claims

3. **Tenant Isolation:**
   ```python
   if user.role != "admin":
       # Filter by user.tenant_id
       results = filter_by_tenant(results, user.tenant_id)
   ```
   - Non-admin users see only their tenant
   - Admin sees all (with explicit audit)

4. **Audit Logging:**
   ```python
   logger.info(
       "Admin action: %s by user=%s role=%s tenant=%s",
       action, user.username, user.role, user.tenant_id
   )
   ```
   - All admin actions logged
   - Include user identity, timestamp, action

5. **Four-Eyes for Critical Operations:**
   ```python
   # For edge approval/rejection
   if edge.proposed_by == current_user.username:
       raise HTTPException(403, "Cannot approve own proposal")
   ```
   - Proposer != approver
   - Separate review required

## Testing Requirements

### Contract Tests

For each restored endpoint:

```python
def test_endpoint_requires_auth():
    """Endpoint rejects unauthenticated requests."""
    response = client.get("/api/admin/endpoint")
    assert response.status_code == 401

def test_endpoint_requires_role():
    """Endpoint rejects unauthorized roles."""
    response = client.get(
        "/api/admin/endpoint",
        headers={"Authorization": f"Bearer {analyst_token}"}
    )
    assert response.status_code == 403

def test_endpoint_works_with_auth():
    """Endpoint works for authorized users."""
    response = client.get(
        "/api/admin/endpoint",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    # Verify response structure matches frontend contract
```

### Frontend Integration Tests

```javascript
describe('Admin Dashboard', () => {
  it('shows audit logs with authentication', async () => {
    const logs = await api.fetchAuditLogs();
    expect(logs).toHaveLength(greaterThan(0));
  });

  it('shows ingestion tasks', async () => {
    const tasks = await api.fetchIndexingTasks();
    expect(tasks).toBeInstanceOf(Array);
  });

  it('allows edge approval workflow', async () => {
    const edges = await api.fetchProposedEdges();
    if (edges.length > 0) {
      await api.confirmProposedEdge(edges[0].id);
    }
  });
});
```

## Migration Path

### Option A: Full Compatibility (Recommended)

1. Restore all P0/P1 endpoints with proper auth
2. Keep existing request/response contracts
3. Frontend works without changes
4. Deploy backend, verify, deploy frontend updates separately

**Pros:** Minimal frontend changes, faster deployment  
**Cons:** More backend work

### Option B: Partial Migration

1. Restore only critical P0 endpoints
2. Deprecate less-used P1/P2 endpoints
3. Update frontend to remove/replace deprecated features
4. Coordinate backend + frontend deployment

**Pros:** Cleaner codebase, remove unused features  
**Cons:** Requires frontend changes, coordinated deployment

### Option C: Hybrid Approach (Current Plan)

1. Restore P0 immediately for critical functions
2. Restore P1 for full admin capabilities
3. Evaluate P2 - restore only if actively used
4. Document intentional deprecations

**Pros:** Balanced approach, prioritizes critical paths  
**Cons:** Requires frontend audit to confirm usage

## Rollout Plan

### Week 1: Assessment & Planning
- [x] Document all missing endpoints
- [x] Analyze frontend dependencies
- [x] Prioritize restoration order
- [ ] Create detailed implementation tickets

### Week 2: P0 Implementation (R1-09a)
- [ ] Restore audit logs endpoint
- [ ] Restore ingestion tasks endpoint
- [ ] Restore edge review endpoints (3)
- [ ] Restore compliance report endpoint
- [ ] Restore user sync endpoint
- [ ] Write security tests for each
- [ ] Deploy to staging

### Week 3: P1 Implementation & Testing (R1-09b)
- [ ] Restore RBAC matrix
- [ ] Restore cache statistics (2 endpoints)
- [ ] Restore cache operations (2 endpoints)
- [ ] Restore staleness check
- [ ] Frontend integration tests
- [ ] Full admin dashboard smoke test

### Week 4: P2 Evaluation & Deployment (R1-09c/d)
- [ ] Evaluate notification endpoints
- [ ] Evaluate feedback admin endpoint
- [ ] Document deprecations
- [ ] Production deployment
- [ ] Monitor for errors

## Success Criteria

### Restored Functionality
- ✅ Admin can view audit logs
- ✅ Admin can monitor ingestion tasks
- ✅ Admin can review and approve proposed edges
- ✅ Admin can generate compliance reports
- ✅ Admin can view cache statistics
- ✅ Admin can perform targeted cache operations
- ✅ All user management functions work

### Security Maintained
- ✅ All endpoints require authentication
- ✅ All endpoints enforce authorization
- ✅ Tenant isolation works correctly
- ✅ Four-eyes enforced for critical operations
- ✅ All admin actions audited

### Frontend Working
- ✅ No 404 errors on admin pages
- ✅ All dashboard widgets render
- ✅ All admin workflows functional
- ✅ Error handling graceful

## Appendix: Endpoint Comparison

### Before (Insecure but Functional)
```
18 admin endpoints available
No authentication required
Frontend fully functional
Security risk: High
```

### After Wave 1.1 (Secure but Broken)
```
8 admin endpoints available
Authentication required
Frontend partially broken
Security risk: Low
Functionality: Reduced
```

### Target (Secure and Functional)
```
26 admin endpoints available
Authentication required
Authorization enforced
Tenant isolation active
Four-eyes for critical ops
Frontend fully functional
Security risk: Low
Functionality: Full
```

## Sign-Off

**Backend Implementation:** _____________  
**Frontend Verification:** _____________  
**Security Review:** _____________  
**Deployment Approval:** _____________

## References

- Route Matrix: `remediation/wave1_2/R0/ROUTE_COMPATIBILITY_MATRIX.csv`
- Frontend API: `mf-context-engine/src/services/api.js`
- Admin Routes: `backend/app/api/routes/admin.py`
- Auth Specs: `docs/AMC_Tasks_3_11_26/AMC_Specs/05_ASSURANCE_SECURITY_RELEASE_GATES.md`
