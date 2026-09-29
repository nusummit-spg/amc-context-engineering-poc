# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_evaluation_tier_integration.py
===================================
Unit & integration tests for multi-tier evaluation ladder in EvaluationRouter:
  - Tier 1A: Deterministic Rules Engine (STOP-1 gate)
  - Tier 2: NLI Semantic Alignment (STOP-2 gate)
  - Tier 3: LLM Judge / Answer Critic (STOP-3 gate)
  - Fallback: Escalation to human review
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.evaluation.evaluation_router import EvaluationRouter
from app.evaluation.answer_critic import CriticSeverity, CritiqueResult
from app.engine import config as engine_config


def test_tier1a_deterministic_pass():
    """Verify clean deterministic pass triggers STOP-1 with 0 LLM tokens."""
    router = EvaluationRouter(enable_tier2=False, enable_tier3=False)
    evidence = {
        "response_text": "The fund TER is 0.82% [source: C_101]",
        "source_age_days": 2,
        "chunks": [{"text": "The fund TER is 0.82%"}],
        "chunk_ids": ["C_101"],
    }
    res = router.evaluate("resp_001", evidence)
    assert res["verdict"] == "PASS"
    assert res["tier"] == "T1A_RULES"
    assert res["llm_tokens_used"] == 0
    assert "STOP-1" in res["stop_reason"]


def test_tier1a_deterministic_fail_stop1():
    """Verify deterministic rule failure stops execution at STOP-1 with 0 LLM tokens."""
    router = EvaluationRouter(enable_tier2=False, enable_tier3=False)
    evidence = {
        "response_text": "The fund TER is 0.50%",
        "source_age_days": 20,  # Stale source (> 7 days)
        "chunks": [{"text": "The fund TER is 0.82%"}],
        "chunk_ids": ["C_101"],
    }
    res = router.evaluate("resp_002", evidence)
    assert res["verdict"] == "FAIL"
    assert res["tier"] == "T1A_RULES"
    assert res["llm_tokens_used"] == 0
    assert "STOP-1" in res["stop_reason"]


def test_tier2_nli_entailment_stop2():
    """Verify Tier 1 inconclusive escalates to Tier 2 NLI and passes on entailment (STOP-2)."""
    router = EvaluationRouter(enable_tier2=True, enable_tier3=False)
    evidence = {
        "response_text": "Axis Bluechip Fund invests predominantly in large cap equity stocks.",
        "retrieved_context": "Axis Bluechip Fund is an open-ended equity scheme investing predominantly in large cap equity stocks across diversified sectors.",
    }
    res = router.evaluate("resp_003", evidence)
    assert res["verdict"] == "PASS"
    assert res["tier"] == "T2_NLI"
    assert res["llm_tokens_used"] == 0
    assert res["nli_result"]["label"] == "entailment"
    assert "STOP-2" in res["stop_reason"]


def test_tier2_nli_contradiction_stop2():
    """Verify Tier 1 inconclusive escalates to Tier 2 NLI and fails on contradiction (STOP-2)."""
    router = EvaluationRouter(enable_tier2=True, enable_tier3=False)
    evidence = {
        "response_text": "Investors are guaranteed a 20% annual return on this investment.",
        "retrieved_context": "SEBI circular strictly prohibits any mutual fund scheme from promising or offering guaranteed returns.",
    }
    res = router.evaluate("resp_004", evidence)
    assert res["verdict"] == "FAIL"
    assert res["tier"] == "T2_NLI"
    assert res["llm_tokens_used"] == 0
    assert res["nli_result"]["label"] == "contradiction"
    assert "STOP-2" in res["stop_reason"]


@pytest.mark.asyncio
async def test_tier3_llm_judge_escalation(monkeypatch):
    """Verify escalation to Tier 3 when Tier 1 and Tier 2 NLI are inconclusive."""
    router = EvaluationRouter(enable_tier2=True, enable_tier3=True)

    # Mock NLI to return neutral (inconclusive)
    mock_nli = MagicMock()
    mock_nli.evaluate = MagicMock(return_value=("neutral", 0.50))
    monkeypatch.setattr("app.evaluation.nli_evaluator.get_nli_evaluator", lambda: mock_nli)

    # Mock AnswerCritic to return a safe critique
    mock_critic = MagicMock()
    mock_critic.critique_answer = AsyncMock(return_value=CritiqueResult(
        severity=CriticSeverity.SAFE,
        confidence=0.92,
        tokens_used=45,
        issues=[],
        explanation="Answer complies with all safety and context guidelines"
    ))
    monkeypatch.setattr("app.evaluation.answer_critic.get_answer_critic", lambda: mock_critic)

    evidence = {
        "query": "What is the investment objective?",
        "response_text": "The scheme seeks long-term capital appreciation.",
        "retrieved_context": "General information about mutual fund scheme investment objectives.",
    }

    res = await router.evaluate_async("resp_005", evidence)
    assert res["verdict"] == "PASS"
    assert res["tier"] == "T3_LLM_JUDGE"
    assert res["llm_tokens_used"] == 45
    assert "STOP-3" in res["stop_reason"]


def test_fallback_escalate_to_human_review():
    """Verify fallback to NEEDS_HUMAN_REVIEW when all automated tiers are inconclusive."""
    router = EvaluationRouter(enable_tier2=False, enable_tier3=False)
    evidence = {
        "response_text": "General financial statement without numeric values or citations.",
    }
    res = router.evaluate("resp_006", evidence)
    assert res["verdict"] == "NEEDS_HUMAN_REVIEW"
    assert res["tier"] == "ESCALATED"
    assert res["confidence"] == 0.3
    assert res["llm_tokens_used"] == 0
    assert "human review" in res["explanation"].lower()
