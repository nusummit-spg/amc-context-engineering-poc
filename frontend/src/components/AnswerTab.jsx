import RelationshipGraph from './graphs/RelationshipGraph';

export default function AnswerTab({ query, loading, onRowClick }) {
  const c = query?.cg;

  return (
    <>
      <div style={{ fontSize: 12, color: 'var(--slate)', marginBottom: 12 }}>
        Query: <span style={{ color: 'var(--navy)', fontStyle: 'italic', fontWeight: 500 }}>"{query?.full}"</span>
      </div>

      {loading && <div className="panel-status">Running hybrid vector + graph + NER search…</div>}

      {!loading && !c && (
        <div className="panel-status">No results yet. Enter a query above and click "Run ContextGraph Search".</div>
      )}

      {!loading && c && (
        <>
          {(c.type === 'exposure' || c.type === 'compliance') ? (
            <div className="answer-card">
              <div className="label">
                {c.type === 'exposure' ? 'Structured Exposure (Graph DB)' : 'Compliance Status (Graph DB)'} — click a row to view source
              </div>
              {c.rows.map((r, i) => (
                <div className="row cg-clickable" key={i} onClick={() => onRowClick(r.sourceDoc)}>
                  <div>
                    <div className="scheme">{r.scheme}</div>
                    <div className="detail">{r.detail}</div>
                  </div>
                  <div className="pct">{r.pct}</div>
                </div>
              ))}
              <div className="compliance-pill">✓ {c.compliance}</div>
            </div>
          ) : (
            <div className="answer-card">
              <div className="label">Synthesis Source</div>
              <div style={{ fontSize: 13, color: 'var(--navy)', fontWeight: 600 }}>{c.compliance}</div>
            </div>
          )}

          <div className="narrative">
            <div className="label">Claude Synthesis (Vector + Graph)</div>
            <span dangerouslySetInnerHTML={{ __html: c.narrative }} />
          </div>

          {c.graph && (
            <div className="graphviz">
              <div className="label">Relationship Graph (live traversal)</div>
              <div className="gv-box"><RelationshipGraph /></div>
            </div>
          )}

          <div className="metrics">
            {c.metrics.map((m, i) => (
              <div className="metric" key={i}>
                <div className="num">{m[0]}</div>
                <div className="lbl">{m[1]}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}