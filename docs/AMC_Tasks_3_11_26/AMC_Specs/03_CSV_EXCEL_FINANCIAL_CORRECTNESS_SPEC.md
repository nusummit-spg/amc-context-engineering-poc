# 03 — CSV / Excel Financial Correctness: Implementation Specification

## 1. Primary objective

Make all CSV/XLSX-dependent questions about AMC/schemes, NAV, AAUM, rankings, counts and distributions return **exact, as-of-defined, reproducible, source-linked results**, or an explicit abstention. Re-ingestion of extra chunks is **not** a substitute for exact execution.

### Governing requirements
- Use **one canonical structured dataset importer**, not a collection of ad-hoc FAISS index scripts, graph embeddings and DataFrame singleton imports.
- Preserve exact imported values and source-location evidence; semantic search is secondary for discovery and explanations.
- No fabricated/fixed confidence, row counts, completeness, trace or citation.
- No numeric answer from LLM alone; no falling back to LLM on SQL/structured executor error.
- Preserve PDF/text quality by maintaining a versioned compatibility route and separate control-test suite.

## 2. Dataset inventory / observed source fields

The committed `chunks/manifest.json` declares **16,245 rows, 22 chunks (21 × 750 + 495)**. Columns in the viewed CSV chunk:

| Source field | Proposed canonical type | Interpretation / control |
|---|---|---|
| `Scheme_Code` | TEXT | Preserve leading zeros and source identity; do not assume it uniquely names a scheme across all times without steward approval |
| `Scheme_Name` | TEXT | Display name; not a safe sole grouping key |
| `AMC` | TEXT | Canonical AMC ID derived via alias table, retains original display |
| `Scheme_Type` | ENUM / TEXT | Normalize values with alias dictionary, preserve unknowns |
| `Scheme_Category` | ENUM / TEXT | Controlled taxonomy + source raw category and version |
| `Scheme_NAV_Name` | TEXT | Option/plan display string; derive plan/option only using reviewed mapping |
| `Scheme_Min_Amt` | DECIMAL(18,2) nullable | Source meaning/currency to verify |
| `NAV` | DECIMAL(20,6) nullable | Exact NAV per unit; no cross-date ranking without temporal policy |
| `Latest_NAV_Date` | DATE nullable | Date associated with NAV observation |
| `Average_AUM_Cr` | DECIMAL(24,6) nullable | AAUM in INR crore at **source record grain**; additive semantics require steward signoff |
| `AAUM_Quarter` | canonical quarter ENUM/date interval | Independent from NAV as-of date |
| `ISIN_Div_Payout/Growth` | TEXT nullable | Preserve punctuation/case and raw source; normalize missing `-` |
| `ISIN_Div_Reinvestment` | TEXT nullable | One of potentially several identifiers |
| `ISIN_Div_Payout/Growth/Div_Reinvestment` | TEXT nullable | May contain concatenated identifiers; never split by length without a validated parser |
| `Launch_Date` | DATE nullable | Needs source convention verification |
| `Closure_Date` | DATE nullable | Sample rows show same value as launch; **do not infer active status from presence alone** |

The manifest is a **declaration**, not proof of row-level completeness in the serving stores. Run sum of actual rows, header checks, unique row IDs, row checksums and business-key profiling. Also verify no mixed `AAUM_Quarter` or `Latest_NAV_Date` values get silently combined.

## 3. Grain, identity and metric dictionary

### Separate identifiers
- `source_row_id = sha256(dataset_version || logical_original_source_path || original_physical_row_number || raw_row_sha256)` as immutable provenance anchor. Path and row number refer to the **original unchunked logical source**, not the chunk file; row number is 1-based data row relative to that original source.
- `source_business_key`: source `Scheme_Code` + source plan/option identifier(s) + `NAV_date` or AAUM quarter **where appropriate**. Use nullable composite with collision handling, not unconditional uniqueness assumptions.
- `amc_id`: source-independent canonical ID resolved from a versioned aliases table; preserve original AMC text.
- `scheme_id`: steward-approved canonical scheme grouping; prefer AMC+source scheme identity mapping rather than `Scheme_Name` only.
- `plan_option_id`: distinguish Direct vs Regular, Growth vs IDCW and other variants, using reviewed rules.
- `observation_id`: unique fact row with metric, observation period, source and value.

### Metric specification registry (signed by business owner)
Each metric defines `metric_id`, `source_columns`, `unit`, `grain`, `valid_aggregation`, `as_of/period_rule`, `null_policy`, `duplicate_policy`, `permitted_filters`, and a known-answer fixture.

| Metric | Default safe treatment | Needs steward decision |
|---|---|---|
| `nav_per_unit` | Exact lookup by plan/option/ISIN + date; no SUM | Whether highest-NAV comparisons across differing dates are allowed |
| `aaum_cr` | Exact source AAUM observation; use SUM only if rows are demonstrably disjoint at approved grain | Plan/option overlap and quarter definition |
| `distinct_scheme_count` | COUNT DISTINCT canonical scheme ID, after entity resolution | Scheme status, cross-AMC mergers/renames |
| `plan_variant_count` | COUNT DISTINCT canonical plan_option ID | Multiple ISIN or option rows versus plan count |
| `amc_aum_cr` | Data-steward-approved aggregation of `aaum_cr` within one quarter | Can rows be summed without duplication? |
| `avg_scheme_aum_cr` | Explicit mean over approved denominator | Mean of plans vs schemes; weighted or unweighted |
| `market_share_pct` | Numerator/denominator from same unit, grain, period and population | Coverage and whether source is an industry-complete dataset |

**Critical rule:** Never label `SUM(Average_AUM_Cr)` as definitive industry AUM without a verified additivity rule and scope of the dataset. Label results as *dataset-derived*, not necessarily industry-wide, until coverage has been independently established.

## 4. Proposed normalized schema (SQLite/DuckDB draft; adapt per engine)

```sql
CREATE TABLE dataset_versions (
  dataset_version TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  source_document_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  expected_rows INTEGER NOT NULL,
  parsed_rows INTEGER NOT NULL,
  valid_rows INTEGER NOT NULL,
  rejected_rows INTEGER NOT NULL,
  published_at TEXT,
  status TEXT NOT NULL CHECK(status IN
    ('RECEIVED','STAGED','VALIDATED','RECONCILED','ACTIVE','RETIRED','QUARANTINED','FAILED'))
);
CREATE TABLE source_rows (
  source_row_id TEXT PRIMARY KEY,
  dataset_version TEXT NOT NULL REFERENCES dataset_versions(dataset_version),
  source_filename TEXT NOT NULL,
  physical_row_number INTEGER NOT NULL,
  raw_row_sha256 TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  UNIQUE(dataset_version, source_filename, physical_row_number)
);
CREATE TABLE nav_observations (
  observation_id TEXT PRIMARY KEY,
  dataset_version TEXT NOT NULL REFERENCES dataset_versions(dataset_version),
  source_row_id TEXT NOT NULL REFERENCES source_rows(source_row_id),
  tenant_id TEXT NOT NULL,
  amc_id TEXT,
  scheme_id TEXT,
  plan_option_id TEXT,
  source_scheme_code TEXT,
  nav_date TEXT,
  nav_decimal TEXT,
  nav_unit TEXT NOT NULL DEFAULT 'INR_PER_UNIT'
);
CREATE TABLE aaum_observations (
  observation_id TEXT PRIMARY KEY,
  dataset_version TEXT NOT NULL REFERENCES dataset_versions(dataset_version),
  source_row_id TEXT NOT NULL REFERENCES source_rows(source_row_id),
  tenant_id TEXT NOT NULL,
  amc_id TEXT,
  scheme_id TEXT,
  plan_option_id TEXT,
  aaum_quarter TEXT,
  aaum_cr_decimal TEXT,
  valid_for_aggregation INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE active_dataset_pointers (
  tenant_id TEXT NOT NULL,
  domain TEXT NOT NULL,
  dataset_version TEXT NOT NULL REFERENCES dataset_versions(dataset_version),
  generation INTEGER NOT NULL,
  PRIMARY KEY(tenant_id, domain)
);
```

The TEXT decimal is illustrative when SQLite Decimal fidelity is not implemented. Production should use exact scaled integers or a decimal-aware engine/adapter; conversion via Python `Decimal` must be round-trip tested. Do not run SQL `SUM()` on TEXT decimal values directly. For analytical use, implement a validated scaled-integer column (`aaum_micro_cr`) or engine-specific DECIMAL type. Reject overflow and unit mismatch.

## 5. Ingestion algorithm (two-track ingestion)

```
A. hash/source-register -> parse CSV/XLSX (streamed, no truncate)
B. validate schema, names, types, units, null/date conventions, row counts
C. assign immutable row anchors; quarantine invalid rows with reason
D. normalize AMC / scheme / plan / option / period in canonical tables
E. calculate summary and reconciliation report; hard fail on missing rows
F. stage typed source snapshot (authoritative for finance)
G. optionally generate search summaries from staged rows (for discovery)
H. optionally materialize graph relationships with source/version edges
I. validate row parity, aliases, provenance, index counts and cross-data-plane links
J. publish active manifest pointer **only if required checks pass**
K. invalidate/version-key caches and emit `corpus.version.activated.v1`
```

- Make all 22 chunks individually resumable but link to the original file hash and original row offsets. Reject gaps, overlaps, duplicate chunk ingestion and inconsistent header/order.
- Support XLSX sheet IDs, Excel date serials, formulas-vs-cached values, hidden rows and merged cells as **explicit policy decisions**; do not silently assume the first row always contains correct headers.
- Store an operator-visible `ingestion_run_id`, stage durations, errors, retry counters, row counts and validation checksums.
- If source is large, use a stream-based parser instead of `list(csv.reader(...))`. Restrict upload size, encoding, CSV injection and malformed records.
- Avoid calling the LLM to extract each numeric value. Entity/taxonomy enrichment must not block canonical row capture when optional.

### Acceptance criteria for ingestion
1. Actual row count equals manifest count (e.g. 16,245), all 22 chunks present, no gap/overlap, exact total hash parity with source.
2. Every accepted row has `source_row_id`, source version, typed metric fields and validation status.
3. Missing/duplicate/inconsistent rows prevent version activation; no partial graph or vector write can mark complete.
4. Re-ingesting identical content is idempotent; content change creates a new version and traceable diff.
5. Failure injection at parse, SQL, graph, vector, cache and activation stages either rolls back or leaves old active version serving.

## 6. Query planner and secure executor design

**Plan parse:** deterministic rules for exact key/date/metric extraction; LLM may supply a typed plan candidate for complex natural language. Entity resolver maps aliases and explicitly flags ambiguity. Validate against metric registry. No free-form SQL from model or user.

**Execution:** compile approved plan to fixed template or ORM query with bound parameters. All table/column/metric/order selections are from trusted enums. Enforce tenant and dataset-version filters in data access itself; never rely on planner prompt to add them.

**Result:** return `(rows, units, filters, exclusions, row_provenance, result_set_hash, executed_plan, observed_latency, reproducible_count)`.

Example conceptual plan execution, **valid only after data steward approves additivity**:

```sql
SELECT amc_id, SUM(aaum_micro_cr) AS total_aaum_micro_cr
FROM aaum_observations
WHERE tenant_id = :tenant_id
  AND dataset_version = :dataset_version
  AND aaum_quarter = :approved_quarter
  AND valid_for_aggregation = 1
GROUP BY amc_id
ORDER BY total_aaum_micro_cr DESC, amc_id ASC
LIMIT :limit;
```

In addition to result rows, return counts of exclusions, duplicate suppression, period violations and unresolved entities. Provide `result_set_hash` calculated on normalized output, not UI Markdown.

### Failure rules
- `STRUCTURED_SOURCE_UNAVAILABLE`: SQL store/index missing, inconsistent version, timeout; **never** silently route to approximate vector response.
- `AMBIGUOUS_QUERY`: scheme vs plan or `average` grain unspecified; ask one precise disambiguation or emit documented conservative assumption if approved.
- `INCOMPATIBLE_PERIODS`: NAV dates or AAUM quarters not comparable under selected metric rules.
- `UNSUPPORTED_METRIC`: no signed metric definition; no ad hoc arithmetic.
- `NO_MATCH`: explicit zero result with examined filters; distinct from data unavailability.

## 7. Retrieval and answer generation policy

- Route `count`, `top N`, `sum`, `ratio`, `average`, `NAV`, `AAUM`, `date`, `ISIN` through typed planner first.
- For mixed questions, construct separate verified financial result and document/regulatory evidence and synthesize **only explanations**.
- Disallow default filters (`Growth`, `Equity`, `Open Ended`, etc.) unless query or approved API default explicitly requests them; echo filters.
- When response is table-backed, emit a table directly. Do not ask LLM to recreate rows, compute percentages, derive numbers or invent footnotes.
- Include both `aaum_quarter` and `latest_nav_date` if mixed; no vague `latest` without dataset timestamp.
- Protect UI hyperlinks: source evidence should point to source document+row/line or a secured exact-fact endpoint, not unrelated API routes or synthetic pages.
- If the planner is uncertain between an exact fund name and a generic query, prioritize conservative resolution or show multiple candidates rather than guessing.

## 8. Golden test design

Use a curated, independently steward-labeled CSV gold dataset. Suggested distribution: 40 exact lookups, 40 filters/comparisons, 35 aggregations/rankings, 20 date/quarter variants, 20 ambiguous/no-answer cases, 20 adversarial values, 25 mixed CSV+PDF/regulation = **200 cases**. Add PDF control cases separately.

| Case | Example query | Required assertions |
|---|---|---|
| E01 | “NAV for scheme code 100033 on 2026-06-29” | Value 922.67 as shown in viewed chunk row; preserve source row anchor, units and date; verify against current dataset snapshot before treating as gold |
| E02 | “How many records are in this snapshot?” | Exactly 16,245 if manifest-source reconciliation passes; not a guessed phrase |
| E03 | “Top 5 AMCs by AAUM in Q1 2026” | SQL result equals independently computed gold; one quarter; deterministic tie-break; version |
| E04 | “Open ended versus close ended scheme distribution for top five AMCs” | Correct grouping and denominator; no duplicate schemes across categories; sum of percentages within tolerance |
| E05 | “Average AUM of SBI fund” | Requires ambiguity resolution: plan vs scheme vs AMC and period |
| E06 | “Highest NAV regardless of date” | Policy-based comparability or explicit clarification, not silently filtered equity-growth-only table |
| E07 | “No such scheme” | NO_MATCH, no fabricated NAV |
| E08 | “How many schemes are inactive?” | Do not infer using Closure_Date until field semantics verified |
| E09 | “NAV and SEBI investment limit for scheme X” | Structured NAV + authoritative dated source clause, no cross-source value invention |
| E10 | Corrupted chunk/duplicate row | Ingest quarantines and active version remains unchanged |
| E11 | Changed spreadsheet formula | Formula-value policy applied, result/lineage stable or rejected |
| E12 | Failed SQL driver | `STRUCTURED_SOURCE_UNAVAILABLE`, no LLM-generated numeric fallback |

**Every test must assert route, query plan, exact normalized result, source-row provenance, version, authorized principal, citations, failure semantics and latency from measured clock.** Keyword presence is insufficient.

## 9. Recommended code layout and migration

```
backend/app/tabular/
  contracts.py            # schema, metric enums and plan types
  source_registry.py      # registered sources and versions
  csv_excel_loader.py     # streaming, normalized parse
  canonical_identity.py   # AMC / scheme / plan / option mapping
  quality.py              # row-, column- and snapshot-level checks
  repository.py           # immutable typed dataset storage
  planner.py              # parse plan + ambiguity + validation
  executor.py             # parameterized safe queries
  proofs.py               # source-row anchors/result hashes
  publisher.py            # atomic active pointer and invalidation
  api.py                  # versioned read/admin endpoints
```

Adapt `scheme_aggregation_service.py` to a compatibility facade over `tabular.executor`. Refactor `fast_path_interceptor.py` to dispatch to that typed service and fail closed for structured questions. Retain graph+vector for PDF/text, plus optional CSV row discovery. Deprecate direct vector modification from `scripts/ingest_csv.py` after parity tests. Do not delete old paths until shadow comparison and rollback are proven.

## 10. Definition of done

The first CSV correctness release is complete only when (a) all accepted source rows are reconciled; (b) an agreed set of finance formulas is signed; (c) no observed critical exact-answer mismatches occur in gold evaluation; (d) every answer carries proof metadata; (e) protected users cannot read other tenants' data; (f) backend/React e2e passes for key cases; (g) failures abstain rather than hallucinate; (h) rollback returns old exact answers and source links.
