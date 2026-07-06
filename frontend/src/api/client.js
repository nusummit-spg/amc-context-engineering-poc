// API client for the NuSummit ContextGraph backend.
//
// Base URL resolves from VITE_API_BASE_URL (see .env.example). Every call
// throws an ApiError with .status / .code / .detail on non-2xx responses so
// callers can render the structured {error:{code,message,detail}} shape the
// backend returns (see backend/app/core/errors.py).

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, { status, code, detail, path } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code || "unknown_error";
    this.detail = detail || {};
    this.path = path;
  }
}

async function request(path, { method = "GET", body, isForm = false, signal } = {}) {
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: isForm ? undefined : { "Content-Type": "application/json" },
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
      signal,
    });
  } catch (networkErr) {
    throw new ApiError(
      "Could not reach the ContextGraph API. Is the backend running?",
      { status: 0, code: "network_error", detail: { cause: String(networkErr) } }
    );
  }

  if (!res.ok) {
    let payload = null;
    try { payload = await res.json(); } catch { /* no body */ }
    const err = payload?.error;
    throw new ApiError(err?.message || `Request failed (${res.status})`, {
      status: res.status,
      code: err?.code || "http_error",
      detail: err?.detail,
      path: err?.path || path,
    });
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  baseUrl: BASE_URL,

  // ---- /status ----------------------------------------------------------
  getStatus: (signal) => request("/status", { signal }),

  // ---- /query -------------------------------------------------------------
  runQuery: ({ query, mode = "contextgraph", top_k }, signal) =>
    request("/query", { method: "POST", body: { query, mode, top_k }, signal }),

  // ---- /taxonomy ----------------------------------------------------------
  getTaxonomyTree: (signal) => request("/taxonomy", { signal }),
  getTaxonomyNodeDocs: (path, signal) =>
    request(`/taxonomy/node/docs?path=${encodeURIComponent(path)}`, { signal }),
  getTaxonomyHighlight: (query, signal) =>
    request(`/taxonomy/highlight?query=${encodeURIComponent(query)}`, { signal }),

  // ---- /graph ---------------------------------------------------------------
  getFullGraph: (limit = 500, signal) => request(`/graph?limit=${limit}`, { signal }),
  getNeighborhood: (name, depth = 1, signal) =>
    request(`/graph/neighborhood?name=${encodeURIComponent(name)}&depth=${depth}`, { signal }),
  getTraversalHighlight: (query, signal) =>
    request(`/graph/traversal?query=${encodeURIComponent(query)}`, { signal }),

  // ---- /docs ----------------------------------------------------------------
  listDocuments: (signal) => request("/docs", { signal }),
  getDocument: (documentId, signal) => request(`/docs/${encodeURIComponent(documentId)}`, { signal }),

  // ---- /ingest --------------------------------------------------------------
  ingestFile: (file, signal) => {
    const form = new FormData();
    form.append("file", file);
    return request("/ingest/file", { method: "POST", body: form, isForm: true, signal });
  },
  getIngestStatus: (jobId, signal) => request(`/ingest/status/${jobId}`, { signal }),
};
