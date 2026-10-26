"""
Step 2  EvidenceEnrichmentService

Responsibilities (runs for BOTH active and passive rows):
  1. Fetch the frozen D0â€“D3 evidence snapshot via EvidenceAdapter.
  2. Cluster / deduplicate against existing open records on the same
     response_id + entity_name.
  3. Derive entry_route:
       - 'hitl'                    when source == 'active'
       - 'dissatisfaction_converted'  when passive + â‰¥2 dissatisfaction signals fire
       - 'automatic'               otherwise
  4. Return EnrichmentResult (including the optional DissatisfactionSignal
     for auditability).
"""

from __future__ import annotations

import re
from typing import Optional

import structlog

from feedback_loop.logging_config import get_pipeline_logger
from feedback_loop.logging import get_feedback_logger, log_step_info, log_step_warning
from feedback_loop.adapters.db import AbstractDatabaseAdapter
from feedback_loop.adapters.evidence import AbstractEvidenceAdapter
from feedback_loop.config import FeedbackLoopConfig
from feedback_loop.domain_models import (
    DissatisfactionSignal,
    EnrichmentResult,
    EntryRoute,
    EvidenceSnapshot,
    FeedbackRecord,
    FeedbackSource,
    FollowUpQuery,
)

logger = structlog.get_logger(__name__)
step_logger_enr = get_feedback_logger("enrichment")


def _cosine_similarity(text_a: str, text_b: str) -> float:
    """Lightweight TF bag-of-words cosine similarity.
    Avoids a model dependency for a simple re-query check.
    Production code can swap this for a sentence-transformer call.

    Args:
        text_a (str): The text a.
        text_b (str): The text b.

    Returns:
        float: Resulting float instance.
    """
    from collections import Counter
    import math

    def token_counts(text: str) -> Counter:
        """Token counts.

        Args:
            text (str): Input text content.

        Returns:
            Counter: Resulting Counter instance.
        """
        return Counter(re.findall(r"\w+", text.lower()))

    a, b = token_counts(text_a), token_counts(text_b)
    shared = set(a) & set(b)
    if not shared:
        return 0.0
    dot = sum(a[t] * b[t] for t in shared)
    mag_a = math.sqrt(sum(v ** 2 for v in a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _matches_correction_pattern(text: str, patterns: list[str]) -> bool:
    """Lightweight regex/keyword check  zero token cost.

    Args:
        text (str): Input text content.
        patterns (list[str]): Collection or list of patterns.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _extract_entities_simple(text: str) -> list[str]:
    """Simple capitalised-phrase extractor as a fallback when spaCy is not
    available.  Used only for same-entity dissatisfaction signal.

    Args:
        text (str): Input text content.

    Returns:
        list[str]: List of resulting items or records.
    """
    # Match runs of title-case words (2+ chars each)
    matches = re.findall(r"\b([A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,})*)\b", text)
    return [m.strip() for m in matches]


class EvidenceEnrichmentService:
    """
    Step 2  evidence fetch, enrichment, deduplication, and
    dissatisfaction signal detection.
    """

    def __init__(
        self,
        config: FeedbackLoopConfig,
        evidence_adapter: AbstractEvidenceAdapter,
        db: AbstractDatabaseAdapter,
    ) -> None:
        """Initialize a new instance of EvidenceEnrichmentService.

        Args:
            config (FeedbackLoopConfig): Configuration dictionary or settings object.
            evidence_adapter (AbstractEvidenceAdapter): The evidence adapter.
            db (AbstractDatabaseAdapter): Database session instance.
        """
        self._config = config
        self._evidence = evidence_adapter
        self._db = db

        # Lazy-load spaCy NER for same-entity check
        self._nlp = None

    def _get_nlp(self):
        """Retrieve nlp.

        Returns:
            Result of the operation.
        """
        if self._nlp is None:
            try:
                import spacy  # noqa: PLC0415
                self._nlp = spacy.load("en_core_web_sm")
            except Exception:
                self._nlp = False
        return self._nlp or None

    def _extract_entities(self, text: str) -> list[str]:
        """Extract entities.

        Args:
            text (str): Input text content.

        Returns:
            list[str]: List of resulting items or records.
        """
        nlp = self._get_nlp()
        if nlp:
            doc = nlp(text)
            return [ent.text for ent in doc.ents if ent.label_ in ("ORG", "PRODUCT", "PERSON")]
        return _extract_entities_simple(text)

    #  Dissatisfaction signal detection (Section 3) 

    def _detect_dissatisfaction(
        self,
        snapshot: EvidenceSnapshot,
        followups: list[FollowUpQuery],
    ) -> Optional[DissatisfactionSignal]:
        """Score 3 deterministic, zero-token signals against the first
        follow-up query.  Returns DissatisfactionSignal when â‰¥ min_signals
        fire, otherwise None.

        Args:
            snapshot (EvidenceSnapshot): The snapshot.
            followups (list[FollowUpQuery]): Collection or list of followups.

        Returns:
            Optional[DissatisfactionSignal]: Matching object or record if found, None otherwise.
        """
        if not followups:
            return None  # silence  stays automatic

        next_query = followups[0]
        fired: list[str] = []

        # Signal 1  re-query similarity
        similarity = _cosine_similarity(snapshot.original_query, next_query.text)
        if similarity >= self._config.requery_similarity_threshold:
            fired.append("requery_similarity")

        # Signal 2  correction language
        if _matches_correction_pattern(next_query.text, self._config.correction_patterns):
            fired.append("correction_language")

        # Signal 3  same entity
        if snapshot.entity_name:
            entities_in_followup = self._extract_entities(next_query.text)
            if any(
                snapshot.entity_name.lower() in e.lower()
                or e.lower() in snapshot.entity_name.lower()
                for e in entities_in_followup
            ):
                fired.append("same_entity")

        if len(fired) >= self._config.min_signals_required:
            return DissatisfactionSignal(
                triggers=fired,
                source_text=next_query.text,
                confidence=round(len(fired) / 3, 4),
            )
        return None

    #  Public API 

    def run(self, row: FeedbackRecord, session_id: str = None, feedback_id: str = None) -> EnrichmentResult:
        """Run operation.

        Args:
            row (FeedbackRecord): The row.
            session_id (str): Unique identifier of the session.
            feedback_id (str): Unique identifier of the feedback.

        Returns:
            EnrichmentResult: Resulting EnrichmentResult instance.
        """
        """
        """
        step_logger = None
        log_step_info(
            step_logger_enr,
            "ENRICHMENT_START",
            "Enrichment starting for response_id=%s (source=%s)",
            row.response_id,
            row.source,
        )
        if session_id and feedback_id:
            step_logger = get_pipeline_logger("enrichment", session_id, feedback_id)
            if step_logger:
                step_logger.info("Enrichment starting")
        
        # 1. Fetch frozen evidence snapshot
        snapshot = self._evidence.get_evidence_snapshot(row.response_id)
        evidence_snapshot_ref = row.response_id  # FK into interaction_evidence

        # 2. Deduplication  check for an existing open cluster
        existing = self._db.find_open_cluster(row.response_id, row.entity_name)
        if existing:
            log_step_info(
                step_logger_enr,
                "DUPLICATE_DETECTED",
                "Duplicate cluster detected for response_id=%s, entity=%s",
                row.response_id,
                row.entity_name,
            )
            if step_logger:
                step_logger.info("Duplicate detected", response_id=row.response_id)
            logger.info(
                "duplicate_detected",
                feedback_id=row.feedback_id,
                response_id=row.response_id,
                existing_entry_route=existing.entry_route,
            )
            return EnrichmentResult(
                evidence_snapshot_ref=evidence_snapshot_ref,
                evidence_snapshot=snapshot,
                is_duplicate=True,
                cluster_id=row.response_id,
                entry_route=EntryRoute(existing.entry_route),
            )

        # 3. entry_route  active is always hitl
        if row.source == FeedbackSource.ACTIVE:
            log_step_info(
                step_logger_enr,
                "ENRICHMENT_COMPLETE",
                "Enrichment complete for response_id=%s: entry_route=hitl",
                row.response_id,
            )
            return EnrichmentResult(
                evidence_snapshot_ref=evidence_snapshot_ref,
                evidence_snapshot=snapshot,
                is_duplicate=False,
                entry_route=EntryRoute.HITL,
            )

        # 4. Passive  check for dissatisfaction signal
        followups = self._evidence.get_followup_activity(
            session_id=row.session_id,
            response_id=row.response_id,
            window_minutes=self._config.passive_window_minutes,
        )
        dissatisfaction = self._detect_dissatisfaction(snapshot, followups)

        if dissatisfaction:
            log_step_info(
                step_logger_enr,
                "DISSATISFACTION_DETECTED",
                "Dissatisfaction signals detected for %s: %s (confidence=%.2f)",
                row.response_id,
                dissatisfaction.triggers,
                dissatisfaction.confidence,
            )

        entry_route = (
            EntryRoute.DISSATISFACTION_CONVERTED
            if dissatisfaction
            else EntryRoute.AUTOMATIC
        )

        log_step_info(
            step_logger_enr,
            "ENRICHMENT_COMPLETE",
            "Enrichment complete for response_id=%s: entry_route=%s",
            row.response_id,
            entry_route,
        )

        if step_logger:
            step_logger.info("Enrichment complete", entry_route=str(entry_route))
        logger.info(
            "enrichment_complete",
            feedback_id=row.feedback_id,
            entry_route=entry_route,
            dissatisfaction_signals=dissatisfaction.triggers if dissatisfaction else [],
        )

        return EnrichmentResult(
            evidence_snapshot_ref=evidence_snapshot_ref,
            evidence_snapshot=snapshot,
            is_duplicate=False,
            entry_route=entry_route,
            dissatisfaction_signal=dissatisfaction,
        )

