"""Fail-closed adapter from an approved application proposal to durable work.

The trusted caller must assemble a full, tenant-isolated snapshot from the
canonical document catalog, not untrusted HTTP request data.
This module never calls Neo4j or FAISS directly.
"""
from dataclasses import dataclass
from typing import Any
from .journal import Journal
from .types import Conflict


@dataclass(frozen=True)
class ApprovedProposal:
    proposal_id: str
    tenant: str
    revision: int
    proposer_id: str
    reviewer_id: str
    status: str
    entity_id: str
    attribute: str
    proposed_value: Any


def queue_verified_approval(journal: Journal, proposal: ApprovedProposal,
                            complete_corpus_snapshot: list[dict]) -> str:
    if proposal.status.upper() != "APPROVED":
        raise Conflict("publication requires an explicitly APPROVED persisted proposal")
    if not proposal.proposer_id or not proposal.reviewer_id or proposal.proposer_id == proposal.reviewer_id:
        raise Conflict("independent human proposer/reviewer IDs are mandatory")
    if proposal.revision < 1:
        raise Conflict("approved revision must be positive")
    if not proposal.tenant or not proposal.entity_id or not proposal.attribute:
        raise Conflict("tenant-scoped target identity is required")
    if not isinstance(complete_corpus_snapshot, list):
        raise Conflict("complete snapshot must come from the trusted corpus catalog")
    # The store validates each row and its tenant again before staging.
    return journal.submit(tenant=proposal.tenant,
                          key=f"{proposal.proposal_id}:r{proposal.revision}",
                          proposal_id=proposal.proposal_id, revision=proposal.revision,
                          payload={"entity":proposal.entity_id,
                                   "attribute": proposal.attribute,
                                   "corrected_value": proposal.proposed_value,
                                   "full_vector_snapshot": complete_corpus_snapshot})
