"""
Step 1  ClassificationService
NER + Sentiment (VADER) + Intent detection.

Active path only  skipped entirely when:
  - row.source == 'passive'  (no notes text)
  - row.corrections is already structured (nothing to extract)

The service is intentionally stateless: construct once, call many times.
spaCy model is loaded lazily on first use and cached on the instance.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import structlog

from feedback_loop.logging_config import get_pipeline_logger
from feedback_loop.logging import get_feedback_logger, log_step_info, log_step_warning
from feedback_loop.domain_models import ClassificationResult, FeedbackRecord

logger = structlog.get_logger(__name__)
step_logger_cls = get_feedback_logger("classification")

# Intent keyword sets  lightweight, no model call required
_CORRECTION_KEYWORDS = frozenset([
    "wrong", "incorrect", "not right", "actually", "should be",
    "should have", "mistaken", "error", "please check", "factsheet",
])
_COMPLAINT_KEYWORDS = frozenset([
    "terrible", "useless", "awful", "bad", "horrible", "unacceptable",
    "disappointed", "frustrating", "pathetic",
])


def _classify_intent(text: str) -> str:
    """Rule-based intent classifier. Returns 'correction', 'complaint',
    'query', or 'neutral'. No token cost.

    Args:
        text (str): Input text content.

    Returns:
        str: Resulting str instance.
    """
    lower = text.lower()
    if any(kw in lower for kw in _CORRECTION_KEYWORDS):
        return "correction"
    if any(kw in lower for kw in _COMPLAINT_KEYWORDS):
        return "complaint"
    if "?" in text:
        return "query"
    return "neutral"


class ClassificationService:
    """
    Encapsulates NER (spaCy), sentiment (VADER), and intent detection.

    spaCy and VADER are optional at import time  the service degrades
    gracefully when they are not installed (returns empty results with a
    warning), so the package can be installed in environments where the
    heavy NLP libraries are not yet available.
    """

    def __init__(self, spacy_model: str = "en_core_web_sm") -> None:
        """Initialize a new instance of ClassificationService.

        Args:
            spacy_model (str): The spacy model.
        """
        self._spacy_model_name = spacy_model
        self._nlp = None          # lazy-loaded
        self._vader = None        # lazy-loaded

    #  Lazy loaders 

    def _get_nlp(self):
        """Retrieve nlp.

        Returns:
            Result of the operation.
        """
        if self._nlp is None:
            try:
                import spacy  # noqa: PLC0415
                self._nlp = spacy.load(self._spacy_model_name)
            except Exception as exc:
                logger.warning(
                    "spacy_load_failed",
                    model=self._spacy_model_name,
                    error=str(exc),
                )
                self._nlp = False   # sentinel: don't retry
        return self._nlp or None

    def _get_vader(self):
        """Retrieve vader.

        Returns:
            Result of the operation.
        """
        if self._vader is None:
            try:
                from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # noqa: PLC0415
                self._vader = SentimentIntensityAnalyzer()
            except Exception as exc:
                logger.warning("vader_load_failed", error=str(exc))
                self._vader = False
        return self._vader or None

    #  Public API 

    def should_run(self, row: FeedbackRecord) -> bool:
        """Returns True when Step 1 should execute.
        Skipped when source is passive or corrections are already structured.

        Args:
            row (FeedbackRecord): The row.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if row.source == "passive":
            return False
        if row.corrections:
            # structured correction provided  nothing to extract
            return False
        if not row.notes:
            return False
        return True

    def run(self, row: FeedbackRecord, session_id: str = None, feedback_id: str = None) -> ClassificationResult:
        """Run operation.

        Args:
            row (FeedbackRecord): The row.
            session_id (str): Unique identifier of the session.
            feedback_id (str): Unique identifier of the feedback.

        Returns:
            ClassificationResult: Resulting ClassificationResult instance.
        """
        """
        """
        
        # Initialize logger for this feedback item
        log_step_info(
            step_logger_cls,
            "CLASSIFICATION_START",
            "Classification starting for feedback_id=%s (text_length=%d)",
            row.feedback_id,
            len(row.notes or ""),
        )
        if session_id and feedback_id:
            step_logger = get_pipeline_logger("classification", session_id, feedback_id)
            if step_logger:
                step_logger.info("Classification starting", text_length=len(row.notes or ""))
        else:
            step_logger = None
        notes = row.notes or ""
        result = ClassificationResult()

        #  Sentiment (VADER) 
        vader = self._get_vader()
        if vader:
            scores = vader.polarity_scores(notes)
            result.sentiment_compound = round(scores["compound"], 4)

        #  Intent 
        result.intent = _classify_intent(notes)

        #  NER (spaCy) 
        nlp = self._get_nlp()
        if nlp:
            doc = nlp(notes)

            # Prefer entity_name from the feedback row; fall back to NER
            if row.entity_name:
                result.entity_extracted = row.entity_name
                result.entity_type = row.entity_type
            else:
                # Take first ORG / PRODUCT / PERSON entity found
                for ent in doc.ents:
                    if ent.label_ in ("ORG", "PRODUCT", "PERSON", "GPE"):
                        result.entity_extracted = ent.text
                        result.entity_type = ent.label_
                        break

            # Extract numeric values mentioned (e.g. "14.2%" or "38%")
            number_pattern = re.compile(r"\b(\d+(?:\.\d+)?)\s*%")
            matches = number_pattern.findall(notes)
            if matches:
                # Take the first explicit number as the user-asserted value
                result.value_mentioned = f"{matches[0]}%"
        else:
            # NER unavailable  fall back to row-level fields
            result.entity_extracted = row.entity_name
            result.entity_type = row.entity_type

        log_step_info(
            step_logger_cls,
            "CLASSIFICATION_COMPLETE",
            "Classification complete for %s: intent=%s, entity=%s, sentiment=%.4f",
            row.feedback_id,
            result.intent,
            result.entity_extracted,
            result.sentiment_compound,
        )

        if step_logger:
            step_logger.info(
                "classification_complete",
                feedback_id=row.feedback_id,
                intent=result.intent,
                entity=result.entity_extracted,
                sentiment=result.sentiment_compound,
            )
        return result

