# AMC Wave 3.1 — MVP Technical Design Specification (TDS-31 v1)

**Classification:** Engineering design for a **controlled read-only verified-publication pilot**, not deployed, not UAT-approved.  
**Source analyzed:** `feature/amc-wave31-integration` at `75680052d3660645dd9e929b7c61ab234ed06d28` (2026-11-14). **Draft PR:** #13 into `amc-dev`.  
**Execution references:** [Action plan](MVP_REMAINING_ACTION_PLAN_V1.md) · [Local-agent instruction set](MVP_AGENT_EXECUTION_INSTRUCTIONS_V1.md) · [Existing validation handoff](TEAM_LOCAL_VALIDATION_HANDOFF.md).  
**Decision authority:** Approved changes must preserve the deployed behavior for `AMC_VERIFIED_SERVING_MODE=off` and reject unsafe behavior in `enforce`; any change to authorization or rollback semantics requires independent review before merge.

## 1. Architectural objectives and threat model

### Functional requirements

| ID | Contract | Owner / module | Release proof |
|---|---|---|---|
| FR01 | Authorized tenant user can log in, query and chat over an **ACTIVE** signed corpus | `app/api/routes/auth.py`, `query.py`, `chat.py` | Real HTTP integration |
| FR02 | Retrieval returns tenant-owned authorized results and traceable source/corpus version | `amc_publication/vector_bridge28.py`, v2 orchestrator | Real FAISS/index/citation |
| FR03 | Active publication receipt remains invariant across completed answer or streamed response | `request_fence29.py` | Revocation during request |
| FR04 | Operator publication uses durable work/effects and atomically changes authoritative receipt | `amc_publication/*`, journal and scopes | Real PG + graph + FAISS |
| FR05 | Crash/retry/rollback preserves one active generation or blocks serving until recovered | authority and recovery modules | Fault-injection |
| FR06 | Denied / disabled features show clear errors and do not mutate data | ASGI perimeter, frontend | HTTP / browser test |
| FR07 | QA evidence is reproducible on exact Git SHA and distinguishes source-only from live runtime | `collect_local_evidence31.py` and `mvp_evidence_gate31.py` | Log/JUnit and evidence review |

### Nonfunctional requirements

- **NFR01 Isolation:** Test two tenants with overlapping document IDs and same query; no cross-tenant content, graph links, cache snippets, citations or document download.
- **NFR02 Consistency:** No response emitted when authority absent, suspended, changed, unsigned, invalid, or stale. Test pinned generation before/after each retrieve and stream segment; no fallback.
- **NFR03 Concurrency:** One mutation owner per (`tenant`, `namespace`); the unique SQL row must enforce races in separate live DB sessions, not only mocked locks.
- **NFR04 Availability:** If PG, Neo4j, FAISS, model provider or signer is unavailable, return a bounded denial / controlled error; do not silently return stale data.
- **NFR05 Traceability:** Work ID, receipt ID, scope epoch, tenant, generation/digest, request ID and retry correlation observable in non-sensitive traces. Never include keys/tokens/text bodies unnecessarily.
- **NFR06 Reproducibility:** Python 3.11 canonical, exact committed feature SHA, explicit package versions and offline synthetic fixture hashes. No test denominator changes.
- **NFR07 Security:** Default-deny routes and startup background services in enforced mode, deny direct raw source APIs, no credentials/source corpora in Git.
- **NFR08 Resource budget:** Stay within a single developer machine where practical; use disposable localhost-bound PG/Neo4j, FAISS CPU and selective tests; report observed p95/throughput without invented thresholds.
- **NFR09 Rollback:** Separate *runtime serving rollback* from Git ref revert and database downgrade. Do not downgrade a production database.

### Actors / trust boundaries

**Pilot user** (tenant-scoped JWT/session) → **FastAPI ASGI perimeter** → **authn/authz dependencies** → **v2 retrieval orchestrator + request-lifetime fence** → **verified vector bridge** → **PostgreSQL receipt/authority** → **signed on-disk FAISS/index** and **tenant-scoped Neo4j** → **synthesis/citations**.

Separate **operator/CLI** → durable publication work and scoped claim → graph mutation/effects → signed FAISS staging → verified receipt activation → recovery/rollback. This operator is NOT exposed through a general-purpose HTTP mutation endpoint during pilot.

Explicitly untrusted: user-supplied tenant in payload, model output, legacy cached answers, raw filesystem path, unverified FAISS index, graph facts without durable work evidence, stale SQLite content, backend error messages, untrusted prompt/instructions embedded in source docs.

## 2. Logical component design

### 2.1 Runtime sequence

1. ASGI request arrives at `app.main:create_app`; `VerifiedPilotPerimeter31` enforces exact method/path allowlist when `AMC_VERIFIED_SERVING_MODE=enforce`. Invalid mode or WebSocket must not reach private endpoints.
2. Auth route validates bearer/session against central SQL user store. Tenant derives exclusively from authenticated principal, never from a caller's arbitrary JSON field; explicit admin role needed for operator work outside pilot.
3. `/api/query` / `/api/query/v2` / `/api/chat` dispatch through v2 only (`QUERY_ENGINE=v2`), with tenant/user passed to orchestrator. `legacy_guard31.py` ensures startup and entrypoint fail-closed behavior.
4. `VerifiedOrchestratorFence29` obtains pin for tenant+generation before answer. The bridge independently verifies active bound receipt, signed immutable index, ownership and metadata. Query planning/LLM synthesis may use graph but cannot release a response from any unverified retrieval path.
5. Before returning answer and before each buffered SSE frame release, re-read active authority; if revocation or generation change, abort with sanitized error rather than serving stale content.
6. Frontend renders answer and source provenance only if server included authorized metadata; intentionally disabled file-download routes must not be bypassed by direct URL or assumed functional.

**Test requirement:** API route response must not be used as authority proof; the test must inspect actual PG receipt, signed on-disk index and graph ownership.

### 2.2 Verified pilot route contract

| Route/method | In enforced pilot | Proof |
|---|---|---|
| POST `/api/auth/login`, POST `/api/auth/logout`, GET `/api/auth/me` | Allowed through auth service | Credential and role/auth token lifecycle |
| POST `/api/query`, `/api/query/v2`, `/api/query/stream` | v2 + explicit tenant only | Valid signed corpus; SSE revocation |
| POST `/api/chat`, `/api/chat/query`, `/api/chat/v2`, `/api/chat/stream` | v2 + tenant | Session ownership, history isolation |
| GET `/api/publication/status/{work_id}` | Allowed but must enforce tenant+role | Cross-tenant work-ID probe denied |
| GET `/health`, `/api/health` | Non-sensitive operational summary | Not equivalent to publication readiness |
| GET `/assets/*`, `/static-files/*`, approved SPA paths | Static only; no path traversal/data alias | URL encoding, double slash and path sanitization |
| `/api/query/traditional`, `/api/graph`, `/api/docs`, `/api/files`, `/files`, `/api/taxonomy` | 503 or explicit denial in enforce | No leaked bytes or fallback |
| `/api/admin/*`, `/api/ingest/*`, `/api/feedback/*`, aggregation, unreviewed governance, WS | Disabled (fail closed) | No state changes |
| Unrecognized/invalid method/path, invalid mode | Denied without leaking route details | Negative abuse matrix |

**Compatibility:** `AMC_VERIFIED_SERVING_MODE=off` preserves existing legacy behavior only for explicit non-pilot regression. Never route an enforced-mode production request into off mode to mask failure. Review CORS preflight `OPTIONS` separately: allowing preflight does not authorize underlying route or bypass auth.

### 2.3 Startup lifecycle

- `app.core.db_runtime31.resolve_database_url` selects explicit `DATABASE_URL`; requires `postgresql+psycopg` driver under enforce; **SQLite fallback allowed only off-mode**. Any invalid mode fails at startup.
- Before creating schema or serving, verify application SQLAlchemy engine points to the same disposable DB as Alembic. Under enforce mode, `verify_migrated_postgresql` insists exact version `014_publication_scope_claim_v31`. **No `Base.metadata.create_all` or SQLite-only migration scripts against verified PostgreSQL.**
- `main.lifespan` disables unreceipted graph schema/rules seed, legacy FAISS warming, semantic-cache warmup, ingestion queue, background feedback/retry/lifecycle workers and scheduler under enforce.
- **Known validation risk:** Constructing `Container`, creating driver clients or initializing global modules may cause imports or side effects even before HTTP route entry. Add a boot-time mutation/IO spy or external PG/Neo4j audit to prove no unintended writes, and ensure service readiness is not falsely healthy when no active signed receipt exists.
- On shutdown, close only actually-started resources; ensure no orphan threads or tasks. Test process termination at each phase and startup recovery.

## 3. Durable publication and data model

### 3.1 Canonical persistence boundaries

| Component | Source file / expected state | Required invariant |
|---|---|---|
| Publication work / effect journal | Existing `publication_work_v2`, `publication_effect` and related models | Work IDs immutable; append/terminal status auditable; idempotent replay |
| Active receipt authority | `backend/amc_publication/active_authority28.py`, Alembic 013 | One scoped ACTIVE or SUSPENDED generation, receipt/work FK relationships |
| Empty-authority scope lock | `PublicationScopeClaim31`, Alembic 014 | SQL unique composite (`tenant`, `namespace`) and HELD / RELEASED state machine |
| Scope preimage | `AuthorityPreimage` | Snapshots prior authority before any external graph mutation |
| Auth/session data | `app/core/database.py` + auth schema | Pilot authenticates against same PG; no SQLite shadow fallback |
| FAISS generation manifest | `amc_publication` signing/catalog modules | Immutable index bytes, tenant, digest, generation, receipt match |
| Neo4j graph | Scoped graph client + change effects | Only mutation authorized by durable work; readback before receipt activation |

**Migration checks (real PG):** Walk 001→014; test constraints, unique/foreign keys, duplicate inserts, enum/status check constraints, ALTER idempotence where applicable, heads count, exact revision, and failed upgrade rollback on a fresh copy. Inspect table/column naming mismatches between SQLAlchemy models, migrations and actual queries. Run migration preflight before starting the backend. Never use `create_all` to hide an omitted migration.

### 3.2 Mutation state machine (target / verify existing implementation)

`PREPARED` → (acquire HELD scope claim) → `AUTHORITY_SUSPENDED` → `GRAPH_MUTATION_PENDING` → `GRAPH_READBACK_VERIFIED` → `FAISS_STAGED_VERIFIED` → `RECEIPT_COMMITTED` / `ACTIVE` → release claim. On failure: `RECONCILING` → restore graph and prior active generation **only on proven matching preimage**, or `DENIED_REQUIRES_REVIEW`. These are **logical phases**, not a claim that matching enum strings already exist in code; adapt to implemented work/receipt states and document the mapping.

**Atomicity boundary:** PostgreSQL transaction can atomically commit SQL receipt + ACTIVE authority + scope state, but it cannot atomically commit Neo4j+filesystem. Use durable prepare/effect ledger and idempotent compensating actions for those external systems. SQL transaction boundaries must be explicit; never claim a single ACID transaction across PG, graph and FAISS.

**Concurrency / CAS:** Scope acquisition must use unique SQL row and row lock, not process-local mutex. For a fresh tenant no row exists: simultaneous INSERT/claim must produce one winner and one retriable denial. For an existing tenant: compare generation epoch/digest, work ownership and prior status; a stale worker cannot claim an ACTIVE pointer published by another. Test both competing publisher and rollback/publisher races. For a crashed HELD claim, recovery must use durable work identity and preimage, not force-release by time alone.

**Rollback:** Suspension must precede graph mutation. Failure after graph mutation must trigger compensating readback; serve neither stale graph facts nor FAISS chunks until the old authority is proven safe to reactivate. Schema downgrade is NOT a rollback strategy. Classify unprovable restoration as fail-closed and require operator review.

### 3.3 Synthetic fixture design

- 2 tenants: `tenant_alpha`, `tenant_beta`; 2 users with roles; 2 named publications per tenant; overlapping doc/source IDs across tenants intentionally.
- 3–5 synthetic docs per tenant with explicit chunk IDs, taxonomy, evidence quote and source URL/metadata. Embed expected answer and intentionally conflicting negative text.
- FAISS gen A signed and ACTIVE; gen B staged and then ACTIVE; tampered gen C; missing index; invalid signature; altered tenant/digest. Keep test signing key explicitly disposable and **not** a production secret.
- Neo4j graph with tenant labels/property and 2 known edges; mutate one edge and deliberately fail before FAISS commit. Verify generation A readback and B absence after compensation.
- Fault hooks: kill worker at acquired claim, after graph write, before receipt commit, after receipt commit before in-memory FAISS reload, during long SSE response, during rollback.
- Test data must be generated locally, not real fund/customer documents; manifest SHA-256 recorded in evidence.

## 4. Retrieval, citation and verified answer semantics

### 4.1 Vector/LLM boundary

`VerifiedVectorBridge` must only wrap the active verified retriever, refuse direct write/unsafe attributes, and reject cross-tenant vector hits or user-scope mismatch before reranking/synthesis. A semantic cache/fast-path/graph answer cannot bypass this receipt check. Verify asynchronous background tasks do not complete with stale data after HTTP request cancellation.

### 4.2 Source provenance schema (proposed response contract)

Keep API schemas backward-compatible where possible; introduce typed metadata only when needed. The response should expose, or a secured internal audit record must capture:

`request_id`, `user_id` (internal only), `tenant_id` (internal), `active_generation_id`, `receipt_id`, `manifest_digest`, `source_id`, `document_id`, `chunk_id`, `taxonomy_path`, `source_version`, `citation_display_label`, `citation_page` when applicable, and `authority_checked_at`. Never echo raw JWT, secrets or private operational SQL IDs to public client unless permitted.

**Citation gate:** Every exposed citation corresponds to an authorized chunk present in the signed manifest / tenant corpus and preserved through synthesis. Placeholder, cross-tenant, missing-document or made-up citation is a P0 failure. Because enforced mode currently disables raw `/api/files`, do not emit broken “click to open” links or re-enable unrestricted files; choose a non-clickable provenance card for pilot, or design a receipt-bound document gateway as a separate authorized feature.

### 4.3 SSE / request lifetime

`VerifiedOrchestratorFence29` currently buffers up to 4 MiB / 4096 frames as a bounded fail-closed mechanism. Verify no answer chunk is delivered **before the post-generation authorization check**; re-check while emitting frames. On authority change, stream must stop without later leaking answer chunks. If a partial answer was already emitted before a mid-stream rollback, document that the earlier authorized content cannot be retracted; release guarantee is **no further stale delivery**, not retroactive erasure. Client must show an interrupted/invalidated state, not “complete.”

## 5. HTTP security and multitenancy test design

Use FastAPI `TestClient` or `httpx.AsyncClient` with lifespan and actual synthetic DB auth; supplement with real service tests. Maintain a table of (route, method, mode, identity, tenant, expected status, content/body hash, data side effects). Cover:

- Anonymous login vs authorized login, expired session, revoked token, malformed token, active/inactive user and role mismatch.
- Explicit tenant mismatch in header/body, two concurrent sessions, same source/document ID in different tenants, cross-tenant `publication/status/{work_id}`.
- URI obfuscation: duplicate slash, traversal/dot segments, percent encoding, `HEAD`, `OPTIONS` preflight, query-string variations, static asset filename injection.
- Legacy `QUERY_ENGINE=legacy/canary/shadow` under enforce must fail; off-mode must retain existing semantics without converting them into acceptance evidence.
- Request/response size bounds, malformed JSON, cancellation, stream interruption, provider outage, receipt suspension/revocation.
- Verify no protected data appears in server logs, trace IDs or error details, and no direct `/files` alias leaks raw corpus bytes.

**Security release criterion:** zero cross-tenant reads/mutations, zero unreceipted answers, zero valid legacy route bypasses. Code-level presence of middleware is not proof; only actual HTTP tests count.

## 6. Frontend and product behavior

**Pilot navigation** should expose only: sign-in/sign-out, Q&A, citations/provenance panel, last publication status if authorized, and clear read-only labeling. Existing broad dashboards, ingestion, graph explorer, correction approval and aggregation buttons must be hidden/disabled in verified pilot rather than emitting confusing 503 loops. Avoid claiming complete provenance when a source is metadata-only.

**Client states to specify and test:** no authorized corpus, suspended publication, expired session, provider down, malformed response, retrieval denied, request timeout, cancellation, no results, success with 1–N citations, SSE revoked mid-stream. For errors present a concise user-facing reason and opaque troubleshooting ID; no raw stack trace.

**Browser acceptance:** Chrome/Firefox where feasible, responsive mobile viewport, keyboard-focusable controls, no broken API endpoints, no accidental stale result after navigation, clean production build, CSP/CORS appropriate to local hosting and no client API secret.

## 7. Verification and qualification design

### 7.1 Test layers

| Layer | Mechanism | Inputs | Exit criteria |
|---|---|---|---|
| L0 Source | Python 3.11 compile/import, Alembic DAG audit, frontend static build | exact clean Git SHA | zero syntax/import errors; all module paths resolve |
| L1 Unit | Pytest suites Wave28–31, guards/DB/perimeter/evidence | fake PG/FAISS for unit only | no failing or silently skipped P0 tests |
| L2 SQL/graph/index integration | Disposable PostgreSQL 16, Neo4j 5.24, real small FAISS index | synthetic tenants, signatures | true atomicity/concurrency/readback |
| L3 API | FastAPI with actual auth and initialized app lifespan | signed active corpus | positive/negative HTTP/SSE including revocation |
| L4 UI | Node tests, Vite build, Playwright or browser smoke | local API, synthetic credentials | end-to-end Q&A/citation and blocked flows |
| L5 Operations | failure injection, restart, restore, duration/latency | disposable release candidate | rollback and predictable failure behavior |
| L6 Pilot staging | operator-approved isolated deployment, canary, SLO | release image and signoff | release owner acceptance; **not feasible without an environment** |

### 7.2 Test commands and boundaries

From repository root (Python 3.11 venv activated, deps installed), with evidence outside the Git checkout:

`python -m tools.amc_release.collect_local_evidence31 --repo . --full-backend --frontend`  
`python -m tools.amc_release.qualification31 --repo . --out ../mvp-evidence/source.json`  
`python -m tools.amc_release.mvp_evidence_gate31 --checkout . --evidence-dir ../mvp-evidence --out ../mvp-evidence/result.json`

For real database migration, use `backend/scripts/alembic_dag_preflight.py` then `python -m alembic -c alembic.ini upgrade head` from `backend/`, with *both* `DATABASE_URL` and `AMC_MIGRATION_DATABASE_URL` set to the identical disposable PG URL. If Docker is absent, L2–L5 remain **BLOCKED**, not PASS. The evidence collector itself **does not run infrastructure validation**, as stated in its header.

### 7.3 Evidence schema and provenance

Per gate: `gate`, exact 40-character `commit_sha`, `status=PASS/FAIL/BLOCKED`, real UTC `observed_at`, `environment` (OS, Python, Node, service versions), `inputs_hashes`, `evidence_refs` (nonempty, redacted, immutable), `test_counts`, `failure_ids`, `operator_reviewer` and source log/JUnit SHA-256. Existing `mvp_evidence_gate31.py` checks only a subset; expand it if necessary to enforce missing provenance dimensions. A redacted team report may be committed, but raw service logs and secrets remain outside Git.

**Exact-SHA hazard:** If test summary is later committed to same branch, the branch SHA changes. Therefore commit code first, re-run tests on the committed SHA, keep raw evidence out-of-tree, and put summary hashes in PR comment or externally approved store. If a final docs-only commit is unavoidable, repeat at least source-level qualification and identify the tested code SHA explicitly.

### 7.4 Gate decision vocabulary

`PASS_SOURCE_ONLY` = no live-service claims.  
`PASS_RUNTIME_LOCAL` = real disposable local service acceptance, not staging/UAT.  
`BLOCKED_DEPENDENCY` = prerequisite unavailable, never silently skipped.  
`FAIL_SECURITY` = provable unsafe behavior; halt release and prioritize fix.  
`EVIDENCE_PRESENT_REQUIRES_INDEPENDENT_REVIEW` = schema complete but release not automatically approved.  
`MVP_ACCEPTED` = only after independent owner/governance/engineering review and actual staging/operational criteria; never automatically emitted by an offline script.

## 8. Operations, security and rollback runbook contract

- **Config freeze:** exact app/container checksum, flag values, DB migration target, verified FAISS root, Neo4j URI, allowed CORS origin. Secrets never printed in logs or in the handoff.
- **Start:** disposable PostgreSQL and Neo4j health checks → migration DAG and upgrade → real fixture publication through operator path → verify active receipt, graph and signed FAISS → start app `enforce` with `QUERY_ENGINE=v2` → authenticated smoke.
- **Readiness:** distinguish HTTP process liveness from ability to serve signed tenant data. Report degraded readiness when index/PG/provider is unavailable.
- **Rollback:** stop new publication; suspend authority; confirm old graph/FAISS preimage; reconcile work/receipt journal; only re-activate exact proven generation; verify authenticated Q&A and no stale content. Document restoration limits and on-call owner.
- **Recovery:** repeated crash at each durable boundary must either converge to one verified ACTIVE corpus or deny serving and leave auditable intervention. Do not force-activate by editing SQL rows manually.
- **Audit:** track who published/approved, how work was derived, hashes and receipt, duration, errors, rollback reason and completion status; verify retention and redaction.
- **No “release to production” automation** in this branch; GitHub Actions budget preserved. A deployment requires separate authorization, code owner review and environment availability.

## 9. Design decisions / alternatives

| ADR | Choice | Rationale | Revisit trigger |
|---|---|---|---|
| ADR31-01 | Controlled read-only verified Q&A pilot | Reduces ingress and mutation attack surface, smallest useful demonstration | Product owner requires interactive ingestion |
| ADR31-02 | PostgreSQL authoritative journal | Cross-worker row locks/unique constraints required | Only after alternative is proven transactionally equivalent |
| ADR31-03 | Neo4j + filesystem as external effects | Cannot share SQL transaction; durable effects/compensation mandatory | Different graph/index engine chosen |
| ADR31-04 | Signed immutable FAISS snapshots | Prevent silent index substitution and stale cache exposure | Another immutable vector backend proven |
| ADR31-05 | Exact route allowlist in enforce | Avoid legacy or unreviewed endpoint bypass | Each new route requires review, auth and tests |
| ADR31-06 | No schema mutation at verified app startup | Migration must be controlled and auditable | Operational migration process designed |
| ADR31-07 | Local-only tests until infrastructure exists | No spend and no current CI capacity | Disposable staging provisioned |
| ADR31-08 | Source evidence never equals UAT | Prevent optimistic release assertions | Never; permanent principle |

## 10. Implementation file map and review checklist

### Existing relevant files to inspect before editing
- `backend/app/main.py`; `backend/app/core/database.py`; `backend/app/core/db_runtime31.py`; `backend/app/api/pilot_perimeter31.py`; `backend/app/api/routes/legacy_guard31.py`.
- `backend/app/api/routes/query.py`, `chat.py`, `auth.py`, `files.py`, `docs.py`, `graph.py`, `taxonomy.py`, `ingest.py`, `governance.py`; `backend/app/api/deps.py`.
- `backend/amc_publication/active_authority28.py`, `request_fence29.py`, `vector_bridge28.py`, `serving27.py`, `ingestion_boundary29.py`, journal/worker/recovery source; `backend/alembic/versions/013_*` and `014_*`.
- `tools/amc_release/collect_local_evidence31.py`, `run_wave31_tests.py`, `qualification31.py`, `mvp_evidence_gate31.py`, `ops/validation/compose.wave31.local.yml`.
- `backend/tests/test_verified_legacy_route_gates31.py`, `test_pilot_perimeter31.py`, `test_db_runtime31.py`, `tools/amc_release/tests_wave28-31/`, `mf-context-engine` frontend.

### Change-control checklist
1. State requirement ID and original failing observation before code change. Prefer smallest verified patch, no wholesale rewrite.
2. Add negative **and** positive tests for each corrected ingress/authority boundary. Include explicit off-mode compatibility.
3. Any schema change adds Alembic migration and tests, never only ORM `create_all`. Any new serving path adds receipt checks and tenant auth.
4. Evidence log redaction, known error shape, user-visible behavior and rollback path must accompany behavior change.
5. Commit coherent fixes to same feature branch without force/rebase; report exact SHA and decision. Keep PR #13 draft.

## 11. Open design questions requiring explicit decisions

- **Q1 Product:** Does read-only verified-publication Q&A satisfy the first MVP user value, or is user ingestion indispensable? If latter, this spec becomes a restricted pilot only.
- **Q2 Provenance:** Should pilot citations remain metadata-only, or is a receipt-bound source-document download/view endpoint required?
- **Q3 Tenancy:** Is one controlled tenant sufficient for the pilot (while isolation is still tested with two), or must true shared multi-tenant operations be demonstrated?
- **Q4 Operations:** Who is authorized to run initial publication, revoke, recover and sign a corpus? No customer-facing self-publication in current route allowlist.
- **Q5 Observability:** What actual performance/SLO thresholds can the intended host sustain? Define after measurement, not from model guesses.
- **Q6 Staging:** Is a short-lived isolated staging deployment available for final acceptance? Until then, `MVP_ACCEPTED` remains blocked.

These are decision items, **not** permission to skip safety tests. Agent should assume the narrower pilot and continue implementation; flag choices explicitly for product owner.

---
**Architecture verdict:** Design is implementable without new enterprise services, but **end-to-end qualification still requires a real disposable database, graph engine and index on a running machine**. No amount of source-only testing can validate cross-system effects, live race safety or release operations.
