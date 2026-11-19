# AMC Wave 4.0 — Implementation Status (against TDS-40 v1)

**Status: ENGINEERING CANDIDATE. Not release-ready, not UAT-accepted.** Branch `amc-dev-wave31-integration`,
commits `33375b3`, `7efbfcf`, `8fe6596`, `267ed04` (on top of `bf9adb7`). Nothing pushed, merged or deployed.
The design documents (TDS-40, GP-40, task tracker) are on branch `docs/wave40-enhancement-plan`.

Architecture is unchanged: the FastAPI monolith, React, PostgreSQL, Neo4j, signed FAISS, publication journal,
two-person approvals and the pilot perimeter. Every Wave 4.0 behaviour is behind a flag that defaults to off.
With every flag off, Wave 3.1 behaviour is unchanged (tested).

## 1. What is implemented

| Enh. | Implemented | Key files |
|---|---|---|
| **E1** Verified structured data plane | Staging with chunk-manifest reconciliation; exact scaled-integer storage; Ed25519-signed manifest; two-person-approved activation in one SQL transaction under the existing scope claim; rollback = approved re-activation; verified serving (pin, prove signature + content hash, run, re-check) | `amc_publication/fin40.py`, `fin_query40.py`, `structured_serving40.py`, Alembic `016` |
| **E2** Canonical identity + metric registry | AMFI scheme code = plan/option; AAUM at PLAN_OPTION grain (data-verified); plan/option rule table; metric registry v1 (7 metrics) whose hash is signed into each dataset manifest, so dataset approval covers it | `fin40.py` |
| **E3** Routing + numeric-safe answers | Deterministic router (STRUCTURED / DOCUMENT / ABSTAIN / CLARIFY), Indian FY quarters, AMC matching that ignores common words; server-rendered tables with Indian digit grouping; no LLM for numbers; numeric guardrail for document answers (stream holds chunks, then releases guarded text); additive response fields | `app/retrieval/intent_router40.py`, `composer40.py`, `structured_path40.py`, `orchestrator.py`, `models/query.py` |
| **E6** Residency + embedder binding | Provider/region allowlist and fallback refusal at startup; provider re-check and PII scrub on every outbound call; embedder identity signed into FAISS manifests and compared before hits are released | `app/core/provider_policy40.py`, `llm.py` (4 lines), `amc_publication/embedder_identity40.py`, `faiss_artifacts.py`, `faiss_reader27.py`, `vector_bridge28.py`, `vector/client.py` |
| **E7** Pilot feedback | `POST /api/feedback/v40`, append-only, bound to the caller's own evidence; PII-scrubbed comment; offline export | `amc_publication/evidence40.py`, `app/api/routes/pilot40.py`, `operator_cli feedback-export`, Alembic `017` |
| **E9** Evidence + readiness | Append-only `query_evidence_v40` written in the fence after the final authority check and before release; the answer is withheld if the row cannot be written; `GET /api/ready` | `request_fence29.py`, `evidence40.py`, `pilot40.py`, `pilot_perimeter31.py` |
| E10 (partial) | Fixed `tabular/executor.py` AttributeError raised on every call (`PlanIntent.MAX`) | `app/tabular/executor.py` |

Required migration head is now **`017_query_evidence_feedback_v40`** (`db_runtime31`, its message and the pinned
tests moved together, per ADR31-09).

## 2. Deviations from TDS-40 (deliberate; update the spec)

1. **`fin` activation is its own transaction, not a third effect inside the FAISS/graph journal.** All `fin` rows
   are in PostgreSQL, so activation (signature check, approval, receipt, pointer switch, retire previous) is one ACID
   transaction serialized by the existing `_claim_scope(tenant, "fin_dataset")` row lock. Coupling it to the
   document-corpus journal would have forced a dataset re-stage on every corpus publication, without adding safety.
   A `publication_work_v2` row (status `published`) is still written for audit.
2. **There is no `fin_entity_alias` table yet.** AMC and scheme resolution uses the pinned version's own names. When
   more than one entity matches, the result is CLARIFY, never a guess. A steward-approved alias table remains open.
3. **The metric registry is approved together with each dataset** (its hash is in the signed manifest), not through a
   separate registry activation flow.
4. **Migrations:** 016 (`fin`) and 017 (evidence + feedback). The spec's 018/019 are not needed for what was built.
   019 (regulatory catalog) belongs to E4, which is not started.
5. **Additional flags** beyond TDS-40 §5.1: `AMC_NUMERIC_GUARD`, `AMC_PROVIDER_POLICY`, `AMC_EMBEDDER_BINDING`.
6. **AAUM periods are stored as date ranges** (`2026-01-01..2026-03-31`), not as `YYYYQn`. This avoids the
   calendar-vs-financial-year ambiguity, which the router resolves explicitly or by asking.

## 3. Pilot configuration (illustrative)

```
AMC_VERIFIED_SERVING_MODE=enforce
AMC_FIN_PLANE=on            AMC_NUMERIC_GUARD=on        AMC_QE_POSTGRES=on
AMC_EMBEDDER_BINDING=on     (republish FAISS generations first, so they carry an embedder identity)
AMC_PROVIDER_POLICY=on      AMC_LLM_PROVIDER_ALLOWLIST=<chosen in-region provider>
                            AMC_LLM_REGION=<declared region>   AMC_LLM_REGION_ALLOWLIST=<approved regions>
AMC_PILOT_FEEDBACK=on|off   (product decision)
AMC_PILOT_TENANTS=tenant_alpha
DATABASE_URL at Alembic head 017
```

**Operator flow for fund data:** `fin-stage` → `fin-subject` → two approvers sign with
`amc_publication.approvals31 sign` → `fin-activate` → `fin-status`. Rollback is `fin-activate` of the previous
version, with a fresh approval.

## 4. Test evidence (this Windows machine, disposable local services, synthetic tenants)

| Suite | Result |
|---|---|
| New unit tests: `test_fin_plane40` (33), `test_structured_path40` (41), `test_provider_policy40` (21), `test_evidence_feedback40` (10) | 105 passed (SQLite with FK enforcement) |
| Live PostgreSQL 16 + Neo4j 5.24: `tests/live40` + live31 migration, FAISS serving, HTTP/SSE enforce matrix | **179 passed, 1 pinned xfail, 0 failed** |
| Wave 2.8–3.1 tool runner (`run_wave31_tests`, at `8fe6596`) | 272 cases: 268 passed, 3 failed, 1 skipped. The 3 failures are the known Windows symlink-privilege tests (`WinError 1314`), the same as the Wave 3.1 baseline |
| Real-data check | 16,245/16,245 rows reconciled, 0 rejected, 1,434 float artefacts rounded and counted; top-5 AMC AAUM equal to an independent `csv` + `Decimal` computation; PostgreSQL and SQLite results identical for all 6 intents |

**Pre-existing failures (identical on `bf9adb7`, not caused by this work):** 6 tests:
- `test_aggregation_integration::test_fast_path_differentiates_q1_and_q2`
- `test_category_aggregation::test_fast_path_category_interception`
- `test_configurable_enhancements` × 2 (missing GROQ_API_KEY)
- `test_parallel_execution::test_parallel_graph_and_vector_retrieval`
- `test_plan_execution::test_corpus_wide_aggregation_reaches_cypher_without_entities`

Separately, 7 legacy `test_tabular_queries` tests now fail on real policy outcomes instead of crashing. The legacy
tabular path is off-mode only.

**Open, not explained:** `test_signing31` failed intermittently in 2 of about 11 large batch runs (two different
tamper tests). It was not reproduced in 8 further batch runs or in 12 isolated runs on each of the baseline and
this branch. The error text was not captured, so the cause (a Wave 4 change or environment I/O) is unknown.
Rerun with full output before treating `signing31` as green.

## 5. Not done (remaining TDS-40 scope)

- **E4** Regulatory corpus currency (in-force metadata, supersession lineage, migration 019, offline candidate job).
- **E5** Gold sets (GS-FIN 200 / GS-REG 120 / GS-MIX 30 / GS-ADV 50), `eval40` harness and the `answer_quality`
  evidence gate. All answer quality is **unmeasured with a real model and embedder**; tests use stubs and mocks.
- **E6 provider adapter:** no in-region provider adapter was written. That waits on decision D3. The policy works
  with any provider name in `llm.py`.
- **E8** Evidence viewer, and **E11** frontend: answer cards for `answer_kind`, feedback UI, readiness display,
  the pilot allowlist entries for the new routes, Playwright on 3 engines. **The current pilot UI does not yet render
  the new response fields specially:** it shows the markdown answer.
- **E10** Remaining: green default suite, facade modules, repo hygiene, SQLite Alembic chain, dependency split,
  Linux qualification run.
- **E12** Staging, pen test, CSCRF/DPDP records, canary/rollback rehearsal.
- **Organizational:** steward sign-off on O1–O5 and the metric registry, named key holders, decisions D1–D10.
- **Independent security review** of the boundary changes:
  - the perimeter additions
  - fence evidence and withholding
  - the provider policy
  - `fin` activation
