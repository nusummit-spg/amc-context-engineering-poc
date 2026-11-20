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
 * The API calls the verified pilot perimeter admits (backend/app/api/pilot_perimeter31.py).
 * Everything else is answered 503 by the backend, so in pilot mode the client refuses those calls
 * itself, quietly and before any network request. This must equal the backend allowlist; a Python
 * test compares the two so they cannot drift apart.
 */
export const PILOT_ALLOWED_API = [
  "POST /api/auth/login", "POST /api/auth/logout", "GET /api/auth/me",
  "POST /api/query", "POST /api/query/v2", "POST /api/query/stream",
  "POST /api/chat", "POST /api/chat/query", "POST /api/chat/v2", "POST /api/chat/stream",
  "GET /api/health",
];
export const PILOT_ALLOWED_API_PREFIXES = ["GET /api/publication/status/"];
/**
 * Wave 4.0 reviewed routes (backend W40_ROUTES in pilot_perimeter31.py; a Python test keeps them equal).
 * POST /api/feedback/v40 is also gated by AMC_PILOT_FEEDBACK on the server: when off it is denied there.
 */
export const PILOT_W40_API = ["GET /api/ready", "GET /api/suggestions/v40", "POST /api/feedback/v40"];

export class PilotDisabledError extends Error {
  constructor(method, path) {
    super(`${method} ${path} is not available in the read-only pilot`);
    this.name = "PilotDisabledError";
    this.pilotDisabled = true;
  }
}

/** True when the pilot perimeter would admit this call. `path` is the full path, e.g. /api/query. */
export function isPilotApiAllowed(method, path) {
  const clean = String(path || "").split("?")[0].split("#")[0];
  const key = `${String(method || "GET").toUpperCase()} ${clean}`;
  return PILOT_ALLOWED_API.includes(key) || PILOT_W40_API.includes(key)
    || PILOT_ALLOWED_API_PREFIXES.some((p) => key.startsWith(p));
}

/** Navigation and features the pilot hides because their backend routes are denied. */
export function pilotHidesFeature(pilot = isPilotMode()) {
  return pilot === true;
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
