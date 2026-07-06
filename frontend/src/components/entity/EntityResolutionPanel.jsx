import { useState } from "react";
import { api } from "../../api/client";
import { MOCK_ALIASES } from "../../data/mockData";
import { TYPE_COLOR } from "../graph/graphLayout";
import { ErrorBanner } from "../common/Banners";
import "./EntityResolutionPanel.css";

function AliasCard({ entity }) {
  const [resolved, setResolved] = useState(false);
  return (
    <div className={`alias-card ${resolved ? "is-resolved" : ""}`}>
      <button className="alias-card__toggle" onClick={() => setResolved((r) => !r)}>
        {resolved ? "Show raw aliases" : "Resolve aliases"}
      </button>

      <div className="alias-card__stage">
        <div className="alias-card__aliases">
          {entity.aliases.map((a, i) => (
            <span
              className="alias-pill"
              key={a}
              style={{ transitionDelay: `${i * 45}ms` }}
            >
              {a}
            </span>
          ))}
        </div>

        <div className="alias-card__arrow" aria-hidden="true">
          <svg width="40" height="16" viewBox="0 0 40 16"><path d="M0 8 H32 M24 2 L32 8 L24 14" stroke="currentColor" strokeWidth="1.6" fill="none" /></svg>
        </div>

        <div className="alias-card__canonical">
          <span className="alias-node" style={{ "--node-color": TYPE_COLOR[entity.entity_type] }}>
            <span className="alias-node__dot" />
            <span>
              <strong>{entity.canonical_name}</strong>
              <span className="badge">{entity.entity_type}</span>
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}

export default function EntityResolutionPanel() {
  const [probe, setProbe] = useState("");
  const [probeState, setProbeState] = useState({ loading: false, error: null, data: null });

  async function runProbe(e) {
    e.preventDefault();
    if (!probe.trim()) return;
    setProbeState({ loading: true, error: null, data: null });
    try {
      const data = await api.getNeighborhood(probe.trim(), 1);
      setProbeState({ loading: false, error: null, data });
    } catch (err) {
      setProbeState({ loading: false, error: err, data: null });
    }
  }

  return (
    <div className="entity-panel">
      <div className="card entity-panel__intro">
        <h3>Alias → canonical resolution</h3>
        <p>
          The extraction pipeline records every surface form an entity appears under across the corpus.
          At query time, the resolver collapses whichever alias was mentioned back to one canonical graph node —
          this is what makes “Adani”, “the Adani group”, and “APSEZ” all count toward the same exposure figure.
        </p>
        <form className="entity-panel__probe" onSubmit={runProbe}>
          <input
            type="text"
            placeholder="Try a live alias, e.g. “APSEZ” or “Bajaj Fin.”"
            value={probe}
            onChange={(e) => setProbe(e.target.value)}
          />
          <button className="btn btn--clay" type="submit" disabled={probeState.loading}>
            {probeState.loading ? "Resolving…" : "Resolve against API"}
          </button>
        </form>
        {probeState.error && <ErrorBanner error={probeState.error} title="Couldn't resolve that alias" />}
        {probeState.data && (
          <div className="entity-panel__probe-result">
            <span className="eyebrow">Resolved neighborhood</span>
            <div className="entity-panel__probe-nodes">
              {probeState.data.nodes.map((n) => (
                <span className="badge badge--clay" key={n.id}>{n.label} · {n.entity_type}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="entity-panel__grid">
        {MOCK_ALIASES.map((entity) => (
          <AliasCard entity={entity} key={entity.node_id} />
        ))}
      </div>
    </div>
  );
}
