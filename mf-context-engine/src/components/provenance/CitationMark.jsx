import React from "react";
import Tooltip from "./Tooltip";
import "./CitationMark.css";

export default function CitationMark({ citation, marker }) {
  if (!citation) {
    return (
      <span className="mf-cite-mark mf-cite-mark--fallback">
        [{marker}]
      </span>
    );
  }

  const src = citation.source || citation;
  const docTitle = src.document_name || src.document_title || src.name || src.doc || "Source Document";
  const pageNum = src.page_number !== undefined ? src.page_number : src.page;
  const pageLabel = src.page_label || (pageNum != null ? `p. ${pageNum}` : "—");
  const snippet = src.snippet || src.verbatim_text || src.full_text || "";
  
  let sourceUrl = src.source_url || src.url;
  if (!sourceUrl && docTitle.toLowerCase().endsWith(".pdf")) {
    sourceUrl = `/api/files/${encodeURIComponent(docTitle)}${pageNum ? `#page=${pageNum}` : ""}`;
  }

  const tooltipContent = (
    <div>
      <div className="mf-tooltip-title">
        <span>📄 {docTitle}</span>
        <span className="mf-tooltip-badge">{pageLabel}</span>
      </div>
      {snippet && (
        <div className="mf-tooltip-snippet">
          "{snippet.length > 360 ? snippet.slice(0, 360) + "…" : snippet}"
        </div>
      )}
      <div className="mf-tooltip-footer">
        <span>Citation [{marker}]</span>
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mf-tooltip-link"
            onClick={(e) => e.stopPropagation()}
          >
            Open Document ↗
          </a>
        ) : (
          <span>(Document unlinked)</span>
        )}
      </div>
    </div>
  );

  return (
    <Tooltip content={tooltipContent} placement="top" maxWidth={440} minWidth={340}>
      <span className="mf-cite-mark" aria-label={`Citation ${marker}: ${docTitle} ${pageLabel}`}>
        [{marker}]
      </span>
    </Tooltip>
  );
}
