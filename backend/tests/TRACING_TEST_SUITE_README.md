# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Comprehensive Multi-Turn Query Testing with End-to-End Tracing

## Overview

This test suite captures and traces **every metric across all components** for multi-turn queries, providing complete observability into:

- **Vector DB Retrieval:** Candidate counts, reranking scores, bypass decisions
- **Graph Traversal:** Node/edge counts, entity matching, traversal depth
- **NER Pipeline:** Layer A/B entity extraction, disambiguation
- **Entity Resolution:** Similarity matching, confidence scores
- **Context Preservation:** Multi-turn history compression, context propagation
- **LLM Integration:** Token counts (input/output/cached), model used, cost
- **Response Quality:** Citations, confidence labels, answer correctness

## Architecture

### Core Components

```
backend/app/core/tracing.py
├── QueryTracingContext          # Single source of truth for all metrics
├── ComponentMetrics             # Per-component latency and metrics
├── CacheMetrics                 # Cache hit/miss and savings
└── EntityResolutionMetrics      # Entity resolution quality metrics

backend/tests/test_multiturn_queries_with_tracing.py
├── MultiTurnQueryTestFixture    # Base class for multi-turn tests
├── _validate_query_turn()       # Per-turn assertion helpers
└── Aggregation helpers          # Cross-turn statistics

backend/tests/test_scenarios_with_tracing.py
├── TestAdaniFinancialPerformance        # Scenario 1: Financial metrics + comparisons
├── TestFundManagerRelationships         # Scenario 2: Graph traversal + entity linking
├── TestMiningAndCoalBusiness            # Scenario 3: Domain-specific extraction
├── TestSEBIRegulatoryFramework          # Scenario 4: Regulatory comparisons
└── TestAdaniGroupVerticals              # Scenario 5: Organizational hierarchy

backend/tests/test_metrics_validators.py
├── LatencySLAThresholds         # Configurable SLA bounds
├── Latency validators           # Component and end-to-end timing
├── Vector DB validators         # Retrieval quality, bypass logic
├── Graph validators             # Coverage, depth, match types
├── NER validators               # Entity extraction, type classification
├── Entity resolution validators # Confidence, disambiguation
├── LLM validators               # Token budgets, cache efficiency
├── Response validators          # Citations, confidence labels
└── MultiTurn validators         # History preservation, context progression

backend/tests/test_runner_with_reporting.py
├── ScenarioRunResult            # Per-scenario aggregated results
├── TestExecutionSummary         # Cross-scenario summary
└── TestRunnerWithReporting      # Orchestration and reporting
```

## Usage

### Quick Start

Run all five scenarios with full tracing:

```python
from tests.test_runner_with_reporting import TestRunnerWithReporting

runner = TestRunnerWithReporting()
summary = runner.run_all_scenarios()
runner.print_summary(summary)
report_path = runner.generate_final_report(summary)
```

### CLI Execution

```bash
cd backend
python -m pytest tests/test_runner_with_reporting.py -v

# Or run individual scenarios
python -m pytest tests/test_scenarios_with_tracing.py::TestAdaniFinancialPerformance -v
```

### Running a Custom Test Scenario

```python
from tests.test_multiturn_queries_with_tracing import MultiTurnQueryTestFixture

fixture = MultiTurnQueryTestFixture("my_test_scenario")

# Turn 1: Initial query
trace1 = fixture.add_turn(
    query="What was Q1 FY19 EBITDA?",
    expected_answer_contains=["589", "EBITDA"],
    expected_entities=["Q1 FY19"],
    expected_graph_nodes_min=2,
    expected_graph_edges_min=1,
    query_type_expected="direct_lookup"
)

# Turn 2: Follow-up with context
trace2 = fixture.add_turn(
    query="How does this compare to Q1 FY18?",
    expected_answer_contains=["727", "compare"],
    query_type_expected="comparison"
)

# Get aggregated report
report = fixture.get_summary_report()
report_path = fixture.save_summary_report()
```

## Test Scenarios

### 1. Adani Financial Performance Deep Dive

**Focus:** Financial metrics retrieval and year-over-year comparisons

| Turn | Query | Expected Output | Validation |
|------|-------|-----------------|-----------|
| 1 | Q1 FY19 EBITDA? | Rs 589 cr, -19% YoY | Direct lookup, 1+ graph edge |
| 2 | vs Q1 FY18? | Rs 727 cr, comparison | Comparison mode, context preserved |
| 3 | Business segments? | Coal, Mining, CGD, Solar, Agro | Aggregation, 5+ entities |
| 4 | Key executives? | Pranav Adani, Rakesh Shah, Vinay Prakash | NER identifies persons, 3+ entities |

**Metrics Tracked:**
- Vector DB: Candidate count progression
- Graph: Business segment relationships
- NER: Person entity identification
- LLM: Token budget for comparisons

### 2. Fund Manager and Company Relationships

**Focus:** Multi-hop graph traversal and entity resolution

| Turn | Query | Expected Output | Validation |
|------|-------|-----------------|-----------|
| 1 | Who is Pranav Adani? | Fund manager at Adani Enterprises Limited | Entity resolution, PART_OF |
| 2 | Other executives? | Rakesh Shah also PART_OF Adani Enterprises | Graph traversal, 2+ hops |
| 3 | Mundra Solar execs? | Ramesh Nair, Rakesh Tiwary | Scope switching, entity linking |
| 4 | Related to Adani Group? | Ecosystem comparison, yes | Multi-entity comparison |

**Metrics Tracked:**
- Entity Resolution: Confidence scores, disambiguation
- Graph: Multi-hop traversal depth (1-2 hops)
- NER: Consistent entity identification across turns

### 3. Mining and Coal Business Exploration

**Focus:** Domain-specific knowledge extraction and role mapping

| Turn | Query | Expected Output | Validation |
|------|-------|-----------------|-----------|
| 1 | Mining projects? | Parsa, GP3, Talabira 2 & 3 | Aggregation, 4+ entities |
| 2 | Talabira details? | Scheme name vs managed entity, NLC | Entity aliasing handling |
| 3 | Coal trading performance? | Business segment classification | Direct lookup with domain context |
| 4 | Mining executive? | Ram Patodia manages Mining/ICM | Executive-role mapping |

**Metrics Tracked:**
- Graph: Project relationships, management structures
- NER: Domain-specific term classification
- Entity Resolution: Handling entity aliases

### 4. SEBI Regulatory Framework Understanding

**Focus:** Regulatory metric extraction and cross-regulatory comparison

| Turn | Query | Expected Output | Validation |
|------|-------|-----------------|-----------|
| 1 | MF borrowing limits? | 20% of net assets, temporary use | Direct regulatory lookup |
| 2 | vs InvITs? | 49% of asset value, different purpose | Cross-entity comparison |
| 3 | InvIT purposes? | Capex, acquisitions, refinancing | Conditional logic understanding |
| 4 | Synthesis? | MFs stricter (20% vs 49%) | Multi-turn reasoning |

**Metrics Tracked:**
- Vector DB: Document prose retrieval for regulations
- LLM: Context accumulation across turns
- Response: Citation accuracy for regulatory claims

### 5. Adani Group Business Verticals

**Focus:** Organizational hierarchy and subsidiary classification

| Turn | Query | Expected Output | Validation |
|------|-------|-----------------|-----------|
| 1 | Group companies? | Adani Enterprises, Gas, Wilmar, Mundra Solar | Aggregation, 4+ entities |
| 2 | Wilmar business? | Agri, food, Fortune brand, edible oil | Subsidiary function |
| 3 | Gas business? | CGD, Naresh Poddar executive | Executive-company linking |
| 4 | Mining executive? | Vinay Prakash oversees coal/mining | Vertical role mapping |

**Metrics Tracked:**
- Graph: Organizational hierarchy depth (3+ hops)
- NER: Consistent executive identification
- Entity Resolution: Cross-company entity linking

## Metrics Captured

### Per-Query Metrics (QueryTracingContext)

```python
# Query classification
query_type: str                     # direct_lookup, aggregation, comparison, open_ended
query_type_confidence: float        # 0-1 confidence in classification

# Component timings (ms)
components: Dict[str, ComponentMetrics]
  - query_classification
  - ner_pipeline
  - entity_resolution
  - vector_db_retrieval
  - graph_traversal
  - llm_generation
  - response_analysis

# Vector DB
vector_db_candidates_raw: int       # Pre-reranking count
vector_db_candidates_reranked: int  # Post-reranking count
vector_db_bypass_flag: bool         # Graph-only fallback used
vector_db_pruned: bool              # Reduced from 5 to 1

# Graph
graph_nodes_retrieved: int
graph_edges_retrieved: int
graph_matched_by: str               # entity, product, none
graph_entities_used: List[str]

# NER
ner_entities_layer_a: List          # Rule-based entities
ner_entities_layer_b: List          # ML-based entities

# LLM
llm_tokens_input: int
llm_tokens_output: int
llm_tokens_cached: int              # Prompt caching
llm_cache_creation_tokens: int
llm_cost_usd: float

# Response quality
answer_has_citations: bool
citation_count: int
answer_confidence_label: str        # high/medium/low confidence
```

### Per-Scenario Aggregates (ScenarioRunResult)

```python
# Latency statistics
total_latency_ms: float
avg_latency_ms: float
p50_latency_ms: float
p95_latency_ms: float
p99_latency_ms: float

# Token usage
total_tokens: int
avg_tokens_per_turn: float

# Component averages
vector_avg_candidates: float
graph_avg_nodes: float
graph_avg_edges: float
ner_avg_entities: float
llm_avg_input_tokens: float
llm_avg_output_tokens: float

# Pass rates
passed_turns: int
failed_turns: int
test_passed: bool
```

## Validation Helpers

### Latency Validators

```python
from tests.test_metrics_validators import (
    LatencySLAThresholds,
    validate_all_component_latencies,
    validate_latency_breakdown
)

thresholds = LatencySLAThresholds(
    vector_db_max_ms=500,
    graph_traversal_max_ms=300,
    llm_generation_max_ms=3000,
    end_to_end_max_ms=5000
)

results = validate_all_component_latencies(trace, thresholds)
balanced, msg = validate_latency_breakdown(trace, max_single_component_percent=60)
```

### Vector DB Validators

```python
valid, msg = validate_vector_retrieval_quality(
    trace, 
    min_candidates=1, 
    max_candidates=10
)

valid, msg = validate_vector_bypass_logic(trace, query_type="aggregation")
```

### Graph Validators

```python
valid, msg = validate_graph_coverage(
    trace,
    min_nodes=2,
    min_edges=1,
    require_match=True
)

valid, msg = validate_graph_traversal_depth(trace, expected_hops=1)

valid, msg = validate_graph_match_type(trace, allowed_match_types=["entity", "product"])
```

### NER/Entity Resolution Validators

```python
valid, msg = validate_ner_entity_extraction(
    trace,
    min_entities_total=2,
    min_layer_a=1,
    min_layer_b=0
)

valid, msg = validate_entity_resolution_quality(
    trace,
    min_confidence=0.7
)

valid, msg = validate_entity_disambiguation(
    trace,
    max_ambiguous_ratio=0.3
)
```

### LLM Validators

```python
valid, msg = validate_llm_token_usage(
    trace,
    max_input_tokens=8000,
    max_output_tokens=2000,
    max_total_tokens=10000
)

valid, msg = validate_llm_cache_efficiency(trace, min_cache_hit_rate=0.0)
```

### Response Validators

```python
valid, msg = validate_response_citations(trace, require_citations=True)

valid, msg = validate_response_confidence(
    trace,
    allowed_confidences=["high confidence", "medium confidence"]
)
```

### Multi-Turn Validators

```python
valid, msg = validate_chat_history_preservation(traces)

valid, msg = validate_context_relevance_progression(traces)
```

### Composite Validator

```python
from tests.test_metrics_validators import validate_query_trace

report = validate_query_trace(
    trace,
    thresholds=thresholds,
    require_graph=True,
    require_citations=True
)

print(f"Pass Rate: {report.pass_rate:.1%}")
for validator, error in report.failures:
    print(f"  ✗ {validator}: {error}")
```

## Output Structure

```
logs/test_runs/test-run-YYYYMMDD-HHMMSS/
├── TEST_EXECUTION_REPORT.md                     # Summary markdown report
├── adani_financial_performance/
│   ├── scenario_results.json                    # Aggregated scenario metrics
│   ├── validation_reports.json                  # Validation details
│   ├── traces.csv                               # Query-level traces (Excel-friendly)
│   └── trace_*_*.jsonl                          # Individual trace files
├── fund_manager_relationships/
│   ├── scenario_results.json
│   ├── validation_reports.json
│   ├── traces.csv
│   └── trace_*_*.jsonl
├── ... (3 more scenarios)
```

## Example: Full Test Run

```python
from tests.test_runner_with_reporting import TestRunnerWithReporting
from tests.test_metrics_validators import LatencySLAThresholds

# Configure SLA thresholds
thresholds = LatencySLAThresholds(
    vector_db_max_ms=400,
    graph_traversal_max_ms=250,
    llm_generation_max_ms=2500,
    end_to_end_max_ms=4000,
    end_to_end_p95_ms=3800,
    end_to_end_p99_ms=4200
)

# Run all scenarios
runner = TestRunnerWithReporting(thresholds=thresholds)
summary = runner.run_all_scenarios()

# Print summary
runner.print_summary(summary)

# Generate report
report_path = runner.generate_final_report(summary)

# Analyze results
print(f"\nLatency Percentiles:")
latencies = summary.get_latency_percentiles()
for key, value in latencies.items():
    print(f"  {key}: {value:.2f}ms")

print(f"\nToken Statistics:")
tokens = summary.get_token_statistics()
for key, value in tokens.items():
    print(f"  {key}: {value}")

print(f"\nReport: {report_path}")
```

## Key Features

### 1. **End-to-End Tracing**
Every query flows through a `QueryTracingContext` that captures metrics at 7 component stages.

### 2. **Multi-Turn Context Preservation**
Chat history is automatically accumulated and validated across turns to ensure context awareness.

### 3. **Comprehensive Validation**
40+ validator functions cover latency SLAs, retrieval quality, graph coverage, entity extraction, token usage, and response quality.

### 4. **Real-World Scenarios**
Five distinct test scenarios mirror actual user interactions: financial comparisons, relationship discovery, domain extraction, regulatory understanding, and organizational queries.

### 5. **Metrics Export**
Results exported to JSON (detailed), CSV (analysis-friendly), and Markdown (human-readable) formats.

### 6. **SLA Compliance Tracking**
Configurable thresholds for P50, P95, P99 latency and component-level SLAs.

### 7. **Detailed Reporting**
Automatic generation of comprehensive reports with recommendations, failures, and performance baselines.

## Debugging Tips

### Latency Bottleneck
Check `trace.get_component_latency_breakdown()` to see which components consume most time.

### Graph Not Matching
Verify `trace.graph_matched_by` and `trace.graph_entities_used` to see if NER identified the right entities.

### Token Overuse
Compare `trace.llm_tokens_input` to `trace.vector_db_candidates_reranked` to see if context is bloated.

### Citation Missing
Check if answer contains `[` and `]` characters; if not, response quality validator will fail.

### Context Not Preserved
Verify `trace.chat_history_length` increases with turn number; if not, history compression failed.

## Performance Baselines (Expected)

Based on the implementation plan and current system:

| Metric | Expected | SLA |
|--------|----------|-----|
| Vector DB Latency | 100-300ms | <500ms |
| Graph Traversal | 50-150ms | <300ms |
| NER Processing | 10-50ms | <100ms |
| LLM Generation | 800-2000ms | <3000ms |
| **End-to-End** | **1500-3500ms** | **<5000ms** |
| **P95 (multi-query)** | ~4000ms | <4500ms |
| Avg Tokens/Query | 1000-2000 | <10000 |

## Future Enhancements

- [ ] Real-time dashboard with live metrics streaming
- [ ] Continuous monitoring and alerting on SLA breaches
- [ ] Comparative analysis across multiple test runs
- [ ] Cost optimization recommendations
- [ ] Automated baseline regression detection
- [ ] Cache effectiveness analysis
- [ ] Graph query optimization suggestions

---

**Version:** 1.0  
**Last Updated:** August 17, 2026  
**Maintainer:** Context Engineering Team
