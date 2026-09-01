# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""NER + Entity Extractor (LLM-based AMC-domain NER)."""
import logging

from pydantic import BaseModel, Field

from app.core.llm import LLMClient
from app.prompts import get_prompt
from app.schemas.documents import Document

logger = logging.getLogger("extraction")

_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "Scheme", "Issuer", "IssuerGroup", "Analyst", "Sector",
                            "RiskTheme", "RegulatoryCircular", "ClauseType", "Document",
                            "TableFact", "FinancialMetric", "ESGMetric", "ComplianceRule",
                            "Penalty", "Clause", "Section",
                        ],
                    },
                    "surface_form": {"type": "string"},
                    "normalized_name": {"type": "string"},
                    "properties": {"type": "object", "additionalProperties": True},
                    "confidence": {"type": "number"},
                },
                "required": ["type", "surface_form", "normalized_name"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entities"],
    "additionalProperties": False,
}


class ExtractedMention(BaseModel):
    type: str
    surface_form: str
    normalized_name: str
    properties: dict = Field(default_factory=dict)
    context: str = ""
    confidence: float = Field(default=0.85, ge=0.0, le=1.0,
                              description="LLM extraction confidence. Rule-extracted=0.95, LLM=0.85 default.")


class EntityExtractor:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def extract(self, document: Document) -> list[ExtractedMention]:
        prompt = get_prompt("entity_extraction")
        mentions: list[ExtractedMention] = []
        seen: set[tuple[str, str]] = set()

        # Extract per-section to keep prompts small and context tight.
        for section in document.sections:
            if not section.text.strip():
                continue
            rendered = prompt.render(content=section.text[:6000])
            try:
                result = await self._llm.complete_structured(
                    rendered, _EXTRACTION_SCHEMA, system=prompt.system, fast=True,
                )
            except Exception as exc:
                logger.warning("Entity extraction failed on section of %s: %s",
                               document.filename, exc)
                continue
            for raw in result.get("entities", []):
                key = (raw["type"], raw["normalized_name"].lower())
                if key in seen:
                    continue
                seen.add(key)
                
                confidence = float(raw.get("confidence", 0.85))
                confidence = max(0.0, min(1.0, confidence))  # clamp to [0,1]
                
                mentions.append(ExtractedMention(
                    type=raw["type"],
                    surface_form=raw["surface_form"],
                    normalized_name=raw["normalized_name"],
                    properties=raw.get("properties", {}),
                    context=section.text[:300],
                    confidence=confidence,
                ))
        return mentions
