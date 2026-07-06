import { useEffect, useRef, useState, useCallback } from "react";
import { ApiError } from "../api/client";

/**
 * Runs `fetcher(signal)` and tracks {data, loading, error, isMock}.
 *
 * If the API is unreachable (network_error) or returns a 502 upstream error
 * (Neo4j/Qdrant down) and a `mockValue` was supplied, the hook falls back to
 * that fixture and flags `isMock: true` so the UI can show a "demo data"
 * notice instead of a hard failure. Real 4xx errors (bad request, not found)
 * still surface as errors — the backend is reachable, so the failure is real.
 */
export function useResource(fetcher, { deps = [], mockValue = undefined, enabled = true } = {}) {
  const [state, setState] = useState({ data: undefined, loading: enabled, error: null, isMock: false });
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback((signal) => {
    if (!enabled) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    Promise.resolve()
      .then(() => fetcherRef.current(signal))
      .then((data) => {
        if (signal?.aborted) return;
        setState({ data, loading: false, error: null, isMock: false });
      })
      .catch((err) => {
        if (signal?.aborted) return;
        const isConnectivity = err instanceof ApiError && (err.status === 0 || err.status === 502);
        if (isConnectivity && mockValue !== undefined) {
          setState({ data: mockValue, loading: false, error: null, isMock: true });
        } else {
          setState({ data: undefined, loading: false, error: err, isMock: false });
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, mockValue]);

  useEffect(() => {
    const controller = new AbortController();
    run(controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { ...state, reload: () => run() };
}
