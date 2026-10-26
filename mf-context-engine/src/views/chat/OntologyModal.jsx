import { Share2 } from "lucide-react";
import ModalCard from "./ModalCard";
import OntologyGraph from "../panels/OntologyGraph";

export default function OntologyModal({ open, onClose, data }) {
  const r = data?.r || {};
  const entitySummary = data?.entitySummary || [];
  const nodes = r.graph_nodes || [];
  const edges = r.graph_edges || [];
  const matched = r.matched_entity_texts || [];

  return (
    <ModalCard
      open={open}
      onClose={onClose}
      title="Ontology View"
      icon={<Share2 size={15} strokeWidth={1.75} />}
      query={data?.query}
      size="md"
    >
      <p className="cg-ontology-lede">
        These are the entities the system connected to answer your question, and how they relate to
        one another. Hover any entity to isolate its relationships.
      </p>

      <OntologyGraph nodes={nodes} edges={edges} matchedTexts={matched} />

      {edges.length > 0 && (
        <>
          <div className="cg-label" style={{ marginTop: 18 }}>Relationships</div>
          <ul className="cg-ontology-rels">
            {edges.map((e, i) => (
              <li key={i}>
                <b>{e.s}</b>
                <span className="cg-ontology-rel-verb">{String(e.rel).replace(/_/g, " ").toLowerCase()}</span>
                <b>{e.o}</b>
              </li>
            ))}
          </ul>
        </>
      )}

      {entitySummary.length > 0 && (
        <>
          <div className="cg-label" style={{ marginTop: 18 }}>Entity types touched by this query</div>
          <div style={{ marginTop: 6 }}>
            {entitySummary.map((t, i) => (
              <div key={i} className={`cg-tree-node ${t.active ? "active" : ""}`}>
                <span>{t.label}</span><span>{t.count}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </ModalCard>
  );
}
