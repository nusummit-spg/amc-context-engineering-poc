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


@router.get("/pending-corrections", response_model=List[CorrectionProposal])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN, Role.REVIEWER])
async def get_pending_corrections(
    current_role: Role = Depends(get_client_role)
) -> List[CorrectionProposal]:
    """Retrieve all pending (unapproved) fact corrections in the shadow graph.

    Args:
        current_role (Role): The current role.

    Returns:
        List[CorrectionProposal]: List of resulting items or records.
    """
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
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN, Role.REVIEWER])
def get_correction_detail(
    patch_id: str,
    current_role: Role = Depends(get_client_role)
) -> CorrectionProposal:
    """Retrieve detailed metadata and evidence for a specific patch.

    Args:
        patch_id (str): Unique identifier of the patch.
        current_role (Role): The current role.

    Returns:
        CorrectionProposal: Resulting CorrectionProposal instance.
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
    """Approve correction patch: promotes to permanent canonical status and removes TTL.

    Args:
        patch_id (str): Unique identifier of the patch.
        payload (Optional[ApproveRejectIn]): Request or event payload.
        current_role (Role): The current role.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
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
        from app.engine.graph_store import get_driver, config as g_config
        driver = get_driver()
        if driver:
            neo4j_session = driver.session(database=getattr(g_config, "NEO4J_DATABASE", "neo4j"))
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
    """Reject correction patch: deletes patch from shadow graph.

    Args:
        patch_id (str): Unique identifier of the patch.
        payload (Optional[ApproveRejectIn]): Request or event payload.
        current_role (Role): The current role.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
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
    """Batch process (approve or reject) multiple correction patches at once.

    Args:
        payload (BatchApprovalIn): Request or event payload.
        current_role (Role): The current role.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
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


class GovernanceBatchIn(BaseModel):
    auto_approve_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    max_risk_level: str = Field(default="LOW", pattern="^(LOW|MEDIUM|HIGH)$")
    dry_run: bool = False


@router.post("/run-batch", response_model=Dict[str, Any])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN])
async def run_governance_batch(
    payload: Optional[GovernanceBatchIn] = None,
    current_role: Role = Depends(get_client_role),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Run automated hands-free governance batch processor:
    Evaluates all pending patches. Those with confidence >= auto_approve_threshold (default 0.95)
    and risk_level == LOW are canonically promoted to the Neo4j graph and fast-path, retiring shadow patches.

    Args:
        payload (Optional[GovernanceBatchIn]): Request or event payload.
        current_role (Role): The current role.
        db (Session): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    threshold = payload.auto_approve_threshold if payload else 0.95
    max_risk = payload.max_risk_level if payload else "LOW"
    dry_run = payload.dry_run if payload else False

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
    approved_ids: List[str] = []
    rejected_ids: List[str] = []
    needs_review_ids: List[str] = []

    neo4j_session = None
    try:
        from app.engine.graph_store import get_driver, config as g_config
        driver = get_driver()
        if driver:
            neo4j_session = driver.session(database=getattr(g_config, "NEO4J_DATABASE", "neo4j"))
    except Exception as exc:
        logger.debug("Neo4j session acquisition notice: %s", exc)

    try:
        from app.services.repair_integration import get_repair_integration
        repair_int = get_repair_integration()
    except Exception:
        repair_int = None

    try:
        for patch in pending:
            risk = assess_risk_level(patch.confidence, patch.canonical_value, patch.corrected_value)
            risk_acceptable = (risk == "LOW") if max_risk == "LOW" else (risk in ("LOW", "MEDIUM"))

            if patch.confidence >= threshold and risk_acceptable:
                if not dry_run:
                    ok = patch_layer.promote_to_permanent(patch.patch_id, neo4j_session=neo4j_session)
                    if ok:
                        approved_ids.append(patch.patch_id)
                        log_governance_audit("AUTO_APPROVE_BATCH", patch.patch_id, current_role.value, {
                            "confidence": patch.confidence,
                            "threshold": threshold,
                            "risk_level": risk
                        })
                        if repair_int:
                            try:
                                await repair_int.promote_patch(patch.patch_id)
                            except Exception:
                                pass
                    else:
                        needs_review_ids.append(patch.patch_id)
                else:
                    approved_ids.append(patch.patch_id)
            elif patch.confidence < 0.50:
                if not dry_run:
                    patch_layer.delete_patch(patch.patch_id)
                    rejected_ids.append(patch.patch_id)
                    log_governance_audit("AUTO_REJECT_BATCH", patch.patch_id, current_role.value, {
                        "confidence": patch.confidence
                    })
                else:
                    rejected_ids.append(patch.patch_id)
            else:
                needs_review_ids.append(patch.patch_id)
    finally:
        if neo4j_session:
            try:
                neo4j_session.close()
            except Exception:
                pass

    # Also synchronize microservice batch runner if available
    microservice_report = None
    if repair_int and not dry_run:
        try:
            microservice_report = await repair_int.run_governance_batch(auto_approve_threshold=threshold)
        except Exception as exc:
            logger.debug("Microservice run_governance_batch notice: %s", exc)

    # Also synchronize SQL RepairProposal batch scheduler if database session active
    try:
        from app.services.governance_scheduler import GovernanceBatchScheduler
        scheduler = GovernanceBatchScheduler(confidence_threshold=threshold)
        await scheduler.run_weekly_batch()
    except Exception as s_exc:
        logger.debug("SQL governance scheduler batch notice: %s", s_exc)

    ms_approved = (microservice_report.get("approved", 0) if microservice_report else 0)
    ms_evaluated = (microservice_report.get("total_evaluated", 0) if microservice_report else 0)
    ms_promoted = (microservice_report.get("deployed", 0) if microservice_report else 0)
    ms_rejected = (microservice_report.get("rejected", 0) if microservice_report else 0)
    ms_review = (microservice_report.get("needs_review", 0) if microservice_report else 0)

    final_total = max(total_evaluated, ms_evaluated)
    final_approved = max(len(approved_ids), ms_approved)
    final_promoted = max(len(approved_ids), ms_promoted)
    final_rejected = max(len(rejected_ids), ms_rejected)
    final_review = max(len(needs_review_ids), ms_review)

    return {
        "status": "completed",
        "total_evaluated": final_total,
        "approved": final_approved,
        "promoted_to_graph": final_promoted,
        "rejected": final_rejected,
        "needs_review": final_review,
        "approved_patches": approved_ids,
        "dry_run": dry_run,
        "threshold_used": threshold,
        "max_risk_level": max_risk,
        "microservice_sync": microservice_report,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


class ProposalReviewIn(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    comment: Optional[str] = None


@router.post("/promote", response_model=Dict[str, Any])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN])
def promote_approved_proposals(
    batch_id: Optional[str] = None,
    proposal_id: Optional[str] = None,
    current_role: Role = Depends(get_client_role),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Apply approved repair proposals to canonical Neo4j graph and vector stores.

    Args:
        batch_id (Optional[str]): Unique identifier of the batch.
        proposal_id (Optional[str]): Unique identifier of the proposal.
        current_role (Role): The current role.
        db (Session): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    service = PromotionService(db=db)
    try:
        result = service.apply_approved_proposals(batch_id=batch_id, proposal_id=proposal_id, db=db)
        return {"status": "success", "result": result}
    except Exception as exc:
        logger.error("Promotion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Promotion failed: {str(exc)}"
        )


@router.post("/promote/{patch_id}", response_model=Dict[str, Any])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN])
async def promote_patch_direct(
    patch_id: str,
    payload: Optional[ApproveRejectIn] = None,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """Directly promote a single patch into canonical Neo4j graph and retire its shadow patch.

    Args:
        patch_id (str): Unique identifier of the patch.
        payload (Optional[ApproveRejectIn]): Request or event payload.
        current_role (Role): The current role.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    patch_layer = get_correction_patch_layer()
    patch = patch_layer.get_patch_by_id(patch_id)
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patch {patch_id} not found"
        )

    # 1. Promote in local patch layer (and Neo4j if available)
    neo4j_session = None
    try:
        from app.engine.graph_store import get_driver, config as g_config
        driver = get_driver()
        if driver:
            neo4j_session = driver.session(database=getattr(g_config, "NEO4J_DATABASE", "neo4j"))
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

    # 2. Also notify repair engine microservice
    try:
        from app.services.repair_integration import get_repair_integration
        repair_int = get_repair_integration()
        await repair_int.promote_patch(patch_id)
    except Exception as exc:
        logger.debug("Repair microservice promote notification: %s", exc)

    comment = payload.comment if payload else None
    log_governance_audit("PROMOTE_DIRECT", patch_id, current_role.value, {"comment": comment})

    return {
        "status": "promoted",
        "patch_id": patch_id,
        "promoted_by": current_role.value,
        "promoted_at": datetime.utcnow().isoformat() + "Z",
        "comment": comment
    }


@router.get("/proposals", response_model=List[Dict[str, Any]])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN, Role.REVIEWER])
def list_repair_proposals(
    status_filter: Optional[str] = None,
    proposal_type: Optional[str] = None,
    limit: int = 50,
    current_role: Role = Depends(get_client_role),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List repair proposals from the repair proposal queue.

    Args:
        status_filter (Optional[str]): The status filter.
        proposal_type (Optional[str]): The proposal type.
        limit (int): Maximum number of records to return.
        current_role (Role): The current role.
        db (Session): Database session instance.

    Returns:
        List[Dict[str, Any]]: List of resulting items or records.
    """
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
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN])
def review_repair_proposal(
    proposal_id: str,
    payload: ProposalReviewIn,
    current_role: Role = Depends(get_client_role),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Review, approve, or reject a repair proposal.

    Args:
        proposal_id (str): Unique identifier of the proposal.
        payload (ProposalReviewIn): Request or event payload.
        current_role (Role): The current role.
        db (Session): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    proposal = db.query(RepairProposal).filter(RepairProposal.proposal_id == proposal_id).first()
    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal {proposal_id} not found"
        )
    proposal.status = "approved" if payload.action == "approve" else "rejected"
    proposal.reviewed_at = datetime.utcnow().isoformat() + "Z"
    proposal.reviewed_by = current_role.value
    db.commit()
    return {
        "status": proposal.status,
        "proposal_id": proposal_id,
        "reviewed_by": proposal.reviewed_by,
        "reviewed_at": proposal.reviewed_at
    }


@router.get("/mutations", response_model=List[Dict[str, Any]])
@require_roles([Role.COMPLIANCE_OFFICER, Role.ADMIN, Role.REVIEWER])
def list_graph_mutations(
    limit: int = 50,
    current_role: Role = Depends(get_client_role),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List historical graph mutations applied to Neo4j.

    Args:
        limit (int): Maximum number of records to return.
        current_role (Role): The current role.
        db (Session): Database session instance.

    Returns:
        List[Dict[str, Any]]: List of resulting items or records.
    """
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
