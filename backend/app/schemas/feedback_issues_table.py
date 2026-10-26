# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
feedback_issues_table.py
========================
SQLAlchemy schema for FeedbackIssue table in SQLite (data.db).
Represents aggregated issues reported via feedback, tracking issue status,
contributor count, canonical query text, embedding, and repair task linkage.
"""

import uuid
from enum import Enum
from sqlalchemy import (
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.models import _now_iso


class IssueStatus(str, Enum):
    REPORTED = "reported"
    UNDER_REVIEW = "under_review"
    IN_REPAIR = "in_repair"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


OPEN_ISSUE_STATUSES = {
    IssueStatus.REPORTED.value,
    IssueStatus.UNDER_REVIEW.value,
    IssueStatus.IN_REPAIR.value,
    IssueStatus.REOPENED.value,
}

CLOSED_ISSUE_STATUSES = {
    IssueStatus.RESOLVED.value,
    IssueStatus.CLOSED.value,
}


class FeedbackIssue(Base):
    __tablename__ = "feedback_issues"

    issue_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"iss_{uuid.uuid4().hex[:12]}"
    )
    canonical_query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_embedding_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    primary_entities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    taxonomy_paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=IssueStatus.REPORTED.value, index=True
    )
    repair_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    contributor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)

    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_feedback_issues_query_hash", "query_hash"),
        Index("idx_feedback_issues_status", "status"),
        Index("idx_feedback_issues_tenant", "tenant_id"),
        Index("idx_feedback_issues_created", "created_at"),
    )
