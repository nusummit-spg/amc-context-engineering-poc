# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

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
import json
import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import Container, get_container
from app.api.routes.files import get_pdf_url
from app.engine import config as engine_config
from app.engine import faiss_store as engine_faiss
from app.engine import graph_store, retrieval
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
    resp.response_id = f"resp_{uuid.uuid4().hex[:12]}"
    resp.interaction_id = f"int_{uuid.uuid4().hex[:12]}"
    resp.traditional = TraditionalResult(
        files=[{
            "name": d.get("name"),
            "document_id": d.get("name"),
            "score": d.get("score"),
            "page": d.get("page"),
            "url": get_pdf_url(d.get("name", ""), d.get("page")),
            "snippet": d.get("snippet"),
            "full_text": d.get("full_text"),
        } for d in docs],
        snippet=result.get("answer"),
        metrics={
            "docs_returned": len(docs),
            "retrieve_ms": int(result.get("retrieve_time", 0) * 1000),
            "llm_ms": int(result.get("llm_time", 0) * 1000),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "total_tokens": result.get("total_tokens", 0),
            "note": "Vanilla RAG — flat vector search + LLM over retrieved passages.",
            "telemetry_breakdown": result.get("telemetry_breakdown", {}),
        },
    )
    resp.latency_ms = int(result.get("total_time", 0) * 1000)
    return resp


def _contextgraph_response(query: str, result: dict, entity_summary: list | None = None) -> QueryResponse:
    docs = result.get("docs", [])
    edges = result.get("graph_edges", [])
    resp = QueryResponse(query=query, mode="contextgraph")
    resp.response_id = f"resp_{uuid.uuid4().hex[:12]}"
    resp.interaction_id = f"int_{uuid.uuid4().hex[:12]}"

    citations_list = []
    for i, d in enumerate(docs):
        doc_name = d.get("name") or d.get("document_title") or d.get("document_id") or f"Document {i+1}"
        page_num = d.get("page") if d.get("page") is not None else d.get("page_num")
        page_lbl = f"p. {page_num}" if page_num is not None else "—"
        verbatim = d.get("full_text") or d.get("parent_text") or d.get("text") or d.get("snippet") or ""
        source_url = get_pdf_url(doc_name, page_num)
        chunk = {
            "chunk_id": f"src.{i+1}",
            "document_id": d.get("document_id") or doc_name,
            "document_name": doc_name,
            "page_number": page_num,
            "page_label": page_lbl,
            "verbatim_text": verbatim,
            "snippet": d.get("snippet") or (verbatim[:200] if verbatim else ""),
            "source_url": source_url,
            "local_doc_path": f"/api/files/{doc_name}",
            "score": d.get("score", 0.9),
        }
        citations_list.append({
            "marker": str(i + 1),
            "source": chunk,
        })

    provenance_list = [
        {
            "doc": c["source"]["document_name"],
            "document_title": c["source"]["document_name"],
            "name": c["source"]["document_name"],
            "page": c["source"]["page_number"] or 1,
            "page_number": c["source"]["page_number"],
            "page_label": c["source"]["page_label"],
            "chunk_id": f"p.{c['source']['page_number'] or 1}",
            "snippet": c["source"]["snippet"],
            "verbatim_text": c["source"]["verbatim_text"],
            "score": c["source"]["score"],
            "url": c["source"]["source_url"],
            "source_url": c["source"]["source_url"],
        }
        for c in citations_list
    ]

    telemetry_dict = result.get("telemetry_breakdown", {})
    metrics_list = telemetry_dict.get("cross_validation_ledger", {}).get("metrics", [])

    conf_label = result.get("confidence_label", "high confidence")
    conf_level = _confidence(conf_label)

    answer_str = result.get("answer") or "No answer generated."

    resp.answer = SynthesisOutput(
        answer=answer_str,
        answer_markdown=answer_str,
        confidence=conf_level,
        compliance_note=result.get("confidence_reason") or "",
        provenance=provenance_list,
        citations=citations_list,
        metrics=metrics_list,
    )
    resp.sources = [
        SourceAttribution(
            source_index=i + 1,
            document_id=c["source"]["document_id"],
            document_title=c["source"]["document_name"],
            snippet=c["source"]["snippet"],
            page=c["source"]["page_number"] or 1,
            page_number=c["source"]["page_number"],
            page_label=c["source"]["page_label"],
            verbatim_text=c["source"]["verbatim_text"],
            url=c["source"]["source_url"],
        )
        for i, c in enumerate(citations_list)
    ]
    edges_used = result.get("graph_edges_used_in_prompt", [])
    resp.graph_highlight = {
        "node_names": sorted({str(n) for n in result.get("graph_nodes", [])}),
        "relationships": sorted({e.get("rel") for e in edges if e.get("rel")}),
        "entities": sorted(result.get("matched_entity_texts", []) or []),
        "labels": sorted(result.get("active_labels", []) or []),
        # Full edges + entity-type summary so a thin UI client can render the graph.
        "edges": [{"s": e.get("s"), "rel": e.get("rel"), "o": e.get("o"), "conf": e.get("conf", 1.0)}
                  for e in edges],
        "edges_used_in_prompt": [{"s": e.get("s"), "rel": e.get("rel"), "o": e.get("o"), "conf": e.get("conf", 1.0)}
                                  for e in edges_used],
        "entity_summary": entity_summary or [],
        "query_type": result.get("query_type"),
        "graph_matched_by": result.get("graph_matched_by"),
        "used_verified_aggregate": result.get("used_verified_aggregate", False),
        "used_comparison_mode": result.get("used_comparison_mode", False),
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "total_tokens": result.get("total_tokens", 0),
        "telemetry_breakdown": result.get("telemetry_breakdown", {}),
        "provenance": provenance_list,
    }
    resp.latency_ms = int(result.get("total_time", 0) * 1000)
    return resp


# ---------- endpoints ----------

async def _run_v2_orchestrator(request: QueryRequest, container: Container) -> QueryResponse:
    query = request.query
    mode = request.mode
    resp_obj = await container.orchestrator.answer(query, top_k=request.top_k)
    intent = resp_obj.intent
    retrieval_res = resp_obj.retrieval
    context = resp_obj.context
    synthesis = resp_obj.synthesis
    trace = resp_obj.trace

    trad_result = None
    if mode in ("traditional", "both"):
        hits = await container.orchestrator.traditional_search(query, top_k=request.top_k)
        trad_result = TraditionalResult(
            files=[{
                "name": h.get("document_title") or h.get("filename") or h.get("document_id"),
                "document_id": h.get("document_id"),
                "score": h.get("score"),
                "page": h.get("page_start", 1),
                "snippet": h.get("text", "")[:300],
                "full_text": h.get("text", ""),
            } for h in hits],
            snippet=synthesis.answer if mode == "traditional" else None,
            metrics={
                "docs_returned": len(hits),
                "retrieve_ms": int(trace.vector_ms if trace else 0),
                "llm_ms": int(trace.generation_ms if trace else 0),
                "input_tokens": trace.input_tokens if trace else 0,
                "output_tokens": trace.output_tokens if trace else 0,
                "total_tokens": (trace.input_tokens + trace.output_tokens) if trace else 0,
                "note": "v2 Target Corpus Vector Search Baseline",
            },
        )

    sources = [
        SourceAttribution(
            source_index=src.source_index,
            document_id=src.document_id,
            document_title=src.document_title,
            chunk_id=src.chunk_id,
            snippet=src.snippet,
            page=getattr(src, "page", None),
            url=get_pdf_url(src.document_title or src.document_id, getattr(src, "page", None)),
        )
        for src in context.sources
    ] if context.sources else [
        SourceAttribution(
            source_index=i + 1,
            document_id=c.document_id,
            document_title=c.document_title or c.document_id,
            chunk_id=c.chunk_id,
            snippet=c.text[:300],
            page=getattr(c, "page", None),
            url=get_pdf_url(c.document_title or c.document_id, getattr(c, "page", None)),
        )
        for i, c in enumerate(retrieval_res.chunks[:5])
    ]

    graph_nodes = sorted({f.subject for f in retrieval_res.graph_facts} | {f.object for f in retrieval_res.graph_facts})
    graph_rels = sorted({f.predicate for f in retrieval_res.graph_facts})

    return QueryResponse(
        query=query,
        mode=mode,
        intent=intent,
        answer=synthesis if mode in ("contextgraph", "both") else None,
        sources=sources if mode in ("contextgraph", "both") else [],
        traversal_paths=retrieval_res.traversal_paths,
        taxonomy_paths=intent.taxonomy_paths,
        graph_highlight={"node_names": graph_nodes, "relationships": graph_rels},
        context_debug=context,
        traditional=trad_result,
        latency_ms=int(trace.request_total_ms if trace else 0),
        trace=trace,
        serving_engine="v2",
        corpus_version=container.settings.active_corpus_version,
        response_id=f"resp_{uuid.uuid4().hex[:12]}",
        interaction_id=f"int_{uuid.uuid4().hex[:12]}",
    )


@router.post("/v2", response_model=QueryResponse)
async def run_query_v2(
    request: QueryRequest,
    container: Container = Depends(get_container),
) -> QueryResponse:
    """Explicit v2 ContextGraph orchestrator endpoint."""
    return await _run_v2_orchestrator(request, container)


@router.post("/traditional", response_model=QueryResponse)
async def run_traditional(request: QueryRequest) -> QueryResponse:
    store = _get_store()
    result = await asyncio.to_thread(retrieval.traditional_rag, request.query, store)
    return _traditional_response(request.query, result)


@router.post("/contextgraph", response_model=QueryResponse)
async def run_contextgraph(request: QueryRequest) -> QueryResponse:
    store = _get_store()
    result = await asyncio.to_thread(retrieval.hybrid_graphrag, request.query, store)
    summary = await asyncio.to_thread(graph_store.get_entity_type_summary, result.get("active_labels"))
    return _contextgraph_response(request.query, result, summary)


@router.post("", response_model=QueryResponse)
async def run_query(
    request: QueryRequest,
    container: Container = Depends(get_container),
) -> QueryResponse:
    """Production query endpoint with QUERY_ENGINE feature flag routing."""
    engine = container.settings.query_engine.lower()

    if engine == "v2":
        return await _run_v2_orchestrator(request, container)

    if engine == "canary":
        canary_pct = max(0, min(100, container.settings.canary_percentage))
        import zlib
        bucket = zlib.crc32(request.query.encode("utf-8")) % 100
        if bucket < canary_pct:
            resp = await _run_v2_orchestrator(request, container)
            resp.serving_engine = f"canary-v2 ({canary_pct}%)"
            return resp

    if engine == "shadow":
        from app.retrieval.shadow import get_shadow_runner
        shadow_runner = get_shadow_runner()
        await shadow_runner.execute_shadow(
            query=request.query,
            legacy_result={},
            orchestrator=container.orchestrator,
        )

    # Default legacy engine execution
    store = _get_store()
    resp = QueryResponse(query=request.query, mode=request.mode)
    resp.serving_engine = "legacy"
    resp.corpus_version = "amc_master_legacy"
    resp.response_id = f"resp_{uuid.uuid4().hex[:12]}"
    resp.interaction_id = f"int_{uuid.uuid4().hex[:12]}"

    if request.mode in ("traditional", "both"):
        trad = await asyncio.to_thread(retrieval.traditional_rag, request.query, store)
        trad_resp = _traditional_response(request.query, trad)
        resp.traditional = trad_resp.traditional
        resp.latency_ms = int(trad.get("total_time", 0) * 1000)

    if request.mode in ("contextgraph", "both"):
        ctx = await asyncio.to_thread(retrieval.hybrid_graphrag, request.query, store)
        summary = await asyncio.to_thread(graph_store.get_entity_type_summary, ctx.get("active_labels"))
        cg = _contextgraph_response(request.query, ctx, summary)
        resp.answer, resp.sources, resp.graph_highlight = cg.answer, cg.sources, cg.graph_highlight
        resp.response_id = cg.response_id
        resp.interaction_id = cg.interaction_id
        if request.mode == "contextgraph":
            resp.latency_ms = cg.latency_ms

    return resp


# ---------- SSE helpers ----------

def _format_sse(event_type: str, data: dict) -> str:
    """Format a single SSE message frame."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _query_stream_generator(request: QueryRequest, container: Container):
    """Async generator that drives the orchestrator stream and formats SSE frames.

    Handles:
    - Per-event-type SSE framing
    - Converts internal type names to SSE event types
    - Catches top-level exceptions and emits error SSE frame
    """
    try:
        async for event in container.orchestrator.answer_stream(
            query=request.query,
            top_k=request.top_k,
        ):
            event_type = event.get("type", "chunk")
            # Map internal type names → SSE event types
            if event_type == "metadata":
                yield _format_sse("metadata", event)
            elif event_type == "sources":
                yield _format_sse("sources", event)
            elif event_type == "answer_chunk":
                yield _format_sse("chunk", event)
            elif event_type == "complete":
                yield _format_sse("done", event)
            elif event_type == "error":
                yield _format_sse("error", event)
            else:
                yield _format_sse("chunk", event)
    except Exception as exc:
        yield _format_sse("error", {"type": "error", "message": str(exc), "recoverable": False})


async def _chat_stream_generator(request, container: "Container"):
    """Async generator for chat streaming (multi-turn aware)."""
    try:
        async for event in container.orchestrator.answer_stream(
            query=request.query,
            top_k=getattr(request, "top_k", None),
            history=getattr(request, "history", None),
            session_id=getattr(request, "session_id", None),
        ):
            event_type = event.get("type", "chunk")
            if event_type == "metadata":
                yield _format_sse("metadata", event)
            elif event_type == "sources":
                yield _format_sse("sources", event)
            elif event_type == "answer_chunk":
                yield _format_sse("chunk", event)
            elif event_type == "complete":
                yield _format_sse("done", event)
            elif event_type == "error":
                yield _format_sse("error", event)
            else:
                yield _format_sse("chunk", event)
    except Exception as exc:
        yield _format_sse("error", {"type": "error", "message": str(exc), "recoverable": False})


# ---------- Streaming endpoints ----------

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",   # Disable nginx buffering for true streaming
    "Connection": "keep-alive",
}


@router.post("/stream", response_class=StreamingResponse)
async def query_stream(
    request: QueryRequest,
    container: Container = Depends(get_container),
) -> StreamingResponse:
    """Server-Sent Events streaming endpoint for /query.

    Streams pipeline progress events in real-time:
      event: metadata — intent + entities (immediately after classification)
      event: sources  — retrieved documents (after vector search)
      event: chunk    — LLM answer tokens as they arrive
      event: done     — completion signal with response_id
      event: error    — recoverable/non-recoverable error notification
    """
    return StreamingResponse(
        _query_stream_generator(request, container),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


@router.get("/health/stream-test")
async def stream_health_check() -> StreamingResponse:
    """Lightweight streaming capability probe.

    Returns a single SSE frame so the client can confirm SSE is supported
    end-to-end (not blocked by a proxy, firewall, or CORS policy).
    """
    async def _gen():
        yield _format_sse("ping", {"type": "ping", "status": "streaming_supported"})

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )
