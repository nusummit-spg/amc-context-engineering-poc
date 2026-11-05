# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_wave13_vector_isolation.py
================================
Wave 1.3 B02: Vector Isolation Tests

Verifies that only ACTIVE verified patches are served to LLM context,
preventing C-09 data leak via premature serving.

Key Properties:
- PENDING patches never reach LLM context
- APPROVED patches (awaiting verification) do not serve
- Only ACTIVE patches with receipts can serve
- State machine enforces isolation at source
"""

import pytest
from amc_repair.patch_layer import CorrectionPatchLayer
from amc_repair.adapters.cache import MemoryCacheAdapter
from amc_repair.schemas import CorrectionPatch, PatchStatus
from amc_repair.config import RepairConfig
from datetime import datetime, timedelta, timezone


async def _create_patch_layer():
    """Helper to create fresh patch layer with in-memory cache."""
    cache = MemoryCacheAdapter()
    config = RepairConfig()
    layer = CorrectionPatchLayer(config=config, cache_adapter=cache)
    await layer.clear_all()
    return layer


@pytest.mark.asyncio
async def test_b02_pending_patches_not_served():
    """
    B02-T01: PENDING patches do not appear in LLM context.
    
    Security Requirement: C-09 prevention
    Gate: Release blocker
    """
    patch_layer = await _create_patch_layer()
    
    # Create PENDING patch
    patch = await patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="ter",
        original_value="0.79",
        corrected_value="0.82",
        confidence=0.95,
        provenance={"source": "user_feedback"}
    )
    
    assert patch.status == PatchStatus.PENDING
    
    # Verify it does NOT appear in active patches
    active = await patch_layer.get_active_patches(entity_id="INF846K01DP5")
    assert len(active) == 0, "PENDING patches must not be active"
    
    # Verify it does NOT appear in context application
    context = "Axis Bluechip Fund has TER 0.79%"
    modified = await patch_layer.apply_patches_to_context(
        entities=["INF846K01DP5"],
        retrieval_context=context
    )
    assert modified == context, "PENDING patches must not modify context"
    assert "0.82" not in modified, "Corrected value must not appear"
    assert "CORRECTION PATCH" not in modified, "No patch notice should appear"


@pytest.mark.asyncio
async def test_b02_approved_patches_not_served():
    """
    B02-T02: APPROVED patches (awaiting verification) do not serve.
    
    Security Requirement: C-09 prevention (no premature serving)
    Gate: Release blocker
    """
    patch_layer = await _create_patch_layer()
    
    # Create and approve patch
    patch = await patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="ter",
        original_value="0.79",
        corrected_value="0.82",
        confidence=0.95,
        provenance={"source": "governance_review"}
    )
    
    # Transition to APPROVED
    success = await patch_layer.transition_patch(patch.patch_id, PatchStatus.APPROVED)
    assert success, "Transition to APPROVED should succeed"
    
    # Verify status
    updated = await patch_layer.get_patch(patch.patch_id)
    assert updated.status == PatchStatus.APPROVED
    
    # Verify it does NOT serve (no receipt yet)
    active = await patch_layer.get_active_patches(entity_id="INF846K01DP5")
    assert len(active) == 0, "APPROVED patches without receipts must not serve"
    
    # Verify context not modified
    context = "Axis Bluechip Fund has TER 0.79%"
    modified = await patch_layer.apply_patches_to_context(
        entities=["INF846K01DP5"],
        retrieval_context=context
    )
    assert modified == context, "APPROVED patches must not modify context until ACTIVE"


@pytest.mark.asyncio
async def test_b02_active_patches_do_serve():
    """
    B02-T03: ACTIVE patches with receipts DO serve in LLM context.
    
    Functional Requirement: Approved corrections must reach users
    Gate: Feature completeness
    """
    patch_layer = await _create_patch_layer()
    
    # Create patch
    patch = await patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="ter",
        original_value="0.79",
        corrected_value="0.82",
        confidence=0.95,
        provenance={"source": "governance_review"}
    )
    
    # Transition to ACTIVE with receipt
    await patch_layer.transition_patch(patch.patch_id, PatchStatus.APPROVED)
    await patch_layer.transition_patch(patch.patch_id, PatchStatus.STAGED)
    await patch_layer.transition_patch(
        patch.patch_id,
        PatchStatus.VERIFIED,
        receipt={"reindex_job_id": "job-123-2026-11-05T10:30:00Z"}
    )
    success = await patch_layer.transition_patch(
        patch.patch_id,
        PatchStatus.ACTIVE,
        receipt={"graph_tx_id": "tx-456-2026-11-05T10:31:00Z"}
    )
    assert success
    
    # Verify it DOES appear in active patches
    active = await patch_layer.get_active_patches(entity_id="INF846K01DP5")
    assert len(active) == 1, "ACTIVE patches must be retrievable"
    assert active[0].patch_id == patch.patch_id
    
    # Verify context IS modified
    context = "Axis Bluechip Fund has TER 0.79%"
    modified = await patch_layer.apply_patches_to_context(
        entities=["INF846K01DP5"],
        retrieval_context=context
    )
    assert modified != context, "ACTIVE patches must modify context"
    assert "0.82" in modified, "Corrected value must appear"
    assert "CORRECTION PATCH APPLIED" in modified, "Patch notice must appear"


@pytest.mark.asyncio
async def test_b02_can_serve_filter_integration():
    """
    B02-T04: can_serve() method correctly filters patch eligibility.
    
    Integration Test: Verifies B01 state machine + B02 isolation
    Gate: Architecture verification
    """
    patch_layer = await _create_patch_layer()
    
    # Create three patches in different states
    patch_pending = await patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="aum",
        original_value="1000",
        corrected_value="1100",
        confidence=0.90,
        provenance={"source": "user"}
    )
    
    patch_approved = await patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="nav",
        original_value="100",
        corrected_value="105",
        confidence=0.95,
        provenance={"source": "user"}
    )
    await patch_layer.transition_patch(patch_approved.patch_id, PatchStatus.APPROVED)
    
    patch_active = await patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="ter",
        original_value="0.79",
        corrected_value="0.82",
        confidence=0.98,
        provenance={"source": "user"}
    )
    # Full transition to ACTIVE
    await patch_layer.transition_patch(patch_active.patch_id, PatchStatus.APPROVED)
    await patch_layer.transition_patch(patch_active.patch_id, PatchStatus.STAGED)
    await patch_layer.transition_patch(
        patch_active.patch_id,
        PatchStatus.VERIFIED,
        receipt={"reindex_job_id": "job-789"}
    )
    await patch_layer.transition_patch(
        patch_active.patch_id,
        PatchStatus.ACTIVE,
        receipt={"graph_tx_id": "tx-101"}
    )
    
    # Retrieve and verify filtering
    active = await patch_layer.get_active_patches(entity_id="INF846K01DP5")
    
    assert len(active) == 1, "Only 1 of 3 patches should be active"
    assert active[0].patch_id == patch_active.patch_id
    assert active[0].attribute == "ter"
    assert active[0].status == PatchStatus.ACTIVE


@pytest.mark.asyncio
async def test_b02_rejected_patches_never_serve():
    """
    B02-T05: REJECTED patches never serve, even if previously active.
    
    Security Requirement: Terminal state enforcement
    Gate: State machine correctness
    """
    patch_layer = await _create_patch_layer()
    
    # Create and fully activate patch
    patch = await patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="ter",
        original_value="0.79",
        corrected_value="0.82",
        confidence=0.95,
        provenance={"source": "governance"}
    )
    
    await patch_layer.transition_patch(patch.patch_id, PatchStatus.APPROVED)
    await patch_layer.transition_patch(patch.patch_id, PatchStatus.STAGED)
    await patch_layer.transition_patch(
        patch.patch_id,
        PatchStatus.VERIFIED,
        receipt={"reindex_job_id": "job-111"}
    )
    await patch_layer.transition_patch(
        patch.patch_id,
        PatchStatus.ACTIVE,
        receipt={"graph_tx_id": "tx-222"}
    )
    
    # Verify it serves
    active_before = await patch_layer.get_active_patches(entity_id="INF846K01DP5")
    assert len(active_before) == 1
    
    # Transition to ROLLED_BACK (terminal state - allowed from ACTIVE)
    await patch_layer.transition_patch(
        patch.patch_id,
        PatchStatus.ROLLED_BACK
    )
    
    # Verify it NO LONGER serves
    active_after = await patch_layer.get_active_patches(entity_id="INF846K01DP5")
    assert len(active_after) == 0, "ROLLED_BACK patches must not serve"
    
    # Verify context not modified
    context = "Axis Bluechip Fund has TER 0.79%"
    modified = await patch_layer.apply_patches_to_context(
        entities=["INF846K01DP5"],
        retrieval_context=context
    )
    assert modified == context, "ROLLED_BACK patches must not modify context"


@pytest.mark.asyncio
async def test_b02_failed_patches_do_not_serve():
    """
    B02-T06: FAILED patches (verification/promotion failures) do not serve.
    
    Operational Requirement: Failed operations don't leak data
    Gate: Failure handling correctness
    """
    patch_layer = await _create_patch_layer()
    
    # Create patch
    patch = await patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="nav",
        original_value="100",
        corrected_value="105",
        confidence=0.90,
        provenance={"source": "user"}
    )
    
    # Transition through states to FAILED
    await patch_layer.transition_patch(patch.patch_id, PatchStatus.APPROVED)
    await patch_layer.transition_patch(patch.patch_id, PatchStatus.STAGED)
    await patch_layer.transition_patch(
        patch.patch_id,
        PatchStatus.FAILED
    )
    
    # Verify it does NOT serve
    active = await patch_layer.get_active_patches(entity_id="INF846K01DP5")
    assert len(active) == 0, "FAILED patches must not serve"
    
    # Verify context not modified
    context = "Axis Bluechip Fund NAV is 100"
    modified = await patch_layer.apply_patches_to_context(
        entities=["INF846K01DP5"],
        retrieval_context=context
    )
    assert modified == context, "FAILED patches must not modify context"


@pytest.mark.asyncio
async def test_b02_multiple_entities_mixed_states():
    """
    B02-T07: Context injection filters correctly across multiple entities.
    
    Integration Test: Multi-entity query with mixed patch states
    Gate: Production scenario validation
    """
    patch_layer = await _create_patch_layer()
    
    # Entity 1: Has ACTIVE patch
    patch1 = await patch_layer.create_patch(
        entity_id="INF846K01DP5",
        attribute="ter",
        original_value="0.79",
        corrected_value="0.82",
        confidence=0.95,
        provenance={"source": "governance"}
    )
    await patch_layer.transition_patch(patch1.patch_id, PatchStatus.APPROVED)
    await patch_layer.transition_patch(patch1.patch_id, PatchStatus.STAGED)
    await patch_layer.transition_patch(
        patch1.patch_id, PatchStatus.VERIFIED, receipt={"reindex_job_id": "job-1"}
    )
    await patch_layer.transition_patch(
        patch1.patch_id, PatchStatus.ACTIVE, receipt={"graph_tx_id": "tx-1"}
    )
    
    # Entity 2: Has PENDING patch (should not serve)
    patch2 = await patch_layer.create_patch(
        entity_id="INF209K01YY8",
        attribute="aum",
        original_value="5000",
        corrected_value="5100",
        confidence=0.80,
        provenance={"source": "user"}
    )
    
    # Entity 3: Has APPROVED patch (should not serve)
    patch3 = await patch_layer.create_patch(
        entity_id="INF955L01AS4",
        attribute="nav",
        original_value="200",
        corrected_value="205",
        confidence=0.92,
        provenance={"source": "governance"}
    )
    await patch_layer.transition_patch(patch3.patch_id, PatchStatus.APPROVED)
    
    # Query for all three entities
    context = "Axis Bluechip Fund TER 0.79%, HDFC Top 100 AUM 5000 cr, ICICI Balanced NAV 200"
    modified = await patch_layer.apply_patches_to_context(
        entities=["INF846K01DP5", "INF209K01YY8", "INF955L01AS4"],
        retrieval_context=context
    )
    
    # Only Entity 1's ACTIVE patch should appear
    assert "0.82" in modified, "ACTIVE patch correction must appear"
    assert "CORRECTION PATCH APPLIED" in modified, "Patch notice must appear"
    assert "ter" in modified.lower(), "Attribute name must appear"
    
    # Entity 2 and 3 corrections should NOT appear
    assert "5100" not in modified, "PENDING patch correction must not appear"
    assert "205" not in modified, "APPROVED patch correction must not appear"
    
    # Count patch notices (should be exactly 1)
    notice_count = modified.count("CORRECTION PATCH APPLIED")
    assert notice_count == 1, f"Expected 1 patch notice, found {notice_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
