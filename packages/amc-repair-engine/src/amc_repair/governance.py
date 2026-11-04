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
            # REP-01 / REP-02: Human authorization mandatory.
            # Confidence is a triage score, NOT authorization. No automatic approvals or promotions.
            if patch.confidence >= self.config.auto_approve_confidence:
                report.needs_review += 1
                log_step_info(logger, "PATCH_RECOMMENDED_APPROVAL", "Patch %s recommended for human approval (confidence=%.2f >= %.2f) - auto-approval disabled per REP-01", patch.patch_id, patch.confidence, self.config.auto_approve_confidence)
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
