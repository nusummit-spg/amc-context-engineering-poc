import os
import sys
import pytest
from starlette.testclient import TestClient

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app
from app.core.database import SessionLocal
from app.schemas.auth_users_table import AuthUser

client = TestClient(app)

def test_create_new_user_with_default_password_and_login():
    """Verify that a user created without explicit password receives Welcome@2026 and can log in."""
    # 1. Admin logs in
    admin_login = client.post("/api/auth/login", json={"username": "compliance_officer", "password": "Compliance@2026"})
    assert admin_login.status_code == 200
    token = admin_login.json()["token"]

    username = "new_compliance_analyst"
    # Ensure clean state
    client.delete(f"/api/admin/users/{username}", headers={"Authorization": f"Bearer {token}"})

    # 2. Admin creates user WITHOUT providing a password
    create_resp = client.post(
        "/api/admin/users",
        json={
            "username": username,
            "full_name": "New Compliance Analyst",
            "role": "Compliance & Regulatory Officer",
            "department": "Regulatory",
            "email": "new.analyst@amc.com",
            "status": "Active"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert create_resp.status_code == 200
    res_data = create_resp.json()
    assert res_data["assigned_password"] == "Welcome@2026"

    # 3. Newly created user logs in using the default temporary password
    user_login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "Welcome@2026"}
    )
    assert user_login.status_code == 200, f"Login failed: {user_login.text}"
    user_token = user_login.json()["token"]
    assert user_login.json()["user"]["username"] == username

    # 4. User can access auth/me and sessions
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["username"] == username

    sess_resp = client.get("/api/sessions", headers={"Authorization": f"Bearer {user_token}"})
    assert sess_resp.status_code == 200

    # Clean up
    client.delete(f"/api/admin/users/{username}", headers={"Authorization": f"Bearer {token}"})


def test_create_new_user_with_custom_password_and_login():
    """Verify that a user created with a custom password can log in immediately."""
    admin_login = client.post("/api/auth/login", json={"username": "compliance_officer", "password": "Compliance@2026"})
    assert admin_login.status_code == 200
    token = admin_login.json()["token"]

    username = "custom_fund_manager"
    client.delete(f"/api/admin/users/{username}", headers={"Authorization": f"Bearer {token}"})

    # Admin creates user with a custom password
    create_resp = client.post(
        "/api/admin/users",
        json={
            "username": username,
            "full_name": "Custom Fund Manager",
            "role": "Fund Manager / Portfolio Manager",
            "department": "Equities",
            "email": "custom.manager@amc.com",
            "status": "Active",
            "password": "MyCustomPassword#2026"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["assigned_password"] == "MyCustomPassword#2026"

    # Login with wrong password fails
    wrong_login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "WrongPassword"}
    )
    assert wrong_login.status_code == 401

    # Login with custom password succeeds
    correct_login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "MyCustomPassword#2026"}
    )
    assert correct_login.status_code == 200
    assert correct_login.json()["user"]["username"] == username

    # Clean up
    client.delete(f"/api/admin/users/{username}", headers={"Authorization": f"Bearer {token}"})
