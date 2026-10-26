"""
Verification script for:
1. SessionLocal fix in deps.py & authentication login
2. Admin self-deletion prevention (Bearer token & X-User-ID)
3. Other user management operations (create, delete other user)
4. System & query endpoints
"""
import os
import sys

# Ensure backend root is in sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from starlette.testclient import TestClient
from app.main import app

def main():
    """Main.
    """
    client = TestClient(app)
    print("=" * 60)
    print("1. Testing Auth Login (POST /api/auth/login)")
    print("=" * 60)
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "compliance_officer", "password": "Compliance@2026"}
    )
    print(f"Status: {login_resp.status_code}")
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    auth_data = login_resp.json()
    token = auth_data["token"]
    user = auth_data["user"]
    print(f"Logged in user: {user['username']} ({user['role']})")
    print(f"Token received: {token[:20]}...")

    print("\n" + "=" * 60)
    print("2. Testing Auth Me (GET /api/auth/me)")
    print("=" * 60)
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status: {me_resp.status_code}")
    assert me_resp.status_code == 200
    print(f"Me data: {me_resp.json()}")

    print("\n" + "=" * 60)
    print("3. Testing Admin Self-Deletion Prevention (Backend API)")
    print("=" * 60)
    # Attempt 3a: Self-deletion using Bearer token
    print("Attempting to delete own account using Authorization: Bearer <token>...")
    del_self_token = client.delete(
        f"/api/admin/users/{user['username']}",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status: {del_self_token.status_code}, Detail: {del_self_token.json()}")
    assert del_self_token.status_code == 400
    assert "cannot delete their own account" in del_self_token.json()["detail"].lower()
    print("-> Self-deletion via Bearer token blocked as expected!")

    # Attempt 3b: Self-deletion using X-User-ID header
    print("Attempting to delete own account using X-User-ID header...")
    del_self_header = client.delete(
        f"/api/admin/users/{user['username']}",
        headers={"X-User-ID": user["username"]}
    )
    print(f"Status: {del_self_header.status_code}, Detail: {del_self_header.json()}")
    assert del_self_header.status_code == 400
    assert "cannot delete their own account" in del_self_header.json()["detail"].lower()
    print("-> Self-deletion via X-User-ID header blocked as expected!")

    print("\n" + "=" * 60)
    print("4. Testing Management of Other Users (Create & Delete)")
    print("=" * 60)
    temp_username = "test_analyst_2026"
    print(f"Creating user {temp_username}...")
    create_resp = client.post(
        "/api/admin/users",
        json={
            "username": temp_username,
            "full_name": "Test Analyst 2026",
            "role": "Fund Manager / Portfolio Manager",
            "department": "Research",
            "email": "analyst2026@amc.com",
            "status": "Active"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Create status: {create_resp.status_code}")
    assert create_resp.status_code == 200

    print(f"Deleting user {temp_username} (other user)...")
    del_other_resp = client.delete(
        f"/api/admin/users/{temp_username}",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Delete other user status: {del_other_resp.status_code}, Response: {del_other_resp.json()}")
    assert del_other_resp.status_code == 200
    assert del_other_resp.json()["deleted"] == temp_username
    print("-> Deletion of other user succeeded as expected!")

    print("\n" + "=" * 60)
    print("5. Testing Protected System Users Protection")
    print("=" * 60)
    prot_resp = client.delete(
        "/api/admin/users/sarah_compliance",
        headers={"X-User-ID": "different_admin"}
    )
    print(f"Status: {prot_resp.status_code}, Detail: {prot_resp.json()}")
    assert prot_resp.status_code == 400
    assert "default system users cannot be deleted" in prot_resp.json()["detail"].lower()
    print("-> Protected system user deletion blocked as expected!")

    print("\n" + "=" * 60)
    print("6. Testing Status & RBAC API Endpoints")
    print("=" * 60)
    users_resp = client.get("/api/admin/users")
    print(f"/api/admin/users status: {users_resp.status_code}, total: {users_resp.json().get('total')}")
    assert users_resp.status_code == 200

    rbac_resp = client.get("/api/admin/rbac")
    print(f"/api/admin/rbac status: {rbac_resp.status_code}, total roles: {rbac_resp.json().get('total_roles')}")
    assert rbac_resp.status_code == 200

    audit_resp = client.get("/api/admin/audit")
    print(f"/api/admin/audit status: {audit_resp.status_code}, total logs: {len(audit_resp.json().get('logs', []))}")
    assert audit_resp.status_code == 200

    print("\n" + "=" * 60)
    print("7. Testing Multi-User Authentication & Chat Access Across Personas")
    print("=" * 60)
    test_users = [
        ("compliance_officer", "Compliance@2026"),
        ("sarah.compliance", "Compliance@2026"),
        ("vikram.pm", "Portfolio@2026"),
        ("ananya.esg", "Sustainability@2026"),
        ("rahul.sales", "Distribution@2026"),
        ("priya.investor", "Investor@2026"),
    ]

    for u_name, u_pass in test_users:
        print(f"\n--> Testing Persona: {u_name}")
        # 1. Login
        l_resp = client.post("/api/auth/login", json={"username": u_name, "password": u_pass})
        assert l_resp.status_code == 200, f"Login failed for {u_name}: {l_resp.text}"
        u_token = l_resp.json()["token"]
        auth_hdr = {"Authorization": f"Bearer {u_token}", "X-User-ID": u_name}

        # 2. GET /api/sessions (should be 200, NOT 401)
        sess_resp = client.get("/api/sessions", headers=auth_hdr)
        assert sess_resp.status_code == 200, f"Sessions failed for {u_name}: {sess_resp.status_code}"
        sess_data = sess_resp.json()
        count = len(sess_data) if isinstance(sess_data, list) else len(sess_data.get('sessions', []))
        print(f"    [OK] /api/sessions returned 200 ({count} sessions)")

        # 3. POST /api/chat/title (should be 200, NOT 401)
        title_resp = client.post(
            "/api/chat/title",
            json={"query": "What are the SEBI regulations for large cap funds?"},
            headers=auth_hdr
        )
        assert title_resp.status_code == 200, f"Chat title failed for {u_name}: {title_resp.status_code}"
        print(f"    [OK] /api/chat/title returned 200: {title_resp.json().get('title')}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY ACROSS ALL USER PERSONAS!")
    print("=" * 60)

if __name__ == "__main__":
    main()
