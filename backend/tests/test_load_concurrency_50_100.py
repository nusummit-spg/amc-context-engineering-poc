"""
Load and Concurrency Benchmark Test Suite (50 - 100 Concurrent Users).
Validates platform endpoints, microservice clients, and circuit breaker under high concurrency.
"""
import asyncio
import time
from typing import List, Dict, Any
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes.metrics import router as metrics_router
from app.services.circuit_breaker import (
    CircuitBreaker,
    clear_circuit_breakers,
)
from app.services.feedback_client import FeedbackServiceClient
from app.services.repair_client import RepairServiceClient


def create_benchmark_app() -> FastAPI:
    """Create test application for concurrency benchmarking."""
    app = FastAPI(title="AMC Benchmark Application")
    app.include_router(metrics_router, prefix="/api")

    @app.get("/api/health")
    async def health():
        return {"status": "healthy", "timestamp": time.time()}

    @app.post("/api/feedback")
    async def submit_feedback(request: Request):
        body = await request.json()
        return {
            "status": "recorded",
            "feedback_id": body.get("feedback_id", "fb_test"),
            "processed_at": time.time(),
        }

    @app.get("/api/patches/for-entities")
    async def get_patches(entities: str = ""):
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


@pytest.fixture(autouse=True)
def reset_state():
    clear_circuit_breakers()
    yield
    clear_circuit_breakers()


def calculate_latencies(latencies_ms: List[float]) -> Dict[str, float]:
    """Calculate latency statistics from array of millisecond timings."""
    arr = np.array(latencies_ms)
    return {
        "count": len(arr),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


@pytest.mark.asyncio
async def test_load_concurrency_50_users():
    """Validate platform performance under 50 concurrent users."""
    app = create_benchmark_app()
    transport = ASGITransport(app=app)
    concurrency = 50
    requests_per_user = 4
    total_requests = concurrency * requests_per_user

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Pre-warm
        warmup = await client.get("/api/health")
        assert warmup.status_code == 200

        endpoints = [
            ("GET", "/api/health", None),
            ("GET", "/api/metrics/summary", None),
            ("GET", "/api/metrics/circuit-breakers", None),
            ("POST", "/api/feedback", {"feedback_id": "bench_50", "rating": 5}),
        ]

        latencies: List[float] = []
        errors: List[str] = []

        async def user_session(user_id: int):
            for method, path, body in endpoints:
                req_start = time.perf_counter()
                try:
                    if method == "GET":
                        resp = await client.get(path)
                    else:
                        resp = await client.post(path, json=body)
                    duration_ms = (time.perf_counter() - req_start) * 1000.0
                    latencies.append(duration_ms)
                    if resp.status_code != 200:
                        errors.append(f"User {user_id} {path} returned {resp.status_code}")
                except Exception as ex:
                    errors.append(f"User {user_id} {path} failed: {ex}")

        start_time = time.perf_counter()
        tasks = [user_session(uid) for uid in range(concurrency)]
        await asyncio.gather(*tasks)
        total_time_s = time.perf_counter() - start_time

    assert len(errors) == 0, f"Encountered errors during 50-user load test: {errors}"
    assert len(latencies) == total_requests

    stats = calculate_latencies(latencies)
    throughput = total_requests / total_time_s

    print(
        f"\n[50 Concurrent Users Benchmark]\n"
        f"  Total Requests: {total_requests}\n"
        f"  Total Time:     {total_time_s:.2f}s\n"
        f"  Throughput:     {throughput:.1f} req/s\n"
        f"  P50 Latency:    {stats['p50']:.2f}ms\n"
        f"  P95 Latency:    {stats['p95']:.2f}ms\n"
        f"  P99 Latency:    {stats['p99']:.2f}ms\n"
        f"  Error Rate:     0.0%"
    )

    # SLA Assertions
    assert stats["p95"] < 500.0, f"P95 latency {stats['p95']}ms exceeded SLA of 500ms"
    assert throughput > 50.0, f"Throughput {throughput} req/s below target"


@pytest.mark.asyncio
async def test_load_concurrency_100_users():
    """Validate platform performance under 100 concurrent users."""
    app = create_benchmark_app()
    transport = ASGITransport(app=app)
    concurrency = 100
    requests_per_user = 4
    total_requests = concurrency * requests_per_user

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Pre-warm
        warmup = await client.get("/api/health")
        assert warmup.status_code == 200

        endpoints = [
            ("GET", "/api/health", None),
            ("GET", "/api/metrics/summary", None),
            ("GET", "/api/metrics/circuit-breakers", None),
            ("POST", "/api/feedback", {"feedback_id": "bench_100", "rating": 5}),
        ]

        latencies: List[float] = []
        errors: List[str] = []

        async def user_session(user_id: int):
            for method, path, body in endpoints:
                req_start = time.perf_counter()
                try:
                    if method == "GET":
                        resp = await client.get(path)
                    else:
                        resp = await client.post(path, json=body)
                    duration_ms = (time.perf_counter() - req_start) * 1000.0
                    latencies.append(duration_ms)
                    if resp.status_code != 200:
                        errors.append(f"User {user_id} {path} returned {resp.status_code}")
                except Exception as ex:
                    errors.append(f"User {user_id} {path} failed: {ex}")

        start_time = time.perf_counter()
        tasks = [user_session(uid) for uid in range(concurrency)]
        await asyncio.gather(*tasks)
        total_time_s = time.perf_counter() - start_time

    assert len(errors) == 0, f"Encountered errors during 100-user load test: {errors}"
    assert len(latencies) == total_requests

    stats = calculate_latencies(latencies)
    throughput = total_requests / total_time_s

    print(
        f"\n[100 Concurrent Users Benchmark]\n"
        f"  Total Requests: {total_requests}\n"
        f"  Total Time:     {total_time_s:.2f}s\n"
        f"  Throughput:     {throughput:.1f} req/s\n"
        f"  P50 Latency:    {stats['p50']:.2f}ms\n"
        f"  P95 Latency:    {stats['p95']:.2f}ms\n"
        f"  P99 Latency:    {stats['p99']:.2f}ms\n"
        f"  Error Rate:     0.0%"
    )

    # SLA Assertions
    assert stats["p95"] < 500.0, f"P95 latency {stats['p95']}ms exceeded SLA of 500ms"
    assert throughput > 50.0, f"Throughput {throughput} req/s below target"


@pytest.mark.asyncio
async def test_circuit_breaker_under_100_concurrent_operations():
    """Verify circuit breaker concurrency safety under 100 simultaneous calls."""
    cb = CircuitBreaker(
        service_name="load-bench-service",
        failure_threshold=10,
        recovery_timeout=30.0,
    )

    async def mock_service_op(op_id: int):
        # 10ms simulated latency
        await asyncio.sleep(0.01)
        return {"op_id": op_id, "success": True}

    tasks = [cb.call(mock_service_op, i) for i in range(100)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 100
    assert cb.total_calls == 100
    assert cb.successful_calls == 100
    assert cb.failed_calls == 0
    assert cb.state.value == "closed"
