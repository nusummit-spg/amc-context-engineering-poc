# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_dissatisfaction_detector.py
================================
Unit tests for Track 4: Dissatisfaction Detection Module and Claim Extraction.
"""

import pytest
from app.feedback.dissatisfaction_detector import DissatisfactionDetector
from app.feedback.correction_extractor import CorrectionExtractor


@pytest.fixture
def detector():
    return DissatisfactionDetector()


@pytest.fixture
def extractor():
    return CorrectionExtractor()


def test_clear_correction_detected(detector):
    is_correction, claim = detector.is_correction_attempt(
        follow_up_query="No that's incorrect! TER is 0.82% not 0.79%",
        original_response="The TER is 0.79%",
        original_query="What is the TER of Axis Bluechip Fund?"
    )
    assert is_correction is True
    assert claim is not None
    assert claim.attribute == "TER"
    assert claim.asserted_value == "0.82"
    assert claim.rejected_value == "0.79"


def test_clarification_not_detected(detector):
    is_correction, claim = detector.is_correction_attempt(
        follow_up_query="Can you also tell me the NAV?",
        original_response="The TER is 0.82%",
        original_query="What is the TER?"
    )
    assert is_correction is False
    assert claim is None


def test_positive_follow_up_not_detected(detector):
    is_correction, claim = detector.is_correction_attempt(
        follow_up_query="Great, thank you! What about the 5-year return?",
        original_response="The TER is 0.82%",
        original_query="What is the TER?"
    )
    assert is_correction is False
    assert claim is None


def test_sentiment_frustration(detector):
    is_frustrated, score = detector._detect_frustration("That's completely wrong and incorrect!")
    assert is_frustrated is True
    assert score <= detector.sentiment_threshold

    is_frustrated_pos, score_pos = detector._detect_frustration("Great, excellent response!")
    assert is_frustrated_pos is False
    assert score_pos > 0


def test_same_referent_check(detector):
    same_topic, sim = detector._check_same_referent(
        follow_up_query="That TER value is wrong, it's 0.82%",
        original_query="What is the TER of Axis Bluechip Fund?"
    )
    assert same_topic is True
    assert sim >= 0.65

    diff_topic, sim_diff = detector._check_same_referent(
        follow_up_query="What is the weather in Mumbai today?",
        original_query="What is the TER of Axis Bluechip Fund?"
    )
    assert diff_topic is False


def test_correction_language(detector):
    has_intent, conf = detector._has_correction_language(
        "That's wrong, check the source, it should actually be 0.82%"
    )
    assert has_intent is True
    assert conf >= 0.65

    no_intent, conf_none = detector._has_correction_language(
        "Can you give me more information on this fund?"
    )
    assert no_intent is False
    assert conf_none == 0.0


def test_extractor_numbers_and_currency(extractor):
    numbers = extractor._extract_numbers("NAV should be ₹64.31 not Rs. 64.18 with 12.5% return")
    assert 64.31 in numbers
    assert 64.18 in numbers
    assert 12.5 in numbers


def test_extractor_claim_complete(extractor):
    claim = extractor.extract_claim(
        feedback_text="NAV should be ₹64.31 not ₹64.18",
        original_response="The current NAV is ₹64.18",
        original_query="What is the NAV of Axis Bluechip?"
    )
    assert claim is not None
    assert claim.attribute == "NAV"
    assert claim.asserted_value == "64.31"
    assert claim.rejected_value == "64.18"
