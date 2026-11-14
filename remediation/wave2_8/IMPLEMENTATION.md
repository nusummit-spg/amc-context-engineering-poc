# AMC Wave 2.8 — Durable active-receipt authority and retrieval cutover

**Status:** Local SQLite/reference implementation tested; **NOT deployed or UAT-cleared**.

## What is included

- `backend/amc_publication/active_authority28.py`: persisted authoritative `(tenant, namespace, generation, epoch, work, receipt)` binding. Prior binding is captured before graph mutation. New publication suspends the previous authority until its receipt commits. Rollback only restores an earlier exact, still-verified publication after both compensation effects complete.
- `backend/amc_publication/serving28.py`: request-side verifier that ties immutable bytes and actual serving reader to the exact bound receipt, rejecting ambiguous historical publications.
- `backend/amc_publication/vector_bridge28.py`: AMC `search` / `similarity_search` interface over the verified reader, with tenant, owner, metadata and taxonomy filtering. Rejects non-standard read APIs and legacy fallback.
- `backend/alembic/versions/013_active_receipt_authority_v28.py`: additive migration, no automatic legacy pointer backfill.
- `tools/amc_release/active_cutover28.py`: dry-run source-locked edits to journal, vector factory, retrieval orchestrator, and traditional query endpoint. **Apply only after Wave 2.5/2.6/2.7 source fixes.**
- `tools/amc_release/release_audit28.py`: read-only exact-commit audit, intentionally never claims UAT/production.
- `.github/workflows/amc-wave28-qualification.yml`: manual-only source, Windows/Linux contract and disposable PostgreSQL migration checks; no automatic release.

## Critical safe sequencing

1. Restore actual AMC checkout at reviewed source SHA (or re-audit changes); create feature branch with repository owner.
2. Install cumulative additive components using `install_wave28.py --repo <path>` (dry-run) and `--apply` only after review. This does not edit existing application source.
3. Apply Wave 2.5 then Wave 2.6 journal/worker/governance source fixes, then Wave 2.7 FastAPI route wiring. Review every patch and source SHA.
4. Review `python -m tools.amc_release.active_cutover28 --repo .` diff and apply after direct inspection. The journal patch is **mandatory**; adding sidecar tables without updating the journal does not establish active receipt authority.
5. Install migration using reviewed Alembic upgrade; **do not add missing historical migrations or stamp databases blindly**. Existing databases have no authority binding until a new, actually verified publication occurs.
6. Commit reviewed code and run manual Wave 2.8 qualification on the exact feature SHA; reconcile JUnit test identities, not only counts.
7. Keep `AMC_VERIFIED_SERVING_MODE=off` until every retrieval route, writer/ingestion call and cache path has passed real integration tests. `enforce` refuses legacy base-vector reads, legacy fast paths, unbound caches, missing tenants, and unapproved correction overlays.
8. Qualify real Neo4j CAS/readback, PostgreSQL simultaneous worker/fence behavior, FAISS binary loader/search across OSes, authenticated API routes, rollback/restore after crash, and staging browsers. Collect 1h/24h SLO windows and canary evidence. Only then request independent UAT approval.

## Engineering risks before enablement

- `get_vector_store()` is consumed by both query and ingestion paths. The verified bridge deliberately does not expose legacy vector writes. Separate the ingestion writer factory before enabling enforcement globally.
- Legacy `app.engine.faiss_store` retrieval paths and other direct stores have not been audited end-to-end in the complete checkout. An opt-in bridge is not proof that all endpoints are protected. Static source checks + authenticated endpoint tests are mandatory.
- Streaming answers require revocation checks throughout streaming, not only at request start. Wave 2.8 validates before orchestration and within verified vector search, but no full streaming-lifecycle guarantee is claimed without live testing.
- The source-locked orchestrator patch disables unbound semantic cache lookup and shadow correction overlays in enforcement mode. This may temporarily reduce answer quality; correctness is the priority.
- New binding tables have no backfill. Legacy data remains fail-closed until re-publication through the reviewed worker. Out-of-order manual mutations must not create an active binding.

## Evidence standard

Offline database tests establish transactional ordering and failure rejection. They do **not** establish independent Neo4j readback, actual FAISS binary reload, post-commit streaming concurrency, Windows path behavior in deployment, or end-to-end UAT readiness. Release remains **BLOCKED**.
