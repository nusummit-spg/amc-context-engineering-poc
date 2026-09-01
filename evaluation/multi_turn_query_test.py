# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
multi_turn_query_test.py
========================
Runs 5 multi-turn conversation chains across BOTH Traditional Vector RAG and
ContextGraph pipelines.

For each turn it records:
  - Answer text
  - input_tokens / output_tokens / total_tokens
  - Cumulative token savings (ContextGraph vs Traditional)

Then validates each ContextGraph answer against a set of expected
ground-truth fragments drawn directly from the selected source documents:
  • Categorization and Rationalization of Mutual Fund Schemes.pdf
  • AEL_Earnings_Call_Q4_FY24.pdf
  • Adani_Portfolio_H1FY25_ESG.pdf
  • April 2024.pdf  (SEBI monthly bulletin)
  • Guidelines for Investment Advisers.pdf

Usage:
    cd C:\\Users\\Laptopadmin\\Desktop\\context-engineering\\streamlit_app
    python ..\evaluation\\multi_turn_query_test.py

The script writes results to:
    evaluation/results/multi_turn_results.json   (machine-readable)
    evaluation/results/multi_turn_report.md      (human-readable)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# PATH BOOTSTRAP — add streamlit_app to sys.path so we can import its modules
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent          # evaluation/
PROJECT_ROOT = SCRIPT_DIR.parent                       # context-engineering/
STREAMLIT_APP = PROJECT_ROOT / "streamlit_app"

if str(STREAMLIT_APP) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_APP))

# ---------------------------------------------------------------------------
# Now import the project's own modules (config / retrieval / faiss_store)
# ---------------------------------------------------------------------------
os.chdir(str(STREAMLIT_APP))   # config.py resolves relative paths from CWD

import config                            # noqa: E402
import faiss_store as fs                 # noqa: E402
import retrieval                         # noqa: E402

# Ensure FAISS store uses the right index directory
fs.INDEXES_DIR = config.FAISS_DIR

# ---------------------------------------------------------------------------
# RESULTS OUTPUT DIR
# ---------------------------------------------------------------------------
RESULTS_DIR = SCRIPT_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 5 MULTI-TURN CONVERSATION CHAINS
# Each chain has a "topic" and 4 turns that build on each other.
# Ground-truth fragments are pulled from the actual PDFs.
# ---------------------------------------------------------------------------
CHAINS = [
    # ── Chain 1: SEBI Mutual Fund Categorisation ──────────────────────────
    {
        "chain_id": "C1",
        "topic": "SEBI Mutual Fund Categorisation & Scheme Definitions",
        "source_doc": "Categorization and Rationalization of Mutual Fund Schemes.pdf",
        "turns": [
            {
                "turn": 1,
                "query": "What are the five broad categories of mutual fund schemes under SEBI's categorization framework?",
                "ground_truth_fragments": [
                    "Equity Schemes",
                    "Debt Schemes",
                    "Hybrid Schemes",
                    "Solution Oriented Schemes",
                    "Other Schemes",
                ],
            },
            {
                "turn": 2,
                "query": "Within those categories, how many sub-types fall under Equity Schemes?",
                "ground_truth_fragments": [
                    "large cap",
                    "mid cap",
                    "small cap",
                    "multi cap",
                    "ELSS",
                ],
            },
            {
                "turn": 3,
                "query": "What is the minimum equity allocation required for a Large Cap Fund and how is Large Cap defined?",
                "ground_truth_fragments": [
                    "80%",
                    "top 100",
                    "full market capitalisation",
                ],
            },
            {
                "turn": 4,
                "query": "How does a Multi Cap Fund's allocation mandate differ from a Flexi Cap Fund?",
                "ground_truth_fragments": [
                    "25%",
                    "large cap",
                    "mid cap",
                    "small cap",
                    "flexi",
                    "minimum",
                ],
            },
        ],
    },

    # ── Chain 2: AEL FY24 Earnings & Financial Performance ────────────────
    {
        "chain_id": "C2",
        "topic": "Adani Enterprises FY24 Earnings Call & Financial Performance",
        "source_doc": "AEL_Earnings_Call_Q4_FY24.pdf",
        "turns": [
            {
                "turn": 1,
                "query": "What was Adani Enterprises' consolidated revenue and EBITDA in FY24?",
                "ground_truth_fragments": [
                    "96,421",
                    "13,237",
                    "EBITDA",
                    "FY24",
                ],
            },
            {
                "turn": 2,
                "query": "Which incubating businesses drove EBITDA growth in FY24?",
                "ground_truth_fragments": [
                    "airport",
                    "roads",
                    "new industries",
                    "incubat",
                ],
            },
            {
                "turn": 3,
                "query": "What were the key capital expenditure highlights for green hydrogen?",
                "ground_truth_fragments": [
                    "green hydrogen",
                    "ANIL",
                    "Navi Mumbai",
                ],
            },
            {
                "turn": 4,
                "query": "What is the debt-to-EBITDA or leverage position of Adani Enterprises as discussed in the earnings call?",
                "ground_truth_fragments": [
                    "debt",
                    "EBITDA",
                    "leverage",
                ],
            },
        ],
    },

    # ── Chain 3: Adani ESG Sustainability ─────────────────────────────────
    {
        "chain_id": "C3",
        "topic": "Adani Portfolio ESG & Sustainability Targets (H1 FY25)",
        "source_doc": "Adani_Portfolio_H1FY25_ESG.pdf",
        "turns": [
            {
                "turn": 1,
                "query": "What are Adani Portfolio's key ESG and decarbonization targets for 2030?",
                "ground_truth_fragments": [
                    "net-zero",
                    "45 GW",
                    "renewable",
                    "Khavda",
                    "airport",
                ],
            },
            {
                "turn": 2,
                "query": "What credit ratings does Adani Portfolio maintain across its entities?",
                "ground_truth_fragments": [
                    "AA",
                    "CRISIL",
                    "ICRA",
                    "CARE",
                    "stable",
                ],
            },
            {
                "turn": 3,
                "query": "What water and waste sustainability initiatives are part of the ESG deck?",
                "ground_truth_fragments": [
                    "water",
                    "waste",
                    "landfill",
                    "plastic",
                ],
            },
            {
                "turn": 4,
                "query": "How does Adani's safety leadership framework feature in their ESG commitments?",
                "ground_truth_fragments": [
                    "safety",
                    "million trees",
                ],
            },
        ],
    },

    # ── Chain 4: SEBI Investment Adviser Guidelines ───────────────────────
    {
        "chain_id": "C4",
        "topic": "SEBI Guidelines for Investment Advisers",
        "source_doc": "Guidelines for Investment Advisers.pdf",
        "turns": [
            {
                "turn": 1,
                "query": "What are the eligibility and qualification requirements for becoming a SEBI registered Investment Adviser?",
                "ground_truth_fragments": [
                    "net worth",
                    "professional",
                    "NISM",
                    "certification",
                    "qualification",
                ],
            },
            {
                "turn": 2,
                "query": "What are the KYC and client onboarding obligations for Investment Advisers?",
                "ground_truth_fragments": [
                    "KYC",
                    "risk profile",
                    "suitability",
                    "client",
                    "onboard",
                ],
            },
            {
                "turn": 3,
                "query": "How are fee structures and advisory charges regulated for Investment Advisers?",
                "ground_truth_fragments": [
                    "fee",
                    "charges",
                    "advisory",
                    "AUM",
                    "flat",
                ],
            },
            {
                "turn": 4,
                "query": "What compliance and reporting obligations must Investment Advisers fulfil with SEBI?",
                "ground_truth_fragments": [
                    "compliance",
                    "report",
                    "annual",
                    "audit",
                    "SEBI",
                ],
            },
        ],
    },

    # ── Chain 5: SEBI April 2024 Circular — Algo Trading & Mutual Funds ──
    {
        "chain_id": "C5",
        "topic": "SEBI April 2024 Circular — Retail Algo Trading & Mutual Fund Changes",
        "source_doc": "April 2024.pdf",
        "turns": [
            {
                "turn": 1,
                "query": "What new framework did SEBI introduce in April 2024 for retail investor participation in algorithmic trading?",
                "ground_truth_fragments": [
                    "algo",
                    "retail",
                    "broker",
                    "algorithm",
                ],
            },
            {
                "turn": 2,
                "query": "What safeguards must brokers implement to protect retail investors in algo trading?",
                "ground_truth_fragments": [
                    "broker",
                    "safeguard",
                    "risk",
                    "limit",
                    "approval",
                ],
            },
            {
                "turn": 3,
                "query": "What changes to mutual fund borrowing limits were announced in SEBI's April 2024 circulars?",
                "ground_truth_fragments": [
                    "borrow",
                    "mutual fund",
                    "limit",
                    "NAV",
                ],
            },
            {
                "turn": 4,
                "query": "What was the SEBI circular about risk-adjusted return disclosure — specifically the Information Ratio — for mutual funds?",
                "ground_truth_fragments": [
                    "information ratio",
                    "risk",
                    "return",
                    "disclosure",
                ],
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _contains_fragments(answer: str, fragments: list[str]) -> dict:
    """Check how many ground-truth fragments appear in the answer (case-insensitive)."""
    answer_lower = answer.lower()
    hits = [f for f in fragments if f.lower() in answer_lower]
    return {
        "matched": hits,
        "missed":  [f for f in fragments if f.lower() not in answer_lower],
        "score":   len(hits) / len(fragments) if fragments else 0.0,
    }


def _run_chain(chain: dict, store) -> dict:
    """Execute all turns in a chain for both Traditional and ContextGraph modes."""
    chain_id = chain["chain_id"]
    topic = chain["topic"]
    print(f"\n{'='*70}")
    print(f"  Chain {chain_id}: {topic}")
    print(f"{'='*70}")

    trad_history:  list[dict] = []
    graph_history: list[dict] = []

    trad_cumulative_tokens  = 0
    graph_cumulative_tokens = 0

    turns_results = []

    for turn_info in chain["turns"]:
        turn_num = turn_info["turn"]
        query    = turn_info["query"]
        gt_frags = turn_info["ground_truth_fragments"]

        print(f"\n  Turn {turn_num}: {query[:80]}…")

        # ── Traditional RAG ──────────────────────────────────────────────
        # Build history string for prompt (Traditional RAG in streamlit app
        # doesn't accept chat_history param; we manually inject it)
        history_prefix = ""
        if trad_history:
            history_prefix = "CONVERSATION HISTORY:\n" + "\n".join(
                f"{m['role'].upper()}: {m['content']}" for m in trad_history[-4:]
            ) + "\n\n"

        t0 = time.perf_counter()
        # Traditional RAG: just query + store (no chat_history param in this version)
        trad_result = retrieval.traditional_rag(
            query=query,
            store=store,
        )
        trad_latency = round((time.perf_counter() - t0) * 1000, 1)
        trad_tokens  = trad_result.get("total_tokens", 0)
        trad_cumulative_tokens += trad_tokens

        trad_history.append({"role": "user",      "content": query})
        trad_history.append({"role": "assistant",  "content": trad_result.get("answer", "")})

        print(f"    [Traditional] tokens={trad_tokens:,}  latency={trad_latency}ms")

        # ── Context Graph (Hybrid) ───────────────────────────────────────
        # streamlit_app hybrid_graphrag uses 'history' parameter
        t1 = time.perf_counter()
        graph_result = retrieval.hybrid_graphrag(
            query=query,
            store=store,
            history=graph_history if graph_history else None,
        )
        graph_latency = round((time.perf_counter() - t1) * 1000, 1)
        graph_tokens  = graph_result.get("total_tokens", 0)
        graph_cumulative_tokens += graph_tokens

        graph_history.append({"role": "user",      "content": query})
        graph_history.append({"role": "assistant",  "content": graph_result.get("answer", "")})

        print(f"    [ContextGraph] tokens={graph_tokens:,}  latency={graph_latency}ms")

        # ── Verification ─────────────────────────────────────────────────
        trad_verify  = _contains_fragments(trad_result.get("answer", ""), gt_frags)
        graph_verify = _contains_fragments(graph_result.get("answer", ""), gt_frags)

        token_saving = trad_tokens - graph_tokens
        cumulative_saving = trad_cumulative_tokens - graph_cumulative_tokens

        print(f"    [Verification] Traditional score={trad_verify['score']:.0%}  "
              f"ContextGraph score={graph_verify['score']:.0%}  "
              f"Token saving={token_saving:+,}")

        turns_results.append({
            "turn": turn_num,
            "query": query,
            "ground_truth_fragments": gt_frags,
            "traditional": {
                "answer":         trad_result.get("answer", ""),
                "input_tokens":   trad_result.get("input_tokens", 0),
                "output_tokens":  trad_result.get("output_tokens", 0),
                "total_tokens":   trad_tokens,
                "latency_ms":     trad_latency,
                "verification":   trad_verify,
            },
            "contextgraph": {
                "answer":         graph_result.get("answer", ""),
                "input_tokens":   graph_result.get("input_tokens", 0),
                "output_tokens":  graph_result.get("output_tokens", 0),
                "total_tokens":   graph_tokens,
                "latency_ms":     graph_latency,
                "verification":   graph_verify,
                "graph_nodes":    len(graph_result.get("graph_nodes", [])),
                "graph_edges":    len(graph_result.get("graph_edges", [])),
                "query_type":     graph_result.get("query_type", ""),
                "confidence":     graph_result.get("confidence_label", ""),
            },
            "token_saving_this_turn": token_saving,
            "cumulative_token_saving_vs_traditional": cumulative_saving,
        })

    return {
        "chain_id":                    chain_id,
        "topic":                        topic,
        "source_doc":                   chain["source_doc"],
        "turns":                        turns_results,
        "total_traditional_tokens":     trad_cumulative_tokens,
        "total_contextgraph_tokens":    graph_cumulative_tokens,
        "total_token_saving":           trad_cumulative_tokens - graph_cumulative_tokens,
        "token_saving_pct":             round(
            (trad_cumulative_tokens - graph_cumulative_tokens) / max(trad_cumulative_tokens, 1) * 100, 1
        ),
    }


# ---------------------------------------------------------------------------
# REPORT WRITER
# ---------------------------------------------------------------------------

def _write_report(all_chain_results: list[dict], output_path: Path):
    lines = [
        "# Multi-Turn Query Evaluation Report",
        f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Overview",
        "",
        "This report runs **5 multi-turn conversation chains** (4 turns each) against",
        "**both Traditional Vector RAG and ContextGraph** pipelines.",
        "Answers are verified against ground-truth fragments extracted from the source PDFs.",
        "",
        "---",
        "",
    ]

    # Summary table
    lines += [
        "## Summary Table",
        "",
        "| Chain | Topic | Trad Tokens | Graph Tokens | Saving | Saving % |",
        "|-------|-------|------------|--------------|--------|----------|",
    ]
    grand_trad = grand_graph = 0
    for r in all_chain_results:
        grand_trad  += r["total_traditional_tokens"]
        grand_graph += r["total_contextgraph_tokens"]
        saving_pct = r["token_saving_pct"]
        symbol = "[+]" if saving_pct > 0 else "[-]"
        lines.append(
            f"| **{r['chain_id']}** | {r['topic'][:45]} | "
            f"{r['total_traditional_tokens']:,} | {r['total_contextgraph_tokens']:,} | "
            f"{r['total_token_saving']:+,} | {symbol} {saving_pct}% |"
        )
    grand_saving = grand_trad - grand_graph
    grand_pct = round(grand_saving / max(grand_trad, 1) * 100, 1)
    lines += [
        f"| **TOTAL** | — | **{grand_trad:,}** | **{grand_graph:,}** | "
        f"**{grand_saving:+,}** | **{grand_pct}%** |",
        "",
        "---",
        "",
    ]

    # Per-chain detail
    for r in all_chain_results:
        lines += [
            f"## Chain {r['chain_id']}: {r['topic']}",
            f"> **Source Document**: `{r['source_doc']}`",
            "",
        ]
        for t in r["turns"]:
            trad  = t["traditional"]
            graph = t["contextgraph"]
            trad_v  = trad["verification"]
            graph_v = graph["verification"]

            lines += [
                f"### Turn {t['turn']}: {t['query']}",
                "",
                "**Ground-truth fragments to verify against source document:**",
                ", ".join(f"`{f}`" for f in t["ground_truth_fragments"]),
                "",
                "#### Traditional Vector RAG",
                f"> **Tokens**: input={trad['input_tokens']:,} | output={trad['output_tokens']:,} | **total={trad['total_tokens']:,}**  |  latency={trad['latency_ms']}ms",
                "",
                f"**Answer**: {trad['answer'][:600]}{'…' if len(trad['answer']) > 600 else ''}",
                "",
                f"**Verification score**: {trad_v['score']:.0%}  [OK] matched: {trad_v['matched']}  [MISS] missed: {trad_v['missed']}",
                "",
                "#### ContextGraph (Hybrid Graph + Vector RAG)",
                f"> **Tokens**: input={graph['input_tokens']:,} | output={graph['output_tokens']:,} | **total={graph['total_tokens']:,}**  |  latency={graph['latency_ms']}ms",
                f"> Graph nodes touched: {graph['graph_nodes']} | Query type: `{graph['query_type']}` | Confidence: `{graph['confidence']}`",
                "",
                f"**Answer**: {graph['answer'][:600]}{'…' if len(graph['answer']) > 600 else ''}",
                "",
                f"**Verification score**: {graph_v['score']:.0%}  [OK] matched: {graph_v['matched']}  [MISS] missed: {graph_v['missed']}",
                "",
                f"**Token saving this turn vs Traditional**: `{t['token_saving_this_turn']:+,}` | "
                f"**Cumulative saving so far**: `{t['cumulative_token_saving_vs_traditional']:+,}`",
                "",
                "---",
                "",
            ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  [OK] Report written -> {output_path}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("\n" + "="*70)
    print("  MULTI-TURN QUERY EVALUATION")
    print("  Traditional Vector RAG  vs  ContextGraph (Hybrid)")
    print("="*70)
    print(f"  Chains: {len(CHAINS)} | Turns per chain: 4 | Total queries: {len(CHAINS)*4}")
    print(f"  FAISS index dir: {config.FAISS_DIR}")
    print(f"  LLM model: {config.CLAUDE_MODEL_LIGHT}")

    # Load the FAISS store
    print("\n  Loading FAISS amc_master index …", end="", flush=True)
    store = fs.BrochureFAISSStore("amc_master")
    print(" done.")

    all_results: list[dict] = []
    overall_start = time.perf_counter()

    for chain in CHAINS:
        result = _run_chain(chain, store)
        all_results.append(result)

    total_elapsed = round((time.perf_counter() - overall_start), 1)

    # Write JSON
    json_path = RESULTS_DIR / "multi_turn_results.json"
    payload = {
        "generated_at": datetime.now().isoformat(),
        "total_elapsed_seconds": total_elapsed,
        "chains": all_results,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  [OK] JSON results written -> {json_path}")

    # Write Markdown Report
    md_path = RESULTS_DIR / "multi_turn_report.md"
    _write_report(all_results, md_path)

    # Quick Console Summary
    print("\n" + "="*70)
    print("  FINAL SUMMARY")
    print("="*70)
    grand_trad  = sum(r["total_traditional_tokens"]  for r in all_results)
    grand_graph = sum(r["total_contextgraph_tokens"] for r in all_results)
    grand_saving = grand_trad - grand_graph
    grand_pct   = round(grand_saving / max(grand_trad, 1) * 100, 1)
    print(f"  Grand Total -- Traditional: {grand_trad:,} tokens | ContextGraph: {grand_graph:,} tokens")
    print(f"  Overall Token Saving: {grand_saving:+,} ({grand_pct}%)")
    print(f"  Total elapsed time: {total_elapsed}s")
    print("="*70)


if __name__ == "__main__":
    main()
