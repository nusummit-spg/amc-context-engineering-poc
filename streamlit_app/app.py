"""Streamlit UI.

Query serving is a thin HTTP client over the FastAPI backend (POST
/api/query/traditional, /api/query/contextgraph) — no ML libs (torch, faiss,
gliner, sentence-transformers) load in this container; all retrieval runs in
the API. That's what keeps API + Streamlit running together on the same box
without OOMing (they'd otherwise each load their own copy of every model).

The Analytics tab's graph explorer (analytics_view.py) is the one exception:
it does its own direct, lightweight Neo4j reads via graph_store.py — that
module has no ML dependencies (just the `neo4j` driver), so giving Streamlit
its own connection for live graph browsing doesn't reintroduce the memory
problem, and avoids having to invent proxy endpoints for read-only graph
exploration that isn't tied to any single query response.
"""
import concurrent.futures
import os

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

from compare_view import render_traditional_panel, render_contextgraph_panel

API_BASE = os.environ.get("API_BASE", "http://api:8000")

CUSTOM_CSS = """
<style>
/* Base App Layout & Background */
.stApp { background-color: #F8F7F3; background-image: radial-gradient(#E5E0D8 1px, transparent 0); background-size: 24px 24px; }
header { background-color: transparent !important; }

/* Tabs Layout */
.stTabs [data-baseweb="tab-list"] { gap: 24px; }
.stTabs [data-baseweb="tab"] { padding-top: 1rem; padding-bottom: 0.5rem; color: #8A8378; font-weight: 600; }
.stTabs [aria-selected="true"] { color: #A8412C !important; border-bottom-color: #A8412C !important; }

/* Text Inputs */
.stTextInput input { background-color: #EFEAE0 !important; border: 1px solid #E7E1D4 !important; border-radius: 8px !important; color: #5C574C !important; }
.stTextInput input:focus { border-color: #A8412C !important; box-shadow: 0 0 0 1px #A8412C !important; }

/* ── BUTTONS STYLED EXACTLY LIKE DISPLAY BOXES (2D FLAT) ── */
.stButton > button {
    border-radius: 8px !important;
    box-shadow: none !important;
    padding: 0.6rem 1.2rem !important;
}

/* Example Buttons / Secondary Buttons */
.stButton > button[kind="secondary"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E7E1D4 !important;
    color: #5C574C !important;
    font-weight: 600;
    transition: all 0.2s ease;
}
.stButton > button[kind="secondary"]:hover {
    border-color: #A8412C !important;
    color: #A8412C !important;
    background-color: #F8F7F3 !important;
}

/* Action Button / Primary Button */
.stButton > button[kind="primary"] {
    background-color: #A8412C !important;
    color: white !important;
    border: 1px solid #8C3523 !important;
    font-weight: 600;
}
.stButton > button[kind="primary"]:hover {
    background-color: #8C3523 !important;
    border-color: #6A281A !important;
    color: white !important;
}

/* Metrics Styling */
[data-testid="stMetricValue"] { color: #231F1C; }
[data-testid="stMetricLabel"] { color: #8A8378; }

/* ── CUSTOM THEMED LOADERS (st.info / st.spinner) ── */
div[data-testid="stAlert"] {
    background-color: #EFEAE0 !important;
    border: 1px solid #E7E1D4 !important;
    border-radius: 12px !important;
    color: #5C574C !important;
}
div[data-testid="stAlert"] svg {
    color: #A8412C !important;
    fill: #A8412C !important;
}

/* Fix the bottom white space edge case */
footer { visibility: hidden; display: none; }
.block-container { padding-bottom: 2rem !important; }
</style>
"""


# ── API client + adapters (QueryResponse JSON -> the dict shape compare_view.py
#    and analytics_view.py expect — matching the engine's own retrieval.py
#    output field-for-field, so those rendering modules need no changes) ──

def _local_api(path: str, query: str) -> dict:
    import retrieval
    import faiss_store
    import graph_store
    if not hasattr(_local_api, "store"):
        _local_api.store = faiss_store.BrochureFAISSStore("amc_master")
    store = _local_api.store

    if path == "/api/query/traditional":
        res = retrieval.traditional_rag(query, store)
        docs = res.get("docs", [])
        return {
            "query": query,
            "mode": "traditional",
            "traditional": {
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
                }
            },
            "latency_ms": int(res.get("total_time", 0) * 1000)
        }
    else:  # /api/query/contextgraph
        res = retrieval.hybrid_graphrag(query, store)
        summary = graph_store.get_entity_type_summary(res.get("active_labels"))
        docs = res.get("docs", [])
        edges = res.get("graph_edges", [])
        edges_used = res.get("graph_edges_used_in_prompt", [])
        return {
            "query": query,
            "mode": "contextgraph",
            "answer": {
                "answer": res.get("answer") or "No answer generated.",
                "confidence": res.get("confidence_label"),
                "compliance_note": res.get("confidence_label"),
            },
            "sources": [{
                "document_title": d.get("name", ""),
                "document_id": d.get("name", ""),
                "snippet": d.get("snippet")
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
            },
            "latency_ms": int(res.get("total_time", 0) * 1000)
        }


def _api(path: str, query: str) -> dict:
    if API_BASE.lower() in ("local", "embedded"):
        return _local_api(path, query)
    try:
        r = requests.post(f"{API_BASE}{path}", json={"query": query}, timeout=240)
        r.raise_for_status()
        return r.json()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        if API_BASE == "http://api:8000":
            # Transparent fallback to direct local execution when running outside Docker on Windows
            return _local_api(path, query)
        raise exc


def _to_traditional(resp: dict) -> dict:
    t = resp.get("traditional") or {}
    m = t.get("metrics") or {}
    return {
        "answer": t.get("snippet") or "",
        "docs": [{
            "name": f.get("name"),
            "score": f.get("score") or 0,
            "page": f.get("page"),
            "snippet": f.get("snippet") or "",
            "full_text": f.get("full_text") or "",
        } for f in t.get("files", [])],
        "total_tokens": m.get("total_tokens", 0),
        "total_time": (resp.get("latency_ms") or 0) / 1000,
    }


def _to_hybrid(resp: dict) -> dict:
    ans = resp.get("answer") or {}
    gh = resp.get("graph_highlight") or {}
    return {
        "answer": ans.get("answer") or "",
        "query_type": gh.get("query_type"),
        "confidence_label": ans.get("compliance_note") or ans.get("confidence") or "",
        "docs": [{"name": s.get("document_title") or s.get("document_id"),
                  "snippet": s.get("snippet")} for s in resp.get("sources", [])],
        "graph_nodes": gh.get("node_names", []),
        "graph_edges": gh.get("edges", []),
        "graph_edges_used_in_prompt": gh.get("edges_used_in_prompt", []),
        "matched_entity_texts": set(gh.get("entities", []) or []),
        "active_labels": set(gh.get("labels", []) or []),
        "graph_matched_by": gh.get("graph_matched_by"),
        "used_verified_aggregate": gh.get("used_verified_aggregate", False),
        "used_comparison_mode": gh.get("used_comparison_mode", False),
        "entity_summary": gh.get("entity_summary", []),
        "total_tokens": gh.get("total_tokens", 0),
        "total_time": (resp.get("latency_ms") or 0) / 1000,
    }


# ── UI ──

if "comparisons" not in st.session_state:
    st.session_state.comparisons = []
if "compare_query" not in st.session_state:
    st.session_state.compare_query = ""
if "last_hybrid" not in st.session_state:
    st.session_state.last_hybrid = None
if "last_traditional" not in st.session_state:
    st.session_state.last_traditional = None

st.set_page_config(page_title="MF Context Engine", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
tab_compare, tab_analytics = st.tabs(["⚖️ Compare", "📊 Analytics"])

with tab_compare:
    st.caption(f"🟢 Backend: {API_BASE}")

    col_ex1, col_ex2, col_q, col_run = st.columns([1.3, 1.3, 3.4, 1])
    if col_ex1.button("Example: concentration", use_container_width=True):
        st.session_state.compare_query = "What's our exposure to Adani Group across all schemes?"
    if col_ex2.button("Example: compliance", use_container_width=True):
        st.session_state.compare_query = "Which schemes need exit load disclosure updates after SEBI's latest circular?"
    query = col_q.text_input("query", value=st.session_state.compare_query,
                             label_visibility="collapsed",
                             placeholder="Type your query and run it against both search modes…")
    run = col_run.button("Run query", type="primary", use_container_width=True)

    if run and query:
        col_left, col_right = st.columns(2)
        ph_trad = col_left.empty()
        ph_ctx = col_right.empty()
        ph_trad.info("Running traditional vector search…")
        ph_ctx.info("Running graph + vector retrieval…")

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(_api, "/api/query/traditional", query): "traditional",
                pool.submit(_api, "/api/query/contextgraph", query): "hybrid",
            }
            for future in concurrent.futures.as_completed(futures):
                kind = futures[future]
                try:
                    resp = future.result()
                except Exception as exc:
                    (ph_trad if kind == "traditional" else ph_ctx).error(f"{kind} failed: {exc}")
                    continue
                if kind == "traditional":
                    results["traditional"] = _to_traditional(resp)
                    with ph_trad.container():
                        components.html(render_traditional_panel(results["traditional"]),
                                        height=520, scrolling=True)
                else:
                    results["hybrid"] = _to_hybrid(resp)
                    with ph_ctx.container():
                        components.html(render_contextgraph_panel(results["hybrid"],
                                                                  results["hybrid"]["entity_summary"]),
                                        height=520, scrolling=True)

        if "traditional" in results and "hybrid" in results:
            st.session_state.last_hybrid = results["hybrid"]
            st.session_state.last_traditional = results["traditional"]
            st.session_state.comparisons.append({
                "query": query,
                "traditional_time": results["traditional"]["total_time"],
                "hybrid_time": results["hybrid"]["total_time"],
                "traditional_tokens": results["traditional"].get("total_tokens", 0),
                "hybrid_tokens": results["hybrid"].get("total_tokens", 0),
            })

with tab_analytics:
    import analytics_view
    analytics_view.render_analytics_tab(None)
