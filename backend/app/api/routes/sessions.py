# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
sessions.py
===========
Session management API routes for reading and writing chat session files
in logs/chat_sessions/.
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

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


class SessionPayload(BaseModel):
    session_id: Optional[str] = None
    id: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _get_session_path(session_id: str) -> Path:
    # Ensure safe filename without path traversal
    safe_id = Path(session_id).name
    return SESSIONS_DIR / f"{safe_id}.json"


@router.get("", response_model=List[SessionItem])
async def list_sessions(limit: int = Query(20, ge=1, le=100)) -> List[SessionItem]:
    """
    List saved chat sessions from logs/chat_sessions/ directory.
    Sorted by modified time (newest first), up to limit (default 20).
    Corrupt or unreadable session files are skipped gracefully.
    """
    if not SESSIONS_DIR.exists():
        return []

    json_paths = list(SESSIONS_DIR.glob("*.json"))
    # Sort newest-first based on file modification time
    sorted_paths = sorted(
        json_paths,
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )

    results: List[SessionItem] = []
    for path in sorted_paths:
        if len(results) >= limit:
            break
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            
            # Support both list of messages format and dict with history format
            history = data if isinstance(data, list) else data.get("history", [])
            
            # Extract first user message for preview (truncated to 45 chars + '…')
            first_query = ""
            for turn in history:
                if isinstance(turn, dict) and turn.get("role") == "user":
                    first_query = str(turn.get("content", "")).strip()
                    if first_query:
                        break
            
            if len(first_query) > 45:
                preview = first_query[:44] + "…"
            elif first_query:
                preview = first_query
            else:
                preview = "(empty)"

            turn_count = len(history) // 2
            mtime = path.stat().st_mtime

            results.append(
                SessionItem(
                    session_id=path.stem,
                    preview=preview,
                    turn_count=turn_count,
                    modified_time=mtime,
                )
            )
        except Exception:
            # Skip corrupt or unreadable session files gracefully (REQ-1.11.10)
            continue

    return results


@router.get("/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    """
    Load a session by session_id from disk.
    """
    path = _get_session_path(session_id)
    if not path.exists():
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
            }
        # If dict, ensure session_id / id is populated
        data["session_id"] = data.get("session_id") or session_id
        data["id"] = data.get("id") or session_id
        return data
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not load session {session_id}: {exc}",
        )


@router.post("/{session_id}")
async def save_session(session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save session to logs/chat_sessions/{session_id}.json with atomic write,
    UTF-8 encoding, 2-space indentation, and default=str for non-JSON types.
    """
    path = _get_session_path(session_id)
    try:
        # Atomic write: write to temp file first, then replace
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

        return {"status": "ok", "session_id": session_id}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save session {session_id}: {exc}",
        )


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    """
    Delete a session file if it exists.
    """
    path = _get_session_path(session_id)
    if path.exists():
        try:
            path.unlink()
            return {"status": "deleted", "session_id": session_id}
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not delete session {session_id}: {exc}",
            )
    return {"status": "not_found", "session_id": session_id}
