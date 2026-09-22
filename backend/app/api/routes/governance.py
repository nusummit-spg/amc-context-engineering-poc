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

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.compliance.security import get_client_role, require_roles
from app.graph.correction_patch_layer import CorrectionPatch, get_correction_patch_layer
from app.models.compliance_models import Role

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
    """
    Assess regulatory and data risk of a proposed fact change:
      - HIGH: low confidence (< 0.70) OR > 20% relative numeric delta
      - MEDIUM: moderate confidence (0.70 - 0.85) OR 10-20% relative delta
      - LOW: high confidence (>= 0.85) AND <= 10% relative delta
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


@router.get("/pending-corrections", response_model=List[CorrectionProposal])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN, Role.REVIEWER])
def get_pending_corrections(
    current_role: Role = Depends(get_client_role)
) -> List[CorrectionProposal]:
    """
    Retrieve all pending (unapproved) fact corrections in the shadow graph.
    """
    patch_layer = get_correction_patch_layer()
    pending_patches = patch_layer.get_all_pending()

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

        proposals.append(CorrectionProposal(
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
        ))

    return proposals


@router.get("/correction/{patch_id}", response_model=CorrectionProposal)
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN, Role.REVIEWER])
def get_correction_detail(
    patch_id: str,
    current_role: Role = Depends(get_client_role)
) -> CorrectionProposal:
    """
    Retrieve detailed metadata and evidence for a specific patch.
    """
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
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN])
def approve_correction(
    patch_id: str,
    payload: Optional[ApproveRejectIn] = None,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Approve correction patch: promotes to permanent canonical status and removes TTL.
    """
    patch_layer = get_correction_patch_layer()
    patch = patch_layer.get_patch_by_id(patch_id)
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patch {patch_id} not found"
        )

    # Optional Neo4j session write
    neo4j_session = None
    try:
        from app.api.deps import get_container
        container = get_container()
        if hasattr(container, "graph") and container.graph is not None:
            neo4j_session = container.graph._get_driver().session()
    except Exception as exc:
        logger.debug("Neo4j session acquisition notice: %s", exc)

    try:
        success = patch_layer.promote_to_permanent(patch_id, neo4j_session=neo4j_session)
    finally:
        if neo4j_session:
            try:
                neo4j_session.close()
            except Exception:
                pass

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to promote patch {patch_id}"
        )

    comment = payload.comment if payload else None
    log_governance_audit("APPROVE", patch_id, current_role.value, {"comment": comment})

    return {
        "status": "approved",
        "patch_id": patch_id,
        "approved_by": current_role.value,
        "approved_at": datetime.utcnow().isoformat() + "Z",
        "comment": comment
    }


@router.post("/reject/{patch_id}", response_model=Dict[str, Any])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN])
def reject_correction(
    patch_id: str,
    payload: Optional[ApproveRejectIn] = None,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Reject correction patch: deletes patch from shadow graph.
    """
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
    log_governance_audit("REJECT", patch_id, current_role.value, {"reason": reason})

    return {
        "status": "rejected",
        "patch_id": patch_id,
        "rejected_by": current_role.value,
        "rejected_at": datetime.utcnow().isoformat() + "Z",
        "reason": reason
    }


@router.post("/batch-approve", response_model=Dict[str, Any])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN])
def batch_approve_corrections(
    payload: BatchApprovalIn,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Batch process (approve or reject) multiple correction patches at once.
    """
    patch_layer = get_correction_patch_layer()
    succeeded = []
    failed = []

    for pid in payload.patch_ids:
        try:
            if payload.action == "approve":
                ok = patch_layer.promote_to_permanent(pid)
                if ok:
                    succeeded.append(pid)
                    log_governance_audit("APPROVE_BATCH", pid, current_role.value, {"comment": payload.comment})
                else:
                    failed.append(pid)
            elif payload.action == "reject":
                ok = patch_layer.delete_patch(pid)
                if ok:
                    succeeded.append(pid)
                    log_governance_audit("REJECT_BATCH", pid, current_role.value, {"comment": payload.comment})
                else:
                    failed.append(pid)
        except Exception as exc:
            logger.warning("Batch action error on %s: %s", pid, exc)
            failed.append(pid)

    return {
        "action": payload.action,
        "total": len(payload.patch_ids),
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
        "succeeded": succeeded,
        "failed": failed
    }
