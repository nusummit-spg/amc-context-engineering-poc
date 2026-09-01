# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS2/WS5e — Ingestion pipeline with canonical identity & ledger:

  [Parser] -> [Canonical Identity Hashing] -> [Chunker] -> [PII Scrub]
           -> [LLM Classifier -> Taxonomy Tagger]
           -> [NER + Entity Extractor -> Entity Resolver]
           -> [Relationship Extractor]
           -> writes: (Document)->(DocumentVersion)->(Chunk/Entity/TaxonomyNode)
           -> writes: chunks+embeddings to versioned FAISS vector store
"""
import logging
from pathlib import Path

from app.config import get_settings
from app.contracts.identity import (
    compute_content_sha256,
    generate_document_id,
    generate_document_version_id,
    generate_source_id,
)
from app.extraction.ambiguity import build_ambiguity_report, should_run_relationship_llm
from app.extraction.classifier import TaxonomyClassifier
from app.extraction.entities import EntityExtractor
from app.extraction.relationships import RelationshipExtractor
from app.extraction.resolver import EntityResolver
from app.graph.client import GraphClient
from app.ingestion.chunker import chunk_document
from app.ingestion.ledger import IngestionLedger, IngestionStage
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
        corpus_version: str | None = None,
    ) -> None:
        self._settings = get_settings()
        self._corpus_version = corpus_version or getattr(self._settings, "active_corpus_version", "v2_baseline_20260814")
        self._registry = build_registry()
        self._scrubber = PiiScrubber(alias_seed_path)
        self._vector = vector_store
        self._graph = graph_client
        self._classifier = classifier
        self._entity_extractor = entity_extractor
        self._resolver = resolver
        self._relationship_extractor = relationship_extractor
        self._ledger = IngestionLedger(corpus_version=self._corpus_version)

    async def ingest_file(self, path: Path) -> Document:
        logger.info("Ingesting %s (corpus_version=%s)", path.name, self._corpus_version)

        # Use posix path representation to prevent collisions between different subdirectories
        source_rel_path = path.as_posix() if isinstance(path, Path) else str(path).replace("\\", "/")
        source_id = generate_source_id(source_rel_path, namespace="corpus")
        doc_id = generate_document_id(source_id)
        doc_ver_id = generate_document_version_id(doc_id, content_sha)

        if self._ledger.is_activated(doc_ver_id):
            logger.info("Document version %s already activated in ledger, skipping duplicate ingest", doc_ver_id)

        # 1. Parse into unified schema
        parser = self._registry.get(path)
        document = parser.parse(path)
        document.document_id = doc_id
        document.source_id = source_id
        document.content_sha256 = content_sha
        document.document_version_id = doc_ver_id
        document.corpus_version = self._corpus_version

        self._ledger.record_stage(doc_ver_id, IngestionStage.PARSED, {"filename": path.name, "doc_id": doc_id})

        # 2. Chunk (heading/clause aware with canonical chunk IDs)
        chunks = chunk_document(document, max_tokens=self._settings.chunk_max_tokens)
        self._ledger.record_stage(doc_ver_id, IngestionStage.CHUNKED, {"chunks_count": len(chunks)})

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

        # 5b. Ambiguity gate — decide if relationship LLM is warranted
        ambiguity_report = build_ambiguity_report(
            document_id=document.document_id,
            mentions=raw_entities,
            sections=document.sections,
        )

        # 6. Relationship extraction (rule-based always; LLM only when gate fires)
        relationships = await self._relationship_extractor.extract(
            document, resolved,
            skip_llm=not should_run_relationship_llm(ambiguity_report),
        )

        # 7. Persist — graph population
        try:
            await self._graph.run(
                """
                MERGE (d:Document {document_id: $document_id})
                SET d.source_id = $source_id,
                    d.name = $name,
                    d.doc_type = $doc_type,
                    d.category = $category
                MERGE (v:DocumentVersion {document_version_id: $doc_ver_id})
                SET v.document_id = $document_id,
                    v.content_sha256 = $content_sha,
                    v.corpus_version = $corpus_version
                MERGE (d)-[:HAS_VERSION]->(v)
                """,
                document_id=document.document_id,
                source_id=source_id,
                doc_ver_id=doc_ver_id,
                content_sha=content_sha,
                corpus_version=self._corpus_version,
                name=document.title or document.filename,
                doc_type=document.doc_type.value,
                category=document.category.value,
            )
            for chunk in chunks:
                await self._graph.run(
                    """
                    MATCH (v:DocumentVersion {document_version_id: $doc_ver_id})
                    MERGE (c:Chunk {chunk_id: $chunk_id})
                    SET c.order = $order, c.locator = $locator
                    MERGE (v)-[:HAS_CHUNK]->(c)
                    """,
                    doc_ver_id=doc_ver_id,
                    chunk_id=chunk.chunk_id,
                    order=chunk.order,
                    locator=chunk.section_locator or f"chunk_{chunk.order}",
                )
            for entity in resolved:
                await self._graph.upsert_entity(entity)
                await self._graph.run(
                    f"""
                    MATCH (v:DocumentVersion {{document_version_id: $doc_ver_id}}), (e:{entity.entity_type.value} {{name: $name}})
                    MERGE (v)-[:MENTIONS]->(e)
                    """,
                    doc_ver_id=doc_ver_id,
                    name=entity.name,
                )
            for taxonomy_path in classification.taxonomy_paths:
                await self._graph.run(
                    """
                    MATCH (v:DocumentVersion {document_version_id: $doc_ver_id})
                    MERGE (t:TaxonomyNode {path: $path})
                    ON CREATE SET t.name = $node_name
                    MERGE (v)-[:TAGGED_AS]->(t)
                    """,
                    doc_ver_id=doc_ver_id,
                    path=taxonomy_path,
                    node_name=taxonomy_path.split("/")[-1],
                )
            for rel, source_name, target_name in relationships:
                rel.source_document_id = document.document_id
                rel.source_version_id = doc_ver_id
                rel.corpus_version = self._corpus_version
                await self._graph.upsert_relationship(rel, source_name, target_name)
            
            self._ledger.record_stage(doc_ver_id, IngestionStage.GRAPH_WRITTEN)
        except Exception as exc:
            logger.warning("Graph population partially failed for %s: %s", path.name, exc)

        # 8. Persist — embeddings to VectorStore
        indexed = await self._vector.index_chunks(chunks, {
            "title": document.title,
            "filename": document.filename,
            "doc_type": document.doc_type.value,
            "category": document.category.value,
        })
        self._ledger.record_stage(doc_ver_id, IngestionStage.VECTOR_WRITTEN, {"indexed_chunks": indexed})
        self._ledger.record_stage(doc_ver_id, IngestionStage.ACTIVATED)

        # Event-driven cache invalidation upon activation (Configurable)
        if getattr(self._settings, "enable_cache_invalidation_on_ingest", True):
            try:
                from app.retrieval.cache import get_semantic_cache
                cache = get_semantic_cache()
                cache.invalidate(corpus_version=self._corpus_version)
                logger.info("Event hook: invalidated semantic cache for corpus_version=%s upon activation", self._corpus_version)
            except Exception as cache_exc:
                logger.warning("Cache invalidation hook notice: %s", cache_exc)

        logger.info(
            "Ingested %s into %s: %d chunks, %d entities, %d relationships (doc_ver_id=%s)",
            path.name, self._corpus_version, indexed, len(resolved), len(relationships), doc_ver_id,
        )
        return document
