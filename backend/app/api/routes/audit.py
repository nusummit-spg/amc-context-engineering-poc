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
from app.api.deps import CurrentUser
from app.core.database import get_db
from app.schemas.audit_metadata_table import AuditMetadata
from app.schemas.violations_table import Violation
from app.schemas.response_feedback_table import ResponseFeedback
from app.schemas.query_evidence_table import QueryEvidence
from app.schemas.compliance_rules_table import ComplianceRule
from app.schemas.fund_schemes_table import FundScheme
from app.schemas.chat_sessions_table import ChatSession

from app.models.audit import (
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
    """Convert row into dict.

    Args:
        row: The row.

    Returns:
        dict: Dictionary containing result data or status.
    """
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def _now_iso() -> str:
    """Now iso.

    Returns:
        str: Resulting str instance.
    """
    return datetime.now(timezone.utc).isoformat()


def _create_row(db: Session, model_cls, data: dict):
    """Shared insert helper: commits, and turns FK/constraint failures into a 400
    instead of a raw 500, since a broken FK is exactly what we're testing for here.

    Args:
        db (Session): Database session instance.
        model_cls: Collection or list of model cls.
        data (dict): Input data payload.

    Returns:
        Result of the operation.
    """
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
    """Create or process create audit metadata.

    Args:
        payload (AuditMetadataCreate): Request or event payload.
        db (Session): Database session instance.

    Returns:
        Result of the operation.
    """
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, AuditMetadata, data)
    return _row_to_dict(row)


@router.get("/audit-metadata", response_model=List[dict])
def list_audit_metadata(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """Retrieve list audit metadata.

    Args:
        limit (int): Maximum number of records to return.
        db (Session): Database session instance.

    Returns:
        List of audit metadata.
    """
    rows = db.query(AuditMetadata).order_by(AuditMetadata.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


@router.get("/audit-metadata/{audit_id}", response_model=dict)
def get_audit_metadata(audit_id: str, db: Session = Depends(get_db)):
    """Retrieve get audit metadata.

    Args:
        audit_id (str): Unique identifier of the audit.
        db (Session): Database session instance.

    Returns:
        The requested audit metadata.
    """
    row = db.query(AuditMetadata).filter(AuditMetadata.audit_id == audit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="audit_id not found")
    return _row_to_dict(row)


# ---------------------------------------------------------
# violations
# ---------------------------------------------------------

@router.post("/violations", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_violation(payload: ViolationCreate, db: Session = Depends(get_db)):
    """Create or process create violation.

    Args:
        payload (ViolationCreate): Request or event payload.
        db (Session): Database session instance.

    Returns:
        Result of the operation.
    """
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
    """Retrieve list violations.

    Args:
        audit_id (str | None): Unique identifier of the audit.
        limit (int): Maximum number of records to return.
        db (Session): Database session instance.

    Returns:
        List of violations.
    """
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
    """Create or process create response feedback.

    Args:
        payload (ResponseFeedbackCreate): Request or event payload.
        db (Session): Database session instance.

    Returns:
        Result of the operation.
    """
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, ResponseFeedback, data)
    return _row_to_dict(row)


@router.get("/response-feedback", response_model=List[dict])
def list_response_feedback(
    response_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Retrieve list response feedback.

    Args:
        response_id (str | None): Unique identifier of the response.
        limit (int): Maximum number of records to return.
        db (Session): Database session instance.

    Returns:
        List of response feedback.
    """
    q = db.query(ResponseFeedback)
    if response_id:
        q = q.filter(ResponseFeedback.response_id == response_id)
    rows = q.order_by(ResponseFeedback.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------
# query_evidence
# ---------------------------------------------------------

@router.post("/query-evidence", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_query_evidence(
    payload: QueryEvidenceCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Create or process create query evidence.

    Args:
        payload (QueryEvidenceCreate): Request or event payload.
        current_user (CurrentUser): Authenticated user context.
        db (Session): Database session instance.

    Returns:
        Result of the operation.
    """
    data = payload.model_dump(exclude_none=True)
    data["user_id"] = current_user.username
    if current_user.tenant_id:
        data["tenant_id"] = current_user.tenant_id
    row = _create_row(db, QueryEvidence, data)
    return _row_to_dict(row)


@router.get("/query-evidence", response_model=List[dict])
def list_query_evidence(
    current_user: CurrentUser,
    session_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Retrieve list query evidence.

    Args:
        current_user (CurrentUser): Authenticated user context.
        session_id (str | None): Unique identifier of the session.
        limit (int): Maximum number of records to return.
        db (Session): Database session instance.

    Returns:
        List of query evidence.
    """
    q = db.query(QueryEvidence).filter(QueryEvidence.user_id == current_user.username)
    if current_user.tenant_id:
        q = q.filter(QueryEvidence.tenant_id == current_user.tenant_id)
    if session_id:
        q = q.filter(QueryEvidence.session_id == session_id)
    rows = q.order_by(QueryEvidence.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------
# compliance_rules
# ---------------------------------------------------------

@router.post("/compliance-rules", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_compliance_rule(payload: ComplianceRuleCreate, db: Session = Depends(get_db)):
    """Create or process create compliance rule.

    Args:
        payload (ComplianceRuleCreate): Request or event payload.
        db (Session): Database session instance.

    Returns:
        Result of the operation.
    """
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, ComplianceRule, data)
    return _row_to_dict(row)


@router.get("/compliance-rules", response_model=List[dict])
def list_compliance_rules(
    region: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Retrieve list compliance rules.

    Args:
        region (str | None): The region.
        limit (int): Maximum number of records to return.
        db (Session): Database session instance.

    Returns:
        List of compliance rules.
    """
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
    """Create or process create fund scheme.

    Args:
        payload (FundSchemeCreate): Request or event payload.
        db (Session): Database session instance.

    Returns:
        Result of the operation.
    """
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, FundScheme, data)
    return _row_to_dict(row)


@router.get("/fund-schemes", response_model=List[dict])
def list_fund_schemes(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """Retrieve list fund schemes.

    Args:
        limit (int): Maximum number of records to return.
        db (Session): Database session instance.

    Returns:
        List of fund schemes.
    """
    rows = db.query(FundScheme).order_by(FundScheme.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------
# chatsessions
# ---------------------------------------------------------

@router.post("/chat_sessions", response_model=dict, status_code=status.HTTP_201_CREATED)
@router.post("/chat-sessions", response_model=dict, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_session(payload: ChatSessionCreate, db: Session = Depends(get_db)):
    """Create or process create session.

    Args:
        payload (ChatSessionCreate): Request or event payload.
        db (Session): Database session instance.

    Returns:
        Result of the operation.
    """
    data = payload.model_dump(exclude_none=True)
    row = _create_row(db, ChatSession, data)
    return _row_to_dict(row)


@router.get("/chat_sessions", response_model=List[dict])
@router.get("/chat-sessions", response_model=List[dict], include_in_schema=False)
def list_sessions(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """Retrieve list sessions.

    Args:
        limit (int): Maximum number of records to return.
        db (Session): Database session instance.

    Returns:
        List of sessions.
    """
    rows = db.query(ChatSession).order_by(ChatSession.created_at.desc()).limit(limit).all()
    return [_row_to_dict(r) for r in rows]