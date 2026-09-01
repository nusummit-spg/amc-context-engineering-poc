# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS3 — /taxonomy endpoints: tree fetch, node docs, query-highlight paths."""
from fastapi import APIRouter, Depends, Query

from app.api.deps import Container, get_container
from app.core.errors import NotFoundError
from app.graph import cypher_library as cql
from app.schemas.api import (
    TaxonomyNodeDocsResponse,
    TaxonomyNodeOut,
    TaxonomyTreeResponse,
)
from app.schemas.taxonomy import TaxonomyNode

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


def _to_out(node: TaxonomyNode, counts: dict[str, int]) -> TaxonomyNodeOut:
    # A branch's count includes its descendants' documents.
    own = sum(c for path, c in counts.items() if path.startswith(node.path))
    return TaxonomyNodeOut(
        node_id=node.node_id,
        name=node.name,
        path=node.path,
        level=node.level,
        document_count=own,
        children=[_to_out(c, counts) for c in node.children],
    )


async def _doc_counts(container: Container) -> dict[str, int]:
    rows = await container.graph.run(
        "MATCH (d:Document)-[:TAGGED_AS]->(t:TaxonomyNode) "
        "RETURN t.path AS path, count(DISTINCT d) AS c"
    )
    return {r["path"]: r["c"] for r in rows}


@router.get("", response_model=TaxonomyTreeResponse)
async def get_tree(container: Container = Depends(get_container)) -> TaxonomyTreeResponse:
    counts = await _doc_counts(container)
    tree = container.taxonomy
    return TaxonomyTreeResponse(
        version=tree.version,
        domain=tree.domain,
        roots=[_to_out(r, counts) for r in tree.roots],
    )


@router.get("/node/docs", response_model=TaxonomyNodeDocsResponse)
async def node_documents(
    path: str = Query(..., description="Taxonomy path, e.g. Compliance/Regulatory Circulars"),
    container: Container = Depends(get_container),
) -> TaxonomyNodeDocsResponse:
    if container.taxonomy.find(path) is None and not any(
        n.path.startswith(path) for n in container.taxonomy.flatten()
    ):
        raise NotFoundError(f"Unknown taxonomy path: {path}")
    rows = await container.graph.run(cql.TAXONOMY_DOCUMENTS, path=path)
    return TaxonomyNodeDocsResponse(path=path, documents=rows)


@router.get("/highlight")
async def highlight_paths(
    query: str = Query(...),
    container: Container = Depends(get_container),
) -> dict:
    """Which taxonomy branches a query would activate — for the UI tree highlight."""
    intent = await container.orchestrator._intent.classify(query)
    return {
        "query": query,
        "query_type": intent.query_type.value,
        "taxonomy_paths": intent.taxonomy_paths,
    }
