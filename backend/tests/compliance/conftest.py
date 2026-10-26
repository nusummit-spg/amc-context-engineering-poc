# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Pytest fixtures for AMC Compliance Auditing tests."""
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.compliance.rules_engine import RulesEngine
from app.compliance.violation_detector import ViolationDetector
from app.compliance.agents.orchestrator import ComplianceAgentOrchestrator


@pytest.fixture
def mock_graph():
    """Mock GraphClient for in-memory unit tests."""
    mock = MagicMock()
    mock.run = AsyncMock(return_value=[])
    mock.ping = AsyncMock(return_value=True)
    return mock


@pytest.fixture
async def rules_engine(mock_graph):
    """Pre-loaded RulesEngine fixture."""
    engine = RulesEngine(mock_graph)
    await engine.load_rules()
    return engine


@pytest.fixture
async def violation_detector(mock_graph, rules_engine):
    """Pre-loaded ViolationDetector fixture."""
    return ViolationDetector(mock_graph, rules_engine)


@pytest.fixture
async def compliance_orchestrator(mock_graph, rules_engine):
    """Pre-loaded ComplianceAgentOrchestrator fixture."""
    return ComplianceAgentOrchestrator(mock_graph, rules_engine)
