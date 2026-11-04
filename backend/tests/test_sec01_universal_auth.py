# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_sec01_universal_auth.py
============================
Comprehensive tests for SEC-01: Universal CurrentUser enforcement.

Tests authentication requirements on:
- Admin routes (user management, ingestion, cache)
- Audit routes (metadata, violations, feedback, compliance)
- Governance routes (issues, proposals)
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestAdminRoutesAuth:
    """Test admin routes require authentication and admin role"""
    
    def test_list_users_requires_auth(self):
        """GET /api/admin/users should require authentication"""
        response = client.get("/api/admin/users")
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_create_user_requires_auth(self):
        """POST /api/admin/users should require authentication"""
        response = client.post("/api/admin/users", json={
            "username": "test",
            "full_name": "Test User",
            "role": "analyst"
        })
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_delete_user_requires_auth(self):
        """DELETE /api/admin/users/{username} should require authentication"""
        response = client.delete("/api/admin/users/test")
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_sync_users_requires_auth(self):
        """POST /api/admin/users/sync should require authentication"""
        response = client.post("/api/admin/users/sync")
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_rbac_matrix_requires_auth(self):
        """GET /api/admin/rbac should require authentication"""
        response = client.get("/api/admin/rbac")
        assert response.status_code in [401, 404], "Should require authentication or not exist"


class TestAuditRoutesAuth:
    """Test audit routes require authentication"""
    
    def test_list_audit_metadata_requires_auth(self):
        """GET /api/audit/audit-metadata should require authentication"""
        response = client.get("/api/audit/audit-metadata")
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_create_audit_metadata_requires_auth(self):
        """POST /api/audit/audit-metadata should require authentication"""
        response = client.post("/api/audit/audit-metadata", json={
            "audit_id": "test",
            "query_text": "test query"
        })
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_list_violations_requires_auth(self):
        """GET /api/audit/violations should require authentication"""
        response = client.get("/api/audit/violations")
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_create_violation_requires_auth(self):
        """POST /api/audit/violations should require authentication"""
        response = client.post("/api/audit/violations", json={
            "audit_id": "test",
            "rule_id": "R001",
            "severity": "high"
        })
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_list_response_feedback_requires_auth(self):
        """GET /api/audit/response-feedback should require authentication"""
        response = client.get("/api/audit/response-feedback")
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_create_response_feedback_requires_auth(self):
        """POST /api/audit/response-feedback should require authentication"""
        response = client.post("/api/audit/response-feedback", json={
            "response_id": "test",
            "feedback_text": "test feedback"
        })
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_list_compliance_rules_requires_auth(self):
        """GET /api/audit/compliance-rules should require authentication"""
        response = client.get("/api/audit/compliance-rules")
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_create_compliance_rule_requires_auth(self):
        """POST /api/audit/compliance-rules should require authentication"""
        response = client.post("/api/audit/compliance-rules", json={
            "rule_id": "R001",
            "rule_text": "test rule"
        })
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_list_fund_schemes_requires_auth(self):
        """GET /api/audit/fund-schemes should require authentication"""
        response = client.get("/api/audit/fund-schemes")
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_create_fund_scheme_requires_auth(self):
        """POST /api/audit/fund-schemes should require authentication"""
        response = client.post("/api/audit/fund-schemes", json={
            "scheme_id": "S001",
            "scheme_name": "Test Scheme"
        })
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_list_sessions_requires_auth(self):
        """GET /api/audit/chat-sessions should require authentication"""
        response = client.get("/api/audit/chat-sessions")
        assert response.status_code == 401, "Should reject unauthenticated request"
    
    def test_create_session_requires_auth(self):
        """POST /api/audit/chat-sessions should require authentication"""
        response = client.post("/api/audit/chat-sessions", json={
            "session_id": "test",
            "user_id": "test"
        })
        assert response.status_code == 401, "Should reject unauthenticated request"


class TestHeaderSpoofPrevention:
    """Test that X-User-* headers don't grant access without JWT"""
    
    def test_x_user_id_header_ignored(self):
        """X-User-ID header should not grant access without JWT"""
        response = client.get("/api/admin/users", headers={
            "X-User-ID": "admin"
        })
        assert response.status_code == 401, "Should ignore X-User-ID without JWT"
    
    def test_x_user_role_header_ignored(self):
        """X-User-Role header should not grant access without JWT"""
        response = client.post("/api/admin/users", headers={
            "X-User-Role": "admin"
        }, json={
            "username": "attacker",
            "full_name": "Attacker",
            "role": "admin"
        })
        assert response.status_code == 401, "Should ignore X-User-Role without JWT"
    
    def test_combined_headers_ignored(self):
        """Multiple headers should not grant access without JWT"""
        response = client.delete("/api/admin/users/victim", headers={
            "X-User-ID": "admin",
            "X-User-Role": "admin",
            "X-User-Department": "IT"
        })
        assert response.status_code == 401, "Should ignore all X-User-* headers without JWT"


class TestPublicRoutesRemainPublic:
    """Verify that public routes remain accessible"""
    
    def test_health_endpoint_public(self):
        """Health endpoint should remain public"""
        response = client.get("/health")
        # Should not be 401 (either 200 OK or 404 Not Found)
        assert response.status_code != 401, "Health endpoint should be public"
    
    def test_login_endpoint_public(self):
        """Login endpoint should remain public"""
        response = client.post("/api/auth/login", json={
            "username": "test",
            "password": "test"
        })
        # Should not be 401 (could be 400/422 for invalid credentials)
        assert response.status_code != 401, "Login endpoint should be public"


class TestRoleBasedAccessControl:
    """Test role-based access control helpers"""
    
    def test_require_admin_helper(self):
        """require_admin should raise 403 for non-admin users"""
        from app.auth.service import require_admin, AuthenticatedUser
        from fastapi import HTTPException
        
        non_admin_user = AuthenticatedUser(
            username="analyst",
            display_name="Analyst User",
            role="analyst",
            department="Research",
            email="analyst@example.com",
            avatar_initials="AU",
            status="active"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            require_admin(non_admin_user)
        
        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail.lower()
    
    def test_require_admin_allows_admin(self):
        """require_admin should allow admin users"""
        from app.auth.service import require_admin, AuthenticatedUser
        
        admin_user = AuthenticatedUser(
            username="admin",
            display_name="Admin User",
            role="admin",
            department="IT",
            email="admin@example.com",
            avatar_initials="AU",
            status="active"
        )
        
        # Should not raise exception
        require_admin(admin_user)
    
    def test_require_role_helper(self):
        """require_role should enforce allowed roles"""
        from app.auth.service import require_role, AuthenticatedUser
        from fastapi import HTTPException
        
        analyst_user = AuthenticatedUser(
            username="analyst",
            display_name="Analyst User",
            role="analyst",
            department="Research",
            email="analyst@example.com",
            avatar_initials="AU",
            status="active"
        )
        
        # Should raise exception for disallowed role
        with pytest.raises(HTTPException) as exc_info:
            require_role(analyst_user, ["admin", "compliance_owner"])
        
        assert exc_info.value.status_code == 403
        
        # Should allow for included role
        require_role(analyst_user, ["analyst", "researcher"])
    
    def test_get_tenant_id_helper(self):
        """get_tenant_id should extract tenant from user"""
        from app.auth.service import get_tenant_id, AuthenticatedUser
        
        user_with_tenant = AuthenticatedUser(
            username="user1",
            display_name="User One",
            role="analyst",
            department="Research",
            email="user1@example.com",
            avatar_initials="UO",
            status="active",
            tenant_id="tenant_123"
        )
        
        assert get_tenant_id(user_with_tenant) == "tenant_123"
        
        user_without_tenant = AuthenticatedUser(
            username="user2",
            display_name="User Two",
            role="analyst",
            department="Research",
            email="user2@example.com",
            avatar_initials="UT",
            status="active",
            tenant_id=None
        )
        
        # Should default to department
        assert get_tenant_id(user_without_tenant) == "Research"


class TestAuthenticationMatrix:
    """Comprehensive authentication matrix test"""
    
    SENSITIVE_ROUTES = [
        ("GET", "/api/admin/users"),
        ("POST", "/api/admin/users"),
        ("DELETE", "/api/admin/users/test"),
        ("POST", "/api/admin/users/sync"),
        ("GET", "/api/audit/audit-metadata"),
        ("POST", "/api/audit/audit-metadata"),
        ("GET", "/api/audit/violations"),
        ("POST", "/api/audit/violations"),
        ("GET", "/api/audit/response-feedback"),
        ("POST", "/api/audit/response-feedback"),
        ("GET", "/api/audit/compliance-rules"),
        ("POST", "/api/audit/compliance-rules"),
        ("GET", "/api/audit/fund-schemes"),
        ("POST", "/api/audit/fund-schemes"),
        ("GET", "/api/audit/chat-sessions"),
        ("POST", "/api/audit/chat-sessions"),
    ]
    
    def test_all_sensitive_routes_require_auth(self):
        """Verify all sensitive routes reject unauthenticated requests"""
        results = []
        
        for method, route in self.SENSITIVE_ROUTES:
            if method == "GET":
                response = client.get(route)
            elif method == "POST":
                response = client.post(route, json={})
            elif method == "DELETE":
                response = client.delete(route)
            elif method == "PUT":
                response = client.put(route, json={})
            else:
                continue
            
            results.append((method, route, response.status_code))
            
            # All should return 401 (or 422 if request validation fails before auth)
            assert response.status_code in [401, 422], \
                f"{method} {route} returned {response.status_code}, expected 401 or 422"
        
        # Log results for audit trail
        print("\n\nAuthentication Matrix Results:")
        print("=" * 70)
        for method, route, status in results:
            print(f"{method:6} {route:50} -> {status}")
        print("=" * 70)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
