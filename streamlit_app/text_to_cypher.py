"""
text_to_cypher.py
===================
PLACEHOLDER — this module was referenced by retrieval.py's aggregation path
(generate_and_run) but never committed. Rather than invent an LLM-generated,
"safety-validated" Cypher executor (real injection/data-integrity risk to get
wrong) without the actual intended validation logic, this stub always returns
None, so retrieval.py falls through to its existing, complete fallback:
similarity-resolved deterministic aggregation via entity_resolver.py +
graph_store.get_aggregate_for_entity().

Replace this once the real implementation (with its safety validation) is
available. See retrieval.py's docstring for the intended design: the LLM
writes ONE targeted, schema-aware, safety-validated query rather than relying
on a fixed 1-hop pattern.
"""
from __future__ import annotations


def generate_and_run(query: str, product_names: set | None = None) -> list[dict] | None:
    """Always returns None (no generated-Cypher path yet) — see module docstring."""
    return None
