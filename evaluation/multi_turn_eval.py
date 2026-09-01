# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import sys, os, time, json
from pathlib import Path

STREAMLIT_APP = Path(r"c:\Users\Laptopadmin\Desktop\context-engineering\streamlit_app")
sys.path.insert(0, str(STREAMLIT_APP))
os.chdir(str(STREAMLIT_APP))

from dotenv import load_dotenv
load_dotenv()
import config, taxonomy_retrieval, intent_cache

print("Clearing intent cache for a fair test...")
intent_cache.clear_cache()

chain = [
    "What are some of the companies or subsidiaries that are part of Adani Enterprises Limited?",
    "Who are the key individuals associated with Mundra Solar PV Limited?",
    "Is Mundra Solar PV Limited a part of the Adani Group or Adani Enterprises?"
]

results = []
trad_history = []
graph_history = []

print("\nRunning Multi-Turn Comparison Chain...")
print("=" * 60)

for idx, q in enumerate(chain):
    print(f"\nTurn {idx+1}: {q}")
    
    # ── Traditional RAG
    t0 = time.perf_counter()
    trad = taxonomy_retrieval.traditional_rag_v2(q, history=trad_history.copy())
    trad_time = round((time.perf_counter() - t0)*1000, 1)
    
    trad_ans = trad.get('answer', '')
    trad_history.append({"role": "user", "content": q})
    trad_history.append({"role": "assistant", "content": trad_ans})
    
    trad_in = trad.get('input_tokens', 0)
    trad_out = trad.get('output_tokens', 0)
    
    # ── ContextGraph
    t1 = time.perf_counter()
    graph = taxonomy_retrieval.hybrid_graphrag_v2(q, history=graph_history.copy())
    graph_time = round((time.perf_counter() - t1)*1000, 1)
    
    g_ans = graph.get('answer', '')
    if isinstance(g_ans, dict): g_ans = g_ans.get('answer', '')
    
    graph_history.append({"role": "user", "content": q})
    graph_history.append({"role": "assistant", "content": g_ans})
    
    tele = graph.get('telemetry_breakdown', {})
    graph_in = tele.get('tokens_input', 0)
    graph_out = tele.get('tokens_output', 0)
    
    print(f"  Traditional RAG  : {trad_time}ms | {trad_in} in / {trad_out} out")
    print(f"    Answer: {trad_ans[:100].replace(chr(10), ' ')}...")
    print(f"  ContextGraph     : {graph_time}ms | {graph_in} in / {graph_out} out | Cache: {tele.get('cache_hit')}")
    print(f"    Answer: {str(g_ans)[:100].replace(chr(10), ' ')}...")
    
    results.append({
        "turn": idx + 1,
        "query": q,
        "traditional": {
            "time_ms": trad_time,
            "tokens_in": trad_in,
            "tokens_out": trad_out,
            "answer": trad_ans
        },
        "contextgraph": {
            "time_ms": graph_time,
            "tokens_in": graph_in,
            "tokens_out": graph_out,
            "cache_hit": tele.get('cache_hit'),
            "tokens_saved": tele.get('tokens_saved', 0),
            "answer": g_ans
        }
    })

out = Path(r"c:\Users\Laptopadmin\Desktop\context-engineering\evaluation\results\multi_turn_comparison.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"\nSaved metrics to {out}")
