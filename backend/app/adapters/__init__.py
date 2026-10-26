# backend/app/adapters/__init__.py
"""Initialization module for adapters package."""

from app.adapters.feedback_adapters import AMCDatabaseAdapter, AMCEvidenceAdapter

__all__ = ["AMCDatabaseAdapter", "AMCEvidenceAdapter"]
