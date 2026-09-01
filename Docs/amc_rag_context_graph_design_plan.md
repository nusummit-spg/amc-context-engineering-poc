# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC RAG + Context Graph System — Design Plan

**Scope:** Automated acquisition, taxonomy, and context-graph system for Indian AMC/mutual-fund regulatory and reference data, feeding a retrieval-augmented generation layer.

---

## 1. Guiding Principles

These fell out of the research and should shape every design decision below:

1. **Legal tier before technical design.** Every source gets classified (open / permission-gated / closed) before a single line of crawler code is written for it. See Section 3.
2. **Aggregation points over per-entity crawlers.** AMFI functions as a SEBI-mandated central repository for most scheme-level documents — build one well-behaved AMFI integration instead of 40+ AMC-specific scrapers.
3. **Classify by substance, not by label.** Following Morningstar's approach: derive scheme category from actual portfolio holdings, not the self-declared objective in a SID.
4. **Temporal validity is a first-class property, not metadata.** Every regulatory node (circular, Act section, tax provision) carries effective_from / superseded_by — this is the single most important design decision given how much of the source material (SEBI Master Circular, Income-tax Act 2025, direct/regular disclosure rules) is mid-transition right now.
5. **Provenance travels with every chunk.** Source URL, acquisition method, license basis, retrieval date — needed both for citation quality and for defending the system's data lineage if ever questioned by SEBI (Reg 16C liability) or under DPDP.
6. **Human-in-the-loop before anything compliance- or investor-facing.** The AMC bears sole liability for AI/ML tool output under SEBI Regulation 16C — nothing in this system auto-publishes without review.
7. **The taxonomy is the product, not the raw data.** Reference organizations (CRISIL, ICRA, Morningstar) all license the classification/structuring layer built on top of public data, not the raw data itself — that's the durable asset here too.

---

## 2. System Architecture — Layered Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  ACQUISITION LAYER                                               │
│  RSS pollers · scheduled downloaders · assisted-capture tool ·   │
│  licensed-vendor feed connectors                                 │
└───────────────────────────┬───────────────────────────────────--┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  INGESTION & INTEGRITY LAYER                                     │
│  Hash-based change detection · dedup · OCR (scanned PDFs) ·      │
│  raw document store with versioning                              │
└───────────────────────────┬───────────────────────────────────--┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  METADATA & TAXONOMY LAYER                                       │
│  FIBO-anchored entity/instrument tags · SKOS taxonomy ·          │
│  temporal validity fields · SEBI-format-derived schema fields    │
└───────────────────────────┬───────────────────────────────────--┘
                             ▼
┌──────────────────────────┬──────────────────────────────────────┐
│  KNOWLEDGE GRAPH LAYER    │  CHUNKING & EMBEDDING LAYER           │
│  supersedes/amends edges  │  clause-level chunking ·              │
│  applies-to edges ·       │  vector embeddings ·                  │
│  cross-reference edges    │  provenance-tagged chunks              │
└──────────────┬────────────┴───────────────┬──────────────────────┘
               └───────────────┬─────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  CONTEXT ENGINEERING / RETRIEVAL LAYER                            │
│  taxonomy filter → graph traversal → vector search (hybrid) ·     │
│  citation grounding · temporal "currently in force" default       │
└───────────────────────────┬───────────────────────────────────--┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  GOVERNANCE, SECURITY & AUDIT LAYER (spans all layers above)      │
│  RBAC · encryption at rest/in transit · query/response audit log ·│
│  human-review gate before compliance-facing output                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Legal Tiering — Source Registry

| Category | Source | Access Method | Legal Tier | Notes |
|---|---|---|---|---|
| Regulatory | SEBI RSS feed | Official syndication feed | **Tier 1 — Open** | Covers new circulars/orders/press releases only, not archive |
| Regulatory | SEBI Master Circular (Mutual Funds) | Scheduled PDF download | **Tier 2 — Permission-gated** | Single consolidated source; still subject to SEBI's reproduction-permission policy |
| Regulatory | SEBI standalone circulars (archive) | Scheduled crawl / assisted capture | **Tier 2** | Use mainly for amendment-history trail beneath the Master Circular |
| Regulatory | AMFI (NAV, AUM/flow reports, SID/SAI/KIM, portfolio disclosures, factsheets) | Direct file/API pull | **Tier 1 — Open** | SEBI-mandated public/free publication; single aggregation point |
| Regulatory | RBI DBIE, MPC press releases | Direct download / API | **Tier 1 — Open** | Explicit "reuse with courtesy" framing from RBI |
| Regulatory | MOSPI (CPI/GDP) | Direct download | **Tier 1 — Open** | Primary source for macro context data |
| Regulatory | Official Gazette (Acts, Rules) | Direct download | **Tier 1 — Open** | Public domain once gazetted |
| Regulatory | Income Tax Dept (incometaxindia.gov.in) | Direct download | **Tier 1 — Open** | Golden source for both 1961 and 2025 Acts, FAQs, CBDT circulars |
| Transactional/Operational | BSE StAR MF API structure doc, NSE/BSE settlement docs | Direct download | **Tier 1 — Open (docs only)** | Mechanics/process documentation only |
| Transactional/Operational | CAMS/KFintech investor transaction data (CAS) | N/A | **Tier 3 — Closed** | Personal financial data, consent-gated — not part of this system's acquisition surface |
| Scheme reference | Benchmark index methodology (NSE Indices/BISPL) | Direct download | **Tier 1 — Open (methodology only)** | Index values/history are licensed IP — Tier 3 |
| Distribution/Compliance | SEBI/AMFI KYC framework regulations | Direct download | **Tier 1 — Open (framework only)** | CKYC/KRA records themselves are Tier 3 — closed |
| Distribution/Compliance | AMFI Master Circular for MFDs (commission/TER disclosure) | Direct download | **Tier 1 — Open** | Published directly by AMFI |
| Market data | NSE/BSE prices, tick data, index values | Licensed vendor feed | **Tier 3 — Closed** | Requires a real commercial exchange-data license — procurement item, not a crawler target |

**Build implication:** roughly 80% of what this system needs (everything scheme/regulation/taxation/macro-related) is Tier 1. The remaining 20% (live market/index data, any investor-level data) needs either a formal SEBI permission/CFRT engagement or a licensed vendor — budget and plan those as separate procurement tracks, not crawler engineering tasks.

---

## 4. Governance Requirements (precede build)

- **Designate an accountable senior owner** for the AI/ML system per SEBI's Regulation 16C framing — the AMC is solely liable for the tool's data-privacy, security, and output-accuracy, whether built in-house or bought.
- **Testing & validation framework** — documented before production use, anticipating SEBI's pending consultation-paper requirements (tiered oversight, senior technical review).
- **DPIA** if any pipeline ever touches investor-personal data (it currently shouldn't, per the Tier 3 exclusions above) — re-run this assessment if that scope ever changes.
- **Written permission request to SEBI** for circular reproduction, filed early — this is a real lead-time item, not a formality.

---

## 5. Component Design

### 5.1 Acquisition Layer
- RSS poller for SEBI (new-circular detection).
- Scheduled downloaders for AMFI (NAV daily, factsheets/portfolio disclosures monthly, AUM/flow report monthly, SID/SAI/KIM on-change).
- RBI DBIE / MOSPI scheduled pulls (macro context).
- "Assisted capture" tool (browser extension) for compliance-team-initiated downloads of Tier 2 material, pending formal permission.
- Connector slot reserved for a licensed vendor feed (index/market data) — pluggable, not built in-house.

### 5.2 Ingestion & Integrity Layer
- SHA-256 hash every downloaded document; diff on re-crawl to catch silent SEBI-side edits.
- OCR pass (with confidence scoring) for scanned/older PDFs — flag low-confidence extractions for human review rather than silently ingesting.
- Raw document store retains every version, never overwrites.

### 5.3 Metadata & Taxonomy Layer
- Schema fields bootstrapped from SEBI's own "Formats for Master Circular for Mutual Funds" document (already regulator-defined field structures).
- Entity/instrument concepts mapped to FIBO where they overlap; extended with India/SEBI-specific concepts where FIBO has no local coverage.
- Taxonomy expressed in SKOS (broader/narrower/related terms) for portability and tooling.
- Construction audited against ISO 25964 / ANSI-NISO Z39.19 rules: unique concept labels, defined relationship types, scope notes.
- Every node carries `effective_from`, `superseded_date`, `status` (active/superseded/withdrawn).

### 5.4 Knowledge Graph Layer
- Edge types modeled on LegalRuleML/Akoma Ntoso concepts: `supersedes`, `amends`, `applies_to (entity_type)`, `cross_references (Act/Regulation)`.
- Scheme-level nodes link to: benchmark index (methodology, not value), classification taxonomy node, fund manager, AMC.
- Tax provisions modeled with explicit dual effective-date boundaries (July 23, 2024 indexation change; April 1, 2026 Act replacement) as independent nodes, not a merged "recent changes" bucket.

### 5.5 Chunking & Embedding Layer
- Clause/paragraph-level chunking for regulatory and tax text — fixed-size token windows are the wrong tool here; meaning lives at clause boundaries.
- Every chunk retains a provenance block: source URL, document version hash, acquisition date, license basis.

### 5.6 Context Engineering / Retrieval Layer
- Hybrid retrieval: **taxonomy tag filter → graph traversal (relationships, supersession) → vector search (semantic nuance within the filtered set)** — not pure vector RAG, per the pattern both academic systems (ComplianceNLP, RAGulating Compliance) converge on.
- Default retrieval scope: "currently in force" unless a query explicitly asks for history.
- Every generated answer grounded with a citation back to source paragraph.

### 5.7 Governance, Security & Audit Layer
- RBAC on the graph/vector store; encryption at rest and in transit.
- Full query/response audit log.
- Crawler etiquette: robots.txt respected, rate-limited, honest user-agent.
- Primary-domain-only ingestion to limit prompt-injection surface from untrusted third-party content.
- Human review gate on anything that feeds a filing, investor communication, or compliance decision.

---

## 6. Taxonomy Quality Benchmarking

| Measure | Method |
|---|---|
| Semantic alignment | % of taxonomy nodes mapped to FIBO concepts |
| Construction quality | Audit against ISO 25964 / Z39.19 checklist |
| Retrieval quality | Precision/recall against a compliance-officer-verified gold Q&A set |
| Interoperability | Taxonomy expressed in SKOS/OWL, not a proprietary schema |
| Maturity (optional, formal) | EDMC DCAM score |

---

## 7. Phased Roadmap

1. **Phase 1 — Tier 1 foundation.** AMFI (NAV, factsheets, portfolio disclosures, SID/SAI/KIM), SEBI RSS, RBI DBIE, MOSPI, Income Tax Dept. Build taxonomy skeleton (FIBO-mapped, SKOS-expressed) against this data alone.
2. **Phase 2 — Regulatory depth.** Formal SEBI reproduction-permission request; ingest Master Circular + amendment trail; build the supersession graph.
3. **Phase 3 — Knowledge graph maturity.** Full edge modeling (applies-to, cross-references, tax effective-date boundaries); temporal-validity-default retrieval.
4. **Phase 4 — Context engineering layer.** Hybrid retrieval, citation grounding, human-review gate; pilot with compliance/legal team internally.
5. **Phase 5 — Licensed data integration.** NSE/BSE index/market data via a commercial vendor connector, only if scheme-performance-explainability requirements actually need it.

---

## 8. Reference Models

- **CRISIL Mutual Fund Ranking** — methodology combining NAV + portfolio attributes; licensing model (build once, license to multiple institutional clients) worth mirroring for any future external-facing product.
- **ICRA Analytics** — sourcing pattern worth studying: public filings + direct AMC relationship channel, not scraping alone.
- **Morningstar** — the taxonomy design reference: holdings-based (not self-declared) classification, hierarchical exhaustive/mutually-exclusive structure, published methodology with a regular review cycle.
- **ComplianceNLP / RAGulating Compliance (academic)** — architectural precedent for the graph-augmented RAG pattern used in Section 5.6.

---

## 9. Open Decisions

- Timing and scope of the formal SEBI CFRT / reproduction-permission engagement.
- Whether Phase 5 (licensed market/index data) is in scope now or deferred until a concrete performance-explainability use case exists.
- Internal vs. external audience for the system's outputs — this determines how strict the human-review gate needs to be under SEBI Reg 16C.
