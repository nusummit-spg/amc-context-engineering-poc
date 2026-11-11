"""PUB08: Read-only publication status and reconciliation route.

Provides a stable API for frontend and governance to check the state of
any publication job without exposing internal data structures.
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PublicationWork, PublicationEffect, PublicationReceipt
from .journal import Journal

router = APIRouter(prefix="/api/publication", tags=["publication"])

def _get_job_status(work_id: str, sessions) -> Dict[str, Any]:
    """Read job status from the Journal."""
    journal = Journal(sessions)
    snapshot = journal.snapshot(work_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publication job {work_id} not found",
        )

    with sessions() as s:
        effects = s.scalars(
            select(PublicationEffect).where(
                PublicationEffect.work_id == work_id
            )
        ).all()
        receipts = s.scalars(
            select(PublicationReceipt).where(
                PublicationReceipt.work_id == work_id
            )
        ).all()

    return {
        "work_id": work_id,
        "status": snapshot["status"],
        "tenant": snapshot.get("tenant"),
        "epoch": snapshot.get("epoch"),
        "attempts": snapshot.get("attempts"),
        "last_error": snapshot.get("last_error"),
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
def get_publication_status(work_id: str) -> Dict[str, Any]:
    """Get the current status of a publication job.

    States: QUEUED, LEASED, published, rolled_back, failed, rollback_pending.
    """
    from app.core.database import SessionLocal
    return _get_job_status(work_id, SessionLocal)
    