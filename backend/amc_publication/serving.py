"""Serving authorization depends on verified persisted publication evidence.

Do NOT interpret legacy patch.approved or a synthetic verification receipt as
sufficient for serving. Every request must bind tenant, work and receipt.
"""
from .feedback import FeedbackCausality


def is_serving_eligible(sessions, *, tenant: str, status: str,
                        work_id: str | None, receipt_id: str | None,
                        revoked: bool = False, expired: bool = False) -> bool:
    if not tenant or not work_id or not receipt_id or revoked or expired:
        return False
    if status.upper() != "ACTIVE":
        return False
    return FeedbackCausality(sessions).is_verified_active(tenant, work_id, receipt_id)
