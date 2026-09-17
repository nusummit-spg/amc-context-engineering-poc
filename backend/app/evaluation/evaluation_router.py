# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
evaluation_router.py
====================
Evaluation router executing tiered evaluation ladder:
  - Tier 1A: Deterministic Rules Engine (STOP-1 gate)
  - Tier 2: NLI / Semantic Alignment (escalation)
  - Tier 3: LLM Judge (arbitration)
"""

import logging
from typing import Any, Dict, List, Optional

from app.evaluation.deterministic_rules import (
    DeterministicRuleEngine,
    RuleResult,
    RuleVerdict,
)

logger = logging.getLogger("app.evaluation.router")


class EvaluationRouter:
    """
    Tiered evaluation router implementing Keerthi's STOP-1 gate.
    Ensures 40-60% of deterministic checks are resolved at Tier 1A with 0 LLM tokens.
    """

    def __init__(self, rule_engine: Optional[DeterministicRuleEngine] = None):
        self.rule_engine = rule_engine or DeterministicRuleEngine()

    def evaluate(
        self,
        response_id: str,
        evidence_pack: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate an answer against evidence pack using tiered routing.
        """
        response_text = evidence_pack.get("response_text") or evidence_pack.get("user_answer") or ""

        # Tier 1A: Execute deterministic rules
        rule_results = self.rule_engine.evaluate_all(
            response_text=response_text,
            evidence_pack=evidence_pack
        )

        # Check STOP-1 failure gate
        if self.rule_engine.should_stop(rule_results):
            failed_rules = [r for r in rule_results if r.verdict == RuleVerdict.FAIL and r.confidence >= 0.9]
            fail_explanation = failed_rules[0].explanation if failed_rules else "Deterministic rule check failed"

            logger.info("STOP-1 triggered for response %s: %s", response_id, fail_explanation)
            return {
                "response_id": response_id,
                "verdict": "FAIL",
                "tier": "T1A_RULES",
                "confidence": 1.0,
                "llm_tokens_used": 0,
                "rule_results": [
                    {
                        "rule_id": r.rule_id,
                        "rule_name": r.rule_name,
                        "verdict": r.verdict.value,
                        "confidence": r.confidence,
                        "explanation": r.explanation,
                        "evidence": r.evidence
                    }
                    for r in rule_results
                ],
                "explanation": fail_explanation,
                "stop_reason": "STOP-1: Deterministic high-confidence failure"
            }

        # Check if all evaluated rules cleanly passed
        conclusive_passes = [r for r in rule_results if r.verdict == RuleVerdict.PASS]
        inconclusives = [r for r in rule_results if r.verdict == RuleVerdict.INCONCLUSIVE]

        if conclusive_passes and not inconclusives:
            logger.info("All deterministic rules passed for response %s (0 LLM tokens)", response_id)
            return {
                "response_id": response_id,
                "verdict": "PASS",
                "tier": "T1A_RULES",
                "confidence": 1.0,
                "llm_tokens_used": 0,
                "rule_results": [
                    {
                        "rule_id": r.rule_id,
                        "rule_name": r.rule_name,
                        "verdict": r.verdict.value,
                        "confidence": r.confidence,
                        "explanation": r.explanation,
                        "evidence": r.evidence
                    }
                    for r in rule_results
                ],
                "explanation": "All deterministic compliance and accuracy rules passed",
                "stop_reason": "STOP-1: Deterministic high-confidence pass"
            }

        # Inconclusive - requires escalation to Tier 2 (NLI) / Tier 3 (LLM)
        logger.info("Tier 1A inconclusive for response %s; prepared for Tier 2/3 escalation", response_id)
        return {
            "response_id": response_id,
            "verdict": "INCONCLUSIVE",
            "tier": "T1A_RULES",
            "confidence": 0.5,
            "llm_tokens_used": 0,
            "rule_results": [
                {
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "verdict": r.verdict.value,
                    "confidence": r.confidence,
                    "explanation": r.explanation,
                    "evidence": r.evidence
                }
                for r in rule_results
            ],
            "explanation": "Deterministic checks inconclusive; ready for semantic NLI escalation",
            "stop_reason": None
        }
