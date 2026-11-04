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
"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class InvitationToken(Base):
    """Secure invitation token for new user enrollment.
    
    Generated when an admin creates a new user account. The invitation token
    is sent to the user (out-of-band) and allows them to set their own password.
    """
    __tablename__ = "invitation_tokens"

    # Token (primary key, cryptographically secure random)
    token: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)

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

    def __repr__(self) -> str:
        """Return unambiguous string representation of the instance.

        Returns:
            str: Resulting str instance.
        """
        return f"<InvitationToken username={self.username} used={self.used} expires_at={self.expires_at}>"
