# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.metrics")


@dataclass
class ComponentMetric:
    """Tracks timing and resource usage for each pipeline component."""
    component_name: str
    start_time: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finalize(self):
        if self.end_time is None:
            self.end_time = time.perf_counter()
        if self.latency_ms == 0.0:
            self.latency_ms = (self.end_time - self.start_time) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        self.finalize()
        return {
            "component": self.component_name,
            "latency_ms": round(self.latency_ms, 2),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_hit": self.cache_hit,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class QueryMetrics:
    """Complete metrics for a single query request."""
    request_id: str
    query: str
    query_type: str = "unknown"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Per-component tracking
    components: List[ComponentMetric] = field(default_factory=list)

    # Aggregates
    total_latency_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_hit: bool = False

    # Quality metrics
    hallucination_detected: bool = False
    citation_accuracy: float = 1.0  # 0.0-1.0
    answer_relevance: float = 1.0   # 0.0-1.0

    # Metadata
    namespace: str = ""
    entities_count: int = 0
    graph_edges_found: int = 0
    vector_chunks_retrieved: int = 0

    def add_component(self, component: ComponentMetric):
        component.finalize()
        self.components.append(component)

    def finalize(self):
        """Calculate aggregates after all components complete."""
        for c in self.components:
            c.finalize()
        if self.components:
            if self.total_latency_ms == 0.0:
                self.total_latency_ms = sum(c.latency_ms for c in self.components)
            self.total_input_tokens = sum(c.input_tokens for c in self.components)
            self.total_output_tokens = sum(c.output_tokens for c in self.components)
            self.cache_hit = any(c.cache_hit for c in self.components)

    def to_dict(self) -> Dict[str, Any]:
        self.finalize()
        return {
            "request_id": self.request_id,
            "query": self.query,
            "query_type": self.query_type,
            "timestamp": self.timestamp,
            "components": [c.to_dict() for c in self.components],
            "total_latency_ms": round(self.total_latency_ms, 2),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "cache_hit": self.cache_hit,
            "hallucination_detected": self.hallucination_detected,
            "citation_accuracy": round(self.citation_accuracy, 3),
            "answer_relevance": round(self.answer_relevance, 3),
            "namespace": self.namespace,
            "entities_count": self.entities_count,
            "graph_edges_found": self.graph_edges_found,
            "vector_chunks_retrieved": self.vector_chunks_retrieved,
        }


class MetricsStore:
    """Stores and aggregates metrics for analysis."""

    def __init__(self, storage_path: Optional[Path] = None):
        if storage_path is None:
            backend_root = Path(__file__).resolve().parent.parent.parent
            self.storage_path = backend_root / "logs" / "metrics"
        else:
            self.storage_path = storage_path

        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create metrics directory %s: %s", self.storage_path, exc)

        self.metrics: List[QueryMetrics] = []
        self.session_start = datetime.now()

    def record(self, metrics: QueryMetrics):
        """Record a single query's metrics."""
        metrics.finalize()
        self.metrics.append(metrics)
        self._persist_metric(metrics)

    def _persist_metric(self, metrics: QueryMetrics):
        """Write metric to disk for offline analysis."""
        try:
            filename = self.storage_path / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{metrics.request_id[:8]}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(metrics.to_dict(), f, indent=2)
        except Exception as exc:
            logger.debug("Failed to persist metric: %s", exc)

    def summary(self, filter_by_phase: Optional[str] = None) -> Dict[str, Any]:
        """Generate summary statistics."""
        filtered = self.metrics
        if filter_by_phase:
            filtered = [m for m in self.metrics if m.query_type == filter_by_phase]

        if not filtered:
            return {
                "count": 0,
                "latency_p50_ms": 0.0,
                "latency_p99_ms": 0.0,
                "latency_avg_ms": 0.0,
                "token_avg": 0.0,
                "cache_hit_rate": 0.0,
                "citation_accuracy_avg": 1.0,
                "hallucination_rate": 0.0,
            }

        latencies = sorted([m.total_latency_ms for m in filtered])
        tokens = [m.total_input_tokens + m.total_output_tokens for m in filtered]
        p50_idx = len(latencies) // 2
        p99_idx = min(len(latencies) - 1, int(len(latencies) * 0.99))

        return {
            "count": len(filtered),
            "latency_p50_ms": round(latencies[p50_idx], 2),
            "latency_p99_ms": round(latencies[p99_idx], 2),
            "latency_avg_ms": round(sum(latencies) / len(latencies), 2),
            "token_avg": round(sum(tokens) / len(tokens), 1),
            "cache_hit_rate": round(sum(1 for m in filtered if m.cache_hit) / len(filtered), 3),
            "citation_accuracy_avg": round(sum(m.citation_accuracy for m in filtered) / len(filtered), 3),
            "hallucination_rate": round(sum(1 for m in filtered if m.hallucination_detected) / len(filtered), 3),
        }

    def clear(self):
        self.metrics.clear()


# Global singleton
_metrics_store: Optional[MetricsStore] = None


def get_metrics_store() -> MetricsStore:
    global _metrics_store
    if _metrics_store is None:
        _metrics_store = MetricsStore()
    return _metrics_store


def _summarize_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summary statistics over raw metric dicts (same shape as MetricsStore.summary)."""
    if not records:
        return {
            "count": 0,
            "latency_p50_ms": 0.0,
            "latency_p99_ms": 0.0,
            "latency_avg_ms": 0.0,
            "token_avg": 0.0,
            "cache_hit_rate": 0.0,
            "citation_accuracy_avg": 1.0,
            "hallucination_rate": 0.0,
        }

    latencies = sorted(float(r.get("total_latency_ms", 0.0)) for r in records)
    tokens = [int(r.get("total_input_tokens", 0)) + int(r.get("total_output_tokens", 0)) for r in records]
    n = len(latencies)
    return {
        "count": n,
        "latency_p50_ms": round(latencies[n // 2], 2),
        "latency_p99_ms": round(latencies[min(n - 1, int(n * 0.99))], 2),
        "latency_avg_ms": round(sum(latencies) / n, 2),
        "token_avg": round(sum(tokens) / n, 1),
        "cache_hit_rate": round(sum(1 for r in records if r.get("cache_hit")) / n, 3),
        "citation_accuracy_avg": round(sum(float(r.get("citation_accuracy", 1.0)) for r in records) / n, 3),
        "hallucination_rate": round(sum(1 for r in records if r.get("hallucination_detected")) / n, 3),
    }


def load_persisted_metrics(
    storage_path: Optional[Path] = None,
    since_seconds: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Reads metric records written to disk by the API process.

    Ops scripts run in their own process, so the in-memory MetricsStore they
    create is always empty — the served traffic lives in the API worker. These
    records are the only cross-process view of it.
    """
    if storage_path is None:
        storage_path = Path(__file__).resolve().parent.parent.parent / "logs" / "metrics"
    if not storage_path.exists():
        return []

    cutoff = time.time() - since_seconds if since_seconds else None
    records: List[Dict[str, Any]] = []
    for path in storage_path.glob("metrics_*.json"):
        try:
            if cutoff is not None and path.stat().st_mtime < cutoff:
                continue
            with open(path, "r", encoding="utf-8") as f:
                records.append(json.load(f))
        except Exception as exc:
            logger.debug("Skipping unreadable metric file %s: %s", path, exc)
    records.sort(key=lambda r: r.get("timestamp", ""))
    return records


def summarize_persisted_metrics(
    storage_path: Optional[Path] = None,
    since_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Summary over on-disk metrics, falling back to the in-process store."""
    records = load_persisted_metrics(storage_path, since_seconds)
    if records:
        return _summarize_records(records)
    return get_metrics_store().summary()
