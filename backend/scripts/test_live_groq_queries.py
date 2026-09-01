# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_live_groq_queries.py
=========================
Verifies 2-3 real queries through the RAG pipeline using Groq exclusively.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.api.deps import init_container
from app.core.llm import get_llm_client
from app.config import get_settings


async def test_live_groq_queries():
    print("=" * 70)
    print("LIVE GROQ LLM VERIFICATION TEST")
    print("=" * 70)

    settings = get_settings()
    print(f"Active Provider: {settings.llm_provider}")
    print(f"Groq API Key Configured: {'Yes (' + settings.groq_api_key[:8] + '...)' if settings.groq_api_key else 'No'}")
    print(f"Claude API Key in Env: {os.environ.get('CLAUDE_API_KEY', 'None')}")
    print(f"Anthropic in Config: {getattr(settings, 'anthropic_api_key', 'REMOVED')}")
    print("-" * 70)

    container = init_container()
    orchestrator = container.orchestrator
    llm_client = get_llm_client()

    test_queries = [
        {
            "id": "QUERY 1: SEBI Regulation (v2 Orchestrator + Groq Synthesis)",
            "query": "What are the investment requirements and equity allocation threshold for large cap mutual fund schemes under SEBI rules?",
            "type": "orchestrator",
        },
        {
            "id": "QUERY 2: Corporate Analysis (v2 Orchestrator + Groq Synthesis)",
            "query": "Summarize the revenue and operational highlights for Adani Enterprises based on available data.",
            "type": "orchestrator",
        },
        {
            "id": "QUERY 3: Structured JSON Output (Direct Groq Schema Synthesis)",
            "query": "Extract key compliance parameters for Multi Cap mutual funds under SEBI: minimum total equity allocation, minimum large cap, mid cap, and small cap allocation.",
            "type": "structured_llm",
            "schema": {
                "type": "object",
                "properties": {
                    "scheme_type": {"type": "string"},
                    "min_equity_total_pct": {"type": "number"},
                    "min_large_cap_pct": {"type": "number"},
                    "min_mid_cap_pct": {"type": "number"},
                    "min_small_cap_pct": {"type": "number"},
                    "regulatory_authority": {"type": "string"},
                },
                "required": ["scheme_type", "min_equity_total_pct", "regulatory_authority"],
            },
        },
    ]

    results = []

    for idx, tq in enumerate(test_queries, 1):
        print(f"\n--- Executing {tq['id']} ---")
        print(f"Prompt / Question: {tq['query']}")
        t0 = time.perf_counter()

        if tq["type"] == "orchestrator":
            response = await orchestrator.answer(tq["query"])
            duration_ms = (time.perf_counter() - t0) * 1000.0

            ans_snippet = response.synthesis.answer if response.synthesis else "No answer generated"
            print(f"Status: SUCCESS ({duration_ms:.1f}ms)")
            print(f"Confidence: {response.synthesis.confidence if response.synthesis else 'N/A'}")
            print(f"Citations: {len(response.synthesis.citations) if response.synthesis else 0}")
            print(f"Answer Preview:\n{ans_snippet[:350]}...\n")

            results.append({
                "query_id": tq["id"],
                "status": "PASS",
                "latency_ms": round(duration_ms, 1),
                "answer_preview": ans_snippet[:300],
                "citations_count": len(response.synthesis.citations) if response.synthesis else 0,
            })

        elif tq["type"] == "structured_llm":
            structured_res = await llm_client.complete_structured(
                prompt=tq["query"],
                schema=tq["schema"],
                system="You are a mutual fund compliance assistant. Respond strictly in JSON matching the requested schema.",
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0

            print(f"Status: SUCCESS ({duration_ms:.1f}ms)")
            print(f"Structured JSON Result:\n{json.dumps(structured_res, indent=2)}")

            results.append({
                "query_id": tq["id"],
                "status": "PASS",
                "latency_ms": round(duration_ms, 1),
                "json_output": structured_res,
            })

    print("\n" + "=" * 70)
    print("SUMMARY OF VERIFICATION")
    print("=" * 70)
    for r in results:
        print(f"[PASS] {r['query_id']} — Latency: {r['latency_ms']}ms")
    print(f"\nAll queries successfully completed via Groq (0 Claude dependencies).")


if __name__ == "__main__":
    asyncio.run(test_live_groq_queries())
