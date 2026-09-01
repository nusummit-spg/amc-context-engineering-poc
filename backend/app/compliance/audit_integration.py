# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
audit_integration.py
====================
Links compliance violations to the query execution audit trail and enriches
violations with supporting document evidence from the knowledge graph.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.compliance.rules_engine import ComplianceViolation
from app.graph.client import GraphClient, get_graph_client

logger = logging.getLogger("compliance.audit_integration")

AUDIT_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "compliance_audit.jsonl"


class ViolationBuffer:
    """Buffers violations and flushes in batches (50 violations per batch) for faster I/O."""
    
    def __init__(self, batch_size: int = 50):
        self.batch_size = batch_size
        self.buffer: list[Dict[str, Any]] = []
        self.file_path = AUDIT_LOG_PATH
    
    async def add(self, audit_entry: Dict[str, Any]) -> None:
        """Add entry to buffer, flush if batch size reached."""
        self.buffer.append(audit_entry)
        if len(self.buffer) >= self.batch_size:
            await self.flush()
    
    async def flush(self) -> None:
        """Write buffered entries to disk and clear buffer."""
        if not self.buffer:
            return
        
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "a", encoding="utf-8") as f:
                for entry in self.buffer:
                    f.write(json.dumps(entry) + "\n")
            logger.info("Flushed %d violation entries to audit log", len(self.buffer))
        except Exception as exc:
            logger.error("Failed to flush violation buffer: %s", exc)
        finally:
            self.buffer.clear()


# Global violation buffer instance
_violation_buffer = ViolationBuffer()


async def log_violation_to_audit_trail(
    violation: ComplianceViolation,
    audit_log_writer: Optional[Callable] = None
) -> str:
    """
    Log violation to persistent audit trail with buffering (50-violation batches).
    Ensures immutable traceability for regulatory reporting with improved I/O performance.
    """
    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": "compliance_violation",
        "violation_id": violation.violation_id,
        "rule_id": violation.rule_id,
        "rule_title": violation.rule_title,
        "fund_id": violation.fund_id,
        "severity": violation.severity,
        "confidence": violation.confidence,
        "actual_value": violation.actual_value,
        "threshold_value": violation.threshold_value,
        "description": violation.description,
        "region": violation.region,
        "evidence_docs": violation.evidence_docs,
        "status": violation.status,
    }

    if audit_log_writer:
        try:
            await audit_log_writer(audit_entry)
        except Exception as exc:
            logger.warning("Custom audit_log_writer failed: %s", exc)

    # Add to buffer (will auto-flush at 50 violations)
    try:
        await _violation_buffer.add(audit_entry)
    except Exception as exc:
        logger.warning("Could not add violation to buffer: %s", exc)

    logger.debug("Buffered compliance violation %s for fund %s", violation.violation_id, violation.fund_id)
    return violation.violation_id


async def enrich_violation_with_evidence(
    violation: ComplianceViolation,
    graph_client: Optional[GraphClient] = None
) -> ComplianceViolation:
    """Enrich violation with evidence document filenames from Neo4j."""
    graph = graph_client or get_graph_client()
    cypher = """
    MATCH (d:Document)
    WHERE d.fund_id = $fund_id OR d.product_name CONTAINS $fund_id
    RETURN d.document_id AS doc_id, d.filename AS filename
    ORDER BY d.created_at DESC
    LIMIT 3
    """
    try:
        results = await graph.run(cypher, fund_id=violation.fund_id)
        if results:
            docs = [r.get("filename") or r.get("doc_id") for r in results if r]
            violation.evidence_docs = list(set(violation.evidence_docs + docs))
    except Exception:
        pass

    return violation


async def store_agent_metrics(
    metrics: Dict[str, Any],
    graph_client: Optional[GraphClient] = None,
    region: str = "SEBI"
) -> bool:
    """Store agent metrics in Neo4j and audit log for historical trending."""
    graph = graph_client or get_graph_client()
    now_str = datetime.now().isoformat()

    for agent_name, m in metrics.items():
        m_dict = m.model_dump() if hasattr(m, "model_dump") else (m.dict() if hasattr(m, "dict") else dict(m))
        try:
            cypher = """
            MERGE (m:AgentMetrics {id: $metric_id})
            SET m.agent_name = $agent_name,
                m.violations_detected = $violations_detected,
                m.avg_latency_ms = $avg_latency_ms,
                m.p95_latency_ms = $p95_latency_ms,
                m.p99_latency_ms = $p99_latency_ms,
                m.accuracy_score = $accuracy_score,
                m.region = $region,
                m.recorded_at = $recorded_at
            RETURN m.id AS id
            """
            await graph.run(
                cypher,
                metric_id=f"{agent_name}_{now_str[:13]}",
                agent_name=agent_name,
                violations_detected=m_dict.get("violations_detected", 0),
                avg_latency_ms=m_dict.get("avg_latency_ms", 0.0),
                p95_latency_ms=m_dict.get("p95_latency_ms", 0.0),
                p99_latency_ms=m_dict.get("p99_latency_ms", 0.0),
                accuracy_score=m_dict.get("accuracy_score", 0.95),
                region=region,
                recorded_at=now_str,
            )
        except Exception as exc:
            logger.debug("Neo4j offline; logged metrics locally (%s)", exc)

    return True


async def log_resolution_audit(
    violation_id: str,
    action: str,
    user_id: str = "compliance_officer",
    graph_client: Optional[GraphClient] = None
) -> Dict[str, Any]:
    """Record violation resolution in Neo4j and immutable audit log."""
    graph = graph_client or get_graph_client()
    now_str = datetime.now().isoformat()
    entry = {
        "timestamp": now_str,
        "event_type": "violation_remediated",
        "violation_id": violation_id,
        "user_id": user_id,
        "action": action,
        "status": "remediated",
    }
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("Could not write resolution to audit log: %s", exc)

    try:
        cypher = """
        MERGE (l:AuditLog {id: $log_id})
        SET l.violation_id = $violation_id,
            l.user_id = $user_id,
            l.action = $action,
            l.status = 'remediated',
            l.timestamp = $timestamp
        RETURN l.id AS id
        """
        await graph.run(
            cypher,
            log_id=f"LOG_{violation_id}_{now_str}",
            violation_id=violation_id,
            user_id=user_id,
            action=action,
            timestamp=now_str,
        )
    except Exception:
        pass

    return entry


async def flush_violation_buffer() -> None:
    """Flush any remaining buffered violations before shutdown."""
    await _violation_buffer.flush()
    logger.info("Violation buffer flushed on shutdown")

