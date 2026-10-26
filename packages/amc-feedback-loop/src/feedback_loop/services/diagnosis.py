"""
Step 5 — Failure Diagnosis Service
===================================
Maps root cause and adaptive router findings to the architectural stack layer:
- KNOWLEDGE: Missing/incorrect data in source documents
- RETRIEVAL: Vector search or graph traversal missed entity/facts
- GRAPH: Knowledge graph structure / relation issue
- CONTEXT_ENGINEERING: Context assembly or budget fitting issue
- MODEL: LLM hallucination / synthesis error
- GUARDRAIL: Policy / guardrail failure
- COMPLIANCE: Regulatory constraint violation
- PRESENTATION: Formatting / clarity issue
- FEEDBACK_INVALID: User feedback inaccurate / invalid
"""

from __future__ import annotations

from typing import Optional

from feedback_loop.domain_models import (
    DiagnosisResult,
    EvidenceSnapshot,
    RootCause,
    RouterResult,
    StackLayer,
)
from feedback_loop.logging import get_feedback_logger, log_step_info

logger = get_feedback_logger("diagnosis")


class DiagnosisService:
    """Step 5: Failure diagnosis — maps root cause and router findings to stack layer."""

    def diagnose(
        self,
        root_cause: Optional[RootCause],
        router_result: RouterResult,
        snapshot: EvidenceSnapshot,
    ) -> DiagnosisResult:
        """Diagnose failure root cause and classification.

        Args:
            root_cause (Optional[RootCause]): The root cause.
            router_result (RouterResult): The router result.
            snapshot (EvidenceSnapshot): The snapshot.

        Returns:
            DiagnosisResult: Resulting DiagnosisResult instance.
        """
        log_step_info(logger, "DIAGNOSIS_START", "Failure diagnosis starting for root_cause=%s", root_cause)
        diagnosis_map = {
            RootCause.COMPLIANCE: StackLayer.COMPLIANCE,
            RootCause.MODEL: StackLayer.MODEL,
            RootCause.PRESENTATION: StackLayer.PRESENTATION,
            RootCause.FEEDBACK_INVALID: StackLayer.FEEDBACK_INVALID,
            RootCause.GUARDRAIL: StackLayer.GUARDRAIL,
            RootCause.CONTEXT_ENGINEERING: StackLayer.CONTEXT_ENGINEERING,
            RootCause.GRAPH: StackLayer.GRAPH,
        }

        fired_rules = [f.rule for f in (router_result.rules_fired or [])]

        if root_cause == RootCause.KNOWLEDGE:
            if "C04_structured_correction" in fired_rules:
                return DiagnosisResult(
                    stack_layer=StackLayer.KNOWLEDGE,
                    confidence=0.9,
                    evidence="User provided explicit structured correction indicating knowledge gap",
                )
            return DiagnosisResult(
                stack_layer=StackLayer.KNOWLEDGE,
                confidence=0.85,
                evidence=f"Knowledge root cause mapped with rules: {fired_rules}",
            )

        if root_cause == RootCause.RETRIEVAL:
            evidence_details = f"Retrieval rules fired: {fired_rules}" if fired_rules else "Retrieval failure"
            return DiagnosisResult(
                stack_layer=StackLayer.RETRIEVAL,
                confidence=0.85,
                evidence=evidence_details,
            )

        res = None
        if root_cause in diagnosis_map:
            res = DiagnosisResult(
                stack_layer=diagnosis_map[root_cause],
                confidence=0.8,
                evidence=f"Direct mapping from root cause {root_cause}",
            )
        else:
            res = DiagnosisResult(
                stack_layer=StackLayer.UNKNOWN,
                confidence=0.5,
                evidence="Default fallback mapping",
            )

        log_step_info(
            logger,
            "DIAGNOSIS_COMPLETE",
            "Diagnosis complete: stack_layer=%s, confidence=%.2f",
            res.stack_layer,
            res.confidence,
        )
        return res
