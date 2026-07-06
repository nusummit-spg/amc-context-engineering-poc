import { useMemo, useState } from "react";
import { TYPE_ORDER, TYPE_COLOR, layoutGraph, edgeCurve } from "./graphLayout";
import "./KnowledgeGraph.css";

/**
 * @param nodes GraphNodeOut[]  @param edges GraphEdgeOut[]
 * @param highlightNodeLabels string[]  — node labels to highlight (from a query traversal)
 * @param highlightRelTypes string[]    — relationship types to highlight
 */
export default function KnowledgeGraph({ nodes, edges, highlightNodeLabels = [], highlightRelTypes = [] }) {
  const [selectedId, setSelectedId] = useState(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState(null);

  const { positions, width, height, NODE_RADIUS } = useMemo(() => layoutGraph(nodes), [nodes]);

  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);

  const queryHighlightSet = useMemo(() => new Set(highlightNodeLabels), [highlightNodeLabels]);
  const queryRelSet = useMemo(() => new Set(highlightRelTypes), [highlightRelTypes]);
  const hasQueryHighlight = queryHighlightSet.size > 0;

  const selectedNode = selectedId ? byId[selectedId] : null;

  const { connectedNodeIds, connectedEdgeIds } = useMemo(() => {
    if (!selectedId) return { connectedNodeIds: new Set(), connectedEdgeIds: new Set() };
    const nodeIds = new Set([selectedId]);
    const edgeIds = new Set();
    edges.forEach((e) => {
      if (e.source === selectedId || e.target === selectedId) {
        edgeIds.add(e.id);
        nodeIds.add(e.source);
        nodeIds.add(e.target);
      }
    });
    return { connectedNodeIds: nodeIds, connectedEdgeIds: edgeIds };
  }, [selectedId, edges]);

  const hasSelection = !!selectedId;

  // Bend duplicate edges between the same pair of columns apart so labels don't collide.
  const edgeBend = useMemo(() => {
    const seen = {};
    const map = {};
    edges.forEach((e) => {
      const key = [e.source, e.target].sort().join("|");
      seen[key] = (seen[key] || 0) + 1;
      map[e.id] = (seen[key] - 1) * 22 * (seen[key] % 2 === 0 ? -1 : 1);
    });
    return map;
  }, [edges]);

  function nodeState(id) {
    const label = byId[id]?.label;
    const queryHit = hasQueryHighlight && queryHighlightSet.has(label);
    if (hasSelection) {
      if (id === selectedId) return "selected";
      if (connectedNodeIds.has(id)) return "connected";
      return "dim";
    }
    if (hasQueryHighlight) return queryHit ? "query" : "dim-soft";
    return "default";
  }

  function edgeState(e) {
    if (hasSelection) return connectedEdgeIds.has(e.id) ? "connected" : "dim";
    if (hasQueryHighlight) {
      const bothEndsHit = queryHighlightSet.has(byId[e.source]?.label) && queryHighlightSet.has(byId[e.target]?.label);
      const relHit = queryRelSet.has(e.relationship_type);
      return bothEndsHit && relHit ? "query" : "dim-soft";
    }
    return "default";
  }

  return (
    <div className="kgraph">
      <div className="kgraph__toolbar">
        <div className="kgraph__legend">
          {TYPE_ORDER.filter((t) => nodes.some((n) => n.entity_type === t)).map((t) => (
            <span className="kgraph__legend-item" key={t}>
              <span className="kgraph__swatch" style={{ background: TYPE_COLOR[t] }} />
              {t}
            </span>
          ))}
        </div>
        {(hasSelection || hasQueryHighlight) && (
          <button className="btn btn--ghost kgraph__clear" onClick={() => setSelectedId(null)}>
            {hasSelection ? "Clear selection" : "Click a node to explore"}
          </button>
        )}
      </div>

      <div className="kgraph__canvas-wrap">
        <svg className="kgraph__svg" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label="Knowledge graph of entities and relationships">
          <defs>
            <marker id="kg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--paper-line-strong)" />
            </marker>
            <marker id="kg-arrow-active" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--clay)" />
            </marker>
          </defs>

          <g className="kgraph__edges">
            {edges.map((e) => {
              const s = positions[e.source]; const t = positions[e.target];
              if (!s || !t) return null;
              const state = edgeState(e);
              const bend = edgeBend[e.id] || 0;
              const d = edgeCurve(s.x, s.y, t.x, t.y, bend);
              const mx = (s.x + t.x) / 2;
              const my = (s.y + t.y) / 2 + bend * 0.5;
              const active = state === "connected" || state === "query";
              return (
                <g
                  key={e.id}
                  className={`kgraph__edge kgraph__edge--${state}`}
                  onMouseEnter={() => setHoveredEdgeId(e.id)}
                  onMouseLeave={() => setHoveredEdgeId(null)}
                >
                  <path d={d} fill="none" markerEnd={active ? "url(#kg-arrow-active)" : "url(#kg-arrow)"} />
                  {(active || hoveredEdgeId === e.id) && (
                    <g transform={`translate(${mx}, ${my})`}>
                      <rect x={-(e.label.length * 3.1)} y={-9} width={e.label.length * 6.2} height={15} rx={4} />
                      <text textAnchor="middle" dy="2.5">{e.label}</text>
                    </g>
                  )}
                </g>
              );
            })}
          </g>

          <g className="kgraph__nodes">
            {nodes.map((n) => {
              const p = positions[n.id];
              if (!p) return null;
              const state = nodeState(n.id);
              return (
                <g
                  key={n.id}
                  className={`kgraph__node kgraph__node--${state}`}
                  transform={`translate(${p.x}, ${p.y})`}
                  onClick={() => setSelectedId(n.id === selectedId ? null : n.id)}
                  tabIndex={0}
                  role="button"
                  aria-pressed={n.id === selectedId}
                  onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setSelectedId(n.id === selectedId ? null : n.id); } }}
                >
                  <circle r={NODE_RADIUS} fill={TYPE_COLOR[n.entity_type] || "var(--ink-faint)"} />
                  <text className="kgraph__node-label" x={NODE_RADIUS + 6} dy="3.5">{n.label}</text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      <div className="kgraph__detail">
        {selectedNode ? (
          <>
            <div className="kgraph__detail-head">
              <span className="kgraph__swatch" style={{ background: TYPE_COLOR[selectedNode.entity_type] }} />
              <strong>{selectedNode.label}</strong>
              <span className="badge">{selectedNode.entity_type}</span>
            </div>
            <ul className="kgraph__paths">
              {edges.filter((e) => e.source === selectedId || e.target === selectedId).map((e) => (
                <li key={e.id}>
                  <span className="mono">{byId[e.source]?.label}</span>
                  <span className="kgraph__paths-rel"> —{e.relationship_type}→ </span>
                  <span className="mono">{byId[e.target]?.label}</span>
                </li>
              ))}
            </ul>
          </>
        ) : hasQueryHighlight ? (
          <p className="kgraph__hint">Highlighted nodes and edges show the branch this query's traversal touched. Click any node to trace its full local neighborhood.</p>
        ) : (
          <p className="kgraph__hint">Click a node to highlight everything directly connected to it.</p>
        )}
      </div>
    </div>
  );
}
