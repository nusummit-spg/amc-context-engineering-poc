import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { useResource } from "../../hooks/useResource";
import { DEMO_QUERIES, MOCK_TAXONOMY, MOCK_GRAPH } from "../../data/mockData";
import TaxonomyTree from "../taxonomy/TaxonomyTree";
import KnowledgeGraph from "../graph/KnowledgeGraph";
import { SkeletonBlock, SkeletonCards } from "../common/Skeleton";
import { ErrorBanner, DemoModeNotice } from "../common/Banners";
import "./ComparePage.css";

function emptySide() {
  return { data: null, loading: false, error: null, isMock: false };
}

export default function ComparePage({ onOpenDocument, refreshKey = 0 }) {
  const [mode, setMode] = useState("demo");
  const [demoIdx, setDemoIdx] = useState(0);
  const [customQuery, setCustomQuery] = useState("");
  const [trad, setTrad] = useState(emptySide());
  const [cg, setCg] = useState(emptySide());
  const [cgTab, setCgTab] = useState("answer");

  // refreshKey changes the moment the backend flips demo <-> live (or a real
  // ingest finishes), so these re-fetch immediately instead of staying stuck
  // on whatever they resolved to on first mount.
  const taxonomyRes = useResource(
    (signal) => api.getTaxonomyTree(signal),
    { deps: [refreshKey], mockValue: MOCK_TAXONOMY }
  );
  const graphRes = useResource(
    (signal) => api.getFullGraph(500, signal),
    { deps: [refreshKey], mockValue: MOCK_GRAPH }
  );

  const demoResponse = DEMO_QUERIES[demoIdx].response;
  const queryText = mode === "demo" ? demoResponse.query : customQuery;
  const tradResult = mode === "demo" ? demoResponse.traditional : trad.data;
  const cgResult = mode === "demo" ? demoResponse : cg.data;
  const tradLoading = mode === "custom" && trad.loading;
  const cgLoading = mode === "custom" && cg.loading;
  const tradIsMock = mode === "custom" && trad.isMock;
  const cgIsMock = mode === "custom" && cg.isMock;

  async function runTraditional(e) {
    e.preventDefault();
    if (!customQuery.trim()) return;
    setMode("custom");
    setTrad({ ...emptySide(), loading: true });
    try {
      const res = await api.runQuery({ query: customQuery, mode: "traditional" });
      setTrad({ data: res.traditional || res, loading: false, error: null, isMock: false });
    } catch (err) {
      if (err instanceof ApiError && (err.status === 0 || err.status === 502)) {
        setTrad({ data: DEMO_QUERIES[0].response.traditional, loading: false, error: null, isMock: true });
      } else {
        setTrad({ data: null, loading: false, error: err, isMock: false });
      }
    }
  }

  async function runContextGraph(e) {
    e.preventDefault();
    if (!customQuery.trim()) return;
    setMode("custom");
    setCg({ ...emptySide(), loading: true });
    try {
      const res = await api.runQuery({ query: customQuery, mode: "contextgraph" });
      setCg({ data: res, loading: false, error: null, isMock: false });
    } catch (err) {
      if (err instanceof ApiError && (err.status === 0 || err.status === 502)) {
        setCg({ data: DEMO_QUERIES[0].response, loading: false, error: null, isMock: true });
      } else {
        setCg({ data: null, loading: false, error: err, isMock: false });
      }
    }
  }

  // The demo fixtures use `traversal.{highlight_nodes,highlight_relationships}`;
  // the live backend's /query response instead returns a flat `graph_highlight`
  // object with `{node_names, relationships}` (see backend/app/schemas/api.py:
  // QueryResponse.graph_highlight). Read both shapes so the Ontology View
  // highlights correctly whether the answer came from demo data or a live query.
  const highlightNodes =
    cgResult?.traversal?.highlight_nodes || cgResult?.graph_highlight?.node_names || [];
  const highlightRels =
    cgResult?.traversal?.highlight_relationships || cgResult?.graph_highlight?.relationships || [];
  const taxonomyPaths = cgResult?.intent?.taxonomy_paths || cgResult?.taxonomy_paths || [];

  return (
    <div className="compare">
      <div className="card compare__intro">
        <div className="compare__query-picker">
          <div className="compare__demo-tabs" role="tablist" aria-label="Demo query">
            {DEMO_QUERIES.map((q, i) => (
              <button
                key={q.id}
                role="tab"
                aria-selected={mode === "demo" && demoIdx === i}
                className={`compare__demo-tab ${mode === "demo" && demoIdx === i ? "is-active" : ""}`}
                onClick={() => { setMode("demo"); setDemoIdx(i); }}
              >
                <span className="eyebrow">Demo {i + 1}</span>
                {q.label}
              </button>
            ))}
          </div>
          <form className="compare__custom-form">
            <input
              type="text"
              placeholder="Or type your own query and run it against both search modes…"
              value={mode === "custom" ? customQuery : customQuery}
              onChange={(e) => setCustomQuery(e.target.value)}
            />
            <div className="compare__run-buttons">
              <button className="btn btn--ghost" onClick={runTraditional} disabled={!customQuery.trim() || trad.loading}>
                {trad.loading ? "Searching…" : "Run Traditional"}
              </button>
              <button className="btn btn--clay" onClick={runContextGraph} disabled={!customQuery.trim() || cg.loading}>
                {cg.loading ? "Searching…" : "Run ContextGraph"}
              </button>
            </div>
          </form>
        </div>
        <p className="compare__query-text">
          <span className="eyebrow">Query</span> "{queryText || "(no query yet — pick a demo above or type your own)"}"
        </p>
      </div>

      <div className="compare__grid">
        <TraditionalColumn
          result={tradResult}
          loading={tradLoading}
          error={mode === "custom" ? trad.error : null}
          isMock={tradIsMock}
          onRetry={runTraditional}
          onOpenDocument={onOpenDocument}
        />

        <div className="card compare__col compare__col--cg">
          <div className="compare__col-head">
            <span className="compare__dot compare__dot--cg" />
            <h3>ContextGraph</h3>
            <span className="badge badge--clay">hybrid graph + vector</span>
          </div>

          <div className="compare__cg-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={cgTab === "answer"}
              className={`compare__cg-tab ${cgTab === "answer" ? "is-active" : ""}`}
              onClick={() => setCgTab("answer")}
            >
              Answer
            </button>
            <button
              role="tab"
              aria-selected={cgTab === "graph"}
              className={`compare__cg-tab ${cgTab === "graph" ? "is-active" : ""}`}
              onClick={() => setCgTab("graph")}
            >
              Ontology View
            </button>
          </div>

          {mode === "custom" && cg.error && (
            <ErrorBanner error={cg.error} title="ContextGraph search failed" onRetry={runContextGraph} />
          )}

          {cgTab === "answer" && (
            <AnswerTab result={cgResult} loading={cgLoading} isMock={cgIsMock} onOpenDocument={onOpenDocument} />
          )}

          {cgTab === "graph" && (
            <OntologyTab
              taxonomyRes={taxonomyRes}
              graphRes={graphRes}
              taxonomyPaths={taxonomyPaths}
              highlightNodes={highlightNodes}
              highlightRels={highlightRels}
              hasResult={!!cgResult}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function TraditionalColumn({ result, loading, error, isMock, onRetry, onOpenDocument }) {
  return (
    <div className="card compare__col compare__col--trad">
      <div className="compare__col-head">
        <span className="compare__dot compare__dot--trad" />
        <h3>Traditional Document Search</h3>
        <span className="badge">vector-only</span>
      </div>

      {isMock && <DemoModeNotice compact />}
      {error && <ErrorBanner error={error} title="Traditional search failed" onRetry={onRetry} />}
      {loading && <SkeletonCards count={3} />}

      {!loading && !error && !result && (
        <p className="compare__empty">No results yet. Pick a demo query above, or enter your own and click "Run Traditional".</p>
      )}

      {!loading && result && (
        <>
          <span className="eyebrow">Files returned, ranked by similarity — click to open</span>
          <ul className="compare__filelist">
            {(result.files || []).map((f) => (
              <li key={f.document_id || f.name}>
                <button className="compare__file" onClick={() => onOpenDocument?.(f.document_id)}>
                  <span className="compare__file-name">{f.name}</span>
                  <span className="badge badge--blue">score {f.score}</span>
                </button>
                {f.snippet && <p className="compare__snippet">"{f.snippet}"</p>}
              </li>
            ))}
          </ul>

          {result.metrics?.note && (
            <div className="compare__warn">
              <span aria-hidden="true">⚠</span>
              <span>{result.metrics.note}</span>
            </div>
          )}

          <div className="compare__metric-row">
            <Metric label="Docs returned" value={result.metrics?.docs_returned ?? (result.files || []).length} />
            <Metric label="Consolidation" value={result.metrics?.consolidation || "manual"} />
          </div>
        </>
      )}
    </div>
  );
}

function AnswerTab({ result, loading, isMock, onOpenDocument }) {
  if (loading) return <SkeletonBlock height={220} />;
  if (!result) {
    return <p className="compare__empty">No results yet. Pick a demo query above, or enter your own and click "Run ContextGraph".</p>;
  }
  const a = result.answer;
  return (
    <div className="compare__answer">
      {isMock && <DemoModeNotice compact />}

      {a ? (
        <>
          <span className={`badge badge--${a.confidence === "high" ? "moss" : a.confidence === "medium" ? "amber" : ""}`}>
            {a.confidence} confidence
          </span>
          <p className="compare__answer-text">{a.answer}</p>

          {a.structured_rows?.length > 0 && (
            <div className="compare__table-wrap">
              <table className="compare__table">
                <thead>
                  <tr>{Object.keys(a.structured_rows[0]).map((k) => <th key={k}>{k.replace(/_/g, " ")}</th>)}</tr>
                </thead>
                <tbody>
                  {a.structured_rows.map((row, i) => (
                    <tr key={i}>{Object.values(row).map((v, j) => <td key={j}>{v === null || v === undefined ? "—" : String(v)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {a.compliance_note && (
            <div className="compare__compliance">
              <span className="eyebrow">Compliance note</span>
              <p>{a.compliance_note}</p>
            </div>
          )}

          {a.citations?.length > 0 && (
            <div className="compare__citations">
              <span className="eyebrow">Sources — click to open</span>
              <ul>
                {a.citations.map((c) => {
                  const src = result.sources?.find((s) => s.source_index === c.source_index);
                  return (
                    <li key={c.source_index}>
                      <button className="compare__source-btn" onClick={() => src && onOpenDocument?.(src.document_id)}>
                        [{c.source_index}] {c.document_title}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="compare__empty">No synthesis returned for this query.</p>
      )}
    </div>
  );
}

function OntologyTab({ taxonomyRes, graphRes, taxonomyPaths, highlightNodes, highlightRels, hasResult }) {
  return (
    <div className="compare__ontology">
      <p className="compare__ontology-note">
        ContextGraph builds this knowledge graph once from the full ingested corpus. Every query traverses a
        subset of the same graph — it is not rebuilt per query. {hasResult ? "The branch and nodes touched by the current query are highlighted below." : "Run a query to see its traversal highlighted here."}
      </p>

      <div className="compare__ontology-grid">
        <div className="compare__ontology-panel">
          <h4>Taxonomy branch activated</h4>
          {taxonomyRes.isMock && <DemoModeNotice compact />}
          {taxonomyRes.loading ? <SkeletonBlock height={200} /> : taxonomyRes.error ? (
            <ErrorBanner error={taxonomyRes.error} onRetry={taxonomyRes.reload} />
          ) : (
            <div className="compare__mini-tree">
              <TaxonomyTree roots={taxonomyRes.data.roots} highlightedPaths={taxonomyPaths} />
            </div>
          )}
        </div>

        <div className="compare__ontology-panel">
          <h4>Graph nodes touched</h4>
          {graphRes.isMock && <DemoModeNotice compact />}
          {graphRes.loading ? <SkeletonBlock height={200} /> : graphRes.error ? (
            <ErrorBanner error={graphRes.error} onRetry={graphRes.reload} />
          ) : (
            <div className="compare__mini-graph">
              <KnowledgeGraph
                nodes={graphRes.data.nodes}
                edges={graphRes.data.edges}
                highlightNodeLabels={highlightNodes}
                highlightRelTypes={highlightRels}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, tone }) {
  return (
    <div className={`compare__metric ${tone ? `compare__metric--${tone}` : ""}`}>
      <span className="compare__metric-value">{value}</span>
      <span className="compare__metric-label">{label}</span>
    </div>
  );
}
