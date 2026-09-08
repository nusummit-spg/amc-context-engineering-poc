#!/usr/bin/env python3
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
measure_hyde_impact.py
======================
Measures the latency and token impact of HyDE response caching.
Compares warm cache hits (<5ms) vs cold execution.
"""
import sys
import time
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from app.engine import hyde, config

TEST_QUERIES = [
    "What is the NAV of Adani Growth fund?",
    "Compare the risk profile of equity funds with debt funds",
    "Explain SEBI guidelines on fund categorization",
    "What are the exit load implications for retail investors?",
    "Tell me about ESG compliance requirements for mutual funds",
]


def measure():
    print("=" * 70)
    print("MEASURING HYDE RESPONSE CACHING LATENCY IMPACT")
    print("=" * 70)

    config.ENABLE_HYDE_CACHE = True
    hyde.clear_hyde_cache()

    cold_latencies = []
    warm_latencies = []

    for i, q in enumerate(TEST_QUERIES, 1):
        print(f"\nQuery {i}: {q}")
        
        # Cold call (or cache miss)
        t0 = time.perf_counter()
        doc1, lat1 = hyde.generate_hypothetical_document(q)
        cold_latencies.append(lat1)
        print(f"  [Cold]  Latency: {lat1:6.1f}ms | Doc length: {len(doc1)} chars")

        # Warm call (Cache Hit)
        t0 = time.perf_counter()
        doc2, lat2 = hyde.generate_hypothetical_document(q)
        warm_latencies.append(lat2)
        print(f"  [Warm]  Latency: {lat2:6.1f}ms | Match: {doc1 == doc2}")

    print("\n" + "=" * 70)
    print("HYDE MEASUREMENT SUMMARY")
    print("=" * 70)
    avg_cold = sum(cold_latencies) / len(cold_latencies)
    avg_warm = sum(warm_latencies) / len(warm_latencies)
    speedup = avg_cold / max(avg_warm, 0.001)

    print(f"Average Cold Latency: {avg_cold:6.1f}ms")
    print(f"Average Warm Latency: {avg_warm:6.1f}ms")
    print(f"Cache Hit Speedup:    {speedup:6.1f}x")
    print("=" * 70)

    stats = hyde.get_hyde_cache_stats()
    print(f"HyDE Cache Stats: {stats}\n")


if __name__ == "__main__":
    measure()
