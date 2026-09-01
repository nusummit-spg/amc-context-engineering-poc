# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Phase 3 — Post-Ingestion Cross-Document Entity Resolution.

Links entity mentions across different documents (e.g., 'Adani Enterprises Ltd'
in AEL_AR_FY24.pdf and Adani_Portfolio_H1FY25_ESG.pdf) with canonical SAME_AS edges.
"""
import logging
from typing import Any
import numpy as np

from app.graph.client import GraphClient
from app.engine.faiss_store import _get_embedder

logger = logging.getLogger("extraction.cross_doc")


async def resolve_cross_doc_entities(
    graph: GraphClient, similarity_threshold: float = 0.90
) -> int:
    """Finds unresolved entity pairs across different documents and links them with SAME_AS edges."""
    logger.info("Starting cross-document entity resolution pass...")

    # Fetch all Entity names and IDs from Neo4j
    query = """
    MATCH (e)
    WHERE (e:Issuer OR e:Scheme OR e:RegulatoryCircular OR e:IssuerGroup)
      AND e.name IS NOT NULL
    RETURN id(e) AS node_id, labels(e)[0] AS label, e.name AS name,
           e.source_document_id AS doc_id
    LIMIT 2000
    """
    nodes = await graph.run(query)
    if len(nodes) < 2:
        logger.info("Not enough entity nodes for cross-document resolution.")
        return 0

    names = [n["name"] for n in nodes]
    embedder = _get_embedder()
    
    # Compute embeddings for exact string + semantic clustering
    vecs = embedder.encode(names, normalize_embeddings=True)
    
    edges_created = 0
    num_nodes = len(nodes)

    for i in range(num_nodes):
        for j in range(i + 1, num_nodes):
            node_a = nodes[i]
            node_b = nodes[j]

            # Only compare entities of the same label from DIFFERENT documents
            if node_a["label"] != node_b["label"]:
                continue
            if node_a.get("doc_id") and node_b.get("doc_id") and node_a["doc_id"] == node_b["doc_id"]:
                continue

            # Calculate cosine similarity
            sim = float(np.dot(vecs[i], vecs[j]))
            
            # Match condition: exact case-insensitive match OR high embedding similarity
            is_exact = node_a["name"].strip().lower() == node_b["name"].strip().lower()
            
            if is_exact or sim >= similarity_threshold:
                # Merge / Create SAME_AS relationship in Cypher
                merge_cypher = """
                MATCH (a), (b)
                WHERE id(a) = $id_a AND id(b) = $id_b
                MERGE (a)-[r:SAME_AS]->(b)
                SET r.confidence = $sim, r.resolved_type = $rel_type
                """
                await graph.run(
                    merge_cypher,
                    id_a=node_a["node_id"],
                    id_b=node_b["node_id"],
                    sim=round(sim, 4),
                    rel_type="exact" if is_exact else "embedding_similarity"
                )
                edges_created += 1

    logger.info("Cross-document entity resolution finished: %d SAME_AS edges created.", edges_created)
    return edges_created
