# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# Implementation Plan: Auto-Crawling & Dynamic Taxonomy Generation

**Source**: `autocrawling_taxonomy_design.md` (design doc, status: design phase)
**Purpose of this document**: Turn that design into a buildable, sequenced plan — what gets built in what order, why that order, what "done" looks like per phase, and where the risk sits.
**Non-goal**: This does not change any architecture decision from the design doc. It only sequences and operationalizes it.

---

## 1. Sequencing Principle

The design doc lists four acquisition channels (A–D) as if parallel, but they are not equal risk or equal dependency. The build order below is driven by three rules:

1. **Foundation before channels.** `provenance_ledger.py` and `ingestion_gateway.py` are load-bearing for every channel — build and test them against synthetic data before any real channel touches them.
2. **Lowest-risk, highest-control channel first.** Channel D (admin manual ingest) has no scraping/legal ambiguity and is the fastest way to exercise the gateway → indexing → taxonomy path end-to-end with a human in the loop. Build it first even though the doc lists it last.
3. **Legal lead time starts on day one, in parallel with engineering.** The SEBI permission letter (2–4 week external process) blocks Channel A regardless of engineering readiness — file it at Phase 0, not when Channel A's code is ready.

Existing pipeline (`build_index.py`, NER, graph_store, FAISS) is explicitly **zero changes** per the design doc — no phase touches it; it's a consumer of the new gateway.

---

## 2. Phase-by-Phase Plan

### Phase 0 — Foundations & Legal Kickoff
**Builds**: `provenance_ledger.py` (SQLite schema + all key functions), `config.py` additions (`SEBI_RSS_URL`, `AMFI_NAV_URL`, `MEMBER_PORTAL_INBOX`, `RETRIEVAL_ACTIVE_ONLY`, `CACHE_GRAPH_MODE`), `taxonomy.py` extension (version backup + atomic write, no new dimensions yet).
**Parallel action (non-engineering)**: File SEBI permission request letter for bulk historical download — this is the longest lead-time item in the whole plan and has zero code dependency.
**Definition of done**: `backfill_existing_documents()` successfully migrates current `data/AMC/` contents into the provenance table with correct hashes; `find_by_hash`, `find_by_filename`, `get_active_filenames` pass unit tests against the backfilled data.
**Depends on**: nothing.
**Blocks**: every later phase.

### Phase 1 — Ingestion Gateway
**Builds**: `ingestion_gateway.py` (`IngestRequest`/`IngestResult`, `process_ingest()` with dedup + namespace routing + provenance write).
**Definition of done**: `test_ingestion_gateway_dedup()` passes — same PDF submitted twice is rejected on the second call, FAISS/build_index untouched by a duplicate.
**Depends on**: Phase 0.
**Blocks**: all four channels.

### Phase 2 — Channel D: Admin Authorized Ingest
**Builds**: "📥 Authorized Ingest" tab in `admin_view.py` (URL/upload form, metadata fields, RBAC-populated `authorized_by`).
**Why second, not last**: it's a human-gated write path with no external polling, no rate limits, no legal review needed — the cheapest way to prove Phase 0/1 work against real documents before automating acquisition.
**Definition of done**: A compliance officer can ingest a PDF by URL or upload, see it land in the provenance ledger, and see `build_index.py` pick it up on its next run — with zero changes to `build_index.py` itself.
**Depends on**: Phase 1.

### Phase 3 — Channel C: Member Portal Watcher
**Builds**: `amfi_member_portal.py` (`MemberPortalWatcher` class using `watchdog`).
**Why third**: also legally uncomplicated (watching a folder a human already has authority to populate), and it's a good low-complexity way to test the gateway under an automated (non-admin-UI) trigger before tackling network scraping.
**Definition of done**: dropping a PDF into `MEMBER_PORTAL_INBOX` results in an ingestion within ~2 seconds, logged to `logs/member_portal_log.jsonl`.
**Depends on**: Phase 1.

### Phase 4 — Channel B: AMFI Portal Adapter
**Builds**: `amfi_portal_adapter.py` — `fetch_nav_all()`, `fetch_scheme_history()`, `fetch_sid_sai_listing()`, `fetch_amfi_monthly_aum()`.
**Why fourth**: first channel that involves real network polling of a third party, but on SEBI-mandated public disclosure endpoints — lower legal ambiguity than Channel A, and a good testbed for hash-based "has this changed" logic before applying it to RSS.
**Definition of done**: `test_taxonomy_nav_extract()`-equivalent — a full `NAVAll.txt` pull correctly identifies new fund houses/scheme names as a diff against the previous pull, with unchanged pulls returning `(empty_df, False)`.
**Depends on**: Phase 1.

### Phase 5 — Channel A: SEBI RSS Ingester
**Builds**: `sebi_feed_ingester.py` — `poll_sebi_rss()`, `detect_supersession_from_title()`, `download_circular_pdf()`, `run_daily_sebi_poll()`.
**Gate**: do not enable scheduled/bulk polling until the Phase 0 permission letter response is in hand; the live-feed poll (RSS is explicitly designed for machine consumption per the doc) can proceed without it, but historical backfill should wait.
**Definition of done**: `test_sebi_rss_poll()` and `test_supersession_detection()` pass; rate limiting (1 poll/5min, 3 downloads/min) verified under a mocked feed with >10 entries.
**Depends on**: Phase 1. **Soft-depends on**: Phase 0 legal response for historical backfill only.

### Phase 6 — Taxonomy Extractor (core IP)
Build the 7-step pipeline in sub-phases, not all at once — each step is independently testable:

| Sub-phase | Builds | Test gate |
|---|---|---|
| 6a | Step 1 routing + Step 2A tabular extraction (`tabular_nav_extract`, `tabular_sid_extract`) | `test_taxonomy_nav_extract()` |
| 6b | Step 2B NER-driven extraction (`ner_circular_extract`, all 3 sub-strategies) | `test_taxonomy_circular_extract()` |
| 6c | Step 3 concept normalization | dedup/case-normalization unit tests |
| 6d | Step 4 FIBO anchoring (`map_to_fibo`, `build_fibo_mapping_report`) | `test_fibo_mapping_coverage()` |
| 6e | Step 5 merge + versioning (`merge_taxonomy_delta`) | manual diff check against a known delta |
| 6f | Step 6 Neo4j graph node generation | node/edge count assertions against a test graph |
| 6g | Step 7 NER hot-reload | `test_ner_hot_reload()` — new term recognized without restart |

**Why this order within the phase**: 6a/6b (extraction) must exist before 6c (normalization) has anything to normalize; 6e (merge) must exist before 6f (graph nodes, which read from the merged delta) or 6g (hot-reload, which reads the merged file). 6d (FIBO) can be built in parallel with 6c since it only needs raw extracted terms.
**Depends on**: Phase 2 or 4 (needs at least one real ingestion channel producing documents to extract from — Channel D is sufficient to start).

### Phase 7 — Regulatory Lifecycle Enricher
**Builds**: `regulatory_lifecycle_enricher.py` — `upsert_regulatory_document()`, `detect_and_link_amendments()`, `confirm_supersession()`, `reject_supersession()`; admin review queue UI (extends the Phase 2 tab).
**Definition of done**: `test_admin_confirm_supersession()` — confirming a proposed edge flips the old document's status to `superseded` in both provenance ledger and graph, and drops it from `taxonomy_retrieval.py`'s active-status filter.
**Depends on**: Phase 5 (supersession detection needs SEBI circular data) and Phase 6f (graph nodes must exist to attach edges to).

### Phase 8 — Pipeline Orchestrator & Scheduler
**Builds**: `pipeline_scheduler.py` (`run_production_pipeline()`, APScheduler `SCHEDULE_CONFIG`), admin "Run Now" buttons.
**Definition of done**: `test_full_pipeline_e2e()` — a mocked RSS entry flows through acquisition → gateway → indexing → taxonomy → graph enrichment → a retrieval query returns an answer grounded in the new circular.
**Depends on**: Phases 2–7 all functional individually (this phase wires them, doesn't build new extraction logic).

### Phase 9 — Staleness Monitor
**Builds**: `staleness_monitor.py` (`run_drift_check`, SHA-256 re-check on a sample of known-source documents).
**Definition of done**: drift on a deliberately-modified test document is detected and alerted within one scheduled run.
**Depends on**: Phase 0 (provenance ledger with `source_url` populated) — can be built any time after Phase 1, but has no urgency until real scheduled channels (5, 8) exist.

### Phase 10 — Taxonomy Versioning & SKOS Export
**Builds**: `restore_taxonomy_version()`, `diff_taxonomy_versions()`, `export_taxonomy_skos()`.
**Definition of done**: `test_taxonomy_skos_export()` — valid SKOS RDF output containing every active taxonomy term, FIBO-mapped terms carry `skos:exactMatch`/`skos:closeMatch`.
**Depends on**: Phase 6e (versioned backups already exist from the merge step — this phase adds rollback/diff/export tooling on top).
**Note**: this is explicitly the IP/showcase artifact per the design doc — worth prioritizing ahead of Phase 9 if there's a demo or external-sharing deadline.

### Phase 11 — Hardening & Full Regression
Run the complete test table from the design doc together, plus load/failure-mode testing not explicitly listed:
- Full RSS feed outage (network tool denies domain) → pipeline degrades gracefully, no crash, alert logged
- Duplicate content with different filenames (same PDF re-published under a new URL) → dedup by hash still catches it
- Concurrent ingestion from two channels for the same document within the same run
- Taxonomy merge conflict (two extraction jobs racing on the same `taxonomy.json`) → atomic write prevents corruption

### Phase 12 — Rollout
- Enable Channel D + C in production first (no scheduling needed — they're human/event triggered).
- Enable Channel B scheduled polling (daily NAV, weekly SID/AUM) per `SCHEDULE_CONFIG`.
- Enable Channel A scheduled polling only after Phase 0's legal response is confirmed for the scope being polled (live RSS vs. historical backfill).
- Turn on `staleness_check` and full `pipeline_scheduler` last, once every phase has run manually without incident for an agreed burn-in period.

---

## 3. Dependency Graph

```
Phase 0 (Foundations) ──┬─────────────────────────────────────────────┐
   │ (legal letter, parallel, no code dep)                            │
   ▼                                                                   │
Phase 1 (Gateway) ──┬──────────────┬──────────────┬──────────────┐    │
                     ▼              ▼              ▼              ▼    │
                 Phase 2         Phase 3        Phase 4        Phase 5 │
                 (Ch. D)         (Ch. C)        (Ch. B)        (Ch. A) │
                     │                             │              │ ◄──┘ (soft: backfill only)
                     └──────────────┬──────────────┘              │
                                    ▼                              │
                              Phase 6 (Taxonomy Extractor, 6a-6g)   │
                                    │                               │
                                    └───────────────┬───────────────┘
                                                     ▼
                                          Phase 7 (Lifecycle Enricher)
                                                     │
                                                     ▼
                                          Phase 8 (Orchestrator/Scheduler)
                                                     │
                                     ┌───────────────┼───────────────┐
                                     ▼               ▼               ▼
                              Phase 9 (Staleness)  Phase 10 (Versioning/SKOS)
                                     └───────────────┬───────────────┘
                                                      ▼
                                          Phase 11 (Hardening) → Phase 12 (Rollout)
```

---

## 4. Effort & Risk Summary

| Phase | Relative complexity | Primary risk | Mitigation |
|---|---|---|---|
| 0 | Low | Legal letter delay blocks nothing engineering-wise, but blocks rollout | File it immediately, track separately from engineering sprints |
| 1 | Low-Med | Dedup logic edge cases (same file, different name) | Explicit test for both hash-match and filename-match-different-hash cases |
| 2 | Low | RBAC integration for `authorized_by` | Confirm session/auth pattern already used elsewhere in `admin_view.py` before building |
| 3 | Low | File-write-in-progress races (partial PDF) | 2-second debounce + magic-byte validation, as specified |
| 4 | Medium | AMFI page/format changes silently breaking parsers | Hash + row-count sanity checks on each pull, alert on anomaly, not just on error |
| 5 | Medium-High | Legal ambiguity on bulk historical download; title-parsing regex brittleness | Keep live-feed and historical-backfill as separately gated features |
| 6 | High (largest phase) | NER extraction quality (false positives in `regulatory_obligations`) | Build 6a→6g incrementally with test gates per step; do not defer testing to the end |
| 7 | Medium | Auto-linking wrong supersession pairs | Everything stays `pending_confirmation: True` until a human confirms — already designed in |
| 8 | Medium | Orchestration masking a failure in one channel as pipeline-wide success | `PipelineReport` should surface per-phase status, not just overall pass/fail |
| 9 | Low | False-positive drift alerts on sites with legitimate frequent changes | Sample size tuning (start at 10, adjust from observed false-positive rate) |
| 10 | Low-Med | SKOS export correctness for external sharing | Validate output against an RDF/SKOS validator, not just internal round-trip |
| 11-12 | Medium | Concurrent-write corruption of `taxonomy.json` under real scheduled load | Confirm atomic write (temp file + rename) actually prevents torn reads under the scheduler's real concurrency, not just in unit tests |

---

## 5. File Build Order (concrete checklist)

```
[ ] provenance_ledger.py          (Phase 0)
[ ] config.py additions           (Phase 0)
[ ] taxonomy.py extension          (Phase 0)
[ ] ingestion_gateway.py          (Phase 1)
[ ] admin_view.py: Authorized Ingest tab   (Phase 2)
[ ] amfi_member_portal.py         (Phase 3)
[ ] amfi_portal_adapter.py        (Phase 4)
[ ] sebi_feed_ingester.py         (Phase 5)
[ ] taxonomy_extractor.py         (Phase 6, built in 6a-6g sub-steps)
[ ] ner_pipeline.py: cache invalidation hook   (Phase 6g)
[ ] graph_store.py: init_regulatory_schema()   (Phase 6f)
[ ] regulatory_lifecycle_enricher.py   (Phase 7)
[ ] admin_view.py: proposed-edge review queue  (Phase 7)
[ ] pipeline_scheduler.py         (Phase 8)
[ ] build_index.py: processed_ledger_meta.json companion   (Phase 8, minimal touch)
[ ] staleness_monitor.py          (Phase 9)
[ ] taxonomy.py: versioning/rollback/SKOS export functions   (Phase 10)
```

This matches the design doc's Section 7/8 file inventory, ordered by the dependency graph above rather than by the order listed in the original doc.

---

## 6. Open Questions to Resolve Before Phase 6

These aren't blocking earlier phases but should be settled before the taxonomy extractor is built, since they shape its output schema:

- Confidence threshold for auto-accepting a `regulatory_obligations` extraction vs. routing to human review (the design doc gates supersession by confidence but doesn't specify a threshold for general obligation extraction).
- Whether `compliance_concepts` keyword matching should be case-sensitive/whole-word only, to avoid false positives on common short acronyms.
- FIBO mapping fuzzy-match threshold (doc specifies 0.85 via `difflib` — confirm this is validated against a labeled sample, not just chosen by intuition).
