# Repair Engine Authentication Guide

Quick reference for developers working with the authenticated Repair Engine microservice.

---

## Overview

The Repair Engine requires JWT bearer token authentication for all mutation and sensitive read operations. Both end-user tokens (from the main application) and service-to-service tokens are supported.

---

## Environment Configuration

```bash
# Required environment variable (shared with main app)
REPAIR_SERVICE_SECRET=your-production-secret-change-this

# Optional: Repair service URL
REPAIR_ENGINE_URL=http://localhost:8002
```

---

## Token Formats

### End-User Token (from main app)

```json
{
  "sub": "alice",
  "user_id": "user_123",
  "tenant_id": "tenant_A",
  "roles": ["reviewer"],
  "iat": 1730719200,
  "exp": 1730722800
}
```

### Service Token

```json
{
  "token_type": "service",
  "service_name": "feedback-service",
  "scopes": ["patch_read", "patch_approve"],
  "iat": 1730719200,
  "exp": 1730722800
}
```

---

## Issuing Service Tokens

```python
from amc_repair.auth import issue_service_token

# Issue token with specific scopes
token, expiration = issue_service_token(
    service_name="feedback-service",
    scopes=["patch_read", "patch_create", "patch_approve"],
    secret="your-shared-secret",  # Defaults to REPAIR_SERVICE_SECRET
    ttl_minutes=60  # Token valid for 1 hour
)

print(f"Token: {token}")
print(f"Expires at: {expiration}")
```

---

## Making Authenticated Requests

### Using the Client

```python
from app.clients.repair_client import get_repair_service_client

# Get client instance
client = get_repair_service_client()

# Pass your authentication token
patches = await client.get_pending_patches(auth_token=user_token)

# Approve a patch
success = await client.approve_patch(
    patch_id="patch_123",
    auth_token=user_token
)
```

### Using httpx Directly

```python
import httpx

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

async with httpx.AsyncClient() as client:
    # Get pending patches
    response = await client.get(
        "http://localhost:8002/api/patches/pending",
        headers=headers
    )
    
    # Create a patch
    response = await client.post(
        "http://localhost:8002/api/patches",
        json={
            "entity_id": "AMC_001",
            "attribute": "regulatory_fact",
            "corrected_value": "New value",
            "confidence": 0.95
        },
        headers=headers
    )
```

### Using curl

```bash
# Set your token
TOKEN="your.jwt.token"

# List pending patches
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8002/api/patches/pending

# Approve a patch
curl -X POST \
     -H "Authorization: Bearer $TOKEN" \
     http://localhost:8002/api/patches/patch_123/approve
```

---

## Endpoint Authentication Requirements

| Endpoint | Auth Level | Notes |
|----------|-----------|-------|
| `GET /api/health` | None | Public health check |
| `POST /api/patches` | User | Creates patch, tracks proposer |
| `GET /api/patches/pending` | User | Lists patches, tenant filtered |
| `GET /api/patches/for-entities` | ⚠️ TODO | Currently public |
| `GET /api/patches/{id}` | ⚠️ TODO | Currently public |
| `POST /api/patches/{id}/approve` | Reviewer/Admin | Four-eyes enforced |
| `POST /api/patches/{id}/reject` | Reviewer/Admin | Requires reviewer role |
| `POST /api/patches/batch-approve` | Reviewer/Admin | Four-eyes per patch |
| `POST /api/governance/promote/{id}` | Admin/Promoter | Requires promotion permission |
| `POST /api/governance/run-batch` | Admin/Promoter | Requires admin role |

---

## Role Requirements

### User Roles

| Role | Permissions |
|------|-------------|
| `user` | Can create patches |
| `reviewer` | Can approve/reject patches |
| `admin` | Can approve, promote, run governance |

### Service Scopes

| Scope | Permissions |
|-------|-------------|
| `patch_read` | Can read patches |
| `patch_create` | Can create patches |
| `patch_approve` | Can approve patches |
| `patch_promotion` | Can promote to production |

---

## Four-Eyes Enforcement

The system enforces separation of duties: **proposer ≠ approver**.

### How It Works

1. **Patch Creation:** Proposer identity stored in provenance
   ```json
   {
     "proposer_id": "user_123",
     "proposer_username": "alice",
     "tenant_id": "tenant_A"
   }
   ```

2. **Patch Approval:** System checks proposer ≠ approver
   ```python
   # This will succeed
   alice creates patch → bob approves ✅
   
   # This will fail with 403
   alice creates patch → alice approves ❌
   ```

3. **Batch Approval:** Each patch checked individually
   ```json
   {
     "approved": ["patch_1", "patch_3"],
     "four_eyes_violations": [
       {
         "patch_id": "patch_2",
         "proposer": "alice",
         "reason": "Cannot approve own patch"
       }
     ]
   }
   ```

---

## Tenant Isolation

### End Users

Users can only access patches from their own tenant:

```python
# Alice (tenant_A) can see only tenant_A patches
# Bob (tenant_B) can see only tenant_B patches

# Cross-tenant operations result in 403
```

### Service Tokens

Service tokens can operate across tenants:

```python
# Service with is_service=True bypasses tenant filtering
# Used for admin/operational services
```

---

## Error Responses

### 401 Unauthorized

```json
{
  "detail": "Invalid or expired authentication token"
}
```

**Causes:**
- Missing Authorization header
- Invalid token signature
- Expired token
- Malformed token

### 403 Forbidden

```json
{
  "detail": "User alice does not have approval permissions"
}
```

**Causes:**
- Insufficient role/permissions
- Four-eyes violation (self-approval)
- Cross-tenant operation attempt

### 404 Not Found

```json
{
  "detail": "Patch patch_123 not found"
}
```

---

## Testing

### Run Authentication Tests

```bash
cd packages/amc-repair-engine
python -m pytest tests/test_repair_service_auth.py -v
```

### Manual Testing Flow

```bash
# 1. Start repair service
uvicorn amc_repair.server:app --port 8002 --reload

# 2. Test unauthenticated (expect 401)
curl http://localhost:8002/api/patches/pending
# Response: {"detail":"Not authenticated"}

# 3. Issue a test token (Python)
from amc_repair.auth import issue_service_token
token, _ = issue_service_token("test", ["patch_read"])
print(token)

# 4. Test authenticated (expect 200)
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8002/api/patches/pending
# Response: {"total":0,"patches":[]}
```

---

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Token Validity

```python
from amc_repair.auth import verify_token_signature

payload = verify_token_signature(token, secret)
if payload:
    print(f"Valid token for: {payload}")
else:
    print("Invalid token")
```

### Check User Permissions

```python
from amc_repair.auth import parse_repair_user

user = parse_repair_user(payload)
print(f"Can approve: {user.can_approve()}")
print(f"Can promote: {user.can_promote()}")
print(f"Roles: {user.roles}")
```

---

## Security Best Practices

### Token Security

- ✅ **DO** use HTTPS in production
- ✅ **DO** rotate secrets regularly
- ✅ **DO** use short token lifetimes (1-24 hours)
- ✅ **DO** store secrets in environment variables
- ❌ **DON'T** commit secrets to version control
- ❌ **DON'T** log tokens
- ❌ **DON'T** pass tokens in URLs

### Production Deployment

```bash
# Generate strong secret
SECRET=$(openssl rand -base64 32)

# Set in both services
export REPAIR_SERVICE_SECRET="$SECRET"

# Configure network isolation
# Repair service should not be publicly accessible
# Use internal service mesh or VPN
```

### Token Rotation

```python
# Graceful secret rotation
OLD_SECRET = os.getenv("REPAIR_SERVICE_SECRET_OLD")
NEW_SECRET = os.getenv("REPAIR_SERVICE_SECRET")

# Try new secret first, fall back to old
payload = verify_token_signature(token, NEW_SECRET)
if not payload and OLD_SECRET:
    payload = verify_token_signature(token, OLD_SECRET)
```

---

## Integration with Main Application

### Getting User Token

```python
from app.auth.service import AuthService

# User logs in
token, expiry = auth_service.create_session("alice", ttl_minutes=60)

# Pass to repair client
patches = await repair_client.get_pending_patches(auth_token=token)
```

### Service-to-Service Calls

```python
# Issue service token with specific scopes
from amc_repair.auth import issue_service_token

token, _ = issue_service_token(
    service_name="main-app",
    scopes=["patch_read", "patch_approve"],
    ttl_minutes=120
)

# Use for background jobs
await repair_client.approve_patch(patch_id, auth_token=token)
```

---

## Troubleshooting

### "Not authenticated" Error

**Problem:** Getting 401 on authenticated requests

**Solutions:**
1. Check Authorization header format: `Authorization: Bearer <token>`
2. Verify token is not expired
3. Confirm REPAIR_SERVICE_SECRET matches between services
4. Check token signature with `verify_token_signature()`

### "Four-eyes policy violation" Error

**Problem:** Cannot approve own patches

**Solution:** This is by design. Different user must approve:
```python
# Alice creates patch
alice_token = get_token("alice")
await create_patch(..., auth_token=alice_token)

# Bob must approve (not Alice)
bob_token = get_token("bob")
await approve_patch(patch_id, auth_token=bob_token)
```

### "Cannot approve patches from different tenant" Error

**Problem:** Cross-tenant operation blocked

**Solutions:**
1. Use service token with `is_service=True`
2. Ensure user has correct tenant_id
3. Verify patch provenance matches user's tenant

---

## API Reference

See detailed API documentation:
- **Auth Module:** `packages/amc-repair-engine/src/amc_repair/auth.py`
- **Server:** `packages/amc-repair-engine/src/amc_repair/server.py`
- **Tests:** `packages/amc-repair-engine/tests/test_repair_service_auth.py`
- **Documentation:** `remediation/wave1_2/R1/R1-02_REPAIR_SERVICE_AUTH_COMPLETE.md`

---

## Support

For issues or questions:
1. Check this guide first
2. Review test cases in `tests/test_repair_service_auth.py`
3. Check detailed documentation in `R1-02_REPAIR_SERVICE_AUTH_COMPLETE.md`
4. Enable debug logging for troubleshooting

---

**Last Updated:** 2026-11-04  
**Version:** 1.0 (Wave 1.2 R1-02)
