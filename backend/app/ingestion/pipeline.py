"""WS2/WS5e — Ingestion pipeline, matching the architecture diagram:

  [Parser] -> [Chunker] -> [PII Scrub] -> [LLM Classifier -> Taxonomy Tagger]
           -> [NER + Entity Extractor -> Entity Resolver]
           -> [Relationship Extractor]
           -> writes: chunks+embeddings to Qdrant, entities+edges to Neo4j
"""
import logging
from pathlib import Path

from app.config import get_settings
from app.extraction.classifier import TaxonomyClassifier
from app.extraction.entities import EntityExtractor
from app.extraction.relationships import RelationshipExtractor
from app.extraction.resolver import EntityResolver
from app.graph.client import GraphClient
from app.ingestion.chunker import chunk_document
from app.ingestion.parsers import build_registry
from app.ingestion.pii import PiiScrubber
from app.schemas.documents import Document
from app.vector.client import VectorStore

logger = logging.getLogger("ingestion")


class IngestionPipeline:
    def __init__(
        self,
        vector_store: VectorStore,
        graph_client: GraphClient,
        classifier: TaxonomyClassifier,
        entity_extractor: EntityExtractor,
        resolver: EntityResolver,
        relationship_extractor: RelationshipExtractor,
        alias_seed_path: Path | None = None,
    ) -> None:
        self._settings = get_settings()
        self._registry = build_registry()
        self._scrubber = PiiScrubber(alias_seed_path)
        self._vector = vector_store
        self._graph = graph_client
        self._classifier = classifier
        self._entity_extractor = entity_extractor
        self._resolver = resolver
        self._relationship_extractor = relationship_extractor

    async def ingest_file(self, path: Path) -> Document:
        logger.info("Ingesting %s", path.name)

        # 1. Parse into unified schema
        parser = self._registry.get(path)
        document = parser.parse(path)

        # 2. Chunk (heading/clause aware)
        chunks = chunk_document(document, max_tokens=self._settings.chunk_max_tokens)

        # 3. PII scrub
        for chunk in chunks:
            chunk.text, modified = self._scrubber.scrub(chunk.text)
            chunk.pii_scrubbed = modified

        # 4. Taxonomy classification (LLM) — tags document + all its chunks
        classification = await self._classifier.classify(document)
        document.category = classification.category
        for chunk in chunks:
            chunk.taxonomy_paths = classification.taxonomy_paths

        # 5. Entity extraction (LLM NER) + resolution against known aliases
        raw_entities = await self._entity_extractor.extract(document)
        resolved = await self._resolver.resolve_all(raw_entities, document)
        for chunk in chunks:
            chunk.entity_ids = [
                e.name for e in resolved
                if e.name.lower() in chunk.text.lower()
                or any(a.lower() in chunk.text.lower() for a in e.aliases)
            ]

        # 6. Relationship extraction (rule-based first, LLM-assisted second)
        relationships = await self._relationship_extractor.extract(document, resolved)

        # 7. Persist — graph population (WS5e)
        await self._graph.run(
            """
            MERGE (d:Document {document_id: $document_id})
            SET d.name = $name, d.doc_type = $doc_type, d.category = $category
            """,
            document_id=document.document_id,
            name=document.title or document.filename,
            doc_type=document.doc_type.value,
            category=document.category.value,
        )
        for entity in resolved:
            await self._graph.upsert_entity(entity)
            await self._graph.run(
                f"""
                MATCH (d:Document {{document_id: $document_id}}), (e:{entity.entity_type.value} {{name: $name}})
                MERGE (d)-[:MENTIONS]->(e)
                """,
                document_id=document.document_id,
                name=entity.name,
            )
        for taxonomy_path in classification.taxonomy_paths:
            await self._graph.run(
                """
                MATCH (d:Document {document_id: $document_id})
                MERGE (t:TaxonomyNode {path: $path})
                ON CREATE SET t.name = $node_name
                MERGE (d)-[:TAGGED_AS]->(t)
                """,
                document_id=document.document_id,
                path=taxonomy_path,
                node_name=taxonomy_path.split("/")[-1],
            )
        for rel, source_name, target_name in relationships:
            rel.source_document_id = document.document_id
            await self._graph.upsert_relationship(rel, source_name, target_name)

        # 8. Persist — embeddings to Qdrant
        indexed = await self._vector.index_chunks(chunks, {
            "title": document.title,
            "filename": document.filename,
            "doc_type": document.doc_type.value,
            "category": document.category.value,
        })
        logger.info(
            "Ingested %s: %d chunks, %d entities, %d relationships",
            path.name, indexed, len(resolved), len(relationships),
        )
        return document
