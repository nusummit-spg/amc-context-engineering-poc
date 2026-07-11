// Query API layer.
//
// USE_MOCK toggles between the real FastAPI endpoints (default) and a canned
// response for rendering the page with zero backend. To use the mock, set
// VITE_USE_MOCK=true in frontend/.env.
//
// Calls are relative ("/api/...") so Vite's dev proxy (vite.config.js) forwards
// them to http://localhost:8000.

const USE_MOCK =
  (import.meta.env.VITE_USE_MOCK ?? 'false').toString().toLowerCase() === 'true';
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function postQuery(path, queryText) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: queryText }),
  });
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// --- adapters: backend QueryResponse -> frontend panel shapes ---

function toTradShape(resp) {
  const t = resp.traditional ?? {};
  const files = (t.files ?? []).map((f) => ({
    docId: f.document_id,
    icon: '📄',
    name: f.name,
    meta: `score ${f.score}`,
  }));
  return {
    files,
    snippet: t.snippet ?? '',
    warn: t.metrics?.note
      ?? 'No consolidated answer — each document must be reviewed individually.',
    metrics: [
      [String(t.metrics?.docs_returned ?? files.length), 'Documents returned'],
      [`${resp.latency_ms ?? 0} ms`, 'Latency'],
      [t.metrics?.consolidation ?? 'manual', 'Consolidation'],
    ],
  };
}

function toCgShape(resp) {
  const answer = resp.answer ?? {};
  const qt = resp.intent?.query_type;
  const type =
    qt === 'exposure_aggregation' ? 'exposure'
    : qt === 'compliance_check' ? 'compliance'
    : 'synthesis';

  const rows = (answer.structured_rows ?? []).map((r) => ({
    scheme: r.scheme ?? r.name ?? r.entity ?? '',
    detail: r.detail ?? r.note ?? r.description ?? '',
    pct: r.pct ?? r.percentage ?? r.value ?? '',
    sourceDoc: r.sourceDoc ?? r.document_id ?? r.source_document_id ?? null,
  }));

  return {
    type,
    rows,
    compliance: answer.compliance_note ?? `Confidence: ${answer.confidence ?? 'n/a'}`,
    narrative: answer.answer ?? '',
    graph: Boolean(resp.graph_highlight?.node_names?.length),
    metrics: [
      [`${resp.latency_ms ?? 0} ms`, 'Latency'],
      [String(resp.sources?.length ?? 0), 'Sources'],
      [answer.confidence ?? 'n/a', 'Confidence'],
    ],
  };
}

// --- canned mock responses (already in panel shape) ---

const MOCK_TRAD = {
  files: [
    { docId: 'DOC-001', icon: '📄', name: 'Adani_Exposure_Report_Q3.pdf', meta: 'score 0.88' },
    { docId: 'DOC-002', icon: '📝', name: 'Scheme_Holdings_Infra_Fund.docx', meta: 'score 0.81' },
    { docId: 'DOC-003', icon: '📊', name: 'Portfolio_NAV_Snapshot.xlsx', meta: 'score 0.77' },
  ],
  snippet: 'The Infra Fund holds Adani Green Energy at 5.8% of NAV as of Q3 …',
  warn: 'No consolidated answer — each document must be reviewed individually.',
  metrics: [['3', 'Documents returned'], ['~900 ms', 'Latency (mock)'], ['manual', 'Consolidation']],
};

const MOCK_CG = {
  type: 'exposure',
  rows: [
    { scheme: 'NuSummit Infra Fund', detail: 'Adani Green Energy', pct: '5.8%', sourceDoc: 'DOC-001' },
    { scheme: 'NuSummit Flexi Cap', detail: 'Adani Ports & SEZ', pct: '2.1%', sourceDoc: 'DOC-002' },
  ],
  compliance: 'Within single-issuer-group limits (SEBI 10% cap)',
  narrative:
    'Aggregated exposure to the <b>Adani Group</b> across all schemes is <b>7.9% of combined NAV</b>, '
    + 'driven mainly by the Infra Fund. [1][2]',
  graph: true,
  metrics: [['~2200 ms', 'Latency (mock)'], ['2', 'Sources'], ['high', 'Confidence']],
};

// --- public API ---

export async function fetchTraditionalSearch(queryText) {
  if (USE_MOCK) {
    await delay(900); // vector-only should be the faster of the two
    return MOCK_TRAD;
  }
  return toTradShape(await postQuery('/api/query/traditional', queryText));
}

export async function fetchContextGraphSearch(queryText) {
  if (USE_MOCK) {
    await delay(2200); // hybrid vector+graph+NER should visibly take longer
    return MOCK_CG;
  }
  return toCgShape(await postQuery('/api/query/contextgraph', queryText));
}
