"""
Relationship Extractor — [Relationship Extractor] stage, final step before
graph write. Constrained to VALID_PREDICATES so output always matches
graph/schema.py's relationship types.
"""
import json
import os
from dataclasses import dataclass
from typing import List, Dict

from app.core.llm_provider import get_provider  # adjust to your core/ module's actual path

VALID_PREDICATES = [
    "manages", "benchmarks_against", "holds", "rated_by", "classified_under",
    "issued_by", "governed_by", "managed_by", "tracks", "amends",
    "flagged_in", "monitored_for",
]

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "relationship_extraction.txt")
with open(_PROMPT_PATH, "r") as f:
    _PROMPT_TEMPLATE = f.read()


@dataclass
class Triple:
    subject: str
    predicate: str
    object: str
    confidence: float
    source_chunk_id: str
    properties: Dict = None


def extract_relationships(chunk_text: str, chunk_id: str, entities: List[dict]) -> List[Triple]:
    """entities: list of {"text": str, "label": str} from extraction/entities.py, post-resolver."""
    if not entities:
        return []

    prompt = _PROMPT_TEMPLATE.format(
        entities_json=json.dumps([{"text": e["text"], "label": e["label"]} for e in entities], indent=2),
        valid_predicates=", ".join(VALID_PREDICATES),
        chunk_id=chunk_id,
        chunk_text=chunk_text,
    )

    provider = get_provider()
    raw_triples = provider.generate_json(prompt)
    if not isinstance(raw_triples, list):
        return []

    triples = []
    for t in raw_triples:
        if t.get("predicate") not in VALID_PREDICATES:
            continue  # guards against the LLM inventing predicates outside the schema
        triples.append(
            Triple(
                subject=t["subject"], predicate=t["predicate"], object=t["object"],
                confidence=float(t.get("confidence", 0.5)), source_chunk_id=chunk_id,
                properties=t.get("properties") or {},
            )
        )
    return triples