"""Pydantic schemas and serialization models for graph mutations table."""

from sqlalchemy import Column, String, Text, JSON, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
import uuid
from datetime import datetime, timezone


def _now_iso() -> str:
    """Now iso.

    Returns:
        str: Resulting str instance.
    """
    return datetime.now(timezone.utc).isoformat()


class GraphMutation(Base):
    __tablename__ = "graph_mutations"

    mutation_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"mut_{uuid.uuid4().hex[:12]}"
    )
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    mutation_cypher: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_nodes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    applied_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    applied_by: Mapped[str] = mapped_column(String(64), nullable=False, default="promotion_service")
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # B03: Immutable verification receipt (C-11 integrity proof)
    verified_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # Value read back from graph
    verification_timestamp: Mapped[str | None] = mapped_column(String(40), nullable=True)  # When verified
    verification_receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Full receipt with entity_id, attribute, tx_id

    __table_args__ = (
        Index("idx_mutation_applied_at", "applied_at"),
    )
