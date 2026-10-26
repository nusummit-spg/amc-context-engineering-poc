# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
Auth Users Table — stores application user credentials and metadata.

This replaces the JSON-based user store with a database-backed repository,
enabling dynamic user management and better scalability.
"""
from datetime import datetime
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AuthUser(Base):
    """User account stored in the database.
    
    Replaces hardcoded JSON users.json with database-backed user management.
    """
    __tablename__ = "auth_users"

    # Primary key
    username: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)

    # Password (hashed with PBKDF2)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)

    # User identity
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str] = mapped_column(String(256), nullable=False, index=True)

    # Role and department
    role: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    # Avatar
    avatar_initials: Mapped[str] = mapped_column(String(10), nullable=False, default="")

    # Account status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active", index=True)

    # Tenant (for multi-tenant isolation)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Audit fields
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    def __repr__(self) -> str:
        """Return unambiguous string representation of the instance.

        Returns:
            str: Resulting str instance.
        """
        return f"<AuthUser username={self.username} role={self.role} status={self.status}>"
