"""
Base adapter interfaces for dependency injection.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class DatabaseAdapter(ABC):
    """Interface for feedback persistence operations."""

    @abstractmethod
    async def store_feedback(
        self,
        session_id: str,
        response_id: str,
        feedback_text: str,
        issue_types: List[str],
        source: str,
        **kwargs
    ) -> str:
        """Store feedback record and return assigned feedback_id."""
        pass

    @abstractmethod
    async def get_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve feedback by primary identifier."""
        pass

    @abstractmethod
    async def get_recent_feedback(
        self,
        limit: int = 20,
        issue_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve recent feedback records."""
        pass

    @abstractmethod
    async def store_evaluation_record(self, record: Dict[str, Any]) -> str:
        """Store unified evaluation record."""
        pass

    @abstractmethod
    async def close(self):
        """Cleanup connection resources."""
        pass


class EvidenceAdapter(ABC):
    """Interface for evidence pack storage."""

    @abstractmethod
    async def store_evidence(
        self,
        response_id: str,
        evidence: Dict[str, Any]
    ) -> str:
        """Store evidence pack and return reference key/path."""
        pass

    @abstractmethod
    async def retrieve_evidence(self, response_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve evidence pack for a given response_id."""
        pass

    @abstractmethod
    async def close(self):
        """Cleanup resources."""
        pass
