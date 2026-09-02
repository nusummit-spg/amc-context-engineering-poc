# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
tests/test_phase2_schemas.py
============================
Unit tests for the 4 Phase 2 Analysis Layer Pydantic schemas:
1. RootCauseAnalysis
2. ViolationCluster
3. EvidenceMetadata
4. FundFamilyAnalysis
"""

import pytest
from pydantic import ValidationError

from app.schemas.root_cause_analysis import RootCauseAnalysis
from app.schemas.violation_cluster import ViolationCluster
from app.schemas.evidence_metadata import EvidenceMetadata
from app.schemas.fund_family_analysis import FundFamilyAnalysis


# ---------------------------------------------------------------------------
# 1. RootCauseAnalysis Schema Tests
# ---------------------------------------------------------------------------

def test_root_cause_analysis_valid():
    rca = RootCauseAnalysis(
        rca_id="RCA_TEST_001",
        violation_id="VIO_TEST_001",
        primary_category="operational_error",
        secondary_categories=["system_failure"],
        root_cause_description="Trade allocation failure due to rounding precision mismatch in portfolio engine.",
        is_systemic=True,
        repeat_violation_count=2,
        cluster_id="CLUSTER_001",
        market_context="High volatility expiry day",
        contributing_factors=["Feed latency", "Server queue saturation"],
        detection_mechanism="rules_engine",
        preventability_score=0.90,
        recommended_remedy_type="GUARDRAIL_UPDATE",
        investigated_by="compliance_officer_1",
        analyzed_at="2026-08-17T12:00:00Z",
    )
    assert rca.rca_id == "RCA_TEST_001"
    assert rca.primary_category == "operational_error"
    assert rca.is_systemic is True
    assert rca.preventability_score == 0.90
    assert len(rca.secondary_categories) == 1


def test_root_cause_analysis_invalid_bounds():
    with pytest.raises(ValidationError):
        RootCauseAnalysis(
            rca_id="RCA_BAD",
            violation_id="VIO_BAD",
            primary_category="operational_error",
            root_cause_description="Test",
            preventability_score=1.5,  # Exceeds 1.0
            analyzed_at="2026-08-17T12:00:00Z",
        )


# ---------------------------------------------------------------------------
# 2. ViolationCluster Schema Tests
# ---------------------------------------------------------------------------

def test_violation_cluster_valid():
    cluster = ViolationCluster(
        cluster_id="CLUSTER_TEST_001",
        cluster_name="Debt Concentration Across Hybrid Schemes",
        violation_ids=["VIO_001", "VIO_002"],
        common_rule_ids=["SEBI_SINGLE_ISSUER_004"],
        affected_fund_ids=["FUND_001", "FUND_003"],
        affected_amc_id="AMC_NIPPON_INDIA",
        severity="CRITICAL",
        cluster_density_score=0.85,
        is_systemic_risk=True,
        created_at="2026-08-17T12:00:00Z",
    )
    assert cluster.cluster_id == "CLUSTER_TEST_001"
    assert len(cluster.violation_ids) == 2
    assert cluster.cluster_density_score == 0.85
    assert cluster.severity == "CRITICAL"


def test_violation_cluster_empty_violations_fails():
    with pytest.raises(ValidationError):
        ViolationCluster(
            cluster_id="CLUSTER_BAD",
            cluster_name="Empty Cluster",
            violation_ids=[],  # min_length=1 required
            affected_amc_id="AMC_TEST",
            cluster_density_score=0.5,
            created_at="2026-08-17T12:00:00Z",
        )


# ---------------------------------------------------------------------------
# 3. EvidenceMetadata Schema Tests
# ---------------------------------------------------------------------------

def test_evidence_metadata_valid():
    evidence = EvidenceMetadata(
        evidence_id="EVID_TEST_001",
        document_id="DOC_SEBI_CIRCULAR_114",
        document_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        collected_at="2026-08-17T12:00:00Z",
        retention_expiry_date="2034-08-17",
        relevance_score=0.96,
        chain_of_custody_signoff="OFFICER_SIGN_123",
        source_authority_tier="TIER_1_REGULATOR",
        is_tamper_evident=True,
    )
    assert evidence.evidence_id == "EVID_TEST_001"
    assert evidence.relevance_score == 0.96
    assert evidence.is_tamper_evident is True
    assert evidence.source_authority_tier == "TIER_1_REGULATOR"


# ---------------------------------------------------------------------------
# 4. FundFamilyAnalysis Schema Tests
# ---------------------------------------------------------------------------

def test_fund_family_analysis_valid():
    analysis = FundFamilyAnalysis(
        analysis_id="FFA_TEST_001",
        amc_id="AMC_HDFC_MF",
        fund_family_name="HDFC Mutual Fund Family",
        total_funds_analyzed=18,
        cross_fund_correlation_score=0.28,
        portfolio_manager_accountability_scores={
            "MGR_ROSHI_JAIN": 0.97,
            "MGR_CHIRAG_SETALVAD": 0.94,
        },
        systemic_risk_flag=False,
        dominant_violation_category="F05",
        highest_risk_fund_id="FUND_002",
        analyzed_at="2026-08-17T12:00:00Z",
    )
    assert analysis.amc_id == "AMC_HDFC_MF"
    assert analysis.total_funds_analyzed == 18
    assert analysis.cross_fund_correlation_score == 0.28
    assert analysis.systemic_risk_flag is False
    assert analysis.portfolio_manager_accountability_scores["MGR_ROSHI_JAIN"] == 0.97
