"""WS3 — /query endpoints: run the retrieval engine, return structured responses.

The split-screen comparison UI calls two dedicated endpoints in parallel so each
side reports its own independent latency:

  POST /query/traditional   -> flat vector search only (comparison baseline)
  POST /query/contextgraph  -> full 7-step flow (graph + scoped vector + synthesis)

POST /query (mode=...) is kept as a combined convenience endpoint.
"""
import time

from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container
from app.schemas.api import QueryRequest, QueryResponse, TraditionalResult

router = APIRouter(prefix="/query", tags=["query"])


def _traditional_result(hits: list[dict]) -> TraditionalResult:
    files: list[dict] = []
    seen: set[str] = set()
    for h in hits:
        doc_id = h.get("document_id", "")
        if doc_id in seen:
            continue
        seen.add(doc_id)
        files.append({
            "name": h.get("document_title") or doc_id,
            "document_id": doc_id,
            "score": round(h.get("score", 0.0), 3),
            "snippet": (h.get("text") or "")[:220],
        })
    return TraditionalResult(
        files=files,
        snippet=(hits[0].get("text", "")[:300] if hits else None),
        metrics={
            "docs_returned": len(files),
            "consolidation": "manual",
            "note": "No consolidated answer — each document must be reviewed individually.",
        },
    )


async def _run_traditional(
    request: QueryRequest, container: Container, response: QueryResponse
) -> None:
    hits = await container.orchestrator.traditional_search(
        request.query, top_k=request.top_k
    )
    response.traditional = _traditional_result(hits)


async def _run_contextgraph(
    request: QueryRequest, container: Container, response: QueryResponse
) -> None:
    intent, retrieval, context, synthesis = await container.orchestrator.answer(
        request.query, top_k=request.top_k
    )
    response.intent = intent
    response.answer = synthesis
    response.sources = context.sources
    response.traversal_paths = retrieval.traversal_paths
    response.taxonomy_paths = intent.taxonomy_paths
    response.context_debug = context
    response.graph_highlight = {
        "node_names": sorted({f.subject for f in retrieval.graph_facts}
                             | {f.object for f in retrieval.graph_facts}),
        "relationships": sorted({f.predicate for f in retrieval.graph_facts}),
    }


@router.post("/traditional", response_model=QueryResponse)
async def run_traditional(
    request: QueryRequest,
    container: Container = Depends(get_container),
) -> QueryResponse:
    """Traditional RAG baseline — flat vector search, no graph, no synthesis."""
    start = time.perf_counter()
    response = QueryResponse(query=request.query, mode="traditional")
    await _run_traditional(request, container, response)
    response.latency_ms = int((time.perf_counter() - start) * 1000)
    return response


@router.post("/contextgraph", response_model=QueryResponse)
async def run_contextgraph(
    request: QueryRequest,
    container: Container = Depends(get_container),
) -> QueryResponse:
    """Context engineering — full 7-step hybrid flow with synthesized answer."""
    start = time.perf_counter()
    response = QueryResponse(query=request.query, mode="contextgraph")
    await _run_contextgraph(request, container, response)
    response.latency_ms = int((time.perf_counter() - start) * 1000)
    return response


@router.post("", response_model=QueryResponse)
async def run_query(
    request: QueryRequest,
    container: Container = Depends(get_container),
) -> QueryResponse:
    """Combined endpoint kept for convenience; prefer the two dedicated endpoints
    above when you need per-side latency."""
    start = time.perf_counter()
    response = QueryResponse(query=request.query, mode=request.mode)

    if request.mode in ("traditional", "both"):
        await _run_traditional(request, container, response)

    if request.mode in ("contextgraph", "both"):
        await _run_contextgraph(request, container, response)

    response.latency_ms = int((time.perf_counter() - start) * 1000)
    return response
