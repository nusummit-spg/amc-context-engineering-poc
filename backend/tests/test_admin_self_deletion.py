import pytest
from starlette.testclient import TestClient
from app.main import app
from app.api.deps import get_auth_service

@pytest.fixture
def client():
    return TestClient(app)

def test_login_flow(client):
    """Test login via POST /api/auth/login after SessionLocal fix."""
    resp = client.post(
        "/api/auth/login",
        json={"username": "compliance_officer", "password": "Compliance@2026"}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    assert "token" in data
    assert data["user"]["username"] == "compliance_officer"
    return data["token"]

def test_admin_cannot_delete_own_account_via_bearer_token(client):
    """Administrators cannot delete their own account using JWT Bearer token."""
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "compliance_officer", "password": "Compliance@2026"}
    )
    token = login_resp.json()["token"]

    del_resp = client.delete(
        "/api/admin/users/compliance_officer",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert del_resp.status_code == 400
    assert "cannot delete their own account" in del_resp.json()["detail"].lower()

def test_admin_cannot_delete_own_account_via_user_header(client):
    """Administrators cannot delete their own account using X-User-ID header."""
    del_resp = client.delete(
        "/api/admin/users/compliance_officer",
        headers={"X-User-ID": "compliance_officer"}
    )
    assert del_resp.status_code == 400
    assert "cannot delete their own account" in del_resp.json()["detail"].lower()

def test_admin_can_create_and_delete_other_user(client):
    """Administrators can still create, update, and delete other user accounts."""
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "compliance_officer", "password": "Compliance@2026"}
    )
    token = login_resp.json()["token"]

    # 1. Create a new test user
    create_resp = client.post(
        "/api/admin/users",
        json={
            "username": "test_analyst_temp",
            "full_name": "Test Analyst",
            "role": "Fund Manager / Portfolio Manager",
            "department": "Research",
            "email": "test_analyst@amc.com",
            "status": "Active"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert create_resp.status_code == 200

    # 2. Delete the created user (other user)
    del_resp = client.delete(
        "/api/admin/users/test_analyst_temp",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] == "test_analyst_temp"

def test_protected_system_users_cannot_be_deleted(client):
    """Default system users remain protected from deletion."""
    del_resp = client.delete(
        "/api/admin/users/sarah_compliance",
        headers={"X-User-ID": "other_admin"}
    )
    assert del_resp.status_code == 400
    assert "default system users cannot be deleted" in del_resp.json()["detail"].lower()
