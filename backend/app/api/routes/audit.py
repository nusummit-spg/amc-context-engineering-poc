#app/api/routes/audit.py

"""
audit.py
========
CRUD-lite endpoints (create + list/get) for the 7 AMC audit-schema tables,
so they can be exercised via API instead of only the seed script.

Endpoints (each table has POST + GET list, audit_metadata also has GET by id):
  /api/audit-schema/audit-metadata
  /api/audit-schema/violations
  /api/audit-schema/response-feedback
  /api/audit-schema/query-evidence
  /api/audit-schema/compliance-rules
  /api/audit-schema/fund-schemes
  /api/audit-schema/sessions
"""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import (
    AuditMetadata,
    Violation,
    ResponseFeedback,
    QueryEvidence,
    ComplianceRule,
    FundScheme,
    ChatSession,
)
from app.schemas.audit import (
    AuditMetadataCreate,
    ViolationCreate,
    ResponseFeedbackCreate,
    QueryEvidenceCreate,
    ComplianceRuleCreate,
    FundSchemeCreate,
    ChatSessionCreate,
)

router = APIRouter(prefix="/audit-schema", tags=["audit-schema"])


def _row_to_dict(row) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_row(db: Session, model_cls, data: dict):
    """Shared insert helper: commits, and turns FK/constraint failures into a 400
    instead of a raw 500, since a broken FK is exactly what we're testing for here."""
    row = model_cls(**data)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Constraint violation (bad foreign key, duplicate unique value, "
                   f"or failed CHECK constraint): {exc.orig}",
        )
    db.refresh(row)
    return row


# ---------------------------------------------------------
# audit_metadata
# ---------------------------------------------------------

@router.post("/audit-metadata", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_audit_metadata(payload: AuditMetadataCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, AuditMetadata, data)
    return _row_to_dict(row)


@router.get("/audit-metadata", response_model=List[dict])
def list_audit_metadata(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(AuditMetadata).order_by(AuditMetadata.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


@router.get("/audit-metadata/{audit_id}", response_model=dict)
def get_audit_metadata(audit_id: str, db: Session = Depends(get_db)):
    row = db.query(AuditMetadata).filter(AuditMetadata.audit_id == audit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="audit_id not found")
    return _row_to_dict(row)


# ---------------------------------------------------------
# violations
# ---------------------------------------------------------

@router.post("/violations", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_violation(payload: ViolationCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_none=True)
    data.setdefault("detected_at", _now_iso())
    row = _create_row(db, Violation, data)
    return _row_to_dict(row)


@router.get("/violations", response_model=List[dict])
def list_violations(
    audit_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Violation)
    if audit_id:
        q = q.filter(Violation.audit_id == audit_id)
    rows = q.order_by(Violation.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------
# response_feedback
# ---------------------------------------------------------

@router.post("/response-feedback", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_response_feedback(payload: ResponseFeedbackCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, ResponseFeedback, data)
    return _row_to_dict(row)


@router.get("/response-feedback", response_model=List[dict])
def list_response_feedback(
    response_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(ResponseFeedback)
    if response_id:
        q = q.filter(ResponseFeedback.response_id == response_id)
    rows = q.order_by(ResponseFeedback.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------
# query_evidence
# ---------------------------------------------------------

@router.post("/query-evidence", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_query_evidence(payload: QueryEvidenceCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, QueryEvidence, data)
    return _row_to_dict(row)


@router.get("/query-evidence", response_model=List[dict])
def list_query_evidence(
    session_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(QueryEvidence)
    if session_id:
        q = q.filter(QueryEvidence.session_id == session_id)
    rows = q.order_by(QueryEvidence.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------
# compliance_rules
# ---------------------------------------------------------

@router.post("/compliance-rules", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_compliance_rule(payload: ComplianceRuleCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, ComplianceRule, data)
    return _row_to_dict(row)


@router.get("/compliance-rules", response_model=List[dict])
def list_compliance_rules(
    region: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(ComplianceRule)
    if region:
        q = q.filter(ComplianceRule.region == region)
    rows = q.order_by(ComplianceRule.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------
# fund_schemes
# ---------------------------------------------------------

@router.post("/fund-schemes", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_fund_scheme(payload: FundSchemeCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, FundScheme, data)
    return _row_to_dict(row)


@router.get("/fund-schemes", response_model=List[dict])
def list_fund_schemes(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(FundScheme).order_by(FundScheme.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------
# sessions
# ---------------------------------------------------------

@router.post("/sessions", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_session(payload: ChatSessionCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, ChatSession, data)
    return _row_to_dict(row)


@router.get("/sessions", response_model=List[dict])
def list_sessions(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(ChatSession).order_by(ChatSession.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]