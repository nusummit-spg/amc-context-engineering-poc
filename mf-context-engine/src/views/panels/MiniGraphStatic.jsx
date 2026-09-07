export default function MiniGraphStatic({ nodes, edges, matchedTexts, width = 460 }) {
  if (!nodes || nodes.length === 0) {
    return <div className="cg-graph-note">No graph nodes matched this query.</div>;
  }
  const cols = 4;
  const pos = {};
  nodes.forEach((n, i) => {
    pos[n] = [30 + (i % cols) * ((width - 60) / Math.max(cols - 1, 1)), 25 + Math.floor(i / cols) * 46];
  });
  const height = 25 + (Math.floor(nodes.length / cols) + 1) * 46;

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`}>
      {edges.map((e, i) => {
        if (!pos[e.s] || !pos[e.o]) return null;
        const [x1, y1] = pos[e.s];
        const [x2, y2] = pos[e.o];
        return (
          <g key={i}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#D8D2C4" strokeWidth="1" />
            <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 5} fontSize="8" fill="#1F3A5F" textAnchor="middle">
              {e.rel}
            </text>
          </g>
        );
      })}
      {nodes.map((n) => {
        const [x, y] = pos[n];
        const color = matchedTexts.includes(n) ? "#1F3A5F" : "#D8D2C4";
        return (
          <g key={n}>
            <circle cx={x} cy={y} r="6" fill={color} />
            <text x={x} y={y + 15} fontSize="8.5" fill="#5C574C" textAnchor="middle">
              {n.slice(0, 14)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
