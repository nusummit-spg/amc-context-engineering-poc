"""
Governance batch processor promoting validated patches into canonical graph database.
"""
from typing import Any, Dict, List
from .config import RepairConfig
from .schemas import GovernanceBatchReport
from .patch_layer import CorrectionPatchLayer
from .adapters.base import GraphAdapter

class GovernanceBatch:
    def __init__(
        self,
        config: RepairConfig,
        patch_layer: CorrectionPatchLayer,
        graph_adapter: GraphAdapter
    ):
        self.config = config
        self.patch_layer = patch_layer
        self.graph = graph_adapter

    async def run_batch(self, dry_run: bool = False) -> GovernanceBatchReport:
        pending = await self.patch_layer.get_all_pending()
        report = GovernanceBatchReport(total_evaluated=len(pending))

        for patch in pending[:self.config.batch_size]:
            if patch.confidence >= self.config.auto_approve_confidence:
                report.approved += 1
                if not dry_run:
                    await self.patch_layer.approve_patch(patch.patch_id)
                    success = await self.graph.apply_entity_patch(
                        entity_id=patch.entity_id,
                        attribute=patch.attribute,
                        value=patch.corrected_value
                    )
                    if success:
                        report.promoted_to_graph += 1
            elif patch.confidence < 0.5:
                report.rejected += 1
                if not dry_run:
                    await self.patch_layer.reject_patch(patch.patch_id)
            else:
                report.needs_review += 1

        return report
