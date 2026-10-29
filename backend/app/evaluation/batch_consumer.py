# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
batch_consumer.py
==================
Batch evaluation consumer for records flagged with repair=True.
Processes pending unified_evaluation_records in batches of 25 with shared context caching.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import cast, or_, String
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.logging import log_step_info, log_step_error, log_step_warning
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.models import LifecycleStatus
from app.evaluation.evaluation_router import EvaluationRouter
from app.evaluation.shared_context_cache import get_shared_cache

logger = logging.getLogger("app.evaluation.batch_consumer")


class BatchEvaluationConsumer:
    """
    Consumes unified_evaluation_records where repair=True and lifecycle_status='open'.
    Processes in batches of 25 with shared context optimization.
    """

    def __init__(self, batch_size: int = 25):
        """Initialize a new instance of BatchEvaluationConsumer.

        Args:
            batch_size (int): The batch size.
        """
        self.batch_size = batch_size
        self.router = EvaluationRouter()
        self.cache = get_shared_cache()

    async def _fetch_subgraph_from_neo4j(self, entity_id: str) -> Optional[dict]:
        """Fetch 1-hop subgraph for entity from Neo4j.

        Args:
            entity_id (str): Unique identifier of the entity.

        Returns:
            Optional[dict]: Dictionary containing result data or status.
        """
        try:
            from app.graph.client import GraphClient
            client = GraphClient()
            cypher = """
            MATCH (e {name: $entity_id})-[r]-(target)
            RETURN e.name as source, type(r) as relationship, target.name as target_name
            LIMIT 20
            """
            results = await client.run(cypher, entity_id=entity_id)
            if not results:
                # Try by id property
                cypher_id = """
                MATCH (e {id: $entity_id})-[r]-(target)
                RETURN e.id as source, type(r) as relationship, target.name as target_name
                LIMIT 20
                """
                results = await client.run(cypher_id, entity_id=entity_id)
            return {"entity_id": entity_id, "triplets": results}
        except Exception as exc:
            logger.debug("Could not fetch subgraph from Neo4j for %s: %s", entity_id, exc)
            return None

    async def _build_evidence_pack(self, record: UnifiedEvaluationRecord, db: Session) -> Dict[str, Any]:
        """Fetch evidence from query_evidence table and assemble evaluation pack.

        Args:
            record (UnifiedEvaluationRecord): The record.
            db (Session): Database session instance.

        Returns:
            Dict[str, Any]: Dictionary containing result data or status.
        """
        from app.schemas.query_evidence_table import QueryEvidence

        evidence = (
            db.query(QueryEvidence)
            .filter(QueryEvidence.response_id == record.response_id)
            .first()
        )

        if not evidence:
            raise ValueError(f"No QueryEvidence found for response {record.response_id}")

        # Extract textual fields from evidence JSON
        context_str = ""
        chunks_list = []
        assembled = evidence.assembled_context_json
        if isinstance(assembled, list):
            chunks_list = assembled
            context_str = " ".join([c.get("content") or c.get("text") or "" for c in assembled if isinstance(c, dict)])
        elif isinstance(assembled, dict):
            chunks_list = assembled.get("chunks", [assembled])
            context_str = assembled.get("context", "")

        response_str = ""
        synthesis = evidence.synthesis_output_json
        if isinstance(synthesis, dict):
            response_str = synthesis.get("answer") or synthesis.get("response") or str(synthesis)
        else:
            response_str = str(synthesis or "")

        evidence_pack: Dict[str, Any] = {
            "response_text": response_str,
            "query": evidence.query_text or "",
            "context": context_str,
            "chunks": chunks_list,
            "intent": evidence.query_intent or evidence.query_type,
            "entity_id": None,
        }

        # Inspect chunks for entity identification
        for chunk in chunks_list:
            if isinstance(chunk, dict) and chunk.get("entity_id"):
                evidence_pack["entity_id"] = chunk["entity_id"]
                break

        # Subgraph caching
        entity_id = evidence_pack.get("entity_id")
        if entity_id:
            subgraph = self.cache.get_subgraph(entity_id, hops=1)
            if subgraph is None:
                subgraph = await self._fetch_subgraph_from_neo4j(entity_id)
                if subgraph:
                    self.cache.set_subgraph(entity_id, hops=1, data=subgraph)
            evidence_pack["subgraph"] = subgraph

        return evidence_pack

    async def process_batch(self, db: Optional[Session] = None) -> int:
        """Main batch processing step.

        Args:
            db (Optional[Session]): Optional database session. If None, creates a new SessionLocal.

        Returns:
            int: Resulting int instance.
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            # Clean expired cache entries
            self.cache.clear_expired()

            # Fetch pending records requiring repair that haven't been evaluated
            pending = (
                db.query(UnifiedEvaluationRecord)
                .filter(
                    UnifiedEvaluationRecord.repair.in_([True, 1]),
                    UnifiedEvaluationRecord.lifecycle_status.in_(["open", LifecycleStatus.OPEN, getattr(LifecycleStatus.OPEN, "value", "open")]),
                    or_(
                        UnifiedEvaluationRecord.deterministic_results.is_(None),
                        cast(UnifiedEvaluationRecord.deterministic_results, String) == "null",
                        cast(UnifiedEvaluationRecord.deterministic_results, String) == "",
                    ),
                )
                .order_by(UnifiedEvaluationRecord.created_at)
                .limit(self.batch_size)
                .all()
            )

            if not pending:
                return 0

            log_step_info(
                logger,
                "BATCH_FETCH",
                "Step 1: Fetched %d pending records flagged for automated evaluation & repair",
                len(pending)
            )

            # Advance status to DIAGNOSING
            for record in pending:
                record.lifecycle_status = LifecycleStatus.DIAGNOSING.value if hasattr(LifecycleStatus.DIAGNOSING, "value") else "diagnosing"
                record.updated_at = datetime.now(timezone.utc).isoformat()
            db.commit()

            log_step_info(
                logger,
                "BATCH_DIAGNOSING",
                "Step 2: Advanced %d records to diagnosing status for evaluation",
                len(pending)
            )

            processed = 0
            for record in pending:
                try:
                    evidence_pack = await self._build_evidence_pack(record, db)
                    eval_result = await asyncio.to_thread(
                        self.router.evaluate,
                        response_id=record.response_id,
                        evidence_pack=evidence_pack,
                    )

                    record.deterministic_results = eval_result.get("rule_results")
                    record.gnn_plausibility_score = eval_result.get("gnn_plausibility_score", 0.5)
                    record.semantic_results = eval_result.get("nli_result")
                    record.llm_evaluation = eval_result.get("critic_result")

                    raw_verdict = eval_result.get("verdict")
                    verdict_val = None
                    if raw_verdict:
                        norm = str(raw_verdict).lower().strip()
                        if norm in ("valid", "partially_valid", "invalid", "subjective", "insufficient_evidence"):
                            verdict_val = norm
                        elif norm in ("pass",):
                            verdict_val = "valid"
                        elif norm in ("fail",):
                            verdict_val = "invalid"
                        elif norm in ("warn", "revise", "partial"):
                            verdict_val = "partially_valid"
                        elif "inconclusive" in norm or "insufficient" in norm:
                            verdict_val = "insufficient_evidence"
                        else:
                            verdict_val = "valid"

                    record.adjudication_verdict = verdict_val
                    record.adjudication_confidence = eval_result.get("confidence")

                    # If evaluation passes -> RESOLVED, else revert to OPEN for repair proposal
                    if str(raw_verdict).upper() in ("PASS", "VALID") or verdict_val == "valid":
                        record.lifecycle_status = LifecycleStatus.RESOLVED.value if hasattr(LifecycleStatus.RESOLVED, "value") else "resolved"
                    else:
                        record.lifecycle_status = LifecycleStatus.OPEN.value if hasattr(LifecycleStatus.OPEN, "value") else "open"

                    record.updated_at = datetime.now(timezone.utc).isoformat()
                    processed += 1

                    log_step_info(
                        logger,
                        "RECORD_EVALUATION",
                        "Step 3: Evaluated response %s -> verdict=%s (confidence=%.2f, status=%s)",
                        record.response_id, verdict_val, record.adjudication_confidence or 0.0, record.lifecycle_status
                    )
                except Exception as exc:
                    log_step_error(
                        logger,
                        "RECORD_EVAL_ERROR",
                        "Step 3 error: Evaluation failed for response %s: %s (marked as insufficient_evidence)",
                        record.response_id, exc
                    )
                    record.deterministic_results = [{"error": str(exc), "verdict": "INCONCLUSIVE"}]
                    record.adjudication_verdict = "insufficient_evidence"
                    record.lifecycle_status = LifecycleStatus.RESOLVED.value if hasattr(LifecycleStatus.RESOLVED, "value") else "resolved"
                    record.updated_at = datetime.now(timezone.utc).isoformat()
                    processed += 1

            db.commit()
            log_step_info(
                logger,
                "BATCH_COMPLETE",
                "Step 4: Batch evaluation complete: %d/%d records successfully evaluated",
                processed, len(pending)
            )
            return processed
        finally:
            if should_close:
                db.close()


_batch_task: Optional[asyncio.Task] = None
_consumer_running: bool = False


async def start_batch_consumer(interval_seconds: int = 300) -> None:
    """Start background loop for batch evaluation consumer.

    Args:
        interval_seconds (int): Collection or list of interval seconds.
    """
    global _consumer_running, _batch_task
    if _consumer_running:
        return
    _consumer_running = True
    consumer = BatchEvaluationConsumer(batch_size=25)
    log_step_info(
        logger,
        "CONSUMER_STARTED",
        "Batch evaluation worker started: polling every %d seconds for pending records",
        interval_seconds
    )
    while _consumer_running:
        try:
            await asyncio.sleep(interval_seconds)
            await consumer.process_batch()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            log_step_error(logger, "CONSUMER_LOOP_ERROR", "Batch consumer worker loop error: %s", exc)


async def stop_batch_consumer() -> None:
    """Stop the background batch evaluation consumer gracefully."""
    global _consumer_running, _batch_task
    _consumer_running = False
    if _batch_task and not _batch_task.done():
        _batch_task.cancel()
        try:
            await asyncio.wait_for(_batch_task, timeout=5.0)
            log_step_info(logger, "CONSUMER_STOPPED", "Batch evaluation worker stopped successfully")
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        except Exception as exc:
            logger.warning("Error stopping batch consumer task: %s", exc)
        finally:
            _batch_task = None
