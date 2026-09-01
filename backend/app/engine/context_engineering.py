# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
context_engineering.py
========================
Assembles the final prompt from retrieval outputs. Owns section ordering,
deduplication, and token budgeting — retrieval.py just calls build_prompt().
"""
import re
from app.engine import config

# context_engineering.py (Updated Section)

def _dedupe_prose_against_graph(hits: list[dict], graph_facts_text: str) -> list[dict]:
    """Loosen lexical overlap to prevent context starvation of prose text."""
    if not graph_facts_text:
        return hits
    graph_terms = set(re.findall(r'\b[A-Z][a-zA-Z]{3,}\b', graph_facts_text))
    if not graph_terms:
        return hits
    kept = []
    for h in hits:
        chunk_terms = set(re.findall(r'\b[A-Z][a-zA-Z]{3,}\b', h['parent_text']))
        overlap = len(chunk_terms & graph_terms) / max(len(chunk_terms), 1)
        # Increase the threshold to 0.85 so we only drop text if it's an absolute duplicate
        if overlap < 0.85: 
            kept.append(h)
    return kept

# Increase vector chunk breathing room for deeper answers
QUERY_TYPE_BUDGETS = {
    "aggregation":   {"graph_frac": 0.5, "vector_frac": 0.35},
    "comparison":    {"graph_frac": 0.4, "vector_frac": 0.4},
    "direct_lookup": {"graph_frac": 0.2, "vector_frac": 0.65},
    "open_ended":    {"graph_frac": 0.1, "vector_frac": 0.75},
}
DEFAULT_TOKEN_BUDGET = 1200  # tightened from 1500

RANKING_PREAMBLE = """Rank sources by reliability: VERIFIED FACTS (graph-computed, cite "[graph]") >
GRAPH RELATIONSHIPS (structured, cite [1][2]) > DOCUMENT PROSE (cite [1][2] using ONLY the
short numeric index shown before each source below -- never restate the filename or page
inline). Note conflicts only if they materially change the answer. Say if nothing answers
the question. Answer in one tight paragraph (3-5 sentences) plus, only if the question asks
for multiple distinct items, a short list of just those items -- no extra headers, no
invented sections, no restating source material."""

def build_prompt(query: str, verified_facts: str, comparison_blocks: str,
                  top_edges: list[dict], hits: list[dict], query_type: str = "open_ended",
                  trust_verified_facts: bool = False, total_token_budget: int = DEFAULT_TOKEN_BUDGET
                  ) -> tuple[str, int]:
    has_structured = bool(verified_facts or comparison_blocks or top_edges)

    graph_context_str = "\n".join(f"{e['s']} --{e['rel']}--> {e['o']}" for e in top_edges)
    extra_sections = ""
    if verified_facts:
        extra_sections += f"\n[VERIFIED AGGREGATE]\n{verified_facts}\n"
    if comparison_blocks:
        extra_sections += f"\nPER-ENTITY GRAPH NEIGHBORHOODS:\n{comparison_blocks}\n"
    graph_section = f"\nGRAPH RELATIONSHIPS:\n{graph_context_str}\n" if top_edges else ""

    effective_hits = _dedupe_prose_against_graph(hits, extra_sections + graph_section) \
        if has_structured else hits

    budgets = QUERY_TYPE_BUDGETS.get(query_type, QUERY_TYPE_BUDGETS["open_ended"])
    vector_budget = int(total_token_budget * budgets["vector_frac"])
    if trust_verified_facts and query_type in ("aggregation", "comparison"):
        if config.ENABLE_SMART_VECTOR_PRUNING:
            # Score-gap sensitive budgeting & pruning: if top hits are close (< 0.10), retain top-2
            if len(effective_hits) >= 2:
                score_gap = effective_hits[0].get("score", 0.0) - effective_hits[1].get("score", 0.0)
                if score_gap < 0.10:
                    vector_budget = int(total_token_budget * 0.25)
                    effective_hits = effective_hits[:2]
                else:
                    vector_budget = int(total_token_budget * 0.15)
                    effective_hits = effective_hits[:1]
            elif effective_hits:
                vector_budget = int(total_token_budget * 0.15)
                effective_hits = effective_hits[:1]
        else:
            vector_budget = min(vector_budget, int(total_token_budget * 0.15))
            effective_hits = effective_hits[:1]
    elif trust_verified_facts:
        vector_budget = min(vector_budget, int(total_token_budget * 0.15))

    kept, used = [], 0
    for h in effective_hits:
        cost = len(h['parent_text']) // 4
        if used + cost > vector_budget:
            continue
        kept.append(h)
        used += cost
    effective_hits = kept

    vector_context = "\n\n---\n\n".join(
        f"[{i+1}] {h['product_name']} p.{h['page_num']}\n{h['parent_text']}"
        for i, h in enumerate(effective_hits))

    prompt = f"""{RANKING_PREAMBLE}
{extra_sections}{graph_section}
DOCUMENT PROSE:
{vector_context}

QUESTION: {query}

ANSWER:"""

    # ── output cap — richer answers get a bit more room, but still bounded ──
    max_output_tokens = 260 if not has_structured else 360
    return prompt, max_output_tokens
