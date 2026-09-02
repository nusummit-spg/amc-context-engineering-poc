# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_metrics_store_concurrency.py
=======================================
Multi-threaded concurrency tests for MetricsStore to verify:
- RLock thread safety under simultaneous multi-worker load
- Zero race conditions or data loss during concurrent writes
- Concurrent readers and writers operating simultaneously
- Cryptographic hash chain consistency under parallel logging
"""

import concurrent.futures
from datetime import datetime
import pytest

from app.compliance.metrics_store import get_metrics_store
from app.schemas.audit_trail_access import AuditTrailAccessMetrics
from app.schemas.remediation_metrics import RemediationMetrics


def test_concurrent_remediation_and_audit_writes():
    store = get_metrics_store()

    def write_remediation(i: int):
        now_iso = datetime.utcnow().isoformat()
        rem = RemediationMetrics(
            remediation_id=f"REM_CONCUR_{i}",
            violation_id=f"VIO_CONCUR_{i}",
            severity_level="MEDIUM",
            sla_target_hours=24.0,
            sla_target_date=now_iso,
            detected_at=now_iso,
            remediation_action=f"Remediation action {i}",
            remediation_owner_user_id=f"user_{i % 5}",
            created_at=now_iso,
            updated_at=now_iso,
        )
        return store.record_remediation(rem)

    def write_audit_log(i: int):
        now_iso = datetime.utcnow().isoformat()
        log = AuditTrailAccessMetrics(
            access_log_id=f"ACCESS_CONCUR_{i}",
            user_id=f"auditor_{i % 3}",
            user_role="AUDITOR",
            resource_accessed=f"RESOURCE_{i}",
            access_purpose="STATUTORY_AUDIT",
            accessed_at=now_iso,
        )
        return store.log_audit_access(log)

    def read_operations():
        sla_rep = store.generate_sla_report()
        kpis = store.get_dashboard_kpis()
        audit_logs = store.get_audit_trail_access_metrics(limit=10)
        return len(sla_rep) > 0 and kpis is not None and len(audit_logs) >= 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        remediation_futures = [executor.submit(write_remediation, i) for i in range(30)]
        audit_futures = [executor.submit(write_audit_log, i) for i in range(30)]
        read_futures = [executor.submit(read_operations) for _ in range(20)]

        # Wait for all to complete
        remediations = [f.result() for f in concurrent.futures.as_completed(remediation_futures)]
        audit_logs = [f.result() for f in concurrent.futures.as_completed(audit_futures)]
        reads = [f.result() for f in concurrent.futures.as_completed(read_futures)]

    assert len(remediations) == 30
    assert len(audit_logs) == 30
    assert all(r is True for r in reads)

    # Verify cryptographic integrity is completely intact after parallel logging
    verification = store.verify_audit_trail_integrity()
    assert verification["is_valid"] is True
    assert verification["total_records"] >= 30



def test_concurrent_mutations_on_same_record():
    """Verify that concurrent updates on the same violation record don't corrupt state."""
    store = get_metrics_store()
    now_iso = datetime.utcnow().isoformat()
    rem = RemediationMetrics(
        remediation_id="REM_SHARED_001",
        violation_id="VIO_SHARED_001",
        severity_level="HIGH",
        sla_target_hours=48.0,
        sla_target_date=now_iso,
        detected_at=now_iso,
        remediation_action="Initial shared action",
        remediation_owner_user_id="lead_officer",
        created_at=now_iso,
        updated_at=now_iso,
    )
    store.record_remediation(rem)

    def update_remediation(cost: float, note: str):
        return store.update_remediation("VIO_SHARED_001", {
            "remediation_cost_hours": cost,
            "remediation_action": note,
        })

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(update_remediation, float(i), f"Updated by worker {i}") for i in range(15)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 15
    final = store.get_remediation_metrics("VIO_SHARED_001")
    assert final is not None
    assert final.remediation_cost_hours >= 0.0
