# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
review_queue_view.py
====================
Streamlit view component for the Human Review Queue.
Allows compliance analysts to inspect flagged or low-confidence queries,
assign reviews, and submit verdicts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import os
import requests
import streamlit as st
import pandas as pd


def _get_backend_url() -> str:
    return getattr(st.session_state, "backend_url", os.environ.get("BACKEND_URL", "http://localhost:8000"))


def _get_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = getattr(st.session_state, "token", None)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    user_id = getattr(st.session_state, "username", getattr(st.session_state, "user_id", "compliance_officer"))
    headers["X-User-ID"] = str(user_id)
    return headers


def render_review_queue_tab():
    """Main entry point to render the review queue tab in Streamlit."""
    st.title("📋 Compliance Review Queue")
    st.caption("Human-in-the-loop escalation pipeline for low-confidence and flagged AI responses")

    tab1, tab2, tab3 = st.tabs(["📌 My Assigned Reviews", "📥 Unassigned Queue", "📊 Queue Analytics"])

    with tab1:
        render_my_reviews()

    with tab2:
        render_unassigned_reviews()

    with tab3:
        render_queue_stats()


def render_my_reviews():
    """Show reviews assigned to the current user."""
    backend_url = _get_backend_url()
    headers = _get_headers()

    try:
        res = requests.get(f"{backend_url}/api/review-queue/pending", headers=headers, timeout=5)
        if res.status_code != 200:
            st.warning(f"Could not load assigned reviews (HTTP {res.status_code})")
            return
        data = res.json()
        items = data.get("items", [])
    except Exception as exc:
        st.info("No active backend connection or queue empty. Showing offline status.")
        return

    if not items:
        st.success("🎉 You have zero pending reviews! All clear.")
        return

    st.write(f"**{len(items)}** review(s) assigned to you:")

    for item in items:
        with st.container(border=True):
            col_info, col_prio = st.columns([3, 1])

            with col_info:
                st.markdown(f"**Query:** `{item.get('query')}`")
                st.markdown(f"**User Answer:** {item.get('user_answer')[:250]}...")
                st.caption(f"Reason: `{item.get('reason')}` | Confidence: `{item.get('confidence_score', 0):.2f}`")
                st.caption(f"Response ID: `{item.get('response_id')}` | Queued: {item.get('created_at', '')}")

            with col_prio:
                prio = item.get("priority", 5)
                prio_icon = "🔴" if prio <= 2 else ("🟡" if prio <= 5 else "🟢")
                st.metric("Priority", f"{prio_icon} P{prio}")

            col_app, col_rej = st.columns(2)

            with col_app:
                with st.popover("✅ Approve & Resolve"):
                    verdict = st.selectbox(
                        "Verdict",
                        ["confirmed", "partially_correct", "needs_correction"],
                        key=f"verdict_{item['id']}"
                    )
                    notes = st.text_area("Resolution Notes", key=f"notes_{item['id']}", placeholder="Add compliance remarks...")
                    if st.button("Submit Approval", key=f"btn_app_{item['id']}", type="primary"):
                        try:
                            app_res = requests.post(
                                f"{backend_url}/api/review-queue/{item['id']}/approve",
                                json={"verdict": verdict, "notes": notes},
                                headers=headers,
                                timeout=5
                            )
                            if app_res.status_code == 200:
                                st.success("Review resolved and approved!")
                                st.rerun()
                            else:
                                st.error("Failed to approve.")
                        except Exception as e:
                            st.error(f"Error: {e}")

            with col_rej:
                with st.popover("↩️ Reject / Return to Queue"):
                    reason = st.text_input("Rejection Reason", key=f"rej_reason_{item['id']}", placeholder="Why is this rejected?")
                    if st.button("Confirm Return", key=f"btn_rej_{item['id']}"):
                        try:
                            rej_res = requests.post(
                                f"{backend_url}/api/review-queue/{item['id']}/reject",
                                json={"reason": reason or "Returned by reviewer"},
                                headers=headers,
                                timeout=5
                            )
                            if rej_res.status_code == 200:
                                st.info("Review returned to unassigned queue.")
                                st.rerun()
                            else:
                                st.error("Failed to reject.")
                        except Exception as e:
                            st.error(f"Error: {e}")


def render_unassigned_reviews():
    """Show unassigned queue items for triage and bulk assignment."""
    backend_url = _get_backend_url()
    headers = _get_headers()

    try:
        res = requests.get(f"{backend_url}/api/review-queue/unassigned", headers=headers, timeout=5)
        if res.status_code != 200:
            st.warning("Could not fetch unassigned reviews.")
            return
        items = res.json().get("items", [])
    except Exception as exc:
        st.info("Unassigned queue empty or backend unavailable.")
        return

    if not items:
        st.info("No unassigned reviews waiting in triage.")
        return

    df_rows = []
    for it in items:
        df_rows.append({
            "ID": it.get("id")[:8],
            "Query": it.get("query")[:45] + "...",
            "Reason": it.get("reason"),
            "Score": f"{it.get('confidence_score', 0):.2f}",
            "Priority": f"P{it.get('priority', 5)}",
            "Created": it.get("created_at", "")[:19]
        })

    st.dataframe(pd.DataFrame(df_rows), use_container_width=True)

    st.subheader("Assign Selected")
    selected_ids = st.multiselect(
        "Select Review IDs to assign",
        options=[it["id"] for it in items],
        format_func=lambda x: f"{x[:8]} - {[it['query'][:30] for it in items if it['id'] == x][0]}..."
    )

    if selected_ids:
        assignee = st.text_input("Assign to User ID", value="compliance_officer_1")
        if st.button("Assign Reviews", type="primary"):
            assigned_count = 0
            for it_id in selected_ids:
                try:
                    r = requests.post(
                        f"{backend_url}/api/review-queue/{it_id}/assign",
                        json={"user_id": assignee},
                        headers=headers,
                        timeout=5
                    )
                    if r.status_code == 200:
                        assigned_count += 1
                except Exception:
                    pass
            st.success(f"Assigned {assigned_count} review item(s) to {assignee}.")
            st.rerun()


def render_queue_stats():
    """Display queue throughput, pending backlog, and average resolution latency."""
    backend_url = _get_backend_url()
    headers = _get_headers()

    try:
        res = requests.get(f"{backend_url}/api/review-queue/stats?days=7", headers=headers, timeout=5)
        if res.status_code != 200:
            st.warning("Could not fetch queue analytics.")
            return
        stats = res.json()
    except Exception as exc:
        st.info("Analytics unavailable.")
        return

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Queued", stats.get("total", 0))
    with c2:
        st.metric("Pending Triage", stats.get("pending", {}).get("count", 0))
    with c3:
        st.metric("In Review", stats.get("in_review", {}).get("count", 0))
    with c4:
        st.metric("Approved / Resolved", stats.get("approved", {}).get("count", 0))

    avg_secs = stats.get("average_resolution_time_seconds", 0.0)
    st.metric("Avg Resolution Time", f"{avg_secs:.1f} s")
