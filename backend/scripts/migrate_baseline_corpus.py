# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Migrate baseline corpus into target version v2_baseline_20260814 with canonical IDs and provenance."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pickle
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.config import get_settings
from app.contracts.identity import (
    compute_content_sha256,
    generate_chunk_id,
    generate_document_id,
    generate_document_version_id,
    generate_source_id,
)
from app.extraction.resolver import EntityResolver
from app.graph.client import GraphClient
from app.ingestion.ledger import IngestionLedger, IngestionStage
from app.schemas.documents import Chunk, Document, DocumentCategory, DocumentType, Section
from app.schemas.entities import BaseEntity
from app.vector.client import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_corpus")

CORPUS_VERSION = "v2_baseline_20260814"


async def main():
    settings = get_settings()
    repo_root = root.parent
    
    # 1. Initialize versioned VectorStore, GraphClient, Ledger
    vector_dir = root / "data" / "vector_store" / CORPUS_VERSION
    vector_dir.mkdir(parents=True, exist_ok=True)
    vector_store = VectorStore(faiss_dir=str(vector_dir), corpus_version=CORPUS_VERSION)
    vector_store.ensure_collection()

    graph_client = GraphClient()
    
    alias_seed = root / "seeds" / "entity_aliases.json"
    if not alias_seed.exists():
        alias_seed = root / "data" / "alias_seed.json"
    resolver = EntityResolver(llm=None, alias_seed_path=alias_seed)
    ledger = IngestionLedger(corpus_version=CORPUS_VERSION, ledger_dir=root / "data" / "corpora" / CORPUS_VERSION)

    # 2. Load legacy pickle data to guarantee 100% baseline coverage
    pkl_path = root / "app" / "engine" / "faiss_indexes" / "amc_master" / "index.pkl"
    if not pkl_path.exists():
        raise FileNotFoundError(f"Missing legacy pickle: {pkl_path}")

    with open(pkl_path, "rb") as f:
        legacy_data = pickle.load(f)

    parents = legacy_data.get("parents", {})
    logger.info("Found %d legacy parent records", len(parents))

    # Group parents by source
    grouped_sources: dict[str, list[dict]] = {}
    for pid, p in parents.items():
        src = p.get("source", "unknown")
        p_copy = dict(p)
        p_copy["legacy_parent_id"] = pid
        grouped_sources.setdefault(src, []).append(p_copy)

    # Also check Docs/selected_source_documents
    docs_source_dir = repo_root / "Docs" / "selected_source_documents"

    total_chunks_indexed = 0
    total_docs_indexed = 0

    for src_name, parent_list in sorted(grouped_sources.items()):
        parent_list.sort(key=lambda x: (x.get("page", 1), x.get("legacy_parent_id", "")))
        
        # Check if raw PDF exists in Docs/selected_source_documents
        pdf_path = docs_source_dir / src_name
        if pdf_path.exists():
            raw_bytes = pdf_path.read_bytes()
            content_sha = compute_content_sha256(raw_bytes)
        else:
            concatenated = "".join(p.get("text", "") for p in parent_list)
            raw_bytes = concatenated.encode("utf-8")
            content_sha = compute_content_sha256(raw_bytes)

        source_id = generate_source_id(src_name, namespace="amc_master_baseline")
        doc_id = generate_document_id(source_id)
        doc_ver_id = generate_document_version_id(doc_id, content_sha)

        doc_type = DocumentType.PDF if src_name.lower().endswith(".pdf") else DocumentType.TEXT
        category = DocumentCategory.RESEARCH_NOTE if "call" in src_name.lower() or "earnings" in src_name.lower() else DocumentCategory.REGULATORY_CIRCULAR if "categorization" in src_name.lower() or "circular" in src_name.lower() else DocumentCategory.SCHEME_SID

        document = Document(
            document_id=doc_id,
            source_id=source_id,
            content_sha256=content_sha,
            document_version_id=doc_ver_id,
            corpus_version=CORPUS_VERSION,
            filename=src_name,
            doc_type=doc_type,
            category=category,
            title=src_name,
            sections=[],
        )

        ledger.record_stage(doc_ver_id, IngestionStage.PARSED, {"filename": src_name, "doc_id": doc_id})

        # Build chunks from parent records
        chunks: list[Chunk] = []
        for order, p in enumerate(parent_list):
            text = p.get("text", "").strip()
            page = p.get("page", 1)
            legacy_pid = p.get("legacy_parent_id", f"P{order:05d}")
            if len(text) < 20:
                text = f"[{src_name} p.{page}] {text} (Document section excerpt)"
            locator = f"page_{page}:{legacy_pid}"
            chunk_id = generate_chunk_id(doc_ver_id, locator, text)

            # Taxonomy paths heuristic from category / content
            tax_paths = []
            if "adani" in text.lower() or "adani" in src_name.lower():
                tax_paths.append("Research/Equity/Infrastructure/Coverage Notes")
                tax_paths.append("Risk/Concentration Exposure/Issuer Group/Monitoring")
            if "categorization" in src_name.lower() or "scheme" in text.lower():
                tax_paths.append("Compliance/Scheme Documents/SID/Equity Schemes")
                tax_paths.append("Compliance/Regulatory Circulars/Disclosure/FY26")
            if "hybrid" in src_name.lower() or "fund" in src_name.lower():
                tax_paths.append("Investor Communications/Fund Updates/Factsheets/Monthly")

            # Entity resolution over chunk text
            matched_entities = []
            for query_ent in ["Adani Group", "Adani Enterprises", "SEBI", "Cholamandalam", "NuSummit Infra Fund", "Axis Mutual Fund"]:
                res = resolver.resolve_surface_form(query_ent)
                if res and res.entity and (res.entity.name.lower() in text.lower() or query_ent.lower() in text.lower()):
                    matched_entities.append(res.entity.name)

            chunk = Chunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                document_version_id=doc_ver_id,
                source_id=source_id,
                content_sha256=content_sha,
                source_filename=src_name,
                section_locator=locator,
                page_start=page,
                page_end=page,
                corpus_version=CORPUS_VERSION,
                legacy_parent_id=legacy_pid,
                text=text,
                token_count=len(text) // 4,
                order=order,
                taxonomy_paths=tax_paths,
                entity_ids=matched_entities,
            )
            chunks.append(chunk)

        ledger.record_stage(doc_ver_id, IngestionStage.CHUNKED, {"chunks_count": len(chunks)})

        # Persist graph nodes & edges
        try:
            await graph_client.run(
                """
                MERGE (d:Document {document_id: $document_id})
                SET d.source_id = $source_id,
                    d.name = $name,
                    d.doc_type = $doc_type,
                    d.category = $category
                MERGE (v:DocumentVersion {document_version_id: $doc_ver_id})
                SET v.document_id = $document_id,
                    v.content_sha256 = $content_sha,
                    v.corpus_version = $corpus_version,
                    v.source_filename = $name
                MERGE (d)-[:HAS_VERSION]->(v)
                """,
                document_id=doc_id,
                source_id=source_id,
                doc_ver_id=doc_ver_id,
                content_sha=content_sha,
                corpus_version=CORPUS_VERSION,
                name=src_name,
                doc_type=doc_type.value,
                category=category.value,
            )

            for c in chunks:
                await graph_client.run(
                    """
                    MATCH (v:DocumentVersion {document_version_id: $doc_ver_id})
                    MERGE (chk:Chunk {chunk_id: $chunk_id})
                    SET chk.order = $order,
                        chk.locator = $locator,
                        chk.legacy_parent_id = $legacy_pid
                    MERGE (v)-[:HAS_CHUNK]->(chk)
                    """,
                    doc_ver_id=doc_ver_id,
                    chunk_id=c.chunk_id,
                    order=c.order,
                    locator=c.section_locator,
                    legacy_pid=c.legacy_parent_id,
                )
                for ent_name in c.entity_ids:
                    await graph_client.run(
                        """
                        MATCH (v:DocumentVersion {document_version_id: $doc_ver_id}), (e:Entity {name: $name})
                        MERGE (v)-[:MENTIONS]->(e)
                        """,
                        doc_ver_id=doc_ver_id,
                        name=ent_name,
                    )
                for tpath in c.taxonomy_paths:
                    await graph_client.run(
                        """
                        MATCH (v:DocumentVersion {document_version_id: $doc_ver_id})
                        MERGE (t:TaxonomyNode {path: $path})
                        ON CREATE SET t.name = $node_name
                        MERGE (v)-[:TAGGED_AS]->(t)
                        """,
                        doc_ver_id=doc_ver_id,
                        path=tpath,
                        node_name=tpath.split("/")[-1],
                    )

            ledger.record_stage(doc_ver_id, IngestionStage.GRAPH_WRITTEN)
        except Exception as exc:
            logger.warning("Graph write notice for %s: %s", src_name, exc)

        # Index chunks in vector store
        indexed = await vector_store.index_chunks(chunks, {
            "title": src_name,
            "filename": src_name,
            "doc_type": doc_type.value,
            "category": category.value,
        })
        total_chunks_indexed += indexed
        total_docs_indexed += 1

        ledger.record_stage(doc_ver_id, IngestionStage.VECTOR_WRITTEN, {"indexed_chunks": indexed})
        ledger.record_stage(doc_ver_id, IngestionStage.ACTIVATED)

        logger.info("Migrated [%d/%d] %s: %d chunks", total_docs_indexed, len(grouped_sources), src_name, indexed)

    await graph_client.close()
    logger.info("Migration complete: %d documents, %d chunks indexed into %s", total_docs_indexed, total_chunks_indexed, CORPUS_VERSION)


if __name__ == "__main__":
    asyncio.run(main())
