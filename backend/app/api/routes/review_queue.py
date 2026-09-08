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

from app.compliance.security import get_client_role
from app.db.review_queue_repository import ReviewQueueRepository, get_review_queue_repo
from app.schemas.compliance_models import Role
from app.schemas.review_queue import (
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
    """
    return get_review_queue_repo()


# Who may act on the queue (Task 0.1.3). CAN_REVIEW mirrors the plan's
# can_review() check; CAN_MANAGE mirrors can_manage_reviews() and additionally
# gates assignment, the full queue view, and statistics.
CAN_REVIEW = [Role.REVIEWER, Role.COMPLIANCE_OFFICER, Role.RESOLVER, Role.ADMIN]
CAN_MANAGE = [Role.COMPLIANCE_OFFICER, Role.ADMIN]


def _role_guard(allowed: List[Role]):
    """Build a FastAPI dependency that enforces role membership.

    The @require_roles decorator used elsewhere cannot be applied here: this
    module uses `from __future__ import annotations`, so FastAPI resolves the
    wrapper's string annotations against the decorator's module globals and
    loses the request-body types.
    """
    def guard(current_role: Role = Depends(get_client_role)) -> Role:
        if current_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {[r.value for r in allowed]}",
            )
        return current_role

    return guard


require_review_role = _role_guard(CAN_REVIEW)
require_manage_role = _role_guard(CAN_MANAGE)


def get_current_user_id(
    x_user_id: Optional[str] = Header(default="analyst_default"),
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Extract authenticated user identifier from headers with graceful defaults."""
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    return "analyst_default"


@router.post("/escalate", response_model=Dict[str, Any], dependencies=[Depends(require_review_role)])
async def escalate_answer(
    payload: EscalateRequest,
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
    user_id: str = Depends(get_current_user_id),
):
    """Escalate a low-confidence or problematic answer to the review queue."""
    metadata = payload.metadata or {}
    metadata["escalated_by"] = user_id

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
    limit: int = Query(20, ge=1, le=100),
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
    user_id: str = Depends(get_current_user_id),
):
    """Get pending reviews assigned to current user."""
    items = await repo.get_pending_for_user(user_id, limit=limit)
    return {
        "count": len(items),
        "items": [item.model_dump() for item in items]
    }


@router.get("/unassigned", response_model=Dict[str, Any], dependencies=[Depends(require_manage_role)])
async def get_unassigned_reviews(
    limit: int = Query(20, ge=1, le=100),
    repo: ReviewQueueRepository = Depends(review_repo_dependency),
):
    """Get unassigned reviews waiting in queue."""
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
    """Assign a review queue item to a specific reviewer."""
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
    """Approve a review item, record verdict and notes."""
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
    """Reject a review item and return it to the pending queue with rejection reasons."""
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
    """Get aggregated statistics on review items and resolution times."""
    stats = await repo.get_stats(time_range_days=days)
    return stats
