"""Wave 4.0 pilot routes (TDS-40 E7, E9).

POST /api/feedback/v40  (ADR40-03, AMC_PILOT_FEEDBACK=on) append-only rating of one of the caller's OWN answers.
GET  /api/ready         (ADR40-04) readiness, distinct from /health liveness. Everyone gets {ready: bool};
                         admin/reviewer roles also get the per-check detail. Ready means: database at the exact
                         migration head, trusted public keys loaded, provider policy satisfied, Neo4j reachable,
                         and every tenant in AMC_PILOT_TENANTS has an active receipt-backed FAISS generation (and an
                         active fin dataset when AMC_FIN_PLANE=on).
"""
from __future__ import annotations

import asyncio
import os
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, OptionalCurrentUser

router = APIRouter(tags=["pilot-w40"])
DETAIL_ROLES = {"admin", "reviewer"}


class FeedbackIn(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    rating: Literal["UP", "DOWN"]
    reason: Literal["WRONG_NUMBER", "WRONG_CITATION", "OUTDATED", "INCOMPLETE", "NOT_RELEVANT", "HELPFUL", "OTHER"]
    comment: Optional[str] = Field(default=None, max_length=1000)


def _sessions():
    from sqlalchemy.orm import sessionmaker
    from app.core.database import engine
    return sessionmaker(bind=engine)


@router.post("/api/feedback/v40", status_code=202)
async def submit_pilot_feedback(body: FeedbackIn, current_user: CurrentUser):
    from amc_publication.evidence40 import FeedbackRefused, feedback_enabled, submit_feedback
    if not feedback_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="tenant identity required")

    def _write():
        with _sessions().begin() as s:
            row = submit_feedback(s, tenant=current_user.tenant_id, user_id=current_user.username,
                                  request_id=body.request_id, rating=body.rating, reason=body.reason,
                                  comment=body.comment)
            return row.id
    try:
        feedback_id = await asyncio.to_thread(_write)
    except FeedbackRefused as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {"accepted": True, "feedback_id": feedback_id}


def readiness_checks() -> dict:
    """Synchronous; every check is independent and reports a short, non-secret reason."""
    checks: dict = {}
    enforce = os.environ.get("AMC_VERIFIED_SERVING_MODE", "off") == "enforce"
    checks["verified_mode"] = {"ok": enforce, "detail": "enforce" if enforce else "not in verified mode"}
    try:
        from app.core.database import engine
        from app.core.db_runtime31 import verify_migrated_postgresql
        verify_migrated_postgresql(engine)
        checks["database"] = {"ok": True}
    except Exception as exc:                 # noqa: BLE001
        checks["database"] = {"ok": False, "detail": str(exc)[:160]}
    try:
        from amc_publication.signing31 import verifier_from_env
        checks["trusted_keys"] = {"ok": verifier_from_env() is not None}
    except Exception as exc:                 # noqa: BLE001
        checks["trusted_keys"] = {"ok": False, "detail": str(exc)[:160]}
    try:
        from app.config import get_settings
        from app.core.provider_policy40 import assert_provider_policy
        decision = assert_provider_policy(get_settings())
        checks["provider_policy"] = {"ok": True, "detail": decision or "policy off"}
    except Exception as exc:                 # noqa: BLE001
        checks["provider_policy"] = {"ok": False, "detail": str(exc)[:160]}
    try:
        from neo4j import GraphDatabase
        from app.config import get_settings
        st = get_settings()
        driver = GraphDatabase.driver(st.neo4j_uri, auth=(st.neo4j_user, st.neo4j_password), connection_timeout=2.0)
        try:
            driver.verify_connectivity()
        finally:
            driver.close()
        checks["neo4j"] = {"ok": True}
    except Exception as exc:                 # noqa: BLE001
        checks["neo4j"] = {"ok": False, "detail": type(exc).__name__}
    tenants = [t.strip() for t in os.environ.get("AMC_PILOT_TENANTS", "").split(",") if t.strip()]
    if not tenants:
        checks["tenants"] = {"ok": False, "detail": "AMC_PILOT_TENANTS is not set"}
    else:
        from app.retrieval.structured_path40 import structured_enabled
        from amc_publication.active_authority28 import current_binding
        from amc_publication.fin40 import current_pin
        per = {}
        with _sessions()() as s:
            for tenant in tenants:
                entry = {}
                try:
                    current_binding(s, tenant)
                    entry["documents"] = True
                except Exception as exc:     # noqa: BLE001
                    entry["documents"] = False
                    entry["documents_detail"] = str(exc)[:120]
                if structured_enabled():
                    try:
                        entry["fin_dataset"] = current_pin(s, tenant).dataset_version
                    except Exception as exc:  # noqa: BLE001
                        entry["fin_dataset"] = None
                        entry["fin_detail"] = str(exc)[:120]
                entry["ok"] = entry["documents"] and (not structured_enabled() or bool(entry.get("fin_dataset")))
                per[tenant] = entry
        checks["tenants"] = {"ok": all(e["ok"] for e in per.values()), "detail": per}
    return checks


@router.get("/api/ready")
async def ready(current_user: OptionalCurrentUser = None):
    checks = await asyncio.to_thread(readiness_checks)
    ok = all(c.get("ok") for c in checks.values())
    body: dict = {"ready": ok}
    if current_user is not None and (getattr(current_user, "role", "") or "").lower() in DETAIL_ROLES:
        body["checks"] = checks
    return JSONResponse(status_code=200 if ok else 503, content=body)
