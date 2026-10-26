# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
review_queue.py
===============
FastAPI routing for Human Review Queue management.
Allows compliance officers and analysts to inspect, assign, approve, and reject
low-confidence or flagged context engine answers.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.api.deps import CurrentUser, get_current_user
from app.compliance.security import get_client_role
from app.db.review_queue_repository import ReviewQueueRepository, get_review_queue_repo
from app.models.compliance_models import Role
from app.models.review_queue import (
    ApproveRequest,
    AssignRequest,
    EscalateRequest,
    RejectRequest,
    ReviewQueueItem,
    ReviewReason,
    ReviewStatus,
)

logger = logging.getLogger("app.api.review_queue")

router = APIRouter(prefix="/review-queue", tags=["review"])


def review_repo_dependency() -> ReviewQueueRepository:
    """Zero-argument dependency wrapper.

    get_review_queue_repo() takes an optional `db` argument; using it directly as
    a dependency made FastAPI expose `db` as a query parameter on every
    review-queue endpoint.

    Returns:
        ReviewQueueRepository: Resulting ReviewQueueRepository instance.
    """
    return get_review_queue_repo()


# Who may act on the queue (Task 0.1.3). CAN_REVIEW mirrors the plan's
# can_review() check; CAN_MANAGE mirrors can_manage_reviews() and additionally
# gates assignment, the full queue view, and statistics.
CAN_REVIEW = [Role.REVIEWER, Role.COMPLIANCE_OFFICER, Role.RESOLVER, Role.ADMIN]
CAN_MANAGE = [Role.COMPLIANCE_OFFICER, Role.ADMIN]


def _role_guard(allowed: List[Role]):
    """Build a FastAPI dependency that enforces role membership with mandatory authentication.

    Args:
        allowed (List[Role]): The allowed.

    Returns:
        Result of the operation.
    """
    def guard(
        current_user: CurrentUser,
        current_role: Role = Depends(get_client_role),
    ) -> Role:
        """Guard.

        Args:
            current_user (CurrentUser): Authenticated user context.
            current_role (Role): The current role.

        Returns:
            Role: Resulting Role instance.
        """
        # Map user's actual role from authenticated token identity
        user_role = current_role
        role_lower = (current_user.role or "").lower()
        if "admin" in role_lower:
            user_role = Role.ADMIN
        elif "compliance" in role_lower or "regulatory" in role_lower:
            user_role = Role.COMPLIANCE_OFFICER
        elif "review" in role_lower:
            user_role = Role.REVIEWER
        elif "resolv" in role_lower:
            user_role = Role.RESOLVER

        if user_role not in allowed and current_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {[r.value for r in allowed]}",
            )
        return user_role

    return guard


require_review_role = _role_guard(CAN_REVIEW)
require_manage_role = _role_guard(CAN_MANAGE)


def get_current_user_id(
    current_user: CurrentUser,
) -> str:
    """Extract authenticated user identifier from token (eliminates header spoofing and defaults).

    Args:
        current_user (CurrentUser): Authenticated user context.

    Returns:
        str: Resulting str instance.
    """
    return current_user.username



@router.post("/escalate", response_model=Dict[str, Any], dependencies=[Depends(require_review_role)])
async def escalate_answer(
    payload: EscalateRequest,
    current_user: CurrentUser,
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
):
    """Escalate a low-confidence or problematic answer to the review queue.

    Args:
        payload (EscalateRequest): Request or event payload.
        current_user (CurrentUser): Authenticated user context.
        repo (ReviewQueueRepository): The repo.

    Returns:
        Result of the operation.
    """
    metadata = payload.metadata or {}
    metadata["escalated_by"] = current_user.username
    if current_user.tenant_id:
        metadata["tenant_id"] = current_user.tenant_id

    item = ReviewQueueItem(
        response_id=payload.response_id,
        query=payload.query,
        user_answer=payload.user_answer,
        reason=payload.reason,
        confidence_score=payload.confidence_score,
        priority=payload.priority or 5,
        metadata=metadata,
    )

    # Only honour an explicitly supplied priority; otherwise let the repository
    # derive it from the escalation reason and confidence score.
    item_id = await repo.enqueue(item, auto_priority=payload.priority is None)
    logger.info("Escalated response %s to review queue (item_id=%s, reason=%s)", payload.response_id, item_id, payload.reason)
    return {"item_id": item_id, "status": "queued", "priority": item.priority}


@router.get("/pending", response_model=Dict[str, Any], dependencies=[Depends(require_review_role)])
async def get_pending_reviews(
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
):
    """Get pending reviews assigned to current user.

    Args:
        current_user (CurrentUser): Authenticated user context.
        limit (int): Maximum number of records to return.
        repo (ReviewQueueRepository): The repo.

    Returns:
        The requested pending reviews.
    """
    items = await repo.get_pending_for_user(
        current_user.username,
        tenant_id=current_user.tenant_id,
        limit=limit,
    )
    return {
        "count": len(items),
        "items": [item.model_dump() for item in items]
    }


@router.get("/unassigned", response_model=Dict[str, Any], dependencies=[Depends(require_manage_role)])
async def get_unassigned_reviews(
    limit: int = Query(20, ge=1, le=100),
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
):
    """Get unassigned reviews waiting in queue.

    Args:
        limit (int): Maximum number of records to return.
        repo (ReviewQueueRepository): The repo.

    Returns:
        The requested unassigned reviews.
    """
    items = await repo.get_unassigned(limit=limit)
    return {
        "count": len(items),
        "items": [item.model_dump() for item in items]
    }


@router.post("/{item_id}/assign", response_model=Dict[str, Any], dependencies=[Depends(require_manage_role)])
async def assign_review(
    item_id: str,
    payload: AssignRequest,
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
):
    """Assign a review queue item to a specific reviewer.

    Args:
        item_id (str): Unique identifier of the item.
        payload (AssignRequest): Request or event payload.
        repo (ReviewQueueRepository): The repo.

    Returns:
        Result of the operation.
    """
    success = await repo.assign_to_user(item_id, payload.user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item {item_id} not found"
        )
    return {"status": "assigned", "item_id": item_id, "assigned_to": payload.user_id}


@router.post("/{item_id}/approve", response_model=Dict[str, Any], dependencies=[Depends(require_review_role)])
async def approve_review(
    item_id: str,
    payload: ApproveRequest,
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
    user_id: str = Depends(get_current_user_id),
):
    """Approve a review item, record verdict and notes.

    Args:
        item_id (str): Unique identifier of the item.
        payload (ApproveRequest): Request or event payload.
        repo (ReviewQueueRepository): The repo.
        user_id (str): Unique identifier of the user.

    Returns:
        Result of the operation.
    """
    success = await repo.approve(
        item_id=item_id,
        verdict=payload.verdict,
        notes=payload.notes or "",
        reviewer_id=user_id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item {item_id} not found"
        )

    logger.info("Review queue item %s approved by %s with verdict '%s'", item_id, user_id, payload.verdict)
    return {"status": "approved", "item_id": item_id, "verdict": payload.verdict}


@router.post("/{item_id}/reject", response_model=Dict[str, Any], dependencies=[Depends(require_review_role)])
async def reject_review(
    item_id: str,
    payload: RejectRequest,
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
    user_id: str = Depends(get_current_user_id),
):
    """Reject a review item and return it to the pending queue with rejection reasons.

    Args:
        item_id (str): Unique identifier of the item.
        payload (RejectRequest): Request or event payload.
        repo (ReviewQueueRepository): The repo.
        user_id (str): Unique identifier of the user.

    Returns:
        Result of the operation.
    """
    success = await repo.reject(
        item_id=item_id,
        reason=payload.reason,
        reviewer_id=user_id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item {item_id} not found"
        )

    logger.info("Review queue item %s rejected by %s (returned to queue)", item_id, user_id)
    return {"status": "rejected", "item_id": item_id, "reason": payload.reason}


@router.get("/stats", response_model=Dict[str, Any], dependencies=[Depends(require_manage_role)])
async def get_review_stats(
    days: int = Query(7, ge=1, le=90),
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
):
    """Get aggregated statistics on review items and resolution times.

    Args:
        days (int): Collection or list of days.
        repo (ReviewQueueRepository): The repo.

    Returns:
        The requested review stats.
    """
    stats = await repo.get_stats(time_range_days=days)
    return stats
