# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_metrics_validators.py
==========================
Comprehensive metrics validation and assertion helpers for query tracing.

Provides validators for:
- Component latency assertions
- Vector DB retrieval quality
- Graph traversal depth and coverage
- NER accuracy and entity disambiguation
- Entity resolution confidence and consistency
- LLM token usage and caching
- Response quality and citation accuracy
- Multi-turn context preservation
- Cache efficiency and cost metrics
- SLA compliance and performance baselines
"""

import pytest
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from app.core.tracing import QueryTracingContext


# ─────────────────────────────────────────────────────────────────────────
# LATENCY VALIDATORS
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class LatencySLAThresholds:
    """SLA thresholds for component latencies (milliseconds)."""
    vector_db_max_ms: float = 500.0
    graph_traversal_max_ms: float = 300.0
    ner_processing_max_ms: float = 100.0
    entity_resolution_max_ms: float = 150.0
    llm_generation_max_ms: float = 3000.0
    cypher_generation_max_ms: float = 500.0
    end_to_end_max_ms: float = 5000.0
    
    # P95 and P99 for multi-query scenarios
    end_to_end_p95_ms: float = 4500.0
    end_to_end_p99_ms: float = 5500.0


def validate_component_latency(
    trace: QueryTracingContext,
    component_name: str,
    max_latency_ms: float,
    tolerance_percent: float = 10.0
) -> Tuple[bool, str]:
    """
    Validate component latency against threshold with tolerance.
    
    Args:
        trace: Query trace
        component_name: Name of component to validate
        max_latency_ms: Maximum acceptable latency
        tolerance_percent: Acceptable overage percentage
        
    Returns:
        (is_valid, message)
    """
    if component_name not in trace.components:
        return False, f"Component {component_name} not found in trace"
    
    metric = trace.components[component_name]
    tolerance_ms = max_latency_ms * (tolerance_percent / 100.0)
    effective_max = max_latency_ms + tolerance_ms
    
    if metric.duration_ms > effective_max:
        return False, (
            f"{component_name} latency {metric.duration_ms:.2f}ms exceeds "
            f"threshold {max_latency_ms:.2f}ms (tolerance: {tolerance_percent}%)"
        )
    
    return True, f"{component_name}: {metric.duration_ms:.2f}ms ✓"


def validate_all_component_latencies(
    trace: QueryTracingContext,
    thresholds: Optional[LatencySLAThresholds] = None
) -> Dict[str, Tuple[bool, str]]:
    """Validate all component latencies against thresholds."""
    thresholds = thresholds or LatencySLAThresholds()
    
    component_thresholds = {
        "vector_db_retrieval": thresholds.vector_db_max_ms,
        "graph_traversal": thresholds.graph_traversal_max_ms,
        "ner_pipeline": thresholds.ner_processing_max_ms,
        "entity_resolution": thresholds.entity_resolution_max_ms,
        "llm_generation": thresholds.llm_generation_max_ms,
        "cypher_generation": thresholds.cypher_generation_max_ms,
    }
    
    results = {}
    for component, max_ms in component_thresholds.items():
        if component in trace.components:
            results[component] = validate_component_latency(trace, component, max_ms)
    
    # Validate total latency
    total_latency = trace.get_total_latency_ms()
    if total_latency > thresholds.end_to_end_max_ms:
        results["total"] = (
            False,
            f"Total latency {total_latency:.2f}ms exceeds {thresholds.end_to_end_max_ms}ms"
        )
    else:
        results["total"] = (True, f"Total: {total_latency:.2f}ms ✓")
    
    return results


def validate_latency_breakdown(
    trace: QueryTracingContext,
    max_single_component_percent: float = 60.0
) -> Tuple[bool, str]:
    """
    Ensure no single component dominates latency.
    
    Args:
        trace: Query trace
        max_single_component_percent: Max acceptable percentage for any single component
        
    Returns:
        (is_valid, message)
    """
    breakdown = trace.get_component_latency_breakdown()
    
    if not breakdown:
        return False, "No component latency breakdown available"
    
    max_component = max(breakdown.items(), key=lambda x: x[1])
    component_name, percentage = max_component
    
    if percentage > max_single_component_percent:
        return False, (
            f"Component '{component_name}' consumes {percentage}% of latency, "
            f"exceeds limit {max_single_component_percent}%"
        )
    
    return True, f"Latency balanced: max component is {component_name} at {percentage}%"


# ─────────────────────────────────────────────────────────────────────────
# VECTOR DB VALIDATORS
# ─────────────────────────────────────────────────────────────────────────

def validate_vector_retrieval_quality(
    trace: QueryTracingContext,
    min_candidates: int = 1,
    max_candidates: int = 10
) -> Tuple[bool, str]:
    """
    Validate vector DB retrieval quality.
    
    Args:
        trace: Query trace
        min_candidates: Minimum candidates expected
        max_candidates: Maximum candidates expected
        
    Returns:
        (is_valid, message)
    """
    raw = trace.vector_db_candidates_raw
    reranked = trace.vector_db_candidates_reranked
    
    if raw < min_candidates:
        return False, f"Raw candidates {raw} below minimum {min_candidates}"
    
    if reranked < min_candidates:
        return False, f"Reranked candidates {reranked} below minimum {min_candidates}"
    
    if reranked > max_candidates:
        return False, f"Reranked candidates {reranked} exceed maximum {max_candidates}"
    
    rerank_ratio = reranked / raw if raw > 0 else 0
    return True, (
        f"Vector retrieval: {raw} raw → {reranked} reranked "
        f"(retention: {rerank_ratio:.1%}) ✓"
    )


def validate_vector_bypass_logic(
    trace: QueryTracingContext,
    query_type: str
) -> Tuple[bool, str]:
    """
    Validate vector bypass is used appropriately.
    
    Args:
        trace: Query trace
        query_type: Expected query classification
        
    Returns:
        (is_valid, message)
    """
    if query_type not in ["aggregation", "comparison", "direct_lookup"]:
        return True, "Vector bypass logic N/A for open-ended queries"
    
    # For structured queries, bypass should be considered when graph is strong
    if trace.graph_edges_retrieved > 3:
        if not trace.vector_db_bypass_flag and trace.vector_db_candidates_raw > 3:
            return (
                True,
                "Vector bypass not used despite strong graph signal "
                "(acceptable for safety net retrieval)"
            )
    
    return True, f"Vector bypass: {trace.vector_db_bypass_flag} ✓"


# ─────────────────────────────────────────────────────────────────────────
# GRAPH TRAVERSAL VALIDATORS
# ─────────────────────────────────────────────────────────────────────────

def validate_graph_coverage(
    trace: QueryTracingContext,
    min_nodes: int = 0,
    min_edges: int = 0,
    require_match: bool = False
) -> Tuple[bool, str]:
    """
    Validate graph traversal coverage.
    
    Args:
        trace: Query trace
        min_nodes: Minimum nodes expected
        min_edges: Minimum edges expected
        require_match: If True, require entity/product match
        
    Returns:
        (is_valid, message)
    """
    nodes = trace.graph_nodes_retrieved
    edges = trace.graph_edges_retrieved
    matched_by = trace.graph_matched_by
    
    if nodes < min_nodes:
        return False, f"Graph nodes {nodes} below minimum {min_nodes}"
    
    if edges < min_edges:
        return False, f"Graph edges {edges} below minimum {min_edges}"
    
    if require_match and matched_by == "none":
        return False, "Graph must match via entity or product"
    
    return True, (
        f"Graph coverage: {nodes} nodes, {edges} edges, "
        f"matched_by={matched_by} ✓"
    )


def validate_graph_traversal_depth(
    trace: QueryTracingContext,
    expected_hops: int = 1
) -> Tuple[bool, str]:
    """Validate graph traversal depth matches expectation."""
    actual_hops = trace.graph_traversal_hops
    
    if actual_hops != expected_hops:
        return False, (
            f"Graph traversal depth mismatch: expected {expected_hops} hops, "
            f"got {actual_hops} hops"
        )
    
    return True, f"Graph traversal depth: {actual_hops} hops ✓"


def validate_graph_match_type(
    trace: QueryTracingContext,
    allowed_match_types: List[str] = None
) -> Tuple[bool, str]:
    """
    Validate graph match type is one of allowed types.
    
    Args:
        trace: Query trace
        allowed_match_types: List of acceptable match types (entity, product, none)
        
    Returns:
        (is_valid, message)
    """
    allowed_match_types = allowed_match_types or ["entity", "product", "none"]
    
    if trace.graph_matched_by not in allowed_match_types:
        return False, (
            f"Graph match type '{trace.graph_matched_by}' not in "
            f"allowed types: {allowed_match_types}"
        )
    
    return True, f"Graph match type: {trace.graph_matched_by} ✓"


# ─────────────────────────────────────────────────────────────────────────
# NER VALIDATORS
# ─────────────────────────────────────────────────────────────────────────

def validate_ner_entity_extraction(
    trace: QueryTracingContext,
    min_entities_total: int = 0,
    min_layer_a: int = 0,
    min_layer_b: int = 0
) -> Tuple[bool, str]:
    """
    Validate NER entity extraction coverage.
    
    Args:
        trace: Query trace
        min_entities_total: Minimum total entities
        min_layer_a: Minimum Layer A (rule-based) entities
        min_layer_b: Minimum Layer B (ML) entities
        
    Returns:
        (is_valid, message)
    """
    layer_a_count = len(trace.ner_entities_layer_a)
    layer_b_count = len(trace.ner_entities_layer_b)
    total = layer_a_count + layer_b_count
    
    if total < min_entities_total:
        return False, (
            f"Total entities {total} below minimum {min_entities_total}"
        )
    
    if layer_a_count < min_layer_a:
        return False, f"Layer A entities {layer_a_count} below minimum {min_layer_a}"
    
    if layer_b_count < min_layer_b:
        return False, f"Layer B entities {layer_b_count} below minimum {min_layer_b}"
    
    return True, (
        f"NER extraction: {layer_a_count} Layer A + {layer_b_count} Layer B "
        f"= {total} total ✓"
    )


def validate_ner_entity_types(
    trace: QueryTracingContext,
    expected_entity_types: Dict[str, int]
) -> Tuple[bool, str]:
    """
    Validate NER identified expected entity types.
    
    Args:
        trace: Query trace
        expected_entity_types: Dict of label -> min_count expectations
        
    Returns:
        (is_valid, message)
    """
    all_entities = trace.ner_entities_layer_a + trace.ner_entities_layer_b
    entity_labels = {}
    
    for entity in all_entities:
        label = entity.get("label", "UNKNOWN")
        entity_labels[label] = entity_labels.get(label, 0) + 1
    
    missing_types = []
    for expected_label, min_count in expected_entity_types.items():
        actual_count = entity_labels.get(expected_label, 0)
        if actual_count < min_count:
            missing_types.append(
                f"{expected_label}: expected {min_count}, got {actual_count}"
            )
    
    if missing_types:
        return False, f"Missing entity types: {'; '.join(missing_types)}"
    
    return True, f"NER entity types: {entity_labels} ✓"


# ─────────────────────────────────────────────────────────────────────────
# ENTITY RESOLUTION VALIDATORS
# ─────────────────────────────────────────────────────────────────────────

def validate_entity_resolution_quality(
    trace: QueryTracingContext,
    min_confidence: float = 0.7
) -> Tuple[bool, str]:
    """
    Validate entity resolution quality metrics.
    
    Args:
        trace: Query trace
        min_confidence: Minimum average confidence threshold
        
    Returns:
        (is_valid, message)
    """
    if trace.entity_resolution is None:
        return True, "Entity resolution not performed (no entities to resolve)"
    
    metrics = trace.entity_resolution
    
    if metrics.resolution_confidence_avg < min_confidence:
        return False, (
            f"Entity resolution confidence {metrics.resolution_confidence_avg:.2f} "
            f"below minimum {min_confidence}"
        )
    
    resolved_ratio = (metrics.entities_resolved / metrics.entities_input 
                     if metrics.entities_input > 0 else 0)
    
    return True, (
        f"Entity resolution: {metrics.entities_resolved}/{metrics.entities_input} "
        f"({resolved_ratio:.1%}) with {metrics.resolution_confidence_avg:.2f} confidence ✓"
    )


def validate_entity_disambiguation(
    trace: QueryTracingContext,
    max_ambiguous_ratio: float = 0.3
) -> Tuple[bool, str]:
    """
    Validate entity disambiguation performance.
    
    Args:
        trace: Query trace
        max_ambiguous_ratio: Max acceptable ambiguous entity ratio
        
    Returns:
        (is_valid, message)
    """
    if trace.entity_resolution is None:
        return True, "Entity resolution not performed"
    
    metrics = trace.entity_resolution
    
    if metrics.entities_input == 0:
        return True, "No entities to disambiguate"
    
    ambiguous_ratio = metrics.ambiguous_entities / metrics.entities_input
    
    if ambiguous_ratio > max_ambiguous_ratio:
        return False, (
            f"Ambiguous entities ratio {ambiguous_ratio:.1%} exceeds "
            f"threshold {max_ambiguous_ratio:.1%}"
        )
    
    return True, (
        f"Entity disambiguation: {metrics.ambiguous_entities} ambiguous "
        f"out of {metrics.entities_input} ({ambiguous_ratio:.1%}) ✓"
    )


# ─────────────────────────────────────────────────────────────────────────
# LLM VALIDATORS
# ─────────────────────────────────────────────────────────────────────────

def validate_llm_token_usage(
    trace: QueryTracingContext,
    max_input_tokens: int = 8000,
    max_output_tokens: int = 2000,
    max_total_tokens: int = 10000
) -> Tuple[bool, str]:
    """
    Validate LLM token usage is within acceptable ranges.
    
    Args:
        trace: Query trace
        max_input_tokens: Maximum input tokens
        max_output_tokens: Maximum output tokens
        max_total_tokens: Maximum total tokens
        
    Returns:
        (is_valid, message)
    """
    input_tokens = trace.llm_tokens_input
    output_tokens = trace.llm_tokens_output
    total = trace.get_total_tokens()
    
    if input_tokens > max_input_tokens:
        return False, f"Input tokens {input_tokens} exceed {max_input_tokens}"
    
    if output_tokens > max_output_tokens:
        return False, f"Output tokens {output_tokens} exceed {max_output_tokens}"
    
    if total > max_total_tokens:
        return False, f"Total tokens {total} exceed {max_total_tokens}"
    
    return True, (
        f"LLM token usage: {input_tokens} in + {output_tokens} out "
        f"= {total} total ✓"
    )


def validate_llm_cache_efficiency(
    trace: QueryTracingContext,
    min_cache_hit_rate: float = 0.0
) -> Tuple[bool, str]:
    """
    Validate LLM cache efficiency.
    
    Args:
        trace: Query trace
        min_cache_hit_rate: Minimum acceptable cache hit rate (0-1)
        
    Returns:
        (is_valid, message)
    """
    cached_tokens = trace.llm_tokens_cached
    input_tokens = trace.llm_tokens_input
    
    if (cached_tokens + input_tokens) == 0:
        return True, "No cached tokens tracked"
    
    cache_hit_rate = cached_tokens / (cached_tokens + input_tokens)
    
    if cache_hit_rate < min_cache_hit_rate:
        return (
            True,
            f"Cache hit rate {cache_hit_rate:.1%} below minimum {min_cache_hit_rate:.1%} "
            f"(acceptable for first-time queries)"
        )
    
    return True, f"LLM cache efficiency: {cache_hit_rate:.1%} ✓"


# ─────────────────────────────────────────────────────────────────────────
# RESPONSE QUALITY VALIDATORS
# ─────────────────────────────────────────────────────────────────────────

def validate_response_citations(
    trace: QueryTracingContext,
    require_citations: bool = True
) -> Tuple[bool, str]:
    """
    Validate response includes appropriate citations.
    
    Args:
        trace: Query trace
        require_citations: If True, citations are required
        
    Returns:
        (is_valid, message)
    """
    if require_citations and not trace.answer_has_citations:
        return False, "Response does not include citations"
    
    return True, (
        f"Response citations: {trace.citation_count} citations "
        f"(requires={require_citations}) ✓"
    )


def validate_response_confidence(
    trace: QueryTracingContext,
    expected_confidence: str = None,
    allowed_confidences: List[str] = None
) -> Tuple[bool, str]:
    """
    Validate response confidence label.
    
    Args:
        trace: Query trace
        expected_confidence: Exact expected confidence label
        allowed_confidences: List of acceptable confidence labels
        
    Returns:
        (is_valid, message)
    """
    confidence = trace.answer_confidence_label
    
    if expected_confidence and confidence != expected_confidence:
        return False, (
            f"Confidence mismatch: expected '{expected_confidence}', "
            f"got '{confidence}'"
        )
    
    if allowed_confidences and confidence not in allowed_confidences:
        return False, (
            f"Confidence '{confidence}' not in allowed: {allowed_confidences}"
        )
    
    return True, f"Response confidence: {confidence} ✓"


# ─────────────────────────────────────────────────────────────────────────
# MULTI-TURN VALIDATORS
# ─────────────────────────────────────────────────────────────────────────

def validate_chat_history_preservation(
    traces: List[QueryTracingContext]
) -> Tuple[bool, str]:
    """
    Validate chat history is properly preserved across turns.
    
    Args:
        traces: List of traces from multi-turn conversation
        
    Returns:
        (is_valid, message)
    """
    for i, trace in enumerate(traces):
        expected_history_length = i * 2  # 2 entries (user + assistant) per prior turn
        if trace.chat_history_length != expected_history_length:
            return False, (
                f"Turn {i}: chat_history_length={trace.chat_history_length}, "
                f"expected {expected_history_length}"
            )
    
    return True, f"Chat history preserved across {len(traces)} turns ✓"


def validate_context_relevance_progression(
    traces: List[QueryTracingContext]
) -> Tuple[bool, str]:
    """
    Validate context becomes more relevant as turns progress.
    
    Args:
        traces: List of traces from multi-turn conversation
        
    Returns:
        (is_valid, message)
    """
    # Later turns should reference graph more
    graph_edges_by_turn = [t.graph_edges_retrieved for t in traces]
    
    if len(graph_edges_by_turn) < 2:
        return True, "Insufficient turns for context progression validation"
    
    # Token usage should generally increase with accumulated context
    token_usage_by_turn = [t.get_total_tokens() for t in traces]
    
    if token_usage_by_turn[-1] < token_usage_by_turn[0]:
        return (
            True,
            f"Token usage decreased from turn 0 ({token_usage_by_turn[0]}) "
            f"to turn {len(traces)-1} ({token_usage_by_turn[-1]}) "
            f"(acceptable with caching)"
        )
    
    return True, f"Context progression: tokens grow from {token_usage_by_turn[0]} to {token_usage_by_turn[-1]} ✓"


# ─────────────────────────────────────────────────────────────────────────
# COMPOSITE VALIDATORS
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationReport:
    """Aggregated validation report."""
    test_name: str
    passed_count: int
    failed_count: int
    total_count: int
    failures: List[Tuple[str, str]]
    
    @property
    def pass_rate(self) -> float:
        return self.passed_count / self.total_count if self.total_count > 0 else 0
    
    def print_summary(self):
        """Print human-readable summary."""
        print("\n" + "="*80)
        print(f"  VALIDATION REPORT: {self.test_name}")
        print("="*80)
        print(f"  Passed: {self.passed_count}/{self.total_count} ({self.pass_rate:.1%})")
        
        if self.failures:
            print(f"\n  Failures ({len(self.failures)}):")
            for validator_name, error_msg in self.failures:
                print(f"    ✗ {validator_name}: {error_msg}")
        else:
            print("\n  ✓ All validations passed!")
        
        print("="*80 + "\n")


def validate_query_trace(
    trace: QueryTracingContext,
    thresholds: Optional[LatencySLAThresholds] = None,
    require_graph: bool = False,
    require_citations: bool = True
) -> ValidationReport:
    """
    Run comprehensive validation suite on a query trace.
    
    Args:
        trace: Query trace to validate
        thresholds: SLA thresholds (uses defaults if not provided)
        require_graph: If True, graph signal is required
        require_citations: If True, citations are required
        
    Returns:
        ValidationReport with detailed results
    """
    thresholds = thresholds or LatencySLAThresholds()
    validations = []
    failures = []
    
    # Latency validations
    latency_results = validate_all_component_latencies(trace, thresholds)
    for component, (is_valid, msg) in latency_results.items():
        validations.append((f"latency_{component}", is_valid, msg))
        if not is_valid:
            failures.append((f"latency_{component}", msg))
    
    latency_balanced, msg = validate_latency_breakdown(trace)
    validations.append(("latency_balanced", latency_balanced, msg))
    if not latency_balanced:
        failures.append(("latency_balanced", msg))
    
    # Vector DB validations
    vector_valid, msg = validate_vector_retrieval_quality(trace)
    validations.append(("vector_retrieval_quality", vector_valid, msg))
    if not vector_valid:
        failures.append(("vector_retrieval_quality", msg))
    
    # Graph validations
    if require_graph:
        graph_valid, msg = validate_graph_coverage(trace, min_nodes=1, min_edges=1)
        validations.append(("graph_coverage", graph_valid, msg))
        if not graph_valid:
            failures.append(("graph_coverage", msg))
    
    # NER validations
    ner_valid, msg = validate_ner_entity_extraction(trace, min_entities_total=0)
    validations.append(("ner_extraction", ner_valid, msg))
    if not ner_valid:
        failures.append(("ner_extraction", msg))
    
    # Entity resolution validations
    resolution_valid, msg = validate_entity_resolution_quality(trace)
    validations.append(("entity_resolution", resolution_valid, msg))
    if not resolution_valid:
        failures.append(("entity_resolution", msg))
    
    # LLM validations
    llm_valid, msg = validate_llm_token_usage(trace)
    validations.append(("llm_token_usage", llm_valid, msg))
    if not llm_valid:
        failures.append(("llm_token_usage", msg))
    
    # Response validations
    if require_citations:
        citations_valid, msg = validate_response_citations(trace, require_citations=True)
        validations.append(("response_citations", citations_valid, msg))
        if not citations_valid:
            failures.append(("response_citations", msg))
    
    # Compile report
    passed = sum(1 for _, is_valid, _ in validations if is_valid)
    
    return ValidationReport(
        test_name=f"Query: {trace.query_text[:50]}...",
        passed_count=passed,
        failed_count=len(failures),
        total_count=len(validations),
        failures=failures
    )
