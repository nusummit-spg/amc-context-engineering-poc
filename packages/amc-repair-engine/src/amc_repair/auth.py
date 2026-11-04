"""
Authentication and authorization for Repair Engine microservice.
Supports both end-user JWT tokens and service-to-service authentication.
"""
import hashlib
import hmac
import json
import logging
import base64
import time
import os
from typing import Optional
from dataclasses import dataclass
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("amc_repair.auth")

# Service token secret - must be shared with main application
SERVICE_SECRET = os.getenv("REPAIR_SERVICE_SECRET", "development-secret-change-in-production")
TOKEN_ALGORITHM = "HS256"

security = HTTPBearer()


@dataclass
class RepairUser:
    """Authenticated principal for repair operations."""
    username: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    roles: list[str] = None
    is_service: bool = False
    service_name: Optional[str] = None
    
    def __post_init__(self):
        if self.roles is None:
            self.roles = []
    
    def has_role(self, role: str) -> bool:
        """Check if user has specific role."""
        return role in self.roles or "admin" in self.roles
    
    def can_approve(self) -> bool:
        """Check if user can approve patches."""
        return self.has_role("reviewer") or self.has_role("admin") or self.is_service
    
    def can_promote(self) -> bool:
        """Check if user can promote patches to production."""
        return self.has_role("admin") or (self.is_service and "patch_promotion" in self.roles)


def _b64url_decode(text: str) -> bytes:
    """Base64 URL decode with padding."""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _b64url_encode(raw: bytes) -> str:
    """Base64 URL encode without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def verify_token_signature(token: str, secret: str) -> Optional[dict]:
    """
    Verify JWT-like token signature and decode payload.
    
    Returns:
        Payload dict if valid, None if invalid or expired
    """
    try:
        payload_b64, signature_b64 = token.split(".")
    except ValueError:
        logger.warning("Invalid token format - must be payload.signature")
        return None
    
    # Verify HMAC signature
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256
    ).digest()
    
    if not hmac.compare_digest(_b64url_encode(expected_sig), signature_b64):
        logger.warning("Token signature verification failed")
        return None
    
    # Decode payload
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to decode token payload")
        return None
    
    # Check expiration
    exp = payload.get("exp")
    if exp and exp < int(time.time()):
        logger.warning("Token expired at %d, current time %d", exp, int(time.time()))
        return None
    
    return payload


def parse_repair_user(payload: dict) -> RepairUser:
    """
    Parse JWT payload into RepairUser object.
    
    Supports both end-user tokens (from main app) and service tokens.
    """
    # Check if this is a service token
    if payload.get("token_type") == "service":
        return RepairUser(
            username=payload.get("service_name", "unknown-service"),
            service_name=payload.get("service_name"),
            is_service=True,
            roles=payload.get("scopes", []),
            tenant_id=payload.get("tenant_id")
        )
    
    # End-user token
    return RepairUser(
        username=payload.get("sub", payload.get("username", "unknown")),
        user_id=payload.get("user_id"),
        tenant_id=payload.get("tenant_id"),
        roles=payload.get("roles", []),
        is_service=False
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> RepairUser:
    """
    FastAPI dependency to extract and verify authenticated user.
    
    Supports:
    - End-user JWT from main application
    - Service-to-service authentication tokens
    
    Raises:
        HTTPException: 401 if token invalid, 403 if insufficient permissions
    """
    token = credentials.credentials
    
    # Try to verify with service secret
    payload = verify_token_signature(token, SERVICE_SECRET)
    
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user = parse_repair_user(payload)
    logger.info(
        "Authenticated %s: %s (tenant=%s, roles=%s)",
        "service" if user.is_service else "user",
        user.username,
        user.tenant_id or "default",
        user.roles
    )
    
    return user


async def require_approver(user: RepairUser = Depends(get_current_user)) -> RepairUser:
    """
    Require user to have approval permissions.
    
    Raises:
        HTTPException: 403 if user cannot approve
    """
    if not user.can_approve():
        raise HTTPException(
            status_code=403,
            detail=f"User {user.username} does not have approval permissions. Required roles: reviewer, admin"
        )
    return user


async def require_promoter(user: RepairUser = Depends(get_current_user)) -> RepairUser:
    """
    Require user to have promotion permissions.
    
    Raises:
        HTTPException: 403 if user cannot promote to production
    """
    if not user.can_promote():
        raise HTTPException(
            status_code=403,
            detail=f"User {user.username} does not have promotion permissions. Required roles: admin"
        )
    return user


def issue_service_token(
    service_name: str,
    scopes: list[str],
    secret: str = SERVICE_SECRET,
    ttl_minutes: int = 60
) -> tuple[str, int]:
    """
    Issue a service-to-service authentication token.
    
    Args:
        service_name: Name of the calling service
        scopes: List of permission scopes (e.g., ["patch_read", "patch_approve"])
        secret: Shared secret for signing
        ttl_minutes: Token validity duration
    
    Returns:
        Tuple of (token_string, expiration_timestamp)
    """
    now = int(time.time())
    exp = now + ttl_minutes * 60
    
    payload = {
        "token_type": "service",
        "service_name": service_name,
        "scopes": scopes,
        "iat": now,
        "exp": exp
    }
    
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    
    signature = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256
    ).digest()
    
    signature_b64 = _b64url_encode(signature)
    token = f"{payload_b64}.{signature_b64}"
    
    logger.info(
        "Issued service token for %s with scopes %s, expires at %d",
        service_name,
        scopes,
        exp
    )
    
    return token, exp
