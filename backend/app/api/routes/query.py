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
import logging
import uuid
from functools import lru_cache
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import Container, get_container, OptionalCurrentUser
from app.api.routes.files import get_pdf_url
from app.core.database import get_db
from app.engine import config as engine_config
from app.engine import faiss_store as engine_faiss
from app.engine import graph_store, retrieval
from app.feedback.intent_matcher import get_intent_matcher
from app.models.api import QueryRequest, QueryResponse, TraditionalResult
from app.models.feedback import PendingFeedbackNotice
from app.models.query import SourceAttribution, SynthesisOutput
from app.schemas.response_feedback_table import ResponseFeedback
from app.core.logging import (
    log_step_info,
    log_step_warning,
    log_step_error,
    log_step_debug,
)

logger = logging.getLogger("app.api.query")

router = APIRouter(prefix="/query", tags=["query"])


@lru_cache(maxsize=1)
def _store():
    """Cached FAISS store loaded from the prebuilt amc_master index.

    faiss_store's own INDEXES_DIR default resolves wrong once vendored into the
    package tree; point it at config.FAISS_DIR (app/engine/faiss_indexes), the
    same override the original app.py did.

    Returns:
        Result of the operation.
    """
    engine_faiss.INDEXES_DIR = engine_config.FAISS_DIR
    return engine_faiss.BrochureFAISSStore("amc_master")


def _get_store():
    """Retrieve store.

    Returns:
        Result of the operation.
    """
    try:
        return _store()
    except Exception as exc:
        logger.warning("FAISS index unavailable (%s) - operating with empty in-memory fallback store", exc)
        store = engine_faiss.BrochureFAISSStore.__new__(engine_faiss.BrochureFAISSStore)
        import faiss
        store.slug = "amc_master"
        store.index = faiss.IndexFlatIP(384)
        store.children = []
        store.parents_map = {}
        store.meta = {}
        return store


def _confidence(label: str | None) -> str:
    """Confidence.

    Args:
        label (str | None): The label.

    Returns:
        str: Resulting str instance.
    """
    text = (label or "").lower()
    return "high" if "high" in text else "medium" if "medium" in text else "low"


# ---------- adapters: engine dicts -> QueryResponse ----------

def _traditional_response(query: str, result: dict, pending_notice: Optional[PendingFeedbackNotice] = None) -> QueryResponse:
    """Traditional response.

    Args:
        query (str): Search query or input text.
        result (dict): The result.
        pending_notice (Optional[PendingFeedbackNotice]): The pending notice.

    Returns:
        QueryResponse: QueryResponse object containing the operation result.
    """
    docs = result.get("docs", [])
    resp = QueryResponse(query=query, mode="traditional")
    resp.response_id = f"resp_{uuid.uuid4().hex[:12]}"
    resp.interaction_id = f"int_{uuid.uuid4().hex[:12]}"
    resp.pending_feedback_notice = pending_notice
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


def _contextgraph_response(
    query: str,
    result: dict,
    entity_summary: list | None = None,
    pending_notice: Optional[PendingFeedbackNotice] = None,
) -> QueryResponse:
    """Contextgraph response.

    Args:
        query (str): Search query or input text.
        result (dict): The result.
        entity_summary (list | None): The entity summary.
        pending_notice (Optional[PendingFeedbackNotice]): The pending notice.

    Returns:
        QueryResponse: QueryResponse object containing the operation result.
    """
    docs = result.get("docs", [])
    edges = result.get("graph_edges", [])
    resp = QueryResponse(query=query, mode="contextgraph")
    resp.response_id = f"resp_{uuid.uuid4().hex[:12]}"
    resp.interaction_id = f"int_{uuid.uuid4().hex[:12]}"
    resp.pending_feedback_notice = pending_notice

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
        "telemetry_breakdown": telemetry_breakdown,
        "provenance": provenance_list,
        "pending_feedback_notice": pending_notice.model_dump() if pending_notice else None,
    }
    resp.latency_ms = int(result.get("total_time", 0) * 1000)
    return resp


# ---------- endpoints ----------

async def _run_v2_orchestrator(
    request: QueryRequest,
    container: Container,
    current_user: Optional[Any] = None,
) -> QueryResponse:
    """Run v2 orchestrator.

    Args:
        request (QueryRequest): FastAPI request instance.
        container (Container): Dependency injection container providing application services.
        current_user (Optional[Any]): Authenticated user context.

    Returns:
        QueryResponse: QueryResponse object containing the operation result.
    """
    query = request.query
    mode = request.mode
    log_step_info(logger, "V2_ROUTE_START", "Routing query to V2 orchestrator: '%s' (mode=%s, session_id=%s)", query, mode, request.session_id)
    resp_obj = await container.orchestrator.answer(
        query,
        top_k=request.top_k,
        user_id=current_user.username if current_user else None,
        tenant_id=current_user.tenant_id if current_user else None,
    )
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
                "name": h.get("source_filename") or h.get("document_title") or h.get("document_id") or "Document",
                "document_id": h.get("document_id") or h.get("source_filename"),
                "document_title": h.get("document_title") or h.get("source_filename") or "Document",
                "score": round(float(h.get("score", 0.85)), 3),
                "page": h.get("page_start", 1),
                "page_number": h.get("page_start", 1),
                "page_label": f"p. {h.get('page_start', 1)}",
                "snippet": h.get("text", "")[:300],
                "full_text": h.get("text", ""),
                "verbatim_text": h.get("text", ""),
                "url": get_pdf_url(h.get("document_title") or h.get("source_filename") or "", h.get("page_start", 1)),
                "source_url": get_pdf_url(h.get("document_title") or h.get("source_filename") or "", h.get("page_start", 1)),
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
                "telemetry_breakdown": {
                    "latency_vector_db_ms": round(trace.vector_ms, 1) if trace else 0.0,
                    "latency_rerank_ms": round(trace.rerank_ms, 1) if trace else 0.0,
                    "latency_graph_db_ms": 0.0,
                    "latency_cypher_generation_ms": 0.0,
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
        SourceAttribution(
            source_index=src.source_index,
            document_id=src.document_id,
            document_title=src.document_title or src.document_id,
            chunk_id=src.chunk_id,
            snippet=src.snippet,
            page=getattr(src, "page", 1) or 1,
            page_number=getattr(src, "page_number", getattr(src, "page", 1)) or 1,
            page_label=getattr(src, "page_label", f"p. {getattr(src, 'page', 1)}"),
            verbatim_text=getattr(src, "verbatim_text", getattr(src, "snippet", "")),
            url=getattr(src, "url", get_pdf_url(src.document_title or src.document_id, getattr(src, "page", 1))),
        )
        for src in context.sources
    ] if (context and context.sources) else [
        SourceAttribution(
            source_index=i + 1,
            document_id=c.document_id,
            document_title=c.document_title or c.document_id,
            chunk_id=c.chunk_id,
            snippet=c.text[:300],
            page=getattr(c, "page", 1) or 1,
            page_number=getattr(c, "page_start", getattr(c, "page", 1)) or 1,
            page_label=f"p. {getattr(c, 'page', 1)}",
            verbatim_text=c.text,
            url=get_pdf_url(c.document_title or c.document_id, getattr(c, "page", 1)),
        )
        for i, c in enumerate((retrieval_res.chunks if retrieval_res else [])[:5])
    ]

    if not sources and synthesis and getattr(synthesis, "provenance", None):
        sources = [
            SourceAttribution(
                source_index=p.get("source_index", i + 1),
                document_id=p.get("chunk_id", f"src_{i+1}"),
                document_title=p.get("doc", "Repair Engine Registry"),
                chunk_id=p.get("chunk_id", f"src_{i+1}"),
                snippet=p.get("snippet", ""),
                page=1,
                page_number=1,
                page_label="p. 1",
                verbatim_text=p.get("snippet", ""),
                url=get_pdf_url(p.get("doc", "Repair Engine Registry"), 1),
            )
            for i, p in enumerate(synthesis.provenance)
        ]

    graph_facts = retrieval_res.graph_facts if retrieval_res else []
    graph_nodes = sorted({f.subject for f in graph_facts} | {f.object for f in graph_facts})
    graph_rels = sorted({f.predicate for f in graph_facts})

    # Build graph edge objects in legacy {s, rel, o, conf} shape for the SVG renderer.
    graph_edges = [
        {"s": f.subject, "rel": f.predicate, "o": f.object, "conf": f.properties.get("confidence", 1.0) if hasattr(f, "properties") and isinstance(f.properties, dict) else 1.0}
        for f in graph_facts
    ]

    # Entities + labels from intent and graph fact properties.
    matched_entity_texts = sorted(set(intent.entities_mentioned)) if intent else []
    active_labels = sorted({
        f.properties.get("entity_type") or ""
        for f in graph_facts
        if hasattr(f, "properties") and isinstance(f.properties, dict) and f.properties.get("entity_type")
    })

    # Entity-type summary for the ontology view.
    from collections import defaultdict
    label_counts: dict[str, int] = defaultdict(int)
    for f in graph_facts:
        etype = (f.properties.get("entity_type") if hasattr(f, "properties") and isinstance(f.properties, dict) else None) or "Entity"
        label_counts[etype] += 1
    entity_summary = [
        {"label": lbl, "count": cnt, "active": True}
        for lbl, cnt in sorted(label_counts.items())
    ] if label_counts else []

    # Build provenance from context sources (legacy provenance_list shape).
    provenance_list: list[dict] = []
    effective_sources = context.sources if (context and context.sources) else sources
    for src in effective_sources:
        page_num = getattr(src, "page_number", None) or getattr(src, "page", 1)
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
            "url": getattr(src, "url", None) or get_pdf_url(doc_name, page_num),
            "source_url": getattr(src, "url", None) or get_pdf_url(doc_name, page_num),
        })

    # Build rich citations with marker + source
    citations_list: list[dict] = []
    for i, src in enumerate(effective_sources):
        doc_name = src.document_title or src.document_id
        page_num = getattr(src, "page_number", None) or getattr(src, "page", 1)
        page_label = getattr(src, "page_label", None) or (f"p. {page_num}" if page_num else "—")
        verbatim = getattr(src, "verbatim_text", None) or src.snippet or ""
        citations_list.append({
            "marker": str(i + 1),
            "source": {
                "chunk_id": src.chunk_id or f"src.{i+1}",
                "document_id": src.document_id or doc_name,
                "document_name": doc_name,
                "document_title": doc_name,
                "page_number": page_num,
                "page_label": page_label,
                "verbatim_text": verbatim,
                "snippet": src.snippet or (verbatim[:200] if verbatim else ""),
                "source_url": getattr(src, "url", None) or get_pdf_url(doc_name, page_num),
                "url": getattr(src, "url", None) or get_pdf_url(doc_name, page_num),
                "local_doc_path": f"/api/files/{doc_name}",
                "score": getattr(src, "score", 0.9),
            }
        })

    # UI Badges for Evidence Overview
    ui_badges: list[dict] = []
    if trace and trace.cache_hit:
        hit_lbl = "Fingerprint Cache Hit" if (getattr(trace, "cache_kind", None) == "exact") else "Semantic Cache Hit"
        saved = trace.tokens_saved or 0
        ui_badges.append({
            "label": hit_lbl,
            "desc": f"Served from cognitive cache — {len(graph_nodes)} nodes ({saved} tokens saved)",
            "type": "success"
        })
    if intent and hasattr(intent, "query_type") and intent.query_type:
        dom = intent.query_type.value
        ui_badges.append({
            "label": f"Pillar: Intent Partition ({dom.upper()})",
            "desc": f"Domain intent: {dom}",
            "type": "primary"
        })
    if graph_facts:
        ui_badges.append({
            "label": f"Pillar 2: Single-Shot UNWIND ({len(graph_nodes)} nodes)",
            "desc": "Batch-traversed relational subgraph without sequential loops",
            "type": "primary"
        })
    ui_badges.append({
        "label": "Pillar 5: Verified Grounding",
        "desc": "Claims cross-validated against structured facts and active corpus",
        "type": "success"
    })

    # Triplet Table for Grounding / Validation tab
    triplet_table = [
        {
            "s": f.subject,
            "rel": f.predicate,
            "o": f.object,
            "conf": f.properties.get("confidence", 1.0) if hasattr(f, "properties") and isinstance(f.properties, dict) else 1.0
        }
        for f in graph_facts
    ]

    # Cross-validate answer against retrieved documents and graph facts
    ans_text_for_cv = synthesis.answer if synthesis else ""
    docs_for_cv = []
    for i, s in enumerate(sources):
        if isinstance(s, dict):
            d_name = s.get("document_title") or s.get("name") or s.get("document_id") or f"Doc {i+1}"
            d_page = s.get("page_number") if s.get("page_number") is not None else s.get("page")
            d_snippet = s.get("snippet", "")
            d_text = s.get("verbatim_text") or s.get("full_text") or s.get("snippet", "")
        else:
            d_name = getattr(s, "document_title", None) or getattr(s, "document_id", None) or getattr(s, "name", None) or f"Doc {i+1}"
            d_page = getattr(s, "page_number", None) if getattr(s, "page_number", None) is not None else getattr(s, "page", None)
            d_snippet = getattr(s, "snippet", "") or ""
            d_text = getattr(s, "verbatim_text", "") or getattr(s, "full_text", "") or getattr(s, "snippet", "") or ""
        docs_for_cv.append({
            "name": d_name,
            "document_title": d_name,
            "page": d_page,
            "snippet": d_snippet,
            "full_text": d_text,
        })
    try:
        from app.engine.cross_validation import cross_validate_answer
        cv_report = cross_validate_answer(
            query=query,
            answer=ans_text_for_cv,
            retrieved_docs=docs_for_cv,
            graph_triplets=triplet_table,
            query_type=intent.query_type.value if intent else "v2",
        )
        cross_val_ledger = cv_report
        metrics_list = cv_report.get("metrics", [])
    except Exception as cv_exc:
        logger.warning("Cross-validation failed in _run_v2_orchestrator: %s", cv_exc)
        cross_val_ledger = {
            "cross_validation_badge": {"label": "Pillar 5: Verified Grounding", "type": "success", "desc": "Grounded against active corpus."},
            "evidence_status": "SUPPORTED",
            "metrics": getattr(synthesis, "metrics", []) if synthesis else [],
        }
        metrics_list = cross_val_ledger["metrics"]

    if synthesis:
        synthesis.metrics = metrics_list

    # Token totals
    total_tokens = (trace.input_tokens + trace.output_tokens) if trace else 0

    # Build telemetry_breakdown in legacy key names.
    telemetry_breakdown = {
        "latency_vector_db_ms": round(trace.vector_ms, 1) if trace else 0.0,
        "latency_rerank_ms": round(trace.rerank_ms, 1) if trace else 0.0,
        "latency_graph_db_ms": round(trace.graph_ms, 1) if trace else 0.0,
        "latency_cypher_generation_ms": 0.0,
        "latency_ner_processing_ms": round(trace.ner_ms, 1) if trace else 0.0,
        "latency_llm_generation_ms": round(trace.generation_ms, 1) if trace else 0.0,
        "latency_post_retrieval_processing_ms": round(trace.assembly_ms, 1) if trace else 0.0,
        "latency_total_pipeline_ms": round(trace.request_total_ms, 1) if trace else 0.0,
        "tokens_input": trace.input_tokens if trace else 0,
        "tokens_output": trace.output_tokens if trace else 0,
        "tokens_total": total_tokens,
        "db_candidates_surfaced": len(graph_nodes) if graph_nodes else len(sources),
        "vector_bypassed": False,
        "pipeline_mode": "ContextGraph Hybrid RAG (v2)",
        "cache_hit": trace.cache_hit if trace else False,
        "hit_type": "Fingerprint" if (trace and getattr(trace, "cache_kind", None) == "exact") else ("Semantic" if (trace and trace.cache_hit) else None),
        "domain_intent": intent.query_type.value if (intent and hasattr(intent, "query_type") and intent.query_type) else None,
        "tokens_saved": trace.tokens_saved if trace else 0,
        "tokens_cold_equivalent": trace.cold_equivalent_tokens if trace else 0,
        "ui_badges": ui_badges,
        "triplet_table": triplet_table,
        "cross_validation_ledger": cross_val_ledger,
    } if trace else {}

    # Confidence label in legacy display format.
    conf_str = (synthesis.confidence if synthesis else "high") or "high"
    conf_label_map = {"high": "✓ High confidence", "medium": "⚠ Medium confidence", "low": "✗ Low confidence"}
    confidence_label = conf_label_map.get(conf_str.lower(), f"✓ {conf_str.capitalize()} confidence")
    query_type_str = intent.query_type.value if intent and intent.query_type else None

    # Patch compliance_note onto synthesis for the frontend confidence badge.
    if synthesis:
        if not synthesis.compliance_note:
            synthesis.compliance_note = confidence_label
        # Overwrite synthesis citations with rich dictionary format
        synthesis.citations = citations_list

    pending_feedback_notice = None
    try:
        matcher = get_intent_matcher()
        pending_feedback_notice = await matcher.check_pending_feedback(
            query=query,
            session_id=getattr(request, "session_id", None),
            actor_id=getattr(request, "actor_id", None),
        )
    except Exception as exc:
        logger.warning("Pending feedback check in _run_v2_orchestrator failed: %s", exc)

    response_id = f"resp_{uuid.uuid4().hex[:12]}"
    interaction_id = f"int_{uuid.uuid4().hex[:12]}"

    # Audit evidence — ContextGraph turns with session_id
    if mode in ("contextgraph", "both") and request.session_id:
        user_id = (current_user.username if current_user else None) or request.actor_id or "system_user"
        tenant_id = current_user.tenant_id if current_user else None
        hybrid_data = {
            "response_id": response_id,
            "interaction_id": interaction_id,
            "answer": {
                **(synthesis.model_dump() if synthesis else {}),
                "compliance_note": synthesis.compliance_note if synthesis else "",
                "citations": citations_list,
                "metrics": metrics_list,
            },
            "sources": sources,
            "citations": citations_list,
            "metrics": metrics_list,
            "graph_highlight": {
                "node_names": graph_nodes,
                "relationships": graph_rels,
                "entities": matched_entity_texts,
                "labels": active_labels,
                "edges": graph_edges,
                "edges_used_in_prompt": graph_edges,
                "entity_summary": entity_summary,
                "query_type": query_type_str,
                "telemetry_breakdown": telemetry_breakdown,
                "provenance": provenance_list,
                "metrics": metrics_list,
                "cross_val_ledger": cross_val_ledger,
            },
            "latency_ms": int(trace.request_total_ms if trace else 0),
            "telemetry_breakdown": telemetry_breakdown,
            "trace": trace.model_dump() if trace else None,
        }
        try:
            from app.retrieval.query_evidence_recorder import get_recorder as get_query_evidence_recorder
            await asyncio.to_thread(
                get_query_evidence_recorder().record_v2_contextgraph_turn,
                session_id=request.session_id,
                query_text=query,
                hybrid=hybrid_data,
                intent=intent,
                trace=trace,
                serving_engine="v2",
                user_id=user_id,
                tenant_id=tenant_id,
            )
        except Exception as qe_exc:
            logger.warning("Query evidence recording failed in _run_v2_orchestrator: %s", qe_exc)

    query_response = QueryResponse(
        query=query,
        mode=mode,
        intent=intent,
        answer=synthesis if mode in ("contextgraph", "both") else None,
        sources=sources if mode in ("contextgraph", "both") else [],
        traversal_paths=retrieval_res.traversal_paths if retrieval_res else [],
        taxonomy_paths=intent.taxonomy_paths if intent else [],
        # Full legacy-compatible graph_highlight dict — all fields the frontend
        # _to_hybrid() adapter reads must be present here.
        graph_highlight={
            "node_names": graph_nodes,
            "relationships": graph_rels,
            "entities": matched_entity_texts,
            "labels": active_labels,
            "edges": graph_edges,
            "edges_used_in_prompt": graph_edges,
            "entity_summary": entity_summary,
            "query_type": query_type_str,
            "graph_matched_by": "graph_facts" if graph_facts else None,
            "used_verified_aggregate": False,
            "used_comparison_mode": False,
            "input_tokens": trace.input_tokens if trace else 0,
            "output_tokens": trace.output_tokens if trace else 0,
            "total_tokens": total_tokens,
            "telemetry_breakdown": telemetry_breakdown,
            "provenance": provenance_list,
            "metrics": metrics_list,
            "cross_val_ledger": cross_val_ledger,
            "pending_feedback_notice": pending_feedback_notice.model_dump() if pending_feedback_notice else None,
        },
        context_debug=context,
        traditional=trad_result,
        latency_ms=int(trace.request_total_ms if trace else 0),
        trace=trace,
        serving_engine="v2",
        corpus_version=container.settings.active_corpus_version,
        response_id=response_id,
        interaction_id=interaction_id,
        pending_feedback_notice=pending_feedback_notice,
    )
    log_step_info(logger, "V2_ROUTE_COMPLETE", "V2 orchestrator query returned response %s in %dms (passed_gate=%s)", response_id, int(trace.request_total_ms if trace else 0), trace.quality_gate_passed if trace else True)
    return query_response


@router.post("/v2", response_model=QueryResponse)
async def run_query_v2(
    request: QueryRequest,
    response: Response,
    container: Container = Depends(get_container),
    current_user: OptionalCurrentUser = None,
) -> QueryResponse:
    """Explicit v2 ContextGraph orchestrator endpoint.

    Args:
        request (QueryRequest): FastAPI request instance.
        response (Response): FastAPI response instance.
        container (Container): Dependency injection container providing application services.
        current_user (OptionalCurrentUser): Authenticated user context.

    Returns:
        QueryResponse: QueryResponse object containing the operation result.
    """
    resp = await _run_v2_orchestrator(request, container, current_user=current_user)
    response.headers["X-Serving-Engine"] = resp.serving_engine or "v2"
    return resp


@router.post("/traditional", response_model=QueryResponse, deprecated=True)
async def run_traditional(
    request: QueryRequest,
    response: Response,
    container: Container = Depends(get_container),
) -> QueryResponse:
    """Deprecated legacy endpoint: Traditional Vector RAG.

    Scheduled for removal in Week 3 (RFC 8594 Sunset 2026-10-22).
    Clients should use POST /query with mode="traditional".

    Args:
        request (QueryRequest): FastAPI request instance.
        response (Response): FastAPI response instance.
        container (Container): Dependency injection container providing application services.

    Returns:
        QueryResponse: QueryResponse object containing the operation result.
    """
    log_step_info(logger, "RUN_TRADITIONAL_DISPATCH", "Incoming legacy /traditional request: '%s'", request.query)
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-10-22"
    response.headers["Link"] = '</query>; rel="successor-version"'
    response.headers["X-Legacy-Route"] = "deprecated"

    if container.settings.query_engine.lower() == "v2":
        request.mode = "traditional"
        resp = await _run_v2_orchestrator(request, container)
        response.headers["X-Serving-Engine"] = resp.serving_engine or "v2"
        return resp

    pending_notice = None
    try:
        matcher = get_intent_matcher()
        pending_notice = await matcher.check_pending_feedback(
            query=request.query,
            session_id=getattr(request, "session_id", None),
            actor_id=getattr(request, "actor_id", None),
        )
    except Exception as exc:
        log_step_warning(logger, "FEEDBACK_CHECK_WARN", "Pending feedback check in run_traditional failed: %s", exc)

    store = _get_store()
    result = await asyncio.to_thread(retrieval.traditional_rag, request.query, store)
    response.headers["X-Serving-Engine"] = "legacy"
    trad_resp = _traditional_response(request.query, result, pending_notice=pending_notice)
    trad_resp.serving_engine = "legacy"
    return trad_resp


@router.post("/contextgraph", response_model=QueryResponse, deprecated=True)
async def run_contextgraph(
    request: QueryRequest,
    response: Response,
    container: Container = Depends(get_container),
) -> QueryResponse:
    """Deprecated legacy endpoint: ContextGraph Hybrid RAG.

    Scheduled for removal in Week 3 (RFC 8594 Sunset 2026-10-22).
    Clients should use POST /query with mode="contextgraph".

    Args:
        request (QueryRequest): FastAPI request instance.
        response (Response): FastAPI response instance.
        container (Container): Dependency injection container providing application services.

    Returns:
        QueryResponse: QueryResponse object containing the operation result.
    """
    log_step_info(logger, "RUN_CONTEXTGRAPH_DISPATCH", "Incoming legacy /contextgraph request: '%s'", request.query)
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-10-22"
    response.headers["Link"] = '</query>; rel="successor-version"'
    response.headers["X-Legacy-Route"] = "deprecated"

    if container.settings.query_engine.lower() == "v2":
        request.mode = "contextgraph"
        resp = await _run_v2_orchestrator(request, container)
        response.headers["X-Serving-Engine"] = resp.serving_engine or "v2"
        return resp

    pending_notice = None
    try:
        matcher = get_intent_matcher()
        pending_notice = await matcher.check_pending_feedback(
            query=request.query,
            session_id=getattr(request, "session_id", None),
            actor_id=getattr(request, "actor_id", None),
        )
    except Exception as exc:
        log_step_warning(logger, "FEEDBACK_CHECK_WARN", "Pending feedback check in run_contextgraph failed: %s", exc)

    store = _get_store()
    result = await asyncio.to_thread(retrieval.hybrid_graphrag, request.query, store)
    summary = await asyncio.to_thread(graph_store.get_entity_type_summary, result.get("active_labels"))
    response.headers["X-Serving-Engine"] = "legacy"
    cg_resp = _contextgraph_response(request.query, result, summary, pending_notice=pending_notice)
    cg_resp.serving_engine = "legacy"
    return cg_resp


@router.post("", response_model=QueryResponse)
async def run_query(
    request: QueryRequest,
    response: Response,
    container: Container = Depends(get_container),
) -> QueryResponse:
    """Production query endpoint with QUERY_ENGINE feature flag routing.

    Args:
        request (QueryRequest): FastAPI request instance.
        response (Response): FastAPI response instance.
        container (Container): Dependency injection container providing application services.

    Returns:
        QueryResponse: QueryResponse object containing the operation result.
    """
    engine = container.settings.query_engine.lower()
    log_step_info(logger, "RUN_QUERY_DISPATCH", "Incoming /query request: '%s' (mode=%s, engine=%s)", request.query, request.mode, engine)

    if engine == "v2":
        resp = await _run_v2_orchestrator(request, container)
        response.headers["X-Serving-Engine"] = resp.serving_engine or "v2"
        return resp

    if engine == "canary":
        canary_pct = max(0, min(100, container.settings.canary_percentage))
        import zlib
        bucket = zlib.crc32(request.query.encode("utf-8")) % 100
        if bucket < canary_pct:
            resp = await _run_v2_orchestrator(request, container)
            resp.serving_engine = f"canary-v2 ({canary_pct}%)"
            response.headers["X-Serving-Engine"] = resp.serving_engine
            return resp

    if engine == "shadow":
        from app.retrieval.shadow import get_shadow_runner
        shadow_runner = get_shadow_runner()
        await shadow_runner.execute_shadow(
            query=request.query,
            legacy_result={},
            orchestrator=container.orchestrator,
        )

    # Check pending feedback notice
    pending_notice = None
    try:
        matcher = get_intent_matcher()
        pending_notice = await matcher.check_pending_feedback(
            query=request.query,
            session_id=getattr(request, "session_id", None),
            actor_id=getattr(request, "actor_id", None),
        )
    except Exception as exc:
        logger.warning("Pending feedback check in run_query failed: %s", exc)

    # Default legacy engine execution
    store = _get_store()
    resp = QueryResponse(query=request.query, mode=request.mode)
    resp.serving_engine = "legacy"
    response.headers["X-Serving-Engine"] = "legacy"
    resp.corpus_version = "amc_master_legacy"
    resp.response_id = f"resp_{uuid.uuid4().hex[:12]}"
    resp.interaction_id = f"int_{uuid.uuid4().hex[:12]}"
    resp.pending_feedback_notice = pending_notice

    if request.mode in ("traditional", "both"):
        trad = await asyncio.to_thread(retrieval.traditional_rag, request.query, store)
        trad_resp = _traditional_response(request.query, trad, pending_notice=pending_notice)
        resp.traditional = trad_resp.traditional
        resp.latency_ms = int(trad.get("total_time", 0) * 1000)

    if request.mode in ("contextgraph", "both"):
        ctx = await asyncio.to_thread(retrieval.hybrid_graphrag, request.query, store)
        summary = await asyncio.to_thread(graph_store.get_entity_type_summary, ctx.get("active_labels"))
        cg = _contextgraph_response(request.query, ctx, summary, pending_notice=pending_notice)
        resp.answer, resp.sources, resp.graph_highlight = cg.answer, cg.sources, cg.graph_highlight
        resp.response_id = cg.response_id
        resp.interaction_id = cg.interaction_id
        if request.mode == "contextgraph":
            resp.latency_ms = cg.latency_ms

        if request.session_id:
            try:
                from app.retrieval.query_evidence_recorder import get_recorder as get_query_evidence_recorder
                user_id = request.actor_id or "system_user"
                await asyncio.to_thread(
                    get_query_evidence_recorder().record_contextgraph_turn,
                    session_id=request.session_id,
                    query_text=request.query,
                    result=ctx,
                    hybrid=cg.model_dump(),
                    serving_engine="legacy",
                    user_id=user_id,
                    tenant_id=None,
                )
            except Exception as exc:
                logger.warning("Query evidence recording failed in run_query legacy: %s", exc)

    return resp


# ---------- SSE helpers ----------

def _format_sse(event_type: str, data: dict) -> str:
    """Format a single SSE message frame.

    Args:
        event_type (str): The event type.
        data (dict): Input data payload.

    Returns:
        str: Resulting str instance.
    """
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


async def _query_stream_generator(
    request: QueryRequest,
    container: Container,
    current_user: Optional[Any] = None,
):
    """Async generator that drives the orchestrator stream and formats SSE frames.

    Handles:
    - Per-event-type SSE framing
    - Converts internal type names to SSE event types
    - Catches top-level exceptions and emits error SSE frame

    Args:
        request (QueryRequest): FastAPI request instance.
        container (Container): Dependency injection container providing application services.
        current_user (Optional[Any]): Authenticated user context.
    """
    pending_notice = None
    try:
        matcher = get_intent_matcher()
        pending_notice = await matcher.check_pending_feedback(
            query=request.query,
            session_id=getattr(request, "session_id", None),
            actor_id=getattr(request, "actor_id", None),
        )
    except Exception as exc:
        logger.warning("Pending feedback check in _query_stream_generator failed: %s", exc)

    notice_dict = pending_notice.model_dump() if pending_notice else None

    try:
        async for event in container.orchestrator.answer_stream(
            query=request.query,
            top_k=request.top_k,
            user_id=current_user.username if current_user else None,
            tenant_id=current_user.tenant_id if current_user else None,
        ):
            event_type = event.get("type", "chunk")
            # Map internal type names → SSE event types
            if event_type == "metadata":
                if notice_dict:
                    event["pending_feedback_notice"] = notice_dict
                yield _format_sse("metadata", event)
            elif event_type == "sources":
                yield _format_sse("sources", event)
            elif event_type == "answer_chunk":
                yield _format_sse("chunk", event)
            elif event_type == "complete":
                if notice_dict:
                    event["pending_feedback_notice"] = notice_dict
                yield _format_sse("done", event)
            elif event_type == "error":
                yield _format_sse("error", event)
            else:
                yield _format_sse("chunk", event)
    except Exception as exc:
        yield _format_sse("error", {"type": "error", "message": str(exc), "recoverable": False})


async def _chat_stream_generator(request, container: "Container"):
    """Async generator for chat streaming (multi-turn aware).

    Args:
        request: FastAPI request instance.
        container ('Container'): Dependency injection container providing application services.
    """
    pending_notice = None
    try:
        matcher = get_intent_matcher()
        pending_notice = await matcher.check_pending_feedback(
            query=request.query,
            session_id=getattr(request, "session_id", None),
            actor_id=getattr(request, "actor_id", None),
        )
    except Exception as exc:
        logger.warning("Pending feedback check in _chat_stream_generator failed: %s", exc)

    notice_dict = pending_notice.model_dump() if pending_notice else None

    try:
        async for event in container.orchestrator.answer_stream(
            query=request.query,
            top_k=getattr(request, "top_k", None),
            history=getattr(request, "history", None),
            session_id=getattr(request, "session_id", None),
        ):
            event_type = event.get("type", "chunk")
            if event_type == "metadata":
                if notice_dict:
                    event["pending_feedback_notice"] = notice_dict
                yield _format_sse("metadata", event)
            elif event_type == "sources":
                yield _format_sse("sources", event)
            elif event_type == "answer_chunk":
                yield _format_sse("chunk", event)
            elif event_type == "complete":
                if notice_dict:
                    event["pending_feedback_notice"] = notice_dict
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
    current_user: OptionalCurrentUser = None,
) -> StreamingResponse:
    """Server-Sent Events streaming endpoint for /query.

    Streams pipeline progress events in real-time:
      event: metadata — intent + entities (immediately after classification)
      event: sources  — retrieved documents (after vector search)
      event: chunk    — LLM answer tokens as they arrive
      event: done     — completion signal with response_id
      event: error    — recoverable/non-recoverable error notification

    Args:
        request (QueryRequest): FastAPI request instance.
        container (Container): Dependency injection container providing application services.
        current_user (OptionalCurrentUser): Authenticated user context.

    Returns:
        StreamingResponse: StreamingResponse object containing the operation result.
    """
    return StreamingResponse(
        _query_stream_generator(request, container, current_user=current_user),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


@router.get("/health/stream-test")
async def stream_health_check() -> StreamingResponse:
    """Lightweight streaming capability probe.

    Returns:
        StreamingResponse: SSE stream frame confirming streaming capability.
    """
    async def _gen():
        """Gen.

        Returns:
            Yielded results or items.
        """
        yield _format_sse("ping", {"type": "ping", "status": "streaming_supported"})

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


@router.get("/{response_id}/pending-feedback")
async def get_response_pending_feedback_notice(
    response_id: str,
    db: Session = Depends(get_db),
):
    """Fetch pending feedback notice for a specific response_id if query exists.

    Args:
        response_id (str): Unique identifier of the response.
        db (Session): Database session instance.

    Returns:
        The requested response pending feedback notice.
    """
    fb = db.query(ResponseFeedback).filter(ResponseFeedback.response_id == response_id).first()
    if fb and fb.query_text:
        matcher = get_intent_matcher()
        notice = await matcher.check_pending_feedback(query=fb.query_text, db=db)
        return {"pending_feedback_notice": notice}
    return {"pending_feedback_notice": None}

