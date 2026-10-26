// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// ===========================================================================

/**
 * Client-side mock engine fallbacks for comparison views when backend API is offline or unreachable.
 */

export function generateTraditionalResult(query) {
  const queryStr = String(query || "").trim();
  return {
    query: queryStr,
    answer: `Traditional Document Search match for: "${queryStr}". Retrieved relevant source passages from mutual fund scheme factsheets and regulatory documentation.`,
    docs: [
      {
        name: "Axis_Bluechip_Fund_Factsheet.pdf",
        document_id: "Axis_Bluechip_Fund_Factsheet.pdf",
        page: 2,
        score: 0.87,
        snippet: `Asset allocation and benchmark comparison data for ${queryStr}. Portfolio constituents and top sector holdings summary.`,
        full_text: `Axis Bluechip Fund Factsheet — Full excerpt regarding investment objectives, benchmark index performance against NIFTY 50 TRI, and expense ratios.`
      },
      {
        name: "SEBI_Mutual_Funds_Regulations_2026.pdf",
        document_id: "SEBI_Mutual_Funds_Regulations_2026.pdf",
        page: 8,
        score: 0.81,
        snippet: `Regulatory norms and disclosure requirements under SEBI circular guidelines applicable to ${queryStr}.`,
        full_text: `SEBI circular guidelines on scheme categorization, risk disclosure metrics, and governance requirements for asset management companies.`
      }
    ],
    total_time: 1.45,
    retrieve_time: 0.85,
    llm_time: 0.60,
    input_tokens: 412,
    output_tokens: 135,
    total_tokens: 547,
    telemetry_breakdown: {
      latency_vector_db_ms: 850,
      latency_llm_generation_ms: 600,
      tokens_input: 412,
      tokens_output: 135,
      tokens_total: 547,
      db_candidates_surfaced: 5,
      pipeline_mode: "Traditional Vector RAG (Client Fallback)"
    }
  };
}

export function generateHybridResult(query) {
  const queryStr = String(query || "").trim();
  return {
    query: queryStr,
    answer: `ContextGraph Hybrid RAG synthesis for "${queryStr}": Traversed relational knowledge graph connecting mutual fund schemes, fund managers, and SEBI regulatory requirements with vector passage attribution.`,
    docs: [
      {
        name: "Axis_Bluechip_Fund_Factsheet.pdf",
        document_id: "Axis_Bluechip_Fund_Factsheet.pdf",
        page: 2,
        page_num: 2,
        page_number: 2,
        score: 0.94,
        snippet: `Verified portfolio overlap and performance metrics for ${queryStr}.`,
        full_text: `Axis Bluechip Fund Factsheet — Context-verified passage with cryptographic ledger validation and entity grounding.`
      }
    ],
    graph_nodes: ["Axis Bluechip Fund", "Axis Asset Management Company", "NIFTY 50 TRI", "SEBI"],
    graph_rels: ["MANAGES", "BENCHMARKS_AGAINST", "REGULATED_BY"],
    graph_edges: [
      { s: "Axis Asset Management Company", rel: "MANAGES", o: "Axis Bluechip Fund", conf: 0.98 },
      { s: "Axis Bluechip Fund", rel: "BENCHMARKS_AGAINST", o: "NIFTY 50 TRI", conf: 0.99 },
      { s: "Axis Bluechip Fund", rel: "REGULATED_BY", o: "SEBI", conf: 1.0 }
    ],
    edges_used_in_prompt: [
      { s: "Axis Asset Management Company", rel: "MANAGES", o: "Axis Bluechip Fund", conf: 0.98 },
      { s: "Axis Bluechip Fund", rel: "BENCHMARKS_AGAINST", o: "NIFTY 50 TRI", conf: 0.99 }
    ],
    active_labels: ["Fund House", "Mutual Fund Scheme", "Benchmark Index", "Regulator"],
    confidence_label: "✓ High confidence",
    confidence_reason: "Supported by authoritative factsheet disclosure and SEBI circular matching.",
    total_time: 0.62,
    retrieve_time: 0.22,
    llm_time: 0.40,
    input_tokens: 210,
    output_tokens: 95,
    total_tokens: 305,
    telemetry_breakdown: {
      latency_vector_db_ms: 120,
      latency_graph_db_ms: 100,
      latency_llm_generation_ms: 400,
      tokens_input: 210,
      tokens_output: 95,
      tokens_total: 305,
      db_candidates_surfaced: 8,
      pipeline_mode: "ContextGraph Hybrid RAG (Client Fallback)",
      ui_badges: [
        { label: "Deterministic Graph Verified", type: "success" },
        { label: "Provenance Attributed", type: "primary" }
      ],
      triplet_table: [
        { subject: "Axis Asset Management Company", relation: "MANAGES", object: "Axis Bluechip Fund", confidence: "0.98" },
        { subject: "Axis Bluechip Fund", relation: "BENCHMARKS_AGAINST", object: "NIFTY 50 TRI", confidence: "0.99" }
      ]
    }
  };
}

export function getEntitySourceInfo(nodes = []) {
  const DEFAULT_MAP = {
    "Axis Bluechip Fund": { label: "Mutual Fund Scheme", source: "Axis_Bluechip_Fund_Factsheet.pdf", product_name: "Axis Bluechip Fund" },
    "Axis Asset Management Company": { label: "Fund House", source: "Axis_Bluechip_Fund_Factsheet.pdf", product_name: "Axis AMC" },
    "NIFTY 50 TRI": { label: "Benchmark Index", source: "NSE India / Index Methodology", product_name: "NIFTY 50" },
    "SEBI": { label: "Regulator", source: "SEBI Mutual Funds Regulations 1996", product_name: "SEBI" },
    "Adani Enterprises": { label: "Corporate Entity", source: "AEL_Annual_Return_FY_2024.pdf", product_name: "Adani Enterprises Ltd" },
    "EBITDA": { label: "Financial Metric", source: "Financial Statements / Annual Report", product_name: "Financials" },
    "NAV": { label: "Financial Metric", source: "Axis_Bluechip_Fund_Factsheet.pdf", product_name: "Net Asset Value" },
    "TER": { label: "Expense Ratio", source: "SEBI Master Circular 2024", product_name: "Total Expense Ratio" },
    "AUM": { label: "Fund Metric", source: "AMFI Monthly Disclosure", product_name: "Assets Under Management" },
    "Riskometer": { label: "Compliance Tag", source: "SEBI Circular on Product Labeling", product_name: "Very High Risk" },
  };

  const result = {};
  (nodes || []).forEach((node) => {
    if (DEFAULT_MAP[node]) {
      result[node] = DEFAULT_MAP[node];
    } else {
      result[node] = {
        label: "Entity",
        source: "Document Corpus / Knowledge Graph",
        product_name: node,
      };
    }
  });
  return result;
}

export function generateFullSubgraph(limit = 60) {
  const fullEdges = [
    { s: "Axis Asset Management Company", rel: "MANAGES", o: "Axis Bluechip Fund", conf: 0.98 },
    { s: "Axis Bluechip Fund", rel: "BENCHMARKS_AGAINST", o: "NIFTY 50 TRI", conf: 0.99 },
    { s: "Axis Bluechip Fund", rel: "REGULATED_BY", o: "SEBI", conf: 1.0 },
    { s: "Axis Bluechip Fund", rel: "REPORTS_METRIC", o: "NAV", conf: 0.95 },
    { s: "Axis Bluechip Fund", rel: "SUBJECT_TO_LIMIT", o: "TER", conf: 0.96 },
    { s: "Axis Bluechip Fund", rel: "HAS_RISK_RATING", o: "Riskometer", conf: 0.97 },
    { s: "Axis Asset Management Company", rel: "REPORTS_METRIC", o: "AUM", conf: 0.94 },
    { s: "Axis Asset Management Company", rel: "REGULATED_BY", o: "SEBI", conf: 1.0 },
    { s: "Adani Enterprises", rel: "REPORTS", o: "EBITDA", conf: 0.95 },
    { s: "Adani Enterprises", rel: "REGULATED_BY", o: "SEBI", conf: 1.0 },
    { s: "NIFTY 50 TRI", rel: "CONTAINS", o: "Adani Enterprises", conf: 0.92 },
    { s: "SEBI", rel: "ISSUES_REGULATION", o: "TER", conf: 0.98 },
    { s: "SEBI", rel: "MANDATES", o: "Riskometer", conf: 0.99 },
  ];

  const slicedEdges = fullEdges.slice(0, limit);
  const nodeSet = new Set();
  slicedEdges.forEach((e) => {
    nodeSet.add(e.s);
    nodeSet.add(e.o);
  });
  const nodes = Array.from(nodeSet).map((id) => ({ id, label: id }));

  return {
    nodes,
    edges: slicedEdges,
  };
}

