# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""Authentication API routes: /api/auth/login, /api/auth/logout, /api/auth/me.

Thin HTTP layer only — all credential checking and token handling lives in
`AuthService` (app/auth/service.py). Routes never touch the JSON file or a
password hash directly.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header

from app.api.deps import get_auth_service
from app.auth.service import AuthResult, AuthService
from app.core.errors import AppError
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, UserPublic

logger = logging.getLogger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])


class InvalidCredentialsError(AppError):
    status_code = 401
    error_code = "invalid_credentials"


class AccountInactiveError(AppError):
    status_code = 403
    error_code = "account_inactive"


class SessionInvalidError(AppError):
    status_code = 401
    error_code = "session_invalid"


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, auth_service: AuthService = Depends(get_auth_service)) -> LoginResponse:
    result: AuthResult = auth_service.authenticate(payload.username, payload.password, payload.remember_me)

    if not result.success:
        # Same generic message + same status code whether the username
        # doesn't exist or the password was wrong — never reveal which.
        if result.error and "not active" in result.error:
            raise AccountInactiveError(result.error)
        raise InvalidCredentialsError(result.error or "Authentication failed.")

    return LoginResponse(
        token=result.token,
        expires_at=result.expires_at,
        user=UserPublic(**result.user.__dict__),
    )


@router.post("/logout")
async def logout() -> dict:
    # Tokens are stateless (signed + self-expiring), so there is nothing to
    # invalidate server-side today; the frontend discards the token. This
    # endpoint exists so the frontend has one stable place to call, and so a
    # future server-side revocation list can be added here transparently.
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> MeResponse:
    token = _extract_bearer_token(authorization)
    user = auth_service.resolve_session(token) if token else None
    if user is None:
        raise SessionInvalidError("Session is missing, invalid, or has expired.")
    return MeResponse(user=UserPublic(**user.__dict__))
