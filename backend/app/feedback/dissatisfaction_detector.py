# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
dissatisfaction_detector.py
===========================
Detects implicit user dissatisfaction and correction attempts in follow-up queries.
Implements Step FD:
  1. Frustration Detection (VADER sentiment analysis)
  2. Same Referent Check (SentenceTransformer embedding similarity)
  3. Correction Language Patterns (Regex matching)
  4. Structured Claim Extraction
"""

from typing import Optional, Tuple
import re
import logging

from app.feedback.correction_extractor import CorrectionExtractor, StructuredClaim

logger = logging.getLogger("app.feedback.dissatisfaction")

# Lazy loading of models to optimize startup
_embedder = None
_vader = None


def get_embedder(model_name: str = "all-MiniLM-L6-v2"):
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(model_name)
            logger.info("Loaded SentenceTransformer model: %s", model_name)
        except Exception as exc:
            logger.warning("SentenceTransformer unavailable: %s", exc)
            _embedder = False
    return _embedder if _embedder is not False else None


def get_vader():
    global _vader
    if _vader is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _vader = SentimentIntensityAnalyzer()
        except ImportError:
            _vader = False
    return _vader if _vader is not False else None


class DissatisfactionDetector:
    """
    Detects when a follow-up query is actually a correction attempt.
    """

    DEFAULT_SENTIMENT_THRESHOLD = -0.35
    DEFAULT_SIMILARITY_THRESHOLD = 0.75
    DEFAULT_INTENT_CONFIDENCE_THRESHOLD = 0.65

    CORRECTION_PATTERNS = [
        r"\b(wrong|incorrect|not right|mistake|error|inaccurate)\b",
        r"\b(actually|should be|correct answer is|real value is|true value)\b",
        r"\b(that'?s? not|no\b|not true|disagree|not\s+[\d.]+%?)\b",
        r"\b(check|verify|look again|re-check|double-check)\b",
        r"\b(my records show|according to|source says|document says)\b",
        r"\b(outdated|old data|stale|not current)\b"
    ]

    def __init__(
        self,
        sentiment_threshold: float = DEFAULT_SENTIMENT_THRESHOLD,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        intent_confidence_threshold: float = DEFAULT_INTENT_CONFIDENCE_THRESHOLD,
        embedder_model: str = "all-MiniLM-L6-v2"
    ):
        self.sentiment_threshold = sentiment_threshold
        self.similarity_threshold = similarity_threshold
        self.intent_confidence_threshold = intent_confidence_threshold
        self.embedder_model = embedder_model
        self.extractor = CorrectionExtractor()

    def _detect_frustration(self, text: str) -> Tuple[bool, float]:
        """
        Returns (is_frustrated, compound_score).
        Score range: -1.0 to 1.0.
        """
        vader = get_vader()
        if vader:
            scores = vader.polarity_scores(text)
            compound = scores["compound"]
            is_frustrated = compound <= self.sentiment_threshold
            return is_frustrated, compound

        # Fallback keyword scoring if VADER is unavailable
        negative_keywords = ["wrong", "incorrect", "not", "no", "error", "mistake", "bad", "terrible", "disagree", "awful", "poor", "inaccurate"]
        positive_keywords = ["great", "excellent", "good", "thanks", "thank", "helpful", "correct", "perfect", "appreciate", "nice", "awesome"]
        text_lower = text.lower()
        neg_count = sum(1 for kw in negative_keywords if kw in text_lower)
        pos_count = sum(1 for kw in positive_keywords if kw in text_lower)
        if pos_count > neg_count:
            fallback_score = min(0.25 * pos_count, 1.0)
        elif neg_count > 0:
            fallback_score = max(-0.25 * neg_count, -1.0)
        else:
            fallback_score = 0.0
        is_frustrated = fallback_score <= self.sentiment_threshold
        return is_frustrated, fallback_score

    def _check_same_referent(
        self,
        follow_up_query: str,
        original_query: str,
        original_response: str = ""
    ) -> Tuple[bool, float]:
        """
        Check if follow-up refers to same topic/referent using domain attribute matching,
        shared numerical values, and embedding cosine similarity.
        """
        if not follow_up_query:
            return False, 0.0

        # 1. Attribute matching: if both refer to same metric (e.g. TER, NAV), they share referent
        attr_follow = self.extractor._detect_attribute(follow_up_query)
        attr_orig = self.extractor._detect_attribute(original_query) or (
            self.extractor._detect_attribute(original_response) if original_response else None
        )
        if attr_follow and attr_orig and attr_follow == attr_orig:
            return True, 0.90

        # 2. Number overlap: if follow-up mentions a number from the original response (the rejected value)
        nums_follow = set(self.extractor._extract_numbers(follow_up_query))
        nums_orig = set(self.extractor._extract_numbers(original_response or "")) | set(
            self.extractor._extract_numbers(original_query or "")
        )
        if nums_follow and nums_orig and (nums_follow & nums_orig):
            return True, 0.85

        # 3. Embedding cosine similarity
        sim = 0.0
        embedder = get_embedder(self.embedder_model)
        if embedder and original_query:
            try:
                from sklearn.metrics.pairwise import cosine_similarity
                follow_emb = embedder.encode(follow_up_query)
                orig_emb = embedder.encode(original_query)
                sim = float(cosine_similarity([follow_emb], [orig_emb])[0][0])
                if sim >= self.similarity_threshold:
                    return True, sim
            except Exception as exc:
                logger.debug("Embedding similarity failed: %s", exc)

        # 4. Word overlap fallback
        words_follow = set(re.findall(r"\w+", follow_up_query.lower()))
        words_orig = set(re.findall(r"\w+", (original_query + " " + (original_response or "")).lower()))
        common_stops = {"the", "is", "a", "of", "and", "in", "to", "what", "that", "this", "it", "not"}
        meaningful_overlap = (words_follow & words_orig) - common_stops
        if meaningful_overlap:
            overlap_score = min(len(meaningful_overlap) * 0.25, 0.9)
            if overlap_score >= self.similarity_threshold:
                return True, overlap_score

        return False, sim

    def _has_correction_language(self, text: str) -> Tuple[bool, float]:
        """
        Checks if text matches correction language patterns.
        """
        text_lower = (text or "").lower()
        matches = 0
        for pattern in self.CORRECTION_PATTERNS:
            if re.search(pattern, text_lower):
                matches += 1

        confidence = min(matches * 0.35, 1.0)
        has_intent = confidence >= self.intent_confidence_threshold
        return has_intent, round(confidence, 2)

    def is_correction_attempt(
        self,
        follow_up_query: str,
        original_response: str = "",
        original_query: str = ""
    ) -> Tuple[bool, Optional[StructuredClaim]]:
        """
        Main entry point for Step FD.
        Evaluates 3 signals: Frustration, Same Referent, Correction Language.
        """
        if not follow_up_query or not follow_up_query.strip():
            return False, None

        is_frustrated, sentiment_score = self._detect_frustration(follow_up_query)
        same_topic, similarity_score = self._check_same_referent(follow_up_query, original_query, original_response)
        has_correction_lang, intent_confidence = self._has_correction_language(follow_up_query)

        # Decision: all 3 signals must indicate correction
        is_correction = is_frustrated and same_topic and has_correction_lang

        if not is_correction:
            return False, None

        claim = self.extractor.extract_claim(
            feedback_text=follow_up_query,
            original_response=original_response,
            original_query=original_query
        )

        if claim:
            # Blend signal confidence
            detection_confidence = (abs(sentiment_score) + similarity_score + intent_confidence) / 3.0
            claim.confidence = round(min(claim.confidence, max(detection_confidence, 0.5)), 2)

        return True, claim
