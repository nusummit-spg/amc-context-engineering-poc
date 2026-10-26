# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================
#app/api/routes/feedback.py
"""
feedback.py
===========
API router for per-response human feedback capture and retrieval.
Endpoints:
  POST /api/feedback
  GET  /api/feedback
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

import uuid
import json
from datetime import datetime, timezone

from app.compliance.failure_taxonomy import FAILURE_TAXONOMY, VALID_CODES
from app.models.feedback_quality import FeedbackQualityMetrics
from app.models.feedback_quality import FeedbackQualityMetrics
from app.models.feedback_analytics import FeedbackCategoryAnalytics
from app.models.response_quality import ResponseQualityMetrics
from app.models.compliance_models import Role
from app.api.deps import CurrentUser, OptionalCurrentUser
from app.config import get_settings
from app.models.feedback import (
    CategoryBreakdownItem,
    FeedbackIn,
    FeedbackOut,
    FeedbackStatusCheckResponse,
    FeedbackIssueDetailOut,
    FeedbackIssueListOut,
    IssueRepairTransitionRequest,
    IssueRepairTransitionResponse,
    IssueStatusUpdateRequest,
    MyFeedbackItemOut,
    MyFeedbackListOut,
)
from app.compliance.metrics_store import get_metrics_store
from app.compliance.security import get_client_role, require_roles
from app.core.database import SessionLocal, get_db
from app.feedback import issue_store
from app.feedback.feedback_cache import get_feedback_cache
from app.feedback.intent_matcher import clear_pending_feedback_cache, get_intent_matcher
from app.feedback.issue_matcher import get_issue_matcher
from app.feedback.repair_linkage import get_repair_linkage_service
from app.schemas.response_feedback_table import ResponseFeedback
from sqlalchemy.orm import Session

logger = logging.getLogger("app.api.feedback")

router = APIRouter(prefix="/feedback", tags=["feedback"])




@router.get("/taxonomy", response_model=Dict[str, Any])
def get_failure_taxonomy() -> Dict[str, Any]:
    """Retrieve the failure taxonomy categories with simple user-friendly labels and tooltips.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    return {"categories": FAILURE_TAXONOMY}


@router.get("/telemetry", response_model=Dict[str, Any])
def get_feedback_telemetry(
    current_role: Optional[Role] = Depends(get_client_role),
    current_user: OptionalCurrentUser = None,
) -> Dict[str, Any]:
    """Telemetry dashboard endpoint for feedback status cache hit rate,
    active entries, invalidations, and reconciliation drift size (Phase 5).

    Args:
        current_role (Optional[Role]): The current role.
        current_user (OptionalCurrentUser): Authenticated user context.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    cache = get_feedback_cache()
    telemetry = cache.get_telemetry()
    return {
        "status": "ok",
        "cache": telemetry,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }



@router.get("/pending-notice")
async def get_pending_feedback_notice(
    query: str = Query(..., min_length=1, description="User query to check for pending repair feedback"),
    session_id: Optional[str] = Query(None, description="Current session ID"),
    actor_id: Optional[str] = Query(None, description="Current actor / user ID"),
    db: Session = Depends(get_db),
    current_role: Optional[Role] = Depends(get_client_role),
) -> Dict[str, Any]:
    """Check if query matches an existing feedback entry with pending repair.

    Args:
        query (str): Search query or input text.
        session_id (Optional[str]): Unique identifier of the session.
        actor_id (Optional[str]): Unique identifier of the actor.
        db (Session): Database session instance.
        current_role (Optional[Role]): The current role.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    matcher = get_intent_matcher()
    role_str = (
        current_role.value
        if hasattr(current_role, "value")
        else str(current_role)
        if current_role
        else None
    )
    notice = await matcher.check_pending_feedback(
        query=query,
        session_id=session_id,
        actor_id=actor_id,
        db=db,
        role=role_str,
    )
    return {"pending_feedback_notice": notice}


@router.get("/status", response_model=FeedbackStatusCheckResponse)
def get_feedback_status(
    response_id: Optional[str] = Query(None, description="Response ID to check status for"),
    query: Optional[str] = Query(None, description="User query text to match"),
    query_text: Optional[str] = Query(None, description="Alternative parameter for user query text"),
    tenant_id: Optional[str] = Query(None, description="Tenant ID scope"),
    db: Session = Depends(get_db),
    current_role: Optional[Role] = Depends(get_client_role),
) -> Dict[str, Any]:
    """Check if query (or response_id) matches an open reported issue.
    Returns concise, non-blocking status information for rendering in the feedback modal.

    Args:
        response_id (Optional[str]): Unique identifier of the response.
        query (Optional[str]): Search query or input text.
        query_text (Optional[str]): The query text.
        tenant_id (Optional[str]): Unique identifier of the tenant.
        db (Session): Database session instance.
        current_role (Optional[Role]): The current role.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    effective_query = (query or query_text or "").strip()
    if not effective_query and response_id:
        from app.schemas.query_evidence_table import QueryEvidence
        qe = db.query(QueryEvidence).filter(QueryEvidence.response_id == response_id).first()
        if qe and qe.query_text:
            effective_query = qe.query_text.strip()
        else:
            rf = db.query(ResponseFeedback).filter(ResponseFeedback.response_id == response_id).first()
            if rf and rf.query_text:
                effective_query = rf.query_text.strip()

    if not effective_query:
        return {"has_existing_issue": False}

    settings = get_settings()
    cache = get_feedback_cache()
    if settings.feedback_cache_enabled:
        cached_res = cache.get(tenant_id, effective_query)
        if cached_res is not None:
            if not settings.feedback_category_breakdown_enabled and "category_breakdown" in cached_res:
                resp = dict(cached_res)
                resp.pop("category_breakdown", None)
                return resp
            return cached_res

    matcher = get_issue_matcher()
    match = matcher.lookup(query=effective_query, db=db, tenant_id=tenant_id)
    if not match or not match.matched:
        miss_res = {"has_existing_issue": False}
        if settings.feedback_cache_enabled:
            cache.set(
                tenant_id,
                effective_query,
                miss_res,
                issue_id=None,
                ttl_seconds=settings.feedback_cache_ttl_seconds,
            )
        return miss_res

    result = {
        "has_existing_issue": True,
        "issue_id": match.issue_id,
        "status": match.status,
        "message": match.message or "A similar query has already been reported. The issue is pending review or repair.",
        "match_type": match.match_type,
        "similarity_score": match.similarity_score,
        "contributor_count": match.contributor_count or 1,
    }

    if settings.feedback_category_breakdown_enabled and match.issue_id:
        breakdown = issue_store.get_issue_category_breakdown(db, match.issue_id, limit=5)
        result["category_breakdown"] = breakdown

    if settings.feedback_cache_enabled:
        cache.set(
            tenant_id,
            effective_query,
            result,
            issue_id=match.issue_id,
            ttl_seconds=settings.feedback_cache_ttl_seconds,
        )

    return result



@router.get("/mine", response_model=MyFeedbackListOut)
def get_my_feedback(
    limit: int = Query(50, ge=1, le=200, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    page: Optional[int] = Query(None, ge=1, description="1-indexed page number"),
    page_size: Optional[int] = Query(None, ge=1, le=200, description="Page size"),
    q: Optional[str] = Query(None, description="Search term across query, entities, categories, comments"),
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve feedback issues reported or contributed to by the currently authenticated user.
    Server-side enforced: strictly derived from current_user.username session, never client parameters.
    Contributors are anonymized (also_reported_by_count) and triage actions are omitted (§3, §4, §7.2).
    Supports server-side search (q), status filtering, and pagination (Phase 5).

    Args:
        limit (int): Maximum number of records to return.
        offset (int): Offset index for pagination.
        page (Optional[int]): The page.
        page_size (Optional[int]): The page size.
        q (Optional[str]): The q.
        status (Optional[str]): Target status value.
        current_user (CurrentUser): Authenticated user context.
        db (Session): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    import math
    from app.schemas.feedback_issues_table import FeedbackIssue

    username = current_user.username
    tenant_id = current_user.tenant_id

    page_val = page if isinstance(page, int) else None
    page_size_val = page_size if isinstance(page_size, int) else None
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0
    q_val = q if isinstance(q, str) else None
    status_val = status if isinstance(status, str) else None

    effective_limit = page_size_val or limit_val
    effective_offset = ((page_val - 1) * effective_limit) if page_val else offset_val

    # Query all feedback entries submitted by this user that are linked to an issue
    user_feedbacks = (
        db.query(ResponseFeedback)
        .filter(ResponseFeedback.actor_id == username)
        .order_by(ResponseFeedback.created_at.desc())
        .all()
    )

    feedbacks_by_issue: Dict[str, List[ResponseFeedback]] = {}
    for fb in user_feedbacks:
        if fb.issue_id:
            feedbacks_by_issue.setdefault(fb.issue_id, []).append(fb)

    issue_ids = list(feedbacks_by_issue.keys())
    if not issue_ids:
        return {
            "total": 0,
            "page": 1,
            "page_size": effective_limit,
            "total_pages": 1,
            "items": [],
        }

    query = db.query(FeedbackIssue).filter(FeedbackIssue.issue_id.in_(issue_ids))
    if tenant_id:
        query = query.filter(
            (FeedbackIssue.tenant_id == tenant_id) | (FeedbackIssue.tenant_id.is_(None))
        )

    if status_val and status_val.strip().lower() != "all":
        query = query.filter(FeedbackIssue.status == status_val.strip().lower())

    all_matched_issues = query.order_by(FeedbackIssue.updated_at.desc()).all()

    # Apply search filter q if provided
    if q_val and q_val.strip():
        q_clean = q_val.strip().lower()
        filtered = []
        for issue in all_matched_issues:
            match_canonical = q_clean in (issue.canonical_query_text or "").lower()
            match_id = q_clean in (issue.issue_id or "").lower()
            match_entities = any(q_clean in (e or "").lower() for e in (issue.primary_entities or []))
            # Also check user comments & user categories
            fbs = feedbacks_by_issue.get(issue.issue_id, [])
            match_comments = any(q_clean in (fb.feedback_text or "").lower() for fb in fbs)
            match_cats = False
            for fb in fbs:
                cats = fb.categories if fb.categories is not None else fb.selected_categories
                if isinstance(cats, list) and any(q_clean in (c or "").lower() for c in cats):
                    match_cats = True
                    break
            if match_canonical or match_id or match_entities or match_comments or match_cats:
                filtered.append(issue)
        all_matched_issues = filtered

    total = len(all_matched_issues)
    paged_issues = all_matched_issues[effective_offset : effective_offset + effective_limit]
    total_pages = max(1, math.ceil(total / effective_limit)) if total > 0 else 1
    current_page_num = (effective_offset // effective_limit) + 1

    items = []
    for issue in paged_issues:
        fbs = feedbacks_by_issue.get(issue.issue_id, [])
        user_cats = set()
        user_comments = []
        for fb in fbs:
            cats = fb.categories if fb.categories is not None else fb.selected_categories
            if isinstance(cats, list):
                for c in cats:
                    if c:
                        user_cats.add(c.strip().upper())
            if fb.feedback_text:
                user_comments.append(fb.feedback_text)

        items.append({
            "issue_id": issue.issue_id,
            "canonical_query_text": issue.canonical_query_text,
            "status": issue.status,
            "repair_task_id": issue.repair_task_id,
            "also_reported_by_count": max(0, issue.contributor_count - 1),
            "primary_entities": issue.primary_entities or [],
            "taxonomy_paths": issue.taxonomy_paths or [],
            "user_reported_categories": sorted(list(user_cats)),
            "user_feedback_count": len(fbs),
            "user_feedback_texts": user_comments,
            "created_at": issue.created_at,
            "updated_at": issue.updated_at,
        })

    return {
        "total": total,
        "page": current_page_num,
        "page_size": effective_limit,
        "total_pages": total_pages,
        "items": items,
    }



@router.post("/reconcile-categories", response_model=Dict[str, Any])
@require_roles([Role.ADMIN, Role.COMPLIANCE_OFFICER])
def reconcile_feedback_categories(
    issue_id: Optional[str] = Query(None, description="Optional single issue_id to reconcile"),
    db: Session = Depends(get_db),
    current_role: Role = Depends(get_client_role),
) -> Dict[str, Any]:
    """Trigger reconciliation job to recalculate feedback_issue_category_counts from response_feedback records.
    Guarantees counter consistency against drift (§8).

    Args:
        issue_id (Optional[str]): Unique identifier of the issue.
        db (Session): Database session instance.
        current_role (Role): The current role.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    res = issue_store.reconcile_issue_category_counts(db=db, issue_id=issue_id)
    return res


# ── Issue Lifecycle & Repair Engine Linkage (Phase 3) ─────────────────────────


def is_admin_tier_role(user: Optional[Any], client_role: Optional[Role]) -> bool:
    """Validate that user has an admin-tier role (Admin or Compliance Officer).
    Checks both token-authenticated session and X-User-Role header.

    Args:
        user (Optional[Any]): The user.
        client_role (Optional[Role]): The client role.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    ADMIN_ROLES = {
        "admin",
        "compliance_officer",
        "compliance & regulatory officer",
        "compliance officer",
        "amc_admin",
        "compliance_lead",
    }
    if user:
        role_clean = (getattr(user, "role", "") or "").strip().lower()
        if role_clean in ADMIN_ROLES or "admin" in role_clean or "compliance" in role_clean:
            return True
        return False

    if client_role in [Role.ADMIN, Role.COMPLIANCE_OFFICER]:
        return True

    return False


@router.post("/issues/{issue_id}/repair", response_model=IssueRepairTransitionResponse)
def initiate_issue_repair(
    issue_id: str,
    payload: Optional[IssueRepairTransitionRequest] = None,
    db: Session = Depends(get_db),
    current_role: Optional[Role] = Depends(get_client_role),
    current_user: OptionalCurrentUser = None,
) -> Dict[str, Any]:
    """Transition an issue to 'in_repair' and create or reuse a Repair Engine task (Phase 3).
    Guarantees idempotency (Section 9):
    If the issue already has a repair_task_id, reuses it without duplicate creation.

    Args:
        issue_id (str): Unique identifier of the issue.
        payload (Optional[IssueRepairTransitionRequest]): Request or event payload.
        db (Session): Database session instance.
        current_role (Optional[Role]): The current role.
        current_user (OptionalCurrentUser): Authenticated user context.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    if not is_admin_tier_role(current_user, current_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin-tier role required to initiate repair.",
        )
    linkage = get_repair_linkage_service()
    actor_id = payload.actor_id if payload else None
    if not actor_id and current_user:
        actor_id = current_user.username
    metadata = payload.metadata if payload else None
    try:
        result = linkage.get_or_create_repair_task(
            db=db,
            issue_id=issue_id,
            actor_id=actor_id,
            metadata=metadata,
        )
        get_feedback_cache().invalidate_issue(issue_id)
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(val_err))
    except Exception as exc:
        logger.error("Failed to initiate repair task for issue_id=%s: %s", issue_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate repair task: {str(exc)}",
        )


@router.post("/issues/{issue_id}/status", response_model=IssueRepairTransitionResponse)
def transition_issue_lifecycle_status(
    issue_id: str,
    payload: IssueStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_role: Optional[Role] = Depends(get_client_role),
    current_user: OptionalCurrentUser = None,
) -> Dict[str, Any]:
    """Update lifecycle status of a FeedbackIssue (Section 6 & 9).
    Statuses: reported, under_review, in_repair, resolved, closed, reopened.
    Transitioning to in_repair automatically links/creates repair_task_id.
    Transitioning to reopened clears repair_task_id for fresh triage determination.

    Args:
        issue_id (str): Unique identifier of the issue.
        payload (IssueStatusUpdateRequest): Request or event payload.
        db (Session): Database session instance.
        current_role (Optional[Role]): The current role.
        current_user (OptionalCurrentUser): Authenticated user context.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    if not is_admin_tier_role(current_user, current_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin-tier role required to update issue lifecycle.",
        )
    linkage = get_repair_linkage_service()
    actor_id = payload.actor_id or (current_user.username if current_user else None)
    try:
        result = linkage.transition_issue_status(
            db=db,
            issue_id=issue_id,
            new_status=payload.status,
            resolution_notes=payload.resolution_notes,
            actor_id=actor_id,
        )
        get_feedback_cache().invalidate_issue(issue_id)
        return result
    except ValueError as val_err:
        if "not found" in str(val_err).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(val_err))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(val_err))
    except Exception as exc:
        logger.error("Failed to transition status for issue_id=%s: %s", issue_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to transition issue status: {str(exc)}",
        )


@router.get("/issues/{issue_id}", response_model=FeedbackIssueDetailOut)
def get_feedback_issue(
    issue_id: str,
    db: Session = Depends(get_db),
    current_role: Optional[Role] = Depends(get_client_role),
    current_user: OptionalCurrentUser = None,
) -> Dict[str, Any]:
    """Retrieve full issue metadata, repair task linkage, and linked feedback entries.

    Args:
        issue_id (str): Unique identifier of the issue.
        db (Session): Database session instance.
        current_role (Optional[Role]): The current role.
        current_user (OptionalCurrentUser): Authenticated user context.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    if not is_admin_tier_role(current_user, current_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin-tier role required to view issue details.",
        )
    linkage = get_repair_linkage_service()
    details = linkage.get_issue_details(db, issue_id)
    if not details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FeedbackIssue '{issue_id}' not found",
        )
    return details


@router.get("/issues", response_model=FeedbackIssueListOut)
def list_feedback_issues(
    status: Optional[str] = Query(None, description="Filter by status (reported, under_review, in_repair, resolved, closed, reopened)"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    q: Optional[str] = Query(None, description="Search query across query text, issue ID, entities, or repair task ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    page: Optional[int] = Query(None, ge=1, description="1-indexed page number"),
    page_size: Optional[int] = Query(None, ge=1, le=200, description="Page size"),
    db: Session = Depends(get_db),
    current_role: Optional[Role] = Depends(get_client_role),
    current_user: OptionalCurrentUser = None,
) -> Dict[str, Any]:
    """List feedback issues with optional status/tenant filtering, server-side search (q), and pagination.

    Args:
        status (Optional[str]): Target status value.
        tenant_id (Optional[str]): Unique identifier of the tenant.
        q (Optional[str]): The q.
        limit (int): Maximum number of records to return.
        offset (int): Offset index for pagination.
        page (Optional[int]): The page.
        page_size (Optional[int]): The page size.
        db (Session): Database session instance.
        current_role (Optional[Role]): The current role.
        current_user (OptionalCurrentUser): Authenticated user context.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    if not is_admin_tier_role(current_user, current_role):
        raise HTTPException(
            status_code=403,
            detail="Access denied. Admin-tier role required to view issue triage queue.",
        )

    import math
    from app.schemas.feedback_issues_table import FeedbackIssue

    page_val = page if isinstance(page, int) else None
    page_size_val = page_size if isinstance(page_size, int) else None
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0
    q_val = q if isinstance(q, str) else None
    status_val = status if isinstance(status, str) else None

    effective_limit = page_size_val or limit_val
    effective_offset = ((page_val - 1) * effective_limit) if page_val else offset_val

    query = db.query(FeedbackIssue)
    if status_val and status_val.strip().lower() != "all":
        query = query.filter(FeedbackIssue.status == status_val.strip().lower())
    effective_tenant = tenant_id or (getattr(current_user, "tenant_id", None) if current_user else None)
    if effective_tenant:
        query = query.filter(
            (FeedbackIssue.tenant_id == effective_tenant) | (FeedbackIssue.tenant_id.is_(None))
        )
    if q_val and q_val.strip():
        search_pattern = f"%{q_val.strip()}%"
        query = query.filter(
            FeedbackIssue.canonical_query_text.ilike(search_pattern)
            | FeedbackIssue.issue_id.ilike(search_pattern)
            | FeedbackIssue.primary_entities.ilike(search_pattern)
            | FeedbackIssue.repair_task_id.ilike(search_pattern)
        )

    total = query.count()
    items_db = query.order_by(FeedbackIssue.created_at.desc()).offset(effective_offset).limit(effective_limit).all()
    linkage = get_repair_linkage_service()
    items = []
    for item in items_db:
        details = linkage.get_issue_details(db, item.issue_id)
        if details:
            items.append(details)

    total_pages = max(1, math.ceil(total / effective_limit)) if total > 0 else 1
    current_page_num = (effective_offset // effective_limit) + 1

    return {
        "total": total,
        "page": current_page_num,
        "page_size": effective_limit,
        "total_pages": total_pages,
        "items": items,
    }



@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
@require_roles([Role.REVIEWER, Role.COMPLIANCE_OFFICER, Role.ADMIN])
def submit_feedback(
    payload: FeedbackIn,
    background_tasks: BackgroundTasks,
    current_role: Role = Depends(get_client_role),
    current_user: OptionalCurrentUser = None,
) -> Dict[str, Any]:

    """Record or update human failure taxonomy feedback for an LLM response.
    Requires at least one failure code OR non-empty commentary.
    Upserts by (response_id, actor_id) directly to data.db (single source of truth).

    Args:
        payload (FeedbackIn): Request or event payload.
        background_tasks (BackgroundTasks): Background tasks runner for deferred execution.
        current_role (Role): The current role.
        current_user (OptionalCurrentUser): Authenticated user context.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    feedback_text_clean = (payload.feedback_text or "").strip()
    if not payload.selected_categories and not feedback_text_clean:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Submit at least one category or a comment.",
        )

    # Resolve actor from authenticated session if not explicitly in payload
    effective_actor_id = payload.actor_id or (current_user.username if current_user else None)

    # Cancel active timer if one is running for this query/session
    try:
        from app.feedback.feedback_timer import get_feedback_timer_manager
        timer_mgr = get_feedback_timer_manager()
        timer_turn = timer_mgr._pending_turns.get(payload.session_id)
        if timer_turn and timer_turn.response_id == payload.response_id:
            if timer_turn.timer_task and not timer_turn.timer_task.done():
                timer_turn.timer_task.cancel()
                logger.info(
                    "[TIMER_CANCELLED] Cancelled active timer for session_id=%s, response_id=%s due to incoming feedback",
                    payload.session_id,
                    payload.response_id,
                )
            timer_turn.is_recorded = True
    except Exception as timer_err:
        logger.debug("FeedbackTimer check notice in submit_feedback: %s", timer_err)

    db = SessionLocal()
    try:
        # Contextual Feedback Status Awareness (Phase 1): Match or create FeedbackIssue
        issue_matcher = get_issue_matcher()
        effective_query_for_issue = (payload.query_text or "").strip()
        if not effective_query_for_issue and payload.response_id:
            from app.schemas.query_evidence_table import QueryEvidence
            qe = db.query(QueryEvidence).filter(QueryEvidence.response_id == payload.response_id).first()
            if qe and qe.query_text:
                effective_query_for_issue = qe.query_text.strip()

        issue_id = None
        issue_status = None
        was_matched = False
        match_type = None

        if effective_query_for_issue:
            try:
                issue, m_type, matched = issue_matcher.find_or_create(
                    query=effective_query_for_issue,
                    db=db,
                    actor_id=effective_actor_id,
                )
                issue_id = issue.issue_id
                issue_status = issue.status
                was_matched = matched
                match_type = m_type
            except Exception as match_err:
                logger.warning("IssueMatcher find_or_create error: %s", match_err)

        # Check if feedback already exists for this query/session (handles timer expiration or previous query turns)
        existing = db.query(ResponseFeedback).filter(
            (ResponseFeedback.response_id == payload.response_id) |
            ((ResponseFeedback.session_id == payload.session_id) & (ResponseFeedback.interaction_id == payload.interaction_id))
        ).first()
        
        now_iso = datetime.now(timezone.utc).isoformat()
        feedback_id = existing.feedback_id if existing else f"fb_{uuid.uuid4().hex[:12]}"
        
        if existing:
            # Late or on-time feedback updating existing record without duplicate
            logger.info(
                "[LATE_FEEDBACK_HANDLED] Identified existing feedback record feedback_id=%s for session_id=%s, response_id=%s. Updating record without duplicates.",
                existing.feedback_id,
                payload.session_id,
                payload.response_id,
            )
            old_categories = existing.categories if existing.categories is not None else existing.selected_categories
            existing.interaction_id = payload.interaction_id or existing.interaction_id
            existing.session_id = payload.session_id
            existing.turn_number = payload.turn_number or existing.turn_number
            existing.query_text = payload.query_text or existing.query_text or (effective_query_for_issue or None)
            existing.selected_categories = payload.selected_categories
            existing.categories = payload.selected_categories
            existing.feedback_text = feedback_text_clean if feedback_text_clean else existing.feedback_text
            existing.actor_id = effective_actor_id or existing.actor_id
            existing.actor_role = payload.actor_role or existing.actor_role
            existing.client_timestamp = payload.client_timestamp or existing.client_timestamp
            if issue_id:
                existing.issue_id = issue_id
                existing.match_type = match_type
                # Atomic category count update in the same transaction (Phase 1)
                issue_store.record_issue_categories(
                    db=db,
                    issue_id=issue_id,
                    category_codes=payload.selected_categories,
                    old_category_codes=old_categories,
                )
            existing.updated_at = now_iso
            # Note: SQLite WAL mode provides transaction-level isolation.
            # Concurrent updates are serialized at the database transaction level with a 30s busy timeout.
            # For fine-grained row-level locking (SELECT FOR UPDATE) under high concurrency, migrate to PostgreSQL.
            db.commit()
            logger.info(
                "[RECORD_UPDATED] Updated feedback record feedback_id=%s in data.db for response_id=%s",
                existing.feedback_id,
                payload.response_id,
            )
            logger.info(
                "[DUPLICATE_PREVENTED] Prevented duplicate feedback insertion for session_id=%s, response_id=%s; record feedback_id=%s updated.",
                payload.session_id,
                payload.response_id,
                existing.feedback_id,
            )
        else:
            # Create new feedback record
            new_feedback = ResponseFeedback(
                feedback_id=feedback_id,
                response_id=payload.response_id,
                interaction_id=payload.interaction_id,
                session_id=payload.session_id,
                turn_number=payload.turn_number,
                query_text=payload.query_text or effective_query_for_issue or None,
                actor_id=effective_actor_id,
                actor_role=payload.actor_role,
                selected_categories=payload.selected_categories,
                categories=payload.selected_categories,
                feedback_text=feedback_text_clean if feedback_text_clean else None,
                client_timestamp=payload.client_timestamp,
                issue_id=issue_id,
                match_type=match_type,
                created_at=now_iso,
                updated_at=now_iso,
            )
            db.add(new_feedback)
            # Atomic category count update in the same transaction (Phase 1)
            if issue_id and payload.selected_categories:
                issue_store.record_issue_categories(
                    db=db,
                    issue_id=issue_id,
                    category_codes=payload.selected_categories,
                )
            db.commit()
            logger.info(
                "[RECORD_INSERTED] Inserted feedback record into data.db: feedback_id=%s, response_id=%s, session_id=%s, issue_id=%s",
                feedback_id,
                payload.response_id,
                payload.session_id,
                issue_id,
            )

        # Invalidate in-memory query notice cache and status cache so subsequent checks reflect new submission
        try:
            clear_pending_feedback_cache(suppress_prior_feedbacks=False)
            if issue_id:
                get_feedback_cache().invalidate_issue(issue_id)
            from app.retrieval.cache import get_semantic_cache
            get_semantic_cache().clear()
        except Exception as cache_err:
            logger.debug("Failed to clear feedback cache in submit_feedback: %s", cache_err)
        
        result = {

            "feedback_id": feedback_id,
            "response_id": payload.response_id,
            "stored_at": now_iso,
            "status": "recorded",
            "issue_id": issue_id,
            "issue_status": issue_status,
            "was_matched_to_existing_issue": was_matched,
            "match_type": match_type,
        }

        # Automatically score feedback quality and assign priority tier
        metrics_store = get_metrics_store()
        quality_eval = metrics_store.evaluate_feedback_quality(
            feedback_id=feedback_id,
            response_id=payload.response_id,
            feedback_text=feedback_text_clean,
            selected_categories=payload.selected_categories,
            actor_role=payload.actor_role,
        )
        result["priority_tier"] = quality_eval.priority_tier
        result["signal_quality_score"] = quality_eval.signal_quality_score

        # Track 8 + Track 6: Extract structured claims and register shadow patch
        if feedback_text_clean:
            try:
                from app.feedback import get_ner_pipeline
                from app.graph.correction_patch_layer import get_correction_patch_layer
                ner = get_ner_pipeline()
                claim = ner.extract_structured_claim(
                    feedback_text=feedback_text_clean,
                    original_query=payload.query_text
                )
                if claim and claim.resolved_entity_id and claim.attribute and claim.asserted_value:
                    patch_layer = get_correction_patch_layer()
                    patch_layer.add_correction(
                        entity_id=claim.resolved_entity_id,
                        attribute=claim.attribute,
                        canonical_value=claim.rejected_value or "canonical",
                        corrected_value=claim.asserted_value,
                        confidence=claim.confidence,
                        provenance={
                            "feedback_id": feedback_id,
                            "actor_id": payload.actor_id,
                            "source": "User Feedback Submission"
                        },
                        approved=False
                    )
                    logger.info("Auto-registered correction patch for %s.%s = %s",
                                claim.resolved_entity_id, claim.attribute, claim.asserted_value)
            except Exception as claim_exc:
                logger.debug("Structured claim extraction notice: %s", claim_exc)

        # Trigger human-feedback-loop in background
        try:
            from app.services.feedback import trigger_feedback_loop
            background_tasks.add_task(
                trigger_feedback_loop,
                feedback_id=feedback_id,
                session_id=payload.session_id,
                response_id=payload.response_id,
                source="active",
            )
        except Exception as fb_loop_exc:
            logger.warning("Could not queue feedback loop task: %s", fb_loop_exc)

        return result
    except Exception as exc:
        db.rollback()
        logger.error("Failed to store response feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback in database. Please retry.",
        )
    finally:
        db.close()


@router.get("", response_model=List[Dict[str, Any]])
def get_feedback(
    response_id: Optional[str] = Query(None, description="Filter by response ID"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    limit: int = Query(50, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """Retrieve stored feedback records from data.db, optionally filtered by response_id or session_id.

    Args:
        response_id (Optional[str]): Unique identifier of the response.
        session_id (Optional[str]): Unique identifier of the session.
        limit (int): Maximum number of records to return.

    Returns:
        List[Dict[str, Any]]: List of resulting items or records.
    """
    db = SessionLocal()
    try:
        query = db.query(ResponseFeedback)
        
        if response_id:
            query = query.filter(ResponseFeedback.response_id == response_id)
        elif session_id:
            query = query.filter(ResponseFeedback.session_id == session_id)
        
        results = query.order_by(ResponseFeedback.updated_at.desc()).limit(limit).all()
        
        feedback_list = []
        for fb in results:
            feedback_list.append({
                "feedback_id": fb.feedback_id,
                "response_id": fb.response_id,
                "interaction_id": fb.interaction_id,
                "session_id": fb.session_id,
                "turn_number": fb.turn_number,
                "query_text": fb.query_text,
                "actor_id": fb.actor_id,
                "actor_role": fb.actor_role,
                "selected_categories": fb.selected_categories,
                "categories": fb.categories or fb.selected_categories,
                "feedback_text": fb.feedback_text,
                "issue_id": fb.issue_id,
                "match_type": fb.match_type,
                "client_timestamp": fb.client_timestamp,
                "created_at": fb.created_at,
                "updated_at": fb.updated_at,
            })
        
        return feedback_list
    except Exception as exc:
        logger.error("Failed to query feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve feedback records.",
        )
    finally:
        db.close()


# =============================================================================
# Phase 1 Foundation Layer Feedback Metrics Endpoints
# =============================================================================

@router.get("/category-analytics", response_model=List[FeedbackCategoryAnalytics])
def get_feedback_category_analytics(
    period: str = Query(default="2024-09", description="Reporting period (e.g. 2024-09, 2024-09-week-1)")
) -> List[FeedbackCategoryAnalytics]:
    """Retrieve F01-F12 category frequency, trend, and velocity analytics for a reporting period.

    Args:
        period (str): The period.

    Returns:
        List[FeedbackCategoryAnalytics]: List of resulting items or records.
    """
    metrics_store = get_metrics_store()
    return metrics_store.get_category_analytics(period=period)


@router.post("/category-analytics/refresh", response_model=List[FeedbackCategoryAnalytics])
@require_roles([Role.ADMIN, Role.COMPLIANCE_OFFICER])
def refresh_feedback_category_analytics(
    period: str = Query(default="2024-09", description="Reporting period to recalculate"),
    current_role: Role = Depends(get_client_role),
) -> List[FeedbackCategoryAnalytics]:
    """Trigger on-demand recalculation and aggregation of category analytics.

    Args:
        period (str): The period.
        current_role (Role): The current role.

    Returns:
        List[FeedbackCategoryAnalytics]: List of resulting items or records.
    """
    metrics_store = get_metrics_store()
    return metrics_store.refresh_category_analytics(period=period)


@router.get("/high-priority", response_model=List[FeedbackQualityMetrics])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN])
def get_high_priority_feedback(
    limit: int = Query(default=20, ge=1, le=100, description="Max high-priority items to return"),
    current_role: Role = Depends(get_client_role),
) -> List[FeedbackQualityMetrics]:
    """Fetch prioritized P0 (Critical/Regulatory) and P1 (High) feedback items for immediate triage.

    Args:
        limit (int): Maximum number of records to return.
        current_role (Role): The current role.

    Returns:
        List[FeedbackQualityMetrics]: List of resulting items or records.
    """
    metrics_store = get_metrics_store()
    return metrics_store.get_high_priority_feedback(limit=limit)


@router.get("/responses/{response_id}/quality-score", response_model=ResponseQualityMetrics)
def get_response_quality_metrics(response_id: str) -> ResponseQualityMetrics:
    """Fetch composite ResponseQualityMetrics and Traditional vs ContextGraph delta for a response.

    Args:
        response_id (str): Unique identifier of the response.

    Returns:
        ResponseQualityMetrics: ResponseQualityMetrics object containing the operation result.
    """
    metrics_store = get_metrics_store()
    return metrics_store.get_response_quality(response_id=response_id)


@router.get("/{feedback_id}/quality-metrics", response_model=FeedbackQualityMetrics)
def get_feedback_quality_metrics(feedback_id: str) -> FeedbackQualityMetrics:
    """Fetch detail score, clarity, credibility, actionability, and priority tier for a specific feedback ID.

    Args:
        feedback_id (str): Unique identifier of the feedback.

    Returns:
        FeedbackQualityMetrics: Resulting FeedbackQualityMetrics instance.
    """
    metrics_store = get_metrics_store()
    metrics = metrics_store.get_feedback_quality(feedback_id=feedback_id)
    if not metrics:
        raise HTTPException(
            status_code=404,
            detail=f"Feedback quality metrics not found for feedback ID: {feedback_id}"
        )
    return metrics


class FeedbackQualityUpdateIn(BaseModel):
    priority_tier: Optional[str] = Field(None, description="P0, P1, P2, P3")
    action_difficulty: Optional[str] = Field(None, description="LOW, MEDIUM, HIGH")
    is_actionable: Optional[bool] = Field(None, description="Whether actionable")
    review_confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence rating")


@router.patch("/{feedback_id}/quality-metrics", response_model=FeedbackQualityMetrics)
@require_roles([Role.REVIEWER, Role.COMPLIANCE_OFFICER, Role.ADMIN])
def update_feedback_quality_assessment(
    feedback_id: str,
    update_in: FeedbackQualityUpdateIn,
    current_role: Role = Depends(get_client_role),
) -> FeedbackQualityMetrics:
    """Update feedback quality scoring or priority tier assignment.

    Args:
        feedback_id (str): Unique identifier of the feedback.
        update_in (FeedbackQualityUpdateIn): The update in.
        current_role (Role): The current role.

    Returns:
        FeedbackQualityMetrics: Resulting FeedbackQualityMetrics instance.
    """
    metrics_store = get_metrics_store()
    updated = metrics_store.update_feedback_quality(
        feedback_id=feedback_id,
        update_data=update_in.model_dump(exclude_unset=True)
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Feedback quality record not found for feedback ID: {feedback_id}"
        )
    return updated


class FollowUpDetectionIn(BaseModel):
    session_id: str = Field(..., description="Session identifier")
    previous_response_id: str = Field(..., description="Response ID being corrected")
    follow_up_query: str = Field(..., min_length=1, description="User's follow-up query text")
    original_response: Optional[str] = Field(None, description="Original response text if available")
    original_query: Optional[str] = Field(None, description="Original query text if available")
    session_history: Optional[List[str]] = Field(default=None, description="Optional previous queries in session")


FollowUpDetectionRequest = FollowUpDetectionIn


_dissatisfaction_detector = None


def get_dissatisfaction_detector():
    """Retrieve dissatisfaction detector.

    Returns:
        The requested dissatisfaction detector.
    """
    global _dissatisfaction_detector
    if _dissatisfaction_detector is None:
        from app.feedback.dissatisfaction_detector import DissatisfactionDetector
        _dissatisfaction_detector = DissatisfactionDetector()
    return _dissatisfaction_detector


async def run_follow_up_detection_logic(
    session_id: str,
    previous_response_id: str,
    follow_up_query: str,
    original_query: Optional[str] = "",
    original_response: Optional[str] = "",
    session_history: Optional[List[str]] = None,
    current_role_value: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None,
) -> Dict[str, Any]:
    """Core reusable logic to detect if a follow-up query is an implicit correction attempt.
    If detected, auto-creates structured feedback in data.db and registers a provisional
    patch in CorrectionPatchLayer (passive self-healing).

    Args:
        session_id (str): Unique identifier of the session.
        previous_response_id (str): Unique identifier of the previous response.
        follow_up_query (str): The follow up query.
        original_query (Optional[str]): The original query.
        original_response (Optional[str]): The original response.
        session_history (Optional[List[str]]): The session history.
        current_role_value (Optional[str]): The current role value.
        background_tasks (Optional[BackgroundTasks]): Background tasks runner for deferred execution.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    db = SessionLocal()
    try:
        # Retrieve previous interaction from data.db
        prev_interaction = db.query(ResponseFeedback).filter(
            (ResponseFeedback.response_id == previous_response_id) &
            (ResponseFeedback.session_id == session_id)
        ).order_by(ResponseFeedback.updated_at.desc()).first()

        orig_query = original_query or (prev_interaction.query_text if prev_interaction else "") or ""
        orig_resp = original_response or (prev_interaction.feedback_text if prev_interaction else "") or ""

        detector = get_dissatisfaction_detector()
        try:
            is_correction, claim = detector.is_correction_attempt(
                follow_up_query=follow_up_query,
                original_response=orig_resp,
                original_query=orig_query,
                previous_queries=session_history or []
            )
        except Exception as exc:
            logger.error("Dissatisfaction detection failed: %s", exc, exc_info=True)
            return {
                "is_correction": False,
                "correction_detected": False,
                "feedback_created": False,
                "auto_created_feedback": False,
                "confidence": 0.0,
                "error": str(exc),
            }

        if is_correction and claim:
            target_entity_id = claim.entity_id
            if not target_entity_id and claim.entity_name:
                try:
                    from app.feedback.fund_name_matcher import get_fund_name_matcher
                    matcher = get_fund_name_matcher()
                    match_res = matcher.match_fund(claim.entity_name)
                    if match_res and match_res.get("isin"):
                        target_entity_id = match_res["isin"]
                except Exception as match_exc:
                    logger.debug("Fund matching notice in follow-up: %s", match_exc)
                if not target_entity_id:
                    target_entity_id = claim.entity_name

            claim_dict = {
                "entity_id": target_entity_id,
                "entity_name": claim.entity_name,
                "attribute": claim.attribute,
                "asserted_value": claim.asserted_value,
                "rejected_value": claim.rejected_value,
                "raw_text": claim.raw_text,
                "confidence": claim.confidence
            }
            try:
                role_val = current_role_value or Role.ADMIN.value
                now_iso = datetime.now(timezone.utc).isoformat()
                existing = db.query(ResponseFeedback).filter(
                    (ResponseFeedback.response_id == previous_response_id) &
                    (ResponseFeedback.session_id == session_id)
                ).order_by(ResponseFeedback.updated_at.desc()).first()

                if not existing:
                    existing = db.query(ResponseFeedback).filter(
                        (ResponseFeedback.response_id == previous_response_id) &
                        (ResponseFeedback.actor_id == role_val)
                    ).first()
                
                feedback_id = existing.feedback_id if existing else f"fb_{uuid.uuid4().hex[:12]}"
                
                if existing:
                    existing.selected_categories = ["F08"]
                    existing.feedback_text = claim.raw_text
                    existing.automated_category = "auto_correction_detected"
                    existing.automated_confidence = claim.confidence
                    if not existing.actor_id:
                        existing.actor_id = role_val
                        existing.actor_role = role_val
                    existing.updated_at = now_iso
                else:
                    new_feedback = ResponseFeedback(
                        feedback_id=feedback_id,
                        response_id=previous_response_id,
                        interaction_id=f"inter_{uuid.uuid4().hex[:8]}",
                        session_id=session_id,
                        turn_number=prev_interaction.turn_number if prev_interaction else 1,
                        query_text=orig_query,
                        actor_id=role_val,
                        actor_role=role_val,
                        selected_categories=["F08"],
                        feedback_text=claim.raw_text,
                        automated_category="auto_correction_detected",
                        automated_confidence=claim.confidence,
                        created_at=now_iso,
                        updated_at=now_iso,
                    )
                    db.add(new_feedback)
                
                db.commit()

                # Auto-register provisional correction in CorrectionPatchLayer
                patch_id = None
                if target_entity_id and claim.attribute and claim.asserted_value:
                    try:
                        from app.graph.correction_patch_layer import get_correction_patch_layer
                        patch_layer = get_correction_patch_layer()
                        patch_id = patch_layer.add_correction(
                            entity_id=target_entity_id,
                            attribute=claim.attribute,
                            canonical_value=claim.rejected_value or "canonical",
                            corrected_value=claim.asserted_value,
                            confidence=min(claim.confidence * 0.8, 0.75),
                            provenance={
                                "source": "passive_followup_detection",
                                "feedback_id": feedback_id,
                                "session_id": session_id,
                            },
                            approved=False,
                        )
                        logger.info("Auto-registered passive patch %s for %s.%s = %s",
                                    patch_id, target_entity_id, claim.attribute, claim.asserted_value)
                    except Exception as patch_exc:
                        logger.warning("Could not auto-register passive patch: %s", patch_exc)

                # Trigger background feedback loop
                try:
                    from app.services.feedback import trigger_feedback_loop
                    if background_tasks:
                        background_tasks.add_task(
                            trigger_feedback_loop,
                            feedback_id=feedback_id,
                            session_id=session_id,
                            response_id=previous_response_id,
                            source="passive_followup",
                        )
                    else:
                        import asyncio
                        asyncio.create_task(asyncio.to_thread(
                            trigger_feedback_loop,
                            feedback_id=feedback_id,
                            session_id=session_id,
                            response_id=previous_response_id,
                            source="passive_followup",
                        ))
                except Exception as fb_exc:
                    logger.debug("Could not queue feedback loop task: %s", fb_exc)

                return {
                    "is_correction": True,
                    "correction_detected": True,
                    "feedback_created": True,
                    "auto_created_feedback": True,
                    "feedback_id": feedback_id,
                    "patch_id": patch_id,
                    "confidence": claim.confidence,
                    "signals": {
                        "is_frustrated": True,
                        "same_referent": True,
                        "has_correction_lang": True,
                    },
                    "structured_claim": claim_dict,
                    "claim": claim_dict,
                }
            except Exception as exc:
                db.rollback()
                logger.error("Failed to auto-create feedback record: %s", exc, exc_info=True)
                return {
                    "is_correction": True,
                    "correction_detected": True,
                    "feedback_created": False,
                    "auto_created_feedback": False,
                    "claim": claim_dict,
                    "structured_claim": claim_dict,
                    "confidence": claim.confidence,
                    "error": str(exc),
                }

        return {
            "is_correction": False,
            "correction_detected": False,
            "feedback_created": False,
            "auto_created_feedback": False,
            "confidence": 0.0,
            "signals": {},
            "claim": None,
            "structured_claim": None,
        }
    finally:
        db.close()


@router.post("/follow-up-detection", response_model=Dict[str, Any])
async def detect_follow_up_correction(
    payload: FollowUpDetectionIn,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """Detect if a follow-up query is actually an implicit correction attempt.
    If detected, auto-creates structured feedback in data.db and registers a provisional
    patch in CorrectionPatchLayer (passive self-healing).

    Args:
        payload (FollowUpDetectionIn): Request or event payload.
        background_tasks (BackgroundTasks): Background tasks runner for deferred execution.
        current_role (Role): The current role.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    res = await run_follow_up_detection_logic(
        session_id=payload.session_id,
        previous_response_id=payload.previous_response_id,
        follow_up_query=payload.follow_up_query,
        original_query=payload.original_query,
        original_response=payload.original_response,
        session_history=payload.session_history,
        current_role_value=current_role.value if current_role else None,
        background_tasks=background_tasks,
    )
    if res.get("error") and not res.get("is_correction"):
        raise HTTPException(
            status_code=500,
            detail="Dissatisfaction detection service error"
        )
    return res



