# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
Invitation Token Security Module

Wave 1.3 A05 (C-14) Implementation:
- HMAC-SHA256 hashing of invitation tokens
- Constant-time comparison to prevent timing attacks
- Atomic single-use enforcement
- Rate limiting support

Security Requirements:
- Never store plaintext tokens
- Never return plaintext tokens after initial creation
- Use constant-time comparison
- Atomic database operations for redemption
- Rate limiting on failed attempts
"""

import hmac
import hashlib
import secrets
import os
from typing import Optional, Tuple
from datetime import datetime, timezone

# A05: Server secret for token hashing
# In production, must be strong and consistent across app instances
INVITATION_SECRET = os.getenv("INVITATION_TOKEN_SECRET", os.getenv("JWT_SECRET", "change-this-secret"))

# A05: Rate limiting configuration
MAX_REDEMPTION_ATTEMPTS = int(os.getenv("MAX_INVITATION_ATTEMPTS", "5"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("INVITATION_RATE_LIMIT_SECONDS", "300"))  # 5 minutes


def generate_invitation_token() -> str:
    """Generate cryptographically secure invitation token.
    
    A05: Generates 32-byte (256-bit) URL-safe token.
    The plaintext token is returned to the admin ONCE and never stored.
    
    Returns:
        URL-safe base64 encoded token (43 characters)
    """
    return secrets.token_urlsafe(32)


def hash_invitation_token(plaintext_token: str) -> str:
    """Hash invitation token using HMAC-SHA256.
    
    A05: Creates keyed hash of token using server secret.
    This hash is stored in the database, NOT the plaintext token.
    
    Args:
        plaintext_token: The plaintext invitation token
    
    Returns:
        Hex-encoded HMAC-SHA256 hash (64 characters)
    """
    return hmac.new(
        INVITATION_SECRET.encode('utf-8'),
        plaintext_token.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def verify_invitation_token(plaintext_token: str, stored_hash: str) -> bool:
    """Verify invitation token using constant-time comparison.
    
    A05: Prevents timing attacks by using hmac.compare_digest.
    
    Args:
        plaintext_token: Token provided by user
        stored_hash: Hash stored in database
    
    Returns:
        True if token matches hash, False otherwise
    """
    computed_hash = hash_invitation_token(plaintext_token)
    return hmac.compare_digest(computed_hash, stored_hash)


def check_rate_limit(attempts: int, last_attempt: Optional[datetime]) -> Tuple[bool, Optional[str]]:
    """Check if invitation redemption is rate limited.
    
    A05: Prevents brute force attacks on invitation tokens.
    
    Args:
        attempts: Number of failed redemption attempts
        last_attempt: Timestamp of last attempt
    
    Returns:
        Tuple of (allowed: bool, reason: Optional[str])
    """
    if attempts >= MAX_REDEMPTION_ATTEMPTS:
        if last_attempt:
            elapsed = (datetime.now(timezone.utc) - last_attempt.replace(tzinfo=timezone.utc)).total_seconds()
            if elapsed < RATE_LIMIT_WINDOW_SECONDS:
                remaining = int(RATE_LIMIT_WINDOW_SECONDS - elapsed)
                return False, f"Too many failed attempts. Try again in {remaining} seconds."
        # If window passed, reset is allowed
    
    return True, None


def create_invitation_record_data(
    username: str,
    expires_at: datetime,
    created_by: str,
    plaintext_token: str
) -> dict:
    """Create invitation record data with hashed token.
    
    A05: Prepares database record with token hash, not plaintext.
    
    Args:
        username: Username for the invitation
        expires_at: Expiration timestamp
        created_by: Admin who created the invitation
        plaintext_token: The generated plaintext token (to be hashed)
    
    Returns:
        Dictionary of database record fields
    """
    return {
        "token_hash": hash_invitation_token(plaintext_token),
        "username": username,
        "expires_at": expires_at,
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc),
        "used": False,
        "used_at": None,
        "used_from_ip": None,
        "redemption_attempts": 0,
        "last_attempt_at": None,
    }


# A05: Validation for production secrets
def validate_invitation_secret():
    """Validate that invitation secret is strong in production."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env in ["production", "prod", "staging"]:
        if INVITATION_SECRET == "change-this-secret":
            raise RuntimeError(
                f"FATAL: Invitation token security requires strong secret in {env} environment. "
                "Set INVITATION_TOKEN_SECRET or JWT_SECRET to a cryptographically strong value."
            )
        if len(INVITATION_SECRET) < 32:
            import logging
            logging.warning(
                "INVITATION_TOKEN_SECRET is weak (< 32 characters) in %s environment.",
                env
            )

# Run validation at module import
validate_invitation_secret()
