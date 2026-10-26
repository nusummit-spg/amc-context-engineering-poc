# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""NER + Entity Extractor (LLM-based AMC-domain NER)."""
import asyncio
import logging

from pydantic import BaseModel, Field

from app.core.llm import LLMClient
from app.prompts import get_prompt
from app.models.documents import Document

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
        """Initialize a new instance of EntityExtractor.

        Args:
            llm (LLMClient): The llm.
        """
        self._llm = llm

    async def extract(self, document: Document) -> list[ExtractedMention]:
        """Extract operation.

        Args:
            document (Document): The document.

        Returns:
            list[ExtractedMention]: List of resulting items or records.
        """
        prompt = get_prompt("entity_extraction")
        mentions: list[ExtractedMention] = []
        seen: set[tuple[str, str]] = set()

        # Group sections into text windows (800 - 4000 chars) to avoid hundreds of separate LLM calls
        windows: list[str] = []
        current_buf: list[str] = []
        current_len = 0
        for section in document.sections:
            t = section.text.strip()
            if not t or len(t) < 30:
                continue
            if current_len + len(t) > 4000 and current_buf:
                windows.append("\n\n".join(current_buf))
                current_buf = [t]
                current_len = len(t)
            else:
                current_buf.append(t)
                current_len += len(t)
        if current_buf:
            windows.append("\n\n".join(current_buf))

        for window_text in windows:
            rendered = prompt.render(content=window_text[:6000])
            try:
                result = await self._llm.complete_structured(
                    rendered, _EXTRACTION_SCHEMA, system=prompt.system, fast=True,
                )
            except Exception as exc:
                logger.warning("Entity extraction failed on section of %s: %s",
                               document.filename, exc)
                continue

            entities_list = (
                result.get("entities", [])
                if isinstance(result, dict)
                else (result if isinstance(result, list) else [])
            )
            for raw in entities_list:
                if isinstance(raw, str):
                    raw_name = raw.strip()
                    if not raw_name:
                        continue
                    key = ("Entity", raw_name.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    mentions.append(ExtractedMention(
                        type="Entity",
                        surface_form=raw_name,
                        normalized_name=raw_name,
                        properties={},
                        context=window_text[:300],
                        confidence=0.85,
                    ))
                    continue

                if not isinstance(raw, dict):
                    continue

                raw_type = str(raw.get("type") or "Entity")
                raw_surface = str(raw.get("surface_form") or raw.get("name") or "")
                raw_norm = str(raw.get("normalized_name") or raw_surface or "")
                if not raw_norm:
                    continue

                key = (raw_type, raw_norm.lower())
                if key in seen:
                    continue
                seen.add(key)

                try:
                    conf = float(raw.get("confidence", 0.85))
                except (ValueError, TypeError):
                    conf = 0.85
                conf = max(0.0, min(1.0, conf))

                props = raw.get("properties", {})
                if not isinstance(props, dict):
                    props = {}

                mentions.append(ExtractedMention(
                    type=raw_type,
                    surface_form=raw_surface or raw_norm,
                    normalized_name=raw_norm,
                    properties=props,
                    context=window_text[:300],
                    confidence=conf,
                ))

            # Small pause to avoid Groq rate limit spikes during batch ingest
            await asyncio.sleep(0.2)

        return mentions
