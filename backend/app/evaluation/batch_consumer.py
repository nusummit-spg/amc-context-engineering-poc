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

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
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

    async def process_batch(self) -> int:
        """Main batch processing step.

        Returns:
            int: Resulting int instance.
        """
        db = SessionLocal()
        try:
            # Clean expired cache entries
            self.cache.clear_expired()

            # Fetch pending records requiring repair that haven't been evaluated
            pending = (
                db.query(UnifiedEvaluationRecord)
                .filter(
                    UnifiedEvaluationRecord.repair == True,
                    UnifiedEvaluationRecord.lifecycle_status == LifecycleStatus.OPEN,
                    UnifiedEvaluationRecord.deterministic_results.is_(None),
                )
                .order_by(UnifiedEvaluationRecord.created_at)
                .limit(self.batch_size)
                .all()
            )

            if not pending:
                return 0

            logger.info("BatchEvaluationConsumer processing batch of %d records", len(pending))

            # Advance status to DIAGNOSING
            for record in pending:
                record.lifecycle_status = LifecycleStatus.DIAGNOSING
                record.updated_at = datetime.now(timezone.utc).isoformat()
            db.commit()

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
                    record.adjudication_verdict = eval_result.get("verdict")
                    record.adjudication_confidence = eval_result.get("confidence")

                    # If evaluation passes -> RESOLVED, else revert to OPEN for repair proposal
                    if eval_result.get("verdict") in ("PASS", "VALID"):
                        record.lifecycle_status = LifecycleStatus.RESOLVED
                    else:
                        record.lifecycle_status = LifecycleStatus.OPEN

                    record.updated_at = datetime.now(timezone.utc).isoformat()
                    processed += 1
                except Exception as exc:
                    logger.error("Evaluation failed for record %s: %s", record.response_id, exc)
                    record.lifecycle_status = LifecycleStatus.OPEN

            db.commit()
            logger.info("BatchEvaluationConsumer completed: %d/%d records evaluated", processed, len(pending))
            return processed
        finally:
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
    logger.info("BatchEvaluationConsumer started (interval=%ds)", interval_seconds)
    while _consumer_running:
        try:
            await asyncio.sleep(interval_seconds)
            await consumer.process_batch()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Batch consumer loop error: %s", exc)


async def stop_batch_consumer() -> None:
    """Stop the background batch evaluation consumer gracefully."""
    global _consumer_running, _batch_task
    _consumer_running = False
    if _batch_task and not _batch_task.done():
        _batch_task.cancel()
        try:
            await asyncio.wait_for(_batch_task, timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        except Exception as exc:
            logger.warning("Error stopping batch consumer task: %s", exc)
        finally:
            _batch_task = None
