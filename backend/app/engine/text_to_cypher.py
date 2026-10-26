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
financial-document question. The graph has node label `Entity` with properties:
- Common properties: text, label, product_name, source, isin.
- Mutual Fund Schemes (`label: 'Scheme'`):
    - `aum_cr`: AUM in Crores (stored as string — always convert via `toFloat(s.aum_cr)` for math/aggregations).
      NOTE: Property `aum` does NOT exist in the database; ALWAYS use `aum_cr`.
    - `nav`: Net Asset Value (stored as string — convert via `toFloat(s.nav)`).
- Relationships between Entity nodes:
    - Schemes are offered by AMCs via:
      `(scheme:Entity {label: 'Scheme'})-[:OFFERED_BY]->(amc:Entity {label: 'AMC'})`
      (Do NOT use `MANAGES` for AMCs managing schemes; use `OFFERED_BY`).
    - Other relationships: HOLDS, INVESTS_IN, PART_OF, IN_CATEGORY, etc., with a `confidence` property.

Known entity label VALUES (the `label` property, not the node label): {entity_labels}
Known relationship TYPES currently in the graph: {rel_types}
{scope_clause}

RULES:
- Output ONLY the Cypher query — no markdown fences, no commentary.
- Must start with MATCH. Must be read-only (no CREATE/MERGE/DELETE/SET/REMOVE).
- Must end with a RETURN clause and a LIMIT clause (LIMIT 25 or fewer).
- NEVER use CONTAINS on a single common/generic word as your only filter —
  prefer exact matches on n.text and filter on n.label where possible.
- If querying AUM on a scheme, ALWAYS use `toFloat(s.aum_cr)`. NEVER use property `.aum`.
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


def invalidate_user_cypher_cache(user_id: str, tenant_id: Optional[str] = None) -> int:
    """Invalidate all Cypher cache entries for a specific user.

    Args:
        user_id (str): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        int: Resulting int instance.
    """
    from app.core.cache_utils import invalidate_user_cache
    return invalidate_user_cache(_CYPHER_CACHE, "cypher", user_id, tenant_id)


def _get_cypher_cache_key(
    question: str,
    product_names: set[str],
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    """Retrieve cypher cache key.

    Args:
        question (str): The question.
        product_names (set[str]): Collection or list of product names.
        user_id (Optional[str]): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        str: Resulting str instance.
    """
    norm_q = " ".join(question.strip().lower().split()[:25])
    sorted_prods = "|".join(sorted(product_names)) if product_names else "__none__"
    if user_id:
        from app.core.cache_utils import generate_cache_key
        return generate_cache_key(
            namespace="cypher",
            key_components={"question": norm_q, "products": sorted_prods},
            user_id=user_id,
            tenant_id=tenant_id,
        )
    raw = f"{sorted_prods}::{norm_q}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _get_cached_schema() -> tuple[list[str], list[str]]:
    """Retrieve cached schema.

    Returns:
        tuple[list[str], list[str]]: List of resulting items or records.
    """
    if _time.time() - _schema_cache["ts"] > _SCHEMA_CACHE_TTL:
        _schema_cache["labels"] = graph_store.get_entity_label_values()
        _schema_cache["rel_types"] = graph_store.get_relationship_types()
        _schema_cache["ts"] = _time.time()
    return _schema_cache["labels"], _schema_cache["rel_types"]


def _clean_cypher_output(raw: str) -> str:
    """Clean cypher output.

    Args:
        raw (str): The raw.

    Returns:
        str: Resulting str instance.
    """
    raw = raw.strip()
    raw = re.sub(r"^```(cypher)?", "", raw, flags=re.I).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return raw


def _correct_cypher_syntax(cypher: str, err_msg: str = "") -> str:
    """Attempts deterministic, zero-cost syntax fixes for common LLM Cypher generation mistakes.
    Fixes missing aliases, missing LIMIT clauses, unquoted hyphenated property names,
    domain attribute mismatches (.aum -> .aum_cr), numeric string conversions, and relationship fixes.

    Args:
        cypher (str): The cypher.
        err_msg (str): The err msg.

    Returns:
        str: Resulting str instance.
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

    # 5. Fix property name: .aum -> .aum_cr (property is named aum_cr in Neo4j)
    fixed = re.sub(r"\.aum\b(?!_cr)", ".aum_cr", fixed)

    # 6. Convert string numeric fields (aum_cr, nav) inside aggregation / arithmetic / coalesce to toFloat
    # E.g. coalesce(scheme.aum_cr, 0) -> coalesce(toFloat(scheme.aum_cr), 0.0)
    fixed = re.sub(
        r"coalesce\(\s*([a-zA-Z0-9_]+\.(?:aum_cr|nav))\s*,\s*0(?:\.0)?\s*\)",
        r"coalesce(toFloat(\1), 0.0)",
        fixed,
        flags=re.I
    )
    # E.g. sum(scheme.aum_cr) -> sum(toFloat(scheme.aum_cr)) if not already toFloat
    fixed = re.sub(
        r"(sum|avg|min|max)\(\s*(?!toFloat\()([a-zA-Z0-9_]+\.(?:aum_cr|nav))\s*\)",
        r"\1(toFloat(\2))",
        fixed,
        flags=re.I
    )

    # 7. Domain relationship repairs: AMC MANAGES Scheme -> Scheme OFFERED_BY AMC
    # (amc:Entity {label: 'AMC'})-[:MANAGES]->(scheme:Entity) -> (amc:Entity {label: 'AMC'})<-[:OFFERED_BY]-(scheme:Entity)
    fixed = re.sub(
        r"\((\w+)(?::Entity)?\s*\{label:\s*['\"]AMC['\"]\}\)\s*-\s*\[:MANAGES\]\s*->\s*\((\w+)",
        r"(\1:Entity {label: 'AMC'})<-[:OFFERED_BY]-(\2",
        fixed,
        flags=re.I
    )
    fixed = re.sub(
        r"\((\w+)\)\s*-\s*\[:MANAGES\]\s*->\s*\((\w+)(?::Entity)?\s*\{label:\s*['\"](?:Scheme|MUTUAL_FUND_SCHEME_NAME)['\"]\}\)",
        r"(\1)<-[:OFFERED_BY]-(\2:Entity {label: 'Scheme'})",
        fixed,
        flags=re.I
    )

    return fixed


def generate_and_run_with_correction(
    question: str,
    product_names: set[str],
    allow_global_scope: bool = False,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> tuple[Optional[list[dict[str, Any]]], dict]:
    """Generates and executes Cypher with multi-tier fallback:
    Tier 1: Query Cache Hit (0ms, 0 tokens)
    Tier 2: LLM Generation -> Direct Execution
    Tier 2.5: Rule-Based Syntax Auto-Correction (0ms, avoids slow LLM retry)
    Tier 3: LLM Retry with critique

    ``allow_global_scope`` lets corpus-wide aggregation questions ("total AUM of
    all equity schemes") run without any resolved product/entity scope. Without
    it those queries — precisely the ones the Cypher path exists for — return
    immediately because no product_name filter can be built.

    Args:
        question (str): The question.
        product_names (set[str]): Collection or list of product names.
        allow_global_scope (bool): The allow global scope.
        user_id (Optional[str]): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        tuple[Optional[list[dict[str, Any]]], dict]: List of resulting items or records.
    """
    empty_usage = {"input_tokens": 0, "output_tokens": 0, "source": "none"}
    if not product_names and not allow_global_scope:
        return None, empty_usage

    cache_key = _get_cypher_cache_key(
        question, product_names or {"__global__"}, user_id=user_id, tenant_id=tenant_id
    )

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

    if product_names:
        scope_clause = (
            "This question is scoped to these product_name values only. Your query MUST "
            f"filter on n.product_name IN {list(product_names)}."
        )
    else:
        scope_clause = (
            "This question is a corpus-wide aggregation. Do NOT filter on product_name. "
            "Aggregate across the whole graph using count/sum/avg/collect and ORDER BY as needed."
        )

    prompt = _CYPHER_PROMPT.format(
        entity_labels=", ".join(entity_labels[:30]),
        rel_types=", ".join(rel_types[:30]),
        scope_clause=scope_clause,
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

        # Tier 2.1: Pre-apply domain and syntax auto-repairs before execution
        if config.ENABLE_CYPHER_AUTO_CORRECTION:
            cypher = _correct_cypher_syntax(cypher)

        # Direct execution attempt
        rows, err_msg = graph_store.run_safe_cypher(cypher, max_rows=config.CYPHER_MAX_ROWS)
        
        if err_msg is None and rows:
            if len(_CYPHER_CACHE) < _CYPHER_CACHE_MAX:
                _CYPHER_CACHE[cache_key] = cypher
            empty_usage["source"] = "llm_direct"
            empty_usage["cypher"] = cypher
            return rows, empty_usage

        if err_msg is None and not rows:
            # Query succeeded syntactically but returned 0 rows, check if further correction helps
            if config.ENABLE_CYPHER_AUTO_CORRECTION:
                corrected_cypher = _correct_cypher_syntax(cypher)
                if corrected_cypher != cypher:
                    c_rows, c_err = graph_store.run_safe_cypher(corrected_cypher, max_rows=config.CYPHER_MAX_ROWS)
                    if c_err is None and c_rows:
                        if len(_CYPHER_CACHE) < _CYPHER_CACHE_MAX:
                            _CYPHER_CACHE[cache_key] = corrected_cypher
                        empty_usage["source"] = "corrected"
                        empty_usage["cypher"] = corrected_cypher
                        return c_rows, empty_usage
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


def generate_and_run(
    question: str,
    product_names: set[str],
    allow_global_scope: bool = False,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> tuple[Optional[list[dict[str, Any]]], dict]:
    """Preserves backwards compatibility with existing pipeline callers.

    Args:
        question (str): The question.
        product_names (set[str]): Collection or list of product names.
        allow_global_scope (bool): The allow global scope.
        user_id (Optional[str]): Unique identifier of the user.
        tenant_id (Optional[str]): Unique identifier of the tenant.

    Returns:
        tuple[Optional[list[dict[str, Any]]], dict]: List of resulting items or records.
    """
    return generate_and_run_with_correction(
        question,
        product_names,
        allow_global_scope=allow_global_scope,
        user_id=user_id,
        tenant_id=tenant_id,
    )

