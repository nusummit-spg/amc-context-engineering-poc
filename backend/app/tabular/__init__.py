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

__all__ = [
    "contracts",
    "repository", 
    "planner",
    "executor",
    "ingester"
]
