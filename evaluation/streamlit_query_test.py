# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
streamlit_query_test.py
========================
Runs a single query through EXACTLY the same code path Streamlit uses:
  - taxonomy_retrieval.traditional_rag_v2()
  - taxonomy_retrieval.hybrid_graphrag_v2()
Captures every available metric from both pipelines.
"""
import sys, os, time, json
from pathlib import Path

STREAMLIT_APP = Path(__file__).resolve().parent.parent / "streamlit_app"
sys.path.insert(0, str(STREAMLIT_APP))
os.chdir(str(STREAMLIT_APP))

from dotenv import load_dotenv
load_dotenv()

import config
import llm_text_client
import taxonomy_retrieval

QUERY = "Within those categories, what is the minimum equity allocation for a Large Cap Fund and how is Large Cap defined?"

print("\n" + "="*72)
print("  STREAMLIT PIPELINE QUERY TEST")
print("  Using: taxonomy_retrieval.traditional_rag_v2 + hybrid_graphrag_v2")
print("="*72)
print(f"  Model    : {llm_text_client._resolve_model_and_fallbacks()[0]}")
print(f"  Query    : {QUERY}")
print("="*72)

# ─────────────────────────────────────────────────────────────
# TRADITIONAL RAG V2
# ─────────────────────────────────────────────────────────────
print("\n[1/2] Running Traditional RAG v2 ...")
t0 = time.perf_counter()
trad = taxonomy_retrieval.traditional_rag_v2(QUERY)
trad_wall = round((time.perf_counter() - t0) * 1000, 1)

trad_in  = trad.get("input_tokens",  trad.get("total_tokens", 0) // 2)
trad_out = trad.get("output_tokens", trad.get("total_tokens", 0) - trad_in)
trad_tot = trad.get("total_tokens",  trad_in + trad_out)
trad_time = trad.get("total_time", trad_wall / 1000)

print(f"  Done in {trad_wall}ms")

# ─────────────────────────────────────────────────────────────
# CONTEXT GRAPH V2
# ─────────────────────────────────────────────────────────────
print("\n[2/2] Running ContextGraph v2 (hybrid_graphrag_v2) ...")
t1 = time.perf_counter()
graph = taxonomy_retrieval.hybrid_graphrag_v2(QUERY)
graph_wall = round((time.perf_counter() - t1) * 1000, 1)

tele = graph.get("telemetry_breakdown", {})
graph_in  = tele.get("tokens_input",  graph.get("input_tokens",  0))
graph_out = tele.get("tokens_output", graph.get("output_tokens", 0))
graph_tot = tele.get("tokens_total",  graph.get("total_tokens",  graph_in + graph_out))
graph_cold= tele.get("tokens_cold_equivalent", 0)
graph_saved = tele.get("tokens_saved", 0)
graph_time  = graph.get("total_time", graph_wall / 1000)

lat_ner    = tele.get("latency_ner_processing_ms",      0)
lat_graph  = tele.get("latency_graph_db_ms",            0)
lat_vector = tele.get("latency_vector_db_ms",           0)
lat_llm    = tele.get("latency_llm_generation_ms",      0)
lat_post   = tele.get("latency_post_retrieval_processing_ms", 0)
lat_total  = tele.get("latency_total_pipeline_ms",      graph_wall)

graph_nodes = graph.get("graph_nodes", [])
graph_edges = graph.get("graph_edges", [])
intent = tele.get("domain_intent", graph.get("query_type", ""))
cache_hit   = tele.get("cache_hit", False)
pipeline_mode = tele.get("pipeline_mode", "ContextGraph v2")
vec_bypassed  = tele.get("vector_bypassed", False)
db_candidates = tele.get("db_candidates_surfaced", 0)

print(f"  Done in {graph_wall}ms")

# ─────────────────────────────────────────────────────────────
# PRINT FULL REPORT
# ─────────────────────────────────────────────────────────────
print("\n" + "="*72)
print("  TRADITIONAL RAG v2 — FULL METRICS")
print("="*72)
print(f"  Tokens In       : {trad_in}")
print(f"  Tokens Out      : {trad_out}")
print(f"  Total Tokens    : {trad_tot}")
print(f"  Wall Latency    : {trad_wall}ms")
print(f"  Pipeline Time   : {round(trad_time*1000,1)}ms")
print(f"  Docs Retrieved  : {len(trad.get('docs', []))}")
print(f"\n  Answer:")
ans = trad.get("answer", "")
for line in ans.split("\n"):
    print(f"    {line}")

print("\n" + "="*72)
print("  CONTEXTGRAPH v2 — FULL METRICS")
print("="*72)
print(f"  Pipeline Mode   : {pipeline_mode}")
print(f"  Cache Hit       : {cache_hit}")
print(f"  Intent / Domain : {intent}")
print(f"  Confidence      : {graph.get('confidence_label', '?')}")
print()
print(f"  --- TOKEN METRICS ---")
print(f"  Tokens In            : {graph_in}")
print(f"  Tokens Out           : {graph_out}")
print(f"  Total Tokens         : {graph_tot}")
print(f"  Cold-Start Equiv     : {graph_cold}  (what it WOULD cost w/o cache)")
print(f"  Tokens Saved (cache) : {graph_saved}")
print()
print(f"  --- LATENCY BREAKDOWN ---")
print(f"  NER Processing      : {lat_ner}ms")
print(f"  Graph DB (Neo4j)    : {lat_graph}ms")
print(f"  Vector DB (FAISS)   : {lat_vector}ms")
print(f"  LLM Generation      : {lat_llm}ms")
print(f"  Post-Retrieval      : {lat_post}ms")
print(f"  Total Pipeline      : {lat_total}ms")
print(f"  Wall Clock          : {graph_wall}ms")
print()
print(f"  --- GRAPH METRICS ---")
print(f"  Graph Nodes         : {len(graph_nodes)} -> {graph_nodes[:5]}")
print(f"  Graph Edges         : {len(graph_edges)}")
print(f"  Matched By          : {graph.get('graph_matched_by', 'none')}")
print(f"  DB Candidates       : {db_candidates}")
print(f"  Vector Bypassed     : {vec_bypassed}")
for e in graph_edges[:5]:
    print(f"    Edge: {e.get('s')} --[{e.get('rel')}]--> {e.get('o')}")
print()
print(f"  --- ANSWER ---")
gans = graph.get("answer", {})
if isinstance(gans, dict):
    gans = gans.get("answer", "")
for line in str(gans).split("\n"):
    print(f"    {line}")

# ─────────────────────────────────────────────────────────────
# COMPARISON TABLE
# ─────────────────────────────────────────────────────────────
print("\n" + "="*72)
print("  SIDE-BY-SIDE COMPARISON")
print("="*72)
print(f"  {'Metric':<28} {'Traditional':>14} {'ContextGraph':>14}")
print(f"  {'-'*28} {'-'*14} {'-'*14}")
print(f"  {'Tokens In':<28} {trad_in:>14} {graph_in:>14}")
print(f"  {'Tokens Out':<28} {trad_out:>14} {graph_out:>14}")
print(f"  {'Total Tokens':<28} {trad_tot:>14} {graph_tot:>14}")
print(f"  {'Wall Latency (ms)':<28} {trad_wall:>14} {graph_wall:>14}")
print(f"  {'LLM Latency (ms)':<28} {'N/A':>14} {lat_llm:>14}")
print(f"  {'Graph Nodes':<28} {'0':>14} {len(graph_nodes):>14}")
print(f"  {'Cache Hit':<28} {'No':>14} {str(cache_hit):>14}")
print(f"  {'Docs / Chunks':<28} {len(trad.get('docs',[])):>14} {db_candidates:>14}")

token_delta = trad_tot - graph_tot
lat_delta   = round(trad_wall - graph_wall, 1)
print(f"  {'-'*28} {'-'*14} {'-'*14}")
print(f"  {'Token Delta (Trad - Graph)':<28} {token_delta:>+14}")
print(f"  {'Latency Delta (ms)':<28} {lat_delta:>+14}")
print("="*72)

# ─────────────────────────────────────────────────────────────
# SAVE JSON
# ─────────────────────────────────────────────────────────────
out_path = Path(__file__).parent / "results" / "streamlit_query_metrics.json"
out_path.parent.mkdir(exist_ok=True)
payload = {
    "query": QUERY,
    "model": llm_text_client._resolve_model_and_fallbacks()[0],
    "traditional": {
        "tokens_in": trad_in, "tokens_out": trad_out, "total_tokens": trad_tot,
        "wall_latency_ms": trad_wall, "pipeline_time_ms": round(trad_time*1000,1),
        "docs_retrieved": len(trad.get("docs",[])),
        "answer": trad.get("answer",""),
    },
    "contextgraph": {
        "tokens_in": graph_in, "tokens_out": graph_out, "total_tokens": graph_tot,
        "cold_equivalent_tokens": graph_cold, "tokens_saved": graph_saved,
        "wall_latency_ms": graph_wall,
        "latency_ner_ms": lat_ner, "latency_graph_ms": lat_graph,
        "latency_vector_ms": lat_vector, "latency_llm_ms": lat_llm,
        "latency_post_ms": lat_post, "latency_total_ms": lat_total,
        "graph_nodes": graph_nodes, "graph_edges": graph_edges,
        "graph_matched_by": graph.get("graph_matched_by",""),
        "intent": intent, "cache_hit": cache_hit,
        "pipeline_mode": pipeline_mode, "db_candidates": db_candidates,
        "confidence": graph.get("confidence_label",""),
        "answer": str(gans),
    },
    "comparison": {
        "token_delta": token_delta,
        "latency_delta_ms": lat_delta,
    }
}
out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  Saved -> {out_path}")
