import { useState } from "react";

/**
 * Deterministic radial layout: nodes the query matched sit on an inner ring,
 * the surrounding one-hop context on an outer ring. Reads far better than a
 * fixed grid because edges radiate outward instead of criss-crossing rows.
 */
function layout(nodes, matched, width, height) {
  const cx = width / 2;
  const cy = height / 2;
  const inner = nodes.filter((n) => matched.includes(n));
  const outer = nodes.filter((n) => !matched.includes(n));
  const pos = {};

  const place = (list, radiusX, radiusY, offset) => {
    list.forEach((n, i) => {
      if (list.length === 1) {
        pos[n] = [cx, cy - (offset ? radiusY : 0)];
        return;
      }
      const angle = offset + (i / list.length) * Math.PI * 2;
      pos[n] = [cx + Math.cos(angle) * radiusX, cy + Math.sin(angle) * radiusY];
    });
  };

  if (inner.length === 1 && outer.length > 0) {
    pos[inner[0]] = [cx, cy];
  } else {
    place(inner, width * 0.17, height * 0.17, -Math.PI / 2);
  }
  place(outer, width * 0.38, height * 0.36, -Math.PI / 2 + Math.PI / Math.max(outer.length, 1));

  return pos;
}

export default function OntologyGraph({ nodes = [], edges = [], matchedTexts = [], width = 640, height = 340 }) {
  const [hovered, setHovered] = useState(null);

  if (!nodes.length) {
    return <div className="cg-graph-note">No graph nodes matched this query.</div>;
  }

  const pos = layout(nodes, matchedTexts, width, height);
  const isMatched = (n) => matchedTexts.includes(n);
  const connected = (n) =>
    hovered && (n === hovered || edges.some((e) => (e.s === hovered && e.o === n) || (e.o === hovered && e.s === n)));

  const truncate = (s, len = 18) => (s.length > len ? `${s.slice(0, len)}…` : s);

  return (
    <div className="cg-ograph">
      <svg
        className="cg-ograph-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Graph of ${nodes.length} entities and ${edges.length} relationships`}
      >
        {edges.map((e, i) => {
          if (!pos[e.s] || !pos[e.o]) return null;
          const [x1, y1] = pos[e.s];
          const [x2, y2] = pos[e.o];
          const active = hovered && (e.s === hovered || e.o === hovered);
          const dim = hovered && !active;
          return (
            <g key={i} className={`cg-ograph-edge ${active ? "is-active" : ""} ${dim ? "is-dim" : ""}`}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} />
              <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 5} textAnchor="middle">
                {e.rel}
              </text>
            </g>
          );
        })}

        {nodes.map((n) => {
          const [x, y] = pos[n];
          const matched = isMatched(n);
          const dim = hovered && !connected(n);
          return (
            <g
              key={n}
              className={`cg-ograph-node ${matched ? "is-matched" : ""} ${dim ? "is-dim" : ""}`}
              onMouseEnter={() => setHovered(n)}
              onMouseLeave={() => setHovered(null)}
              tabIndex={0}
              onFocus={() => setHovered(n)}
              onBlur={() => setHovered(null)}
            >
              <title>{n}</title>
              <circle cx={x} cy={y} r={matched ? 8 : 6} />
              <text x={x} y={y + 20} textAnchor="middle">
                {truncate(n)}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="cg-ograph-legend">
        <span className="cg-ograph-legend-item">
          <span className="cg-ograph-swatch cg-ograph-swatch--matched" />
          Matched by this query ({nodes.filter(isMatched).length})
        </span>
        <span className="cg-ograph-legend-item">
          <span className="cg-ograph-swatch" />
          Surrounding context ({nodes.filter((n) => !isMatched(n)).length})
        </span>
      </div>
    </div>
  );
}
