# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
Revoked Token Table — tracks invalidated JWT tokens.

Implements server-side token revocation for logout, password change,
and account deactivation scenarios.
"""
from datetime import datetime, timezone
from sqlalchemy import String, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RevokedToken(Base):
    """Tracks revoked JWT tokens to enable server-side invalidation.
    
    Tokens are identified by JTI (JWT ID) and tracked until expiration.
    Expired revocations are cleaned up automatically to prevent unbounded growth.
    """
    __tablename__ = "revoked_tokens"

    # Primary key: JWT ID (unique identifier per token)
    jti: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    
    # Username associated with the token (for audit trail)
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    
    # When the token was revoked
    revoked_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    
    # When the token naturally expires (for cleanup)
    expires_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    
    # Reason for revocation (for audit/debugging)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)  # "logout", "password_change", "admin_revoked"
    
    # Optional: IP address that triggered revocation
    revoked_by_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        Index("idx_revoked_tokens_expires", "expires_at"),
        Index("idx_revoked_tokens_username_revoked", "username", "revoked_at"),
    )

    @classmethod
    def cleanup_expired(cls, db) -> int:
        """Purge tokens that have already naturally expired.

        Returns:
            int: Number of deleted expired records.
        """
        now = datetime.now(timezone.utc)
        deleted = db.query(cls).filter(cls.expires_at < now).delete(synchronize_session=False)
        db.commit()
        return deleted

    def __repr__(self) -> str:
        """Return unambiguous string representation of the instance.

        Returns:
            str: Resulting str instance.
        """
        return f"<RevokedToken jti={self.jti[:8]}... username={self.username} reason={self.reason}>"
