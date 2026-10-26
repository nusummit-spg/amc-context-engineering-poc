# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_correction_patch_layer.py
==============================
Unit tests for Track 6: Correction Patch Layer (Shadow Graph).
Verifies:
  - Adding unapproved patches sets TTL (7 days)
  - Adding approved patches has no expiration
  - Fetching corrections and in-memory fallback
  - Injecting active patches into retrieval context
  - Promoting patches to permanent canonical status
  - Deleting patches on rejection
"""

from unittest.mock import MagicMock
import pytest
from app.graph.correction_patch_layer import CorrectionPatchLayer, CorrectionPatch


@pytest.fixture
def patch_layer():
    """Isolated in-memory patch layer instance for testing."""
    return CorrectionPatchLayer(redis_client=None, ttl_days=7)


def test_add_and_get_unapproved_patch(patch_layer):
    patch_id = patch_layer.add_correction(
        entity_id="INF846K01DP5",
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.85,
        provenance={"feedback_id": "fb_test_1", "source": "AMFI latest"},
        approved=False
    )
    assert patch_id.startswith("patch_")

    patch = patch_layer.get_correction("INF846K01DP5", "TER")
    assert patch is not None
    assert patch.patch_id == patch_id
    assert patch.entity_id == "INF846K01DP5"
    assert patch.attribute == "TER"
    assert patch.canonical_value == "0.79"
    assert patch.corrected_value == "0.82"
    assert patch.confidence == 0.85
    assert patch.approved is False
    assert patch.expires_at is not None


def test_add_approved_patch_has_no_ttl(patch_layer):
    patch_id = patch_layer.add_correction(
        entity_id="INF846K01DP5",
        attribute="NAV",
        canonical_value="64.18",
        corrected_value="64.31",
        confidence=0.95,
        provenance={"feedback_id": "fb_test_2"},
        approved=True
    )
    patch = patch_layer.get_correction("INF846K01DP5", "NAV")
    assert patch is not None
    assert patch.approved is True
    assert patch.expires_at is None


def test_apply_patches_to_context(patch_layer):
    patch_layer.add_correction(
        entity_id="INF846K01DP5",
        attribute="TER",
        canonical_value="0.79%",
        corrected_value="0.82%",
        confidence=0.88,
        provenance={"source": "AMFI official portal"},
        approved=False
    )

    original_context = "The Axis Bluechip Fund has an expense ratio (TER) of 0.79% per factsheet v17."
    modified_context = patch_layer.apply_patches_to_context(
        entities=["INF846K01DP5"],
        retrieval_context=original_context
    )

    assert "ACTIVE CORRECTIONS" in modified_context
    assert "[CORRECTION - TER]" in modified_context
    assert "0.82%" in modified_context
    assert "0.79%" in modified_context
    assert original_context in modified_context


def test_apply_patches_no_match(patch_layer):
    original_context = "Some fund facts."
    modified_context = patch_layer.apply_patches_to_context(
        entities=["NON_EXISTENT_ENTITY"],
        retrieval_context=original_context
    )
    assert modified_context == original_context


def test_get_all_pending(patch_layer):
    patch_layer.add_correction("E1", "TER", "0.5", "0.6", 0.8, approved=False)
    patch_layer.add_correction("E2", "NAV", "10", "11", 0.9, approved=True)
    patch_layer.add_correction("E3", "AUM", "100", "120", 0.85, approved=False)

    pending = patch_layer.get_all_pending()
    assert len(pending) == 2
    pending_entities = {p.entity_id for p in pending}
    assert pending_entities == {"E1", "E3"}


def test_promote_to_permanent(patch_layer):
    mock_session = MagicMock()
    patch_id = patch_layer.add_correction(
        entity_id="INF846K01DP5",
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.85,
        approved=False
    )

    success = patch_layer.promote_to_permanent(patch_id, neo4j_session=mock_session)
    assert success is True

    # Check Neo4j run was invoked
    mock_session.run.assert_called_once()

    # Check patch status in store
    patch = patch_layer.get_patch_by_id(patch_id)
    assert patch is not None
    assert patch.approved is True
    assert patch.expires_at is None


def test_delete_patch(patch_layer):
    patch_id = patch_layer.add_correction(
        entity_id="INF846K01DP5",
        attribute="TER",
        canonical_value="0.79",
        corrected_value="0.82",
        confidence=0.85
    )
    assert patch_layer.get_correction("INF846K01DP5", "TER") is not None

    deleted = patch_layer.delete_patch(patch_id)
    assert deleted is True
    assert patch_layer.get_correction("INF846K01DP5", "TER") is None
