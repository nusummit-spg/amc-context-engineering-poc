"""
Correction Patch Layer managing provisional and approved entity patches with self-healing retrieval injection.
"""
import uuid
from typing import Any, Dict, List, Optional
from .config import RepairConfig
from .schemas import CorrectionPatch
from .adapters.base import CacheAdapter
from .logging import get_repair_logger, log_step_info, log_step_debug, log_step_warning

logger = get_repair_logger("patch_layer")

class CorrectionPatchLayer:
    def __init__(self, config: RepairConfig, cache_adapter: CacheAdapter):
        """Initialize a new instance of CorrectionPatchLayer.

        Args:
            config (RepairConfig): Configuration dictionary or settings object.
            cache_adapter (CacheAdapter): The cache adapter.
        """
        self.config = config
        self.cache = cache_adapter
        self._prefix = config.redis_key_prefix

    def _key(self, patch_id: str) -> str:
        """Key.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            str: Resulting str instance.
        """
        return f"{self._prefix}{patch_id}"

    async def create_patch(
        self,
        entity_id: str,
        attribute: str,
        corrected_value: Any,
        original_value: Optional[Any] = None,
        canonical_value: Optional[Any] = None,
        confidence: float = 1.0,
        source: str = "feedback",
        auto_approve: bool = False,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> CorrectionPatch:
        """Create patch.

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.
            corrected_value (Any): The corrected value.
            original_value (Optional[Any]): The original value.
            canonical_value (Optional[Any]): The canonical value.
            confidence (float): The confidence.
            source (str): The source.
            auto_approve (bool): The auto approve.
            provenance (Optional[Dict[str, Any]]): The provenance.

        Returns:
            CorrectionPatch: Resulting CorrectionPatch instance.
        """
        patch_id = f"patch_{uuid.uuid4().hex[:12]}"
        orig = canonical_value if canonical_value is not None else original_value
        patch = CorrectionPatch(
            patch_id=patch_id,
            entity_id=entity_id,
            attribute=attribute,
            corrected_value=corrected_value,
            original_value=orig,
            canonical_value=orig,
            confidence=confidence,
            approved=auto_approve,
            source=source,
            provenance=provenance or {},
        )
        await self.cache.set(self._key(patch_id), patch.to_dict())
        log_step_info(
            logger,
            "PATCH_LAYER_CREATE",
            "Stored patch %s in cache (entity=%s.%s, val=%s, approved=%s)",
            patch_id,
            entity_id,
            attribute,
            corrected_value,
            auto_approve,
        )
        return patch

    async def get_patch(self, patch_id: str) -> Optional[CorrectionPatch]:
        """Retrieve patch.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            Optional[CorrectionPatch]: Matching object or record if found, None otherwise.
        """
        data = await self.cache.get(self._key(patch_id))
        if data:
            return CorrectionPatch(**data)
        return None

    async def approve_patch(self, patch_id: str) -> bool:
        """Approve patch.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        patch = await self.get_patch(patch_id)
        if not patch:
            log_step_warning(logger, "PATCH_LAYER_APPROVE_MISS", "Patch %s not found for approval", patch_id)
            return False
        patch.approved = True
        await self.cache.set(self._key(patch_id), patch.to_dict())
        log_step_info(logger, "PATCH_LAYER_APPROVED", "Patch %s approved in cache layer", patch_id)
        return True

    async def reject_patch(self, patch_id: str) -> bool:
        """Reject patch.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        res = await self.cache.delete(self._key(patch_id))
        log_step_info(logger, "PATCH_LAYER_REJECTED", "Patch %s rejected (deleted=%s)", patch_id, res)
        return res

    async def get_all_pending(self) -> List[CorrectionPatch]:
        """Retrieve all pending.

        Returns:
            List[CorrectionPatch]: List of resulting items or records.
        """
        keys = await self.cache.get_keys_by_pattern(f"{self._prefix}*")
        pending: List[CorrectionPatch] = []
        for k in keys:
            data = await self.cache.get(k)
            if data and not data.get("approved", False):
                pending.append(CorrectionPatch(**data))
        return pending

    async def get_active_patches(self, entity_id: Optional[str] = None) -> List[CorrectionPatch]:
        """Retrieve active patches.

        Args:
            entity_id (Optional[str]): Unique identifier of the entity.

        Returns:
            List[CorrectionPatch]: List of resulting items or records.
        """
        keys = await self.cache.get_keys_by_pattern(f"{self._prefix}*")
        active: List[CorrectionPatch] = []
        target = entity_id.strip().lower() if entity_id else ""
        for k in keys:
            data = await self.cache.get(k)
            if data and data.get("approved", False):
                p = CorrectionPatch(**data)
                p_eid = (p.entity_id or "").strip().lower()
                if not target or p_eid == target or target in p_eid or p_eid in target:
                    active.append(p)
        return active

    async def get_patches_for_entity(self, entity_id: str) -> List[CorrectionPatch]:
        """Get all patches (active or for entity) for a given entity ID.

        Args:
            entity_id (str): Unique identifier of the entity.

        Returns:
            List[CorrectionPatch]: List of resulting items or records.
        """
        keys = await self.cache.get_keys_by_pattern(f"{self._prefix}*")
        matches: List[CorrectionPatch] = []
        target = entity_id.strip().lower() if entity_id else ""
        for k in keys:
            data = await self.cache.get(k)
            if data:
                e_id = (data.get("entity_id") or "").strip().lower()
                if e_id and (e_id == target or target in e_id or e_id in target):
                    matches.append(CorrectionPatch(**data))
        return matches

    async def apply_patches_to_context(
        self,
        entities: List[str],
        retrieval_context: str
    ) -> str:
        """Injects verified active correction patches into retrieved text context.

        Args:
            entities (List[str]): List of entity identifiers or objects.
            retrieval_context (str): The retrieval context.

        Returns:
            str: Resulting str instance.
        """
        modified_context = retrieval_context
        applied_count = 0
        for eid in entities:
            patches = await self.get_active_patches(entity_id=eid)
            for p in patches:
                notice = f"\n[CORRECTION PATCH APPLIED: {p.attribute} = {p.corrected_value} (supersedes prior context)]\n"
                modified_context = notice + modified_context
                applied_count += 1
        if applied_count > 0:
            log_step_info(logger, "PATCH_INJECT_CONTEXT", "Injected %d active patches into context for entities %s", applied_count, entities)
        else:
            log_step_debug(logger, "PATCH_INJECT_CONTEXT", "No active patches found for entities %s", entities)
        return modified_context

    async def clear_all(self):
        """Clear all.
        """
        keys = await self.cache.get_keys_by_pattern(f"{self._prefix}*")
        for k in keys:
            await self.cache.delete(k)
