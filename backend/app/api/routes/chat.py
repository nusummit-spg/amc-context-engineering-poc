# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS-Phase2 — /chat endpoint: multi-turn conversation on top of the existing
traditional_rag / hybrid_graphrag engine functions.

Coreference resolution (rewriting "why is their limit higher?" into a
self-contained query) and history compression live in app.engine.context_memory.
This route is the only caller of those — engine functions themselves stay
usable standalone (chat_history=None) for the existing /query endpoints.
"""
import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import Container, get_container
from app.api.routes.files import get_pdf_url
from app.api.routes.query import (
    _contextgraph_response,
    _get_store,
    _run_v2_orchestrator,
    _traditional_response,
)
from app.engine import context_memory, graph_store, retrieval
from app.schemas.api import ChatRequest, ChatResponse, ChatTitleRequest, ChatTitleResponse, QueryRequest

router = APIRouter(prefix="/chat", tags=["chat"])


async def _run_v2_chat(request: ChatRequest, container: Container) -> ChatResponse:
    query = request.query
    history = request.history
    session_id = request.session_id
    turn_index = len(history) // 2 + 1

    resp_obj = await container.orchestrator.answer(
        query=query,
        history=history,
        session_id=session_id,
    )
    intent = resp_obj.intent
    retrieval_res = resp_obj.retrieval
    context = resp_obj.context
    synthesis = resp_obj.synthesis
    trace = resp_obj.trace

    trad_result = None
    if request.mode in ("traditional", "both"):
        hits = await container.orchestrator.traditional_search(query)
        from app.schemas.api import TraditionalResult
        trad_result = TraditionalResult(
            files=[{
                "name": h.get("document_title") or h.get("filename") or h.get("document_id"),
                "document_id": h.get("document_id"),
                "score": h.get("score"),
                "page": h.get("page_start", 1),
                "url": get_pdf_url(h.get("document_title") or h.get("filename") or h.get("document_id", ""), h.get("page_start", 1)),
                "snippet": h.get("text", "")[:300],
                "full_text": h.get("text", ""),
            } for h in hits],
            snippet=synthesis.answer if request.mode == "traditional" else None,
            metrics={
                "docs_returned": len(hits),
                "retrieve_ms": int(trace.vector_ms if trace else 0),
                "llm_ms": int(trace.generation_ms if trace else 0),
            },
        )

    sources = [
        {
            **s.model_dump(),
            "url": get_pdf_url(s.document_title or s.document_id, getattr(s, "page", None)),
        }
        for s in context.sources
    ] if context.sources else [
        {
            "source_index": i + 1,
            "document_id": c.document_id,
            "document_title": c.document_title or c.document_id,
            "snippet": c.text[:300],
            "page": getattr(c, "page", None),
            "url": get_pdf_url(c.document_title or c.document_id, getattr(c, "page", None)),
        }
        for i, c in enumerate(retrieval_res.chunks[:5])
    ]

    graph_nodes = sorted({f.subject for f in retrieval_res.graph_facts} | {f.object for f in retrieval_res.graph_facts})
    graph_rels = sorted({f.predicate for f in retrieval_res.graph_facts})

    response_id = f"resp_{uuid.uuid4().hex[:12]}"
    interaction_id = f"int_{uuid.uuid4().hex[:12]}"

    hybrid_data = {
        "response_id": response_id,
        "interaction_id": interaction_id,
        "answer": synthesis.model_dump() if synthesis else None,
        "sources": sources,
        "graph_highlight": {"node_names": graph_nodes, "relationships": graph_rels},
        "latency_ms": int(trace.request_total_ms if trace else 0),
        "trace": trace.model_dump() if trace else None,
    }

    return ChatResponse(
        query=query,
        resolved_query=query,
        mode=request.mode,
        traditional=trad_result,
        hybrid=hybrid_data if request.mode in ("contextgraph", "both") else None,
        history=history,
        session_id=session_id,
        turn_index=turn_index,
        trace=trace,
        serving_engine="v2",
        corpus_version=container.settings.active_corpus_version,
        response_id=response_id,
        interaction_id=interaction_id,
    )


@router.post("/v2", response_model=ChatResponse)
async def run_chat_v2(
    request: ChatRequest,
    container: Container = Depends(get_container),
) -> ChatResponse:
    """Explicit v2 multi-turn chat endpoint."""
    return await _run_v2_chat(request, container)


@router.post("", response_model=ChatResponse)
async def run_chat(
    request: ChatRequest,
    container: Container = Depends(get_container),
) -> ChatResponse:
    """Multi-turn chat endpoint with QUERY_ENGINE routing."""
    engine = container.settings.query_engine.lower()

    if engine == "v2":
        return await _run_v2_chat(request, container)

    if engine == "canary":
        canary_pct = max(0, min(100, container.settings.canary_percentage))
        import zlib
        routing_key = request.session_id or request.query
        bucket = zlib.crc32(routing_key.encode("utf-8")) % 100
        if bucket < canary_pct:
            resp = await _run_v2_chat(request, container)
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

    store = _get_store()

    resolved_query = request.query
    if request.history:
        try:
            resolved_query = await asyncio.to_thread(
                context_memory.resolve_coreferences, request.query, request.history
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Coreference resolution failed: {exc}")

    turn_index = len(request.history) // 2 + 1
    response_id = f"resp_{uuid.uuid4().hex[:12]}"
    interaction_id = f"int_{uuid.uuid4().hex[:12]}"

    resp = ChatResponse(
        query=request.query,
        resolved_query=resolved_query,
        mode=request.mode,
        history=request.history,
        session_id=request.session_id,
        turn_index=turn_index,
        serving_engine="legacy",
        corpus_version="amc_master_legacy",
        response_id=response_id,
        interaction_id=interaction_id,
    )

    if request.mode in ("traditional", "both"):
        try:
            trad_result = await asyncio.to_thread(
                retrieval.traditional_rag, resolved_query, store,
                chat_history=request.history, session_id=request.session_id,
                turn_index=turn_index, original_query=request.query,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Traditional RAG failed: {exc}")
        resp.traditional = _traditional_response(resolved_query, trad_result).traditional

    if request.mode in ("contextgraph", "both"):
        try:
            ctx_result = await asyncio.to_thread(
                retrieval.hybrid_graphrag, resolved_query, store,
                chat_history=request.history, session_id=request.session_id,
                turn_index=turn_index, original_query=request.query,
            )
            summary = await asyncio.to_thread(graph_store.get_entity_type_summary, ctx_result.get("active_labels"))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"ContextGraph RAG failed: {exc}")
        cg_resp = _contextgraph_response(resolved_query, ctx_result, summary)
        resp.response_id = cg_resp.response_id or response_id
        resp.interaction_id = cg_resp.interaction_id or interaction_id
        resp.hybrid = {
            "response_id": resp.response_id,
            "interaction_id": resp.interaction_id,
            "answer": cg_resp.answer.model_dump() if cg_resp.answer else None,
            "sources": [s.model_dump() for s in cg_resp.sources],
            "graph_highlight": cg_resp.graph_highlight,
            "latency_ms": cg_resp.latency_ms,
        }

    return resp


# ---------- Chat streaming endpoint ----------

_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def _format_sse(event_type: str, data: dict) -> str:
    """Format a single SSE message frame."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _chat_stream_generator(request: "ChatRequest", container: Container):
    """Async generator for multi-turn chat streaming with full ContextGraph fidelity."""
    engine = container.settings.query_engine.lower()
    if engine == "v2":
        try:
            async for event in container.orchestrator.answer_stream(
                query=request.query,
                top_k=None,
                history=request.history,
                session_id=request.session_id,
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
        return

    # Default legacy engine streaming with full provenance, citations, graph triplets & telemetry
    queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    store = _get_store()
    resolved_query = request.query
    if request.history:
        try:
            resolved_query = await asyncio.to_thread(
                context_memory.resolve_coreferences, request.query, request.history
            )
        except Exception as exc:
            yield _format_sse("error", {"type": "error", "message": f"Coreference resolution failed: {exc}", "recoverable": False})
            return

    turn_index = len(request.history) // 2 + 1
    response_id = f"resp_{uuid.uuid4().hex[:12]}"
    interaction_id = f"int_{uuid.uuid4().hex[:12]}"

    def on_metadata(meta):
        loop.call_soon_threadsafe(queue.put_nowait, ("metadata", meta))

    def on_sources(docs_list):
        formatted_sources = [
            {
                "name": d.get("name"),
                "document_id": d.get("name"),
                "document_title": d.get("name"),
                "score": d.get("score"),
                "page": d.get("page"),
                "page_number": d.get("page"),
                "page_label": f"p. {d.get('page')}" if d.get("page") is not None else "—",
                "snippet": d.get("snippet"),
                "url": get_pdf_url(d.get("name", ""), d.get("page")),
            }
            for d in docs_list
        ]
        loop.call_soon_threadsafe(queue.put_nowait, ("sources", {"type": "sources", "sources": formatted_sources}))

    def on_chunk(text, idx):
        loop.call_soon_threadsafe(queue.put_nowait, ("chunk", {"type": "answer_chunk", "text": text, "index": idx}))

    def run_worker():
        try:
            ctx_result = retrieval.hybrid_graphrag(
                resolved_query,
                store,
                chat_history=request.history,
                session_id=request.session_id,
                turn_index=turn_index,
                original_query=request.query,
                stream_callback=on_chunk,
                metadata_callback=on_metadata,
                sources_callback=on_sources,
            )
            summary = graph_store.get_entity_type_summary(ctx_result.get("active_labels"))
            cg_resp = _contextgraph_response(resolved_query, ctx_result, summary)

            hybrid_payload = {
                "response_id": cg_resp.response_id or response_id,
                "interaction_id": cg_resp.interaction_id or interaction_id,
                "answer": cg_resp.answer.model_dump() if cg_resp.answer else None,
                "sources": [s.model_dump() for s in cg_resp.sources],
                "graph_highlight": cg_resp.graph_highlight,
                "confidence_label": ctx_result.get("confidence_label", "✓ High confidence"),
                "confidence_reason": ctx_result.get("confidence_reason", ""),
                "telemetry_breakdown": ctx_result.get("telemetry_breakdown", {}),
                "latency_ms": cg_resp.latency_ms,
            }

            loop.call_soon_threadsafe(queue.put_nowait, ("done", {
                "type": "complete",
                "response_id": response_id,
                "interaction_id": interaction_id,
                "hybrid": hybrid_payload,
            }))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", {
                "type": "error", "message": str(exc), "recoverable": False
            }))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    worker_task = asyncio.create_task(asyncio.to_thread(run_worker))
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            event_type, event_data = item
            yield _format_sse(event_type, event_data)
    finally:
        await worker_task


@router.post("/stream", response_class=StreamingResponse)
async def chat_stream(
    request: ChatRequest,
    container: Container = Depends(get_container),
) -> StreamingResponse:
    """Server-Sent Events streaming endpoint for /chat.

    Multi-turn aware: passes history and session_id so the orchestrator
    can perform coreference resolution before streaming.

    Event types match /query/stream for frontend symmetry:
      event: metadata, sources, chunk, done, error
    """
    return StreamingResponse(
        _chat_stream_generator(request, container),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


# ---------- Fast Conversation Title Generation ----------

def _fast_heuristic_title(query: str) -> str:
    """Instant heuristic fallback to extract a clean 2-5 word title without LLM."""
    import re
    cleaned = re.sub(
        r"^(can you\s+|could you\s+|please\s+|tell me about\s+|what is the\s+|what are the\s+|what is\s+|what are\s+|explain the\s+|explain\s+|how does\s+|how do i\s+|how to\s+|give me\s+|what about\s+|describe\s+|show me\s+|summarize\s+)+",
        "",
        query.strip(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[?!.,:;]+$", "", cleaned).strip()
    words = [w for w in cleaned.split() if w]
    if not words:
        return "New Conversation"
    chosen = words[:5]
    return " ".join(w if w.isupper() else w.capitalize() for w in chosen)


async def generate_chat_title(query: str) -> str:
    """Lightweight, near-instant conversation title generation (capped at 20 tokens)."""
    from app.engine import config, llm_text_client
    prompt = (
        "You are a concise conversation title generator. "
        "Generate a short, meaningful 2 to 5 word title that captures the primary topic and intent of the following user query.\n"
        "Rules:\n"
        "- Between 2 and 5 words maximum.\n"
        "- Plain text only: no quotation marks, no markdown, no ending period.\n"
        "- Respond with ONLY the title.\n\n"
        f"Query: {query}\n"
        "Title:"
    )
    try:
        raw_title, _ = await asyncio.to_thread(
            llm_text_client.call_llm_with_usage,
            prompt,
            model_id=config.GROQ_MODEL_LIGHT,
            max_tokens=20,
        )
        cleaned = (raw_title or "").strip().strip("\"'#* \n\r\t")
        cleaned_words = [w for w in cleaned.split() if w]
        if 2 <= len(cleaned_words) <= 6:
            return " ".join(cleaned_words[:5])
        elif len(cleaned_words) == 1 and len(cleaned_words[0]) > 2:
            return cleaned_words[0]
    except Exception as exc:
        import logging
        logging.getLogger("app").warning("Fast AI title generation fallback: %s", exc)

    return _fast_heuristic_title(query)


@router.post("/title", response_model=ChatTitleResponse)
async def generate_title_endpoint(
    request: ChatTitleRequest,
    container: Container = Depends(get_container),
) -> ChatTitleResponse:
    """Fast, lightweight endpoint to generate a concise 2-5 word conversation title."""
    title = await generate_chat_title(request.query)
    return ChatTitleResponse(title=title, session_id=request.session_id)
