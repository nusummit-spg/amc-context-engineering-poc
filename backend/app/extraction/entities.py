"""
NER + Entity Extractor — [NER + Entity Extractor] stage. Two-tier:
Layer A: deterministic regex/spaCy rules (ISIN, AUM/NAV figures, dates) — free, instant.
Layer B: GLiNER zero-shot for named entities that don't follow a fixed pattern
(scheme names, issuers, fund managers, benchmarks).
"""
import re
from dataclasses import dataclass
from typing import List
import spacy
from spacy.pipeline import EntityRuler
from gliner import GLiNER

ISIN_PATTERN = r"\bIN[EF][A-Z0-9]{9}\b"
AUM_PATTERN = r"\b(?:₹|Rs\.?)?\s?[\d,]+(?:\.\d+)?\s?(?:Cr|Crore|Lakh|Lac|bn|mn)\b"
DATE_PATTERN = r"\b\d{1,2}[-/](?:\d{1,2}|[A-Za-z]{3,9})[-/]\d{2,4}\b"

MF_LABELS = [
    "mutual fund scheme", "fund house", "benchmark index", "ISIN",
    "credit rating", "asset class", "fund manager", "issuer",
    "issuer group", "regulatory circular",
]

_gliner_model: GLiNER | None = None


@dataclass
class ExtractedEntity:
    text: str
    label: str
    start: int
    end: int
    score: float
    source: str  # "layer_a_rules" | "layer_b_gliner"


def _get_gliner() -> GLiNER:
    global _gliner_model
    if _gliner_model is None:
        _gliner_model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
    return _gliner_model


def _build_rule_pipeline(gazetteer_terms: List[str] | None = None):
    nlp = spacy.blank("en")
    ruler: EntityRuler = nlp.add_pipe("entity_ruler")
    patterns = [{"label": "ISIN", "pattern": [{"TEXT": {"REGEX": ISIN_PATTERN}}]}]
    if gazetteer_terms:
        patterns += [{"label": "FUND_HOUSE_OR_SCHEME", "pattern": t} for t in gazetteer_terms]
    ruler.add_patterns(patterns)
    return nlp


def extract_layer_a(text: str, gazetteer_terms: List[str] | None = None) -> List[ExtractedEntity]:
    nlp = _build_rule_pipeline(gazetteer_terms)
    doc = nlp(text)
    entities = [
        ExtractedEntity(text=e.text, label=e.label_, start=e.start_char, end=e.end_char,
                         score=1.0, source="layer_a_rules")
        for e in doc.ents
    ]
    for match in re.finditer(AUM_PATTERN, text):
        entities.append(ExtractedEntity(text=match.group(), label="AUM_OR_NAV",
                                         start=match.start(), end=match.end(), score=1.0, source="layer_a_rules"))
    for match in re.finditer(DATE_PATTERN, text):
        entities.append(ExtractedEntity(text=match.group(), label="DATE",
                                         start=match.start(), end=match.end(), score=1.0, source="layer_a_rules"))
    return entities


def extract_layer_b(text: str, threshold: float = 0.5) -> List[ExtractedEntity]:
    model = _get_gliner()
    raw = model.predict_entities(text, MF_LABELS, threshold=threshold)
    return [
        ExtractedEntity(text=r["text"], label=r["label"], start=r["start"], end=r["end"],
                         score=r["score"], source="layer_b_gliner")
        for r in raw
    ]


def extract_entities(text: str, gazetteer_terms: List[str] | None = None) -> List[ExtractedEntity]:
    """Merged, deduped Layer A + Layer B output — the input to resolver.py."""
    layer_a = extract_layer_a(text, gazetteer_terms)
    layer_b = extract_layer_b(text)

    merged = {}
    for e in layer_a:
        merged[e.text.lower()] = e
    for e in layer_b:
        merged.setdefault(e.text.lower(), e)  # Layer A wins on collision (deterministic > probabilistic)
    return list(merged.values())