import { useState } from "react";
import { ChevronDown, ChevronRight, CheckCircle2, AlertTriangle, FileSearch } from "lucide-react";
import ModalCard from "./ModalCard";
import ProvenancePanel from "../../components/provenance/ProvenancePanel";
import TelemetryDetails from "../panels/TelemetryDetails";
import MiniGraphStatic from "../panels/MiniGraphStatic";

const BADGE_COLORS = {
  success: { bg: "var(--color-success-bg)", fg: "var(--color-success-text)" },
  primary: { bg: "var(--color-navy-100)", fg: "var(--color-navy-700)" },
  default: { bg: "var(--color-warning-bg)", fg: "var(--color-warning-text)" },
};

function Section({ title, summary, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="cg-evidence-section">
      <button
        type="button"
        className="cg-evidence-section-head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="cg-evidence-section-title">{title}</span>
        <span className="cg-evidence-section-right">
          {!open && summary && <span className="cg-evidence-section-summary">{summary}</span>}
          {open ? <ChevronDown size={15} strokeWidth={1.75} /> : <ChevronRight size={15} strokeWidth={1.75} />}
        </span>
      </button>
      {open && <div className="cg-evidence-section-body">{children}</div>}
    </div>
  );
}

/** Translates the model's confidence label into something a non-specialist can act on. */
function confidenceExplainer(label, sourceCount) {
  const low = /moderate|low/i.test(label || "");
  if (low) {
    return `This answer drew on ${sourceCount || "few"} supporting source${sourceCount === 1 ? "" : "s"} and some claims are weakly grounded — worth verifying against the documents below before acting on it.`;
  }
  return `Every claim in this answer traces back to the ${sourceCount} cited source${sourceCount === 1 ? "" : "s"} listed below.`;
}

export default function EvidenceModal({ open, onClose, data }) {
  const r = data?.r || {};
  const tb = r.telemetry_breakdown || {};
  const badges = tb.ui_badges || [];
  const triplets = tb.triplet_table || [];
  const entitySummary = data?.entitySummary || [];
  const citations =
    r.citations && r.citations.length > 0
      ? r.citations
      : (r.provenance && r.provenance.length > 0 ? r.provenance : r.docs || []);

  return (
    <ModalCard
      open={open}
      onClose={onClose}
      title="Evidence & Sources"
      icon={<FileSearch size={15} strokeWidth={1.75} />}
      query={data?.query}
      size="lg"
    >
      <Section title="Overview" summary={r.confidence_label} defaultOpen={true}>
        <div style={{ marginBottom: 10 }}>
          <span className={`cg-badge ${/moderate|low/i.test(r.confidence_label || "") ? "" : "green"}`} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            {/moderate|low/i.test(r.confidence_label || "") ? (
              <AlertTriangle size={12} strokeWidth={2} />
            ) : (
              <CheckCircle2 size={12} strokeWidth={2} />
            )}
            {r.confidence_label} {r.confidence_reason || ""}
          </span>
        </div>

        <p className="cg-evidence-explainer">
          {confidenceExplainer(r.confidence_label, citations.length)}
        </p>

        {badges.length > 0 && (
          <div className="cg-badges-block">
            {badges.map((b, i) => {
              const c = BADGE_COLORS[b.type] || BADGE_COLORS.default;
              return (
                <div key={i} style={{ background: c.bg, color: c.fg, borderRadius: "var(--radius-sm)", padding: "6px 10px", fontSize: 11.5, fontWeight: 600, marginBottom: 6 }}>
                  {b.label} &mdash; <span style={{ fontWeight: 400 }}>{b.desc}</span>
                </div>
              );
            })}
          </div>
        )}

        <div className="cg-stats">
          <div className="cg-stat">
            <div className="cg-stat-num">{r.graph_nodes?.length ?? 0}</div>
            <div className="cg-stat-label">Graph nodes touched</div>
          </div>
          <div className="cg-stat">
            <div className="cg-stat-num">{(r.total_tokens ?? 0).toLocaleString()}</div>
            <div className="cg-stat-label">Tokens used</div>
          </div>
          <div className="cg-stat">
            <div className="cg-stat-num">{(r.total_time ?? 0).toFixed(2)}s</div>
            <div className="cg-stat-label">Total time</div>
          </div>
        </div>
      </Section>

      <Section
        title={`Document Sources (${citations.length})`}
        summary={citations.length ? `${citations.length} cited` : "none"}
        defaultOpen={true}
      >
        {citations.length > 0 ? (
          <ProvenancePanel citations={citations} flat />
        ) : (
          <div className="cg-evidence-empty">No source documents attached to this response.</div>
        )}
      </Section>

      <Section
        title="Graph Context"
        summary={`${r.graph_nodes?.length ?? 0} nodes · ${r.graph_edges?.length ?? 0} edges`}
      >
        <div className="cg-label">Entity types touched by this query</div>
        <div style={{ marginTop: 6 }}>
          {entitySummary.map((t, i) => (
            <div key={i} className={`cg-tree-node ${t.active ? "active" : ""}`}>
              <span>{t.label}</span><span>{t.count}</span>
            </div>
          ))}
        </div>
        <div className="cg-label" style={{ marginTop: 12 }}>Graph neighborhood</div>
        <MiniGraphStatic nodes={r.graph_nodes || []} edges={r.graph_edges || []} matchedTexts={r.matched_entity_texts || []} width={760} />
        <div className="cg-graph-note">Colored nodes/edges matched this query directly; grey nodes are one hop of surrounding context.</div>
      </Section>

      <Section
        title="Grounding / Validation"
        summary={triplets.length ? `${triplets.length} relationship${triplets.length === 1 ? "" : "s"}` : "none"}
      >
        {triplets.length > 0 ? (
          <table className="cg-mini-table">
            <thead>
              <tr>
                <th>Subject Node</th><th>Relationship</th><th>Target Node</th><th style={{ textAlign: "right" }}>Conf</th>
              </tr>
            </thead>
            <tbody>
              {triplets.map((t, i) => (
                <tr key={i}>
                  <td><b>{String(t.s).slice(0, 30)}</b></td>
                  <td><code>{t.rel}</code></td>
                  <td>{String(t.o).slice(0, 35)}</td>
                  <td style={{ textAlign: "right" }}>{(t.conf ?? 1).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="cg-evidence-empty">No graph triplet path was traversed for this response.</div>
        )}
      </Section>

      <Section
        title="Retrieval Details"
        summary={`${(r.total_time ?? 0).toFixed(2)}s · ${(r.total_tokens ?? 0).toLocaleString()} tokens`}
      >
        {r.telemetry_breakdown ? (
          <TelemetryDetails t={r.telemetry_breakdown} />
        ) : (
          <div className="cg-evidence-empty">No retrieval telemetry available.</div>
        )}
      </Section>
    </ModalCard>
  );
}
