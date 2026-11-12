# AMC Wave 3.1 — Source-package handoff

This branch is **only for distributing the already-prepared Wave 3.1 archive and local-agent runbook**. It is not the implementation branch. Do not merge this artifacts branch into `amc-dev` or the integration branch.

## Download

1. In GitHub, open `handoffs/wave3_1/AMC_Wave3_1_Cumulative_Release_Integration_2026-11-11.zip` and click **Download raw file**.
2. Download `AMC_Wave31_Local_Agent_Integration_Runbook_2026-11-12.md` from the same directory.
3. Verify the ZIP SHA-256 before use:

```powershell
(Get-FileHash -Algorithm SHA256 .\AMC_Wave3_1_Cumulative_Release_Integration_2026-11-11.zip).Hash.ToLowerInvariant()
```

Expected: `d1a75cf4f4343a0fb2abac3f24ac7abaa09b500117180d7e3329f202777327e3`

## Integration target

The local agent must follow the runbook against an **exact, clean `amc-dev` checkout** at `2c0415c4d23a3338428c8314c869299aa0ab771f`. The cumulative installer creates a temporary local branch. After integration and test remediation, the team should push **code changes only** to `feature/amc-wave31-integration`, not back to this artifacts branch.

No source changes are implemented by this artifacts commit. It does not establish full-repository integration, runtime acceptance, UAT or MVP readiness.
