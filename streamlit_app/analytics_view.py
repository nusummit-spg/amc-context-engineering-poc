"""
analytics_view.py
===================
Analytics tab — two sections:

1. Ontology & Graph Explorer: click-to-explore graph where clicking a node
   NEVER triggers a Streamlit rerun. All per-node reasoning ("why is this
   node here") is computed once, server-side, then embedded as JSON into
   the HTML component — clicking is pure client-side JS from that point on.

2. Run history: token/latency comparisons logged from the Compare tab.

Critical fix vs. the previous version: the graph shown here is built from
`graph_edges_used_in_prompt` — the SAME trimmed, relevance-filtered edges
that actually went into the LLM's prompt — not the raw untrimmed fallback
set. If the graph had nothing directly relevant (Path 3 fallback), that's
now shown as an explicit warning instead of silently rendering unrelated
nodes next to a correct answer.
"""
from __future__ import annotations
import json
import html as _html

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

import graph_store


CSS = """
<style>
.og-wrap { font-family:'Segoe UI',Arial,sans-serif; color:#231F1C; }
.og-row { display:flex; gap:20px; }
.og-graph-col { flex: 1.4; min-width:0; }
.og-detail-col { flex: 1; min-width:0; border-left:1px solid #E7E1D4; padding-left:20px; }
.og-label { font-size:10.5px; letter-spacing:.05em; color:#8A8378; text-transform:uppercase; font-weight:600; margin-bottom:8px; }
.og-node-name { font-size:17px; font-weight:700; margin-bottom:10px; }
.og-reason { border:1px solid #E7E1D4; border-radius:8px; padding:10px 12px; margin-bottom:8px; font-size:12.5px; line-height:1.5; }
.og-reason b { color:#A8412C; }
.og-badge { display:inline-block; padding:3px 10px; border-radius:999px; font-size:10.5px;
  font-weight:600; background:#EFEAE0; color:#5C574C; text-transform:uppercase; margin-bottom:10px; }
.og-badge.green { background:#E4EEE1; color:#3F6B42; }
.og-badge.amber { background:#F3E4C9; color:#8A5A20; }
.og-empty { color:#8A8378; font-size:12.5px; padding:20px 0; }
.og-source { font-size:11.5px; color:#5C574C; margin-top:6px; }
.og-note { font-size:11px; color:#8A8378; margin-top:10px; }
.og-node-dot { transition: r 0.1s; cursor:pointer; }
.og-node-dot.og-active { stroke:#231F1C; stroke-width:2px; }
</style>
"""

JS_TEMPLATE = """
<script>
const NODE_DATA = %(node_data_json)s;

function ogShowNode(id) {
  document.querySelectorAll('.og-node-dot').forEach(el => el.classList.remove('og-active'));
  const dot = document.getElementById('dot-' + id);
  if (dot) dot.classList.add('og-active');

  const data = NODE_DATA[id];
  const panel = document.getElementById('og-detail-panel');
  if (!data) { panel.innerHTML = "<div class='og-empty'>No details for this node.</div>"; return; }

  let badgeClass = data.matched_directly ? 'green' : (data.is_fallback ? 'amber' : '');
  let badgeText = data.matched_directly ? 'Matched directly from your question'
                  : (data.is_fallback ? 'Indicative only — not directly matched to your query'
                  : 'Connected to a matched entity');

  let out = "<div class='og-badge " + badgeClass + "'>" + badgeText + "</div>";
  out += "<div class='og-node-name'>" + data.text + "</div>";
  if (data.label) out += "<div class='og-label'>Entity type: " + data.label + "</div>";

  if (data.reasons.length === 0) {
    out += "<div class='og-empty'>No specific relationship reason recorded — this node appeared as part of a broader graph pull, not a direct match.</div>";
  } else {
    data.reasons.forEach(r => { out += "<div class='og-reason'>" + r + "</div>"; });
  }

  if (data.source) {
    out += "<div class='og-source'>Source: " + data.source +
            (data.product_name ? " (" + data.product_name + ")" : "") + "</div>";
  }
  panel.innerHTML = out;
}
</script>
"""


def _build_graph_html(nodes, edges, matched_texts, source_info, is_fallback_graph, width=480):
    """Builds the SVG graph AND the per-node reasoning JSON together. All the
    'why is this node here' logic is computed HERE, once, server-side — the
    browser never asks the server anything after this point."""
    if not nodes:
        return "<div class='og-graph-col'><div class='og-empty'>No graph data for this scope.</div></div>", {}

    cols = 4
    pos = {n: (35 + (i % cols) * (width - 70) / max(cols - 1, 1), 30 + (i // cols) * 55)
           for i, n in enumerate(nodes)}
    height = 30 + (len(nodes) // cols + 1) * 55

    edges_svg = ""
    for e in edges:
        if e["s"] not in pos or e["o"] not in pos:
            continue
        x1, y1 = pos[e["s"]]; x2, y2 = pos[e["o"]]
        color = "#C9C2B4" if is_fallback_graph else "#A8412C"
        edges_svg += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.2"/>'
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 5
        edges_svg += f'<text x="{mx}" y="{my}" font-size="8" fill="{color}" text-anchor="middle">{_html.escape(e["rel"])}</text>'

    nodes_svg = ""
    node_data = {}
    for i, n in enumerate(nodes):
        x, y = pos[n]
        matched = n in matched_texts
        color = "#A8412C" if matched else ("#D8D2C4" if is_fallback_graph else "#E8A08C")
        node_id = f"n{i}"
        nodes_svg += (f'<circle id="dot-{node_id}" class="og-node-dot" cx="{x}" cy="{y}" r="7" '
                      f'fill="{color}" onclick="ogShowNode(\'{node_id}\')"/>')
        nodes_svg += (f'<text x="{x}" y="{y+18}" font-size="8.5" fill="#5C574C" '
                       f'text-anchor="middle">{_html.escape(n[:15])}</text>')

        reasons = []
        for e in edges:
            conf_str = f" (confidence {e['conf']:.2f})" if isinstance(e.get('conf'), (int, float)) else ""
            if e["s"] == n:
                reasons.append(f"<b>{_html.escape(n)}</b> --{_html.escape(e['rel'])}--&gt; "
                                f"{_html.escape(e['o'])}{conf_str}")
            elif e["o"] == n:
                reasons.append(f"{_html.escape(e['s'])} --{_html.escape(e['rel'])}--&gt; "
                                f"<b>{_html.escape(n)}</b>{conf_str}")

        info = source_info.get(n, {})
        node_data[node_id] = {
            "text": n,
            "label": info.get("label") or "",
            "matched_directly": matched,
            "is_fallback": bool(is_fallback_graph and not matched),
            "reasons": reasons[:6],
            "source": info.get("source") or "",
            "product_name": info.get("product_name") or "",
        }

    svg = (f'<div class="og-graph-col"><svg width="100%" viewBox="0 0 {width} {height}">'
           f'{edges_svg}{nodes_svg}</svg></div>')
    return svg, node_data


def _render_graph_component(nodes, edges, matched_texts, source_info, is_fallback_graph, note):
    svg_html, node_data = _build_graph_html(nodes, edges, matched_texts, source_info, is_fallback_graph)
    full_html = f"""
    {CSS}
    <div class="og-wrap">
      <div class="og-row">
        {svg_html}
        <div class="og-detail-col">
          <div class="og-label">Node details</div>
          <div id="og-detail-panel"><div class='og-empty'>Click a node to see why it's here.</div></div>
        </div>
      </div>
      <div class="og-note">{note}</div>
    </div>
    {JS_TEMPLATE % {"node_data_json": json.dumps(node_data)}}
    """
    components.html(full_html, height=460, scrolling=True)


def render_analytics_tab(store):
    st.subheader("Ontology & Graph Explorer")

    scope = st.radio("Scope", ["Last query's graph", "Full knowledge graph"],
                      horizontal=True, label_visibility="collapsed")

    if scope == "Last query's graph":
        hybrid = st.session_state.get("last_hybrid")
        if not hybrid:
            st.info("Run a query in the Compare tab first to see its graph here.")
        else:
            # ── the actual fix: use the SAME trimmed edges the LLM saw ──
            used_edges = hybrid.get("graph_edges_used_in_prompt", [])
            is_fallback = hybrid.get("graph_matched_by") == "fallback" or not used_edges

            if is_fallback:
                st.warning(
                    "No graph relationships were directly relevant to this query — the "
                    "answer was grounded on document search, not the graph. Showing the "
                    "broader graph neighborhood below for reference only, not as verification."
                )
                edges_to_show = hybrid.get("graph_edges", [])[:10]
            else:
                edges_to_show = used_edges

            nodes_to_show = list({e["s"] for e in edges_to_show} | {e["o"] for e in edges_to_show})
            matched_texts = hybrid.get("matched_entity_texts", set())
            source_info = graph_store.get_entities_source_info_batch(nodes_to_show)

            note = ("Colored nodes matched your question directly. Click any node to see "
                    "exactly which relationship(s) put it in this graph.")
            _render_graph_component(nodes_to_show, edges_to_show, matched_texts,
                                     source_info, is_fallback, note)

    else:
        full = graph_store.get_subgraph(limit=60)
        edges_to_show = full["edges"]
        nodes_to_show = list({e["s"] for e in edges_to_show} | {e["o"] for e in edges_to_show})
        source_info = graph_store.get_entities_source_info_batch(nodes_to_show)
        note = "Showing up to 60 relationships from the full graph. Click any node to explore it."
        _render_graph_component(nodes_to_show, edges_to_show, set(), source_info, False, note)

    st.divider()
    st.subheader("Traditional vs. ContextGraph — run history")
    comparisons = st.session_state.get("comparisons", [])
    if not comparisons:
        st.info("Run a query in the Compare tab first.")
        return

    df = pd.DataFrame(comparisons)
    st.dataframe(df, use_container_width=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Avg traditional latency", f"{df['traditional_time'].mean():.2f}s")
    c2.metric("Avg hybrid latency", f"{df['hybrid_time'].mean():.2f}s",
               delta=f"{df['hybrid_time'].mean() - df['traditional_time'].mean():+.2f}s")
    if "traditional_tokens" in df.columns:
        c3.metric("Avg hybrid token delta",
                   f"{(df['hybrid_tokens'] - df['traditional_tokens']).mean():+.0f}")
    st.bar_chart(df.set_index("query")[["traditional_time", "hybrid_time"]])
    if "traditional_tokens" in df.columns:
        st.bar_chart(df.set_index("query")[["traditional_tokens", "hybrid_tokens"]])