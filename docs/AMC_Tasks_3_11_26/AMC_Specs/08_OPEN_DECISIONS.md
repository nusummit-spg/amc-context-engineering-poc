# 08 — Open Decisions, Assumptions and Nonblocking Questions

No answer is required before beginning the **read-only baseline, security containment, API inventory and diagnostic harness**. Certain domain interpretations do require explicit business-owner acceptance before financial formulas become authoritative.

## Business semantics requiring approval

1. **Data source and trust:** Is `mutual_fund_data.csv` a canonical approved business dataset, a test export, or a merged convenience extract? Can it be described as industry-complete? **Conservative default:** call it a dataset snapshot, not the full market.
2. **AAUM additivity:** Is `Average_AUM_Cr` additive across the source's plan/option rows? Are some options duplicates or alternate identifiers? **Conservative default:** prohibit aggregations labelled authoritative until plan/option grain is signed.
3. **Time semantics:** Does `AAUM_Quarter` represent one reporting quarter across all records? Is `Latest_NAV_Date` consistent? **Conservative default:** require a quarter for AAUM and an as-of policy for NAV.
4. **Closure_Date:** Why do sample rows have `Launch_Date == Closure_Date`? Is the field genuine closure date, incorrectly populated, or period convention? **Conservative default:** do not derive active/inactive status from that field.
5. **Canonical identity:** Who approves AMC, scheme, plan and option alias mapping and ambiguity resolution? **Conservative default:** preserve all originals, quarantine ambiguous merges.
6. **Source refresh and ownership:** Who approves new CSV and SEBI data publication and effective-date applicability? **Conservative default:** authorized steward and compliance owner sign-off.

## Deployment/operating decisions

7. **Target tenancy:** Is this a single-organization internal application or multi-tenant SaaS? **Conservative default:** design explicit tenant boundaries and deny access on missing identity, even if initial deployment has one tenant.
8. **Hosting:** Which environment is authoritative for release (local, AWS, Cloudflare or other)? **Conservative default:** do not assume current Docker Compose is runnable; harden standalone first, deploy only to an authorized environment.
9. **Microservices requirement:** Are feedback and repair separate services today, or embedded by default? **Conservative default:** keep contract boundaries but do not force physical split without SLO evidence.
10. **Review policy:** Which roles may approve source-value and regulatory corrections? **Conservative default:** human reviewer(s) with independent approver for critical changes, no auto approval.
11. **Data handling:** Are there PII, internal fund material, nonpublic research, or licensing limits in source corpus? **Conservative default:** treat all documents as restricted until classified and authorized.
12. **Latency / scale targets:** Concurrency, corpus growth and p95/p99 targets? **Conservative default:** instrument baseline before choosing database/vector scaling technology.

## Decision records to create

`ADR-001 Truth hierarchy`, `ADR-002 Finance grain & metric registry`, `ADR-003 Source identity/versions`, `ADR-004 SQL-vs-graph-vs-vector routing`, `ADR-005 Pending patch isolation`, `ADR-006 Repair publication authorization`, `ADR-007 Data-plane activation consistency`, `ADR-008 Evaluation release gating`, `ADR-009 Service/deployment topology`.

## Review boundary

All design and backlog items are **proposals**, not proof of passing tests or completed code changes. Externally verifiable findings are linked to the pinned GitHub branch in `01_SOURCE_REVIEW_AND_ROOT_CAUSES.md`. Before making irreversible data decisions, reproduce in the user's authorized runtime with protected dataset exports and actual service credentials; do not share secrets with an AI reviewer.
