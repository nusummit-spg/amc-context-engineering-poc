import { useState } from "react";
import { Share2, CheckCircle2, AlertTriangle } from "lucide-react";
import TelemetryDetails from "./TelemetryDetails";
import MiniGraphStatic from "./MiniGraphStatic";
import FeedbackContainer from "../../components/feedback/FeedbackContainer";
import MarkdownAnswer from "../../components/provenance/MarkdownAnswer";
import ProvenancePanel from "../../components/provenance/ProvenancePanel";

const BADGE_COLORS = {
  success: { bg: "var(--color-success-bg)", fg: "var(--color-success-text)" },
  primary: { bg: "var(--color-navy-100)", fg: "var(--color-navy-700)" },
  default: { bg: "var(--color-warning-bg)", fg: "var(--color-warning-text)" },
};

export default function ContextGraphPanel({
  r,
  entitySummary,
  responseId,
  interactionId,
  sessionId,
  turnNumber,
  query,
  actorId,
  actorRole,
  isCurrentTurn = true,
  showFeedback = true,
}) {
  const [tab, setTab] = useState("answer");
  const tb = r?.telemetry_breakdown || {};
  const badges = tb.ui_badges || [];
  const triplets = tb.triplet_table || [];

  if (!r) return null;

  return (
    <div className="cg-wrap cg-panel">
      <div className="cg-panel-head">
        <div className="cg-panel-title">
          <span className="cg-dot ctx"></span>ContextGraph
        </div>
        <span className="cg-badge">hybrid graph + vector</span>
      </div>
      <p className="cg-panel-lede">
        Resolves the entities in your question, walks the relationships between them, then writes a
        single answer with every claim traced back to a source.
      </p>
      <div className="cg-tabs">
        <button className={`cg-tab ${tab === "answer" ? "active" : ""}`} onClick={() => setTab("answer")}>
          Answer
        </button>
        <button className={`cg-tab ${tab === "ontology" ? "active" : ""}`} onClick={() => setTab("ontology")}>
          Ontology View
        </button>
      </div>

      {tab === "answer" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span className={`cg-badge ${/moderate|low/i.test(r.confidence_label || "") ? "" : "green"}`} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              {/moderate|low/i.test(r.confidence_label || "") ? (
                <AlertTriangle size={12} strokeWidth={2} />
              ) : (
                <CheckCircle2 size={12} strokeWidth={2} />
              )}
              {r.confidence_label} {r.confidence_reason || ""}
            </span>
          </div>

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

          {triplets.length > 0 && (
            <details className="cg-triplet-details">
              <summary style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <Share2 size={13} strokeWidth={1.75} />
                Graph Triplet Path Traversed ({r.graph_nodes?.length ?? 0} Nodes | {r.graph_edges?.length ?? 0} Edges)
              </summary>
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
            </details>
          )}

          <div className="cg-answer">
            <MarkdownAnswer
              text={typeof r.answer === "string" ? r.answer : (r.answer?.answer || "")}
              citations={r.citations || r.docs || []}
              metrics={r.metrics || []}
            />
          </div>

          <ProvenancePanel
            citations={
              r.citations && r.citations.length > 0
                ? r.citations
                : (r.provenance && r.provenance.length > 0 ? r.provenance : r.docs || [])
            }
          />

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

          <TelemetryDetails t={r.telemetry_breakdown} />

          {showFeedback && (
            <FeedbackContainer
              responseId={responseId || r.response_id || `resp_${turnNumber || 1}`}
              interactionId={interactionId || r.interaction_id || `int_${sessionId || "cg"}`}
              sessionId={sessionId || r.session_id || "session_default"}
              turnNumber={turnNumber || r.turn_number || r.turn_index || 1}
              query={query || r.query || ""}
              actorId={actorId}
              actorRole={actorRole}
              isCurrentTurn={isCurrentTurn}
            />
          )}
        </div>
      )}

      {tab === "ontology" && (
        <div>
          <div className="cg-label">Entity types touched by this query</div>
          <div style={{ marginTop: 6 }}>
            {(entitySummary || []).map((t, i) => (
              <div key={i} className={`cg-tree-node ${t.active ? "active" : ""}`}>
                <span>{t.label}</span><span>{t.count}</span>
              </div>
            ))}
          </div>
          <div className="cg-label" style={{ marginTop: 12 }}>Graph neighborhood</div>
          <MiniGraphStatic nodes={r.graph_nodes || []} edges={r.graph_edges || []} matchedTexts={r.matched_entity_texts || []} />
          <div className="cg-graph-note">Colored nodes/edges matched this query directly; grey nodes are one hop of surrounding context.</div>
        </div>
      )}
    </div>
  );
}
