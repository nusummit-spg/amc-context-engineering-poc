# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
Tabular Data Module (Wave 1 - G03, G04, G05)
=============================================

This module implements the canonical financial data model, typed CSV/XLSX 
ingestion, and deterministic query execution for exact numerical answers.

Key Principles:
- Source data is immutable and versioned
- All financial calculations use typed SQL, never LLM generation
- Every result includes source row proofs and reconciliation
- No numeric fallback to vector/embedding approximations

Architecture:
- contracts.py: Canonical schema, identity, and metric definitions
- repository.py: Typed data access with tenant/version isolation
- planner.py: Intent→QueryPlan validation and compilation
- executor.py: Deterministic SQL execution with proofs
- ingester.py: Full-file CSV/XLSX parsing and staging
"""

from app.tabular.contracts import *
from app.tabular.repository import FinancialDataRepository, SourceRow, NAVObservation, AAUMObservation
from app.tabular.csv_excel_loader import StreamingCSVParser, IngestionPipeline, CanonicalNormalizer
from app.tabular.planner import PlanIntent, QueryPlan, QueryPlanner
from app.tabular.executor import QueryResult, QueryExecutor

__all__ = [
    "contracts",
    "repository", 
    "csv_excel_loader",
    "planner",
    "executor",
    "FinancialDataRepository",
    "SourceRow",
    "NAVObservation",
    "AAUMObservation",
    "StreamingCSVParser",
    "IngestionPipeline",
    "CanonicalNormalizer",
    "PlanIntent",
    "QueryPlan",
    "QueryPlanner",
    "QueryResult",
    "QueryExecutor",
]
