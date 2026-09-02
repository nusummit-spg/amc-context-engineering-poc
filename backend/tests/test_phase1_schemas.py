# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_phase1_schemas.py
============================
Unit tests for the 6 Phase 1 Foundation Layer Pydantic schemas:
1. RegulatoryMetadata
2. FundAuditMetadata
3. RemediationMetrics
4. FeedbackQualityMetrics
5. FeedbackCategoryAnalytics
6. ResponseQualityMetrics
"""

import pytest
from pydantic import ValidationError

from app.schemas.regulatory_metadata import RegulatoryMetadata
from app.schemas.fund_metadata import FundAuditMetadata
from app.schemas.remediation_metrics import RemediationMetrics
from app.schemas.feedback_quality import FeedbackQualityMetrics
from app.schemas.feedback_analytics import FeedbackCategoryAnalytics
from app.schemas.response_quality import ResponseQualityMetrics


# ---------------------------------------------------------------------------
# 1. RegulatoryMetadata Schema Tests
# ---------------------------------------------------------------------------

def test_regulatory_metadata_valid():
    meta = RegulatoryMetadata(
        metadata_id="REG_META_001",
        rule_id="SEBI_EQUITY_ALLOC_001",
        regulation_source="SEBI",
        regulation_section="Circular SEBI/HO/IMD/DF3/CIR/P/2017/114 §2.1",
        regulation_url="https://www.sebi.gov.in/legal/circulars/oct-2017/36199.html",
        effective_date="2017-10-06",
        is_mandatory=True,
        enforcement_level="STRICT",
        framework_version="2026.1",
        jurisdiction_hierarchy=["GLOBAL", "IN", "SEBI"],
        related_regulations=["SEBI_MF_REG_1996"],
        supersedes_rules=["OLD_RULE_001"],
        created_by="auditor_1",
        updated_at="2026-08-17T10:00:00Z",
    )
    assert meta.metadata_id == "REG_META_001"
    assert meta.regulation_source == "SEBI"
    assert meta.is_mandatory is True
    assert len(meta.jurisdiction_hierarchy) == 3

    dumped = meta.model_dump()
    assert dumped["rule_id"] == "SEBI_EQUITY_ALLOC_001"


def test_regulatory_metadata_missing_mandatory_fields():
    with pytest.raises(ValidationError):
        RegulatoryMetadata(
            metadata_id="REG_001",
            # missing rule_id, regulation_source, etc.
        )


# ---------------------------------------------------------------------------
# 2. FundAuditMetadata Schema Tests
# ---------------------------------------------------------------------------

def test_fund_audit_metadata_valid():
    fund = FundAuditMetadata(
        fund_id="FUND_001",
        fund_name="Nippon India Large Cap Fund",
        fund_category="Large Cap Fund",
        fund_type="Open-ended",
        aum_cr=28450.75,
        fund_manager_id="MGR_001",
        fund_manager_experience_years=18.5,
        fund_creation_date="2007-08-08",
        benchmark_index="BSE 100 TRI",
        ytd_return_pct=16.82,
        expense_ratio_pct=0.82,
        portfolio_turnover_pct=24.5,
        sharpe_ratio=1.45,
        top_holding_concentration_pct=8.40,
        sector_concentration_max_pct=28.20,
        amc_id="AMC_NIPPON_INDIA",
        regulatory_status="ACTIVE",
        created_at="2026-08-17T10:00:00Z",
    )
    assert fund.fund_id == "FUND_001"
    assert fund.aum_cr == 28450.75
    assert fund.expense_ratio_pct == 0.82
    assert fund.top_holding_concentration_pct <= 100.0


def test_fund_audit_metadata_invalid_bounds():
    with pytest.raises(ValidationError):
        FundAuditMetadata(
            fund_id="FUND_002",
            fund_name="Test Fund",
            fund_category="Large Cap",
            fund_type="Open-ended",
            aum_cr=-50.0,  # Negative AUM should fail ge=0.0
            fund_manager_id="MGR_002",
            fund_manager_experience_years=5.0,
            fund_creation_date="2020-01-01",
            benchmark_index="NIFTY 50",
            ytd_return_pct=12.0,
            expense_ratio_pct=1.5,
            portfolio_turnover_pct=10.0,
            sharpe_ratio=1.0,
            top_holding_concentration_pct=150.0,  # Exceeds 100%
            sector_concentration_max_pct=30.0,
            amc_id="AMC_TEST",
            created_at="2026-08-17T10:00:00Z",
        )


# ---------------------------------------------------------------------------
# 3. RemediationMetrics Schema Tests
# ---------------------------------------------------------------------------

def test_remediation_metrics_valid():
    rem = RemediationMetrics(
        remediation_id="REM_001",
        violation_id="VIO_001",
        severity_level="CRITICAL",
        sla_target_hours=24.0,
        sla_target_date="2026-08-18T10:00:00Z",
        detected_at="2026-08-17T10:00:00Z",
        remediation_initiated_at="2026-08-17T11:00:00Z",
        remediation_action="Rebalanced single-issuer debt holding below 10%",
        remediation_owner_user_id="compliance_officer_1",
        remediation_actual_completion_at="2026-08-17T20:00:00Z",
        resolution_time_hours=10.0,
        sla_adherence="WITHIN_SLA",
        sla_variance_hours=-14.0,
        remediation_effectiveness="EFFECTIVE",
        verification_date="2026-08-18T08:00:00Z",
        verified_by_user_id="cco_user",
        re_violation_within_7d=False,
        re_violation_within_30d=False,
        root_cause_addressed=True,
        systemic_fix_applied=True,
        escalated=False,
        escalation_reason=None,
        remediation_cost_hours=4.5,
        created_at="2026-08-17T10:00:00Z",
        updated_at="2026-08-18T08:00:00Z",
    )
    assert rem.remediation_id == "REM_001"
    assert rem.sla_adherence == "WITHIN_SLA"
    assert rem.sla_variance_hours == -14.0
    assert rem.root_cause_addressed is True


# ---------------------------------------------------------------------------
# 4. FeedbackQualityMetrics Schema Tests
# ---------------------------------------------------------------------------

def test_feedback_quality_metrics_valid():
    fq = FeedbackQualityMetrics(
        quality_id="FQ_001",
        feedback_id="FB_001",
        response_id="RESP_001",
        detail_score=0.85,
        clarity_score=0.90,
        completeness_score=0.80,
        reviewer_credibility_score=0.95,
        actionability_score=0.90,
        is_actionable=True,
        action_difficulty="LOW",
        has_reproduction_steps=True,
        inter_reviewer_agreement_pct=95.0,
        signal_quality_score=0.88,
        is_duplicate_feedback=False,
        priority_tier="P0",
        evaluated_at="2026-08-17T10:00:00Z",
    )
    assert fq.priority_tier == "P0"
    assert fq.signal_quality_score == 0.88
    assert fq.is_actionable is True


# ---------------------------------------------------------------------------
# 5. FeedbackCategoryAnalytics Schema Tests
# ---------------------------------------------------------------------------

def test_feedback_category_analytics_valid():
    fca = FeedbackCategoryAnalytics(
        analytics_id="FCA_2024_09_F08",
        reporting_period="2024-09",
        category_id="F08",
        category_name="Factual / Numerical Accuracy",
        frequency_count=18,
        frequency_pct=36.0,
        trend="DECREASING",
        prior_period_count=24,
        category_velocity_pct=-25.0,
        median_response_severity="HIGH",
        avg_resolution_time_days=1.2,
        top_query_pattern="What is the expense ratio of X?",
        top_fund_with_category="FUND_001",
        recommended_action="Deploy strict numeric cell binding",
        estimated_effort_hours=12.0,
        period_start_date="2024-09-01",
    )
    assert fca.category_id == "F08"
    assert fca.frequency_count == 18
    assert fca.category_velocity_pct == -25.0
    assert fca.trend == "DECREASING"


# ---------------------------------------------------------------------------
# 6. ResponseQualityMetrics Schema Tests
# ---------------------------------------------------------------------------

def test_response_quality_metrics_valid():
    rq = ResponseQualityMetrics(
        response_quality_id="RQ_001",
        response_id="RESP_001",
        llm_model="openai/gpt-oss-120b",
        retrieval_mode="contextgraph",
        query_type="compliance_check",
        total_feedback_count=5,
        positive_feedback_count=4,
        negative_feedback_count=1,
        overall_quality_score=0.88,
        accuracy_score=0.92,
        clarity_score=0.85,
        compliance_risk_score=0.05,
        inter_reviewer_agreement_pct=100.0,
        failure_categories=["F06"],
        most_common_failure_category="F06",
        response_improved=True,
        comparable_traditional_score=0.63,
        comparable_contextgraph_score=0.88,
        mode_performance_delta=0.25,
        top_k_used=5,
    )
    assert rq.response_id == "RESP_001"
    assert rq.overall_quality_score == 0.88
    assert rq.mode_performance_delta == 0.25
    assert rq.retrieval_mode == "contextgraph"
