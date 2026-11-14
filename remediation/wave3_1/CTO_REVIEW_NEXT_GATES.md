# AMC Wave 3.1 — CTO integration review and next engineering gates

**Reviewed base:** `amc-dev` at `2c0415c4d23a3338428c8314c869299aa0ab771f`  
**Local-agent implementation:** `83ee6cac712099f0b0b3986ea449e75f31824d26`, originally pushed to `amc-dev-wave31-integration`  
**Review verdict:** **ENGINEERING INTEGRATION IN PROGRESS — NOT UAT / NOT MVP ACCEPTED**

## 1. Verified source inventory

- One cumulative implementation commit; 158 changed paths against the source baseline.
- Added Alembic 013 active authority, 014 first-publication scope claim, verified vector bridge, request-lifetime fence, governance/ingestion containment and release test controls.
- Local-agent commit reports three Windows Python 3.14 symlink privilege test failures and does **not** claim live PostgreSQL, Neo4j, FAISS, Alembic upgrade, frontend or UAT testing.
- The new manual Wave 3.1 CI workflow has **no observed run** at the reviewed integration SHA.

## 2. P0 review findings and source remediation

| ID | Finding | Source remediation | Acceptance |
|---|---|---|---|
| R31-API-01 | `/query/traditional`, `/query/contextgraph` and `/query` can dispatch directly to legacy FAISS/RAG when configured for legacy, canary or shadow | Deny unreceipted routes when `AMC_VERIFIED_SERVING_MODE=enforce`; allow only explicit v2 serving path | New unit + HTTP tests in both modes |
| R31-API-02 | `/chat` and `/chat/stream` can dispatch legacy RAG | Require `QUERY_ENGINE=v2` in enforced mode prior to dispatch / response stream | Real authenticated SSE tests |
| R31-API-03 | `/graph` returns raw Neo4j data without verified receipt authority | Refuse direct graph routes in enforced mode | Tenant-isolation route tests |
| R31-API-04 | `/docs`, `/files` and `/taxonomy` expose raw document / graph reads | Refuse unreceipted routes in enforced mode, pending verified per-document provenance | Files/taxonomy HTTP tests and eventual signed serving alternative |
| R31-API-05 | `/schemes/aggregation` reads independently loaded CSV/chunk data | Deny entire legacy aggregation router in enforced mode until signed corpus authorization is implemented | Explicit product-owner decision and tests |
| R31-AUTH-06 | `/query` v2 dispatch previously dropped `current_user`, while `/query/stream` opened SSE before tenant precheck | Forward authenticated context; reject missing tenant before v2/SSE handling | HTTP AuthN/AuthZ tests |
| R31-SEC-07 | Authenticated source-document downloads were returned with `Cache-Control: public` | Replace with `private, no-store` | Verify response headers |
| R31-CI-08 | Existing integration commit has not been qualified on fresh exact SHA | Leave workflow manual; run local suites then explicit CI when Actions budget permits | Both OS + immutable JUnit evidence |

The source changes above are **not accepted as passing** until the current commit is actually compiled and tested. The new AST/unit checks cover source guard wiring and helper behavior, but do not replace endpoint-level tests.

## 3. Next local-agent execution (single consolidated batch)

From a clean checkout of the **current review branch** (do not re-run `install_wave31.py`, `apply_all31.py`, or earlier installers):

```bash
git fetch origin
git switch feature/amc-wave31-integration
git pull --ff-only origin feature/amc-wave31-integration
git rev-parse HEAD
python -m compileall -q backend
PYTHONPATH=backend:. python -m pytest -q backend/tests/test_verified_legacy_route_gates31.py
python -m tools.amc_release.qualification31 --repo . --out remediation/wave3_1/source-review.json
python -m tools.amc_release.run_wave31_tests --root . --full-backend --out remediation/wave3_1/qualification.json
cd mf-context-engine
npm ci
npm test
npm run build
# Browser UAT only when service endpoints and fixtures are provided:
# npx playwright test --config playwright.uat.config.mjs
```

Run with **Python 3.11** for the canonical Linux/Windows qualification. Do not suppress failures with `|| true`. If Windows symlink tests fail, capture their exact identities and environment privileges; do not count failed/untested cases as passes.

## 4. Infrastructure and application acceptance still required

1. Rehearse full Alembic 001→014 DAG and upgrade on a **fresh disposable PostgreSQL** DB; separately rehearse SQLite. Check schema, FK constraints, enum checks, unique scope-claim semantics and rollback behavior. Never downgrade the production database.
2. With real PostgreSQL isolation, race two first-publisher workers on the same tenant/namespace; verify one owner and no premature graph mutation. Crash and resume with the exact work/receipt.
3. Execute real Neo4j mutation/readback/CAS/compensation tests. Inject partial failure between graph and FAISS and independently inspect durable receipts/effects.
4. Load actual FAISS binaries, verify active signed generation and tenant-specific search, deny stale or substituted receipt, and prove rollback revokes result delivery.
5. Execute authenticated HTTP integration for `/query`, `/chat`, `/graph`, `/files`, `/docs`, `/taxonomy`, `/schemes/aggregation`, ingestion and governance in both `off` and `enforce`. Negative tests must prove bypasses are refused and off-mode regression preserved.
6. Execute frontend Node/React tests, production build, and authenticated browser smoke against staging using realistic AMC fixtures.
7. Collect source SHA-bound JUnit, logs, migration history, runtime metrics, rollback drill and application data-provenance evidence. Run manual two-OS CI only after local defects are resolved and capacity is available.

## 5. Release decision and rules

**BLOCK:** never enable `AMC_VERIFIED_SERVING_MODE=enforce` on customer traffic until every required serving route is reviewed, legacy paths are denied or converted to receipt-bound adapters, and infra tests pass. **BLOCK UAT** until engineering sign-off, bounded staging canary, error budget/SLO and rollback evidence.

Do not merge this draft PR into `amc-dev` yet. Do not publish private AMC datasets, credentials or generated `.bak` files. The branch changes are subject to independent review, **not** a production deployment.
