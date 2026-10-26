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
        """Initialize a new instance of RepairServiceClient.

        Args:
            base_url (str): The base url.
        """
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
        """Create correction patch in repair engine.

        Returns:
            patch_id: Unique identifier for the patch

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.
            canonical_value (Any): The canonical value.
            corrected_value (Any): The corrected value.
            confidence (float): The confidence.
            provenance (Dict[str, Any]): The provenance.
            approved (bool): The approved.
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
        """Get all patches for specified entities.

        Used during query orchestration to apply corrections.

        Args:
            entity_ids (List[str]): Collection or list of entity ids.

        Returns:
            List[Dict[str, Any]]: List of resulting items or records.
        """
        params = {"entity_ids": ",".join(entity_ids)}
        response = await self.get("/api/patches/for-entities", params=params)
        return response.get("patches", [])
    
    async def get_pending_corrections(self) -> List[Dict[str, Any]]:
        """Get all pending (unapproved) corrections.

        Returns:
            List[Dict[str, Any]]: List of resulting items or records.
        """
        response = await self.get("/api/patches/pending")
        return response.get("patches", [])
    
    async def approve_patch(self, patch_id: str) -> bool:
        """Approve a correction patch.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        response = await self.post(f"/api/patches/{patch_id}/approve", {})
        return response.get("status") == "approved"
    
    async def reject_patch(
        self,
        patch_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """Reject a correction patch.

        Args:
            patch_id (str): Unique identifier of the patch.
            reason (Optional[str]): The reason.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        payload = {"reason": reason} if reason else {}
        response = await self.post(f"/api/patches/{patch_id}/reject", payload)
        return response.get("status") == "rejected"
    
    async def batch_approve_patches(
        self,
        patch_ids: List[str]
    ) -> Dict[str, List[str]]:
        """Batch approve multiple patches.

        Args:
            patch_ids (List[str]): Collection or list of patch ids.

        Returns:
            Dict[str, List[str]]: List of resulting items or records.
        """
        payload = {"patch_ids": patch_ids}
        return await self.post("/api/patches/batch-approve", payload)
    
    async def run_governance_batch(
        self,
        auto_approve_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """Trigger governance batch execution.

        Args:
            auto_approve_threshold (Optional[float]): The auto approve threshold.

        Returns:
            Dict[str, Any]: Dictionary containing result data or status.
        """
        payload = {}
        if auto_approve_threshold:
            payload["auto_approve_threshold"] = auto_approve_threshold
        
        logger.info("Triggering governance batch")
        
        return await self.post("/api/governance/run-batch", payload)
