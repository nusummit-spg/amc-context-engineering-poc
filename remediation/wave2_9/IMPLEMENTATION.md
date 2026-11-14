# AMC Wave 2.9 — Ingestion Isolation and Request-Lifetime Serving Authority

**Base:** `amc-dev` commit `2c0415c4d23a3338428c8314c869299aa0ab771f`, reviewed 11 November 2026.  
**Delivery:** Offline cumulative Waves 2.3–2.9, not committed or deployed.  
**Release:** **BLOCKED** — still requires full actual-repository compilation, live multi-store verification and independent UAT.

## Critical architecture defects addressed

1. `app.ingestion.pipeline.IngestionPipeline.ingest_file` writes to Neo4j before writing to FAISS. In Wave 2.8 enforce mode, the vector serving bridge intentionally has no indexing method. A partially written graph could therefore survive an invalid ingest. **Wave 2.9 blocks this pipeline before parsing or any graph write** and blocks both HTTP ingest entrypoints before uploads/queueing.
2. `app.api.deps.Container` injected one vector store into both the ingestion pipeline and retrieval orchestrator. **Wave 2.9 explicitly splits the ports:** verified reader to retrieval, a rejecting write-port to legacy ingestion while enforce mode is active; off mode remains unchanged.
3. Direct `VectorStore` methods could bypass the API and mutate live FAISS. **Wave 2.9 blocks eight base read/hydration/mutation entrypoints** under enforce mode: constructor hydration, `ensure_collection`, `_persist`, `index_chunks`, `add`, `add_documents`, synthetic-chunk ingest/evict and deletion. Constructor no longer loads legacy FAISS/pickle to obtain embeddings in enforce mode.
4. Cached, traditional and streamed responses could outlive the receipt checked at the beginning of a request. **Wave 2.9 pins generation/work/receipt/epoch for the whole answer** and validates again after retrieval. Streaming frames are buffered before first delivery and rechecked between frames; this is **not** an atomic cross-store lock, and a revocation between the final check and network send is still a theoretical race.
5. Unapproved ingestion now has an independent **content-addressed quarantine**. This stores candidate chunks with raw-source hashes, explicit tenant/source version, deduplicated chunk IDs and an immutable digest; it **never** writes Neo4j, FAISS, the journal or active pointers. It records `publication_authorized=false`, `complete_corpus=false`. Independent catalog completeness review, HMAC signing, four-eyes authorization and journal publication remain mandatory.

## New components

| Path | Outcome |
|---|---|
| `backend/amc_publication/ingestion_boundary29.py` | Content-addressed immutable quarantine and explicit rejecting ingestion port |
| `backend/amc_publication/request_fence29.py` | Whole-request and buffered-stream active-receipt fencing |
| `tools/amc_release/ingest_cutover29.py` | SHA-pinned, dry-run-first source transformation of dependency wiring, ingestion API, pipeline and base VectorStore |
| `tools/amc_release/quarantine29.py` | Manual-only JSON quarantine importer; dry-run by default |
| `install_wave29.py` | Cumulative additive installer; refuses overwrites and symlink targets |
| `.github/workflows/amc-wave29-integration.yml` | Manual-only Linux/Windows tests with exact SHA, optional full backend suite |
| `tools/amc_release/tests_wave29/*` | Adversarial contracts, synthetic source patch execution, staging CLI, installer and request-race tests |

## Required integration order in a *real* Git checkout

1. Create `feature/amc-release-candidate-hardening` from the reviewed `amc-dev` commit or re-review any new HEAD. Back up existing databases and FAISS files.
2. Outside the checkout, extract the cumulative ZIP. Run `python install_wave29.py --repo <real-checkout>` to preview additions. Review paths, then `python install_wave29.py --repo <real-checkout> --apply`. The installer **does not patch existing source**.
3. **Corrected sequencing:** From the pristine reviewed source, apply the **combined Wave 2.5+2.6 `publication_patch26_cli` exactly once**, then Wave 2.7 `app_wiring27_cli`, then Wave 2.8 `active_cutover28`, then Wave 2.9 `ingest_cutover29`. **Do NOT apply `publication_patch25_cli` first**: the Wave 2.6 implementation already composes Wave 2.5 from the unmodified reviewed source, and applying 25 first can cause Git-blob drift errors. Inspect every diff and do not force them. Alternatively preview and perform the full checked integration with `python -m tools.amc_release.apply_all29 --repo . --bundle /path/to/extracted/wave29` and `--apply` (creates a *local*, uncommitted feature branch; no remote push).
4. Review `python -m tools.amc_release.ingest_cutover29 --repo .`; only then use `--apply`. This source patch refuses source drift and creates `.wave29.bak` backups. Do **not** use its test-only `skip_reviewed_sha` option in production.
5. On a **disposable** database run Alembic `upgrade head` and actual rollback/re-upgrade for the Wave 1.9–2.8 migrations. Do not stamp or fabricate missing revisions. The Wave 2.8 active receipt authority has no automatic legacy backfill.
6. Keep `AMC_VERIFIED_SERVING_MODE=off` until previously published content is re-verified with an active receipt and all legacy routes and writers are audited. Start enforce mode only on an isolated staging deployment and expect the legacy `/api/ingest/file` and `/api/ingest/batch` endpoints to return HTTP 503 intentionally.
7. For an unapproved candidate, run `python -m tools.amc_release.quarantine29 --source candidate.json --root /secure/quarantine` first; use `--apply` only after review. Input shape is exactly `tenant`, `source_version`, `batch_id`, `submitted_by`, `documents`. Every document requires `tenant_id`, `chunk_id`, `text`, `source_version`, `source_sha256` (raw source SHA-256). Quarantined data is **not** an approved complete corpus.
8. Independently reconcile an authoritative canonical catalog and prepare signed full-snapshot approval using existing Waves 2.5/2.6 tools. Publish only via the durable Journal/PublicationWorker, with real graph readback and FAISS reader activation proof.
9. Trigger `AMC Wave 2.9 Integration Qualification` manually; compare Windows/Linux test inventory and run the optional full-backend suite. Perform authenticated endpoint checks, real Neo4j/FAISS/Postgres concurrency, 1h/24h SLO windows, canary and rollback before a signed go/no-go decision.

## Unified local branch bootstrap and cumulative patch sequencing

The previous Waves 2.5–2.8 handoff had an incorrect sequence in some examples. **Wave 2.6 already composes Wave 2.5**, so invoking `publication_patch25_cli --apply` before `publication_patch26_cli --apply` is not supported on the same pristine source. The Wave 2.9 branch-bootstrap tool uses the correct order.

From the **extracted cumulative bundle root**, first preview:

```bash
python -m tools.amc_release.apply_all29 --repo /path/to/real-amc-checkout --bundle .
```

Then, only after reviewing the dry-run output and confirming a clean reviewed baseline:

```bash
python -m tools.amc_release.apply_all29 --repo /path/to/real-amc-checkout --bundle . --apply
```

This creates a **local** `feature/amc-release-candidate-hardening` branch, installs previous additive work, applies **combined Wave 25+26 once** then 27, 28 and 29, compiles relevant code, and executes Wave 2.9 boundary tests. It never commits, pushes, deploys or certifies UAT. On a failed stage it stops on the partially modified local branch and preserves backups for manual reconciliation. Never assume a partial run succeeded.

## Explicit failure/containment conditions

- `enforce` mode + legacy direct VectorStore indexing → denied.
- `enforce` mode + ingestion pipeline/file/batch endpoint → denied **before** graph mutation and file or queue creation.
- Invalid verified-mode token → denied; never silently defaults to legacy.
- Missing tenant or receipt authority → denied; no fallback to unscoped retrieval.
- Published receipt/epoch changes while building response → denied.
- SSE response exceeds bounded buffer → denied before any answer frame.
- Candidate with repeated chunk IDs, mixed tenant/version, missing raw-source digest or changed bytes → denied.
- Canary failure, omitted telemetry or partial exact-commit CI → release remains BLOCKED.

## Evidence caveats

The source-locked transform targets real reviewed GitHub file structures but the container could **not clone GitHub** (DNS unavailable); the supplied integration execution tests are on source-compatible fixtures and bundled Wave 1.9/2.0 reference modules. The full AMC checkout, real Neo4j, PostgreSQL concurrency, FAISS activation, npm build, browser UAT and Windows runners were **not executed**. Do not infer production or UAT readiness from offline counts.

**Future boundary:** A fully supported live ingestion replacement still requires a governed source-inventory service, canonical source completeness attestation and publication journal adapter; Wave 2.9 provides the safe non-activating staging boundary and blocks the unsafe legacy route rather than falsely promoting partial datasets.
