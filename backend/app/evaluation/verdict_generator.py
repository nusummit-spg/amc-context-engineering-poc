# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
verdict_generator.py
====================
Multi-Tier Verdict Generation Service for evaluating model answers and feedback items.
Implements Task 0.2.3 of the Chief Architect Implementation Plan.
Tiers:
  - Tier 0: Rule-based heuristic pattern matching (instant, 0 latency)
  - Tier 1: NLI Semantic Entailment analysis (high accuracy)
  - Tier 2: Calibrated confidence and coverage heuristics (fallback)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

from app.evaluation.nli_evaluator import NLIEvaluator, get_nli_evaluator
from app.schemas.review_queue import Verdict

logger = logging.getLogger("app.evaluation.verdict")


class VerdictGenerator:
    """Generates structured verdicts (CONFIRMED, PARTIALLY_CORRECT, NEEDS_CORRECTION, AMBIGUOUS)."""

    def __init__(self, nli_evaluator: Optional[NLIEvaluator] = None):
        self.nli_evaluator = nli_evaluator or get_nli_evaluator()

    async def generate_verdict(
        self,
        query: str,
        retrieved_context: str,
        llm_answer: str,
        user_feedback: str = "",
        confidence_score: float = 0.5,
    ) -> Tuple[Verdict, Dict[str, Any]]:
        """
        Generate resolution verdict using multi-tiered evaluation.
        Returns: (Verdict, metadata_dict)
        """
        logger.debug("Generating verdict for query '%s' (conf=%.2f)", query[:40], confidence_score)

        # ── Tier 0: Rule-Based Deterministic Check ────────────────────────
        tier0 = self._tier0_rule_check(llm_answer, user_feedback)
        if tier0.get("is_definitive"):
            logger.info("Tier 0 rule match: %s -> %s", tier0.get("issue"), tier0.get("verdict"))
            return tier0["verdict"], tier0

        # ── Tier 1: NLI Semantic Entailment Evaluation ────────────────────
        nli_label, nli_conf = self.nli_evaluator.evaluate(retrieved_context, llm_answer)
        tier1 = self._tier1_nli_check(nli_label, nli_conf)
        if tier1.get("is_definitive"):
            logger.info("Tier 1 NLI match: %s (conf=%.2f) -> %s", nli_label, nli_conf, tier1.get("verdict"))
            return tier1["verdict"], tier1

        # ── Tier 2: Heuristic Fallback ────────────────────────────────────
        tier2 = self._tier2_heuristic(query, retrieved_context, llm_answer, confidence_score)
        logger.info("Tier 2 heuristic applied -> %s", tier2.get("verdict"))
        return tier2["verdict"], tier2

    def _tier0_rule_check(self, answer: str, feedback: str) -> Dict[str, Any]:
        """Detect obvious compliance red-flags or direct feedback cues."""
        ans_lower = (answer or "").lower()
        fb_lower = (feedback or "").lower()

        # Prohibited return guarantees
        if "guarantee" in ans_lower and ("%" in answer or "return" in ans_lower):
            return {
                "is_definitive": True,
                "verdict": Verdict.NEEDS_CORRECTION,
                "tier": 0,
                "issue": "Prohibited guaranteed return claim detected",
                "confidence": 0.98,
            }

        # User explicitly reported error or hallucination
        if any(w in fb_lower for w in ["hallucination", "incorrect", "wrong number", "false claim"]):
            return {
                "is_definitive": True,
                "verdict": Verdict.NEEDS_CORRECTION,
                "tier": 0,
                "issue": "Explicit factual error or hallucination reported by reviewer",
                "confidence": 0.92,
            }

        return {"is_definitive": False}

    def _tier1_nli_check(self, nli_label: str, nli_conf: float) -> Dict[str, Any]:
        """Classify based on premise-hypothesis inference."""
        if nli_label == "contradiction" and nli_conf >= 0.75:
            return {
                "is_definitive": True,
                "verdict": Verdict.NEEDS_CORRECTION,
                "tier": 1,
                "issue": f"NLI detected contradiction with context ({nli_conf:.2f})",
                "confidence": nli_conf,
            }

        if nli_label == "entailment" and nli_conf >= 0.85:
            return {
                "is_definitive": True,
                "verdict": Verdict.CONFIRMED,
                "tier": 1,
                "issue": f"NLI confirmed factual entailment ({nli_conf:.2f})",
                "confidence": nli_conf,
            }

        return {"is_definitive": False, "nli_label": nli_label, "nli_confidence": nli_conf}

    def _tier2_heuristic(
        self,
        query: str,
        context: str,
        answer: str,
        conf: float,
    ) -> Dict[str, Any]:
        """Heuristic confidence grading when tiers 0-1 are inconclusive."""
        if conf >= 0.75:
            return {
                "verdict": Verdict.CONFIRMED,
                "tier": 2,
                "issue": "High context quality and confidence score",
                "confidence": conf,
            }
        elif conf <= 0.40:
            return {
                "verdict": Verdict.AMBIGUOUS,
                "tier": 2,
                "issue": "Low confidence score; requires human verification",
                "confidence": conf,
            }
        else:
            return {
                "verdict": Verdict.PARTIALLY_CORRECT,
                "tier": 2,
                "issue": "Medium confidence; partial coverage likely",
                "confidence": conf,
            }


# Global singleton
_verdict_generator: Optional[VerdictGenerator] = None


def get_verdict_generator() -> VerdictGenerator:
    global _verdict_generator
    if _verdict_generator is None:
        _verdict_generator = VerdictGenerator()
    return _verdict_generator
