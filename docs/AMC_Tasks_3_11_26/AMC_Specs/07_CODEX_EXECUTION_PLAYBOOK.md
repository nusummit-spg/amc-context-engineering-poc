# 07 — Local Codex Execution Playbook and CTO Review Handoff

## 1. Ground rules

- Work only on a feature/remediation branch forked from locked baseline `e3c74e0`. Never rewrite `main` or `amc-dev` directly without normal review.
- No direct production execution, deployment, data deletion, password rotation or canonical-data mutation without authorized human operational approval.
- Treat repository source, documents and generated examples as proprietary unless their owners explicitly permit sharing; do not include source documents, database copies, secrets, private logs or full customer responses in public tickets.
- Prioritize one complete vertical slice (source→typed execution→response→proof→feedback→repair→release) over extending several agent implementations.
- Avoid adding libraries or microservices without a measured failure they resolve; prefer Python/FastAPI, Pydantic, SQL (SQLite/DuckDB as justified), Neo4j, FAISS, React.
- Do not silently weaken the PDF/TXT working path while fixing CSV.

## 2. Execution wave plan (parallel where dependencies allow)

### Wave 0 — Safe containment and reproducibility
`G01`, `G02`, immediate `G10` tasks T01–T03/T09–T11, initial `G14` task T01.

Deliver: baseline traces, captured gold set, access-control matrix, disabled pending-patch serving and canonical auto-promote, clean build config. No data migrations or public rollout.

### Wave 1 — Canonical tabular vertical slice
`G03` → `G04` → `G05` and first 40 exact source-row lookup tests from `G13`.

Deliver: read-only versioned dataset, exact NAV and AAUM by key/date/period, source-row proof, controlled activation. Verify 16,245 declared rows and 22 chunks without assuming validation passed.

### Wave 2 — Routing and answer correctness
`G06`, `G07`, AMC compatibility in `G08`; extend to 200-case CSV gold and 50 PDF/TXT controls.

Deliver: typed plans, fail-closed financial routing, real citations, accurate trace and confidence policy; canary only after gate.

### Wave 3 — Feedback/Repair system integration
`G09`, remaining `G10`, `G11`, plus `G12` regulatory lifecycle.

Deliver: immutable evidence, safe triage, authorized review, staged mutation, outbox retries, publication receipt and rollback; no approval-by-confidence.

### Wave 4 — Operational quality and release evidence
Complete `G13`, `G14` and remaining backlog. Audit security, correctness, load/recovery and repeatability. No broad production launch without signed release verdict.

## 3. How to run bulk Codex tasks safely

The 196 tasks are deliberately grouped into independent **goals**, not micro-prompts. Codex can take batches of 10–14 tasks for one goal after prerequisite gates. Suitable early work batches:

- Batch A: `G01-T01`–`G01-T14` plus `G14-T01` for baseline and reproducibility.
- Batch B: `G02-T01`–`G02-T14` plus `G10-T01`–`G10-T03` for containment (no canonical mutation).
- Batch C: `G03-T01`–`G03-T14` with steward review for metric decisions.
- Batch D: `G04-T01`–`G04-T14` after source semantics are signed.
- Batch E: `G05-T01`–`G05-T14` for typed financial query engine.
- Batch F: `G06`/`G07` (separate PRs, parallel shared contract review).
- Batch G: `G09`/`G10`/`G11` sequential integration PRs after safety policy is secured.
- Batch H: `G12`/`G13`/`G14` with staged verification and release evidence.

**Avoid** combining destructive migrations, authentication changes and repair auto-promotion changes in one unreviewable PR. A bulk slot may contain many tasks, but it should still produce an auditable logical change set with a rollback path.

## 4. Copy/paste primary Codex instruction

```text
You are implementing the NuSummit AMC Context Engineering CTO Remediation Blueprint.
Work from branch SHA e3c74e011d70e2921b8e0ee2287e6fc71cb30bb0.
Read README_START_HERE.md, 01_SOURCE_REVIEW_AND_ROOT_CAUSES.md,
02_TARGET_ARCHITECTURE_AND_CONTRACTS.md, 03_CSV_EXCEL_FINANCIAL_CORRECTNESS_SPEC.md,
04_AMC_FEEDBACK_REPAIR_LIFECYCLE_SPEC.md, 05_ASSURANCE_SECURITY_RELEASE_GATES.md,
06_GOALS_AND_TASKS.md and tasks.csv.

Current batch: <insert goal IDs/task IDs>.

Implement the full batch autonomously within the existing architecture.
Preserve the three logical modules AMC Core, Feedback and Repair.
Do not alter production or mutate live datasets. Use fixtures and an isolated
staging database. Never let pending/model-proposed patches influence user answers.
Financial numbers must come from approved typed source data, with exact date,
metric grain, row references and deterministic computation; no generative fallback.
Protect sensitive routes by verified identity and server-derived authorization.

For each task:
  1. inspect existing code and nearby tests;
  2. implement minimal necessary changes with tests;
  3. run named unit, contract, integration and golden regression checks;
  4. document before/after behavior and risk;
  5. record actual test logs and source hashes;
  6. document safe rollback and any blockers rather than inventing success.

Deliver a PR-ready change log mapping task IDs to file diffs and proof. Include
incomplete tasks, direct test commands, passing/failing cases, ADR updates,
security findings and release classification (PASS/REVIEW/BLOCK).
Do not mark a test passed if not executed. Do not produce simulated benchmark
scores labelled as actual RAG quality. Do not deploy without explicit approval.
```

## 5. Output structure requested from Codex at each batch

```
artifacts/<batch-id>/
  changes.md             # task ID → summary and files changed
  verification.md        # test command, environment, result, screenshots as appropriate
  benchmark.json         # actual live run results, date, corpus/model versions
  security_results.json  # applicable route tests, auth and tenant findings
  data_reconciliation.json # if ingestion/metric change
  release_gate.json      # PASS / REVIEW / BLOCK with reason and hash refs
  rollback.md            # actual tested restoration steps
  gaps.md                # open blockers, no concealed failures
```

For implementation PR: keep source code and tests in repository, store generated runtime evidence in sanitized CI artifacts. Add a small `README` explaining how to reproduce the output locally.

## 6. Gate review matrix (CTO audit on a follow-up)

| Checkpoint | Files / proof expected | Non-negotiable result |
|---|---|---|
| A — Containment | route inventory, auth tests, patch policy tests | no default-admin, anonymous sensitive route or pending-truth override |
| B — CSV | schema dictionary, manifest checksum report, gold cases | consistent typed numeric result and source row; fail-closed errors |
| C — AMC/Feedback/Repair | evidence packs, state transitions, approval audit, rollback drills | no unapproved promotion and no phantom `APPLIED`/`RESOLVED` |
| D — Production readiness | fresh checkout build, CI runs, load/SLO report, incident playbook | release candidate gates pass against exact SHA/data versions |

When requesting the next audit, supply the PR URL, release SHA, active dataset/corpus manifest, test output, sanitized failed query examples, CI logs and any rollout notes. The CTO review will compare each promised acceptance criterion against those artifacts, not against claims in docs.

## 7. GitHub issue structure

Create one epic issue per goal, 14 task issues or checklist items for its work. Suggested labels: `goal:Gxx`, `priority:P0/P1`, `module:amc/feedback/repair/shared`, `status:todo/doing/review/blocked/done`, `risk:security/correctness/reliability`, `needs:steward-signoff`, `test:gold/live/security`. Use `tasks.csv` for import or scripting; no issue creation was performed as part of this assessment.

## 8. Sequence exceptions / stop rules

Stop a batch and mark **BLOCK** if: the source/metric grain is ambiguous and affects financial totals; auth cannot be verified; tests show cross-tenant leakage; a proposed repair bypasses approval; stored artifact contains unauthorized sensitive data; or a migration lacks a recoverable old snapshot. Continue non-blocking code cleanup in separate isolated PRs, but do not force publication.
