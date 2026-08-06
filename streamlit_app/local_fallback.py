"""
local_fallback.py
====================
Shared "no FastAPI backend reachable" fallback for the Streamlit UI: calls
the local engine (retrieval.py) directly and reshapes the result into the
same dict shapes the FastAPI backend's /api/query/* and /api/chat endpoints
return, so app.py's Compare tab and chat_view.py's Chat tab share one
implementation instead of each inventing (or, in chat_view.py's case,
forgetting to invent) their own local-execution path.

`history` (optional) is a flat [{"role": "user"/"assistant", "content": ...}]
list, threaded straight through to retrieval.py's traditional_rag/
hybrid_graphrag, which fold the last few turns into the synthesis prompt so
follow-ups with pronouns ("is there an exception to that rule?") resolve
correctly instead of being answered as a standalone query. This is a plain
prompt-level injection, not the FastAPI backend's context_memory rewrite —
simpler, but it closes the gap that used to exist here entirely.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import faiss_store
import graph_store
import retrieval

_store: Optional["faiss_store.BrochureFAISSStore"] = None


def _get_store() -> "faiss_store.BrochureFAISSStore":
    global _store
    if _store is None:
        _store = faiss_store.BrochureFAISSStore("amc_master")
    return _store


def local_traditional(query: str, history: List[dict] | None = None,
                       user_role: str | None = None) -> Dict[str, Any]:
    """Shape matches QueryResponse.traditional / ChatResponse.traditional."""
    res = retrieval.traditional_rag(query, _get_store(), history=history, user_role=user_role)
    docs = res.get("docs", [])
    return {
        "files": [{
            "name": d.get("name"),
            "score": d.get("score"),
            "page": d.get("page"),
            "snippet": d.get("snippet"),
            "full_text": d.get("full_text"),
        } for d in docs],
        "snippet": res.get("answer"),
        "metrics": {
            "total_tokens": res.get("total_tokens", 0),
            "telemetry_breakdown": res.get("telemetry_breakdown", {}),
        },
        "latency_ms": int(res.get("total_time", 0) * 1000),
    }


def local_contextgraph(query: str, history: List[dict] | None = None,
                        user_role: str | None = None) -> Dict[str, Any]:
    """Shape matches the contextgraph body of QueryResponse / ChatResponse.hybrid."""
    res = retrieval.hybrid_graphrag(query, _get_store(), history=history, user_role=user_role)
    summary = graph_store.get_entity_type_summary(res.get("active_labels"))
    docs = res.get("docs", [])
    edges = res.get("graph_edges", [])
    edges_used = res.get("graph_edges_used_in_prompt", [])
    return {
        "answer": {
            "answer": res.get("answer") or "No answer generated.",
            "confidence": res.get("confidence_label"),
            "compliance_note": res.get("confidence_label"),
        },
        "sources": [{
            "document_title": d.get("name", ""),
            "document_id": d.get("name", ""),
            "snippet": d.get("snippet"),
        } for d in docs],
        "graph_highlight": {
            "node_names": sorted({str(n) for n in res.get("graph_nodes", [])}),
            "relationships": sorted({e.get("rel") for e in edges if e.get("rel")}),
            "entities": sorted(res.get("matched_entity_texts", []) or []),
            "labels": sorted(res.get("active_labels", []) or []),
            "edges": [{"s": e.get("s"), "rel": e.get("rel"), "o": e.get("o"), "conf": e.get("conf")} for e in edges],
            "edges_used_in_prompt": [{"s": e.get("s"), "rel": e.get("rel"), "o": e.get("o"), "conf": e.get("conf")} for e in edges_used],
            "entity_summary": summary or [],
            "query_type": res.get("query_type"),
            "graph_matched_by": res.get("graph_matched_by"),
            "used_verified_aggregate": res.get("used_verified_aggregate", False),
            "used_comparison_mode": res.get("used_comparison_mode", False),
            "total_tokens": res.get("total_tokens", 0),
            "telemetry_breakdown": res.get("telemetry_breakdown", {}),
        },
        "latency_ms": int(res.get("total_time", 0) * 1000),
    }
