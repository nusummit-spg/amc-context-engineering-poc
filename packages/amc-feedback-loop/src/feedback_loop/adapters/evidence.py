"""
Evidence adapter  read-only access to AMC's interaction_evidence table
and in-session follow-up query activity.

The abstract base defines the contract.  The InMemoryEvidenceAdapter is the
test stub.  Production implementations call AMC's internal API or DB directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from feedback_loop.domain_models import EvidenceChunk, EvidenceSnapshot, FollowUpQuery


class AbstractEvidenceAdapter(ABC):
    """
    Read-only contract over AMC's interaction_evidence table and
    in-session query log.

    The module never writes to these sources  it only reads via this
    interface to stay decoupled from AMC's schema.
    """

    @abstractmethod
    def get_evidence_snapshot(self, response_id: str) -> EvidenceSnapshot:
        """Fetch the frozen D0â€“D3 context for a given response_id.
        Raises KeyError if the response is not found in interaction_evidence.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            EvidenceSnapshot: Resulting EvidenceSnapshot instance.
        """
        ...

    @abstractmethod
    def get_followup_activity(
        self,
        session_id: str,
        response_id: str,
        window_minutes: int,
    ) -> list[FollowUpQuery]:
        """Return follow-up queries made in the same session within
        *window_minutes* after the given response was delivered.

        Returns an empty list when the user made no follow-up (silence).
        The caller (Step 2 / dissatisfaction detection) interprets an empty
        list as automatic  nothing to infer.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            window_minutes (int): Collection or list of window minutes.

        Returns:
            list[FollowUpQuery]: List of resulting items or records.
        """
        ...

    @abstractmethod
    def validate_response_exists(self, response_id: str) -> bool:
        """Fast existence check against ResponseMetadataCache (24h TTL).
        Returns True when the response_id is known; False / raises when not.
        This mirrors AMC's ~1ms cache lookup described in Section 2.3.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        ...


#  In-memory stub (tests / local dev) 

class InMemoryEvidenceAdapter(AbstractEvidenceAdapter):
    """
    Thread-safe in-memory adapter.  Pre-seed with snapshots and follow-ups
    for test scenarios.  Not for production use.
    """

    def __init__(self) -> None:
        """Initialize a new instance of InMemoryEvidenceAdapter.
        """
        # response_id â†’ EvidenceSnapshot
        self._snapshots: dict[str, EvidenceSnapshot] = {}
        # session_id â†’ list[FollowUpQuery] (ordered by created_at)
        self._followups: dict[str, list[FollowUpQuery]] = {}
        # response_id set that passes the cache check
        self._known_responses: set[str] = set()

    #  Seeding helpers 

    def seed_snapshot(self, snapshot: EvidenceSnapshot) -> None:
        """Seed snapshot.

        Args:
            snapshot (EvidenceSnapshot): The snapshot.
        """
        self._snapshots[snapshot.response_id] = snapshot
        self._known_responses.add(snapshot.response_id)

    def seed_followups(self, session_id: str, queries: list[FollowUpQuery]) -> None:
        """Seed followups.

        Args:
            session_id (str): Unique identifier of the session.
            queries (list[FollowUpQuery]): Collection or list of queries.
        """
        self._followups[session_id] = sorted(queries, key=lambda q: q.created_at)

    def seed_known_response(self, response_id: str) -> None:
        """Seed known response.

        Args:
            response_id (str): Unique identifier of the response.
        """
        self._known_responses.add(response_id)

    #  AbstractEvidenceAdapter implementation 

    def get_evidence_snapshot(self, response_id: str) -> EvidenceSnapshot:
        """Retrieve evidence snapshot.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            EvidenceSnapshot: Resulting EvidenceSnapshot instance.
        """
        try:
            return self._snapshots[response_id]
        except KeyError:
            raise KeyError(
                f"No interaction_evidence snapshot found for response_id={response_id}"
            )

    def get_followup_activity(
        self,
        session_id: str,
        response_id: str,
        window_minutes: int,
    ) -> list[FollowUpQuery]:
        """Returns all follow-ups for the session.
        In-memory stub ignores the time window  tests control the list directly.
        A production implementation filters by created_at within the window.

        Args:
            session_id (str): Unique identifier of the session.
            response_id (str): Unique identifier of the response.
            window_minutes (int): Collection or list of window minutes.

        Returns:
            list[FollowUpQuery]: List of resulting items or records.
        """
        return list(self._followups.get(session_id, []))

    def validate_response_exists(self, response_id: str) -> bool:
        """Validate response exists.

        Args:
            response_id (str): Unique identifier of the response.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        return response_id in self._known_responses

