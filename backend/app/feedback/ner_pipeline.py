# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
ner_pipeline.py
===============
Extracts structured claims from free-text user feedback with entity extraction,
domain attribute detection, and number role assignment.
Integrates with FundNameMatcher to resolve extracted names to canonical ISINs.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.feedback.fund_name_matcher import FundNameMatcher, get_fund_name_matcher

logger = logging.getLogger("app.feedback.ner_pipeline")

_nlp = None


def get_nlp(model_name: str = "en_core_web_sm"):
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load(model_name)
        except Exception as exc:
            logger.debug("spaCy model notice in ner pipeline: %s", exc)
            _nlp = False
    return _nlp if _nlp is not False else None


@dataclass
class RawClaim:
    """
    Raw correction claim extracted from feedback before or during entity resolution.
    """
    entity_candidates: List[str]
    attribute: Optional[str]
    asserted_value: Optional[str]
    rejected_value: Optional[str]
    raw_text: str
    confidence: float
    resolved_entity_id: Optional[str] = None
    resolved_entity_name: Optional[str] = None


class FeedbackNERPipeline:
    """
    Pipeline for parsing user feedback text into structured correction claims.
    """

    ATTRIBUTE_KEYWORDS = {
        "TER": ["ter", "expense ratio", "total expense", "cost ratio", "expense"],
        "NAV": ["nav", "net asset value", "unit price"],
        "RETURN": ["return", "cagr", "performance", "growth", "returns", "1yr_return", "3yr_return", "5yr_return"],
        "AUM": ["aum", "assets under management", "corpus", "fund size"],
        "EXIT_LOAD": ["exit load", "redemption charge", "exit fee"],
        "MIN_INVESTMENT": ["minimum investment", "min investment", "minimum amount"],
        "SHARPE_RATIO": ["sharpe", "sharpe ratio"],
        "ALPHA": ["alpha"],
        "BETA": ["beta"],
        "RISK_GRADE": ["risk", "risk grade", "risk category"],
        "BENCHMARK": ["benchmark", "index"]
    }

    # Common AMC name anchors for heuristic pattern extraction
    AMC_KEYWORDS = [
        "axis", "hdfc", "icici", "sbi", "mirae", "kotak", "aditya birla",
        "absl", "dsp", "nippon", "uti", "tata", "parag parikh", "quant"
    ]

    def __init__(self, matcher: Optional[FundNameMatcher] = None):
        self.matcher = matcher or get_fund_name_matcher()

    def extract_structured_claim(
        self,
        feedback_text: str,
        original_query: Optional[str] = None,
        original_response: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Optional[RawClaim]:
        if not feedback_text or not feedback_text.strip():
            return None

        # 1. Extract entities
        entities = self._extract_entities(feedback_text)
        if not entities and original_query:
            entities = self._extract_entities(original_query)

        # 2. Detect attribute
        attribute = self._detect_attribute(feedback_text)
        if not attribute and original_query:
            attribute = self._detect_attribute(original_query)

        # 3. Extract numbers
        numbers = self._extract_numbers(feedback_text)
        response_numbers = self._extract_numbers(original_response or "")

        if not attribute and not numbers:
            return None

        # 4. Assign number roles
        asserted_val, rejected_val = self._assign_number_roles(feedback_text, numbers, response_numbers)

        # 5. Calculate base confidence
        confidence = 0.5
        if entities:
            confidence += 0.2
        if attribute:
            confidence += 0.2
        if asserted_val:
            confidence += 0.1
        confidence = min(confidence, 1.0)

        # Sort entity candidates by length descending (longest/most specific first)
        entities = sorted(entities, key=len, reverse=True)

        # 6. Entity resolution via FundNameMatcher
        resolved_id = None
        resolved_name = None
        for cand in entities:
            res = self.matcher.resolve(cand, user_context=user_context)
            if res and not res.get("ambiguous") and res.get("isin"):
                resolved_id = res["isin"]
                resolved_name = res["fund_name"]
                confidence = min(confidence, res.get("confidence", 0.9))
                break

        return RawClaim(
            entity_candidates=entities,
            attribute=attribute,
            asserted_value=asserted_val,
            rejected_value=rejected_val,
            raw_text=feedback_text,
            confidence=round(confidence, 2),
            resolved_entity_id=resolved_id,
            resolved_entity_name=resolved_name
        )

    def _extract_entities(self, text: str) -> List[str]:
        entities: List[str] = []
        if not text:
            return entities

        # Strategy 1: spaCy NER (if available)
        nlp = get_nlp()
        if nlp:
            try:
                doc = nlp(text)
                for ent in doc.ents:
                    if ent.label_ in ("ORG", "PRODUCT") and any(w in ent.text.lower() for w in ["fund", "growth", "bluechip", "asset", "equity"]):
                        entities.append(ent.text)
            except Exception as exc:
                logger.debug("spaCy NER exception: %s", exc)

        # Strategy 2: Pattern matching on AMC keywords
        text_clean = text.strip()
        for kw in self.AMC_KEYWORDS:
            pattern = re.compile(
                r"\b(" + re.escape(kw) + r"\b[\w\s\-]+?(?:fund|growth|direct|regular|plan|equity|cap)?)",
                re.I
            )
            match = pattern.search(text_clean)
            if match:
                candidate = match.group(1).strip()
                if len(candidate) >= 4 and candidate not in entities:
                    entities.append(candidate)

        # Strategy 3: Generic capitalized scheme pattern
        cap_pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5}(?:\s+Fund)?)\b")
        for m in cap_pattern.finditer(text):
            cand = m.group(1).strip()
            if cand not in entities:
                entities.append(cand)

        # Deduplicate and trim generic endings
        cleaned: List[str] = []
        for e in entities:
            e_clean = re.sub(r"\s+(?:is|has|was|should|wrong|ter|nav)$", "", e, flags=re.I).strip()
            if e_clean and e_clean not in cleaned:
                cleaned.append(e_clean)

        return cleaned

    def _detect_attribute(self, text: str) -> Optional[str]:
        text_lower = (text or "").lower()
        for attr_key, keywords in self.ATTRIBUTE_KEYWORDS.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                    return attr_key
        return None

    def _extract_numbers(self, text: str) -> List[float]:
        pattern = r"(?:₹|Rs\.?\s*)?(\d+(?:\.\d+)?)\s*%?"
        matches = re.findall(pattern, text or "")
        return [float(m) for m in matches if m]

    def _assign_number_roles(
        self,
        text: str,
        numbers: List[float],
        response_numbers: Optional[List[float]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        if not numbers:
            return None, None

        # Two numbers in feedback: e.g. "TER is 0.82% not 0.79%"
        if len(numbers) >= 2:
            return str(numbers[0]), str(numbers[1])

        # One number in feedback: asserted value
        asserted = str(numbers[0])
        rejected = None
        if response_numbers:
            rejected = str(response_numbers[0])

        return asserted, rejected


_global_ner_pipeline = None


def get_ner_pipeline() -> FeedbackNERPipeline:
    global _global_ner_pipeline
    if _global_ner_pipeline is None:
        _global_ner_pipeline = FeedbackNERPipeline()
    return _global_ner_pipeline
