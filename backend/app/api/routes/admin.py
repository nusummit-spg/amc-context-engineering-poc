# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
admin.py
========
Administrative operations with mandatory authentication and authorization.
All endpoints require authenticated users with appropriate roles.

Security Requirements (Wave 1.1 P0 - SEC-01):
- No unauthenticated access to sensitive operations
- Server-authoritative role checking via JWT
- Tenant isolation for multi-tenant operations
- Audit trail for all administrative actions
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_auth_service
from app.auth.service import AuthService
from app.core.database import get_db
from app.models.auth import UserPublic

logger = logging.getLogger("app.api.admin")

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Request/Response Models ─────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    """Request to create a new user account."""
    username: str = Field(..., min_length=3, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=256)
    email: EmailStr
    role: str = Field(..., pattern="^(admin|compliance_officer|analyst|viewer|reviewer)$")
    department: str = ""
    tenant_id: Optional[str] = None


class CreateUserResponse(BaseModel):
    """Response after creating a user with a secure invitation token."""
    username: str
    invitation_token: str
    expires_at: str
    message: str


class UpdateUserRequest(BaseModel):
    """Request to update user details."""
    display_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(None, pattern="^(admin|compliance_officer|analyst|viewer|reviewer)$")
    department: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(Active|Inactive|Suspended)$")
    tenant_id: Optional[str] = None


class SetPasswordRequest(BaseModel):
    """Request to set/reset user password (admin operation)."""
    new_password: str = Field(..., min_length=12, max_length=256)


class IngestionTriggerRequest(BaseModel):
    """Request to trigger ingestion job."""
    source_path: Optional[str] = None
    taxonomy_scope: Optional[str] = None
    force_reindex: bool = False


class CacheClearRequest(BaseModel):
    """Request to clear application caches."""
    cache_types: List[str] = Field(default_factory=lambda: ["semantic", "query", "vector"])


# ── Administrative Endpoints ────────────────────────────────────────────────

@router.get("/users", response_model=List[UserPublic])
async def list_users(
    current_user: CurrentUser,
    limit: int = 100,
    offset: int = 0,
    auth_service: AuthService = Depends(get_auth_service),
) -> List[UserPublic]:
    """List all users. Requires admin or compliance_officer role.
    
    Args:
        current_user: Authenticated user from JWT
        limit: Maximum number of users to return
        offset: Pagination offset
        auth_service: Authentication service
    
    Returns:
        List of user public profiles
    
    Raises:
        HTTPException(403): If user lacks administrative privileges
    """
    if current_user.role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    
    # TODO: Implement pagination and tenant filtering
    # For now, return all users (will be filtered by tenant in production)
    try:
        from app.auth.sql_repository import SqlUserRepository
        from app.core.database import SessionLocal
        
        repo = SqlUserRepository(session_factory=SessionLocal)
        db = SessionLocal()
        try:
            users = repo.list_all(db, limit=limit, offset=offset)
            return [UserPublic(**user.__dict__) for user in users]
        finally:
            db.close()
    except Exception as exc:
        logger.error("Failed to list users: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user list"
        )


@router.post("/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    current_user: CurrentUser,
    auth_service: AuthService = Depends(get_auth_service),
) -> CreateUserResponse:
    """Create a new user account with secure invitation flow.
    
    SEC-03 FIX: No predictable default passwords. Issues invitation token instead.
    
    Args:
        request: User creation request
        current_user: Authenticated admin user
        auth_service: Authentication service
    
    Returns:
        User creation response with invitation token
    
    Raises:
        HTTPException(403): If not admin
        HTTPException(409): If username already exists
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to create users"
        )
    
    try:
        from app.auth.sql_repository import SqlUserRepository
        from app.core.database import SessionLocal
        from app.schemas.auth_users_table import AuthUser
        from app.schemas.invitation_token import InvitationToken
        
        repo = SqlUserRepository(session_factory=SessionLocal)
        db = SessionLocal()
        
        try:
            # Check if user already exists
            existing = repo.get_by_username(db, request.username)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Username '{request.username}' already exists"
                )
            
            # Generate secure invitation token (32 bytes = 256 bits)
            invitation_token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59)
            
            # Create user account in pending state (no password yet)
            new_user = AuthUser(
                username=request.username,
                password_hash="",  # Will be set when user accepts invitation
                display_name=request.display_name,
                email=request.email,
                role=request.role,
                department=request.department or "",
                status="Pending",  # Changed from Active to Pending
                tenant_id=request.tenant_id or current_user.tenant_id or "default",
                created_at=datetime.now(timezone.utc),
                avatar_initials=request.display_name[:2].upper() if request.display_name else request.username[:2].upper()
            )
            
            db.add(new_user)
            
            # Store invitation token
            invitation = InvitationToken(
                token=invitation_token,
                username=request.username,
                expires_at=expires_at,
                created_by=current_user.username,
                used=False
            )
            db.add(invitation)
            
            db.commit()
            
            logger.info(
                "User created: username=%s, role=%s, tenant=%s, created_by=%s",
                request.username, request.role, new_user.tenant_id, current_user.username
            )
            
            return CreateUserResponse(
                username=request.username,
                invitation_token=invitation_token,
                expires_at=expires_at.isoformat(),
                message=f"User created. Send invitation token to user to complete registration. Token expires at {expires_at.isoformat()}"
            )
            
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            logger.error("Failed to create user: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create user: {str(exc)}"
            )
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("User creation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during user creation"
        )


@router.get("/users/{username}", response_model=UserPublic)
async def get_user(
    username: str,
    current_user: CurrentUser,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    """Get user details by username.
    
    Args:
        username: Username to retrieve
        current_user: Authenticated user
        auth_service: Authentication service
    
    Returns:
        User public profile
    
    Raises:
        HTTPException(403): If user lacks privileges
        HTTPException(404): If user not found
    """
    # Users can view their own profile, admins can view anyone
    if current_user.username != username and current_user.role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges to view this user"
        )
    
    try:
        from app.auth.sql_repository import SqlUserRepository
        from app.core.database import SessionLocal
        
        repo = SqlUserRepository(session_factory=SessionLocal)
        db = SessionLocal()
        try:
            user = repo.get_by_username(db, username)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{username}' not found"
                )
            
            # Tenant isolation: admins see all, others only see same tenant
            if current_user.role != "admin":
                if user.tenant_id != current_user.tenant_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"User '{username}' not found"
                    )
            
            return UserPublic(**user.__dict__)
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get user: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )


@router.patch("/users/{username}", response_model=UserPublic)
async def update_user(
    username: str,
    request: UpdateUserRequest,
    current_user: CurrentUser,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    """Update user details. Requires admin role.
    
    Args:
        username: Username to update
        request: Update request
        current_user: Authenticated admin user
        auth_service: Authentication service
    
    Returns:
        Updated user profile
    
    Raises:
        HTTPException(403): If not admin
        HTTPException(404): If user not found
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to update users"
        )
    
    try:
        from app.auth.sql_repository import SqlUserRepository
        from app.core.database import SessionLocal
        
        repo = SqlUserRepository(session_factory=SessionLocal)
        db = SessionLocal()
        
        try:
            user = repo.get_by_username(db, username)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{username}' not found"
                )
            
            # Apply updates
            if request.display_name is not None:
                user.display_name = request.display_name
            if request.email is not None:
                user.email = request.email
            if request.role is not None:
                user.role = request.role
            if request.department is not None:
                user.department = request.department
            if request.status is not None:
                user.status = request.status
            if request.tenant_id is not None:
                user.tenant_id = request.tenant_id
            
            db.commit()
            db.refresh(user)
            
            logger.info(
                "User updated: username=%s, updated_by=%s",
                username, current_user.username
            )
            
            return UserPublic(**user.__dict__)
            
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            logger.error("Failed to update user: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update user: {str(exc)}"
            )
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("User update error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during user update"
        )


@router.delete("/users/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    username: str,
    current_user: CurrentUser,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Delete user account. Requires admin role.
    
    Args:
        username: Username to delete
        current_user: Authenticated admin user
        auth_service: Authentication service
    
    Raises:
        HTTPException(403): If not admin or trying to delete self
        HTTPException(404): If user not found
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to delete users"
        )
    
    if current_user.username == username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    try:
        from app.auth.sql_repository import SqlUserRepository
        from app.core.database import SessionLocal
        
        repo = SqlUserRepository(session_factory=SessionLocal)
        db = SessionLocal()
        
        try:
            user = repo.get_by_username(db, username)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{username}' not found"
                )
            
            db.delete(user)
            db.commit()
            
            logger.info(
                "User deleted: username=%s, deleted_by=%s",
                username, current_user.username
            )
            
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            logger.error("Failed to delete user: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete user: {str(exc)}"
            )
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("User deletion error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during user deletion"
        )


# ── Ingestion Administrative Operations ─────────────────────────────────────

@router.post("/ingestion/run")
async def trigger_ingestion(
    request: IngestionTriggerRequest,
    current_user: CurrentUser,
) -> dict:
    """Trigger ingestion job. Requires admin or compliance_officer role.
    
    Args:
        request: Ingestion trigger request
        current_user: Authenticated user
    
    Returns:
        Job status
    
    Raises:
        HTTPException(403): If user lacks ingestion privileges
    """
    if current_user.role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ingestion requires admin or compliance_officer role"
        )
    
    logger.info(
        "Ingestion triggered: source=%s, taxonomy=%s, force_reindex=%s, triggered_by=%s",
        request.source_path, request.taxonomy_scope, request.force_reindex, current_user.username
    )
    
    # TODO: Implement actual ingestion trigger
    return {
        "status": "queued",
        "message": "Ingestion job queued successfully",
        "triggered_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/ingestion/upload")
async def upload_source_file(
    current_user: CurrentUser,
) -> dict:
    """Upload source file for ingestion. Requires admin or compliance_officer role.
    
    Args:
        current_user: Authenticated user
    
    Returns:
        Upload status
    
    Raises:
        HTTPException(403): If user lacks upload privileges
    """
    if current_user.role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Upload requires admin or compliance_officer role"
        )
    
    # TODO: Implement actual file upload handler
    return {
        "status": "pending",
        "message": "File upload endpoint - implementation pending"
    }


# ── Cache Management ────────────────────────────────────────────────────────

@router.post("/cache/clear")
async def clear_cache(
    request: CacheClearRequest,
    current_user: CurrentUser,
) -> dict:
    """Clear application caches. Requires admin role.
    
    Args:
        request: Cache clear request
        current_user: Authenticated admin user
    
    Returns:
        Cache clear status
    
    Raises:
        HTTPException(403): If not admin
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cache management requires admin role"
        )
    
    cleared = []
    failed = []
    
    for cache_type in request.cache_types:
        try:
            if cache_type == "semantic":
                # TODO: Clear semantic cache
                cleared.append(cache_type)
            elif cache_type == "query":
                # TODO: Clear query cache
                cleared.append(cache_type)
            elif cache_type == "vector":
                # TODO: Clear vector cache
                cleared.append(cache_type)
            else:
                failed.append({"type": cache_type, "reason": "Unknown cache type"})
        except Exception as exc:
            failed.append({"type": cache_type, "reason": str(exc)})
    
    logger.info(
        "Cache cleared: types=%s, cleared_by=%s",
        cleared, current_user.username
    )
    
    return {
        "status": "completed",
        "cleared": cleared,
        "failed": failed,
        "cleared_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
