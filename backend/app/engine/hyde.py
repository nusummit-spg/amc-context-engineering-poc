# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import hashlib
import time
from typing import Any, Dict, Tuple
from app.engine import config
from app.engine.llm_text_client import call_llm_with_usage

HYDE_SYSTEM_PROMPT = """You are an expert AMC knowledge assistant. 
Your task is to generate a HYPOTHETICAL document excerpt that perfectly answers the user's question.
This hypothetical document will be used to perform a vector similarity search against real documents.
Write the response as if it were an official SEBI circular, an AMFI guideline, or a formal Mutual Fund portfolio disclosure.
DO NOT use conversational filler (e.g. "Here is the excerpt"). Just output the raw hypothetical text.
Keep it strictly under 150 words."""

# Cache configuration
_HYDE_CACHE: Dict[str, Tuple[str, float]] = {}  # {cache_key: (result, timestamp)}
_HYDE_TTL = 3600  # 1 hour
_HYDE_MAX_CACHE_SIZE = 5000

def _get_cache_key(query: str) -> str:
    """Normalize first 30 words to match semantically equivalent query prefixes."""
    query_norm = " ".join(query.strip().lower().split()[:30])
    return hashlib.md5(query_norm.encode("utf-8")).hexdigest()

def _prune_cache_if_needed():
    """Evict oldest entries when cache reaches capacity."""
    if len(_HYDE_CACHE) >= _HYDE_MAX_CACHE_SIZE:
        to_remove = int(_HYDE_MAX_CACHE_SIZE * 0.2)
        oldest = sorted(_HYDE_CACHE.items(), key=lambda x: x[1][1])[:to_remove]
        for key, _ in oldest:
            _HYDE_CACHE.pop(key, None)

def generate_hypothetical_document(query: str) -> Tuple[str, float]:
    """
    Calls the LLM to generate a hypothetical document for the given query,
    with an in-memory MD5 prefix cache for sub-millisecond repeated queries.
    Returns (hypothetical_document_text, latency_ms).
    """
    t0 = time.perf_counter()
    cache_key = _get_cache_key(query)
    now = time.time()

    # Tier 1: Cache check
    if config.ENABLE_HYDE_CACHE and cache_key in _HYDE_CACHE:
        result, timestamp = _HYDE_CACHE[cache_key]
        if now - timestamp < _HYDE_TTL:
            cache_hit_latency = (time.perf_counter() - t0) * 1000.0
            print(f"  [hyde] Cache HIT ({cache_hit_latency:.2f}ms)")
            return result, cache_hit_latency

    # Tier 2: Cache miss -> Call LLM
    print("  [hyde] Cache MISS -> Generating hypothetical document...")
    hypothetical_doc, _ = call_llm_with_usage(
        system_prompt=HYDE_SYSTEM_PROMPT,
        user_prompt=query,
        model_id=config.GROQ_MODEL_LIGHT,
        max_tokens=250
    )
    result_text = hypothetical_doc.strip()
    latency = (time.perf_counter() - t0) * 1000.0

    _prune_cache_if_needed()
    _HYDE_CACHE[cache_key] = (result_text, now)

    print(f"  [hyde] Generated in {latency:.1f}ms")
    return result_text, latency

def clear_hyde_cache():
    """Clears the HyDE cache (useful for testing or manual invalidation)."""
    global _HYDE_CACHE
    _HYDE_CACHE.clear()

def get_hyde_cache_stats() -> Dict[str, Any]:
    """Returns HyDE cache statistics for monitoring."""
    now = time.time()
    valid_entries = sum(1 for _, (_, ts) in _HYDE_CACHE.items() if (now - ts) < _HYDE_TTL)
    return {
        "cache_size": len(_HYDE_CACHE),
        "valid_entries": valid_entries,
        "max_size": _HYDE_MAX_CACHE_SIZE,
        "ttl_seconds": _HYDE_TTL
    }

