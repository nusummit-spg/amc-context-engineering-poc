/**
 * Read-only verified pilot: source-document links.
 *
 * In the controlled pilot the backend perimeter denies the raw document routes
 * (/api/files, /files, /api/docs, /docs) with 503 on purpose. Linking to them would
 * produce dead links, so the UI shows the citation as non-clickable provenance
 * (title, page, snippet) instead. This is a UX guard only: the security boundary is
 * the backend perimeter, never this helper.
 *
 * Enable at build time with VITE_AMC_PILOT_MODE=true. Default is off, which keeps the
 * existing behavior for the non-pilot app.
 */

const DENIED_PATH_PREFIXES = ["/api/files", "/files", "/api/docs", "/docs"];

export const PILOT_SOURCE_DISABLED_TEXT = "Source document viewing is disabled in the read-only pilot";

export function isPilotMode(env = import.meta.env) {
  return String(env?.VITE_AMC_PILOT_MODE ?? "").toLowerCase() === "true";
}

/** True when `url` points at one of the raw document routes the pilot denies. */
export function isRawSourceUrl(url) {
  if (typeof url !== "string" || !url.trim()) return false;
  let pathname;
  try {
    pathname = new URL(url.trim(), "http://pilot.invalid").pathname;
  } catch {
    return false;
  }
  let decoded = pathname;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    /* keep the undecoded path */
  }
  const lowered = decoded.toLowerCase();
  return DENIED_PATH_PREFIXES.some(
    (prefix) => lowered === prefix || lowered.startsWith(prefix + "/")
  );
}

/**
 * Returns the URL to render, or null when the pilot would only produce a dead link.
 * Outside pilot mode the URL is returned unchanged.
 */
export function pilotSafeSourceUrl(url, pilot = isPilotMode()) {
  if (!url) return url ?? null;
  if (!pilot) return url;
  return isRawSourceUrl(url) ? null : url;
}
