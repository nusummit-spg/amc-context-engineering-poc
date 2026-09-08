#!/usr/bin/env python3
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
Benchmark baseline performance before and across efficiency improvements.
Runs 12 representative queries across 4 categories and saves full metrics.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from app.api.deps import init_container
from app.core.metrics import get_metrics_store

BASELINE_QUERIES = [
    # 1. Simple entity lookups (cache-friendly, fast)
    ("What is the NAV of Adani Growth fund?", "simple_entity"),
    ("Tell me about Tata Balanced scheme", "simple_entity"),
    ("What is the AUM of Axis Bluechip?", "simple_entity"),
    
    # 2. Comparisons (multi-entity, benefits from decomposition & parallelization)
    ("Compare Adani Growth vs Tata Balanced", "comparison"),
    ("Which is better: equity or debt funds?", "comparison"),
    ("Compare the risk and return characteristics of large cap versus mid cap schemes", "comparison"),
    
    # 3. Aggregations (benefits from Cypher generation & correction)
    ("What is the total AUM of all equity schemes?", "aggregation"),
    ("List the top 5 performing funds", "aggregation"),
    ("How many funds comply with SEBI categorization norms?", "aggregation"),
    
    # 4. Complex questions (multi-step reasoning, benefits from decomposition)
    ("How do SEBI regulations affect fund performance, specifically for Adani schemes?", "complex"),
    ("Explain the relationship between NAV, performance metrics, and regulatory compliance", "complex"),
    ("What are the exit load implications for retail investors under the latest guidelines?", "complex"),
]


async def run_benchmark(output_name: str = "baseline_metrics.json"):
    container = init_container()
    orchestrator = container.orchestrator
    metrics_store = get_metrics_store()

    print("=" * 80)
    print("EFFICIENCY BENCHMARK RUN")
    print("=" * 80)
    print(f"Total queries: {len(BASELINE_QUERIES)}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = []
    for i, (query, query_type) in enumerate(BASELINE_QUERIES, 1):
        print(f"[{i:02d}/{len(BASELINE_QUERIES):02d}] {query_type.upper():<14}: {query[:55]}...")
        try:
            t0 = time.perf_counter()
            response = await orchestrator.answer(query, track_metrics=True)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            trace = getattr(response, "trace", None)
            cache_hit = trace.cache_hit if trace else False
            tokens = (trace.input_tokens + trace.output_tokens) if trace else 0

            result_entry = {
                "query": query,
                "type": query_type,
                "latency_ms": round(elapsed_ms, 2),
                "cache_hit": cache_hit,
                "tokens": tokens,
            }
            results.append(result_entry)
            print(f"       -> {elapsed_ms:6.1f}ms | cache_hit={cache_hit}")
        except Exception as exc:
            print(f"       -> ERROR: {exc}")
            results.append({
                "query": query,
                "type": query_type,
                "error": str(exc),
            })

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    summary = metrics_store.summary()
    print(json.dumps(summary, indent=2))

    log_dir = backend_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / output_name
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "query_count": len(results),
            "summary": summary,
            "queries": results,
        }, f, indent=2)

    print(f"\n[OK] Benchmark saved to: {out_path}\n")
    return results, summary


if __name__ == "__main__":
    asyncio.run(run_benchmark())
