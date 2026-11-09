"""Durable publication repository.

Implements CRUD for publication_work_v2, publication_effect_v2,
publication_pointer_v2, publication_receipt_v2, feedback_publication_link_v2,
and publication_fence_v2 tables.

Wave 1.9 durable publication foundation.
"""

from typing import Optional, List, Any
from datetime import datetime
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .models import (
    PublicationWork, PublicationEffect, GenerationPointer,
    PublicationReceipt, PublicationFence, FeedbackPublicationLink
)


class PublicationRepository:
    """Durable publication repository for Wave 1.9."""
    
    def __init__(self, session: Session):
        """Initialize repository with SQLAlchemy session.
        
        Args:
            session: SQLAlchemy session instance
        """
        self.session = session
    
    # === Publication Work (v2) ===
    
    def create_work(self, work: PublicationWork) -> PublicationWork:
        """Create a new publication work record.
        
        Args:
            work: PublicationWork instance
            
        Returns:
            Created PublicationWork with ID
        """
        self.session.add(work)
        self.session.commit()
        self.session.refresh(work)
        return work
    
    def get_work_by_id(self, work_id: str) -> Optional[PublicationWork]:
        """Get publication work by ID.
        
        Args:
            work_id: Work ID
            
        Returns:
            PublicationWork or None
        """
        stmt = select(PublicationWork).where(PublicationWork.id == work_id)
        return self.session.scalar(stmt)
    
    def get_work_by_idempotency_key(
        self, tenant: str, idempotency_key: str
    ) -> Optional[PublicationWork]:
        """Get publication work by idempotency key.
        
        Args:
            tenant: Tenant ID
            idempotency_key: Idempotency key
            
        Returns:
            PublicationWork or None
        """
        stmt = select(PublicationWork).where(
            and_(
                PublicationWork.tenant == tenant,
                PublicationWork.idempotency_key == idempotency_key
            )
        )
        return self.session.scalar(stmt)
    
    def get_works_by_status(
        self, status: str, limit: int = 100
    ) -> List[PublicationWork]:
        """Get publication works by status.
        
        Args:
            status: Status to filter by
            limit: Maximum results
            
        Returns:
            List of PublicationWork
        """
        stmt = select(PublicationWork).where(
            PublicationWork.status == status
        ).limit(limit)
        return list(self.session.scalars(stmt))
    
    def update_work_status(
        self, work_id: str, status: str, **kwargs
    ) -> int:
        """Update publication work status and optional fields.
        
        Args:
            work_id: Work ID
            status: New status
            kwargs: Additional fields to update
            
        Returns:
            Number of rows updated
        """
        stmt = update(PublicationWork).where(
            PublicationWork.id == work_id
        ).values(status=status, **kwargs)
        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount
    
    def update_work_with_lease(
        self, work_id: str, status: str, owner: str, lease_until: datetime
    ) -> bool:
        """Update work with lease (fenced claim).
        
        Args:
            work_id: Work ID
            status: New status
            owner: Worker owner
            lease_until: Lease expiry timestamp
            
        Returns:
            True if updated, False if not found
        """
        stmt = update(PublicationWork).where(
            PublicationWork.id == work_id
        ).values(
            status=status,
            owner=owner,
            lease_until=lease_until,
            attempts=PublicationWork.attempts + 1
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount > 0
    
    # === Publication Effect (v2) ===
    
    def create_effect(self, effect: PublicationEffect) -> PublicationEffect:
        """Create a new publication effect record.
        
        Args:
            effect: PublicationEffect instance
            
        Returns:
            Created PublicationEffect with ID
        """
        self.session.add(effect)
        self.session.commit()
        self.session.refresh(effect)
        return effect
    
    def get_effect(
        self, work_id: str, kind: str, target: str
    ) -> Optional[PublicationEffect]:
        """Get publication effect by composite key.
        
        Args:
            work_id: Work ID
            kind: Effect kind (graph, vector, etc.)
            target: Target identifier
            
        Returns:
            PublicationEffect or None
        """
        stmt = select(PublicationEffect).where(
            and_(
                PublicationEffect.work_id == work_id,
                PublicationEffect.kind == kind,
                PublicationEffect.target == target
            )
        )
        return self.session.scalar(stmt)
    
    def get_effects_for_work(
        self, work_id: str
    ) -> List[PublicationEffect]:
        """Get all effects for a work.
        
        Args:
            work_id: Work ID
            
        Returns:
            List of PublicationEffect
        """
        stmt = select(PublicationEffect).where(
            PublicationEffect.work_id == work_id
        )
        return list(self.session.scalars(stmt))
    
    def update_effect_state(
        self, work_id: str, kind: str, target: str, state: str
    ) -> int:
        """Update effect state.
        
        Args:
            work_id: Work ID
            kind: Effect kind
            target: Target identifier
            state: New state (prepared, verified, compensated)
            
        Returns:
            Number of rows updated
        """
        stmt = update(PublicationEffect).where(
            and_(
                PublicationEffect.work_id == work_id,
                PublicationEffect.kind == kind,
                PublicationEffect.target == target
            )
        ).values(state=state)
        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount
    
    def verify_effect(
        self, work_id: str, kind: str, target: str, verified_at: datetime
    ) -> int:
        """Mark effect as verified.
        
        Args:
            work_id: Work ID
            kind: Effect kind
            target: Target identifier
            verified_at: Verification timestamp
            
        Returns:
            Number of rows updated
        """
        stmt = update(PublicationEffect).where(
            and_(
                PublicationEffect.work_id == work_id,
                PublicationEffect.kind == kind,
                PublicationEffect.target == target
            )
        ).values(
            state="verified",
            verified_at=verified_at
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount
    
    # === Generation Pointer (v2) ===
    
    def get_pointer(
        self, tenant: str, namespace: str
    ) -> Optional[GenerationPointer]:
        """Get active generation pointer.
        
        Args:
            tenant: Tenant ID
            namespace: Namespace
            
        Returns:
            GenerationPointer or None
        """
        stmt = select(GenerationPointer).where(
            and_(
                GenerationPointer.tenant == tenant,
                GenerationPointer.namespace == namespace
            )
        )
        return self.session.scalar(stmt)
    
    def set_pointer(
        self, tenant: str, namespace: str, generation_id: str,
        artifact_digest: str
    ) -> GenerationPointer:
        """Set active generation pointer (creates or updates).
        
        Args:
            tenant: Tenant ID
            namespace: Namespace
            generation_id: New generation ID
            artifact_digest: Artifact digest
            
        Returns:
            GenerationPointer instance
        """
        existing = self.get_pointer(tenant, namespace)
        if existing:
            existing.generation_id = generation_id
            existing.artifact_digest = artifact_digest
            existing.epoch += 1
            existing.activated_at = datetime.now()
            self.session.commit()
            self.session.refresh(existing)
            return existing
        
        pointer = GenerationPointer(
            tenant=tenant,
            namespace=namespace,
            generation_id=generation_id,
            artifact_digest=artifact_digest,
            epoch=1
        )
        self.session.add(pointer)
        self.session.commit()
        self.session.refresh(pointer)
        return pointer
    
    # === Publication Receipt (v2) ===
    
    def create_receipt(self, receipt: PublicationReceipt) -> PublicationReceipt:
        """Create a new publication receipt.
        
        Args:
            receipt: PublicationReceipt instance
            
        Returns:
            Created PublicationReceipt with ID
        """
        self.session.add(receipt)
        self.session.commit()
        self.session.refresh(receipt)
        return receipt
    
    def get_receipt_by_work_id(
        self, work_id: str
    ) -> Optional[PublicationReceipt]:
        """Get receipt by work ID.
        
        Args:
            work_id: Work ID
            
        Returns:
            PublicationReceipt or None
        """
        stmt = select(PublicationReceipt).where(
            PublicationReceipt.work_id == work_id
        )
        return self.session.scalar(stmt)
    
    def get_receipt_by_id(self, receipt_id: str) -> Optional[PublicationReceipt]:
        """Get receipt by ID.
        
        Args:
            receipt_id: Receipt ID
            
        Returns:
            PublicationReceipt or None
        """
        stmt = select(PublicationReceipt).where(
            PublicationReceipt.id == receipt_id
        )
        return self.session.scalar(stmt)
    
    def mark_receipt_verified(self, receipt_id: str) -> int:
        """Mark receipt as verified.
        
        Args:
            receipt_id: Receipt ID
            
        Returns:
            Number of rows updated
        """
        stmt = update(PublicationReceipt).where(
            PublicationReceipt.id == receipt_id
        ).values(verified=True)
        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount
    
    # === Feedback Publication Link (v2) ===
    
    def create_feedback_link(
        self, link: FeedbackPublicationLink
    ) -> FeedbackPublicationLink:
        """Create feedback publication link.
        
        Args:
            link: FeedbackPublicationLink instance
            
        Returns:
            Created FeedbackPublicationLink
        """
        self.session.add(link)
        self.session.commit()
        self.session.refresh(link)
        return link
    
    def get_feedback_link(
        self, tenant: str, issue_id: str
    ) -> Optional[FeedbackPublicationLink]:
        """Get feedback publication link.
        
        Args:
            tenant: Tenant ID
            issue_id: Issue ID
            
        Returns:
            FeedbackPublicationLink or None
        """
        stmt = select(FeedbackPublicationLink).where(
            and_(
                FeedbackPublicationLink.tenant == tenant,
                FeedbackPublicationLink.issue_id == issue_id
            )
        )
        return self.session.scalar(stmt)
    
    def update_feedback_link_status(
        self, tenant: str, issue_id: str, status: str
    ) -> int:
        """Update feedback link status.
        
        Args:
            tenant: Tenant ID
            issue_id: Issue ID
            status: New status
            
        Returns:
            Number of rows updated
        """
        stmt = update(FeedbackPublicationLink).where(
            and_(
                FeedbackPublicationLink.tenant == tenant,
                FeedbackPublicationLink.issue_id == issue_id
            )
        ).values(status=status)
        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount
    
    # === Publication Fence (v2) ===
    
    def get_fence_counter(self) -> int:
        """Get current fence counter value.
        
        Returns:
            Counter value
        """
        stmt = select(PublicationFence).where(
            PublicationFence.id == 1
        )
        fence = self.session.scalar(stmt)
        return fence.counter if fence else 0
    
    def increment_fence_counter(self) -> int:
        """Increment and return fence counter.
        
        Returns:
            New counter value
        """
        stmt = update(PublicationFence).where(
            PublicationFence.id == 1
        ).values(counter=PublicationFence.counter + 1)
        result = self.session.execute(stmt)
        self.session.commit()
        
        # Refresh to get new value
        stmt = select(PublicationFence).where(PublicationFence.id == 1)
        fence = self.session.scalar(stmt)
        return fence.counter if fence else 0
    
    def claim_with_fence(self, work_id: str, tenant: str) -> int:
        """Claim work with fencing.
        
        Args:
            work_id: Work ID
            tenant: Tenant ID
            
        Returns:
            Fence value at claim time
        """
        fence_value = self.increment_fence_counter()
        stmt = update(PublicationWork).where(
            PublicationWork.id == work_id
        ).values(
            fence=fence_value,
            tenant=tenant
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return fence_value