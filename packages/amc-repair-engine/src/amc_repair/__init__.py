"""
AMC Repair Engine - Self-correcting repair and governance framework.
"""
from typing import Any, Dict, List, Optional
from .config import RepairConfig
from .schemas import CorrectionPatch, EvaluationResult, GovernanceBatchReport
from .patch_layer import CorrectionPatchLayer
from .evaluator import TieredEvaluator
from .governance import GovernanceBatch
from .adapters.base import CacheAdapter, GraphAdapter
from .adapters.cache import MemoryCacheAdapter, MemoryAdapter, RedisAdapter
from .adapters.graph import MemoryGraphAdapter, Neo4jAdapter

__version__ = "0.1.0"
__all__ = [
    "RepairConfig",
    "RepairEngine",
    "CorrectionPatch",
    "EvaluationResult",
    "GovernanceBatchReport",
    "CorrectionPatchLayer",
    "TieredEvaluator",
    "GovernanceBatch",
    "CacheAdapter",
    "GraphAdapter",
    "MemoryCacheAdapter",
    "MemoryAdapter",
    "RedisAdapter",
    "MemoryGraphAdapter",
    "Neo4jAdapter",
]


class RepairEngine:
    """
    Main interface coordinating repair engine capabilities.
    """

    def __init__(
        self,
        config: Optional[RepairConfig] = None,
        cache_adapter: Optional[CacheAdapter] = None,
        graph_adapter: Optional[GraphAdapter] = None,
    ):
        self.config = config or RepairConfig()
        self.cache = cache_adapter or MemoryCacheAdapter()
        self.graph = graph_adapter or MemoryGraphAdapter()

        self.patch_layer = CorrectionPatchLayer(self.config, self.cache)
        self.evaluator = TieredEvaluator(self.config)
        self.governance = GovernanceBatch(self.config, self.patch_layer, self.graph)

    async def add_correction(
        self,
        entity_id: str,
        attribute: str,
        canonical_value: Any,
        corrected_value: Any,
        confidence: float = 1.0,
        provenance: Optional[Dict[str, Any]] = None,
        approved: bool = False,
    ) -> str:
        """Create a correction patch and return patch_id."""
        patch = await self.patch_layer.create_patch(
            entity_id=entity_id,
            attribute=attribute,
            corrected_value=corrected_value,
            canonical_value=canonical_value,
            confidence=confidence,
            source=provenance.get("source", "feedback") if provenance else "feedback",
            auto_approve=approved,
            provenance=provenance,
        )
        return patch.patch_id

    async def get_pending_corrections(self) -> List[CorrectionPatch]:
        """Get all unapproved patches."""
        return await self.patch_layer.get_all_pending()

    async def approve_correction(self, patch_id: str) -> bool:
        """Approve a correction patch."""
        return await self.patch_layer.approve_patch(patch_id)

    async def reject_correction(self, patch_id: str) -> bool:
        """Reject and remove a correction patch."""
        return await self.patch_layer.reject_patch(patch_id)

    async def run_governance_batch(
        self,
        auto_approve_threshold: Optional[float] = None,
        dry_run: bool = False
    ) -> GovernanceBatchReport:
        """Run scheduled governance batch promotion."""
        if auto_approve_threshold is not None:
            self.config.auto_approve_confidence = auto_approve_threshold
        return await self.governance.run_batch(dry_run=dry_run)

    async def close(self):
        await self.cache.close()
        await self.graph.close()
