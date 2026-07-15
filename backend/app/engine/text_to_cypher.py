"""
text_to_cypher.py
===================
LLM generates ONE read-only Cypher query for aggregation-type questions,
scoped to the schema and documents actually relevant to this query. This
replaces relying solely on the fixed substring-match aggregate path, which
could silently match a generic term across the entire corpus.

graph_store.run_safe_cypher() validates and executes; this module never
touches the driver directly.
"""
from __future__ import annotations
import re
import time as _time
from typing import Any, Optional

from app.engine import config
from app.engine import graph_store
from app.engine import llm_text_client

_CYPHER_PROMPT = """You write a SINGLE read-only Neo4j Cypher query to answer a
financial-document question. The graph has one node label, `Entity`, with
properties: text, label, product_name, source, isin. Relationships are typed
edges between Entity nodes (e.g. MANAGES, HOLDS, INVESTS_IN, PART_OF) with a
`confidence` property.

Known entity label VALUES (the `label` property, not the node label): {entity_labels}
Known relationship TYPES currently in the graph: {rel_types}
This question is scoped to these product_name values only — your query MUST
filter on n.product_name IN {product_names}.

RULES:
- Output ONLY the Cypher query — no markdown fences, no commentary.
- Must start with MATCH. Must be read-only (no CREATE/MERGE/DELETE/SET/REMOVE).
- Must end with a RETURN clause and a LIMIT clause (LIMIT 25 or fewer).
- NEVER use CONTAINS on a single common/generic word as your only filter —
  filter by n.product_name first, and prefer exact matches on n.text.
- If the question cannot be answered with one MATCH query against this
  schema, output exactly: NO_QUERY

QUESTION: {question}

CYPHER:"""


# ── schema cache — avoids two Neo4j round-trips (labels + rel types) on
#    every single aggregation query. Schema barely changes between calls,
#    so a 5-minute TTL is safe and cheap. ─────────────────────────────────
_schema_cache: dict[str, Any] = {"labels": None, "rel_types": None, "ts": 0}
_SCHEMA_CACHE_TTL = 300


def _get_cached_schema() -> tuple[list[str], list[str]]:
    if _time.time() - _schema_cache["ts"] > _SCHEMA_CACHE_TTL:
        _schema_cache["labels"] = graph_store.get_entity_label_values()
        _schema_cache["rel_types"] = graph_store.get_relationship_types()
        _schema_cache["ts"] = _time.time()
    return _schema_cache["labels"], _schema_cache["rel_types"]


def _clean_cypher_output(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(cypher)?", "", raw, flags=re.I).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return raw


def generate_and_run(question: str, product_names: set[str]
                      ) -> tuple[Optional[list[dict[str, Any]]], dict]:
    """
    Returns (query_result_rows_or_None, usage). usage is ALWAYS returned —
    even on failure/NO_QUERY — so the caller can add this call's real token
    cost to its running total instead of it being silently uncounted.
    """
    empty_usage = {"input_tokens": 0, "output_tokens": 0}
    if not product_names:
        return None, empty_usage

    entity_labels, rel_types = _get_cached_schema()

    prompt = _CYPHER_PROMPT.format(
        entity_labels=", ".join(entity_labels[:30]),
        rel_types=", ".join(rel_types[:30]),
        product_names=list(product_names),
        question=question,
    )

    raw, usage = llm_text_client.call_llm_with_usage(prompt, model_id=config.CLAUDE_MODEL_LIGHT)
    cypher = _clean_cypher_output(raw or "")

    if not cypher or cypher.upper() == "NO_QUERY":
        return None, usage

    return graph_store.run_safe_cypher(cypher, max_rows=config.CYPHER_MAX_ROWS), usage