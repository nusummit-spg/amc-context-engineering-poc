"""WS3 — /graph endpoints: full graph fetch, node neighbourhood, traversal highlight."""
from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import Container, get_container
from backend.app.core.errors import NotFoundError
from backend.app.schemas.api import GraphEdgeOut, GraphNodeOut, GraphResponse

router = APIRouter(prefix="/graph", tags=["graph"])


def _to_response(raw: dict) -> GraphResponse:
    nodes = [
        GraphNodeOut(
            id=n["id"],
            label=(n["props"] or {}).get("name", ""),
            entity_type=(n["labels"] or ["Unknown"])[0],
            properties={k: v for k, v in (n["props"] or {}).items() if k != "name"},
        )
        for n in raw.get("nodes", [])
    ]
    edges = [
        GraphEdgeOut(
            id=e["id"],
            source=e["source"],
            target=e["target"],
            relationship_type=e["rel_type"],
            label=_edge_label(e),
            properties=e.get("props") or {},
        )
        for e in raw.get("edges", [])
    ]
    return GraphResponse(nodes=nodes, edges=edges)


def _edge_label(edge: dict) -> str:
    props = edge.get("props") or {}
    if edge["rel_type"] == "HOLDS" and props.get("pct_nav") is not None:
        return f"HOLDS {props['pct_nav']}%"
    if edge["rel_type"] == "AFFECTS" and props.get("status"):
        return f"AFFECTS · {props['status']}"
    return edge["rel_type"]


@router.get("", response_model=GraphResponse)
async def full_graph(
    limit: int = Query(500, le=2000),
    container: Container = Depends(get_container),
) -> GraphResponse:
    raw = await container.graph.full_graph(limit=limit)
    return _to_response(raw)


@router.get("/neighborhood", response_model=GraphResponse)
async def neighborhood(
    name: str = Query(..., description="Canonical entity name"),
    depth: int = Query(1, ge=1, le=3),
    container: Container = Depends(get_container),
) -> GraphResponse:
    entity = container.resolver.resolve_surface_form(name)
    canonical = entity.name if entity else name
    raw = await container.graph.neighborhood(canonical, depth=depth)
    if not raw.get("nodes"):
        raise NotFoundError(f"No graph node found for: {name}")
    return _to_response(raw)


@router.get("/traversal")
async def traversal_highlight(
    query: str = Query(...),
    container: Container = Depends(get_container),
) -> dict:
    """Nodes/edges a query's traversal touches — for click-to-highlight in the UI."""
    intent = await container.orchestrator._intent.classify(query)
    entities = []
    for surface in intent.entities_mentioned:
        e = container.resolver.resolve_surface_form(surface)
        if e:
            entities.append(e)
    facts, paths, cyphers = await container.orchestrator._traversal.traverse(intent, entities)
    return {
        "query": query,
        "query_type": intent.query_type.value,
        "highlight_nodes": sorted({f.subject for f in facts} | {f.object for f in facts}),
        "highlight_relationships": sorted({f.predicate for f in facts}),
        "traversal_paths": paths,
        "cypher_templates": cyphers,
    }
