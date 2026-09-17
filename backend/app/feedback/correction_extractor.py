# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
correction_extractor.py
=======================
Extracts structured claims (entity, attribute, asserted value, rejected value)
from user correction feedback using domain vocabulary, regex heuristics, and spaCy NER.
"""

from dataclasses import dataclass
import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger("app.feedback.correction_extractor")

# spaCy lazy loading
_nlp = None


def get_nlp(model_name: str = "en_core_web_sm"):
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load(model_name)
            logger.info("Loaded spaCy model: %s", model_name)
        except Exception as exc:
            logger.warning("spaCy model '%s' unavailable: %s", model_name, exc)
            _nlp = False
    return _nlp if _nlp is not False else None


@dataclass
class StructuredClaim:
    """
    Structured correction claim extracted from feedback text.
    """
    entity_id: Optional[str]
    entity_name: Optional[str]
    attribute: Optional[str]
    asserted_value: Optional[str]
    rejected_value: Optional[str]
    raw_text: str
    confidence: float


class CorrectionExtractor:
    """
    Extracts structured claims from correction feedback text.
    """

    ATTRIBUTE_KEYWORDS = {
        "TER": ["ter", "expense ratio", "total expense", "cost ratio", "expense"],
        "NAV": ["nav", "net asset value", "unit price"],
        "RETURN": ["return", "cagr", "performance", "growth", "returns", "1yr_return", "3yr_return", "5yr_return"],
        "AUM": ["aum", "assets under management", "corpus", "fund size"],
        "EXIT_LOAD": ["exit load", "redemption charge", "exit fee"],
        "MINIMUM_INVESTMENT": ["minimum investment", "min investment", "minimum amount"],
        "SHARPE_RATIO": ["sharpe", "sharpe ratio"],
        "ALPHA": ["alpha"],
        "BETA": ["beta"],
        "RISK_GRADE": ["risk", "risk grade", "risk category"],
        "BENCHMARK": ["benchmark", "index"]
    }

    def __init__(self, spacy_model: str = "en_core_web_sm"):
        self.spacy_model = spacy_model

    def _extract_numbers(self, text: str) -> List[float]:
        """
        Extract numeric values from text (handles currency ₹, Rs, decimals, %).
        """
        pattern = r"(?:₹|Rs\.?\s*)?(\d+(?:\.\d+)?)\s*%?"
        matches = re.findall(pattern, text or "")
        return [float(m) for m in matches if m]

    def _detect_attribute(self, text: str) -> Optional[str]:
        """
        Detect mutual fund attribute from vocabulary keywords.
        """
        text_lower = (text or "").lower()
        for attr_name, keywords in self.ATTRIBUTE_KEYWORDS.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                    return attr_name
        return None

    def _extract_entity(self, text: str) -> Optional[str]:
        """
        Extract fund or organization entity using spaCy NER with fallback patterns.
        """
        if not text:
            return None

        nlp = get_nlp(self.spacy_model)
        if nlp:
            try:
                doc = nlp(text)
                for ent in doc.ents:
                    if ent.label_ == "ORG" and "fund" in ent.text.lower():
                        return ent.text.strip()
                for ent in doc.ents:
                    if ent.label_ == "ORG":
                        return ent.text.strip()
            except Exception as exc:
                logger.debug("spaCy extraction error: %s", exc)

        # Fallback regex pattern for capitalized Fund / Asset names
        pattern = r'\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){1,5}(?:\s+Fund|\s+Scheme)?)\b'
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
        return None

    def extract_claim(
        self,
        feedback_text: str,
        original_response: str = "",
        original_query: str = ""
    ) -> Optional[StructuredClaim]:
        """
        Extract structured claim from feedback text and interaction context.
        """
        feedback_numbers = self._extract_numbers(feedback_text)
        response_numbers = self._extract_numbers(original_response)

        attribute = self._detect_attribute(feedback_text) or self._detect_attribute(original_query)
        if not attribute and not feedback_numbers:
            return None

        # Determine asserted and rejected values
        # Heuristic 1: "should be X not Y" or "X not Y"
        asserted_value = None
        rejected_value = None

        if len(feedback_numbers) >= 2:
            asserted_value = str(feedback_numbers[0])
            rejected_value = str(feedback_numbers[1])
        elif len(feedback_numbers) == 1:
            asserted_value = str(feedback_numbers[0])
            if response_numbers:
                rejected_value = str(response_numbers[0])
        elif response_numbers:
            # If user said "TER is wrong" without asserting a number
            rejected_value = str(response_numbers[0])

        # Entity extraction from original query or feedback
        entity_name = self._extract_entity(original_query) or self._extract_entity(feedback_text)

        # Confidence calculation
        confidence = 0.5
        if attribute:
            confidence += 0.2
        if asserted_value is not None:
            confidence += 0.15
        if rejected_value is not None:
            confidence += 0.1
        if entity_name:
            confidence += 0.05

        return StructuredClaim(
            entity_id=None,
            entity_name=entity_name,
            attribute=attribute,
            asserted_value=asserted_value,
            rejected_value=rejected_value,
            raw_text=feedback_text,
            confidence=min(round(confidence, 2), 1.0)
        )
