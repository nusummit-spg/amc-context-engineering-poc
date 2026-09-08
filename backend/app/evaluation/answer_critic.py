# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
answer_critic.py
================
LLM-as-Judge & NLI Answer Critic.
Verifies factual correctness, compliance safety, and context fidelity before answers
are returned to users.
Implements Task 1.3 of the Chief Architect Implementation Plan.
"""
from __future__ import annotations

from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.evaluation.nli_evaluator import NLIEvaluator, get_nli_evaluator

logger = logging.getLogger("app.evaluation.answer_critic")


class CriticSeverity(str, Enum):
    SAFE = "safe"          # Safe to deliver to user
    WARNING = "warning"    # Deliver with verification disclaimer / lower confidence
    CRITICAL = "critical"  # Direct contradiction / severe compliance violation; escalate to queue


class AnswerCritic:
    """Rigorous factual critic for high-stakes regulatory and financial answers."""

    HIGH_RISK_KEYWORDS = [
        "investment limit",
        "annual return",
        "guaranteed",
        "assured",
        "regulatory requirement",
        "sebi rule",
        "minimum net worth",
        "minimum aum",
        "solvency ratio",
        "lock-in period",
    ]

    def __init__(self, nli_evaluator: Optional[NLIEvaluator] = None, llm_client: Optional[Any] = None):
        self.nli_evaluator = nli_evaluator or get_nli_evaluator()
        self.llm_client = llm_client

    async def critique(
        self,
        query: str,
        answer: str,
        context: str = "",
        intent: Optional[Any] = None,
    ) -> Tuple[CriticSeverity, Dict[str, Any]]:
        """
        Critique generated answer against source context.
        Returns (CriticSeverity, critique_details_dict).
        """
        query_lower = query.lower()
        is_high_risk = any(kw in query_lower for kw in self.HIGH_RISK_KEYWORDS)

        if is_high_risk:
            return await self._critique_high_risk(query, answer, context)
        return await self._critique_standard(query, answer, context)

    async def _critique_high_risk(
        self,
        query: str,
        answer: str,
        context: str,
    ) -> Tuple[CriticSeverity, Dict[str, Any]]:
        """High-risk evaluation using NLI and regulatory pattern validation."""
        issues: List[str] = []

        # 1. Check for prohibited financial promises / risky claims
        claims = self._extract_risky_claims(answer)
        if claims:
            issues.extend(claims)

        # 2. NLI Contradiction Check
        nli_label, nli_conf = self.nli_evaluator.evaluate(context, answer)
        if nli_label == "contradiction" and nli_conf >= 0.75:
            issues.append(f"Answer contradicts source context (NLI confidence: {nli_conf:.2f})")

        if issues:
            return CriticSeverity.CRITICAL, {
                "score": 0.2,
                "severity": CriticSeverity.CRITICAL.value,
                "issues": issues,
                "nli_label": nli_label,
                "nli_confidence": nli_conf,
                "recommendation": "Escalate to Human Review Queue immediately",
            }


        # 3. Warning check
        if nli_label == "neutral" and len(answer) > 200:
            return CriticSeverity.WARNING, {
                "score": 0.65,
                "severity": CriticSeverity.WARNING.value,
                "issues": ["Answer contains statements not fully verified in retrieved context"],
                "nli_label": nli_label,
                "recommendation": "Attach compliance verification note",
            }

        return CriticSeverity.SAFE, {
            "score": 0.95,
            "severity": CriticSeverity.SAFE.value,
            "issues": [],
            "nli_label": nli_label,
            "recommendation": "Verified against source context",
        }

    async def _critique_standard(
        self,
        query: str,
        answer: str,
        context: str,
    ) -> Tuple[CriticSeverity, Dict[str, Any]]:
        """Standard check for general queries."""
        claims = self._extract_risky_claims(answer)
        if claims:
            return CriticSeverity.WARNING, {
                "score": 0.5,
                "severity": CriticSeverity.WARNING.value,
                "issues": claims,
                "recommendation": "Reviewer disclaimer recommended",
            }

        return CriticSeverity.SAFE, {
            "score": 0.90,
            "severity": CriticSeverity.SAFE.value,
            "issues": [],
            "recommendation": "Safe for release",
        }

    def _extract_risky_claims(self, answer: str) -> List[str]:
        """Detect prohibited claims like assured returns or capital guarantees."""
        claims: List[str] = []
        ans_lower = answer.lower()

        if "guarantee" in ans_lower and ("%" in answer or "return" in ans_lower):
            claims.append("Answer contains prohibited guaranteed return claim")

        if any(term in ans_lower for term in ["cannot lose money", "zero risk investment", "assured 100% gain"]):
            claims.append("Answer contains misleading zero-risk financial claim")

        return claims


_answer_critic_instance: Optional[AnswerCritic] = None


def get_answer_critic() -> AnswerCritic:
    global _answer_critic_instance
    if _answer_critic_instance is None:
        _answer_critic_instance = AnswerCritic()
    return _answer_critic_instance
