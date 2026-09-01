# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
regulatory_lifecycle_enricher.py
==================================
Phase 7: Detect and manage regulatory document supersessions.

Key functions:
  - Auto-detect supersession from SEBI feed parsing (Phase 5)
  - Store proposed edges in Neo4j with pending_confirmation=True
  - Provide admin review UI for confirming/rejecting edges
  - Update graph and provenance when confirmed
  - Drop superseded documents from active retrieval set
"""
from __future__ import annotations
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.engine import config
from app.engine.graph_store import run_safe_cypher
from app.engine.provenance_ledger import (
    DocumentStatus,
    get_ledger,
)


logger = logging.getLogger(__name__)
_PROPOSED_EDGES_LOG = config.LOG_DIR / "proposed_supersession_edges.jsonl"


@dataclass
class SupersessionEdge:
    """Proposed regulatory supersession relationship."""
    edge_id: str
    source_doc_hash: str
    target_doc_hash: str
    source_title: str
    target_title: str
    confidence: float
    reason: str  # "title_parsing", "manual_confirmation", etc.
    detected_at: str
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[str] = None
    rejected_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    status: str = "pending"  # pending, confirmed, rejected
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_doc_hash": self.source_doc_hash,
            "target_doc_hash": self.target_doc_hash,
            "source_title": self.source_title,
            "target_title": self.target_title,
            "confidence": self.confidence,
            "reason": self.reason,
            "detected_at": self.detected_at,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
            "rejected_at": self.rejected_at,
            "rejection_reason": self.rejection_reason,
            "status": self.status,
        }


class SupersessionManager:
    """Manages regulatory supersession detection and confirmation."""
    
    def __init__(self, edges_log: Path = _PROPOSED_EDGES_LOG):
        self.edges_log = edges_log
        self._load_edges()
    
    def _load_edges(self) -> None:
        """Load all edges from log file."""
        self.edges: Dict[str, SupersessionEdge] = {}
        if self.edges_log.exists():
            with open(self.edges_log, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        edge = SupersessionEdge(**data)
                        self.edges[edge.edge_id] = edge
                    except json.JSONDecodeError:
                        continue
    
    def _save_edge(self, edge: SupersessionEdge) -> None:
        """Append edge to log file."""
        self.edges_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.edges_log, "a") as f:
            f.write(json.dumps(edge.to_dict()) + "\n")
    
    def propose_supersession(
        self,
        old_doc_hash: str,
        new_doc_hash: str,
        old_title: str,
        new_title: str,
        confidence: float = 0.9,
        reason: str = "title_parsing"
    ) -> SupersessionEdge:
        """
        Propose a new supersession edge.
        
        Args:
            old_doc_hash: hash of superseded document
            new_doc_hash: hash of new/superseding document
            old_title: title of old document
            new_title: title of new document
            confidence: confidence score (0.0-1.0)
            reason: how the supersession was detected
            
        Returns:
            SupersessionEdge object
        """
        edge_id = str(uuid.uuid4())[:8]
        edge = SupersessionEdge(
            edge_id=edge_id,
            source_doc_hash=old_doc_hash,
            target_doc_hash=new_doc_hash,
            source_title=old_title,
            target_title=new_title,
            confidence=confidence,
            reason=reason,
            detected_at=datetime.now(timezone.utc).isoformat(),
            status="pending"
        )
        
        self.edges[edge_id] = edge
        self._save_edge(edge)
        
        logger.info(
            f"[enricher] Proposed supersession: {old_title} -> {new_title} "
            f"(confidence={confidence})"
        )
        
        return edge
    
    def get_pending_edges(self) -> List[SupersessionEdge]:
        """Get all pending (unconfirmed) supersession edges."""
        return [e for e in self.edges.values() if e.status == "pending"]
    
    def confirm_supersession(
        self,
        edge_id: str,
        confirmed_by: str
    ) -> bool:
        """
        Confirm a proposed supersession edge.
        Updates provenance ledger and Neo4j graph.
        
        Args:
            edge_id: ID of the edge to confirm
            confirmed_by: username confirming the edge
            
        Returns:
            True if confirmed successfully
        """
        if edge_id not in self.edges:
            logger.error(f"[enricher] Edge not found: {edge_id}")
            return False
        
        edge = self.edges[edge_id]
        if edge.status != "pending":
            logger.warning(f"[enricher] Edge {edge_id} is not pending (status={edge.status})")
            return False
        
        # Update edge
        edge.status = "confirmed"
        edge.confirmed_by = confirmed_by
        edge.confirmed_at = datetime.now(timezone.utc).isoformat()
        
        # Update provenance ledger
        ledger = get_ledger()
        old_rec = ledger.find_by_hash(edge.source_doc_hash)
        if old_rec:
            ledger.update_status(
                edge.source_doc_hash,
                DocumentStatus.SUPERSEDED,
                superseded_by_hash=edge.target_doc_hash
            )
            logger.info(
                f"[enricher] Marked {old_rec.filename} as superseded by "
                f"{edge.target_doc_hash[:8]}..."
            )
        
        # Create Neo4j relationship
        self._create_graph_supersession_edge(edge)
        
        # Log confirmation
        self._save_edge(edge)
        
        logger.info(f"[enricher] Confirmed supersession edge: {edge_id}")
        return True
    
    def reject_supersession(
        self,
        edge_id: str,
        reason: str = ""
    ) -> bool:
        """
        Reject a proposed supersession edge.
        
        Args:
            edge_id: ID of the edge to reject
            reason: optional rejection reason
            
        Returns:
            True if rejected successfully
        """
        if edge_id not in self.edges:
            logger.error(f"[enricher] Edge not found: {edge_id}")
            return False
        
        edge = self.edges[edge_id]
        edge.status = "rejected"
        edge.rejected_at = datetime.now(timezone.utc).isoformat()
        edge.rejection_reason = reason
        
        self._save_edge(edge)
        
        logger.info(f"[enricher] Rejected supersession edge: {edge_id}")
        return True
    
    def _create_graph_supersession_edge(self, edge: SupersessionEdge) -> None:
        """Create Neo4j SUPERSEDES relationship."""
        try:
            cypher = """
                MATCH (old_doc:Document {sha256_hash: $old_hash})
                MATCH (new_doc:Document {sha256_hash: $new_hash})
                CREATE (old_doc)-[r:SUPERSEDES {
                    confirmed_at: $confirmed_at,
                    confirmed_by: $confirmed_by
                }]->(new_doc)
                RETURN r
            """
            
            params = {
                "old_hash": edge.source_doc_hash,
                "new_hash": edge.target_doc_hash,
                "confirmed_at": edge.confirmed_at,
                "confirmed_by": edge.confirmed_by,
            }
            
            result = run_safe_cypher(cypher, params)
            logger.info(f"[enricher] Created Neo4j SUPERSEDES relationship")
        except Exception as e:
            logger.error(f"[enricher] Failed to create graph edge: {e}")
    
    def get_active_documents_for_retrieval(self) -> List[str]:
        """
        Get list of active (non-superseded) document filenames for retrieval.
        Used by retrieval.py to filter results.
        """
        ledger = get_ledger()
        return ledger.get_active_filenames()


# Module singleton
_manager: Optional[SupersessionManager] = None


def get_supersession_manager() -> SupersessionManager:
    """Get the global supersession manager instance."""
    global _manager
    if _manager is None:
        _manager = SupersessionManager()
    return _manager


def upsert_regulatory_document(
    filename: str,
    source_hash: str,
    title: str,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Upsert a regulatory document into the enrichment system.
    Called by ingestion_gateway after a document is ingested.
    
    Returns:
        report with any supersessions detected
    """
    report = {
        "filename": filename,
        "source_hash": source_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "supersessions_proposed": [],
    }
    
    # Check if this document supersedes any existing documents
    # (This would be populated by sebi_feed_ingester.detect_supersession_from_title)
    # For now, just log that enrichment occurred
    
    logger.info(f"[enricher] Upserted document: {filename}")
    return report


def detect_and_link_amendments(
    circular_title: str,
    circular_content: str
) -> List[SupersessionEdge]:
    """
    Detect amendment relationships in circular text.
    
    Examples:
      - "Amendment to Circular ABC-2021-123"
      - "Clarification on Master Circular XYZ"
    """
    edges = []
    import re
    
    # Pattern: Amendment to/of Circular/Master Circular [number]
    pattern = r"(?:Amendment|Modification|Clarification|Addendum).*?(?:to|of)\s+(?:Circular|Master Circular)\s+([A-Z0-9\-]+)"
    
    for match in re.finditer(pattern, circular_title, re.IGNORECASE):
        ref_id = match.group(1)
        
        # Would look up ref_id in graph to find the original document
        logger.info(f"[enricher] Detected amendment reference: {ref_id}")
    
    return edges


def get_pending_proposed_edges() -> List[Dict[str, Any]]:
    """Get all pending proposed supersession edges (for admin UI)."""
    manager = get_supersession_manager()
    pending = manager.get_pending_edges()
    
    return [
        {
            "edge_id": e.edge_id,
            "source": e.source_title[:50],
            "target": e.target_title[:50],
            "confidence": e.confidence,
            "reason": e.reason,
        }
        for e in pending
    ]


def confirm_supersession_edge(edge_id: str, authorized_by: str) -> bool:
    """Admin-triggered: confirm a proposed edge."""
    manager = get_supersession_manager()
    return manager.confirm_supersession(edge_id, authorized_by)


def reject_supersession_edge(edge_id: str, reason: str = "") -> bool:
    """Admin-triggered: reject a proposed edge."""
    manager = get_supersession_manager()
    return manager.reject_supersession(edge_id, reason)


if __name__ == "__main__":
    manager = get_supersession_manager()
    
    # Test: Propose a supersession
    edge = manager.propose_supersession(
        old_doc_hash="abc123",
        new_doc_hash="def456",
        old_title="Circular 2023-123: NAV Disclosure",
        new_title="Amended Circular 2023-123: NAV Disclosure",
        confidence=0.95
    )
    print(f"Proposed edge: {edge.edge_id}")
    print(f"Pending edges: {manager.get_pending_edges()}")
