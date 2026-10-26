# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
repair_proposals.py
===================
SQLAlchemy schema for automated repair proposals (vector & graph).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.models import _now_iso


class RepairProposal(Base):
    """
    Repair proposal queued for automated governance or human approval.
    Supports knowledge graph Cypher mutations and vector reindexing.
    """
    __tablename__ = "repair_proposals"

    proposal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unified_record_ref: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("unified_evaluation_records.response_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    proposal_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'vector' | 'graph'
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    attribute: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # For graph repairs
    mutation_cypher: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_nodes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # For vector repairs
    document_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reindex_required: Mapped[bool] = mapped_column(Boolean, default=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    # Status: pending → approved → applied OR rejected

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    reviewed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applied_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    regression_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        CheckConstraint("proposal_type IN ('vector', 'graph')", name="ck_proposal_type"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'applied')", name="ck_proposal_status"),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_proposal_confidence"),
        Index("idx_proposal_status_confidence", "status", "confidence"),
        Index("idx_proposal_created", "created_at"),
    )
