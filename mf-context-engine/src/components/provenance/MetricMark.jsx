import React from "react";
import Tooltip from "./Tooltip";
import "./MetricMark.css";

const PROVENANCE_LABELS = {
  verbatim: { label: "From source", color: "#10B981", badgeClass: "mf-metric-tag-verbatim" },
  computed: { label: "Calculated", color: "#3B82F6", badgeClass: "mf-metric-tag-computed" },
  assumed: { label: "Assumption", color: "#F59E0B", badgeClass: "mf-metric-tag-assumed" },
};

export default function MetricMark({ metric, children }) {
  if (!metric) {
    return <span>{children}</span>;
  }

  const pType = metric.provenance_type || "verbatim";
  const meta = PROVENANCE_LABELS[pType] || PROVENANCE_LABELS.verbatim;

  const tooltipContent = (
    <div className="mf-metric-tooltip-content">
      <div className="mf-tooltip-title">
        <span className={`mf-metric-badge ${meta.badgeClass}`}>{meta.label}</span>
        <span className="mf-metric-surface">{metric.surface_text || children}</span>
      </div>

      <div className="mf-metric-explanation">
        {metric.explanation || "Extracted figure from context."}
      </div>

      {metric.formula && (
        <div className="mf-metric-formula-box">
          <div className="mf-metric-subhead">Formula / Calculation</div>
          <code>{metric.formula}</code>
        </div>
      )}

      {metric.inputs_used && Object.keys(metric.inputs_used).length > 0 && (
        <div className="mf-metric-inputs-box">
          <div className="mf-metric-subhead">Input Variables</div>
          <ul className="mf-metric-inputs-list">
            {Object.entries(metric.inputs_used).map(([k, v]) => (
              <li key={k}>
                <b>{k}:</b> {String(v)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {metric.assumption_basis && (
        <div className="mf-metric-assumption-box">
          <div className="mf-metric-subhead">Assumption Basis</div>
          <div>{metric.assumption_basis}</div>
        </div>
      )}

      {metric.supporting_citation_markers && metric.supporting_citation_markers.length > 0 && (
        <div className="mf-tooltip-footer">
          <span>Supporting Citations:</span>
          <span>
            {metric.supporting_citation_markers.map((c) => `[${c}]`).join(", ")}
          </span>
        </div>
      )}
    </div>
  );

  return (
    <Tooltip content={tooltipContent} placement="top" maxWidth={440} minWidth={320}>
      <span className={`mf-metric-mark mf-metric-mark--${pType}`} tabIndex={0}>
        {children || metric.surface_text}
      </span>
    </Tooltip>
  );
}
