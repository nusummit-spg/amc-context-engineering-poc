# 05 — Security, Assurance Harness, Operations and Release Gates

## 1. Release philosophy

Trust should be earned through executable evidence. README badges, successful starts, 100% synthetic scores and the existence of test files are not sufficient. A release is the exact commit + immutable dataset/corpus version + configurations + model versions + executed gate outputs.

## 2. Urgent security changes

**P0: protect before expanding functionality.**

1. Require a verified principal for all sensitive APIs. Assign least privilege per route, operation, and resource. Allow anonymous health check only where appropriate; redact internal information.
2. Replace `get_client_role(X-User-Role)` with identity-provider-/server-backed role resolver; do not default to ADMIN. Ignore/reject caller role headers for authorization.
3. Guard `POST /api/admin/users`, all mutation paths, query/graph/documents/ingest, compliance analytics/reports, governance and repair endpoints with `CurrentUser` and explicit policies.
4. Remove predictable default credentials, default Neo4j passwords from production manifests, password reflection in responses, and insecure dev secret fallback in any non-local environment; rotate any credential that might have been used beyond test environments.
5. Enforce tenant and document ACL at physical data access (SQL, graph, FAISS payloads, source files), not only in UI or last-step postfilter. Deny access if principal/tenant missing for private data.
6. Fix quota enforcement: actor/tier derived from verified identity, not `X-User-ID` or `X-User-Tier`; secure reverse-proxy IP handling.
7. Secure internal service calls (JWT/mTLS as environment supports), enforce inbound scope, request size, timeout, rate, idempotency, service identity and operation allowlist.
8. Static content and source downloads must verify resource ownership/classification; respond with consistent 404/403 without leaking location.
9. Uploaded CSV/Excel/PDF parsing occurs with size, format, encoding, antivirus/sandbox as appropriate and zip-bomb/injection checks.
10. PII handling requires explicit retention, redaction, encryption-at-rest and access log policy; do not persist raw feedback/source snippets in overly broad logs.

**Security-test examples**: missing token on every API class, header spoof, role escalation, cross-tenant retrieval, protected source download, anonymous ingestion, arbitrary Cypher/SQL attempts, path traversal, user account management, false approval, malicious CSV value, prompt injection from feedback, replayed event and stale token.

## 3. Assurance Harness — test taxonomy

| Gate | Purpose | Required evidence |
|---|---|---|
| SEC | AuthN/AuthZ, tenancy and service identity | DAST/negative API tests, SAST, secrets and dependency scan, routes matrix |
| DATA | Source completeness, metric grammar, version | row and checksum parity, duplicate/null report, schema registry approval |
| RAG | Retrieval, citation, response safety | gold query report by intent, claim-level source support, false-claim analysis |
| NUM | Exact NAV/AUM/aggregate correctness | typed-value parity vs independent steward gold; units, dates, filters |
| FB | Feedback ownership, classification and triage | confusion matrix, dedup and escalation SLA tests, mock/passive safeguards |
| REP | Repair promotion and rollback | permission evidence, dry-run diff, idempotency, pre/postcondition receipts |
| REG | Regulatory temporal correctness | source applicability/effective date/supersession cases |
| OPS | Load, resilience and recovery | latency histograms, cold/warm/stream, chaos tests, backup/restore |
| UX | Chat/Compare/CSV provenance rendering | browser E2E screenshot/DOM assertions, accessibility, source links |

### Independent benchmark methodology

- Build and freeze a stratified evaluation set **before** tuning and never insert expected answer into the prompt/context. Label by a separate data steward.
- Keep dev/test/holdout partition; split across entities, documents and date ranges to avoid train/test leakage.
- Evaluate same query under traditional vector, current v2 and new typed-query route in shadow with identical corpus versions.
- Score separately: numeric exact match, recall@k of **gold source rows**, retrieval precision, citation support, completeness, answer correctness, abstention appropriateness, temporal correctness, security and latency.
- Compare adverse effects on PDF/text controls; the CSV fix must not degrade current strengths.
- Report confidence intervals for sampled metrics and absolute failure counts, especially zero-tolerance categories. Large score changes require human error analysis, not automatic success labels.
- RAGAS or NLI may complement, not replace, exact numeric tests, independent labels and human reviewer calibration.

### Baseline evaluation cohort (minimum)

| Cohort | Count | Key pass condition |
|---|---:|---|
| CSV exact lookups (NAV/AAUM/ISIN) | 40 | exact typed match, source-row anchor, approved date |
| CSV filters, comparison, aggregation and distribution | 75 | correct normalized filters, grouping, units, denominators |
| CSV time/grain ambiguity and abstention | 40 | fail-safe or explicit clarification, never fabricate |
| CSV + regulatory/PDF mixed | 25 | verified numeric plus authoritative source clause |
| CSV adversarial/no match | 20 | safe rejection or no match; no unauthorized data |
| PDF/text control tests | 50 | no statistically meaningful regression |
| Feedback/Repair lifecycle | 40 | workflow/correctness/security and rollback assertions |

Coverage is a proposed start, not evidence that thresholds are met.

## 4. Production gate targets (proposed; calibrate on pilot)

**Release blocking:**
- P0/P1 security vulnerabilities: **zero open P0**, risk acceptance required for remaining P1; cross-tenant leaks **zero**.
- Financial critical cohort: **100% exact** normalized NAV/AUM and signed formula answers on designated critical cases.
- Regulatory critical cohort: **zero unsupported material regulatory claims** in reviewed sample.
- Source completeness: **100% of expected rows accounted for** (accepted + explicit quarantined); no unaccounted source/chunk gap.
- Release approval: **100% of active repairs have valid authorizer, test and postcondition receipt**.
- Gated suite pass: all tests designated release-blocking pass against exact commit/data version.

**Operational SLOs (initial candidates, not current claims):**
- Structured-query availability ≥99.9% on target deployment (exclude approved maintenance only under clear rules).
- p95 structured-query response ≤2 s and p95 document answer ≤10 s at agreed representative load; calibrate after measured baselines.
- Correlation completeness ≥99% for query→evidence→feedback→repair events; 100% for release-gate receipts.
- Bounded resource usage: specify max memory and concurrent model calls from profiling; enforce timeouts and queue limits.
- Track p50/p95/p99 latency, cold starts, cache hit and correctness separately; never substitute a hardcoded 2ms trace for measurement.

## 5. Full test layers

1. **Unit**: metric registry, type conversion, as-of comparison, identity mapping, intent parsing, policy, evidence matching, patch transitions.
2. **Property-based/metamorphic**: reorder rows, split/rejoin chunks, duplicate a row, change CSV line endings, rename labels, random nulls, shift dates, remove data. Results should remain invariant or fail explicitly per policy.
3. **Contract**: OpenAPI schema, event schemas, consumer compatibility, tenant-bound IDs, idempotency and validation errors.
4. **Component**: SQL transaction/rollback, graph query, vector scope and rerank, feedback adjudication, repair staging.
5. **Integration**: SQL+graph+FAISS source parity, user ownership, service-to-service calls, release pointer switch.
6. **End-to-end**: full authenticated browser/chat journey, wrong answer report, review, correction and post-release answer.
7. **Chaos/recovery**: Neo4j down, SQL down, index missing, Redis down, network timeout, duplicate event, partial stage and failed promote.
8. **Security**: 401/403 matrix for all routes, privilege/header spoof, tenant cross-access, prompt injection, unsafe query and file handling.
9. **Performance**: cold and warm load, p95/p99, memory leak, vector scan cost, lifecycle worker concurrency, startup readiness.

## 6. Observability model

For each query: `trace_id`, `response_id`, `user_hash`, `tenant_id`, `intent`, `plan_hash`, `serving_engine`, `source_versions`, `dataset_version`, `model_id`, `route_decision`, `cache_namespace`, `relevant_row_count`, `evidence_source_ids`, `claim_verdicts`, actual elapsed times, input/output tokens and cost estimate. Do not log raw secrets or unrestricted PII.

For each ingestion: source hash, schema, expected/parsed/valid/rejected counts, stage timings, row checksum report, graph/vector activation receipts, retries and active-pointer generations.

For each feedback and repair: issue ID, evidence completeness, classifier verdict, root cause, proposal ID, approval actor, base/target version, validation report, commit receipt, rollback status, user notification.

Dashboards: wrong-answer by intent/metric, unsupported-claim rate, CSV completeness, source staleness, pending corrections, rollback incidents, failed cross-module messages, p95, cold start, cost/answer, token consumption and release-candidate gate status. Establish alert thresholds with pilot baselines.

## 7. CI/CD and deployment

- New GitHub Actions workflow: build/lint/typecheck, dependency and secret scan, unit/contract tests, integration stack, gold tests, browser E2E smoke, promotion/rollback chaos, SBoM and release artifact signing.
- Validate `docker-compose.yml` via `docker compose config` and actual clean build. Remove/refactor references to missing Streamlit and Dockerfiles; provide a supported dev Compose and an independently tested prod deployment topology.
- Pin core dependencies and model IDs; record schema versions and data manifests in release bundle. Check Python/Node supported versions in environment matrix.
- No startup task may mutate canonical graph or seed production content without a guarded migration operator action.
- Background schedulers: ensure one leader/worker, durable leases, no duplicate jobs under multi-process deployment.
- Database migrations: forward/backward compatibility, backup, restore drill, required schema checks and failure rollback.
- Use staged config, secret manager and network restrictions; tests must prove public ports have no privileged mutations.
- Shadow then canary rollout, using the same gold and live sampled outcomes; rollback by version pointer/config with time-bounded verification.

## 8. Release acceptance template

Every goal/PR should attach:

```
Change ID / goal / tasks:
Source base SHA / target SHA:
Dataset/corpus schema and version:
Risk classification / security impact:
Functional description and interface diff:
Exact unit/contract/integration/E2E test commands + results:
Gold benchmark before/after with failure cases:
Staging and production canary plan:
Reproducible evidence links/artifacts:
Rollback command and observed drill result:
Reviewer approvals and date:
Unresolved findings and documented risk acceptance:
```

## 9. Re-audit checkpoints

- **Gate A — Containment:** verify auth denial, no automatic canonical repair and no pending patch influence.
- **Gate B — CSV Alpha:** reconcile all source rows, prove typed queries on static 200-case dataset, no generative fallback for financial questions.
- **Gate C — Cross-module Beta:** verify feedback→repair state, approvals, immutable receipts, negative tests and rollback.
- **Gate D — Release Candidate:** deployment from clean checkout, full suite, SLO/load evidence, secure network configuration, data/version retention.

Do not claim a gate passed without attached logs and hashes produced in the target environment.
