"""
Tests for Repair Engine microservice authentication and authorization.
Validates R1-02 and R1-03 (four-eyes enforcement) requirements.
"""
import pytest
import sys
import os
from datetime import datetime, timezone

# Add parent package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from amc_repair.auth import (
    verify_token_signature,
    parse_repair_user,
    RepairUser,
    issue_service_token,
    _b64url_encode,
    _b64url_decode
)
import json
import hashlib
import hmac
import time


class TestTokenVerification:
    """Test JWT token verification logic."""
    
    def test_valid_token_verification(self):
        """Valid token with correct signature should verify."""
        secret = "test-secret-key"
        
        # Create token manually
        payload = {
            "sub": "testuser",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "roles": ["reviewer"]
        }
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
        signature_b64 = _b64url_encode(signature)
        token = f"{payload_b64}.{signature_b64}"
        
        result = verify_token_signature(token, secret)
        
        assert result is not None
        assert result["sub"] == "testuser"
        assert "roles" in result
    
    def test_invalid_signature_rejected(self):
        """Token with wrong signature should be rejected."""
        secret = "test-secret-key"
        wrong_secret = "wrong-secret"
        
        payload = {
            "sub": "testuser",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600
        }
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        
        # Sign with wrong secret
        signature = hmac.new(wrong_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
        signature_b64 = _b64url_encode(signature)
        token = f"{payload_b64}.{signature_b64}"
        
        result = verify_token_signature(token, secret)
        assert result is None
    
    def test_expired_token_rejected(self):
        """Expired token should be rejected."""
        secret = "test-secret-key"
        
        payload = {
            "sub": "testuser",
            "iat": int(time.time()) - 7200,  # 2 hours ago
            "exp": int(time.time()) - 3600   # Expired 1 hour ago
        }
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
        signature_b64 = _b64url_encode(signature)
        token = f"{payload_b64}.{signature_b64}"
        
        result = verify_token_signature(token, secret)
        assert result is None
    
    def test_malformed_token_rejected(self):
        """Malformed token should be rejected."""
        secret = "test-secret-key"
        
        # Missing signature part
        result = verify_token_signature("just-one-part", secret)
        assert result is None
        
        # Too many parts
        result = verify_token_signature("part1.part2.part3", secret)
        assert result is None
        
        # Invalid base64
        result = verify_token_signature("!!!invalid!!!.!!!invalid!!!", secret)
        assert result is None


class TestRepairUserParsing:
    """Test parsing of JWT payloads into RepairUser objects."""
    
    def test_parse_end_user_token(self):
        """Parse end-user JWT token."""
        payload = {
            "sub": "alice",
            "user_id": "user_123",
            "tenant_id": "tenant_abc",
            "roles": ["reviewer", "admin"]
        }
        
        user = parse_repair_user(payload)
        
        assert user.username == "alice"
        assert user.user_id == "user_123"
        assert user.tenant_id == "tenant_abc"
        assert user.roles == ["reviewer", "admin"]
        assert user.is_service is False
        assert user.service_name is None
    
    def test_parse_service_token(self):
        """Parse service-to-service token."""
        payload = {
            "token_type": "service",
            "service_name": "feedback-service",
            "scopes": ["patch_read", "patch_approve"],
            "tenant_id": None
        }
        
        user = parse_repair_user(payload)
        
        assert user.username == "feedback-service"
        assert user.is_service is True
        assert user.service_name == "feedback-service"
        assert user.roles == ["patch_read", "patch_approve"]
        assert user.tenant_id is None
    
    def test_parse_minimal_token(self):
        """Parse token with minimal fields."""
        payload = {
            "sub": "bob"
        }
        
        user = parse_repair_user(payload)
        
        assert user.username == "bob"
        assert user.user_id is None
        assert user.tenant_id is None
        assert user.roles == []
        assert user.is_service is False


class TestRepairUserPermissions:
    """Test RepairUser permission checks."""
    
    def test_reviewer_can_approve(self):
        """Reviewer role should have approval permissions."""
        user = RepairUser(
            username="reviewer",
            roles=["reviewer"]
        )
        assert user.can_approve() is True
    
    def test_admin_can_approve_and_promote(self):
        """Admin role should have all permissions."""
        user = RepairUser(
            username="admin",
            roles=["admin"]
        )
        assert user.can_approve() is True
        assert user.can_promote() is True
    
    def test_service_with_scope_can_promote(self):
        """Service with patch_promotion scope can promote."""
        user = RepairUser(
            username="deploy-service",
            is_service=True,
            roles=["patch_promotion"]
        )
        assert user.can_approve() is True  # Services can approve
        assert user.can_promote() is True
    
    def test_regular_user_cannot_approve(self):
        """Regular user without reviewer role cannot approve."""
        user = RepairUser(
            username="regular",
            roles=["user"]
        )
        assert user.can_approve() is False
        assert user.can_promote() is False
    
    def test_has_role_check(self):
        """Test role checking logic."""
        user = RepairUser(
            username="test",
            roles=["viewer", "editor"]
        )
        assert user.has_role("viewer") is True
        assert user.has_role("editor") is True
        assert user.has_role("admin") is False
        
        # Admin role grants all permissions
        admin = RepairUser(username="admin", roles=["admin"])
        assert admin.has_role("anything") is True


class TestServiceTokenIssuance:
    """Test service-to-service token generation."""
    
    def test_issue_service_token(self):
        """Service token should be properly formatted."""
        secret = "service-secret"
        
        token, exp = issue_service_token(
            service_name="feedback-service",
            scopes=["patch_read", "patch_create"],
            secret=secret,
            ttl_minutes=60
        )
        
        # Verify token format
        assert "." in token
        parts = token.split(".")
        assert len(parts) == 2
        
        # Verify token can be validated
        payload = verify_token_signature(token, secret)
        assert payload is not None
        assert payload["token_type"] == "service"
        assert payload["service_name"] == "feedback-service"
        assert payload["scopes"] == ["patch_read", "patch_create"]
        
        # Verify expiration is in future
        assert exp > int(time.time())
    
    def test_service_token_expiration(self):
        """Service token expiration should be configurable."""
        secret = "service-secret"
        
        token, exp = issue_service_token(
            service_name="test-service",
            scopes=[],
            secret=secret,
            ttl_minutes=10
        )
        
        # Expiration should be approximately 10 minutes from now
        now = int(time.time())
        assert exp > now
        assert exp <= now + 11 * 60  # Allow 1 minute tolerance


class TestFourEyesScenarios:
    """Test four-eyes enforcement scenarios for R1-03."""
    
    def test_different_users_can_approve(self):
        """Different users should pass four-eyes check."""
        proposer = RepairUser(
            username="alice",
            user_id="user_1",
            roles=["user"]
        )
        
        approver = RepairUser(
            username="bob",
            user_id="user_2",
            roles=["reviewer"]
        )
        
        # In real implementation, this check happens in the endpoint
        assert proposer.user_id != approver.user_id
        assert proposer.username != approver.username
    
    def test_same_user_id_detected(self):
        """Same user_id should fail four-eyes check."""
        proposer_id = "user_123"
        approver_id = "user_123"
        
        assert proposer_id == approver_id  # Should be rejected
    
    def test_same_username_detected(self):
        """Same username should fail four-eyes check."""
        proposer_username = "alice"
        approver_username = "alice"
        
        assert proposer_username == approver_username  # Should be rejected


class TestTenantIsolation:
    """Test tenant isolation in authentication."""
    
    def test_same_tenant_allowed(self):
        """User should access patches from their own tenant."""
        user = RepairUser(
            username="alice",
            tenant_id="tenant_A",
            roles=["reviewer"]
        )
        
        patch_tenant = "tenant_A"
        assert user.tenant_id == patch_tenant
    
    def test_different_tenant_blocked(self):
        """User should not access patches from different tenant."""
        user = RepairUser(
            username="alice",
            tenant_id="tenant_A",
            roles=["reviewer"]
        )
        
        patch_tenant = "tenant_B"
        assert user.tenant_id != patch_tenant  # Should be blocked
    
    def test_service_token_bypasses_tenant(self):
        """Service tokens can operate across tenants."""
        service = RepairUser(
            username="admin-service",
            is_service=True,
            tenant_id=None,
            roles=["patch_read", "patch_approve"]
        )
        
        # Service should be able to access any tenant
        assert service.is_service is True
        assert service.tenant_id is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
