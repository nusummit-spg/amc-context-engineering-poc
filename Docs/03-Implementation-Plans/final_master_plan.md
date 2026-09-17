# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# AMC Context Engineering — Final Master Implementation Plan
## All Open Questions Resolved · Ready to Execute

**Prepared**: 2026-08-06 | **Version**: Final (all decisions confirmed)
**Total scope**: 7 new files · 9 modified files · 16–18 working days

---

## Decision Log — All 5 Questions Resolved

| Q# | Question | Decision | Impact on Plan |
|---|---|---|---|
| **Q1** | Built FOR AMC or AS product? | **For AMCs (shared RAG/taxonomy model)** — may share with other AMCs | Adds AMFI member portal as Layer 1D + multi-tenant isolation design note |
| **Q2** | Supersession edges auto or confirm? | **Go with recommendation** = Proposed + Admin Confirm | `confidence:"medium"` auto-created, admin promotes to `"confirmed"` |
| **Q3** | Provenance ledger JSON or SQLite? | **SQLite from Day 1** | `provenance_ledger.py` uses SQLite (`sqlite3` stdlib), no migration later |
| **Q4** | Neo4j re-traversal on cache hits — optional? | **Production recommendation = Smart Default** (see below) | `CACHE_GRAPH_MODE` config flag with `"smart"` default |
| **Q5** | Multi-turn 25% metric — blocking or parallel? | **Parallel investigation** — non-blocking | Separate audit track, does not delay pipeline work |

---

## Q4 Decision: Smart Graph Mode for Cache Hits (Expanded)

**The production recommendation** — neither "always live" nor "always skip":

```
CACHE_GRAPH_MODE = "smart"   (default — recommended for production)
CACHE_GRAPH_MODE = "live"    (current behavior — always re-traverses)
CACHE_GRAPH_MODE = "skip"    (token-minimized — graph panel shows cached nodes)
```

**Smart mode logic**:
```
On cache hit:
  IF cached.graph_node_count <= 5:
    → Skip Neo4j re-traversal (graph is simple, stale risk is low)
    → Serve cached graph nodes directly
    → tokens_input = ~0 (fingerprint probe only)
  IF cached.graph_node_count > 5:
    → Run live Neo4j re-traversal (graph is complex, freshness matters)
    → tokens_input = ~12 (embedding + cosine sim overhead)
```

**Rationale**:
- Regulatory queries that hit dense graph clusters (SEBI circular networks with 10–20 nodes) benefit from live re-traversal — those relationships change as new circulars are indexed
- Simple entity lookups (3–5 nodes) are stable — a "Large Cap Fund" node doesn't change between queries
- Smart mode maximizes token savings while keeping graph accuracy where it counts

**Production tradeoff table**:

| Mode | Token Cost (warm) | Graph Freshness | Best For |
|---|---|---|---|
| `skip` | ~0 | Stale | Token-minimized demos |
| `smart` | ~0 or ~12 | Fresh when needed | **Production (recommended)** |
| `live` | ~12 | Always fresh | Compliance-critical environments |

---

## Q1 Decision: Built FOR AMCs — Architecture Implications

Since this is built for AMCs with potential sharing of the RAG/taxonomy model:

### What Changes in Layer 1 (Data Acquisition)
Add **Layer 1D: AMFI Member Portal Adapter** — the AMC as a registered AMFI member is an authorized recipient of:
- AMFI circulars to member AMCs
- SEBI circulars distributed via intermediary channels
- SEBI SI/intermediary portal documents

This is the **legally cleanest of all channels** — the AMC is *archiving what was officially addressed to them*, not scraping anything.

### Multi-Tenant Isolation Design Note (for future sharing)
When the RAG/taxonomy model is shared with another AMC customer, each AMC's proprietary data (internal memos, fund manager notes, client-specific documents) must be isolated. SEBI circulars and AMFI data are shared (they are the same for all AMCs). Design principle:
```
Namespace pattern:
  data/AMC/shared/         ← SEBI circulars, AMFI data, Gazette — shared across tenants
  data/AMC/{amc_name}/     ← AMC-specific documents — tenant-isolated
```
The RBAC system (`rbac.py`) already enforces this at the query layer. The data organization formalizes it at the ingestion layer.

---

## Critical Issues — Fix First (Phase 0, Days 1–3)

### Fix 1: NER Cold-Start Spike (157 seconds → <500ms)

**Root cause**: `_get_gliner()` lazy-loads the GLiNER model on the **first live user request**. First request takes 157 seconds.

**Plan**:

#### [`ner_pipeline.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py) — Add `warmup_ner_models()`
```python
def warmup_ner_models() -> None:
    """Pre-load spaCy + GLiNER at startup. Call once from app.py."""
    print("  [NER Warmup] Loading spaCy EntityRuler...", flush=True)
    _get_nlp()
    print("  [NER Warmup] Loading GLiNER model...", flush=True)
    _get_gliner()
    print("  [NER Warmup] Done.", flush=True)
```

#### [`app.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/app.py) — Startup hook
```python
@st.cache_resource
def _startup_warmup():
    import ner_pipeline
    ner_pipeline.warmup_ner_models()
    return True
_startup_warmup()
```

**Trade-off**: App startup is 15–30 seconds slower. Completely acceptable in production (startup happens once per process). Eliminates a 157-second UX-destroying spike on first user request.

---

### Fix 2: Ghost Token Accounting on Cache Hits

**Root cause**: [`taxonomy_retrieval.py` lines 395–397](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/taxonomy_retrieval.py#L395-L397) reports the original cold run's token count on every warm cache hit, making total tokens appear identical for cold and warm runs.

**Plan — 3 stages**:

#### Stage A: Honest Reporting (30 min, highest impact)
```python
# Replace lines 395–397 in taxonomy_retrieval.py:
CACHE_PROBE_TOKENS = 12  # Embedding lookup + cosine similarity overhead
"tokens_input":  CACHE_PROBE_TOKENS,
"tokens_output": 0,
"tokens_total":  CACHE_PROBE_TOKENS,
"tokens_cold_equivalent": cached.total_tokens,   # What it WOULD have cost
"tokens_saved": cached.total_tokens - CACHE_PROBE_TOKENS,
```

#### Stage B: Fingerprint Gate (exact match → 0 tokens)
Add to [`intent_cache.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/intent_cache.py) `IntentAwareCache`:
```python
self._fingerprint_index: Dict[str, str] = {}  # md5 → cache_key

def fingerprint_probe(self, query: str) -> Optional[CacheEntry]:
    """Stage 1: O(1) exact text match — no embedding, no cosine sim."""
    import hashlib
    fp = hashlib.md5(query.lower().strip().encode()).hexdigest()
    cache_key = self._fingerprint_index.get(fp)
    return self._get_by_key(cache_key) if cache_key else None
```
Call `fingerprint_probe()` BEFORE `fs._embed_texts()` in `hybrid_graphrag_v2()`.

#### Stage C: Smart Graph Mode Integration
Wire the `CACHE_GRAPH_MODE` config flag (see Q4 decision) into the cache hit block:
```python
# In taxonomy_retrieval.py cache hit block:
graph_mode = getattr(config, "CACHE_GRAPH_MODE", "smart")
should_traverse = (
    graph_mode == "live"
    or (graph_mode == "smart" and cached.graph_node_count > 5)
)
if should_traverse:
    live_graph_ctx = retrieve_graph(query, ...)
    cache_probe_tokens = 12
else:
    # Serve cached graph nodes directly
    live_graph_ctx = _cached_graph_nodes_to_ctx(cached)
    cache_probe_tokens = 0
```

#### Stage D: Token Savings UI Panel
Update [`chat_view.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/chat_view.py) telemetry expander to show:
```
Token Efficiency Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cold Equivalent:  1,020 tokens  ($0.0031)
Cache Probe Cost:    12 tokens  ($0.0000)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Net Savings:      1,008 tokens  (98.8%)
API Cost Saved:   $0.0031 / query
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Fix 3: Large Cap / Small Cap Graph Node Coverage

**Root cause**: Hybrid system said "lacked data" for Large Cap/Small Cap fund specs in Turn 2, while Traditional RAG answered correctly. Graph traversal either missing nodes or entity labels not matched.

**Plan**:
1. Run diagnostic: `MATCH (e:Entity) WHERE e.text CONTAINS "Large Cap" RETURN e.text, e.label, e.product_name`
2. If missing: add to gazetteer in [`ner_pipeline.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/streamlit_app/ner_pipeline.py) `_COMMON_DOMAIN_ENTITIES`
3. Trigger incremental re-index of SEBI Categorization circular (`Categorization and Rationalization of Mutual Fund Schemes.pdf`)

---

## Production Pipeline — Full Architecture

> [!IMPORTANT]
> **Zero changes to retrieval, reasoning, or LLM logic.** `build_index.py`, `faiss_store.py`, `taxonomy_retrieval.py` are downstream consumers — pipeline only touches data entry side.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: DATA ACQUISITION (4 channels)                                  │
│                                                                           │
│  1A: sebi_feed_ingester.py     ← SEBI RSS feed (legally cleanest)        │
│  1B: amfi_portal_adapter.py    ← AMFI NAV + SID/SAI + AUM reports        │
│  1C: admin_view.py (new tab)   ← Human-authorized ingest (any doc)       │
│  1D: amfi_member_portal.py     ← AMC's own authorized AMFI inbox         │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: INGESTION GATEWAY                                               │
│  ingestion_gateway.py + provenance_ledger.py (SQLite)                    │
│  SHA-256 dedup · provenance record · status tagging · file routing       │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 3: EXISTING PIPELINE (ZERO CHANGES)                               │
│  build_index.py → document_extractors → pii_scrub → chunking →          │
│  NER → graph_store.upsert_entities() → FAISS embed                       │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 4: REGULATORY GRAPH ENRICHMENT                                    │
│  regulatory_lifecycle_enricher.py                                         │
│  [:SUPERSEDES] [:AMENDED_BY] [:APPLIES_TO] edges — confidence-gated     │
│  Admin confirms "proposed" → "confirmed" edges                           │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 5: ACTIVE-STATUS FILTER + STALENESS MONITOR                       │
│  taxonomy_retrieval.py — default: status="active" only                  │
│  staleness_monitor.py — SHA-256 drift detection on source URLs           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## New Files to Build (7 total)

### `provenance_ledger.py` (SQLite — Day 4)

**Why SQLite**: At AMFI SID/SAI/KIM scale (potentially 5,000+ documents across 40+ AMCs),
JSON file lookups become O(n) per document. SQLite with indexed columns gives O(1) lookups
from Day 1 with zero migration debt later.

**SQLite schema**:
```sql
CREATE TABLE provenance (
    provenance_id     TEXT PRIMARY KEY,
    filename          TEXT NOT NULL UNIQUE,
    sha256_hash       TEXT NOT NULL,
    acquisition_channel TEXT NOT NULL,
    source_url        TEXT,
    doc_type          TEXT,
    department        TEXT,
    entity_type       TEXT,
    status            TEXT DEFAULT 'active',
    supersedes        TEXT,
    superseded_by     TEXT,
    ingest_timestamp  TEXT NOT NULL,
    authorized_by     TEXT NOT NULL,
    drift_detected    INTEGER DEFAULT 0,
    graph_node_count  INTEGER DEFAULT 0
);

CREATE INDEX idx_status    ON provenance(status);
CREATE INDEX idx_hash      ON provenance(sha256_hash);
CREATE INDEX idx_dept      ON provenance(department);
CREATE INDEX idx_entity    ON provenance(entity_type);
```

**Key functions**:
```python
def get_connection() -> sqlite3.Connection
def find_by_hash(sha256: str) -> Optional[ProvenanceRecord]
def find_by_filename(filename: str) -> Optional[ProvenanceRecord]
def get_active_filenames() -> Set[str]        # O(1) after cached — for retrieval filter
def update_status(filename: str, new_status: str, superseded_by: str = None)
def generate_compliance_report() -> str       # Regulation 16C audit export
def backfill_existing_documents() -> int      # One-time migration — returns count processed
```

**`backfill_existing_documents()` logic**:
```
For every file in data/AMC/ folder:
  1. Compute SHA-256 hash
  2. INSERT OR IGNORE into provenance table with:
     acquisition_channel = "manual_public_download"
     status = "active"
     authorized_by = "system_backfill"
     source_url = "" (unknown at backfill time)
  3. Log: "Backfilled {count} existing documents"
Run ONCE before any new ingestion starts.
```

---

### `ingestion_gateway.py` (Day 5)

```python
@dataclass
class IngestRequest:
    filepath: Path
    acquisition_channel: str  # "sebi_rss"|"amfi_portal"|"admin_upload"|"amfi_member_portal"
    source_url: str
    doc_type: str
    department: str
    entity_type: str
    status: str = "active"
    authorized_by: str = "system"
    supersedes: Optional[str] = None
    namespace: str = "shared"   # "shared" | "{amc_name}" for tenant isolation

@dataclass
class IngestResult:
    accepted: bool
    reason: str           # "new_document"|"already_indexed"|"content_modified"|"rejected"
    sha256_hash: str
    provenance_id: str
    destination_path: Path

def process_ingest(req: IngestRequest) -> IngestResult:
    """
    1. Compute SHA-256 hash
    2. Dedup check: find_by_hash() → if exists and hash same → "already_indexed"
    3. If hash differs → old entry marked "modified", new entry created
    4. Write provenance record to SQLite
    5. Copy to data/AMC/{namespace}/{doc_type}/
    6. If supersedes → update_status(supersedes_filename, "superseded", superseded_by=filename)
    7. Return IngestResult
    """
```

---

### `sebi_feed_ingester.py` (Day 6)

**Legal basis**: SEBI RSS feed is explicitly designed for automated syndication (zero ToU friction).
Rate limit: max 1 request per 5 minutes. Honest user-agent string.

```python
def poll_sebi_rss(feed_url: str) -> List[FeedEntry]
def download_circular_pdf(url: str, dest_dir: Path) -> DownloadResult
def detect_supersession(title: str, existing_titles: List[str]) -> Optional[str]
def run_daily_sebi_poll() -> IngestionReport

SUPERSESSION_PATTERNS = [
    (r"Amendment to (?:SEBI )?Circular (?:dated|on) (.+?) dated", "AMENDED_BY"),
    (r"Addendum to (?:SEBI )?Circular(?: on)?(.+)", "AMENDED_BY"),
    (r"Extension of timeline for implementation of(.*?)dated", "EXTENDS"),
    (r"Deferment of timeline for(.*?)dated", "DEFERS"),
    (r"Clarification(?: on| regarding)(.*?)Circular", "CLARIFIES"),
    (r"(?:Modification|Review) of (?:framework|provisions)(.*)", "MODIFIES"),
]
```

---

### `amfi_portal_adapter.py` (Day 7)

**Legal basis**: AMFI NAV data + SID/SAI/KIM = SEBI-mandated public disclosures.
`mfapi.in` = community open API (clearly intended for public reuse).

```python
def fetch_nav_all() -> pd.DataFrame                     # NAVAll.txt polling
def fetch_scheme_history(scheme_code: str) -> pd.DataFrame  # mfapi.in history
def fetch_amfi_monthly_aum_report() -> DownloadResult   # Monthly AUM PDF
def fetch_sid_sai_listing() -> List[dict]               # SID/SAI/KIM listing
def fetch_amfi_circulars() -> List[FeedEntry]           # AMFI circular listing
```

---

### `amfi_member_portal.py` (Day 7, Layer 1D — NEW based on Q1 decision)

**Legal basis**: AMC as AMFI registered member is an **authorized recipient** of all AMFI
member circulars. Archiving what was sent to you = zero legal exposure.

```python
def ingest_from_member_email_folder(inbox_path: Path) -> List[IngestResult]
    """
    Watch a designated folder where compliance officer saves PDFs received via
    official AMFI member email. Auto-ingest with acquisition_channel="amfi_member_portal".
    Fully authorized — no crawling, no scraping.
    """

def watch_folder(path: Path, callback: Callable) -> None
    """
    Lightweight folder watcher using Python watchdog library.
    On new PDF file detected → process_ingest() → index.
    """
```

---

### `regulatory_lifecycle_enricher.py` (Day 11)

**Supersession Confidence Gate** (implementing Q2 recommendation):

```python
CONFIDENCE_LEVELS = {
    "confirmed": "admin has verified this relationship",
    "medium": "auto-detected from title pattern — pending admin review",
    "low": "inferred from partial title match — needs manual verification"
}

def upsert_regulatory_document(record: ProvenanceRecord) -> None:
    """MERGE RegulatoryDocument node with status, department, entity_type, effective_from."""

def detect_and_link_amendments_from_titles(records: List[ProvenanceRecord]) -> List[ProposedEdge]:
    """
    Run SUPERSESSION_PATTERNS on every circular title.
    → Create [:SUPERSEDES {confidence: "medium", pending_confirmation: True}] edges
    → Do NOT mark superseded document as status="superseded" yet
    → Return list of ProposedEdge for admin review queue
    """

def confirm_supersession_edge(proposed_edge_id: str, authorized_by: str) -> None:
    """
    Admin has reviewed and confirmed a proposed edge.
    → Set confidence = "confirmed", pending_confirmation = False
    → Update superseded document: status = "superseded", superseded_date = now()
    → Update _active_sources set in taxonomy_retrieval (invalidate cached set)
    """

def reject_supersession_edge(proposed_edge_id: str, reason: str) -> None:
    """Admin rejected: delete the proposed edge from graph."""
```

**New Neo4j schema** (extends `graph_store.init_schema()`):
```cypher
CREATE CONSTRAINT regulatory_doc_key IF NOT EXISTS
  FOR (d:RegulatoryDocument) REQUIRE d.filename IS UNIQUE;

CREATE INDEX reg_doc_status IF NOT EXISTS FOR (d:RegulatoryDocument) ON (d.status);
CREATE INDEX reg_doc_dept IF NOT EXISTS FOR (d:RegulatoryDocument) ON (d.department);

-- Relationships:
(:RegulatoryDocument)-[:SUPERSEDES {confidence, pending_confirmation, created_at}]->(:RegulatoryDocument)
(:RegulatoryDocument)-[:AMENDED_BY {confidence, pending_confirmation}]->(:RegulatoryDocument)
(:RegulatoryDocument)-[:APPLIES_TO]->(:EntityType {name: "AMC"|"Broker"|"RA"|"All"})
```

---

### `staleness_monitor.py` (Day 12)

```python
def run_drift_check(sample_size: int = 20) -> DriftReport:
    """
    For documents with a source_url:
    1. HEAD request → check Last-Modified header
    2. If modified: full download + re-hash
    3. If hash changed: drift_detected=True, alert admin
    4. If 404: flag for manual review
    """

def generate_staleness_alert(drifted: List[str]) -> str
```

---

### `pipeline_scheduler.py` (Day 10)

```python
def run_production_pipeline(mode: str = "incremental") -> PipelineReport:
    """
    Step 1: sebi_feed_ingester.run_daily_sebi_poll()
    Step 2: amfi_portal_adapter.fetch_nav_all() + fetch_sid_sai_listing()
    Step 3: For each new doc: ingestion_gateway.process_ingest()
    Step 4: build_index.build(rebuild=False)  ← UNCHANGED EXISTING
    Step 5: regulatory_lifecycle_enricher.detect_and_link_amendments_from_titles()
    Step 6: staleness_monitor.run_drift_check(sample_size=10)
    Step 7: Log to logs/pipeline_run_log.jsonl
    """
```

---

## Files Modified (9 files, minimal changes)

| File | Change | Lines Added | Risk |
|---|---|---|---|
| `ner_pipeline.py` | Add `warmup_ner_models()` | ~10 | Negligible |
| `app.py` | `@st.cache_resource` startup warmup | ~5 | Low |
| `taxonomy_retrieval.py` | Fix ghost tokens (L395–397) + smart graph mode + active-status filter | ~40 | Low |
| `intent_cache.py` | Fingerprint index + `input_tokens_cold` + `graph_node_count` fields | ~30 | Low (backward compat) |
| `chat_view.py` | Token savings panel in telemetry expander | ~40 | Low |
| `graph_store.py` | Add `init_regulatory_schema()` | ~30 | Low |
| `admin_view.py` | "Authorized Ingest" tab + pipeline trigger + proposed edge review queue | ~90 | Medium |
| `build_index.py` | Write `processed_ledger_meta.json` companion file | ~10 | Negligible |
| `config.py` | Add `RETRIEVAL_ACTIVE_ONLY`, `CACHE_GRAPH_MODE`, `SEBI_RSS_URL`, `AMFI_NAV_URL`, `MEMBER_PORTAL_INBOX` | ~12 | Negligible |

---

## Parallel Track: Multi-Turn 25% Metric Audit (Q5 — Non-blocking)

**Status**: Parallel investigation. Does not delay Phase 0, 1, or 2 work.

**What needs investigating**:
- Multi-turn scoring logic in the test harness (`scratch/run_actual_codebase_tests.py`)
- Whether the 25% figure reflects actual system performance or a test harness artifact
- Specifically: how the harness determines a "correct" multi-turn answer (cosine sim threshold? keyword match? exact match?)

**Approach**:
1. Read `scratch/run_actual_codebase_tests.py` multi-turn test section in isolation
2. Run 5 manual multi-turn queries and compare to harness score
3. If harness scoring is wrong: fix the test, not the system
4. If system is genuinely weak at multi-turn: investigate `intent_cache.py` date entity guard (too strict?) and `INTENT_HISTORY_TURNS` config

**Owner**: Separate audit session. Does not block pipeline development.

---

## Data Acquisition Legal Tiering (Final Reference)

| Data | Source | Legal Tier | Acquisition | Status |
|---|---|---|---|---|
| New SEBI circulars | SEBI RSS feed | ✅ Open (designed for bots) | `sebi_feed_ingester.py` | Phase 1 |
| Historical SEBI circulars | sebi.gov.in archive | ⚠️ Permission-gated | Admin authorized upload | Phase 1 |
| AMFI member circulars | AMFI member portal | ✅ Open (authorized recipient) | `amfi_member_portal.py` | Phase 1 |
| NAV data (all schemes) | portal.amfiindia.com | ✅ Open | `amfi_portal_adapter.py` | Phase 1 |
| SID/SAI/KIM | AMFI portal (SEBI-mandated) | ✅ Open | `amfi_portal_adapter.py` | Phase 1 |
| Monthly AUM/flow report | amfiindia.com | ✅ Open | `amfi_portal_adapter.py` | Phase 1 |
| Master Circulars | sebi.gov.in | ⚠️ Permission-gated | Admin authorized upload | Phase 1 |
| Gazette Acts/Rules | egazette.gov.in | ✅ Public domain | Scheduled download | Phase 3 |
| RBI macro data | dbie.rbi.org.in | ✅ Open (explicit reuse) | Scheduled download | Phase 3 |
| Income Tax Act 2025 | incometaxindia.gov.in | ✅ Open | One-time download | Phase 3 |
| NSE/BSE prices | NSE/BSE direct | ❌ Licensed IP | Commercial contract | Out of scope |
| Benchmark index values | NSE Indices/BISPL | ❌ Licensed IP | Commercial contract | Out of scope |
| Investor CAS data | CAMS/KFintech | ❌ Personal data (DPDP) | Never | Out of scope |

> [!CAUTION]
> **Action item (non-engineering)**: File written permission request with SEBI for historical circular reproduction. 2–4 week lead time. Until received, historical circular ingestion via admin upload path (human-authorized download) only. RSS feed for new circulars is legally clear immediately.

---

## Phased Roadmap (Final)

### Phase 0: Critical Bug Fixes (Days 1–3)

| Day | Task | File(s) | Effort |
|---|---|---|---|
| **Day 1 AM** | `warmup_ner_models()` + startup hook | `ner_pipeline.py`, `app.py` | 1h |
| **Day 1 PM** | Fix ghost token lines 395–397 (Stage A) | `taxonomy_retrieval.py` | 30min |
| **Day 2 AM** | Fingerprint gate `IntentAwareCache` (Stage B) | `intent_cache.py` | 2h |
| **Day 2 PM** | Smart graph mode `CACHE_GRAPH_MODE` (Stage C) | `taxonomy_retrieval.py`, `config.py` | 2h |
| **Day 3 AM** | Token savings panel (Stage D) | `chat_view.py` | 3h |
| **Day 3 PM** | Large Cap / Small Cap node coverage fix | `ner_pipeline.py` + Neo4j | 2h |

### Phase 1: Production Pipeline Core (Days 4–10)

| Day | Task | File(s) | Effort |
|---|---|---|---|
| **Day 4** | `provenance_ledger.py` (SQLite schema + CRUD + backfill) | NEW | Medium |
| **Day 5** | `ingestion_gateway.py` (hash dedup + routing + provenance write) | NEW | Medium |
| **Day 6** | `sebi_feed_ingester.py` (RSS poll + PDF download + supersession detect) | NEW | High |
| **Day 7** | `amfi_portal_adapter.py` + `amfi_member_portal.py` | NEW × 2 | Medium |
| **Day 8** | `admin_view.py` — Authorized Ingest tab + pipeline trigger | MODIFY | Medium |
| **Day 9** | `config.py` + `build_index.py` ledger_meta.json companion | MODIFY | Low |
| **Day 10** | `pipeline_scheduler.py` (full orchestrator + run log) | NEW | Medium |

### Phase 2: Graph Lifecycle Enrichment (Days 11–13)

| Day | Task | File(s) | Effort |
|---|---|---|---|
| **Day 11** | `graph_store.py` (`init_regulatory_schema()`) + `regulatory_lifecycle_enricher.py` | MODIFY + NEW | High |
| **Day 12** | `staleness_monitor.py` (drift detection) | NEW | Medium |
| **Day 12** | `taxonomy_retrieval.py` active-status filter + `_active_sources` cache set | MODIFY | Low |
| **Day 13** | Integration test: end-to-end RSS → ingest → index → lifecycle edges → retrieval | All | High |

### Phase 3: Analytics & Compliance Dashboard (Days 14–16)

| Day | Task | File(s) | Effort |
|---|---|---|---|
| **Day 14** | `SavingsLedger` in `intent_cache.py` + `analytics_view.py` Token Economy widget | MODIFY | Medium |
| **Day 15** | Provenance compliance report export + admin panel polish + proposed edge review UI | Multiple | Medium |
| **Day 16** | Buffer: supersession detection tuning, multi-tenant namespace testing, documentation | — | Buffer |

### Parallel Track (Throughout)

| Track | Owner | Status |
|---|---|---|
| Multi-turn 25% metric audit | Separate session | Non-blocking, run alongside Phase 1–2 |
| SEBI written permission request | Business/Legal | File immediately, 2–4 week lead time |

---

## Verification Plan

| Test | Expected Result | Pass Criteria |
|---|---|---|
| **NER warmup** | First query NER latency | < 500ms (not 157,000ms) |
| **Ghost token fix** | Run same query twice | Warm: `tokens_input=12`, `tokens_saved=1,008` |
| **Fingerprint gate** | Exact same query repeated | Embedding not called, `tokens ≈ 0` |
| **Smart graph mode** | Cache hit with 3 nodes | Graph traversal skipped, `tokens = 0` |
| **Smart graph mode** | Cache hit with 10 nodes | Live traversal runs, `tokens = 12` |
| **Backfill** | `backfill_existing_documents()` | 100% of `data/AMC/` files have SQLite record |
| **SHA-256 dedup** | Ingest same PDF twice | Second: `reason="already_indexed"`, FAISS unchanged |
| **Status filter** | Mark circular as superseded → query its content | `RETRIEVAL_ACTIVE_ONLY=True` → not returned |
| **Supersession edge** | Ingest "Addendum to SEBI Circular…" | Neo4j: `[:AMENDED_BY {confidence:"medium", pending_confirmation:True}]` |
| **Admin confirm** | Admin confirms a proposed edge | `confidence="confirmed"`, superseded doc `status="superseded"` |
| **End-to-end** | Mock RSS → pipeline → query | Answer grounded in new circular, provenance `"sebi_rss"` |
| **Compliance report** | `generate_compliance_report()` | All records have `acquisition_channel`, `authorized_by`, `sha256_hash` |

---

## Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| SEBI RSS URL changes | Medium | Feed health-check in `pipeline_scheduler.py` — alert on consecutive failures |
| Supersession detection false positives | Medium | `confidence:"medium"` + admin confirm before activating — no auto-damage |
| `backfill_provenance()` corrupts ledger | High | Take SQLite backup before running; run in transaction |
| SEBI copyright permission delays | Low | RSS + admin upload covers 90% of use cases immediately |
| AMFI site structure drift | Medium | Staleness monitor catches 404s; admin alerted before quality degrades |
| Multi-turn 25% is system weakness not test bug | Low | Parallel investigation — if system issue found, fix `INTENT_HISTORY_TURNS` config |
| Member portal inbox path misconfigured | Low | Validate path at startup; fallback gracefully with log warning |
