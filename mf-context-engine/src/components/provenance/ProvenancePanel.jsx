import React, { useState } from "react";
import { Pin, ChevronUp, ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import "./ProvenancePanel.css";

export default function ProvenancePanel({ citations = [] }) {
  const [panelOpen, setPanelOpen] = useState(true);
  const [expandedRows, setExpandedRows] = useState({});

  if (!Array.isArray(citations) || citations.length === 0) {
    return null;
  }

  // Normalize citations to consistent shape
  const normalizedSources = citations.map((item, idx) => {
    if (typeof item === "string") {
      return {
        marker: String(idx + 1),
        docName: item,
        pageNumber: null,
        pageLabel: "—",
        snippet: "",
        verbatimText: "",
        sourceUrl: item.toLowerCase().endsWith(".pdf") ? `/api/files/${encodeURIComponent(item)}` : null,
      };
    }

    const src = item.source || item;
    const docName = src.document_name || src.document_title || src.title || src.name || src.doc || `Source Document [${idx + 1}]`;
    const pageNum = src.page_number !== undefined ? src.page_number : (src.page !== undefined ? src.page : null);
    const pageLabel = src.page_label || (pageNum != null ? `p. ${pageNum}` : "—");
    const verbatim = src.verbatim_text || src.full_text || src.snippet || "";
    const snippet = src.snippet || (verbatim ? verbatim.slice(0, 140) : "");
    
    let sourceUrl = src.source_url || src.url;
    if (!sourceUrl && docName.toLowerCase().endsWith(".pdf")) {
      sourceUrl = `/api/files/${encodeURIComponent(docName)}${pageNum ? `#page=${pageNum}` : ""}`;
    }

    return {
      marker: item.marker || String(idx + 1),
      docName,
      pageNumber: pageNum,
      pageLabel,
      snippet,
      verbatimText: verbatim,
      sourceUrl,
    };
  });

  const toggleRow = (idx) => {
    setExpandedRows((prev) => ({
      ...prev,
      [idx]: !prev[idx],
    }));
  };

  return (
    <div className="mf-provenance-container">
      <details
        className="mf-provenance-details"
        open={panelOpen}
        onToggle={(e) => setPanelOpen(e.target.open)}
      >
        <summary className="mf-provenance-summary">
          <span className="mf-provenance-summary-title">
            <Pin size={14} strokeWidth={1.75} />
            Document Provenance &amp; Exact Page Citations ({normalizedSources.length} Sources)
          </span>
          <span className="mf-provenance-toggle-hint" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            {panelOpen ? "Collapse panel" : "Expand panel"}
            {panelOpen ? <ChevronUp size={14} strokeWidth={1.75} /> : <ChevronDown size={14} strokeWidth={1.75} />}
          </span>
        </summary>

        <div className="mf-provenance-table-wrap">
          <table className="mf-provenance-table">
            <thead>
              <tr>
                <th style={{ width: "40px" }}>#</th>
                <th style={{ width: "35%" }}>Source Document</th>
                <th style={{ width: "90px" }}>Page</th>
                <th>Verbatim Source Text (Click chevron to view full text)</th>
              </tr>
            </thead>
            <tbody>
              {normalizedSources.map((row, idx) => {
                const isExpanded = !!expandedRows[idx];
                const hasLongText = (row.verbatimText && row.verbatimText.length > 120);

                return (
                  <React.Fragment key={idx}>
                    <tr className={`mf-provenance-row ${isExpanded ? "mf-row-expanded" : ""}`}>
                      <td className="mf-cell-marker">
                        <span className="mf-provenance-marker-tag">[{row.marker}]</span>
                      </td>
                      <td className="mf-cell-doc">
                        {row.sourceUrl ? (
                          <a
                            href={row.sourceUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="mf-provenance-doc-link"
                            title={`Open ${row.docName} in a new tab`}
                          >
                            <b>{row.docName}</b> <ExternalLink size={12} strokeWidth={1.75} style={{ verticalAlign: "-1px" }} />
                          </a>
                        ) : (
                          <b>{row.docName}</b>
                        )}
                      </td>
                      <td className="mf-cell-page">
                        <span className="mf-page-badge">{row.pageLabel}</span>
                      </td>
                      <td className="mf-cell-snippet">
                        <div className="mf-snippet-container">
                          {hasLongText && (
                            <button
                              type="button"
                              className="mf-accordion-toggle-btn"
                              onClick={() => toggleRow(idx)}
                              title={isExpanded ? "Collapse full text" : "Expand full verbatim text"}
                              aria-label={isExpanded ? "Collapse full text" : "Expand full verbatim text"}
                            >
                              {isExpanded ? <ChevronDown size={13} strokeWidth={1.75} /> : <ChevronRight size={13} strokeWidth={1.75} />}
                            </button>
                          )}
                          <span className="mf-snippet-preview">
                            "{row.snippet.length > 120 ? row.snippet.slice(0, 120) + "…" : row.snippet}"
                          </span>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && row.verbatimText && (
                      <tr className="mf-verbatim-expanded-row">
                        <td colSpan={4} className="mf-verbatim-cell">
                          <div className="mf-verbatim-blockquote">
                            <div className="mf-verbatim-header">
                              <span>Full Verbatim Clause / Context ({row.docName}, {row.pageLabel})</span>
                              {row.sourceUrl && (
                                <a
                                  href={row.sourceUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="mf-verbatim-source-link"
                                >
                                  Open Page View <ExternalLink size={11} strokeWidth={1.75} style={{ verticalAlign: "-1px" }} />
                                </a>
                              )}
                            </div>
                            <div className="mf-verbatim-body">
                              {row.verbatimText}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
