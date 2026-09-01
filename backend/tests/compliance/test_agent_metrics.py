# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_agent_metrics.py
=====================
Tests domain agent metrics collection, percentile calculation, and telemetry.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.compliance.agents.orchestrator import ComplianceAgentOrchestrator
from app.compliance.rules_engine import RulesEngine
from app.schemas.compliance_models import AgentMetrics, AggregatedAgentMetrics


@pytest.fixture
def mock_orchestrator():
    mock_g = MagicMock()
    mock_g.run = AsyncMock(return_value=[])
    mock_g.ping = AsyncMock(return_value=True)
    engine = RulesEngine(graph_client=mock_g)
    return ComplianceAgentOrchestrator(graph_client=mock_g, rules_engine=engine)


@pytest.mark.asyncio
async def test_orchestrator_metrics_collection(mock_orchestrator):
    res = await mock_orchestrator.audit_fund_all_domains("SEBI_FUND_001")

    assert "audit_latency_ms" in res
    assert res["audit_latency_ms"] >= 0.0

    metrics = mock_orchestrator.get_agent_metrics(region="SEBI")
    assert len(metrics) == 5
    assert "PortfolioAgent" in metrics
    assert "GovernanceAgent" in metrics
    assert "KYCAgent" in metrics
    assert "RiskAgent" in metrics
    assert "ReportingAgent" in metrics

    p_metric = metrics["PortfolioAgent"]
    assert isinstance(p_metric, AgentMetrics)
    assert p_metric.avg_latency_ms >= 0.0
    assert p_metric.p95_latency_ms >= 0.0
    assert p_metric.p99_latency_ms >= 0.0
    assert p_metric.accuracy_score == 0.95


@pytest.mark.asyncio
async def test_audit_all_funds_concurrency(mock_orchestrator):
    funds = [
        {"fund_id": f"TEST_FUND_{i}", "category": "equity_fund", "region": "SEBI"}
        for i in range(5)
    ]
    batch_res = await mock_orchestrator.audit_all_funds(funds=funds, region="SEBI", concurrency=5)

    assert batch_res["total_funds"] == 5
    assert "scores_by_domain" in batch_res
    assert "violations_by_domain" in batch_res
    assert batch_res["elapsed_ms"] < 2000.0  # Fast parallel execution

