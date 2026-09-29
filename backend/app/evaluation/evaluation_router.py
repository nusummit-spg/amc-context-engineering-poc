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
  - Tier 1A: Deterministic Rules Engine (STOP-1 gate, 0 LLM tokens)
  - Tier 2: NLI / Semantic Alignment (STOP-2 gate, 0 LLM tokens)
  - Tier 3: LLM Judge (STOP-3 gate, arbitration)
  - Fallback: Escalation to human review queue
"""
from __future__ import annotations

import asyncio
import concurrent.futures
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
    Tiered evaluation router implementing Keerthi's STOP-1, STOP-2, and STOP-3 gates.
    Ensures 40-60% of deterministic checks are resolved at Tier 1A with 0 LLM tokens,
    escalating to Tier 2 (NLI) and Tier 3 (LLM Judge) only when inconclusive.
    """

    def __init__(
        self,
        rule_engine: Optional[DeterministicRuleEngine] = None,
        enable_tier2: Optional[bool] = None,
        enable_tier3: Optional[bool] = None,
    ):
        self.rule_engine = rule_engine or DeterministicRuleEngine()
        self._enable_tier2 = enable_tier2
        self._enable_tier3 = enable_tier3

    @property
    def is_tier2_enabled(self) -> bool:
        if self._enable_tier2 is not None:
            return self._enable_tier2
        try:
            from app.engine import config as engine_config
            if getattr(engine_config, "ENABLE_TIER2_NLI_EVALUATION", False):
                return True
        except ImportError:
            pass
        try:
            from app.config import get_settings
            return getattr(get_settings(), "enable_tier2_nli_evaluation", False)
        except Exception:
            return False

    @property
    def is_tier3_enabled(self) -> bool:
        if self._enable_tier3 is not None:
            return self._enable_tier3
        try:
            from app.engine import config as engine_config
            if getattr(engine_config, "ENABLE_TIER3_LLM_JUDGE", False):
                return True
        except ImportError:
            pass
        try:
            from app.config import get_settings
            return getattr(get_settings(), "enable_tier3_llm_judge", False)
        except Exception:
            return False

    def evaluate(
        self,
        response_id: str,
        evidence_pack: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Synchronous evaluation entry point.
        Executes Tier 1A deterministic rules, then escalates to Tier 2 (NLI)
        and Tier 3 (LLM Judge) as needed.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    lambda: asyncio.run(self.evaluate_async(response_id, evidence_pack))
                ).result()
        return asyncio.run(self.evaluate_async(response_id, evidence_pack))

    async def evaluate_async(
        self,
        response_id: str,
        evidence_pack: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Asynchronous evaluation entry point through the full tiered evaluation ladder.
        """
        response_text = evidence_pack.get("response_text") or evidence_pack.get("user_answer") or ""

        # ── Tier 1A: Deterministic Rules ─────────────────────────────────
        rule_results = self.rule_engine.evaluate_all(
            response_text=response_text,
            evidence_pack=evidence_pack
        )

        serialized_rules = [
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "verdict": r.verdict.value,
                "confidence": r.confidence,
                "explanation": r.explanation,
                "evidence": r.evidence
            }
            for r in rule_results
        ]

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
                "rule_results": serialized_rules,
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
                "rule_results": serialized_rules,
                "explanation": "All deterministic compliance and accuracy rules passed",
                "stop_reason": "STOP-1: Deterministic high-confidence pass"
            }

        logger.info("Tier 1A inconclusive for response %s; evaluating Tier 2/3 escalation", response_id)

        # ── Tier 2: NLI Semantic Alignment ──────────────────────────────
        if self.is_tier2_enabled:
            try:
                from app.evaluation.nli_evaluator import get_nli_evaluator
                nli_evaluator = get_nli_evaluator()

                retrieved_context = (
                    evidence_pack.get("retrieved_context")
                    or evidence_pack.get("context")
                    or ""
                )
                if not retrieved_context and "chunks" in evidence_pack:
                    retrieved_context = " ".join(
                        c.get("text", "") for c in evidence_pack["chunks"] if isinstance(c, dict)
                    )

                nli_label, nli_confidence = nli_evaluator.evaluate(
                    retrieved_context,
                    response_text
                )

                logger.info("Tier 2 NLI: label=%s, confidence=%.2f", nli_label, nli_confidence)

                tier2_threshold = 0.85
                try:
                    from app.config import get_settings
                    tier2_threshold = getattr(get_settings(), "tier2_nli_confidence_threshold", 0.85)
                except Exception:
                    pass

                # STOP-2 gate: High-confidence NLI verdict
                if nli_confidence >= tier2_threshold:
                    if nli_label == "entailment":
                        return {
                            "response_id": response_id,
                            "verdict": "PASS",
                            "tier": "T2_NLI",
                            "confidence": nli_confidence,
                            "llm_tokens_used": 0,
                            "rule_results": serialized_rules,
                            "nli_result": {"label": nli_label, "confidence": nli_confidence},
                            "explanation": "NLI semantic entailment confirmed answer accuracy",
                            "stop_reason": "STOP-2: High-confidence NLI pass"
                        }
                    elif nli_label == "contradiction":
                        return {
                            "response_id": response_id,
                            "verdict": "FAIL",
                            "tier": "T2_NLI",
                            "confidence": nli_confidence,
                            "llm_tokens_used": 0,
                            "rule_results": serialized_rules,
                            "nli_result": {"label": nli_label, "confidence": nli_confidence},
                            "explanation": "NLI detected semantic contradiction with retrieved context",
                            "stop_reason": "STOP-2: High-confidence NLI fail"
                        }
            except Exception as exc:
                logger.warning("Tier 2 NLI evaluation exception: %s", exc)

        # ── Tier 3: LLM Judge (Last Resort) ──────────────────────────────
        if self.is_tier3_enabled:
            try:
                from app.evaluation.answer_critic import get_answer_critic, CriticSeverity
                critic = get_answer_critic()

                retrieved_context = (
                    evidence_pack.get("retrieved_context")
                    or evidence_pack.get("context")
                    or ""
                )
                if not retrieved_context and "chunks" in evidence_pack:
                    retrieved_context = " ".join(
                        c.get("text", "") for c in evidence_pack["chunks"] if isinstance(c, dict)
                    )

                critique = await critic.critique_answer(
                    query=evidence_pack.get("query", ""),
                    answer=response_text,
                    context=retrieved_context,
                    intent=evidence_pack.get("intent", "")
                )

                logger.info(
                    "Tier 3 LLM Judge: severity=%s, confidence=%.2f, tokens=%d",
                    critique.severity, critique.confidence, critique.tokens_used
                )

                verdict_map = {
                    CriticSeverity.NONE: "PASS",
                    CriticSeverity.LOW: "PASS",
                    CriticSeverity.SAFE: "PASS",
                    CriticSeverity.MEDIUM: "WARN",
                    CriticSeverity.WARNING: "WARN",
                    CriticSeverity.HIGH: "FAIL",
                    CriticSeverity.CRITICAL: "FAIL",
                }

                return {
                    "response_id": response_id,
                    "verdict": verdict_map.get(critique.severity, "PASS"),
                    "tier": "T3_LLM_JUDGE",
                    "confidence": critique.confidence,
                    "llm_tokens_used": critique.tokens_used,
                    "rule_results": serialized_rules,
                    "critic_result": {
                        "severity": critique.severity.value,
                        "confidence": critique.confidence,
                        "issues": critique.issues,
                        "explanation": critique.explanation
                    },
                    "explanation": critique.explanation,
                    "stop_reason": "STOP-3: LLM judge arbitration complete"
                }
            except Exception as exc:
                logger.error("Tier 3 LLM Judge exception: %s", exc)

        # ── Fallback: Escalate to Human Review ───────────────────────────
        return {
            "response_id": response_id,
            "verdict": "NEEDS_HUMAN_REVIEW",
            "tier": "ESCALATED",
            "confidence": 0.3,
            "llm_tokens_used": 0,
            "rule_results": serialized_rules,
            "explanation": "All automated tiers inconclusive; requires human review",
            "stop_reason": None
        }
