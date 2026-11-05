"""
outbox_events_table.py
======================
SQLAlchemy schema for transactional outbox pattern.

B05: Wave 1.3 - Transaction Saga
Implements outbox pattern for atomicity across graph + vector operations.
"""

from sqlalchemy import Column, String, Text, JSON, Boolean, Integer, Index
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


class OutboxEvent(Base):
    """
    B05: Transactional outbox for cross-service operations.
    
    Ensures atomicity of operations that span multiple systems:
    - Graph mutations (Neo4j)
    - Vector updates (FAISS)
    - State transitions (PostgreSQL)
    
    Pattern:
    1. Write to outbox in same transaction as state change
    2. Background processor reads outbox and executes operations
    3. Mark as processed only after all operations succeed
    4. Retry failed events with exponential backoff
    """
    __tablename__ = "outbox_events"

    event_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"evt_{uuid.uuid4().hex[:12]}"
    )
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # e.g., "repair_proposal", "patch", "correction"
    
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # The ID of the entity being changed
    
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # e.g., "PATCH_PROMOTED", "GRAPH_MUTATION_REQUIRED", "VECTOR_REINDEX_REQUIRED"
    
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Full event data needed to execute the operation
    
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # Status: pending → processing → completed | failed
    
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    processed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        Index("idx_outbox_status_created", "status", "created_at"),
    )
