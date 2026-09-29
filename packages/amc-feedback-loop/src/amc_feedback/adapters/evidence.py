"""
Evidence pack storage adapters.
"""
from typing import Any, Dict, Optional
from .base import EvidenceAdapter

class InMemoryEvidenceAdapter(EvidenceAdapter):
    """In-memory evidence adapter for ephemeral storage / testing."""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    async def store_evidence(self, response_id: str, evidence: Dict[str, Any]) -> str:
        self._store[response_id] = evidence
        return response_id

    async def retrieve_evidence(self, response_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(response_id)

    async def close(self):
        self._store.clear()
