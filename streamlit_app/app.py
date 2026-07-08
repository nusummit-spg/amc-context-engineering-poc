"""Streamlit UI — thin client over the FastAPI backend.

Calls POST /api/query/traditional and /api/query/contextgraph and renders the
comparison panels. No ML/torch here — all retrieval + LLM runs in the API, so
this container stays light (streamlit + requests + pandas).
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
.stApp { background-color: #F8F7F3; background-image: radial-gradient(#E5E0D8 1px, transparent 0); background-size: 24px 24px; }
header { background-color: transparent !important; }
.stTabs [data-baseweb="tab-list"] { gap: 24px; }
.stTabs [data-baseweb="tab"] { padding-top: 1rem; padding-bottom: 0.5rem; color: #8A8378; font-weight: 600; }
.stTabs [aria-selected="true"] { color: #A8412C !important; border-bottom-color: #A8412C !important; }
.stTextInput input { background-color: #EFEAE0 !important; border: 1px solid #E7E1D4 !important; border-radius: 8px !important; color: #5C574C !important; }
.stTextInput input:focus { border-color: #A8412C !important; box-shadow: 0 0 0 1px #A8412C !important; }
.stButton > button[kind="secondary"] { background-color: #FFFFFF; border: 1px solid #E7E1D4; border-radius: 8px; color: #5C574C; font-weight: 600; transition: all 0.2s; }
.stButton > button[kind="secondary"]:hover { border-color: #A8412C; color: #A8412C; background-color: #FFF; }
.stButton > button[kind="primary"] { background-color: #A8412C; color: white; border-radius: 8px; border: none; font-weight: 600; }
.stButton > button[kind="primary"]:hover { background-color: #8C3523; color: white; }
[data-testid="stMetricValue"] { color: #231F1C; }
[data-testid="stMetricLabel"] { color: #8A8378; }
</style>
"""


# ── API + adapters (QueryResponse -> the dict shape compare_view expects) ──

def _api(path: str, query: str) -> dict:
    r = requests.post(f"{API_BASE}{path}", json={"query": query}, timeout=240)
    r.raise_for_status()
    return r.json()


def _to_traditional(resp: dict) -> dict:
    t = resp.get("traditional") or {}
    return {
        "answer": t.get("snippet") or "",
        "docs": [{"name": f.get("name"), "score": f.get("score"),
                  "snippet": (f.get("snippet") or "")[:160]} for f in t.get("files", [])],
        "total_time": (resp.get("latency_ms") or 0) / 1000,
    }


def _to_hybrid(resp: dict) -> dict:
    ans = resp.get("answer") or {}
    gh = resp.get("graph_highlight") or {}
    return {
        "answer": ans.get("answer") or "",
        "confidence_label": ans.get("compliance_note") or ans.get("confidence") or "",
        "docs": [{"name": s.get("document_title") or s.get("document_id")} for s in resp.get("sources", [])],
        "graph_nodes": gh.get("node_names", []),
        "graph_edges": gh.get("edges", []),
        "matched_entity_texts": set(gh.get("entities", []) or []),
        "entity_summary": gh.get("entity_summary", []),
        "total_time": (resp.get("latency_ms") or 0) / 1000,
    }


def _relevancy(result: dict) -> float:
    """Directional proxy: citation density + graph signal + no-hedge + substance."""
    answer = result.get("answer", "") or ""
    score = min(answer.count("[") * 0.15, 0.45)
    score += 0.25 if result.get("graph_edges") else 0
    score += 0.2 if "isn't in" not in answer.lower() and "not in the context" not in answer.lower() else 0
    score += 0.1 if len(answer) > 120 else 0
    return round(min(score, 1.0), 2)


# ── UI ──

if "comparisons" not in st.session_state:
    st.session_state.comparisons = []
if "compare_query" not in st.session_state:
    st.session_state.compare_query = ""

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
            st.session_state.comparisons.append({
                "query": query,
                "traditional_time": results["traditional"]["total_time"],
                "hybrid_time": results["hybrid"]["total_time"],
                "traditional_relevancy": _relevancy(results["traditional"]),
                "hybrid_relevancy": _relevancy(results["hybrid"]),
            })

with tab_analytics:
    st.subheader("Traditional vs. ContextGraph — run history")
    if not st.session_state.comparisons:
        st.info("Run a query in the Compare tab first.")
    else:
        df = pd.DataFrame(st.session_state.comparisons)
        st.dataframe(df, use_container_width=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Avg traditional latency", f"{df['traditional_time'].mean():.2f}s")
        c2.metric("Avg hybrid latency", f"{df['hybrid_time'].mean():.2f}s",
                  delta=f"{df['hybrid_time'].mean() - df['traditional_time'].mean():+.2f}s")
        c3.metric("Avg relevancy gain", f"{(df['hybrid_relevancy'] - df['traditional_relevancy']).mean():+.2f}")
        st.bar_chart(df.set_index("query")[["traditional_time", "hybrid_time"]])
        st.bar_chart(df.set_index("query")[["traditional_relevancy", "hybrid_relevancy"]])
