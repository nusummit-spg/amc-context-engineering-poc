"""Release evidence inspection: durable DB facts, not invented uptime or SLOs.

Can assert counts/readiness and explicitly exposes UNKNOWN measurements. It
CANNOT approve a release: requires independent integration + external signing.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker


@dataclass(frozen=True)
class AssuranceSnapshot:
    tenant: str
    jobs_by_status: dict[str, int]
    effects_by_status: dict[str, int]
    receipts: int
    feedback_links: dict[str, int]
    operational_readiness: str
    p95_latency: str
    observed_uptime: str
    release_gate: str

    def to_dict(self):
        return asdict(self)


class DurableAssuranceReader:
    def __init__(self, sessions: sessionmaker):
        self.sessions = sessions

    def snapshot(self, tenant: str) -> AssuranceSnapshot:
        if not tenant:
            raise ValueError("tenant required")
        from amc_publication.models import PublicationWork, PublicationEffect, PublicationReceipt, FeedbackPublicationLink
        with self.sessions() as s:
            jobs = dict(s.execute(select(PublicationWork.status, func.count()).where(
                PublicationWork.tenant == tenant).group_by(PublicationWork.status)).all())
            effects = dict(s.execute(select(PublicationEffect.state, func.count()).where(
                PublicationEffect.tenant == tenant).group_by(PublicationEffect.state)).all())
            receipts = s.scalar(select(func.count()).select_from(PublicationReceipt).where(
                PublicationReceipt.tenant == tenant)) or 0
            links = dict(s.execute(select(FeedbackPublicationLink.status, func.count()).where(
                FeedbackPublicationLink.tenant == tenant).group_by(FeedbackPublicationLink.status)).all())
        # A DB record is not a continuous availability measurement; never infer uptime.
        if not jobs:
            readiness = "UNKNOWN"
        elif jobs.get("failed", 0) or jobs.get("rollback_pending", 0):
            readiness = "FAIL"
        elif jobs.get("queued", 0) or jobs.get("leased", 0) or not jobs.get("published", 0):
            readiness = "INCOMPLETE"
        elif receipts < jobs.get("published", 0):
            readiness = "FAIL"
        else:
            readiness = "EVIDENCE_PRESENT_NOT_RELEASE_APPROVED"
        return AssuranceSnapshot(tenant, jobs, effects, receipts, links, readiness,
                                 "UNKNOWN_NO_LATENCY_SAMPLES", "UNKNOWN_NO_SLO_WINDOWS", "BLOCK")
