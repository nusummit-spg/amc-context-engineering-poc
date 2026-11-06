"""
publication_intents_table.py
=============================
SQLAlchemy schema for immutable publication intents and receipts.

B01/P01: Immutable publication intents for verified graph/vector publication.

Intent schema: keyed by proposal_id + approved_revision + tenant + target_entity + source_version
Receipt schema: includes preimage, postimage, verified timestamp, and immutable evidence
"""

from sqlalchemy import Column, String, Text, JSON, Boolean, Integer, Index, DateTime
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


class PublicationIntent(Base):
    """
    P01: Immutable publication intent for verified graph/vector publication.
    
    Intent is created when a proposal is approved, before external execution.
    Intent is marked completed when all external effects are verified.
    
    Key fields:
    - intent_id: Unique identifier for the intent
    - proposal_id: Reference to the repair proposal
    - approved_revision: Version number at approval time (for versioning)
    - tenant: Tenant scope for multi-tenant isolation
    - target_entity: Entity being modified
    - source_version: Source document version at publication time
    
    Status flow:
    PENDING → APPROVED → PUBLISHING → PUBLISHED | FAILED
    """
    __tablename__ = "publication_intents"

    intent_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"intent_{uuid.uuid4().hex[:12]}"
    )
    
    proposal_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Versioning at approval time
    approved_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    
    # Multi-tenant isolation
    tenant: Mapped[str] = mapped_column(String(128), nullable=False, default="default", index=True)
    
    # Target entity information
    target_entity: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # Source version at publication time
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Publication details
    publication_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Types: "graph_mutation", "vector_reindex", "patch_activation"
    
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Full payload needed for execution and verification
    
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # Status: pending → approved → publishing → published | failed
    
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    approved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    publishing_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        Index("idx_intent_proposal_revision", "proposal_id", "approved_revision"),
        Index("idx_intent_status_created", "status", "created_at"),
        Index("idx_intent_tenant_entity", "tenant", "target_entity"),
    )


class PublicationReceipt(Base):
    """
    P01: Immutable publication receipt for verified effects.
    
    Receipt is created when an intent is successfully published.
    Contains preimage, postimage, and immutable evidence of external effects.
    
    Key fields:
    - receipt_id: Unique identifier
    - intent_id: Reference to the publication intent
    - preimage: Value/state before publication (for rollback)
    - postimage: Value/state after publication (for verification)
    - verified_at: Timestamp of verification
    - signature: Optional cryptographic signature of receipt
    """
    __tablename__ = "publication_receipts"

    receipt_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"receipt_{uuid.uuid4().hex[:12]}"
    )
    
    intent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Preimage (before publication)
    preimage: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Postimage (after publication)
    postimage: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Verification evidence
    verified_at: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_method: Mapped[str] = mapped_column(String(64), nullable=False)
    # Methods: "readback", "checksum", "probe_query", "audit_log"
    
    # Immutable evidence
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    # Tenant for multi-tenant isolation
    tenant: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    
    # Optional cryptographic signature
    signature: Mapped[str | None] = mapped_column(String(256), nullable=True)
    
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso, index=True)
    
    __table_args__ = (
        Index("idx_receipt_intent", "intent_id"),
        Index("idx_receipt_source_hash", "source_hash"),
    )