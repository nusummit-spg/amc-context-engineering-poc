import OntologyGraph from './graphs/OntologyGraph';
import documents from '../data/documents';

export default function OntologyTab({ ontology, onDocClick }) {
  return (
    <>
      <div className="ont-header">
        The full knowledge graph ContextGraph builds once, from ingesting all <b>21 source documents</b>
        {' '}across the AMC's research, compliance, and investor-communication corpus. Every query
        (Adani exposure, SEBI circular, NBFC house view) traverses a subset of this same graph —
        it is not rebuilt per query.
      </div>

      <div className="ont-stats">
        {ontology.nodeTypeCounts.map((s, i) => (
          <div className="ont-stat" key={i}>
            <div className="ont-stat-dot" style={{ background: s.color }}></div>
            <div className="ont-stat-num">{s.count}</div>
            <div className="ont-stat-lbl">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="ont-legend">
        {ontology.legend.map((l, i) => (
          <div className="item" key={i}>
            <span className="sw" style={{ background: l.color }}></span>
            {l.label}
          </div>
        ))}
      </div>

      <div className="ont-svg-box">
        <OntologyGraph ontology={ontology} />
      </div>

      <div className="ont-section-label">Entities Resolved Across Documents — click to view sources</div>
      {ontology.sourceMap.map((s, i) => (
        <div className="ont-path-card" key={i}>
          <div className="pathline">
            {s.entity} <span style={{ color: 'var(--slate)', fontWeight: 500 }}>— appears in {s.count} documents</span>
          </div>
          <div className="ont-doc-chips">
            {s.docs.map((docId) => (
              <span className="ont-doc-chip" key={docId} onClick={() => onDocClick(docId)}>
                {documents[docId].title}
              </span>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}