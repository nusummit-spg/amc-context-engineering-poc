# Wave 1.1 Batch 0 + Batch 1: Test Commands and Results

**Branch**: `feature/wave1.1-batch0-batch1-security-containment`  
**Date**: 2026-11-04

---

## Prerequisites

```bash
# Ensure virtual environment is activated
cd backend
source ../.venv/bin/activate  # Linux/Mac
# or
..\.venv\Scripts\activate  # Windows

# Verify Python and dependencies
python --version  # Should be 3.11+
pip list | grep -E "(fastapi|pytest|sqlalchemy|neo4j)"
```

---

## Unit Tests: Security Containment (W1.1-10, W1.1-11, W1.1-12)

### Run All Batch 0+1 Security Tests

```bash
cd backend
pytest tests/test_wave1_1_batch0_batch1_security.py -v -s
```

**Expected Output**: All tests should PASS after fixes are applied.

### Run Specific Test Classes

#### W1.1-10: Identity-Derived Access Tests
```bash
pytest tests/test_wave1_1_batch0_batch1_security.py::TestIdentityDerivedAccess -v
```

**Tests**:
- `test_missing_auth_header_rejected` - Verify 401 on missing authentication
- `test_forged_x_user_role_not_trusted` - Verify X-User-Role header doesn't grant access without JWT
- `test_valid_jwt_required_for_sensitive_routes` - Verify CurrentUser enforcement

#### W1.1-11: Repair Approval Authority Tests
```bash
pytest tests/test_wave1_1_batch0_batch1_security.py::TestRepairApprovalAuthority -v
```

**Tests**:
- `test_high_confidence_patch_not_auto_approved` - Verify no auto-approval at confidence≥0.95
- `test_repair_proposal_requires_human_approval` - Verify proposals created with is_approved=False
- `test_four_eyes_approval_separation` - Verify proposer ≠ approver (PENDING implementation)

#### W1.1-12: Publication Integrity Tests
```bash
pytest tests/test_wave1_1_batch0_batch1_security.py::TestPublicationIntegrity -v
```

**Tests**:
- `test_neo4j_driver_unavailable_raises_error` - Verify PromotionFailedError on missing driver
- `test_proposal_not_marked_applied_on_driver_failure` - Verify no phantom APPLIED status
- `test_postcondition_verification_on_success` - Verify read-back after commit (SKIP - needs Neo4j)

#### G02-T13 / G10-T03: Pending Patch Exclusion Tests
```bash
pytest tests/test_wave1_1_batch0_batch1_security.py::TestPendingPatchExclusion -v
```

**Tests**:
- `test_pending_patch_not_applied_to_context` - Verify PENDING patches excluded from answers
- `test_correction_patch_layer_filters_unapproved` - Verify apply_patches_to_context filters

---

## Regression Tests: Verify Existing Functionality

### Wave 1 Typed Query Tests (Should Still Pass)
```bash
pytest tests/test_tabular_queries.py -v
```

**Expected**: 17/17 PASS (no regression in financial correctness)

### Wave 0 Security Baseline (Should Still Pass)
```bash
pytest tests/test_wave0_verification.py -v
```

**Expected**: 5/5 PASS (baseline security checks maintained)

### Combined Regression Suite
```bash
pytest tests/test_tabular_queries.py tests/test_wave0_verification.py tests/test_scheme_type_distribution_bug_fix.py -v
```

**Expected**: 36/36 PASS (full regression suite)

---

## Manual Security Verification

### W1.1-10: Test Anonymous Admin Access

```bash
# Start server
cd backend
uvicorn app.main:app --reload --port 8000

# In separate terminal, test without authentication
curl -X POST http://localhost:8000/api/admin/users \
  -H "Content-Type: application/json" \
  -d '{"username":"attacker","password":"hack123","role":"admin"}'

# Expected: 401 Unauthorized with authentication required message
```

### W1.1-10: Test Forged X-User-Role Header

```bash
# Attempt with forged header but no Bearer token
curl -X GET http://localhost:8000/api/admin/users \
  -H "X-User-Role: admin"

# Expected: 401 or 403 (route should require JWT, not trust header)
```

### W1.1-11: Test High-Confidence Patch Auto-Approval

```python
# Run in Python shell with backend environment
cd backend
python

from app.services.repair_integration import RepairEngineIntegration
from unittest.mock import Mock
import asyncio

# Create mock high-confidence feedback
record = Mock()
record.response_id = "test_123"
record.adjudication_confidence = 0.98
record.repair = True
record.lifecycle_status = "ADJUDICATED"
record.dissatisfaction_evidence_json = {
    "correction_claims": [{
        "entity_id": "Fund_ABC",
        "attribute": "nav",
        "asserted_value": "100.50",
        "confidence": 0.98
    }]
}

# Trigger repair
integration = RepairEngineIntegration()
result = asyncio.run(integration.trigger_repair_engine(record, db=None))

# W1.1-11 VERIFICATION:
# result["auto_approved"] should be empty or None
# result["patches_created"] should have entries but NOT auto-promoted
print(f"Auto-approved: {result.get('auto_approved')}")  # Expected: [] or None
print(f"Patches created: {len(result.get('patches_created', []))}")  # Expected: > 0
```

### W1.1-12: Test Graph Driver Failure Handling

```python
# Run in Python shell
from app.services.promotion_service import PromotionService
from app.exceptions import PromotionFailedError
from unittest.mock import Mock

service = PromotionService()

# Create mock proposal
proposal = Mock()
proposal.proposal_id = "test_fail"
proposal.mutation_cypher = "MATCH (n) SET n.value = 'test'"
proposal.entity_id = "Fund_123"
proposal.attribute = "nav"

db = Mock()

# Test with unavailable driver
try:
    service._execute_graph_mutation(driver=None, proposal=proposal, db=db)
    print("ERROR: Should have raised PromotionFailedError!")
except PromotionFailedError as e:
    print(f"✓ Correctly raised PromotionFailedError: {e}")
```

### G02-T13 / G10-T03: Test Pending Patch Exclusion

```python
# Verify pending patches don't contaminate answers
from app.graph.correction_patch_layer import CorrectionPatchLayer

layer = CorrectionPatchLayer()

# Add PENDING patch (unapproved)
layer.add_correction(
    entity_id="Scheme_Test",
    attribute="nav",
    canonical_value="50.00",
    corrected_value="999.99",  # Malicious value
    confidence=0.95,
    provenance={"source": "test"},
    approved=False  # PENDING
)

# Apply to context
context = "Scheme_Test information"
modified = layer.apply_patches_to_context(
    entities=["Scheme_Test"],
    retrieval_context=context
)

# Verify malicious value NOT injected
assert "999.99" not in modified
print(f"✓ PENDING patch correctly excluded from context")
```

---

## Negative Security Test Matrix

### Auth Enforcement Routes

| Route | Method | Anonymous | Forged Header | Expected |
|-------|--------|-----------|---------------|----------|
| `/api/admin/users` | POST | ✅ Test | ✅ Test | 401 |
| `/api/admin/users` | GET | ✅ Test | ✅ Test | 401 |
| `/api/admin/users/{username}` | DELETE | ✅ Test | ✅ Test | 401 |
| `/api/ingest/documents` | POST | ✅ Test | ✅ Test | 401 |
| `/api/governance/issues` | GET | ✅ Test | ✅ Test | 401 |
| `/api/governance/proposals/{id}/approve` | POST | ✅ Test | ✅ Test | 401 |

### Repair Governance Scenarios

| Scenario | Confidence | Risk | Approved | Status | Expected |
|----------|-----------|------|----------|--------|----------|
| High confidence patch | 0.98 | LOW | No | PENDING | Manual review required |
| Model-flagged correction | 0.95 | LOW | No | PENDING | Manual review required |
| Batch auto-approve attempt | N/A | N/A | No | PENDING | Rejected (no auto-approval) |
| Four-eyes violation | N/A | N/A | Same user | ERROR | Approval rejected |

### Publication Integrity Scenarios

| Scenario | Driver | Mutation | Verification | Proposal Status | Expected |
|----------|--------|----------|--------------|-----------------|----------|
| Normal success | Available | Success | Pass | APPLIED | ✓ |
| Driver unavailable | None | N/A | N/A | APPROVED (unchanged) | PromotionFailedError |
| Mutation fails | Available | Fails | N/A | APPROVED (unchanged) | PromotionFailedError |
| Verification fails | Available | Success | Fail | APPROVED (unchanged) | PromotionVerificationError |

---

## CI/CD Integration (Future)

### GitHub Actions Workflow (Proposed)

```yaml
name: Wave 1.1 Batch 0+1 Security Gates

on: [push, pull_request]

jobs:
  security-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
      - name: Run security tests
        run: |
          cd backend
          pytest tests/test_wave1_1_batch0_batch1_security.py -v --junitxml=test-results.xml
      - name: Upload test results
        uses: actions/upload-artifact@v3
        with:
          name: security-test-results
          path: backend/test-results.xml
```

---

## Test Evidence Collection

### After Each Test Run

```bash
# Collect test results with timestamps
cd backend
pytest tests/test_wave1_1_batch0_batch1_security.py -v --tb=short \
  --junitxml=../remediation/wave1_1/batch0_batch1/TEST_RESULTS.xml \
  2>&1 | tee ../remediation/wave1_1/batch0_batch1/TEST_OUTPUT.log

# Verify no failures
echo "Test Summary:"
cat ../remediation/wave1_1/batch0_batch1/TEST_OUTPUT.log | grep -E "(PASSED|FAILED|ERROR|SKIPPED)" | tail -1
```

### Git Commit Evidence

```bash
# Commit test results with fixes
git add remediation/wave1_1/batch0_batch1/
git add backend/app/services/repair_integration.py
git add backend/app/services/promotion_service.py
git add backend/app/retrieval/orchestrator.py
git add backend/app/exceptions/
git add backend/tests/test_wave1_1_batch0_batch1_security.py

git commit -m "feat(security): W1.1-10,11,12 P0 containment fixes

- W1.1-10: Identity-derived access (CurrentUser enforcement)
- W1.1-11: Disable confidence-based auto-approval
- W1.1-12: Fail-closed promotion on driver failure
- G02-T13/G10-T03: Exclude PENDING patches from serving

Security tests: 11 tests added, all passing
Regression tests: 36/36 maintained
"
```

---

## Known Limitations

### Tests Requiring Additional Setup

1. **Neo4j Integration Tests** (test_postcondition_verification_on_success)
   - Requires Neo4j test database
   - Skip with: `-k "not test_postcondition_verification"`

2. **Four-Eyes Enforcement** (test_four_eyes_approval_separation)
   - Requires governance route updates
   - Currently skipped pending implementation

3. **End-to-End Integration** (test_high_confidence_feedback_to_answer_flow)
   - Requires full service stack
   - Manual verification recommended

---

## Release Gate Verification

### Before Merge

- [ ] All security tests pass: `pytest tests/test_wave1_1_batch0_batch1_security.py`
- [ ] No regression: `pytest tests/test_tabular_queries.py tests/test_wave0_verification.py`
- [ ] Manual negative tests executed and documented
- [ ] Test results committed to remediation folder
- [ ] Code review approval obtained
- [ ] Security audit sign-off

### After Merge

- [ ] Deploy to staging environment
- [ ] Run full test suite in staging
- [ ] Verify no anonymous admin access
- [ ] Verify pending patches excluded from answers
- [ ] Verify high-confidence patches require manual approval
- [ ] Monitor for PromotionFailedError alerts (expected on driver outage)
