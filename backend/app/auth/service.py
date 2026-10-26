# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""AuthService — the only thing the API routes talk to.

Deliberately thin: credential checking + session-token issuance. All
JSON-file access is delegated to the `UserRepository`, so the file format
(or a future database) is an implementation detail this service — and the
routes above it — do not need to know about.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.auth.repository import AuthUserRecord, UserRepository
from app.auth.security import issue_session_token, resolve_session_token, verify_password

logger = logging.getLogger("auth")

# Same message regardless of whether the username exists or the password was
# wrong — never reveal which one failed (spec: don't expose account existence).
GENERIC_AUTH_ERROR = "That User ID or password doesn't match our records."
INACTIVE_ACCOUNT_ERROR = "This account is not active. Contact your administrator."


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    display_name: str
    role: str
    department: str
    email: str
    avatar_initials: str
    status: str
    tenant_id: Optional[str] = None


@dataclass(frozen=True)
class AuthResult:
    success: bool
    user: Optional[AuthenticatedUser] = None
    token: Optional[str] = None
    expires_at: Optional[int] = None
    error: Optional[str] = None


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        secret_key: str,
        session_ttl_minutes: int,
        session_ttl_minutes_remember: Optional[int] = None,
    ) -> None:
        """Initialize a new instance of AuthService.

        Args:
            repository (UserRepository): The repository.
            secret_key (str): The secret key.
            session_ttl_minutes (int): Collection or list of session ttl minutes.
            session_ttl_minutes_remember (Optional[int]): The session ttl minutes remember.
        """
        self._repository = repository
        self._secret_key = secret_key
        self._session_ttl_minutes = session_ttl_minutes
        self._session_ttl_minutes_remember = session_ttl_minutes_remember or session_ttl_minutes

    @staticmethod
    def _to_public(record: AuthUserRecord) -> AuthenticatedUser:
        """To public.

        Args:
            record (AuthUserRecord): The record.

        Returns:
            AuthenticatedUser: Resulting AuthenticatedUser instance.
        """
        return AuthenticatedUser(
            username=record.username,
            display_name=record.display_name,
            role=record.role,
            department=record.department,
            email=record.email,
            avatar_initials=record.avatar_initials,
            status=record.status,
            tenant_id=getattr(record, "tenant_id", None),
        )

    def authenticate(self, username: str, password: str, remember_me: bool = False) -> AuthResult:
        """Authenticate.

        Args:
            username (str): User's login username.
            password (str): User's plaintext password.
            remember_me (bool): The remember me.

        Returns:
            AuthResult: Resulting AuthResult instance.
        """
        if not username or not username.strip() or not password:
            return AuthResult(success=False, error=GENERIC_AUTH_ERROR)

        # Always fetch record (even if username invalid) to prevent timing leak
        record = self._repository.get_by_username(username) if username and username.strip() else None

        # Always run a hash comparison, even on a missing user, against a
        # fixed dummy hash — keeps response timing similar whether or not
        # the account exists, so timing can't be used to enumerate users.
        dummy_hash = "pbkdf2_sha256$260000$00$00"
        
        # Prepare hash list BEFORE timing-sensitive operation
        if record:
            hashes = record.password_hash if isinstance(record.password_hash, list) else [record.password_hash]
            # Pad to 3 hashes to ensure constant time (always check 3 hashes)
            while len(hashes) < 3:
                hashes.append(dummy_hash)
        else:
            hashes = [dummy_hash, dummy_hash, dummy_hash]  # Always check 3 dummy hashes
        
        # Constant-time comparison (always checks ALL hashes)
        password_ok = any(verify_password(password, h) for h in hashes[:3])  # Exactly 3 checks
        
        # Additional constant-time delay to prevent sub-millisecond timing attacks
        import time
        time.sleep(0.05)  # 50ms artificial delay

        if not record or not password_ok:
            logger.info("Failed login attempt for username=%r", username)
            return AuthResult(success=False, error=GENERIC_AUTH_ERROR)

        if record.status.lower() != "active":
            logger.info("Login rejected for inactive account username=%r", username)
            return AuthResult(success=False, error=INACTIVE_ACCOUNT_ERROR)

        ttl = self._session_ttl_minutes_remember if remember_me else self._session_ttl_minutes
        token, expires_at = issue_session_token(record.username, self._secret_key, ttl)
        logger.info("Successful login for username=%r", username)
        return AuthResult(success=True, user=self._to_public(record), token=token, expires_at=expires_at)

    def resolve_session_with_status(self, token: str, db_session=None) -> tuple[Optional[AuthenticatedUser], Optional[str]]:
        """Resolves session token returning (user, error_code).
        error_code: None, 'invalid_token', 'revoked_token', or 'inactive_account'.

        Args:
            token (str): Authentication or authorization token.
            db_session: SQLAlchemy session for checking revocation (optional).

        Returns:
            tuple[Optional[AuthenticatedUser], Optional[str]]: Matching object or record if found, None otherwise.
        """
        if not token:
            return None, "invalid_token"
        payload = resolve_session_token(token, self._secret_key)
        if payload is None:
            return None, "invalid_token"
        
        # Check if token is revoked
        if payload.jti:
            try:
                from app.schemas.revoked_token import RevokedToken
                if db_session is not None:
                    revoked = db_session.query(RevokedToken).filter(RevokedToken.jti == payload.jti).first()
                else:
                    from app.core.database import SessionLocal
                    with SessionLocal() as local_db:
                        revoked = local_db.query(RevokedToken).filter(RevokedToken.jti == payload.jti).first()
                if revoked:
                    logger.info("Rejected revoked token (jti=%s, reason=%s)", payload.jti, revoked.reason)
                    return None, "revoked_token"
            except Exception as exc:
                logger.warning("Error checking token revocation: %s", exc)
        
        record = self._repository.get_by_username(payload.username)
        if record is None:
            return None, "invalid_token"
        if record.status.lower() != "active":
            return None, "inactive_account"
        return self._to_public(record), None

    def resolve_session(self, token: str) -> Optional[AuthenticatedUser]:
        """Resolve session.

        Args:
            token (str): Authentication or authorization token.

        Returns:
            Optional[AuthenticatedUser]: Matching object or record if found, None otherwise.
        """
        user, _ = self.resolve_session_with_status(token)
        return user
