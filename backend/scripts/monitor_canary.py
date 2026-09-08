#!/usr/bin/env python3
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
monitor_canary.py
=================
Continuous canary soak monitor (Week 5-6, Task 5.1).

Polls the on-disk metric records at a fixed interval for the length of the soak,
comparing each window against logs/baseline_metrics.json. Prints a HEALTHY /
UNHEALTHY line per check and exits non-zero if the canary breached a regression
threshold on consecutive checks — so it can gate an automated rollback.

Usage:
    python scripts/monitor_canary.py                        # 24h soak, 60s interval
    python scripts/monitor_canary.py --hours 2 --interval 30
    python scripts/monitor_canary.py --once                 # single check, for CI
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from app.core.metrics import summarize_persisted_metrics

BASELINE_FILE = backend_root / "logs" / "baseline_metrics.json"

LATENCY_WARN_FACTOR = 1.10      # 10% slower than baseline = warn
TOKEN_WARN_FACTOR = 1.10
ACCURACY_WARN_FACTOR = 0.95
MAX_HALLUCINATION_RATE = 0.15

# Consecutive unhealthy checks before the monitor calls it a failure. A single
# bad window is usually a traffic blip, not a regression.
UNHEALTHY_STREAK_LIMIT = 3


def load_baseline() -> dict:
    if not BASELINE_FILE.exists():
        print(f"[WARN] No baseline at {BASELINE_FILE}; run scripts/benchmark_baseline.py first.")
        print("[WARN] Monitoring will report metrics but cannot detect regressions.")
        return {}
    try:
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("summary", {})
    except Exception as exc:
        print(f"[WARN] Could not read baseline: {exc}")
        return {}


def check_window(baseline: dict, window_seconds: float) -> tuple[bool, dict, list[str]]:
    """Returns (is_healthy, summary, issues) for the trailing window."""
    summary = summarize_persisted_metrics(since_seconds=window_seconds)
    if not summary.get("count"):
        return True, summary, []

    issues = []
    base_lat = baseline.get("latency_avg_ms") or 0.0
    base_tok = baseline.get("token_avg") or 0.0
    base_acc = baseline.get("citation_accuracy_avg") or 1.0

    if base_lat and summary["latency_avg_ms"] > base_lat * LATENCY_WARN_FACTOR:
        issues.append(
            f"Latency regression: {summary['latency_avg_ms']:.0f}ms vs {base_lat:.0f}ms baseline"
        )
    if base_tok and summary["token_avg"] > base_tok * TOKEN_WARN_FACTOR:
        issues.append(
            f"Token regression: {summary['token_avg']:.0f} vs {base_tok:.0f} baseline"
        )
    if summary["citation_accuracy_avg"] < base_acc * ACCURACY_WARN_FACTOR:
        issues.append(
            f"Accuracy regression: {summary['citation_accuracy_avg']:.1%} vs {base_acc:.1%} baseline"
        )
    if summary["hallucination_rate"] > MAX_HALLUCINATION_RATE:
        issues.append(f"Hallucination rate {summary['hallucination_rate']:.1%} above ceiling")

    return (not issues), summary, issues


def monitor(hours: float, interval: int, window_minutes: float, once: bool) -> bool:
    baseline = load_baseline()

    print("=" * 70)
    print("CANARY MONITORING")
    print("=" * 70)
    if baseline:
        print(f"Baseline latency:  {baseline.get('latency_avg_ms', 0):.0f}ms")
        print(f"Baseline tokens:   {baseline.get('token_avg', 0):.0f}")
        print(f"Baseline accuracy: {baseline.get('citation_accuracy_avg', 1.0):.1%}")
    print(f"Soak: {hours:g}h | check every {interval}s | trailing window {window_minutes:g}min")
    print("=" * 70)

    deadline = time.time() + hours * 3600
    window_seconds = window_minutes * 60
    unhealthy_streak = 0
    healthy = True

    try:
        while True:
            is_healthy, summary, issues = check_window(baseline, window_seconds)
            stamp = datetime.now().strftime("%H:%M:%S")

            if not summary.get("count"):
                print(f"[{stamp}] No traffic in the trailing window yet...")
            else:
                status = "HEALTHY" if is_healthy else "UNHEALTHY"
                print(f"\n[{stamp}] {status}")
                print(f"  Queries:   {summary['count']}")
                print(f"  Latency:   {summary['latency_avg_ms']:.0f}ms avg / {summary['latency_p99_ms']:.0f}ms p99")
                print(f"  Cache hit: {summary['cache_hit_rate']:.1%}")
                print(f"  Accuracy:  {summary['citation_accuracy_avg']:.1%}")
                for issue in issues:
                    print(f"  ! {issue}")

                unhealthy_streak = 0 if is_healthy else unhealthy_streak + 1
                if unhealthy_streak >= UNHEALTHY_STREAK_LIMIT:
                    print(f"\n[ABORT] {unhealthy_streak} consecutive unhealthy checks -> ROLL BACK THE CANARY")
                    healthy = False
                    break

            if once or time.time() >= deadline:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitoring interrupted by operator.")

    print("\n" + "=" * 70)
    print("CANARY MONITORING COMPLETE — " + ("HEALTHY" if healthy else "REGRESSION DETECTED"))
    print("=" * 70)
    return healthy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Canary soak monitor")
    parser.add_argument("--hours", type=float, default=24.0, help="Soak duration in hours")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between checks")
    parser.add_argument("--window-minutes", type=float, default=15.0,
                        help="Trailing window of metrics each check evaluates")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit")
    args = parser.parse_args()

    sys.exit(0 if monitor(args.hours, args.interval, args.window_minutes, args.once) else 1)
