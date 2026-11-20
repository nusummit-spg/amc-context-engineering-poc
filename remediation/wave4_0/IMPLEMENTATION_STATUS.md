# AMC Wave 4.0 — Implementation Status (against TDS-40 v1)

**Status: ENGINEERING CANDIDATE. Not release-ready, not UAT-accepted.** Branch `amc-dev-wave31-integration`,
commits `33375b3`, `7efbfcf`, `8fe6596`, `267ed04`, plus the E5 and E11 commits (on top of `bf9adb7`). Nothing pushed, merged or deployed.
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
| **E5** Gold sets + harness (partial) | GS-FIN 200 and GS-ADV 50 **generated** by SQL over the approved snapshot (not the serving code, not an LLM), deterministic and hash-pinned; GS-REG / GS-MIX are DRAFT templates awaiting authors. `eval40` drives the live HTTP API as a pilot user, records request ids, and scores all 8 E5 metrics with its own number extractor, which is stricter than the guardrail: numbers that appear only in the question count as ungrounded. Citations are checked against the signed FAISS payloads; G11 `answer_quality` was added to `mvp_evidence_gate31`. The evidence record is written only on a full PASS from a clean checkout with the provider, model and embedder declared. No LLM judge. | `tools/amc_release/gold40.py`, `eval40.py`, `mvp_evidence_gate31.py`, `remediation/wave4_0/gold/` |
| **E11** Pilot UI (partial) | Typed answer cards: **STRUCTURED** (verified table with units in headers, Indian grouping, half-even rounding, as-of badge "AAUM Q4 FY26" / "NAV 29-Jun-2026", filter chips, exclusions, disclosure, "How was this computed?" drawer); **ABSTAIN** (typed message, suggestion chips); **CLARIFY** (option chips that fill the question box). Feedback thumbs + reason picker (build flag `VITE_AMC_PILOT_FEEDBACK`, hidden on a server 404). Readiness pill. Starter prompts from the tenant's own verified dataset (`GET /api/suggestions/v40`, ADR40-05). Stopped / interrupted streams are marked incomplete or withdrawn. Table semantics, ARIA labels and keyboard focus for the new parts. Playwright suite on 3 engines | `mf-context-engine/src/components/answer40/`, `src/utils/answer40.js`, `ChatTab.jsx`, `AssistantMessage.jsx`, `api.js`, `pilotSources.js`, `app/api/routes/chat.py`, `pilot40.py`, `pilot_perimeter31.py`, `tests/pilot40.spec.mjs` |
| E10 (partial) | Fixed `tabular/executor.py` AttributeError raised on every call (`PlanIntent.MAX`) | `app/tabular/executor.py` |

Required migration head is now **`017_query_evidence_feedback_v40`** (`db_runtime31`, its message and the pinned
tests moved together, per ADR31-09).

### 1.1 Defects the E5 harness found on its first run (fixed, with regression tests)

The first in-process run over GS-FIN scored `fin_exact_match` 0.9528, below the 0.99 bar. P0 cases were at 1.0. Ten
cases failed, from three causes:

1. **"Which 10 funds have the largest AAUM?" returned 5 rows.** The router read a count only after "top" or before
   "largest". It now also reads "which/list/show/the N funds|schemes|AMCs|categories".
2. **"Kotak Mahindra Asset Management …" asked "which AMC?"** It also matched "Mahindra Manulife". A candidate is
   now dropped when its words occur only inside a longer run of another candidate's name in the question.
   "Kotak and Mahindra Manulife" still asks.
3. **NAV by full scheme name asked "which plan?".** The resolver compared words as substrings: "it" matched inside
   "capital", "cap" inside "midcap". It now compares whole words and prefers the one plan/option whose full name is
   exactly the requested name.

After the fixes, both in process and over live HTTP, every gated metric is at 1.0 or 0. The exception is
`abstention_answerable` at 0.9955 (threshold 0.90): one prompt-injection question was refused, which the gold set
allows.

### 1.2 Defects found while building E11 (fixed)

1. **The chat stream dropped every Wave 4.0 field.** `/api/chat/stream`, which the pilot UI uses, rebuilt the
   final answer for its `hybrid` frame and kept only text, citations and metrics. The UI could therefore only show
   markdown. `_w40_answer_fields` now passes `answer_kind`, `structured_result`, `abstention`, `clarification`,
   gaps and provenance through unchanged.
2. **Stop left the turn "loading" forever.** The stream client swallowed the abort, so the stopped-answer branch
   never ran. The turn is now settled after the stream returns. It is shown as stopped (partial text kept,
   marked incomplete) or interrupted (withdrawn, no partial text).
3. **A dropped connection re-sent the question.** The client's reconnect created a new request and appended its
   text to the partial answer. It also fell back to the non-streaming path. Neither happens once any part of an
   answer has arrived; the turn is shown as interrupted.
4. **Picking "Calendar Q1 2026" asked the same question again.** The clarification options repeated the
   ambiguous "Q1 2026". Each option now names an exact month range ("January to March 2026 (calendar Q1
   2026)"), which the parser reads first.

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
7. **E5 gate counting:** `fin_exact_match_p0` (100%) is a separate metric. `abstention_correctness` is split into
   `abstention_should_abstain` (≥95%) and `abstention_answerable` (≥90%). Cross-tenant probes may be answered from
   the caller's own documents or declined: only leakage fails.

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
| **E5 in process:** `tools/amc_release/tests_wave40` (16 tests), including all 250 frozen GS-FIN + GS-ADV cases through the real router, executor and composer on the real dataset | 16 passed; every gated metric met |
| **E5 live HTTP:** `tests/live40/test_eval40_live.py` against real app, PostgreSQL 16, Neo4j 5.24, signed FAISS, signed + approved dataset; stub LLM and query embedder | 1 passed. 250 cases, all HTTP 200: fin exact match 1.0 (P0 1.0), routing 1.0, ungrounded numbers 0, citation validity 1.0, advice refusal 1.0, cross-tenant leaks 0. 250/250 evidence rows found by request id. Decision BLOCKED (GS-REG, GS-MIX, real model) |
| **E11 browser:** `tests/pilot40.spec.mjs` (9 tests) against `tests/live40/pilot_demo40.py`: real app in enforce mode, PostgreSQL, Neo4j, signed FAISS, signed and approved dataset, built pilot UI; stub LLM. One test replaces the stream response to simulate a dropped connection | **Chromium 9/9, WebKit 9/9 passed. Firefox not run:** Windows refused to execute Playwright's Firefox ("Permission denied", likely Smart App Control or endpoint policy) |
| E11 frontend unit tests (`npm test`) and Python parity tests (`PILOT_W40_API` = backend `W40_ROUTES`) | 42 passed; parity and perimeter tests passed |
| Release-tool suites `tests_wave31` + `tests_wave40` | all passed (the evidence-gate tests now include G11) |
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
- **E5 remaining:**
  - **GS-REG:** 120 cases authored by a Compliance SME; 3 templates are in place.
  - **GS-MIX:** 30 cases, which needs MIXED answers first (E3).
  - **Prompt injection inside documents:** not covered; needs a signed fixture corpus.
  - **SME rating round:** `sme-sheet`, then two raters and the kappa calculation.
  - **A run on the chosen provider and embedder (D3).** This is what actually measures answer quality. **Document-answer
    quality is still unmeasured:** with the grounded stub LLM, document grounding passes by construction.
  - **The 60-case smoke subset in CI** on every merge.
- **E6 provider adapter:** no in-region provider adapter was written. That waits on decision D3. The policy works
  with any provider name in `llm.py`.
- **E8:** the evidence viewer.
- **E11 remaining:**
  - **DOCUMENT provenance cards** (reference number, date, clause, in-force badge, superseded warning). These need
    E4 metadata.
  - **MIXED answers:** not produced by the backend yet.
  - **A Firefox run:** allow Playwright's Firefox on this machine, or run it on CI.
  - **A full WCAG 2.1 AA audit:** an axe or screen-reader pass. Only the new components got semantic markup.
  - **Hashing the screenshots and traces into release evidence:** they are kept under
    `mf-context-engine/reports/pilot40-artifacts`.
  - **UC1–UC6 depth:** the suite covers one representative case per use case.
- **E10** Remaining: green default suite, facade modules, repo hygiene, SQLite Alembic chain, dependency split,
  Linux qualification run.
- **E12** Staging, pen test, CSCRF/DPDP records, canary/rollback rehearsal.
- **Organizational:** steward sign-off on O1–O5 and the metric registry, named key holders, decisions D1–D10.
- **Independent security review** of the boundary changes:
  - the perimeter additions
  - fence evidence and withholding
  - the provider policy
  - `fin` activation
