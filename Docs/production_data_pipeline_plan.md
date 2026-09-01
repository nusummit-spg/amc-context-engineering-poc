# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Production Data Pipeline Plan
## From "Demo-Ready Manual Downloads" → "Legally Clean, Automated, Auditable Production Pipeline"

---

## Executive Summary

The current system has **manually downloaded PDFs** placed into `data/AMC/SEBI_Circulars/` and
related folders. This is excellent for showcasing — the engineering (45 IP Pillars, Hybrid GraphRAG,
IntentCache, etc.) is completely production-grade. The only gap is the **data acquisition layer**:
how documents enter the system, how they are verified as legally sourced, and how they stay
current and accurate over time.

This plan bridges that gap in a 5-layer production pipeline — **no changes to any retrieval or
reasoning code**. The existing `build_index.py`, `graph_store.py`, `faiss_store.py`, and
`taxonomy_retrieval.py` are consumed unchanged as downstream consumers.

**Estimated build time: 8–12 working days**

---

## Current State vs. Target State

| Dimension | Current (Demo) | Target (Production) |
|---|---|---|
| **Data acquisition** | Manual PDF download by a human | Automated: RSS feed + authorized portal polling |
| **Legal provenance** | Implicit (documents exist on disk) | Explicit: `acquisition_channel`, `source_url`, `sha256_hash` per document |
| **Document lifecycle** | All documents treated as static | `status: active / superseded / withdrawn` + supersession links |
| **Staleness detection** | None — once indexed, never re-checked | SHA-256 hash drift detection on each crawl cycle |
| **Regulatory relationships** | Entity-level NER edges only | `[:SUPERSEDES]`, `[:AMENDED_BY]`, `[:APPLIES_TO]`, `[:EFFECTIVE_FROM]` lifecycle edges in Neo4j |
| **Incremental updates** | File-name based ledger (`processed_ledger.txt`) | Ledger extended with provenance JSON metadata per document |
| **Retrieval filter** | All indexed documents returned | Default filter: `status = "active"` unless user requests history |
| **Audit trail** | Basic extraction cache | Full `Regulation 16C`-compliant acquisition audit log |

---

## Architecture Overview

```
╔══════════════════════════════════════════════════════════════════════════╗
║                     LAYER 1: DATA ACQUISITION                            ║
║  ┌──────────────────────┐   ┌───────────────────────┐   ┌─────────────┐ ║
║  │ sebi_feed_ingester.py│   │ amfi_portal_adapter.py│   │ admin_view  │ ║
║  │ (SEBI RSS polling)   │   │ (AMFI NAV + circulars)│   │ (Manual tab)│ ║
║  └──────────┬───────────┘   └───────────┬───────────┘   └──────┬──────┘ ║
║             │                           │                       │        ║
╚═════════════╪═══════════════════════════╪═══════════════════════╪════════╝
              │                           │                       │
╔═════════════╪═══════════════════════════╪═══════════════════════╪════════╗
║             ▼    LAYER 2: INGESTION GATEWAY                    ▼        ║
║         ┌───────────────────────────────────────────────────────────┐   ║
║         │                 ingestion_gateway.py                       │   ║
║         │  • SHA-256 hash computation + dedup check                  │   ║
║         │  • Acquisition channel + source URL tagging                │   ║
║         │  • document_status: active / superseded / withdrawn        │   ║
║         │  • Write to provenance_ledger.json                         │   ║
║         │  • Drop verified PDF into data/AMC/{category}/             │   ║
║         └────────────────────────┬──────────────────────────────────┘   ║
╚══════════════════════════════════╪═════════════════════════════════════╝
                                   │
╔══════════════════════════════════╪═════════════════════════════════════╗
║          LAYER 3: EXISTING INDEXING PIPELINE (UNCHANGED)               ║
║                                  │                                      ║
║         ┌────────────────────────▼──────────────────────────────────┐  ║
║         │    build_index.py  (EXISTING — NO CODE CHANGES)            │  ║
║         │  document_extractors → pii_scrub → chunking → NER →        │  ║
║         │  graph_store.upsert_entities() → faiss embedding           │  ║
║         └────────────────────────┬──────────────────────────────────┘  ║
╚══════════════════════════════════╪═════════════════════════════════════╝
                                   │
╔══════════════════════════════════╪═════════════════════════════════════╗
║          LAYER 4: GRAPH LIFECYCLE ENRICHMENT (NEW SCHEMA)              ║
║                                  │                                      ║
║         ┌────────────────────────▼──────────────────────────────────┐  ║
║         │    regulatory_lifecycle_enricher.py  (NEW)                 │  ║
║         │  • Parse circular title → detect [:SUPERSEDES] patterns    │  ║
║         │  • Write [:AMENDED_BY], [:APPLIES_TO], [:EFFECTIVE_FROM]   │  ║
║         │  • Extend graph_store.init_schema() with new constraints   │  ║
║         └────────────────────────┬──────────────────────────────────┘  ║
╚══════════════════════════════════╪═════════════════════════════════════╝
                                   │
╔══════════════════════════════════╪═════════════════════════════════════╗
║          LAYER 5: RETRIEVAL FILTER + STALENESS MONITOR                 ║
║                                  │                                      ║
║  ┌───────────────────────────────▼──────────────┐  ┌─────────────────┐ ║
║  │ taxonomy_retrieval.py  (MINIMAL ENHANCEMENT)  │  │ staleness_     │ ║
║  │ • Default filter: status = "active"           │  │ monitor.py     │ ║
║  │ • Config flag: RETRIEVAL_ACTIVE_ONLY = True   │  │ (drift detect) │ ║
║  └───────────────────────────────────────────────┘  └─────────────────┘ ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Layer 1: Data Acquisition

### Module 1A: `sebi_feed_ingester.py` (NEW)

**Purpose**: Poll SEBI's official RSS feed and download new circulars automatically.
This is the **legally cleanest acquisition channel** — SEBI explicitly publishes the feed
for automated syndication.

**Target RSS Endpoints** (to be confirmed at implementation time):
```
https://www.sebi.gov.in/rss.html  — Press releases + circulars
https://www.sebi.gov.in/legal/circulars/  — Main circular listing page
```

**Key Functions to Build**:
```python
def poll_sebi_rss(feed_url: str) -> List[FeedEntry]:
    """
    Fetch RSS feed, parse entries.
    Returns list of: {title, link, published_date, department, doc_type}
    Rate-limit: max 1 request/5 minutes. Identify user-agent honestly.
    """

def download_circular_pdf(url: str, dest_dir: Path) -> DownloadResult:
    """
    Download PDF if not already in provenance ledger (hash check first).
    Returns: {filepath, sha256_hash, download_timestamp, source_url, status: "new" | "known" | "modified"}
    """

def detect_supersession(title: str, existing_titles: List[str]) -> Optional[str]:
    """
    Pattern match circular titles for supersession language:
    - "Amendment to Circular dated..."
    - "Addendum to..."
    - "Deferment of timeline for..."
    - "Extension of timeline for..."
    Returns: filename of the circular being superseded/amended, or None
    """

def run_daily_sebi_poll() -> IngestionReport:
    """
    Orchestrator: poll → detect new → download → hash → handoff to ingestion_gateway
    Designed to be called by scheduler or admin panel trigger.
    """
```

**Data Model for Each Feed Entry**:
```python
@dataclass
class FeedEntry:
    circular_id: str          # e.g. "SEBI/HO/IMD/2025/0123"
    title: str
    source_url: str
    published_date: datetime
    department: str           # IMD, MRD, MIRSD, HO, CFD — parsed from title/metadata
    entity_type: str          # AMC, Broker, RA, All — inferred from title patterns
    doc_type: str             # "circular" | "master_circular" | "faq" | "order"
    pdf_url: str
    supersedes_title: str     # If detected from title pattern — may be None
```

---

### Module 1B: `amfi_portal_adapter.py` (NEW)

**Purpose**: Ingest from AMFI's official data channels — already confirmed legally clean
(`portal.amfiindia.com` and `mfapi.in` are public utility services).

**Key Functions to Build**:
```python
def fetch_nav_all() -> pd.DataFrame:
    """
    Pull from: https://portal.amfiindia.com/spages/NAVAll.txt
    Returns: DataFrame of all current NAV values.
    Hash entire response → compare to last known hash → only index if changed.
    """

def fetch_scheme_history(scheme_code: str) -> pd.DataFrame:
    """
    Pull from: https://api.mfapi.in/mf/{scheme_code}
    Used for NAV history enrichment.
    """

def fetch_amfi_circular_listing() -> List[dict]:
    """
    Scrape AMFI's public circular listing page (AMFI TOS to be confirmed).
    Returns structured list of AMFI circular metadata.
    """
```

> [!NOTE]
> AMFI data via `mfapi.in` has zero legal risk and should be ingested first —
> it's the fastest path to enriching the fund performance domain of the graph.

---

### Module 1C: Admin Panel — "Authorized Ingest" Tab (EXTEND `admin_view.py`)

**Purpose**: Human-in-the-loop capture for documents a compliance officer has reviewed and
decided to ingest. Legally equivalent to an authorized person downloading a document.
Provides the acquisition channel provenance trail for Regulation 16C.

**New Tab to Add**: `"📥 Authorized Ingest"` alongside existing tabs in `admin_view.py`

**UI Elements**:
```
┌────────────────────────────────────────────────────────────┐
│           Authorized Document Ingest                        │
├────────────────────────────────────────────────────────────┤
│  Source URL:  [https://sebi.gov.in/circular/...]           │
│  OR Upload:   [Browse PDF]                                  │
│  Document Type: [Circular ▼] [Master Circular ▼] [FAQ ▼]   │
│  Department:    [IMD ▼] [MRD ▼] [MIRSD ▼] [HO ▼] [CFD ▼] │
│  Entity Type:   [AMC ▼] [Broker ▼] [All ▼]                 │
│  Status:        [Active ▼]                                  │
│  Authorized by: [current RBAC user — auto-populated]        │
│  [Ingest Document]                                          │
└────────────────────────────────────────────────────────────┘
```

**On Submit**:
1. Compute SHA-256 hash of uploaded/downloaded PDF
2. Check provenance ledger — reject if already indexed (show existing entry)
3. Write to `provenance_ledger.json` with full metadata
4. Drop file into `data/AMC/SEBI_Circulars/` (or appropriate subfolder)
5. Trigger incremental `build_index.build(rebuild=False)` in background thread
6. Show real-time progress in Streamlit expander

---

## Layer 2: Ingestion Gateway

### Module: `ingestion_gateway.py` (NEW)

**Purpose**: Single entry point for ALL acquisition channels. Ensures every document
that enters the indexing pipeline has been properly hashed, tagged, and logged
regardless of which acquisition channel brought it in.

**Key Functions**:
```python
@dataclass
class IngestRequest:
    filepath: Path
    acquisition_channel: str    # "sebi_rss" | "amfi_portal" | "admin_authorized_upload"
                                # | "admin_authorized_url" | "amfi_member_portal"
    source_url: str             # Original URL the document came from
    doc_type: str               # "circular" | "master_circular" | "faq" | "nav_data"
    department: str             # For SEBI: IMD, MRD, MIRSD, HO, CFD
    entity_type: str            # "AMC" | "Broker" | "All" | ...
    status: str                 # "active" — default on ingest
    authorized_by: str          # Username from RBAC session
    supersedes: Optional[str]   # Filename of circular this supersedes, if known

@dataclass
class IngestResult:
    accepted: bool
    reason: str                 # "new_document" | "already_indexed" | "content_modified"
    sha256_hash: str
    provenance_id: str          # UUID for this ingest event
    destination_path: Path

def process_ingest(req: IngestRequest) -> IngestResult:
    """
    1. Compute SHA-256 hash of document
    2. Lookup hash in provenance_ledger.json
       - If found AND content same: return "already_indexed" — skip
       - If found BUT hash changed: mark old entry as "modified", accept new
       - If not found: accept as "new_document"
    3. Write provenance record to provenance_ledger.json
    4. Copy file to destination data/ directory
    5. If supersedes != None: update status of superseded document in ledger
    6. Return IngestResult
    """
```

### Module: `provenance_ledger.py` (NEW)

**Purpose**: Persistent JSON store recording the legal provenance of every document in the system.
This is the **Regulation 16C compliance artifact** — if SEBI or DPDP Board ever asks "where did
this data come from and under what right?", this ledger answers that question.

**Storage**: `data/provenance_ledger.json` (root of data directory, outside FAISS indexes)

**Schema per Document Record**:
```json
{
  "provenance_id": "uuid-v4",
  "filename": "Categorization and Rationalization of Mutual Fund Schemes.pdf",
  "sha256_hash": "a3f7c2...",
  "acquisition_channel": "admin_authorized_upload",
  "source_url": "https://sebi.gov.in/legal/circulars/...",
  "doc_type": "circular",
  "department": "IMD",
  "entity_type": "AMC",
  "status": "active",
  "supersedes": null,
  "superseded_by": null,
  "ingest_timestamp": "2026-08-05T13:00:00+05:30",
  "authorized_by": "sarah_compliance",
  "indexed_at": "2026-08-05T13:05:00+05:30",
  "last_verified_hash": "2026-08-05T13:00:00+05:30",
  "drift_detected": false
}
```

**Key Functions**:
```python
def get_ledger() -> Dict[str, ProvenanceRecord]:      # Load / create
def find_by_hash(sha256: str) -> Optional[ProvenanceRecord]:
def find_by_filename(filename: str) -> Optional[ProvenanceRecord]:
def update_status(filename: str, new_status: str, superseded_by: str = None):
def write_record(record: ProvenanceRecord):
def generate_compliance_report() -> str:              # For Regulation 16C audit export
```

---

## Layer 3: Existing Indexing Pipeline (Zero Changes)

`build_index.py` is consumed **completely unchanged**. The ingestion gateway drops verified
files into the `data/AMC/` folder hierarchy, and `build_index.py` picks them up on its
next incremental run.

**One Minor Enhancement** (not a code change, a ledger enhancement):
The existing `processed_ledger.txt` (plain filename list) needs a companion
`processed_ledger_meta.json` that maps filename → provenance_id, enabling the graph
enrichment layer (Layer 4) to look up the regulatory metadata for each indexed document.

```json
{
  "Categorization and Rationalization of Mutual Fund Schemes.pdf": {
    "provenance_id": "uuid-v4",
    "status": "active",
    "department": "IMD",
    "entity_type": "AMC",
    "acquisition_channel": "sebi_rss"
  }
}
```

This companion ledger is written by `ingestion_gateway.py`, read by `regulatory_lifecycle_enricher.py`.

---

## Layer 4: Graph Lifecycle Enrichment

### Module: `regulatory_lifecycle_enricher.py` (NEW)

**Purpose**: After `build_index.py` indexes a document, this module adds the **regulatory
relationship edges** to Neo4j that make the knowledge graph genuinely superior to flat
vector RAG — specifically the lifecycle edges that allow the system to say
"this circular was superseded last year" instead of confidently citing dead law.

**New Neo4j Schema** (extend `graph_store.init_schema()`):
```cypher
-- New node label: RegulatoryDocument
CREATE CONSTRAINT regulatory_doc_key IF NOT EXISTS
  FOR (d:RegulatoryDocument) REQUIRE d.filename IS UNIQUE;

CREATE INDEX reg_doc_status IF NOT EXISTS
  FOR (d:RegulatoryDocument) ON (d.status);

CREATE INDEX reg_doc_dept IF NOT EXISTS
  FOR (d:RegulatoryDocument) ON (d.department);

-- New relationship types:
(:RegulatoryDocument)-[:SUPERSEDES]->(:RegulatoryDocument)
(:RegulatoryDocument)-[:AMENDED_BY]->(:RegulatoryDocument)
(:RegulatoryDocument)-[:APPLIES_TO]->(:EntityType {name: "AMC" | "Broker" | "RA"})
(:RegulatoryDocument {effective_from: date, superseded_date: date, status: "active"})
```

**Key Functions**:
```python
def upsert_regulatory_document(provenance_record: ProvenanceRecord):
    """
    MERGE RegulatoryDocument node with lifecycle properties:
    - filename, status, department, entity_type
    - effective_from (from provenance ingest_timestamp)
    - superseded_date (populated when status changes to "superseded")
    - sha256_hash, acquisition_channel (for audit)
    """

def link_supersession_chain(filename: str, supersedes_filename: str):
    """
    MERGE (new:RegulatoryDocument {filename: $filename})
    MERGE (old:RegulatoryDocument {filename: $supersedes_filename})
    MERGE (new)-[:SUPERSEDES]->(old)
    SET old.status = "superseded", old.superseded_date = $now,
        old.superseded_by = $filename
    """

def link_entity_type_applicability(filename: str, entity_types: List[str]):
    """
    MERGE (d:RegulatoryDocument {filename: $filename})
    FOREACH (et IN $entity_types |
      MERGE (e:EntityType {name: et})
      MERGE (d)-[:APPLIES_TO]->(e)
    )
    """

def detect_and_link_amendments_from_titles(provenance_records: List[ProvenanceRecord]):
    """
    Run over all provenance records where title contains amendment language:
    "Amendment to Circular dated...", "Addendum to...", "Extension of timeline for..."
    Use regex + date entity extraction to resolve which existing circular is being amended.
    Create [:AMENDED_BY] edges in graph.
    """
```

**Amendment Detection Patterns** (compiled regex set):
```python
SUPERSESSION_PATTERNS = [
    (r"Amendment to (?:SEBI )?Circular (?:dated|on) (.+?) dated", "AMENDED_BY"),
    (r"Addendum to (?:SEBI )?Circular(?: on)?(.+)", "AMENDED_BY"),
    (r"Extension of timeline for implementation of(.*?)dated", "EXTENDS"),
    (r"Deferment of timeline for(.*?)dated", "DEFERS"),
    (r"Clarification(?: on| regarding)(.*?)Circular", "CLARIFIES"),
    (r"(?:Modification|Review) of (?:framework|provisions)(.*)", "MODIFIES"),
]
```

> [!IMPORTANT]
> The amendment detection is **best-effort NLP** — it will correctly identify ~70-80%
> of supersession relationships from title text alone. Manual corrections via the
> Admin Panel "Authorized Ingest" tab cover the remaining 20-30%.
> This is an IP differentiator: no existing RAG system does this automatically.

---

## Layer 5: Retrieval Filter + Staleness Monitor

### Enhancement 5A: Active-Status Filter in `taxonomy_retrieval.py`

**Current behavior**: All indexed chunks are returned regardless of their document's
current regulatory status. A superseded circular's chunks are indistinguishable from
an active one's in retrieval.

**Target behavior**: By default, retrieval only surfaces chunks from `status = "active"` documents.

**Implementation approach**:
- Add a new config flag: `RETRIEVAL_ACTIVE_ONLY = True` (default)
- In `retrieve_vector()`: filter chunks whose `source` filename maps to `status=active`
  in the provenance ledger (loaded once as a module-level set for O(1) lookup)
- In `retrieve_graph()`: add `AND d.status = "active"` to Cypher queries on `RegulatoryDocument` nodes
- Expose as an optional toggle in the UI ("Include superseded circulars in search")

**Key data structure** (loaded once at startup):
```python
# In taxonomy_retrieval.py module globals:
_active_sources: Set[str] = set()  # set of filenames with status="active"

def _load_active_sources():
    """Load from provenance_ledger.json on startup. Refresh every 60min."""
    ledger = provenance_ledger.get_ledger()
    return {rec.filename for rec in ledger.values() if rec.status == "active"}
```

---

### Module 5B: `staleness_monitor.py` (NEW)

**Purpose**: Periodically re-check the SHA-256 hash of every known document against
its source URL. If SEBI silently edits a published circular (this does happen), the
system detects it and flags the document for re-ingestion review.

**Key Functions**:
```python
def run_drift_check(provenance_ledger: Dict, sample_size: int = 20) -> DriftReport:
    """
    For each document with a source_url in the provenance ledger:
    1. HEAD request to source_url — check Last-Modified header
    2. If Last-Modified > ingest_timestamp: download and re-hash
    3. If hash changed: set drift_detected = True, alert compliance officer
    4. If URL 404s: flag document for manual status review
    Returns: count of documents checked, drifted, 404d
    """

def generate_staleness_alert(drifted_docs: List[str]) -> str:
    """Format an alert message for the admin panel / email notification."""

@dataclass
class DriftReport:
    checked_count: int
    drifted_count: int
    not_found_count: int
    drifted_filenames: List[str]
    not_found_filenames: List[str]
    checked_at: datetime
```

**Trigger Strategy** (no separate daemon needed):
- Called from the Admin Panel "Staleness Check" button (manual trigger)
- Optionally called at end of each `run_daily_sebi_poll()` cycle (lightweight sample)
- Checks max `sample_size=20` documents per run to avoid hammering government servers

---

## Pipeline Orchestrator

### Module: `pipeline_scheduler.py` (NEW)

**Purpose**: Ties all acquisition and enrichment steps into a single callable pipeline.
Can be triggered manually (Admin Panel button), or via a simple Python `schedule` cron,
or eventually via an external job scheduler (Airflow, APScheduler).

**Orchestration Flow**:
```python
def run_production_pipeline(mode: str = "incremental"):
    """
    Full pipeline orchestration:

    Step 1: Acquire new documents
        sebi_feed_ingester.run_daily_sebi_poll()
        amfi_portal_adapter.fetch_nav_all()
        [Admin manual ingests happen separately via UI]

    Step 2: Ingest gateway processing
        For each downloaded document:
            ingestion_gateway.process_ingest(req)

    Step 3: Index new documents
        build_index.build(rebuild=(mode == "rebuild"))
        [EXISTING — NO CODE CHANGES]

    Step 4: Graph lifecycle enrichment
        regulatory_lifecycle_enricher.detect_and_link_amendments_from_titles(
            provenance_records=provenance_ledger.get_new_since_last_run()
        )

    Step 5: Staleness drift check (lightweight sample)
        staleness_monitor.run_drift_check(sample_size=10)

    Step 6: Report
        Log ingestion report to logs/pipeline_run_log.jsonl
    """
```

---

## New Files Summary

| File | Location | Purpose | Layer |
|---|---|---|---|
| `sebi_feed_ingester.py` | `streamlit_app/` | SEBI RSS polling + PDF download | 1A |
| `amfi_portal_adapter.py` | `streamlit_app/` | AMFI NAV + circular ingestion | 1B |
| `ingestion_gateway.py` | `streamlit_app/` | Unified ingest entry point + hash dedup | 2 |
| `provenance_ledger.py` | `streamlit_app/` | Regulation 16C compliance audit trail | 2 |
| `regulatory_lifecycle_enricher.py` | `streamlit_app/` | Graph lifecycle edges + supersession | 4 |
| `staleness_monitor.py` | `streamlit_app/` | SHA-256 drift detection on source URLs | 5B |
| `pipeline_scheduler.py` | `streamlit_app/` | Full pipeline orchestrator | All |

---

## Files Enhanced (Minimal Changes Only)

| File | What Changes | Estimated Lines Added |
|---|---|---|
| `admin_view.py` | Add "Authorized Ingest" tab (Tab 4) | ~60 lines |
| `graph_store.py` | Add `init_regulatory_schema()` for new node/edge types | ~30 lines |
| `build_index.py` | Write `processed_ledger_meta.json` alongside existing ledger | ~10 lines |
| `config.py` | Add `RETRIEVAL_ACTIVE_ONLY`, `SEBI_RSS_URL`, `AMFI_NAV_URL` flags | ~8 lines |
| `taxonomy_retrieval.py` | Load `_active_sources` set; filter chunks by status | ~20 lines |

> [!IMPORTANT]
> **Zero changes to any reasoning, retrieval, or LLM logic.** Only data acquisition,
> provenance metadata, and one optional status filter in retrieval.

---

## Implementation Timeline (8–12 Working Days)

| Day | Deliverable | Effort |
|---|---|---|
| **Day 1** | `provenance_ledger.py` — data model, read/write, compliance report | Medium |
| **Day 2** | `ingestion_gateway.py` — hash dedup, provenance write, file routing | Medium |
| **Day 3** | `sebi_feed_ingester.py` — RSS polling, PDF download, supersession detection | High |
| **Day 4** | `amfi_portal_adapter.py` — NAV fetch, hash check | Low |
| **Day 5** | `admin_view.py` — "Authorized Ingest" tab UI | Medium |
| **Day 6** | `graph_store.py` + `regulatory_lifecycle_enricher.py` — schema + lifecycle edges | High |
| **Day 7** | `staleness_monitor.py` — drift detection, alert generation | Medium |
| **Day 8** | `pipeline_scheduler.py` — orchestrator, logging | Medium |
| **Day 9** | `taxonomy_retrieval.py` — active-status filter, `_active_sources` set | Low |
| **Day 10** | Integration testing: full cold run → RSS ingest → index → graph edges → retrieve | High |
| **Day 11** | Provenance compliance report generation + Admin Panel polish | Medium |
| **Day 12** | Buffer: edge cases, supersession detection tuning, documentation | Buffer |

---

## Verification Plan

### Test 1: Legal Provenance Completeness
```
Run: provenance_ledger.generate_compliance_report()
Expect: Every file in data/AMC/ has a corresponding provenance record
        with acquisition_channel, source_url, sha256_hash, authorized_by
Pass criteria: 100% coverage
```

### Test 2: SHA-256 Deduplication
```
Run: Attempt to ingest same PDF twice via ingestion_gateway
Expect: Second ingest returns status="already_indexed", file NOT re-indexed
Pass criteria: FAISS index size unchanged, ledger shows single record
```

### Test 3: Status-Filtered Retrieval
```
Step 1: Mark one circular as status="superseded" in provenance ledger
Step 2: Query taxonomy_retrieval.hybrid_graphrag_v2() for its content
Expect: With RETRIEVAL_ACTIVE_ONLY=True → superseded circular NOT returned
        With RETRIEVAL_ACTIVE_ONLY=False → superseded circular returned (historical mode)
```

### Test 4: Supersession Edge in Graph
```
Run: regulatory_lifecycle_enricher for "Addendum to SEBI Circular on Borrowing by Mutual Funds.pdf"
Expect: Neo4j contains (:RegulatoryDocument)-[:AMENDED_BY]->(:RegulatoryDocument) edge
        "Borrowing by Mutual Funds.pdf" status = "superseded"
Verify: Cypher MATCH (a)-[:AMENDED_BY]->(b) RETURN a.filename, b.filename
```

### Test 5: Drift Detection
```
Run: staleness_monitor.run_drift_check(sample_size=5)
Expect: For documents with valid source_url → check completes without error
        For documents without source_url → gracefully skipped with log
```

### Test 6: End-to-End RSS → Query
```
Step 1: Mock SEBI RSS feed with 1 new circular entry
Step 2: Run pipeline_scheduler.run_production_pipeline()
Step 3: Query the new circular's content via chat UI
Expect: Answer is grounded in the new circular, provenance shows "sebi_rss" channel
```

---

## Open Questions

> [!IMPORTANT]
> **Q1: SEBI RSS URL Confirmation**
> The exact RSS endpoint needs to be confirmed at implementation time. SEBI's website
> structure changes periodically. Plan: check `https://www.sebi.gov.in/rss.html` and
> `https://sebi.gov.in/sebiweb/other/OtherAction.do?doRecent=yes&type=1` at build time.

> [!IMPORTANT]
> **Q2: For which entity is this being built — the AMC itself, or as a vendor product?**
> - If **built for the AMC**: the AMC's own AMFI member portal and authorized email inbox
>   become a legal acquisition channel (Option 6 from the AMC_website_crawl_info.md).
>   This should be added as a fourth acquisition module if applicable.
> - If **sold as a product to multiple AMCs**: each AMC customer uses their own authorized
>   portal access, and the licensed redistributor route (Taxmann/Lexplosion) becomes the
>   shared data layer. This changes the architecture of Layer 1 significantly.

> [!NOTE]
> **Q3: Supersession Detection Confidence Threshold**
> The regex-based amendment detection will have false positives (e.g., "Extension of
> timeline" circulars are about deadlines, not content supersession). Should the system
> auto-create [:SUPERSEDES] edges, or create them as "proposed" edges requiring admin
> confirmation before activation? Recommended: auto-create with `confidence: "medium"`,
> admin can promote to `confidence: "confirmed"` or delete.

> [!NOTE]
> **Q4: Historical Document Migration**
> The 163 existing SEBI circulars + 24 Master Circulars currently in the system have
> no provenance records. Plan: run a one-time `backfill_provenance()` function that:
> - Assigns `acquisition_channel: "manual_public_download"` to all existing documents
> - Computes SHA-256 hashes from existing files
> - Sets `status: "active"` as default (manual review to mark superseded ones)
> - Sets `authorized_by: "system_backfill"`
> This backfill runs ONCE and does not touch the FAISS index or Neo4j.
