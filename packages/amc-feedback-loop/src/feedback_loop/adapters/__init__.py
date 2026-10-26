"""
Adapter layer — abstract contracts and in-memory stubs.

Host applications implement AbstractDatabaseAdapter and AbstractEvidenceAdapter
against their own persistence and AMC data layers, then pass the instances
into start_feedback_loop().
"""

from feedback_loop.adapters.db import AbstractDatabaseAdapter, InMemoryDatabaseAdapter
from feedback_loop.adapters.evidence import AbstractEvidenceAdapter, InMemoryEvidenceAdapter

__all__ = [
    "AbstractDatabaseAdapter",
    "InMemoryDatabaseAdapter",
    "AbstractEvidenceAdapter",
    "InMemoryEvidenceAdapter",
]
