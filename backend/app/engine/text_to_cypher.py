# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

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


import hashlib

# ── schema cache — avoids two Neo4j round-trips (labels + rel types) on
#    every single aggregation query. Schema barely changes between calls,
#    so a 5-minute TTL is safe and cheap. ─────────────────────────────────
_schema_cache: dict[str, Any] = {"labels": None, "rel_types": None, "ts": 0}
_SCHEMA_CACHE_TTL = 300

# ── cypher cache — caches successfully generated and executed Cypher queries ─
_CYPHER_CACHE: dict[str, str] = {}  # cache_key -> cypher_query
_CYPHER_CACHE_MAX = 500


def clear_cypher_cache():
    """Clears cached Cypher queries."""
    global _CYPHER_CACHE, _schema_cache
    _CYPHER_CACHE.clear()
    _schema_cache = {"labels": None, "rel_types": None, "ts": 0}


def _get_cypher_cache_key(question: str, product_names: set[str]) -> str:
    norm_q = " ".join(question.strip().lower().split()[:25])
    sorted_prods = "|".join(sorted(product_names)) if product_names else "__none__"
    raw = f"{sorted_prods}::{norm_q}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


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


def _correct_cypher_syntax(cypher: str, err_msg: str = "") -> str:
    """
    Attempts deterministic, zero-cost syntax fixes for common LLM Cypher generation mistakes.
    Fixes missing aliases, missing LIMIT clauses, and unquoted hyphenated property names.
    """
    fixed = cypher.strip()

    # 1. Missing alias on aggregate return (e.g. RETURN count(e) -> RETURN count(e) AS result)
    fixed = re.sub(
        r"(RETURN\s+(?:count|sum|avg|min|max)\([^)]+\))(?!\s+AS)",
        r"\1 AS result",
        fixed,
        flags=re.I
    )

    # 2. Missing LIMIT in aggregation / match queries
    if "RETURN" in fixed.upper() and "LIMIT" not in fixed.upper():
        fixed = fixed.rstrip(";") + "\nLIMIT 25"

    # 3. Unquoted hyphenated property names (e.g. n.exit-load -> n.[`exit-load`])
    fixed = re.sub(r"\.([a-zA-Z0-9_]+-[a-zA-Z0-9_-]+)", r".[`\1`]", fixed)

    # 4. Redundant UNWIND x AS x
    fixed = re.sub(r"UNWIND\s+(\w+)\s+AS\s+\1(?=\s|;|$)", "", fixed, flags=re.I)

    return fixed


def generate_and_run_with_correction(
    question: str,
    product_names: set[str]
) -> tuple[Optional[list[dict[str, Any]]], dict]:
    """
    Generates and executes Cypher with multi-tier fallback:
    Tier 1: Query Cache Hit (0ms, 0 tokens)
    Tier 2: LLM Generation -> Direct Execution
    Tier 2.5: Rule-Based Syntax Auto-Correction (0ms, avoids slow LLM retry)
    Tier 3: LLM Retry with critique
    """
    empty_usage = {"input_tokens": 0, "output_tokens": 0, "source": "none"}
    if not product_names:
        return None, empty_usage

    cache_key = _get_cypher_cache_key(question, product_names)

    # Tier 1: Check Cypher cache
    if cache_key in _CYPHER_CACHE:
        cached_cypher = _CYPHER_CACHE[cache_key]
        rows, err = graph_store.run_safe_cypher(cached_cypher, max_rows=config.CYPHER_MAX_ROWS)
        if err is None:
            print("  [text_to_cypher] Cypher cache HIT")
            return rows, {"input_tokens": 0, "output_tokens": 0, "source": "cache", "cypher": cached_cypher}
        else:
            _CYPHER_CACHE.pop(cache_key, None)

    entity_labels, rel_types = _get_cached_schema()

    prompt = _CYPHER_PROMPT.format(
        entity_labels=", ".join(entity_labels[:30]),
        rel_types=", ".join(rel_types[:30]),
        product_names=list(product_names),
        question=question,
    )

    MAX_RETRIES = 2
    for attempt in range(MAX_RETRIES):
        raw, usage = llm_text_client.call_llm_with_usage(prompt, model_id=config.GROQ_MODEL_LIGHT)
        
        empty_usage["input_tokens"] += usage.get("input_tokens", 0)
        empty_usage["output_tokens"] += usage.get("output_tokens", 0)
        
        cypher = _clean_cypher_output(raw or "")
        if not cypher or cypher.upper() == "NO_QUERY":
            return None, empty_usage

        # Direct execution attempt
        rows, err_msg = graph_store.run_safe_cypher(cypher, max_rows=config.CYPHER_MAX_ROWS)
        
        if err_msg is None:
            if len(_CYPHER_CACHE) < _CYPHER_CACHE_MAX:
                _CYPHER_CACHE[cache_key] = cypher
            empty_usage["source"] = "llm_direct"
            empty_usage["cypher"] = cypher
            return rows, empty_usage

        # Tier 2.5: Try rule-based syntax correction before LLM retry
        if config.ENABLE_CYPHER_AUTO_CORRECTION:
            print(f"  [cypher-auto-repair] Attempt {attempt+1} failed ({err_msg}). Trying rule-based correction...")
            corrected_cypher = _correct_cypher_syntax(cypher, err_msg)
            if corrected_cypher != cypher:
                corrected_rows, corrected_err = graph_store.run_safe_cypher(
                    corrected_cypher, max_rows=config.CYPHER_MAX_ROWS
                )
                if corrected_err is None:
                    print("  [cypher-auto-repair] Rule-based correction SUCCEEDED (saved LLM retry)!")
                    if len(_CYPHER_CACHE) < _CYPHER_CACHE_MAX:
                        _CYPHER_CACHE[cache_key] = corrected_cypher
                    empty_usage["source"] = "corrected"
                    empty_usage["cypher"] = corrected_cypher
                    return corrected_rows, empty_usage

        print(f"  [cypher-critique] Attempt {attempt+1} failed: {err_msg}")
        if attempt < MAX_RETRIES - 1:
            prompt += f"\n\n{raw}\n\nThe above Cypher query failed with the following Neo4j Error:\n{err_msg}\n\nPlease correct the syntax and provide ONLY the corrected Cypher query."

    return None, empty_usage


def generate_and_run(question: str, product_names: set[str]
                      ) -> tuple[Optional[list[dict[str, Any]]], dict]:
    """Preserves backwards compatibility with existing pipeline callers."""
    return generate_and_run_with_correction(question, product_names)

