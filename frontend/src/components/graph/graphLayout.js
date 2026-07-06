// Deterministic swim-lane layout: one column per entity type, nodes stacked
// vertically within their column. No physics simulation — this keeps the
// diagram legible and stable across renders, which matters more than
// organic spacing for a "how does the retrieval traverse this" explainer.

export const TYPE_ORDER = [
  "Scheme", "Issuer", "IssuerGroup", "Sector",
  "RiskTheme", "ClauseType", "RegulatoryCircular", "Analyst", "Document",
];

export const TYPE_COLOR = {
  Scheme: "#BD5B3F",
  Issuer: "#35506B",
  IssuerGroup: "#7C3F2E",
  Sector: "#4C6B4E",
  RiskTheme: "#A9762A",
  ClauseType: "#8A7355",
  RegulatoryCircular: "#2E6E6A",
  Analyst: "#6B5B95",
  Document: "#6E6858",
};

const COL_WIDTH = 168;
const ROW_HEIGHT = 64;
const MARGIN_X = 90;
const MARGIN_Y = 44;
const NODE_RADIUS = 9;

export function layoutGraph(nodes) {
  const byType = {};
  TYPE_ORDER.forEach((t) => { byType[t] = []; });
  nodes.forEach((n) => {
    if (!byType[n.entity_type]) byType[n.entity_type] = [];
    byType[n.entity_type].push(n);
  });

  const positions = {};
  let maxRows = 0;
  TYPE_ORDER.forEach((type, colIdx) => {
    const list = byType[type] || [];
    list.sort((a, b) => a.label.localeCompare(b.label));
    maxRows = Math.max(maxRows, list.length);
    list.forEach((n, rowIdx) => {
      positions[n.id] = {
        x: MARGIN_X + colIdx * COL_WIDTH,
        y: MARGIN_Y + rowIdx * ROW_HEIGHT,
        col: colIdx,
        row: rowIdx,
      };
    });
  });

  const width = MARGIN_X * 2 + (TYPE_ORDER.length - 1) * COL_WIDTH;
  const height = MARGIN_Y * 2 + Math.max(maxRows - 1, 0) * ROW_HEIGHT;

  return { positions, width: Math.max(width, 640), height: Math.max(height, 320), NODE_RADIUS };
}

export function edgeCurve(x1, y1, x2, y2, bend = 0) {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2 + bend;
  return `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`;
}
