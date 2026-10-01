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
import logging
import uuid
from typing import Any, Dict, List, Optional

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
from app.retrieval.query_evidence_recorder import get_recorder as get_query_evidence_recorder
from app.models.api import ChatRequest, ChatResponse, ChatTitleRequest, ChatTitleResponse, QueryRequest

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("app.api.chat")


async def _trigger_follow_up_detection(
    session_id: str,
    previous_response_id: str,
    previous_query: str,
    follow_up_query: str,
    session_history: Optional[list] = None,
):
    """Run follow-up detection in background without adding latency to the response pipeline."""
    try:
        import time
        from app.core.metrics import (
            passive_feedback_detections_triggered,
            passive_feedback_corrections_found,
            passive_feedback_detection_latency,
        )

        passive_feedback_detections_triggered.inc()
        start_t = time.perf_counter()

        logger.info(
            "Auto follow-up detection: session=%s, prev_resp=%s",
            session_id,
            previous_response_id,
        )
        from app.api.routes.feedback import run_follow_up_detection_logic

        result = await run_follow_up_detection_logic(
            session_id=session_id,
            previous_response_id=previous_response_id,
            follow_up_query=follow_up_query,
            original_query=previous_query,
            session_history=session_history,
        )
        latency = time.perf_counter() - start_t
        passive_feedback_detection_latency.observe(latency)

        if result and result.get("is_correction"):
            passive_feedback_corrections_found.inc()
            logger.info(
                "Correction detected automatically via passive feedback: %s",
                result.get("claim"),
            )
    except Exception as exc:
        logger.warning("Passive follow-up detection failed: %s", exc)


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
        from app.models.api import TraditionalResult
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
                "input_tokens": trace.input_tokens if trace else 0,
                "output_tokens": trace.output_tokens if trace else 0,
                "total_tokens": (trace.input_tokens + trace.output_tokens) if trace else 0,
                # Build telemetry_breakdown in legacy key format so the frontend
                # _adapt_traditional() and _render_telemetry_card() functions work.
                "telemetry_breakdown": {
                    "latency_vector_db_ms": round(trace.vector_ms, 1) if trace else 0.0,
                    "latency_rerank_ms": round(trace.rerank_ms, 1) if trace else 0.0,
                    "latency_graph_db_ms": round(trace.graph_ms, 1) if trace else 0.0,
                    "latency_ner_processing_ms": round(trace.ner_ms, 1) if trace else 0.0,
                    "latency_llm_generation_ms": round(trace.generation_ms, 1) if trace else 0.0,
                    "latency_post_retrieval_processing_ms": round(trace.assembly_ms, 1) if trace else 0.0,
                    "latency_total_pipeline_ms": round(trace.request_total_ms, 1) if trace else 0.0,
                    "tokens_input": trace.input_tokens if trace else 0,
                    "tokens_output": trace.output_tokens if trace else 0,
                    "tokens_total": (trace.input_tokens + trace.output_tokens) if trace else 0,
                    "db_candidates_surfaced": len(hits),
                    "vector_bypassed": False,
                    "pipeline_mode": "Traditional Vector RAG (v2)",
                } if trace else {},
            },
        )

    sources = [
        {
            **s.model_dump(),
            "url": get_pdf_url(s.document_title or s.document_id, getattr(s, "page", None)),
        }
        for s in context.sources
    ] if context and context.sources else [
        {
            "source_index": i + 1,
            "document_id": c.document_id,
            "document_title": c.document_title or c.document_id,
            "snippet": c.text[:300],
            "page": getattr(c, "page", None),
            "url": get_pdf_url(c.document_title or c.document_id, getattr(c, "page", None)),
        }
        for i, c in enumerate((retrieval_res.chunks if retrieval_res else [])[:5])
    ]

    graph_facts = retrieval_res.graph_facts if retrieval_res else []
    graph_nodes = sorted({f.subject for f in graph_facts} | {f.object for f in graph_facts})
    graph_rels = sorted({f.predicate for f in graph_facts})

    # Build graph edge objects in the legacy {s, rel, o, conf} shape so the
    # frontend _render_mini_graph() SVG renderer and triplet inspector work.
    graph_edges = [
        {"s": f.subject, "rel": f.predicate, "o": f.object, "conf": f.properties.get("confidence", 1.0)}
        for f in graph_facts
    ]

    # Derive entity names and active labels from intent + graph facts.
    matched_entity_texts = sorted(set(intent.entities_mentioned)) if intent else []
    # Collect unique entity-type labels from graph fact properties when available.
    active_labels = sorted({
        f.properties.get("entity_type") or ""
        for f in graph_facts
        if f.properties.get("entity_type")
    })

    # Build a minimal entity_summary list (ontology tree) from the graph facts.
    # Group node names by their entity_type property; fall back to a single
    # "Entity" bucket when no type info is present.
    from collections import defaultdict
    label_counts: dict[str, int] = defaultdict(int)
    for f in graph_facts:
        etype = f.properties.get("entity_type") or "Entity"
        label_counts[etype] += 1
    entity_summary = [
        {"label": lbl, "count": cnt, "active": True}
        for lbl, cnt in sorted(label_counts.items())
    ] if label_counts else []

    # Build provenance rows from context sources (same structure as legacy provenance_list).
    provenance_list: list[dict] = []
    if context and context.sources:
        for i, src in enumerate(context.sources):
            page_num = getattr(src, "page_number", None) or getattr(src, "page", None)
            page_label = getattr(src, "page_label", None) or (f"p. {page_num}" if page_num else "—")
            verbatim = getattr(src, "verbatim_text", None) or src.snippet or ""
            doc_name = src.document_title or src.document_id
            provenance_list.append({
                "doc": doc_name,
                "document_title": doc_name,
                "name": doc_name,
                "page": page_num or 1,
                "page_number": page_num,
                "page_label": page_label,
                "chunk_id": src.chunk_id or f"p.{page_num or 1}",
                "snippet": src.snippet or (verbatim[:200] if verbatim else ""),
                "verbatim_text": verbatim,
                "score": getattr(src, "score", 0.9),
                "url": get_pdf_url(doc_name, page_num),
                "source_url": get_pdf_url(doc_name, page_num),
            })

    # Token counts
    total_tokens = (trace.input_tokens + trace.output_tokens) if trace else 0

    # Build telemetry_breakdown in the legacy key names so _render_telemetry_card()
    # and all frontend stat panels display correctly.
    telemetry_breakdown = {
        "latency_vector_db_ms": round(trace.vector_ms, 1) if trace else 0.0,
        "latency_rerank_ms": round(trace.rerank_ms, 1) if trace else 0.0,
        "latency_graph_db_ms": round(trace.graph_ms, 1) if trace else 0.0,
        "latency_ner_processing_ms": round(trace.ner_ms, 1) if trace else 0.0,
        "latency_llm_generation_ms": round(trace.generation_ms, 1) if trace else 0.0,
        "latency_post_retrieval_processing_ms": round(trace.assembly_ms, 1) if trace else 0.0,
        "latency_total_pipeline_ms": round(trace.request_total_ms, 1) if trace else 0.0,
        "tokens_input": trace.input_tokens if trace else 0,
        "tokens_output": trace.output_tokens if trace else 0,
        "tokens_total": total_tokens,
        "db_candidates_surfaced": len(graph_nodes),
        "vector_bypassed": False,
        "pipeline_mode": "ContextGraph Hybrid RAG (v2)",
        # Cache savings fields — populated when trace indicates a cache hit.
        "cache_hit": trace.cache_hit if trace else False,
        "tokens_saved": trace.tokens_saved if trace else 0,
        "tokens_cold_equivalent": trace.cold_equivalent_tokens if trace else 0,
    } if trace else {}

    # Derive confidence_label in the legacy display format.
    conf_str = (synthesis.confidence if synthesis else "high") or "high"
    conf_label_map = {"high": "✓ High confidence", "medium": "⚠ Medium confidence", "low": "✗ Low confidence"}
    confidence_label = conf_label_map.get(conf_str.lower(), f"✓ {conf_str.capitalize()} confidence")

    # query_type string for the frontend badge
    query_type_str = intent.query_type.value if intent and intent.query_type else None

    response_id = f"resp_{uuid.uuid4().hex[:12]}"
    interaction_id = f"int_{uuid.uuid4().hex[:12]}"

    # Build the hybrid dict in the exact legacy-compatible shape so the
    # frontend _adapt_hybrid() / _to_hybrid() adapters need no changes.
    hybrid_data = {
        "response_id": response_id,
        "interaction_id": interaction_id,
        # answer block — match legacy SynthesisOutput field names expected by adapters
        "answer": {
            **(synthesis.model_dump() if synthesis else {}),
            # Ensure compliance_note + confidence surface correctly regardless of
            # whether the adapter reads .compliance_note or .confidence.
            "compliance_note": confidence_label,
            "confidence": conf_str,
        },
        # sources list — one entry per context source
        "sources": sources,
        # graph_highlight — full legacy-compatible dict; adapters read everything from here
        "graph_highlight": {
            "node_names": graph_nodes,
            "relationships": graph_rels,
            "entities": matched_entity_texts,
            "labels": active_labels,
            "edges": graph_edges,
            "edges_used_in_prompt": graph_edges,   # V2 doesn't separate "used" vs "all"; expose all
            "entity_summary": entity_summary,
            "query_type": query_type_str,
            "graph_matched_by": "graph_facts" if graph_facts else None,
            "used_verified_aggregate": False,
            "used_comparison_mode": False,
            "total_tokens": total_tokens,
            "telemetry_breakdown": telemetry_breakdown,
            "provenance": provenance_list,
        },
        "latency_ms": int(trace.request_total_ms if trace else 0),
        "confidence_label": confidence_label,
        "confidence_reason": synthesis.compliance_note if synthesis else "",
        "telemetry_breakdown": telemetry_breakdown,
        "trace": trace.model_dump() if trace else None,
    }

    # Audit evidence — ContextGraph turns only (never traditional-only turns).
    if request.mode in ("contextgraph", "both"):
        await asyncio.to_thread(
            get_query_evidence_recorder().record_v2_contextgraph_turn,
            session_id=session_id,
            query_text=query,
            hybrid=hybrid_data,
            intent=intent,
            trace=trace,
            serving_engine="v2",
        )
        # Feedback timer & lifecycle management in data.db
        try:
            from app.feedback.feedback_timer import get_feedback_timer_manager
            feedback_timer = get_feedback_timer_manager()
            await feedback_timer.on_query_submitted(
                session_id=session_id,
                response_id=response_id,
                interaction_id=interaction_id,
                turn_number=turn_index,
                query_text=query,
                response_text=synthesis.answer if synthesis else None,
            )
        except Exception as timer_exc:
            logger.error("FeedbackTimer registration error: %s", timer_exc, exc_info=True)

        # Register response with SessionManager and trigger passive follow-up detection if eligible
        try:
            from app.feedback.session_manager import get_session_manager
            session_manager = get_session_manager()
            previous_response = await session_manager.register_response(
                session_id=session_id,
                response_id=response_id,
                query_text=query,
            )
            logger.info(f"SessionManager: Registered response_id={response_id}, previous={previous_response is not None}")
            if previous_response:
                await session_manager.mark_detected(session_id, previous_response.response_id)
                history_queries = [
                    h.get("query", "") if isinstance(h, dict) else getattr(h, "query", "")
                    for h in (history or [])
                ]
                asyncio.create_task(_trigger_follow_up_detection(
                    session_id=session_id,
                    previous_response_id=previous_response.response_id,
                    previous_query=previous_response.query_text,
                    follow_up_query=query,
                    session_history=[q for q in history_queries if q],
                ))
        except Exception as sm_exc:
            logger.warning("SessionManager registration error: %s", sm_exc, exc_info=True)

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

        # Audit evidence — ContextGraph half only; the traditional_rag result
        # above is deliberately not recorded.
        await asyncio.to_thread(
            get_query_evidence_recorder().record_contextgraph_turn,
            session_id=request.session_id,
            query_text=resolved_query,
            result=ctx_result,
            hybrid=resp.hybrid,
            serving_engine="legacy",
        )

    if resp.response_id:
        try:
            from app.feedback.feedback_timer import get_feedback_timer_manager
            feedback_timer = get_feedback_timer_manager()
            await feedback_timer.on_query_submitted(
                session_id=request.session_id,
                response_id=resp.response_id,
                interaction_id=resp.interaction_id or response_id,
                turn_number=turn_index,
                query_text=request.query,
                response_text=resp.hybrid.get("answer", {}).get("answer") if resp.hybrid and resp.hybrid.get("answer") else None,
            )
        except Exception as timer_exc:
            logger.error("FeedbackTimer registration error (legacy): %s", timer_exc, exc_info=True)

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
        # Streamed events arrive piecemeal; accumulate enough to write one
        # query_evidence record when the stream completes.
        stream_meta: dict = {}
        stream_sources: list = []
        answer_parts: list[str] = []
        try:
            async for event in container.orchestrator.answer_stream(
                query=request.query,
                top_k=None,
                history=request.history,
                session_id=request.session_id,
            ):
                event_type = event.get("type", "chunk")
                if event_type == "metadata":
                    stream_meta = event
                    yield _format_sse("metadata", event)
                elif event_type == "sources":
                    stream_sources = event.get("sources") or []
                    yield _format_sse("sources", event)
                elif event_type == "answer_chunk":
                    answer_parts.append(event.get("text", ""))
                    yield _format_sse("chunk", event)
                elif event_type == "complete":
                    # Build proper hybrid data structure from the enriched complete event
                    complete_trace = event.get("trace", {})
                    complete_answer = event.get("answer", {})
                    complete_graph_facts = event.get("graph_facts", [])
                    complete_sources = event.get("context_sources", stream_sources)
                    
                    hybrid_data_complete = {
                        "response_id": event.get("response_id"),
                        "interaction_id": event.get("response_id"),  # Use response_id as interaction_id
                        "answer": complete_answer if complete_answer else {
                            "answer": "".join(answer_parts).strip(),
                            "confidence": "high",
                            "compliance_note": None,
                            "citations": [],
                            "structured_rows": [],
                        },
                        "sources": complete_sources if complete_sources else stream_sources,
                        "graph_highlight": {
                            "node_names": event.get("graph_nodes", []),
                            "relationships": event.get("graph_relationships", []),
                            "entities": stream_meta.get("entities") or [],
                        },
                        "latency_ms": complete_trace.get("request_total_ms"),
                    }
                    
                    await asyncio.to_thread(
                        get_query_evidence_recorder().record_v2_contextgraph_turn,
                        session_id=request.session_id,
                        query_text=request.query,
                        hybrid=hybrid_data_complete,
                        intent={
                            "query_type": stream_meta.get("intent"),
                            "entities_mentioned": stream_meta.get("entities") or [],
                        },
                        trace=complete_trace,
                        serving_engine="v2-stream",
                    )
                    
                    # Register with SessionManager for passive feedback detection
                    try:
                        from app.feedback.session_manager import get_session_manager
                        session_manager = get_session_manager()
                        response_id_for_passive = event.get("response_id", f"resp_{uuid.uuid4().hex[:12]}")
                        previous_response = await session_manager.register_response(
                            session_id=request.session_id,
                            response_id=response_id_for_passive,
                            query_text=request.query,
                        )
                        logger.info(f"SessionManager (v2-stream): Registered response_id={response_id_for_passive}, previous={previous_response is not None}")
                        if previous_response:
                            await session_manager.mark_detected(request.session_id, previous_response.response_id)
                            history_queries = [
                                h.get("query", "") if isinstance(h, dict) else getattr(h, "query", "")
                                for h in (request.history or [])
                            ]
                            asyncio.create_task(_trigger_follow_up_detection(
                                session_id=request.session_id,
                                previous_response_id=previous_response.response_id,
                                previous_query=previous_response.query_text,
                                follow_up_query=request.query,
                                session_history=[q for q in history_queries if q],
                            ))
                    except Exception as sm_exc:
                        logger.warning("SessionManager registration error (v2-stream): %s", sm_exc, exc_info=True)

                    # Feedback timer & lifecycle management in data.db
                    try:
                        from app.feedback.feedback_timer import get_feedback_timer_manager
                        feedback_timer = get_feedback_timer_manager()
                        await feedback_timer.on_query_submitted(
                            session_id=request.session_id,
                            response_id=response_id_for_passive,
                            interaction_id=event.get("response_id", response_id_for_passive),
                            turn_number=len(request.history) // 2 + 1,
                            query_text=request.query,
                            response_text=complete_answer.get("answer") if complete_answer else "".join(answer_parts).strip(),
                        )
                    except Exception as timer_exc:
                        logger.error("FeedbackTimer registration error (v2-stream): %s", timer_exc, exc_info=True)
                    
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

            # Audit evidence — this worker only ever runs hybrid_graphrag.
            get_query_evidence_recorder().record_contextgraph_turn(
                session_id=request.session_id,
                query_text=resolved_query,
                result=ctx_result,
                hybrid=hybrid_payload,
                serving_engine="legacy-stream",
            )

            # Signal completion with metadata for SessionManager registration
            loop.call_soon_threadsafe(queue.put_nowait, ("done", {
                "type": "complete",
                "response_id": response_id,
                "interaction_id": interaction_id,
                "hybrid": hybrid_payload,
                "_register_passive": True,  # Signal to register with SessionManager
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
            
            # Handle passive feedback registration on completion
            if event_type == "done" and event_data.get("_register_passive"):
                try:
                    from app.feedback.session_manager import get_session_manager
                    session_manager = get_session_manager()
                    previous_response = await session_manager.register_response(
                        session_id=request.session_id,
                        response_id=response_id,
                        query_text=request.query,
                    )
                    logger.info(f"SessionManager (stream): Registered response_id={response_id}, previous={previous_response is not None}")
                    if previous_response:
                        await session_manager.mark_detected(request.session_id, previous_response.response_id)
                        history_queries = [
                            h.get("query", "") if isinstance(h, dict) else getattr(h, "query", "")
                            for h in (request.history or [])
                        ]
                        asyncio.create_task(_trigger_follow_up_detection(
                            session_id=request.session_id,
                            previous_response_id=previous_response.response_id,
                            previous_query=previous_response.query_text,
                            follow_up_query=request.query,
                            session_history=[q for q in history_queries if q],
                        ))
                except Exception as sm_exc:
                    logger.warning("SessionManager registration error (stream): %s", sm_exc, exc_info=True)

                # Feedback timer & lifecycle management in data.db
                try:
                    from app.feedback.feedback_timer import get_feedback_timer_manager
                    feedback_timer = get_feedback_timer_manager()
                    await feedback_timer.on_query_submitted(
                        session_id=request.session_id,
                        response_id=response_id,
                        interaction_id=interaction_id,
                        turn_number=turn_index,
                        query_text=request.query,
                        response_text=event_data.get("hybrid", {}).get("answer", {}).get("answer") if event_data.get("hybrid") else None,
                    )
                except Exception as timer_exc:
                    logger.error("FeedbackTimer registration error (legacy-stream): %s", timer_exc, exc_info=True)
                
                # Remove internal flag before yielding to client
                event_data.pop("_register_passive", None)
            
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
        logger.warning("Fast AI title generation fallback: %s", exc)

    return _fast_heuristic_title(query)


@router.post("/title", response_model=ChatTitleResponse)
async def generate_title_endpoint(
    request: ChatTitleRequest,
    container: Container = Depends(get_container),
) -> ChatTitleResponse:
    """Fast, lightweight endpoint to generate a concise 2-5 word conversation title."""
    title = await generate_chat_title(request.query)
    return ChatTitleResponse(title=title, session_id=request.session_id)
