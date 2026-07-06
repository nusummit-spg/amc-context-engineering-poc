export default function OntologyGraph({ ontology }) {
  const nodeColors = ontology.legend.map(l => l.color);
  const nodesById = {};
  ontology.nodes.forEach(n => { nodesById[n.id] = n; });

  const maxX = Math.max(...ontology.nodes.map(n => n.x)) + 90;
  const maxY = Math.max(...ontology.nodes.map(n => n.y)) + 50;

  return (
    <svg width="100%" viewBox={`0 0 ${maxX} ${maxY}`} style={{ maxHeight: 480 }}>
      {/* edges: line + label at midpoint */}
      {ontology.edges.map((e, i) => {
        const a = nodesById[e.from];
        const b = nodesById[e.to];
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2;
        return (
          <g key={i}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#d8c7f5" strokeWidth="1.4" />
            <text x={mx} y={my - 4} className="ont-edge-label" textAnchor="middle">{e.label}</text>
          </g>
        );
      })}

      {/* nodes: circle + wrapped label (labels can be multi-line via \n) */}
      {ontology.nodes.map((n) => {
        const color = nodeColors[n.type] || '#888';
        const lines = String(n.label).split('\n');
        const r = lines.some(l => l.length > 11) ? 32 : 26;
        return (
          <g key={n.id}>
            <circle cx={n.x} cy={n.y} r={r} fill={color} />
            {lines.map((l, i) => (
              <text
                key={i}
                x={n.x}
                y={n.y + (i - (lines.length - 1) / 2) * 9.5 + 3}
                className="ont-node-label"
                textAnchor="middle"
              >
                {l}
              </text>
            ))}
          </g>
        );
      })}
    </svg>
  );
}