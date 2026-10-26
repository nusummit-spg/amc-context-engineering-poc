# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
Rate Limiter — Simple in-memory rate limiting for authentication endpoints.

Implements sliding window rate limiting with automatic cleanup of expired entries.
"""
import asyncio
import time
import logging
import threading
from collections import defaultdict
from functools import wraps
from typing import Dict, List, Optional
from fastapi import HTTPException, Request, status

logger = logging.getLogger("app.core.rate_limiter")


class AuthRateLimiter:
    """Rate limiter specifically designed for authentication endpoints."""
    
    def __init__(self):
        """Initialize rate limiter with in-memory storage."""
        self._login_attempts: Dict[str, List[float]] = defaultdict(list)
        self._lockouts: Dict[str, float] = {}  # username:ip or ip:ip -> unlock_time
        self._lock = asyncio.Lock()
    
    def _get_key(self, username: str, client_ip: str) -> str:
        """Generate rate limit key combining username and IP."""
        return f"{username}:{client_ip}"
    
    async def check_login_allowed(
        self, 
        username: str, 
        client_ip: str,
        max_attempts: int = 5,
        window_seconds: int = 900,  # 15 minutes default
        max_ip_attempts: int = 20,
    ) -> tuple[bool, Optional[str], int]:
        """Check if login attempt is allowed under rate limit.
        
        Args:
            username: Username attempting login
            client_ip: Client IP address
            max_attempts: Maximum attempts allowed in window per user+IP
            window_seconds: Time window in seconds
            max_ip_attempts: Maximum total attempts allowed per IP across all users
            
        Returns:
            tuple[bool, Optional[str], int]: (allowed, error_message, retry_after_seconds)
        """
        now = time.time()
        user_key = self._get_key(username, client_ip)
        ip_key = f"ip:{client_ip}"
        
        async with self._lock:
            # 1. Check IP-level lockout
            if ip_key in self._lockouts:
                unlock_time = self._lockouts[ip_key]
                if now < unlock_time:
                    remaining = int(unlock_time - now) + 1
                    return False, f"Too many requests from this network. Try again in {remaining} seconds.", remaining
                else:
                    del self._lockouts[ip_key]

            # 2. Check User+IP lockout
            if user_key in self._lockouts:
                unlock_time = self._lockouts[user_key]
                if now < unlock_time:
                    remaining = int(unlock_time - now) + 1
                    return False, f"Account temporarily locked due to failed attempts. Try again in {remaining} seconds.", remaining
                else:
                    del self._lockouts[user_key]
            
            # Clean old attempts (outside window)
            self._login_attempts[user_key] = [
                t for t in self._login_attempts[user_key] 
                if now - t < window_seconds
            ]
            self._login_attempts[ip_key] = [
                t for t in self._login_attempts[ip_key] 
                if now - t < window_seconds
            ]
            
            # Check user+IP attempt rate
            user_attempts = self._login_attempts[user_key]
            if len(user_attempts) >= max_attempts:
                self._lockouts[user_key] = now + window_seconds
                logger.warning(
                    "Login rate limit exceeded for username=%s from IP=%s (%d attempts)",
                    username,
                    client_ip,
                    len(user_attempts)
                )
                return False, f"Too many failed login attempts. Account locked for {window_seconds // 60} minutes.", window_seconds
            
            # Check IP-wide attempt rate (prevents credential spraying)
            ip_attempts = self._login_attempts[ip_key]
            if len(ip_attempts) >= max_ip_attempts:
                self._lockouts[ip_key] = now + window_seconds
                logger.warning(
                    "IP-wide login rate limit exceeded from IP=%s (%d attempts across accounts)",
                    client_ip,
                    len(ip_attempts)
                )
                return False, f"Too many failed login attempts from this network. Try again in {window_seconds // 60} minutes.", window_seconds

            # Record this attempt
            self._login_attempts[user_key].append(now)
            self._login_attempts[ip_key].append(now)
            return True, None, 0
    
    async def record_successful_login(self, username: str, client_ip: str):
        """Clear rate limit counter on successful login.
        
        Args:
            username: Username that logged in successfully
            client_ip: Client IP address
        """
        user_key = self._get_key(username, client_ip)
        async with self._lock:
            if user_key in self._login_attempts:
                del self._login_attempts[user_key]
            if user_key in self._lockouts:
                del self._lockouts[user_key]
    
    async def cleanup_expired(self):
        """Remove expired lockouts and old attempts (background task)."""
        now = time.time()
        async with self._lock:
            # Remove expired lockouts
            expired_lockouts = [k for k, t in self._lockouts.items() if t < now]
            for k in expired_lockouts:
                del self._lockouts[k]
            
            # Remove attempt lists with no recent attempts (older than 1 hour)
            expired_attempts = [
                k for k, attempts in self._login_attempts.items()
                if not attempts or (now - max(attempts) > 3600)
            ]
            for k in expired_attempts:
                del self._login_attempts[k]
            
            if expired_lockouts or expired_attempts:
                logger.debug(
                    "Cleaned up %d expired lockouts and %d stale attempt lists",
                    len(expired_lockouts),
                    len(expired_attempts)
                )


# Global rate limiter instance
_auth_limiter = AuthRateLimiter()


def get_auth_rate_limiter() -> AuthRateLimiter:
    """Get the global auth rate limiter instance.
    
    Returns:
        AuthRateLimiter: Global rate limiter
    """
    return _auth_limiter


async def limit_login_requests(
    request: Request,
    username: str,
    max_attempts: int = 5,
    window_seconds: int = 900
) -> None:
    """FastAPI dependency or helper to enforce login rate limiting.

    Args:
        request: FastAPI request object
        username: Username attempting login
        max_attempts: Maximum attempts in window
        window_seconds: Time window in seconds

    Raises:
        HTTPException: 429 if rate limit exceeded (with Retry-After header)
    """
    client_ip = request.client.host if request.client else "unknown"
    limiter = get_auth_rate_limiter()

    allowed, error, retry_after = await limiter.check_login_allowed(
        username, 
        client_ip,
        max_attempts,
        window_seconds
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error or "Too many requests",
            headers={"Retry-After": str(retry_after or window_seconds)}
        )


def limit_requests(max_requests: int = 5, window_seconds: int = 60):
    """Decorator to enforce rate limiting on async endpoint functions.

    Usage:
        @router.post("/login")
        @limit_requests(max_requests=5, window_seconds=60)
        async def login(payload: LoginRequest, request: Request, ...): ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            payload = kwargs.get("payload")
            username = getattr(payload, "username", "anonymous") if payload else "anonymous"
            if request:
                await limit_login_requests(
                    request=request,
                    username=username,
                    max_attempts=max_requests,
                    window_seconds=window_seconds,
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class IPRateLimiter:
    """Sliding window rate limiter for client IP addresses."""

    def __init__(self, max_requests: int = 120, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            timestamps = [t for t in self._requests[client_ip] if now - t < self.window_seconds]
            if len(timestamps) >= self.max_requests:
                self._requests[client_ip] = timestamps
                return False, 0
            timestamps.append(now)
            self._requests[client_ip] = timestamps
            remaining = self.max_requests - len(timestamps)
            return True, remaining


_ip_limiter = IPRateLimiter()


def get_ip_rate_limiter() -> IPRateLimiter:
    """Return the global IP rate limiter singleton."""
    return _ip_limiter


TIER_QUOTAS = {
    "free": 100,
    "standard": 500,
    "pro": 2000,
    "enterprise": 10000,
    "admin": 100000,
}

_user_quotas: Dict[str, List[float]] = defaultdict(list)
_quota_lock = threading.Lock()


def check_user_quota(user_id: str, tier: str = "free") -> tuple[bool, str]:
    """Check whether a user has exceeded their hourly quota based on tier.

    Returns:
        tuple[bool, str]: (is_allowed, error_message)
    """
    now = time.time()
    tier_limit = TIER_QUOTAS.get((tier or "free").lower(), 100)
    window = 3600  # 1 hour window

    with _quota_lock:
        timestamps = [t for t in _user_quotas[user_id] if now - t < window]
        if len(timestamps) >= tier_limit:
            _user_quotas[user_id] = timestamps
            return False, f"Hourly query quota of {tier_limit} requests exceeded for tier '{tier}'."
        timestamps.append(now)
        _user_quotas[user_id] = timestamps
        return True, ""
