# AMC Wave 2.0 — additive quality-code overlay

This ZIP contains **real tested source code** for source-byte/CSV integrity, full
financial contributor ledgers, fail-closed reference queries, Wave 1.9 Feedback
causality audit, tenant-scoped assurance evidence, CLI, non-overwriting installer
and GitHub Actions tests. It does **not** install automatically or deploy.

Read `AMC_Wave2_0_Code_Implementation_Goals_Next_Actions_2026-11-06.md` for
step-by-step Windows PowerShell commands, goals, remaining integration tasks,
quality gates and a ready-to-paste Codex prompt.

**Run safely**: `python tools/install_wave20_overlay.py --repo <your-local-git-repo>`
shows a dry run; append `--apply` to copy only files that do not exist.
Install the Wave 1.9 overlay first for the Wave 1.9 Feedback contract tests.

**Local result**: 112 combined Wave 1.9 + Wave 2.0 synthetic/SQLite tests passed.
**Production release remains BLOCKED.**
