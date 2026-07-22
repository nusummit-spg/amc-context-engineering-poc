"""
chat_view.py
=============
Multi-turn chat tab — thin HTTP client over POST /api/chat, same
architecture as the rest of this app (no ML libs load in this container;
all retrieval runs in the API). Reuses compare_view.py's rendering
functions so Traditional/ContextGraph panels look identical to the
Compare tab.

Each turn fires two independent /api/chat calls (mode=traditional,
mode=contextgraph) via a client-side ThreadPoolExecutor, exactly like the
Compare tab's pattern — this is what lets the faster ContextGraph panel
render before the slower Traditional panel finishes, instead of both
waiting on a single combined call.
"""
import concurrent.futures
import json
import os
import uuid
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

from compare_view import render_traditional_panel, render_contextgraph_panel

API_BASE = os.environ.get("API_BASE", "http://api:8000")
SESSIONS_DIR = Path(__file__).resolve().parent / "logs" / "chat_sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _save_session(session_id: str, history: list[dict]) -> None:
    try:
        # default=str is a safety net, not a license to store non-JSON types on
        # purpose — anything that hits it (e.g. a stray set()) round-trips as a
        # string on reload, which is a lossy but non-fatal degradation.
        _session_path(session_id).write_text(
            json.dumps(history, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        st.warning(f"Could not save chat session to disk: {exc}")


def _load_session(session_id: str) -> list[dict] | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        st.warning(f"Could not load session {session_id}: {exc}")
        return None


def _adapt_traditional(t: dict) -> dict:
    m = t.get("metrics") or {}
    return {
        "answer": t.get("snippet") or "",
        "docs": [{
            "name": f.get("name"), "score": f.get("score") or 0,
            "page": f.get("page"), "snippet": f.get("snippet") or "",
            "full_text": f.get("full_text") or "",
        } for f in t.get("files", [])],
        "total_tokens": m.get("total_tokens", 0),
        "total_time": m.get("llm_ms", 0) / 1000,
        "telemetry_breakdown": m.get("telemetry_breakdown", {}),
    }


def _adapt_hybrid(h: dict) -> dict:
    ans = h.get("answer") or {}
    gh = h.get("graph_highlight") or {}
    return {
        "answer": ans.get("answer") or "",
        "query_type": gh.get("query_type"),
        "confidence_label": ans.get("compliance_note") or ans.get("confidence") or "",
        "docs": [{"name": s.get("document_title") or s.get("document_id"),
                  "snippet": s.get("snippet")} for s in h.get("sources", [])],
        "graph_nodes": gh.get("node_names", []),
        "graph_edges": gh.get("edges", []),
        "graph_edges_used_in_prompt": gh.get("edges_used_in_prompt", []),
        "matched_entity_texts": list(set(gh.get("entities", []) or [])),
        "active_labels": list(set(gh.get("labels", []) or [])),
        "graph_matched_by": gh.get("graph_matched_by"),
        "used_verified_aggregate": gh.get("used_verified_aggregate", False),
        "used_comparison_mode": gh.get("used_comparison_mode", False),
        "entity_summary": gh.get("entity_summary", []),
        "total_tokens": gh.get("total_tokens", 0),
        "total_time": (h.get("latency_ms") or 0) / 1000,
        "telemetry_breakdown": gh.get("telemetry_breakdown", {}),
    }


def _fetch_mode(mode: str, query: str, history: list[dict], session_id: str) -> dict:
    payload = {"query": query, "session_id": session_id, "history": history, "mode": mode}
    r = requests.post(f"{API_BASE}/api/chat", json=payload, timeout=240)
    r.raise_for_status()
    data = r.json()
    return data.get("traditional") if mode == "traditional" else data.get("hybrid")


def render_chat_tab():
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = str(uuid.uuid4())
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    col_q, col_run, col_new = st.columns([5.1, 0.9, 1.1])

    query = col_q.text_input("query", value=st.session_state.get("chat_query", ""),
                              label_visibility="collapsed",
                              placeholder="Ask a follow-up — conversation context carries forward…",
                              key="chat_query_input")
    run = col_run.button("Send", type="primary", use_container_width=True, key="chat_run")
    if col_new.button("🔄 New Session", use_container_width=True, key="chat_new_session"):
        # Starts a fresh session_id + empty history — clears the screen and
        # drops all prior turns from the context sent to the LLM. The old
        # session's JSON file on disk is left alone (still resumable below).
        st.session_state.chat_session_id = str(uuid.uuid4())
        st.session_state.chat_history = []
        st.session_state.chat_query = ""
        st.rerun()

    with st.expander(f"Session: `{st.session_state.chat_session_id}`  ·  resume a previous session"):
        resume_id = st.text_input("Session ID to resume", label_visibility="collapsed",
                                   placeholder="Paste a session ID and press Enter…", key="chat_resume_id")
        if resume_id and st.button("Load session", key="chat_resume_btn"):
            loaded = _load_session(resume_id.strip())
            if loaded is not None:
                st.session_state.chat_session_id = resume_id.strip()
                st.session_state.chat_history = loaded
                st.rerun()
            else:
                st.error("No saved session found with that ID.")

    if run and query:
        st.session_state.chat_query = ""
        st.session_state.chat_history.append(
            {"role": "user", "content": query, "turn_index": len(st.session_state.chat_history) // 2 + 1})
        st.session_state.chat_history.append({"role": "assistant", "loading": True})
        st.rerun()

    # Group flat history into (user, assistant) turn pairs
    turns = []
    hist = st.session_state.chat_history
    for i in range(0, len(hist), 2):
        turns.append((hist[i], hist[i + 1] if i + 1 < len(hist) else None))

    loading = None  # only one turn is ever mid-flight at a time (input is blocked while loading)

    # Newest turn first
    for user_msg, asst_msg in reversed(turns):
        st.markdown(f"**Turn {user_msg.get('turn_index', 1)}:** {user_msg['content']}")
        if asst_msg is None:
            st.divider()
            continue
        if asst_msg.get("loading"):
            col_left, col_right = st.columns(2)
            ph_left, ph_right = col_left.empty(), col_right.empty()
            ph_left.info("Traditional RAG is generating…")
            ph_right.info("ContextGraph is generating…")
            loading = (user_msg, asst_msg, ph_left, ph_right)
        else:
            if asst_msg.get("error_trad"):
                st.error(f"Traditional RAG failed: {asst_msg['error_trad']}")
            if asst_msg.get("error_hybrid"):
                st.error(f"ContextGraph failed: {asst_msg['error_hybrid']}")
            col_left, col_right = st.columns(2)
            if asst_msg.get("traditional"):
                with col_left:
                    components.html(render_traditional_panel(asst_msg["traditional"]), height=450, scrolling=True)
            if asst_msg.get("hybrid"):
                with col_right:
                    components.html(render_contextgraph_panel(
                        asst_msg["hybrid"], asst_msg["hybrid"].get("entity_summary")), height=450, scrolling=True)
        st.divider()

    if loading:
        user_msg, asst_msg, ph_left, ph_right = loading
        q = user_msg["content"]
        session_id = st.session_state.chat_session_id
        # History payload excludes the in-flight (user, loading-assistant) pair
        hist_payload = st.session_state.chat_history[:-2]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_hybrid = executor.submit(_fetch_mode, "contextgraph", q, hist_payload, session_id)
            fut_trad = executor.submit(_fetch_mode, "traditional", q, hist_payload, session_id)

            for fut in concurrent.futures.as_completed([fut_hybrid, fut_trad]):
                try:
                    result = fut.result()
                except Exception as exc:
                    if fut is fut_hybrid:
                        ph_right.error(f"ContextGraph failed: {exc}")
                        asst_msg["error_hybrid"] = str(exc)
                    else:
                        ph_left.error(f"Traditional RAG failed: {exc}")
                        asst_msg["error_trad"] = str(exc)
                    continue

                if fut is fut_hybrid:
                    hybrid_clean = _adapt_hybrid(result or {})
                    asst_msg["hybrid"] = hybrid_clean
                    with ph_right.container():
                        components.html(render_contextgraph_panel(hybrid_clean, hybrid_clean.get("entity_summary")),
                                         height=450, scrolling=True)
                else:
                    trad_clean = _adapt_traditional(result or {})
                    asst_msg["traditional"] = trad_clean
                    with ph_left.container():
                        components.html(render_traditional_panel(trad_clean), height=450, scrolling=True)

        asst_msg["loading"] = False
        asst_msg["content"] = (asst_msg.get("hybrid") or {}).get("answer", "No answer.")
        _save_session(session_id, st.session_state.chat_history)
        st.rerun()
