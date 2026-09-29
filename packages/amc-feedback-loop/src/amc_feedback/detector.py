"""
Dissatisfaction and correction detector identifying explicit and implicit correction intents.
"""
import re
from typing import List, Tuple
from .config import FeedbackConfig

_CORRECTION_TRIGGERS = [
    r"\b(actually|not|instead of|incorrect|wrong|mistake|false|update|corrected)\b",
    r"\b(it is|it's|ter is|nav is|is actually)\s+(\d+\.?\d*%?)",
    r"\b(should be|supposed to be|rather than)\b",
]

_POSITIVE_TRIGGERS = [
    r"\b(thank|thanks|good|great|helpful|accurate|perfect|awesome)\b"
]

class DissatisfactionDetector:
    def __init__(self, config: FeedbackConfig):
        self.config = config

    def is_correction_attempt(
        self,
        feedback_text: str,
        original_query: str = "",
        original_response: str = ""
    ) -> Tuple[bool, float, List[str]]:
        text_lower = feedback_text.lower()
        signals: List[str] = []

        # Check positive sentiment suppression
        for p in _POSITIVE_TRIGGERS:
            if re.search(p, text_lower):
                # If there are no explicit correction markers, return False
                if not any(re.search(c, text_lower) for c in _CORRECTION_TRIGGERS):
                    return False, 0.1, ["positive_sentiment"]

        score = 0.0

        for pattern in _CORRECTION_TRIGGERS:
            match = re.search(pattern, text_lower)
            if match:
                score += 0.35
                signals.append(f"matched_trigger:{match.group(0)}")

        # Detect numbers / percentages in feedback
        if re.search(r"\d+\.?\d*%?", feedback_text):
            score += 0.3
            signals.append("contains_numerical_claim")

        confidence = min(1.0, score)
        is_correction = confidence >= self.config.dissatisfaction_threshold
        return is_correction, confidence, signals
