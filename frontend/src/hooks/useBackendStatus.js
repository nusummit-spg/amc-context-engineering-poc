import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "../api/client";

// How often to poll while the tab is visible. Kept short so "demo -> live"
// feels instant once the backend comes up, without hammering the API.
const POLL_MS = 4000;

/**
 * Tracks backend reachability ("checking" | "live" | "demo") and re-checks:
 *   - on an interval, so a backend that starts *after* the page loads is
 *     picked up automatically instead of requiring a refresh
 *   - immediately whenever the tab regains focus/visibility, so switching
 *     back from the terminal where you just started the API feels instant
 *
 * Exposes a `refreshKey` that increments only when the status actually
 * *changes* (demo -> live or live -> demo), so consumers can use it as a
 * dependency to re-fetch real data the moment the backend comes online,
 * without re-fetching on every poll tick.
 */
export function useBackendStatus() {
  const [status, setStatus] = useState("checking"); // checking | live | demo
  const [refreshKey, setRefreshKey] = useState(0);
  const statusRef = useRef(status);

  const check = useCallback(async () => {
    let next;
    try {
      await api.getStatus();
      next = "live";
    } catch {
      next = "demo";
    }
    const prev = statusRef.current;
    statusRef.current = next;
    if (prev !== next) {
      // Only bump refreshKey on a real transition, and skip the very first
      // resolution (checking -> live/demo) since consumers already fetch
      // on mount — this avoids a redundant duplicate fetch on load.
      if (prev !== "checking") setRefreshKey((k) => k + 1);
      setStatus(next);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer;

    const tick = async () => {
      if (cancelled) return;
      await check();
      if (!cancelled) timer = setTimeout(tick, POLL_MS);
    };
    tick();

    const onVisible = () => { if (document.visibilityState === "visible") check(); };
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      clearTimeout(timer);
      window.removeEventListener("focus", check);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [check]);

  return { status, refreshKey };
}
