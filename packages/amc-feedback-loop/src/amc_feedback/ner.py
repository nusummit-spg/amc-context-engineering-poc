"""
Configurable NER pipeline layer combining regex/gazetteer matching and open-domain models.
"""
import re
from typing import Any, Dict, List
from .config import FeedbackConfig
from .schemas import EntityMention

_ISIN_RE = re.compile(r"\bIN[EF][A-Z0-9]{9}\b")
_PERCENT_RE = re.compile(r"\b\d+\.?\d*%\b")
_NUMBER_RE = re.compile(r"\b\d+\.?\d*\b")

class NERPipeline:
    def __init__(self, config: FeedbackConfig):
        self.config = config
        self._nlp = None
        self._gliner = None

    def extract_entities(self, text: str) -> List[EntityMention]:
        mentions: List[EntityMention] = []

        # Rule-based ISIN
        for m in _ISIN_RE.finditer(text):
            mentions.append(EntityMention(
                text=m.group(),
                label="ISIN",
                start=m.start(),
                end=m.end(),
                score=1.0,
                layer="rule"
            ))

        # Configured attribute keywords
        text_lower = text.lower()
        for attr, keywords in self.config.attribute_keywords.items():
            for kw in keywords:
                start = 0
                while True:
                    idx = text_lower.find(kw.lower(), start)
                    if idx == -1:
                        break
                    mentions.append(EntityMention(
                        text=text[idx : idx + len(kw)],
                        label=f"ATTR_{attr}",
                        start=idx,
                        end=idx + len(kw),
                        score=0.95,
                        layer="keyword"
                    ))
                    start = idx + len(kw)

        # GLiNER zero-shot fallback if enabled and installed
        if self.config.use_gliner:
            try:
                from gliner import GLiNER
                if self._gliner is None:
                    self._gliner = GLiNER.from_pretrained(self.config.gliner_model_id, local_files_only=True)
                raw = self._gliner.predict_entities(
                    text,
                    ["mutual fund scheme name", "fund house", "financial metric"],
                    threshold=0.4
                )
                for r in raw:
                    mentions.append(EntityMention(
                        text=r["text"],
                        label=r["label"].upper().replace(" ", "_"),
                        start=r["start"],
                        end=r["end"],
                        score=float(r["score"]),
                        layer="gliner"
                    ))
            except Exception:
                pass

        return mentions
