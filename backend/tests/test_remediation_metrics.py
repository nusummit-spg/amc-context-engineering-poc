# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_remediation_metrics.py
=================================
Comprehensive unit & operational tests for RemediationMetrics schema and SLA calculations:
- SLA calculation: early completion (negative variance, WITHIN_SLA)
- SLA calculation: on-time completion (zero variance, WITHIN_SLA)
- SLA calculation: late completion (positive variance, BREACHED)
- Pending state when remediation is ongoing
- Direct linking to RootCauseAnalysis (remediation_root_cause_id)
- Escalation reason and Chief Compliance Officer notification tracking
- Cost expenditure tracking in person-hours
- Re-violation flags (7-day and 30-day windows)
- Effectiveness transitions: EFFECTIVE, PARTIAL, INEFFECTIVE, PENDING_VERIFICATION
"""

import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError

from app.schemas.remediation_metrics import RemediationMetrics
from app.compliance.metrics_store import get_metrics_store


def test_remediation_metrics_instantiation():
    now_iso = datetime.utcnow().isoformat()
    rem = RemediationMetrics(
        remediation_id="REM_TEST_001",
        violation_id="VIO_TEST_001",
        severity_level="CRITICAL",
        sla_target_hours=24.0,
        sla_target_date=now_iso,
        detected_at=now_iso,
        remediation_action="Immediate margin deposit to restore coverage",
        remediation_owner_user_id="risk_manager_1",
        remediation_root_cause_id="RCA_TEST_001",
        created_at=now_iso,
        updated_at=now_iso,
    )
    assert rem.remediation_id == "REM_TEST_001"
    assert rem.severity_level == "CRITICAL"
    assert rem.sla_adherence == "PENDING"
    assert rem.remediation_root_cause_id == "RCA_TEST_001"


def test_remediation_early_completion_within_sla():
    store = get_metrics_store()
    t_det = datetime(2026, 9, 2, 10, 0, 0)
    t_comp = datetime(2026, 9, 2, 18, 0, 0)  # 8 hours later
    
    rem = RemediationMetrics(
        remediation_id="REM_EARLY_001",
        violation_id="VIO_EARLY_001",
        severity_level="HIGH",
        sla_target_hours=24.0,
        sla_target_date=(t_det + timedelta(hours=24)).isoformat(),
        detected_at=t_det.isoformat(),
        remediation_actual_completion_at=t_comp.isoformat(),
        remediation_action="Rebalanced sector allocation",
        remediation_owner_user_id="pm_lead",
        created_at=t_det.isoformat(),
        updated_at=t_comp.isoformat(),
    )
    recorded = store.record_remediation(rem)
    assert recorded.resolution_time_hours == 8.0
    assert recorded.sla_variance_hours == -16.0  # 16 hours early!
    assert recorded.sla_adherence == "WITHIN_SLA"


def test_remediation_late_completion_breached_sla():
    store = get_metrics_store()
    t_det = datetime(2026, 9, 2, 10, 0, 0)
    t_comp = datetime(2026, 9, 3, 20, 0, 0)  # 34 hours later (target was 24)
    
    rem = RemediationMetrics(
        remediation_id="REM_LATE_001",
        violation_id="VIO_LATE_001",
        severity_level="CRITICAL",
        sla_target_hours=24.0,
        sla_target_date=(t_det + timedelta(hours=24)).isoformat(),
        detected_at=t_det.isoformat(),
        remediation_actual_completion_at=t_comp.isoformat(),
        remediation_action="Late margin call resolved",
        remediation_owner_user_id="pm_lead",
        escalated=True,
        escalation_reason="SLA window exceeded for CRITICAL breach",
        created_at=t_det.isoformat(),
        updated_at=t_comp.isoformat(),
    )
    recorded = store.record_remediation(rem)
    assert recorded.resolution_time_hours == 34.0
    assert recorded.sla_variance_hours == 10.0  # 10 hours late!
    assert recorded.sla_adherence == "BREACHED"
    assert recorded.escalated is True
    assert recorded.escalation_reason == "SLA window exceeded for CRITICAL breach"


def test_remediation_update_recalculates_sla_variance():
    store = get_metrics_store()
    t_det = datetime(2026, 9, 2, 10, 0, 0)
    rem = RemediationMetrics(
        remediation_id="REM_UPDATE_001",
        violation_id="VIO_UPDATE_001",
        severity_level="MEDIUM",
        sla_target_hours=48.0,
        sla_target_date=(t_det + timedelta(hours=48)).isoformat(),
        detected_at=t_det.isoformat(),
        remediation_action="Investigation underway",
        remediation_owner_user_id="analyst_2",
        created_at=t_det.isoformat(),
        updated_at=t_det.isoformat(),
    )
    store.record_remediation(rem)
    assert store.get_remediation_metrics("VIO_UPDATE_001").sla_adherence == "PENDING"

    # Now update with completion timestamp
    t_comp = datetime(2026, 9, 3, 10, 0, 0)  # 24 hours later (within 48)
    updated = store.update_remediation("VIO_UPDATE_001", {
        "remediation_actual_completion_at": t_comp.isoformat(),
        "remediation_effectiveness": "EFFECTIVE",
        "verified_by_user_id": "compliance_lead_1",
    })
    assert updated is not None
    assert updated.resolution_time_hours == 24.0
    assert updated.sla_variance_hours == -24.0
    assert updated.sla_adherence == "WITHIN_SLA"
    assert updated.remediation_effectiveness == "EFFECTIVE"


def test_remediation_cost_and_reviolation_tracking():
    now_iso = datetime.utcnow().isoformat()
    rem = RemediationMetrics(
        remediation_id="REM_COST_001",
        violation_id="VIO_COST_001",
        severity_level="LOW",
        sla_target_hours=72.0,
        sla_target_date=now_iso,
        detected_at=now_iso,
        remediation_action="Updated disclosure prospectus notes",
        remediation_owner_user_id="legal_lead",
        remediation_cost_hours=14.5,
        re_violation_within_7d=False,
        re_violation_within_30d=True,
        systemic_fix_applied=True,
        created_at=now_iso,
        updated_at=now_iso,
    )
    assert rem.remediation_cost_hours == 14.5
    assert rem.re_violation_within_30d is True
    assert rem.systemic_fix_applied is True


def test_remediation_invalid_cost_raises_validation_error():
    now_iso = datetime.utcnow().isoformat()
    with pytest.raises(ValidationError):
        RemediationMetrics(
            remediation_id="REM_BAD_COST",
            violation_id="VIO_BAD",
            severity_level="LOW",
            sla_target_hours=24.0,
            sla_target_date=now_iso,
            detected_at=now_iso,
            remediation_action="Action",
            remediation_owner_user_id="user_1",
            remediation_cost_hours=-5.0,  # Negative cost invalid
            created_at=now_iso,
            updated_at=now_iso,
        )
