import React from "react";
import { Download, ExternalLink } from "lucide-react";
import { PILOT_SOURCE_DISABLED_TEXT, isPilotMode, pilotSafeSourceUrl } from "../../utils/pilotSources";

/**
 * Renders a source citation entry as a clickable PDF link or CSV download link.
 * Opens PDF document in a new browser tab with page anchoring.
 * Triggers direct attachment download for CSV files.
 */
export default function CitationLink({ index, title, url, page }) {
  const displayTitle = title || `Document ${index}`;
  const isCsv = displayTitle.toLowerCase().endsWith(".csv") || (url && url.toLowerCase().includes(".csv"));
  let effectiveUrl = url || null;
  if (!effectiveUrl && isCsv) {
    effectiveUrl = `/api/files/${encodeURIComponent(displayTitle)}?download=true`;
  }
  // Read-only pilot: raw document routes are denied, so show provenance without a dead link.
  const pilot = isPilotMode();
  effectiveUrl = pilotSafeSourceUrl(effectiveUrl, pilot);

  if (!effectiveUrl) {
    return (
      <div
        className="cg-citation-item cg-citation--unavailable"
        title={pilot ? PILOT_SOURCE_DISABLED_TEXT : "Source document unavailable on disk"}
      >
        <span className="cg-citation-num">[{index}]</span>
        <span className="cg-citation-title">{displayTitle}</span>
        {page && <span className="cg-citation-page-tag">p.{page}</span>}
        <span className="cg-citation-unavailable-badge">
          {pilot ? "(source view disabled in pilot)" : "(source unavailable)"}
        </span>
      </div>
    );
  }

  if (isCsv) {
    return (
      <div className="cg-citation-item">
        <span className="cg-citation-num">[{index}]</span>
        <a
          className="cg-citation-link cg-citation-download"
          href={effectiveUrl}
          download={displayTitle}
          title={`Click to download ${displayTitle} to your local system`}
        >
          {displayTitle}
          <Download size={11} strokeWidth={2} style={{ marginLeft: 4, verticalAlign: "-1px" }} />
        </a>
      </div>
    );
  }

  return (
    <div className="cg-citation-item">
      <span className="cg-citation-num">[{index}]</span>
      <a
        className="cg-citation-link"
        href={effectiveUrl}
        target="_blank"
        rel="noopener noreferrer"
        title={`Open ${displayTitle}${page ? ` at page ${page}` : ""} in a new tab`}
      >
        {displayTitle}
        {page && <span className="cg-citation-page-tag">p.{page}</span>}
      </a>
    </div>
  );
}
