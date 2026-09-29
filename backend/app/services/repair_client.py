"""
Client for Repair Engine Service communication.
"""
import logging
from typing import Dict, List, Optional, Any

from .client_base import ServiceClient

logger = logging.getLogger("repair_client")


class RepairServiceClient(ServiceClient):
    """
    Client for communicating with Repair Engine Service.
    
    Used when repair engine and platform are deployed as separate services.
    """
    
    def __init__(self, base_url: str):
        super().__init__(
            base_url=base_url,
            service_name="repair-engine",
            timeout=30.0
        )
    
    async def create_correction_patch(
        self,
        entity_id: str,
        attribute: str,
        canonical_value: Any,
        corrected_value: Any,
        confidence: float,
        provenance: Dict[str, Any],
        approved: bool = False
    ) -> str:
        """
        Create correction patch in repair engine.
        
        Returns:
            patch_id: Unique identifier for the patch
        """
        payload = {
            "entity_id": entity_id,
            "attribute": attribute,
            "canonical_value": canonical_value,
            "corrected_value": corrected_value,
            "confidence": confidence,
            "provenance": provenance,
            "approved": approved
        }
        
        logger.info(f"Creating patch: {entity_id}.{attribute}")
        
        response = await self.post("/api/patches", payload)
        return response["patch_id"]
    
    async def get_patches_for_entities(
        self,
        entity_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Get all patches for specified entities.
        
        Used during query orchestration to apply corrections.
        """
        params = {"entity_ids": ",".join(entity_ids)}
        response = await self.get("/api/patches/for-entities", params=params)
        return response.get("patches", [])
    
    async def get_pending_corrections(self) -> List[Dict[str, Any]]:
        """Get all pending (unapproved) corrections."""
        response = await self.get("/api/patches/pending")
        return response.get("patches", [])
    
    async def approve_patch(self, patch_id: str) -> bool:
        """Approve a correction patch."""
        response = await self.post(f"/api/patches/{patch_id}/approve", {})
        return response.get("status") == "approved"
    
    async def reject_patch(
        self,
        patch_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """Reject a correction patch."""
        payload = {"reason": reason} if reason else {}
        response = await self.post(f"/api/patches/{patch_id}/reject", payload)
        return response.get("status") == "rejected"
    
    async def batch_approve_patches(
        self,
        patch_ids: List[str]
    ) -> Dict[str, List[str]]:
        """Batch approve multiple patches."""
        payload = {"patch_ids": patch_ids}
        return await self.post("/api/patches/batch-approve", payload)
    
    async def run_governance_batch(
        self,
        auto_approve_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """Trigger governance batch execution."""
        payload = {}
        if auto_approve_threshold:
            payload["auto_approve_threshold"] = auto_approve_threshold
        
        logger.info("Triggering governance batch")
        
        return await self.post("/api/governance/run-batch", payload)
