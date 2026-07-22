CSS = """
<style>
.cg-wrap { font-family:'Segoe UI',Arial,sans-serif; color:#231F1C; }
.cg-panel { border:1px solid #1C1917; border-radius:10px; background:#FFFFFF; padding:18px; }
.cg-panel-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.cg-panel-title { font-weight:700; font-size:14px; }
.cg-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:8px; }
.cg-dot.trad { background:#5C574C; } .cg-dot.ctx { background:#A8412C; }
.cg-badge { display:inline-block; padding:3px 10px; border-radius:999px; font-size:11px;
  font-weight:600; background:#EFEAE0; color:#5C574C; text-transform:uppercase; }
.cg-badge.green { background:#E4EEE1; color:#3F6B42; }
.cg-label { font-size:10.5px; letter-spacing:.05em; color:#8A8378; text-transform:uppercase; font-weight:600; }
.cg-doc { border:1px solid #E7E1D4; border-radius:8px; padding:9px 11px; margin-bottom:7px; }
.cg-doc-head { display:flex; justify-content:space-between; font-size:12.5px; font-weight:600; }
.cg-doc-score { background:#EFEAE0; padding:1px 8px; border-radius:6px; font-size:10.5px; color:#5C574C; }
.cg-doc-snippet { font-size:11.5px; font-style:italic; color:#6B6558; margin-top:3px; }
.cg-warning { background:#F3E4C9; color:#8A5A20; border-radius:8px; padding:9px 11px; font-size:12px; margin-top:8px; }
.cg-stats { display:flex; gap:8px; margin-top:10px; }
.cg-stat { flex:1; border:1px solid #E7E1D4; border-radius:8px; padding:8px; }
.cg-stat-num { font-size:17px; font-weight:700; } .cg-stat-label { font-size:10.5px; color:#8A8378; }
.cg-tabs { display:flex; gap:16px; border-bottom:1px solid #E7E1D4; margin-bottom:12px; }
.cg-tab { padding-bottom:7px; font-size:12.5px; font-weight:600; color:#8A8378; cursor:pointer; }
.cg-tab.active { color:#A8412C; border-bottom:2px solid #A8412C; }
.cg-answer { font-size:13px; line-height:1.55; }
.cg-tree-node { padding:5px 0; display:flex; justify-content:space-between; font-size:12px; border-bottom:1px solid #F0ECE2; }
.cg-tree-node.active { color:#A8412C; font-weight:600; }
.cg-sources { font-size:11px; color:#5C574C; margin-top:8px; }
.cg-graph-note { font-size:11px; color:#8A8378; margin-top:8px; }
.cg-doc-full { font-size:12px; color:#3A3630; margin-top:6px; line-height:1.5;
  border-top:1px dashed #E7E1D4; padding-top:6px; white-space:pre-wrap; }
.cg-doc summary { cursor:pointer; font-size:11px; color:#A8412C; font-weight:600; margin-top:5px; }
</style>
"""
import html

def _markdown_to_html(text: str) -> str:
    """Minimal markdown->HTML for LLM-generated answers — headers, bold,
    italics, paragraphs. No external dependency needed for this small a
    subset of markdown."""
    import re, html
    text = html.escape(text)
    text = re.sub(r'^#{1,6}\s*(.+)$', r'<strong>\1</strong>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)\*(?!\*)', r'<i>\1</i>', text)
    text = text.replace('\n\n', '</p><p>').replace('\n', '<br>')
    return f"<p>{text}</p>"

def _render_telemetry_card(t: dict) -> str:
    if not t or not isinstance(t, dict):
        return ""
    cypher_gen_ms = t.get('latency_cypher_generation_ms', 0)
    cypher_row = (
        f"""<tr style="border-bottom:1px solid #EAEAEA;"><td style="padding:4px 0;"><b>Cypher Generation (LLM + Neo4j exec)</b></td><td style="text-align:right;">{cypher_gen_ms:.1f} ms</td></tr>"""
        if cypher_gen_ms > 0 else ""
    )
    rerank_ms = t.get('latency_rerank_ms', 0)
    rerank_row = (
        f"""<tr style="border-bottom:1px solid #EAEAEA;"><td style="padding:4px 0;"><b>Cross-Encoder Reranking</b></td><td style="text-align:right;">{rerank_ms:.1f} ms</td></tr>"""
        if rerank_ms > 0 else ""
    )
    return f"""
    <details style="margin-top:14px; border:1px solid #E7E1D4; border-radius:8px; padding:10px; background:#FAFAFA;">
      <summary style="cursor:pointer; font-size:12px; font-weight:700; color:#5C574C;">⚡ Microsecond Telemetry & Execution Ledger</summary>
      <table style="width:100%; font-size:11.5px; margin-top:8px; border-collapse:collapse;">
        <tr style="border-bottom:1px solid #EAEAEA;"><td style="padding:4px 0;"><b>Vector DB Lookup (FAISS)</b></td><td style="text-align:right;">{t.get('latency_vector_db_ms', 0):.1f} ms</td></tr>
        {rerank_row}
        <tr style="border-bottom:1px solid #EAEAEA;"><td style="padding:4px 0;"><b>Graph Traversal (Neo4j UNWIND)</b></td><td style="text-align:right;">{t.get('latency_graph_db_ms', 0):.1f} ms</td></tr>
        <tr style="border-bottom:1px solid #EAEAEA;"><td style="padding:4px 0;"><b>NER & Entity Resolution</b></td><td style="text-align:right;">{t.get('latency_ner_processing_ms', 0):.1f} ms</td></tr>
        {cypher_row}
        <tr style="border-bottom:1px solid #EAEAEA;"><td style="padding:4px 0;"><b>Post-Retrieval Pruning / Table Prep</b></td><td style="text-align:right;">{t.get('latency_post_retrieval_processing_ms', 0):.1f} ms</td></tr>
        <tr style="border-bottom:1px solid #EAEAEA;"><td style="padding:4px 0;"><b>LLM Synthesis Latency</b></td><td style="text-align:right;">{t.get('latency_llm_generation_ms', 0):.1f} ms</td></tr>
        <tr style="border-bottom:1px solid #EAEAEA; font-weight:700; background:#EFEAE0;"><td style="padding:4px;"><b>Total Pipeline Execution</b></td><td style="text-align:right; padding:4px;">{t.get('latency_total_pipeline_ms', 0):.1f} ms</td></tr>
        <tr><td style="padding:6px 0 2px 0;"><b>Tokens (Input / Output / Total)</b></td><td style="text-align:right; padding:6px 0 2px 0;"><b>{t.get('tokens_input', 0):,}</b> in / <b>{t.get('tokens_output', 0):,}</b> out / <b>{t.get('tokens_total', 0):,}</b></td></tr>
        <tr><td style="padding:2px 0;"><b>DB Candidates Surfaced</b></td><td style="text-align:right; padding:2px 0;">{t.get('db_candidates_surfaced', 0)} {'nodes' if 'ContextGraph' in t.get('pipeline_mode', '') else 'chunks'}</td></tr>
        <tr><td style="padding:2px 0;"><b>Vector Noise Bypassed (Pillar 1)</b></td><td style="text-align:right; padding:2px 0; font-weight:bold; color:{'#3F6B42' if t.get('vector_bypassed') else '#8A8378'};">{str(t.get('vector_bypassed', False)).upper()}</td></tr>
      </table>
    </details>
"""


def render_traditional_panel(r):
    docs_html = "".join(f"""
      <div class="cg-doc">
        <div class="cg-doc-head"><span>{d['name']} · p.{d.get('page','?')}</span><span class="cg-doc-score">score {d['score']}</span></div>
        <div class="cg-doc-snippet">"{d['snippet']}…"</div>
        <details><summary>Show full source text</summary>
          <div class="cg-doc-full">{html.escape(d.get('full_text', ''))}</div>
        </details>
      </div>""" for d in r["docs"]) or "<div class='cg-graph-note'>No matching documents found.</div>"

    telemetry_html = _render_telemetry_card(r.get("telemetry_breakdown", {}))

    return f"""{CSS}
    <div class="cg-wrap cg-panel">
      <div class="cg-panel-head">
        <div class="cg-panel-title"><span class="cg-dot trad"></span>Traditional Document Search</div>
        <span class="cg-badge">vector-only</span>
      </div>
      <div class="cg-label">Files returned, ranked by similarity</div>
      <div style="margin-top:8px">{docs_html}</div>
      <div class="cg-warning">⚠ No consolidated answer — each document must be reviewed individually.</div>
      <div class="cg-answer">{_markdown_to_html(r['answer'])}</div>
      <div class="cg-stats">
        <div class="cg-stat"><div class="cg-stat-num">{len(r['docs'])}</div><div class="cg-stat-label">Docs returned</div></div>
        <div class="cg-stat"><div class="cg-stat-num">{r.get('total_tokens', 0):,}</div><div class="cg-stat-label">Tokens used</div></div>
        <div class="cg-stat"><div class="cg-stat-num">{r['total_time']:.2f}s</div><div class="cg-stat-label">Total time</div></div>
      </div>
      {telemetry_html}
    </div>"""


def _render_mini_graph(nodes, edges, matched_texts, width=460):
    if not nodes:
        return "<div class='cg-graph-note'>No graph nodes matched this query.</div>"
    cols = 4
    pos = {n: (30 + (i % cols) * (width - 60) / max(cols - 1, 1), 25 + (i // cols) * 46)
           for i, n in enumerate(nodes)}
    height = 25 + (len(nodes) // cols + 1) * 46

    edges_svg = ""
    for e in edges:
        if e["s"] not in pos or e["o"] not in pos:
            continue
        x1, y1 = pos[e["s"]]; x2, y2 = pos[e["o"]]
        edges_svg += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#A8412C" stroke-width="1.2"/>'
        edges_svg += f'<text x="{(x1+x2)/2}" y="{(y1+y2)/2-5}" font-size="8" fill="#A8412C" text-anchor="middle">{e["rel"]}</text>'

    nodes_svg = ""
    for n, (x, y) in pos.items():
        color = "#A8412C" if n in matched_texts else "#D8D2C4"
        nodes_svg += f'<circle cx="{x}" cy="{y}" r="6" fill="{color}"/>'
        nodes_svg += f'<text x="{x}" y="{y+15}" font-size="8.5" fill="#5C574C" text-anchor="middle">{n[:14]}</text>'

    return f'<svg width="100%" viewBox="0 0 {width} {height}">{edges_svg}{nodes_svg}</svg>'


def render_contextgraph_panel(r, entity_summary):
    sources_html = "".join(f"<div>[{i+1}] {d['name']}</div>" for i, d in enumerate(r["docs"]))
    tree_html = "".join(f"""
      <div class="cg-tree-node {'active' if t['active'] else ''}">
        <span>{t['label']}</span><span>{t['count']}</span>
      </div>""" for t in entity_summary)
    graph_svg = _render_mini_graph(r["graph_nodes"], r["graph_edges"], r["matched_entity_texts"])
    telemetry_html = _render_telemetry_card(r.get("telemetry_breakdown", {}))

    # Render dynamic Intent Traffic Controller badges
    tb = r.get("telemetry_breakdown", {})
    badges_list = tb.get("ui_badges", [])
    badges_html = ""
    for b in badges_list:
        bg_col = "#E4EEE1" if b["type"] == "success" else ("#E8F0FE" if b["type"] == "primary" else "#F3E4C9")
        txt_col = "#3F6B42" if b["type"] == "success" else ("#1A73E8" if b["type"] == "primary" else "#8A5A20")
        badges_html += f"""
        <div style="background:{bg_col}; color:{txt_col}; border-radius:6px; padding:6px 10px; font-size:11.5px; font-weight:600; margin-bottom:6px;">
          ⚡ {b['label']} &mdash; <span style="font-weight:400;">{b['desc']}</span>
        </div>"""

    # Render Triplet Inspector card
    triplet_list = tb.get("triplet_table", [])
    triplet_rows_html = ""
    for trp in triplet_list:
        triplet_rows_html += f"""
        <tr style="border-bottom:1px solid #EAEAEA;">
          <td style="padding:4px 0;"><b>{html.escape(str(trp.get('s',''))[:30])}</b></td>
          <td style="padding:4px 8px; color:#A8412C;"><code>{html.escape(str(trp.get('rel','')))}</code></td>
          <td style="padding:4px 0;">{html.escape(str(trp.get('o',''))[:35])}</td>
          <td style="text-align:right; padding:4px 0;">{trp.get('conf', 1.0):.2f}</td>
        </tr>"""
    triplet_card_html = ""
    if triplet_rows_html:
        triplet_card_html = f"""
        <details style="margin:10px 0; border:1px solid #E7E1D4; border-radius:8px; padding:10px; background:#FDFCFA;">
          <summary style="cursor:pointer; font-size:12px; font-weight:700; color:#A8412C;">🕸️ Graph Triplet Path Traversed ({len(r.get('graph_nodes', []))} Nodes | {len(r.get('graph_edges', []))} Edges)</summary>
          <table style="width:100%; font-size:11px; margin-top:8px; border-collapse:collapse;">
            <tr style="border-bottom:1.5px solid #D8D2C4; text-align:left;">
              <th style="padding:4px 0;">Subject Node</th><th style="padding:4px 8px;">Relationship</th><th style="padding:4px 0;">Target Node</th><th style="text-align:right;">Conf</th>
            </tr>
            {triplet_rows_html}
          </table>
        </details>"""

    return f"""{CSS}
    <div class="cg-wrap cg-panel">
      <div class="cg-panel-head">
        <div class="cg-panel-title"><span class="cg-dot ctx"></span>ContextGraph</div>
        <span class="cg-badge">hybrid graph + vector</span>
      </div>
      <div class="cg-tabs">
        <div class="cg-tab active" onclick="cgTab(this,'answer')">Answer</div>
        <div class="cg-tab" onclick="cgTab(this,'ontology')">Ontology View</div>
      </div>
      <div data-view="answer">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <span class="cg-badge green">{r['confidence_label']}</span>
        </div>
        {badges_html}
        {triplet_card_html}
        <div class="cg-answer">{_markdown_to_html(r['answer'])}</div>
        <div class="cg-label" style="margin-top:12px">Sources</div>
        <div class="cg-sources">{sources_html}</div>
        <div class="cg-stats">
          <div class="cg-stat"><div class="cg-stat-num">{len(r['graph_nodes'])}</div><div class="cg-stat-label">Graph nodes touched</div></div>
          <div class="cg-stat"><div class="cg-stat-num">{r.get('total_tokens', 0):,}</div><div class="cg-stat-label">Tokens used</div></div>
          <div class="cg-stat"><div class="cg-stat-num">{r['total_time']:.2f}s</div><div class="cg-stat-label">Total time</div></div>
        </div>
        {telemetry_html}
      </div>
      <div data-view="ontology" style="display:none">
        <div class="cg-label">Entity types touched by this query</div>
        <div style="margin-top:6px">{tree_html}</div>
        <div class="cg-label" style="margin-top:12px">Graph neighborhood</div>
        {graph_svg}
        <div class="cg-graph-note">Colored nodes/edges matched this query directly; grey nodes are one hop of surrounding context.</div>
      </div>
    </div>
    <script>
    function cgTab(el, which) {{
      var tabs = el.parentElement.children;
      for (var i=0;i<tabs.length;i++) tabs[i].classList.remove('active');
      el.classList.add('active');
      el.closest('.cg-panel').querySelectorAll('[data-view]').forEach(v =>
        v.style.display = (v.dataset.view === which ? 'block' : 'none'));
    }}
    </script>"""