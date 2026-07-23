"""
judge_eval.py
===============
Offline faithfulness/completeness regression harness.

Runs a small fixed set of known queries against both retrieval pipelines
(traditional_rag, hybrid_graphrag) using the already-indexed FAISS store,
then asks a separate, stronger Claude model (config.CLAUDE_MODEL_RELATIONS —
a judge should not be weaker than the model it's grading) to score each
answer against the context that was actually retrieved for it.

This is deliberately a lightweight, deterministic harness — not an
adversarial multi-turn agent — so it's cheap to re-run after every change to
context_engine/semantic_cache.py, context_engine/hyde.py, or
text_to_cypher.py's critique loop, to catch faithfulness regressions from
those changes early.

Run from streamlit_app/:
    python -m evals.judge_eval [--store amc_master] [--mode both|traditional|hybrid] [--clear-cache]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import config
import faiss_store
import llm_text_client
import retrieval
from context_engine import semantic_cache

REPORT_DIR = config.LOG_DIR / "judge_eval"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# EDIT ME — adjust to match documents actually present in your FAISS index.
# answerable=True means the corpus should contain a real answer. The
# answerable=False cases are the "should refuse" adversarial questions
# (mirrors the colleague's AARE baseline test) — a fabricated answer here
# is a hard fail regardless of what the judge's numeric scores say.
EVAL_QUERIES: List[Dict[str, Any]] = [
    {"query": "What does SEBI require Investment Advisers to disclose about their use of AI tools?", "answerable": True},
    {"query": "What are Adani Enterprises' ESG and sustainability commitments?", "answerable": True},
    {"query": "What are the core algorithmic trading guidelines for Investment Advisers according to SEBI?", "answerable": True},
    {"query": "How many mutual fund schemes are managed under each fund house?", "answerable": True},
    {"query": "What are the RBI's governance requirements for NBFC robo-advisors?", "answerable": False},
    {"query": "How does SEBI's stance compare with the EU AI Act's requirements for financial services?", "answerable": False},
    {"query": "What does the ISO/IEC 42001 standard require for AI management systems in this context?", "answerable": False},
    {"query": "What are AMFI's specific guidelines on algorithmic trading disclosures?", "answerable": False},
]

_JUDGE_PROMPT = """You are grading a RAG (retrieval-augmented generation) system's
answer for factual faithfulness. You will be shown the question, the context
the system retrieved, and the answer it produced.

QUESTION: {question}

RETRIEVED CONTEXT:
{context}

SYSTEM ANSWER:
{answer}

Score the answer on these axes and respond with ONLY a JSON object (no
markdown fences, no commentary):
{{
  "faithfulness": <1-5 integer, 5 = every claim is directly traceable to the
      retrieved context, 1 = the answer contains claims not supported by or
      contradicting the context>,
  "completeness": <1-5 integer, 5 = uses all the relevant information the
      context actually offers, 1 = ignores clearly relevant available context>,
  "correctly_declined": <true if the context does not contain the answer AND
      the system's answer explicitly says so rather than guessing; false if
      the system fabricated an answer despite insufficient context; null if
      the context DID contain a real answer (only meaningful for genuinely
      unanswerable questions)>,
  "reasoning": "<one sentence explaining the scores>"
}}"""


def _context_string_for(result: Dict[str, Any]) -> str:
    docs = result.get("docs", [])
    joined = "\n\n---\n\n".join(d.get("full_text", d.get("snippet", "")) for d in docs)
    return joined or "(no context retrieved)"


def judge_answer(question: str, context: str, answer: str) -> Dict[str, Any]:
    prompt = _JUDGE_PROMPT.format(question=question, context=context[:6000], answer=answer)
    parsed = llm_text_client.call_llm_json(prompt, model_id=config.CLAUDE_MODEL_RELATIONS)
    if not parsed:
        return {"faithfulness": None, "completeness": None, "correctly_declined": None,
                "reasoning": "judge call failed or returned unparseable output"}
    return parsed


def run_case(store, case: Dict[str, Any], mode: str) -> Dict[str, Any]:
    query = case["query"]
    fn = retrieval.traditional_rag if mode == "traditional" else retrieval.hybrid_graphrag
    result = fn(query, store)
    context = _context_string_for(result)
    judged = judge_answer(query, context, result.get("answer", ""))

    verdict = "PASS"
    if case["answerable"]:
        if isinstance(judged.get("faithfulness"), (int, float)) and judged["faithfulness"] < 3:
            verdict = "FAIL"
    else:
        if judged.get("correctly_declined") is False:
            verdict = "FAIL"

    return {
        "mode": mode,
        "query": query,
        "answerable": case["answerable"],
        "answer": result.get("answer", ""),
        "cache_hit": result.get("telemetry_breakdown", {}).get("cache_hit"),
        "judge": judged,
        "verdict": verdict,
    }


def run_eval(store_slug: str, modes: List[str]) -> List[Dict[str, Any]]:
    store = faiss_store.get_store(store_slug)
    rows: List[Dict[str, Any]] = []

    for mode in modes:
        print(f"\n{'=' * 80}\n  MODE: {mode.upper()}\n{'=' * 80}", flush=True)
        for case in EVAL_QUERIES:
            row = run_case(store, case, mode)
            rows.append(row)
            tag = "answerable" if case["answerable"] else "should-decline"
            j = row["judge"]
            print(f"[{row['verdict']}] ({tag}) \"{row['query'][:70]}\"", flush=True)
            print(f"       faithfulness={j.get('faithfulness')} completeness={j.get('completeness')} "
                  f"correctly_declined={j.get('correctly_declined')} cache_hit={row['cache_hit']}", flush=True)
            print(f"       {j.get('reasoning', '')}", flush=True)
    return rows


def print_summary(rows: List[Dict[str, Any]]) -> None:
    print(f"\n{'=' * 80}\n  SUMMARY\n{'=' * 80}", flush=True)
    for mode in sorted({r["mode"] for r in rows}):
        mode_rows = [r for r in rows if r["mode"] == mode]
        passed = sum(1 for r in mode_rows if r["verdict"] == "PASS")
        faith_scores = [r["judge"]["faithfulness"] for r in mode_rows
                         if isinstance(r["judge"].get("faithfulness"), (int, float))]
        avg_faith = sum(faith_scores) / len(faith_scores) if faith_scores else 0.0
        print(f"  {mode:12s}  {passed}/{len(mode_rows)} passed   avg faithfulness={avg_faith:.2f}/5", flush=True)


def save_report(rows: List[Dict[str, Any]]) -> Path:
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = REPORT_DIR / f"judge_eval_{ts}.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="amc_master", help="FAISS index slug to query (default: amc_master)")
    ap.add_argument("--mode", choices=["traditional", "hybrid", "both"], default="both")
    ap.add_argument("--clear-cache", action="store_true",
                     help="Reset the semantic cache before running, so every query is a fresh cache miss")
    args = ap.parse_args()

    if args.clear_cache:
        semantic_cache.clear()

    run_modes = ["traditional", "hybrid"] if args.mode == "both" else [args.mode]
    eval_rows = run_eval(args.store, run_modes)
    print_summary(eval_rows)
    out_path = save_report(eval_rows)
    print(f"\nFull report written to {out_path}", flush=True)
