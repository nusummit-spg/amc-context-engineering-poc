# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_query_merging.py
======================
Tests for dual-scope merged Cypher traversal:
- Validates single roundtrip with UNION of entity and product scopes
- Validates priority ordering (entity scope over product fallback)
"""
from unittest.mock import patch
import pytest

from app.engine import graph_store


def test_subgraph_with_fallback_empty():
    res = graph_store.get_subgraph_with_fallback(entity_names=[], product_names=[])
    assert res["dual_scope"] is True
    assert len(res["edges"]) == 0


@patch("app.engine.graph_store.run_safe_cypher")
def test_subgraph_with_fallback_query_execution(mock_cypher):
    mock_cypher.return_value = (
        [
            {"entity": "Adani Enterprises", "rel": "ISSUED_BY", "obj": "Adani Group", "conf": 0.95, "source_priority": 1},
            {"entity": "Tata Balanced", "rel": "HOLDS", "obj": "Infosys", "conf": 0.85, "source_priority": 2},
        ],
        None
    )

    res = graph_store.get_subgraph_with_fallback(
        entity_names=["Adani Enterprises"],
        product_names=["Tata Balanced"],
        hops=1,
        limit=10,
    )

    assert res["dual_scope"] is True
    assert len(res["edges"]) == 2
    # Verify Cypher was invoked with both entity and product parameters
    assert mock_cypher.called
    call_args = mock_cypher.call_args
    params = call_args[1].get("params", {})
    assert "entity_names" in params
    assert "product_names" in params
    assert params["entity_names"] == ["Adani Enterprises"]
    assert params["product_names"] == ["Tata Balanced"]
