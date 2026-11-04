# Source Baseline - Wave 1.1 P0 Closure

**Date:** 2026-11-04
**Repository:** nusummit-spg/amc-context-engineering-poc
**Branch:** feature/wave1-canonical-data-and-typed-queries
**Commit (Audit Reference):** 910bae72030cbf641badbdb6e2c6fe82b78a9479
**Local Implementation Base:** Current working directory

## Component Versions

- Python Backend: FastAPI-based application
- Database: SQLite (data.db) + Neo4j (graph)
- Vector Store: FAISS
- Authentication: JWT-based with SQLAlchemy session tracking
- Repair Engine: Modular package (amc-repair-engine)
- Feedback Loop: Modular package (amc-feedback-loop)

## Route Inventory (From main.py)

### Currently Registered Routes
1. `/api/auth/*` - Authentication (auth.py)
2. `/api/admin/*` - **MISSING** - Imported but file doesn't exist
3. `/api/query/*` - Query operations (query.py)
4. `/api/chat/*` - Chat interface (chat.py)
5. `/api/sessions/*` - Session management (sessions.py)
6. `/api/taxonomy/*` - Taxonomy operations (taxonomy.py)
7. `/api/graph/*` - Graph operations (graph.py)
8. `/api/docs/*` - Documentation (docs.py)
9. `/api/ingest/*` - Ingestion operations (ingest.py)
10. `/api/status/*` - Status/health checks (status.py)
11. `/api/compliance/*` - Compliance operations (compliance.py)
12. `/api/feedback/*` - Feedback operations (feedback.py)
13. `/api/review_queue/*` - Review queue (review_queue.py)
14. `/api/governance/*` - Governance operations (governance.py)
15. `/api/files/*` - File operations (files.py)
16. `/api/metrics/*` - Metrics (metrics.py)
17. `/api/feedback-evaluation/*` - Feedback evaluation (feedback_evaluation.py)
18. `/api/audit/*` - Audit operations (audit.py)

### Standalone Endpoints
- `/health` - Health check
- `/api/health` - Health check
- `/api/health/passive-feedback` - Passive feedback health
- `/metrics` - Prometheus metrics
- `/api/metrics/prometheus` - Prometheus metrics
- `/api/responses/{response_id}/quality-score` - Quality score
- `/metrics/dashboard` - Metrics dashboard
- `/files/*` - File serving (also registered at root)

## Critical Findings from Audit

### SEC-01: Missing Authentication on Admin Routes
- `admin.py` **does not exist** but is imported in main.py
- Governance routes use insecure `get_client_role(x_user_role: Header)` 
- Many ingestion, audit, cache control routes lack auth

### SEC-02: Header-based Role Authorization
- `get_client_role()` in `compliance/security.py` reads `X-User-Role` header
- Now rejects missing headers (improvement) but still accepts client-supplied role
- Should use JWT-verified role from `CurrentUser` dependency

### SEC-03: Predictable Password
- Default password "Welcome@2026" found in user creation

### SEC-04: Missing Service-to-Service Auth
- Repair microservice endpoints need workload identity

## Available Auth Infrastructure

- ✅ JWT-based authentication system exists
- ✅ `CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]` available
- ✅ User model has: username, role, department, tenant_id
- ✅ Token revocation table implemented
- ✅ SQL-backed user repository available

## Implementation Status - Pre-Fix

- [x] JWT authentication system - EXISTS
- [x] User dependencies (CurrentUser) - EXISTS
- [ ] Admin routes - MISSING (file doesn't exist)
- [ ] Server-authoritative role checking - PENDING
- [ ] Endpoint authentication matrix - PENDING
- [ ] Secure enrollment flow - PENDING
- [ ] Tenant filtering - PARTIAL (field exists, enforcement missing)

## Next Steps

1. Create admin.py with proper authentication
2. Replace header-based role with JWT-verified role
3. Audit all routes for authentication requirements
4. Fix predictable passwords
5. Implement tenant isolation
