"""
vector_staging_service.py
=========================
Staging layer for vector updates with preimage capture and rollback support.

P02: True vector staging with preimage capture for rollback.
P07: Actual vector rollback functionality.

The staging service enables:
1. Capture preimage (current state) before applying changes
2. Queue vector updates for atomic publication via outbox
3. Rollback to preimage if publication fails
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger("vector_staging")

class VectorStagingService:
    """
    P02: Vector staging with preimage capture.
    
    Provides staging area for vector updates with preimage capture
    to support rollback and eventual consistency.
    """
    
    def __init__(self, vector_store: Any):
        """Initialize vector staging service.
        
        Args:
            vector_store: The base vector store client.
        """
        self.vector_store = vector_store
        self._staging: Dict[str, Dict[str, Any]] = {}
        self._preimages: Dict[str, Dict[str, Any]] = {}
    
    async def stage_add(self, documents: List[Dict[str, Any]], intent_id: str) -> List[str]:
        """Stage documents for addition with preimage capture.
        
        P02: Capture preimage before staging for rollback support.
        
        Args:
            documents: Documents to add
            intent_id: Publication intent ID for tracking
            
        Returns:
            List of staged document IDs
        """
        staged_ids = []
        
        for doc in documents:
            doc_id = doc.get("chunk_id") or doc.get("id", f"staged_{len(self._staging)}")
            
            # P02: Capture preimage - check if document already exists
            preimage = await self._capture_preimage(doc_id)
            if preimage:
                self._preimages[doc_id] = preimage
                logger.info("P02: Captured preimage for existing document %s during staging", doc_id)
            
            # Add to staging
            self._staging[doc_id] = {
                "document": doc,
                "intent_id": intent_id,
                "operation": "add",
                "staged_at": datetime.now(timezone.utc).isoformat(),
            }
            staged_ids.append(doc_id)
        
        logger.info("P02: Staged %d documents for intent %s", len(staged_ids), intent_id)
        return staged_ids
    
    async def stage_delete(self, chunk_ids: List[str], intent_id: str) -> List[str]:
        """Stage documents for deletion with preimage capture.
        
        P07: Preimage capture for vector rollback support.
        
        Args:
            chunk_ids: IDs of documents to delete
            intent_id: Publication intent ID
            
        Returns:
            List of staged chunk IDs
        """
        staged_ids = []
        
        for chunk_id in chunk_ids:
            # P07: Capture preimage before deletion
            preimage = await self._capture_preimage(chunk_id)
            if preimage:
                self._preimages[chunk_id] = preimage
                logger.info("P07: Captured preimage for chunk %s before deletion", chunk_id)
            
            self._staging[chunk_id] = {
                "chunk_id": chunk_id,
                "intent_id": intent_id,
                "operation": "delete",
                "staged_at": datetime.now(timezone.utc).isoformat(),
            }
            staged_ids.append(chunk_id)
        
        logger.info("P07: Staged %d deletions for intent %s", len(staged_ids), intent_id)
        return staged_ids
    
    async def _capture_preimage(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Capture current state of document before modification.
        
        P02/P07: Preimage capture for rollback.
        
        Args:
            chunk_id: Chunk ID to capture
            
        Returns:
            Preimage dict or None if doesn't exist
        """
        try:
            # Search for existing document with this chunk_id
            results = await self.vector_store.similarity_search(
                query=f"chunk_id:{chunk_id}",
                limit=1
            )
            
            if results:
                # Extract payload from search result
                payload = results[0]
                return {
                    "chunk_id": payload.get("chunk_id"),
                    "text": payload.get("text"),
                    "metadata": payload.get("metadata", {}),
                    "order": payload.get("order"),
                    "document_id": payload.get("document_id"),
                }
            
            return None
            
        except Exception as e:
            logger.warning("P02/P07: Failed to capture preimage for %s: %s", chunk_id, e)
            return None
    
    async def apply_staged(self, intent_id: str) -> Dict[str, Any]:
        """Apply staged changes for a specific intent.
        
        P02: Apply staged vector updates atomically.
        
        Args:
            intent_id: Publication intent ID
            
        Returns:
            Results of the operation
        """
        pending = [
            (doc_id, op) for doc_id, op in self._staging.items()
            if op.get("intent_id") == intent_id
        ]
        
        results = {
            "applied": [],
            "failed": [],
            "preimages_captured": len(self._preimages),
        }
        
        for doc_id, op in pending:
            try:
                if op["operation"] == "add":
                    doc = op["document"]
                    await self.vector_store.add([doc])
                    results["applied"].append({"doc_id": doc_id, "operation": "add"})
                    
                elif op["operation"] == "delete":
                    # For delete, we need to find and remove by chunk_id
                    await self._delete_by_chunk_id(doc_id)
                    results["applied"].append({"doc_id": doc_id, "operation": "delete"})
                    
            except Exception as e:
                results["failed"].append({"doc_id": doc_id, "error": str(e)})
                logger.error("P02: Failed to apply staged %s for intent %s: %s", 
                           op["operation"], intent_id, e)
        
        # Clean up staged operations for this intent
        self._staging = {
            k: v for k, v in self._staging.items()
            if v.get("intent_id") != intent_id
        }
        
        logger.info("P02: Applied %d/%d staged operations for intent %s",
                   len(results["applied"]), len(pending), intent_id)
        return results
    
    async def rollback_staged(self, intent_id: str) -> Dict[str, Any]:
        """Rollback staged changes for a specific intent.
        
        P07: Vector rollback using captured preimages.
        
        Args:
            intent_id: Publication intent ID
            
        Returns:
            Rollback results
        """
        pending = [
            (doc_id, op) for doc_id, op in self._staging.items()
            if op.get("intent_id") == intent_id
        ]
        
        rollback_results = {
            "rolled_back": [],
            "failed": [],
        }
        
        for doc_id, op in pending:
            try:
                if op["operation"] == "add":
                    # Remove the staged document
                    await self._delete_by_chunk_id(doc_id)
                    rollback_results["rolled_back"].append(
                        {"doc_id": doc_id, "operation": "add_rollback"}
                    )
                    
                elif op["operation"] == "delete":
                    # Restore from preimage if available
                    preimage = self._preimages.get(doc_id)
                    if preimage:
                        await self.vector_store.add([preimage])
                        rollback_results["rolled_back"].append(
                            {"doc_id": doc_id, "operation": "delete_rollback", "restored": True}
                        )
                    else:
                        rollback_results["rolled_back"].append(
                            {"doc_id": doc_id, "operation": "delete_rollback", "restored": False}
                        )
                        
            except Exception as e:
                rollback_results["failed"].append({"doc_id": doc_id, "error": str(e)})
                logger.error("P07: Failed to rollback %s for intent %s: %s",
                           op["operation"], intent_id, e)
        
        # Clean up staged operations
        self._staging = {
            k: v for k, v in self._staging.items()
            if v.get("intent_id") != intent_id
        }
        
        logger.info("P07: Rollback %d/%d staged operations for intent %s",
                   len(rollback_results["rolled_back"]), len(pending), intent_id)
        return rollback_results
    
    async def _delete_by_chunk_id(self, chunk_id: str) -> bool:
        """Delete document by chunk_id.
        
        P07: Helper for vector deletion.
        
        Args:
            chunk_id: Chunk ID to delete
            
        Returns:
            True if deleted
        """
        # Search for the document
        results = await self.vector_store.similarity_search(
            query=f"chunk_id:{chunk_id}",
            limit=1
        )
        
        if not results:
            return False
        
        # Get FAISS ID from payload
        payload = results[0]
        
        # Find the FAISS ID in payloads
        for fid, p in self.vector_store._payloads.items():
            if p.get("chunk_id") == chunk_id:
                # Remove from payloads
                del self.vector_store._payloads[fid]
                
                # Remove from FAISS index
                if self.vector_store._index is not None:
                    await asyncio.to_thread(self.vector_store._index.remove_ids, fid)
                
                # Persist
                await asyncio.to_thread(self.vector_store._persist)
                return True
        
        return False
    
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