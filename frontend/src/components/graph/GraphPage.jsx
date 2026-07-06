import { useState } from "react";
import { api } from "../../api/client";
import { useResource } from "../../hooks/useResource";
import { MOCK_GRAPH } from "../../data/mockData";
import KnowledgeGraph from "./KnowledgeGraph";
import { SkeletonBlock } from "../common/Skeleton";
import { ErrorBanner, DemoModeNotice } from "../common/Banners";
import "./GraphPage.css";

export default function GraphPage() {
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState({ nodes: [], rels: [] });
  const [queryState, setQueryState] = useState({ loading: false, error: null });

  const graphRes = useResource(
    (signal) => api.getFullGraph(500, signal),
    { deps: [], mockValue: MOCK_GRAPH }
  );

  async function runHighlight(e) {
    e.preventDefault();
    if (!query.trim()) { setHighlight({ nodes: [], rels: [] }); return; }
    setQueryState({ loading: true, error: null });
    try {
      const res = await api.getTraversalHighlight(query);
      setHighlight({ nodes: res.highlight_nodes || [], rels: res.highlight_relationships || [] });
      setQueryState({ loading: false, error: null });
    } catch (err) {
      setQueryState({ loading: false, error: err });
    }
  }

  return (
    <div className="graph-page">
      <div className="card graph-page__query">
        <form onSubmit={runHighlight}>
          <input
            type="text"
            placeholder="Type a query to trace which nodes and edges its traversal would touch…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="btn btn--clay" type="submit" disabled={queryState.loading}>
            {queryState.loading ? "Tracing…" : "Trace traversal"}
          </button>
        </form>
        {queryState.error && <ErrorBanner error={queryState.error} title="Couldn't trace that query" />}
      </div>

      <div className="card graph-page__canvas">
        {graphRes.isMock && <DemoModeNotice />}
        {graphRes.loading && <SkeletonBlock height={420} />}
        {graphRes.error && <ErrorBanner error={graphRes.error} onRetry={graphRes.reload} />}
        {graphRes.data && (
          <KnowledgeGraph
            nodes={graphRes.data.nodes}
            edges={graphRes.data.edges}
            highlightNodeLabels={highlight.nodes}
            highlightRelTypes={highlight.rels}
          />
        )}
      </div>
    </div>
  );
}
