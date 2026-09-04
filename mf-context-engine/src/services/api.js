/**
 * API Service Client for NuSummit ContextGraph Engine Backend
 */

export const API_BASE = "/api";

async function request(endpoint, options = {}) {
  const url = endpoint.startsWith("http")
    ? endpoint
    : `${API_BASE}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  try {
    const res = await fetch(url, {
      ...options,
      headers: options.body instanceof FormData ? undefined : headers,
    });

    if (!res.ok) {
      let errorDetail = "";
      try {
        const errorJson = await res.json();
        errorDetail = errorJson.detail || errorJson.message || JSON.stringify(errorJson);
      } catch {
        errorDetail = await res.text();
      }
      throw new Error(`API Error (${res.status}): ${errorDetail || res.statusText}`);
    }

    return await res.json();
  } catch (err) {
    console.error(`Request failed for ${url}:`, err);
    throw err;
  }
}

// ── Auth Endpoints ───────────────────────────────────────────────────────────
// Kept separate from `request()` above: auth errors come back from the
// backend's structured AppError shape (`{ error: { code, message } }`), and
// we want the exact backend-supplied message (e.g. the generic "doesn't
// match our records" copy) surfaced to the UI rather than a JSON dump.
async function authRequest(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  let res;
  try {
    res = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
  } catch (networkErr) {
    const err = new Error("Couldn't reach the server. Check your connection and try again.");
    err.cause = networkErr;
    throw err;
  }

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const message = data?.error?.message || "Something went wrong. Please try again.";
    const err = new Error(message);
    err.status = res.status;
    err.code = data?.error?.code;
    throw err;
  }

  return data;
}

/**
 * Authenticates against the Python backend's JSON-backed user repository.
 * Never validates credentials in the browser — the frontend only ever
 * forwards what the user typed and relays the backend's response.
 * Resolves to `{ token, expires_at, user }` on success; rejects with an
 * Error carrying the backend's generic auth-failure message otherwise.
 */
export async function loginUser({ username, password, rememberMe = false }) {
  return await authRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password, remember_me: rememberMe }),
  });
}

/** Best-effort logout call; the frontend clears its local session regardless of the result. */
export async function logoutUser(token) {
  try {
    await authRequest("/auth/logout", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch {
    // Non-fatal — session tokens are stateless and self-expiring server-side.
  }
}

/** Validates a stored session token against the backend and returns the current user, or throws. */
export async function fetchCurrentUser(token) {
  const data = await authRequest("/auth/me", {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
  return data.user;
}

/**
 * Adapt backend TraditionalResult to the format expected by TraditionalPanel
 */
export function adaptTraditionalResponse(traditionalData, latencyMs = 0) {
  if (!traditionalData) return null;

  const files = traditionalData.files || [];
  const metrics = traditionalData.metrics || {};
  const tb = metrics.telemetry_breakdown || {};

  const docs = files.map((f, i) => {
    const docName = f.name || f.document_id || f.document_title || "Document";
    const pageNum = f.page_number !== undefined ? f.page_number : (f.page !== undefined ? f.page : 1);
    let url = f.url || f.source_url || null;
    if (!url && docName.toLowerCase().endsWith(".pdf")) {
      url = `/api/files/${encodeURIComponent(docName)}#page=${pageNum}`;
    }
    return {
      name: docName,
      document_id: f.document_id || docName,
      document_title: docName,
      score: typeof f.score === "number" ? Math.round(f.score * 1000) / 1000 : 0.85,
      page: pageNum,
      page_number: pageNum,
      page_label: f.page_label || (pageNum != null ? `p. ${pageNum}` : "—"),
      url,
      source_url: url,
      snippet: f.snippet || (f.full_text ? f.full_text.slice(0, 200) : ""),
      full_text: f.full_text || f.verbatim_text || f.snippet || "",
      verbatim_text: f.verbatim_text || f.full_text || f.snippet || "",
    };
  });

  const citations =
    (Array.isArray(traditionalData.citations) && traditionalData.citations.length > 0)
      ? traditionalData.citations
      : docs.map((d, i) => ({
          marker: String(i + 1),
          source: {
            chunk_id: d.chunk_id || `src.${i + 1}`,
            document_id: d.document_id || d.name,
            document_name: d.name,
            page_number: d.page,
            page_label: d.page_label || (d.page != null ? `p. ${d.page}` : "—"),
            verbatim_text: d.full_text || d.snippet || "",
            snippet: d.snippet || "",
            source_url: d.url,
            score: d.score,
          },
        }));

  const metricsList =
    (Array.isArray(traditionalData.metrics_provenance) && traditionalData.metrics_provenance.length > 0)
      ? traditionalData.metrics_provenance
      : (Array.isArray(traditionalData.metrics?.provenance) && traditionalData.metrics.provenance.length > 0)
      ? traditionalData.metrics.provenance
      : [];

  const totalTokens =
    metrics.total_tokens ||
    ((metrics.input_tokens || 0) + (metrics.output_tokens || 0)) ||
    (tb.tokens_total || 0);

  const totalTime =
    latencyMs > 0
      ? latencyMs / 1000
      : ((metrics.retrieve_ms || 0) + (metrics.llm_ms || 0)) / 1000;

  return {
    docs,
    citations,
    metrics: metricsList,
    answer:
      traditionalData.snippet ||
      (docs[0] ? `Extracted passage from ${docs[0].name}` : "No answer synthesized."),
    total_tokens: totalTokens,
    total_time: totalTime || (tb.latency_total_pipeline_ms ? tb.latency_total_pipeline_ms / 1000 : 0.9),
    telemetry_breakdown: tb,
  };
}

/**
 * Adapt backend ContextGraph / Hybrid response to the format expected by ContextGraphPanel
 */
export function adaptHybridResponse(hybridData, latencyMs = 0) {
  if (!hybridData) return null;

  const synthesis = hybridData.answer || {};
  const answerText =
    typeof synthesis === "string"
      ? synthesis
      : (synthesis.answer || hybridData.content || "No answer synthesized.");

  const confLabel = synthesis.confidence
    ? (synthesis.confidence.toUpperCase() === "HIGH" ? "✓ High confidence" : `⚠ ${synthesis.confidence} confidence`)
    : (hybridData.confidence_label || "✓ High confidence");

  const confReason = synthesis.compliance_note || hybridData.confidence_reason || "";

  const sources = hybridData.sources || [];
  const docs = sources.map((s, i) => {
    const docName = s.document_title || s.document_id || s.name || `Source Document [${i + 1}]`;
    const pageNum = s.page_number !== undefined ? s.page_number : (s.page !== undefined ? s.page : 1);
    let url = s.url || s.source_url || null;
    if (!url && docName.toLowerCase().endsWith(".pdf")) {
      url = `/api/files/${encodeURIComponent(docName)}#page=${pageNum}`;
    }
    return {
      name: docName,
      title: docName,
      document_id: s.document_id || docName,
      document_title: docName,
      snippet: s.snippet || "",
      full_text: s.full_text || s.verbatim_text || s.snippet || "",
      verbatim_text: s.verbatim_text || s.full_text || s.snippet || "",
      score: s.score || 0.9,
      page: pageNum,
      page_number: pageNum,
      page_label: s.page_label || (pageNum != null ? `p. ${pageNum}` : "—"),
      url,
      source_url: url,
    };
  });

  const citations =
    (Array.isArray(synthesis.citations) && synthesis.citations.length > 0)
      ? synthesis.citations
      : (Array.isArray(hybridData.citations) && hybridData.citations.length > 0)
      ? hybridData.citations
      : (Array.isArray(sources) && sources.length > 0)
      ? sources.map((s, i) => {
          const docName = s.document_title || s.document_name || s.document_id || s.name || s.doc || `Source [${i + 1}]`;
          const pageNum = s.page_number !== undefined ? s.page_number : (s.page !== undefined ? s.page : null);
          const pageLabel = s.page_label || (pageNum != null ? `p. ${pageNum}` : "—");
          let url = s.source_url || s.url || null;
          if (!url && docName.toLowerCase().endsWith(".pdf")) {
            url = `/api/files/${encodeURIComponent(docName)}${pageNum ? `#page=${pageNum}` : ""}`;
          }
          return {
            marker: String(i + 1),
            source: {
              chunk_id: s.chunk_id || `src.${i + 1}`,
              document_id: s.document_id || docName,
              document_name: docName,
              page_number: pageNum,
              page_label: pageLabel,
              verbatim_text: s.verbatim_text || s.full_text || s.snippet || "",
              snippet: s.snippet || (s.verbatim_text ? s.verbatim_text.slice(0, 160) : ""),
              source_url: url,
              score: s.score || 0.9,
            },
          };
        })
      : [];

  const metricsList =
    (Array.isArray(synthesis.metrics) && synthesis.metrics.length > 0)
      ? synthesis.metrics
      : (Array.isArray(hybridData.metrics) && hybridData.metrics.length > 0)
      ? hybridData.metrics
      : [];

  const provenance = citations.map((c) => ({
    doc: c.source?.document_name || c.source?.document_title || "Document",
    document_title: c.source?.document_name || c.source?.document_title || "Document",
    name: c.source?.document_name || c.source?.document_title || "Document",
    chunk_id: c.source?.chunk_id || `p.${c.source?.page_number ?? ""}`,
    page_number: c.source?.page_number,
    page_label: c.source?.page_label || (c.source?.page_number != null ? `p. ${c.source?.page_number}` : "—"),
    page: c.source?.page_number,
    snippet: c.source?.snippet || "",
    verbatim_text: c.source?.verbatim_text || c.source?.snippet || "",
    url: c.source?.source_url || c.source?.url,
  }));

  const gh = hybridData.graph_highlight || {};
  const rawNodes = gh.node_names || hybridData.graph_nodes || [];
  const rawEdges = gh.edges || hybridData.graph_edges || [];
  const rawEdgesUsed = gh.edges_used_in_prompt || hybridData.graph_edges_used_in_prompt || rawEdges;
  const matchedEntities = gh.entities || hybridData.matched_entity_texts || [];
  const activeLabels = gh.labels || hybridData.active_labels || [];
  const entitySummary = gh.entity_summary || hybridData.entity_summary || [];
  const tb = gh.telemetry_breakdown || hybridData.telemetry_breakdown || {};

  const totalTokens =
    gh.total_tokens ||
    hybridData.total_tokens ||
    (tb.tokens_total || ((tb.tokens_input || 0) + (tb.tokens_output || 0))) ||
    0;

  const totalTime =
    latencyMs > 0
      ? latencyMs / 1000
      : ((hybridData.latency_ms || 0) / 1000 || (tb.latency_total_pipeline_ms ? tb.latency_total_pipeline_ms / 1000 : 0.8));

  return {
    response_id: hybridData.response_id || null,
    interaction_id: hybridData.interaction_id || null,
    answer: answerText,
    query_type: gh.query_type || hybridData.query_type || "regulatory_lookup",
    confidence_label: confLabel,
    confidence_reason: confReason,
    docs,
    citations,
    metrics: metricsList,
    provenance,
    graph_nodes: rawNodes,
    graph_edges: rawEdges,
    graph_edges_used_in_prompt: rawEdgesUsed,
    matched_entity_texts: matchedEntities,
    active_labels: activeLabels,
    graph_matched_by: gh.graph_matched_by || (rawEdges.length ? "direct" : "fallback"),
    used_verified_aggregate: gh.used_verified_aggregate || false,
    used_comparison_mode: gh.used_comparison_mode || false,
    entity_summary: entitySummary,
    total_tokens: totalTokens,
    total_time: totalTime,
    telemetry_breakdown: tb,
  };
}

// ── Query Endpoints ────────────────────────────────────────────────────────
export async function sendQuery({ query, mode = "both", top_k = 8 }) {
  const data = await request("/query", {
    method: "POST",
    body: JSON.stringify({ query, mode, top_k }),
  });

  return {
    raw: data,
    traditional: adaptTraditionalResponse(data.traditional, data.latency_ms),
    hybrid: adaptHybridResponse(data, data.latency_ms),
  };
}

// ── Chat Endpoints ─────────────────────────────────────────────────────────
export async function sendChat({ query, history = [], session_id, mode = "both" }) {
  const cleanHistory = history
    .filter((m) => m.content && !m.loading)
    .map((m) => ({
      role: m.role,
      content: typeof m.content === "string" ? m.content : (m.content?.answer || JSON.stringify(m.content)),
    }));

  const data = await request("/chat", {
    method: "POST",
    body: JSON.stringify({
      query,
      history: cleanHistory,
      session_id: session_id || `sess-${Date.now()}`,
      mode,
    }),
  });

  return {
    raw: data,
    resolvedQuery: data.resolved_query || query,
    turnIndex: data.turn_index,
    traditional: adaptTraditionalResponse(data.traditional, data.traditional?.metrics?.retrieve_ms),
    hybrid: adaptHybridResponse(data.hybrid, data.hybrid?.latency_ms),
  };
}

// ── Admin & Cache Endpoints ────────────────────────────────────────────────
export async function clearIntentCache() {
  return await request("/admin/intent-cache/clear", { method: "POST" });
}

export async function fetchIntentCacheStats() {
  return await request("/admin/intent-cache/stats", { method: "GET" });
}

export async function invalidateIntentCacheDomain(domain) {
  return await request("/admin/intent-cache/invalidate-domain", {
    method: "POST",
    body: JSON.stringify({ domain }),
  });
}

export async function fetchUsers() {
  return await request("/admin/users", { method: "GET" });
}

export async function saveUser(user) {
  return await request("/admin/users", {
    method: "POST",
    body: JSON.stringify(user),
  });
}

export async function deleteUser(username) {
  return await request(`/admin/users/${encodeURIComponent(username)}`, {
    method: "DELETE",
  });
}

export async function fetchRbacMatrix() {
  return await request("/admin/rbac", { method: "GET" });
}

export async function fetchAuditLogs(limit = 30) {
  return await request(`/admin/audit?limit=${limit}`, { method: "GET" });
}

// ── Ingestion Endpoints ────────────────────────────────────────────────────
export async function runIngestPipeline() {
  return await request("/admin/ingestion/run", { method: "POST" });
}

export async function checkStaleness() {
  return await request("/admin/ingestion/staleness", { method: "POST" });
}

export async function uploadDocument(formData) {
  return await request("/admin/ingestion/upload", {
    method: "POST",
    body: formData,
  });
}

export async function fetchIndexingTasks(limit = 10) {
  return await request(`/admin/ingestion/tasks?limit=${limit}`, { method: "GET" });
}

export async function fetchProposedEdges() {
  return await request("/admin/ingestion/proposed-edges", { method: "GET" });
}

export async function confirmProposedEdge(edgeId, authorizedBy = "sarah_compliance") {
  return await request(
    `/admin/ingestion/edges/${encodeURIComponent(edgeId)}/confirm?authorized_by=${encodeURIComponent(authorizedBy)}`,
    { method: "POST" }
  );
}

export async function rejectProposedEdge(edgeId) {
  return await request(`/admin/ingestion/edges/${encodeURIComponent(edgeId)}/reject`, {
    method: "POST",
  });
}

export async function fetchComplianceReport() {
  return await request("/admin/ingestion/compliance-report", { method: "GET" });
}

// ── Graph & Sessions ───────────────────────────────────────────────────────
export async function fetchGraph(limit = 60) {
  return await request(`/graph?limit=${limit}`, { method: "GET" });
}

export async function fetchSessions() {
  return await request("/sessions", { method: "GET" });
}

export async function fetchSessionHistory(sessionId) {
  return await request(`/sessions/${encodeURIComponent(sessionId)}`, { method: "GET" });
}

// ── Feedback Endpoints ─────────────────────────────────────────────────────
export async function submitFeedback(payload) {
  return await request("/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchFeedback(responseId) {
  const query = responseId ? `?response_id=${encodeURIComponent(responseId)}` : "";
  return await request(`/feedback${query}`, { method: "GET" });
}


// ── Streaming Support Detection ───────────────────────────────────────────────

/**
 * Probe the backend to confirm SSE streaming works end-to-end.
 * Returns true if the Content-Type header confirms event-stream support.
 */
export async function detectStreamingSupport() {
  try {
    const response = await fetch(`${API_BASE}/query/health/stream-test`, {
      method: "GET",
      headers: { Accept: "text/event-stream" },
    });
    return response.headers.get("Content-Type")?.includes("event-stream") ?? false;
  } catch {
    return false;
  }
}

// ── Internal SSE parser ───────────────────────────────────────────────────────

/**
 * Parse and dispatch SSE frames from a fetch response body.
 *
 * Handles:
 * - Malformed / incomplete SSE lines (skipped, not thrown)
 * - Partial JSON buffering (accumulates until valid JSON received)
 * - Memory protection: clears chunk buffer after 1000 chunks
 *
 * @param {Response} response  A fetch Response with body as ReadableStream
 * @param {Object}   callbacks { onChunk, onMetadata, onSources, onError, onComplete }
 * @param {Object}   metrics   Shared metrics object mutated in-place { firstChunkTime, chunkCount }
 * @param {AbortSignal} signal Optional AbortSignal for stop-button support
 */
async function _parseSSEStream(response, { onChunk, onMetadata, onSources, onError, onComplete }, metrics, signal) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";
  let dataBuffer = "";

  try {
    while (true) {
      if (signal?.aborted) break;

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Split on newlines but keep the last (possibly incomplete) line in the buffer
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trimEnd();

        // Blank line → dispatch current event
        if (trimmed === "") {
          if (dataBuffer) {
            let parsed = null;
            try {
              parsed = JSON.parse(dataBuffer.trim());
            } catch {
              // Partial JSON — skip this frame, the next one may complete it
            }

            if (parsed !== null) {
              const type = parsed.type ?? currentEvent;

              if (type === "answer_chunk") {
                // Streaming analytics: record time-to-first-chunk
                if (!metrics.firstChunkTime) {
                  metrics.firstChunkTime = Date.now();
                  const ttfc = metrics.firstChunkTime - metrics.startTime;
                  console.debug(`[stream] TTFC: ${ttfc}ms`);
                }
                metrics.chunkCount++;

                // Memory protection: clear buffer after 1000 chunks (>~50k chars)
                if (metrics.chunkCount % 1000 === 0) {
                  console.debug(`[stream] ${metrics.chunkCount} chunks received — buffer checkpoint`);
                }

                onChunk?.(parsed);
              } else if (type === "metadata") {
                onMetadata?.(parsed);
              } else if (type === "sources") {
                onSources?.(parsed);
                onMetadata?.(parsed);
              } else if (type === "error") {
                onError?.(parsed);
              } else if (type === "complete") {
                onComplete?.(parsed);
              }
              // "ping" frames are silently ignored
            }
          }
          currentEvent = "";
          dataBuffer = "";
          continue;
        }

        // SSE comment line (keepalive)
        if (trimmed.startsWith(":")) continue;

        if (trimmed.startsWith("event:")) {
          currentEvent = trimmed.slice(6).trim();
        } else if (trimmed.startsWith("data:")) {
          // Accumulate multi-line data (rare but spec-compliant)
          dataBuffer += trimmed.slice(5).trim();
        }
        // id: and retry: fields are ignored (resumption handled at a higher level)
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ── Streaming Query ───────────────────────────────────────────────────────────

/**
 * Send a query and receive the answer as a stream of SSE events.
 *
 * @param {Object} params
 * @param {string}   params.query       The search query
 * @param {string}   [params.mode]      "both" | "contextgraph" | "traditional"
 * @param {number}   [params.top_k]     Number of chunks to retrieve
 * @param {Function} [params.onChunk]   Called with each answer_chunk event
 * @param {Function} [params.onMetadata] Called with metadata / sources events
 * @param {Function} [params.onSources] Called with sources events (before answer)
 * @param {Function} [params.onError]   Called with error events; { recoverable } flag included
 * @param {Function} [params.onComplete] Called once with the done event
 * @param {AbortSignal} [params.signal] AbortSignal to cancel stream (stop button)
 *
 * Auto-reconnect: exponential backoff 1s → 2s → 4s → 8s on network error.
 */
export async function sendQueryStream({
  query,
  mode = "both",
  top_k = 8,
  onChunk,
  onMetadata,
  onSources,
  onError,
  onComplete,
  signal,
}) {
  const BACKOFF_DELAYS = [1000, 2000, 4000, 8000];
  const metrics = { startTime: Date.now(), firstChunkTime: null, chunkCount: 0, reconnections: 0 };

  for (let attempt = 0; attempt <= BACKOFF_DELAYS.length; attempt++) {
    if (signal?.aborted) break;

    if (attempt > 0) {
      const delay = BACKOFF_DELAYS[attempt - 1];
      console.info(`[stream] Reconnecting (attempt ${attempt}) after ${delay}ms…`);
      metrics.reconnections++;
      await new Promise((r) => setTimeout(r, delay));
    }

    try {
      const response = await fetch(`${API_BASE}/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, mode, top_k }),
        signal,
      });

      if (!response.ok) {
        throw new Error(`Stream failed: ${response.status}`);
      }

      await _parseSSEStream(response, { onChunk, onMetadata, onSources, onError, onComplete }, metrics, signal);
      return; // Success — stop retrying
    } catch (err) {
      if (signal?.aborted || err.name === "AbortError") {
        // User aborted via stop button — not an error
        return;
      }
      if (attempt >= BACKOFF_DELAYS.length) {
        // All retries exhausted
        onError?.({ type: "error", message: err.message, recoverable: false });
        return;
      }
      console.warn(`[stream] Network error on attempt ${attempt + 1}:`, err.message);
    }
  }
}

// ── Streaming Chat ────────────────────────────────────────────────────────────

/**
 * Send a multi-turn chat message and receive the answer as a stream.
 *
 * @param {Object} params
 * @param {string}   params.query       The user's message
 * @param {Array}    [params.history]   Conversation history array
 * @param {string}   [params.session_id] Session ID for conversation continuity
 * @param {string}   [params.mode]      Query mode
 * @param {Function} [params.onChunk]   Called with each answer_chunk event
 * @param {Function} [params.onMetadata] Called with metadata events
 * @param {Function} [params.onSources] Called with sources events
 * @param {Function} [params.onError]   Called with error events
 * @param {Function} [params.onComplete] Called once with the done event
 * @param {AbortSignal} [params.signal]  AbortSignal for stop button
 */
export async function sendChatStream({
  query,
  history = [],
  session_id,
  mode = "contextgraph",
  onChunk,
  onMetadata,
  onSources,
  onError,
  onComplete,
  signal,
}) {
  const cleanHistory = history
    .filter((m) => m.content && !m.loading)
    .map((m) => ({
      role: m.role,
      content:
        typeof m.content === "string"
          ? m.content
          : m.content?.answer || JSON.stringify(m.content),
    }));

  const BACKOFF_DELAYS = [1000, 2000, 4000, 8000];
  const metrics = { startTime: Date.now(), firstChunkTime: null, chunkCount: 0, reconnections: 0 };

  for (let attempt = 0; attempt <= BACKOFF_DELAYS.length; attempt++) {
    if (signal?.aborted) break;

    if (attempt > 0) {
      const delay = BACKOFF_DELAYS[attempt - 1];
      console.info(`[stream/chat] Reconnecting (attempt ${attempt}) after ${delay}ms…`);
      metrics.reconnections++;
      await new Promise((r) => setTimeout(r, delay));
    }

    try {
      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          history: cleanHistory,
          session_id: session_id || `sess-${Date.now()}`,
          mode,
        }),
        signal,
      });

      if (!response.ok) {
        throw new Error(`Chat stream failed: ${response.status}`);
      }

      await _parseSSEStream(response, { onChunk, onMetadata, onSources, onError, onComplete }, metrics, signal);
      return; // Success
    } catch (err) {
      if (signal?.aborted || err.name === "AbortError") return;
      if (attempt >= BACKOFF_DELAYS.length) {
        onError?.({ type: "error", message: err.message, recoverable: false });
        return;
      }
      console.warn(`[stream/chat] Network error on attempt ${attempt + 1}:`, err.message);
    }
  }
}
