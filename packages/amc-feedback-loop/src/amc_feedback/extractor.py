"""
Correction claim extractor that isolates the target entity, modified attribute, asserted value, and rejected value.
"""
import re
from typing import Optional
from .config import FeedbackConfig
from .ner import NERPipeline
from .matcher import EntityMatcher
from .schemas import CorrectionClaim

_VAL_RE = re.compile(r"(\d+\.?\d*%?)")

class CorrectionExtractor:
    def __init__(self, config: FeedbackConfig, ner: NERPipeline, matcher: EntityMatcher):
        self.config = config
        self.ner = ner
        self.matcher = matcher

    def extract_claim(
        self,
        feedback_text: str,
        original_response: str = ""
    ) -> Optional[CorrectionClaim]:
        # 1. Resolve Entity
        resolved = self.matcher.match(feedback_text)
        if not resolved and original_response:
            resolved = self.matcher.match(original_response)

        entity_id = resolved.canonical_id if resolved else None
        entity_name = resolved.canonical_name if resolved else None

        # 2. Detect Attribute
        attribute = "TER"
        text_lower = feedback_text.lower()
        for attr, keywords in self.config.attribute_keywords.items():
            if any(kw in text_lower for kw in keywords):
                attribute = attr
                break

        # 3. Extract asserted value (e.g., "0.82%" or "0.82")
        # Pattern like "0.82, not 0.79" or "actually 0.82"
        asserted_value = None
        rejected_value = None

        m_not = re.search(r"(\d+\.?\d*%?)\s*(?:,\s*|\s+)not\s+(\d+\.?\d*%?)", text_lower)
        if m_not:
            asserted_value = m_not.group(1).replace("%", "")
            rejected_value = m_not.group(2).replace("%", "")
        else:
            numbers = _VAL_RE.findall(feedback_text)
            if numbers:
                asserted_value = numbers[0].replace("%", "")
                if len(numbers) > 1:
                    rejected_value = numbers[1].replace("%", "")

        if not asserted_value:
            return None

        # Try to extract rejected value from original response if still None
        if not rejected_value and original_response:
            orig_numbers = _VAL_RE.findall(original_response)
            if orig_numbers:
                rejected_value = orig_numbers[0].replace("%", "")

        return CorrectionClaim(
            resolved_entity_id=entity_id,
            resolved_entity_name=entity_name,
            attribute=attribute,
            asserted_value=asserted_value,
            rejected_value=rejected_value,
            confidence=0.85 if entity_id else 0.65
        )
