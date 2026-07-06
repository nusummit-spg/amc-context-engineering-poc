import { useMemo, useState } from "react";
import { api } from "../../api/client";
import { useResource } from "../../hooks/useResource";
import { MOCK_DOCS } from "../../data/mockData";
import { SkeletonCards } from "../common/Skeleton";
import { ErrorBanner, DemoModeNotice, EmptyState } from "../common/Banners";
import DocumentModal from "./DocumentModal";
import "./RawCorpusPanel.css";

export default function RawCorpusPanel() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [openDoc, setOpenDoc] = useState(null);

  const { data, loading, error, isMock, reload } = useResource(
    (signal) => api.listDocuments(signal),
    { deps: [], mockValue: MOCK_DOCS }
  );

  const categories = useMemo(() => {
    if (!data) return [];
    return ["all", ...new Set(data.map((d) => d.category))];
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.filter((d) => {
      const matchesCategory = category === "all" || d.category === category;
      const matchesQuery = !query.trim() || `${d.title} ${d.filename}`.toLowerCase().includes(query.toLowerCase());
      return matchesCategory && matchesQuery;
    });
  }, [data, category, query]);

  return (
    <div className="corpus-panel">
      {isMock && <DemoModeNotice />}
      {error && <ErrorBanner error={error} onRetry={reload} title="Couldn't load the corpus" />}

      <div className="corpus-panel__toolbar">
        <input
          type="search"
          placeholder="Search documents…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="corpus-panel__search"
        />
        <div className="corpus-panel__filters">
          {categories.map((c) => (
            <button
              key={c}
              className={`corpus-panel__filter ${category === c ? "is-active" : ""}`}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {loading && <SkeletonCards count={6} />}

      {!loading && filtered.length === 0 && (
        <EmptyState title="No documents match" hint="Try a different search term or category." />
      )}

      {!loading && filtered.length > 0 && (
        <div className="corpus-panel__list">
          {filtered.map((doc) => (
            <button className="doc-card" key={doc.document_id} onClick={() => setOpenDoc(doc.document_id)}>
              <div className="doc-card__head">
                <span className="doc-card__type badge">{doc.doc_type}</span>
                <span className="doc-card__chunks">{doc.chunk_count} chunks</span>
              </div>
              <h4>{doc.title || doc.filename}</h4>
              <p className="doc-card__filename mono">{doc.filename}</p>
              <div className="doc-card__paths">
                {(doc.taxonomy_paths || []).slice(0, 2).map((p) => (
                  <span className="badge badge--clay" key={p}>{p.split("/").slice(-1)[0]}</span>
                ))}
              </div>
            </button>
          ))}
        </div>
      )}

      {openDoc && <DocumentModal documentId={openDoc} onClose={() => setOpenDoc(null)} />}
    </div>
  );
}
