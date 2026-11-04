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

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import get_auth_service
from app.auth.service import AuthResult, AuthService
from app.core.errors import AppError
from app.core.rate_limiter import limit_login_requests, get_auth_rate_limiter, limit_requests
from app.models.auth import LoginRequest, LoginResponse, MeResponse, UserPublic

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
    """Extract bearer token.

    Args:
        authorization (str | None): The authorization.

    Returns:
        str | None: Resulting str | None instance.
    """
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service)
) -> LoginResponse:
    """Authenticate user credentials and issue authentication token.

    Args:
        payload (LoginRequest): Request or event payload.
        request (Request): FastAPI request object.
        auth_service (AuthService): The auth service.

    Returns:
        LoginResponse: LoginResponse object containing the operation result.
    """
    # Apply rate limiting before authentication
    await limit_login_requests(request, payload.username, max_attempts=5, window_seconds=900)
    
    result: AuthResult = auth_service.authenticate(payload.username, payload.password, payload.remember_me)

    if not result.success:
        # Same generic message + same status code whether the username
        # doesn't exist or the password was wrong — never reveal which.
        if result.error and "not active" in result.error:
            raise AccountInactiveError(result.error)
        raise InvalidCredentialsError(result.error or "Authentication failed.")

    # Clear rate limit on successful login
    client_ip = request.client.host if request.client else "unknown"
    limiter = get_auth_rate_limiter()
    await limiter.record_successful_login(payload.username, client_ip)
    
    assert result.token is not None
    assert result.expires_at is not None
    return LoginResponse(
        token=result.token,
        expires_at=result.expires_at,
        user=UserPublic(**result.user.__dict__),
    )


@router.post("/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    """Log out current user and invalidate active session by revoking the token.

    Args:
        request (Request): The incoming request.
        authorization (str | None): Authorization header containing bearer token.
        auth_service (AuthService): The auth service.

    Returns:
        dict: Dictionary containing result data or status.
    """
    from app.core.database import SessionLocal
    from app.schemas.revoked_token import RevokedToken
    from app.auth.security import resolve_session_token
    from app.config import get_settings
    from datetime import datetime, timezone

    token = _extract_bearer_token(authorization)
    if not token:
        return {"ok": True, "message": "No active session to logout"}

    db = SessionLocal()
    try:
        # Decode token to extract JTI and expiration
        payload = resolve_session_token(token, get_settings().auth_secret_key)
        if not payload or not payload.jti:
            # Old token without JTI or invalid token
            return {"ok": True, "message": "Token invalidated client-side"}

        client_ip = request.client.host if request and request.client else None

        # Add to revocation table
        revoked = RevokedToken(
            jti=payload.jti,
            username=payload.username,
            revoked_at=datetime.now(timezone.utc),
            expires_at=datetime.fromtimestamp(payload.expires_at, tz=timezone.utc),
            reason="logout",
            revoked_by_ip=client_ip,
        )
        db.add(revoked)
        db.commit()
        logger.info("Token revoked for username=%s (jti=%s, ip=%s)", payload.username, payload.jti, client_ip)

        return {"ok": True, "message": "Successfully logged out"}
    except Exception as exc:
        db.rollback()
        logger.warning("Could not revoke token: %s", exc)
        return {"ok": True, "message": "Logged out (server-side revocation failed)"}
    finally:
        db.close()


@router.get("/me", response_model=MeResponse)
async def me(
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> MeResponse:
    """Retrieve me.

    Args:
        authorization (str | None): The authorization.
        auth_service (AuthService): The auth service.

    Returns:
        MeResponse: MeResponse object containing the operation result.
    """
    token = _extract_bearer_token(authorization)
    if not token:
        raise SessionInvalidError("Session is missing, invalid, or has expired.")

    user, error = auth_service.resolve_session_with_status(token)
    if error == "revoked_token":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if error == "inactive_account":
        raise AccountInactiveError("User account is inactive")
    if user is None:
        raise SessionInvalidError("Session is missing, invalid, or has expired.")

    return MeResponse(user=UserPublic(**user.__dict__))


# ── Secure Enrollment ────────────────────────────────────────────────────────

class AcceptInvitationRequest(BaseModel):
    """Request to accept invitation and set initial password."""
    invitation_token: str = Field(..., min_length=32)
    password: str = Field(..., min_length=12, max_length=256)


class AcceptInvitationResponse(BaseModel):
    """Response after accepting invitation."""
    success: bool
    message: str
    username: str | None = None


@router.post("/accept-invitation", response_model=AcceptInvitationResponse)
async def accept_invitation(
    payload: AcceptInvitationRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> AcceptInvitationResponse:
    """Accept invitation and set initial password (SEC-03 fix).
    
    Args:
        payload: Invitation acceptance request
        request: FastAPI request object  
        auth_service: Authentication service
    
    Returns:
        Acceptance status
        
    Raises:
        HTTPException(400): If token invalid or expired
        HTTPException(409): If token already used
    """
    from app.core.database import SessionLocal
    from app.schemas.invitation_token import InvitationToken
    from app.schemas.auth_users_table import AuthUser
    from app.auth.security import hash_password
    from datetime import datetime, timezone
    
    db = SessionLocal()
    try:
        # Find invitation token
        invitation = db.query(InvitationToken).filter(
            InvitationToken.token == payload.invitation_token
        ).first()
        
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invitation token"
            )
        
        # Check if already used
        if invitation.used:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Invitation token has already been used"
            )
        
        # Check expiration
        if datetime.now(timezone.utc) > invitation.expires_at.replace(tzinfo=timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation token has expired"
            )
        
        # Validate password strength
        if len(payload.password) < 12:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 12 characters"
            )
        
        # Find user
        user = db.query(AuthUser).filter(AuthUser.username == invitation.username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User account not found"
            )
        
        # Set password and activate
        user.password_hash = hash_password(payload.password)
        user.status = "Active"
        user.updated_at = datetime.now(timezone.utc)
        
        # Mark invitation as used
        client_ip = request.client.host if request.client else None
        invitation.used = True
        invitation.used_at = datetime.now(timezone.utc)
        invitation.used_from_ip = client_ip
        
        db.commit()
        
        logger.info(
            "Invitation accepted: username=%s, ip=%s",
            invitation.username, client_ip
        )
        
        return AcceptInvitationResponse(
            success=True,
            message="Account activated successfully. You can now log in.",
            username=invitation.username
        )
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error("Failed to accept invitation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process invitation"
        )
    finally:
        db.close()

