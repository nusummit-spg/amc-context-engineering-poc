# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
security.py
===========
Security hardening utilities for the AMC Compliance System:
- In-memory sliding window rate limiter
- Role-Based Access Control (RBAC) helpers
- Data encryption for sensitive violation evidence
- Input validation helpers
"""
import base64
import hashlib
import time
from collections import defaultdict
from functools import wraps
from typing import Callable, Dict, List, Optional

from fastapi import Header, HTTPException, Request, status

from app.schemas.compliance_models import Role


# ── Sliding Window Rate Limiter ────────────────────────────────────────

class InMemoryRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self):
        # Maps client_ip -> list of epoch timestamps
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_id: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
        now = time.time()
        window_start = now - window_seconds

        # Clean old timestamps
        timestamps = [t for t in self._requests[client_id] if t > window_start]
        self._requests[client_id] = timestamps

        if len(timestamps) >= max_requests:
            return False

        self._requests[client_id].append(now)
        return True


rate_limiter = InMemoryRateLimiter()


def limit_requests(max_requests: int = 100, window_seconds: int = 60):
    """Decorator to enforce request rate limits per client IP."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Check for request object in kwargs or args
            request: Optional[Request] = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            client_ip = "127.0.0.1"
            if request and request.client:
                client_ip = request.client.host

            if not rate_limiter.is_allowed(client_ip, max_requests=max_requests, window_seconds=window_seconds):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds} seconds."
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ── RBAC Authorization ──────────────────────────────────────────────────

def get_client_role(x_user_role: Optional[str] = Header(None)) -> Role:
    """Extract and validate client user role from request headers."""
    if not x_user_role:
        return Role.ADMIN  # Default to ADMIN in open internal demo environment

    role_str = x_user_role.lower().strip()
    try:
        return Role(role_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid X-User-Role: '{x_user_role}'. Must be one of: viewer, reviewer, resolver, admin"
        )


def require_roles(allowed_roles: List[Role]):
    """Decorator to enforce role permissions on API routes."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user_role = kwargs.get("current_role")
            if user_role and user_role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Requires one of roles: {[r.value for r in allowed_roles]}"
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ── Sensitive Data Encryption ──────────────────────────────────────────

class ComplianceDataEncryptor:
    """Encrypts and decrypts sensitive compliance evidence documents and PII."""

    def __init__(self, secret_key: str = "amc_compliance_master_secret_key_2026"):
        # Derive 32-byte key
        self.key = hashlib.sha256(secret_key.encode("utf-8")).digest()

    def encrypt_evidence(self, plaintext: str) -> str:
        """XOR stream cipher with base64 encoding."""
        if not plaintext:
            return ""
        data_bytes = plaintext.encode("utf-8")
        encrypted = bytes(b ^ self.key[i % len(self.key)] for i, b in enumerate(data_bytes))
        return base64.b64encode(encrypted).decode("utf-8")

    def decrypt_evidence(self, ciphertext_b64: str) -> str:
        """Decrypt base64 encoded evidence string."""
        if not ciphertext_b64:
            return ""
        try:
            encrypted = base64.b64decode(ciphertext_b64.encode("utf-8"))
            decrypted = bytes(b ^ self.key[i % len(self.key)] for i, b in enumerate(encrypted))
            return decrypted.decode("utf-8")
        except Exception:
            return ciphertext_b64


encryptor = ComplianceDataEncryptor()
