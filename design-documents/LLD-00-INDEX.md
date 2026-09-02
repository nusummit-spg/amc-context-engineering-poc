# AMC Feedback, Evaluation & Self-Healing RAG — Low Level Design Index

**Project:** AMC Context Engineering POC  
**Version:** 1.0  
**Status:** Design Baseline — August 2026  
**Authors:** Combined from multiple design contributions  
**Audience:** Engineering, Architecture, Compliance

---

## Document Map

This folder contains the complete low-level design for the AMC feedback loop, governed evaluation, and self-healing RAG system. Each document covers one concern in full depth.   

| Document | Title | Concern |
|---|---|---|
| **LLD-00** | This file | Index, decisions log, glossary |
| **LLD-01** | System Overview | Architecture vision, control planes, design boundaries |
| **LLD-02** | Evidence Capture | EvidencePack D0–D3, temporal claims, storage |
| **LLD-03** | Feedback Pipeline | Sync capture, async batch, PostgreSQL schema, token economics |
| **LLD-04** | Evaluation Router | 9 stages, E0–E5 ladder, stop rules, budget bands |
| **LLD-05** | Failure Taxonomy | F01–F14 families, R0–R5 repair classes, attribution graph |
| **LLD-06** | Self-Healing RAG | 3-level healing, R001–R012 recipes, shadow validation |
| **LLD-07** | Compliance Plane | C01–C14 controls, jurisdiction packs, data lineage |
| **LLD-08** | Data Models | All PostgreSQL DDL, Python schemas, API contracts |

---

## Reading Order

**For a new team member:** LLD-01 → LLD-02 → LLD-03 → LLD-04 → LLD-05  
**For an infrastructure engineer:** LLD-01 → LLD-08 → LLD-06  
**For a compliance reviewer:** LLD-01 → LLD-07 → LLD-05 → LLD-02  
**For a data engineer:** LLD-08 → LLD-02 → LLD-03  
**For a platform architect:** LLD-01 → LLD-04 → LLD-05 → LLD-06 → LLD-07

---

## Architecture Design Decisions Log

Each decision records what was chosen, what was rejected, and why. These are permanent records — do not delete superseded entries.

---

### ADR-001 — Freeze EvidencePack at response time, not evaluation time

**Status:** Accepted  
**Context:** Evaluation runs hours after response generation. Sources, graph edges, and embeddings change in the interim.  
**Decision:** Create an immutable D0–D3 snapshot immediately when a response is generated. All evaluators reference this frozen object.  
**Rejected alternative:** Re-fetch evidence at evaluation time.  
**Consequence:** Evaluation is reproducible. Later source updates do not retroactively change verdicts. Audit trail is reliable.

---

### ADR-002 — Deterministic-first evaluation; LLM is a last resort

**Status:** Accepted  
**Context:** LLM evaluation is expensive, slow, and nondeterministic. Most AMC failures (stale source, missing retrieval, numeric mismatch) are diagnosable by rules.  
**Decision:** Apply the E0–E5 cascade. Stop as soon as a decisive result is available. LLM (E4) is invoked for only 2–5% of traffic.  
**Rejected alternative:** Run an LLM judge on every response.  
**Consequence:** 70–80% token saving. Predictable latency. Reproducible audit trail. System becomes less LLM-dependent as rules accumulate.

---

### ADR-003 — Feedback is a claim, not ground truth

**Status:** Accepted  
**Context:** Users can be wrong, spammy, or biased. Feedback must be adjudicated before it influences the knowledge graph.  
**Decision:** Raw feedback creates a `FailureObservation`. It requires separate adjudication before becoming a confirmed `RootCause`. High-confidence corrections only (≥ 0.85) are auto-applied.  
**Rejected alternative:** Direct feedback → graph update.  
**Consequence:** Feedback poisoning is structurally prevented. Confidence gate provides a safety buffer.

---

### ADR-004 — Non-blocking feedback capture

**Status:** Accepted  
**Context:** Feedback confirmation must feel instant to the user. NLP pre-classification and database writes must not block the HTTP response.  
**Decision:** NER, sentiment, and intent classification run as `BackgroundTask`. HTTP response returns in < 100 ms. PostgreSQL write is async.  
**Rejected alternative:** Synchronous pre-classification before response.  
**Consequence:** User experience is unaffected. Classification runs in the background.

---

### ADR-005 — Failure-Attribution Graph is separate from the Context Graph

**Status:** Accepted  
**Context:** Merging operational failure data into the production graph risks contaminating answer retrieval with unverified diagnostic hypotheses.  
**Decision:** Two separate graph instances, sharing only canonical IDs (`source_id`, `scheme_id`, `taxonomy_node_id`). Different access policies, different retention.  
**Rejected alternative:** Single graph with labelled failure nodes.  
**Consequence:** Zero risk of feedback poisoning affecting user-facing answers. Clear separation of operational and serving concerns.

---

### ADR-006 — Shadow repair before production promotion

**Status:** Accepted  
**Context:** A repair that fixes one retrieval problem may introduce regressions in unrelated query cohorts.  
**Decision:** All repairs execute in a quarantined shadow environment. Regression + compliance + blast-radius tests must pass before atomic promotion.  
**Rejected alternative:** Direct production writes with rollback capability.  
**Consequence:** Blast-radius is bounded before the repair reaches users. Rollback is never needed in production because the decision was made in shadow.

---

### ADR-007 — Jurisdiction + role + product + channel → applicability, not country alone

**Status:** Accepted  
**Context:** The same sentence can have different regulatory significance depending on who says it, to whom, about which product, in which jurisdiction, in which channel.  
**Decision:** Applicability resolution uses a multidimensional key. `jurisdiction = US` alone is insufficient.  
**Rejected alternative:** Country-based policy selection.  
**Consequence:** Compliant behaviour across SEC/FINRA/SEBI/FCA/ESMA contexts from a single platform.

---

### ADR-008 — Batch LLM evaluation (25 items per call) with semantic deduplication

**Status:** Accepted  
**Context:** Individual LLM calls per feedback item cost ~2,100 tokens each. At production scale this is unaffordable.  
**Decision:** Group 25 feedback items per LLM call. Amortise system prompt and graph context across all 25. Apply semantic deduplication first (cosine ≥ 0.85) to reduce item count by ~40%.  
**Rejected alternative:** Per-item LLM evaluation.  
**Consequence:** 70–80% token reduction headline; up to 91% with all optimisations combined.

---

### ADR-009 — Repair Recipe Registry prevents agent improvisation

**Status:** Accepted  
**Context:** Allowing an agent to invent a repair action for each failure is unpredictable and hard to audit.  
**Decision:** Every known failure class has a versioned, tested, approved `RepairRecipe` (R001–R012). Agents are only invoked when no recipe matches (Level 3 semantic healing).  
**Rejected alternative:** Agent-generated repairs for all cases.  
**Consequence:** > 90% of repairs are deterministic and auditworthy. Novel failures enter a discovery queue and eventually become recipes.

---

### ADR-010 — Incident correlation prevents duplicate diagnosis cost

**Status:** Accepted  
**Context:** A single ingestion failure can produce hundreds of related `FailureObservation` records. Diagnosing each independently wastes tokens.  
**Decision:** The Failure-Attribution Graph correlates observations by source version, taxonomy node, model version, and time window. New observations matching an active incident skip diagnosis.  
**Rejected alternative:** Independent diagnosis per observation.  
**Consequence:** During systemic failures, diagnostic cost approaches zero for all observations after the first confirmed root cause.

---

## Glossary

| Term | Definition |
|---|---|
| **EvidencePack** | Immutable snapshot of retrieval results, graph paths, citations, and source versions at response time (D0–D3) |
| **D0** | Response Finalization — IDs, model version, latency, token counts, guardrail state |
| **D1** | Interaction Snapshot — query, intent, entities, system configuration at response time |
| **D2** | Evidence/Provenance Pack — all retrieved chunks, graph paths, source versions |
| **D3** | Applicability Context — jurisdiction, role, product, channel, policy pack version |
| **Adaptive Router** | Deterministic policy engine that selects the minimum sufficient evaluator for each interaction |
| **E0–E5** | Evaluation depth levels: E0=telemetry, E1=rules, E2=statistical, E3=semantic, E4=LLM, E5=agent/human |
| **F01–F14** | Failure families from Intent to Evaluation Integrity |
| **R0–R5** | Repair eligibility classes from No-Repair to Prohibited-Auto-Repair |
| **R001–R012** | Standard repair recipes for known failure patterns |
| **B0–B5** | Token budget bands: B0=0 tokens, B5=human-approved exception |
| **Failure-Attribution Graph** | Separate graph tracking failure observations, root causes, incidents, and repairs |
| **Context Graph** | Production Neo4j graph serving user-facing answers (must remain separate from failure graph) |
| **SourceManifest** | Registry record for a source document including version, hash, chunk count, embedding metadata |
| **RepairRecipe** | Versioned, approved procedure for a known failure class |
| **Shadow Environment** | Isolated copy of vector index and graph where repairs execute before production promotion |
| **HITL** | Human-in-the-Loop — user feedback mechanism |
| **NER** | Named Entity Recognition — lightweight entity extraction on feedback text |
| **TER** | Total Expense Ratio — a mutual fund cost metric |
| **NAV** | Net Asset Value — daily price of a mutual fund unit |
| **ISIN** | International Securities Identification Number — canonical fund identifier |
| **SID** | Scheme Information Document — SEBI-mandated fund disclosure document |
| **KIM** | Key Information Memorandum — SEBI-mandated summary disclosure |
| **Blast Radius** | Scope of unintended side-effects of a repair: single_chunk → document → entity → index |
| **Deterministic Conversion Rate** | % of novel recurring failures converted to rules or recipes over time |
| **Escalation Yield** | Material new findings per case escalated to a more expensive evaluator |
| **Claim** | An assertion in a response, modelled with entity, attribute, value, and temporal validity |
| **ControlSet** | The applicable set of compliance controls resolved from jurisdiction + role + product + channel |
| **PolicyPack** | Versioned, compliance-approved set of rules for a specific jurisdiction/role combination |

---

## Implementation Phase Map

| Phase | Scope | Status |
|---|---|---|
| **Phase 1** | Feedback capture, PostgreSQL buffer, batch LLM evaluation, Neo4j graph corrections, cache invalidation, APScheduler orchestration | Complete (7 Python modules) |
| **Phase 2** | Adaptive Evaluation Router, AMC Taxonomy Intelligence, Jurisdiction Rule Packs, Failure-Attribution Graph, cost-aware evaluation planning | Designed — pending implementation |
| **Phase 3** | RAG Health Engine, Repair Recipe Registry, shadow environment, regression gate, post-heal monitoring | Designed — pending implementation |

---

*All documents in this folder are part of a single coherent design. Cross-references between documents use the `LLD-NN` prefix.*
