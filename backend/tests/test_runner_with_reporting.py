# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_runner_with_reporting.py
=============================
Comprehensive test runner with detailed metrics reporting and analysis.

Capabilities:
- Unified test execution across all 5 scenarios
- Real-time trace capture and metrics aggregation
- Component-level SLA validation
- Performance baseline establishment and comparison
- Multi-turn context preservation verification
- Detailed JSON/CSV export for analysis
- Summary dashboard and HTML reporting
"""

import json
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import statistics

from app.core.tracing import QueryTracingContext
from tests.test_metrics_validators import (
    LatencySLAThresholds,
    validate_query_trace,
    validate_all_component_latencies,
    validate_chat_history_preservation,
    validate_context_relevance_progression,
    ValidationReport,
)


@dataclass
class ScenarioRunResult:
    """Results for a single scenario execution."""
    scenario_name: str
    scenario_class_name: str
    turn_count: int
    passed_turns: int
    failed_turns: int
    total_latency_ms: float
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    total_tokens: int
    avg_tokens_per_turn: float
    vector_avg_candidates: float
    graph_avg_nodes: float
    graph_avg_edges: float
    ner_avg_entities: float
    llm_avg_input_tokens: float
    llm_avg_output_tokens: float
    validation_reports: List[ValidationReport]
    traces: List[QueryTracingContext]
    test_passed: bool
    errors: List[str]
    
    @property
    def pass_rate(self) -> float:
        return self.passed_turns / self.turn_count if self.turn_count > 0 else 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "scenario_class_name": self.scenario_class_name,
            "turn_count": self.turn_count,
            "passed_turns": self.passed_turns,
            "failed_turns": self.failed_turns,
            "pass_rate": f"{self.pass_rate:.1%}",
            "total_latency_ms": round(self.total_latency_ms, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "total_tokens": self.total_tokens,
            "avg_tokens_per_turn": round(self.avg_tokens_per_turn, 1),
            "vector_avg_candidates": round(self.vector_avg_candidates, 1),
            "graph_avg_nodes": round(self.graph_avg_nodes, 1),
            "graph_avg_edges": round(self.graph_avg_edges, 1),
            "ner_avg_entities": round(self.ner_avg_entities, 1),
            "llm_avg_input_tokens": round(self.llm_avg_input_tokens, 1),
            "llm_avg_output_tokens": round(self.llm_avg_output_tokens, 1),
            "test_passed": self.test_passed,
            "error_count": len(self.errors),
            "errors": self.errors,
        }


@dataclass
class TestExecutionSummary:
    """Summary of entire test execution."""
    test_run_id: str
    timestamp: datetime
    scenario_count: int
    total_turns: int
    total_passed: int
    total_failed: int
    scenarios: List[ScenarioRunResult]
    thresholds: LatencySLAThresholds
    
    @property
    def overall_pass_rate(self) -> float:
        return self.total_passed / self.total_turns if self.total_turns > 0 else 0
    
    @property
    def scenario_pass_count(self) -> int:
        return sum(1 for s in self.scenarios if s.test_passed)
    
    def get_latency_percentiles(self) -> Dict[str, float]:
        """Calculate latency percentiles across all scenarios."""
        all_latencies = []
        for scenario in self.scenarios:
            all_latencies.extend([t.get_total_latency_ms() for t in scenario.traces])
        
        if not all_latencies:
            return {}
        
        sorted_latencies = sorted(all_latencies)
        return {
            "min": min(all_latencies),
            "p50": statistics.median(all_latencies),
            "p95": sorted_latencies[int(len(sorted_latencies) * 0.95)] if len(sorted_latencies) > 1 else sorted_latencies[0],
            "p99": sorted_latencies[int(len(sorted_latencies) * 0.99)] if len(sorted_latencies) > 1 else sorted_latencies[0],
            "max": max(all_latencies),
            "mean": statistics.mean(all_latencies),
            "stdev": statistics.stdev(all_latencies) if len(all_latencies) > 1 else 0,
        }
    
    def get_token_statistics(self) -> Dict[str, int]:
        """Calculate token statistics across all scenarios."""
        all_input_tokens = []
        all_output_tokens = []
        
        for scenario in self.scenarios:
            for trace in scenario.traces:
                all_input_tokens.append(trace.llm_tokens_input)
                all_output_tokens.append(trace.llm_tokens_output)
        
        return {
            "total_input_tokens": sum(all_input_tokens),
            "total_output_tokens": sum(all_output_tokens),
            "avg_input_tokens": round(statistics.mean(all_input_tokens), 1) if all_input_tokens else 0,
            "avg_output_tokens": round(statistics.mean(all_output_tokens), 1) if all_output_tokens else 0,
        }


class TestRunnerWithReporting:
    """Comprehensive test runner with metrics collection and reporting."""
    
    def __init__(
        self,
        output_base_dir: Optional[Path] = None,
        thresholds: Optional[LatencySLAThresholds] = None,
    ):
        self.test_run_id = f"test-run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.output_base_dir = output_base_dir or Path("logs/test_runs")
        self.run_output_dir = self.output_base_dir / self.test_run_id
        self.run_output_dir.mkdir(parents=True, exist_ok=True)
        
        self.thresholds = thresholds or LatencySLAThresholds()
        self.scenarios: List[ScenarioRunResult] = []
        self.start_time = datetime.now()
    
    def run_scenario_test(
        self,
        scenario_class,
        scenario_name: str,
    ) -> ScenarioRunResult:
        """
        Execute a single scenario test with full tracing and validation.
        
        Args:
            scenario_class: Test scenario class (e.g., TestAdaniFinancialPerformance)
            scenario_name: Human-readable scenario name
            
        Returns:
            ScenarioRunResult with detailed metrics
        """
        print(f"\n{'='*80}")
        print(f"  SCENARIO: {scenario_name}")
        print('='*80)
        
        scenario_output_dir = self.run_output_dir / scenario_name.lower().replace(" ", "_")
        scenario_output_dir.mkdir(parents=True, exist_ok=True)
        
        result = ScenarioRunResult(
            scenario_name=scenario_name,
            scenario_class_name=scenario_class.__name__,
            turn_count=0,
            passed_turns=0,
            failed_turns=0,
            total_latency_ms=0.0,
            avg_latency_ms=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
            p99_latency_ms=0.0,
            total_tokens=0,
            avg_tokens_per_turn=0.0,
            vector_avg_candidates=0.0,
            graph_avg_nodes=0.0,
            graph_avg_edges=0.0,
            ner_avg_entities=0.0,
            llm_avg_input_tokens=0.0,
            llm_avg_output_tokens=0.0,
            validation_reports=[],
            traces=[],
            test_passed=False,
            errors=[],
        )
        
        try:
            # Instantiate scenario
            scenario = scenario_class()
            
            # Run all test methods (turn1, turn2, turn3, turn4, scenario_summary)
            test_methods = [
                ("turn1", "test_turn1_*"),
                ("turn2", "test_turn2_*"),
                ("turn3", "test_turn3_*"),
                ("turn4", "test_turn4_*"),
                ("summary", "test_scenario_summary"),
            ]
            
            for method_name, pattern in test_methods:
                # Find actual test method
                actual_method = None
                for attr_name in dir(scenario):
                    if attr_name.startswith(f"test_{method_name}"):
                        actual_method = getattr(scenario, attr_name)
                        break
                
                if actual_method and callable(actual_method):
                    try:
                        print(f"\n  Running {method_name}...")
                        
                        # Get fixture
                        if hasattr(scenario, "fixture"):
                            fixture = scenario.fixture()
                        else:
                            # Call fixture property/method
                            fixture_attr = getattr(scenario, "fixture")
                            if callable(fixture_attr):
                                fixture = fixture_attr()
                            else:
                                fixture = fixture_attr
                        
                        # Execute test
                        actual_method(fixture)
                        
                        # If it's a turn test, collect trace
                        if method_name.startswith("turn"):
                            if hasattr(fixture, "traces") and fixture.traces:
                                trace = fixture.traces[-1]
                                result.traces.append(trace)
                                result.turn_count += 1
                                result.passed_turns += 1
                                
                                # Validate trace
                                validation = validate_query_trace(
                                    trace,
                                    thresholds=self.thresholds,
                                    require_graph=True,
                                    require_citations=True
                                )
                                result.validation_reports.append(validation)
                                
                                if validation.pass_rate < 1.0:
                                    print(f"    Validation: {validation.pass_rate:.1%}")
                        
                        print(f"    ✓ {method_name} passed")
                        
                    except Exception as e:
                        result.failed_turns += 1
                        result.errors.append(f"{method_name}: {str(e)}")
                        print(f"    ✗ {method_name} failed: {e}")
            
            # Compute aggregated statistics
            if result.traces:
                latencies = [t.get_total_latency_ms() for t in result.traces]
                tokens = [t.get_total_tokens() for t in result.traces]
                vectors = [t.vector_db_candidates_reranked for t in result.traces]
                graph_nodes = [t.graph_nodes_retrieved for t in result.traces]
                graph_edges = [t.graph_edges_retrieved for t in result.traces]
                ner_entities = [
                    len(t.ner_entities_layer_a) + len(t.ner_entities_layer_b)
                    for t in result.traces
                ]
                llm_input = [t.llm_tokens_input for t in result.traces]
                llm_output = [t.llm_tokens_output for t in result.traces]
                
                result.total_latency_ms = sum(latencies)
                result.avg_latency_ms = statistics.mean(latencies)
                sorted_latencies = sorted(latencies)
                result.p50_latency_ms = statistics.median(latencies)
                result.p95_latency_ms = sorted_latencies[int(len(sorted_latencies) * 0.95)] if len(sorted_latencies) > 1 else sorted_latencies[0]
                result.p99_latency_ms = sorted_latencies[int(len(sorted_latencies) * 0.99)] if len(sorted_latencies) > 1 else sorted_latencies[0]
                
                result.total_tokens = sum(tokens)
                result.avg_tokens_per_turn = statistics.mean(tokens)
                result.vector_avg_candidates = statistics.mean(vectors)
                result.graph_avg_nodes = statistics.mean(graph_nodes)
                result.graph_avg_edges = statistics.mean(graph_edges)
                result.ner_avg_entities = statistics.mean(ner_entities)
                result.llm_avg_input_tokens = statistics.mean(llm_input)
                result.llm_avg_output_tokens = statistics.mean(llm_output)
            
            # Validate multi-turn context preservation
            if len(result.traces) > 1:
                chat_valid, chat_msg = validate_chat_history_preservation(result.traces)
                context_valid, context_msg = validate_context_relevance_progression(result.traces)
                
                if not chat_valid:
                    result.errors.append(f"Chat history: {chat_msg}")
                if not context_valid:
                    result.errors.append(f"Context: {context_msg}")
            
            result.test_passed = result.failed_turns == 0 and len(result.errors) == 0
            
        except Exception as e:
            result.errors.append(f"Scenario execution failed: {str(e)}")
            result.test_passed = False
            print(f"    ✗ Scenario failed: {e}")
        
        # Save scenario results
        self._save_scenario_results(result, scenario_output_dir)
        
        print(f"\n  Summary: {result.passed_turns}/{result.turn_count} turns passed")
        print(f"  Avg latency: {result.avg_latency_ms:.2f}ms | Avg tokens: {result.avg_tokens_per_turn:.0f}")
        print(f"  Test: {'✓ PASSED' if result.test_passed else '✗ FAILED'}")
        
        self.scenarios.append(result)
        return result
    
    def run_all_scenarios(self) -> TestExecutionSummary:
        """
        Run all five test scenarios.
        
        Returns:
            TestExecutionSummary with complete results
        """
        from tests.test_scenarios_with_tracing import (
            TestAdaniFinancialPerformance,
            TestFundManagerRelationships,
            TestMiningAndCoalBusiness,
            TestSEBIRegulatoryFramework,
            TestAdaniGroupVerticals,
        )
        
        scenarios = [
            (TestAdaniFinancialPerformance, "Adani Financial Performance"),
            (TestFundManagerRelationships, "Fund Manager Relationships"),
            (TestMiningAndCoalBusiness, "Mining and Coal Business"),
            (TestSEBIRegulatoryFramework, "SEBI Regulatory Framework"),
            (TestAdaniGroupVerticals, "Adani Group Verticals"),
        ]
        
        for scenario_class, scenario_name in scenarios:
            self.run_scenario_test(scenario_class, scenario_name)
        
        # Compute summary
        total_turns = sum(s.turn_count for s in self.scenarios)
        total_passed = sum(s.passed_turns for s in self.scenarios)
        total_failed = sum(s.failed_turns for s in self.scenarios)
        
        summary = TestExecutionSummary(
            test_run_id=self.test_run_id,
            timestamp=self.start_time,
            scenario_count=len(self.scenarios),
            total_turns=total_turns,
            total_passed=total_passed,
            total_failed=total_failed,
            scenarios=self.scenarios,
            thresholds=self.thresholds,
        )
        
        return summary
    
    def _save_scenario_results(self, result: ScenarioRunResult, output_dir: Path):
        """Save scenario results to various formats."""
        
        # Save JSON summary
        json_path = output_dir / "scenario_results.json"
        with open(json_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        
        # Save validation reports
        validation_path = output_dir / "validation_reports.json"
        with open(validation_path, "w") as f:
            json.dump([
                {
                    "test_name": v.test_name,
                    "passed": v.passed_count,
                    "failed": v.failed_count,
                    "total": v.total_count,
                    "pass_rate": f"{v.pass_rate:.1%}",
                    "failures": v.failures,
                }
                for v in result.validation_reports
            ], f, indent=2)
        
        # Save trace details (CSV for easy analysis)
        if result.traces:
            csv_path = output_dir / "traces.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "trace_id",
                    "query",
                    "query_type",
                    "latency_ms",
                    "vector_candidates",
                    "graph_nodes",
                    "graph_edges",
                    "ner_entities",
                    "llm_input_tokens",
                    "llm_output_tokens",
                    "citations_count",
                    "confidence",
                ])
                
                for trace in result.traces:
                    writer.writerow([
                        trace.trace_id,
                        trace.query_text[:50],
                        trace.query_type,
                        round(trace.get_total_latency_ms(), 2),
                        trace.vector_db_candidates_reranked,
                        trace.graph_nodes_retrieved,
                        trace.graph_edges_retrieved,
                        len(trace.ner_entities_layer_a) + len(trace.ner_entities_layer_b),
                        trace.llm_tokens_input,
                        trace.llm_tokens_output,
                        trace.citation_count,
                        trace.answer_confidence_label,
                    ])
    
    def generate_final_report(self, summary: TestExecutionSummary) -> Path:
        """
        Generate comprehensive final report.
        
        Returns:
            Path to generated report
        """
        report_path = self.run_output_dir / "TEST_EXECUTION_REPORT.md"
        
        latency_stats = summary.get_latency_percentiles()
        token_stats = summary.get_token_statistics()
        
        report_content = f"""# Test Execution Report

**Test Run ID:** {summary.test_run_id}  
**Timestamp:** {summary.timestamp.isoformat()}  
**Duration:** {(datetime.now() - summary.timestamp).total_seconds():.1f}s

## Executive Summary

- **Overall Pass Rate:** {summary.overall_pass_rate:.1%}
- **Scenarios Passed:** {summary.scenario_pass_count}/{summary.scenario_count}
- **Turns Passed:** {summary.total_passed}/{summary.total_turns}
- **Total Test Time:** {summary.total_turns * summary.get_latency_percentiles().get("mean", 0):.2f}ms (estimated)

## Performance Metrics

### Latency (ms)
| Metric | Value |
|--------|-------|
| Min | {latency_stats.get("min", 0):.2f} |
| P50 | {latency_stats.get("p50", 0):.2f} |
| P95 | {latency_stats.get("p95", 0):.2f} |
| P99 | {latency_stats.get("p99", 0):.2f} |
| Max | {latency_stats.get("max", 0):.2f} |
| Mean | {latency_stats.get("mean", 0):.2f} |
| Stdev | {latency_stats.get("stdev", 0):.2f} |

### Token Usage
| Metric | Value |
|--------|-------|
| Total Input Tokens | {token_stats.get("total_input_tokens", 0)} |
| Total Output Tokens | {token_stats.get("total_output_tokens", 0)} |
| Avg Input per Query | {token_stats.get("avg_input_tokens", 0):.1f} |
| Avg Output per Query | {token_stats.get("avg_output_tokens", 0):.1f} |

## Scenario Results

"""
        
        for i, scenario in enumerate(summary.scenarios, 1):
            status = "✓ PASSED" if scenario.test_passed else "✗ FAILED"
            report_content += f"""### {i}. {scenario.scenario_name}

**Status:** {status}  
**Turns:** {scenario.passed_turns}/{scenario.turn_count} passed ({scenario.pass_rate:.1%})  
**Avg Latency:** {scenario.avg_latency_ms:.2f}ms (p95: {scenario.p95_latency_ms:.2f}ms)  
**Avg Tokens:** {scenario.avg_tokens_per_turn:.0f}  
**Graph Coverage:** {scenario.graph_avg_nodes:.1f} nodes, {scenario.graph_avg_edges:.1f} edges  
**NER Entities:** {scenario.ner_avg_entities:.1f} avg  

"""
            if scenario.errors:
                report_content += f"**Errors:** {'; '.join(scenario.errors)}\n\n"
        
        # SLA Compliance
        report_content += f"""## SLA Compliance

| Component | Threshold (ms) | Status |
|-----------|----------------|--------|
| Vector DB | {summary.thresholds.vector_db_max_ms} | {'✓' if latency_stats.get('mean', 0) < summary.thresholds.vector_db_max_ms else '✗'} |
| Graph Traversal | {summary.thresholds.graph_traversal_max_ms} | {'✓' if latency_stats.get('mean', 0) < summary.thresholds.graph_traversal_max_ms else '✗'} |
| LLM Generation | {summary.thresholds.llm_generation_max_ms} | {'✓' if latency_stats.get('mean', 0) < summary.thresholds.llm_generation_max_ms else '✗'} |
| End-to-End | {summary.thresholds.end_to_end_max_ms} | {'✓' if latency_stats.get('mean', 0) < summary.thresholds.end_to_end_max_ms else '✗'} |

## Detailed Results

All detailed traces, validation reports, and metrics are available in:
- `logs/test_runs/{summary.test_run_id}/`

Each scenario includes:
- `scenario_results.json` - Aggregated metrics
- `validation_reports.json` - Validation details
- `traces.csv` - Query-level traces
- `trace_*/` - Individual trace JSON files

## Recommendations

"""
        
        # Generate recommendations
        if summary.overall_pass_rate < 1.0:
            report_content += f"- **Failing Tests:** Investigate {summary.total_failed} failed turns in detail\n"
        
        if latency_stats.get("p95", 0) > summary.thresholds.end_to_end_p95_ms:
            report_content += f"- **Latency:** P95 latency ({latency_stats.get('p95', 0):.0f}ms) exceeds SLA ({summary.thresholds.end_to_end_p95_ms}ms)\n"
        
        if token_stats.get("total_input_tokens", 0) > 50000:
            report_content += f"- **Token Usage:** Consider optimizing context window usage\n"
        
        report_content += "\n---\n*Report generated by test_runner_with_reporting.py*\n"
        
        with open(report_path, "w") as f:
            f.write(report_content)
        
        return report_path
    
    def print_summary(self, summary: TestExecutionSummary):
        """Print human-readable summary to console."""
        print("\n" + "="*80)
        print("  TEST EXECUTION SUMMARY")
        print("="*80)
        print(f"  Test Run: {summary.test_run_id}")
        print(f"  Overall Pass Rate: {summary.overall_pass_rate:.1%}")
        print(f"  Scenarios: {summary.scenario_pass_count}/{summary.scenario_count} passed")
        print(f"  Turns: {summary.total_passed}/{summary.total_turns} passed")
        print()
        
        latency_stats = summary.get_latency_percentiles()
        print(f"  Latency (ms):")
        print(f"    Mean: {latency_stats.get('mean', 0):.2f}")
        print(f"    P95: {latency_stats.get('p95', 0):.2f}")
        print(f"    P99: {latency_stats.get('p99', 0):.2f}")
        print()
        
        token_stats = summary.get_token_statistics()
        print(f"  Tokens:")
        print(f"    Total: {token_stats.get('total_input_tokens', 0) + token_stats.get('total_output_tokens', 0)}")
        print(f"    Avg per Query: {token_stats.get('avg_input_tokens', 0) + token_stats.get('avg_output_tokens', 0):.0f}")
        print()
        
        print(f"  Output: {self.run_output_dir}")
        print("="*80 + "\n")


if __name__ == "__main__":
    """CLI entry point for running all tests."""
    import sys
    
    runner = TestRunnerWithReporting()
    
    print("\nStarting comprehensive test suite with tracing...")
    summary = runner.run_all_scenarios()
    
    runner.print_summary(summary)
    report_path = runner.generate_final_report(summary)
    
    print(f"Report saved to: {report_path}\n")
    
    # Exit with appropriate code
    sys.exit(0 if summary.overall_pass_rate == 1.0 else 1)
