# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC Context Engineering — Master Implementation Plan

**Prepared**: 2026-08-06 | **Scope**: Fixing identified issues + Production Pipeline + Data Acquisition

---

## Executive Summary

This plan consolidates four documents into a single phased roadmap:

| Document | Core Issue Addressed |
|---|---|
| `Cache_Token_Optimization_Zero_Token_Warm_Hit_Architecture.md` | Fix ghost token accounting in cache hits |
| `AMC_website_crawl_info.md` + `amc_rag_context_graph_design_plan.md` | Legal data acquisition strategy, taxonomy anchoring |
| `production_data_pipeline_plan.md` | Automate document ingest, provenance ledger, regulatory graph edges |
| Test Evaluation Findings | Fix NER cold-start (157s), investigate multi-turn metric, cover graph node gaps |

**Total new/modified files: 12** | **Estimated build time: 16–20 working days**

---

## Critical Issues to Fix First (Pre-Pipeline)

### Issue 1 — NER Cold-Start Latency (157,101 ms → target: <500 ms)

**Root cause** (confirmed from `01_query_execution_audit.jsonl`):
- `_get_gliner()` in [`ner_pipeline.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L150-L172) is a lazy singleton — GLiNER model loads on first call in the hot request path
- First request: 157 seconds. Second: 29 seconds. Fully cached: 0.02 ms
- spaCy `_get_nlp()` has the same lazy-load pattern (line 33-48)

**Root cause diagram**:
```
Request arrives → NER needed → _get_gliner() → model is None → 
GLiNER.from_pretrained() [157,000ms download/load] → NER runs → response
```

**Fix** — Pre-warm NER model at application startup (before any request is served):

```python
# In ner_pipeline.py — add warmup function
def warmup_ner_models() -> None:
    """
    Pre-load spaCy + GLiNER models at startup.
    Call this once from app.py/taxonomy_retrieval.py startup hook.
    Eliminates 157-second cold-start spike on first user request.
    """
    print("  [NER Warmup] Pre-loading spaCy EntityRuler...", flush=True)
    _get_nlp()   # Force load spaCy + EntityRuler + gazetteer patterns
    print("  [NER Warmup] Pre-loading GLiNER model...", flush=True)
    _get_gliner()  # Force download/load GLiNER model
    print("  [NER Warmup] Done — both models cached in memory.", flush=True)

# In app.py — call at Streamlit init (once per process)
# Use st.cache_resource to ensure single execution
@st.cache_resource
def _startup_warmup():
    import ner_pipeline
    ner_pipeline.warmup_ner_models()
    return True
_startup_warmup()
```

**Pros**: Zero change to request path logic. Eliminates UX-destroying first-request spike entirely. Works with existing ONNX fallback path.

**Cons**: App startup is slower by ~15–30 seconds (model load time). Acceptable trade-off vs. 157-second live latency. Not an issue in production (startup happens once).

**Files changed**: [`ner_pipeline.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py) (add `warmup_ner_models()`), [`app.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/app.py) (add `@st.cache_resource` startup hook)

---

### Issue 2 — Ghost Token Accounting on Cache Hits (from Cache doc)

**Root cause** (exact lines in [`taxonomy_retrieval.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L395-L397)):
```python
# Lines 395-397 — CURRENT (broken):
"tokens_input":  cached.total_tokens,   # Reports COLD run tokens — wrong
"tokens_output": 0,
"tokens_total":  cached.total_tokens,   # Same as cold — shows zero savings
```

**Fix — 3-stage implementation** (matches Cache doc phases 1+2+4):

**Stage A: Honest token reporting** (30 min, highest immediate impact):
```python
# In taxonomy_retrieval.py — cache hit block (lines 385-409):
CACHE_PROBE_TOKENS = 12    # Real work: embedding lookup + cosine similarity
"tokens_input":  CACHE_PROBE_TOKENS,
"tokens_output": 0,
"tokens_total":  CACHE_PROBE_TOKENS,
"tokens_cold_equivalent": cached.total_tokens,  # New: what it WOULD have cost
"tokens_saved": cached.total_tokens - CACHE_PROBE_TOKENS,  # New: net savings
```

**Stage B: Pre-cache fingerprint gate** (eliminates embedding cost on exact repeats):
```python
# In intent_cache.py — IntentAwareCache class:
self._fingerprint_index: Dict[str, str] = {}  # md5 → cache_key

def fingerprint_probe(self, query: str) -> Optional[CacheEntry]:
    fp = hashlib.md5(query.lower().strip().encode()).hexdigest()
    cache_key = self._fingerprint_index.get(fp)
    return self._get_by_key(cache_key) if cache_key else None
```

**Stage C: Token Ledger + UI display** (demo-ready savings panel):
- Adds `TokenLedger` dataclass with `cold_*` and `warm_*` fields split out
- Updates [`chat_view.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/chat_view.py) to show savings panel in telemetry expander
- Adds `SavingsLedger` to [`intent_cache.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/intent_cache.py) for cumulative tracking

**Pros of fix**: Makes the value proposition honest and demonstrable. 98.8% token reduction becomes the correct headline. Also enables CO₂ / cost tracking as a sustainability angle.

**Cons**: Stage C requires UI work and adds complexity to `CacheEntry` dataclass. Old disk-persisted JSON cache files will have no `input_tokens_cold` field — needs backward-compatible deserialization with `item.get("input_tokens_cold", item["total_tokens"])`.

**Files changed**: [`taxonomy_retrieval.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py) (lines 395-409), [`intent_cache.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/intent_cache.py) (CacheEntry dataclass + fingerprint index), [`chat_view.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/chat_view.py) (token savings panel)

---

### Issue 3 — Graph Node Coverage Gap (Large Cap / Small Cap — Taxonomy Turn 2)

**Root cause**: The hybrid system said it "lacked data" for Large Cap and Small Cap fund specs in `03_taxonomy_showcase_results.json` Turn 2, while Traditional RAG answered correctly. The graph nodes for these categories either have no entity coverage or graph traversal didn't reach them.

**Fix**:
1. Audit Neo4j for `Entity.label = "SCHEME_NAME"` nodes matching "Large Cap Fund", "Small Cap Fund" — run `MATCH (e:Entity) WHERE e.text CONTAINS "Large Cap" RETURN e`
2. If missing: add them to the gazetteer in [`ner_pipeline.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py#L60-L73) `_COMMON_DOMAIN_ENTITIES` list
3. Trigger incremental re-index of the SEBI categorization document

---

## Production Pipeline Implementation

> [!IMPORTANT]
> **Zero changes to any retrieval or LLM reasoning logic.** `build_index.py`, `graph_store.py`, `faiss_store.py`, and `taxonomy_retrieval.py` are downstream consumers — the pipeline layers only touch data acquisition, provenance, and graph schema extension.

---

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1: DATA ACQUISITION (3 channels)                              │
│  sebi_feed_ingester.py  │  amfi_portal_adapter.py  │  admin_view.py │
│  (SEBI RSS + PDF dl)    │  (NAV, SID/SAI, factshts)│  (Manual tab)  │
└────────────────────────────────┬────────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 2: INGESTION GATEWAY                                          │
│  ingestion_gateway.py + provenance_ledger.py                         │
│  SHA-256 dedup · provenance JSON · status tagging · file routing     │
└────────────────────────────────┬────────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: EXISTING PIPELINE (ZERO CHANGES)                           │
│  build_index.py → document_extractors → pii_scrub → chunking →      │
│  NER → graph_store.upsert_entities → FAISS embed                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 4: REGULATORY GRAPH ENRICHMENT                               │
│  regulatory_lifecycle_enricher.py                                    │
│  [:SUPERSEDES] [:AMENDED_BY] [:APPLIES_TO] [:EFFECTIVE_FROM] edges  │
└────────────────────────────────┬────────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 5: ACTIVE-STATUS FILTER + STALENESS MONITOR                  │
│  taxonomy_retrieval.py (status filter) + staleness_monitor.py       │
│  Default: status="active" documents only in retrieval               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## New Files to Build

### `sebi_feed_ingester.py` — Layer 1A

**What it does**: Polls SEBI's official RSS feed (designed for automated syndication — zero legal ambiguity). Downloads new circular PDFs, hashes them, and hands off to `ingestion_gateway.py`.

**Key functions**:
```python
def poll_sebi_rss(feed_url: str) -> List[FeedEntry]
def download_circular_pdf(url: str, dest_dir: Path) -> DownloadResult
def detect_supersession(title: str, existing_titles: List[str]) -> Optional[str]
def run_daily_sebi_poll() -> IngestionReport
```

**Data model**:
```python
@dataclass
class FeedEntry:
    circular_id: str        # e.g. "SEBI/HO/IMD/2025/0123"
    title: str
    source_url: str
    published_date: datetime
    department: str         # IMD | MRD | MIRSD | HO | CFD
    entity_type: str        # AMC | Broker | RA | All
    doc_type: str           # circular | master_circular | faq | order
    pdf_url: str
    supersedes_title: str   # Detected from title pattern — may be None
```

**Amendment Detection Patterns**:
```python
SUPERSESSION_PATTERNS = [
    (r"Amendment to (?:SEBI )?Circular (?:dated|on) (.+?) dated", "AMENDED_BY"),
    (r"Addendum to (?:SEBI )?Circular(?: on)?(.+)", "AMENDED_BY"),
    (r"Extension of timeline for implementation of(.*?)dated", "EXTENDS"),
    (r"Deferment of timeline for(.*?)dated", "DEFERS"),
    (r"Clarification(?: on| regarding)(.*?)Circular", "CLARIFIES"),
]
```

**Pros**: Legally cleanest channel (SEBI explicitly designed RSS for automated syndication). No ToU friction. Perfectly defensible under SEBI Reg 16C. Automated once running.

**Cons**: RSS feed covers **new circulars only** — does not backfill the historical archive (pre-feed circulars). Rate-limit carefully: max 1 request/5 minutes to avoid IP blocks. SEBI website structure has changed before — feed URL needs monitoring.

---

### `amfi_portal_adapter.py` — Layer 1B

**What it does**: Ingests from AMFI's public channels — confirmed Tier 1 (open for reuse with no legal ambiguity).

**Data sourced**:
- **NAV data**: `portal.amfiindia.com/spages/NAVAll.txt` — daily, all schemes, public utility
- **NAV history**: `api.mfapi.in/mf/{scheme_code}` — community wrapper, permissive
- **AMFI circulars**: `amfiindia.com` circular listing page
- **Monthly AUM/flow report**: PDF, published within first 8–10 working days each month
- **SID/SAI/KIM**: SEBI mandates dual-publication on AMFI's portal — one integration covers all 40+ AMCs

```python
def fetch_nav_all() -> pd.DataFrame
def fetch_scheme_history(scheme_code: str) -> pd.DataFrame
def fetch_amfi_monthly_aum_report() -> DownloadResult
def fetch_sid_sai_listing() -> List[dict]
```

**Pros**: No copyright friction for NAV/portfolio data (SEBI mandates public/free publication). AMFI as centralized aggregation point = single integration covers entire industry. `mfapi.in` is effectively a public utility with a clear community intent.

**Cons**: HTML structure of AMFI's listing pages can change — needs drift monitoring. `mfapi.in` is third-party infrastructure (community-maintained), not official — should be treated as a convenient but non-guaranteed channel. SID/SAI PDFs can be large and numerous.

---

### `ingestion_gateway.py` — Layer 2

**What it does**: Single entry point for ALL acquisition channels. Ensures every document has SHA-256 hash, provenance metadata, and proper status before entering `build_index.py`.

```python
@dataclass
class IngestRequest:
    filepath: Path
    acquisition_channel: str  # "sebi_rss" | "amfi_portal" | "admin_authorized_upload"
    source_url: str
    doc_type: str             # circular | master_circular | faq | nav_data
    department: str           # IMD | MRD | MIRSD | HO | CFD
    entity_type: str          # AMC | Broker | All
    status: str               # "active" — default on ingest
    authorized_by: str        # RBAC username
    supersedes: Optional[str] # Filename of circular being superseded

def process_ingest(req: IngestRequest) -> IngestResult:
    # 1. SHA-256 hash
    # 2. Dedup check vs provenance_ledger
    # 3. Write provenance record
    # 4. Route file to data/AMC/{category}/
    # 5. Update superseded document status if applicable
```

**Pros**: All acquisition channels funnel through one validation point. Reg 16C compliance artifact is generated automatically. Dedup prevents re-indexing same document twice.

**Cons**: Adds a processing step between download and indexing. File I/O for hashing large PDFs is negligible (<50ms for typical circular PDF) but should be async for bulk historical backfill.

---

### `provenance_ledger.py` — Layer 2

**What it does**: Persistent JSON store. Every document in the system has a ledger record answering "where did this come from, under what right, and is it still current?"

**Schema per record**:
```json
{
  "provenance_id": "uuid-v4",
  "filename": "Categorization and Rationalization of Mutual Fund Schemes.pdf",
  "sha256_hash": "a3f7c2...",
  "acquisition_channel": "sebi_rss",
  "source_url": "https://sebi.gov.in/legal/circulars/...",
  "doc_type": "circular",
  "department": "IMD",
  "entity_type": "AMC",
  "status": "active",
  "supersedes": null,
  "superseded_by": null,
  "ingest_timestamp": "2026-08-05T13:00:00+05:30",
  "authorized_by": "sebi_rss_daemon",
  "drift_detected": false
}
```

**Key functions**:
```python
def get_ledger() -> Dict[str, ProvenanceRecord]
def find_by_hash(sha256: str) -> Optional[ProvenanceRecord]
def update_status(filename: str, new_status: str, superseded_by: str = None)
def generate_compliance_report() -> str  # Reg 16C audit export
def backfill_existing_documents() -> None  # One-time migration for existing data/AMC/
```

**Pros**: Directly answers SEBI Reg 16C "data lineage" questions. Enables status-filtered retrieval (active-only default). Foundation for staleness drift detection. One-time backfill function handles existing indexed documents.

**Cons**: JSON file will grow large with thousands of documents — at 163+ existing circulars it's fine, but at 10,000+ documents should migrate to SQLite for indexed lookups. Plan for migration early.

> [!WARNING]
> **Backward Compatibility**: The 163 existing circulars in `data/AMC/SEBI_Circulars/` have no provenance records. The `backfill_existing_documents()` function must run once to create records for all existing files (assigning `acquisition_channel: "manual_public_download"`, `status: "active"`, `authorized_by: "system_backfill"`). Without this, the active-status filter in Layer 5 would exclude all existing documents.

---

### `regulatory_lifecycle_enricher.py` — Layer 4

**What it does**: After `build_index.py` indexes a document, writes regulatory relationship edges to Neo4j. This is the key differentiator that lets the system say "this circular was superseded" instead of confidently citing dead law.

**New Neo4j schema** (extends `graph_store.init_schema()`):
```cypher
CREATE CONSTRAINT regulatory_doc_key IF NOT EXISTS
  FOR (d:RegulatoryDocument) REQUIRE d.filename IS UNIQUE;

CREATE INDEX reg_doc_status IF NOT EXISTS
  FOR (d:RegulatoryDocument) ON (d.status);

-- New relationship types:
(:RegulatoryDocument)-[:SUPERSEDES]->(:RegulatoryDocument)
(:RegulatoryDocument)-[:AMENDED_BY]->(:RegulatoryDocument)
(:RegulatoryDocument)-[:APPLIES_TO]->(:EntityType {name: "AMC"})
(:RegulatoryDocument {status, effective_from, superseded_date, department})
```

**Key functions**:
```python
def upsert_regulatory_document(provenance_record: ProvenanceRecord)
def link_supersession_chain(filename: str, supersedes_filename: str)
def link_entity_type_applicability(filename: str, entity_types: List[str])
def detect_and_link_amendments_from_titles(records: List[ProvenanceRecord])
```

**Pros**: The single most valuable graph enhancement — enables temporal validity queries that vector RAG fundamentally cannot do. Directly addresses the test evaluation finding of missing regulatory lifecycle edges. Best-effort regex covers ~70-80% of supersession cases automatically. The remaining 20-30% covered by admin confirmation flow.

**Cons**: Regex-based amendment detection will have false positives ("Extension of timeline" circulars are about deadlines, not content supersession). Recommend: auto-create with `confidence: "medium"`, admin promotes to `confirmed` or rejects. Adds Neo4j schema migration — needs to be run once on existing database.

---

### `staleness_monitor.py` — Layer 5B

**What it does**: Periodically re-checks SHA-256 hash of known documents against source URLs. Detects silent SEBI edits (this does happen) and URL 404s (circular moved/deleted).

```python
def run_drift_check(provenance_ledger: Dict, sample_size: int = 20) -> DriftReport
def generate_staleness_alert(drifted_docs: List[str]) -> str
```

**Strategy**: Sample 20 docs per run (not all — avoids hammering government servers). Trigger from Admin Panel "Staleness Check" button + end of each daily RSS poll cycle.

**Pros**: Catches the "silently edited circular" failure mode that the `AMC_website_crawl_info.md` flagged as the highest-stakes silent failure. Rate-limited by design.

**Cons**: HEAD requests to SEBI's servers may not always return reliable `Last-Modified` headers (government sites are inconsistent). Must handle graceful fallback to full-download-and-hash when HEAD request is insufficient.

---

### `pipeline_scheduler.py` — Orchestrator

**What it does**: Ties all 5 layers into a single callable pipeline. Triggered from Admin Panel or Python scheduler.

```python
def run_production_pipeline(mode: str = "incremental"):
    # Step 1: Acquire → sebi_feed_ingester + amfi_portal_adapter
    # Step 2: Ingest gateway → process_ingest() for each new doc
    # Step 3: Index → build_index.build(rebuild=False) [UNCHANGED]
    # Step 4: Enrich → regulatory_lifecycle_enricher
    # Step 5: Drift check → staleness_monitor (sample 10)
    # Step 6: Log → pipeline_run_log.jsonl
```

---

## Files to Modify (Minimal Changes Only)

| File | What Changes | Lines Added | Risk |
|---|---|---|---|
| [`ner_pipeline.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py) | Add `warmup_ner_models()` | ~10 | Negligible |
| [`app.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/app.py) | `@st.cache_resource` startup warmup | ~5 | Low |
| [`taxonomy_retrieval.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py) | Fix ghost token lines 395-397 + active-status filter | ~30 | Low |
| [`intent_cache.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/intent_cache.py) | Add fingerprint index + `input_tokens_cold` field | ~25 | Low (backward compat needed) |
| [`chat_view.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/chat_view.py) | Token savings panel in telemetry expander | ~40 | Low |
| [`graph_store.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/graph_store.py) | Add `init_regulatory_schema()` for new node/edge types | ~30 | Low |
| [`admin_view.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/admin_view.py) | Add "Authorized Ingest" tab + pipeline trigger button | ~70 | Medium |
| [`build_index.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/build_index.py) | Write `processed_ledger_meta.json` | ~10 | Negligible |
| [`config.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/config.py) | Add `RETRIEVAL_ACTIVE_ONLY`, `SEBI_RSS_URL`, `AMFI_NAV_URL` flags | ~10 | Negligible |

> [!IMPORTANT]
> **Zero changes to any reasoning, retrieval, or LLM logic.** The existing hybrid GraphRAG, context budgeting, and answer generation paths are not touched.

---

## Data Acquisition Strategy (Mapped to Codebase)

### Legal Tiering (from AMC crawl doc + design plan)

| Data Category | Source | Legal Tier | Acquisition Method | Maps to Module |
|---|---|---|---|---|
| New SEBI circulars | SEBI RSS feed | ✅ Open (designed for bots) | `sebi_feed_ingester.py` | Layer 1A |
| Master Circular | SEBI website | ⚠️ Permission-gated | Assisted capture / admin upload | Admin tab |
| Historical circulars | SEBI archive | ⚠️ Permission-gated | Assisted capture (human-authorized) | Admin tab |
| NAV data (all schemes) | `portal.amfiindia.com/NAVAll.txt` | ✅ Open | `amfi_portal_adapter.py` | Layer 1B |
| SID/SAI/KIM | `portal.amfiindia.com` (SEBI-mandated) | ✅ Open | `amfi_portal_adapter.py` | Layer 1B |
| Portfolio disclosures | AMFI (standardized monthly) | ✅ Open | `amfi_portal_adapter.py` | Layer 1B |
| Monthly AUM/flow report | `amfiindia.com` | ✅ Open | `amfi_portal_adapter.py` | Layer 1B |
| AMFI MFD Master Circular | `amfiindia.com` | ✅ Open | `amfi_portal_adapter.py` | Layer 1B |
| RBI macro data | `dbie.rbi.org.in` (explicit reuse invitation) | ✅ Open | Scheduled download | Future |
| Gazette Acts/Rules | `egazette.gov.in` | ✅ Open (public domain) | Scheduled download | Future |
| Income Tax Act 2025 | `incometaxindia.gov.in` | ✅ Open | Scheduled download | Future |
| BSE StAR MF API docs | `bsestarmf.in/APIFileStructure.pdf` | ✅ Open (docs only) | One-time download | Future |
| NSE/BSE market prices | NSE/BSE direct | ❌ Closed (licensed IP) | Commercial vendor contract | Out of scope |
| Benchmark index values | NSE Indices / BISPL | ❌ Closed (licensed IP) | Commercial vendor contract | Out of scope |
| Investor CAS data | CAMS/KFintech | ❌ Closed (personal data) | Not in scope — DPDP boundary | Never |

> [!CAUTION]
> **SEBI reproduction permission**: SEBI's copyright policy requires written permission for reproducing circular content. File this request early (2–4 week lead time). Until received, all SEBI circular ingestion should be via the RSS feed (new circulars only) or the Assisted Capture / admin upload path (human-authorized download, not bulk automated scraping). The licensed redistributor route (Taxmann/Lexplosion/Ricago, ~₹1–5L/yr) bypasses this entirely and should be evaluated for enterprise scale.

### Taxonomy Anchoring (from design plan)

The taxonomy should be anchored to:
- **FIBO** (Financial Industry Business Ontology) for entity/instrument concepts
- **SKOS** for the taxonomy hierarchy itself (broader/narrower/related)
- **ISO 25964 / ANSI-NISO Z39.19** for construction quality audit
- **LegalRuleML / Akoma Ntoso** for regulatory edge types (`supersedes`, `amends`, `applies_to`)

This is a longer-term enrichment task (design plan Phase 2–3). For now, the `regulatory_lifecycle_enricher.py` provides the foundation graph schema that FIBO/SKOS mapping will build on top of.

---

## Phased Implementation Roadmap

### Phase 0: Bug Fixes (Days 1–3) — HIGHEST PRIORITY

| Day | Task | File(s) | Effort |
|---|---|---|---|
| **Day 1** | Add `warmup_ner_models()` + `@st.cache_resource` startup hook | `ner_pipeline.py`, `app.py` | Low |
| **Day 1** | Fix ghost token accounting (lines 395-397) | `taxonomy_retrieval.py` | 30 min |
| **Day 2** | Add fingerprint gate to `IntentAwareCache` | `intent_cache.py` | 2h |
| **Day 2** | Update `CacheEntry` with `input_tokens_cold` (backward compat) | `intent_cache.py` | 1h |
| **Day 3** | Add token savings panel to `chat_view.py` telemetry | `chat_view.py` | 3h |
| **Day 3** | Audit + fix Large Cap / Small Cap graph node coverage | `ner_pipeline.py` + Neo4j | 2h |

### Phase 1: Production Pipeline Core (Days 4–10)

| Day | Task | File(s) | Effort |
|---|---|---|---|
| **Day 4** | `provenance_ledger.py` — data model + read/write + compliance report | NEW | Medium |
| **Day 4** | `backfill_existing_documents()` — one-time migration for existing files | in ledger.py | Medium |
| **Day 5** | `ingestion_gateway.py` — hash dedup + provenance write + file routing | NEW | Medium |
| **Day 6** | `sebi_feed_ingester.py` — RSS polling + PDF download + supersession detection | NEW | High |
| **Day 7** | `amfi_portal_adapter.py` — NAV fetch + SID/SAI listing + hash check | NEW | Medium |
| **Day 8** | `admin_view.py` — "Authorized Ingest" tab + pipeline trigger | MODIFY | Medium |
| **Day 9** | `config.py` + `build_index.py` — new flags + ledger_meta.json | MODIFY | Low |
| **Day 10** | `pipeline_scheduler.py` — orchestrator + logging | NEW | Medium |

### Phase 2: Graph Lifecycle Enrichment (Days 11–13)

| Day | Task | File(s) | Effort |
|---|---|---|---|
| **Day 11** | `graph_store.py` — `init_regulatory_schema()` — new node/edge types | MODIFY | Medium |
| **Day 11** | `regulatory_lifecycle_enricher.py` — MERGE nodes + supersession chains | NEW | High |
| **Day 12** | `staleness_monitor.py` — SHA-256 drift detection | NEW | Medium |
| **Day 12** | `taxonomy_retrieval.py` — active-status filter + `_active_sources` set | MODIFY | Low |
| **Day 13** | Integration test: RSS poll → ingest gateway → index → lifecycle edges → retrieval | - | High |

### Phase 3: Analytics & Compliance (Days 14–16)

| Day | Task | File(s) | Effort |
|---|---|---|---|
| **Day 14** | Cumulative savings ledger in `intent_cache.py` (`SavingsLedger` class) | MODIFY | Medium |
| **Day 14** | `analytics_view.py` — Token Economy Dashboard widget | MODIFY | Medium |
| **Day 15** | Provenance compliance report generation + admin panel polish | `admin_view.py`, `provenance_ledger.py` | Medium |
| **Day 16** | Buffer: supersession detection tuning, edge case handling, documentation | - | Buffer |

---

## Pros & Cons Summary

### Pros of This Full Plan
| Dimension | Benefit |
|---|---|
| **NER fix** | Eliminates 157-second UX-destroying cold-start. App feels production-ready immediately. |
| **Token fix** | Makes the 98.8% token savings claim honest and demonstrable — key for commercial positioning. |
| **Data acquisition** | Tier 1 sources (SEBI RSS + AMFI) cover 80% of needed data with zero legal exposure. |
| **Provenance ledger** | Directly answers SEBI Reg 16C "data lineage" questions. Creates a real compliance artifact. |
| **Lifecycle graph edges** | The single biggest differentiator vs. plain vector RAG — system can say "this circular is superseded" |
| **Active-status filter** | Prevents system from confidently citing dead law — the highest-stakes silent failure mode. |
| **Zero disruption** | All retrieval, reasoning, and LLM logic untouched. Risk is contained to data pipeline. |

### Cons / Risks to Manage

| Risk | Mitigation |
|---|---|
| **SEBI RSS URL may change** | Monitor URL at implementation time; add health-check that alerts on feed unavailability |
| **Supersession detection ~70-80% accuracy** | Create "proposed" edges requiring admin confirmation before activation |
| **Provenance ledger will need SQLite at scale** | Design interface now, swap JSON → SQLite when records exceed ~5,000 |
| **backfill_provenance() is a one-time migration** | Run in a transaction, keep a backup of existing data before running |
| **SEBI copyright permission not yet obtained** | RSS feed (new circulars) and admin-authorized uploads are safe immediately. File permission request ASAP |
| **AMFI site structure drift** | Staleness monitor detects URL 404s; admin is alerted before retrieval quality degrades |
| **Multi-turn 25% metric still uninvestigated** | Separate audit of test harness scoring logic — not blocking pipeline work |

---

## Verification Plan

| Test | Expected Result | Pass Criteria |
|---|---|---|
| **NER warmup** | First query: NER latency < 500ms | No >1000ms NER spike on fresh app start |
| **Token fix** | Run query twice | Warm: tokens_input=12, tokens_saved=1,008 |
| **Fingerprint gate** | Repeat same query | Exact repeat: embedding not called (tokens≈0) |
| **Provenance completeness** | `generate_compliance_report()` | 100% of files in `data/AMC/` have ledger records |
| **SHA-256 dedup** | Ingest same PDF twice | Second ingest: `status="already_indexed"`, FAISS unchanged |
| **Status-filtered retrieval** | Mark circular as superseded → query its content | With `RETRIEVAL_ACTIVE_ONLY=True`: not returned |
| **Supersession edge** | Ingest "Addendum to SEBI Circular…" | Neo4j: `(:RegulatoryDocument)-[:AMENDED_BY]->(:RegulatoryDocument)` |
| **End-to-end** | Mock RSS feed with 1 new entry → run pipeline → query | Answer grounded in new circular, provenance shows "sebi_rss" channel |

---

## Open Questions (Need User Decision)

> [!IMPORTANT]
> **Q1: Is this being built FOR the AMC (internal tool) or AS a product sold TO multiple AMCs?**
> - **For the AMC**: AMFI member portal + authorized email inbox are additional legal acquisition channels (Option 6 from crawl doc). Add `amfi_member_portal_adapter.py` as Layer 1D.
> - **As a product**: Licensed redistributor route (Taxmann/Lexplosion, ~₹1–5L/yr) becomes the shared data layer and should be added as Layer 1E. Architecture of Layer 1 changes significantly.

> [!IMPORTANT]
> **Q2: Should supersession edges auto-activate or require admin confirmation?**
> - **Auto-activate**: Faster, but regex has ~20-30% false positive rate (e.g., "Extension of timeline" circulars)
> - **Proposed + confirm**: Safer, but requires admin review loop. Recommended.

> [!NOTE]
> **Q3: Provenance ledger storage — JSON vs SQLite from Day 1?**
> At current scale (~163 circulars), JSON is fine. If planning for 5,000+ documents from AMFI SID/SAI/KIM ingestion, start with SQLite immediately rather than migrating later.

> [!NOTE]
> **Q4: Should the Neo4j re-traversal on cache hits be made optional?**
> Current behavior: live graph traversal runs even on cache hits (for UI graph visualization). Making it optional would reduce warm-hit cost to truly ~0 tokens, but graph panel would show stale data.

> [!NOTE]
> **Q5: Multi-turn 25% metric investigation** — This needs a separate audit session examining the test harness scoring logic. Should this be a blocking item before production deployment, or a parallel investigation?

---

*Plan prepared by: Antigravity | 2026-08-06*
