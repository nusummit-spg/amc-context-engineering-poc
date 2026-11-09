"""Durable Wave 1.9 publication tables.

Isolated metadata on purpose: installation into the legacy app must be explicit.
Existing 009-011 schema is left intact. No DDL runs on import.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint,
    CheckConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    # UTC-naive for consistent SQLite / PostgreSQL timestamp without timezone testing.
    # Values are UTC exclusively; public API serializes ISO Z.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class PublicationWork(Base):
    __tablename__ = "publication_work_v2"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    proposal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime())
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    last_error: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("tenant", "idempotency_key", name="uq_pub_v2_tenant_key"),
        CheckConstraint("status IN ('queued','leased','published','failed','rollback_pending','rolled_back')", name="ck_pub_v2_status"),
        Index("idx_pub_v2_status_lease", "status", "lease_until"),
    )


class PublicationEffect(Base):
    __tablename__ = "publication_effect_v2"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    work_id: Mapped[str] = mapped_column(String(64), ForeignKey("publication_work_v2.id"), nullable=False)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    preimage: Mapped[dict] = mapped_column(JSON, nullable=False)
    postimage: Mapped[dict] = mapped_column(JSON, nullable=False)
    pre_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    post_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="prepared")
    claim_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime())
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    __table_args__ = (
        UniqueConstraint("work_id", "kind", "target", name="uq_pub_v2_effect"),
        CheckConstraint("state IN ('prepared','verified','compensated')", name="ck_pub_v2_effect_state"),
    )


class GenerationPointer(Base):
    """Single authoritative active generation per tenant and namespace."""
    __tablename__ = "publication_pointer_v2"
    tenant: Mapped[str] = mapped_column(String(128), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), primary_key=True)
    generation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)


class PublicationReceipt(Base):
    """Immutable final receipt: only written when all effect readbacks pass."""
    __tablename__ = "publication_receipt_v2"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    work_id: Mapped[str] = mapped_column(String(64), ForeignKey("publication_work_v2.id"), nullable=False, unique=True)
    tenant: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)


class PublicationFence(Base):
    """Single monotonic sequence, globally orders claims even across different jobs."""
    __tablename__ = "publication_fence_v2"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class FeedbackPublicationLink(Base):
    """Durable feedback result; never inferred from staging counts."""
    __tablename__ = "feedback_publication_link_v2"
    tenant: Mapped[str] = mapped_column(String(128), primary_key=True)
    issue_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    work_id: Mapped[str] = mapped_column(String(64), ForeignKey("publication_work_v2.id"), nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(64), ForeignKey("publication_receipt_v2.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="resolved")
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)
