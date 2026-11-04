# SEC-01 Universal Authentication Enforcement: Route Audit

**Date**: 2026-11-04  
**Purpose**: Complete audit of all API routes for authentication enforcement

---

## Route Classification

### PUBLIC (No authentication required)
- `/health` - System health check
- `/api/health` - API health check
- `/api/auth/login` - User authentication endpoint
- `/docs`, `/redoc`, `/openapi.json` - API documentation

### SENSITIVE (MUST require CurrentUser)

#### Admin Routes (`/api/admin/*`)
- ✅ `/admin/users` [GET, POST, DELETE] - User management
- ✅ `/admin/rbac` [GET] - Role matrix
- ✅ `/admin/audit` [GET] - Audit logs
- ✅ `/admin/ingestion/*` [POST, GET] - Data ingestion
- ✅ `/admin/intent-cache/*` [GET, POST] - Cache management
- ✅ `/admin/feedback/issues` [GET] - Admin feedback view

#### Governance Routes (`/api/governance/*`)
- ✅ `/governance/issues` [GET, POST] - Issue management
- ✅ `/governance/issues/{id}/*` [PUT, POST] - Issue actions
- ✅ `/governance/proposals` [GET, POST] - Repair proposals
- ✅ `/governance/proposals/{id}/*` [PUT, POST] - Proposal actions

#### Ingest Routes (`/api/ingest/*`)
- ✅ `/ingest/documents` [POST] - Document upload
- ✅ `/ingest/csv` [POST] - CSV upload

#### Audit Routes (`/api/audit/*`)
- ⚠️ `/audit/audit-metadata` [GET, POST] - Needs auth
- ⚠️ `/audit/violations` [GET, POST] - Needs auth
- ⚠️ `/audit/response-feedback` [GET, POST] - Needs auth
- ✅ `/audit/query-evidence` [GET] - Has CurrentUser
- ⚠️ `/audit/compliance-rules` [GET, POST] - Needs auth
- ⚠️ `/audit/fund-schemes` [GET, POST] - Needs auth
- ⚠️ `/audit/chat-sessions` [GET, POST] - Needs auth

### AUTHENTICATED-OPTIONAL (Tenant isolation when authenticated)
- `/api/chat` [POST] - Chat queries
- `/api/query` [POST] - Query endpoint
- `/api/chat/stream` [POST] - Streaming chat
- `/api/compare` [POST] - Document comparison
- `/api/feedback` [POST] - User feedback submission

---

## Implementation Strategy

### Phase 1: Critical Admin/Governance Routes (DONE in Wave 0+1)
- Admin user management
- Governance approval routes

### Phase 2: Audit & Compliance Routes (THIS BATCH)
- All `/api/audit/*` routes except those with existing CurrentUser
- Compliance rule management
- Fund scheme management
- Session management

### Phase 3: Optional Auth with Tenant Isolation (FUTURE)
- Chat/query routes support optional auth
- When authenticated, enforce tenant isolation
- When anonymous, limit to public data only

---

## Security Requirements

### For ALL Sensitive Routes:
```python
async def protected_route(
    current_user: CurrentUser,  # ← REQUIRED
    # ... other params
) -> ResponseType:
    # Verified user with JWT token
    # current_user.username, current_user.role, current_user.department
    pass
```

### For Tenant-Scoped Routes:
```python
async def tenant_scoped_route(
    current_user: CurrentUser,
    # ... other params
) -> ResponseType:
    # Filter by tenant_id derived from current_user
    tenant_id = current_user.department or "default"
    # Apply tenant filter to all queries
    pass
```

### For Admin-Only Routes:
```python
from app.auth.service import require_admin

async def admin_only_route(
    current_user: CurrentUser,
    # ... other params
) -> ResponseType:
    require_admin(current_user)  # Raises 403 if not admin
    # Admin operations
    pass
```

