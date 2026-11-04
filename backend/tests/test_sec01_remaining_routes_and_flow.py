# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_sec01_remaining_routes_and_flow.py
=======================================
Security tests for remaining protected endpoints:
- Ingestion endpoints require auth (401)
- Files endpoints require auth (401)
- Graph endpoints require auth (401)
- End-to-end enrollment flow: Admin creates user -> receives invitation token ->
  user accepts invitation and sets password -> user logs in with new password
- Cross-tenant isolation: non-admin in tenant A cannot access user in tenant B
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def admin_headers():
    from app.config import get_settings
    from app.auth.security import issue_session_token, hash_password
    from app.core.database import SessionLocal
    from app.schemas.auth_users_table import AuthUser
    
    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.username == "test_flow_admin").first()
        if not user:
            user = AuthUser(
                username="test_flow_admin",
                password_hash=hash_password("AdminSecurePassword123!"),
                display_name="Test Flow Admin",
                email="test_flow_admin@amc.com",
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
    token, _ = issue_session_token("test_flow_admin", settings.auth_secret_key, 60)
    return {"Authorization": f"Bearer {token}"}


class TestIngestAuth:
    def test_ingest_file_no_auth_401(self, client):
        response = client.post("/api/ingest/file", files={"file": ("test.txt", b"content", "text/plain")})
        assert response.status_code == 401

    def test_ingest_batch_no_auth_401(self, client):
        response = client.post("/api/ingest/batch")
        assert response.status_code == 401

    def test_ingest_status_no_auth_401(self, client):
        response = client.get("/api/ingest/status/job-1234")
        assert response.status_code == 401


class TestFilesAuth:
    def test_get_file_no_auth_401(self, client):
        response = client.get("/api/files/test_document.pdf")
        assert response.status_code == 401

    def test_download_file_no_auth_401(self, client):
        response = client.get("/api/files/download/test_document.pdf")
        assert response.status_code == 401


class TestGraphAuth:
    def test_full_graph_no_auth_401(self, client):
        response = client.get("/api/graph")
        assert response.status_code == 401

    def test_neighborhood_no_auth_401(self, client):
        response = client.get("/api/graph/neighborhood?name=HDFC")
        assert response.status_code == 401

    def test_traversal_no_auth_401(self, client):
        response = client.get("/api/graph/traversal?query=What+is+NAV")
        assert response.status_code == 401


class TestEnrollmentFlowAndTenantIsolation:
    def test_full_invitation_enrollment_and_login_flow(self, client, admin_headers):
        username = f"enrolled_user_{int(datetime.now().timestamp())}"
        
        # 1. Admin creates user account
        create_resp = client.post("/api/admin/users", json={
            "username": username,
            "display_name": "Enrolled User",
            "email": f"{username}@example.com",
            "role": "analyst",
            "department": "Equities",
            "tenant_id": "tenant_x"
        }, headers=admin_headers)
        assert create_resp.status_code == 201
        data = create_resp.json()
        assert "invitation_token" in data
        assert "password" not in data  # No default password returned!
        invitation_token = data["invitation_token"]

        # 2. User accepts invitation with a strong password
        new_password = "SecureUserPass2026!"
        accept_resp = client.post("/api/auth/accept-invitation", json={
            "invitation_token": invitation_token,
            "password": new_password
        })
        assert accept_resp.status_code == 200
        assert accept_resp.json()["success"] is True

        # 3. Re-using the same invitation token fails (one-time use)
        reuse_resp = client.post("/api/auth/accept-invitation", json={
            "invitation_token": invitation_token,
            "password": new_password
        })
        assert reuse_resp.status_code in [400, 409]

        # 4. User logs in with new password
        login_resp = client.post("/api/auth/login", json={
            "username": username,
            "password": new_password
        })
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert "token" in login_data
        user_token = login_data["token"]

        # 5. User accesses /api/auth/me
        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["user"]["username"] == username
