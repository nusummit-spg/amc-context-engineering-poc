"""Feedback causality based on verified durable work and receipt rows."""
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from .models import (
    PublicationWork, PublicationEffect, PublicationReceipt, GenerationPointer,
    FeedbackPublicationLink, utcnow
)
from .types import Conflict


class FeedbackCausality:
    def __init__(self, sessions: sessionmaker):
        self.sessions = sessions

    def is_verified_active(self, tenant: str, work_id: str, receipt_id: str) -> bool:
        with self.sessions() as s:
            job = s.get(PublicationWork, work_id)
            receipt = s.get(PublicationReceipt, receipt_id)
            if not job or not receipt or job.tenant != tenant or receipt.tenant != tenant:
                return False
            if job.status != "published" or not receipt.verified or receipt.work_id != job.id:
                return False
            ptr = s.get(GenerationPointer, (tenant, "vector_faiss"))
            if not ptr or ptr.generation_id != receipt.generation_id or ptr.artifact_digest != receipt.generation_digest:
                return False
            effects = s.scalars(select(PublicationEffect).where(PublicationEffect.work_id == work_id)).all()
            return len(effects) == 2 and {e.kind for e in effects} == {"graph", "vector"} and all(e.state == "verified" for e in effects)

    def resolve(self, tenant: str, issue_id: str, work_id: str, receipt_id: str) -> bool:
        if not self.is_verified_active(tenant, work_id, receipt_id):
            return False
        with self.sessions.begin() as s:
            link = s.get(FeedbackPublicationLink, (tenant, issue_id))
            if link and (link.work_id != work_id or link.receipt_id != receipt_id):
                raise Conflict("feedback issue already linked to another publication")
            if link:
                link.status = "resolved"
            else:
                s.add(FeedbackPublicationLink(tenant=tenant, issue_id=issue_id,
                                              work_id=work_id, receipt_id=receipt_id,
                                              status="resolved"))
        return True

    def reopen_after_rollback(self, tenant: str, work_id: str) -> int:
        """Persistently flag issues whose publication was revoked."""
        with self.sessions.begin() as s:
            job = s.get(PublicationWork, work_id)
            if not job or job.tenant != tenant or job.status != "rolled_back":
                raise Conflict("rollback is not verified for this tenant")
            links = s.scalars(select(FeedbackPublicationLink).where(
                FeedbackPublicationLink.tenant == tenant,
                FeedbackPublicationLink.work_id == work_id,
                FeedbackPublicationLink.status == "resolved")).all()
            for link in links:
                link.status = "needs_review"
                link.updated_at = utcnow()
            return len(links)

    def status(self, tenant: str, issue_id: str) -> str:
        with self.sessions() as s:
            link = s.get(FeedbackPublicationLink, (tenant, issue_id))
            return link.status if link else "unlinked"
