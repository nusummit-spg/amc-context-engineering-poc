# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_cypher_aggregation.py
==========================
Tests for Cypher aggregation intent detection, syntax auto-correction,
and query execution.
"""
from unittest.mock import MagicMock, patch
import pytest

from app.engine import text_to_cypher
from app.retrieval.intent import IntentClassifier
from app.schemas.query import QueryType


def test_aggregation_keyword_detection():
    detect = IntentClassifier._detect_aggregation

    assert detect("What is the total AUM of all schemes?")[0] is True
    assert detect("What is the total AUM of all schemes?")[1] == "sum"

    assert detect("How many schemes comply with SEBI?")[0] is True
    assert detect("How many schemes comply with SEBI?")[1] == "count"

    assert detect("List the top 5 performing funds")[0] is True
    assert detect("List the top 5 performing funds")[1] == "ranking"

    assert detect("Tell me about Adani Growth")[0] is False


def test_cypher_auto_correction_rules():
    # 1. Missing alias on aggregate return
    bad1 = "MATCH (n:Entity) RETURN count(n)"
    fixed1 = text_to_cypher._correct_cypher_syntax(bad1)
    assert "AS result" in fixed1

    # 2. Missing LIMIT
    bad2 = "MATCH (n:Entity) RETURN n.text"
    fixed2 = text_to_cypher._correct_cypher_syntax(bad2)
    assert "LIMIT 25" in fixed2

    # 3. Hyphenated properties
    bad3 = "MATCH (n:Entity) RETURN n.exit-load"
    fixed3 = text_to_cypher._correct_cypher_syntax(bad3)
    assert "n.[`exit-load`]" in fixed3


@patch("app.engine.graph_store.run_safe_cypher")
@patch("app.engine.llm_text_client.call_llm_with_usage")
def test_cypher_correction_prevents_retry_on_recoverable_error(mock_llm, mock_cypher):
    text_to_cypher.clear_cypher_cache()
    # LLM outputs Cypher with missing alias: RETURN count(n)
    mock_llm.return_value = ("MATCH (n:Entity) RETURN count(n)", {"input_tokens": 10, "output_tokens": 5})

    # First attempt fails with Neo4j error requiring alias, rule-based repair then succeeds!
    mock_cypher.side_effect = [
        (None, "Neo.ClientError.Statement.SyntaxError: Expression in RETURN must be given an alias"),
        ([{"result": 42}], None),
    ]

    rows, usage = text_to_cypher.generate_and_run_with_correction(
        question="What is the total count of funds?",
        product_names={"FundA"}
    )

    assert rows == [{"result": 42}]
    assert usage["source"] == "corrected"
    assert mock_llm.call_count == 1  # Saved LLM retry!
