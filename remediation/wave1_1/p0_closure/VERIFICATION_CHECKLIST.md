# Wave 1.1 P0 Closure Verification Checklist

**Purpose:** Step-by-step verification procedure for P0 security fixes  
**Date:** 2026-11-04  
**Status:** READY FOR TESTING

## Pre-Deployment Verification

### 1. Code Quality Checks ✅

- [x] All Python files pass syntax validation
- [x] No import errors in route files
- [x] Comprehensive docstrings added
- [x] Type hints maintained
- [x] Consistent error handling
- [x] Security logging added

**Verification Command:**
```bash
cd backend
python -m py_compile app/api/routes/admin.py
python -m py_compile app/api/routes/auth.py
python -m py_compile app/api/routes/governance.py
python -m py_compile app/schemas/invitation_token.py
```

**Result:** ✅ All files compile successfully

### 2. Database Schema Updates ⚠️

- [ ] Server starts successfully
- [ ] `invitation_tokens` table created
- [ ] `auth_users` table exists
- [ ] No migration errors in logs

**Verification Steps:**
```bash
cd backend
uvicorn app.main:app --reload

# In another terminal:
sqlite3 data.db
.schema invitation_tokens
.schema auth_users
.quit
```

**Expected:**
- invitation_tokens table with fields: token, username, expires_at, created_by, used, etc.
- auth_users table with fields: username, password_hash, role, tenant_id, etc.

### 3. Server Startup ⚠️

- [ ] Application imports successfully
- [ ] No circular dependency errors
- [ ] All routes registered
- [ ] Admin router mounted
- [ ] FastAPI /docs accessible

**Verification:**
```bash
cd backend
uvicorn app.main:app --reload
# Check logs for errors
# Visit http://localhost:8000/docs
```

**Expected Output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Functional Testing

### 4. Authentication Flow ⚠️

#### 4.1 Login with Existing User

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your_password"}'
```

**Expected:** 200 OK with JWT token
**Store token for next tests:**
```bash
export TOKEN="<token_from_response>"
```

#### 4.2 Access /me Endpoint

```bash
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

**Expected:** 200 OK with user details

#### 4.3 Access Without Token (Should Fail)

```bash
curl http://localhost:8000/api/admin/users
```

**Expected:** 401 Unauthorized with message about missing authentication

### 5. Admin Endpoints - User Management ⚠️

#### 5.1 List Users (Admin Only)

```bash
curl http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $TOKEN"
```

**Expected:** 
- 200 OK if token is admin role
- 403 Forbidden if token is analyst/viewer

#### 5.2 Create User with Invitation

```bash
curl -X POST http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "display_name": "Test User",
    "email": "test@example.com",
    "role": "analyst",
    "department": "Engineering"
  }'
```

**Expected:**
- 201 Created
- Response includes invitation_token
- Response does NOT include password
- User account in "Pending" status

**Verify in Database:**
```sql
SELECT username, status FROM auth_users WHERE username = 'testuser';
-- Should show: testuser | Pending

SELECT token, username, expires_at FROM invitation_tokens WHERE username = 'testuser';
-- Should show token record
```

#### 5.3 Accept Invitation

```bash
curl -X POST http://localhost:8000/api/auth/accept-invitation \
  -H "Content-Type: application/json" \
  -d '{
    "invitation_token": "<token_from_step_5.2>",
    "password": "SecurePassword123!"
  }'
```

**Expected:**
- 200 OK
- Message: "Account activated successfully"
- User status changed to "Active"

**Verify:**
```sql
SELECT username, status FROM auth_users WHERE username = 'testuser';
-- Should show: testuser | Active
```

#### 5.4 Login as New User

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "SecurePassword123!"}'
```

**Expected:** 200 OK with valid JWT token

### 6. Authorization Enforcement ⚠️

#### 6.1 Analyst Cannot Access Admin Endpoints

```bash
# Login as analyst
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "SecurePassword123!"}'

export ANALYST_TOKEN="<token_from_response>"

# Try to list users (should fail)
curl http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $ANALYST_TOKEN"
```

**Expected:** 403 Forbidden with message about insufficient privileges

#### 6.2 X-User-Role Header Rejected

```bash
curl http://localhost:8000/api/governance/pending-corrections \
  -H "X-User-Role: admin"
```

**Expected:** 401 Unauthorized (X-User-Role header ignored, JWT required)

### 7. Governance Endpoints ⚠️

#### 7.1 No Confidence-Based Auto-Approval

```bash
curl -X POST http://localhost:8000/api/governance/run-batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "auto_approve_threshold": 0.95,
    "max_risk_level": "LOW",
    "dry_run": false
  }'
```

**Expected:**
- 200 OK (if admin/compliance_officer)
- Response status: "review_categorization_completed"
- Message contains "REP-01 COMPLIANCE"
- No patches automatically approved
- Lists: recommended_for_approval, recommended_for_rejection, requires_detailed_review

**Critical:** Verify that even high-confidence patches are NOT automatically promoted

### 8. Tenant Isolation ⚠️

#### 8.1 Create Users in Different Tenants

```bash
# Create user in tenant A
curl -X POST http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "user_tenant_a",
    "display_name": "User Tenant A",
    "email": "usera@example.com",
    "role": "analyst",
    "tenant_id": "tenant_a"
  }'

# Create user in tenant B
curl -X POST http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "user_tenant_b",
    "display_name": "User Tenant B",
    "email": "userb@example.com",
    "role": "analyst",
    "tenant_id": "tenant_b"
  }'
```

#### 8.2 Verify Cross-Tenant Access Blocked

```bash
# Login as user from tenant A
# (Need to accept invitation first - see step 5.3)

# Try to access user from tenant B
curl http://localhost:8000/api/admin/users/user_tenant_b \
  -H "Authorization: Bearer $TENANT_A_TOKEN"
```

**Expected:** 404 Not Found (cross-tenant users hidden)

**Admin Should See Both:**
```bash
curl http://localhost:8000/api/admin/users/user_tenant_b \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Expected:** 200 OK (admin sees all tenants)

## Security Test Suite

### 9. Run Automated Security Tests ⚠️

```bash
cd backend
pytest tests/test_sec01_universal_auth.py -v
```

**Expected:**
- All `_no_auth_401` tests PASS
- All `_analyst_403` tests PASS (when unskipped)
- HeaderAuthRejection tests PASS
- Some tests may be skipped (require full JWT setup)

**Minimum Required:**
- At least 80% of tests passing
- Zero unexpected failures
- All 401 tests passing (auth enforcement)

### 10. Manual Adversarial Testing ⚠️

#### 10.1 Attempt SQL Injection in Username

```bash
curl -X GET http://localhost:8000/api/admin/users/admin'--
```

**Expected:** 401 or 404, not 500 (no SQL error exposed)

#### 10.2 Attempt JWT Forgery

```bash
curl http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer fake_token_12345"
```

**Expected:** 401 Unauthorized (invalid token rejected)

#### 10.3 Attempt Role Escalation

```bash
# With analyst token, try to create admin user
curl -X POST http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $ANALYST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "backdoor",
    "display_name": "Backdoor Admin",
    "email": "backdoor@example.com",
    "role": "admin"
  }'
```

**Expected:** 403 Forbidden (only admin can create users)

## Audit & Logging Verification

### 11. Check Security Audit Logs ⚠️

```bash
# Check governance audit log
cat logs/governance_audit.jsonl | tail -20

# Check application logs for security events
grep -i "authentication\|authorization\|invitation\|admin" logs/*.log
```

**Expected:**
- All governance actions logged with username (not client-supplied role)
- User creation logged
- Invitation acceptance logged with IP
- Failed auth attempts logged

## Rollback Preparedness

### 12. Document Current State ⚠️

```bash
# Backup database
cp data.db data.db.backup_$(date +%Y%m%d_%H%M%S)

# Document Git commit
git log -1 --oneline

# List modified files
git status
git diff --name-only
```

**Rollback Procedure:**
1. Stop server
2. `git checkout <previous_commit>`
3. Restore database backup: `cp data.db.backup_YYYYMMDD_HHMMSS data.db`
4. Restart server

## Final Checklist

### Critical Gates (Must Pass Before Deploy)

- [ ] Server starts without errors
- [ ] Database migrations complete
- [ ] Login works for existing users
- [ ] JWT tokens are generated and validated
- [ ] Admin endpoints reject unauthenticated requests (401)
- [ ] Admin endpoints reject non-admin users (403)
- [ ] New user creation generates invitation token (not password)
- [ ] Invitation acceptance works
- [ ] X-User-Role header is ignored (not accepted for auth)
- [ ] /run-batch does NOT auto-approve patches
- [ ] Security audit logs are being written
- [ ] At least basic security tests pass

### Medium Priority (Should Pass)

- [ ] Cross-tenant access is blocked
- [ ] Analyst cannot access admin functions
- [ ] Self-service user actions work (view own profile)
- [ ] Cannot delete own account
- [ ] Invitation tokens expire correctly
- [ ] One-time invitation token use enforced

### Low Priority (Nice to Have)

- [ ] All route handlers have proper error handling
- [ ] All endpoints return consistent JSON structure
- [ ] OpenAPI/Swagger docs reflect new endpoints
- [ ] Response times acceptable (< 200ms for simple requests)

## Status Summary

**Overall Status:** ⚠️ PENDING VERIFICATION

**Blockers:**
1. Server startup not verified
2. JWT authentication flow not tested
3. Database migrations not confirmed
4. No automated test runs yet

**Ready for:**
- Manual testing by developer
- Integration with test environment
- Security review by compliance team

**NOT ready for:**
- Production deployment
- User acceptance testing
- Load testing

## Sign-Off

### Developer Verification

- [ ] All code changes reviewed
- [ ] Syntax checks passed
- [ ] Manual smoke testing completed
- [ ] Security tests written
- [ ] Documentation updated

**Developer:** _________________  
**Date:** _________________

### Security Review

- [ ] Authentication mechanisms verified
- [ ] Authorization checks confirmed
- [ ] No default passwords in use
- [ ] Audit logging functional
- [ ] Vulnerability scan passed

**Security Reviewer:** _________________  
**Date:** _________________

### Deployment Approval

- [ ] All critical gates passed
- [ ] Rollback procedure documented
- [ ] Monitoring alerts configured
- [ ] Incident response plan ready

**Approver:** _________________  
**Date:** _________________
