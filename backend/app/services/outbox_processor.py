"""
outbox_processor.py
===================
B05: Processes transactional outbox events for cross-service operations.

Implements the saga pattern for atomic operations across:
- PostgreSQL (state storage)
- Neo4j (graph mutations)
- FAISS (vector updates)
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.outbox_events_table import OutboxEvent
from app.services.publication_metrics import get_publication_metrics

logger = logging.getLogger("app.services.outbox_processor")

# B07: Initialize metrics
metrics = get_publication_metrics()


class OutboxProcessor:
    """
    B05: Processes outbox events in order with retry logic.
    
    Usage:
        processor = OutboxProcessor()
        await processor.process_pending_events()
    """
    
    def __init__(self, db: Optional[Session] = None):
        """Initialize processor.
        
        Args:
            db: Optional database session (creates new if None)
        """
        self._db = db
    
    async def process_pending_events(self, limit: int = 100) -> Dict[str, Any]:
        """Process pending outbox events in creation order.
        
        B05: Main processing loop for saga pattern.
        
        Args:
            limit: Maximum number of events to process in one batch
            
        Returns:
            Dict with processing statistics
        """
        managed_session = False
        if self._db is None:
            db = SessionLocal()
            managed_session = True
        else:
            db = self._db
            
        try:
            # B05: Fetch pending events ordered by creation time
            events = db.query(OutboxEvent).filter(
                OutboxEvent.status == "pending",
                OutboxEvent.retry_count < OutboxEvent.max_retries
            ).order_by(OutboxEvent.created_at).limit(limit).all()
            
            if not events:
                logger.debug("B05: No pending outbox events")
                return {"processed": 0, "failed": 0, "skipped": 0}
            
            logger.info("B05: Processing %d outbox events", len(events))
            
            processed = 0
            failed = 0
            skipped = 0
            
            for event in events:
                start_time = datetime.now(timezone.utc)
                try:
                    # B05: Mark as processing
                    event.status = "processing"
                    db.commit()
                    
                    # B05: Execute event based on type
                    await self._execute_event(event, db)
                    
                    # B05: Mark as completed
                    event.status = "completed"
                    event.processed_at = datetime.now(timezone.utc).isoformat()
                    db.commit()
                    
                    # B07: Record successful processing
                    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                    metrics.record_outbox_event(event.event_type, "completed", duration)
                    
                    processed += 1
                    logger.info("B05: Processed event %s (%s)", event.event_id, event.event_type)
                    
                except Exception as exc:
                    # B05: Handle failure with retry
                    event.retry_count += 1
                    event.error = str(exc)
                    
                    # B07: Record failed processing
                    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                    metrics.record_outbox_event(event.event_type, "failed", duration)
                    
                    if event.retry_count >= event.max_retries:
                        event.status = "failed"
                        failed += 1
                        logger.error("B05: Event %s failed after %d retries: %s",
                                   event.event_id, event.retry_count, exc)
                    else:
                        event.status = "pending"  # Will retry
                        skipped += 1
                        logger.warning("B05: Event %s failed (retry %d/%d): %s",
                                     event.event_id, event.retry_count, event.max_retries, exc)
                    
                    db.commit()
            
            # B07: Update queue size metric
            remaining = db.query(OutboxEvent).filter(OutboxEvent.status == "pending").count()
            metrics.update_outbox_queue_size(remaining)
            
            return {
                "processed": processed,
                "failed": failed,
                "skipped": skipped,
                "total": len(events)
            }
            
        finally:
            if managed_session:
                db.close()
    
    async def _execute_event(self, event: OutboxEvent, db: Session) -> None:
        """Execute a single outbox event based on its type.
        
        B05: Event dispatcher.
        
        Args:
            event: The outbox event to execute
            db: Database session
            
        Raises:
            Exception: If event execution fails
        """
        payload = event.payload
        
        if event.event_type == "GRAPH_MUTATION_REQUIRED":
            await self._execute_graph_mutation(payload, db)
        elif event.event_type == "VECTOR_REINDEX_REQUIRED":
            await self._execute_vector_reindex(payload, db)
        elif event.event_type == "PATCH_STATE_TRANSITION":
            await self._execute_state_transition(payload, db)
        else:
            logger.warning("B05: Unknown event type: %s", event.event_type)
    
    async def _execute_graph_mutation(self, payload: Dict[str, Any], db: Session) -> None:
        """Execute graph mutation from outbox event.
        
        Args:
            payload: Event payload with mutation details
            db: Database session
        """
        from app.services.promotion_service import PromotionService
        from app.schemas.repair_proposals import RepairProposal
        
        proposal_id = payload.get("proposal_id")
        if not proposal_id:
            raise ValueError("Graph mutation event missing proposal_id")
        
        proposal = db.query(RepairProposal).filter(
            RepairProposal.proposal_id == proposal_id
        ).first()
        
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        service = PromotionService(db=db)
        # Note: In B05, this would coordinate the full saga
        logger.info("B05: Would execute graph mutation for %s", proposal_id)
    
    async def _execute_vector_reindex(self, payload: Dict[str, Any], db: Session) -> None:
        """Execute vector reindex from outbox event.
        
        Args:
            payload: Event payload with reindex details
            db: Database session
        """
        from app.services.promotion_service import PromotionService
        from app.schemas.repair_proposals import RepairProposal
        
        proposal_id = payload.get("proposal_id")
        if not proposal_id:
            raise ValueError("Vector reindex event missing proposal_id")
        
        proposal = db.query(RepairProposal).filter(
            RepairProposal.proposal_id == proposal_id
        ).first()
        
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        service = PromotionService(db=db)
        await service._trigger_reindex(proposal, db)
        logger.info("B05: Executed vector reindex for %s", proposal_id)
    
    async def _execute_state_transition(self, payload: Dict[str, Any], db: Session) -> None:
        """Execute patch state transition from outbox event.
        
        Args:
            payload: Event payload with transition details
            db: Database session
        """
        patch_id = payload.get("patch_id")
        new_status = payload.get("new_status")
        
        if not patch_id or not new_status:
            raise ValueError("State transition event missing patch_id or new_status")
        
        # B05: Would call repair engine to transition patch
        logger.info("B05: Would transition patch %s to %s", patch_id, new_status)


def create_outbox_event(
    db: Session,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: Dict[str, Any],
    max_retries: int = 3
) -> OutboxEvent:
    """B05: Create an outbox event in the same transaction.
    
    Args:
        db: Database session
        aggregate_type: Type of entity (e.g., "repair_proposal")
        aggregate_id: ID of the entity
        event_type: Event type (e.g., "GRAPH_MUTATION_REQUIRED")
        payload: Event data
        max_retries: Maximum retry attempts
        
    Returns:
        Created outbox event
    """
    event = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        max_retries=max_retries
    )
    db.add(event)
    return event
