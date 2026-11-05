# Patch Status State Machine Contract

## Normal Flow

```
PENDING -> APPROVED -> STAGED -> VERIFIED -> ACTIVE
```

## Terminal States

- **REJECTED** - Declined by reviewer (no further transitions)
- **FAILED** - Technical failure during promotion (no further transitions)
- **ROLLED_BACK** - Reverted after deployment (no further transitions)
- **SUPERSEDED** - Replaced by newer version (no further transitions)

## State Transition Rules

| Current State | Allowed Next States | Requirements |
|---------------|---------------------|--------------|
| PENDING | APPROVED, REJECTED | Initial state, awaiting human review |
| APPROVED | STAGED, REJECTED | Approved by reviewer, queued for promotion |
| STAGED | VERIFIED, FAILED | Queued, waiting for verification |
| VERIFIED | ACTIVE, FAILED | Verified external effects, ready to serve |
| ACTIVE | ROLLED_BACK, SUPERSEDED | Serving in answers, can be reverted |
| REJECTED | (none) | Permanent terminal state |
| FAILED | (none) | Permanent terminal state |
| ROLLED_BACK | (none) | Permanent terminal state |
| SUPERSEDED | (none) | Permanent terminal state |

## Timestamp Requirements

| State | Timestamp Field | Set By |
|-------|-----------------|--------|
| APPROVED | approved_at, approved_by | Reviewer approval |
| STAGED | staged_at | Promotion service |
| VERIFIED | verified_at, publication_receipt | Verification service |
| ACTIVE | activated_at, publication_receipt | Activation service |

## Serving Eligibility

A patch can serve in answers only when ALL of the following conditions are met:

1. `status == PatchStatus.ACTIVE`
2. `publication_receipt is not None`
3. `verified_at is not None`

## Backward Compatibility

The `approved` boolean field is computed from `status`:
- True if status is APPROVED, STAGED, VERIFIED, or ACTIVE
- False if status is PENDING, REJECTED, FAILED, ROLLED_BACK, or SUPERSEDED

## Error Handling

- Invalid state transitions raise `StateTransitionError`
- Missing patches return `False` from transition methods
- Redis failures fall back to in-memory store
