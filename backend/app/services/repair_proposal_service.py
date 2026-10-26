# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
repair_proposal_service.py
===========================
Generates automated repair proposals (graph mutations & vector reindexing)
from adjudicated unified evaluation records.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.repair_proposals import RepairProposal
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.models import _now_iso
from app.services.cypher_validator import get_cypher_validator

logger = logging.getLogger("app.services.repair_proposal")


class RepairProposalService:
    """Generate repair proposals from evaluated unified records."""

    def __init__(self):
        """Initialize a new instance of RepairProposalService.
        """
        self.validator = get_cypher_validator()

    def create_proposal_from_record(
        self,
        record: UnifiedEvaluationRecord,
        db: Session,
        is_approved: bool = False,
    ) -> RepairProposal:
        """Create repair proposal based on record's repair_target and evaluation results.

        Args:
            record (UnifiedEvaluationRecord): The record.
            db (Session): Database session instance.
            is_approved (bool): Whether proposal is already approved via auto-repair.

        Returns:
            RepairProposal: Resulting RepairProposal instance.
        """
        if not record.repair or not record.repair_target:
            raise ValueError(f"Record {record.response_id} does not require repair")

        proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
        repair_target_str = (
            record.repair_target.value
            if hasattr(record.repair_target, "value")
            else str(record.repair_target)
        )

        if repair_target_str == "graph":
            proposal = self._create_graph_proposal(proposal_id, record, db, is_approved=is_approved)
        elif repair_target_str == "vector":
            proposal = self._create_vector_proposal(proposal_id, record, db, is_approved=is_approved)
        else:
            raise ValueError(f"Unknown repair target: {record.repair_target}")

        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        logger.info(
            "Created repair proposal %s (type=%s, target=%s, confidence=%.2f, status=%s)",
            proposal.proposal_id,
            proposal.proposal_type,
            proposal.entity_id or proposal.document_ids,
            proposal.confidence,
            proposal.status,
        )
        return proposal

    def _create_graph_proposal(
        self,
        proposal_id: str,
        record: UnifiedEvaluationRecord,
        db: Session,
        is_approved: bool = False,
    ) -> RepairProposal:
        """Generate safe Cypher mutation proposal for knowledge graph correction.

        Args:
            proposal_id (str): Unique identifier of the proposal.
            record (UnifiedEvaluationRecord): The record.
            db (Session): Database session instance.

        Returns:
            RepairProposal: Resulting RepairProposal instance.
        """
        entity_id = "INF846K01DP5"  # default entity
        attribute = "TER"
        corrected_value = "0.82"

        # Check ResponseFeedback if present
        if record.feedback_ref:
            feedback = (
                db.query(ResponseFeedback)
                .filter(ResponseFeedback.feedback_id == record.feedback_ref)
                .first()
            )
            if feedback:
                classification = feedback.classification_json or {}
                if isinstance(classification, dict):
                    entity_id = classification.get("entity_extracted") or classification.get("entity_id") or entity_id
                    attribute = classification.get("attribute") or attribute
                    corrected_value = classification.get("value_mentioned") or corrected_value

        # Check QueryEvidence context
        evidence = (
            db.query(QueryEvidence)
            .filter(QueryEvidence.response_id == record.response_id)
            .first()
        )
        if evidence and evidence.assembled_context_json:
            assembled = evidence.assembled_context_json
            if isinstance(assembled, list):
                for chunk in assembled:
                    if isinstance(chunk, dict) and chunk.get("entity_id"):
                        entity_id = chunk["entity_id"]
                        break
            elif isinstance(assembled, dict):
                sources = assembled.get("sources") or assembled.get("chunks") or []
                if isinstance(sources, list):
                    for chunk in sources:
                        if isinstance(chunk, dict) and (chunk.get("entity_id") or chunk.get("document_id")):
                            entity_id = chunk.get("entity_id") or chunk.get("document_id")
                            break

        # Check dissatisfaction evidence if available
        if record.dissatisfaction_evidence_json:
            dissatisfaction = record.dissatisfaction_evidence_json
            if isinstance(dissatisfaction, dict) and dissatisfaction.get("structured_claim"):
                claim = dissatisfaction["structured_claim"]
                entity_id = claim.get("resolved_entity_id") or entity_id
                attribute = claim.get("attribute") or attribute
                corrected_value = claim.get("asserted_value") or corrected_value

        mutation_cypher = f"""
MATCH (e {{id: '{entity_id}'}})
SET e.{attribute} = '{corrected_value}',
    e.last_updated = datetime(),
    e.updated_by = 'feedback_loop',
    e.correction_source = '{record.response_id}'
RETURN e
""".strip()

        is_safe, reason = self.validator.validate(mutation_cypher)
        if not is_safe:
            logger.error("Unsafe Cypher mutation rejected for record %s: %s", record.response_id, reason)
            raise ValueError(f"Unsafe mutation: {reason}")

        affected_nodes = self.validator.extract_affected_nodes(mutation_cypher)
        if not affected_nodes:
            affected_nodes = [entity_id]

        confidence = record.adjudication_confidence or 0.85

        return RepairProposal(
            proposal_id=proposal_id,
            unified_record_ref=record.response_id,
            proposal_type="graph",
            entity_id=entity_id,
            attribute=attribute,
            mutation_cypher=mutation_cypher,
            affected_nodes=affected_nodes,
            confidence=confidence,
            status="approved" if is_approved else "pending",
            reviewed_at=_now_iso() if is_approved else None,
            reviewed_by="hands_free_auto_repair" if is_approved else None,
        )

    def _create_vector_proposal(
        self,
        proposal_id: str,
        record: UnifiedEvaluationRecord,
        db: Session,
        is_approved: bool = False,
    ) -> RepairProposal:
        """Generate vector store reindexing proposal.

        Args:
            proposal_id (str): Unique identifier of the proposal.
            record (UnifiedEvaluationRecord): The record.
            db (Session): Database session instance.
            is_approved (bool): Whether proposal is already approved via auto-repair.

        Returns:
            RepairProposal: Resulting RepairProposal instance.
        """
        evidence = (
            db.query(QueryEvidence)
            .filter(QueryEvidence.response_id == record.response_id)
            .first()
        )

        document_ids: List[str] = []
        if evidence and evidence.assembled_context_json:
            assembled = evidence.assembled_context_json
            if isinstance(assembled, list):
                for chunk in assembled:
                    if isinstance(chunk, dict):
                        doc_id = chunk.get("document_id") or chunk.get("doc_id") or chunk.get("chunk_id")
                        if doc_id:
                            document_ids.append(str(doc_id))
            elif isinstance(assembled, dict):
                sources = assembled.get("sources") or assembled.get("chunks") or []
                for chunk in sources:
                    if isinstance(chunk, dict):
                        doc_id = chunk.get("document_id") or chunk.get("doc_id") or chunk.get("chunk_id")
                        if doc_id:
                            document_ids.append(str(doc_id))

        if not document_ids:
            document_ids = [f"doc_{record.response_id}"]

        confidence = record.adjudication_confidence or 0.80

        return RepairProposal(
            proposal_id=proposal_id,
            unified_record_ref=record.response_id,
            proposal_type="vector",
            document_ids=document_ids,
            reindex_required=True,
            confidence=confidence,
            status="approved" if is_approved else "pending",
            reviewed_at=_now_iso() if is_approved else None,
            reviewed_by="hands_free_auto_repair" if is_approved else None,
        )
