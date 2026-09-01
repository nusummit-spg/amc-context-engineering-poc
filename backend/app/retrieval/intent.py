# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Retrieval step 1 — Intent classification (LLM -> QueryIntent)."""
import logging

from app.core.llm import LLMClient
from app.prompts import get_prompt
from app.schemas.query import QueryIntent, QueryType
from app.schemas.taxonomy import TaxonomyTree

logger = logging.getLogger("retrieval")

_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "query_type": {
            "type": "string",
            "enum": [
                "exposure_aggregation", "compliance_check",
                "house_view_synthesis", "entity_lookup", "general",
            ],
        },
        "entities_mentioned": {"type": "array", "items": {"type": "string"}},
        "taxonomy_paths": {"type": "array", "items": {"type": "string"}},
        "requires_graph": {"type": "boolean"},
        "requires_vector": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": [
        "query_type", "entities_mentioned", "taxonomy_paths",
        "requires_graph", "requires_vector",
    ],
    "additionalProperties": False,
}


class IntentClassifier:
    def __init__(self, llm: LLMClient, taxonomy: TaxonomyTree):
        self._llm = llm
        self._taxonomy = taxonomy
        self._valid_paths = sorted(n.path for n in taxonomy.flatten())

    async def classify(self, query: str) -> QueryIntent:
        prompt = get_prompt("query_intent")
        rendered = prompt.render(
            taxonomy_paths="\n".join(self._valid_paths),
            query=query,
        )
        try:
            result = await self._llm.complete_structured(
                rendered, _INTENT_SCHEMA, system=prompt.system, fast=True,
            )
        except Exception as exc:
            logger.warning("Intent classification failed, falling back to general: %s", exc)
            return QueryIntent(
                query_type=QueryType.GENERAL,
                requires_graph=False, requires_vector=True,
            )

        # Keep only taxonomy paths that exist (LLM may hallucinate a variant);
        # also accept prefixes of valid paths (branch-level activation).
        paths = []
        for p in result.get("taxonomy_paths", []):
            if p in self._valid_paths or any(v.startswith(p) for v in self._valid_paths):
                paths.append(p)

        return QueryIntent(
            query_type=QueryType(result["query_type"]),
            entities_mentioned=result.get("entities_mentioned", []),
            taxonomy_paths=paths,
            requires_graph=result.get("requires_graph", True),
            requires_vector=result.get("requires_vector", True),
            reasoning=result.get("reasoning"),
        )
