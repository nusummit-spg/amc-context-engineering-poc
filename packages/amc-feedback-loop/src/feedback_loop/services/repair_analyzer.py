"""
Step 6 — Repair Analyzer Service
=================================
Analyzes diagnosis output and severity to determine if automated repair
should be scheduled and assigns the repair target ('vector' or 'graph').
"""

from __future__ import annotations

from typing import Optional

from feedback_loop.domain_models import (
    DiagnosisResult,
    RepairAnalysis,
    RepairTarget,
    RootCause,
    Severity,
    StackLayer,
)
from feedback_loop.logging import get_feedback_logger, log_step_info

logger = get_feedback_logger("repair_analyzer")


class RepairAnalyzerService:
    """Step 6: Repair analysis — decide if automated repair is needed and target layer."""

    def analyze(
        self,
        diagnosis: DiagnosisResult,
        severity: Optional[Severity],
        root_cause: Optional[RootCause],
        confidence: float,
    ) -> RepairAnalysis:
        """Analyze.

        Args:
            diagnosis (DiagnosisResult): Collection or list of diagnosis.
            severity (Optional[Severity]): The severity.
            root_cause (Optional[RootCause]): The root cause.
            confidence (float): The confidence.

        Returns:
            RepairAnalysis: Resulting RepairAnalysis instance.
        """
        log_step_info(
            logger,
            "REPAIR_ANALYSIS_START",
            "Repair analysis evaluating diagnosis: layer=%s, severity=%s, confidence=%.2f",
            diagnosis.stack_layer,
            severity,
            confidence,
        )
        """
        Decide:
        1. Should repair be attempted? (repair=True/False)
        2. Where to apply fix? (repair_target='vector'|'graph'|None)

        Rules:
        - Severity >= HIGH and confidence >= 0.75 → repair=True
        - KNOWLEDGE / GRAPH stack layer → repair_target='graph'
        - RETRIEVAL / MODEL stack layer → repair_target='vector'
        - Others (e.g. PRESENTATION, FEEDBACK_INVALID, etc.) → repair=False
        """
        # Gate 1: Severity + confidence threshold
        should_repair = (
            severity in [Severity.CRITICAL, Severity.HIGH]
            and confidence >= 0.75
        )

        res = None
        if not should_repair:
            res = RepairAnalysis(
                repair=False,
                repair_target=None,
                reason="Below repair threshold (requires HIGH/CRITICAL severity and confidence >= 0.75)",
            )
        else:
            # Gate 2: Repairability check
            target_map = {
                StackLayer.KNOWLEDGE: RepairTarget.GRAPH,
                StackLayer.GRAPH: RepairTarget.GRAPH,
                StackLayer.COMPLIANCE: RepairTarget.GRAPH,
                StackLayer.CONTEXT_ENGINEERING: RepairTarget.VECTOR,
                StackLayer.RETRIEVAL: RepairTarget.VECTOR,
                StackLayer.MODEL: RepairTarget.VECTOR,
            }

            repair_target = target_map.get(diagnosis.stack_layer)

            if repair_target is None:
                res = RepairAnalysis(
                    repair=False,
                    repair_target=None,
                    reason=f"Stack layer {diagnosis.stack_layer} not repairable",
                )
            else:
                res = RepairAnalysis(
                    repair=True,
                    repair_target=repair_target,
                    reason=f"Repairability confirmed for {diagnosis.stack_layer} targeting {repair_target.value}",
                )

        log_step_info(
            logger,
            "REPAIR_ANALYSIS_COMPLETE",
            "Repair analysis complete: repair=%s, target=%s (reason: %s)",
            res.repair,
            res.repair_target,
            res.reason,
        )
        return res
