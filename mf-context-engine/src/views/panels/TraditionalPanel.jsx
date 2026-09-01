import { useState } from "react";
import TelemetryDetails from "./TelemetryDetails";
import MarkdownAnswer from "../../components/provenance/MarkdownAnswer";

function DocCard({ d }) {
  const [showFull, setShowFull] = useState(false);
  return (
    <div className="cg-doc">
      <div className="cg-doc-head">
        <span>{d.name} · p.{d.page ?? "?"}</span>
        <span className="cg-doc-score">score {d.score}</span>
      </div>
      <div className="cg-doc-snippet">"{d.snippet}…"</div>
      <details open={showFull} onToggle={(e) => setShowFull(e.target.open)}>
        <summary>Show full source text</summary>
        <div className="cg-doc-full">{d.full_text}</div>
      </details>
    </div>
  );
}

export default function TraditionalPanel({ r }) {
  return (
    <div className="cg-wrap cg-panel">
      <div className="cg-panel-head">
        <div className="cg-panel-title">
          <span className="cg-dot trad"></span>Traditional Document Search
        </div>
        <span className="cg-badge">vector-only</span>
      </div>
      <div className="cg-label">Files returned, ranked by similarity</div>
      <div style={{ marginTop: 8 }}>
        {r.docs && r.docs.length > 0 ? (
          r.docs.map((d, i) => <DocCard key={i} d={d} />)
        ) : (
          <div className="cg-graph-note">No matching documents found.</div>
        )}
      </div>
      <div className="cg-warning">⚠ No consolidated answer — each document must be reviewed individually.</div>
      <div className="cg-answer">
        <MarkdownAnswer
          text={typeof r.answer === "string" ? r.answer : (r.answer?.answer || "")}
          citations={r.citations || r.docs || []}
          metrics={r.metrics || []}
        />
      </div>
      <div className="cg-stats">
        <div className="cg-stat">
          <div className="cg-stat-num">{r.docs?.length ?? 0}</div>
          <div className="cg-stat-label">Docs returned</div>
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
    </div>
  );
}
