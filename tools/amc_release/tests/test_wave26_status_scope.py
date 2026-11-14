"""Status-route source-adapter contract, tenant and reviewer isolation."""
from tools.amc_release.publication_patch26 import harden_status_route26, SourceDrift
import pytest

ORIGINAL='''from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import PublicationWork, PublicationEffect, PublicationReceipt
from .journal import Journal

router = APIRouter(prefix="/api/publication", tags=["publication"])
def _get_job_status(work_id: str, sessions) -> Dict[str, Any]:
    journal = Journal(sessions)
    snapshot = journal.snapshot(work_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
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
        "last_error": snapshot.get("last_error"),
        "effects": effects,
        "receipts": receipts,
    }

@router.get("/status/{work_id}")
def get_publication_status(work_id: str) -> Dict[str, Any]:
    from app.core.database import SessionLocal
    return _get_job_status(work_id, SessionLocal)
'''


def test_readonly_status_requires_jwt_and_tenant():
    new=harden_status_route26(ORIGINAL)
    assert 'CurrentUser' in new
    assert 'W26_TENANT_SCOPED_STATUS' in new
    assert 'snapshot.get("tenant") != tenant' in new
    assert 'PublicationEffect.tenant == tenant' in new
    assert 'PublicationReceipt.tenant == tenant' in new
    assert '"error_present"' in new and '"last_error":' not in new
    compile(new,'status_route.py','exec')


def test_no_tenant_header_fallback():
    new=harden_status_route26(ORIGINAL)
    assert 'getattr(current_user, "tenant_id", None)' in new
    assert 'X-User-Role' in new  # explicitly prohibited by comment
    assert 'authorized tenant-scoped reviewer required' in new


def test_status_source_drift_fails_closed():
    with pytest.raises(SourceDrift):harden_status_route26(ORIGINAL.replace('PublicationReceipt.work_id == work_id','PublicationReceipt.work_id == other'))


def test_previously_patched_status_refused():
    with pytest.raises(SourceDrift):harden_status_route26(harden_status_route26(ORIGINAL))
