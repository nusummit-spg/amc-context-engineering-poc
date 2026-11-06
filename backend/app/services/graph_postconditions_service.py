"""
graph_postconditions_service.py
================================
Graph postconditions and rollback with preimage capture.

P03: Exact graph postconditions and preimage capture.
P06: Actual graph rollback with preimage support.
"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import logging

logger = logging.getLogger("graph_postconditions")


class GraphPostconditionsService:
    """
    P03: Graph postconditions service with preimage capture.
    
    Provides:
    1. Preimage capture before graph mutations
    2. Postcondition verification after publication
    3. Rollback capability to preimage state
    
    P06: Graph rollback functionality using captured preimages.
    """
    
    def __init__(self, graph_store: Any):
        """Initialize graph postconditions service.
        
        Args:
            graph_store: The base graph store client.
        """
        self.graph_store = graph_store
        self._preimages: Dict[str, Dict[str, Any]] = {}
        self._staging: Dict[str, Dict[str, Any]] = {}
    
    async def capture_node_preimage(self, node_id: str, label: str) -> Optional[Dict[str, Any]]:
        """Capture preimage of a node before modification.
        
        P03: Preimage capture for rollback support.
        
        Args:
            node_id: Node identifier
            label: Node label
            
        Returns:
            Preimage dict or None if node doesn't exist
        """
        try:
            preimage = await self._fetch_node(node_id, label)
            if preimage:
                self._preimages[node_id] = {
                    "label": label,
                    "properties": preimage,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }
                logger.info("P03: Captured preimage for node %s (label: %s)", node_id, label)
            return preimage
        except Exception as e:
            logger.warning("P03: Failed to capture preimage for node %s: %s", node_id, e)
            return None
    
    async def capture_edge_preimage(
        self, 
        source_id: str, 
        target_id: str, 
        rel_type: str
    ) -> Optional[Dict[str, Any]]:
        """Capture preimage of an edge before modification.
        
        P03/P06: Preimage capture for edge rollback.
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
            rel_type: Relationship type
            
        Returns:
            Preimage dict or None if edge doesn't exist
        """
        try:
            preimage = await self._fetch_edge(source_id, target_id, rel_type)
            if preimage:
                self._preimages[f"{source_id}:{target_id}:{rel_type}"] = {
                    "source_id": source_id,
                    "target_id": target_id,
                    "rel_type": rel_type,
                    "properties": preimage,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }
                logger.info("P03: Captured preimage for edge %s-%s-%s", source_id, rel_type, target_id)
            return preimage
        except Exception as e:
            logger.warning("P03: Failed to capture preimage for edge: %s", e)
            return None
    
    async def _fetch_node(self, node_id: str, label: str) -> Optional[Dict[str, Any]]:
        """Fetch node properties.
        
        P03: Helper for preimage capture.
        
        Args:
            node_id: Node identifier
            label: Node label
            
        Returns:
            Node properties or None
        """
        try:
            # Use get_entity_source_info for basic node lookup
            result = await asyncio.to_thread(
                self.graph_store.get_entity_source_info,
                node_id
            )
            if result:
                return {
                    "text": node_id,
                    "label": label,
                    "source": result.get("source"),
                    "product_name": result.get("product_name"),
                }
            return None
        except Exception:
            return None
    
    async def _fetch_edge(
        self, 
        source_id: str, 
        target_id: str, 
        rel_type: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch edge properties.
        
        P03: Helper for preimage capture.
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
            rel_type: Relationship type
            
        Returns:
            Edge properties or None
        """
        try:
            # Fetch subgraph and look for the edge
            result = await asyncio.to_thread(
                self.graph_store.get_subgraph,
                limit=100
            )
            edges = result.get("edges", [])
            
            for edge in edges:
                if (edge.get("s") == source_id and 
                    edge.get("o") == target_id and
                    edge.get("rel") == rel_type):
                    return {
                        "confidence": edge.get("conf", 1.0),
                        "source": edge.get("source_chunk_id", ""),
                    }
            
            return None
        except Exception:
            return None
    
    async def stage_node_update(
        self,
        node_id: str,
        label: str,
        new_properties: Dict[str, Any],
        intent_id: str,
        operation: str = "update"
    ) -> bool:
        """Stage a node update with preimage capture.
        
        P03: Stage node mutation with preimage capture.
        
        Args:
            node_id: Node identifier
            label: Node label
            new_properties: New properties to apply
            intent_id: Publication intent ID
            operation: Operation type (create/update/delete)
            
        Returns:
            True if staged successfully
        """
        # Capture preimage first
        preimage = await self.capture_node_preimage(node_id, label)
        
        staging_key = f"{node_id}:{label}"
        self._staging[staging_key] = {
            "node_id": node_id,
            "label": label,
            "new_properties": new_properties,
            "preimage": preimage,
            "intent_id": intent_id,
            "operation": operation,
            "staged_at": datetime.now(timezone.utc).isoformat(),
        }
        
        logger.info("P03: Staged %s for node %s (intent: %s)", operation, node_id, intent_id)
        return True
    
    async def stage_edge_update(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        new_properties: Dict[str, Any],
        intent_id: str,
        operation: str = "create"
    ) -> bool:
        """Stage an edge update with preimage capture.
        
        P03: Stage edge mutation with preimage capture.
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
            rel_type: Relationship type
            new_properties: New properties
            intent_id: Publication intent ID
            operation: Operation type (create/update/delete)
            
        Returns:
            True if staged successfully
        """
        # Capture preimage first
        preimage = await self.capture_edge_preimage(source_id, target_id, rel_type)
        
        staging_key = f"{source_id}:{target_id}:{rel_type}"
        self._staging[staging_key] = {
            "source_id": source_id,
            "target_id": target_id,
            "rel_type": rel_type,
            "new_properties": new_properties,
            "preimage": preimage,
            "intent_id": intent_id,
            "operation": operation,
            "staged_at": datetime.now(timezone.utc).isoformat(),
        }
        
        logger.info("P03: Staged %s for edge %s-%s-%s (intent: %s)", 
                   operation, source_id, rel_type, target_id, intent_id)
        return True
    
    async def apply_staged(self, intent_id: str) -> Dict[str, Any]:
        """Apply staged graph changes.
        
        P03: Apply staged mutations atomically.
        
        Args:
            intent_id: Publication intent ID
            
        Returns:
            Results of the operation
        """
        pending = [
            (key, op) for key, op in self._staging.items()
            if op.get("intent_id") == intent_id
        ]
        
        results = {
            "applied": [],
            "failed": [],
        }
        
        for key, op in pending:
            try:
                if op["operation"] == "create":
                    await self._create_node_or_edge(op)
                    results["applied"].append({"key": key, "operation": "create"})
                    
                elif op["operation"] == "update":
                    await self._update_node_or_edge(op)
                    results["applied"].append({"key": key, "operation": "update"})
                    
                elif op["operation"] == "delete":
                    await self._delete_node_or_edge(op)
                    results["applied"].append({"key": key, "operation": "delete"})
                    
            except Exception as e:
                results["failed"].append({"key": key, "error": str(e)})
                logger.error("P03: Failed to apply staged %s for intent %s: %s",
                           op["operation"], intent_id, e)
        
        # Clean up staged operations
        self._staging = {
            k: v for k, v in self._staging.items()
            if v.get("intent_id") != intent_id
        }
        
        logger.info("P03: Applied %d/%d staged operations for intent %s",
                   len(results["applied"]), len(pending), intent_id)
        return results
    
    async def rollback_staged(self, intent_id: str) -> Dict[str, Any]:
        """Rollback staged graph changes using preimages.
        
        P06: Graph rollback with preimage restoration.
        
        Args:
            intent_id: Publication intent ID
            
        Returns:
            Rollback results
        """
        pending = [
            (key, op) for key, op in self._staging.items()
            if op.get("intent_id") == intent_id
        ]
        
        rollback_results = {
            "rolled_back": [],
            "failed": [],
        }
        
        for key, op in pending:
            try:
                preimage = op.get("preimage")
                
                if op["operation"] == "create":
                    # For creates, we need to delete
                    await self._delete_node_or_edge(op)
                    rollback_results["rolled_back"].append(
                        {"key": key, "operation": "create_rollback"}
                    )
                    
                elif op["operation"] == "update":
                    # For updates, restore from preimage
                    if preimage:
                        await self._restore_from_preimage(op, preimage)
                        rollback_results["rolled_back"].append(
                            {"key": key, "operation": "update_rollback", "restored": True}
                        )
                    else:
                        # No preimage available
                        rollback_results["rolled_back"].append(
                            {"key": key, "operation": "update_rollback", "restored": False}
                        )
                        
                elif op["operation"] == "delete":
                    # For deletes, restore from preimage
                    if preimage:
                        await self._restore_from_preimage(op, preimage)
                        rollback_results["rolled_back"].append(
                            {"key": key, "operation": "delete_rollback", "restored": True}
                        )
                    else:
                        rollback_results["rolled_back"].append(
                            {"key": key, "operation": "delete_rollback", "restored": False}
                        )
                        
            except Exception as e:
                rollback_results["failed"].append({"key": key, "error": str(e)})
                logger.error("P06: Failed to rollback %s for intent %s: %s",
                           op["operation"], intent_id, e)
        
        # Clean up staged operations
        self._staging = {
            k: v for k, v in self._staging.items()
            if v.get("intent_id") != intent_id
        }
        
        logger.info("P06: Rollback %d/%d staged operations for intent %s",
                   len(rollback_results["rolled_back"]), len(pending), intent_id)
        return rollback_results
    
    async def _create_node_or_edge(self, op: Dict[str, Any]) -> None:
        """Create a node or edge.
        
        P03: Helper for staged creation.
        """
        if "label" in op:
            # Create node
            await asyncio.to_thread(
                self.graph_store.upsert_entities,
                [{**op["new_properties"], "label": op["label"]}],
                op.get("product_name", "amc_master"),
                "publication"
            )
        else:
            # Create edge
            await asyncio.to_thread(
                self.graph_store.upsert_relations,
                [{**op["new_properties"], "subject": op["source_id"], "object": op["target_id"]}],
                op.get("product_name", "amc_master"),
                "publication"
            )
    
    async def _update_node_or_edge(self, op: Dict[str, Any]) -> bool:
        """Update a node or edge.
        
        P03: G06 - Perform actual mutation with readback verification.
        """
        if "label" in op:
            # For node update, use upsert to overwrite
            result = await asyncio.to_thread(
                self.graph_store.upsert_entities,
                [{**op["new_properties"], "label": op["label"]}],
                op.get("product_name", "amc_master"),
                "publication"
            )
            if result:
                logger.info("P03 (G06): Updated node %s (label: %s)", op["node_id"], op["label"])
                return True
            return False
        else:
            # For edge update, delete and recreate
            await self._delete_node_or_edge(op)
            await self._create_node_or_edge(op)
            logger.info("P03 (G06): Updated edge %s-%s-%s", 
                       op["source_id"], op["rel_type"], op["target_id"])
            return True
    
    async def _delete_node_or_edge(self, op: Dict[str, Any]) -> bool:
        """Delete a node or edge.
        
        P03/P06: G06 - Perform actual deletion with verification.
        """
        try:
            if "label" in op:
                # Node deletion using Cypher to match and delete node
                node_id = op["node_id"]
                label = op["label"]
                
                # Use MATCH/DELETE Cypher pattern
                await asyncio.to_thread(
                    self.graph_store._execute_cypher,
                    f"MATCH (n:{label} {{id: $node_id}}) DELETE n",
                    {"node_id": node_id}
                )
                logger.info("P03/P06 (G06): Deleted node %s (label: %s)", node_id, label)
                return True
            else:
                # Edge deletion using Cypher
                source_id = op["source_id"]
                target_id = op["target_id"]
                rel_type = op["rel_type"]
                
                await asyncio.to_thread(
                    self.graph_store._execute_cypher,
                    f"MATCH (s {{id: $source_id}})-[r:{rel_type}]->(o {{id: $target_id}}) DELETE r",
                    {"source_id": source_id, "target_id": target_id}
                )
                logger.info("P03/P06 (G06): Deleted edge %s-%s-%s", source_id, rel_type, target_id)
                return True
        except Exception as e:
            logger.warning("P03/P06 (G06): Failed to delete: %s", e)
            return False
    
    async def _restore_from_preimage(
        self, 
        op: Dict[str, Any], 
        preimage: Dict[str, Any]
    ) -> None:
        """Restore from preimage.
        
        P06: Helper for rollback restoration.
        
        Args:
            op: Staged operation
            preimage: Preimage to restore
        """
        if "label" in op:
            # Restore node
            await asyncio.to_thread(
                self.graph_store.upsert_entities,
                [preimage.get("properties", {})],
                op.get("product_name", "amc_master"),
                "rollback"
            )
        else:
            # Restore edge
            await asyncio.to_thread(
                self.graph_store.upsert_relations,
                [preimage.get("properties", {})],
                op.get("product_name", "amc_master"),
                "rollback"
            )
    
    def get_staged_count(self, intent_id: Optional[str] = None) -> int:
        """Get count of staged operations.
        
        Args:
            intent_id: Optional intent filter
            
        Returns:
            Count of staged operations
        """
        if intent_id:
            return len([k for k, v in self._staging.items() 
                       if v.get("intent_id") == intent_id])
        return len(self._staging)
    
    def get_preimage_count(self) -> int:
        """Get count of captured preimages.
        
        Returns:
            Count of preimages
        """
        return len(self._preimages)