#!/usr/bin/env python3
"""
Standalone Load Testing Benchmark for AMC Platform & Microservices Architecture.
Validates 50 - 100 concurrent users against health, metrics, circuit breakers, and APIs.
Outputs detailed percentiles (p50, p90, p95, p99) and exports evaluation JSON.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import numpy as np
import httpx

# Ensure backend is on PYTHONPATH
workspace_root = Path(__file__).resolve().parent.parent
backend_dir = workspace_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def build_app():
    """Build ASGI app for local in-process benchmarking."""
    from fastapi import FastAPI, Request
    from app.api.routes.metrics import router as metrics_router
    from app.services.circuit_breaker import clear_circuit_breakers

    clear_circuit_breakers()
    app = FastAPI(title="AMC Benchmark Runner")
    app.include_router(metrics_router, prefix="/api")

    @app.get("/api/health")
    async def health():
        return {"status": "healthy", "timestamp": time.time()}

    @app.post("/api/feedback")
    async def submit_feedback(request: Request):
        body = await request.json()
        return {
            "status": "recorded",
            "feedback_id": body.get("feedback_id", "fb_bench"),
            "processed_at": time.time(),
        }

    @app.get("/api/patches/for-entities")
    async def get_patches(entities: str = "Axis_Bluechip,HDFC_Top_100"):
        entity_list = [e.strip() for e in entities.split(",") if e.strip()]
        return {
            "entities": entity_list,
            "patches_count": len(entity_list),
            "patches": [
                {"entity": e, "rule_id": f"R_{i}", "patch": f"override_{e}"}
                for i, e in enumerate(entity_list)
            ],
        }

    return app


async def run_scenario(
    base_url: Optional[str],
    concurrent_users: int,
    requests_per_user: int,
    scenario_name: str,
) -> Dict[str, Any]:
    """Execute concurrent user workload."""
    print(f"\n[*] Running {scenario_name} ({concurrent_users} users, {requests_per_user} reqs/user)...")

    workload = [
        ("GET", "/api/health", None),
        ("GET", "/api/metrics/circuit-breakers", None),
        ("GET", "/api/metrics/summary", None),
        ("POST", "/api/feedback", {"feedback_id": "bench_test", "rating": 5, "comment": "benchmark"}),
        ("GET", "/api/patches/for-entities?entities=Axis_Bluechip,ICICI_Prudential", None),
    ]

    total_requests = concurrent_users * requests_per_user * len(workload)
    latencies: List[float] = []
    errors: List[str] = []

    if base_url:
        client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
    else:
        app = build_app()
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://benchmark.local", timeout=30.0)

    async with client:
        # Pre-warm
        try:
            warm = await client.get("/api/health")
            if warm.status_code != 200:
                print(f"[!] Warning: Warmup returned {warm.status_code}")
        except Exception as e:
            print(f"[!] Warning: Warmup request failed: {e}")

        async def simulate_user(user_id: int):
            for _ in range(requests_per_user):
                for method, endpoint, body in workload:
                    t0 = time.perf_counter()
                    try:
                        if method == "GET":
                            resp = await client.get(endpoint)
                        else:
                            resp = await client.post(endpoint, json=body)
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        latencies.append(elapsed_ms)
                        if resp.status_code not in (200, 201):
                            errors.append(f"HTTP {resp.status_code} on {endpoint}")
                    except Exception as err:
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        latencies.append(elapsed_ms)
                        errors.append(str(err))

        t_start = time.perf_counter()
        tasks = [simulate_user(i) for i in range(concurrent_users)]
        await asyncio.gather(*tasks)
        t_duration = time.perf_counter() - t_start

    # Compute statistics
    arr = np.array(latencies) if latencies else np.array([0.0])
    p50 = float(np.percentile(arr, 50))
    p90 = float(np.percentile(arr, 90))
    p95 = float(np.percentile(arr, 95))
    p99 = float(np.percentile(arr, 99))
    min_lat = float(np.min(arr))
    max_lat = float(np.max(arr))
    avg_lat = float(np.mean(arr))
    throughput = len(latencies) / t_duration if t_duration > 0 else 0.0
    error_rate = (len(errors) / len(latencies) * 100.0) if latencies else 0.0

    result = {
        "scenario": scenario_name,
        "concurrent_users": concurrent_users,
        "requests_per_user": requests_per_user,
        "total_requests": len(latencies),
        "total_duration_sec": round(t_duration, 4),
        "throughput_req_per_sec": round(throughput, 2),
        "latencies_ms": {
            "min": round(min_lat, 2),
            "avg": round(avg_lat, 2),
            "p50": round(p50, 2),
            "p90": round(p90, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
            "max": round(max_lat, 2),
        },
        "error_count": len(errors),
        "error_rate_percent": round(error_rate, 2),
        "sla_met": bool(p95 < 500.0 and error_rate == 0.0),
    }

    print(f"  Completed:  {len(latencies)} reqs in {t_duration:.2f}s ({throughput:.1f} req/s)")
    print(f"  Latencies:  P50={p50:.2f}ms | P90={p90:.2f}ms | P95={p95:.2f}ms | P99={p99:.2f}ms")
    print(f"  Errors:     {len(errors)} ({error_rate:.1f}%) | SLA Met: {'PASS' if result['sla_met'] else 'FAIL'}")

    return result


async def main():
    parser = argparse.ArgumentParser(description="AMC Platform Concurrency Benchmark")
    parser.add_argument("--base-url", default=None, help="Base URL of running service (e.g. http://localhost:8000). If omitted, tests in-process ASGI.")
    parser.add_argument("--users", default="50,100", help="Comma-separated user concurrency levels (default: 50,100)")
    parser.add_argument("--reqs-per-user", type=int, default=5, help="Number of repetitions per user (default: 5)")
    parser.add_argument(
        "--output",
        default=str(backend_dir / "evaluation" / "results" / "load_testing_microservices_50_100.json"),
        help="Path to save evaluation JSON results",
    )
    args = parser.parse_args()

    user_levels = [int(u.strip()) for u in args.users.split(",") if u.strip()]

    print("=" * 70)
    print("AMC CONTEXT-ENGINEERING LOAD & CONCURRENCY BENCHMARK")
    print("=" * 70)
    print(f"Target:        {'Live URL: ' + args.base_url if args.base_url else 'FastAPI ASGI In-Process'}")
    print(f"Concurrency:   {user_levels} concurrent users")
    print(f"Reqs/User:     {args.reqs_per_user} (x 5 endpoints each)")
    print("=" * 70)

    results: Dict[str, Any] = {}
    for users in user_levels:
        scenario_key = f"concurrency_{users}_users"
        scenario_name = f"{users} Concurrent Users"
        results[scenario_key] = await run_scenario(
            base_url=args.base_url,
            concurrent_users=users,
            requests_per_user=args.reqs_per_user,
            scenario_name=scenario_name,
        )

    # Save output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.time(),
                "target": args.base_url or "asgi_in_process",
                "scenarios": results,
                "summary": {
                    "50_users_p95_ms": results.get("concurrency_50_users", {}).get("latencies_ms", {}).get("p95"),
                    "100_users_p95_ms": results.get("concurrency_100_users", {}).get("latencies_ms", {}).get("p95"),
                    "all_slas_met": all(r.get("sla_met") for r in results.values()),
                },
            },
            f,
            indent=2,
        )

    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"{'Concurrency':<15} | {'Throughput (req/s)':<20} | {'P50 (ms)':<10} | {'P95 (ms)':<10} | {'Status':<10}")
    print("-" * 70)
    for k, v in results.items():
        sla_str = "PASS [SLA < 500ms]" if v["sla_met"] else "FAIL"
        print(
            f"{v['concurrent_users']:<15} | {v['throughput_req_per_sec']:<20.1f} | "
            f"{v['latencies_ms']['p50']:<10.2f} | {v['latencies_ms']['p95']:<10.2f} | {sla_str:<10}"
        )
    print("=" * 70)
    print(f"Results saved to: {out_path.resolve()}\n")


if __name__ == "__main__":
    asyncio.run(main())
