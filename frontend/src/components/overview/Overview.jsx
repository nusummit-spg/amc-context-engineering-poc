import { api } from "../../api/client";
import { useResource } from "../../hooks/useResource";
import { SkeletonLine } from "../common/Skeleton";
import { DemoModeNotice } from "../common/Banners";
import "./Overview.css";

const PIPELINE = [
  { stage: "Ingest", detail: "PDF / DOCX / PPTX / MSG / EML / XLSX parsed, chunked, PII-scrubbed" },
  { stage: "Classify & tag", detail: "LLM taxonomy classifier tags each chunk against the 4-level tree" },
  { stage: "Extract", detail: "NER + relationship extraction populate 9 entity types in the graph" },
  { stage: "Resolve", detail: "Surface-form aliases collapse to one canonical node per entity" },
];

const RETRIEVAL_STEPS = [
  { n: 1, label: "Intent & entity resolution", detail: "Classify query type, resolve mentioned entities to canonical nodes, and pick the taxonomy branches in scope." },
  { n: 2, label: "Graph traversal", detail: "Walk the typed relationship graph along a strategy chosen by query type — e.g. Scheme→HOLDS→Issuer→ISSUER_GROUP." },
  { n: 3, label: "Context assembly", detail: "Merge structured graph facts with taxonomy-scoped vector search hits inside a fixed token budget, then gate on quality." },
  { n: 4, label: "Synthesis", detail: "Claude turns assembled context into a cited, structured answer — with a compliance note where relevant." },
];

function Stat({ label, value, tone }) {
  return (
    <div className={`stat ${tone ? `stat--${tone}` : ""}`}>
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  );
}

export default function Overview({ onNavigate }) {
  const { data: status, loading, isMock } = useResource(
    (signal) => api.getStatus(signal),
    { deps: [], mockValue: { status: "degraded", neo4j: "down", qdrant: "down", llm: "missing_api_key", documents_indexed: 8, chunks_indexed: 59 } }
  );

  return (
    <div className="overview">
      <section className="card overview__hero">
        <span className="eyebrow">NuSummit ContextGraph — proof of concept</span>
        <h1>Taxonomy-scoped graph retrieval, versus flat vector search</h1>
        <p>
          The same AMC document corpus, indexed two ways: a flat vector-search baseline that returns
          a pile of files to read, and ContextGraph — hybrid retrieval over a 4-level taxonomy and a
          typed knowledge graph that returns one synthesized, cited answer.
        </p>
        <div className="overview__hero-actions">
          <button className="btn btn--clay" onClick={() => onNavigate("walkthrough")}>Run the query walkthrough</button>
          <button className="btn btn--ghost" onClick={() => onNavigate("graph")}>Explore the graph</button>
        </div>
      </section>

      <section className="overview__stats-row">
        {loading ? (
          <>
            <SkeletonLine width="100%" height={64} />
            <SkeletonLine width="100%" height={64} />
            <SkeletonLine width="100%" height={64} />
            <SkeletonLine width="100%" height={64} />
          </>
        ) : (
          <>
            <Stat label="Documents indexed" value={status.documents_indexed} />
            <Stat label="Chunks indexed" value={status.chunks_indexed} />
            <Stat label="Neo4j" value={status.neo4j} tone={status.neo4j === "up" ? "moss" : "amber"} />
            <Stat label="Qdrant" value={status.qdrant} tone={status.qdrant === "up" ? "moss" : "amber"} />
          </>
        )}
      </section>
      {isMock && <DemoModeNotice />}

      <div className="overview__two-col">
        <section className="card overview__panel">
          <h3>Ingestion pipeline</h3>
          <ol className="overview__pipeline">
            {PIPELINE.map((p) => (
              <li key={p.stage}>
                <strong>{p.stage}</strong>
                <span>{p.detail}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="card overview__panel">
          <h3>Retrieval, 4 steps</h3>
          <ol className="overview__pipeline">
            {RETRIEVAL_STEPS.map((s) => (
              <li key={s.n}>
                <strong>{s.n}. {s.label}</strong>
                <span>{s.detail}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <section className="card overview__panel">
        <h3>Where to look</h3>
        <div className="overview__links">
          <button onClick={() => onNavigate("walkthrough")}><strong>Query Walkthrough</strong><span>Trace two real questions through all four retrieval steps</span></button>
          <button onClick={() => onNavigate("taxonomy")}><strong>Taxonomy Tree</strong><span>Browse the 4-level classification with live document counts</span></button>
          <button onClick={() => onNavigate("graph")}><strong>Knowledge Graph</strong><span>Click any entity to trace its typed relationships</span></button>
          <button onClick={() => onNavigate("entities")}><strong>Entity Resolution</strong><span>See how alias surface forms collapse to one node</span></button>
          <button onClick={() => onNavigate("corpus")}><strong>Raw Corpus</strong><span>Every ingested document, with a chunk-level preview</span></button>
          <button onClick={() => onNavigate("upload")}><strong>Upload Documents</strong><span>Drop a file in to add it to the corpus</span></button>
        </div>
      </section>
    </div>
  );
}
