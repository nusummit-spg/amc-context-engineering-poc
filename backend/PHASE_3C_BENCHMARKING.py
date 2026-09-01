#!/usr/bin/env python3
# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

"""
PHASE_3C_BENCHMARKING.py
========================
Comprehensive benchmarking of Python vs Rust compliance rules engine.

Compares:
1. Python sequential (baseline)
2. Python multiprocessing (for comparison)
3. Rust sequential (via ctypes FFI)

Measures:
- Total wall-clock time
- Per-fund evaluation time
- Rule compilation time (amortized)
- Speedup factors
"""

import time
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("benchmarking")


# ===========================================================================
# Test Data
# ===========================================================================

SAMPLE_RULES = [
    {
        "id": "RULE_001",
        "title": "Max Sector Holding",
        "condition": "holdings.max_sector_holding > 0.30",
        "severity": "high",
        "confidence_threshold": 0.95,
        "applicability": ["equity", "balanced"],
        "exclusions": [],
        "region": "SEBI"
    },
    {
        "id": "RULE_002",
        "title": "Portfolio Concentration",
        "condition": "holdings.concentration_index > 0.35",
        "severity": "high",
        "confidence_threshold": 0.95,
        "applicability": [],
        "exclusions": [],
        "region": "SEBI"
    },
    {
        "id": "RULE_003",
        "title": "Min Fund Size",
        "condition": "metadata.aum_crores < 10.0",
        "severity": "low",
        "confidence_threshold": 0.90,
        "applicability": [],
        "exclusions": ["small_cap"],
        "region": "SEBI"
    },
    {
        "id": "RULE_004",
        "title": "Debt Exposure",
        "condition": "asset_allocation.debt_percent > 0.60",
        "severity": "medium",
        "confidence_threshold": 0.95,
        "applicability": ["debt", "balanced"],
        "exclusions": [],
        "region": "SEBI"
    },
    {
        "id": "RULE_005",
        "title": "Derivative Exposure",
        "condition": "holdings.derivative_percent > 0.20",
        "severity": "high",
        "confidence_threshold": 0.95,
        "applicability": [],
        "exclusions": ["derivative_fund"],
        "region": "SEBI"
    },
]


def generate_sample_funds(count: int) -> List[Dict[str, Any]]:
    """Generate synthetic fund data for testing"""
    import random
    
    funds = []
    for i in range(count):
        fund = {
            "fund_id": f"FUND_{i:05d}",
            "category": random.choice(["equity", "debt", "balanced", "liquid"]),
            "holdings": {
                "max_sector_holding": random.uniform(0.10, 0.50),
                "concentration_index": random.uniform(0.20, 0.60),
                "derivative_percent": random.uniform(0.05, 0.30),
            },
            "metadata": {
                "aum_crores": random.uniform(5.0, 100.0),
            },
            "asset_allocation": {
                "debt_percent": random.uniform(0.10, 0.80),
                "equity_percent": random.uniform(0.20, 0.80),
            },
        }
        funds.append(fund)
    
    return funds


# ===========================================================================
# Python Baseline
# ===========================================================================

def compile_rules_python(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compile rules (Python version - minimal impl for timing)"""
    # In real scenario, this would parse conditions, extract metric paths, etc.
    return rules


def evaluate_fund_python(fund: Dict[str, Any], rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Evaluate fund against rules (Python version - simplified)"""
    violations = []
    
    for rule in rules:
        # Simplified: just parse and compare basic condition
        condition = rule["condition"]
        parts = condition.split()  # e.g., "holdings.max_sector_holding > 0.30"
        
        if len(parts) >= 3:
            metric_path = parts[0].split(".")
            operator = parts[1]
            threshold = float(parts[2])
            
            # Extract metric
            value = fund
            for key in metric_path:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = None
                    break
            
            if value is not None and isinstance(value, (int, float)):
                violated = False
                if operator == ">":
                    violated = value > threshold
                elif operator == "<":
                    violated = value < threshold
                elif operator == ">=":
                    violated = value >= threshold
                elif operator == "<=":
                    violated = value <= threshold
                
                if violated:
                    violations.append({
                        "rule_id": rule["id"],
                        "fund_id": fund["fund_id"],
                        "actual_value": value,
                        "threshold_value": threshold,
                    })
    
    return violations


def benchmark_python_sequential(funds: List[Dict], rules: List[Dict]) -> Tuple[float, int]:
    """Benchmark Python sequential evaluation"""
    compiled = compile_rules_python(rules)
    
    start = time.perf_counter()
    
    all_violations = []
    for fund in funds:
        violations = evaluate_fund_python(fund, compiled)
        all_violations.extend(violations)
    
    elapsed = time.perf_counter() - start
    
    return elapsed, len(all_violations)


# ===========================================================================
# Rust via FFI
# ===========================================================================

def benchmark_rust_sequential(funds: List[Dict], rules: List[Dict]) -> Tuple[float, int]:
    """Benchmark Rust sequential evaluation"""
    try:
        from app.compliance.rules_engine_rust import RulesEngineRustWrapper
        
        wrapper = RulesEngineRustWrapper()
        
        if not wrapper.is_available:
            logger.warning("Rust library not available, skipping Rust benchmark")
            return None, 0
        
        # Compile rules (one-time cost)
        start_compile = time.perf_counter()
        wrapper.compile_rules(rules)
        compile_time = time.perf_counter() - start_compile
        
        # Evaluate all funds (rules already compiled)
        start_eval = time.perf_counter()
        violations = wrapper.evaluate_funds_batch(funds)  # No rules arg needed
        eval_time = time.perf_counter() - start_eval
        
        total_time = compile_time + eval_time
        
        logger.info(f"Rust compile time: {compile_time*1000:.2f}ms")
        logger.info(f"Rust eval time: {eval_time*1000:.2f}ms")
        
        return total_time, len(violations)
    
    except Exception as e:
        logger.error(f"Rust benchmark failed: {e}", exc_info=True)
        return None, 0


# ===========================================================================
# Main Benchmarking
# ===========================================================================

@dataclass
class BenchmarkResult:
    name: str
    fund_count: int
    rule_count: int
    total_time_ms: float
    per_fund_time_ms: float
    violations_count: int
    speedup: Optional[float] = None


def run_benchmarks():
    """Run all benchmarks"""
    
    # Test sizes
    test_sizes = [50, 100, 500]
    
    all_results = []
    
    for size in test_sizes:
        logger.info(f"\n{'='*70}")
        logger.info(f"Benchmarking with {size} funds and {len(SAMPLE_RULES)} rules")
        logger.info(f"{'='*70}")
        
        funds = generate_sample_funds(size)
        rules = SAMPLE_RULES
        
        # Python baseline
        logger.info(f"\n[1/2] Python Sequential...")
        py_time, py_violations = benchmark_python_sequential(funds, rules)
        py_result = BenchmarkResult(
            name="Python Sequential",
            fund_count=size,
            rule_count=len(rules),
            total_time_ms=py_time * 1000,
            per_fund_time_ms=(py_time * 1000) / size,
            violations_count=py_violations,
        )
        all_results.append(py_result)
        logger.info(f"Python: {py_time*1000:.2f}ms total, {py_result.per_fund_time_ms:.4f}ms/fund, {py_violations} violations")
        
        # Rust benchmark
        logger.info(f"\n[2/2] Rust Sequential...")
        rust_time, rust_violations = benchmark_rust_sequential(funds, rules)
        
        if rust_time is not None:
            speedup = py_time / rust_time
            rust_result = BenchmarkResult(
                name="Rust Sequential",
                fund_count=size,
                rule_count=len(rules),
                total_time_ms=rust_time * 1000,
                per_fund_time_ms=(rust_time * 1000) / size,
                violations_count=rust_violations,
                speedup=speedup,
            )
            all_results.append(rust_result)
            logger.info(f"Rust: {rust_time*1000:.2f}ms total, {rust_result.per_fund_time_ms:.4f}ms/fund, {rust_violations} violations")
            logger.info(f">>> SPEEDUP: {speedup:.2f}x <<<")
        else:
            logger.warning("Rust benchmark failed")
    
    # Summary report
    logger.info(f"\n{'='*70}")
    logger.info("SUMMARY REPORT")
    logger.info(f"{'='*70}\n")
    
    for result in all_results:
        print(f"{result.name} ({result.fund_count} funds):")
        print(f"  Total:    {result.total_time_ms:.2f}ms")
        print(f"  Per-fund: {result.per_fund_time_ms:.4f}ms")
        print(f"  Violations: {result.violations_count}")
        if result.speedup:
            print(f"  Speedup: {result.speedup:.2f}x")
        print()
    
    return all_results


if __name__ == "__main__":
    logger.info("Starting Phase 3c Benchmarking...")
    results = run_benchmarks()
    logger.info("Benchmarking complete.")
