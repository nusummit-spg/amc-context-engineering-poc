"""WS-Phase2 — /chat endpoint: multi-turn conversation on top of the existing
traditional_rag / hybrid_graphrag engine functions.

Coreference resolution (rewriting "why is their limit higher?" into a
self-contained query) and history compression live in app.engine.context_memory.
This route is the only caller of those — engine functions themselves stay
usable standalone (chat_history=None) for the existing /query endpoints.
"""
import asyncio

from fastapi import APIRouter, HTTPException

from app.api.routes.query import _get_store, _traditional_response, _contextgraph_response
from app.engine import context_memory, graph_store, retrieval
from app.schemas.api import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def run_chat(request: ChatRequest) -> ChatResponse:
    """Handles multi-turn conversation memory for both Traditional and Hybrid RAG."""
    store = _get_store()

    resolved_query = request.query
    if request.history:
        try:
            resolved_query = await asyncio.to_thread(
                context_memory.resolve_coreferences, request.query, request.history
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Coreference resolution failed: {exc}")

    turn_index = len(request.history) // 2 + 1  # 2 messages per turn (user, assistant)

    resp = ChatResponse(
        query=request.query,
        resolved_query=resolved_query,
        mode=request.mode,
        history=request.history,
        session_id=request.session_id,
        turn_index=turn_index,
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
        resp.hybrid = {
            "answer": cg_resp.answer.model_dump() if cg_resp.answer else None,
            "sources": [s.model_dump() for s in cg_resp.sources],
            "graph_highlight": cg_resp.graph_highlight,
            "latency_ms": cg_resp.latency_ms,
        }

    return resp
