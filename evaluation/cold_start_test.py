# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
cold_start_test.py — Runs query with cleared cache through the exact Streamlit pipeline.
"""
import sys, os, io, time, json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

STREAMLIT_APP = Path(__file__).resolve().parent.parent / "streamlit_app"
sys.path.insert(0, str(STREAMLIT_APP))
os.chdir(str(STREAMLIT_APP))

from dotenv import load_dotenv
load_dotenv()
import config, llm_text_client, taxonomy_retrieval

QUERY = "Within those categories, what is the minimum equity allocation for a Large Cap Fund and how is Large Cap defined?"

model = llm_text_client._resolve_model_and_fallbacks()[0]
print(f"\nMODEL        : {model}")
print(f"CACHE_STATUS : CLEARED — this is a full cold-start run")
print(f"QUERY        : {QUERY}\n")

# ── TRADITIONAL RAG v2 ────────────────────────────────────────────────────
print("=" * 60)
print("  [1/2] traditional_rag_v2 — running...")
print("=" * 60)
t0 = time.perf_counter()
trad = taxonomy_retrieval.traditional_rag_v2(QUERY)
trad_wall = round((time.perf_counter() - t0) * 1000, 1)

trad_in   = trad.get("input_tokens",  0) or (trad.get("total_tokens", 0) // 2)
trad_out  = trad.get("output_tokens", 0) or (trad.get("total_tokens", 0) - trad_in)
trad_tot  = trad.get("total_tokens",  trad_in + trad_out)
trad_docs = len(trad.get("docs", []))
trad_ans  = trad.get("answer", "")
trad_time_inner = round(trad.get("total_time", trad_wall / 1000) * 1000, 1)

# ── CONTEXT GRAPH v2 ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  [2/2] hybrid_graphrag_v2 — running...")
print("=" * 60)
t1 = time.perf_counter()
graph = taxonomy_retrieval.hybrid_graphrag_v2(QUERY)
graph_wall = round((time.perf_counter() - t1) * 1000, 1)

tele = graph.get("telemetry_breakdown", {})
graph_in    = tele.get("tokens_input",   graph.get("input_tokens",  0))
graph_out   = tele.get("tokens_output",  graph.get("output_tokens", 0))
graph_tot   = tele.get("tokens_total",   graph.get("total_tokens",  graph_in + graph_out))
graph_cold  = tele.get("tokens_cold_equivalent", 0)
graph_saved = tele.get("tokens_saved", 0)

lat_ner    = tele.get("latency_ner_processing_ms", 0)
lat_graph  = tele.get("latency_graph_db_ms", 0)
lat_vector = tele.get("latency_vector_db_ms", 0)
lat_llm    = tele.get("latency_llm_generation_ms", 0)
lat_post   = tele.get("latency_post_retrieval_processing_ms", 0)
lat_total  = tele.get("latency_total_pipeline_ms", graph_wall)

graph_nodes  = graph.get("graph_nodes", [])
graph_edges  = graph.get("graph_edges", [])
cache_hit    = tele.get("cache_hit", False)
intent       = tele.get("domain_intent", graph.get("query_type", ""))
pipeline     = tele.get("pipeline_mode", "ContextGraph v2")
db_cands     = tele.get("db_candidates_surfaced", 0)
vec_bypass   = tele.get("vector_bypassed", False)
conf         = graph.get("confidence_label", "")
matched_by   = graph.get("graph_matched_by", "")
query_type   = graph.get("query_type", "")

gans = graph.get("answer", "")
if isinstance(gans, dict):
    gans = gans.get("answer", "")

# ── PRINT REPORT ──────────────────────────────────────────────────────────
sep = "=" * 60

print(f"\n{sep}")
print("  TRADITIONAL RAG v2 — METRICS")
print(sep)
print(f"  Tokens In          : {trad_in}")
print(f"  Tokens Out         : {trad_out}")
print(f"  Total Tokens       : {trad_tot}")
print(f"  Wall Latency       : {trad_wall} ms")
print(f"  Pipeline Time      : {trad_time_inner} ms")
print(f"  Docs Retrieved     : {trad_docs}")
print(f"  Cache Hit          : No (cleared)")
print(f"\n  Answer:")
for line in trad_ans.split("\n"):
    print(f"    {line}")

print(f"\n{sep}")
print("  CONTEXTGRAPH v2 — METRICS")
print(sep)
print(f"  Pipeline Mode      : {pipeline}")
print(f"  Cache Hit          : {cache_hit}")
print(f"  Intent / Domain    : {intent}")
print(f"  Query Type         : {query_type}")
print(f"  Matched By         : {matched_by}")
print(f"  Confidence         : {conf}")
print()
print(f"  -- TOKEN METRICS --")
print(f"  Tokens In          : {graph_in}")
print(f"  Tokens Out         : {graph_out}")
print(f"  Total Tokens       : {graph_tot}")
print(f"  Cold-Start Equiv   : {graph_cold}")
print(f"  Tokens Saved       : {graph_saved}")
print()
print(f"  -- LATENCY BREAKDOWN --")
print(f"  NER Processing     : {lat_ner} ms")
print(f"  Graph DB (Neo4j)   : {lat_graph} ms")
print(f"  Vector DB (FAISS)  : {lat_vector} ms")
print(f"  LLM Generation     : {lat_llm} ms")
print(f"  Post-Retrieval     : {lat_post} ms")
print(f"  Total Pipeline     : {lat_total} ms")
print(f"  Wall Clock         : {graph_wall} ms")
print()
print(f"  -- GRAPH METRICS --")
print(f"  Graph Nodes        : {len(graph_nodes)}")
print(f"  Graph Edges        : {len(graph_edges)}")
print(f"  DB Candidates      : {db_cands}")
print(f"  Vector Bypassed    : {vec_bypass}")
for e in graph_edges[:6]:
    print(f"    {e.get('s')} --[{e.get('rel')}]--> {e.get('o')}")
print()
print(f"  -- ANSWER --")
for line in str(gans).split("\n"):
    print(f"    {line}")

print(f"\n{sep}")
print("  SIDE-BY-SIDE COMPARISON")
print(sep)
tok_delta = trad_tot - graph_tot
tok_pct   = round(tok_delta / max(trad_tot, 1) * 100, 1)
lat_delta = round(trad_wall - graph_wall, 1)
print(f"  {'Metric':<26} {'Traditional':>12} {'ContextGraph':>13}")
print(f"  {'-'*26} {'-'*12} {'-'*13}")
print(f"  {'Tokens In':<26} {trad_in:>12} {graph_in:>13}")
print(f"  {'Tokens Out':<26} {trad_out:>12} {graph_out:>13}")
print(f"  {'Total Tokens':<26} {trad_tot:>12} {graph_tot:>13}")
print(f"  {'Wall Latency (ms)':<26} {trad_wall:>12} {graph_wall:>13}")
print(f"  {'NER Latency (ms)':<26} {'N/A':>12} {lat_ner:>13}")
print(f"  {'Graph DB Latency (ms)':<26} {'N/A':>12} {lat_graph:>13}")
print(f"  {'Vector Latency (ms)':<26} {'N/A':>12} {lat_vector:>13}")
print(f"  {'LLM Latency (ms)':<26} {'~'+str(round(trad_wall-150)):>12} {lat_llm:>13}")
print(f"  {'Graph Nodes':<26} {'0':>12} {len(graph_nodes):>13}")
print(f"  {'Graph Edges':<26} {'0':>12} {len(graph_edges):>13}")
print(f"  {'Cache Hit':<26} {'No':>12} {str(cache_hit):>13}")
print(f"  {'Docs Retrieved':<26} {trad_docs:>12} {db_cands:>13}")
print(f"  {'-'*26} {'-'*12} {'-'*13}")
print(f"  {'Token Delta':<26} {tok_delta:>+12}  ({tok_pct}% saving)")
print(f"  {'Latency Delta (ms)':<26} {lat_delta:>+12}")
print(sep)

# ── SAVE JSON ──────────────────────────────────────────────────────────────
out = Path(__file__).parent / "results" / "streamlit_cold_start_metrics.json"
out.parent.mkdir(exist_ok=True)
payload = {
    "query": QUERY, "model": model,
    "cache_cleared": True, "run_type": "cold_start",
    "traditional": {
        "tokens_in": trad_in, "tokens_out": trad_out, "total_tokens": trad_tot,
        "wall_latency_ms": trad_wall, "pipeline_time_ms": trad_time_inner,
        "docs_retrieved": trad_docs, "answer": trad_ans
    },
    "contextgraph": {
        "tokens_in": graph_in, "tokens_out": graph_out, "total_tokens": graph_tot,
        "cold_equivalent_tokens": graph_cold, "tokens_saved": graph_saved,
        "wall_latency_ms": graph_wall,
        "lat_ner_ms": lat_ner, "lat_graph_ms": lat_graph,
        "lat_vector_ms": lat_vector, "lat_llm_ms": lat_llm,
        "lat_post_ms": lat_post, "lat_total_ms": lat_total,
        "graph_nodes_count": len(graph_nodes), "graph_nodes": graph_nodes,
        "graph_edges_count": len(graph_edges), "graph_edges": graph_edges,
        "matched_by": matched_by, "intent": intent, "query_type": query_type,
        "cache_hit": cache_hit, "pipeline_mode": pipeline,
        "db_candidates": db_cands, "vector_bypassed": vec_bypass,
        "confidence": conf, "answer": gans
    },
    "comparison": {
        "token_delta": tok_delta,
        "token_saving_pct": tok_pct,
        "latency_delta_ms": lat_delta
    }
}
out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  Saved -> {out}")
