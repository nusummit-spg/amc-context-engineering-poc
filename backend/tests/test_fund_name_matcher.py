# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_fund_name_matcher.py
=========================
Unit tests for FundNameMatcher:
  - Exact match lookup
  - Fuzzy string matching
  - Abbreviations expansion (e.g. ABSL)
  - User context disambiguation (Direct vs Regular)
"""

import pytest
from app.feedback.fund_name_matcher import FundNameMatcher


@pytest.fixture
def sample_funds():
    return [
        {
            "isin": "INF846K01DP5",
            "fund_name": "Axis Bluechip Fund Direct Growth",
            "plan": "Direct",
            "option": "Growth"
        },
        {
            "isin": "INF846K01CT5",
            "fund_name": "Axis Bluechip Fund Regular Growth",
            "plan": "Regular",
            "option": "Growth"
        },
        {
            "isin": "INF769K01EW8",
            "fund_name": "Mirae Asset Large Cap Fund Direct Growth",
            "plan": "Direct",
            "option": "Growth"
        },
        {
            "isin": "INF209K01157",
            "fund_name": "Aditya Birla Sun Life Frontline Equity Fund Direct Growth",
            "plan": "Direct",
            "option": "Growth"
        }
    ]


@pytest.fixture
def matcher(sample_funds):
    return FundNameMatcher(fund_master_data=sample_funds)


def test_exact_isin_match(matcher):
    result = matcher.resolve("INF846K01DP5")
    assert result is not None
    assert result["isin"] == "INF846K01DP5"
    assert result["confidence"] == 1.0


def test_exact_name_match(matcher):
    result = matcher.resolve("Axis Bluechip Fund Direct Growth")
    assert result is not None
    assert result["isin"] == "INF846K01DP5"
    assert result["confidence"] == 1.0


def test_fuzzy_name_match(matcher):
    result = matcher.resolve("axis bluechip fund direct growth")
    assert result is not None
    assert result["isin"] == "INF846K01DP5"
    assert result["confidence"] >= 0.70


def test_partial_abbreviation_match(matcher):
    result = matcher.resolve("ABSL Frontline Equity")
    assert result is not None
    assert result["isin"] == "INF209K01157"


def test_user_context_disambiguation(matcher):
    # Ambiguous input between Direct and Regular
    context = {"previous_queries": ["What is the expense ratio of Axis Direct plan?"]}
    result = matcher.resolve("Axis Bluechip", user_context=context)
    assert result is not None
    assert result["isin"] == "INF846K01DP5"  # Direct chosen due to context
