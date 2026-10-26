# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
issue_store.py
==============
CRUD repository and persistence helpers for FeedbackIssue entities in SQLite (data.db).
Manages lifecycle transitions, contributor counts, queries for open issues, and
links between response_feedback entries and feedback_issues.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.compliance.failure_taxonomy import CODE_TO_LABEL
from app.schemas.feedback_issues_table import (
    CLOSED_ISSUE_STATUSES,
    OPEN_ISSUE_STATUSES,
    FeedbackIssue,
    IssueStatus,
)
from app.schemas.feedback_issue_category_counts_table import FeedbackIssueCategoryCount
from app.schemas.models import _now_iso
from app.schemas.response_feedback_table import ResponseFeedback

logger = logging.getLogger("app.feedback.issue_store")


def create_issue(
    db: Session,
    canonical_query_text: str,
    query_hash: str,
    primary_entities: Optional[List[str]] = None,
    taxonomy_paths: Optional[List[str]] = None,
    tenant_id: Optional[str] = None,
    status: str = IssueStatus.REPORTED.value,
    repair_task_id: Optional[str] = None,
    contributor_count: int = 1,
    query_embedding_ref: Optional[str] = None,
    issue_id: Optional[str] = None,
) -> FeedbackIssue:
    """Create a new FeedbackIssue record and commit to database.

    Args:
        db (Session): Database session instance.
        canonical_query_text (str): The canonical query text.
        query_hash (str): The query hash.
        primary_entities (Optional[List[str]]): Collection or list of primary entities.
        taxonomy_paths (Optional[List[str]]): Collection or list of taxonomy paths.
        tenant_id (Optional[str]): Unique identifier of the tenant.
        status (str): Target status value.
        repair_task_id (Optional[str]): Unique identifier of the repair task.
        contributor_count (int): The contributor count.
        query_embedding_ref (Optional[str]): The query embedding ref.
        issue_id (Optional[str]): Unique identifier of the issue.

    Returns:
        FeedbackIssue: Resulting FeedbackIssue instance.
    """
    now_iso = _now_iso()
    assigned_id = issue_id or f"iss_{uuid.uuid4().hex[:12]}"

    issue = FeedbackIssue(
        issue_id=assigned_id,
        canonical_query_text=canonical_query_text.strip(),
        query_hash=query_hash,
        query_embedding_ref=query_embedding_ref,
        primary_entities=primary_entities or [],
        taxonomy_paths=taxonomy_paths or [],
        status=status,
        repair_task_id=repair_task_id,
        contributor_count=max(1, contributor_count),
        tenant_id=tenant_id,
        created_at=now_iso,
        updated_at=now_iso,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    logger.info(
        "[ISSUE_CREATED] Created feedback issue issue_id=%s status=%s hash=%s",
        issue.issue_id,
        issue.status,
        issue.query_hash,
    )
    return issue


def get_issue_by_id(db: Session, issue_id: str) -> Optional[FeedbackIssue]:
    """Retrieve issue by primary key.

    Args:
        db (Session): Database session instance.
        issue_id (str): Unique identifier of the issue.

    Returns:
        Optional[FeedbackIssue]: Matching object or record if found, None otherwise.
    """
    return db.query(FeedbackIssue).filter(FeedbackIssue.issue_id == issue_id).first()


def get_open_issue_by_hash(
    db: Session,
    query_hash: str,
    tenant_id: Optional[str] = None,
) -> Optional[FeedbackIssue]:
    """Retrieve an open issue matching exact query hash and tenant scope.

    Args:
        db (Session): Database session instance.
        query_hash (str): The query hash.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        Optional[FeedbackIssue]: Matching object or record if found, None otherwise.
    """
    query = db.query(FeedbackIssue).filter(
        FeedbackIssue.query_hash == query_hash,
        FeedbackIssue.status.in_(OPEN_ISSUE_STATUSES),
    )
    if tenant_id:
        query = query.filter(
            (FeedbackIssue.tenant_id == tenant_id) | (FeedbackIssue.tenant_id.is_(None))
        )
    return query.first()


def get_closed_issue_by_hash(
    db: Session,
    query_hash: str,
    tenant_id: Optional[str] = None,
) -> Optional[FeedbackIssue]:
    """Retrieve a resolved or closed issue matching exact query hash and tenant scope.

    Args:
        db (Session): Database session instance.
        query_hash (str): The query hash.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        Optional[FeedbackIssue]: Matching object or record if found, None otherwise.
    """
    query = db.query(FeedbackIssue).filter(
        FeedbackIssue.query_hash == query_hash,
        FeedbackIssue.status.in_(CLOSED_ISSUE_STATUSES),
    )
    if tenant_id:
        query = query.filter(
            (FeedbackIssue.tenant_id == tenant_id) | (FeedbackIssue.tenant_id.is_(None))
        )
    return query.order_by(FeedbackIssue.updated_at.desc()).first()


def get_open_issues(
    db: Session,
    tenant_id: Optional[str] = None,
) -> List[FeedbackIssue]:
    """Retrieve all open issues (status in reported, under_review, in_repair, reopened).

    Args:
        db (Session): Database session instance.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        List[FeedbackIssue]: List of resulting items or records.
    """
    query = db.query(FeedbackIssue).filter(
        FeedbackIssue.status.in_(OPEN_ISSUE_STATUSES)
    )
    if tenant_id:
        query = query.filter(
            (FeedbackIssue.tenant_id == tenant_id) | (FeedbackIssue.tenant_id.is_(None))
        )
    return query.order_by(FeedbackIssue.created_at.desc()).all()


def update_issue_status(
    db: Session,
    issue_id: str,
    status: str,
    resolution_notes: Optional[str] = None,
    repair_task_id: Optional[str] = None,
) -> Optional[FeedbackIssue]:
    """Update issue lifecycle status, resolution notes, or repair task ID.

    Args:
        db (Session): Database session instance.
        issue_id (str): Unique identifier of the issue.
        status (str): Target status value.
        resolution_notes (Optional[str]): Collection or list of resolution notes.
        repair_task_id (Optional[str]): Unique identifier of the repair task.

    Returns:
        Optional[FeedbackIssue]: Matching object or record if found, None otherwise.
    """
    issue = get_issue_by_id(db, issue_id)
    if not issue:
        return None

    issue.status = status
    issue.updated_at = _now_iso()
    if resolution_notes is not None:
        issue.resolution_notes = resolution_notes
    if repair_task_id is not None:
        issue.repair_task_id = repair_task_id

    db.commit()
    db.refresh(issue)
    logger.info(
        "[ISSUE_STATUS_UPDATED] Issue issue_id=%s updated to status=%s",
        issue_id,
        status,
    )
    return issue


def reopen_issue_if_resolved(db: Session, issue: FeedbackIssue) -> FeedbackIssue:
    """If an issue is currently resolved or closed, transition to reopened and clear repair_task_id.

    Args:
        db (Session): Database session instance.
        issue (FeedbackIssue): The issue.

    Returns:
        FeedbackIssue: Resulting FeedbackIssue instance.
    """
    if issue.status in CLOSED_ISSUE_STATUSES:
        issue.status = IssueStatus.REOPENED.value
        issue.repair_task_id = None
        issue.updated_at = _now_iso()
        db.commit()
        db.refresh(issue)
        logger.info(
            "[ISSUE_REOPENED] Resolved/closed issue issue_id=%s reopened due to new matching feedback",
            issue.issue_id,
        )
    return issue


def record_contributor(
    db: Session,
    issue: FeedbackIssue,
    actor_id: Optional[str],
) -> int:
    """Increment contributor count if this actor has not previously submitted feedback for this issue.

    Args:
        db (Session): Database session instance.
        issue (FeedbackIssue): The issue.
        actor_id (Optional[str]): Unique identifier of the actor.

    Returns:
        int: Resulting int instance.
    """
    if not actor_id:
        return issue.contributor_count

    # Check prior feedback on this issue with the same actor_id
    prior = (
        db.query(ResponseFeedback)
        .filter(
            ResponseFeedback.issue_id == issue.issue_id,
            ResponseFeedback.actor_id == actor_id,
        )
        .first()
    )

    if not prior:
        issue.contributor_count += 1
        issue.updated_at = _now_iso()
        db.commit()
        db.refresh(issue)
        logger.info(
            "[CONTRIBUTOR_INCREMENTED] Issue issue_id=%s contributor_count=%d (new contributor: %s)",
            issue.issue_id,
            issue.contributor_count,
            actor_id,
        )

    return issue.contributor_count


def link_feedback_entry(
    db: Session,
    feedback_id: str,
    issue_id: str,
    match_type: str,
) -> bool:
    """Link a response_feedback record to a FeedbackIssue.

    Args:
        db (Session): Database session instance.
        feedback_id (str): Unique identifier of the feedback.
        issue_id (str): Unique identifier of the issue.
        match_type (str): The match type.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    entry = db.query(ResponseFeedback).filter(ResponseFeedback.feedback_id == feedback_id).first()
    if not entry:
        return False

    entry.issue_id = issue_id
    entry.match_type = match_type
    entry.updated_at = _now_iso()
    db.commit()
    return True


def record_issue_categories(
    db: Session,
    issue_id: str,
    category_codes: List[str],
    old_category_codes: Optional[List[str]] = None,
) -> None:
    """Atomically updates denormalized failure category counts for an issue.
    Works inside the current database transaction using SQLite UPSERT (ON CONFLICT).
    Handles additions and removal deltas if old_category_codes is provided.

    Args:
        db (Session): Database session instance.
        issue_id (str): Unique identifier of the issue.
        category_codes (List[str]): Collection or list of category codes.
        old_category_codes (Optional[List[str]]): Collection or list of old category codes.
    """
    if not issue_id:
        return

    now_iso = _now_iso()
    clean_new = [c.strip().upper() for c in (category_codes or []) if c and c.strip()]
    unique_new = sorted(list(set(clean_new)))

    if old_category_codes is not None:
        clean_old = [c.strip().upper() for c in old_category_codes if c and c.strip()]
        unique_old = set(clean_old)
        to_add = [c for c in unique_new if c not in unique_old]
        to_remove = [c for c in unique_old if c not in set(unique_new)]
    else:
        to_add = unique_new
        to_remove = []

    # Atomic UPSERT for each newly flagged category
    for code in to_add:
        db.execute(
            text(
                """
                INSERT INTO feedback_issue_category_counts (issue_id, category_code, count, updated_at)
                VALUES (:issue_id, :code, 1, :now)
                ON CONFLICT (issue_id, category_code)
                DO UPDATE SET count = count + 1, updated_at = :now
                """
            ),
            {"issue_id": issue_id, "code": code, "now": now_iso},
        )
        logger.info(
            "[CATEGORY_COUNT_UPSERTED] Increment category count issue_id=%s code=%s",
            issue_id,
            code,
        )

    # Decrement for removed categories on update
    for code in to_remove:
        db.execute(
            text(
                """
                UPDATE feedback_issue_category_counts
                SET count = MAX(0, count - 1), updated_at = :now
                WHERE issue_id = :issue_id AND category_code = :code
                """
            ),
            {"issue_id": issue_id, "code": code, "now": now_iso},
        )


def get_issue_category_breakdown(
    db: Session,
    issue_id: str,
    limit: int = 5,
) -> List[dict]:
    """Retrieve category breakdown for an issue sorted by count descending.
    Point lookup on pre-aggregated feedback_issue_category_counts table.

    Args:
        db (Session): Database session instance.
        issue_id (str): Unique identifier of the issue.
        limit (int): Maximum number of records to return.

    Returns:
        List[dict]: List of resulting items or records.
    """
    if not issue_id:
        return []

    query = (
        db.query(FeedbackIssueCategoryCount)
        .filter(
            FeedbackIssueCategoryCount.issue_id == issue_id,
            FeedbackIssueCategoryCount.count > 0,
        )
        .order_by(
            FeedbackIssueCategoryCount.count.desc(),
            FeedbackIssueCategoryCount.category_code.asc(),
        )
    )
    if limit and limit > 0:
        query = query.limit(limit)

    rows = query.all()
    return [
        {
            "code": r.category_code,
            "label": CODE_TO_LABEL.get(r.category_code, r.category_code),
            "count": r.count,
        }
        for r in rows
    ]


def reconcile_issue_category_counts(
    db: Session,
    issue_id: Optional[str] = None,
) -> dict:
    """Reconciliation job: recomputes feedback_issue_category_counts from raw response_feedback
    entries to guarantee zero drift (§8 & §9 Phase 1 & Phase 5).
    Tracks drift_size and records reconciliation telemetry in FeedbackStatusCache.

    Args:
        db (Session): Database session instance.
        issue_id (Optional[str]): Unique identifier of the issue.

    Returns:
        dict: Dictionary containing result data or status.
    """
    now_iso = _now_iso()
    issue_query = db.query(FeedbackIssue)
    if issue_id:
        issue_query = issue_query.filter(FeedbackIssue.issue_id == issue_id)
    issues = issue_query.all()

    total_issues = len(issues)
    total_categories_tracked = 0
    total_drift = 0

    for issue in issues:
        # Load existing counters to measure drift
        old_rows = (
            db.query(FeedbackIssueCategoryCount)
            .filter(FeedbackIssueCategoryCount.issue_id == issue.issue_id)
            .all()
        )
        old_counts = {r.category_code: r.count for r in old_rows}

        # Collect all categories from feedback entries linked to this issue
        feedbacks = (
            db.query(ResponseFeedback)
            .filter(ResponseFeedback.issue_id == issue.issue_id)
            .all()
        )

        counts: dict[str, int] = {}
        for fb in feedbacks:
            cats = fb.categories if fb.categories is not None else fb.selected_categories
            if isinstance(cats, list):
                for c in set(cats):
                    if c:
                        code = c.strip().upper()
                        counts[code] = counts.get(code, 0) + 1

        # Calculate drift for this issue
        all_codes = set(old_counts.keys()).union(set(counts.keys()))
        for code in all_codes:
            diff = abs(counts.get(code, 0) - old_counts.get(code, 0))
            total_drift += diff

        # Clear existing counters for this issue
        db.query(FeedbackIssueCategoryCount).filter(
            FeedbackIssueCategoryCount.issue_id == issue.issue_id
        ).delete()

        # Insert recomputed counts
        for code, cnt in counts.items():
            if cnt > 0:
                row = FeedbackIssueCategoryCount(
                    issue_id=issue.issue_id,
                    category_code=code,
                    count=cnt,
                    updated_at=now_iso,
                )
                db.add(row)
                total_categories_tracked += cnt

    db.commit()

    # Record reconciliation and purge status cache
    try:
        from app.feedback.feedback_cache import get_feedback_cache
        cache = get_feedback_cache()
        cache.record_reconciliation(drift_size=total_drift, issues_reconciled=total_issues)
    except Exception as cache_err:
        logger.debug("Failed to update cache telemetry after reconciliation: %s", cache_err)

    logger.info(
        "[RECONCILIATION_COMPLETED] Reconciled category counts for %d issues (total count=%d, drift_size=%d)",
        total_issues,
        total_categories_tracked,
        total_drift,
    )
    return {
        "reconciled_issues": total_issues,
        "total_categories_tracked": total_categories_tracked,
        "drift_size": total_drift,
        "timestamp": now_iso,
    }

