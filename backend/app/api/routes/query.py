"""WS3 — /query endpoint: runs the retrieval engine, returns structured response.

mode=contextgraph -> full 7-step flow (graph + scoped vector + synthesis)
mode=traditional  -> flat vector search only (comparison baseline)
mode=both         -> both sides in one call (drives the split-screen UI)
"""
import time

from fastapi import APIRouter, Depends

from backend.app.api.deps import Container, get_container
from backend.app.schemas.api import QueryRequest, QueryResponse, TraditionalResult

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


@router.post("", response_model=QueryResponse)
async def run_query(
    request: QueryRequest,
    container: Container = Depends(get_container),
) -> QueryResponse:
    start = time.perf_counter()
    response = QueryResponse(query=request.query, mode=request.mode)

    if request.mode in ("traditional", "both"):
        hits = await container.orchestrator.traditional_search(
            request.query, top_k=request.top_k
        )
        response.traditional = _traditional_result(hits)

    if request.mode in ("contextgraph", "both"):
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

    response.latency_ms = int((time.perf_counter() - start) * 1000)
    return response
