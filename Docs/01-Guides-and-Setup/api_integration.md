# API Integration & Response Adapters

## 1. API Client Specifications

The frontend communicates with FastAPI endpoints via an Axios client configured in `frontend/src/utils/api.js`:
- **Base URL**: Dynamic fallback resolving from `VITE_API_BASE` -> `window.location.origin` -> `http://localhost:8000`.
- **Timeout**: 240,000 ms (240 seconds).
- **Retry Mechanism**: Exponential backoff on retryable HTTP codes (408, 429, 500, 502, 503, 504).

---

## 2. Response Adapter Contracts

To support seamless interchange between flat vector responses and hybrid graph responses, `frontend/src/utils/adapters.js` provides bidirectional transformation functions:

1. `_adapt_traditional(raw)`: Standardizes traditional vector responses to `{ answer, docs, total_tokens, total_time, telemetry_breakdown }`.
2. `_adapt_hybrid(raw)`: Standardizes ContextGraph hybrid responses into structured answers with confidence badges, matched entity highlights, provenance citations, and graph edges.
