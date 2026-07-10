import concurrent.futures
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import os

import config, retrieval, graph_store, faiss_store
from compare_view import render_traditional_panel, render_contextgraph_panel

faiss_store.INDEXES_DIR = config.FAISS_DIR

API_BASE = os.environ.get("API_BASE", "http://api:8000")
# --- NEW: Custom CSS to match the target UI ---
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
    border-radius: 8px !important; /* Matches the display container roundness */
    box-shadow: none !important; /* Forces the flat 2D look by removing drop shadows */
    padding: 0.6rem 1.2rem !important;
}

/* Example Buttons / Secondary Buttons */
.stButton > button[kind="secondary"] { 
    background-color: #FFFFFF !important; /* Solid white like your display cards */
    border: 1px solid #E7E1D4 !important; /* The exact border color of your cards */
    color: #5C574C !important; 
    font-weight: 600; 
    transition: all 0.2s ease; 
}
.stButton > button[kind="secondary"]:hover { 
    border-color: #A8412C !important; 
    color: #A8412C !important; 
    background-color: #F8F7F3 !important; /* Subtle background shift on hover */
}

/* Action Button / Primary Button */
.stButton > button[kind="primary"] { 
    background-color: #A8412C !important; 
    color: white !important; 
    border: 1px solid #8C3523 !important; /* Slightly darker terracotta border for a 2D edge */
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
    background-color: #EFEAE0 !important; /* Card background match */
    border: 1px solid #E7E1D4 !important;
    border-radius: 12px !important;
    color: #5C574C !important;
}
/* Swap the blue icon color out for your accent color */
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
def get_master_store():
    return faiss_store.BrochureFAISSStore("amc_master")

if "comparisons" not in st.session_state:
    st.session_state.comparisons = []
if "compare_query" not in st.session_state:
    st.session_state.compare_query = ""

if "last_hybrid" not in st.session_state:
    st.session_state.last_hybrid = None
if "last_traditional" not in st.session_state:
    st.session_state.last_traditional = None

@st.cache_resource
def _warm_models():
    """Runs once per server process (not per rerun) — forces spaCy, GLiNER,
    and the sentence-transformer embedder to load now, so the first live
    query during the demo isn't paying cold-start cost."""
    import ner_pipeline
    ner_pipeline.run_layers_ab("warmup query for model preload")
    faiss_store._get_embedder()
    return True

@st.cache_data(ttl=300)
def get_cached_entity_summary():
    return graph_store.get_entity_type_summary(set())

_warm_models()
store = get_master_store()  

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
        try:
            store = get_master_store()
        except FileNotFoundError:
            store = None
            st.warning("No FAISS index found — run `python build_index.py` first.")

        if store is not None:
            col_left, col_right = st.columns(2)
            ph_trad = col_left.empty()
            ph_ctx = col_right.empty()
            ph_trad.info("Running traditional vector search…")
            ph_ctx.info("Running graph + vector retrieval…")

            results = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = {
                    pool.submit(retrieval.traditional_rag, query, store): "traditional",
                    pool.submit(retrieval.hybrid_graphrag, query, store): "hybrid",
                }
                for future in concurrent.futures.as_completed(futures):
                    kind = futures[future]
                    results[kind] = future.result()
                    if kind == "traditional":
                        with ph_trad.container():
                            components.html(render_traditional_panel(results["traditional"]),
                                             height=520, scrolling=True)
                    else:
                        base_summary = get_cached_entity_summary()
                        entity_summary = [{**row, "active": row["label"] in results["hybrid"]["active_labels"]}
                                        for row in base_summary]
                        with ph_ctx.container():
                            components.html(render_contextgraph_panel(results["hybrid"], entity_summary),
                                             height=520, scrolling=True)
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
    analytics_view.render_analytics_tab(store)