"""Read-only, tenant-scoped Feedback ↔ Wave1.9 publication audit.

No issue transitions here. Validation joins actual durable SQL state and never
uses staging counts, generated IDs or optimistic pseudo-receipts.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker


@dataclass(frozen=True)
class FeedbackAudit:
    issue_id: str
    tenant: str
    issue_status: str
    publication_link_status: str | None
    verified_active: bool
    verdict: str
    reasons: tuple[str, ...]

    def to_dict(self):
        return asdict(self)


class FeedbackEvidenceAuditor:
    def __init__(self, *, publication_sessions: sessionmaker, issue_sessions: sessionmaker):
        self.publication_sessions = publication_sessions
        self.issue_sessions = issue_sessions

    def audit(self, tenant: str, issue_id: str) -> FeedbackAudit:
        if not tenant or not issue_id:
            raise ValueError("explicit tenant and issue ID required")
        from amc_publication.models import FeedbackPublicationLink
        from amc_publication.feedback import FeedbackCausality
        # Read under tenant scope. NULL issue tenants are unknown/untrusted.
        with self.issue_sessions() as s:
            row = s.execute(text("SELECT issue_id,tenant_id,status FROM feedback_issues WHERE issue_id=:id"),
                            {"id": issue_id}).mappings().first()
        if not row or row["tenant_id"] != tenant:
            return FeedbackAudit(issue_id, tenant, "UNKNOWN", None, False, "BLOCK", ("ISSUE_NOT_FOUND_IN_TENANT",))
        status = str(row["status"])
        with self.publication_sessions() as s:
            link = s.get(FeedbackPublicationLink, (tenant, issue_id))
            if link:
                work_id, receipt_id, linked_status = link.work_id, link.receipt_id, link.status
            else:
                work_id = receipt_id = linked_status = None
        verified = bool(link and FeedbackCausality(self.publication_sessions).is_verified_active(tenant, work_id, receipt_id))
        reasons = []
        if status in ("resolved", "closed") and not verified:
            reasons.append("ISSUE_CLOSED_WITHOUT_ACTIVE_VERIFIED_PUBLICATION")
        if status in ("resolved", "closed") and linked_status != "resolved":
            reasons.append("ISSUE_LINK_STATE_MISMATCH")
        if linked_status == "resolved" and not verified:
            reasons.append("LINK_STALE_OR_PUBLICATION_REVOKED")
        if linked_status == "resolved" and status not in ("resolved", "closed"):
            reasons.append("LINK_RESOLVED_BUT_ISSUE_NOT_RESOLVED")
        if linked_status == "needs_review" and status in ("resolved", "closed"):
            reasons.append("ROLLBACK_ISSUE_NOT_REOPENED")
        return FeedbackAudit(issue_id, tenant, status, linked_status, verified,
                             "BLOCK" if reasons else "CONSISTENT", tuple(reasons))
