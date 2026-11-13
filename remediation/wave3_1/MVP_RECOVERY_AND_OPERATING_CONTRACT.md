# AMC Wave 3.1 — MVP Recovery and Verified Pilot Contract

**Status: ENGINEERING CANDIDATE. UAT and deployment BLOCKED.**
**Target:** feature/amc-wave31-integration -> amc-dev; draft PR #13.

## Completed source development
- Integrated publication Wave 3.1, migrations 013/014, durable receipt and rollback.
- Sealed unreceipted legacy query/chat/graph/doc/file/taxonomy/aggregation serving routes.
- Installed an ASGI verified-pilot default-deny perimeter; only authenticated pilot query/chat, login, health, publication status and static asset paths are permitted in enforce mode.
- In enforce mode, disabled background Neo4j seed/schema writes, legacy FAISS/cache warmups, scheduler, ingestion queue and feedback/recovery background processes. Off-mode startup stays unchanged.
- Removed hardcoded SQLite runtime choice. Runtime now accepts a DATABASE_URL environment variable. The existing SQLite fallback remains for legacy development.
- Verified mode requires an explicit postgresql+psycopg:// URL and a DB already migrated to exact Alembic revision 014. Startup does not auto-create/migrate verified-mode production schemas.
- Added local unit tests for mode fencing and a fail-closed release-evidence completeness checker.

## Required pilot configuration (illustrative, NOT a production deployment recipe)
- AMC_VERIFIED_SERVING_MODE=enforce
- QUERY_ENGINE=v2
- DATABASE_URL=postgresql+psycopg://USER:SECRET@HOST/DB (pass through secret manager; never commit credentials)
- AMC_VERIFIED_FAISS_ROOT points to a signed, operator-published immutable active corpus
- Tenant-scoped authenticated users, working Neo4j and approved model provider configuration
- Alembic 001→014 applied to the *same* PostgreSQL database before app startup

## Local qualification commands
1. python -m compileall -q backend
2. python -m pytest -q backend/tests/test_pilot_perimeter31.py backend/tests/test_db_runtime31.py backend/tests/test_verified_legacy_route_gates31.py
3. python -m pytest -q tools/amc_release/tests_wave31/test_mvp_evidence_gate31.py
4. python -m tools.amc_release.run_wave31_tests --root . --full-backend --out ../mvp-qualification/wave31.json
5. cd mf-context-engine && npm ci && npm test && npm run build
6. Run real disposable PostgreSQL migrations, concurrency/crash tests, Neo4j compensation, signed FAISS rollback, authenticated API/SSE/browser smoke and staging canary.

## Formal evidence gate
From a CLEAN checkout with evidence outside the repository:
python -m tools.amc_release.mvp_evidence_gate31 --checkout . --evidence-dir ../mvp-qualification --out ../mvp-qualification/mvp-gate.json

Evidence requires source SHA-bound reports for backend integration, auth negative routes, PostgreSQL migration 014, first-publisher concurrency, Neo4j readback, FAISS rollback, frontend/browser, staging smoke and canary/rollback/SLO; plus a non-skipped passing integrated-junit.xml.
Even when evidence is structurally complete, the result is EVIDENCE_PRESENT_REQUIRES_INDEPENDENT_REVIEW, not automatic release approval.

## Remaining P0 blockers
- Complete GitHub HEAD application tests have not been run. The original archive's 669 passed primary tests and additional subtests are reference tests, not integrated-commit acceptance.
- PostgreSQL, Neo4j, FAISS, real auth/SSE, frontend/browser and deployment readiness remain unverified.
- Verified pilot presently excludes direct ingestion and feedback mutation. Product-owner acceptance of a read-only pilot scope is pending.
- Do not merge draft PR #13, migrate production data, enable customer traffic or advertise MVP readiness without independent sign-off.
