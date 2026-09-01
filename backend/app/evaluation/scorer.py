# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Phase 5 — RAGAS Faithfulness & Context Grounding Evaluator.

Evaluates synthesized LLM answers against retrieved graph facts and vector snippets
to detect hallucinations, missing citations, or unsupported claims.
"""
import logging
import re
from typing import Any

logger = logging.getLogger("evaluation.scorer")


def evaluate_faithfulness(
    answer: str, context_text: str, graph_facts: list[str] = None
) -> dict[str, Any]:
    """Computes heuristic & token-overlap RAGAS faithfulness scores on production responses.
    
    Faithfulness = (Number of claims supported by context / Total claims in answer)
    """
    if not answer or not context_text:
        return {
            "faithfulness_score": 0.0,
            "context_recall_score": 0.0,
            "answer_relevance": 0.0,
            "passed": False,
            "reason": "Empty answer or context",
        }

    # Split answer into sentence claims
    claims = [s.strip() for s in re.split(r"(?<=[.!?])\s+", answer) if len(s.strip()) > 15]
    if not claims:
        claims = [answer.strip()]

    context_lower = context_text.lower()
    if graph_facts:
        context_lower += "\n" + "\n".join(f.lower() for f in graph_facts)

    supported_claims = 0

    for claim in claims:
        claim_clean = re.sub(r"\[\d+\]", "", claim).lower()
        words = [w for w in re.findall(r"\b\w{4,}\b", claim_clean) if w not in ("with", "that", "this", "from", "which", "have")]
        
        if not words:
            supported_claims += 1
            continue

        # Check keyword overlap ratio
        matches = sum(1 for w in words if w in context_lower)
        match_ratio = matches / len(words)

        if match_ratio >= 0.50:  # Claim has 50%+ key term grounding in retrieved context
            supported_claims += 1

    faithfulness = round(supported_claims / len(claims), 4)
    context_recall = round(min(1.0, len(context_text) / 800), 4)
    relevance = 0.95 if faithfulness >= 0.80 else (0.70 if faithfulness >= 0.50 else 0.40)

    is_passed = faithfulness >= 0.70

    result = {
        "faithfulness_score": faithfulness,
        "context_recall_score": context_recall,
        "answer_relevance": relevance,
        "total_claims_evaluated": len(claims),
        "supported_claims": supported_claims,
        "passed": is_passed,
    }

    logger.info("Evaluation Scorer: Faithfulness=%.2f | Supported %d/%d claims",
                faithfulness, supported_claims, len(claims))
    return result
