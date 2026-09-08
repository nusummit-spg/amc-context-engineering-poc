#!/usr/bin/env python3
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
check_canary_health.py
======================
Canary promotion gate. Compares observed canary traffic against the recorded
baseline (logs/baseline_metrics.json) and exits non-zero when a regression
threshold is breached, so deploy_canary.sh can roll back automatically.

Usage:
    python scripts/check_canary_health.py [--window-hours 24] [--min-samples 20]
"""
import argparse
import json
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from app.core.metrics import summarize_persisted_metrics

BASELINE_FILE = backend_root / "logs" / "baseline_metrics.json"

# Regression thresholds, relative to baseline.
LATENCY_REGRESSION_FACTOR = 1.15      # >15% slower than baseline = fail
TOKEN_REGRESSION_FACTOR = 1.15        # >15% more tokens = fail
ACCURACY_REGRESSION_FACTOR = 0.95     # >5% accuracy drop = fail
MAX_HALLUCINATION_RATE = 0.15         # absolute ceiling


def load_baseline() -> dict | None:
    if not BASELINE_FILE.exists():
        return None
    try:
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("summary")
    except Exception as exc:
        print(f"[WARN] Could not read baseline {BASELINE_FILE}: {exc}")
        return None


def evaluate_canary_health(window_hours: float = 24.0, min_samples: int = 20) -> bool:
    print("=" * 70)
    print("CANARY PRODUCTION HEALTH EVALUATION GATE")
    print("=" * 70)

    summary = summarize_persisted_metrics(since_seconds=window_hours * 3600)
    count = summary.get("count", 0)
    print(f"Window: last {window_hours:g}h | Sample Size: {count} queries\n")

    if count < min_samples:
        # Not enough evidence either way. This is INCONCLUSIVE, not healthy —
        # promoting on no data is how a bad canary reaches 100% of traffic.
        print(f"[BLOCKED] Insufficient canary traffic: {count} < {min_samples} required samples.")
        print("Hold the canary at its current weight until more traffic accumulates,")
        print("or lower --min-samples if this is a deliberate low-volume soak.")
        print("=" * 70)
        return False

    baseline = load_baseline()
    if baseline is None:
        print(f"[BLOCKED] No baseline found at {BASELINE_FILE}.")
        print("Run: python scripts/benchmark_baseline.py  (before promoting a canary)")
        print("=" * 70)
        return False

    avg_lat = summary.get("latency_avg_ms", 0.0)
    p99_lat = summary.get("latency_p99_ms", 0.0)
    tokens = summary.get("token_avg", 0.0)
    cache_rate = summary.get("cache_hit_rate", 0.0)
    cit_acc = summary.get("citation_accuracy_avg", 1.0)
    halluc = summary.get("hallucination_rate", 0.0)

    base_lat = baseline.get("latency_avg_ms", 0.0)
    base_tokens = baseline.get("token_avg", 0.0)
    base_acc = baseline.get("citation_accuracy_avg", 1.0)

    lat_budget = base_lat * LATENCY_REGRESSION_FACTOR if base_lat else float("inf")
    token_budget = base_tokens * TOKEN_REGRESSION_FACTOR if base_tokens else float("inf")
    acc_floor = base_acc * ACCURACY_REGRESSION_FACTOR

    print("Observed vs Baseline:")
    print(f"  - Average Latency:    {avg_lat:8.1f} ms  (baseline {base_lat:.1f}ms, budget {lat_budget:.1f}ms)")
    print(f"  - P99 Latency:        {p99_lat:8.1f} ms")
    print(f"  - Tokens / query:     {tokens:8.1f}     (baseline {base_tokens:.1f}, budget {token_budget:.1f})")
    print(f"  - Cache Hit Rate:     {cache_rate*100:8.1f} %")
    print(f"  - Citation Accuracy:  {cit_acc*100:8.1f} %   (floor {acc_floor*100:.1f}%)")
    print(f"  - Hallucination Rate: {halluc*100:8.1f} %   (ceiling {MAX_HALLUCINATION_RATE*100:.1f}%)")
    print()

    failures = []
    if avg_lat > lat_budget:
        failures.append(f"Latency {avg_lat:.0f}ms exceeds budget {lat_budget:.0f}ms")
    if tokens > token_budget:
        failures.append(f"Tokens {tokens:.0f} exceeds budget {token_budget:.0f}")
    if cit_acc < acc_floor:
        failures.append(f"Citation accuracy {cit_acc:.1%} below floor {acc_floor:.1%}")
    if halluc > MAX_HALLUCINATION_RATE:
        failures.append(f"Hallucination rate {halluc:.1%} above ceiling {MAX_HALLUCINATION_RATE:.1%}")

    print("=" * 70)
    if failures:
        print("[NO-GO] CANARY HEALTH CHECK FAILED -> TRIGGER ROLLBACK")
        for f in failures:
            print(f"  - {f}")
        print("=" * 70)
        return False

    print("[GO] CANARY HEALTH CHECK PASSED -> PROCEED WITH PROMOTION")
    print("=" * 70)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Canary promotion health gate")
    parser.add_argument("--window-hours", type=float, default=24.0,
                        help="Only consider metrics recorded in the last N hours")
    parser.add_argument("--min-samples", type=int, default=20,
                        help="Minimum queries required for a conclusive verdict")
    args = parser.parse_args()

    sys.exit(0 if evaluate_canary_health(args.window_hours, args.min_samples) else 1)
