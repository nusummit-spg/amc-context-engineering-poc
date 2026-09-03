# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""Password hashing and signed session-token helpers.

Deliberately dependency-free (stdlib `hashlib`/`hmac`/`secrets` only) so the
auth module has no extra install footprint. Swappable later for
passlib/bcrypt or a real JWT library without changing callers — every
function here is used through `AuthService`, never called directly by
routes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional

_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 260_000
_SALT_BYTES = 16


def hash_password(plain_password: str, *, salt: Optional[str] = None) -> str:
    """Returns a self-describing hash string: ``pbkdf2_sha256$iterations$salt$hash``.

    Storing the algorithm/iteration count/salt alongside the hash means the
    JSON user file is portable and can be re-verified even if the tuning
    parameters change later.
    """
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGO, plain_password.encode("utf-8"), salt_bytes, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt_bytes.hex()}${derived.hex()}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Constant-time comparison against a `hash_password`-produced string."""
    try:
        algo, iterations_s, salt_hex, hash_hex = stored_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt_bytes = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac(
            _PBKDF2_ALGO, plain_password.encode("utf-8"), salt_bytes, iterations
        )
        return hmac.compare_digest(expected.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


@dataclass(frozen=True)
class SessionTokenPayload:
    username: str
    issued_at: int
    expires_at: int


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def issue_session_token(username: str, secret_key: str, ttl_minutes: int) -> tuple[str, int]:
    """Creates a compact signed token (HMAC-SHA256) carrying username + expiry.

    Returns ``(token, expires_at_epoch_seconds)``. No server-side session
    store is required to validate it, which keeps the demo backend
    stateless; a real deployment can layer a revocation list on top of
    `resolve_session_token` without changing the API contract.
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": username,
        "iat": now,
        "exp": now + ttl_minutes * 60,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret_key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{payload_b64}.{signature_b64}", payload["exp"]


def resolve_session_token(token: str, secret_key: str) -> Optional[SessionTokenPayload]:
    """Verifies signature + expiry; returns the decoded payload or None."""
    try:
        payload_b64, signature_b64 = token.split(".")
    except ValueError:
        return None

    expected_sig = hmac.new(secret_key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_encode(expected_sig), signature_b64):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_b64))
        username = payload["sub"]
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
    except (ValueError, KeyError, TypeError):
        return None

    if expires_at < int(time.time()):
        return None

    return SessionTokenPayload(username=username, issued_at=issued_at, expires_at=expires_at)
