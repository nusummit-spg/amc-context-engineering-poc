"""
context_engineering.py
========================
Assembles the final prompt from retrieval outputs. Owns section ordering,
deduplication, and token budgeting — retrieval.py just calls build_prompt().
"""
import re

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
DEFAULT_TOKEN_BUDGET = 3600  # Increased to 3600 chars (~900 tokens) to prevent dropping 1200-char parent chunks

PROMPT_TEMPLATES = {
    ("open_ended", "esg_sustainability"): """Rank sources by reliability: VERIFIED FACTS > GRAPH RELATIONSHIPS > DOCUMENT PROSE.
Focus on ESG sustainability initiatives, decarbonization targets, carbon emissions, and environmental benefits.
Cite sources as [1], [2]. Answer clearly in 3-5 structured sentences with bullet points for distinct initiatives.""",
    ("open_ended", "sebi_regulation"): """Rank sources by reliability: VERIFIED FACTS > GRAPH RELATIONSHIPS > DOCUMENT PROSE.
Focus on SEBI regulatory compliance rules, circular clauses, and AMC operational guidelines.
Cite sources as [1], [2]. Answer concisely highlighting mandatory requirements.""",
    ("aggregation", "sebi_regulation"): """VERIFIED AGGREGATES provide primary ground truth. State totals clearly and summarize underlying clauses.""",
    ("comparison", "financial_performance"): """Compare entity metrics side-by-side. Highlight EBITDA, Revenue, Credit Ratings, and leverage differences clearly.""",
}

DEFAULT_PREAMBLE = """Rank sources by reliability: VERIFIED FACTS (graph-computed, cite "[graph]") >
GRAPH RELATIONSHIPS (structured, cite [1][2]) > DOCUMENT PROSE (cite [1][2] using ONLY the
short numeric index shown before each source below — never restate the filename or page
inline). Note conflicts only if they materially change the answer. Say if nothing answers
the question. Answer in one tight paragraph (3-5 sentences) plus, only if the question asks
for multiple distinct items, a short list of just those items — no extra headers, no
invented sections, no restating source material."""

def get_prompt_template(query_type: str, domain_intent: str = None) -> str:
    key = (query_type, domain_intent) if domain_intent else (query_type, None)
    return PROMPT_TEMPLATES.get(key, DEFAULT_PREAMBLE)

def build_prompt(query: str, verified_facts: str, comparison_blocks: str,
                  top_edges: list[dict], hits: list[dict], query_type: str = "open_ended",
                  domain_intent: str = None, history_text: str = "",
                  trust_verified_facts: bool = False, total_token_budget: int = DEFAULT_TOKEN_BUDGET
                  ) -> tuple[str, int]:
    has_structured = bool(verified_facts or comparison_blocks or top_edges)

    import config
    if getattr(config, "ENABLE_TRIPLE_NOTATION", True):
        # Micro-notation triple compression: [REGIME] Subject:Rel(Object)
        graph_context_str = "\n".join(
            f"[GRAPH] {e.get('s', '')}:{e.get('rel', '')}({e.get('o', '')})"
            for e in top_edges
        )
    else:
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
    if trust_verified_facts:
        vector_budget = min(vector_budget, int(total_token_budget * 0.15))

    kept, used = [], 0
    for idx, h in enumerate(effective_hits):
        text = h.get('parent_text') or h.get('child_text') or ""
        cost = len(text) // 4
        rem_chars = (vector_budget - used) * 4
        if rem_chars <= 100 and idx >= 2:
            break
        if len(text) > rem_chars and idx >= 2:
            h = dict(h)
            h['parent_text'] = text[:rem_chars] + "..."
            cost = len(h['parent_text']) // 4
        else:
            h = dict(h)
            h['parent_text'] = text
        kept.append(h)
        used += cost
    effective_hits = kept

    vector_context = "\n\n---\n\n".join(
        f"[{i+1}] {h.get('product_name', 'Unknown Document')} p.{h.get('page_num', 1)}\n{h.get('parent_text', '')}"
        for i, h in enumerate(effective_hits))
    if len(vector_context) > 12000:
        vector_context = vector_context[:12000] + "\n...[truncated for token budget]"


    preamble = get_prompt_template(query_type, domain_intent)
    hist_block = f"{history_text}\n\n" if history_text else ""

    prompt = f"""{preamble}

{hist_block}{extra_sections}{graph_section}
DOCUMENT PROSE:
{vector_context}

QUESTION:
<user_query>
{query}
</user_query>

ANSWER:"""

    # ── output cap — richer answers get a bit more room, but still bounded ──
    max_output_tokens = 512 if not has_structured else 768
    return prompt, max_output_tokens