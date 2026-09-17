# Correction Patch Layer — Methodology & Routes

This is a standalone zoom-in on one box from the main architecture: the **Correction Patch Layer**. It covers the patch object itself, both ways it intercepts the response pipeline, and every route a patch can take from creation to either going live, getting escalated, or dying out.

---

## Flowchart — all routes through the Patch Layer

```mermaid
flowchart TD

    A0["Confirmed Correction<br/>from Resolution stage<br/>(HITL-confirmed OR self-adjudicated)"] --> A1["Build CorrectionPatch object<br/>scope: entity/edge/attribute (narrow, not whole-entity)<br/>original_claim, corrected_claim<br/>provenance tag, confidence score<br/>evidence_refs, TTL"]

    A1 --> B0{"Scope already has<br/>an active patch?"}
    B0 -->|Yes — conflict| B1["Conflict Detected<br/>do NOT last-write-wins"]
    B1 --> B2["Route to Evaluation / HITL Arbitration<br/>two disagreeing signals is itself a finding"]
    B2 --> A1

    B0 -->|No conflict| C0["GNN Re-score the CORRECTED claim<br/>run the fix itself through the same<br/>structural plausibility scorer"]

    C0 --> C1{"Corrected claim<br/>structurally plausible?"}
    C1 -->|No — fix looks worse than original| C2["Do NOT auto-apply<br/>Escalate to HITL / LLM Evaluator"]
    C2 --> D0

    C1 -->|Yes| D0{"Confidence tier?"}

    D0 -->|"High<br/>(HITL-confirmed, above threshold)"| E1["Auto-apply path"]
    D0 -->|"Low<br/>(self-adjudicated, below threshold)"| E2["Log but hold<br/>do not apply yet"]

    E2 --> E3{"Corroboration arrives?<br/>2nd user hits same issue,<br/>or governance acts early"}
    E3 -->|Yes| E1
    E3 -->|No, before TTL expiry| F0["TTL Expiry"]
    F0 --> F1["Patch auto-expires<br/>status: expired, logged"]

    E1 --> G0["Rate / Anomaly Check<br/>same entity patched repeatedly?<br/>one user/session dominating patches?"]
    G0 -->|Anomaly flagged| G1["Hold + flag for governance<br/>possible feedback poisoning"]
    G1 --> B2

    G0 -->|Clean| H0["Lightweight Regression Check<br/>small known-good Q&A set for this entity<br/>NOT the full offline regression suite"]
    H0 --> H1{"Passes?"}
    H1 -->|No| C2
    H1 -->|Yes| I0["Patch goes LIVE — status: provisional"]

    I0 --> J0["Two application points"]
    J0 --> J1["Retrieval-time key lookup<br/>exact entity/edge ID match<br/>primary path when resolution is clean"]
    J0 --> J2["Indexed as retrievable 'correction card'<br/>in the vector index<br/>stricter similarity threshold than normal retrieval<br/>catches differently-phrased queries"]

    J1 --> K0["Context Assembly"]
    J2 --> K0

    K0 --> K1["Patch shown SEPARATE from canonical evidence<br/>labeled: provisional, confidence, provenance<br/>instruction: prefer correction on conflict,<br/>state fact is under review"]

    K1 --> L0["Response delivered to user"]
    L0 --> L1["Outcome Logging<br/>application_count, last_applied_at,<br/>did satisfaction improve on this entity after patch?"]

    L1 --> M0["Feeds back into Evidence Capture<br/>same record type as everything else"]

    I0 --> N0["Still queued in parallel:<br/>Human Governance Queue — weekly batch"]
    N0 --> N1{"Approved?"}
    N1 -->|Yes| N2["Canonical KG Update + Reindex<br/>patch retires — status: ratified"]
    N1 -->|No| N3["Patch revoked<br/>status: revoked, logged"]

    M0 -.feeds evidence for.-> N1
```

---

## The routes, named

| Route | Trigger | Outcome |
|---|---|---|
| **Conflict route** | New patch targets scope with an existing active patch | Never silently overwritten — always kicked to arbitration, treated as a finding, not noise |
| **Self-defeating fix route** | GNN re-scores the *corrected* claim and finds it implausible | Blocked before it ever applies — protects specifically against Pathway 2 (no human involved) producing a bad fix |
| **High-confidence route** | HITL-confirmed, above threshold | Straight to rate check → regression check → live |
| **Low-confidence hold route** | Self-adjudicated, below threshold | Logged but withheld until either a second corroborating signal arrives or it expires unratified — bounded exposure by construction |
| **Anomaly route** | Repeated patches on one entity, or one source dominating patch creation | Held and flagged rather than applied — this is the feedback-poisoning defense |
| **Regression-fail route** | Lightweight known-good check fails for this entity | Rejected the same way a structurally-bad fix is rejected |
| **Live-and-governed route** | Passes every gate above | Applied immediately (fast lane) **and** queued for the weekly canonical review (slow lane) at the same time — these are not sequential, they run in parallel |
| **Expiry route** | Never corroborated or ratified before TTL | Auto-dies — this is what stops a provisional patch from becoming permanent by inertia alone |

## The two threads that never merge

Notice the diagram splits into two parallel destinations once a patch goes live (`I0`):

- **Fast lane** (`J0` onward) — governs what the *LLM shows users*, right now, reversibly.
- **Slow lane** (`N0` onward) — governs what the *knowledge graph itself* contains, permanently, only via governance.

A patch can be live in the fast lane for weeks while still sitting unratified in the slow lane — that gap is intentional, not a bug. It's what lets behavior improve immediately without letting any single patch become ground truth on its own.
