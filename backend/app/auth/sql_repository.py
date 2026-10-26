# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
SQL-based User Repository — database-backed user store.

This replaces the JSON file repository with a SQLAlchemy-based implementation,
enabling real-time user management and better scalability.
"""
from __future__ import annotations

import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.auth.repository import AuthUserRecord, UserRepository
from app.schemas.auth_users_table import AuthUser

logger = logging.getLogger("auth")


class SqlUserRepository(UserRepository):
    """Loads user records from the database.
    
    Thread-safe: each call receives a fresh database session from the caller.
    """

    def __init__(self, session_factory=None):
        """
        Initialize the SQL repository.
        
        Args:
            session_factory: SQLAlchemy SessionFactory (typically SessionLocal).
                           If None, must be provided to each get_by_username call.
        """
        self.session_factory = session_factory

    def get_by_username(self, username: str) -> Optional[AuthUserRecord]:
        """
        Fetch a user by username from the database.
        
        Args:
            username: Username to look up (case-insensitive)
        
        Returns:
            AuthUserRecord if found, None otherwise
        """
        if not username or not username.strip():
            return None

        # Use session_factory to create a new session
        if not self.session_factory:
            logger.error("No session_factory configured in SqlUserRepository")
            return None

        session = self.session_factory()
        
        try:
            clean = username.strip().lower()

            # Query case-insensitive
            user = session.query(AuthUser).filter(
                AuthUser.username.ilike(clean)
            ).first()

            if user:
                # Convert database model to AuthUserRecord
                return AuthUserRecord(
                    username=user.username,
                    password_hash=user.password_hash,
                    display_name=user.display_name,
                    role=user.role,
                    department=user.department,
                    email=user.email,
                    avatar_initials=user.avatar_initials,
                    status=user.status,
                    tenant_id=user.tenant_id,
                )

            # Try with dot/underscore conversion
            if "." in clean:
                alt = clean.replace(".", "_")
                user = session.query(AuthUser).filter(
                    AuthUser.username.ilike(alt)
                ).first()
                if user:
                    return AuthUserRecord(
                        username=user.username,
                        password_hash=user.password_hash,
                        display_name=user.display_name,
                        role=user.role,
                        department=user.department,
                        email=user.email,
                        avatar_initials=user.avatar_initials,
                        status=user.status,
                        tenant_id=user.tenant_id,
                    )

            if "_" in clean:
                alt = clean.replace("_", ".")
                user = session.query(AuthUser).filter(
                    AuthUser.username.ilike(alt)
                ).first()
                if user:
                    return AuthUserRecord(
                        username=user.username,
                        password_hash=user.password_hash,
                        display_name=user.display_name,
                        role=user.role,
                        department=user.department,
                        email=user.email,
                        avatar_initials=user.avatar_initials,
                        status=user.status,
                        tenant_id=user.tenant_id,
                    )

            return None

        except Exception as exc:
            logger.error("Error querying user %s from database: %s", username, exc)
            return None
        finally:
            session.close()

    def create_user(
        self,
        db: Session,
        username: str,
        password_hash: str,
        display_name: str,
        role: str,
        department: str = "",
        email: str = "",
        avatar_initials: str = "",
        status: str = "Active",
        tenant_id: Optional[str] = None,
        is_superuser: bool = False,
    ) -> AuthUser:
        """
        Create a new user in the database.
        
        Args:
            db: Database session
            username: Unique username
            password_hash: Hashed password (PBKDF2)
            display_name: Human-readable name
            role: User role (e.g., "Compliance & Regulatory Officer")
            department: Department name
            email: Email address
            avatar_initials: Avatar initials (auto-generated if not provided)
            status: Account status ("Active", "Inactive", etc.)
            tenant_id: Tenant identifier (for multi-tenant deployments)
            is_superuser: Whether user is a superuser
        
        Returns:
            Created AuthUser instance
        
        Raises:
            Exception: If user already exists or database error
        """
        # Check if user exists
        existing = db.query(AuthUser).filter_by(username=username).first()
        if existing:
            raise ValueError(f"User {username} already exists")

        # Auto-generate avatar initials if not provided
        if not avatar_initials and display_name:
            avatar_initials = "".join(
                w[0] for w in display_name.split()[:2]
            ).upper()

        user = AuthUser(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            department=department,
            email=email,
            avatar_initials=avatar_initials,
            status=status,
            tenant_id=tenant_id,
            is_superuser=is_superuser,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        logger.info("Created user: username=%s role=%s", username, role)
        return user

    def get_all_users(self, db: Session, active_only: bool = False) -> list[AuthUser]:
        """
        Get all users (optionally filtered to active only).
        
        Args:
            db: Database session
            active_only: If True, only return Active users
        
        Returns:
            List of AuthUser instances
        """
        query = db.query(AuthUser)
        
        if active_only:
            query = query.filter_by(status="Active")
        
        return query.all()
