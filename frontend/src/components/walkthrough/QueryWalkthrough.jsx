import { useState } from "react";
import { api } from "../../api/client";
import { useResource } from "../../hooks/useResource";
import { DEMO_QUERIES, MOCK_TAXONOMY, MOCK_GRAPH } from "../../data/mockData";
import TaxonomyTree from "../taxonomy/TaxonomyTree";
import KnowledgeGraph from "../graph/KnowledgeGraph";
import { SkeletonBlock, SkeletonTree } from "../common/Skeleton";
import { ErrorBanner, DemoModeNotice } from "../common/Banners";
import "./QueryWalkthrough.css";

const STEPS = [
  { id: 1, label: "Intent & Entity Resolution", eyebrow: "Step 1 / 4" },
  { id: 2, label: "Graph Traversal", eyebrow: "Step 2 / 4" },
  { id: 3, label: "Context Assembly", eyebrow: "Step 3 / 4" },
  { id: 4, label: "Synthesis", eyebrow: "Step 4 / 4" },
];

function normalizeLiveResult(queryResponse, traversalResponse) {
  return {
    query: queryResponse.query,
    intent: queryResponse.intent,
    resolved_entities: {},
    traversal: {
      highlight_nodes: queryResponse.graph_highlight?.node_names || traversalResponse?.highlight_nodes || [],
      highlight_relationships: queryResponse.graph_highlight?.relationships || traversalResponse?.highlight_relationships || [],
      traversal_paths: queryResponse.traversal_paths || [],
      cypher_templates: traversalResponse?.cypher_templates || [],
    },
    context_debug: queryResponse.context_debug,
    sources: queryResponse.sources || [],
    answer: queryResponse.answer,
    traditional: queryResponse.traditional,
    latency_ms: queryResponse.latency_ms,
  };
}

export default function QueryWalkthrough({ onOpenDocument }) {
  const [mode, setMode] = useState("demo"); // "demo" | "custom"
  const [demoIdx, setDemoIdx] = useState(0);
  const [step, setStep] = useState(1);
  const [customQuery, setCustomQuery] = useState("");
  const [customResult, setCustomResult] = useState(null);
  const [customState, setCustomState] = useState({ loading: false, error: null });

  const taxonomyRes = useResource(
    (signal) => api.getTaxonomyTree(signal),
    { deps: [], mockValue: MOCK_TAXONOMY }
  );
  const graphRes = useResource(
    (signal) => api.getFullGraph(500, signal),
    { deps: [], mockValue: MOCK_GRAPH }
  );

  const result = mode === "demo" ? DEMO_QUERIES[demoIdx].response : customResult;

  async function runCustomQuery(e) {
    e.preventDefault();
    if (!customQuery.trim()) return;
    setMode("custom");
    setStep(1);
    setCustomState({ loading: true, error: null });
    try {
      const [queryResp, traversalResp] = await Promise.all([
        api.runQuery({ query: customQuery, mode: "both" }),
        api.getTraversalHighlight(customQuery).catch(() => null),
      ]);
      setCustomResult(normalizeLiveResult(queryResp, traversalResp));
      setCustomState({ loading: false, error: null });
    } catch (err) {
      setCustomState({ loading: false, error: err });
    }
  }

  const taxonomyPaths = result?.intent?.taxonomy_paths || [];
  const highlightNodes = result?.traversal?.highlight_nodes || [];
  const highlightRels = result?.traversal?.highlight_relationships || [];

  return (
    <div className="walkthrough">
      <div className="walkthrough__intro card">
        <div className="walkthrough__query-picker">
          <div className="walkthrough__demo-tabs" role="tablist" aria-label="Demo query">
            {DEMO_QUERIES.map((q, i) => (
              <button
                key={q.id}
                role="tab"
                aria-selected={mode === "demo" && demoIdx === i}
                className={`walkthrough__demo-tab ${mode === "demo" && demoIdx === i ? "is-active" : ""}`}
                onClick={() => { setMode("demo"); setDemoIdx(i); setStep(1); }}
              >
                <span className="eyebrow">Demo {i + 1}</span>
                {q.label}
              </button>
            ))}
          </div>
          <form className="walkthrough__custom-form" onSubmit={runCustomQuery}>
            <input
              type="text"
              placeholder="Or run your own query against the live API…"
              value={customQuery}
              onChange={(e) => setCustomQuery(e.target.value)}
            />
            <button className="btn btn--clay" type="submit" disabled={customState.loading}>
              {customState.loading ? "Running…" : "Run"}
            </button>
          </form>
        </div>
        <p className="walkthrough__query-text">
          <span className="eyebrow">Query</span> “{result?.query || customQuery}”
        </p>
      </div>

      {mode === "custom" && customState.error && (
        <ErrorBanner error={customState.error} title="Query failed" onRetry={() => runCustomQuery({ preventDefault(){} })} />
      )}

      {(!result || (mode === "custom" && customState.loading)) ? (
        <SkeletonBlock height={220} />
      ) : (
        <>
          <ol className="walkthrough__stepper" aria-label="Retrieval steps">
            {STEPS.map((s) => (
              <li key={s.id}>
                <button
                  className={`walkthrough__step ${step === s.id ? "is-active" : ""} ${step > s.id ? "is-done" : ""}`}
                  onClick={() => setStep(s.id)}
                >
                  <span className="walkthrough__step-num">{s.id}</span>
                  <span>
                    <span className="walkthrough__step-eyebrow eyebrow">{s.eyebrow}</span>
                    <span className="walkthrough__step-label">{s.label}</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>

          <div className="walkthrough__grid">
            <div className="card walkthrough__step-panel">
              <StepBody step={step} result={result} onOpenDocument={onOpenDocument} />
              <div className="walkthrough__nav">
                <button className="btn btn--ghost" disabled={step === 1} onClick={() => setStep((s) => s - 1)}>← Previous</button>
                <button className="btn btn--ghost" disabled={step === 4} onClick={() => setStep((s) => s + 1)}>Next →</button>
              </div>
            </div>

            <div className="walkthrough__side">
              <div className="card walkthrough__side-panel">
                <h4>Taxonomy branch activated</h4>
                {taxonomyRes.isMock && <DemoModeNotice compact />}
                {taxonomyRes.loading ? <SkeletonTree rows={4} /> : taxonomyRes.error ? (
                  <ErrorBanner error={taxonomyRes.error} onRetry={taxonomyRes.reload} />
                ) : (
                  <div className="walkthrough__mini-tree">
                    <TaxonomyTree roots={taxonomyRes.data.roots} highlightedPaths={taxonomyPaths} />
                  </div>
                )}
              </div>

              <div className="card walkthrough__side-panel">
                <h4>Graph nodes touched</h4>
                {graphRes.isMock && <DemoModeNotice compact />}
                {graphRes.loading ? <SkeletonBlock height={180} /> : graphRes.error ? (
                  <ErrorBanner error={graphRes.error} onRetry={graphRes.reload} />
                ) : (
                  <div className="walkthrough__mini-graph">
                    <KnowledgeGraph
                      nodes={graphRes.data.nodes}
                      edges={graphRes.data.edges}
                      highlightNodeLabels={step >= 2 ? highlightNodes : []}
                      highlightRelTypes={step >= 2 ? highlightRels : []}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function StepBody({ step, result, onOpenDocument }) {
  if (step === 1) return <StepIntent result={result} />;
  if (step === 2) return <StepTraversal result={result} />;
  if (step === 3) return <StepContext result={result} onOpenDocument={onOpenDocument} />;
  return <StepSynthesis result={result} onOpenDocument={onOpenDocument} />;
}

function StepIntent({ result }) {
  const { intent, resolved_entities } = result;
  if (!intent) return <p className="walkthrough__empty">No intent data returned for this query.</p>;
  return (
    <div>
      <div className="walkthrough__fact-row">
        <span className="eyebrow">Query type</span>
        <span className="badge badge--clay">{intent.query_type}</span>
      </div>
      <div className="walkthrough__fact-row">
        <span className="eyebrow">Entities mentioned</span>
        <span>{intent.entities_mentioned?.length ? intent.entities_mentioned.join(", ") : "—"}</span>
      </div>
      {Object.keys(resolved_entities || {}).length > 0 && (
        <div className="walkthrough__resolution">
          <span className="eyebrow">Resolved to canonical entities</span>
          <ul>
            {Object.entries(resolved_entities).map(([surface, canonical]) => (
              <li key={surface}><span className="mono">{surface}</span> <span className="walkthrough__arrow">→</span> <strong>{canonical}</strong></li>
            ))}
          </ul>
        </div>
      )}
      <div className="walkthrough__fact-row">
        <span className="eyebrow">Requires</span>
        <span>
          {intent.requires_graph && <span className="badge badge--blue">graph traversal</span>}{" "}
          {intent.requires_vector && <span className="badge">vector search</span>}
        </span>
      </div>
      {intent.reasoning && (
        <div className="walkthrough__reasoning">
          <span className="eyebrow">Classifier reasoning</span>
          <p>{intent.reasoning}</p>
        </div>
      )}
    </div>
  );
}

function StepTraversal({ result }) {
  const t = result.traversal;
  if (!t) return <p className="walkthrough__empty">No traversal data returned for this query.</p>;
  return (
    <div>
      <span className="eyebrow">Traversal paths</span>
      <ul className="walkthrough__paths">
        {(t.traversal_paths || []).map((p, i) => <li key={i} className="mono">{p}</li>)}
        {(!t.traversal_paths || t.traversal_paths.length === 0) && <li className="walkthrough__empty">No graph traversal was needed for this query.</li>}
      </ul>

      {t.cypher_templates?.length > 0 && (
        <>
          <span className="eyebrow">Cypher executed</span>
          <pre className="walkthrough__code">{t.cypher_templates.join("\n\n")}</pre>
        </>
      )}

      <div className="walkthrough__fact-row">
        <span className="eyebrow">Highlighted nodes</span>
        <div className="walkthrough__chips">
          {(t.highlight_nodes || []).map((n) => <span className="badge badge--blue" key={n}>{n}</span>)}
        </div>
      </div>
      <div className="walkthrough__fact-row">
        <span className="eyebrow">Relationship types used</span>
        <div className="walkthrough__chips">
          {(t.highlight_relationships || []).map((r) => <span className="badge" key={r}>{r}</span>)}
        </div>
      </div>
      <p className="walkthrough__hint-text">Traversed nodes are highlighted in the graph panel — jump to the Knowledge Graph tab for the full interactive view.</p>
    </div>
  );
}

function StepContext({ result, onOpenDocument }) {
  const c = result.context_debug;
  if (!c) return <p className="walkthrough__empty">No context-assembly data returned for this query.</p>;
  return (
    <div>
      <div className="walkthrough__metric-grid">
        <Metric label="Tokens used" value={`${c.token_count.toLocaleString()} / ${c.token_budget.toLocaleString()}`} />
        <Metric label="Structured facts" value={c.structured_facts_included} />
        <Metric label="Chunks included" value={c.chunks_included} />
        <Metric label="Chunks dropped" value={c.chunks_dropped} />
        <Metric label="Quality score" value={c.quality_score.toFixed(2)} tone={c.passed_quality_gate ? "moss" : "amber"} />
      </div>

      {c.traversal_explanation?.length > 0 && (
        <>
          <span className="eyebrow">How context was assembled</span>
          <ol className="walkthrough__explain">
            {c.traversal_explanation.map((line, i) => <li key={i}>{line}</li>)}
          </ol>
        </>
      )}

      <span className="eyebrow">Sources drawn on</span>
      <ul className="walkthrough__sources">
        {(result.sources || []).map((s) => (
          <li key={`${s.source_index}-${s.chunk_id}`}>
            <button className="walkthrough__source-btn" onClick={() => onOpenDocument?.(s.document_id)}>
              <span className="badge badge--clay">[{s.source_index}]</span>
              <span>{s.document_title}</span>
            </button>
            {s.snippet && <p className="walkthrough__snippet">“{s.snippet}”</p>}
          </li>
        ))}
        {(!result.sources || result.sources.length === 0) && <li className="walkthrough__empty">No sources attached.</li>}
      </ul>
    </div>
  );
}

function StepSynthesis({ result, onOpenDocument }) {
  const a = result.answer;
  if (!a) return <p className="walkthrough__empty">No synthesis returned for this query.</p>;
  return (
    <div>
      <div className="walkthrough__answer">
        <span className={`badge badge--${a.confidence === "high" ? "moss" : a.confidence === "medium" ? "amber" : ""}`}>
          {a.confidence} confidence
        </span>
        <p className="walkthrough__answer-text">{a.answer}</p>
      </div>

      {a.structured_rows?.length > 0 && (
        <div className="walkthrough__table-wrap">
          <table className="walkthrough__table">
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
        <div className="walkthrough__compliance">
          <span className="eyebrow">Compliance note</span>
          <p>{a.compliance_note}</p>
        </div>
      )}

      {a.citations?.length > 0 && (
        <div className="walkthrough__citations">
          <span className="eyebrow">Citations</span>
          <ul>
            {a.citations.map((c) => {
              const src = result.sources?.find((s) => s.source_index === c.source_index);
              return (
                <li key={c.source_index}>
                  <button className="walkthrough__source-btn" onClick={() => src && onOpenDocument?.(src.document_id)}>
                    [{c.source_index}] {c.document_title}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {result.traditional && (
        <div className="walkthrough__compare">
          <span className="eyebrow">vs. traditional RAG, for the same query</span>
          <p className="walkthrough__compare-note">{result.traditional.metrics?.note}</p>
          <ul className="walkthrough__compare-files">
            {result.traditional.files?.map((f) => (
              <li key={f.document_id}>
                <button className="walkthrough__source-btn" onClick={() => onOpenDocument?.(f.document_id)}>{f.name}</button>
                <span className="badge">score {f.score}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, tone }) {
  return (
    <div className={`metric ${tone ? `metric--${tone}` : ""}`}>
      <span className="metric__value">{value}</span>
      <span className="metric__label">{label}</span>
    </div>
  );
}
