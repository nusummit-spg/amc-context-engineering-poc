# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

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
import chat_view

API_BASE = os.environ.get("API_BASE", "http://api:8000")

@st.cache_resource
def _startup_warmup():
    try:
        import ner_pipeline
        ner_pipeline.warmup_ner_models()
    except Exception as e:
        print(f"  [app] Startup warmup notice: {e}", flush=True)
    return True

_startup_warmup()

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


@st.cache_resource
def _warm_up_resources():
    try:
        import faiss_store
        import graph_store
        faiss_store._get_embedder()
        graph_store.init_schema()
    except Exception as exc:
        print(f"  [app] Warm-up notice: {exc}", flush=True)

_warm_up_resources()


# ── API client + adapters (QueryResponse JSON -> the dict shape compare_view.py
#    and analytics_view.py expect — matching the engine's own retrieval.py
#    output field-for-field, so those rendering modules need no changes) ──

def _local_api(path: str, query: str) -> dict:
    import retrieval
    import faiss_store
    import graph_store
    import taxonomy_retrieval

    if path == "/api/query/traditional":
        # Traditional path: uses taxonomy FAISS index (same 1,967-vector corpus)
        res = taxonomy_retrieval.traditional_rag_v2(query)
        docs = res.get("docs", [])
        return {
            "query": query,
            "mode": "traditional",
            "traditional": {
                "files": [{
                    "name": d.get("name"),
                    "score": d.get("score", 0.0),
                    "page": d.get("page", 0),
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
        res = taxonomy_retrieval.hybrid_graphrag_v2(query)
        # entity_summary comes directly from taxonomy_retrieval (not graph_store)
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
                "entity_summary": res.get("entity_summary", []),
                "query_type": res.get("query_type"),
                "graph_matched_by": res.get("graph_matched_by"),
                "used_verified_aggregate": res.get("used_verified_aggregate", False),
                "used_comparison_mode": res.get("used_comparison_mode", False),
                "total_tokens": res.get("total_tokens", 0),
                "telemetry_breakdown": res.get("telemetry_breakdown", {}),
            },
            "latency_ms": int(res.get("total_time", 0) * 1000)
        }


def _api(path: str, query: str) -> dict:
    if not API_BASE or API_BASE.lower() in ("local", "embedded", "none", "off") or not API_BASE.startswith("http"):
        return _local_api(path, query)
    try:
        r = requests.post(f"{API_BASE}{path}", json={"query": query}, timeout=240)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"  [app] Remote API unreachable ({API_BASE}): {exc}. Falling back to local execution.", flush=True)
        return _local_api(path, query)



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
        "telemetry_breakdown": m.get("telemetry_breakdown", {}),
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
        "telemetry_breakdown": gh.get("telemetry_breakdown", {}),
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
if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_query" not in st.session_state:
    st.session_state.chat_query = ""
if "active_tab" not in st.session_state:
    st.session_state.active_tab = 0

st.set_page_config(page_title="MF Context Engine", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ── ACTIVE USER PROFILE SWITCHER (RBAC) ──────────────────────────────────────
import rbac
import admin_view

rbac_mgr = rbac.get_rbac_manager()
usernames = [u["username"] for u in rbac_mgr.users]
selected_username = st.sidebar.selectbox(
    "👤 Active User Profile (RBAC)",
    usernames,
    index=0,
    help="Switch user roles to test Role-Based Access Control and data boundaries."
)

active_user = rbac_mgr.get_user_by_username(selected_username) or rbac_mgr.users[0]
st.session_state.active_user = active_user
user_role = active_user["role"]

st.sidebar.markdown(f"""
> **User**: `{active_user['full_name']}`  
> **Role**: `{user_role}`  
> **Dept**: `{active_user['department']}`
""")

if st.sidebar.button("🗑️ Clear Intent Cache", use_container_width=True, help="Flush in-memory and disk intent cache so all queries execute fresh LLM synthesis"):
    import intent_cache
    intent_cache.clear_cache()
    st.toast("⚡ Intent Cache cleared cleanly! Next query will execute full LLM synthesis.")
    st.rerun()

# ── BACKGROUND INDEXING NOTIFICATIONS & SIDEBAR STATUS ──────────────────────────
import indexing_manager
unread_tasks = indexing_manager.get_unread_notifications()
for unread in unread_tasks:
    fname = unread.get("filename", "Document")
    if unread.get("status") == "COMPLETED":
        st.toast(
            f"🎉 Indexing complete: '{fname}'! Added {unread.get('entities_count', 0)} entities to Neo4j & {unread.get('chunks_count', 0)} chunks to FAISS.",
            icon="✅"
        )
    elif unread.get("status") == "FAILED":
        st.toast(
            f"⚠️ Indexing failed for '{fname}': {unread.get('error_message', 'Unknown error')}",
            icon="❌"
        )
    indexing_manager.mark_notification_read(unread.get("task_id", ""))

active_indexing = [t for t in indexing_manager.get_all_tasks(limit=5) if t.get("status") == "PROCESSING"]
if active_indexing:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ Background Indexing")
    for at in active_indexing:
        st.sidebar.info(f"Indexing **{at['filename']}**...\n\n_{at.get('stage')}_")
        st.sidebar.progress(float(at.get('progress', 0.1)))

chat_view.render_session_sidebar()

# Check permissions for tab access
perms = rbac.ROLE_PERMISSIONS.get(rbac.AMCRole(user_role), {})
can_compare = perms.get("can_access_compare_tab", True)
can_analytics = perms.get("can_access_analytics_tab", True)
can_admin = perms.get("can_view_admin_panel", False)
can_review = perms.get("can_review_answers", False)

tab_names = ["💬 Chat"]
if can_compare:
    tab_names.append("⚖️ Compare")
if can_analytics:
    tab_names.append("📊 Analytics")
if can_review:
    tab_names.append("📋 Review Queue")
if can_admin:
    tab_names.append("👥 Admin & Governance")

tabs = st.tabs(tab_names)
tab_idx = 0

with tabs[tab_idx]:
    st.caption(f"🟢 Backend: {API_BASE} | Role: {user_role}")
    chat_view.render_chat_tab()

if can_compare:
    tab_idx += 1
    with tabs[tab_idx]:
        st.caption(f"🟢 Backend: {API_BASE} | Role: {user_role}")

        col_q, col_run, col_clear = st.columns([4.6, 1, 1])
        query = col_q.text_input("query", value=st.session_state.compare_query,
                                 label_visibility="collapsed",
                                 placeholder="Type your query and run it against both search modes…")
        run = col_run.button("Run query", type="primary", use_container_width=True, disabled=st.session_state.get("is_running", False))
        if col_clear.button("🗑️ Clear Cache", use_container_width=True, key="compare_clear_cache", help="Flush intent cache for testing"):
            import intent_cache
            intent_cache.clear_cache()
            st.toast("⚡ Intent Cache cleared cleanly!")
            st.rerun()

        if run and query:
            st.session_state.is_running = True
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
                            components.html(render_contextgraph_panel(results["hybrid"], results["hybrid"]["entity_summary"]),
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
            st.session_state.is_running = False

if can_analytics:
    tab_idx += 1
    with tabs[tab_idx]:
        import analytics_view
        analytics_view.render_analytics_tab(None)

if can_review:
    tab_idx += 1
    with tabs[tab_idx]:
        import review_queue_view
        # review_queue_view resolves the backend from session state; keep it in
        # sync with the API_BASE this app was configured with.
        st.session_state.backend_url = API_BASE
        st.session_state.username = active_user.get("username", user_role)
        review_queue_view.render_review_queue_tab()

if can_admin:
    tab_idx += 1
    with tabs[tab_idx]:
        admin_view.render_admin_view()
