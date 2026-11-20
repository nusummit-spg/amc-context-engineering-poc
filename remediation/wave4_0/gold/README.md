# Wave 4.0 gold sets (TDS-40 E5)

The answer-quality harness (`tools/amc_release/eval40.py`) scores against these files. `MANIFEST.json` pins each
file's SHA-256, case count and the fund dataset version the expected values came from. The harness refuses to run
if any file has drifted.

| Suite | File | Status | How it is made |
|---|---|---|---|
| GS-FIN | `gs_fin.jsonl` | 200 FROZEN | **Generated** by `tools/amc_release/gold40.py`: plain SQL over the approved `fin_*_v40` snapshot. It does not use the serving code or any LLM. |
| GS-ADV | `gs_adv.jsonl` | 50 FROZEN | **Generated** with the same SQL. The question templates are in `gold40.py`. |
| GS-REG | `gs_reg.jsonl` | 3 DRAFT templates | **To be authored by a Compliance SME** (120 cases): reference numbers, clause, in-force status and a rubric for each. |
| GS-MIX | `gs_mix.jsonl` | 5 DRAFT templates | **To be authored** once mixed answers exist (E3 gap) (30 cases). |

The harness counts only FROZEN cases. Until GS-REG has 120 and GS-MIX has 30 FROZEN cases, the `answer_quality`
gate stays BLOCKED, whatever the other metrics show.

GS-FIN breaks down as follows:
- **NAV by AMFI code:** 100 cases, 40 of them P0
- **NAV by full plan/option name:** 20 cases
- **AMC ranking by AAUM:** 15 cases, all P0
- **Scheme ranking by AAUM:** 10 across all AMCs, plus 25 within one AMC
- **Category share of AAUM:** 10 cases, all P0
- **Scheme counts:** 2 overall (P0), plus 15 per AMC
- **Dataset summary:** 3 cases, all P0

Period wording varies across cases: none, "Jan-Mar 2026", "Q4 FY26", "January to March 2026".

GS-ADV covers:
- **Advice requests:** 12
- **Unsupported metrics:** 8
- **Ambiguous or out-of-range questions:** 8
- **Numbers planted in the question to be echoed:** 6
- **PII bait:** 6
- **Cross-tenant probes:** 6; these need the `fixtures31` synthetic corpus
- **Prompt injection in the question:** 4

Prompt injection *inside documents* is not covered yet. It needs a signed fixture corpus that contains injected text.

Sixty FROZEN cases are flagged `smoke`, for the per-merge subset. A smoke run is never release evidence.

## Commands

```powershell
# regenerate GS-FIN / GS-ADV from the chunk files (deterministic: a rebuild reproduces the pinned files)
python -m tools.amc_release.gold40 build --tenant tenant_alpha --out remediation/wave4_0/gold
# or from the ACTIVE dataset of a real database
python -m tools.amc_release.gold40 build --tenant tenant_alpha --database-url <url> --out remediation/wave4_0/gold
# after an SME edits GS-REG / GS-MIX (sets status FROZEN), re-pin the hashes, then commit both
python -m tools.amc_release.gold40 rehash --gold remediation/wave4_0/gold
python -m tools.amc_release.gold40 verify --gold remediation/wave4_0/gold
```

A new dataset version means new gold. Rebuild with `--database-url` against the approved snapshot, review the diff
and commit it. The harness rejects a run whose served dataset version differs from `fin_dataset_version` in the
manifest.
