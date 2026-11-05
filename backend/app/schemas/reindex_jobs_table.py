"""
reindex_jobs_table.py
=====================
SQLAlchemy schema for vector store reindex jobs tracking.

B04: Wave 1.3 - Reindex Verification
Tracks vector store reindex operations with verification receipts.
"""

from sqlalchemy import Column, String, Text, JSON, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
import uuid
from datetime import datetime, timezone


def _now_iso() -> str:
    """Generate current ISO timestamp.

    Returns:
        str: ISO format timestamp
    """
    return datetime.now(timezone.utc).isoformat()


class ReindexJob(Base):
    """
    B04: Tracks vector store reindex jobs with verification.
    
    Each reindex job corresponds to a vector-type repair proposal
    and records whether the operation completed successfully.
    """
    __tablename__ = "reindex_jobs"

    job_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"reindex_{uuid.uuid4().hex[:12]}"
    )
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    document_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # Status: pending → running → completed | failed
    
    started_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
