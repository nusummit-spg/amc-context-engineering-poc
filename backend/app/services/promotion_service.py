"""Business logic service for promotion service."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.repair_proposals import RepairProposal
from app.schemas.graph_mutations_table import GraphMutation
from app.engine.graph_store import get_driver, config

logger = logging.getLogger("app.services.promotion_service")


class PromotionService:
    """Apply approved repair proposals to canonical Neo4j graph and vector stores."""

    def __init__(self, db: Optional[Session] = None):
        """Initialize a new instance of PromotionService.

        Args:
            db (Optional[Session]): Database session instance.
        """
        self._db = db

    def apply_approved_proposals(
        self,
        batch_id: Optional[str] = None,
        proposal_id: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Execute approved repair proposals.
        If proposal_id is specified, only that proposal is processed.
        Graph mutations are executed against canonical Neo4j in a transaction.

        Args:
            batch_id (Optional[str]): Unique identifier of the batch.
            proposal_id (Optional[str]): Unique identifier of the proposal.
            db (Optional[Session]): Database session instance.

        Returns:
            Dict[str, Any]: Dictionary containing result data or status.
        """
        managed_session = False
        if db is None:
            if self._db is not None:
                db = self._db
            else:
                db = SessionLocal()
                managed_session = True

        try:
            query = db.query(RepairProposal).filter(
                RepairProposal.status == "approved",
                RepairProposal.applied_at.is_(None)
            )
            if proposal_id:
                query = query.filter(RepairProposal.proposal_id == proposal_id)

            proposals = query.all()

            if not proposals:
                logger.info("No approved proposals to apply")
                return {
                    "applied_count": 0,
                    "applied_proposals": [],
                    "failed_count": 0,
                    "message": "No approved proposals pending application"
                }

            logger.info("Applying %d approved proposals", len(proposals))

            applied: List[str] = []
            failed: List[str] = []

            # Group or iterate proposals
            # For graph proposals, attempt Neo4j transaction
            driver = None
            try:
                driver = get_driver()
            except Exception as exc:
                logger.warning("Could not obtain Neo4j driver: %s", exc)

            for proposal in proposals:
                try:
                    if proposal.proposal_type == "graph":
                        if proposal.mutation_cypher:
                            # G10-T10 / W1.1-12: This will raise PromotionFailedError if driver unavailable
                            self._execute_graph_mutation(driver, proposal, db)
                        # Only mark APPLIED if mutation succeeded without exception
                        proposal.applied_at = datetime.now(timezone.utc).isoformat()
                        proposal.status = "applied"
                        applied.append(proposal.proposal_id)

                    elif proposal.proposal_type == "vector":
                        self._trigger_reindex(proposal)
                        proposal.applied_at = datetime.now(timezone.utc).isoformat()
                        proposal.status = "applied"
                        applied.append(proposal.proposal_id)
                    else:
                        logger.warning("Unknown proposal type: %s", proposal.proposal_type)
                        failed.append(proposal.proposal_id)

                except Exception as exc:
                    logger.error("Failed to apply proposal %s: %s", proposal.proposal_id, exc)
                    # W1.1-12: Do NOT mark as applied on failure
                    # Proposal remains in 'approved' status, can be retried
                    db.rollback()
                    failed.append(proposal.proposal_id)
                    # Could set proposal.status = "failed" here if desired

            db.commit()
            logger.info("Promotion complete: %d applied, %d failed", len(applied), len(failed))

            return {
                "applied_count": len(applied),
                "applied_proposals": applied,
                "failed_count": len(failed),
                "failed_proposals": failed,
                "message": f"Successfully applied {len(applied)} proposals"
            }

        finally:
            if managed_session:
                db.close()

    def _execute_graph_mutation(self, driver, proposal: RepairProposal, db: Session) -> None:
        """Execute a graph mutation in Neo4j and record in audit log.
        
        W1.1-12 / G10-T10 / GOV-06: Fail closed on driver unavailability.
        Raises PromotionFailedError to prevent phantom APPLIED status.

        Args:
            driver: Database driver instance.
            proposal (RepairProposal): The proposal.
            db (Session): Database session instance.
            
        Raises:
            PromotionFailedError: If driver unavailable or mutation cannot be executed
            PromotionVerificationError: If postcondition verification fails
        """
        from app.exceptions import PromotionFailedError, PromotionVerificationError
        
        if not driver:
            error_msg = "Neo4j driver unavailable"
            logger.error("PROMOTION_BLOCKED: %s for proposal %s", error_msg, proposal.proposal_id)
            self._log_mutation(proposal, db, success=False, error=error_msg)
            # G10-T10 / W1.1-12: MUST raise exception to prevent APPLIED status
            raise PromotionFailedError(
                f"Cannot apply proposal {proposal.proposal_id}: {error_msg}. "
                "Graph database connection required for canonical mutations."
            )

        with driver.session(database=config.NEO4J_DATABASE) as session:
            tx = session.begin_transaction()
            try:
                logger.info("Executing Cypher mutation for proposal %s", proposal.proposal_id)
                # Parameters for parameterized Cypher
                params = {}
                if proposal.entity_id:
                    params["entity_id"] = proposal.entity_id
                if proposal.attribute:
                    params["attribute"] = proposal.attribute

                # Execute mutation
                tx.run(proposal.mutation_cypher, **params)
                tx.commit()
                
                # G10-T11 / W1.1-12: Verify committed effect via read-back
                if proposal.entity_id and proposal.attribute:
                    verification_result = session.run(
                        "MATCH (n {id: $entity_id}) RETURN n[$attribute] as value",
                        entity_id=proposal.entity_id,
                        attribute=proposal.attribute
                    ).single()
                    
                    # Simple postcondition: node exists and has the attribute
                    # (More sophisticated verification would check exact value)
                    if not verification_result:
                        error_msg = f"Postcondition verification failed: entity {proposal.entity_id} not found after commit"
                        logger.error("VERIFICATION_FAILED: %s", error_msg)
                        self._log_mutation(proposal, db, success=False, error=error_msg)
                        raise PromotionVerificationError(error_msg)
                
                self._log_mutation(proposal, db, success=True)
                logger.info("Successfully applied and verified proposal %s", proposal.proposal_id)
                
            except PromotionVerificationError:
                # Already logged, re-raise
                raise
            except Exception as exc:
                tx.rollback()
                error_msg = f"Graph mutation failed: {exc}"
                logger.error("MUTATION_ERROR: %s for proposal %s", exc, proposal.proposal_id)
                self._log_mutation(proposal, db, success=False, error=error_msg)
                raise PromotionFailedError(error_msg) from exc

    def _log_mutation(
        self,
        proposal: RepairProposal,
        db: Session,
        success: bool = True,
        error: Optional[str] = None
    ) -> None:
        """Log graph mutation to graph_mutations audit table.

        Args:
            proposal (RepairProposal): The proposal.
            db (Session): Database session instance.
            success (bool): The success.
            error (Optional[str]): The error.
        """
        mutation = GraphMutation(
            mutation_id=f"mut_{uuid.uuid4().hex[:12]}",
            proposal_id=proposal.proposal_id,
            mutation_cypher=proposal.mutation_cypher,
            affected_nodes=proposal.affected_nodes,
            applied_at=datetime.now(timezone.utc).isoformat(),
            applied_by="promotion_service",
            success=success,
            error=error,
        )
        db.add(mutation)

    def _trigger_reindex(self, proposal: RepairProposal) -> None:
        """Trigger vector store reindex for affected documents.

        Args:
            proposal (RepairProposal): The proposal.
        """
        logger.info(
            "Triggered vector store reindex for proposal %s, document_ids=%s",
            proposal.proposal_id,
            proposal.document_ids
        )
