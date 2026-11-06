"""
operational_metrics_service.py
===============================
Operational metrics, cost and observability.

P09: Operational metrics, cost and observability.

Records:
- Success/failure separately for intent created, approval, indexed/staged, 
  externally applied, readback verified, activated, rolled back, replayed, dead-lettered
- Correlation IDs, tenant-safe trace attributes, latency, index size, token/embedding cost
- Retry distribution and SLO/error budget
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging
import time

logger = logging.getLogger("operational_metrics")


class OperationalMetricsService:
    """
    P09: Operational metrics service.
    
    Tracks publication lifecycle metrics without exposing PII or sensitive data.
    """
    
    def __init__(self):
        """Initialize operational metrics service."""
        self._metrics: Dict[str, List[Dict[str, Any]]] = {
            "intent_created": [],
            "approval": [],
            "index_staged": [],
            "external_applied": [],
            "readback_verified": [],
            "activated": [],
            "rolled_back": [],
            "replayed": [],
            "dead_lettered": [],
        }
        self._costs: Dict[str, float] = {
            "embedding_tokens": 0,
            "embedding_cost_usd": 0.0,
            "graph_operations": 0,
            "graph_cost_usd": 0.0,
        }
    
    def record_intent_created(
        self,
        intent_id: str,
        tenant_id: str,
        correlation_id: str,
        proposal_id: str,
        publication_type: str,
    ) -> None:
        """Record publication intent creation.
        
        Args:
            intent_id: Publication intent ID
            tenant_id: Tenant ID
            correlation_id: Correlation ID
            proposal_id: Proposal ID
            publication_type: Type of publication
        """
        self._metrics["intent_created"].append({
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "proposal_id": proposal_id,
            "publication_type": publication_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("P09: Recorded intent created: %s", intent_id)
    
    def record_approval(
        self,
        intent_id: str,
        tenant_id: str,
        correlation_id: str,
        proposal_id: str,
        approver_id: str,
        latency_ms: float,
    ) -> None:
        """Record approval event.
        
        Args:
            intent_id: Publication intent ID
            tenant_id: Tenant ID
            correlation_id: Correlation ID
            proposal_id: Proposal ID
            approver_id: Approver user ID
            latency_ms: Approval latency in milliseconds
        """
        self._metrics["approval"].append({
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "proposal_id": proposal_id,
            "approver_id": approver_id,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("P09: Recorded approval: %s", intent_id)
    
    def record_index_staged(
        self,
        intent_id: str,
        tenant_id: str,
        correlation_id: str,
        index_type: str,
        index_size: int,
        latency_ms: float,
    ) -> None:
        """Record index staging event.
        
        Args:
            intent_id: Publication intent ID
            tenant_id: Tenant ID
            correlation_id: Correlation ID
            index_type: Type of index (graph/vector)
            index_size: Number of items staged
            latency_ms: Staging latency in milliseconds
        """
        self._metrics["index_staged"].append({
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "index_type": index_type,
            "index_size": index_size,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("P09: Recorded index staged: %s (size: %d)", intent_id, index_size)
    
    def record_external_applied(
        self,
        intent_id: str,
        tenant_id: str,
        correlation_id: str,
        operation_type: str,
        entities_affected: int,
        latency_ms: float,
    ) -> None:
        """Record external application event.
        
        Args:
            intent_id: Publication intent ID
            tenant_id: Tenant ID
            correlation_id: Correlation ID
            operation_type: Type of operation (graph_mutation/vector_reindex)
            entities_affected: Number of entities affected
            latency_ms: Application latency in milliseconds
        """
        self._metrics["external_applied"].append({
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "operation_type": operation_type,
            "entities_affected": entities_affected,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("P09: Recorded external applied: %s (entities: %d)", 
                   intent_id, entities_affected)
    
    def record_readback_verified(
        self,
        intent_id: str,
        tenant_id: str,
        correlation_id: str,
        readback_method: str,
        match: bool,
        latency_ms: float,
    ) -> None:
        """Record readback verification event.
        
        Args:
            intent_id: Publication intent ID
            tenant_id: Tenant ID
            correlation_id: Correlation ID
            readback_method: Method used (readback/checksum/probe_query/audit_log)
            match: Whether readback matches expected postimage
            latency_ms: Verification latency in milliseconds
        """
        self._metrics["readback_verified"].append({
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "readback_method": readback_method,
            "match": match,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("P09: Recorded readback verified: %s (match: %s)", intent_id, match)
    
    def record_activated(
        self,
        intent_id: str,
        tenant_id: str,
        correlation_id: str,
        new_active_version: str,
        latency_ms: float,
    ) -> None:
        """Record activation event.
        
        Args:
            intent_id: Publication intent ID
            tenant_id: Tenant ID
            correlation_id: Correlation ID
            new_active_version: Version that became active
            latency_ms: Activation latency in milliseconds
        """
        self._metrics["activated"].append({
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "new_active_version": new_active_version,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("P09: Recorded activated: %s (version: %s)", 
                   intent_id, new_active_version)
    
    def record_rolled_back(
        self,
        intent_id: str,
        tenant_id: str,
        correlation_id: str,
        rollback_method: str,
        restored_entities: int,
        latency_ms: float,
    ) -> None:
        """Record rollback event.
        
        Args:
            intent_id: Publication intent ID
            tenant_id: Tenant ID
            correlation_id: Correlation ID
            rollback_method: Method used (graph/vector)
            restored_entities: Number of entities restored
            latency_ms: Rollback latency in milliseconds
        """
        self._metrics["rolled_back"].append({
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "rollback_method": rollback_method,
            "restored_entities": restored_entities,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("P09: Recorded rolled back: %s (restored: %d)", 
                   intent_id, restored_entities)
    
    def record_replayed(
        self,
        intent_id: str,
        tenant_id: str,
        correlation_id: str,
        replay_reason: str,
        attempts: int,
    ) -> None:
        """Record replay event.
        
        Args:
            intent_id: Publication intent ID
            tenant_id: Tenant ID
            correlation_id: Correlation ID
            replay_reason: Reason for replay (crash/retry/duplicate)
            attempts: Attempt number
        """
        self._metrics["replayed"].append({
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "replay_reason": replay_reason,
            "attempts": attempts,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("P09: Recorded replayed: %s (reason: %s, attempts: %d)", 
                   intent_id, replay_reason, attempts)
    
    def record_dead_lettered(
        self,
        intent_id: str,
        tenant_id: str,
        correlation_id: str,
        error_message: str,
        max_retries_exceeded: bool,
    ) -> None:
        """Record dead-letter event.
        
        Args:
            intent_id: Publication intent ID
            tenant_id: Tenant ID
            correlation_id: Correlation ID
            error_message: Error message
            max_retries_exceeded: Whether max retries were exceeded
        """
        self._metrics["dead_lettered"].append({
            "intent_id": intent_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "error_message": error_message,
            "max_retries_exceeded": max_retries_exceeded,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.warning("P09: Recorded dead-lettered: %s (error: %s)", 
                      intent_id, error_message)
    
    def record_cost(
        self,
        cost_type: str,
        amount: float,
        currency: str = "USD",
    ) -> None:
        """Record cost event.
        
        Args:
            cost_type: Type of cost (embedding/graph_operation)
            amount: Cost amount
            currency: Currency code (default: USD)
        """
        if cost_type == "embedding_tokens":
            self._costs["embedding_tokens"] += amount
        elif cost_type == "embedding_cost_usd":
            self._costs["embedding_cost_usd"] += amount
        elif cost_type == "graph_operations":
            self._costs["graph_operations"] += amount
        elif cost_type == "graph_cost_usd":
            self._costs["graph_cost_usd"] += amount
        else:
            logger.warning("P09: Unknown cost type: %s", cost_type)
    
    def get_metric_summary(self) -> Dict[str, Any]:
        """Get metric summary for monitoring.
        
        Returns:
            Summary dict with counts and distributions
        """
        return {
            "intent_created": len(self._metrics["intent_created"]),
            "approval": len(self._metrics["approval"]),
            "index_staged": len(self._metrics["index_staged"]),
            "external_applied": len(self._metrics["external_applied"]),
            "readback_verified": len(self._metrics["readback_verified"]),
            "activated": len(self._metrics["activated"]),
            "rolled_back": len(self._metrics["rolled_back"]),
            "replayed": len(self._metrics["replayed"]),
            "dead_lettered": len(self._metrics["dead_lettered"]),
            "costs": self._costs,
            "total_published": len(self._metrics["activated"]),
            "total_rolled_back": len(self._metrics["rolled_back"]),
            "total_failed": len(self._metrics["dead_lettered"]),
        }
    
    def get_retry_distribution(self) -> Dict[int, int]:
        """Get retry distribution.
        
        Returns:
            Dict mapping retry count to count of intents
        """
        distribution: Dict[int, int] = {}
        for replay in self._metrics["replayed"]:
            attempts = replay.get("attempts", 1)
            distribution[attempts] = distribution.get(attempts, 0) + 1
        return distribution
    
    def get_latency_histogram(self, metric_type: str) -> Dict[str, Any]:
        """Get latency histogram for a metric type.
        
        Args:
            metric_type: Type of metric (approval/index_staged/external_applied)
            
        Returns:
            Histogram data with bins
        """
        latencies = [
            m.get("latency_ms", 0)
            for m in self._metrics.get(metric_type, [])
        ]
        
        if not latencies:
            return {"min": 0, "max": 0, "avg": 0, "p95": 0, "p99": 0}
        
        latencies.sort()
        return {
            "min": latencies[0],
            "max": latencies[-1],
            "avg": sum(latencies) / len(latencies),
            "p95": latencies[int(len(latencies) * 0.95)] if len(latencies) > 0 else 0,
            "p99": latencies[int(len(latencies) * 0.99)] if len(latencies) > 0 else 0,
        }
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current metrics state.
        
        Returns:
            Current state dict
        """
        return {
            "metrics": self._metrics,
            "costs": self._costs,
        }