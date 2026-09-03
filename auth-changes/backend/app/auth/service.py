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
        self._repository = repository
        self._secret_key = secret_key
        self._session_ttl_minutes = session_ttl_minutes
        self._session_ttl_minutes_remember = session_ttl_minutes_remember or session_ttl_minutes

    @staticmethod
    def _to_public(record: AuthUserRecord) -> AuthenticatedUser:
        return AuthenticatedUser(
            username=record.username,
            display_name=record.display_name,
            role=record.role,
            department=record.department,
            email=record.email,
            avatar_initials=record.avatar_initials,
            status=record.status,
        )

    def authenticate(self, username: str, password: str, remember_me: bool = False) -> AuthResult:
        if not username or not username.strip() or not password:
            return AuthResult(success=False, error=GENERIC_AUTH_ERROR)

        record = self._repository.get_by_username(username)

        # Always run a hash comparison, even on a missing user, against a
        # fixed dummy hash — keeps response timing similar whether or not
        # the account exists, so timing can't be used to enumerate users.
        dummy_hash = "pbkdf2_sha256$260000$00$00"
        candidate_hash = record.password_hash if record else dummy_hash
        password_ok = verify_password(password, candidate_hash)

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

    def resolve_session(self, token: str) -> Optional[AuthenticatedUser]:
        if not token:
            return None
        payload = resolve_session_token(token, self._secret_key)
        if payload is None:
            return None
        record = self._repository.get_by_username(payload.username)
        if record is None or record.status.lower() != "active":
            return None
        return self._to_public(record)
