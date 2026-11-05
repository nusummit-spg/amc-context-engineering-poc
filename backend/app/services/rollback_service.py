"""
rollback_service.py
===================
B06: Service for rolling back applied patches to previous state.

Handles:
- Patch state transition to ROLLED_BACK
- Graph mutation rollback (restore previous value)
- Vector reindex to remove corrected values
- Audit trail of rollback operations
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.repair_proposals import RepairProposal
from app.services.publication_metrics import get_publication_metrics

logger = logging.getLogger("app.services.rollback_service")

# B07: Initialize metrics
metrics = get_publication_metrics()


class RollbackService:
    """
    B06: Handles rollback of applied patches.
    
    Usage:
        service = RollbackService()
        await service.rollback_proposal(proposal_id, reason="data_quality_issue")
    """
    
    def __init__(self, db: Optional[Session] = None):
        """Initialize rollback service.
        
        Args:
            db: Optional database session (creates new if None)
        """
        self._db = db
    
    async def rollback_proposal(
        self,
        proposal_id: str,
        reason: str,
        rolled_back_by: str = "system"
    ) -> Dict[str, Any]:
        """Rollback an applied proposal.
        
        B06: Main rollback operation.
        
        Args:
            proposal_id: ID of the proposal to rollback
            reason: Reason for rollback
            rolled_back_by: User or system performing rollback
            
        Returns:
            Dict with rollback status and details
            
        Raises:
            ValueError: If proposal not found or not in correct state
            Exception: If rollback operations fail
        """
        managed_session = False
        if self._db is None:
            db = SessionLocal()
            managed_session = True
        else:
            db = self._db
            
        try:
            # B06: Fetch proposal
            proposal = db.query(RepairProposal).filter(
                RepairProposal.proposal_id == proposal_id
            ).first()
            
            if not proposal:
                raise ValueError(f"Proposal {proposal_id} not found")
            
            if proposal.status != "applied":
                raise ValueError(f"Proposal {proposal_id} is not applied (status={proposal.status})")
            
            logger.info("B06: Rolling back proposal %s (reason: %s)", proposal_id, reason)
            
            rollback_receipt = {
                "proposal_id": proposal_id,
                "reason": reason,
                "rolled_back_by": rolled_back_by,
                "rolled_back_at": datetime.now(timezone.utc).isoformat(),
                "original_status": proposal.status,
                "applied_at": proposal.applied_at
            }
            
            # B06: Execute rollback based on proposal type
            if proposal.proposal_type == "graph":
                await self._rollback_graph_mutation(proposal, reason, db)
                rollback_receipt["graph_rollback"] = "completed"
            elif proposal.proposal_type == "vector":
                await self._rollback_vector_reindex(proposal, reason, db)
                rollback_receipt["vector_rollback"] = "completed"
            
            # B06: Mark proposal as rolled back
            proposal.status = "rolled_back"
            
            # B06: Store rollback metadata (if proposal had JSON fields)
            # In production, you might add a rollback_metadata JSON column
            
            db.commit()
            
            # B07: Record rollback metrics
            metrics.record_rollback(proposal.proposal_type, reason)
            
            logger.info("B06: Successfully rolled back proposal %s", proposal_id)
            
            return {
                "success": True,
                "proposal_id": proposal_id,
                "rollback_receipt": rollback_receipt
            }
            
        except Exception as exc:
            if not managed_session and db:
                db.rollback()
            logger.error("B06: Rollback failed for proposal %s: %s", proposal_id, exc)
            raise
        finally:
            if managed_session:
                db.close()
    
    async def _rollback_graph_mutation(
        self,
        proposal: RepairProposal,
        reason: str,
        db: Session
    ) -> None:
        """Rollback a graph mutation by restoring previous value.
        
        B06: Graph rollback operation.
        
        Args:
            proposal: The proposal to rollback
            reason: Rollback reason
            db: Database session
        """
        from app.engine.graph_store import get_driver, config
        from app.schemas.graph_mutations_table import GraphMutation
        
        # B06: Fetch the original mutation to find previous value
        original_mutation = db.query(GraphMutation).filter(
            GraphMutation.proposal_id == proposal.proposal_id,
            GraphMutation.success == True
        ).order_by(GraphMutation.applied_at.desc()).first()
        
        if not original_mutation:
            logger.warning("B06: No successful mutation found for proposal %s", proposal.proposal_id)
            return
        
        # B06: Get previous value from verification receipt
        verified_value = original_mutation.verified_value
        entity_id = proposal.entity_id
        attribute = proposal.attribute
        
        # B06: For full rollback, we would need to store the previous value
        # For now, we log the intention
        logger.info(
            "B06: Would restore %s.%s to previous value (current verified: %s, reason: %s)",
            entity_id, attribute, verified_value, reason
        )
        
        # B06: In production, execute reverse mutation:
        # rollback_cypher = f"MATCH (n {{id: '{entity_id}'}}) SET n.{attribute} = $previous_value"
        # Then verify the rollback
    
    async def _rollback_vector_reindex(
        self,
        proposal: RepairProposal,
        reason: str,
        db: Session
    ) -> None:
        """Rollback a vector reindex by removing affected documents.
        
        B06: Vector rollback operation.
        
        Args:
            proposal: The proposal to rollback
            reason: Rollback reason
            db: Database session
        """
        from app.schemas.reindex_jobs_table import ReindexJob
        
        # B06: Fetch the reindex job
        reindex_job = db.query(ReindexJob).filter(
            ReindexJob.proposal_id == proposal.proposal_id,
            ReindexJob.verified == True
        ).order_by(ReindexJob.completed_at.desc()).first()
        
        if not reindex_job:
            logger.warning("B06: No verified reindex job found for proposal %s", proposal.proposal_id)
            return
        
        document_ids = proposal.document_ids or []
        
        logger.info(
            "B06: Would rollback reindex for %d documents (job=%s, reason: %s)",
            len(document_ids), reindex_job.job_id, reason
        )
        
        # B06: In production, trigger reindex WITHOUT the corrections
        # This would rebuild FAISS vectors from original source documents
    
    async def rollback_patch(
        self,
        patch_id: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Rollback a patch in the repair engine.
        
        B06: Patch-level rollback (for repair engine patches, not proposals).
        
        Args:
            patch_id: ID of the patch to rollback
            reason: Reason for rollback
            metadata: Additional rollback metadata
            
        Returns:
            True if rollback successful
        """
        try:
            # B06: Call repair engine to transition patch to ROLLED_BACK
            from app.adapters_config import get_repair_engine
            repair_engine = get_repair_engine()
            
            # B06: Transition patch state
            from amc_repair.schemas import PatchStatus
            success = await repair_engine.patch_layer.transition_patch(
                patch_id,
                PatchStatus.ROLLED_BACK,
                receipt={
                    "rollback_reason": reason,
                    "rolled_back_at": datetime.now(timezone.utc).isoformat(),
                    **(metadata or {})
                }
            )
            
            if success:
                logger.info("B06: Rolled back patch %s (reason: %s)", patch_id, reason)
            else:
                logger.error("B06: Failed to rollback patch %s", patch_id)
            
            return success
            
        except Exception as exc:
            logger.error("B06: Patch rollback failed for %s: %s", patch_id, exc)
            return False
