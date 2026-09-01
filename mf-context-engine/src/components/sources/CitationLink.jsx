/**
 * Renders a source citation entry as a clickable PDF link or unavailable indicator.
 * Opens actual document in a new browser tab with page anchoring where available.
 */
export default function CitationLink({ index, title, url, page }) {
  const displayTitle = title || `Document ${index}`;
  const effectiveUrl = url || null;

  if (!effectiveUrl) {
    return (
      <div className="cg-citation-item cg-citation--unavailable" title="Source document unavailable on disk">
        <span className="cg-citation-num">[{index}]</span>
        <span className="cg-citation-title">{displayTitle}</span>
        <span className="cg-citation-unavailable-badge">(source unavailable)</span>
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
