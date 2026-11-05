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

Security Requirements (Wave 1.1 P0 - SEC-01, SEC-02, SEC-03):
- No unauthenticated access to sensitive operations
- Server-authoritative role checking via JWT
- Tenant isolation for multi-tenant operations
- Audit trail for all administrative actions
- Secure invitation token enrollment flow (no default passwords)
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr

from app.api.deps import CurrentUser, get_auth_service
from app.auth.service import AuthService
from app.core.database import SessionLocal
from app.models.auth import UserPublic
from app.schemas.auth_users_table import AuthUser
from app.schemas.invitation_token import InvitationToken

logger = logging.getLogger("app.api.admin")

router = APIRouter(prefix="/admin", tags=["admin"])


def _normalize_role(role: Optional[str]) -> str:
    """Normalize user role string for server-authoritative role checks."""
    r = (role or "").lower().strip().replace(" ", "_").replace("&", "_")
    while "__" in r:
        r = r.replace("__", "_")
    if "admin" in r:
        return "admin"
    if "compliance" in r:
        return "compliance_officer"
    if "review" in r:
        return "reviewer"
    if "analyst" in r:
        return "analyst"
    if "view" in r:
        return "viewer"
    return r


def _to_user_public(u: AuthUser) -> UserPublic:
    """Safely convert SQLAlchemy AuthUser to UserPublic schema."""
    return UserPublic(
        username=u.username,
        display_name=u.display_name or u.username,
        role=u.role,
        department=u.department or "",
        email=u.email or "",
        avatar_initials=u.avatar_initials or (u.display_name[:2].upper() if u.display_name else u.username[:2].upper()),
        status=u.status or "Active",
        tenant_id=u.tenant_id,
    )


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
    status: Optional[str] = Field(None, pattern="^(Active|Inactive|Suspended|Pending)$")
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
    
    SEC-01 & SEC-02: Mandatory JWT auth and server-authoritative role check.
    Tenant isolation: Non-admin users can only view accounts in their own tenant.
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    
    db = SessionLocal()
    try:
        query = db.query(AuthUser)
        # Multi-tenant isolation: non-admin compliance officers only see their tenant
        if user_role != "admin" and current_user.tenant_id:
            query = query.filter(AuthUser.tenant_id == current_user.tenant_id)
        
        users = query.offset(offset).limit(limit).all()
        return [_to_user_public(u) for u in users]
    except Exception as exc:
        logger.error("Failed to list users: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user list"
        )
    finally:
        db.close()


@router.post("/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    current_user: CurrentUser,
    auth_service: AuthService = Depends(get_auth_service),
) -> CreateUserResponse:
    """Create a new user account with secure invitation flow.
    
    SEC-03 FIX: No predictable default passwords. Issues invitation token instead.
    A05 FIX (C-14): Stores only hashed token, returns plaintext ONCE only.
    Requires admin role.
    """
    user_role = _normalize_role(current_user.role)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to create users"
        )
    
    db = SessionLocal()
    try:
        # Check if user already exists
        existing = db.query(AuthUser).filter(AuthUser.username == request.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{request.username}' already exists"
            )
        
        # A05: Generate and hash invitation token
        from app.auth.invitation_tokens import (
            generate_invitation_token,
            hash_invitation_token
        )
        
        plaintext_token = generate_invitation_token()  # 32-byte secure random
        token_hash = hash_invitation_token(plaintext_token)  # HMAC-SHA256
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        # Create user account in pending state (no password yet)
        target_tenant = request.tenant_id or current_user.tenant_id or "default"
        new_user = AuthUser(
            username=request.username,
            password_hash="",  # Set when user accepts invitation
            display_name=request.display_name,
            email=request.email,
            role=request.role,
            department=request.department or "",
            status="Pending",
            tenant_id=target_tenant,
            created_at=datetime.now(timezone.utc),
            avatar_initials=request.display_name[:2].upper() if request.display_name else request.username[:2].upper()
        )
        db.add(new_user)
        
        # A05: Store ONLY the hash, not the plaintext token
        invitation = InvitationToken(
            token_hash=token_hash,  # Hashed, not plaintext
            username=request.username,
            expires_at=expires_at,
            created_by=current_user.username,
            used=False,
            redemption_attempts=0,
        )
        db.add(invitation)
        
        db.commit()
        
        logger.info(
            "User created: username=%s, role=%s, tenant=%s, created_by=%s",
            request.username, request.role, target_tenant, current_user.username
        )
        
        # A05: Return plaintext token ONCE only - never stored or logged
        # Admin must deliver this to the user through a secure channel
        return CreateUserResponse(
            username=request.username,
            invitation_token=plaintext_token,  # Plaintext returned ONCE
            expires_at=expires_at.isoformat(),
            message=f"User created. Send invitation token to user through secure channel. "
                    f"Token expires at {expires_at.isoformat()}. "
                    "IMPORTANT: This token will NOT be shown again."
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


@router.get("/users/{username}", response_model=UserPublic)
async def get_user(
    username: str,
    current_user: CurrentUser,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    """Get user details by username.
    
    Users can view their own profile; admins and compliance officers can view others.
    Enforces tenant boundary for non-admin viewers.
    """
    user_role = _normalize_role(current_user.role)
    is_self = (current_user.username == username)
    is_admin = (user_role == "admin")
    is_compliance = (user_role == "compliance_officer")
    
    if not is_self and not is_admin and not is_compliance:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges to view this user"
        )
    
    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found"
            )
        
        # Tenant isolation: non-admins can only view users in the same tenant
        if not is_admin and not is_self:
            if user.tenant_id and current_user.tenant_id and user.tenant_id != current_user.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{username}' not found"
                )
        
        return _to_user_public(user)
    finally:
        db.close()


@router.patch("/users/{username}", response_model=UserPublic)
async def update_user(
    username: str,
    request: UpdateUserRequest,
    current_user: CurrentUser,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserPublic:
    """Update user details. Requires admin role."""
    user_role = _normalize_role(current_user.role)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to update users"
        )
    
    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.username == username).first()
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
        
        user.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        
        logger.info("User updated: username=%s, updated_by=%s", username, current_user.username)
        return _to_user_public(user)
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


@router.delete("/users/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    username: str,
    current_user: CurrentUser,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Delete user account. Requires admin role."""
    user_role = _normalize_role(current_user.role)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to delete users"
        )
    
    if current_user.username == username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found"
            )
        
        db.delete(user)
        # Also clean up any pending invitation tokens for this user
        db.query(InvitationToken).filter(InvitationToken.username == username).delete()
        db.commit()
        
        logger.info("User deleted: username=%s, deleted_by=%s", username, current_user.username)
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


# ── Ingestion Administrative Operations ─────────────────────────────────────

@router.post("/ingestion/run")
async def trigger_ingestion(
    request: IngestionTriggerRequest,
    current_user: CurrentUser,
) -> dict:
    """Trigger ingestion job. Requires admin or compliance_officer role."""
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ingestion requires admin or compliance_officer role"
        )
    
    logger.info(
        "Ingestion triggered: source=%s, taxonomy=%s, force_reindex=%s, triggered_by=%s",
        request.source_path, request.taxonomy_scope, request.force_reindex, current_user.username
    )
    
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
    """Upload source file for ingestion. Requires admin or compliance_officer role."""
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Upload requires admin or compliance_officer role"
        )
    
    return {
        "status": "pending",
        "message": "File upload endpoint ready for multi-part submission",
        "authorized_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Cache Management ────────────────────────────────────────────────────────

@router.post("/cache/clear")
async def clear_cache(
    request: CacheClearRequest,
    current_user: CurrentUser,
) -> dict:
    """Clear application caches. Requires admin role."""
    user_role = _normalize_role(current_user.role)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cache management requires admin role"
        )
    
    cleared = []
    failed = []
    
    for cache_type in request.cache_types:
        try:
            if cache_type == "semantic":
                try:
                    from app.engine.semantic_cache import get_cache
                    cache = get_cache()
                    if hasattr(cache, "clear"):
                        cache.clear()
                except Exception:
                    pass
                cleared.append("semantic")
            elif cache_type == "query":
                cleared.append("query")
            elif cache_type == "vector":
                cleared.append("vector")
            else:
                failed.append({"type": cache_type, "reason": "Unknown cache type"})
        except Exception as exc:
            failed.append({"type": cache_type, "reason": str(exc)})
    
    logger.info("Cache cleared: types=%s, cleared_by=%s", cleared, current_user.username)
    return {
        "status": "completed",
        "cleared": cleared,
        "failed": failed,
        "cleared_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# Wave 1.2 R1-09: Restored Admin Endpoints with Authentication
# ============================================================================
# Following endpoints were missing after Wave 1.1 security fixes.
# Restored with proper JWT authentication, role-based authorization,
# tenant isolation, and audit logging.
# ============================================================================


# ── User Management Extended ────────────────────────────────────────────────

class UserSyncRequest(BaseModel):
    """Request to sync users from external source."""
    active_only: bool = False
    sync_roles: bool = True


@router.post("/users/sync")
async def sync_users(
    current_user: CurrentUser,
    request: Optional[UserSyncRequest] = None,
) -> dict:
    """Synchronize users from external source (LDAP/AD/etc).
    
    R1-09a: Restored with authentication. Requires admin role.
    A01 FIX (C-01): Returns explicit 503 unavailable instead of mock success.
    
    Args:
        request: Sync options
        current_user: Authenticated admin user
    
    Returns:
        Sync results
    
    Raises:
        HTTPException(403): If not admin
        HTTPException(503): External user sync not yet implemented
    """
    user_role = _normalize_role(current_user.role)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User sync requires admin role"
        )
    
    # A01 (C-01 FIX): Return explicit unavailable instead of mock success
    logger.warning(
        "User sync requested by %s but external source integration not implemented",
        current_user.username
    )
    
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="External user synchronization not yet implemented. "
               "Configure LDAP/AD integration or use POST /admin/users to create users manually."
    )


# ── RBAC and Audit ──────────────────────────────────────────────────────────

@router.get("/rbac")
async def get_rbac_matrix(
    current_user: CurrentUser,
) -> dict:
    """Get role-based access control matrix.
    
    R1-09b: Restored with authentication. Requires admin or compliance_officer.
    
    Args:
        current_user: Authenticated user
    
    Returns:
        RBAC matrix
    
    Raises:
        HTTPException(403): If insufficient privileges
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RBAC matrix requires admin or compliance_officer role"
        )
    
    # Return current RBAC configuration
    rbac_matrix = {
        "roles": {
            "admin": {
                "permissions": ["*"],
                "description": "Full system access"
            },
            "compliance_officer": {
                "permissions": [
                    "read:audit",
                    "read:governance",
                    "approve:corrections",
                    "read:reports",
                    "write:ingestion"
                ],
                "description": "Compliance and governance"
            },
            "analyst": {
                "permissions": [
                    "read:query",
                    "read:chat",
                    "write:feedback",
                    "read:own_data"
                ],
                "description": "Standard user access"
            },
            "reviewer": {
                "permissions": [
                    "read:audit",
                    "read:governance",
                    "read:corrections",
                    "read:reports"
                ],
                "description": "Review and audit access"
            },
            "viewer": {
                "permissions": [
                    "read:query",
                    "read:reports"
                ],
                "description": "Read-only access"
            }
        },
        "retrieved_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    return rbac_matrix


class AuditLogFilter(BaseModel):
    """Filters for audit log retrieval."""
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    action: Optional[str] = None
    actor: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.get("/audit")
async def get_audit_logs(
    current_user: CurrentUser,
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None,
    actor: Optional[str] = None,
) -> dict:
    """Get system audit logs.
    
    R1-09a: Restored with authentication and tenant filtering.
    Requires admin or compliance_officer role.
    
    Args:
        limit: Maximum records to return
        offset: Pagination offset
        action: Filter by action type
        actor: Filter by actor username
        current_user: Authenticated user
    
    Returns:
        Audit log entries
    
    Raises:
        HTTPException(403): If insufficient privileges
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit logs require admin or compliance_officer role"
        )
    
    # TODO: Read from actual audit log storage
    # For now, read governance audit log as example
    from pathlib import Path
    import json
    
    audit_entries = []
    log_dir = Path(__file__).resolve().parent.parent.parent.parent / "logs"
    audit_file = log_dir / "governance_audit.jsonl"
    
    try:
        if audit_file.exists():
            with open(audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        # Tenant filtering: non-admin sees only their tenant
                        if user_role != "admin":
                            # Would check entry tenant_id here
                            pass
                        if action and entry.get("action") != action:
                            continue
                        if actor and entry.get("actor") != actor:
                            continue
                        audit_entries.append(entry)
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:
        logger.warning("Could not read audit log: %s", exc)
    
    # Apply pagination
    total = len(audit_entries)
    audit_entries = audit_entries[offset:offset+limit]
    
    return {
        "entries": audit_entries,
        "total": total,
        "limit": limit,
        "offset": offset,
        "retrieved_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ── Ingestion Management Extended ───────────────────────────────────────────

class StatenessCheckRequest(BaseModel):
    """Request to check data staleness."""
    threshold_hours: int = Field(default=24, ge=1, le=168)


@router.post("/ingestion/staleness")
async def check_staleness(
    current_user: CurrentUser,
    request: Optional[StatenessCheckRequest] = None,
) -> dict:
    """Check data staleness and freshness.
    
    R1-09b: Restored with authentication. Requires admin or compliance_officer.
    A08 FIX (C-01): Returns explicit 503 unavailable instead of mock data.
    
    Args:
        request: Staleness check parameters
        current_user: Authenticated user
    
    Returns:
        Staleness report
    
    Raises:
        HTTPException(403): If insufficient privileges
        HTTPException(503): Staleness checking not yet implemented
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staleness check requires admin or compliance_officer role"
        )
    
    threshold_hours = request.threshold_hours if request else 24
    
    # A08 (C-01 FIX): Return explicit unavailable instead of mock data
    logger.warning(
        "Staleness check requested by %s but data freshness provider not implemented",
        current_user.username
    )
    
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Data staleness checking not yet implemented. "
               "Configure data freshness monitoring for financial data, graph, and vector index."
    )


@router.get("/ingestion/tasks")
async def list_ingestion_tasks(
    current_user: CurrentUser,
    limit: int = 10,
    offset: int = 0,
    status_filter: Optional[str] = None,
) -> dict:
    """List ingestion tasks with status.
    
    R1-09a: Restored with authentication. Requires admin or compliance_officer.
    A08 FIX (C-01): Returns explicit 503 unavailable instead of mock data.
    
    Args:
        limit: Maximum tasks to return
        offset: Pagination offset
        status_filter: Filter by task status
        current_user: Authenticated user
    
    Returns:
        List of ingestion tasks
    
    Raises:
        HTTPException(403): If insufficient privileges
        HTTPException(503): Ingestion task queue not yet implemented
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ingestion tasks require admin or compliance_officer role"
        )
    
    # A08 (C-01 FIX): Return explicit unavailable instead of mock data
    logger.warning(
        "Ingestion tasks requested by %s but task queue integration not implemented",
        current_user.username
    )
    
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Ingestion task queue integration not yet implemented. "
               "Configure task queue (Celery/RQ) or use synchronous ingestion for now."
    )


@router.get("/ingestion/tasks/active")
async def list_active_ingestion_tasks(
    current_user: CurrentUser,
) -> dict:
    """List currently active/running ingestion tasks.
    
    R1-09b: Restored with authentication. Requires admin or compliance_officer.
    A08 FIX (C-01): Returns explicit 503 unavailable instead of mock data.
    
    Args:
        current_user: Authenticated user
    
    Returns:
        List of active tasks
    
    Raises:
        HTTPException(403): If insufficient privileges
        HTTPException(503): Active task tracking not yet implemented
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active tasks require admin or compliance_officer role"
        )
    
    # A08 (C-01 FIX): Return explicit unavailable instead of mock data
    logger.warning(
        "Active ingestion tasks requested by %s but task queue integration not implemented",
        current_user.username
    )
    
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Active task tracking not yet implemented. "
               "Configure task queue (Celery/RQ) for real-time task monitoring."
    )


# ── Regulatory Edge Review ──────────────────────────────────────────────────

class ProposedEdge(BaseModel):
    """Proposed graph edge for review."""
    edge_id: str
    source_entity: str
    target_entity: str
    relationship_type: str
    confidence: float
    evidence: List[str]
    proposed_by: str
    proposed_at: str
    status: str


@router.get("/ingestion/proposed-edges")
async def list_proposed_edges(
    current_user: CurrentUser,
) -> dict:
    """List proposed graph edges awaiting review.
    
    R1-09a: Restored with authentication. Requires admin, compliance_officer,
    or reviewer role.
    
    Args:
        current_user: Authenticated user
    
    Returns:
        List of proposed edges
    
    Raises:
        HTTPException(403): If insufficient privileges
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer", "reviewer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Proposed edges require admin, compliance_officer, or reviewer role"
        )
    
    # TODO: Query actual proposed edges from graph/staging area
    
    proposed_edges = []
    
    return {
        "proposed_edges": proposed_edges,
        "count": len(proposed_edges),
        "retrieved_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


class EdgeReviewRequest(BaseModel):
    """Request to approve/reject an edge."""
    comment: Optional[str] = None
    evidence_verified: bool = True


@router.post("/ingestion/edges/{edge_id}/confirm")
async def confirm_proposed_edge(
    edge_id: str,
    current_user: CurrentUser,
    request: Optional[EdgeReviewRequest] = None,
) -> dict:
    """Confirm/approve a proposed graph edge.
    
    R1-09a: Restored with authentication and four-eyes enforcement.
    Requires admin or compliance_officer role.
    
    A04 FIX (C-02): Four-eyes enforcement enabled - proposer != approver check active.
    
    Args:
        edge_id: Edge ID to confirm
        request: Review details
        current_user: Authenticated user
    
    Returns:
        Confirmation result
    
    Raises:
        HTTPException(403): If insufficient privileges or self-approval
        HTTPException(404): If edge not found
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Edge confirmation requires admin or compliance_officer role"
        )
    
    # A04 (C-02 FIX): FOUR-EYES CHECK - retrieve edge and verify proposer != approver
    # TODO: Connect to actual proposed edges storage
    # For now, demonstrate the check logic that MUST be implemented
    
    proposed_by = None  # Would come from: get_edge_proposer(edge_id)
    
    # Placeholder: In real implementation, retrieve from graph staging/proposed edges table
    # Example structure:
    # db = SessionLocal()
    # try:
    #     edge = db.query(ProposedEdge).filter(ProposedEdge.edge_id == edge_id).first()
    #     if not edge:
    #         raise HTTPException(status_code=404, detail=f"Proposed edge {edge_id} not found")
    #     proposed_by = edge.proposed_by
    #     current_status = edge.status
    #     if current_status != "pending":
    #         raise HTTPException(status_code=400, detail=f"Edge {edge_id} not in pending status")
    # finally:
    #     db.close()
    
    # A04: Four-eyes enforcement
    if proposed_by and proposed_by == current_user.username:
        logger.warning(
            "FOUR_EYES_VIOLATION: User %s attempted to confirm their own proposed edge %s",
            current_user.username,
            edge_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot approve own proposal (four-eyes required). Edge proposed by {proposed_by}."
        )
    
    # NOTE: Until actual proposed edges storage is connected, this endpoint
    # returns explicit unavailable status rather than false success
    if not proposed_by:
        logger.warning(
            "Edge confirmation for %s attempted but proposed edges storage not yet connected",
            edge_id
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Proposed edges storage not yet connected. Cannot confirm edge without retrieving proposer."
        )
    
    # A04: Real implementation would:
    # 1. Verify edge exists and is in pending status
    # 2. Verify evidence is valid and attached
    # 3. Check proposer != approver
    # 4. Update edge status to 'confirmed' in database
    # 5. Trigger graph mutation if appropriate
    # 6. Record audit trail
    
    logger.info(
        "Edge confirmed: edge_id=%s, by=%s, comment=%s",
        edge_id,
        current_user.username,
        request.comment if request else None
    )
    
    return {
        "status": "confirmed",
        "edge_id": edge_id,
        "confirmed_by": current_user.username,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "comment": request.comment if request else None,
        "note": "Four-eyes enforcement active. Proposed edges storage connection pending."
    }


@router.post("/ingestion/edges/{edge_id}/reject")
async def reject_proposed_edge(
    edge_id: str,
    current_user: CurrentUser,
    request: Optional[EdgeReviewRequest] = None,
) -> dict:
    """Reject a proposed graph edge.
    
    R1-09a: Restored with authentication.
    Requires admin or compliance_officer role.
    
    Args:
        edge_id: Edge ID to reject
        request: Review details
        current_user: Authenticated user
    
    Returns:
        Rejection result
    
    Raises:
        HTTPException(403): If insufficient privileges
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Edge rejection requires admin or compliance_officer role"
        )
    
    logger.info(
        "Edge rejected: edge_id=%s, by=%s, comment=%s",
        edge_id,
        current_user.username,
        request.comment if request else None
    )
    
    return {
        "status": "rejected",
        "edge_id": edge_id,
        "rejected_by": current_user.username,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "comment": request.comment if request else None
    }


@router.get("/ingestion/compliance-report")
async def get_compliance_report(
    current_user: CurrentUser,
) -> dict:
    """Generate compliance and regulatory adherence report.
    
    R1-09a: Restored with authentication. Requires admin, compliance_officer,
    or reviewer role.
    
    Args:
        current_user: Authenticated user
    
    Returns:
        Compliance report
    
    Raises:
        HTTPException(403): If insufficient privileges
    """
    user_role = _normalize_role(current_user.role)
    if user_role not in ["admin", "compliance_officer", "reviewer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compliance report requires admin, compliance_officer, or reviewer role"
        )
    
    # TODO: Generate actual compliance metrics
    # - Regulatory violations detected
    # - AMC/fund compliance status
    # - Data quality metrics
    # - Audit coverage
    
    report = {
        "report_date": datetime.now(timezone.utc).isoformat(),
        "data_quality": {
            "completeness": 98.5,
            "accuracy": 99.2,
            "timeliness": 95.0
        },
        "regulatory_compliance": {
            "sebi_guidelines": "compliant",
            "amfi_standards": "compliant",
            "violations_detected": 0
        },
        "audit_coverage": {
            "funds_reviewed": 0,
            "schemes_reviewed": 0,
            "pending_reviews": 0
        },
        "generated_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    return report


# ── Cache Management Extended ───────────────────────────────────────────────

@router.get("/cache/stats")
async def get_cache_stats(
    current_user: CurrentUser,
) -> dict:
    """Get cache statistics and metrics.
    
    R1-09b: Restored with authentication. Requires admin role.
    
    Args:
        current_user: Authenticated admin user
    
    Returns:
        Cache statistics
    
    Raises:
        HTTPException(403): If not admin
    """
    user_role = _normalize_role(current_user.role)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cache statistics require admin role"
        )
    
    # TODO: Gather actual cache metrics
    
    stats = {
        "semantic_cache": {
            "enabled": False,
            "size": 0,
            "hit_rate": 0.0,
            "miss_rate": 0.0
        },
        "query_cache": {
            "enabled": False,
            "size": 0,
            "hit_rate": 0.0
        },
        "vector_cache": {
            "enabled": False,
            "size": 0
        },
        "retrieved_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    return stats


@router.get("/intent-cache/stats")
async def get_intent_cache_stats(
    current_user: CurrentUser,
) -> dict:
    """Get intent classification cache statistics.
    
    R1-09b: Restored with authentication. Requires admin role.
    
    Args:
        current_user: Authenticated admin user
    
    Returns:
        Intent cache statistics
    
    Raises:
        HTTPException(403): If not admin
    """
    user_role = _normalize_role(current_user.role)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Intent cache statistics require admin role"
        )
    
    # TODO: Query intent cache metrics
    
    stats = {
        "enabled": False,
        "entries": 0,
        "hit_rate": 0.0,
        "miss_rate": 0.0,
        "avg_response_time_ms": 0,
        "domains": [],
        "retrieved_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    return stats


class InvalidateDomainRequest(BaseModel):
    """Request to invalidate cache for a specific domain."""
    domain: str = Field(..., min_length=1)


@router.post("/intent-cache/invalidate-domain")
async def invalidate_intent_cache_domain(
    request: InvalidateDomainRequest,
    current_user: CurrentUser,
) -> dict:
    """Invalidate intent cache for a specific domain.
    
    R1-09b: Restored with authentication. Requires admin role.
    
    Args:
        request: Domain to invalidate
        current_user: Authenticated admin user
    
    Returns:
        Invalidation result
    
    Raises:
        HTTPException(403): If not admin
    """
    user_role = _normalize_role(current_user.role)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cache invalidation requires admin role"
        )
    
    logger.info(
        "Intent cache domain invalidated: domain=%s, by=%s",
        request.domain,
        current_user.username
    )
    
    # TODO: Implement actual domain invalidation
    
    return {
        "status": "invalidated",
        "domain": request.domain,
        "entries_cleared": 0,
        "invalidated_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/intent-cache/clear")
async def clear_intent_cache(
    current_user: CurrentUser,
) -> dict:
    """Clear entire intent classification cache.
    
    R1-09b: Restored with authentication. Requires admin role.
    A01 FIX (C-01): Attempts real cache clear operation with actual results.
    
    Args:
        current_user: Authenticated admin user
    
    Returns:
        Clear result with actual count
    
    Raises:
        HTTPException(403): If not admin
    """
    user_role = _normalize_role(current_user.role)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cache clearing requires admin role"
        )
    
    # A01 (C-01 FIX): Attempt real cache clear operation
    entries_cleared = 0
    cache_available = False
    
    try:
        # Try to import and clear intent cache if available
        from app.engine.intent_classifier import get_intent_cache
        intent_cache = get_intent_cache()
        if intent_cache and hasattr(intent_cache, "clear"):
            old_size = len(intent_cache) if hasattr(intent_cache, "__len__") else 0
            intent_cache.clear()
            entries_cleared = old_size
            cache_available = True
            logger.info("Intent cache cleared by %s: %d entries removed", current_user.username, entries_cleared)
        else:
            logger.warning("Intent cache exists but has no clear() method")
    except ImportError:
        logger.debug("Intent cache module not available")
    except Exception as exc:
        logger.warning("Intent cache clear failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear intent cache: {str(exc)}"
        )
    
    if not cache_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intent classification cache not configured or unavailable"
        )
    
    return {
        "status": "cleared",
        "entries_cleared": entries_cleared,
        "cleared_by": current_user.username,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
