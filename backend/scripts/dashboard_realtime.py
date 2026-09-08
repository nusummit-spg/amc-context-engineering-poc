#!/usr/bin/env python3
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
dashboard_realtime.py
=====================
Real-time terminal dashboard displaying latency, cache hit rates,
and efficiency telemetry from the metrics store.
"""
import os
import sys
import time
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from app.core.metrics import load_persisted_metrics, summarize_persisted_metrics
from app.engine import config


def render_dashboard():
    # Read from the on-disk metric records: the API serves traffic in a separate
    # process, so this script's own in-memory store is always empty.
    summary = summarize_persisted_metrics()
    recent = load_persisted_metrics()[-5:]

    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 80)
    print("     AMC CONTEXT ENGINEERING — EFFICIENCY & OBSERVABILITY DASHBOARD")
    print(f"     Status: ACTIVE | Refreshed: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print("\n[ACTIVE FEATURE FLAGS]")
    print(f"  • HyDE Response Caching:     {'[ON]' if config.ENABLE_HYDE_CACHE else '[OFF]'}")
    print(f"  • HyDE in Orchestrator:       {'[ON]' if config.ENABLE_HYDE_IN_ORCHESTRATOR else '[OFF]'}")
    print(f"  • GLiNER Saturation Bypass:   {'[ON]' if config.ENABLE_GLINER_SKIP else '[OFF]'}")
    print(f"  • Cypher Auto-Correction:     {'[ON]' if config.ENABLE_CYPHER_AUTO_CORRECTION else '[OFF]'}")
    print(f"  • Parallel Retrieval:         {'[ON]' if config.ENABLE_PARALLELIZATION else '[OFF]'}")
    print(f"  • Query Decomposition:        {'[ON]' if config.ENABLE_QUERY_DECOMPOSITION else '[OFF]'}")

    print("\n[PERFORMANCE TELEMETRY]")
    print(f"  Total Queries Tracked:  {summary.get('count', 0)}")
    print(f"  Latency Average:        {summary.get('latency_avg_ms', 0.0):6.1f} ms")
    print(f"  Latency P50:            {summary.get('latency_p50_ms', 0.0):6.1f} ms")
    print(f"  Latency P99:            {summary.get('latency_p99_ms', 0.0):6.1f} ms")
    print(f"  Cache Hit Rate:         {summary.get('cache_hit_rate', 0.0)*100:6.1f} %")
    print(f"  Average Token Usage:    {summary.get('token_avg', 0.0):6.1f} tokens/query")
    print(f"  Citation Accuracy:      {summary.get('citation_accuracy_avg', 1.0)*100:6.1f} %")

    print("\n[RECENT 5 QUERIES]")
    if not recent:
        print("  (No queries recorded yet this session)")
    else:
        for qm in reversed(recent):
            query = qm.get("query", "")
            q_text = query[:40] + ("..." if len(query) > 40 else "")
            hit_str = "[HIT]" if qm.get("cache_hit") else "[MISS]"
            print(f"  • {qm.get('timestamp', '')[11:19]} | {qm.get('query_type', 'unknown'):<15} "
                  f"| {qm.get('total_latency_ms', 0.0):6.1f}ms | {hit_str} | {q_text}")

    print("\n" + "=" * 80)


def watch(interval_seconds: int = 5):
    """Continuously refresh until interrupted."""
    try:
        while True:
            render_dashboard()
            print(f"Refreshing every {interval_seconds}s — Ctrl+C to exit.")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("Dashboard stopped.")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        interval = 5
        for arg in sys.argv[1:]:
            if arg.startswith("--interval="):
                interval = int(arg.split("=", 1)[1])
        watch(interval)
    else:
        render_dashboard()
