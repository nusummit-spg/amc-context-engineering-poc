# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
governance.py
=============
FastAPI router for Track 7: Human Governance Review Queue.
Allows compliance officers and administrators to:
  - Inspect pending correction patches in the shadow graph
  - Review evidence provenance and risk levels
  - Approve patches (promoting to canonical Neo4j knowledge graph and removing TTL)
  - Reject patches (purging from shadow graph)
  - Perform batch approvals/rejections during weekly review cycles
"""

from datetime import datetime, timezone
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser  # SEC-02 FIX: Use JWT-verified role instead of header
from app.graph.correction_patch_layer import CorrectionPatch, get_correction_patch_layer
from app.core.database import get_db
from sqlalchemy.orm import Session
from app.schemas.repair_proposals import RepairProposal
from app.schemas.graph_mutations_table import GraphMutation
from app.services.promotion_service import PromotionService

logger = logging.getLogger("app.api.governance")

router = APIRouter(prefix="/governance", tags=["governance"])


class CorrectionProposal(BaseModel):
    patch_id: str
    entity_id: str
    entity_name: str
    attribute: str
    current_value: str
    proposed_value: str
    confidence: float
    supporting_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str
    expires_at: Optional[str] = None
    feedback_count: int = 1
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH


class ApproveRejectIn(BaseModel):
    comment: Optional[str] = None
    reason: Optional[str] = None


class BatchApprovalIn(BaseModel):
    patch_ids: List[str] = Field(..., min_length=1)
    action: str = Field(..., pattern="^(approve|reject)$")
    comment: Optional[str] = None


def assess_risk_level(confidence: float, current_val: Any, proposed_val: Any) -> str:
    """Assess regulatory and data risk of a proposed fact change:
      - HIGH: low confidence (< 0.70) OR > 20% relative numeric delta
      - MEDIUM: moderate confidence (0.70 - 0.85) OR 10-20% relative delta
      - LOW: high confidence (>= 0.85) AND <= 10% relative delta

    Args:
        confidence (float): The confidence.
        current_val (Any): The current val.
        proposed_val (Any): The proposed val.

    Returns:
        str: Resulting str instance.
    """
    if confidence < 0.70:
        return "HIGH"

    try:
        clean_c = float(str(current_val).replace("%", "").replace("₹", "").replace("Rs", "").strip())
        clean_p = float(str(proposed_val).replace("%", "").replace("₹", "").replace("Rs", "").strip())
        if clean_c > 0:
            rel_change = abs(clean_p - clean_c) / clean_c
            if rel_change > 0.20:
                return "HIGH"
            if rel_change > 0.10:
                return "MEDIUM"
    except Exception:
        pass

    return "LOW" if confidence >= 0.85 else "MEDIUM"


def log_governance_audit(action: str, patch_id: str, actor: str, details: Optional[Dict[str, Any]] = None):
    """Log governance audit.

    Args:
        action (str): The action.
        patch_id (str): Unique identifier of the patch.
        actor (str): The actor.
        details (Optional[Dict[str, Any]]): Collection or list of details.
    """
    log_dir = Path(__file__).resolve().parent.parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    audit_file = log_dir / "governance_audit.jsonl"
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "patch_id": patch_id,
        "actor": actor,
        "details": details or {}
    }
    try:
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.error("Failed writing to governance audit log: %s", exc)


def _normalize_role(role: str | None) -> str:
    r = (role or "").lower().strip().replace(" ", "_").replace("&", "_")
    while "__" in r:
        r = r.replace("__", "_")
    if "admin" in r:
        return "admin"
    if "compliance" in r:
        return "compliance_officer"
    if "review" in r:
        return "reviewer"
    if "analyst" in r:
        return "analyst"
    if "view" in r:
        return "viewer"
    return r


def require_governance_role(current_user: CurrentUser) -> None:
    """Check if user has governance privileges (compliance_officer, admin, or reviewer).
    
    SEC-02 FIX: Server-authoritative role checking from JWT, not headers.
    
    Args:
        current_user: Authenticated user from JWT
    
    Raises:
        HTTPException(403): If user lacks governance privileges
    """
    norm = _normalize_role(current_user.role)
    allowed_roles = ["compliance_officer", "admin", "reviewer"]
    if norm not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Governance access requires one of: {allowed_roles}. Your role: {current_user.role}"
        )


def require_approval_role(current_user: CurrentUser) -> None:
    """Check if user has approval privileges (compliance_officer or admin only).
    
    SEC-02 FIX: Server-authoritative role checking from JWT, not headers.
    
    Args:
        current_user: Authenticated user from JWT
    
    Raises:
        HTTPException(403): If user lacks approval privileges
    """
    norm = _normalize_role(current_user.role)
    allowed_roles = ["compliance_officer", "admin"]
    if norm not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Approval actions require one of: {allowed_roles}. Your role: {current_user.role}"
        )


@router.get("/pending-corrections", response_model=List[CorrectionProposal])
async def get_pending_corrections(
    current_user: CurrentUser,
) -> List[CorrectionProposal]:
    """Retrieve all pending (unapproved) fact corrections in the shadow graph.

    SEC-02 FIX: Uses JWT-verified role from CurrentUser instead of X-User-Role header.

    Args:
        current_user: Authenticated user from JWT

    Returns:
        List[CorrectionProposal]: List of resulting items or records.
    """
    require_governance_role(current_user)
    patch_layer = get_correction_patch_layer()
    pending_patches = list(patch_layer.get_all_pending())

    # Synchronize pending patches from repair engine microservice if available
    try:
        import httpx
        from app.config import get_settings
        repair_url = get_settings().repair_service_url
        if repair_url:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{repair_url}/api/patches/pending")
                if resp.status_code == 200:
                    ms_patches = resp.json().get("patches", [])
                    local_ids = {p.patch_id for p in pending_patches}
                    for mp in ms_patches:
                        pid = mp.get("patch_id")
                        if pid and pid not in local_ids and not mp.get("approved"):
                            pending_patches.append(
                                CorrectionPatch(
                                    patch_id=pid,
                                    entity_id=mp.get("entity_id", "unknown"),
                                    attribute=mp.get("attribute", "general"),
                                    canonical_value=mp.get("canonical_value") or mp.get("original_value"),
                                    corrected_value=mp.get("corrected_value"),
                                    confidence=float(mp.get("confidence", 0.75)),
                                    provenance=mp.get("provenance", {}),
                                    approved=False,
                                    created_at=mp.get("created_at") or (datetime.utcnow().isoformat() + "Z"),
                                    expires_at=mp.get("expires_at"),
                                )
                            )
    except Exception as exc:
        logger.debug("Microservice pending sync notice: %s", exc)

    # Load fund master for friendly entity name resolution
    fund_names_by_isin = {}
    try:
        from app.feedback.fund_name_matcher import get_fund_name_matcher
        matcher = get_fund_name_matcher()
        fund_names_by_isin = {f["isin"]: f["fund_name"] for f in matcher.fund_master}
    except Exception:
        pass

    proposals = []
    for patch in pending_patches:
        entity_name = fund_names_by_isin.get(patch.entity_id, f"Fund {patch.entity_id}")
        risk = assess_risk_level(patch.confidence, patch.canonical_value, patch.corrected_value)

        evidence = []
        if patch.provenance:
            evidence.append({
                "feedback_id": patch.provenance.get("feedback_id", "manual"),
                "source": patch.provenance.get("source", "User Feedback"),
                "actor_id": patch.provenance.get("actor_id", "analyst"),
                "recorded_at": patch.created_at
            })

        proposals.append(
            CorrectionProposal(
                patch_id=patch.patch_id,
                entity_id=patch.entity_id,
                entity_name=entity_name,
                attribute=patch.attribute,
                current_value=str(patch.canonical_value),
                proposed_value=str(patch.corrected_value),
                confidence=patch.confidence,
                supporting_evidence=evidence,
                created_at=patch.created_at,
                expires_at=patch.expires_at,
                feedback_count=len(evidence),
                risk_level=risk
            )
        )

    return proposals


@router.get("/correction/{patch_id}", response_model=CorrectionProposal)
def get_correction_detail(
    patch_id: str,
    current_user: CurrentUser,
) -> CorrectionProposal:
    """Retrieve detailed metadata and evidence for a specific patch.

    SEC-02 FIX: Uses JWT-verified role from CurrentUser instead of X-User-Role header.

    Args:
        patch_id (str): Unique identifier of the patch.
        current_user: Authenticated user from JWT

    Returns:
        CorrectionProposal: Resulting CorrectionProposal instance.
    """
    require_governance_role(current_user)
    patch_layer = get_correction_patch_layer()
    patch = patch_layer.get_patch_by_id(patch_id)
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Correction patch {patch_id} not found"
        )

    fund_name = f"Fund {patch.entity_id}"
    try:
        from app.feedback.fund_name_matcher import get_fund_name_matcher
        matcher = get_fund_name_matcher()
        if patch.entity_id in matcher.isin_to_fund:
            fund_name = matcher.isin_to_fund[patch.entity_id]["fund_name"]
    except Exception:
        pass

    risk = assess_risk_level(patch.confidence, patch.canonical_value, patch.corrected_value)
    evidence = []
    if patch.provenance:
        evidence.append({
            "feedback_id": patch.provenance.get("feedback_id", "manual"),
            "source": patch.provenance.get("source", "User Feedback"),
            "actor_id": patch.provenance.get("actor_id", "analyst"),
            "recorded_at": patch.created_at
        })

    return CorrectionProposal(
        patch_id=patch.patch_id,
        entity_id=patch.entity_id,
        entity_name=fund_name,
        attribute=patch.attribute,
        current_value=str(patch.canonical_value),
        proposed_value=str(patch.corrected_value),
        confidence=patch.confidence,
        supporting_evidence=evidence,
        created_at=patch.created_at,
        expires_at=patch.expires_at,
        feedback_count=len(evidence),
        risk_level=risk
    )


@router.post("/approve/{patch_id}", response_model=Dict[str, Any])
def approve_correction(
    patch_id: str,
    current_user: CurrentUser,
    payload: Optional[ApproveRejectIn] = None,
) -> Dict[str, Any]:
    """Approve correction patch: transitions to APPROVED state (PENDING→APPROVED).
    
    B01 FIX (G06): Approval and promotion are separate actions.
    - Approval: PENDING→APPROVED state transition (this endpoint)
    - Promotion: APPROVED→STAGED→VERIFIED→ACTIVE (via /promote/{patch_id})
    
    Approval does NOT write to canonical Neo4j graph or remove TTL.
    Promotion requires explicit state machine transitions with durable receipts.
    
    SEC-02 FIX: Uses JWT-verified role from CurrentUser instead of X-User-Role header.
    A04 FIX (C-07): Four-eyes enforcement - approver must differ from proposer.

    Args:
        patch_id (str): Unique identifier of the patch.
        payload (Optional[ApproveRejectIn]): Request or event payload.
        current_user: Authenticated user from JWT

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
        
    Raises:
        HTTPException(403): If proposer attempts to approve their own patch
    """
    require_approval_role(current_user)
    patch_layer = get_correction_patch_layer()
    patch = patch_layer.get_patch_by_id(patch_id)
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patch {patch_id} not found"
        )
    
    # A04: Four-eyes enforcement - approver cannot be proposer
    proposer_username = None
    proposer_id = None
    if hasattr(patch, 'provenance') and patch.provenance:
        proposer_username = patch.provenance.get("proposer_username") or patch.provenance.get("actor_id")
        proposer_id = patch.provenance.get("proposer_id") or patch.provenance.get("user_id")
    
    current_user_id = getattr(current_user, 'user_id', None) or current_user.username
    
    if proposer_username and proposer_username == current_user.username:
        logger.warning(
            "FOUR_EYES_VIOLATION: User %s attempted to approve their own patch %s",
            current_user.username,
            patch_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Four-eyes policy violation: Cannot approve your own patch (proposed by {proposer_username})"
        )
    
    if proposer_id and proposer_id == current_user_id:
        logger.warning(
            "FOUR_EYES_VIOLATION: User %s (id=%s) attempted to approve their own patch %s",
            current_user.username,
            current_user_id,
            patch_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Four-eyes policy violation: Cannot approve your own patch"
        )

    # Optional Neo4j session write
    neo4j_session = None
    try:
        from app.engine.graph_store import get_driver, config as g_config
        driver = get_driver()
        if driver:
            neo4j_session = driver.session(database=getattr(g_config, "NEO4J_DATABASE", "neo4j"))
    except Exception as exc:
        logger.debug("Neo4j session acquisition notice: %s", exc)

    # B01: FIX (G06) - Approval should only transition to APPROVED state, not write to Neo4j
    # Promotion (STAGED→VERIFIED→ACTIVE) must happen through /promote endpoint separately
    # Note: This endpoint is synchronous - async approval should use a dedicated service
    
    # Sync path: Transition to APPROVED state only
    patch = patch_layer.get_patch_by_id(patch_id)
    if patch:
        # B01: Transition to APPROVED state only
        # W31_LOCAL_FIX: Wave 2.5 patch dropped this import; it is still required below.
        from app.graph.correction_patch_layer import PatchStatus
        # W25_REVIEWER_PERSISTENCE: preserve approver after to_dict().
        patch.provenance = {**(patch.provenance or {}), "approver_username": current_user.username}
        patch.status = PatchStatus.APPROVED
        patch.approved_at = datetime.now(timezone.utc).isoformat() + "Z"
        patch.approved_by = current_user.username
        patch.approved = True  # Backward compatibility
        patch.expires_at = None  # Approval removes TTL
        
        # Update in stores
        patch_dict = patch.to_dict() if hasattr(patch, 'to_dict') else asdict(patch)
        patch_json = json.dumps(patch_dict)
        
        if patch_layer.redis is not None:
            try:
                patch_key = patch_layer._make_key(patch.entity_id, patch.attribute)
                patch_layer.redis.set(patch_key, patch_json)
                patch_layer.redis.persist(patch_key)
            except Exception as exc:
                logger.debug("Redis persist notice: %s", exc)
        
        with patch_layer._lock:
            patch_layer._mem_store[patch_layer._make_key(patch.entity_id, patch.attribute)] = patch_dict
            patch_layer._mem_store[patch.patch_id] = patch_dict
        
        success = True
        logger.info("APPROVED: Patch %s transitioned to APPROVED by %s", patch_id, current_user.username)
    else:
        success = False

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve patch {patch_id}"
        )

    comment = payload.comment if payload else None
    log_governance_audit("APPROVE", patch_id, current_user.username, {"comment": comment})

    return {
        "status": "approved",
        "patch_id": patch_id,
        "approved_by": current_user.username,
        "approved_at": datetime.utcnow().isoformat() + "Z",
        "comment": comment,
        "note": "Patch state machine transitioned to APPROVED. Use /promote endpoint to stage/verify/activate."
    }


@router.post("/reject/{patch_id}", response_model=Dict[str, Any])
def reject_correction(
    patch_id: str,
    current_user: CurrentUser,
    payload: Optional[ApproveRejectIn] = None,
) -> Dict[str, Any]:
    """Reject correction patch: deletes patch from shadow graph.

    SEC-02 FIX: Uses JWT-verified role from CurrentUser instead of X-User-Role header.

    Args:
        patch_id (str): Unique identifier of the patch.
        payload (Optional[ApproveRejectIn]): Request or event payload.
        current_user: Authenticated user from JWT

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    require_approval_role(current_user)
    
    patch_layer = get_correction_patch_layer()
    patch = patch_layer.get_patch_by_id(patch_id)
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patch {patch_id} not found"
        )

    deleted = patch_layer.delete_patch(patch_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete patch {patch_id}"
        )

    reason = payload.reason if payload else (payload.comment if payload else "Rejected by compliance officer")
    log_governance_audit("REJECT", patch_id, current_user.username, {"reason": reason})

    return {
        "status": "rejected",
        "patch_id": patch_id,
        "rejected_by": current_user.username,
        "rejected_at": datetime.utcnow().isoformat() + "Z",
        "reason": reason
    }


@router.post("/batch-approve", response_model=Dict[str, Any])
def batch_approve_corrections(
    payload: BatchApprovalIn,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Batch process (approve or reject) multiple correction patches at once.

    SEC-02 FIX: Uses JWT-verified role from CurrentUser instead of X-User-Role header.
    A04 FIX (C-07): Four-eyes enforcement applied to each patch individually.

    Args:
        payload (BatchApprovalIn): Request or event payload.
        current_user: Authenticated user from JWT

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    require_approval_role(current_user)
    patch_layer = get_correction_patch_layer()
    succeeded = []
    failed = []
    four_eyes_violations = []

    current_user_id = getattr(current_user, 'user_id', None) or current_user.username

    for pid in payload.patch_ids:
        try:
            # A04: Check four-eyes for each patch before action
            patch = patch_layer.get_patch_by_id(pid)
            if not patch:
                failed.append({"patch_id": pid, "reason": "Patch not found"})
                continue
            
            if payload.action == "approve":
                # Four-eyes check for approval
                proposer_username = None
                proposer_id = None
                if hasattr(patch, 'provenance') and patch.provenance:
                    proposer_username = patch.provenance.get("proposer_username") or patch.provenance.get("actor_id")
                    proposer_id = patch.provenance.get("proposer_id") or patch.provenance.get("user_id")
                
                if (proposer_username and proposer_username == current_user.username) or \
                   (proposer_id and proposer_id == current_user_id):
                    four_eyes_violations.append({
                        "patch_id": pid,
                        "proposer": proposer_username or proposer_id,
                        "reason": "Cannot approve own patch"
                    })
                    logger.warning(
                        "BATCH_FOUR_EYES_VIOLATION: User %s attempted to approve their own patch %s",
                        current_user.username,
                        pid
                    )
                    continue
                
                # B01: FIX (G06) - Approval should only transition to APPROVED state
                # Promotion (STAGED→VERIFIED→ACTIVE) must happen through /promote endpoint
                patch_key = patch_layer._make_key(patch.entity_id, patch.attribute)
                from app.graph.correction_patch_layer import PatchStatus
                
                # W25_REVIEWER_PERSISTENCE_BATCH: serialize approver identity.
                patch.provenance = {**(patch.provenance or {}), "approver_username": current_user.username}
                patch.status = PatchStatus.APPROVED
                patch.approved_at = datetime.now(timezone.utc).isoformat() + "Z"
                patch.approved_by = current_user.username
                patch.approved = True  # Backward compatibility
                patch.expires_at = None  # Approval removes TTL
                
                # Update in stores
                patch_dict = patch.to_dict() if hasattr(patch, 'to_dict') else asdict(patch)
                patch_json = json.dumps(patch_dict)
                
                success = False
                if patch_layer.redis is not None:
                    try:
                        patch_layer.redis.set(patch_key, patch_json)
                        patch_layer.redis.persist(patch_key)
                        success = True
                    except Exception as exc:
                        logger.debug("Redis persist notice: %s", exc)
                
                if success or patch_layer.redis is None:  # Fall back to in-memory
                    with patch_layer._lock:
                        patch_layer._mem_store[patch_key] = patch_dict
                        patch_layer._mem_store[patch.patch_id] = patch_dict
                    success = True
                    logger.info("BATCH_APPROVED: Patch %s transitioned to APPROVED by %s", pid, current_user.username)
                
                if success:
                    succeeded.append(pid)
                    log_governance_audit("APPROVE_BATCH", pid, current_user.username, {"comment": payload.comment})
                else:
                    failed.append({"patch_id": pid, "reason": "Approval failed"})
            elif payload.action == "reject":
                ok = patch_layer.delete_patch(pid)
                if ok:
                    succeeded.append(pid)
                    log_governance_audit("REJECT_BATCH", pid, current_user.username, {"comment": payload.comment})
                else:
                    failed.append({"patch_id": pid, "reason": "Deletion failed"})
        except Exception as exc:
            logger.warning("Batch action error on %s: %s", pid, exc)
            failed.append({"patch_id": pid, "reason": str(exc)})

    return {
        "action": payload.action,
        "total": len(payload.patch_ids),
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
        "four_eyes_violations_count": len(four_eyes_violations),
        "succeeded": succeeded,
        "failed": failed,
        "four_eyes_violations": four_eyes_violations
    }


class GovernanceBatchIn(BaseModel):
    auto_approve_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    max_risk_level: str = Field(default="LOW", pattern="^(LOW|MEDIUM|HIGH)$")
    dry_run: bool = False


@router.post("/run-batch", response_model=Dict[str, Any])
async def run_governance_batch(
    current_user: CurrentUser,
    payload: Optional[GovernanceBatchIn] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Run automated governance batch processor (REP-01 FIX: confidence-based auto-approval DISABLED).
    
    SEC-02 FIX: Uses JWT-verified role instead of X-User-Role header.
    REP-01 FIX: Confidence threshold now only affects REVIEW PRIORITY, not automatic approval.
    All patches require explicit human approval via /approve/{patch_id} or /batch-approve.
    
    Evaluates all pending patches and categorizes them by risk/confidence for review prioritization:
    - High-confidence (>= threshold) LOW risk patches → "recommended_for_approval" list
    - Very low confidence (< 0.50) → "recommended_for_rejection" list  
    - All others → "requires_detailed_review" list
    
    NO PATCHES ARE AUTOMATICALLY APPROVED OR PROMOTED.

    Args:
        payload (Optional[GovernanceBatchIn]): Request or event payload.
        current_user: Authenticated user from JWT
        db (Session): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    require_approval_role(current_user)
    
    threshold = payload.auto_approve_threshold if payload else 0.95
    max_risk = payload.max_risk_level if payload else "LOW"
    dry_run = payload.dry_run if payload else False
    
    logger.warning(
        "REP-01 COMPLIANCE: run_governance_batch invoked but automatic approval is DISABLED. "
        "User %s must review and explicitly approve patches via /approve or /batch-approve endpoints.",
        current_user.username
    )

    patch_layer = get_correction_patch_layer()
    pending = list(patch_layer.get_all_pending())

    # Synchronize any pending corrections from the repair microservice into local patch layer
    try:
        from app.services.service_client import get_service_client
        client = get_service_client()
        m_patches = await client.get_repair_patches(approved=False)
        for mp in m_patches:
            pid = mp.get("patch_id")
            if pid and not any(p.patch_id == pid for p in pending):
                cp = CorrectionPatch(
                    patch_id=pid,
                    entity_id=mp.get("entity_id", "unknown"),
                    attribute=mp.get("attribute", "general"),
                    canonical_value=mp.get("canonical_value") or mp.get("original_value"),
                    corrected_value=mp.get("corrected_value"),
                    confidence=float(mp.get("confidence", 0.75)),
                    provenance=mp.get("provenance", {}),
                    approved=False,
                    created_at=mp.get("created_at") or (datetime.utcnow().isoformat() + "Z"),
                    expires_at=mp.get("expires_at"),
                )
                pending.append(cp)
                if pid not in patch_layer.patches:
                    patch_layer.patches[pid] = cp
    except Exception as exc:
        logger.debug("Microservice batch sync notice: %s", exc)

    total_evaluated = len(pending)
    recommended_for_approval: List[str] = []  # High confidence + low risk (still needs human approval)
    recommended_for_rejection: List[str] = []  # Very low confidence
    requires_detailed_review: List[str] = []   # Medium confidence or higher risk

    # No actual mutations - only categorization for review prioritization
    for patch in pending:
        risk = assess_risk_level(patch.confidence, patch.canonical_value, patch.corrected_value)
        risk_acceptable = (risk == "LOW") if max_risk == "LOW" else (risk in ("LOW", "MEDIUM"))

        if patch.confidence >= threshold and risk_acceptable:
            # REP-01: DO NOT auto-approve, only recommend
            recommended_for_approval.append(patch.patch_id)
            logger.info(
                "Patch %s recommended for approval (confidence=%.2f, risk=%s) - REQUIRES HUMAN APPROVAL",
                patch.patch_id, patch.confidence, risk
            )
        elif patch.confidence < 0.50:
            # Recommend rejection for very low confidence
            recommended_for_rejection.append(patch.patch_id)
            logger.info(
                "Patch %s recommended for rejection (confidence=%.2f)",
                patch.patch_id, patch.confidence
            )
        else:
            # Requires detailed human review
            requires_detailed_review.append(patch.patch_id)
            logger.info(
                "Patch %s requires detailed review (confidence=%.2f, risk=%s)",
                patch.patch_id, patch.confidence, risk
            )
    
    #  REP-01 FIX: DO NOT call microservice or scheduler auto-approval - those also need fixing
    # Commenting out to prevent bypassing human approval requirement
    # microservice_report = None
    # if repair_int and not dry_run:
    #     try:
    #         microservice_report = await repair_int.run_governance_batch(auto_approve_threshold=threshold)
    #     except Exception as exc:
    #         logger.debug("Microservice run_governance_batch notice: %s", exc)
    
    logger.warning(
        "REP-01 COMPLIANCE: Microservice and scheduler auto-approval calls DISABLED. "
        "All approvals must go through explicit /approve or /batch-approve endpoints."
    )

    return {
        "status": "review_categorization_completed",
        "message": "REP-01 COMPLIANCE: No automatic approvals performed. Use /batch-approve to approve recommended patches.",
        "total_evaluated": total_evaluated,
        "recommended_for_approval": len(recommended_for_approval),
        "recommended_for_rejection": len(recommended_for_rejection),
        "requires_detailed_review": len(requires_detailed_review),
        "recommended_approval_patches": recommended_for_approval,
        "recommended_rejection_patches": recommended_for_rejection,
        "detailed_review_patches": requires_detailed_review,
        "dry_run": dry_run,
        "threshold_used": threshold,
        "max_risk_level": max_risk,
        "categorized_by": current_user.username,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


class ProposalReviewIn(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    comment: Optional[str] = None


@router.post("/promote", response_model=Dict[str, Any])
async def promote_approved_proposals(
    current_user: CurrentUser,
    batch_id: Optional[str] = None,
    proposal_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Apply approved repair proposals to canonical Neo4j graph and vector stores.

    SEC-02 FIX: Uses JWT-verified role instead of X-User-Role header.
    A02 FIX: Made async and properly awaits PromotionService.apply_approved_proposals().

    Args:
        batch_id (Optional[str]): Unique identifier of the batch.
        proposal_id (Optional[str]): Unique identifier of the proposal.
        current_user: Authenticated user from JWT
        db (Session): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    require_approval_role(current_user)
    # W31_DISABLE_LEGACY_DIRECT_PROMOTE: direct Neo4j promotion has no v2
    # durable journal or active-receipt binding and must be unreachable.
    from amc_publication.vector_bridge28 import verified_mode
    if verified_mode() == 'enforce':
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Legacy direct promotion disabled; use reviewed v2 publication',
        )
    service = PromotionService(db=db)
    try:
        result = await service.apply_approved_proposals(batch_id=batch_id, proposal_id=proposal_id, db=db)
        return {"status": "success", "result": result}
    except Exception as exc:
        logger.error("Promotion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Promotion failed: {str(exc)}"
        )


@router.post("/promote/{patch_id}", response_model=Dict[str, Any])
async def promote_patch_direct(
    patch_id: str,
    current_user: CurrentUser,
    payload: Optional[ApproveRejectIn] = None,
) -> Dict[str, Any]:
    """Directly promote a single patch using state machine (PENDING→APPROVED→STAGED→VERIFIED→ACTIVE).

    R06 FIX: Uses state machine transitions instead of direct promote_to_permanent bypass.
    Approval must be done separately via /governance/approve/{patch_id} first.

    Args:
        patch_id (str): Unique identifier of the patch.
        payload (Optional[ApproveRejectIn]): Request or event payload.
        current_user: Authenticated user from JWT

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
        
    Raises:
        HTTPException(403): If patch not yet approved or self-promotion attempted
    """
    require_approval_role(current_user)
    patch_layer = get_correction_patch_layer()
    
    # FIX (A10): Use get_patch_by_id which is the actual method defined in CorrectionPatchLayer
    patch = patch_layer.get_patch_by_id(patch_id)
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patch {patch_id} not found"
        )
    
    # R06 FIX: Validate state machine transitions
    # Must be at least APPROVED before promotion
    current_status = patch.status if hasattr(patch, 'status') else 'APPROVED'
    if isinstance(current_status, str):
        from app.graph.correction_patch_layer import PatchStatus
        current_status = PatchStatus(current_status)
    
    # R06: Only allow promotion from APPROVED, STAGED, or VERIFIED states
    if current_status not in [PatchStatus.APPROVED, PatchStatus.STAGED, PatchStatus.VERIFIED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot promote patch in {current_status} status. Must be APPROVED, STAGED, or VERIFIED first."
        )
    
    # A04: Four-eyes for promotion - verify approver differs from promoter
    if hasattr(patch, 'provenance') and patch.provenance:
        approver_username = patch.provenance.get("approver_username")
        proposer_username = patch.provenance.get("proposer_username") or patch.provenance.get("actor_id")
        
        if proposer_username and proposer_username == current_user.username:
            logger.warning(
                "PROMOTION_FOUR_EYES: User %s promoting their own proposed patch %s (approved by %s)",
                current_user.username,
                patch_id,
                approver_username or "unknown"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Four-eyes policy violation: Promoter cannot be the original proposer"
            )

    # W25_TRUSTED_APPROVAL_ADAPTER: existing journal + reviewed signed corpus.
    # No request-time DDL, anonymous tenant, fabricated approval or empty corpus.
    try:
        from app.core.database import SessionLocal
        from amc_publication.approval_catalog26 import queue_from_environment_26 as queue_from_environment
        work_id = queue_from_environment(sessions=SessionLocal, patch=patch, actor=current_user)
    except Exception as exc:
        logger.error("Publication prerequisites failed for %s: %s", patch_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verified publication prerequisites unavailable; no job queued",
        ) from exc

    log_governance_audit("PROMOTE_QUEUED", patch_id, current_user.username,
                         {"work_id": work_id})

    # W26_ACCEPTED_JSON: 202 is a successful HTTP response, never an exception.
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": "Publication intent queued. Worker will verify graph/vector effects.",
            "work_id": work_id,
            "status_url": f"/api/publication/status/{work_id}",
        },
    )


async def _execute_graph_mutation_with_verification(patch_id: str, neo4j_session: Any) -> Dict[str, Any]:
    """Execute graph mutation and verify with readback.
    
    R06: Returns receipt with preimage, postimage, and verification status.
    """
    patch_layer = get_correction_patch_layer()
    patch = await patch_layer.get_patch(patch_id)
    if not patch:
        raise ValueError(f"Patch {patch_id} not found for graph mutation")
    
    preimage = {
        "entity_id": patch.entity_id,
        "attribute": patch.attribute,
        "original_value": str(patch.canonical_value) if hasattr(patch, 'canonical_value') else None
    }
    
    # Execute actual Neo4j mutation if session available
    if neo4j_session:
        try:
            # Execute the mutation
            neo4j_session.run(
                """
                MATCH (e) WHERE (e.dedup_key = $entity_id OR e.isin = $entity_id OR e.id = $entity_id)
                SET e.{attribute} = $new_value
                """.format(attribute=patch.attribute.replace(".", "\\.")),
                parameters={
                    "entity_id": patch.entity_id,
                    "new_value": str(patch.corrected_value)
                }
            )
            
            # Read back to verify
            result = neo4j_session.run(
                """
                MATCH (e) WHERE (e.dedup_key = $entity_id OR e.isin = $entity_id OR e.id = $entity_id)
                RETURN e.{attribute} as value
                """.format(attribute=patch.attribute.replace(".", "\\.")),
                parameters={"entity_id": patch.entity_id}
            )
            record = result.single()
            postimage_value = str(record["value"]) if record else None
            
            postimage = {
                "entity_id": patch.entity_id,
                "attribute": patch.attribute,
                "new_value": postimage_value
            }
            
            # Verify match
            if postimage_value != str(patch.corrected_value):
                raise ValueError(f"Readback verification failed: expected {patch.corrected_value}, got {postimage_value}")
            
            return {
                "type": "graph_mutation",
                "patch_id": patch_id,
                "preimage": preimage,
                "postimage": postimage,
                "verified": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as exc:
            logger.error("Graph mutation or verification failed: %s", exc)
            raise
    else:
        # No Neo4j session - fail closed
        raise ValueError("Neo4j session not available for graph mutation verification")


@router.get("/proposals", response_model=List[Dict[str, Any]])
def list_repair_proposals(
    current_user: CurrentUser,
    status_filter: Optional[str] = None,
    proposal_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List repair proposals from the repair proposal queue.

    SEC-02 FIX: Uses JWT-verified role instead of X-User-Role header.

    Args:
        status_filter (Optional[str]): The status filter.
        proposal_type (Optional[str]): The proposal type.
        limit (int): Maximum number of records to return.
        current_user: Authenticated user from JWT
        db (Session): Database session instance.

    Returns:
        List[Dict[str, Any]]: List of resulting items or records.
    """
    require_governance_role(current_user)
    query = db.query(RepairProposal)
    if status_filter:
        query = query.filter(RepairProposal.status == status_filter)
    if proposal_type:
        query = query.filter(RepairProposal.proposal_type == proposal_type)
    proposals = query.order_by(RepairProposal.created_at.desc()).limit(limit).all()
    return [
        {
            "proposal_id": p.proposal_id,
            "unified_record_ref": p.unified_record_ref,
            "proposal_type": p.proposal_type,
            "entity_id": p.entity_id,
            "attribute": p.attribute,
            "mutation_cypher": p.mutation_cypher,
            "affected_nodes": p.affected_nodes,
            "document_ids": p.document_ids,
            "reindex_required": p.reindex_required,
            "confidence": p.confidence,
            "status": p.status,
            "created_at": p.created_at,
            "reviewed_at": p.reviewed_at,
            "reviewed_by": p.reviewed_by,
            "applied_at": p.applied_at,
            "regression_score": p.regression_score,
        }
        for p in proposals
    ]


@router.post("/proposals/{proposal_id}/review", response_model=Dict[str, Any])
def review_repair_proposal(
    proposal_id: str,
    payload: ProposalReviewIn,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Review, approve, or reject a repair proposal.

    SEC-02 FIX: Uses JWT-verified role instead of X-User-Role header.
    A07 FIX: Four-eyes enforcement - proposer and reviewer/approver must be different users.
    A07 FIX: Does NOT directly promote to permanent status - approval is separate from promotion.
    R03 FIX: Use separate review fields instead of invalid 'reviewed_approved' status.

    Args:
        proposal_id (str): Unique identifier of the proposal.
        payload (ProposalReviewIn): Request or event payload.
        current_user: Authenticated user from JWT
        db (Session): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    require_approval_role(current_user)
    proposal = db.query(RepairProposal).filter(RepairProposal.proposal_id == proposal_id).first()
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal {proposal_id} not found"
        )
    
    # A07: Four-eyes enforcement - reviewer cannot be proposer
    proposer_username = getattr(proposal, 'created_by', None) or getattr(proposal, 'proposed_by', None)
    current_user_id = getattr(current_user, 'user_id', None) or current_user.username
    
    if proposer_username and proposer_username == current_user.username:
        logger.warning(
            "FOUR_EYES_VIOLATION: User %s attempted to review their own proposal %s",
            current_user.username,
            proposal_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Four-eyes policy violation: Cannot review your own proposal (proposed by {proposer_username})"
        )
    
    # R03 FIX: Use separate review fields instead of invalid 'reviewed_approved' status
    # The status field must remain one of: 'pending', 'approved', 'rejected', 'applied', 'rolled_back'
    # Review tracking is stored in: reviewed_at, reviewed_by, review_action
    
    if payload.action == "approve":
        proposal.status = "approved"
        logger.info(
            "APPROVED: Proposal %s marked as approved by %s",
            proposal_id, current_user.username
        )
    else:
        proposal.status = "rejected"
        logger.info(
            "Proposal %s marked as rejected by %s",
            proposal_id, current_user.username
        )
    
    proposal.reviewed_at = datetime.utcnow().isoformat() + "Z"
    proposal.reviewed_by = current_user.username
    db.commit()
    return {
        "status": proposal.status,
        "proposal_id": proposal_id,
        "reviewed_by": proposal.reviewed_by,
        "reviewed_at": proposal.reviewed_at,
        "note": "Review recorded. Proposal status updated. Promotion via /promote endpoint."
    }


@router.get("/mutations", response_model=List[Dict[str, Any]])
def list_graph_mutations(
    current_user: CurrentUser,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List historical graph mutations applied to Neo4j.

    SEC-02 FIX: Uses JWT-verified role instead of X-User-Role header.

    Args:
        limit (int): Maximum number of records to return.
        current_user: Authenticated user from JWT
        db (Session): Database session instance.

    Returns:
        List[Dict[str, Any]]: List of resulting items or records.
    """
    require_governance_role(current_user)
    mutations = db.query(GraphMutation).order_by(GraphMutation.applied_at.desc()).limit(limit).all()
    return [
        {
            "mutation_id": m.mutation_id,
            "proposal_id": m.proposal_id,
            "mutation_cypher": m.mutation_cypher,
            "affected_nodes": m.affected_nodes,
            "applied_at": m.applied_at,
            "applied_by": m.applied_by,
            "success": m.success,
            "error": m.error,
        }
        for m in mutations
    ]
