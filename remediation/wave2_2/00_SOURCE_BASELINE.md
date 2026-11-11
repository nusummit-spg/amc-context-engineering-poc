# Wave 2.2 Source Baseline

- Branch: amc-dev
- Pinned SHA at start: 6c2f0181538a8985fcb3f3264a0e62ebef8a2944
- Fix branch: amc-dev (applied directly)

## CI status at baseline (before Wave 2.2 fixes)

| Check | Status |
|---|---|
| A01 Clean Checkout Audit | PASS |
| A02 Migration Rehearsal | FAIL — KeyError: '003_invitation_token_hash' |
| A03 Unit Tests | FAIL — ModuleNotFoundError: feedback_loop |
| A04 Regression | SKIPPED |
| A05 Fault Injection | SKIPPED |
| A06 Canary | SKIPPED |
| A07 Release Gate | SKIPPED |
| Publication V2 contracts | PASS |
| Quality V2 contracts | PASS |
