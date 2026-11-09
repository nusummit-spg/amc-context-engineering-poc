# Wave 1.9 — Source audit and implementation evidence

- **Observed HEAD:** `91af9fa4eaa8abdb66c55b04fdee484ea0343a3c` on `amc-dev`.
- **GitHub permissions:** `pull: true`, `push: false`. No branch, commit or PR was created.
- **Implementation output:** independent opt-in SQL/graph/FAISS publication engine package, additive Alembic migration 012, test harness, CI scanner patch.
- **Local test result:** 35 passed for Wave 1.9's SQLite/filesystem/fake-graph/DDL tests; production integration tests NOT_RUN.
- **External service tests:** Neo4j NOT_RUN; actual FAISS binaries NOT_RUN; PostgreSQL multi-worker NOT_RUN.
- **CI state at review:** latest Actions run `42219020259` failed at organization-license requirement of `gitleaks/gitleaks-action@v3`; other jobs skipped.
- **Release decision:** **BLOCK**.

## Work completed in code (not yet wired to live paths)

| Area | File(s) | Verified here | Still required |
|---|---|---|---|
| Durable work queue & unique idempotency | `journal.py`, `models.py` | SQLite | PostgreSQL concurrency |
| Monotonic fenced leases | `journal.py` | SQLite simulated workers | Real concurrent workers and Neo4j |
| Persisted pre/postimages | `PublicationEffect` | SQLite and crash tests | Actual external mutation/replay |
| Generation pointer CAS | `GenerationPointer` | SQLite | Active FAISS serving reader |
| Immutable generations | `artifacts.py` | Filesystem SHA | Atomic multi-host storage |
| FAISS binary builder | `faiss_artifacts.py` | Syntax/contract; actual runtime NOT_RUN | faiss-cpu installed smoke + index parity |
| Graph CAS adapter | `graph.py` | Fake graph, allowlist | Neo4j integration + schema alignment |
| Verified rollback | `worker.py` | Crash and replay fake graph | Real 2-system drill |
| Feedback | `feedback.py` | SQL recipient/receipt checks | Live issue record integration |
| Manifest integrity | `integrity.py` | Corrupted bytes/gaps | Connect to ingestion |
| Serving eligibility | `serving.py` | Active work/receipt/pointer checks | Replace all legacy answer paths |
| Telemetry | `metrics.py` | SQL-derived counts | Prometheus + SLO windows |
| CI scanner | `tools/repair_ci_gitleaks.py` | Source transform test | Run on actual Actions |

## Critical remaining gates

1. **Application wiring is not complete.** New files have no production side effects and cannot silently replace current routes. Local Codex must connect the trusted approval source, persistent worker, graph schema, FAISS reader and serving gate.
2. **Actual FAISS index build/readback not tested:** package has `FaissGenerationStore`, but `faiss-cpu` is absent from this sandbox. Production mode refuses JSON-only artifacts and requires a live serving-reader probe.
3. **Real Neo4j and PostgreSQL concurrency:** code includes adapters and monotonic fencing but needs integration test evidence, especially stale worker and crash during cross-store publication.
4. **Existing route bypasses** such as `promote_to_permanent()` and `get_active_patches()` require removal; publication must be single-writer.
5. **Feedback module removal** requires a product-owner migration/deprecation decision, including API/frontend compatibility.
6. **Quantitative finance controls** need full end-to-end ingestion and provenance ledger, plus steward signoff where relevant.

## Minimum decisive tests to run locally

1. `pytest backend/tests/test_wave19_*.py` with no skips in the core suite.
2. Migrate an empty **disposable** PostgreSQL DB and a populated fixture with revision 012; verify upgraded schema, indexes and downgrade rehearsal only on throwaway DB.
3. Start two real workers; make both attempt the same work ID; exactly one mutation permitted, no false receipt.
4. Kill worker after preimage, graph write, vector generation build, pointer swap, graph rollback, and vector rollback; restart and verify a single logical publication or safe retry.
5. Verify exact graph key/tenant/attribute and normalized readback. Fail on missing node, wrong source version, wrong tenant and stale fence.
6. Build/activate actual FAISS generation, reload serving reader, assert exact IDs/count/SHA, corrupt artifact and verify activation denied; then rollback and verify old index content.
7. Resolve Feedback only after verified published receipt, then reopen on rollback.
8. Run CSV numeric gold and PDF/TXT control tests; ensure all contributor IDs are retrievable and AAUM remains blocked without stewardship.
9. Fix Gitleaks license-dependent action with CLI, push a local test branch, inspect actual GitHub Actions results; only passing required checks count.
