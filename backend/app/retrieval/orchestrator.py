"""WS5e — Hybrid retrieval orchestrator: the 7-step flow.

  1. Intent classification        (LLM -> QueryIntent)
  2. Entity resolution            (surface forms -> canonical graph entities)
  3. Graph traversal              (Cypher templates by query type)
  4. Taxonomy scoping             (intent paths -> Qdrant filter)
  5. Vector search                (scoped semantic retrieval)
  6. Context assembly             (facts-first, token budget, quality gate)
  7. LLM synthesis                (inline citations, structured rows)

Also exposes `traditional_search()` — flat unscoped vector search — powering
the left panel of the comparison UI.
"""
import logging

from backend.app.config import get_settings
from backend.app.extraction.resolver import EntityResolver
from backend.app.retrieval.context import ContextAssembler
from backend.app.retrieval.intent import IntentClassifier
from backend.app.retrieval.synthesizer import Synthesizer
from backend.app.retrieval.traversal import GraphTraversal
from backend.app.schemas.entities import BaseEntity
from backend.app.schemas.query import (
    AssembledContext,
    QueryIntent,
    RetrievalResult,
    RetrievedChunk,
    SynthesisOutput,
)
from backend.app.vector.client import VectorStore

logger = logging.getLogger("retrieval")


class RetrievalOrchestrator:
    def __init__(
        self,
        intent_classifier: IntentClassifier,
        resolver: EntityResolver,
        traversal: GraphTraversal,
        vector_store: VectorStore,
        assembler: ContextAssembler,
        synthesizer: Synthesizer,
    ):
        self._intent = intent_classifier
        self._resolver = resolver
        self._traversal = traversal
        self._vector = vector_store
        self._assembler = assembler
        self._synthesizer = synthesizer
        self._top_k = get_settings().vector_top_k

    async def answer(
        self, query: str, top_k: int | None = None
    ) -> tuple[QueryIntent, RetrievalResult, AssembledContext, SynthesisOutput]:
        # Step 1 — intent
        intent = await self._intent.classify(query)
        logger.info("Intent: %s | entities=%s | taxonomy=%s",
                    intent.query_type.value, intent.entities_mentioned, intent.taxonomy_paths)

        # Step 2 — entity resolution
        resolved_entities: list[BaseEntity] = []
        resolved_map: dict[str, str] = {}
        for surface in intent.entities_mentioned:
            entity = self._resolver.resolve_surface_form(surface)
            if entity:
                resolved_entities.append(entity)
                resolved_map[surface] = entity.name

        # Step 3 — graph traversal
        facts, traversal_paths, cyphers = [], [], []
        if intent.requires_graph and resolved_entities:
            facts, traversal_paths, cyphers = await self._traversal.traverse(
                intent, resolved_entities
            )

        # Steps 4-5 — taxonomy-scoped vector search
        chunks: list[RetrievedChunk] = []
        if intent.requires_vector:
            hits = await self._vector.search(
                query,
                top_k=top_k or self._top_k,
                taxonomy_paths=intent.taxonomy_paths or None,
                entity_names=[e.name for e in resolved_entities] or None,
            )
            chunks = [
                RetrievedChunk(
                    chunk_id=h["chunk_id"],
                    document_id=h.get("document_id", ""),
                    document_title=h.get("document_title"),
                    text=h.get("text", ""),
                    score=h.get("score", 0.0),
                    taxonomy_paths=h.get("taxonomy_paths", []),
                )
                for h in hits
            ]

        retrieval = RetrievalResult(
            intent=intent,
            resolved_entities=resolved_map,
            graph_facts=facts,
            chunks=chunks,
            traversal_paths=traversal_paths,
            cypher_queries_run=cyphers,
        )

        # Step 6 — context assembly (WS5d)
        context = self._assembler.assemble(retrieval)
        if not context.passed_quality_gate:
            logger.warning("Context quality gate failed (score=%.2f) for query: %s",
                           context.quality_score, query)

        # Step 7 — synthesis
        synthesis = await self._synthesizer.synthesize(query, context)
        return intent, retrieval, context, synthesis

    async def traditional_search(self, query: str, top_k: int | None = None) -> list[dict]:
        """Flat vector search with no graph, no taxonomy scoping, no synthesis —
        the 'traditional RAG' comparison baseline."""
        hits = await self._vector.search(query, top_k=top_k or self._top_k)
        return hits
