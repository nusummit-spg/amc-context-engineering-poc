# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Wave 0 Verification Tests:
# Test 1: Anonymous / Unauthenticated access returns 401 (GOV-01)
# Test 2: Invalid role rejected with 400, valid role accepted (GOV-01, GOV-02)
# Test 3: Pending / unapproved patches excluded from serving paths (GOV-04, G02-T13)
# Test 4: Auto-approval disabled in config and integration (GOV-03, G02-T12, G10-T01)
# ===========================================================================

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.compliance.security import Role, get_client_role
from app.graph.correction_patch_layer import get_correction_patch_layer


def test_test1_anonymous_access_returns_401():
    """Test 1: Requests without X-User-Role header must return 401 Unauthorized (GOV-01)."""
    with pytest.raises(HTTPException) as exc_info:
        get_client_role(None)
    assert exc_info.value.status_code == 401
    assert "Authentication required: X-User-Role header missing" in exc_info.value.detail


def test_test2_invalid_role_returns_400():
    """Test 2a: Requests with invalid role strings must return 400 Bad Request."""
    with pytest.raises(HTTPException) as exc_info:
        get_client_role("hacker")
    assert exc_info.value.status_code == 400
    assert "Invalid X-User-Role: 'hacker'" in exc_info.value.detail


def test_test2_valid_role_returns_role_enum():
    """Test 2b: Requests with valid role header resolve to the correct Role enum."""
    role = get_client_role("admin")
    assert role == Role.ADMIN

    role_comp = get_client_role("compliance_officer")
    assert role_comp == Role.COMPLIANCE_OFFICER


def test_test3_pending_patch_excluded_from_context():
    """Test 3: Pending/unapproved patches must NOT be applied to serving context (G02-T13)."""
    layer = get_correction_patch_layer()
    layer.clear_all()

    # Create unapproved/pending patch
    res = layer.add_correction(
        entity_id="HDFC Top 100",
        attribute="NAV",
        canonical_value=500.0,
        corrected_value=9999.0,
        confidence=0.99,
        approved=False,
    )
    patch_id = res["patch_id"]

    # Verify excluded from active patches
    active = layer.get_active_patches()
    assert len(active) == 0, f"Expected 0 active approved patches, got {len(active)}"

    # Verify context does NOT contain the pending patch
    context = layer.apply_patches_to_context(["HDFC Top 100"], "Baseline fund NAV is 500.0")
    assert "9999.0" not in context, "Security violation: pending patch leaked into retrieval context!"

    # Approve patch and verify it is now included
    layer.approve_patch(patch_id)
    active_after = layer.get_active_patches()
    assert len(active_after) == 1

    context_approved = layer.apply_patches_to_context(["HDFC Top 100"], "Baseline fund NAV is 500.0")
    assert "9999.0" in context_approved, "Approved patch was not included in context"


def test_test4_auto_approval_disabled():
    """Test 4: Auto-approval must be disabled in settings and governance configuration (GOV-03)."""
    settings = get_settings()
    assert settings.repair_auto_approve_enabled is False
    assert settings.repair_require_human_approval is True
    assert settings.repair_require_four_eyes is True


if __name__ == "__main__":
    test_test1_anonymous_access_returns_401()
    print("PASS: Test 1 (Anonymous 401)")
    test_test2_invalid_role_returns_400()
    print("PASS: Test 2a (Invalid role 400)")
    test_test2_valid_role_returns_role_enum()
    print("PASS: Test 2b (Valid role resolution)")
    test_test3_pending_patch_excluded_from_context()
    print("PASS: Test 3 (Pending patch exclusion)")
    test_test4_auto_approval_disabled()
    print("PASS: Test 4 (Auto-approval disabled)")
    print("\n>>> ALL 4 VERIFICATION TESTS PASSED SUCCESSFULLY! <<<")
