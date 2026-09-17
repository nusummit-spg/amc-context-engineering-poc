# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_deterministic_rules.py
===========================
Unit tests for Track 5: Deterministic Rules Engine (Tier 1A) and STOP-1 gate.
"""

import pytest
from app.evaluation.deterministic_rules import (
    DeterministicRuleEngine,
    RuleVerdict,
)
from app.evaluation.evaluation_router import EvaluationRouter


@pytest.fixture
def engine():
    return DeterministicRuleEngine(source_max_age_days=7, numeric_deviation_threshold=0.05)


@pytest.fixture
def router():
    return EvaluationRouter()


def test_c02_source_currency_pass(engine):
    evidence = {"source_age_days": 3}
    res = engine.evaluate_source_currency(evidence)
    assert res.verdict == RuleVerdict.PASS
    assert res.confidence == 1.0


def test_c02_source_currency_fail(engine):
    evidence = {"source_age_days": 14}
    res = engine.evaluate_source_currency(evidence)
    assert res.verdict == RuleVerdict.FAIL
    assert res.confidence == 1.0
    assert "exceeds" in res.explanation


def test_c03_numeric_accuracy_pass(engine):
    evidence = {"chunks": [{"text": "The scheme TER is 0.82% and current NAV is 64.30."}]}
    res = engine.evaluate_numeric_accuracy(
        response_text="The fund TER is 0.82% with NAV 64.30",
        evidence_pack=evidence
    )
    assert res.verdict == RuleVerdict.PASS
    assert res.confidence == 1.0


def test_c03_numeric_accuracy_fail(engine):
    # Response says 0.79% but source is 0.82% (deviation > 3.6% threshold 5% or 0.70 vs 0.82 > 14%)
    evidence = {"chunks": [{"text": "The scheme TER is 0.82%."}]}
    res = engine.evaluate_numeric_accuracy(
        response_text="The fund TER is 0.70%",  # 14.6% deviation
        evidence_pack=evidence
    )
    assert res.verdict == RuleVerdict.FAIL
    assert res.confidence == 1.0
    assert len(res.evidence["mismatches"]) >= 1


def test_f06_citation_integrity_pass(engine):
    evidence = {"chunk_ids": ["C_101", "C_102", "C_103"]}
    res = engine.evaluate_citation_integrity(
        response_text="As reported in the factsheet [source: C_101] and regulations [chunk_id: C_102].",
        evidence_pack=evidence
    )
    assert res.verdict == RuleVerdict.PASS
    assert res.confidence == 1.0


def test_f06_citation_integrity_fail(engine):
    evidence = {"chunk_ids": ["C_101"]}
    res = engine.evaluate_citation_integrity(
        response_text="As reported in the factsheet [source: C_999].",  # Broken citation
        evidence_pack=evidence
    )
    assert res.verdict == RuleVerdict.FAIL
    assert res.confidence == 1.0
    assert "C_999" in res.evidence["broken_citations"]


def test_stop1_gate_router_zero_tokens(router):
    # Stale source triggers STOP-1
    evidence = {
        "response_text": "The TER is 0.82%",
        "source_age_days": 21,
        "chunks": [{"text": "TER is 0.82%"}],
        "chunk_ids": ["C_1"]
    }
    decision = router.evaluate(response_id="resp_stale_123", evidence_pack=evidence)
    assert decision["verdict"] == "FAIL"
    assert decision["tier"] == "T1A_RULES"
    assert decision["llm_tokens_used"] == 0
    assert "STOP-1" in decision["stop_reason"]


def test_all_pass_gate_router(router):
    evidence = {
        "response_text": "The TER is 0.82% [source: C_101]",
        "source_age_days": 2,
        "chunks": [{"text": "TER is 0.82%"}],
        "chunk_ids": ["C_101"]
    }
    decision = router.evaluate(response_id="resp_clean_123", evidence_pack=evidence)
    assert decision["verdict"] == "PASS"
    assert decision["tier"] == "T1A_RULES"
    assert decision["llm_tokens_used"] == 0
