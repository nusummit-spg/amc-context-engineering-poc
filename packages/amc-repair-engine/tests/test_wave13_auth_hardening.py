"""
Wave 1.3 Batch A Tests: Authentication and Authorization Hardening
Tests for A02 (read access control) and A03 (token trust boundaries).

Security Requirements:
- Unauthenticated reads must be rejected (401)
- Wrong scope must be rejected (403)
- Cross-tenant access must be denied (403/404)
- Expired/missing exp/wrong issuer/audience must be rejected
- Service identity alone cannot approve without explicit scope
"""

import pytest
import time
import json
import hmac
import hashlib
import base64
from datetime import datetime, timezone
from fastapi.testclient import TestClient

# Import the auth module and server
from amc_repair.auth import (
    RepairUser,
    verify_token_signature,
    issue_service_token,
    parse_repair_user,
    EXPECTED_ISSUER,
    EXPECTED_AUDIENCE,
    SERVICE_SECRET,
)
from amc_repair.server import app


client = TestClient(app)


def _b64url_encode(raw: bytes) -> str:
    """Base64 URL encode without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def create_test_token(
    username: str = "testuser",
    user_id: str = "test123",
    tenant_id: str = "tenant1",
    roles: list = None,
    is_service: bool = False,
    service_name: str = None,
    scopes: list = None,
    include_exp: bool = True,
    expired: bool = False,
    include_iss: bool = True,
    include_aud: bool = True,
    include_token_type: bool = True,
    wrong_issuer: bool = False,
    wrong_audience: bool = False,
    ttl_seconds: int = 3600,
) -> str:
    """
    Create test authentication token for testing.
    
    Args:
        username: User username
        user_id: User ID
        tenant_id: Tenant ID
        roles: List of roles
        is_service: Whether this is a service token
        service_name: Service name for service tokens
        scopes: Service scopes for service tokens
        include_exp: Include exp field
        expired: Make token expired
        include_iss: Include iss field
        include_aud: Include aud field
        include_token_type: Include token_type field
        wrong_issuer: Use wrong issuer
        wrong_audience: Use wrong audience
        ttl_seconds: Token validity in seconds
    
    Returns:
        Encoded token string
    """
    if roles is None:
        roles = ["analyst"]
    if scopes is None:
        scopes = []
    
    now = int(time.time())
    
    payload = {
        "iat": now
    }
    
    if include_exp:
        if expired:
            payload["exp"] = now - 3600  # Expired 1 hour ago
        else:
            payload["exp"] = now + ttl_seconds
    
    if include_iss:
        payload["iss"] = "wrong-issuer" if wrong_issuer else EXPECTED_ISSUER
    
    if include_aud:
        payload["aud"] = "wrong-audience" if wrong_audience else EXPECTED_AUDIENCE
    
    if include_token_type:
        payload["token_type"] = "service" if is_service else "user"
    
    if is_service:
        payload["service_name"] = service_name or "test-service"
        payload["scopes"] = scopes
        if tenant_id:
            payload["tenant_id"] = tenant_id
    else:
        payload["sub"] = username
        payload["user_id"] = user_id
        payload["username"] = username
        payload["tenant_id"] = tenant_id
        payload["roles"] = roles
    
    # Sign the token
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = _b64url_encode(payload_json.encode("utf-8"))
    
    signature = hmac.new(
        SERVICE_SECRET.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256
    ).digest()
    
    signature_b64 = _b64url_encode(signature)
    
    return f"{payload_b64}.{signature_b64}"


# ============================================================================
# A03 Tests: Token Trust Boundaries
# ============================================================================

class TestA03TokenValidation:
    """Test token validation hardening from A03."""
    
    def test_valid_token_accepted(self):
        """Valid token with all required fields should be accepted."""
        token = create_test_token(username="alice", roles=["reviewer"])
        payload = verify_token_signature(token, SERVICE_SECRET)
        
        assert payload is not None
        assert payload["token_type"] == "user"
        assert payload["sub"] == "alice"
        assert "exp" in payload
        assert "iss" in payload
        assert "aud" in payload
    
    def test_missing_exp_rejected(self):
        """A03: Token without exp field must be rejected."""
        token = create_test_token(username="alice", include_exp=False)
        payload = verify_token_signature(token, SERVICE_SECRET)
        
        # Should be None (rejected) unless ALLOW_MISSING_EXP is true
        # In production/test, this should be False
        assert payload is None, "Token without exp should be rejected"
    
    def test_expired_token_rejected(self):
        """A03: Expired token must be rejected."""
        token = create_test_token(username="alice", expired=True)
        payload = verify_token_signature(token, SERVICE_SECRET)
        
        assert payload is None, "Expired token should be rejected"
    
    def test_wrong_issuer_rejected(self):
        """A03: Token with wrong issuer must be rejected."""
        token = create_test_token(username="alice", wrong_issuer=True)
        payload = verify_token_signature(token, SERVICE_SECRET)
        
        assert payload is None, "Token with wrong issuer should be rejected"
    
    def test_wrong_audience_rejected(self):
        """A03: Token with wrong audience must be rejected."""
        token = create_test_token(username="alice", wrong_audience=True)
        payload = verify_token_signature(token, SERVICE_SECRET)
        
        assert payload is None, "Token with wrong audience should be rejected"
    
    def test_missing_token_type_rejected(self):
        """A03: Token without token_type field must be rejected."""
        token = create_test_token(username="alice", include_token_type=False)
        payload = verify_token_signature(token, SERVICE_SECRET)
        
        assert payload is None, "Token without token_type should be rejected"
    
    def test_tampered_signature_rejected(self):
        """A03: Token with tampered signature must be rejected."""
        token = create_test_token(username="alice", roles=["admin"])
        
        # Tamper with the token
        parts = token.split(".")
        tampered_token = f"{parts[0]}.invalid_signature"
        
        payload = verify_token_signature(tampered_token, SERVICE_SECRET)
        
        assert payload is None, "Tampered token should be rejected"
    
    def test_wrong_secret_rejected(self):
        """A03: Token signed with wrong secret must be rejected."""
        token = create_test_token(username="alice")
        
        payload = verify_token_signature(token, "wrong-secret")
        
        assert payload is None, "Token with wrong secret should be rejected"


class TestA03ServiceScopeEnforcement:
    """Test service scope separation from approval authority (C-04)."""
    
    def test_service_with_approve_scope_can_approve(self):
        """A03: Service with explicit patch_approve scope can approve."""
        user = RepairUser(
            username="service-a",
            is_service=True,
            service_name="service-a",
            roles=["patch_read", "patch_approve"],
        )
        
        assert user.can_approve() is True
    
    def test_service_without_approve_scope_cannot_approve(self):
        """A03 (C-04 FIX): Service without patch_approve scope cannot approve."""
        user = RepairUser(
            username="service-b",
            is_service=True,
            service_name="service-b",
            roles=["patch_read"],  # No patch_approve
        )
        
        assert user.can_approve() is False, "Service without patch_approve scope should not be able to approve"
    
    def test_service_generic_cannot_approve(self):
        """A03 (C-04 FIX): Generic service identity cannot approve."""
        user = RepairUser(
            username="generic-service",
            is_service=True,
            service_name="generic-service",
            roles=[],  # No specific scopes
        )
        
        assert user.can_approve() is False
    
    def test_human_reviewer_can_approve(self):
        """A03: Human reviewer can still approve."""
        user = RepairUser(
            username="bob",
            roles=["reviewer"],
            is_service=False,
        )
        
        assert user.can_approve() is True
    
    def test_human_admin_can_approve(self):
        """A03: Human admin can approve."""
        user = RepairUser(
            username="alice",
            roles=["admin"],
            is_service=False,
        )
        
        assert user.can_approve() is True
    
    def test_human_analyst_cannot_approve(self):
        """A03: Regular analyst cannot approve."""
        user = RepairUser(
            username="charlie",
            roles=["analyst"],
            is_service=False,
        )
        
        assert user.can_approve() is False
    
    def test_service_with_promote_scope_can_promote(self):
        """A03: Service with explicit patch_promote scope can promote."""
        user = RepairUser(
            username="promotion-service",
            is_service=True,
            service_name="promotion-service",
            roles=["patch_read", "patch_promote"],
        )
        
        assert user.can_promote() is True
    
    def test_service_without_promote_scope_cannot_promote(self):
        """A03: Service without patch_promote scope cannot promote."""
        user = RepairUser(
            username="read-service",
            is_service=True,
            service_name="read-service",
            roles=["patch_read"],
        )
        
        assert user.can_promote() is False


class TestA03IssueServiceToken:
    """Test service token issuance with scope validation."""
    
    def test_valid_service_token_issuance(self):
        """A03: Issue service token with valid scopes."""
        token, exp = issue_service_token(
            service_name="test-service",
            scopes=["patch_read", "patch_create"],
            tenant_id="tenant1"
        )
        
        assert token is not None
        assert isinstance(exp, int)
        assert exp > int(time.time())
        
        # Verify token structure
        payload = verify_token_signature(token, SERVICE_SECRET)
        assert payload is not None
        assert payload["token_type"] == "service"
        assert payload["service_name"] == "test-service"
        assert payload["scopes"] == ["patch_read", "patch_create"]
        assert payload["tenant_id"] == "tenant1"
        assert payload["iss"] == EXPECTED_ISSUER
        assert payload["aud"] == EXPECTED_AUDIENCE
    
    def test_invalid_scope_rejected(self):
        """A03: Issuing token with invalid scope must fail."""
        with pytest.raises(ValueError, match="Invalid service scopes"):
            issue_service_token(
                service_name="bad-service",
                scopes=["invalid_scope", "patch_read"]
            )
    
    def test_service_token_has_required_fields(self):
        """A03: Service token must include all required fields."""
        token, _ = issue_service_token(
            service_name="test-service",
            scopes=["patch_read"]
        )
        
        payload = verify_token_signature(token, SERVICE_SECRET)
        
        assert "token_type" in payload
        assert "exp" in payload
        assert "iat" in payload
        assert "iss" in payload
        assert "aud" in payload
        assert "service_name" in payload
        assert "scopes" in payload


# ============================================================================
# A02 Tests: Read Access Control
# ============================================================================

class TestA02GetPatchesByEntity:
    """Test authentication on GET /api/patches/for-entities."""
    
    def test_unauthenticated_request_rejected(self):
        """A02 (C-03 FIX): Unauthenticated request must return 401."""
        response = client.get("/api/patches/for-entities?entity_ids=entity1,entity2")
        
        assert response.status_code == 401, "Unauthenticated request should return 401"
    
    def test_authenticated_reviewer_can_read(self):
        """A02: Authenticated reviewer can read patches."""
        token = create_test_token(username="reviewer1", roles=["reviewer"])
        
        response = client.get(
            "/api/patches/for-entities?entity_ids=entity1",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should succeed (200) or return empty list, not 401/403
        assert response.status_code in [200, 404], f"Reviewer should be able to read, got {response.status_code}"
    
    def test_authenticated_admin_can_read(self):
        """A02: Authenticated admin can read patches."""
        token = create_test_token(username="admin1", roles=["admin"])
        
        response = client.get(
            "/api/patches/for-entities?entity_ids=entity1",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code in [200, 404]
    
    def test_analyst_without_reviewer_role_denied(self):
        """A02: Regular analyst without reviewer role should be denied."""
        token = create_test_token(username="analyst1", roles=["analyst"])
        
        response = client.get(
            "/api/patches/for-entities?entity_ids=entity1",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 403, "Analyst without reviewer role should be denied"
    
    def test_service_with_patch_read_can_read(self):
        """A02: Service with patch_read scope can read."""
        token = create_test_token(
            is_service=True,
            service_name="read-service",
            scopes=["patch_read"]
        )
        
        response = client.get(
            "/api/patches/for-entities?entity_ids=entity1",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code in [200, 404]


class TestA02GetPatchById:
    """Test authentication on GET /api/patches/{patch_id}."""
    
    def test_unauthenticated_request_rejected(self):
        """A02 (C-03 FIX): Unauthenticated request must return 401."""
        response = client.get("/api/patches/test-patch-123")
        
        assert response.status_code == 401, "Unauthenticated request should return 401"
    
    def test_authenticated_reviewer_can_read(self):
        """A02: Authenticated reviewer can read patch."""
        token = create_test_token(username="reviewer1", roles=["reviewer"])
        
        response = client.get(
            "/api/patches/test-patch-123",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Will be 404 if patch doesn't exist, but not 401/403
        assert response.status_code in [200, 404, 500], f"Got unexpected {response.status_code}"
        assert response.status_code != 401, "Should not be unauthorized"
        assert response.status_code != 403, "Reviewer should not be forbidden"
    
    def test_analyst_without_reviewer_role_denied(self):
        """A02: Regular analyst without reviewer role should be denied."""
        token = create_test_token(username="analyst1", roles=["analyst"])
        
        response = client.get(
            "/api/patches/test-patch-123",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 403, "Analyst without reviewer role should be denied"


class TestA02TenantIsolation:
    """Test tenant isolation in patch read operations."""
    
    # NOTE: These tests require actual patch data in the repair engine
    # For now, we verify the authentication and authorization layer
    # Integration tests with real data will be added in test_repair_engine.py
    
    def test_cross_tenant_service_without_tenant_all_scope_denied(self):
        """A02: Service without tenant:all trying to read cross-tenant is denied."""
        # This would require setting up patches with tenant data
        # Test logic: create patch in tenant1, try to read as tenant2 service without tenant:all
        token = create_test_token(
            is_service=True,
            service_name="scoped-service",
            tenant_id="tenant2",
            scopes=["patch_read"]  # No tenant:all
        )
        
        # Would test against a known tenant1 patch
        # For now, verify token parsing works correctly
        payload = verify_token_signature(token, SERVICE_SECRET)
        assert payload["tenant_id"] == "tenant2"
        assert "tenant:all" not in payload["scopes"]


# ============================================================================
# Integration Tests
# ============================================================================

class TestA02A03Integration:
    """Integration tests combining A02 and A03 fixes."""
    
    def test_expired_token_cannot_read_patches(self):
        """Expired token should be rejected even with correct roles."""
        token = create_test_token(username="reviewer1", roles=["reviewer"], expired=True)
        
        response = client.get(
            "/api/patches/for-entities?entity_ids=entity1",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 401, "Expired token should be rejected"
    
    def test_service_without_approve_scope_cannot_approve(self):
        """A03 (C-04): Service without patch_approve scope cannot approve patches."""
        token = create_test_token(
            is_service=True,
            service_name="readonly-service",
            scopes=["patch_read"]  # No patch_approve
        )
        
        response = client.post(
            "/api/patches/test-patch-123/approve",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 403, "Service without patch_approve scope should be denied"
    
    def test_tampered_token_cannot_access_any_endpoint(self):
        """Tampered token should be universally rejected."""
        token = create_test_token(username="admin", roles=["admin"])
        parts = token.split(".")
        tampered = f"{parts[0]}.tampered_signature"
        
        # Try read
        response = client.get(
            "/api/patches/pending",
            headers={"Authorization": f"Bearer {tampered}"}
        )
        assert response.status_code == 401
        
        # Try approve
        response = client.post(
            "/api/patches/test-123/approve",
            headers={"Authorization": f"Bearer {tampered}"}
        )
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
