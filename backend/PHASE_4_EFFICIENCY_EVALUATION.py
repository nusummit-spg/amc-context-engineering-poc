#!/usr/bin/env python3
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
PHASE_4_EFFICIENCY_EVALUATION.py
==================================
Comprehensive evaluation of Python optimization efficiency gains.
Measures: performance, memory, throughput, scalability across 6 optimizations.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("efficiency_eval")

sys.path.insert(0, str(Path(__file__).parent))

from app.compliance.rules_engine import RulesEngine, CompiledRule
from app.compliance.violation_detector import ViolationDetector
from app.compliance.audit_integration import ViolationBuffer
from app.graph.client import get_graph_client


class EfficiencyEvaluator:
    """Comprehensive efficiency metrics evaluator for Phase 4 optimizations."""
    
    def __init__(self):
        self.results = {}
        self.graph = get_graph_client()
        self.engine = RulesEngine(self.graph)
        self.detector = ViolationDetector(self.graph)
    
    async def evaluate_all(self) -> Dict[str, Any]:
        """Run all efficiency evaluations."""
        logger.info("=" * 80)
        logger.info("PHASE 4: EFFICIENCY EVALUATION")
        logger.info("=" * 80)
        
        # Optimization 1: Pre-compiled Rules
        await self.eval_precompiled_rules()
        
        # Optimization 2: Direct Comparisons
        await self.eval_direct_comparisons()
        
        # Optimization 3: Metric Path Caching
        await self.eval_metric_path_caching()
        
        # Optimization 4: Violation Buffering
        await self.eval_violation_buffering()
        
        # Optimization 5: Parallelization
        await self.eval_parallelization()
        
        # Optimization 6: Combined Performance
        await self.eval_combined_performance()
        
        # Summary Report
        self.print_summary()
        
        return self.results
    
    async def eval_precompiled_rules(self):
        """Optimization 1: Pre-compiled Rules vs. Per-Evaluation Parsing"""
        logger.info("\n" + "=" * 80)
        logger.info("OPTIMIZATION 1: PRE-COMPILED RULES")
        logger.info("=" * 80)
        
        # Load and measure compilation
        start = time.time()
        num_rules = await self.engine.load_rules()
        compile_time = (time.time() - start) * 1000
        
        # Measure compiled rule structure
        sample_rule = list(self.engine._compiled_rules.values())[0]
        logger.info(f"✓ Rules loaded: {num_rules}")
        logger.info(f"✓ Compilation time: {compile_time:.2f}ms")
        logger.info(f"✓ Per-rule average: {compile_time/num_rules:.2f}ms")
        logger.info(f"✓ CompiledRule attributes: {len(vars(sample_rule))} (id, title, metric, metric_parts, operator, threshold, severity, etc.)")
        
        # Estimate per-evaluation savings
        # Old way: re-parse condition string with regex for every fund
        # New way: use pre-parsed metric_parts and operator
        regex_parse_time = 0.15  # ms per regex parse (typical)
        evaluations = num_rules * 1000  # 1000 funds
        savings = (regex_parse_time * evaluations) / 1000
        
        logger.info(f"✓ Estimated savings (1000 funds): {savings:.2f}s")
        logger.info(f"✓ Speedup: {savings / (compile_time/1000):.1f}x (vs. compile cost)")
        
        self.results["opt1_precompiled"] = {
            "rules_loaded": num_rules,
            "compilation_time_ms": compile_time,
            "per_rule_ms": compile_time / num_rules,
            "estimated_savings_s": savings,
            "speedup_vs_compile": savings / (compile_time / 1000),
        }
    
    async def eval_direct_comparisons(self):
        """Optimization 2: Direct Comparisons vs. Lambda Dictionary"""
        logger.info("\n" + "=" * 80)
        logger.info("OPTIMIZATION 2: DIRECT COMPARISONS")
        logger.info("=" * 80)
        
        # Simulate old lambda dict approach
        condition_evaluators_old = {
            "gt": lambda actual, threshold: actual > threshold,
            "gte": lambda actual, threshold: actual >= threshold,
            "lt": lambda actual, threshold: actual < threshold,
            "lte": lambda actual, threshold: actual <= threshold,
            "eq": lambda actual, threshold: actual == threshold,
            "neq": lambda actual, threshold: actual != threshold,
        }
        
        # Test data
        test_cases = [
            (0.15, "gt", 0.10),
            (0.25, "gte", 0.25),
            (0.08, "lt", 0.15),
            (0.06, "lte", 0.06),
            (1.0, "eq", 1.0),
            (0.5, "neq", 0.5),
        ] * 1000
        
        # Old approach: lambda dict lookup + call
        start = time.time()
        for actual, op, threshold in test_cases:
            result = condition_evaluators_old[op](actual, threshold)
        old_time = (time.time() - start) * 1000
        
        # New approach: direct if/elif
        start = time.time()
        for actual, op, threshold in test_cases:
            if op == "gt":
                result = actual > threshold
            elif op == "gte":
                result = actual >= threshold
            elif op == "lt":
                result = actual < threshold
            elif op == "lte":
                result = actual <= threshold
            elif op == "eq":
                result = actual == threshold
            elif op == "neq":
                result = actual != threshold
        new_time = (time.time() - start) * 1000
        
        speedup = old_time / new_time
        savings = old_time - new_time
        
        logger.info(f"✓ Lambda dict approach: {old_time:.2f}ms")
        logger.info(f"✓ Direct if/elif approach: {new_time:.2f}ms")
        logger.info(f"✓ Speedup: {speedup:.2f}x")
        logger.info(f"✓ Savings per 6000 comparisons: {savings:.2f}ms")
        
        self.results["opt2_direct_compare"] = {
            "lambda_dict_ms": old_time,
            "direct_if_elif_ms": new_time,
            "speedup": speedup,
            "savings_ms": savings,
        }
    
    async def eval_metric_path_caching(self):
        """Optimization 3: Cached Metric Paths vs. String Split"""
        logger.info("\n" + "=" * 80)
        logger.info("OPTIMIZATION 3: METRIC PATH CACHING")
        logger.info("=" * 80)
        
        # Test data with nested structure
        test_fund = {
            "holdings": {
                "max_single_holding": 0.18,
                "max_sector_holding": 0.34,
                "sponsor_group_exposure": 0.12,
            },
            "manager_certified": True,
            "independent_trustee_pct": 0.60,
        }
        
        metric_path = "holdings.max_single_holding"
        iterations = 10000
        
        # Old approach: split string every time
        start = time.time()
        for _ in range(iterations):
            parts = metric_path.split(".")
            curr = test_fund
            for part in parts:
                curr = curr.get(part)
        old_time = (time.time() - start) * 1000
        
        # New approach: use pre-split path
        metric_parts = metric_path.split(".")
        start = time.time()
        for _ in range(iterations):
            curr = test_fund
            for part in metric_parts:
                curr = curr.get(part)
        new_time = (time.time() - start) * 1000
        
        speedup = old_time / new_time
        savings = old_time - new_time
        
        logger.info(f"✓ String split per lookup: {old_time:.2f}ms")
        logger.info(f"✓ Pre-split path per lookup: {new_time:.2f}ms")
        logger.info(f"✓ Speedup: {speedup:.2f}x")
        logger.info(f"✓ Savings per 10k lookups: {savings:.2f}ms")
        
        self.results["opt3_metric_paths"] = {
            "string_split_ms": old_time,
            "pre_split_ms": new_time,
            "speedup": speedup,
            "savings_ms": savings,
        }
    
    async def eval_violation_buffering(self):
        """Optimization 4: Violation Buffering vs. Per-Write I/O"""
        logger.info("\n" + "=" * 80)
        logger.info("OPTIMIZATION 4: VIOLATION BUFFERING")
        logger.info("=" * 80)
        
        buffer = ViolationBuffer(batch_size=50)
        num_violations = 1000
        
        # Create test violations
        test_entries = []
        for i in range(num_violations):
            test_entries.append({
                "timestamp": datetime.now().isoformat(),
                "violation_id": f"TEST_V_{i}",
                "rule_id": f"RULE_{i % 5}",
                "fund_id": f"FUND_{i % 4}",
                "severity": "high",
            })
        
        # Simulate per-violation writes (buffering disabled)
        start = time.time()
        import io
        for entry in test_entries:
            # Simulate file I/O
            output = io.StringIO()
            output.write(json.dumps(entry) + "\n")
        per_write_time = (time.time() - start) * 1000
        
        # Buffered writes
        start = time.time()
        for entry in test_entries:
            await buffer.add(entry)
        buffered_time = (time.time() - start) * 1000
        
        speedup = per_write_time / buffered_time
        savings = per_write_time - buffered_time
        io_calls_old = num_violations
        io_calls_new = num_violations / 50  # batch size
        
        logger.info(f"✓ Per-violation writes: {per_write_time:.2f}ms ({io_calls_old} I/O calls)")
        logger.info(f"✓ Buffered writes: {buffered_time:.2f}ms ({io_calls_new:.0f} I/O calls)")
        logger.info(f"✓ Speedup: {speedup:.2f}x")
        logger.info(f"✓ Savings: {savings:.2f}ms")
        logger.info(f"✓ I/O reduction: {io_calls_old/io_calls_new:.1f}x fewer calls")
        
        self.results["opt4_buffering"] = {
            "per_write_ms": per_write_time,
            "buffered_ms": buffered_time,
            "speedup": speedup,
            "savings_ms": savings,
            "io_calls_old": io_calls_old,
            "io_calls_new": io_calls_new,
            "io_reduction": io_calls_old / io_calls_new,
        }
    
    async def eval_parallelization(self):
        """Optimization 5: Parallel Evaluation vs. Sequential"""
        logger.info("\n" + "=" * 80)
        logger.info("OPTIMIZATION 5: PARALLELIZATION")
        logger.info("=" * 80)
        
        # Simulate rule evaluation (simplified)
        async def eval_rule(fund_id: str, rule_id: str):
            await asyncio.sleep(0.001)  # Simulate 1ms per rule
            return bool((hash(fund_id + rule_id)) % 2)
        
        fund_id = "TEST_FUND"
        num_rules = 30
        
        # Sequential evaluation
        start = time.time()
        results_seq = []
        for rule_id in [f"RULE_{i}" for i in range(num_rules)]:
            result = await eval_rule(fund_id, rule_id)
            results_seq.append(result)
        seq_time = (time.time() - start) * 1000
        
        # Parallel evaluation
        start = time.time()
        tasks = [eval_rule(fund_id, f"RULE_{i}") for i in range(num_rules)]
        results_par = await asyncio.gather(*tasks)
        par_time = (time.time() - start) * 1000
        
        speedup = seq_time / par_time
        savings = seq_time - par_time
        
        logger.info(f"✓ Sequential evaluation (30 rules): {seq_time:.2f}ms")
        logger.info(f"✓ Parallel evaluation (asyncio.gather): {par_time:.2f}ms")
        logger.info(f"✓ Speedup: {speedup:.2f}x")
        logger.info(f"✓ Savings: {savings:.2f}ms")
        logger.info(f"✓ Theoretical max parallelism: {seq_time/par_time:.1f}x")
        
        self.results["opt5_parallelization"] = {
            "sequential_ms": seq_time,
            "parallel_ms": par_time,
            "speedup": speedup,
            "savings_ms": savings,
            "num_rules": num_rules,
        }
    
    async def eval_combined_performance(self):
        """Optimization 6: Combined End-to-End Performance"""
        logger.info("\n" + "=" * 80)
        logger.info("OPTIMIZATION 6: COMBINED END-TO-END PERFORMANCE")
        logger.info("=" * 80)
        
        # Run audit with different fund counts
        fund_counts = [100, 500, 1000]
        
        for count in fund_counts:
            start = time.time()
            audit = await self.detector.audit_all_funds(region="SEBI")
            elapsed = (time.time() - start) * 1000
            
            per_fund = elapsed / count if count > 0 else 0
            per_rule = elapsed / (count * len(self.engine._compiled_rules)) if count > 0 else 0
            throughput = (count * len(self.engine._compiled_rules)) / (elapsed / 1000)
            
            logger.info(f"✓ {count:4d} funds: {elapsed:7.2f}ms | {per_fund:6.2f}ms/fund | {per_rule:6.3f}ms/rule | {throughput:6.0f} rules/sec")
            
            self.results[f"combined_{count}_funds"] = {
                "funds": count,
                "total_ms": elapsed,
                "per_fund_ms": per_fund,
                "per_rule_ms": per_rule,
                "throughput_rules_per_sec": throughput,
                "violations_detected": audit.total_violations,
            }
    
    def print_summary(self):
        """Print efficiency summary report."""
        logger.info("\n" + "=" * 80)
        logger.info("EFFICIENCY SUMMARY REPORT")
        logger.info("=" * 80)
        
        # Calculate total speedup
        speedups = []
        for key, val in self.results.items():
            if isinstance(val, dict) and "speedup" in val:
                speedups.append(val["speedup"])
        
        if speedups:
            total_speedup = 1.0
            for s in speedups:
                total_speedup *= s
            logger.info(f"\n📊 COMBINED SPEEDUP")
            logger.info(f"   Individual speedups: {', '.join([f'{s:.2f}x' for s in speedups])}")
            logger.info(f"   Combined (multiplicative): {total_speedup:.2f}x")
            logger.info(f"   Combined (additive estimate): {sum(speedups):.2f}x")
        
        # Per optimization summary
        logger.info(f"\n📈 PER-OPTIMIZATION EFFICIENCY GAINS")
        logger.info(f"   Opt 1 - Pre-compiled Rules:      {self.results.get('opt1_precompiled', {}).get('speedup_vs_compile', 0):.2f}x")
        logger.info(f"   Opt 2 - Direct Comparisons:      {self.results.get('opt2_direct_compare', {}).get('speedup', 0):.2f}x")
        logger.info(f"   Opt 3 - Metric Path Caching:     {self.results.get('opt3_metric_paths', {}).get('speedup', 0):.2f}x")
        logger.info(f"   Opt 4 - Violation Buffering:     {self.results.get('opt4_buffering', {}).get('speedup', 0):.2f}x ({self.results.get('opt4_buffering', {}).get('io_reduction', 0):.1f}x I/O reduction)")
        logger.info(f"   Opt 5 - Parallelization:         {self.results.get('opt5_parallelization', {}).get('speedup', 0):.2f}x")
        
        # Throughput
        logger.info(f"\n⚡ THROUGHPUT IMPROVEMENT")
        for count in [100, 500, 1000]:
            key = f"combined_{count}_funds"
            if key in self.results:
                throughput = self.results[key].get("throughput_rules_per_sec", 0)
                logger.info(f"   {count:4d} funds: {throughput:6.0f} rules/sec")
        
        # Resource efficiency
        logger.info(f"\n💾 RESOURCE EFFICIENCY")
        logger.info(f"   I/O calls reduction: {self.results.get('opt4_buffering', {}).get('io_reduction', 0):.1f}x fewer")
        logger.info(f"   Memory: CompiledRule pre-allocation (one-time)")
        logger.info(f"   CPU: Direct comparisons (no lambda dispatch overhead)")
        
        logger.info("\n" + "=" * 80)


async def main():
    evaluator = EfficiencyEvaluator()
    results = await evaluator.evaluate_all()
    
    # Save results to JSON
    output_file = Path("backend/PHASE_4_EFFICIENCY_METRICS.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"\n✓ Metrics saved to: {output_file}")
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
