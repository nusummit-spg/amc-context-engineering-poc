# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
repair_linkage.py
=================
Service coordinating FeedbackIssue lifecycle with the Repair Engine.
Enforces the single-task-per-issue invariant (Section 9):
  - Exactly one repair task is created when an issue transitions to in_repair.
  - Subsequent matching feedback records attach to the existing issue and reuse
    the already-created repair_task_id without triggering duplicate repair tasks.
  - If an issue was resolved/closed and reopened by new feedback, repair_task_id
    is cleared to allow fresh determination at the next triage step.
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.clients.repair_client import get_repair_service_client
from app.feedback import issue_store
from app.schemas.feedback_issues_table import (
    CLOSED_ISSUE_STATUSES,
    OPEN_ISSUE_STATUSES,
    FeedbackIssue,
    IssueStatus,
)
from app.schemas.models import _now_iso
from app.schemas.response_feedback_table import ResponseFeedback

logger = logging.getLogger("app.feedback.repair_linkage")


class RepairLinkageService:
    """
    Coordinates FeedbackIssue lifecycle with the Repair Engine client.
    Guarantees idempotency and prevents duplicate repair tasks.
    """

    def __init__(self, repair_client=None):
        """Initialize a new instance of RepairLinkageService.

        Args:
            repair_client: The repair client.
        """
        self._repair_client = repair_client

    def _get_client(self):
        """Retrieve client.

        Returns:
            Result of the operation.
        """
        if self._repair_client is None:
            self._repair_client = get_repair_service_client()
        return self._repair_client

    def get_or_create_repair_task(
        self,
        db: Session,
        issue_id: str,
        actor_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ensure a repair task exists for the given FeedbackIssue.
        - If issue.repair_task_id is already set, reuses it (no duplicate created).
        - If issue.repair_task_id is None, invokes the repair client to create one,
          stamps repair_task_id onto the FeedbackIssue, and transitions status to 'in_repair'.

        Args:
            db (Session): Database session instance.
            issue_id (str): Unique identifier of the issue.
            actor_id (Optional[str]): Unique identifier of the actor.
            metadata (Optional[Dict[str, Any]]): Associated metadata dictionary.

        Returns:
            Dict[str, Any]: Dictionary containing result data or status.
        """
        issue = issue_store.get_issue_by_id(db, issue_id)
        if not issue:
            raise ValueError(f"FeedbackIssue '{issue_id}' not found.")

        # Invariant 1: If repair task already exists, reuse it without creating a duplicate
        if issue.repair_task_id:
            logger.info(
                "[REPAIR_TASK_REUSED] Issue issue_id=%s already has repair_task_id=%s. Reusing existing task.",
                issue.issue_id,
                issue.repair_task_id,
            )
            if issue.status != IssueStatus.IN_REPAIR.value:
                issue.status = IssueStatus.IN_REPAIR.value
                issue.updated_at = _now_iso()
                db.commit()
                db.refresh(issue)

            return {
                "issue_id": issue.issue_id,
                "repair_task_id": issue.repair_task_id,
                "status": issue.status,
                "task_created": False,
                "reused": True,
                "message": f"Reused existing repair task '{issue.repair_task_id}' for issue '{issue.issue_id}'.",
            }

        # Invariant 2: If repair task does not exist, create a fresh one and stamp it onto the issue
        client = self._get_client()
        provenance = {
            "issue_id": issue.issue_id,
            "source": "feedback_status_awareness_phase3",
            "actor_id": actor_id,
            **(metadata or {}),
        }

        new_task_id = client.create_repair_task_sync(
            issue_id=issue.issue_id,
            canonical_query=issue.canonical_query_text,
            primary_entities=issue.primary_entities or [],
            taxonomy_paths=issue.taxonomy_paths or [],
            contributor_count=issue.contributor_count,
            provenance=provenance,
        )

        issue.repair_task_id = new_task_id
        issue.status = IssueStatus.IN_REPAIR.value
        issue.updated_at = _now_iso()
        db.commit()
        db.refresh(issue)

        logger.info(
            "[REPAIR_TASK_CREATED] Created and stamped repair_task_id=%s onto issue_id=%s (status=in_repair)",
            new_task_id,
            issue.issue_id,
        )

        return {
            "issue_id": issue.issue_id,
            "repair_task_id": new_task_id,
            "status": issue.status,
            "task_created": True,
            "reused": False,
            "message": f"Created new repair task '{new_task_id}' for issue '{issue.issue_id}'.",
        }

    def transition_issue_status(
        self,
        db: Session,
        issue_id: str,
        new_status: str,
        resolution_notes: Optional[str] = None,
        actor_id: Optional[str] = None,
        repair_task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transitions the lifecycle status of a FeedbackIssue according to Section 6 & 9:
        reported -> under_review -> in_repair -> resolved -> closed (or reopened)

        Args:
            db (Session): Database session instance.
            issue_id (str): Unique identifier of the issue.
            new_status (str): Collection or list of new status.
            resolution_notes (Optional[str]): Collection or list of resolution notes.
            actor_id (Optional[str]): Unique identifier of the actor.
            repair_task_id (Optional[str]): Unique identifier of the repair task.

        Returns:
            Dict[str, Any]: Dictionary containing result data or status.
        """
        issue = issue_store.get_issue_by_id(db, issue_id)
        if not issue:
            raise ValueError(f"FeedbackIssue '{issue_id}' not found.")

        norm_status = new_status.strip().lower()
        valid_statuses = {s.value for s in IssueStatus}
        if norm_status not in valid_statuses:
            raise ValueError(
                f"Invalid issue status '{new_status}'. Allowed: {sorted(list(valid_statuses))}"
            )

        now_iso = _now_iso()

        if repair_task_id and not issue.repair_task_id:
            issue.repair_task_id = repair_task_id

        if norm_status == IssueStatus.IN_REPAIR.value:
            # If issue was resolved or closed, clear old task so fresh triage generates a new task
            if issue.status in CLOSED_ISSUE_STATUSES:
                issue.repair_task_id = None
                db.commit()
            return self.get_or_create_repair_task(db, issue_id, actor_id=actor_id)

        if norm_status == IssueStatus.REOPENED.value:
            issue_store.reopen_issue_if_resolved(db, issue)
            # Reopen explicitly clears repair_task_id
            issue.status = IssueStatus.REOPENED.value
            issue.repair_task_id = None
            issue.updated_at = now_iso
            db.commit()
            db.refresh(issue)
            logger.info(
                "[ISSUE_REOPENED] Issue issue_id=%s manually transitioned to reopened (repair_task_id cleared)",
                issue.issue_id,
            )
            return {
                "issue_id": issue.issue_id,
                "repair_task_id": None,
                "status": issue.status,
                "task_created": False,
                "reused": False,
                "message": f"Issue '{issue.issue_id}' reopened and repair_task_id cleared for fresh determination.",
            }

        if norm_status in CLOSED_ISSUE_STATUSES:
            issue.status = norm_status
            if repair_task_id:
                issue.repair_task_id = repair_task_id
            if resolution_notes:
                issue.resolution_notes = resolution_notes
            issue.updated_at = now_iso
            db.commit()
            db.refresh(issue)
            logger.info(
                "[ISSUE_RESOLVED_OR_CLOSED] Issue issue_id=%s status=%s resolution_notes=%s",
                issue.issue_id,
                norm_status,
                resolution_notes,
            )
            return {
                "issue_id": issue.issue_id,
                "repair_task_id": issue.repair_task_id,
                "status": issue.status,
                "task_created": False,
                "reused": False,
                "message": f"Issue '{issue.issue_id}' updated to status '{norm_status}'.",
            }

        # Statuses: reported, under_review
        issue.status = norm_status
        issue.updated_at = now_iso
        db.commit()
        db.refresh(issue)
        logger.info(
            "[ISSUE_STATUS_TRANSITIONED] Issue issue_id=%s updated to status=%s",
            issue.issue_id,
            norm_status,
        )
        return {
            "issue_id": issue.issue_id,
            "repair_task_id": issue.repair_task_id,
            "status": issue.status,
            "task_created": False,
            "reused": False,
            "message": f"Issue '{issue.issue_id}' updated to status '{norm_status}'.",
        }

    def get_issue_details(self, db: Session, issue_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve complete issue details along with linked feedback count and IDs.

        Args:
            db (Session): Database session instance.
            issue_id (str): Unique identifier of the issue.

        Returns:
            Optional[Dict[str, Any]]: Dictionary containing result data or status.
        """
        issue = issue_store.get_issue_by_id(db, issue_id)
        if not issue:
            return None

        linked_feedbacks = (
            db.query(ResponseFeedback)
            .filter(ResponseFeedback.issue_id == issue.issue_id)
            .order_by(ResponseFeedback.created_at.desc())
            .all()
        )

        return {
            "issue_id": issue.issue_id,
            "canonical_query_text": issue.canonical_query_text,
            "query_hash": issue.query_hash,
            "status": issue.status,
            "repair_task_id": issue.repair_task_id,
            "contributor_count": issue.contributor_count,
            "primary_entities": issue.primary_entities or [],
            "taxonomy_paths": issue.taxonomy_paths or [],
            "tenant_id": issue.tenant_id,
            "created_at": issue.created_at,
            "updated_at": issue.updated_at,
            "resolution_notes": issue.resolution_notes,
            "linked_feedback_count": len(linked_feedbacks),
            "linked_feedback_ids": [f.feedback_id for f in linked_feedbacks],
        }


_repair_linkage_service: Optional[RepairLinkageService] = None


def get_repair_linkage_service() -> RepairLinkageService:
    """Retrieve repair linkage service.

    Returns:
        RepairLinkageService: Resulting RepairLinkageService instance.
    """
    global _repair_linkage_service
    if _repair_linkage_service is None:
        _repair_linkage_service = RepairLinkageService()
    return _repair_linkage_service
