# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_transaction_atomicity.py
===================================
Tests verifying all-or-nothing transaction atomicity and rollback in MetricsStore:
1. Successful transactions commit state changes permanently
2. Mid-operation exceptions trigger immediate rollback to pre-transaction snapshot
3. Multi-entity batch mutations maintain transactional integrity
"""

import pytest
from datetime import datetime

from app.compliance.metrics_store import get_metrics_store
from app.schemas.remediation_metrics import RemediationMetrics


def test_atomic_transaction_commits_on_success():
    """Verify that state changes persist when the transaction block completes successfully."""
    store = get_metrics_store()
    now_iso = datetime.utcnow().isoformat()
    rem = RemediationMetrics(
        remediation_id="REM_TX_SUCCESS_001",
        violation_id="VIO_TX_SUCCESS_001",
        severity_level="LOW",
        sla_target_hours=48.0,
        sla_target_date=now_iso,
        detected_at=now_iso,
        remediation_action="Initial action",
        remediation_owner_user_id="user_tx",
        created_at=now_iso,
        updated_at=now_iso,
    )

    with store.atomic_transaction():
        store.record_remediation(rem)

    # Change must be committed
    assert store.get_remediation_metrics("VIO_TX_SUCCESS_001") is not None


def test_atomic_transaction_rolls_back_on_failure():
    """Verify that all state mutations inside the block are cleanly rolled back if an error occurs."""
    store = get_metrics_store()
    now_iso = datetime.utcnow().isoformat()

    # Pre-transaction state
    initial_remediations_count = len(store._remediations)

    rem1 = RemediationMetrics(
        remediation_id="REM_TX_ROLLBACK_001",
        violation_id="VIO_TX_ROLLBACK_001",
        severity_level="HIGH",
        sla_target_hours=24.0,
        sla_target_date=now_iso,
        detected_at=now_iso,
        remediation_action="Valid first action",
        remediation_owner_user_id="user_tx",
        created_at=now_iso,
        updated_at=now_iso,
    )

    rem2 = RemediationMetrics(
        remediation_id="REM_TX_ROLLBACK_002",
        violation_id="VIO_TX_ROLLBACK_002",
        severity_level="HIGH",
        sla_target_hours=24.0,
        sla_target_date=now_iso,
        detected_at=now_iso,
        remediation_action="Valid second action",
        remediation_owner_user_id="user_tx",
        created_at=now_iso,
        updated_at=now_iso,
    )

    with pytest.raises(RuntimeError, match="Simulated mid-transaction failure"):
        with store.atomic_transaction():
            store.record_remediation(rem1)
            # Verify rem1 is temporarily in memory
            assert "VIO_TX_ROLLBACK_001" in store._remediations

            # Simulate sudden database/network or business logic crash
            raise RuntimeError("Simulated mid-transaction failure")

            # This would have executed if not for the error
            store.record_remediation(rem2)

    # Post-rollback verification:
    # rem1 must be completely removed from the store!
    assert "VIO_TX_ROLLBACK_001" not in store._remediations
    assert "VIO_TX_ROLLBACK_002" not in store._remediations
    assert len(store._remediations) == initial_remediations_count


def test_atomic_transaction_rollback_preserves_modifications_to_existing_record():
    """Verify that updating an existing record inside a failing transaction restores original values."""
    store = get_metrics_store()
    now_iso = datetime.utcnow().isoformat()

    rem = RemediationMetrics(
        remediation_id="REM_ORIGINAL_001",
        violation_id="VIO_ORIGINAL_001",
        severity_level="MEDIUM",
        sla_target_hours=48.0,
        sla_target_date=now_iso,
        detected_at=now_iso,
        remediation_action="Original Action Description",
        remediation_owner_user_id="original_owner",
        created_at=now_iso,
        updated_at=now_iso,
    )
    store.record_remediation(rem)

    with pytest.raises(ValueError, match="Abort update"):
        with store.atomic_transaction():
            store.update_remediation("VIO_ORIGINAL_001", {
                "remediation_action": "Corrupted Temporary Value",
                "remediation_owner_user_id": "temp_owner",
            })
            assert store.get_remediation_metrics("VIO_ORIGINAL_001").remediation_action == "Corrupted Temporary Value"
            raise ValueError("Abort update")

    # Verify original values are restored intact
    restored = store.get_remediation_metrics("VIO_ORIGINAL_001")
    assert restored.remediation_action == "Original Action Description"
    assert restored.remediation_owner_user_id == "original_owner"
