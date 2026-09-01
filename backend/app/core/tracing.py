# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tracing.py
==========
Unified tracing context for capturing metrics across all pipeline components.
Flows from query entry through vector DB, graph store, entity resolution,
context layer, and LLM, enabling end-to-end observability and validation.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, Optional, List
import uuid
import time
import json
from pathlib import Path


@dataclass
class ComponentMetrics:
    """Captures execution metrics for a single component."""
    component_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, success, error
    error_message: Optional[str] = None

    def end(self, metrics_dict: Optional[Dict[str, Any]] = None, status: str = "success", error: Optional[str] = None):
        """End timing for component and record metrics."""
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        if metrics_dict:
            self.metrics.update(metrics_dict)
        self.status = status
        self.error_message = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_name": self.component_name,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "error_message": self.error_message,
            "metrics": self.metrics,
        }


@dataclass
class CacheMetrics:
    """Cache performance metrics."""
    cache_type: str  # "semantic_cache", "faiss_cache", "graph_cache"
    hit: bool
    latency_ms: float
    saved_tokens: int = 0
    entry_age_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EntityResolutionMetrics:
    """Entity resolution metrics."""
    entities_input: int
    entities_resolved: int
    resolution_confidence_avg: float
    ambiguous_entities: int
    latency_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QueryTracingContext:
    """
    Single source of truth for all metrics across one query.
    Flows through the entire retrieval pipeline, capturing metrics at each stage.
    """
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    query_text: str = ""
    session_id: str = ""
    turn_index: int = 0
    chat_history_length: int = 0

    # Pipeline-level classifications
    query_type: str = ""  # direct_lookup, aggregation, comparison, open_ended
    query_type_confidence: float = 0.0

    # Component-level traces
    components: Dict[str, ComponentMetrics] = field(default_factory=dict)

    # Cache metrics (if hit, otherwise None)
    cache_metric: Optional[CacheMetrics] = None

    # Vector DB metrics
    vector_db_candidates_raw: int = 0
    vector_db_candidates_reranked: int = 0
    vector_db_bypass_flag: bool = False
    vector_db_pruned: bool = False

    # Graph metrics
    graph_nodes_retrieved: int = 0
    graph_edges_retrieved: int = 0
    graph_matched_by: str = ""  # entity, product, none
    graph_traversal_hops: int = 0
    graph_entities_used: List[str] = field(default_factory=list)

    # NER metrics
    ner_entities_layer_a: List[Dict[str, Any]] = field(default_factory=list)
    ner_entities_layer_b: List[Dict[str, Any]] = field(default_factory=list)
    ner_disambiguation_calls: int = 0

    # Entity resolution metrics
    entity_resolution: Optional[EntityResolutionMetrics] = None

    # LLM metrics
    llm_model_used: str = ""
    llm_tokens_input: int = 0
    llm_tokens_output: int = 0
    llm_tokens_cached: int = 0
    llm_cache_creation_tokens: int = 0
    llm_cost_usd: float = 0.0

    # Enrichment metrics (aggregation, comparison, etc.)
    cypher_generation_attempted: bool = False
    cypher_generation_successful: bool = False
    verified_aggregate_used: bool = False
    comparison_table_used: bool = False

    # Response metrics
    answer_has_citations: bool = False
    citation_count: int = 0
    answer_confidence_label: str = ""

    def start_component(self, name: str) -> ComponentMetrics:
        """Begin timing a component."""
        metric = ComponentMetrics(
            component_name=name,
            start_time=time.perf_counter()
        )
        self.components[name] = metric
        return metric

    def end_component(
        self,
        name: str,
        metrics_dict: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error: Optional[str] = None
    ):
        """End timing for a component and store metrics."""
        if name in self.components:
            self.components[name].end(metrics_dict, status, error)

    def add_cache_hit(self, cache_type: str, latency_ms: float, saved_tokens: int = 0):
        """Record cache hit."""
        self.cache_metric = CacheMetrics(
            cache_type=cache_type,
            hit=True,
            latency_ms=latency_ms,
            saved_tokens=saved_tokens
        )

    def add_cache_miss(self, cache_type: str, latency_ms: float):
        """Record cache miss."""
        self.cache_metric = CacheMetrics(
            cache_type=cache_type,
            hit=False,
            latency_ms=latency_ms
        )

    def get_total_latency_ms(self) -> float:
        """Sum all component latencies."""
        return sum(c.duration_ms for c in self.components.values())

    def get_component_latency_breakdown(self) -> Dict[str, float]:
        """Get latency as percentage of total for each component."""
        total = self.get_total_latency_ms()
        if total == 0:
            return {}
        return {
            name: round((metric.duration_ms / total) * 100, 1)
            for name, metric in self.components.items()
        }

    def get_total_tokens(self) -> int:
        """Total tokens across LLM calls."""
        return self.llm_tokens_input + self.llm_tokens_output + self.llm_tokens_cached

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for logging/storage."""
        return {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp.isoformat(),
            "query_text": self.query_text,
            "session_id": self.session_id,
            "turn_index": self.turn_index,
            "chat_history_length": self.chat_history_length,
            "query_classification": {
                "type": self.query_type,
                "confidence": self.query_type_confidence,
            },
            "cache": self.cache_metric.to_dict() if self.cache_metric else None,
            "components": {
                name: metric.to_dict()
                for name, metric in self.components.items()
            },
            "vector_db": {
                "candidates_raw": self.vector_db_candidates_raw,
                "candidates_reranked": self.vector_db_candidates_reranked,
                "bypass_flag": self.vector_db_bypass_flag,
                "pruned": self.vector_db_pruned,
            },
            "graph": {
                "nodes_retrieved": self.graph_nodes_retrieved,
                "edges_retrieved": self.graph_edges_retrieved,
                "matched_by": self.graph_matched_by,
                "traversal_hops": self.graph_traversal_hops,
                "entities_used": self.graph_entities_used,
            },
            "ner": {
                "layer_a_count": len(self.ner_entities_layer_a),
                "layer_b_count": len(self.ner_entities_layer_b),
                "disambiguation_calls": self.ner_disambiguation_calls,
                "entities_layer_a": [
                    {"text": e.get("text"), "label": e.get("label")}
                    for e in self.ner_entities_layer_a
                ],
                "entities_layer_b": [
                    {"text": e.get("text"), "label": e.get("label")}
                    for e in self.ner_entities_layer_b
                ],
            },
            "entity_resolution": self.entity_resolution.to_dict() if self.entity_resolution else None,
            "llm": {
                "model": self.llm_model_used,
                "tokens_input": self.llm_tokens_input,
                "tokens_output": self.llm_tokens_output,
                "tokens_cached": self.llm_tokens_cached,
                "cache_creation_tokens": self.llm_cache_creation_tokens,
                "cost_usd": round(self.llm_cost_usd, 4),
            },
            "enrichment": {
                "cypher_generation_attempted": self.cypher_generation_attempted,
                "cypher_generation_successful": self.cypher_generation_successful,
                "verified_aggregate_used": self.verified_aggregate_used,
                "comparison_table_used": self.comparison_table_used,
            },
            "response": {
                "has_citations": self.answer_has_citations,
                "citation_count": self.citation_count,
                "confidence_label": self.answer_confidence_label,
            },
            "latencies": {
                "total_ms": round(self.get_total_latency_ms(), 2),
                "breakdown_percent": self.get_component_latency_breakdown(),
            },
        }

    def save_to_file(self, output_dir: Path) -> Path:
        """Save trace to JSONL file."""
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_ts = self.timestamp.isoformat().replace(":", "-")
        file_path = output_dir / f"trace_{self.trace_id}_{safe_ts}.jsonl"
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")
            return file_path
        except Exception as exc:
            print(f"Warning: Could not write trace to {file_path}: {exc}")
            return None

    def print_summary(self):
        """Print human-readable summary."""
        latency_breakdown = self.get_component_latency_breakdown()
        
        print("\n" + "="*80)
        print(f"  [TRACE SUMMARY] {self.trace_id}")
        print("="*80)
        print(f"  Query: {self.query_text[:100]}...")
        print(f"  Type: {self.query_type} (confidence: {self.query_type_confidence:.1%})")
        print(f"  Session: {self.session_id} | Turn: {self.turn_index}")
        print()
        print(f"  Cache: {self.cache_metric.cache_type} {'HIT' if self.cache_metric and self.cache_metric.hit else 'MISS'}")
        print(f"  NER: {len(self.ner_entities_layer_a)} layer-A + {len(self.ner_entities_layer_b)} layer-B entities")
        print(f"  Graph: {self.graph_nodes_retrieved} nodes, {self.graph_edges_retrieved} edges ({self.graph_matched_by})")
        print(f"  Vector: {self.vector_db_candidates_raw} raw → {self.vector_db_candidates_reranked} reranked | bypass={self.vector_db_bypass_flag} | pruned={self.vector_db_pruned}")
        print(f"  Enrichment: aggregate={self.verified_aggregate_used} | comparison={self.comparison_table_used}")
        print(f"  LLM: {self.llm_model_used} | {self.llm_tokens_input} in + {self.llm_tokens_output} out + {self.llm_tokens_cached} cached = {self.get_total_tokens()} total")
        print()
        print(f"  Latencies (ms):")
        for name, metric in sorted(self.components.items(), key=lambda x: x[1].duration_ms, reverse=True):
            pct = latency_breakdown.get(name, 0)
            print(f"    {name:30s}: {metric.duration_ms:8.2f}ms ({pct:5.1f}%)")
        print(f"    {'TOTAL':30s}: {self.get_total_latency_ms():8.2f}ms")
        print()
        print(f"  Response: {self.citation_count} citations | confidence={self.answer_confidence_label}")
        print("="*80 + "\n")
