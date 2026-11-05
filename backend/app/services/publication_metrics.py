"""
publication_metrics.py
======================
B07: Prometheus metrics for patch publication pipeline.

Tracks:
- State transition counts and latencies
- Verification success/failure rates
- Rollback frequencies
- Outbox processing performance
"""

import logging
from typing import Optional
from datetime import datetime, timezone
try:
    from prometheus_client import Counter, Histogram, Gauge, Summary
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logging.warning("prometheus_client not installed - metrics disabled")

logger = logging.getLogger("app.services.publication_metrics")


# B07: Patch State Transition Metrics
if PROMETHEUS_AVAILABLE:
    patch_state_transitions = Counter(
        'amc_patch_state_transitions_total',
        'Total number of patch state transitions',
        ['from_state', 'to_state', 'success']
    )
    
    patch_state_duration = Histogram(
        'amc_patch_state_duration_seconds',
        'Time spent in each patch state',
        ['state'],
        buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600]
    )
    
    # B07: Verification Metrics
    graph_verifications = Counter(
        'amc_graph_verifications_total',
        'Total number of graph mutation verifications',
        ['status']  # success, value_mismatch, node_not_found
    )
    
    reindex_verifications = Counter(
        'amc_reindex_verifications_total',
        'Total number of vector reindex verifications',
        ['status']  # completed, failed
    )
    
    # B07: Rollback Metrics
    rollbacks = Counter(
        'amc_rollbacks_total',
        'Total number of rollback operations',
        ['proposal_type', 'reason_category']
    )
    
    # B07: Outbox Processing Metrics
    outbox_events_processed = Counter(
        'amc_outbox_events_processed_total',
        'Total number of outbox events processed',
        ['event_type', 'status']  # completed, failed
    )
    
    outbox_processing_duration = Histogram(
        'amc_outbox_processing_duration_seconds',
        'Duration of outbox event processing',
        ['event_type'],
        buckets=[0.1, 0.5, 1, 2, 5, 10, 30]
    )
    
    outbox_queue_size = Gauge(
        'amc_outbox_queue_size',
        'Number of pending events in outbox',
        []
    )
    
    # B07: Pipeline Health Metrics
    active_patches = Gauge(
        'amc_active_patches_total',
        'Total number of active patches currently serving',
        []
    )
    
    proposal_approval_latency = Summary(
        'amc_proposal_approval_latency_seconds',
        'Time from proposal creation to approval'
    )
    
    proposal_application_latency = Summary(
        'amc_proposal_application_latency_seconds',
        'Time from approval to application'
    )


class PublicationMetrics:
    """
    B07: Centralized metrics recording for publication pipeline.
    """
    
    def __init__(self):
        """Initialize metrics recorder."""
        self.enabled = PROMETHEUS_AVAILABLE
        if not self.enabled:
            logger.warning("B07: Prometheus metrics disabled (library not available)")
    
    def record_state_transition(
        self,
        from_state: str,
        to_state: str,
        success: bool = True
    ) -> None:
        """Record a patch state transition.
        
        B07: Track state machine transitions.
        
        Args:
            from_state: Source state
            to_state: Target state
            success: Whether transition succeeded
        """
        if not self.enabled:
            return
        
        try:
            patch_state_transitions.labels(
                from_state=from_state,
                to_state=to_state,
                success=str(success).lower()
            ).inc()
        except Exception as exc:
            logger.debug("B07: Failed to record metric: %s", exc)
    
    def record_verification_result(
        self,
        verification_type: str,
        status: str
    ) -> None:
        """Record a verification result.
        
        B07: Track verification success/failure.
        
        Args:
            verification_type: 'graph' or 'reindex'
            status: Verification outcome
        """
        if not self.enabled:
            return
        
        try:
            if verification_type == "graph":
                graph_verifications.labels(status=status).inc()
            elif verification_type == "reindex":
                reindex_verifications.labels(status=status).inc()
        except Exception as exc:
            logger.debug("B07: Failed to record metric: %s", exc)
    
    def record_rollback(
        self,
        proposal_type: str,
        reason: str
    ) -> None:
        """Record a rollback operation.
        
        B07: Track rollback frequency and reasons.
        
        Args:
            proposal_type: 'graph' or 'vector'
            reason: Rollback reason
        """
        if not self.enabled:
            return
        
        try:
            # Categorize reason for metric cardinality
            reason_category = self._categorize_rollback_reason(reason)
            rollbacks.labels(
                proposal_type=proposal_type,
                reason_category=reason_category
            ).inc()
        except Exception as exc:
            logger.debug("B07: Failed to record metric: %s", exc)
    
    def record_outbox_event(
        self,
        event_type: str,
        status: str,
        duration_seconds: Optional[float] = None
    ) -> None:
        """Record outbox event processing.
        
        B07: Track outbox processing performance.
        
        Args:
            event_type: Type of event
            status: Processing outcome (completed, failed)
            duration_seconds: Processing duration
        """
        if not self.enabled:
            return
        
        try:
            outbox_events_processed.labels(
                event_type=event_type,
                status=status
            ).inc()
            
            if duration_seconds is not None:
                outbox_processing_duration.labels(
                    event_type=event_type
                ).observe(duration_seconds)
        except Exception as exc:
            logger.debug("B07: Failed to record metric: %s", exc)
    
    def update_outbox_queue_size(self, size: int) -> None:
        """Update outbox queue size gauge.
        
        B07: Track pending event backlog.
        
        Args:
            size: Current queue size
        """
        if not self.enabled:
            return
        
        try:
            outbox_queue_size.set(size)
        except Exception as exc:
            logger.debug("B07: Failed to record metric: %s", exc)
    
    def update_active_patches_count(self, count: int) -> None:
        """Update active patches gauge.
        
        B07: Track currently serving patches.
        
        Args:
            count: Number of active patches
        """
        if not self.enabled:
            return
        
        try:
            active_patches.set(count)
        except Exception as exc:
            logger.debug("B07: Failed to record metric: %s", exc)
    
    def record_proposal_latency(
        self,
        stage: str,
        duration_seconds: float
    ) -> None:
        """Record proposal processing latency.
        
        B07: Track pipeline latency.
        
        Args:
            stage: 'approval' or 'application'
            duration_seconds: Time in seconds
        """
        if not self.enabled:
            return
        
        try:
            if stage == "approval":
                proposal_approval_latency.observe(duration_seconds)
            elif stage == "application":
                proposal_application_latency.observe(duration_seconds)
        except Exception as exc:
            logger.debug("B07: Failed to record metric: %s", exc)
    
    def _categorize_rollback_reason(self, reason: str) -> str:
        """Categorize rollback reason to limit cardinality.
        
        Args:
            reason: Raw rollback reason
            
        Returns:
            Category label
        """
        reason_lower = reason.lower()
        
        if "quality" in reason_lower or "incorrect" in reason_lower:
            return "data_quality"
        elif "conflict" in reason_lower or "inconsistent" in reason_lower:
            return "conflict"
        elif "security" in reason_lower or "unauthorized" in reason_lower:
            return "security"
        elif "performance" in reason_lower or "timeout" in reason_lower:
            return "performance"
        else:
            return "other"


# Global metrics instance
_metrics = PublicationMetrics()


def get_publication_metrics() -> PublicationMetrics:
    """Get global publication metrics instance.
    
    B07: Singleton accessor.
    
    Returns:
        PublicationMetrics instance
    """
    return _metrics
