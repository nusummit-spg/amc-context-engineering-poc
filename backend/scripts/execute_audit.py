# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.multiturn_taxonomy_query import load_taxonomy_index, retrieve_vector, retrieve_graph, build_traditional_prompt, build_hybrid_prompt, call_llm, _graph_context_to_text

queries = [
    "Given that FoFs now have these detailed sub-categories, what happens if an AMC wants to launch a new Sectoral or Thematic scheme under the 2026 rules? Are they subject to any portfolio overlap limits?",
    "You mentioned the 50% overlap limit for Sectoral/Thematic schemes. Does this 50% cap apply to large cap funds as well, or is there an exception?",
    "How exactly is this 50% portfolio overlap calculated? Is it based on daily or quarterly weightages?",
    "If an existing thematic fund is currently at 70% overlap, what is the timeline and glide path for them to become compliant with the 50% limit?",
    "What happens to the existing thematic fund if they fail to meet the 50% overlap criteria at the end of the 3-year transition period?",
    "Are there any specific borrowing limits or intraday borrowing restrictions for these thematic funds as they try to realign their portfolios?"
]

def format_auditor(hyb_ans, trad_ans):
    # Ask Groq to be the auditor
    prompt = f"""You are a strict AMC Data Architecture Expert auditor. 
Evaluate these two RAG system responses to the query. 
Determine PASS/FAIL for each, and write a 3-sentence strict analysis comparing them.

Traditional Response: {trad_ans}
Hybrid Graph Response: {hyb_ans}

Format your output exactly like this:
Verdict: ✅ PASS (Hybrid System) / ❌ FAIL (Traditional System)
Analysis: [Analysis text]
"""
    return call_llm(prompt)

def run():
    index, chunks = load_taxonomy_index()
    history = [
        {"role": "user", "content": "How does the 2026 SEBI circular change the categorization of Solution Oriented Schemes and the 'Other Schemes' section?"},
        {"role": "assistant", "content": "Solution Oriented Schemes have been discontinued outright. The 'Other Schemes' section collapsed from 13 legacy subtypes to 2: Index Funds/ETFs and FoFs (Overseas/Domestic)."},
        {"role": "user", "content": "Since 'Other Schemes' collapsed into Index Funds and FoFs, what happened to the 'FoF Domestic' category? Is it officially recognized in the 2026 circular, or is it still an undocumented gap like it was in the 2017 rules?"},
        {"role": "assistant", "content": "It is officially recognized. A separate, much richer sub-categorization applies ONLY to FoFs with multiple underlying funds (Annexure C), splitting them into Equity, Debt, Hybrid, and Commodity-based FoFs."}
    ]
    
    results = []
    
    for i, q in enumerate(queries):
        print(f"Running Turn {i+3}...", flush=True)
        # Traditional
        trad_chunks = retrieve_vector(q, index, chunks, top_k=5)
        trad_prompt = build_traditional_prompt(q, history, trad_chunks)
        trad_ans = call_llm(trad_prompt)
        
        # Hybrid
        hyb_chunks = retrieve_vector(q, index, chunks, top_k=3)
        graph_ctx = retrieve_graph(q)
        hyb_prompt = build_hybrid_prompt(q, history, hyb_chunks, graph_ctx)
        hyb_ans = call_llm(hyb_prompt)
        
        # Auditor
        auditor_eval = format_auditor(hyb_ans, trad_ans)
        
        turn_data = {
            "turn": i+3,
            "query": q,
            "trad_ans": trad_ans,
            "hyb_ans": hyb_ans,
            "auditor": auditor_eval,
            "graph_facts": _graph_context_to_text(graph_ctx).split("\n")
        }
        results.append(turn_data)
        
        # Update history
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": hyb_ans}) # History follows the successful hybrid path
        
    Path("audit_results.json").write_text(json.dumps(results, indent=2))
    print("Done!")

if __name__ == "__main__":
    run()
