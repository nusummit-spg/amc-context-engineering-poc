import React, { useState } from "react";
import { Pin, ChevronUp, ChevronDown, ExternalLink, Download } from "lucide-react";
import "./ProvenancePanel.css";

export default function ProvenancePanel({ citations = [], flat = false }) {
  const [panelOpen, setPanelOpen] = useState(true);

  if (!Array.isArray(citations) || citations.length === 0) {
    return null;
  }

  // Normalize citations to consistent shape
  const normalizedSources = citations.map((item, idx) => {
    if (typeof item === "string") {
      const isCsv = item.toLowerCase().endsWith(".csv");
      return {
        marker: String(idx + 1),
        docName: item,
        pageNumber: null,
        pageLabel: isCsv ? "CSV Data" : "—",
        isCsv,
        sourceUrl: isCsv
          ? `/api/files/${encodeURIComponent(item)}?download=true`
          : (item.toLowerCase().endsWith(".pdf") ? `/api/files/${encodeURIComponent(item)}` : null),
      };
    }

    const src = item.source || item;
    const docName = src.document_name || src.document_title || src.title || src.name || src.doc || `Source Document [${idx + 1}]`;
    const isCsv = docName.toLowerCase().endsWith(".csv") || (src.source_url && src.source_url.toLowerCase().includes(".csv"));
    const pageNum = src.page_number !== undefined ? src.page_number : (src.page !== undefined ? src.page : null);
    const pageLabel = isCsv ? "CSV Data" : (src.page_label || (pageNum != null ? `p. ${pageNum}` : "—"));

    let sourceUrl = src.source_url || src.url;
    if (!sourceUrl) {
      if (docName.toLowerCase().endsWith(".pdf")) {
        sourceUrl = `/api/files/${encodeURIComponent(docName)}${pageNum ? `#page=${pageNum}` : ""}`;
      } else if (isCsv) {
        sourceUrl = `/api/files/${encodeURIComponent(docName)}?download=true`;
      }
    }

    return {
      marker: item.marker || String(idx + 1),
      docName,
      pageNumber: pageNum,
      pageLabel,
      isCsv,
      sourceUrl,
    };
  });

  const table = (
    <div className="mf-provenance-table-wrap">
          <table className="mf-provenance-table">
            <thead>
              <tr>
                <th style={{ width: "48px" }}>#</th>
                <th style={{ width: "70%" }}>Source Document</th>
                <th style={{ width: "110px" }}>Page / Type</th>
              </tr>
            </thead>
            <tbody>
              {normalizedSources.map((row, idx) => (
                <tr key={idx} className="mf-provenance-row">
                  <td className="mf-cell-marker">
                    <span className="mf-provenance-marker-tag">[{row.marker}]</span>
                  </td>
                  <td className="mf-cell-doc">
                    {row.sourceUrl ? (
                      row.isCsv ? (
                        <a
                          href={row.sourceUrl}
                          download={row.docName}
                          className="mf-provenance-doc-link mf-provenance-download-link"
                          title={`Click to download ${row.docName} to your local system`}
                        >
                          <b>{row.docName}</b> <Download size={12} strokeWidth={2} style={{ verticalAlign: "-1px", marginLeft: 4 }} />
                        </a>
                      ) : (
                        <a
                          href={row.sourceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mf-provenance-doc-link"
                          title={`Open ${row.docName} in a new tab`}
                        >
                          <b>{row.docName}</b> <ExternalLink size={12} strokeWidth={1.75} style={{ verticalAlign: "-1px", marginLeft: 4 }} />
                        </a>
                      )
                    ) : (
                      <b>{row.docName}</b>
                    )}
                  </td>
                  <td className="mf-cell-page">
                    <span className="mf-page-badge">{row.pageLabel}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
    </div>
  );

  // Inside the Evidence card the section header already provides the collapse,
  // so a second one just nests two chevrons around the same table.
  if (flat) {
    return <div className="mf-provenance-container mf-provenance-container--flat">{table}</div>;
  }

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
        {table}
      </details>
    </div>
  );
}
