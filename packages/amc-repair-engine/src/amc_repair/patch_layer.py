"""
Correction Patch Layer managing provisional and approved entity patches with self-healing retrieval injection.
"""
import uuid
from typing import Any, Dict, List, Optional
from .config import RepairConfig
from .schemas import CorrectionPatch
from .adapters.base import CacheAdapter

class CorrectionPatchLayer:
    def __init__(self, config: RepairConfig, cache_adapter: CacheAdapter):
        self.config = config
        self.cache = cache_adapter
        self._prefix = config.redis_key_prefix

    def _key(self, patch_id: str) -> str:
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
        return patch

    async def get_patch(self, patch_id: str) -> Optional[CorrectionPatch]:
        data = await self.cache.get(self._key(patch_id))
        if data:
            return CorrectionPatch(**data)
        return None

    async def approve_patch(self, patch_id: str) -> bool:
        patch = await self.get_patch(patch_id)
        if not patch:
            return False
        patch.approved = True
        await self.cache.set(self._key(patch_id), patch.to_dict())
        return True

    async def reject_patch(self, patch_id: str) -> bool:
        return await self.cache.delete(self._key(patch_id))

    async def get_all_pending(self) -> List[CorrectionPatch]:
        keys = await self.cache.get_keys_by_pattern(f"{self._prefix}*")
        pending: List[CorrectionPatch] = []
        for k in keys:
            data = await self.cache.get(k)
            if data and not data.get("approved", False):
                pending.append(CorrectionPatch(**data))
        return pending

    async def get_active_patches(self, entity_id: Optional[str] = None) -> List[CorrectionPatch]:
        keys = await self.cache.get_keys_by_pattern(f"{self._prefix}*")
        active: List[CorrectionPatch] = []
        for k in keys:
            data = await self.cache.get(k)
            if data and data.get("approved", False):
                p = CorrectionPatch(**data)
                if entity_id is None or p.entity_id == entity_id:
                    active.append(p)
        return active

    async def get_patches_for_entity(self, entity_id: str) -> List[CorrectionPatch]:
        """Get all patches (active or for entity) for a given entity ID."""
        keys = await self.cache.get_keys_by_pattern(f"{self._prefix}*")
        matches: List[CorrectionPatch] = []
        for k in keys:
            data = await self.cache.get(k)
            if data and data.get("entity_id") == entity_id:
                matches.append(CorrectionPatch(**data))
        return matches

    async def apply_patches_to_context(
        self,
        entities: List[str],
        retrieval_context: str
    ) -> str:
        """
        Injects verified active correction patches into retrieved text context.
        """
        modified_context = retrieval_context
        for eid in entities:
            patches = await self.get_active_patches(entity_id=eid)
            for p in patches:
                notice = f"\n[CORRECTION PATCH APPLIED: {p.attribute} = {p.corrected_value} (supersedes prior context)]\n"
                modified_context = notice + modified_context
        return modified_context

    async def clear_all(self):
        keys = await self.cache.get_keys_by_pattern(f"{self._prefix}*")
        for k in keys:
            await self.cache.delete(k)
