# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""LLM Classifier -> Taxonomy Tagger (architecture: ingestion pipeline stage 2)."""
import logging

from pydantic import BaseModel, Field

from app.core.llm import LLMClient
from app.prompts import get_prompt
from app.schemas.documents import Document, DocumentCategory
from app.schemas.taxonomy import TaxonomyTree

logger = logging.getLogger("extraction")

_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "taxonomy_paths": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string"},
    },
    "required": ["taxonomy_paths", "category"],
    "additionalProperties": False,
}


class ClassificationResult(BaseModel):
    taxonomy_paths: list[str] = Field(default_factory=list)
    category: DocumentCategory = DocumentCategory.OTHER


class TaxonomyClassifier:
    def __init__(self, llm: LLMClient, taxonomy: TaxonomyTree):
        self._llm = llm
        self._taxonomy = taxonomy
        self._valid_paths = {n.path for n in taxonomy.flatten()}

    async def classify(self, document: Document) -> ClassificationResult:
        prompt = get_prompt("taxonomy_classification")
        content = document.full_text[:8000]
        rendered = prompt.render(
            taxonomy_paths="\n".join(sorted(self._valid_paths)),
            filename=document.filename,
            content=content,
        )
        result = await self._llm.complete_structured(
            rendered, _CLASSIFICATION_SCHEMA, system=prompt.system, fast=True,
        )
        paths = [p for p in result.get("taxonomy_paths", []) if p in self._valid_paths]
        if not paths:
            logger.warning("No valid taxonomy paths for %s (raw: %s)",
                           document.filename, result.get("taxonomy_paths"))
        try:
            category = DocumentCategory(result.get("category", "other"))
        except ValueError:
            category = DocumentCategory.OTHER
        return ClassificationResult(taxonomy_paths=paths, category=category)
