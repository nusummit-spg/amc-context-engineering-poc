import { useState } from "react";
import { api } from "../../api/client";
import { useResource } from "../../hooks/useResource";
import { MOCK_TAXONOMY, MOCK_DOCS } from "../../data/mockData";
import TaxonomyTree from "./TaxonomyTree";
import { SkeletonTree } from "../common/Skeleton";
import { ErrorBanner, DemoModeNotice, EmptyState } from "../common/Banners";
import "./TaxonomyPage.css";

export default function TaxonomyPage({ onOpenDocument }) {
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  const [highlightedPaths, setHighlightedPaths] = useState([]);
  const [queryState, setQueryState] = useState({ loading: false, error: null });

  const treeRes = useResource(
    (signal) => api.getTaxonomyTree(signal),
    { deps: [], mockValue: MOCK_TAXONOMY }
  );

  const docsRes = useResource(
    (signal) => selected ? api.getTaxonomyNodeDocs(selected.path, signal) : Promise.resolve(null),
    {
      deps: [selected?.path],
      enabled: !!selected,
      mockValue: selected ? { path: selected.path, documents: MOCK_DOCS.filter((d) => d.taxonomy_paths?.some((p) => p.startsWith(selected.path))) } : undefined,
    }
  );

  async function runHighlight(e) {
    e.preventDefault();
    if (!query.trim()) { setHighlightedPaths([]); return; }
    setQueryState({ loading: true, error: null });
    try {
      const res = await api.getTaxonomyHighlight(query);
      setHighlightedPaths(res.taxonomy_paths || []);
      setQueryState({ loading: false, error: null });
    } catch (err) {
      setQueryState({ loading: false, error: err });
    }
  }

  return (
    <div className="taxonomy-page">
      <div className="card taxonomy-page__query">
        <form onSubmit={runHighlight}>
          <input
            type="text"
            placeholder="Type a query to see which branches it would activate…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="btn btn--clay" type="submit" disabled={queryState.loading}>
            {queryState.loading ? "Checking…" : "Highlight branches"}
          </button>
        </form>
        {queryState.error && <ErrorBanner error={queryState.error} title="Couldn't classify that query" />}
      </div>

      <div className="taxonomy-page__grid">
        <div className="card taxonomy-page__tree">
          {treeRes.isMock && <DemoModeNotice compact />}
          {treeRes.loading && <SkeletonTree rows={10} />}
          {treeRes.error && <ErrorBanner error={treeRes.error} onRetry={treeRes.reload} />}
          {treeRes.data && (
            <TaxonomyTree
              roots={treeRes.data.roots}
              highlightedPaths={highlightedPaths}
              onSelectNode={setSelected}
              selectedPath={selected?.path}
            />
          )}
        </div>

        <div className="card taxonomy-page__docs">
          {!selected ? (
            <EmptyState title="Select a node" hint="Click any taxonomy node to see the documents tagged under it." />
          ) : (
            <>
              <div className="taxonomy-page__docs-head">
                <span className="eyebrow">{selected.path}</span>
                <h4>{selected.name}</h4>
              </div>
              {docsRes.isMock && <DemoModeNotice compact />}
              {docsRes.loading && <SkeletonTree rows={4} />}
              {docsRes.error && <ErrorBanner error={docsRes.error} onRetry={docsRes.reload} />}
              {docsRes.data && (
                docsRes.data.documents.length === 0 ? (
                  <EmptyState title="No documents here" hint="This branch has no directly tagged documents yet." />
                ) : (
                  <ul className="taxonomy-page__doc-list">
                    {docsRes.data.documents.map((d) => (
                      <li key={d.document_id}>
                        <button onClick={() => onOpenDocument?.(d.document_id)}>
                          <strong>{d.title || d.document_id}</strong>
                          <span className="badge">{d.doc_type}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
