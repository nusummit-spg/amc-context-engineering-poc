# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
Invitation Token Table — stores secure user invitation tokens for enrollment.

Part of SEC-03 fix: Replaces predictable default passwords with secure
invitation-based enrollment workflow.

Wave 1.3 A05 (C-14) Security Hardening:
- Stores only HASHED tokens (HMAC-SHA256), not plaintext
- Constant-time comparison to prevent timing attacks
- Atomic single-use enforcement with row locking
- Rate limiting and brute force protection support
"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class InvitationToken(Base):
    """Secure invitation token for new user enrollment.
    
    Generated when an admin creates a new user account. The invitation token
    is sent to the user (out-of-band) and allows them to set their own password.
    
    A05 Security (C-14):
    - Stores only hashed token (HMAC-SHA256 with server secret)
    - Plaintext token is NEVER stored or returned after initial creation
    - Constant-time comparison prevents timing attacks
    - Atomic single-use with database row locking
    """
    __tablename__ = "invitation_tokens"

    # Token hash (primary key) - NOT the actual token
    # A05: This is HMAC-SHA256(plaintext_token, server_secret), not the plaintext
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)

    # Associated username
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Creator
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Usage tracking
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_from_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    
    # A05: Rate limiting / brute force protection
    redemption_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """Return unambiguous string representation of the instance.

        Returns:
            str: Resulting str instance.
        """
        return f"<InvitationToken username={self.username} used={self.used} expires_at={self.expires_at}>"
