import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.graph.correction_patch_layer import get_correction_patch_layer
from app.api.routes.governance import run_governance_batch, GovernanceBatchIn, assess_risk_level
from app.models.compliance_models import Role


@pytest.fixture(autouse=True)
def clean_patch_layer():
    patch_layer = get_correction_patch_layer()
    with patch_layer._lock:
        patch_layer._mem_store.clear()
    yield
    with patch_layer._lock:
        patch_layer._mem_store.clear()


@pytest.mark.asyncio
async def test_risk_level_assessment():
    """Verify that small relative changes with high confidence are LOW risk, but large shifts are HIGH risk."""
    assert assess_risk_level(0.96, "1.20%", "1.22%") == "LOW"
    assert assess_risk_level(0.96, "1.00%", "1.40%") == "HIGH"
    assert assess_risk_level(0.65, "1.20%", "1.22%") == "HIGH"


@pytest.mark.asyncio
async def test_governance_auto_batch_promotes_high_confidence_low_risk():
    """Patches with confidence >= 0.95 and LOW risk should be auto-approved into canonical graph."""
    patch_layer = get_correction_patch_layer()
    
    # Create high-confidence, low-risk pending patch
    p = patch_layer.add_correction(
        entity_id="HDFC_TOP_100",
        attribute="expense_ratio",
        canonical_value="1.20%",
        corrected_value="1.22%",
        confidence=0.96,
        approved=False
    )
    patch_id = p["patch_id"]

    # Verify pending
    pending = patch_layer.get_all_pending()
    assert any(x.patch_id == patch_id for x in pending)

    # Run auto-approval batch
    result = await run_governance_batch(
        payload=GovernanceBatchIn(auto_approve_threshold=0.95, max_risk_level="LOW", dry_run=False),
        current_role=Role.ADMIN,
        db=MagicMock()
    )

    assert result["status"] == "completed"
    assert result["approved"] >= 1
    assert patch_id in result["approved_patches"]

    # Verify patch is now approved
    stored = patch_layer.get_patch_by_id(patch_id)
    assert stored is not None
    assert stored.approved is True
    assert stored.expires_at is None


@pytest.mark.asyncio
async def test_governance_auto_batch_preserves_lower_confidence():
    """Patches with confidence < threshold must remain pending for human review."""
    patch_layer = get_correction_patch_layer()
    
    p = patch_layer.add_correction(
        entity_id="SBI_BLUECHIP",
        attribute="exit_load",
        canonical_value="1.00%",
        corrected_value="0.95%",
        confidence=0.82,
        approved=False
    )
    patch_id = p["patch_id"]

    result = await run_governance_batch(
        payload=GovernanceBatchIn(auto_approve_threshold=0.95, max_risk_level="LOW", dry_run=False),
        current_role=Role.ADMIN,
        db=MagicMock()
    )

    assert result["status"] == "completed"
    assert patch_id not in result["approved_patches"]
    assert result["needs_review"] >= 1

    stored = patch_layer.get_patch_by_id(patch_id)
    assert stored.approved is False


@pytest.mark.asyncio
async def test_governance_auto_batch_preserves_high_risk_even_with_high_confidence():
    """Large financial deltas (>20%) should NOT auto-approve even if confidence is 0.98."""
    patch_layer = get_correction_patch_layer()
    
    p = patch_layer.add_correction(
        entity_id="AXIS_GROWTH",
        attribute="nav",
        canonical_value="50.0",
        corrected_value="85.0",  # 70% jump -> HIGH risk
        confidence=0.98,
        approved=False
    )
    patch_id = p["patch_id"]

    result = await run_governance_batch(
        payload=GovernanceBatchIn(auto_approve_threshold=0.95, max_risk_level="LOW", dry_run=False),
        current_role=Role.ADMIN,
        db=MagicMock()
    )

    assert patch_id not in result["approved_patches"]
    assert result["needs_review"] >= 1

    stored = patch_layer.get_patch_by_id(patch_id)
    assert stored.approved is False


@pytest.mark.asyncio
async def test_governance_auto_batch_dry_run():
    """Dry run should report eligible patches without mutating their approval status."""
    patch_layer = get_correction_patch_layer()
    
    p = patch_layer.add_correction(
        entity_id="NIPPON_INDIA",
        attribute="aum",
        canonical_value="1000",
        corrected_value="1050",
        confidence=0.97,
        approved=False
    )
    patch_id = p["patch_id"]

    result = await run_governance_batch(
        payload=GovernanceBatchIn(auto_approve_threshold=0.95, max_risk_level="LOW", dry_run=True),
        current_role=Role.ADMIN,
        db=MagicMock()
    )

    assert result["dry_run"] is True
    assert patch_id in result["approved_patches"]

    # But stored status must NOT have changed
    stored = patch_layer.get_patch_by_id(patch_id)
    assert stored.approved is False
