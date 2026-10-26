"""
Governance batch processor promoting validated patches into canonical graph database.
"""
from typing import Any, Dict, List
from .config import RepairConfig
from .schemas import GovernanceBatchReport
from .patch_layer import CorrectionPatchLayer
from .adapters.base import GraphAdapter
from .logging import get_repair_logger, log_step_info, log_step_debug, log_step_warning

logger = get_repair_logger("governance")

class GovernanceBatch:
    def __init__(
        self,
        config: RepairConfig,
        patch_layer: CorrectionPatchLayer,
        graph_adapter: GraphAdapter
    ):
        """Initialize a new instance of GovernanceBatch.

        Args:
            config (RepairConfig): Configuration dictionary or settings object.
            patch_layer (CorrectionPatchLayer): The patch layer.
            graph_adapter (GraphAdapter): The graph adapter.
        """
        self.config = config
        self.patch_layer = patch_layer
        self.graph = graph_adapter

    async def run_batch(self, dry_run: bool = False) -> GovernanceBatchReport:
        """Run batch.

        Args:
            dry_run (bool): The dry run.

        Returns:
            GovernanceBatchReport: Resulting GovernanceBatchReport instance.
        """
        pending = await self.patch_layer.get_all_pending()
        report = GovernanceBatchReport(total_evaluated=len(pending))
        log_step_info(logger, "GOVERNANCE_BATCH_START", "Starting governance batch with %d pending patches (dry_run=%s)", len(pending), dry_run)

        for patch in pending[:self.config.batch_size]:
            if patch.confidence >= self.config.auto_approve_confidence:
                report.approved += 1
                log_step_info(logger, "PATCH_AUTO_APPROVED", "Patch %s auto-approved (confidence=%.2f >= %.2f)", patch.patch_id, patch.confidence, self.config.auto_approve_confidence)
                if not dry_run:
                    await self.patch_layer.approve_patch(patch.patch_id)
                    success = await self.graph.apply_entity_patch(
                        entity_id=patch.entity_id,
                        attribute=patch.attribute,
                        value=patch.corrected_value
                    )
                    if success:
                        report.promoted_to_graph += 1
                        log_step_info(logger, "GRAPH_MUTATION_APPLIED", "Promoted patch %s to canonical graph: %s.%s = %s", patch.patch_id, patch.entity_id, patch.attribute, patch.corrected_value)
                        try:
                            await self.graph.delete_shadow_patch(patch.patch_id)
                        except Exception:
                            pass
            elif patch.confidence < 0.5:
                report.rejected += 1
                log_step_info(logger, "PATCH_REJECTED", "Patch %s rejected (confidence=%.2f < 0.5)", patch.patch_id, patch.confidence)
                if not dry_run:
                    await self.patch_layer.reject_patch(patch.patch_id)
            else:
                report.needs_review += 1
                log_step_info(logger, "PATCH_NEEDS_REVIEW", "Patch %s flagged for review (confidence=%.2f)", patch.patch_id, patch.confidence)

        log_step_info(
            logger,
            "GOVERNANCE_BATCH_COMPLETE",
            "Governance batch finished: evaluated=%d approved=%d promoted=%d rejected=%d review=%d",
            report.total_evaluated,
            report.approved,
            report.promoted_to_graph,
            report.rejected,
            report.needs_review,
        )
        return report
