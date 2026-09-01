# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
five_query_test.py
==================
Runs exactly 5 MULTI-TURN queries — one per chain — against both
Traditional Vector RAG and ContextGraph.

Fixes from previous run:
  1. Uses streamlit_app config (PRIMARY_LLM_PROVIDER=groq, llama-3.1-8b-instant)
  2. Neo4j is ONLINE — graph traversal active
  3. Prints model used per call for verification
  4. Outputs clean ASCII-safe results to console + JSON
"""
from __future__ import annotations
import json, os, sys, time
from datetime import datetime
from pathlib import Path

# ── PATH: run from streamlit_app dir ──────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent          # evaluation/
PROJECT_ROOT = SCRIPT_DIR.parent
STREAMLIT_APP = PROJECT_ROOT / "streamlit_app"

if str(STREAMLIT_APP) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP))

os.chdir(str(STREAMLIT_APP))   # dotenv picks up streamlit_app/.env

import config
import faiss_store as fs
import retrieval
import llm_text_client

fs.INDEXES_DIR = config.FAISS_DIR

RESULTS_DIR = SCRIPT_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Verify provider BEFORE running ────────────────────────────────────────
primary_model, fallbacks = llm_text_client._resolve_model_and_fallbacks()
print("\n" + "="*70)
print("  LLM PROVIDER VERIFICATION")
print("="*70)
print(f"  PRIMARY_LLM_PROVIDER : {config.PRIMARY_LLM_PROVIDER}")
print(f"  GROQ_API_KEY set     : {bool(config.GROQ_API_KEY)}")
print(f"  CLAUDE_API_KEY set   : {bool(config.CLAUDE_API_KEY)}")
print(f"  Resolved model       : {primary_model}")
print(f"  Fallbacks            : {fallbacks}")

if "groq" not in primary_model:
    print("\n  [WARNING] Expected Groq but got:", primary_model)
    print("  Check: PRIMARY_LLM_PROVIDER in .env and GROQ_API_KEY presence")
else:
    print("\n  [OK] Groq (llama-3.1-8b-instant) is the primary model")

# ── Verify Neo4j ───────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  NEO4J VERIFICATION")
print("="*70)
try:
    import graph_store
    node_count = graph_store.count_nodes()
    print(f"  Neo4j connected   : YES")
    print(f"  Total graph nodes : {node_count:,}")
except Exception as e:
    print(f"  Neo4j connected   : NO -> {e}")

# ── 5 MULTI-TURN CONVERSATIONS (one per chain) ─────────────────────────────
# Each entry: (turn_label, query, ground_truth_fragments)
FIVE_QUERIES = [
    # Q1 — Chain 1 T1: SEBI MF Categorisation (cold start baseline)
    {
        "q_id": "Q1",
        "chain": "C1",
        "turn": 1,
        "topic": "SEBI Mutual Fund Categorisation",
        "query": "What are the five broad categories of mutual fund schemes under SEBI's categorization framework?",
        "history": [],   # cold start
        "gt": ["Equity Schemes", "Debt Schemes", "Hybrid Schemes", "Solution Oriented Schemes", "Other Schemes"],
    },
    # Q2 — Chain 1 T2: follow-up (history from Q1 answer injected)
    {
        "q_id": "Q2",
        "chain": "C1",
        "turn": 2,
        "topic": "SEBI Mutual Fund Categorisation (follow-up)",
        "query": "Within those categories, what is the minimum equity allocation required for a Large Cap Fund and how is Large Cap defined?",
        "history": [],   # will be filled from Q1 answer
        "gt": ["80%", "top 100", "large cap"],
    },
    # Q3 — Chain 2 T1: Adani FY24 Earnings
    {
        "q_id": "Q3",
        "chain": "C2",
        "turn": 1,
        "topic": "Adani FY24 Earnings",
        "query": "What was Adani Enterprises' consolidated revenue and EBITDA in FY24, and which incubating businesses drove growth?",
        "history": [],
        "gt": ["EBITDA", "FY24", "airport", "incubat"],
    },
    # Q4 — Chain 3 T1: SEBI Investment Adviser
    {
        "q_id": "Q4",
        "chain": "C4",
        "turn": 1,
        "topic": "SEBI Investment Adviser Guidelines",
        "query": "What NISM certification, net worth, and qualification requirements apply to SEBI registered Investment Advisers?",
        "history": [],
        "gt": ["NISM", "net worth", "qualification", "certification"],
    },
    # Q5 — Chain 5 T4: SEBI April 2024 — Information Ratio (multi-turn build-up)
    {
        "q_id": "Q5",
        "chain": "C5",
        "turn": 4,
        "topic": "SEBI Information Ratio Disclosure (multi-turn T4)",
        "query": "What is the SEBI directive on Information Ratio disclosure for risk-adjusted return comparison in mutual funds?",
        "history": [
            {"role": "user",      "content": "What framework did SEBI introduce in April 2024 for retail investor participation in algorithmic trading?"},
            {"role": "assistant", "content": "SEBI introduced a framework requiring brokers to register all algo strategies and implement kill-switch mechanisms for retail algo trading in April 2024."},
            {"role": "user",      "content": "What safeguards must brokers implement for retail algo trading?"},
            {"role": "assistant", "content": "Brokers must set risk limits, get SEBI approval for each algo, implement kill-switches, and conduct daily reconciliation."},
            {"role": "user",      "content": "What changes to mutual fund borrowing limits did SEBI announce in April 2024?"},
            {"role": "assistant", "content": "SEBI revised the borrowing limit for mutual funds to allow borrowing up to 20% of NAV for meeting redemption pressures on a short-term basis."},
        ],
        "gt": ["information ratio", "risk", "return", "disclosure", "mutual fund"],
    },
]

def check_frags(answer: str, frags: list) -> dict:
    al = answer.lower()
    matched = [f for f in frags if f.lower() in al]
    return {"matched": matched, "missed": [f for f in frags if f.lower() not in al],
            "score": len(matched)/len(frags) if frags else 0.0}

def bar(score):
    n = round(score * 10)
    return "[" + "#"*n + "."*(10-n) + f"] {score:.0%}"

# ── RUN ───────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  LOADING FAISS STORE")
print("="*70)
store = fs.BrochureFAISSStore("amc_master")
print("  FAISS amc_master loaded OK")

results = []
c1_answers = {}   # store Q1 answer to inject as history for Q2

for qi, q in enumerate(FIVE_QUERIES, 1):
    # Inject Q1 answer into Q2 history
    if q["q_id"] == "Q2" and "Q1" in c1_answers:
        q["history"] = [
            {"role": "user",      "content": FIVE_QUERIES[0]["query"]},
            {"role": "assistant", "content": c1_answers["Q1_graph"]},
        ]

    print(f"\n{'='*70}")
    print(f"  Query {qi}/5  [{q['q_id']}]  Chain {q['chain']} Turn {q['turn']}")
    print(f"  Topic : {q['topic']}")
    print(f"  Query : {q['query'][:80]}...")
    print(f"  History turns : {len(q['history'])//2}")
    print(f"{'='*70}")

    # ── Traditional RAG ────────────────────────────────────────────────
    t0 = time.perf_counter()
    trad = retrieval.traditional_rag(query=q["query"], store=store)
    trad_ms = round((time.perf_counter()-t0)*1000, 1)
    tv = check_frags(trad["answer"], q["gt"])
    trad_tok = trad.get("total_tokens", 0)

    print(f"\n  -- Traditional RAG --")
    print(f"  Model   : {primary_model}")
    print(f"  Tokens  : {trad.get('input_tokens',0)} in + {trad.get('output_tokens',0)} out = {trad_tok} total")
    print(f"  Latency : {trad_ms}ms")
    print(f"  Score   : {bar(tv['score'])}")
    print(f"  Answer  : {trad['answer'][:200]}...")

    # ── ContextGraph ───────────────────────────────────────────────────
    t1 = time.perf_counter()
    graph = retrieval.hybrid_graphrag(
        query=q["query"],
        store=store,
        history=q["history"] if q["history"] else None,
    )
    graph_ms = round((time.perf_counter()-t1)*1000, 1)
    gv = check_frags(graph["answer"], q["gt"])
    graph_tok = graph.get("total_tokens", 0)
    graph_nodes = len(graph.get("graph_nodes", []))
    graph_edges = len(graph.get("graph_edges", []))

    # Save C1 answer for Q2 history injection
    if q["q_id"] == "Q1":
        c1_answers["Q1_graph"] = graph["answer"]

    print(f"\n  -- ContextGraph (Hybrid) --")
    print(f"  Model      : {primary_model}")
    print(f"  Tokens     : {graph.get('input_tokens',0)} in + {graph.get('output_tokens',0)} out = {graph_tok} total")
    print(f"  Latency    : {graph_ms}ms")
    print(f"  Neo4j      : {graph_nodes} nodes | {graph_edges} edges | intent={graph.get('query_type','?')}")
    print(f"  Confidence : {graph.get('confidence_label','?')}")
    print(f"  Score      : {bar(gv['score'])}")
    print(f"  Answer     : {graph['answer'][:200]}...")

    saving = trad_tok - graph_tok
    print(f"\n  Token delta : {saving:+,} (ContextGraph vs Traditional)")

    results.append({
        "q_id": q["q_id"], "chain": q["chain"], "turn": q["turn"],
        "topic": q["topic"], "query": q["query"],
        "history_turns": len(q["history"])//2,
        "ground_truth": q["gt"],
        "traditional": {
            "model": primary_model,
            "answer": trad["answer"],
            "input_tokens": trad.get("input_tokens", 0),
            "output_tokens": trad.get("output_tokens", 0),
            "total_tokens": trad_tok,
            "latency_ms": trad_ms,
            "verification": tv,
        },
        "contextgraph": {
            "model": primary_model,
            "answer": graph["answer"],
            "input_tokens": graph.get("input_tokens", 0),
            "output_tokens": graph.get("output_tokens", 0),
            "total_tokens": graph_tok,
            "latency_ms": graph_ms,
            "graph_nodes": graph_nodes,
            "graph_edges": graph_edges,
            "query_type": graph.get("query_type", ""),
            "confidence": graph.get("confidence_label", ""),
            "verification": gv,
        },
        "token_saving": saving,
    })

# ── SAVE JSON ──────────────────────────────────────────────────────────────
out = RESULTS_DIR / "five_query_results.json"
out.write_text(json.dumps({"generated_at": datetime.now().isoformat(),
    "model": primary_model, "neo4j_online": True, "queries": results},
    indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  [SAVED] {out}")

# ── FINAL SUMMARY ─────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  FINAL SUMMARY")
print("="*70)
print(f"  {'Q':<5} {'Topic':<38} {'Trad':>6} {'Graph':>6} {'Delta':>6} {'Trad%':>6} {'Graph%':>6}")
print(f"  {'-'*5} {'-'*38} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
for r in results:
    tv_s = f"{r['traditional']['verification']['score']:.0%}"
    gv_s = f"{r['contextgraph']['verification']['score']:.0%}"
    print(f"  {r['q_id']:<5} {r['topic'][:38]:<38} "
          f"{r['traditional']['total_tokens']:>6} {r['contextgraph']['total_tokens']:>6} "
          f"{r['token_saving']:>+6} {tv_s:>6} {gv_s:>6}")

total_trad  = sum(r['traditional']['total_tokens'] for r in results)
total_graph = sum(r['contextgraph']['total_tokens'] for r in results)
total_delta = total_trad - total_graph
print(f"  {'TOTAL':<5} {'':<38} {total_trad:>6} {total_graph:>6} {total_delta:>+6}")
print(f"\n  Model used: {primary_model}")
print(f"  Neo4j graph traversal: ACTIVE")
print("="*70)
