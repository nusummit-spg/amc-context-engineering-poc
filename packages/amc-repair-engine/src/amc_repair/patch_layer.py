"""
Correction Patch Layer managing provisional and approved entity patches with self-healing retrieval injection.

Wave 1.3 Batch B (B01): State Machine Implementation
- Uses PatchStatus enum for lifecycle management
- Validates state transitions
- Enforces can_serve() for active patches only
"""
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from .config import RepairConfig
from .schemas import CorrectionPatch, PatchStatus
from .adapters.base import CacheAdapter
from .logging import get_repair_logger, log_step_info, log_step_debug, log_step_warning, log_step_error

logger = get_repair_logger("patch_layer")


class StateTransitionError(Exception):
    """B01: Raised when invalid state transition attempted."""
    pass


# B01: Allowed state transitions
ALLOWED_TRANSITIONS = {
    PatchStatus.PENDING: [PatchStatus.APPROVED, PatchStatus.REJECTED],
    PatchStatus.APPROVED: [PatchStatus.STAGED, PatchStatus.REJECTED],
    PatchStatus.STAGED: [PatchStatus.VERIFIED, PatchStatus.FAILED],
    PatchStatus.VERIFIED: [PatchStatus.ACTIVE, PatchStatus.FAILED],
    PatchStatus.ACTIVE: [PatchStatus.ROLLED_BACK, PatchStatus.SUPERSEDED],
    # Terminal states have no valid transitions
    PatchStatus.REJECTED: [],
    PatchStatus.FAILED: [],
    PatchStatus.ROLLED_BACK: [],
    PatchStatus.SUPERSEDED: [],
}

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
        
        B01: All patches start in PENDING status (auto_approve ignored per REP-01).

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.
            corrected_value (Any): The corrected value.
            original_value (Optional[Any]): The original value.
            canonical_value (Optional[Any]): The canonical value.
            confidence (float): The confidence.
            source (str): The source.
            auto_approve (bool): IGNORED - all patches start PENDING per REP-01
            provenance (Optional[Dict[str, Any]]): The provenance.

        Returns:
            CorrectionPatch: Resulting CorrectionPatch instance.
        """
        patch_id = f"patch_{uuid.uuid4().hex[:12]}"
        orig = canonical_value if canonical_value is not None else original_value
        
        # B01: All patches start PENDING, auto_approve ignored per REP-01
        patch = CorrectionPatch(
            patch_id=patch_id,
            entity_id=entity_id,
            attribute=attribute,
            corrected_value=corrected_value,
            original_value=orig,
            canonical_value=orig,
            confidence=confidence,
            status=PatchStatus.PENDING,  # B01: Always PENDING initially
            source=source,
            provenance=provenance or {},
        )
        
        await self.cache.set(self._key(patch_id), patch.to_dict())
        log_step_info(
            logger,
            "PATCH_LAYER_CREATE",
            "Created patch %s in PENDING status (entity=%s.%s, val=%s)",
            patch_id,
            entity_id,
            attribute,
            corrected_value,
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

    async def transition_patch(
        self,
        patch_id: str,
        new_status: PatchStatus,
        actor: Optional[str] = None,
        receipt: Optional[Dict[str, Any]] = None
    ) -> bool:
        """B01: Transition patch to new status with validation.
        
        Validates that the transition is allowed and updates timestamps.
        
        Args:
            patch_id: Patch ID to transition
            new_status: Target status
            actor: Username/identity performing transition
            receipt: Publication receipt (for VERIFIED/ACTIVE transitions)
        
        Returns:
            True if transition successful
            
        Raises:
            StateTransitionError: If transition not allowed
        """
        patch = await self.get_patch(patch_id)
        if not patch:
            log_step_error(logger, "PATCH_TRANSITION_MISS", "Patch %s not found", patch_id)
            return False
        
        # B01: Validate transition
        allowed = ALLOWED_TRANSITIONS.get(patch.status, [])
        if new_status not in allowed:
            raise StateTransitionError(
                f"Invalid transition from {patch.status} to {new_status}. "
                f"Allowed transitions: {allowed}"
            )
        
        # Update status
        old_status = patch.status
        patch.status = new_status
        
        # B01: Update transition timestamps
        now = datetime.now(timezone.utc).isoformat()
        if new_status == PatchStatus.APPROVED:
            patch.approved_at = now
            patch.approved_by = actor
        elif new_status == PatchStatus.STAGED:
            patch.staged_at = now
        elif new_status == PatchStatus.VERIFIED:
            patch.verified_at = now
            if receipt:
                patch.publication_receipt = receipt
        elif new_status == PatchStatus.ACTIVE:
            patch.activated_at = now
            if receipt:
                patch.publication_receipt = receipt
        
        await self.cache.set(self._key(patch_id), patch.to_dict())
        
        log_step_info(
            logger,
            "PATCH_TRANSITION",
            "Patch %s: %s → %s (actor=%s)",
            patch_id,
            old_status,
            new_status,
            actor or "system"
        )
        return True

    async def approve_patch(self, patch_id: str, actor: Optional[str] = None) -> bool:
        """Approve patch (PENDING → APPROVED).
        
        B01: Uses state machine transition.

        Args:
            patch_id (str): Unique identifier of the patch.
            actor (Optional[str]): Username performing approval

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        try:
            return await self.transition_patch(patch_id, PatchStatus.APPROVED, actor=actor)
        except StateTransitionError as e:
            log_step_error(logger, "PATCH_APPROVE_INVALID", "Cannot approve %s: %s", patch_id, e)
            return False

    async def reject_patch(self, patch_id: str, actor: Optional[str] = None) -> bool:
        """Reject patch (PENDING/APPROVED → REJECTED).
        
        B01: Uses state machine transition, then deletes from cache.

        Args:
            patch_id (str): Unique identifier of the patch.
            actor (Optional[str]): Username performing rejection

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        try:
            # Transition to REJECTED first
            success = await self.transition_patch(patch_id, PatchStatus.REJECTED, actor=actor)
            if success:
                # Then remove from cache (optional - could keep for audit)
                await self.cache.delete(self._key(patch_id))
                log_step_info(logger, "PATCH_LAYER_REJECTED", "Patch %s rejected and removed", patch_id)
            return success
        except StateTransitionError as e:
            log_step_error(logger, "PATCH_REJECT_INVALID", "Cannot reject %s: %s", patch_id, e)
            return False

    async def get_all_pending(self) -> List[CorrectionPatch]:
        """Retrieve all pending (PENDING status) patches.
        
        B01: Filters by status instead of approved boolean.

        Returns:
            List[CorrectionPatch]: List of resulting items or records.
        """
        keys = await self.cache.get_keys_by_pattern(f"{self._prefix}*")
        pending: List[CorrectionPatch] = []
        for k in keys:
            data = await self.cache.get(k)
            if data:
                status = data.get("status", "PENDING")
                if status == "PENDING" or status == PatchStatus.PENDING.value:
                    pending.append(CorrectionPatch(**data))
        return pending

    async def get_active_patches(self, entity_id: Optional[str] = None) -> List[CorrectionPatch]:
        """Retrieve ACTIVE patches that can serve in answers.
        
        B01: Only returns patches where can_serve() is True (ACTIVE + verified + receipt).

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
            if data:
                p = CorrectionPatch(**data)
                
                # B01: Use can_serve() method
                if not p.can_serve():
                    continue
                
                # Entity matching
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
