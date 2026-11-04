# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_sec01_universal_auth.py
============================
SEC-01 Security Tests: Universal Authentication Enforcement

Tests that all sensitive endpoints require authentication and proper authorization.
These are adversarial tests - they attempt to access protected resources without
proper credentials and verify they are rejected.

Wave 1.1 P0 Closure - Security Gate Tests
"""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client for the application."""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Create headers with admin JWT token."""
    from app.config import get_settings
    from app.auth.security import issue_session_token, hash_password
    from app.core.database import SessionLocal
    from app.schemas.auth_users_table import AuthUser
    
    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.username == "test_sec_admin").first()
        if not user:
            user = AuthUser(
                username="test_sec_admin",
                password_hash=hash_password("AdminSecurePassword123!"),
                display_name="Test Sec Admin",
                email="test_sec_admin@amc.com",
                role="admin",
                department="IT Security",
                status="Active",
                tenant_id="tenant_admin",
            )
            db.add(user)
            db.commit()
    finally:
        db.close()
    
    settings = get_settings()
    token, _ = issue_session_token("test_sec_admin", settings.auth_secret_key, 60)
    return {
        "Authorization": f"Bearer {token}"
    }


@pytest.fixture
def analyst_headers():
    """Create headers with analyst (non-admin) JWT token."""
    from app.config import get_settings
    from app.auth.security import issue_session_token, hash_password
    from app.core.database import SessionLocal
    from app.schemas.auth_users_table import AuthUser
    
    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.username == "test_sec_analyst").first()
        if not user:
            user = AuthUser(
                username="test_sec_analyst",
                password_hash=hash_password("AnalystSecurePassword123!"),
                display_name="Test Sec Analyst",
                email="test_sec_analyst@amc.com",
                role="analyst",
                department="Research",
                status="Active",
                tenant_id="tenant_analyst",
            )
            db.add(user)
            db.commit()
    finally:
        db.close()
    
    settings = get_settings()
    token, _ = issue_session_token("test_sec_analyst", settings.auth_secret_key, 60)
    return {
        "Authorization": f"Bearer {token}"
    }


# ============================================================================
# SEC-01-01: Admin Endpoints - User Management
# ============================================================================

class TestAdminUserManagement:
    """Test authentication on user management endpoints."""
    
    def test_list_users_no_auth_401(self, client):
        """GET /api/admin/users without auth returns 401."""
        response = client.get("/api/admin/users")
        assert response.status_code == 401
        assert "authentication" in response.json().get("detail", "").lower() or "token" in response.json().get("detail", "").lower()
    
    def test_list_users_analyst_403(self, client, analyst_headers):
        """GET /api/admin/users with analyst role returns 403."""
        response = client.get("/api/admin/users", headers=analyst_headers)
        assert response.status_code == 403
    
    def test_create_user_no_auth_401(self, client):
        """POST /api/admin/users without auth returns 401."""
        response = client.post("/api/admin/users", json={
            "username": "testuser",
            "display_name": "Test User",
            "email": "test@example.com",
            "role": "analyst"
        })
        assert response.status_code == 401
    
    def test_create_user_analyst_403(self, client, analyst_headers):
        """POST /api/admin/users with analyst role returns 403."""
        response = client.post("/api/admin/users", json={
            "username": "testuser",
            "display_name": "Test User",
            "email": "test@example.com",
            "role": "analyst"
        }, headers=analyst_headers)
        assert response.status_code == 403
    
    def test_get_user_no_auth_401(self, client):
        """GET /api/admin/users/{username} without auth returns 401."""
        response = client.get("/api/admin/users/testuser")
        assert response.status_code == 401
    
    def test_update_user_no_auth_401(self, client):
        """PATCH /api/admin/users/{username} without auth returns 401."""
        response = client.patch("/api/admin/users/testuser", json={
            "display_name": "Updated Name"
        })
        assert response.status_code == 401
    
    def test_delete_user_no_auth_401(self, client):
        """DELETE /api/admin/users/{username} without auth returns 401."""
        response = client.delete("/api/admin/users/testuser")
        assert response.status_code == 401


# ============================================================================
# SEC-01-02: Admin Endpoints - Ingestion Control
# ============================================================================

class TestAdminIngestion:
    """Test authentication on ingestion control endpoints."""
    
    def test_trigger_ingestion_no_auth_401(self, client):
        """POST /api/admin/ingestion/run without auth returns 401."""
        response = client.post("/api/admin/ingestion/run", json={})
        assert response.status_code == 401
    
    def test_upload_file_no_auth_401(self, client):
        """POST /api/admin/ingestion/upload without auth returns 401."""
        response = client.post("/api/admin/ingestion/upload")
        assert response.status_code == 401


# ============================================================================
# SEC-01-03: Admin Endpoints - Cache Management
# ============================================================================

class TestAdminCache:
    """Test authentication on cache management endpoints."""
    
    def test_clear_cache_no_auth_401(self, client):
        """POST /api/admin/cache/clear without auth returns 401."""
        response = client.post("/api/admin/cache/clear", json={
            "cache_types": ["semantic"]
        })
        assert response.status_code == 401
    
    def test_clear_cache_analyst_403(self, client, analyst_headers):
        """POST /api/admin/cache/clear with analyst role returns 403."""
        response = client.post("/api/admin/cache/clear", json={
            "cache_types": ["semantic"]
        }, headers=analyst_headers)
        assert response.status_code == 403


# ============================================================================
# SEC-01-04: Governance Endpoints
# ============================================================================

class TestGovernanceAuth:
    """Test authentication on governance endpoints (SEC-02 fix verification)."""
    
    def test_pending_corrections_no_auth_401(self, client):
        """GET /api/governance/pending-corrections without auth returns 401."""
        response = client.get("/api/governance/pending-corrections")
        assert response.status_code == 401
    
    def test_approve_patch_no_auth_401(self, client):
        """POST /api/governance/approve/{patch_id} without auth returns 401."""
        response = client.post("/api/governance/approve/test_patch_id")
        assert response.status_code == 401
    
    def test_reject_patch_no_auth_401(self, client):
        """POST /api/governance/reject/{patch_id} without auth returns 401."""
        response = client.post("/api/governance/reject/test_patch_id")
        assert response.status_code == 401
    
    def test_batch_approve_no_auth_401(self, client):
        """POST /api/governance/batch-approve without auth returns 401."""
        response = client.post("/api/governance/batch-approve", json={
            "patch_ids": ["patch1", "patch2"],
            "action": "approve"
        })
        assert response.status_code == 401
    
    def test_run_batch_no_auth_401(self, client):
        """POST /api/governance/run-batch without auth returns 401."""
        response = client.post("/api/governance/run-batch")
        assert response.status_code == 401
    
    def test_promote_no_auth_401(self, client):
        """POST /api/governance/promote without auth returns 401."""
        response = client.post("/api/governance/promote")
        assert response.status_code == 401
    
    def test_list_proposals_no_auth_401(self, client):
        """GET /api/governance/proposals without auth returns 401."""
        response = client.get("/api/governance/proposals")
        assert response.status_code == 401
    
    def test_review_proposal_no_auth_401(self, client):
        """POST /api/governance/proposals/{id}/review without auth returns 401."""
        response = client.post("/api/governance/proposals/test_id/review", json={
            "action": "approve"
        })
        assert response.status_code == 401


# ============================================================================
# SEC-02: No X-User-Role Header Acceptance
# ============================================================================

class TestHeaderAuthRejection:
    """Verify that X-User-Role header is no longer accepted for authorization."""
    
    def test_governance_rejects_x_user_role_header(self, client):
        """Governance endpoints reject X-User-Role header (must use JWT)."""
        headers = {"X-User-Role": "admin"}  # Old insecure pattern
        response = client.get("/api/governance/pending-corrections", headers=headers)
        # Should be 401 (no Bearer token), not 200
        assert response.status_code == 401
        detail = response.json().get("detail", "").lower()
        assert any(term in detail for term in ["authorization", "authentication", "token"])
    
    def test_admin_rejects_x_user_role_header(self, client):
        """Admin endpoints reject X-User-Role header (must use JWT)."""
        headers = {"X-User-Role": "admin"}
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code == 401


# ============================================================================
# SEC-03: Invitation-Based Enrollment
# ============================================================================

class TestSecureEnrollment:
    """Test secure invitation-based enrollment (no default passwords)."""
    
    def test_accept_invitation_invalid_token_400(self, client):
        """POST /api/auth/accept-invitation with invalid token returns 400 or 422."""
        response = client.post("/api/auth/accept-invitation", json={
            "invitation_token": "invalid_token_12345678901234567890",
            "password": "StrongPassword123!"
        })
        # Should reject invalid token
        assert response.status_code in [400, 404, 422]
    
    def test_accept_invitation_weak_password_400(self, client):
        """POST /api/auth/accept-invitation with weak password returns 400."""
        from app.core.database import SessionLocal
        from app.schemas.auth_users_table import AuthUser
        from app.schemas.invitation_token import InvitationToken
        
        token = "test_valid_invite_token_weak_pass_test"
        db = SessionLocal()
        try:
            # Clean up if exists
            db.query(InvitationToken).filter(InvitationToken.token == token).delete()
            db.query(AuthUser).filter(AuthUser.username == "test_invitee_user").delete()
            db.commit()
            
            pending_user = AuthUser(
                username="test_invitee_user",
                password_hash="",
                display_name="Test Invitee",
                email="invitee@example.com",
                role="analyst",
                department="Research",
                status="Pending",
                tenant_id="default",
            )
            invite = InvitationToken(
                token=token,
                username="test_invitee_user",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                created_by="test_sec_admin",
                used=False,
            )
            db.add(pending_user)
            db.add(invite)
            db.commit()
        finally:
            db.close()
            
        response = client.post("/api/auth/accept-invitation", json={
            "invitation_token": token,
            "password": "weak"  # Too short (<12 chars)
        })
        # Pydantic schema validation returns 422 or endpoint returns 400
        assert response.status_code in [400, 422]
        error_text = str(response.json()).lower()
        assert "password" in error_text or "too_short" in error_text


# ============================================================================
# REP-01: No Confidence-Based Auto-Approval
# ============================================================================

class TestNoAutoApproval:
    """Verify that confidence-based auto-approval is disabled."""
    
    def test_run_batch_does_not_auto_approve(self, client, admin_headers):
        """POST /api/governance/run-batch only categorizes, does not auto-approve."""
        response = client.post("/api/governance/run-batch", json={
            "auto_approve_threshold": 0.95,
            "max_risk_level": "LOW",
            "dry_run": False
        }, headers=admin_headers)
        
        assert response.status_code == 200
        data = response.json()
        # REP-01 compliance: should return categorization, not approvals
        assert data.get("status") == "review_categorization_completed"
        assert "REP-01 COMPLIANCE" in data.get("message", "")
        # Should not have auto-approved anything
        assert "recommended_for_approval" in data
        assert "recommended_for_rejection" in data
        assert "requires_detailed_review" in data
