import { useState, useEffect } from 'react';
import Header from './components/Header';
import QuerySelector from './components/QuerySelector';
import QueryInputPanel from './components/QueryInputPanel';
import TraditionalPanel from './components/TraditionalPanel';
import ContextGraphPanel from './components/ContextGraphPanel';
import DocumentModal from './components/DocumentModal';
import queries from './data/queries';
import corpusOntology from './data/ontology';
import { fetchTraditionalSearch, fetchContextGraphSearch } from './api/contextgraphApi';

function App() {
  const [mode, setMode] = useState('preset'); // 'preset' | 'custom'
  const [activeIndex, setActiveIndex] = useState(0);
  const [openDocId, setOpenDocId] = useState(null);

  // custom query mode — two fully independent result slots
  const [customText, setCustomText] = useState('');
  const [customTrad, setCustomTrad] = useState(null);
  const [customCg, setCustomCg] = useState(null);
  const [tradLoading, setTradLoading] = useState(false);
  const [cgLoading, setCgLoading] = useState(false);
  const [tradError, setTradError] = useState(null);
  const [cgError, setCgError] = useState(null);

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') setOpenDocId(null);
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  async function handleRunTraditional(text) {
    setTradLoading(true);
    setTradError(null);
    try {
      setCustomTrad(await fetchTraditionalSearch(text));
    } catch (err) {
      setTradError(err.message);
    } finally {
      setTradLoading(false);
    }
  }

  async function handleRunContextGraph(text) {
    setCgLoading(true);
    setCgError(null);
    try {
      setCustomCg(await fetchContextGraphSearch(text));
    } catch (err) {
      setCgError(err.message);
    } finally {
      setCgLoading(false);
    }
  }

  // Both panels always render from this single shape, whether the data
  // came from the preset buttons or from custom search results.
  const displayQuery = mode === 'preset'
    ? queries[activeIndex]
    : { full: customText || '(no query entered yet)', trad: customTrad, cg: customCg };

  const tradIsLoading = mode === 'custom' && tradLoading;
  const cgIsLoading = mode === 'custom' && cgLoading;

  return (
    <div className="wrap">
      <Header />

      <div className="mode-tabs">
        <button className={`mode-tab ${mode === 'preset' ? 'active' : ''}`} onClick={() => setMode('preset')}>
          Preset Demo Queries
        </button>
        <button className={`mode-tab ${mode === 'custom' ? 'active' : ''}`} onClick={() => setMode('custom')}>
          Custom Query
        </button>
      </div>

      {mode === 'preset' && (
        <QuerySelector queries={queries} activeIndex={activeIndex} onSelect={setActiveIndex} />
      )}

      {mode === 'custom' && (
        <QueryInputPanel
          text={customText}
          onTextChange={setCustomText}
          onRunTraditional={handleRunTraditional}
          onRunContextGraph={handleRunContextGraph}
          tradLoading={tradLoading}
          cgLoading={cgLoading}
        />
      )}

      {(tradError || cgError) && (
        <div className="query-error">
          {tradError && <div>Traditional search error: {tradError}</div>}
          {cgError && <div>ContextGraph search error: {cgError}</div>}
        </div>
      )}

      <div className="split">
        <TraditionalPanel query={displayQuery} loading={tradIsLoading} onFileClick={setOpenDocId} />
        <ContextGraphPanel query={displayQuery} ontology={corpusOntology} loading={cgIsLoading} onDocClick={setOpenDocId} />
      </div>

      <footer>Illustrative demo — NuSummit Context Engineering Platform · Asset Management / Mutual Fund scenario</footer>

      <DocumentModal docId={openDocId} onClose={() => setOpenDocId(null)} />
    </div>
  );
}

export default App;