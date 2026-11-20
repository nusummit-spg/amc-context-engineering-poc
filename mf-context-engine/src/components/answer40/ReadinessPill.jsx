import { useEffect, useState } from "react";
import { fetchReadiness } from "../../services/api";
import "./answer40.css";

/** GET /api/ready, shown as a small status pill (TDS-40 E9/E11). Re-checked every minute while mounted. */
export default function ReadinessPill({ intervalMs = 60000 }) {
  const [ready, setReady] = useState(null);       // null = unknown yet

  useEffect(() => {
    let alive = true;
    const check = async () => {
      const result = await fetchReadiness();
      if (alive) setReady(result.ready);
    };
    check();
    const t = setInterval(check, intervalMs);
    return () => { alive = false; clearInterval(t); };
  }, [intervalMs]);

  if (ready === null) return null;
  return (
    <span className={`a40-ready ${ready ? "a40-ready--ok" : "a40-ready--down"}`} role="status"
          data-testid="readiness" data-ready={String(ready)}
          title={ready ? "All verified sources are available" : "Answers may be withheld until the verified service recovers"}>
      <span className="a40-ready-dot" aria-hidden="true" />
      {ready ? "Verified service ready" : "Verified service unavailable"}
    </span>
  );
}
