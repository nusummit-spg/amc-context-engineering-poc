"""
query_classifier.py
=====================
Routes each query to the retrieval strategy that's actually good at it.
Cheap regex pass first; only falls to an LLM call for genuinely ambiguous
queries, so this doesn't add meaningful latency to the common case.
"""
from __future__ import annotations
import re

import config
import llm_text_client

AGGREGATION_PATTERNS = re.compile(
    r"\b(total|combined|sum|across all|aggregate|how many|cumulative)\b", re.I)
COMPARISON_PATTERNS = re.compile(
    r"\b(compare|versus|vs\.?|difference between|which.*more|relative to)\b", re.I)
LOOKUP_PATTERNS = re.compile(
    r"\b(who (manages|holds|is)|what is the (benchmark|exit load|isin))\b", re.I)

_CLASSIFY_PROMPT = """Classify this question into exactly one category:
- aggregation: needs a total/sum/count across multiple documents or records
- comparison: needs comparing two or more named entities against each other
- direct_lookup: a single factual attribute of a single named entity
- open_ended: anything else, needs prose synthesis

QUESTION: {query}

Respond with ONLY the category name, nothing else."""


def classify_query(query: str) -> str:
    """Fast path: regex. Only calls the LLM if regex is inconclusive."""
    if AGGREGATION_PATTERNS.search(query):
        return "aggregation"
    if COMPARISON_PATTERNS.search(query):
        return "comparison"
    if LOOKUP_PATTERNS.search(query):
        return "direct_lookup"

    # ambiguous — cheap Haiku call rather than guessing wrong
    result = llm_text_client.call_llm(
        _CLASSIFY_PROMPT.format(query=query), model_id=config.CLAUDE_MODEL_LIGHT)
    result = (result or "").strip().lower()
    if result in ("aggregation", "comparison", "direct_lookup", "open_ended"):
        return result
    return "open_ended"