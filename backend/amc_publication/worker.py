"""Durable publication worker for Wave 1.9.

Processes outbox events by creating publication work records and executing them
with proper fencing, idempotency, and durability guarantees.

Wave 1.9 durable publication foundation.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import SessionLocal
from app.schemas.outbox_events_table import OutboxEvent
from app.schemas.repair_proposals import RepairProposal

from .models import (
    PublicationWork, PublicationEffect, GenerationPointer,
    PublicationReceipt, PublicationFence, FeedbackPublicationLink
)
from .repository import PublicationRepository
from .journal import Journal
from .graph import GraphPort
from .artifacts import ImmutableSnapshotStore
from .types import Conflict, VerificationFailed

logger = logging.getLogger("amc_publication.worker")


class PublicationWorker:
    """Wave 1.9 durable publication worker with graph and vector processing.
    
    This worker processes publication jobs from the journal with proper
    graph/vector coordination, fencing, and durable receipts.
    """

    def __init__(self, journal: Journal, graph: GraphPort, 
                 snapshots: ImmutableSnapshotStore, *, simulation_mode: bool = False,
                 owner: str = "worker_default", failpoint=None):
        """Initialize PublicationWorker.
        
        Args:
            journal: Journal instance for job tracking
            graph: GraphPort for graph CAS operations
            snapshots: ImmutableSnapshotStore for vector corpus snapshots
            simulation_mode: If True, skip actual graph writes (for testing)
            owner: Worker owner identifier (kept for backward compatibility)
            failpoint: Optional dict for simulating failures (kept for backward compatibility)
        """
        self.journal = journal
        self.graph = graph
        self.snapshots = snapshots
        self.simulation_mode = simulation_mode
        self.owner = owner
        self.failpoint = failpoint
        
        # Production worker must have verified FAISS binary for snapshots
        if not simulation_mode:
            # Verify that at least one generation has been staged and verified
            # FAISS binary must exist for production workers
            if not snapshots.root.exists() or not any(snapshots.root.iterdir()):
                raise ValueError("FAISS binary verification required for production worker")
        
        logger.info("PublicationWorker initialized (simulation_mode=%s)", simulation_mode)

    def run_once(self) -> Dict[str, Any]:
        """Process one publication job and return status.
        
        Returns:
            Dict with 'status' key ('published', 'rolled_back', 'failed', etc.)
        """
        # Claim a job from the journal
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        claim = self.journal.claim(self.owner, now)
        
        if not claim:
            logger.debug("PublicationWorker: no jobs to process")
            return {"status": "no_jobs"}
        
        logger.info("PublicationWorker: claimed job %s (mode=%s)", claim.work_id, claim.mode)
        
        if claim.mode == "rollback":
            return self._process_rollback(claim)
        else:
            return self._process_publication(claim)

    def _process_publication(self, claim) -> Dict[str, Any]:
        """Process a publication job."""
        payload = claim.payload
        tenant = claim.tenant
        entity = payload.get("entity")
        attribute = payload.get("attribute")
        corrected_value = payload.get("corrected_value")
        
        # Step 1: Get preimage from graph
        pre_result = self.graph.read(tenant, entity, attribute)
        preimage = {"value": pre_result["value"]}
        
        # Failpoint for graph_preimage_committed
        if self.failpoint:
            self.failpoint("graph_preimage_committed")
        
        # Step 2: Stage vector corpus (if provided)
        vector_snapshot = payload.get("full_vector_snapshot", [])
        if vector_snapshot:
            try:
                generation = self.snapshots.stage(tenant, vector_snapshot)
            except ValueError as exc:
                self.journal.retry(claim, exc)
                return {"status": "retry_scheduled", "error": str(exc)}
            logger.info("PublicationWorker: staged vector corpus %s", generation.digest)
            # Prepare vector effect with the generation as dict
            self.journal.prepare(claim, kind="vector", target=entity,
                                pre={"generation_id": None}, 
                                post={"generation_id": generation.generation_id, 
                                      "digest": generation.digest, "count": generation.count})
            # Failpoint for vector_preimage_committed
            if self.failpoint:
                self.failpoint("vector_preimage_committed")
        
        # Step 3: Prepare graph effect (durable before write)
        postimage = {"value": corrected_value}
        self.journal.prepare(claim, kind="graph", target=entity, 
                            pre=preimage, post=postimage)
        # Failpoint for graph_written
        if self.failpoint:
            self.failpoint("graph_written")
        
        # Step 4: Execute graph CAS (if not simulation, but update InMemoryGraphPort even in simulation)
        if not self.simulation_mode:
            try:
                self.graph.compare_and_set(
                    tenant, entity, attribute, preimage, corrected_value, claim.fence
                )
            except (Conflict, VerificationFailed) as exc:
                self.journal.retry(claim, exc)
                return {"status": "failed", "error": str(exc)}
        else:
            # In simulation mode, still update in-memory graph for testing
            self.graph.compare_and_set(
                tenant, entity, attribute, preimage, corrected_value, claim.fence
            )
       # Failpoint for graph_verified
        if self.failpoint:
            self.failpoint("graph_verified")

        # Step 5: Independent graph readback — W22-10 / PUB06 fix.
        # Must NOT use the intended postimage; call graph.read() independently.
        actual = self.graph.read(tenant, entity, attribute)
        if actual.get("value") != corrected_value:
            err = VerificationFailed(
                f"Graph readback mismatch for {tenant}/{entity}/{attribute}: "
                f"expected {corrected_value!r}, got {actual.get('value')!r}"
            )
            self.journal.retry(claim, err)
            return {"status": "failed", "error": str(err)}
        # Pass the OBSERVED value from independent readback, not the intended postimage.
        self.journal.verified(claim, kind="graph", target=entity, observed={"value": actual["value"]})
        # Failpoint for pointer_switched (after graph verified)
        if self.failpoint and vector_snapshot:
            self.failpoint("pointer_switched")
        
        # Step 6: Switch vector pointer (if corpus staged)
        if vector_snapshot:
            expected = self.journal.pointer(tenant, "vector_faiss")
            self.journal.switch_pointer(
                claim, namespace="vector_faiss", expected=expected,
                new_id=generation.digest, digest=generation.digest
            )
            # Verify vector effect - observed should match what was passed to prepare()
            observed_vector = {"generation_id": generation.generation_id, 
                              "digest": generation.digest, "count": generation.count}
            self.journal.verified(claim, kind="vector", target=entity, observed=observed_vector)
            # Failpoint for vector_verified
            if self.failpoint:
                self.failpoint("vector_verified")
        
        # Step 7: Publish and get receipt
        receipt_id = self.journal.publish(claim)
        
        logger.info("PublicationWorker: published job %s with receipt %s", 
                   claim.work_id, receipt_id)
        
        return {"status": "published", "receipt_id": receipt_id, "work_id": claim.work_id}

    def _process_rollback(self, claim) -> Dict[str, Any]:
        """Process a rollback job."""
        payload = claim.payload
        tenant = claim.tenant
        entity = payload.get("entity")
        attribute = payload.get("attribute")
        
         # Get current active pointer — this is what we roll back FROM.
        current = self.journal.pointer(tenant, "vector_faiss")

        # Failpoint for vector_rollback_committed
        if self.failpoint:
            self.failpoint("vector_rollback_committed")

        # REC03 / W22-11: read the vector effect preimage — this is what was
        # active BEFORE this publication and must be CAS-restored, not deleted.
        with self.journal.sessions() as _s:
            _vec = _s.scalar(select(PublicationEffect).where(
                PublicationEffect.work_id == claim.work_id,
                PublicationEffect.kind == "vector",
                PublicationEffect.target == entity))
        before = dict(_vec.preimage) if _vec and _vec.preimage else {"generation_id": None, "digest": None}

        # CAS from current → prior verified generation (or deactivate if no prior).
        self.journal.switch_back(
            claim,
            current_id=current.get("generation_id") or "",
            current_digest=current.get("digest") or "",
            before=before,
        )
        
        # Read stored graph preimage and restore graph value
        with self.journal.sessions() as s:
            effect = s.scalar(select(PublicationEffect).where(
                PublicationEffect.work_id == claim.work_id, 
                PublicationEffect.kind == "graph",
                PublicationEffect.target == entity))
            if effect and effect.preimage:
                preimage = effect.preimage
                # Read current graph value for CAS expected value
                current_value = self.graph.read(tenant, entity, attribute)
                # Restore graph to preimage value using current value as expected
                self.graph.compare_and_set(
                    tenant, entity, attribute, 
                    current_value,  # Current value is expected
                    preimage.get("value"),  # Restore to preimage
                    claim.fence
                )
        
        # Compensate graph effect
        self.journal.compensate(claim, kind="graph", target=entity)
        
        # Compensate vector effect
        self.journal.compensate(claim, kind="vector", target=entity)
        
        # Finish rollback
        self.journal.finish_rollback(claim)
        
        logger.info("PublicationWorker: rolled back job %s", claim.work_id)
        
        return {"status": "rolled_back", "work_id": claim.work_id}

# B07: Initialize metrics
from app.services.publication_metrics import get_publication_metrics
metrics = get_publication_metrics()


class DurableWorker:
    """Durable publication worker for Wave 1.9."""
    
    def __init__(self, db: Optional[Session] = None):
        """Initialize worker.
        
        Args:
            db: Optional database session (creates new if None)
        """
        self._db = db
        self._repo: Optional[PublicationRepository] = None
    
    def _get_repo(self, db: Session) -> PublicationRepository:
        """Get or create repository for session.
        
        Args:
            db: Database session
            
        Returns:
            PublicationRepository instance
        """
        if self._repo is None:
            self._repo = PublicationRepository(db)
        return self._repo
    
    def process_pending_events(self, limit: int = 100) -> Dict[str, Any]:
        """Process pending outbox events and create publication work records.
        
        Args:
            limit: Maximum number of events to process
            
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
            # Fetch pending events
            events = db.query(OutboxEvent).filter(
                OutboxEvent.status == "pending",
                OutboxEvent.retry_count < OutboxEvent.max_retries
            ).order_by(OutboxEvent.created_at).limit(limit).all()
            
            if not events:
                logger.debug("DurableWorker: No pending outbox events")
                return {"processed": 0, "failed": 0, "skipped": 0}
            
            logger.info("DurableWorker: Processing %d outbox events", len(events))
            
            processed = 0
            failed = 0
            
            for event in events:
                try:
                    # Mark as processing
                    event.status = "processing"
                    db.commit()
                    
                    # Create publication work record
                    work = self._create_work_for_event(event, db)
                    
                    # Mark event as processed
                    event.status = "completed"
                    event.processed_at = datetime.now(timezone.utc).isoformat()
                    db.commit()
                    
                    processed += 1
                    logger.info("DurableWorker: Created work %s for event %s",
                              work.id, event.event_id)
                    
                except Exception as exc:
                    # Handle failure with retry
                    event.retry_count += 1
                    event.error = str(exc)
                    
                    if event.retry_count >= event.max_retries:
                        event.status = "failed"
                        failed += 1
                        logger.error("DurableWorker: Event %s failed after %d retries: %s",
                                   event.event_id, event.retry_count, exc)
                    else:
                        event.status = "pending"
                        logger.warning("DurableWorker: Event %s failed (retry %d/%d): %s",
                                     event.event_id, event.retry_count, event.max_retries, exc)
                    
                    db.commit()
            
            return {
                "processed": processed,
                "failed": failed,
                "skipped": 0,
                "total": len(events)
            }
            
        finally:
            if managed_session:
                db.close()
    
    def _create_work_for_event(
        self, event: OutboxEvent, db: Session
    ) -> PublicationWork:
        """Create publication work record for an outbox event.
        
        Args:
            event: Outbox event
            db: Database session
            
        Returns:
            PublicationWork instance
        """
        repo = self._get_repo(db)
        
        # Extract proposal_id from payload
        payload = event.payload or {}
        proposal_id = payload.get("proposal_id")
        
        # Get proposal for metadata
        proposal = None
        if proposal_id:
            proposal = db.query(RepairProposal).filter(
                RepairProposal.proposal_id == proposal_id
            ).first()
        
        # Create idempotency key from event
        idempotency_key = f"{event.aggregate_type}:{event.aggregate_id}:{event.event_type}"
        
        # Create work record
        work = PublicationWork(
            id=f"work_{uuid.uuid4().hex[:12]}",
            tenant=payload.get("tenant", "default"),
            idempotency_key=idempotency_key,
            proposal_id=proposal_id or "unknown",
            approved_revision=proposal.approved_revision if proposal else 1,
            payload_hash=self._compute_payload_hash(payload),
            payload=payload,
            status="queued",
            epoch=0,
            fence=0,
            owner=None,
            lease_until=None,
            attempts=0,
            max_attempts=5,
            last_error=None,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        
        return repo.create_work(work)
    
    def _compute_payload_hash(self, payload: Dict[str, Any]) -> str:
        """Compute payload hash for idempotency.
        
        Args:
            payload: Event payload
            
        Returns:
            Hex hash string
        """
        import hashlib
        import json
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()[:16]
    
    def claim_work(self, work_id: str, worker_id: str) -> Optional[PublicationWork]:
        """Claim work with fencing.
        
        Args:
            work_id: Work ID
            worker_id: Worker identifier
            
        Returns:
            PublicationWork if claimed, None otherwise
        """
        managed_session = False
        if self._db is None:
            db = SessionLocal()
            managed_session = True
        else:
            db = self._db
            
        try:
            repo = self._get_repo(db)
            
            # Get work
            work = repo.get_work_by_id(work_id)
            if not work:
                return None
            
            # Check if already leased
            if work.status == "leased":
                logger.warning("DurableWorker: Work %s already leased", work_id)
                return None
            
            # Claim with fence
            fence_value = repo.claim_with_fence(work_id, worker_id)
            
            # Update status
            work.status = "leased"
            work.owner = worker_id
            work.lease_until = datetime.now(timezone.utc).replace(tzinfo=None)
            work.epoch = fence_value
            work.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            
            logger.info("DurableWorker: Claimed work %s (fence=%d, worker=%s)",
                      work_id, fence_value, worker_id)
            
            return work
            
        finally:
            if managed_session:
                db.close()
    
    def execute_work(self, work: PublicationWork) -> Dict[str, Any]:
        # """Execute a publication work.
        
        # Args:
        #     work: PublicationWork to execute
            
        # Returns:
        #     Execution results
        # """
        # managed_session = False
        # if self._db is None:
        #     db = SessionLocal()
        #     managed_session = True
        # else:
        #     db = self._db
            
        # try:
        #     repo = self._get_repo(db)
            
        #     # Create effect records
        #     effect_id = f"eff_{uuid.uuid4().hex[:12]}"
        #     effect = PublicationEffect(
        #         id=effect_id,
        #         work_id=work.id,
        #         tenant=work.tenant,
        #         kind=work.payload.get("event_type", "unknown"),
        #         target=work.payload.get("proposal_id", "unknown"),
        #         preimage={},
        #         postimage={},
        #         pre_hash="pending",
        #         post_hash="pending",
        #         state="prepared",
        #         claim_epoch=work.epoch,
        #         verified_at=None,
        #         created_at=datetime.now(timezone.utc).replace(tzinfo=None)
        #     )
            
        #     effect = repo.create_effect(effect)
            
        #     # Update work status
        #     work.status = "published"
        #     work.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        #     db.commit()
            
        #     logger.info("DurableWorker: Executed work %s (effect=%s)",
        #               work.id, effect_id)
            
        #     return {
        #         "work_id": work.id,
        #         "effect_id": effect_id,
        #         "status": "published"
        #     }
            
        # finally:
        #     if managed_session:
        #         db.close()
        """DISABLED — W22-12 / PUB04: previously marked work 'published' using
        placeholder hashes without any Neo4j/FAISS proof. That is a phantom receipt.

        The authoritative publication path is:
            Journal.claim() → PublicationWorker.run_once()

        DurableWorker may only bridge legacy outbox events into Journal jobs
        via _create_work_for_event(). It must never issue receipts.
        """
        raise RuntimeError(
            "DurableWorker.execute_work is disabled (W22-12). "
            "Use Journal + PublicationWorker for verified publication."
        )
    
    
    def process_all(self, limit: int = 100, worker_id: str = "default") -> Dict[str, Any]:
        """Process all pending events — bridge outbox to Journal only.

        W22-12 / PUB03: DurableWorker may only translate outbox events into
        Journal work records. It must NOT execute or publish work.
        PublicationWorker.run_once() is the sole authoritative execution path.
        """
        create_result = self.process_pending_events(limit)

        return {
            "created_work": create_result["processed"],
            "executed_work": 0,
            "failed": create_result["failed"],
            "note": "Work records created; PublicationWorker must claim and execute them.",
        }
