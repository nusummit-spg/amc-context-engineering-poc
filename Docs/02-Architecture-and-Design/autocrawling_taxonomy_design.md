# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Auto-Crawling & Dynamic Taxonomy Generation — Detailed Design Plan

**Purpose**: Forward-looking implementation design — what we are building and how  
**Scope**: Data acquisition automation + living taxonomy generation from crawled content  
**Status**: Design phase — no code changes made yet

---

## 1. Problem Statement

### Current State (What Exists Today)
```
Manual download → Drop PDF into data/AMC/ folder → Run build_index.py → Done
```

The taxonomy (`taxonomy.json`) is a **static file** built once from AMFI CSV/XLSX exports.
It contains 5 fixed dimensions: `fund_houses`, `scheme_names`, `categories`, `sub_categories`, `benchmarks`.

**Gaps this creates:**
- New SEBI circulars add new fund categories, regulatory obligations, compliance terms — these never enter the taxonomy
- AMFI publishes new scheme registrations, new AMC onboardings — these are missed until manual refresh
- The NER gazetteer in `ner_pipeline.py` that drives entity matching is seeded once from this static taxonomy — it grows stale
- The knowledge graph accumulates dead edges (superseded circulars still treated as active)

### Target State (What We Are Building)
```
Scheduled crawler → Ingestion gateway → Indexing pipeline → Auto-taxonomy extraction
      ↓                    ↓                   ↓                     ↓
SEBI RSS feed     SHA-256 dedup +      (existing,           NER-driven concept
AMFI portal       provenance SQLite    zero changes)        extraction + FIBO
AMFI member inbox status tagging                            anchoring + graph
Admin upload                                                node generation
```

The taxonomy becomes **self-updating** — every new document ingested automatically:
1. Extracts new concepts and entity terms
2. Merges them into `taxonomy.json`
3. Refreshes the NER gazetteer cache
4. Creates new graph nodes and regulatory edges in Neo4j
5. Triggers partial FAISS re-embedding for changed chunks

---

## 2. Overall System Architecture

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    AUTO-CRAWLING SUBSYSTEM                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Channel A          Channel B           Channel C          Channel D         ║
║  sebi_feed_         amfi_portal_        amfi_member_       admin_view.py     ║
║  ingester.py        adapter.py          portal.py          (manual tab)      ║
║  ─────────────      ────────────────    ──────────────     ──────────────    ║
║  SEBI RSS feed      AMFI NAV + SID/SAI  AMC authorized     Human-authorized  ║
║  (new circulars)    (scheme data, AUM)  inbox (member)     upload/URL        ║
╚══════════════════════════╤═══════════════════════════════════════════════════╝
                           │  (all channels funnel here)
                           ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                    INGESTION GATEWAY (ingestion_gateway.py)                  ║
║  SHA-256 dedup · provenance_ledger.py (SQLite) · status tagging · routing   ║
╚══════════════════════════╤═══════════════════════════════════════════════════╝
                           │
              ┌────────────┴──────────────┐
              │                           │
              ▼                           ▼
╔═════════════════════════╗   ╔═══════════════════════════════════════════════╗
║  EXISTING PIPELINE      ║   ║  TAXONOMY GENERATION SUBSYSTEM               ║
║  (ZERO CHANGES)         ║   ╠═══════════════════════════════════════════════╣
║  build_index.py →       ║   ║  taxonomy_extractor.py (NEW)                 ║
║  NER → graph_store →    ║   ║  ───────────────────────────────────────────  ║
║  FAISS embed            ║   ║  Step 1: NER-driven concept extraction        ║
╚═════════════════════════╝   ║  Step 2: AMFI structured data parsing        ║
                              ║  Step 3: Regulatory concept normalization     ║
                              ║  Step 4: FIBO/SKOS standard anchoring        ║
                              ║  Step 5: taxonomy.json merge + versioning     ║
                              ║  Step 6: Graph node generation               ║
                              ║  Step 7: NER gazetteer hot-reload            ║
                              ╚════════════════════╤══════════════════════════╝
                                                   │
                                                   ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                RETRIEVAL LAYER (taxonomy_retrieval.py)                       ║
║  FAISS vector search (active-status filtered) + Neo4j graph traversal       ║
║  → Query uses the freshly updated taxonomy for entity matching              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## 3. Auto-Crawling Design

### 3.1 Channel A: `sebi_feed_ingester.py`

**What it does**: Polls SEBI's official RSS feed — the only truly automated channel with zero legal ambiguity because SEBI explicitly designed the feed for machine consumption.

#### Data Model

```python
@dataclass
class FeedEntry:
    circular_id: str        # Extracted from title: "SEBI/HO/IMD/2025/0123"
    title: str              # Full title as in RSS
    source_url: str         # URL to the circular landing page
    pdf_url: str            # Direct link to the PDF file
    published_date: datetime
    department: str         # Parsed: IMD | MRD | MIRSD | HO | CFD | SEBI
    entity_type: str        # Inferred from title: AMC | Broker | RA | Depository | All
    doc_type: str           # circular | master_circular | faq | order | press_release
    supersedes_title: Optional[str]  # Detected from title pattern — may be None
    confidence: str         # "high" | "medium" | "low" (supersession confidence)

@dataclass 
class DownloadResult:
    success: bool
    filepath: Optional[Path]
    sha256_hash: Optional[str]
    error_message: Optional[str]
    http_status: int

@dataclass
class IngestionReport:
    run_timestamp: datetime
    new_documents: int
    already_known: int
    modified_documents: int
    failed_downloads: int
    supersessions_detected: int
    entries: List[FeedEntry]
```

#### Key Functions

```python
def poll_sebi_rss(feed_url: str, timeout_sec: int = 30) -> List[FeedEntry]:
    """
    Fetch and parse the SEBI RSS feed XML.
    
    Implementation notes:
    - Use feedparser library (pure Python, no JS needed)
    - Respect robots.txt: check once on startup, cache result
    - User-agent: "AMC-Compliance-RAG/1.0 (internal AMC regulatory tool)"
    - Rate limit: maximum 1 request per 5 minutes (enforced via rate_limiter.py)
    - Parse each <item>:
        title → circular_id (regex: r"SEBI/[A-Z]{2,4}/[A-Z]+/\d{4}/\d+")
        title → department (keyword scan: "IMD", "MRD", "MIRSD", "HO", "CFD")
        title → entity_type (keyword scan: "Mutual Fund", "Stock Broker", "RA")
        title → doc_type ("Master Circular" / "FAQ" / "Order" / default: "circular")
        link → source_url
        enclosure or link → pdf_url
        pubDate → published_date
    - Returns empty list on HTTP error (does not raise — caller handles gracefully)
    """

def detect_supersession_from_title(title: str, 
                                    known_titles: List[str]) -> Tuple[Optional[str], str]:
    """
    Analyze circular title text for amendment/supersession language.
    
    Patterns to detect (in priority order):
    1. "Amendment to SEBI Circular on {X} dated {date}"
       → edge_type: AMENDED_BY, confidence: "high"
    2. "Addendum to SEBI Circular {ID}"  
       → edge_type: AMENDED_BY, confidence: "high"
    3. "Clarification on {subject} Circular"
       → edge_type: CLARIFIES, confidence: "medium"
    4. "Extension of timeline for implementation of {circular_ref}"
       → edge_type: EXTENDS_DEADLINE, confidence: "medium"
    5. "Deferment of timeline for {circular_ref}"
       → edge_type: DEFERS, confidence: "medium"
    6. "Modification in {framework/provisions}"
       → edge_type: MODIFIES, confidence: "low"
    
    Returns: (superseded_title_or_None, confidence_level)
    
    Matching strategy:
    - Extract date from "dated {DD} {Month} {YYYY}" pattern
    - Extract circular ID from "SEBI/..." pattern
    - If ID match found in known_titles: high confidence
    - If subject keyword match found: medium confidence
    - If neither: None (no supersession detected)
    """

def download_circular_pdf(pdf_url: str, 
                           dest_dir: Path,
                           existing_hashes: Set[str]) -> DownloadResult:
    """
    Download PDF if not already known (hash-checked).
    
    Steps:
    1. HEAD request to get Content-Length + Last-Modified (avoid full download if known)
    2. Compute expected filename from URL (sanitize special chars)
    3. If filename in processed_ledger → compute hash of existing file → compare
       - If hash matches: return DownloadResult(success=True, status="already_known")
       - If hash differs: re-download (content changed silently)
    4. GET request → stream to temp file → compute SHA-256 while streaming
    5. Move temp file to dest_dir/filename on success
    6. Return DownloadResult with hash
    
    Error handling:
    - HTTP 404: mark as "source_moved" — alert admin, do not crash
    - HTTP 429/503: exponential backoff (1s, 2s, 4s) max 3 retries
    - SSL/timeout: log warning, skip document, include in report
    """

def run_daily_sebi_poll() -> IngestionReport:
    """
    Full orchestrator for one polling cycle.
    Called by pipeline_scheduler.py on schedule.
    
    Flow:
    1. Load known circular IDs from provenance_ledger (SQLite lookup)
    2. Poll RSS feed → get FeedEntry list
    3. For each new entry:
       a. download_circular_pdf() → DownloadResult
       b. detect_supersession_from_title() → supersedes_title
       c. Build IngestRequest (channel="sebi_rss", status="active")
       d. Call ingestion_gateway.process_ingest(req)
    4. Return IngestionReport
    5. Log report to logs/sebi_poll_log.jsonl
    """
```

#### Rate Limiting & Compliance
```
- Max 1 RSS poll per 5 minutes (enforced via existing rate_limiter.py)
- Max 3 PDF downloads per minute (stagger downloads)
- robots.txt checked once on startup; result cached for 24 hours
- User-agent string: "AMC-Compliance-RAG/1.0 (internal regulatory intelligence tool)"
- SEBI permission request letter to be filed (2–4 week process) before bulk historical download
```

---

### 3.2 Channel B: `amfi_portal_adapter.py`

**What it does**: Ingests AMFI's public data channels — NAV, SID/SAI, AUM reports. These are SEBI-mandated public disclosures with zero legal ambiguity.

#### Data Sources and Fetch Strategy

```
Source                              URL                                     Frequency
─────────────────────────────────────────────────────────────────────────────────────
NAV (all schemes, current)          portal.amfiindia.com/spages/NAVAll.txt  Daily
NAV history (per scheme)            api.mfapi.in/mf/{scheme_code}           Weekly
Monthly AUM report                  amfiindia.com (PDF, dated link)         Monthly
SID/SAI listing (all AMCs)         amfiindia.com/nav38-full.html           Weekly
Portfolio disclosure (monthly)      amfiindia.com/modules/PortfolioDisc...  Monthly
AMFI circulars to members          amfiindia.com/page/circulars-and-spo    Weekly
```

#### Key Functions

```python
def fetch_nav_all() -> Tuple[pd.DataFrame, bool]:
    """
    Fetch NAVAll.txt — entire industry NAV in one file.
    
    Format: pipe-separated, no header row, fixed columns:
    SchemeCode | ISIN | ISIN2 | SchemeName | NAV | Date
    
    Steps:
    1. Compute SHA-256 of last known file (from provenance_ledger)
    2. HEAD request → check Last-Modified header
    3. If Last-Modified <= last_ingest_time: skip (return False = no update)
    4. GET request → parse into DataFrame
    5. Hash new content → compare with last hash
    6. If changed: return (DataFrame, True) — caller routes to taxonomy extraction
    7. If unchanged: return (empty_df, False)
    
    The DataFrame has columns: scheme_code, isin, scheme_name, nav, date, amc_name
    (amc_name extracted by splitting scheme_name on known fund house prefixes)
    """

def fetch_scheme_history(scheme_code: str, 
                          days_back: int = 365) -> pd.DataFrame:
    """
    Fetch NAV history from mfapi.in for one scheme.
    
    Used for enriching existing scheme nodes in Neo4j with historical NAV series.
    Not called on every crawl cycle — only when a new scheme is first registered.
    """

def fetch_sid_sai_listing() -> List[SIDEntry]:
    """
    Parse AMFI's SID/SAI listing page.
    
    For each registered scheme:
    - scheme_name, amc_name, scheme_type, isin, sid_url, sai_url
    
    Check each SID against provenance_ledger.find_by_url():
    - New SID: download PDF → ingestion_gateway.process_ingest()
    - Known SID: hash check → if content changed → re-ingest
    """

def fetch_amfi_monthly_aum() -> DownloadResult:
    """
    Download AMFI's monthly AUM/flow report PDF.
    
    Link format: amfiindia.com/comback.aspx?article={YYYY}{MM}-MF-Monthly-Data
    Construct URL from current date, download, route to ingestion_gateway.
    """
```

---

### 3.3 Channel C: `amfi_member_portal.py`

**What it does**: Monitor a designated folder on disk where the AMC's compliance team saves PDFs received via their official AMFI member email channel. No scraping — just watching a folder that a human is already authorized to populate.

**Legal basis**: The AMC is a registered AMFI member and an authorized recipient of every circular distributed through member channels. Saving a received email attachment = archiving what was sent to you.

```python
class MemberPortalWatcher:
    """
    Watches a configured folder (MEMBER_PORTAL_INBOX in config.py).
    Uses Python watchdog library for OS-level file events.
    
    On new PDF file detected:
    1. Wait 2 seconds (ensure write is complete)
    2. Validate it's a PDF (magic bytes check)
    3. Build IngestRequest:
       - acquisition_channel = "amfi_member_portal"
       - authorized_by = "member_portal_daemon"
       - status = "active"
    4. Call ingestion_gateway.process_ingest(req)
    5. Log event to logs/member_portal_log.jsonl
    """
    
    def __init__(self, watch_path: Path):
        self.watch_path = watch_path
        self._observer = None
    
    def start(self) -> None:
        """Start watchdog observer in background thread."""
    
    def stop(self) -> None:
        """Stop watchdog observer gracefully."""
    
    def get_status(self) -> dict:
        """Return watcher status for admin panel display."""

def create_member_portal_watcher(inbox_path: Path) -> MemberPortalWatcher:
    """
    Factory: creates and validates the inbox path.
    Called from pipeline_scheduler.py at startup.
    """
```

---

### 3.4 Channel D: Admin Authorized Ingest Tab (in `admin_view.py`)

**What it does**: Extends the existing Admin Panel with a new "📥 Authorized Ingest" tab. A compliance officer can manually ingest a document by URL or file upload — making it a human-authorized action that is legally equivalent to downloading a document in a browser.

#### UI Design

```
Tab: "📥 Authorized Ingest"
────────────────────────────────────────────────────────────────
  Ingest Method:  ○ URL   ○ File Upload

  If URL:
    Source URL:     [https://sebi.gov.in/legal/circulars/...]
    [Fetch & Preview]  → shows PDF title + first 200 chars

  If Upload:
    Drop PDF here:  [Browse Files]

  Document Metadata:
    Type:           [Circular ▼] [Master Circular ▼] [FAQ ▼]
    Department:     [IMD ▼] [MRD ▼] [MIRSD ▼] [HO ▼] [CFD ▼]
    Applies To:     [AMC ☑] [Broker ☐] [RA ☐] [All ☐]
    Status:         [Active ▼]
    Supersedes:     [Search existing circulars...] (optional)
    Notes:          [Free text for compliance officer]

  Authorized By:    sarah_compliance  (auto-populated from RBAC session)

  [Ingest Document]

  ─── After Submission ───
  ✅ Document ingested: SHA-256 abc123...
  📋 Provenance ID: uuid-v4
  📦 Indexing queued — estimated 45 seconds
  🔗 View in Provenance Ledger
────────────────────────────────────────────────────────────────

  Proposed Supersession Review Queue:
  ┌──────────────────────────────────────────────────────────┐
  │ NEW: "Addendum to SEBI Circular on Borrowing by MFs.pdf" │
  │ Proposed AMENDED_BY → "Borrowing by Mutual Funds.pdf"   │
  │ Confidence: Medium (auto-detected from title)            │
  │ [Confirm ✅] [Reject ❌] [Edit Mapping 🖊]              │
  └──────────────────────────────────────────────────────────┘
```

---

### 3.5 Ingestion Gateway: `ingestion_gateway.py`

Single entry point for **all** four channels above. No document enters `build_index.py` without going through here.

```python
@dataclass
class IngestRequest:
    filepath: Path
    acquisition_channel: str   # "sebi_rss" | "amfi_portal" | "amfi_member_portal" | "admin_authorized"
    source_url: str
    doc_type: str              # "circular" | "master_circular" | "faq" | "nav_data" | "sid" | "aum_report"
    department: str            # "IMD" | "MRD" | "MIRSD" | "HO" | "CFD" | "AMFI" | ""
    entity_type: str           # "AMC" | "Broker" | "RA" | "All" | ""
    status: str = "active"
    authorized_by: str = "system"
    supersedes: Optional[str] = None
    namespace: str = "shared"  # "shared" | "{amc_name}" for tenant isolation

@dataclass
class IngestResult:
    accepted: bool
    reason: str                # "new_document" | "already_indexed" | "content_modified" | "validation_failed"
    sha256_hash: str
    provenance_id: str
    destination_path: Optional[Path]
    taxonomy_trigger: bool     # Whether this ingest should trigger taxonomy extraction

def process_ingest(req: IngestRequest) -> IngestResult:
    """
    Steps:
    1. Validate: check filepath exists, is valid PDF/CSV/XLSX
    2. Compute SHA-256 hash of file content
    3. Dedup check via provenance_ledger.find_by_hash(hash):
       - MATCH (same hash): return already_indexed — do not re-index
       - MATCH (same filename, different hash): content_modified → re-index
       - NO MATCH: new_document → proceed
    4. Determine namespace path: data/AMC/shared/{doc_type}/ or data/AMC/{namespace}/
    5. Copy file to destination path
    6. Write ProvenanceRecord to SQLite:
       {provenance_id, filename, sha256_hash, acquisition_channel, source_url,
        doc_type, department, entity_type, status, supersedes,
        ingest_timestamp, authorized_by}
    7. If supersedes is set:
       - Update old record: status="superseded", superseded_by=new_filename
       - Queue graph lifecycle edge creation (async, via regulatory_lifecycle_enricher)
    8. Set taxonomy_trigger = True if doc_type in ("circular", "master_circular", "sid")
    9. Return IngestResult
    """
```

### 3.6 Provenance Ledger: `provenance_ledger.py` (SQLite)

```python
# SQLite schema — data/provenance.db
CREATE TABLE provenance (
    provenance_id       TEXT PRIMARY KEY,
    filename            TEXT NOT NULL UNIQUE,
    sha256_hash         TEXT NOT NULL,
    acquisition_channel TEXT NOT NULL,   -- sebi_rss | amfi_portal | amfi_member_portal | admin_authorized
    source_url          TEXT DEFAULT '',
    doc_type            TEXT DEFAULT '',  -- circular | master_circular | faq | nav_data | sid | aum_report
    department          TEXT DEFAULT '',  -- IMD | MRD | MIRSD | HO | CFD | AMFI
    entity_type         TEXT DEFAULT '',  -- AMC | Broker | RA | All
    status              TEXT DEFAULT 'active',  -- active | superseded | withdrawn | modified
    supersedes          TEXT DEFAULT NULL,       -- filename of doc this supersedes
    superseded_by       TEXT DEFAULT NULL,       -- filename of doc that superseded this
    namespace           TEXT DEFAULT 'shared',
    ingest_timestamp    TEXT NOT NULL,
    authorized_by       TEXT NOT NULL,
    notes               TEXT DEFAULT '',
    drift_detected      INTEGER DEFAULT 0,
    graph_node_count    INTEGER DEFAULT 0,
    taxonomy_extracted  INTEGER DEFAULT 0        -- has taxonomy extractor processed this?
);

CREATE INDEX idx_status     ON provenance(status);
CREATE INDEX idx_hash       ON provenance(sha256_hash);
CREATE INDEX idx_dept       ON provenance(department);
CREATE INDEX idx_entity     ON provenance(entity_type);
CREATE INDEX idx_doc_type   ON provenance(doc_type);
CREATE INDEX idx_namespace  ON provenance(namespace);
```

**Key functions**:
```python
def get_active_filenames() -> Set[str]          # Used by taxonomy_retrieval.py every 5min
def find_by_hash(sha256: str) -> Optional[ProvenanceRecord]
def find_by_filename(filename: str) -> Optional[ProvenanceRecord]
def update_status(filename: str, new_status: str, superseded_by: str = None)
def get_unprocessed_for_taxonomy() -> List[ProvenanceRecord]  # where taxonomy_extracted=0
def mark_taxonomy_extracted(filename: str)
def generate_compliance_report() -> str         # SEBI Reg 16C audit export
def backfill_existing_documents() -> int        # One-time migration for existing data/AMC/
```

---

## 4. Taxonomy Generation Design

> [!IMPORTANT]
> This is the core of our IP differentiation. The taxonomy stops being a static file maintained by hand and becomes a **living knowledge structure** that grows with every document ingested.

### 4.1 What the Taxonomy Currently Is

The existing `taxonomy.json` has 5 flat dimension lists:
```json
{
  "fund_houses": ["HDFC Mutual Fund", "SBI Mutual Fund", ...],
  "scheme_names": ["HDFC Liquid Fund", ...],
  "categories": ["Equity Schemes", "Debt Schemes", ...],
  "sub_categories": ["Large Cap Fund", "Mid Cap Fund", ...],
  "benchmarks": ["Nifty 50", "Sensex", ...]
}
```

### 4.2 What the Taxonomy Will Become

A **multi-dimensional, versioned, FIBO-anchored knowledge structure** stored in two places:
- `taxonomy.json` (extended) — for fast in-process NER gazetteer loading
- Neo4j graph nodes — for semantic relationship traversal during retrieval

**New taxonomy dimensions added by auto-extraction**:
```json
{
  "fund_houses":           [...],           // existing — now auto-updated from AMFI
  "scheme_names":          [...],           // existing — now auto-updated from AMFI
  "categories":            [...],           // existing — now auto-updated from SEBI circulars
  "sub_categories":        [...],           // existing — now auto-updated from SEBI circulars
  "benchmarks":            [...],           // existing — now auto-updated from SID documents

  "regulatory_obligations": [...],          // NEW: compliance requirements from SEBI circulars
  "sebi_circular_ids":      [...],          // NEW: canonical circular IDs (SEBI/HO/IMD/...)
  "applicable_entity_types":  [...],        // NEW: AMC | Broker | RA | Depository | All
  "departments":            [...],          // NEW: IMD | MRD | MIRSD | HO | CFD
  "compliance_concepts":    [...],          // NEW: KYC, AML, CSCRF, SIF, PMS, ESG...
  "fund_managers":          [...],          // NEW: extracted from SID documents
  "aum_tiers":              [...],          // NEW: B30 cities, top 30 cities, women investors
  "risk_categories":        [...],          // NEW: Very High Risk, High Risk, Moderate Risk...
  "asset_classes":          [...],          // NEW: Gold ETF, InvIT, REIT, International FoF...
  "regulatory_regimes":     [...],          // NEW: Pre-2017 SEBI, Post-2017 SEBI...
  "fibo_aligned_concepts":  {...}           // NEW: nodes with FIBO concept ID mapping
}
```

---

### 4.3 Taxonomy Extractor: `taxonomy_extractor.py` (NEW)

This is the core new module. It runs **after** every successful ingestion and extracts taxonomy concepts from the new document.

#### Architecture: 7-Step Extraction Pipeline

```
New Document (PDF text extracted by build_index.py)
         │
         ▼
Step 1: Source-type routing
         │
    ┌────┴─────────────────────────────────┐
    │                                      │
    ▼                                      ▼
AMFI structured data              SEBI circular / SID / master circular
(NAVAll.txt, SID listing)         (unstructured regulatory text)
    │                                      │
    ▼                                      ▼
Step 2A: Tabular extraction        Step 2B: NER-driven extraction
         │                                 │
         └──────────────┬─────────────────┘
                        │
                        ▼
               Step 3: Concept normalization
               (dedup, case normalize, remove noise)
                        │
                        ▼
               Step 4: FIBO standard anchoring
               (map to known FIBO concept IDs)
                        │
                        ▼
               Step 5: taxonomy.json merge
               (add_to_dimension() with dedup)
                        │
                        ▼
               Step 6: Neo4j graph node generation
               (MERGE TaxonomyConcept nodes + CLASSIFIED_AS edges)
                        │
                        ▼
               Step 7: NER gazetteer hot-reload
               (invalidate _gazetteer_cache in ner_pipeline.py)
```

#### Step 1: Source-Type Routing

```python
def extract_taxonomy_from_document(filepath: Path, 
                                    provenance: ProvenanceRecord) -> TaxonomyDelta:
    """
    Route to correct extraction strategy based on document type and acquisition channel.
    
    Routing table:
    ┌───────────────────────────────────────────────────────────────┐
    │ doc_type          │ channel          │ extraction_strategy    │
    ├───────────────────┼──────────────────┼───────────────────────┤
    │ nav_data          │ amfi_portal      │ tabular_nav_extract()  │
    │ sid / sai         │ amfi_portal      │ tabular_sid_extract()  │
    │ circular          │ sebi_rss         │ ner_circular_extract() │
    │ master_circular   │ any              │ ner_circular_extract() │
    │ faq               │ sebi_rss         │ ner_faq_extract()      │
    │ aum_report        │ amfi_portal      │ tabular_aum_extract()  │
    └───────────────────┴──────────────────┴───────────────────────┘
    """
```

#### Step 2A: Tabular Extraction (AMFI Data)

```python
def tabular_nav_extract(nav_df: pd.DataFrame) -> TaxonomyDelta:
    """
    Extract taxonomy concepts from NAVAll.txt DataFrame.
    
    Extracts:
    ┌─────────────────────────────────────────────────────────────────┐
    │ Source Column    │ → Taxonomy Dimension   │ Example Value       │
    ├──────────────────┼────────────────────────┼─────────────────────┤
    │ amc_name         │ → fund_houses          │ "HDFC Mutual Fund"  │
    │ scheme_name      │ → scheme_names         │ "HDFC Liquid Fund"  │
    │ scheme_type      │ → categories           │ "Debt Schemes"      │
    │ sub_type         │ → sub_categories       │ "Liquid Fund"       │
    │ isin             │ → (graph node only)    │ "INF179K01VH5"      │
    └──────────────────┴────────────────────────┴─────────────────────┘
    
    Algorithm:
    1. Group schemes by amc_name → extract unique fund houses
    2. Extract unique scheme_names (full name as registered)
    3. Parse scheme_type from scheme_name prefix patterns:
       - "HDFC Large Cap Fund" → scheme_type = "Equity"
       - "HDFC Liquid Fund" → scheme_type = "Debt"
       (uses _SCHEME_TYPE_PATTERNS dict — regex patterns mapped to categories)
    4. Return TaxonomyDelta with new terms not already in taxonomy.json
    """

def tabular_sid_extract(sid_pdf_text: str, 
                         scheme_name: str) -> TaxonomyDelta:
    """
    Extract from SID (Scheme Information Document) PDF.
    
    Key sections to parse:
    - "Type of Scheme: {category} — {sub_category}" → categories, sub_categories
    - "Benchmark: {index name}" → benchmarks
    - "Fund Manager(s): {name(s)}" → fund_managers (NEW dimension)
    - "Risk-o-meter: {level}" → risk_categories (NEW dimension)
    - "Plans/Options: Direct/Regular" → (graph metadata only)
    - "Exit Load: {conditions}" → (graph metadata only)
    - "Total Expense Ratio (TER): {value}%" → (graph metadata only)
    
    Uses regex + section header detection (not LLM — fast and reliable for SID format)
    """
```

#### Step 2B: NER-Driven Extraction (SEBI Circulars)

```python
def ner_circular_extract(circular_text: str, 
                          circular_id: str,
                          department: str) -> TaxonomyDelta:
    """
    Extract taxonomy concepts from SEBI circular text using NER + rule patterns.
    
    Three sub-strategies:
    
    Sub-strategy 1 — Regulatory obligation extraction:
        Scan for compliance requirement language:
        - "shall" / "shall not" / "must" / "are required to"
        → Extract subject + obligation phrase
        → Add to regulatory_obligations dimension
        Example: "AMCs shall ensure adequate liquidity..."
                 → concept: "AMC liquidity requirement"
    
    Sub-strategy 2 — Compliance concept extraction (keyword set):
        COMPLIANCE_KEYWORDS = {
            "KYC", "AML", "CFT", "CSCRF", "PMS", "AIF", "SIF",
            "InvIT", "REIT", "ESG", "BRSR", "PMLA", "FPI",
            "NRI", "ISIN", "NAV", "TER", "NFO", "SIP", "SWP",
            "FoF", "ETF", "ELSS", "QSB", "PaRRVA", "DigiLocker",
            "MITRA", "iSPOT", "EoD", "SWAGAT-FI"
        }
        → Any keyword found in text → add to compliance_concepts dimension
        → Also create a TermDefinition graph node if definition found nearby
    
    Sub-strategy 3 — Fund category extraction from circular text:
        SEBI circulars often mention specific fund types by name.
        Look for patterns:
        - "Mutual Fund schemes investing in {X}"
        - "Category: {X} / Sub-category: {X}"
        - "Specialized Investment Funds (SIFs)"
        → Extract as sub_category or asset_class entries
    
    Returns TaxonomyDelta with:
    - new_regulatory_obligations: List[str]
    - new_compliance_concepts: List[str]  
    - new_categories: List[str]
    - new_sub_categories: List[str]
    - new_asset_classes: List[str]
    - circular_metadata: dict  # For graph node creation
    """
```

#### Step 3: Concept Normalization

```python
def normalize_concept(raw_text: str) -> Optional[str]:
    """
    Clean and normalize extracted concept terms before adding to taxonomy.
    
    Rules applied in order:
    1. Strip leading/trailing whitespace and punctuation
    2. Collapse internal whitespace (double spaces, tabs, newlines)
    3. Remove boilerplate suffixes: " Regulations, 20XX", " dated ...", " as amended"
    4. Title-case for fund house names and scheme names
    5. UPPERCASE for regulatory abbreviations (SEBI, AMFI, AML, KYC...)
    6. Length filter: reject if < 3 chars or > 120 chars
    7. Noise filter: reject if matches any noise pattern:
       NOISE_PATTERNS = [r"^\d+$", r"^[.,;:]+$", r"^the\s", r"^a\s", r"^an\s"]
    8. Dedup check against existing taxonomy entries (case-insensitive)
    
    Returns normalized string or None if concept should be rejected
    """

@dataclass
class TaxonomyDelta:
    """
    What this extraction run found that isn't already in taxonomy.json.
    Only net-new concepts are stored here.
    """
    source_filename: str
    extraction_timestamp: datetime
    new_terms: Dict[str, List[str]]   # dimension → list of new terms
    graph_nodes: List[dict]            # Neo4j MERGE statements to create
    fibo_mappings: Dict[str, str]     # raw_term → FIBO concept ID (if matched)
    extraction_confidence: str         # "high" | "medium" | "low"
    total_new_concepts: int
```

#### Step 4: FIBO Standard Anchoring

```python
# FIBO is the Financial Industry Business Ontology — W3C OWL-based standard
# We will NOT download or install the full FIBO ontology library
# Instead: maintain a curated mapping table for the concepts we care about

FIBO_CONCEPT_MAPPINGS = {
    # FIBO concept ID → our taxonomy term(s)
    "fibo-fnd-acc-aeq/EquityInstrument": ["Equity Schemes", "Large Cap Fund", "ELSS"],
    "fibo-fnd-acc-4lt/DebtInstrument": ["Debt Schemes", "Liquid Fund", "Corporate Bond"],
    "fibo-be-le-fbo/FormalOrganization": ["HDFC Mutual Fund", "SBI Mutual Fund", ...],
    "fibo-fnd-rel-rel/isGovernedBy": ["GOVERNED_BY_SEBI_CIRCULAR"],
    "fibo-fbc-fi-fi/FinancialInstrument": ["Scheme", "ETF", "InvIT", "REIT"],
    ...
}

# Reverse lookup: our term → FIBO concept ID
_REVERSE_FIBO_MAP: Dict[str, str] = {}  # built once at startup from above

def map_to_fibo(concept_text: str) -> Optional[str]:
    """
    Check if a newly extracted concept has a known FIBO equivalent.
    Returns FIBO concept ID string or None.
    Uses exact match + fuzzy match (difflib.get_close_matches threshold 0.85).
    """

def build_fibo_mapping_report() -> dict:
    """
    Generate coverage report: what % of our taxonomy is FIBO-anchored?
    Used in the compliance/IP showcase report.
    """
```

#### Step 5: `taxonomy.json` Merge and Versioning

```python
def merge_taxonomy_delta(delta: TaxonomyDelta) -> MergeResult:
    """
    Merge new concepts from TaxonomyDelta into taxonomy.json.
    
    Algorithm:
    1. Load current taxonomy.json as Dict[str, Set[str]]
    2. For each dimension in delta.new_terms:
       a. Current set: taxonomy[dimension]
       b. Incoming set: set(delta.new_terms[dimension])
       c. Net new: incoming - current (set subtraction)
       d. Add net_new to taxonomy[dimension]
    3. Apply FIBO mappings: for each new term that has a fibo_id, 
       add to "fibo_aligned_concepts" dict: {term: fibo_id}
    4. Save taxonomy_versions/{timestamp}_taxonomy.json (versioned backup)
    5. Write updated taxonomy.json (atomic write via temp file + rename)
    6. Return MergeResult with counts and version ID
    
    Versioning:
    - Keep last 30 versions in taxonomy_versions/ folder
    - Each version named: 20260806_143022_taxonomy.json
    - Rollback function: restore_taxonomy_version(version_id)
    """

@dataclass
class MergeResult:
    version_id: str
    concepts_added: int
    concepts_by_dimension: Dict[str, int]  # how many added to each dimension
    fibo_anchored_count: int
    taxonomy_total_concepts: int           # total after merge
```

#### Step 6: Neo4j Graph Node Generation

```python
def generate_graph_nodes(delta: TaxonomyDelta, 
                          provenance: ProvenanceRecord) -> int:
    """
    Create Neo4j nodes and edges from extracted taxonomy concepts.
    
    Node types created:
    ┌──────────────────────────────────────────────────────────────────────┐
    │ Taxonomy Concept    │ Neo4j Node Label     │ Key Properties          │
    ├─────────────────────┼──────────────────────┼─────────────────────────┤
    │ SEBI circular       │ RegulatoryDocument   │ filename, status, dept  │
    │ Compliance concept  │ ComplianceConcept    │ term, fibo_id, source   │
    │ Fund category       │ SchemeCategory       │ name, type, sebi_code   │
    │ Fund house (new)    │ Entity (FUND_HOUSE)  │ text, label, source     │
    │ Reg obligation      │ Obligation           │ text, applies_to, type  │
    └─────────────────────┴──────────────────────┴─────────────────────────┘
    
    Edge types created:
    ┌──────────────────────────────────────────────────────────────────────┐
    │ Edge                       │ Meaning                                 │
    ├────────────────────────────┼─────────────────────────────────────────┤
    │ (RegulatoryDocument)-[:APPLIES_TO]->(EntityType)                     │
    │ (RegulatoryDocument)-[:INTRODUCES]->(:SchemeCategory)               │
    │ (RegulatoryDocument)-[:MANDATES]->(:Obligation)                     │
    │ (ComplianceConcept)-[:IS_FIBO_EQUIVALENT]->(:FIBOConcept)           │
    │ (SchemeCategory)-[:CLASSIFIED_AS]->(:Category)                      │
    └──────────────────────────────────────────────────────────────────────┘
    
    Uses graph_store.py MERGE pattern (no duplicates, idempotent).
    All MERGEs batched via UNWIND for efficiency.
    Returns: count of nodes created/updated
    """
```

#### Step 7: NER Gazetteer Hot-Reload

```python
def hot_reload_ner_gazetteer() -> None:
    """
    Invalidate the NER pipeline's in-memory taxonomy cache so the next
    request picks up the updated taxonomy.json automatically.
    
    This is critical: without this, new taxonomy concepts don't benefit
    NER entity matching until the next app restart.
    
    Implementation:
    1. Import ner_pipeline module
    2. Set ner_pipeline._gazetteer_cache = None  (invalidate cache)
    3. Set ner_pipeline._nlp = None  (force spaCy EntityRuler rebuild)
    4. Log: "[taxonomy] NER gazetteer invalidated — will reload on next request"
    
    The hot-reload happens in the same process, so next request to
    layer_a_rule_ner() will call _get_gazetteer() → load_taxonomy() →
    read the updated taxonomy.json → rebuild EntityRuler patterns.
    
    IMPORTANT: This does NOT require an app restart.
    """
```

---

### 4.4 Regulatory Lifecycle Enricher: `regulatory_lifecycle_enricher.py`

Focuses specifically on the regulatory lifecycle edges in Neo4j — separate from general taxonomy extraction.

```python
def upsert_regulatory_document(record: ProvenanceRecord) -> None:
    """
    Create/update RegulatoryDocument node in Neo4j.
    
    Cypher:
    MERGE (d:RegulatoryDocument {filename: $filename})
    SET d.status = $status,
        d.department = $department,
        d.entity_type = $entity_type,
        d.doc_type = $doc_type,
        d.acquisition_channel = $channel,
        d.sha256_hash = $hash,
        d.effective_from = $ingest_timestamp
    """

def detect_and_link_amendments(records: List[ProvenanceRecord]) -> List[ProposedEdge]:
    """
    For each new record where supersedes_title was detected:
    
    1. Find the matching RegulatoryDocument in Neo4j
    2. Create proposed edge:
       (new_doc)-[:SUPERSEDES {confidence: "medium", pending_confirmation: True}]->(old_doc)
    3. Do NOT mark old_doc as status="superseded" yet — wait for admin confirmation
    4. Return list of ProposedEdge for admin review queue
    
    Edge confidence levels:
    - "high": circular_id match found (SEBI/HO/IMD/2025/123 → exact match)
    - "medium": title keyword + date match (80% confidence)
    - "low": subject keyword match only (50% confidence)
    """

def confirm_supersession(proposed_edge_id: str, admin_user: str) -> None:
    """
    Admin has confirmed a proposed edge.
    1. Set edge: {confidence: "confirmed", pending_confirmation: False}
    2. Update old doc: status="superseded", superseded_date=now
    3. Update provenance_ledger: old doc status="superseded"
    4. Invalidate _active_sources_cache in taxonomy_retrieval.py
    5. Log confirmation to audit trail
    """

def reject_supersession(proposed_edge_id: str, reason: str) -> None:
    """Delete proposed edge. Log rejection."""
```

---

## 5. Pipeline Orchestrator: `pipeline_scheduler.py`

Ties everything together into a single schedulable pipeline.

```python
def run_production_pipeline(mode: str = "incremental") -> PipelineReport:
    """
    Full pipeline execution. Steps in order:
    
    ── ACQUISITION PHASE ──
    Step 1A: sebi_feed_ingester.run_daily_sebi_poll()
             → IngestionReport: new_documents, supersessions_detected
    
    Step 1B: amfi_portal_adapter.fetch_nav_all()
             → If changed: build IngestRequest → ingestion_gateway.process_ingest()
             amfi_portal_adapter.fetch_sid_sai_listing()
             → For each new/changed SID: ingestion_gateway.process_ingest()
    
    Step 1C: MemberPortalWatcher runs continuously — events already queued
    
    ── INGESTION GATEWAY PHASE ──
    Step 2: All acquired docs processed via ingestion_gateway.process_ingest()
            → writes to data/AMC/{namespace}/{doc_type}/
            → writes to provenance_ledger (SQLite)
    
    ── INDEXING PHASE ──  
    Step 3: If any new documents accepted:
            build_index.build(rebuild=False)   ← UNCHANGED EXISTING CODE
            (picks up new files from data/AMC/ folder, skips already-indexed)
    
    ── TAXONOMY GENERATION PHASE ──
    Step 4: Get unprocessed records: provenance_ledger.get_unprocessed_for_taxonomy()
            For each unprocessed record:
              delta = taxonomy_extractor.extract_taxonomy_from_document(filepath, record)
              merge_result = taxonomy_extractor.merge_taxonomy_delta(delta)
              graph_nodes = taxonomy_extractor.generate_graph_nodes(delta, record)
              provenance_ledger.mark_taxonomy_extracted(filename)
            After all extractions: taxonomy_extractor.hot_reload_ner_gazetteer()
    
    ── REGULATORY GRAPH ENRICHMENT PHASE ──
    Step 5: regulatory_lifecycle_enricher.upsert_regulatory_document() for new records
            regulatory_lifecycle_enricher.detect_and_link_amendments(new_records)
            → Returns ProposedEdge list → stored for admin review
    
    ── STALENESS CHECK PHASE ──
    Step 6: staleness_monitor.run_drift_check(sample_size=10)
            → SHA-256 re-check on 10 random documents with known source_url
            → Alert if any drift detected
    
    ── REPORTING PHASE ──
    Step 7: Generate PipelineReport
            Log to logs/pipeline_run_log.jsonl
    
    Returns: PipelineReport
    """
```

### Scheduling Strategy

```python
# In pipeline_scheduler.py — schedule configuration
SCHEDULE_CONFIG = {
    "sebi_rss_poll": {
        "frequency": "every 6 hours",
        "trigger": "cron(0 */6 * * *)",
        "max_runtime_sec": 300,
    },
    "amfi_nav_update": {
        "frequency": "daily at 8pm IST",
        "trigger": "cron(30 14 * * 1-5)",  # 14:30 UTC = 20:00 IST weekdays
        "max_runtime_sec": 120,
    },
    "sid_sai_check": {
        "frequency": "weekly on Monday",
        "trigger": "cron(0 3 * * 1)",      # 3am UTC Monday
        "max_runtime_sec": 600,
    },
    "staleness_check": {
        "frequency": "daily",
        "trigger": "cron(0 2 * * *)",
        "max_runtime_sec": 180,
    },
}
```

For the initial implementation, scheduling will be driven by **APScheduler** (Python-native, no external daemon required). The admin panel exposes a "Run Now" button for each pipeline phase.

---

## 6. Integration Points: How It All Connects

```
taxonomy_extractor.hot_reload_ner_gazetteer()
          │
          ▼
ner_pipeline._gazetteer_cache = None
          │
          ▼  (next request)
ner_pipeline._get_gazetteer() → taxonomy.load_taxonomy() → reads new taxonomy.json
          │
          ▼
layer_a_rule_ner() → EntityRuler now recognizes new fund houses, scheme names, concepts
          │
          ▼
graph_store.upsert_entities() → new entities get graph nodes
          │
          ▼
taxonomy_retrieval.retrieve_graph() → queries include new nodes in traversal
          │
          ▼
LLM answer grounded in up-to-date regulatory knowledge
```

---

## 7. New Files Summary

| File | Layer | Purpose |
|---|---|---|
| `sebi_feed_ingester.py` | Acquisition | SEBI RSS polling + PDF download |
| `amfi_portal_adapter.py` | Acquisition | AMFI NAV + SID/SAI + AUM reports |
| `amfi_member_portal.py` | Acquisition | AMC authorized inbox folder watcher |
| `ingestion_gateway.py` | Gateway | Unified entry + SHA-256 dedup + provenance write |
| `provenance_ledger.py` | Gateway | SQLite provenance store |
| `taxonomy_extractor.py` | **Taxonomy** | **Core: 7-step extraction + FIBO anchoring + graph node generation** |
| `regulatory_lifecycle_enricher.py` | Graph | Regulatory lifecycle edges (SUPERSEDES, AMENDED_BY) |
| `staleness_monitor.py` | Monitoring | SHA-256 drift detection |
| `pipeline_scheduler.py` | Orchestration | Full pipeline orchestrator |

## 8. Files Modified (Minimal)

| File | What Changes |
|---|---|
| `taxonomy.py` | Add version backup, extend dimensions, atomic write |
| `ner_pipeline.py` | Add `warmup_ner_models()` (already done) + cache invalidation hook |
| `graph_store.py` | Add `init_regulatory_schema()` for new node/edge types |
| `admin_view.py` | Add "Authorized Ingest" tab + proposed edge review queue |
| `build_index.py` | Write `processed_ledger_meta.json` companion |
| `config.py` | Add `SEBI_RSS_URL`, `AMFI_NAV_URL`, `MEMBER_PORTAL_INBOX`, `RETRIEVAL_ACTIVE_ONLY`, `CACHE_GRAPH_MODE` |

---

## 9. Taxonomy Versioning Design

```
streamlit_app/
├── taxonomy.json                    ← active (always the latest)
└── taxonomy_versions/
    ├── 20260806_143022_taxonomy.json
    ├── 20260807_083011_taxonomy.json
    └── ...  (keep last 30)
```

```python
def restore_taxonomy_version(version_id: str) -> None:
    """Rollback to a previous taxonomy version. Hot-reloads NER gazetteer after."""

def diff_taxonomy_versions(v1: str, v2: str) -> TaxonomyDiff:
    """Show what concepts were added/removed between two versions."""

def export_taxonomy_skos(output_path: Path) -> None:
    """
    Export current taxonomy in W3C SKOS format (RDF/XML or Turtle).
    Maps taxonomy dimensions to SKOS:ConceptScheme.
    Maps each term to SKOS:Concept with skos:prefLabel and skos:inScheme.
    Maps FIBO-anchored concepts to skos:exactMatch or skos:closeMatch.
    
    This is the IP artifact — a machine-readable, standards-compliant taxonomy
    that can be shared with other AMCs or submitted for regulatory review.
    """
```

---

## 10. Testing Strategy

| Test | What It Validates |
|---|---|
| `test_sebi_rss_poll()` | RSS feed parses correctly, rate limit enforced, supersession patterns detected |
| `test_ingestion_gateway_dedup()` | Same PDF twice → second rejected, FAISS unchanged |
| `test_taxonomy_nav_extract()` | NAVAll.txt → new fund houses + scheme names in taxonomy.json |
| `test_taxonomy_circular_extract()` | SEBI circular → compliance concepts + regulatory obligations extracted |
| `test_ner_hot_reload()` | New term added to taxonomy → recognized by NER on next request without restart |
| `test_supersession_detection()` | "Addendum to Borrowing Circular" → AMENDED_BY edge, confidence=medium |
| `test_admin_confirm_supersession()` | Admin confirms → old doc status=superseded, dropped from retrieval |
| `test_taxonomy_skos_export()` | Valid SKOS RDF output, all active taxonomy terms present |
| `test_fibo_mapping_coverage()` | Report: % of taxonomy terms with FIBO concept ID |
| `test_full_pipeline_e2e()` | Mock RSS entry → pipeline → query → answer grounded in new circular |
