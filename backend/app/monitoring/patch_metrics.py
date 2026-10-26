# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
app.monitoring.patch_metrics
=============================
Telemetry for self-healing patch system performance (GAP 2).
Tracks effectiveness and performance of all 5 healing layers.
"""

import logging
import time
from typing import Optional

try:
    from prometheus_client import Counter, Histogram, Gauge
    PROM_AVAILABLE = True
except ImportError:
    PROM_AVAILABLE = False
    
    # Dummy implementations for when Prometheus is unavailable
    class Counter:
        def __init__(self, *args, **kwargs):
            """Initialize a new instance of Counter.
            """
            pass
        def labels(self, **kwargs):
            """Labels.

            Returns:
                Result of the operation.
            """
            return self
        def inc(self):
            """Inc.
            """
            pass
    
    class Histogram:
        def __init__(self, *args, **kwargs):
            """Initialize a new instance of Histogram.
            """
            pass
        def labels(self, **kwargs):
            """Labels.

            Returns:
                Result of the operation.
            """
            return self
        def observe(self, val):
            """Observe.

            Args:
                val: The val.
            """
            pass
    
    class Gauge:
        def __init__(self, *args, **kwargs):
            """Initialize a new instance of Gauge.
            """
            pass
        def labels(self, **kwargs):
            """Labels.

            Returns:
                Result of the operation.
            """
            return self
        def set(self, val):
            """Set operation.

            Args:
                val: The val.
            """
            pass

logger = logging.getLogger("monitoring.patch_metrics")


class PatchMetricsCollector:
    """Tracks effectiveness and performance of each healing layer."""
    
    def __init__(self):
        """Initialize a new instance of PatchMetricsCollector.
        """
        if PROM_AVAILABLE:
            # Layer 1: Fast-Path Metrics
            self.fast_path_hits = Counter(
                "fast_path_hits_total",
                "Fast-path interceptor successful hits",
                ["patch_id", "attribute"]
            )
            self.fast_path_latency = Histogram(
                "fast_path_latency_ms",
                "Fast-path response latency in milliseconds",
                buckets=[5, 10, 15, 20, 25, 30, 50]
            )
            self.fast_path_misses = Counter(
                "fast_path_misses_total",
                "Fast-path interceptor misses (fallthrough to full retrieval)"
            )
            
            # Layer 2: Shadow Graph Metrics
            self.shadow_graph_queries = Counter(
                "shadow_graph_queries_total",
                "Shadow graph overlay queries",
                ["entity_id"]
            )
            self.shadow_graph_patches_applied = Gauge(
                "shadow_graph_active_patches",
                "Number of active shadow patches",
                ["entity_id"]
            )
            
            # Layer 3: Guardrail Metrics
            self.guardrail_interventions = Counter(
                "guardrail_interventions_total",
                "Guardrail rewrites of LLM output",
                ["patch_id", "rewrite_type"]
            )
            self.guardrail_latency = Histogram(
                "guardrail_latency_ms",
                "Guardrail verification latency",
                buckets=[50, 100, 150, 200, 250, 300, 500]
            )
            
            # Layer 4: Governance & Promotion
            self.patch_promotions = Counter(
                "patch_promotions_total",
                "Patches promoted to canonical graph",
                ["entity_id", "attribute"]
            )
            self.promotion_duration = Histogram(
                "promotion_duration_seconds",
                "Time from provisional to promoted",
                buckets=[3600, 7200, 21600, 43200, 86400, 172800, 604800]  # 1hr to 7 days
            )
            
            # Patch Confidence Distribution
            self.patch_confidence = Histogram(
                "patch_confidence_score",
                "Confidence scores of created patches",
                buckets=[0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
            )
            
            # Conflict Resolution (GAP 1)
            self.patch_conflicts = Counter(
                "patch_conflicts_total",
                "Patch conflicts detected",
                ["resolution_strategy"]
            )
            
            logger.info("✅ Prometheus available - patch metrics initialized")
        else:
            logger.info("⚠️ Prometheus unavailable - patch metrics will use dummy implementation")
    
    def record_fast_path_hit(
        self, 
        query: str, 
        patch_id: str, 
        latency_ms: float,
        attribute: str = "unknown"
    ):
        """Track successful fast-path interception (Layer 1).

        Args:
            query (str): Search query or input text.
            patch_id (str): Unique identifier of the patch.
            latency_ms (float): Collection or list of latency ms.
            attribute (str): The attribute.
        """
        if PROM_AVAILABLE:
            try:
                self.fast_path_hits.labels(patch_id=patch_id, attribute=attribute).inc()
                self.fast_path_latency.observe(latency_ms)
            except Exception as e:
                logger.debug(f"Metrics recording error: {e}")
        logger.debug(f"⚡ Fast-path HIT: {patch_id} in {latency_ms:.2f}ms")
    
    def record_fast_path_miss(self):
        """Track fast-path miss (fallthrough to full retrieval)."""
        if PROM_AVAILABLE:
            try:
                self.fast_path_misses.inc()
            except Exception as e:
                logger.debug(f"Metrics recording error: {e}")
    
    def record_aggregation_hit(
        self,
        query: str,
        limit: int,
        latency_ms: float,
        schemes_count: int,
    ):
        """Track aggregation query interceptor hits.

        Args:
            query (str): The user query.
            limit (int): Requested number of schemes.
            latency_ms (float): Query latency in milliseconds.
            schemes_count (int): Number of schemes returned.
        """
        if PROM_AVAILABLE:
            try:
                # Increment aggregation hit counter
                if hasattr(self, 'aggregation_hits'):
                    self.aggregation_hits.inc()
                if hasattr(self, 'aggregation_latency'):
                    self.aggregation_latency.observe(latency_ms)
            except Exception as e:
                logger.debug(f"Metrics recording error: {e}")
        
        logger.debug(f"📊 Aggregation HIT: {schemes_count} schemes (limit={limit}) in {latency_ms:.2f}ms")
    
    def record_shadow_graph_retrieval(
        self, 
        entity_id: str, 
        patches_applied: int
    ):
        """Track shadow graph overlay queries (Layer 2).

        Args:
            entity_id (str): Unique identifier of the entity.
            patches_applied (int): The patches applied.
        """
        if PROM_AVAILABLE:
            try:
                self.shadow_graph_queries.labels(entity_id=entity_id).inc()
                self.shadow_graph_patches_applied.labels(entity_id=entity_id).set(patches_applied)
            except Exception as e:
                logger.debug(f"Metrics recording error: {e}")
        logger.debug(f"📊 Shadow graph query: {entity_id}, {patches_applied} patches applied")
    
    def record_guardrail_intervention(
        self, 
        patch_id: str, 
        rewrite_type: str,
        latency_ms: float
    ):
        """Track guardrail corrections (Layer 3).

        Args:
            patch_id (str): Unique identifier of the patch.
            rewrite_type (str): The rewrite type.
            latency_ms (float): Collection or list of latency ms.
        """
        if PROM_AVAILABLE:
            try:
                self.guardrail_interventions.labels(
                    patch_id=patch_id, 
                    rewrite_type=rewrite_type
                ).inc()
                self.guardrail_latency.observe(latency_ms)
            except Exception as e:
                logger.debug(f"Metrics recording error: {e}")
        logger.info(f"🛡️ Guardrail INTERVENTION: {patch_id} ({rewrite_type}) in {latency_ms:.2f}ms")
    
    def record_patch_promotion(
        self,
        entity_id: str,
        attribute: str,
        time_to_promote_seconds: float
    ):
        """Track patch promotion to canonical graph (Layer 4).

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.
            time_to_promote_seconds (float): Collection or list of time to promote seconds.
        """
        if PROM_AVAILABLE:
            try:
                self.patch_promotions.labels(entity_id=entity_id, attribute=attribute).inc()
                self.promotion_duration.observe(time_to_promote_seconds)
            except Exception as e:
                logger.debug(f"Metrics recording error: {e}")
        hours = time_to_promote_seconds / 3600
        logger.info(f"🎯 Patch PROMOTED: {entity_id}.{attribute} (took {hours:.1f} hours)")
    
    def record_patch_confidence(self, confidence: float):
        """Track patch confidence score distribution.

        Args:
            confidence (float): The confidence.
        """
        if PROM_AVAILABLE:
            try:
                self.patch_confidence.observe(confidence)
            except Exception as e:
                logger.debug(f"Metrics recording error: {e}")
    
    def record_patch_conflict(self, resolution_strategy: str):
        """Track patch conflicts and resolution strategies (GAP 1).

        Args:
            resolution_strategy (str): The resolution strategy.
        """
        if PROM_AVAILABLE:
            try:
                self.patch_conflicts.labels(resolution_strategy=resolution_strategy).inc()
            except Exception as e:
                logger.debug(f"Metrics recording error: {e}")
        logger.warning(f"🔄 Patch CONFLICT: resolved via {resolution_strategy}")


# Singleton instance
_global_patch_metrics: Optional[PatchMetricsCollector] = None


def get_patch_metrics() -> PatchMetricsCollector:
    """Get global PatchMetricsCollector instance (singleton).

    Returns:
        PatchMetricsCollector: Resulting PatchMetricsCollector instance.
    """
    global _global_patch_metrics
    if _global_patch_metrics is None:
        _global_patch_metrics = PatchMetricsCollector()
    return _global_patch_metrics
