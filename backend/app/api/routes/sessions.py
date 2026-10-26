# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
sessions.py
===========
Session management API routes with strict user ownership and tenant isolation
enforcement (Phase 2 Security Remediation).
"""
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.api.deps import CurrentUser
from app.auth.service import AuthenticatedUser
from app.core.database import get_db
from app.schemas.chat_sessions_table import ChatSession
from app.schemas.models import _now_iso

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Resolve logs/chat_sessions directory relative to project root or current file
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
SESSIONS_DIR = BASE_DIR / "logs" / "chat_sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


class SessionItem(BaseModel):
    session_id: str
    preview: str
    turn_count: int
    modified_time: Optional[float] = None
    title: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SessionPayload(BaseModel):
    session_id: Optional[str] = None
    id: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _get_session_path(session_id: str) -> Path:
    """Retrieve session path.

    Args:
        session_id (str): Unique identifier of the session.

    Returns:
        Path: Resulting Path instance.
    """
    # Ensure safe filename without path traversal
    safe_id = Path(session_id).name
    return SESSIONS_DIR / f"{safe_id}.json"


def _verify_session_ownership(
    session_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
) -> ChatSession:
    """
    Verify that the current user owns the requested session.

    Args:
        session_id: Session identifier
        current_user: Authenticated user from token
        db: Database session

    Returns:
        ChatSession: The session record if ownership is verified

    Raises:
        HTTPException(404): If session doesn't exist OR user doesn't own it
                           (never reveal whether session exists to unauthorized users)
    """
    query = db.query(ChatSession).filter(
        ChatSession.session_id == session_id,
        ChatSession.user_id == current_user.username,
    )

    # If multi-tenant, enforce tenant boundary
    if current_user.tenant_id:
        query = query.filter(ChatSession.tenant_id == current_user.tenant_id)

    session = query.first()

    if session is None:
        # SECURITY: Return 404 regardless of whether session exists
        # Never reveal to User A that User B's session exists
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    return session


@router.get("", response_model=List[SessionItem])
async def list_sessions(
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    db: DBSession = Depends(get_db),
) -> List[SessionItem]:
    """List saved chat sessions for the CURRENT USER ONLY.

    Authorization: Only returns sessions where user_id matches the authenticated user.
    Sorted by updated_at / created_at (newest first), up to limit (default 50).

    Args:
        current_user (CurrentUser): Authenticated user context.
        limit (int): Maximum number of records to return.
        db (DBSession): Database session instance.

    Returns:
        List[SessionItem]: List of resulting items or records.
    """
    query = db.query(ChatSession).filter(ChatSession.user_id == current_user.username)
    if current_user.tenant_id:
        query = query.filter(ChatSession.tenant_id == current_user.tenant_id)
    query = query.order_by(
        func.coalesce(ChatSession.updated_at, ChatSession.created_at).desc()
    ).limit(limit)

    sessions = query.all()

    results: List[SessionItem] = []
    for session in sessions:
        path = _get_session_path(session.session_id)
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                data = json.loads(content)

                history = data if isinstance(data, list) else data.get("history", [])

                first_query = ""
                for turn in history:
                    if isinstance(turn, dict) and turn.get("role") == "user":
                        content_val = turn.get("content", "")
                        if isinstance(content_val, str) and content_val.strip():
                            first_query = content_val.strip()
                            break

                if not first_query:
                    continue

                preview = first_query[:44] + "…" if len(first_query) > 45 else first_query
                raw_title = data.get("title") if isinstance(data, dict) else None
                title = raw_title if (raw_title and raw_title.strip() and raw_title != "New Conversation") else preview

                turn_count = len([t for t in history if isinstance(t, dict) and t.get("role") == "user"])

                results.append(
                    SessionItem(
                        session_id=session.session_id,
                        preview=preview,
                        title=title,
                        turn_count=turn_count,
                        modified_time=path.stat().st_mtime if path.exists() else None,
                        created_at=session.created_at,
                        updated_at=session.updated_at,
                    )
                )
            except Exception:
                continue


    return results


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    current_user: CurrentUser,
    db: DBSession = Depends(get_db),
) -> Dict[str, Any]:
    """Load a session by session_id - ONLY if owned by current user.

    Args:
        session_id (str): Unique identifier of the session.
        current_user (CurrentUser): Authenticated user context.
        db (DBSession): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    session_record = _verify_session_ownership(session_id, current_user, db)

    path = _get_session_path(session_id)
    if not path.exists():
        # Resilient fallback to query_evidence
        try:
            from app.schemas.query_evidence_table import QueryEvidence
            evidence_turns = (
                db.query(QueryEvidence)
                .filter(QueryEvidence.session_id == session_id)
                .order_by(QueryEvidence.response_id.asc())
                .all()
            )
            if evidence_turns:
                history = []
                for i, ev in enumerate(evidence_turns):
                    history.append({
                        "role": "user",
                        "content": ev.query_text,
                        "turn_index": i + 1,
                    })
                    ans = ev.synthesis_output_json.get("answer") if isinstance(ev.synthesis_output_json, dict) else str(ev.synthesis_output_json)
                    history.append({
                        "role": "assistant",
                        "content": ans or "",
                        "turn_index": i + 1,
                        "response_id": ev.response_id,
                    })
                first_q = history[0]["content"][:44] if history else "Conversation"
                return {
                    "session_id": session_id,
                    "id": session_id,
                    "history": history,
                    "user_id": session_record.user_id,
                    "title": first_q,
                }
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)

        if isinstance(data, list):
            return {
                "session_id": session_id,
                "id": session_id,
                "history": data,
                "user_id": session_record.user_id,
            }

        data["session_id"] = data.get("session_id") or session_id
        data["id"] = data.get("id") or session_id
        data["user_id"] = session_record.user_id
        return data
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not load session {session_id}: {exc}",
        )


@router.post("/{session_id}")
async def save_session(
    session_id: str,
    payload: Dict[str, Any],
    current_user: CurrentUser,
    db: DBSession = Depends(get_db),
) -> Dict[str, Any]:
    """Save session to logs/chat_sessions/{session_id}.json
    ONLY if the session is owned by current user or is being created.

    Args:
        session_id (str): Unique identifier of the session.
        payload (Dict[str, Any]): Request or event payload.
        current_user (CurrentUser): Authenticated user context.
        db (DBSession): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    history = payload if isinstance(payload, list) else payload.get("history", [])
    has_user_msg = any(
        isinstance(t, dict) and t.get("role") == "user" and str(t.get("content", "")).strip()
        for t in history
    )

    if not has_user_msg:
        return {"status": "skipped", "session_id": session_id, "reason": "empty session"}

    # Check if session exists in database
    existing_session = db.query(ChatSession).filter_by(session_id=session_id).first()

    now_str = _now_iso()
    if existing_session:
        # Existing session: verify ownership
        if existing_session.user_id != current_user.username:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
        if current_user.tenant_id and existing_session.tenant_id != current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
        existing_session.updated_at = now_str
    else:
        # New session: create with current user as owner
        new_session = ChatSession(
            session_id=session_id,
            user_id=current_user.username,
            tenant_id=current_user.tenant_id,
            created_at=now_str,
            updated_at=now_str,
        )
        db.add(new_session)

    db.commit()

    # Stamp user_id into JSON payload if dict
    if isinstance(payload, dict):
        payload["user_id"] = current_user.username
        if current_user.tenant_id:
            payload["tenant_id"] = current_user.tenant_id

    # Write to JSON file
    path = _get_session_path(session_id)
    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(SESSIONS_DIR),
            prefix=f"{session_id}_",
            suffix=".tmp",
        )
        try:
            with open(temp_fd, "w", encoding="utf-8") as f:
                f.write(serialized)
            os.replace(temp_path, str(path))
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        return {"status": "ok", "session_id": session_id, "user_id": current_user.username, "rekeyed": False}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save session {session_id}: {exc}",
        )


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: CurrentUser,
    db: DBSession = Depends(get_db),
) -> Dict[str, Any]:
    """Delete a session file and database record.
    ONLY if owned by current user.

    Args:
        session_id (str): Unique identifier of the session.
        current_user (CurrentUser): Authenticated user context.
        db (DBSession): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    from app.schemas.query_evidence_table import QueryEvidence
    from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
    from app.schemas.response_feedback_table import ResponseFeedback
    from app.schemas.repair_proposals import RepairProposal

    session_record = _verify_session_ownership(session_id, current_user, db)

    # 1. Clean up session JSON file on disk
    path = _get_session_path(session_id)
    if path.exists():
        try:
            path.unlink()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not delete session file {session_id}: {exc}",
            )

    # 2. Clean up query evidence JSON file on disk if present
    evidence_path = BASE_DIR / "logs" / "chat_query_evidence" / f"chat_evidence_{Path(session_id).name}.json"
    if evidence_path.exists():
        try:
            evidence_path.unlink()
        except Exception:
            pass

    # 3. Clean up associated child records respecting foreign key order
    uer_records = (
        db.query(UnifiedEvaluationRecord)
        .filter(UnifiedEvaluationRecord.session_id == session_id)
        .all()
    )
    resp_ids = [r.response_id for r in uer_records]

    qe_records = (
        db.query(QueryEvidence)
        .filter(QueryEvidence.session_id == session_id)
        .all()
    )
    for qe in qe_records:
        if qe.response_id not in resp_ids:
            resp_ids.append(qe.response_id)

    # Delete linked RepairProposal rows
    if resp_ids:
        db.query(RepairProposal).filter(
            RepairProposal.unified_record_ref.in_(resp_ids)
        ).delete(synchronize_session=False)

    # Delete UnifiedEvaluationRecord rows
    # (Must delete before QueryEvidence because of evidence_snapshot_ref RESTRICT FK)
    db.query(UnifiedEvaluationRecord).filter(
        UnifiedEvaluationRecord.session_id == session_id
    ).delete(synchronize_session=False)

    # Delete ResponseFeedback rows for this session
    db.query(ResponseFeedback).filter(
        ResponseFeedback.session_id == session_id
    ).delete(synchronize_session=False)

    # Delete QueryEvidence rows for this session
    db.query(QueryEvidence).filter(
        QueryEvidence.session_id == session_id
    ).delete(synchronize_session=False)

    # 4. Delete ChatSession record
    db.delete(session_record)
    db.commit()

    return {"status": "deleted", "session_id": session_id}
