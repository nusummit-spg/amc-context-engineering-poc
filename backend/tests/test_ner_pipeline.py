# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_ner_pipeline.py
====================
Unit tests for FeedbackNERPipeline:
  - Extraction of attribute and asserted/rejected values
  - Extracting entity and linking to canonical ISIN
  - Fallback from original query when entity is omitted in feedback
"""

import pytest
from app.feedback.ner_pipeline import FeedbackNERPipeline


@pytest.fixture
def pipeline():
    return FeedbackNERPipeline()


def test_extract_structured_claim_full(pipeline):
    feedback = "Axis Bluechip Fund TER should be 0.82% not 0.79%"
    claim = pipeline.extract_structured_claim(feedback)
    assert claim is not None
    assert claim.attribute == "TER"
    assert claim.asserted_value == "0.82"
    assert claim.rejected_value == "0.79"
    assert len(claim.entity_candidates) > 0
    # Should resolve to canonical ISIN INF846K01DP5
    assert claim.resolved_entity_id == "INF846K01DP5"


def test_extract_claim_with_original_query(pipeline):
    feedback = "That is wrong, expense ratio is actually 0.82%"
    orig_query = "What is the TER of Axis Bluechip Fund?"
    claim = pipeline.extract_structured_claim(feedback, original_query=orig_query)
    assert claim is not None
    assert claim.attribute == "TER"
    assert claim.asserted_value == "0.82"
    assert claim.resolved_entity_id == "INF846K01DP5"


def test_extract_empty_or_clarification(pipeline):
    claim = pipeline.extract_structured_claim("Can you tell me more about this fund?")
    assert claim is None
