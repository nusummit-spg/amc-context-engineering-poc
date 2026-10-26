# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
feedback_issue_category_counts_table.py
=======================================
SQLAlchemy schema for feedback_issue_category_counts table in SQLite (data.db).
Maintains denormalized, atomically-updated running totals of failure taxonomy
category codes (F01-F12) reported across feedback entries for each FeedbackIssue.
"""

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.models import _now_iso


class FeedbackIssueCategoryCount(Base):
    __tablename__ = "feedback_issue_category_counts"

    issue_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("feedback_issues.issue_id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)

    __table_args__ = (
        Index("idx_category_counts_issue_id", "issue_id"),
    )
