"""Business logic service for deduplication service."""

import logging
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session

from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.models import LifecycleStatus

logger = logging.getLogger("app.services.deduplication_service")


class DeduplicationService:
    """Cluster similar feedback records to reduce noise."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", similarity_threshold: float = 0.88):
        """Initialize a new instance of DeduplicationService.

        Args:
            model_name (str): Name of the model.
            similarity_threshold (float): The similarity threshold.
        """
        self.model_name = model_name
        self.similarity_threshold = similarity_threshold
        self._embedder = None

    @property
    def embedder(self):
        """Get embedder property value.

        Returns:
            Result of the operation.
        """
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self.model_name)
            except Exception as exc:
                logger.warning("Could not initialize SentenceTransformer for deduplication: %s", exc)
                self._embedder = False
        return self._embedder

    def cluster_open_records(self, db: Session) -> int:
        """Find and merge duplicate open records.
        Oldest record becomes canonical, later duplicates are marked RESOLVED.

        Args:
            db (Session): Database session instance.

        Returns:
            int: Resulting int instance.
        """
        records: List[UnifiedEvaluationRecord] = (
            db.query(UnifiedEvaluationRecord)
            .filter(
                UnifiedEvaluationRecord.lifecycle_status.in_([
                    LifecycleStatus.OPEN,
                    LifecycleStatus.OPEN.value if hasattr(LifecycleStatus.OPEN, "value") else "open",
                    "open"
                ])
            )
            .order_by(UnifiedEvaluationRecord.session_id)
            .all()
        )

        if len(records) < 2:
            return 0

        # Extract text for deduplication
        texts = []
        for r in records:
            from app.schemas.response_feedback_table import ResponseFeedback
            feedback_text = ""
            if r.feedback_ref:
                feedback = db.query(ResponseFeedback).filter(ResponseFeedback.feedback_id == r.feedback_ref).first()
                if feedback and feedback.feedback_text:
                    feedback_text = feedback.feedback_text
            text = f"{feedback_text} {r.root_cause} {r.severity}".strip()
            texts.append(text or r.response_id)

        merged_count = 0
        embedder = self.embedder

        if embedder:
            try:
                from sklearn.metrics.pairwise import cosine_similarity
                embeddings = embedder.encode(texts)
                similarity_matrix = cosine_similarity(embeddings)

                resolved_set = set()
                for i in range(len(records)):
                    if i in resolved_set:
                        continue
                    for j in range(i + 1, len(records)):
                        if j in resolved_set:
                            continue
                        if similarity_matrix[i][j] >= self.similarity_threshold:
                            canonical = records[i]
                            duplicate = records[j]

                            duplicate.lifecycle_status = (
                                LifecycleStatus.RESOLVED.value
                                if hasattr(LifecycleStatus.RESOLVED, "value")
                                else "resolved"
                            )
                            duplicate.updated_at = datetime.now(timezone.utc).isoformat()
                            
                            evidence = duplicate.dissatisfaction_evidence_json or {}
                            if isinstance(evidence, dict):
                                evidence["merged_into"] = canonical.response_id
                                duplicate.dissatisfaction_evidence_json = evidence

                            resolved_set.add(j)
                            merged_count += 1
                            logger.info("Merged duplicate %s into %s", duplicate.response_id, canonical.response_id)

                db.commit()
            except Exception as exc:
                logger.error("Embedding deduplication failed: %s", exc)
                db.rollback()
        else:
            # Fallback simple string match
            resolved_set = set()
            for i in range(len(records)):
                if i in resolved_set:
                    continue
                for j in range(i + 1, len(records)):
                    if j in resolved_set:
                        continue
                    if texts[i] and texts[i] == texts[j]:
                        canonical = records[i]
                        duplicate = records[j]

                        duplicate.lifecycle_status = (
                            LifecycleStatus.RESOLVED.value
                            if hasattr(LifecycleStatus.RESOLVED, "value")
                            else "resolved"
                        )
                        duplicate.updated_at = datetime.now(timezone.utc).isoformat()
                        resolved_set.add(j)
                        merged_count += 1

            if merged_count > 0:
                db.commit()

        logger.info("Deduplication complete: merged %d records", merged_count)
        return merged_count
