# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS5e — Relationship extraction: rule-based extractor first, LLM-assisted second.

Rule-based: cheap regex patterns for the highest-value structured facts
(holdings percentages, circular references, compliance statuses).
LLM-assisted: catches relationships the rules miss, constrained to the
ontology's typed edges and the entities already resolved in the document.
"""
import logging
import re

from app.core.llm import LLMClient
from app.prompts import get_prompt
from app.schemas.documents import Document
from app.schemas.entities import BaseEntity, EntityType
from app.schemas.relationships import Relationship, RelationshipType

logger = logging.getLogger("extraction")

# "Adani Ports & SEZ — 4.1%" / "Adani Green Energy - 1.7%" (holding lines in SIDs)
_HOLDING_LINE_RE = re.compile(r"([A-Z][\w&.\' ]{2,50}?)\s*[—\-–]\s*(\d{1,2}(?:\.\d+)?)\s*%")
# "Status: Compliant" style rows from trackers
_STATUS_RE = re.compile(r"Scheme:\s*([^;]+);.*?Status:\s*(Pending|Compliant|Not reviewed)", re.IGNORECASE)

_RELATIONSHIP_SCHEMA = {
    "type": "object",
    "properties": {
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "HOLDS", "ISSUED_BY", "IN_SECTOR", "MONITORED_FOR",
                            "FLAGGED_IN", "COVERS", "APPLIES_TO", "AFFECTS",
                        ],
                    },
                    "properties": {"type": "object", "additionalProperties": True},
                    "confidence": {"type": "number"},
                },
                "required": ["source", "target", "type", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["relationships"],
    "additionalProperties": False,
}

_STATUS_MAP = {"pending": "outdated", "compliant": "compliant", "not reviewed": "not_reviewed"}


class RelationshipExtractor:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def extract(
        self, document: Document, entities: list[BaseEntity],
        skip_llm: bool = False,
    ) -> list[tuple[Relationship, str, str]]:
        """Returns (relationship, source_name, target_name) triples."""
        by_name = {e.name.lower(): e for e in entities}
        for e in entities:
            for alias in e.aliases:
                by_name.setdefault(alias.lower(), e)

        results = self._rule_based(document, by_name)
        if not skip_llm:
            results += await self._llm_assisted(document, entities, by_name, existing=results)
        else:
            logger.info("Skipping LLM relationship extraction (ambiguity gate: not eligible).")
        return results

    # ---------- rule-based ----------

    def _rule_based(
        self, document: Document, by_name: dict[str, BaseEntity]
    ) -> list[tuple[Relationship, str, str]]:
        results: list[tuple[Relationship, str, str]] = []
        schemes = [e for e in by_name.values() if e.entity_type == EntityType.SCHEME]

        for section in document.sections:
            text = section.text

            # Holdings: issuer — pct% lines inside a scheme document.
            # Attribute to the scheme this document is about (single-scheme docs).
            doc_scheme = self._document_scheme(document, schemes)
            if doc_scheme:
                for match in _HOLDING_LINE_RE.finditer(text):
                    issuer_name = match.group(1).strip()
                    entity = by_name.get(issuer_name.lower())
                    if entity and entity.entity_type == EntityType.ISSUER:
                        results.append((
                            Relationship(
                                relationship_type=RelationshipType.HOLDS,
                                source_entity_id=doc_scheme.entity_id,
                                target_entity_id=entity.entity_id,
                                properties={"pct_nav": float(match.group(2))},
                                extraction_method="rule",
                                confidence=0.95,
                            ),
                            doc_scheme.name, entity.name,
                        ))

            # Compliance tracker rows: Scheme + Status -> ClauseType AFFECTS Scheme
            clause_types = [e for e in by_name.values() if e.entity_type == EntityType.CLAUSE_TYPE]
            if clause_types:
                clause = clause_types[0]
                for match in _STATUS_RE.finditer(text):
                    scheme_entity = None
                    scheme_raw = match.group(1).strip()
                    for scheme in schemes:
                        if scheme.name.lower() in scheme_raw.lower() or any(
                            a.lower() in scheme_raw.lower() for a in scheme.aliases
                        ):
                            scheme_entity = scheme
                            break
                    if scheme_entity:
                        status = _STATUS_MAP.get(match.group(2).lower(), "not_reviewed")
                        results.append((
                            Relationship(
                                relationship_type=RelationshipType.AFFECTS,
                                source_entity_id=clause.entity_id,
                                target_entity_id=scheme_entity.entity_id,
                                properties={"status": status},
                                extraction_method="rule",
                                confidence=0.95,
                            ),
                            clause.name, scheme_entity.name,
                        ))
        return results

    @staticmethod
    def _document_scheme(document: Document, schemes: list[BaseEntity]):
        """If the document is clearly about a single scheme (SID), return it."""
        fname = document.filename.lower()
        for scheme in schemes:
            tokens = [scheme.name.lower()] + [a.lower() for a in scheme.aliases]
            if any(t.replace(" ", "").replace("nusummit", "") in fname.replace("_", "")
                   for t in tokens if len(t) > 4):
                return scheme
        return schemes[0] if len(schemes) == 1 else None

    # ---------- LLM-assisted ----------

    async def _llm_assisted(
        self,
        document: Document,
        entities: list[BaseEntity],
        by_name: dict[str, BaseEntity],
        existing: list[tuple[Relationship, str, str]],
    ) -> list[tuple[Relationship, str, str]]:
        if not entities:
            return []
        prompt = get_prompt("relationship_extraction")
        entity_list = "\n".join(f"- {e.entity_type.value}: {e.name}" for e in entities)
        rendered = prompt.render(
            entities=entity_list,
            content=document.full_text[:8000],
        )
        try:
            result = await self._llm.complete_structured(
                rendered, _RELATIONSHIP_SCHEMA, system=prompt.system,
            )
        except Exception as exc:
            logger.warning("LLM relationship extraction failed for %s: %s",
                           document.filename, exc)
            return []

        existing_keys = {
            (r.relationship_type.value, s.lower(), t.lower()) for r, s, t in existing
        }
        results: list[tuple[Relationship, str, str]] = []
        for raw in result.get("relationships", []):
            source = by_name.get(raw["source"].lower())
            target = by_name.get(raw["target"].lower())
            if not source or not target:
                continue
            key = (raw["type"], source.name.lower(), target.name.lower())
            if key in existing_keys:
                continue
            existing_keys.add(key)
            results.append((
                Relationship(
                    relationship_type=RelationshipType(raw["type"]),
                    source_entity_id=source.entity_id,
                    target_entity_id=target.entity_id,
                    properties=raw.get("properties", {}),
                    extraction_method="llm",
                    confidence=min(float(raw.get("confidence", 0.75)), 0.90),
                ),
                source.name, target.name,
            ))
        return results
