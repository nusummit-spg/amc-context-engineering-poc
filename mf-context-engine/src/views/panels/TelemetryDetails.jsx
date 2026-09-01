export default function TelemetryDetails({ t }) {
  if (!t) return null;
  const fmt = (n) => (n ?? 0).toFixed(1);
  return (
    <details className="cg-telemetry-details">
      <summary>⚡ Microsecond Telemetry &amp; Execution Ledger</summary>
      <table className="cg-telemetry-table">
        <tbody>
          <tr>
            <td><b>Vector DB Lookup (FAISS)</b></td>
            <td>{fmt(t.latency_vector_db_ms)} ms</td>
          </tr>
          {t.latency_rerank_ms > 0 && (
            <tr>
              <td><b>Cross-Encoder Reranking</b></td>
              <td>{fmt(t.latency_rerank_ms)} ms</td>
            </tr>
          )}
          <tr>
            <td><b>Graph Traversal (Neo4j UNWIND)</b></td>
            <td>{fmt(t.latency_graph_db_ms)} ms</td>
          </tr>
          <tr>
            <td><b>NER &amp; Entity Resolution</b></td>
            <td>{fmt(t.latency_ner_processing_ms)} ms</td>
          </tr>
          {t.latency_cypher_generation_ms > 0 && (
            <tr>
              <td><b>Cypher Generation (LLM + Neo4j exec)</b></td>
              <td>{fmt(t.latency_cypher_generation_ms)} ms</td>
            </tr>
          )}
          <tr>
            <td><b>Post-Retrieval Pruning / Table Prep</b></td>
            <td>{fmt(t.latency_post_retrieval_processing_ms)} ms</td>
          </tr>
          <tr>
            <td><b>LLM Synthesis Latency</b></td>
            <td>{fmt(t.latency_llm_generation_ms)} ms</td>
          </tr>
          <tr className="total">
            <td><b>Total Pipeline Execution</b></td>
            <td>{fmt(t.latency_total_pipeline_ms)} ms</td>
          </tr>
          <tr>
            <td><b>Tokens (Input / Output / Total)</b></td>
            <td>
              <b>{(t.tokens_input ?? 0).toLocaleString()}</b> in / <b>{(t.tokens_output ?? 0).toLocaleString()}</b> out / <b>{(t.tokens_total ?? 0).toLocaleString()}</b>
            </td>
          </tr>
          {t.cache_hit && (
            <tr className="savings">
              <td><b>Token Savings (Vs Cold Run)</b></td>
              <td><b>{(t.tokens_saved ?? 0).toLocaleString()} tokens saved</b> ({(t.tokens_cold_equivalent ?? 0).toLocaleString()} cold equiv)</td>
            </tr>
          )}
          <tr>
            <td><b>DB Candidates Surfaced</b></td>
            <td>{t.db_candidates_surfaced ?? 0} {(t.pipeline_mode || "").includes("ContextGraph") ? "nodes" : "chunks"}</td>
          </tr>
          <tr>
            <td><b>Vector Noise Bypassed (Pillar 1)</b></td>
            <td style={{ fontWeight: "bold", color: t.vector_bypassed ? "#3F6B42" : "#8A8378" }}>
              {String(!!t.vector_bypassed).toUpperCase()}
            </td>
          </tr>
        </tbody>
      </table>
    </details>
  );
}
