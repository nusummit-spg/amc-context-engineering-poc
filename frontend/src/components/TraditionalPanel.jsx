export default function TraditionalPanel({ query, loading, onFileClick }) {
  const t = query?.trad;

  return (
    <section className="panel trad">
      <div className="panel-head">
        <div className="dot"></div>
        <h2>Traditional Document Search</h2>
        <div className="tag">Click any file to open it</div>
      </div>
      <div className="panel-body">
        <div style={{ fontSize: 12, color: '#8a8a98', marginBottom: 12 }}>
          Query: <span style={{ color: '#cfcfe0', fontStyle: 'italic' }}>"{query?.full}"</span>
        </div>

        {loading && <div className="panel-status">Running vector search…</div>}

        {!loading && !t && (
          <div className="panel-status">No results yet. Enter a query above and click "Run Traditional Search".</div>
        )}

        {!loading && t && (
          <>
            <div className="filelist">
              {t.files.map((f, i) => (
                <div key={f.docId} className="fileitem" style={{ animationDelay: `${i * 0.06}s` }} onClick={() => onFileClick(f.docId)}>
                  <span className="ic">{f.icon}</span>
                  <span className="name">{f.name}</span>
                  <span className="meta">{f.meta}</span>
                </div>
              ))}
            </div>
            <div className="trad-snippet">{t.snippet}</div>
            <div className="trad-warn">
              <span className="ic">⚠</span>
              <span>{t.warn}</span>
            </div>
            <div className="trad-metrics">
              {t.metrics.map((m, i) => (
                <div className="metric" key={i}>
                  <div className="num">{m[0]}</div>
                  <div className="lbl">{m[1]}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}