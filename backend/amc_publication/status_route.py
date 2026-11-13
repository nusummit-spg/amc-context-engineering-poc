"""PUB08: Read-only publication status and reconciliation route.

Provides a stable API for frontend and governance to check the state of
any publication job without exposing internal data structures.
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import CurrentUser
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PublicationWork, PublicationEffect, PublicationReceipt
from .journal import Journal

router = APIRouter(prefix="/api/publication", tags=["publication"])

def _get_job_status(work_id: str, sessions, *, tenant: str) -> Dict[str, Any]:
    """Read job status from the Journal."""
    journal = Journal(sessions)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant identity required")
    snapshot = journal.snapshot(work_id)
    # W26_TENANT_SCOPED_STATUS: never reveal another tenant’s job.
    if snapshot is None or snapshot.get("tenant") != tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication job {work_id} not found",
        )

    with sessions() as s:
        effects = s.scalars(
            select(PublicationEffect).where(
                PublicationEffect.work_id == work_id,
                PublicationEffect.tenant == tenant
            )
        ).all()
        receipts = s.scalars(
            select(PublicationReceipt).where(
                PublicationReceipt.work_id == work_id,
                PublicationReceipt.tenant == tenant
            )
        ).all()

    return {
        "work_id": work_id,
        "status": snapshot["status"],
        "tenant": snapshot.get("tenant"),
        "epoch": snapshot.get("epoch"),
        "attempts": snapshot.get("attempts"),
        "error_present": bool(snapshot.get("last_error")),
        "effects": [
            {
                "kind": e.kind,
                "target": e.target,
                "state": e.state,
                "verified_at": str(e.verified_at) if e.verified_at else None,
            }
            for e in effects
        ],
        "receipts": [
            {
                "receipt_id": r.id,
                "verified": r.verified,
                "generation_id": r.generation_id,
            }
            for r in receipts
        ],
    }

@router.get("/status/{work_id}")
def get_publication_status(work_id: str, current_user: CurrentUser) -> Dict[str, Any]:
    """Get the current status of a publication job.

    States: QUEUED, LEASED, published, rolled_back, failed, rollback_pending.
    """
    from app.core.database import SessionLocal
    # Role and tenant are derived from the authenticated session, NEVER query
    # parameters or X-User-Role headers. Missing tenant -> 403, no fallback.
    role = str(getattr(current_user, "role", "")).lower().strip().replace(" ", "_")
    tenant = getattr(current_user, "tenant_id", None)
    if role not in {"admin", "compliance_officer", "reviewer"} or not tenant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="authorized tenant-scoped reviewer required")
    return _get_job_status(work_id, SessionLocal, tenant=tenant)
    