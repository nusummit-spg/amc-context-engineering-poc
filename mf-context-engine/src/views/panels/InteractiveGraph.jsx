import { useMemo, useState } from "react";

function buildNodeData(nodes, edges, matchedTexts, sourceInfo, isFallbackGraph) {
  const cols = 4;
  const width = 480;
  const pos = {};
  nodes.forEach((n, i) => {
    pos[n] = [35 + (i % cols) * ((width - 70) / Math.max(cols - 1, 1)), 30 + Math.floor(i / cols) * 55];
  });
  const height = 30 + (Math.floor(nodes.length / cols) + 1) * 55;

  const nodeData = {};
  nodes.forEach((n, i) => {
    const matched = matchedTexts.includes(n);
    const nodeId = `n${i}`;
    const reasons = [];
    edges.forEach((e) => {
      const confStr = typeof e.conf === "number" ? ` (confidence ${e.conf.toFixed(2)})` : "";
      if (e.s === n) reasons.push({ html: `<b>${n}</b> --${e.rel}--> ${e.o}${confStr}` });
      else if (e.o === n) reasons.push({ html: `${e.s} --${e.rel}--> <b>${n}</b>${confStr}` });
    });
    const info = sourceInfo[n] || {};
    nodeData[nodeId] = {
      text: n,
      label: info.label || "",
      matched_directly: matched,
      is_fallback: !!(isFallbackGraph && !matched),
      reasons: reasons.slice(0, 6),
      source: info.source || "",
      product_name: info.product_name || "",
    };
  });

  return { pos, width, height, nodeData };
}

export default function InteractiveGraph({ nodes, edges, matchedTexts, sourceInfo, isFallbackGraph, note }) {
  const [activeId, setActiveId] = useState(null);

  const { pos, width, height, nodeData } = useMemo(
    () => buildNodeData(nodes, edges, matchedTexts, sourceInfo, isFallbackGraph),
    [nodes, edges, matchedTexts, sourceInfo, isFallbackGraph]
  );

  if (!nodes || nodes.length === 0) {
    return (
      <div className="og-wrap">
        <div className="og-graph-col"><div className="og-empty">No graph data for this scope.</div></div>
      </div>
    );
  }

  const active = activeId ? nodeData[activeId] : null;

  return (
    <div className="og-wrap">
      <div className="og-row">
        <div className="og-graph-col">
          <svg width="100%" viewBox={`0 0 ${width} ${height}`}>
            {edges.map((e, i) => {
              if (!pos[e.s] || !pos[e.o]) return null;
              const [x1, y1] = pos[e.s];
              const [x2, y2] = pos[e.o];
              const color = isFallbackGraph ? "#C9C2B4" : "#1F3A5F";
              return (
                <g key={i}>
                  <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth="1.2" />
                  <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 5} fontSize="8" fill={color} textAnchor="middle">
                    {e.rel}
                  </text>
                </g>
              );
            })}
            {nodes.map((n, i) => {
              const [x, y] = pos[n];
              const matched = matchedTexts.includes(n);
              const color = matched ? "#1F3A5F" : (isFallbackGraph ? "#D8D2C4" : "#C9BBA0");
              const nodeId = `n${i}`;
              return (
                <g key={n}>
                  <circle
                    id={`dot-${nodeId}`}
                    className={`og-node-dot ${activeId === nodeId ? "og-active" : ""}`}
                    cx={x} cy={y} r="7" fill={color}
                    onClick={() => setActiveId(nodeId)}
                  />
                  <text x={x} y={y + 18} fontSize="8.5" fill="#5C574C" textAnchor="middle">
                    {n.slice(0, 15)}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
        <div className="og-detail-col">
          <div className="og-label">Node details</div>
          <div id="og-detail-panel">
            {!active ? (
              <div className="og-empty">Click a node to see why it's here.</div>
            ) : (
              <div>
                <div className={`og-badge ${active.matched_directly ? "green" : (active.is_fallback ? "amber" : "")}`}>
                  {active.matched_directly
                    ? "Matched directly from your question"
                    : active.is_fallback
                    ? "Indicative only — not directly matched to your query"
                    : "Connected to a matched entity"}
                </div>
                <div className="og-node-name">{active.text}</div>
                {active.label && <div className="og-label">Entity type: {active.label}</div>}
                {active.reasons.length === 0 ? (
                  <div className="og-empty">No specific relationship reason recorded — this node appeared as part of a broader graph pull, not a direct match.</div>
                ) : (
                  active.reasons.map((r, i) => (
                    <div className="og-reason" key={i} dangerouslySetInnerHTML={{ __html: r.html }} />
                  ))
                )}
                {active.source && (
                  <div className="og-source">
                    Source: {active.source}{active.product_name ? ` (${active.product_name})` : ""}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="og-note">{note}</div>
    </div>
  );
}
