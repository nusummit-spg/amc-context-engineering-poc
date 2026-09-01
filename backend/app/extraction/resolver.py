# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Entity Resolver (WS5e) — maps extracted mentions & query surface forms to
canonical entities.

Resolution order:
  1. Exact / alias match against the seed file + known graph entities (cheap).
  2. Fuzzy containment match (e.g. "Adani exposure" -> "Adani Group").
  3. LLM disambiguation for ambiguous mentions (only when candidates conflict).
"""
import json
import logging
from pathlib import Path
from typing import NamedTuple, Optional

from app.core.llm import LLMClient
from app.extraction.entities import ExtractedMention
from app.prompts import get_prompt
from app.schemas.documents import Document
from app.schemas.entities import ENTITY_CLASS_BY_TYPE, BaseEntity, EntityType

logger = logging.getLogger("extraction")

_DISAMBIGUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_id": {"type": ["string", "null"]},
    },
    "required": ["entity_id"],
    "additionalProperties": False,
}


class ResolutionResult(NamedTuple):
    """Typed result of resolving a surface form to a canonical entity."""
    entity: Optional[BaseEntity]
    confidence: float

    @property
    def name(self) -> Optional[str]:
        return self.entity.name if self.entity else None

    @property
    def entity_type(self):
        return self.entity.entity_type if self.entity else None

    def __bool__(self) -> bool:
        return self.entity is not None


class EntityResolver:
    def __init__(self, llm: LLMClient, alias_seed_path: Path):
        self._llm = llm
        self._canonical: dict[str, BaseEntity] = {}   # lower(canonical name) -> entity
        self._alias_index: dict[str, str] = {}        # lower(alias) -> canonical name
        self._load_seed(alias_seed_path)

    def _load_seed(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Alias seed file not found: %s", path)
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("entities", []):
            entity_type = EntityType(item["entity_type"])
            cls = ENTITY_CLASS_BY_TYPE[entity_type]
            entity = cls(
                name=item["canonical_name"],
                entity_type=entity_type,
                aliases=item.get("aliases", []),
            )
            self._register(entity)

    def _register(self, entity: BaseEntity) -> None:
        self._canonical[entity.name.lower()] = entity
        self._alias_index[entity.name.lower()] = entity.name
        for alias in entity.aliases:
            self._alias_index[alias.lower()] = entity.name

    # ---------- public API ----------

    def resolve_surface_form(self, surface: str) -> ResolutionResult:
        """Fast, non-LLM resolution used at query time. Returns ResolutionResult(entity, confidence)."""
        s = surface.lower().strip()
        if s in self._alias_index:
            return ResolutionResult(self._canonical[self._alias_index[s].lower()], 1.0)
        # containment fallback: longest alias contained in / containing the mention
        best: Optional[str] = None
        for alias, canonical in self._alias_index.items():
            if alias in s or s in alias:
                if best is None or len(alias) > len(best):
                    best = alias
        if best:
            return ResolutionResult(self._canonical[self._alias_index[best].lower()], 0.88)
        return ResolutionResult(None, 0.0)

    async def resolve_all(
        self, mentions: list[ExtractedMention], document: Document
    ) -> list[BaseEntity]:
        """Resolve extracted mentions to canonical entities; create new entities
        for genuinely unknown mentions."""
        resolved: dict[str, BaseEntity] = {}
        for mention in mentions:
            entity, conf = self.resolve_surface_form(mention.normalized_name)
            if entity is None:
                entity, conf = self.resolve_surface_form(mention.surface_form)

            if entity is None:
                entity = await self._disambiguate_or_create(mention, mention.confidence)
            else:
                # Update confidence based on match type if it's lower
                if hasattr(entity, "confidence"):
                    entity.confidence = min(entity.confidence, conf)

            if entity.entity_type.value != mention.type:
                # Type conflict between extractor and known entity — trust the seed.
                logger.debug("Type mismatch for %s: extracted %s, known %s",
                             mention.surface_form, mention.type, entity.entity_type)

            if document.document_id not in entity.source_document_ids:
                entity.source_document_ids.append(document.document_id)
            entity.properties.update(
                {k: v for k, v in mention.properties.items() if v is not None}
            )
            resolved[entity.name] = entity
        return list(resolved.values())

    async def _disambiguate_or_create(self, mention: ExtractedMention, base_confidence: float) -> BaseEntity:
        candidates = [
            e for e in self._canonical.values()
            if e.entity_type.value == mention.type
        ]
        if candidates:
            prompt = get_prompt("entity_disambiguation")
            rendered = prompt.render(
                mention=mention.surface_form,
                entity_type=mention.type,
                context=mention.context,
                candidates="\n".join(
                    f"- entity_id: {e.name} | name: {e.name} | aliases: {', '.join(e.aliases)}"
                    for e in candidates
                ),
            )
            try:
                result = await self._llm.complete_structured(
                    rendered, _DISAMBIGUATION_SCHEMA, system=prompt.system, fast=True,
                )
                match_id = result.get("entity_id")
                if match_id and match_id.lower() in self._canonical:
                    entity = self._canonical[match_id.lower()]
                    if mention.surface_form not in entity.aliases:
                        entity.aliases.append(mention.surface_form)
                        self._alias_index[mention.surface_form.lower()] = entity.name
                    return entity
            except Exception as exc:
                logger.warning("Disambiguation failed for %s: %s", mention.surface_form, exc)

        # Genuinely new entity
        entity_type = EntityType(mention.type)
        cls = ENTITY_CLASS_BY_TYPE[entity_type]
        entity = cls(
            name=mention.normalized_name,
            entity_type=entity_type,
            aliases=[mention.surface_form] if mention.surface_form != mention.normalized_name else [],
            confidence=min(base_confidence, 0.75),
        )
        self._register(entity)
        return entity
