# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Unit tests for compliance CSV seed ingestion."""
from pathlib import Path
import pytest
from app.ingestion.compliance_rules_ingester import ComplianceRulesIngester, seed_compliance_data

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "compliance"


@pytest.mark.asyncio
async def test_ingest_regulations_csv(mock_graph):
    ingester = ComplianceRulesIngester(mock_graph)
    csv_file = DATA_DIR / "sebi_regulations.csv"
    assert csv_file.exists()

    result = await ingester.ingest_regulations_csv(csv_file)
    assert result["status"] == "success"
    assert result["regulations_created"] >= 5
    assert result["error_count"] == 0


@pytest.mark.asyncio
async def test_ingest_rules_csv(mock_graph):
    ingester = ComplianceRulesIngester(mock_graph)
    csv_file = DATA_DIR / "rules.csv"
    assert csv_file.exists()

    result = await ingester.ingest_rules_csv(csv_file)
    assert result["status"] == "success"
    assert result["rules_created"] >= 8
    assert result["error_count"] == 0


@pytest.mark.asyncio
async def test_ingest_fund_schemes_csv(mock_graph):
    ingester = ComplianceRulesIngester(mock_graph)
    csv_file = DATA_DIR / "fund_schemes.csv"
    assert csv_file.exists()

    result = await ingester.ingest_fund_schemes_csv(csv_file)
    assert result["status"] == "success"
    assert result["funds_created"] >= 4
    assert result["error_count"] == 0


@pytest.mark.asyncio
async def test_seed_compliance_data(mock_graph):
    results = await seed_compliance_data(mock_graph, data_dir=DATA_DIR)
    assert results["regulations"]["status"] == "success"
    assert results["rules"]["status"] == "success"
    assert results["funds"]["status"] == "success"
