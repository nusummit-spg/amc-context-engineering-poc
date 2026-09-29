# backend/app/adapters/__init__.py
from app.adapters.feedback_adapters import AMCDatabaseAdapter, AMCEvidenceAdapter

__all__ = ["AMCDatabaseAdapter", "AMCEvidenceAdapter"]
