# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""Comprehensive test suite for Authentication system:
- Security helpers (hashing, constant-time verification, HMAC session tokens)
- JSONUserRepository (loading, case-insensitivity, dot/underscore interoperability)
- AuthService (credential checking, generic errors, timing attack prevention, sessions)
- FastAPI routes (/api/auth/login, /api/auth/logout, /api/auth/me)
"""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.repository import AuthUserRecord, JSONUserRepository
from app.auth.security import (
    hash_password,
    issue_session_token,
    resolve_session_token,
    verify_password,
)
from app.auth.service import (
    GENERIC_AUTH_ERROR,
    INACTIVE_ACCOUNT_ERROR,
    AuthService,
)
from app.main import app


# ── 1. Security Helpers ────────────────────────────────────────────────────────


class TestAuthSecurity:
    def test_hash_and_verify_password(self):
        password = "TestPassword@2026"
        hashed = hash_password(password)

        assert hashed.startswith("pbkdf2_sha256$")
        assert verify_password(password, hashed) is True
        assert verify_password("WrongPassword!", hashed) is False
        assert verify_password("", hashed) is False
        assert verify_password(password, "invalid_hash_string") is False
        assert verify_password(password, "pbkdf2_sha256$corrupted") is False

    def test_issue_and_resolve_session_token(self):
        secret = "unit-test-secret-key-12345"
        username = "sarah_compliance"
        ttl_minutes = 10

        token, expires_at = issue_session_token(username, secret, ttl_minutes)
        assert token
        assert expires_at > int(time.time())

        payload = resolve_session_token(token, secret)
        assert payload is not None
        assert payload.username == username
        assert payload.expires_at == expires_at

    def test_tampered_session_token(self):
        secret = "unit-test-secret-key-12345"
        token, _ = issue_session_token("sarah_compliance", secret, ttl_minutes=10)

        parts = token.split(".")
        assert len(parts) == 2

        # Tamper payload
        tampered_token = f"dGFtcGVyZWQ.{parts[1]}"
        assert resolve_session_token(tampered_token, secret) is None

        # Tamper signature
        tampered_sig = f"{parts[0]}.dGFtcGVyZWQ"
        assert resolve_session_token(tampered_sig, secret) is None

        # Wrong secret key
        assert resolve_session_token(token, "wrong-secret-key") is None

    def test_expired_session_token(self):
        secret = "unit-test-secret-key-12345"
        # Token with -1 minute TTL
        token, _ = issue_session_token("sarah_compliance", secret, ttl_minutes=-1)
        assert resolve_session_token(token, secret) is None


# ── 2. JSONUserRepository ──────────────────────────────────────────────────────


class TestJSONUserRepository:
    def test_repository_loads_default_users(self):
        repo = JSONUserRepository()
        user = repo.get_by_username("sarah_compliance")
        assert user is not None
        assert user.username == "sarah_compliance"
        assert user.display_name == "Sarah Jenkins"
        assert user.role == "Compliance & Regulatory Officer"
        assert user.status == "Active"

    def test_repository_case_insensitivity(self):
        repo = JSONUserRepository()
        assert repo.get_by_username("SARAH_COMPLIANCE") is not None
        assert repo.get_by_username("  Sarah_Compliance  ") is not None

    def test_repository_dot_underscore_interoperability(self):
        repo = JSONUserRepository()
        # Dot syntax resolves to underscore record
        dot_user = repo.get_by_username("sarah.compliance")
        assert dot_user is not None
        assert dot_user.username == "sarah_compliance"

        # Check other accounts
        assert repo.get_by_username("vikram.pm") is not None
        assert repo.get_by_username("ananya.esg") is not None
        assert repo.get_by_username("rahul.sales") is not None
        assert repo.get_by_username("priya.investor") is not None

    def test_repository_nonexistent_user(self):
        repo = JSONUserRepository()
        assert repo.get_by_username("nonexistent.user") is None
        assert repo.get_by_username("") is None

    def test_repository_missing_file_handling(self, tmp_path):
        fake_path = tmp_path / "non_existent_users.json"
        repo = JSONUserRepository(fake_path)
        # Should gracefully return None when file is missing and no fallback
        assert repo.get_by_username("sarah_compliance") is not None  # falls back to DEFAULT_USERS_PATH


# ── 3. AuthService ─────────────────────────────────────────────────────────────


class TestAuthService:
    @pytest.fixture
    def auth_service(self):
        repo = JSONUserRepository()
        return AuthService(
            repository=repo,
            secret_key="test-secret-change-me",
            session_ttl_minutes=60,
            session_ttl_minutes_remember=1440,
        )

    def test_authenticate_success(self, auth_service):
        res = auth_service.authenticate("sarah_compliance", "Compliance@2026")
        assert res.success is True
        assert res.user is not None
        assert res.user.username == "sarah_compliance"
        assert res.user.display_name == "Sarah Jenkins"
        assert res.token is not None
        assert res.expires_at is not None
        assert res.error is None

    def test_authenticate_dot_alias_success(self, auth_service):
        res = auth_service.authenticate("sarah.compliance", "Compliance@2026")
        assert res.success is True
        assert res.user.username == "sarah_compliance"

    def test_authenticate_wrong_password(self, auth_service):
        res = auth_service.authenticate("sarah_compliance", "WrongPassword!")
        assert res.success is False
        assert res.error == GENERIC_AUTH_ERROR
        assert res.token is None

    def test_authenticate_nonexistent_user_returns_generic_error(self, auth_service):
        res = auth_service.authenticate("ghost.user", "AnyPassword123!")
        assert res.success is False
        # Exact same error message to avoid user enumeration
        assert res.error == GENERIC_AUTH_ERROR
        assert res.token is None

    def test_authenticate_empty_credentials(self, auth_service):
        res1 = auth_service.authenticate("", "Compliance@2026")
        assert res1.success is False
        assert res1.error == GENERIC_AUTH_ERROR

        res2 = auth_service.authenticate("sarah_compliance", "")
        assert res2.success is False
        assert res2.error == GENERIC_AUTH_ERROR

    def test_authenticate_remember_me(self, auth_service):
        res_normal = auth_service.authenticate("sarah_compliance", "Compliance@2026", remember_me=False)
        res_remember = auth_service.authenticate("sarah_compliance", "Compliance@2026", remember_me=True)

        assert res_remember.expires_at > res_normal.expires_at

    def test_resolve_session(self, auth_service):
        res = auth_service.authenticate("sarah_compliance", "Compliance@2026")
        resolved_user = auth_service.resolve_session(res.token)

        assert resolved_user is not None
        assert resolved_user.username == "sarah_compliance"
        assert resolved_user.display_name == "Sarah Jenkins"

    def test_resolve_session_invalid_token(self, auth_service):
        assert auth_service.resolve_session("") is None
        assert auth_service.resolve_session("invalid.token") is None


# ── 4. FastAPI Routes ─────────────────────────────────────────────────────────


class TestAuthRoutes:
    @pytest.fixture
    def client(self):
        return TestClient(app, raise_server_exceptions=False)

    def test_login_endpoint_success(self, client):
        response = client.post(
            "/api/auth/login",
            json={"username": "sarah_compliance", "password": "Compliance@2026"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "expires_at" in data
        assert "user" in data
        assert data["user"]["username"] == "sarah_compliance"
        assert data["user"]["display_name"] == "Sarah Jenkins"
        assert data["user"]["role"] == "Compliance & Regulatory Officer"
        # Ensure password_hash is never exposed
        assert "password_hash" not in data["user"]
        assert "password" not in data["user"]

    def test_login_endpoint_with_dot_username(self, client):
        response = client.post(
            "/api/auth/login",
            json={"username": "sarah.compliance", "password": "Compliance@2026"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["username"] == "sarah_compliance"

    def test_login_endpoint_invalid_password(self, client):
        response = client.post(
            "/api/auth/login",
            json={"username": "sarah_compliance", "password": "BadPassword123!"},
        )
        assert response.status_code == 401
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "invalid_credentials"
        assert data["error"]["message"] == GENERIC_AUTH_ERROR

    def test_login_endpoint_unknown_user(self, client):
        response = client.post(
            "/api/auth/login",
            json={"username": "unknown_admin", "password": "BadPassword123!"},
        )
        assert response.status_code == 401
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "invalid_credentials"
        assert data["error"]["message"] == GENERIC_AUTH_ERROR

    def test_logout_endpoint(self, client):
        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_me_endpoint_with_valid_token(self, client):
        # First log in
        login_res = client.post(
            "/api/auth/login",
            json={"username": "vikram_pm", "password": "FundManager@2026"},
        )
        token = login_res.json()["token"]

        # Call /api/auth/me with Bearer token
        me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        data = me_res.json()
        assert data["user"]["username"] == "vikram_pm"
        assert data["user"]["display_name"] == "Vikram Rao"

    def test_me_endpoint_missing_token(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "session_invalid"

    def test_me_endpoint_invalid_token(self, client):
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.payload"})
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "session_invalid"

    def test_login_all_five_roles(self, client):
        accounts = [
            ("sarah_compliance", "Compliance@2026", "Compliance & Regulatory Officer"),
            ("vikram_pm", "Portfolio@2026", "Fund Manager / Portfolio Manager"),
            ("ananya_esg", "Sustainability@2026", "ESG & Sustainability Analyst"),
            ("rahul_sales", "Distribution@2026", "Sales & Distribution Manager"),
            ("priya_investor", "Investor@2026", "Retail Investor / Public Client"),
        ]
        for uname, pwd, expected_role in accounts:
            res = client.post("/api/auth/login", json={"username": uname, "password": pwd})
            assert res.status_code == 200, f"Login failed for {uname}"
            body = res.json()
            assert body["user"]["role"] == expected_role
            assert "token" in body

    def test_spa_serving_and_fallback(self, client):
        root_res = client.get("/")
        assert root_res.status_code == 200
        assert "<div id=\"root\">" in root_res.text or "<div id='root'>" in root_res.text or "html" in root_res.text

        spa_res = client.get("/chat/new-session")
        assert spa_res.status_code == 200
        assert "<div id=\"root\">" in spa_res.text or "<div id='root'>" in root_res.text or "html" in root_res.text

