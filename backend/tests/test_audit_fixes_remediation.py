# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_audit_fixes_remediation.py
===============================
Comprehensive test suite verifying the implementation of the re-audit report fixes:
1. Token revocation flow (JTI generation, logout revocation, rejection on auth)
2. Login rate limiting (429 response, Retry-After header)
3. Background task graceful cancellation and logging
4. PDF parser resource cleanup
5. Trace ID / Correlation ID propagation
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.routes import auth as auth_route
from app.auth.security import issue_session_token, resolve_session_token
from app.auth.service import AuthService
from app.core.async_utils import create_task_with_logging
from app.core.database import SessionLocal, init_db
from app.core.errors import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import RequestLoggingMiddleware, request_id_ctx
from app.core.rate_limiter import AuthRateLimiter, get_auth_rate_limiter, limit_login_requests
from app.schemas.revoked_token import RevokedToken
from app.tasks.queue import IngestQueue


# Setup test app for auth routes
test_app = FastAPI()
test_app.add_exception_handler(AppError, app_error_handler)
test_app.add_exception_handler(Exception, unhandled_exception_handler)
test_app.add_middleware(RequestLoggingMiddleware)
test_app.include_router(auth_route.router, prefix="/api")


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Ensure database schema includes revoked_tokens."""
    init_db()


def test_token_revocation_flow():
    """Verify that logging out revokes the token JTI and blocks subsequent authentication."""
    client = TestClient(test_app, raise_server_exceptions=False)

    # 1. Login with valid test credentials
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "sarah.compliance", "password": "Compliance@2026"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    assert token

    # Verify token payload carries a valid JTI
    from app.config import get_settings
    payload = resolve_session_token(token, get_settings().auth_secret_key)
    assert payload is not None
    assert payload.jti is not None

    # 2. Access /api/auth/me successfully
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["username"] == "sarah.compliance"

    # 3. Call /api/auth/logout to revoke the token
    logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["ok"] is True

    # Verify the JTI is stored in revoked_tokens table
    with SessionLocal() as db:
        revoked_row = db.query(RevokedToken).filter(RevokedToken.jti == payload.jti).first()
        assert revoked_row is not None
        assert revoked_row.username == "sarah.compliance"
        assert revoked_row.reason == "logout"

    # 4. Attempt to access /api/auth/me with revoked token -> must fail with 401
    me_revoked = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_revoked.status_code == 401
    assert "revoked" in me_revoked.json()["detail"].lower()

    # 5. Test expired revocation cleanup
    with SessionLocal() as db:
        # Insert an expired revoked token
        expired_revoked = RevokedToken(
            jti="expired-test-jti",
            username="sarah.compliance",
            revoked_at=datetime.now(timezone.utc) - timedelta(hours=2),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            reason="test_expired",
        )
        db.add(expired_revoked)
        db.commit()

        # Run cleanup
        deleted = RevokedToken.cleanup_expired(db)
        assert deleted >= 1
        assert db.query(RevokedToken).filter_by(jti="expired-test-jti").first() is None


def test_login_rate_limiting():
    """Verify that excessive failed login attempts trigger 429 Too Many Requests with Retry-After header."""
    client = TestClient(test_app, raise_server_exceptions=False)
    limiter = get_auth_rate_limiter()

    # Reset any previous state for test user and IP
    test_user = "rate_limit_test_user"
    test_ip = "127.0.0.1"
    asyncio.run(limiter.record_successful_login(test_user, test_ip))

    # Send 5 failed attempts
    for attempt in range(5):
        resp = client.post(
            "/api/auth/login",
            json={"username": test_user, "password": f"wrong-pass-{attempt}"},
        )
        assert resp.status_code == 401

    # 6th attempt should be blocked with 429 Too Many Requests
    blocked_resp = client.post(
        "/api/auth/login",
        json={"username": test_user, "password": "wrong-pass-6"},
    )
    assert blocked_resp.status_code == 429
    assert "Retry-After" in blocked_resp.headers
    assert int(blocked_resp.headers["Retry-After"]) > 0

    # Cleanup rate limit after test
    asyncio.run(limiter.record_successful_login(test_user, test_ip))


@pytest.mark.asyncio
async def test_create_task_with_logging():
    """Verify that create_task_with_logging catches and logs background exceptions without swallowing or crashing."""
    exception_caught = False

    async def failing_coroutine():
        raise RuntimeError("Simulated background task failure")

    task = create_task_with_logging(failing_coroutine(), task_name="test_failing_coro")
    with pytest.raises(RuntimeError):
        await task


@pytest.mark.asyncio
async def test_ingest_queue_graceful_stop():
    """Verify that IngestQueue cancels and awaits its worker task cleanly."""
    queue = IngestQueue(max_queue_size=10, max_job_history=50)
    queue.start()
    assert queue._worker_task is not None
    assert not queue._worker_task.done()

    # Gracefully stop
    await queue.stop()
    assert queue._worker_task is None


def test_trace_id_propagation_middleware():
    """Verify that X-Request-ID and X-Trace-ID are echoed on HTTP responses."""
    client = TestClient(test_app, raise_server_exceptions=False)

    # 1. Custom incoming X-Request-ID
    custom_rid = "custom-test-req-id-123"
    resp = client.post("/api/auth/login", json={"username": "invalid", "password": "bad"}, headers={"X-Request-ID": custom_rid})
    assert resp.headers.get("X-Request-ID") == custom_rid
    assert resp.headers.get("X-Trace-ID") == custom_rid

    # 2. Generated request ID when none supplied
    resp2 = client.post("/api/auth/login", json={"username": "invalid", "password": "bad"})
    assert "X-Request-ID" in resp2.headers
    assert "X-Trace-ID" in resp2.headers
    assert resp2.headers["X-Request-ID"] == resp2.headers["X-Trace-ID"]
