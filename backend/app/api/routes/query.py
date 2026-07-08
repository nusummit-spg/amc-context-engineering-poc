"""WS3 — /query endpoints, powered by the merged context-engineering engine.

  POST /query/traditional   -> engine.retrieval.traditional_rag  (flat vector + LLM)
  POST /query/contextgraph  -> engine.retrieval.hybrid_graphrag  (graph + vector + LLM)
  POST /query               -> mode=traditional|contextgraph|both

The engine returns plain dicts; these handlers adapt them into the QueryResponse
schema the API and frontend already expect. The engine is self-contained (its own
FAISS store + Neo4j via app.engine.config), so these routes don't use the old
orchestrator/container.
"""
import asyncio
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from app.engine import config as engine_config
from app.engine import faiss_store as engine_faiss
from app.engine import retrieval
from app.schemas.api import QueryRequest, QueryResponse, TraditionalResult
from app.schemas.query import SourceAttribution, SynthesisOutput

router = APIRouter(prefix="/query", tags=["query"])


@lru_cache(maxsize=1)
def _store():
    """Cached FAISS store loaded from the prebuilt amc_master index.

    faiss_store's own INDEXES_DIR default resolves wrong once vendored into the
    package tree; point it at config.FAISS_DIR (app/engine/faiss_indexes), the
    same override the original app.py did.
    """
    engine_faiss.INDEXES_DIR = engine_config.FAISS_DIR
    return engine_faiss.BrochureFAISSStore("amc_master")


def _get_store():
    try:
        return _store()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"FAISS index unavailable: {exc}")


def _confidence(label: str | None) -> str:
    text = (label or "").lower()
    return "high" if "high" in text else "medium" if "medium" in text else "low"


# ---------- adapters: engine dicts -> QueryResponse ----------

def _traditional_response(query: str, result: dict) -> QueryResponse:
    docs = result.get("docs", [])
    resp = QueryResponse(query=query, mode="traditional")
    resp.traditional = TraditionalResult(
        files=[{
            "name": d.get("name"),
            "document_id": d.get("name"),
            "score": d.get("score"),
            "snippet": d.get("snippet"),
        } for d in docs],
        snippet=result.get("answer"),
        metrics={
            "docs_returned": len(docs),
            "retrieve_ms": int(result.get("retrieve_time", 0) * 1000),
            "llm_ms": int(result.get("llm_time", 0) * 1000),
            "note": "Vanilla RAG — flat vector search + LLM over retrieved passages.",
        },
    )
    resp.latency_ms = int(result.get("total_time", 0) * 1000)
    return resp


def _contextgraph_response(query: str, result: dict) -> QueryResponse:
    docs = result.get("docs", [])
    edges = result.get("graph_edges", [])
    resp = QueryResponse(query=query, mode="contextgraph")
    resp.answer = SynthesisOutput(
        answer=result.get("answer") or "No answer generated.",
        confidence=_confidence(result.get("confidence_label")),
        compliance_note=result.get("confidence_label"),
    )
    resp.sources = [
        SourceAttribution(
            source_index=i + 1,
            document_id=d.get("name", ""),
            document_title=d.get("name", ""),
            snippet=d.get("snippet"),
        )
        for i, d in enumerate(docs)
    ]
    resp.graph_highlight = {
        "node_names": sorted({str(n) for n in result.get("graph_nodes", [])}),
        "relationships": sorted({e.get("rel") for e in edges if e.get("rel")}),
        "entities": sorted(result.get("matched_entity_texts", []) or []),
        "labels": sorted(result.get("active_labels", []) or []),
    }
    resp.latency_ms = int(result.get("total_time", 0) * 1000)
    return resp


# ---------- endpoints ----------

@router.post("/traditional", response_model=QueryResponse)
async def run_traditional(request: QueryRequest) -> QueryResponse:
    store = _get_store()
    result = await asyncio.to_thread(retrieval.traditional_rag, request.query, store)
    return _traditional_response(request.query, result)


@router.post("/contextgraph", response_model=QueryResponse)
async def run_contextgraph(request: QueryRequest) -> QueryResponse:
    store = _get_store()
    result = await asyncio.to_thread(retrieval.hybrid_graphrag, request.query, store)
    return _contextgraph_response(request.query, result)


@router.post("", response_model=QueryResponse)
async def run_query(request: QueryRequest) -> QueryResponse:
    """Combined endpoint — mode selects one or both sides."""
    store = _get_store()
    resp = QueryResponse(query=request.query, mode=request.mode)

    if request.mode in ("traditional", "both"):
        trad = await asyncio.to_thread(retrieval.traditional_rag, request.query, store)
        resp.traditional = _traditional_response(request.query, trad).traditional
        resp.latency_ms = int(trad.get("total_time", 0) * 1000)

    if request.mode in ("contextgraph", "both"):
        ctx = await asyncio.to_thread(retrieval.hybrid_graphrag, request.query, store)
        cg = _contextgraph_response(request.query, ctx)
        resp.answer, resp.sources, resp.graph_highlight = cg.answer, cg.sources, cg.graph_highlight
        if request.mode == "contextgraph":
            resp.latency_ms = cg.latency_ms

    return resp
