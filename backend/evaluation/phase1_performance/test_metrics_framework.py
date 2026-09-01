# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
Task 1.1: Establish Evaluation Baseline & Metrics Framework
Collects and tracks metrics across all 7 dimensions.
"""
import pytest
import time
import json
from typing import Dict, List
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class MetricsBaseline:
    """Success criteria for each dimension"""
    # Performance
    p50_latency_ms: float = 150.0
    p95_latency_ms: float = 300.0  # SaaS target
    p99_latency_ms: float = 500.0  # vendor target
    throughput_queries_per_sec: float = 10.0
    cache_hit_rate: float = 0.90

    # Compliance
    sebi_adherence_rate: float = 1.0  # 100%
    regulatory_violation_count: int = 0

    # Security
    owasp_coverage: float = 1.0  # all 10 categories
    injection_blocking_rate: float = 1.0  # 100%

    # Agentic
    multiturn_success_rate: float = 0.95
    domain_accuracy: float = 0.90
    constraint_satisfaction_rate: float = 1.0
    error_recovery_rate: float = 1.0

    # Cost
    cost_per_query_usd: float = 0.10
    token_savings_vs_traditional: float = 0.50  # 50% reduction

    # Transparency
    citation_accuracy: float = 1.0  # 100%
    audit_trail_completeness: float = 1.0
    explainability_score: float = 0.85

    # Adversarial
    adversarial_pass_rate: float = 0.95  # <5% compromise

class MetricsCollector:
    """Collects and tracks all evaluation metrics"""

    def __init__(self):
        self.metrics = {
            "performance": [],
            "compliance": [],
            "security": [],
            "agentic": [],
            "cost": [],
            "transparency": [],
            "adversarial": []
        }
        self.baseline = MetricsBaseline()
        self.results_dir = Path("evaluation/results")
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def collect_latency(self, query: str, mode: str = "contextgraph") -> Dict:
        """Collect latency metrics for a query"""
        start = time.perf_counter()
        try:
            from app.retrieval.orchestrator import run_contextgraph_query
            result = run_contextgraph_query(query)
            success = True
            error = None
        except Exception as e:
            result = None
            success = False
            error = str(e)

        end = time.perf_counter()
        latency_ms = (end - start) * 1000

        metric = {
            "query": query,
            "mode": mode,
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
            "timestamp": time.time()
        }

        self.metrics["performance"].append(metric)
        return metric

    def calculate_percentiles(self) -> Dict:
        """Calculate P50/P95/P99 latencies"""
        latencies = [m["latency_ms"] for m in self.metrics["performance"] if m["success"]]
        latencies.sort()

        n = len(latencies)
        if n == 0:
            return {"p50": 0, "p95": 0, "p99": 0, "count": 0}

        return {
            "p50": latencies[int(n * 0.50)] if n > 1 else latencies[0],
            "p95": latencies[min(int(n * 0.95), n-1)],
            "p99": latencies[min(int(n * 0.99), n-1)],
            "count": n,
            "min": latencies[0],
            "max": latencies[-1],
            "mean": sum(latencies) / n
        }

    def check_against_baseline(self) -> Dict:
        """Compare current metrics against baseline"""
        percentiles = self.calculate_percentiles()

        results = {
            "p50_pass": percentiles["p50"] <= self.baseline.p50_latency_ms if percentiles["count"] > 0 else None,
            "p95_pass": percentiles["p95"] <= self.baseline.p95_latency_ms if percentiles["count"] > 0 else None,
            "p99_pass": percentiles["p99"] <= self.baseline.p99_latency_ms if percentiles["count"] > 0 else None,
            "percentiles": percentiles,
            "baseline": asdict(self.baseline)
        }

        return results

    def save_results(self, filename: str = "metrics_baseline.json"):
        """Save metrics to JSON file"""
        results = self.check_against_baseline()
        results["all_metrics"] = self.metrics

        output_path = self.results_dir / filename
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        print(f" Metrics saved to {output_path}")
        return output_path

# Test cases
def test_metrics_framework_initialization():
    """Test that metrics framework initializes correctly"""
    collector = MetricsCollector()
    assert collector.baseline.p95_latency_ms == 300.0
    assert collector.baseline.sebi_adherence_rate == 1.0
    assert collector.baseline.adversarial_pass_rate == 0.95
    print(" Metrics framework initialized successfully")

def test_latency_collection():
    """Test latency metric collection"""
    collector = MetricsCollector()

    # Collect metrics for sample query
    metric = collector.collect_latency("What is the overlap limit for thematic funds?")

    assert "latency_ms" in metric
    assert metric["latency_ms"] > 0
    assert "query" in metric
    print(f" Latency collection works: {metric['latency_ms']:.2f}ms")

def test_percentile_calculation():
    """Test percentile calculation logic"""
    collector = MetricsCollector()

    # Simulate some latency measurements
    for i in range(100):
        collector.metrics["performance"].append({
            "latency_ms": i * 10,
            "success": True
        })

    percentiles = collector.calculate_percentiles()

    assert "p50" in percentiles
    assert "p95" in percentiles
    assert "p99" in percentiles
    assert percentiles["p95"] > percentiles["p50"]
    print(f" Percentile calculation: P50={percentiles['p50']}, P95={percentiles['p95']}, P99={percentiles['p99']}")

def test_baseline_comparison():
    """Test baseline comparison logic"""
    collector = MetricsCollector()

    # Add some good latencies (under baseline)
    for i in range(10):
        collector.metrics["performance"].append({
            "latency_ms": 200.0,  # Under P95 baseline of 300ms
            "success": True
        })

    results = collector.check_against_baseline()

    assert results["p95_pass"] == True
    print(f" Baseline comparison works: P95={results['percentiles']['p95']:.2f}ms (pass={results['p95_pass']})")

if __name__ == "__main__":
    # Run standalone demo
    print("\n" + "="*60)
    print("METRICS FRAMEWORK DEMO")
    print("="*60 + "\n")

    collector = MetricsCollector()
    print(f" Baseline P95 latency: {collector.baseline.p95_latency_ms}ms")
    print(f" Baseline Cost/Query: ${collector.baseline.cost_per_query_usd}")
    print(f" Baseline Adversarial Pass Rate: {collector.baseline.adversarial_pass_rate * 100}%")

    # Run tests
    pytest.main([__file__, "-v"])
