import { useState } from 'react';
import AnswerTab from './AnswerTab';
import OntologyTab from './OntologyTab';

export default function ContextGraphPanel({ query, ontology, loading, onDocClick }) {
  const [tab, setTab] = useState('answer');

  return (
    <section className="panel cg">
      <div className="panel-head">
        <div className="dot"></div>
        <h2>NuSummit ContextGraph</h2>
        <div className="tag">Taxonomy-scoped hybrid retrieval</div>
      </div>

      <div className="cg-tabs">
        <button className={`cg-tab ${tab === 'answer' ? 'active' : ''}`} onClick={() => setTab('answer')}>Answer</button>
        <button className={`cg-tab ${tab === 'ontology' ? 'active' : ''}`} onClick={() => setTab('ontology')}>Ontology View</button>
      </div>

      <div className="panel-body" style={{ display: tab === 'answer' ? 'flex' : 'none' }}>
        <AnswerTab query={query} loading={loading} onRowClick={onDocClick} />
      </div>
      <div className="panel-body" style={{ display: tab === 'ontology' ? 'flex' : 'none' }}>
        <OntologyTab ontology={ontology} onDocClick={onDocClick} />
      </div>
    </section>
  );
}