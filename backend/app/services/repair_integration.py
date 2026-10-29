# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
repair_integration.py
=====================
Integrates repair engine microservice with feedback loop and query context.

End-to-end flow:
  1. User submits feedback with corrections
  2. Feedback loop processes and creates UnifiedEvaluationRecord
  3. If repair=true, extract corrections and call repair engine
  4. Repair engine creates patches (persisted in layer)
  5. Next query: patches injected into context
  6. LLM synthesis uses corrected values
  7. User receives corrected response
"""

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional
import uuid

import httpx
from app.config import get_settings
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from sqlalchemy.orm import Session
from app.core.logging import (
    log_step_info,
    log_step_warning,
    log_step_error,
    log_step_debug,
)

logger = logging.getLogger("app.services.repair_integration")


class RepairEngineIntegration:
    """
    Bridge between feedback loop and repair engine microservice.
    
    Handles:
    - Extraction of corrections from unified evaluation records
    - HTTP communication with repair engine
    - Patch injection into query context
    - Governance batch triggering
    """
    
    def __init__(self, repair_service_url: Optional[str] = None):
        """Initialize with repair engine URL.

        Args:
            repair_service_url (Optional[str]): The repair service url.
        """
        self.repair_service_url = repair_service_url or get_settings().repair_service_url or "http://localhost:8002"
        self.timeout = float(get_settings().service_timeout or 30.0)
    
    async def trigger_repair_engine(
        self,
        record: UnifiedEvaluationRecord,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Trigger repair engine to create patches from unified evaluation record.
        
        Args:
            record: UnifiedEvaluationRecord with corrections
            db: Database session (optional)
        
        Returns:
            Dict with created patch IDs and status
        """
        if not self.repair_service_url:
            logger.debug("Repair service URL not configured, skipping repair engine trigger")
            return {"success": False, "reason": "repair_service_url_not_configured"}
        
        # Check if record has already been processed and resolved to prevent duplicate patches
        from app.schemas.models import LifecycleStatus
        status_val = record.lifecycle_status.value if hasattr(record.lifecycle_status, "value") else str(record.lifecycle_status or "").lower()
        if status_val == "resolved" and db:
            from app.schemas.repair_proposals import RepairProposal
            existing_prop = db.query(RepairProposal).filter(RepairProposal.unified_record_ref == record.response_id).first()
            if existing_prop:
                log_step_info(logger, "REPAIR_ALREADY_RESOLVED", "Skipping repair: Record %s is already resolved (proposal=%s)", record.response_id, existing_prop.proposal_id)
                return {
                    "success": True,
                    "response_id": record.response_id,
                    "patches_created": [],
                    "patches_failed": [],
                    "errors": [],
                    "proposal_id": existing_prop.proposal_id,
                    "already_processed": True,
                }
        
        evidence = record.dissatisfaction_evidence_json or {}
        raw_claims = evidence.get("correction_claims", []) if isinstance(evidence, dict) else []

        valid_claims = []
        for c in raw_claims:
            if isinstance(c, dict) and (c.get("attribute") or c.get("asserted_value") or c.get("entity_id")):
                valid_claims.append(c)

        if not valid_claims:
            # Fallback claim synthesis when repair is flagged by root_cause/adjudication
            synth_entity = None
            synth_attr = record.root_cause or "compliance"
            synth_val = None

            fb_notes = evidence.get("feedback_text") if isinstance(evidence, dict) else None
            fb_cats = []

            if db:
                try:
                    from app.schemas.response_feedback_table import ResponseFeedback
                    fb_row = db.query(ResponseFeedback).filter(ResponseFeedback.response_id == record.response_id).first()
                    if fb_row:
                        fb_notes = fb_notes or fb_row.feedback_text
                        fb_cats = fb_row.selected_categories or []
                except Exception as fb_err:
                    logger.debug("Could not fetch ResponseFeedback for repair synthesis: %s", fb_err)

                try:
                    from app.schemas.query_evidence_table import QueryEvidence
                    q_ev = db.query(QueryEvidence).filter(QueryEvidence.response_id == record.response_id).first()
                    if q_ev:
                        if q_ev.assembled_context_json:
                            ctx = q_ev.assembled_context_json
                            if isinstance(ctx, dict):
                                sources = ctx.get("sources") or ctx.get("chunks") or []
                                if sources and isinstance(sources, list) and isinstance(sources[0], dict):
                                    synth_entity = sources[0].get("document_title") or sources[0].get("document_id") or sources[0].get("entity_id")
                            elif isinstance(ctx, list) and ctx and isinstance(ctx[0], dict):
                                synth_entity = ctx[0].get("document_title") or ctx[0].get("document_id") or ctx[0].get("entity_id")
                        if not synth_entity and q_ev.query_text:
                            synth_entity = "Thematic Fund" if "thematic" in q_ev.query_text.lower() else "AMC Scheme"
                except Exception as q_err:
                    logger.debug("Could not fetch QueryEvidence for repair synthesis: %s", q_err)

            if fb_cats:
                synth_attr = f"{record.root_cause or 'compliance'}_{fb_cats[0]}"

            synth_entity = synth_entity or (record.root_cause.capitalize() if record.root_cause else "Compliance Entity")
            synth_val = fb_notes or f"Flagged {record.root_cause or 'compliance'} repair: {', '.join(fb_cats) if fb_cats else 'triage'}"

            valid_claims = [{
                "entity_id": synth_entity,
                "entity_name": synth_entity,
                "attribute": synth_attr,
                "asserted_value": synth_val,
                "rejected_value": "canonical",
                "confidence": float(record.adjudication_confidence or 0.85),
                "source": "unified_repair_synthesizer"
            }]

        correction_claims = valid_claims

        log_step_info(
            logger,
            "REPAIR_TRIGGER",
            "Step 1: Processing %d correction claim(s) for response %s",
            len(correction_claims),
            record.response_id
        )
        
        result = {
            "success": True,
            "response_id": record.response_id,
            "patches_created": [],
            "patches_failed": [],
            "errors": []
        }
        
        from app.api.routes.governance import assess_risk_level

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for idx, claim in enumerate(correction_claims, 1):
                try:
                    conf = float(claim.get("confidence") or record.adjudication_confidence or 0.75)
                    claim["confidence"] = conf
                    canonical_val = claim.get("rejected_value") or "canonical"
                    corrected_val = claim.get("asserted_value") or claim.get("rejected_value") or "repair_flagged"

                    # Deduplication: check if patch layer already has an active patch for this entity/attribute
                    from app.graph.correction_patch_layer import get_correction_patch_layer, CorrectionPatch
                    p_layer = get_correction_patch_layer()
                    entity_str = str(claim.get("entity_id") or "unknown_entity")
                    attr_str = str(claim.get("attribute") or "general")
                    existing_p = p_layer.get_correction(entity_str, attr_str)
                    if existing_p and (existing_p.corrected_value == corrected_val or (existing_p.provenance and existing_p.provenance.get("response_id") == record.response_id)):
                        log_step_info(logger, "PATCH_REUSED", "Step 2: Found matching patch %s for %s.%s; reusing without duplication", existing_p.patch_id, entity_str, attr_str)
                        result["patches_created"].append(existing_p.patch_id)
                        continue

                    risk = assess_risk_level(conf, canonical_val, corrected_val)
                    claim_is_auto_approved = (conf >= 0.95 and risk == "LOW")

                    patch_response = await self._create_patch_via_api(
                        client=client,
                        claim=claim,
                        response_id=record.response_id,
                        approved=claim_is_auto_approved,
                    )
                    
                    patch_id = (patch_response.get("patch_id") if isinstance(patch_response, dict) else None) or f"patch_{uuid.uuid4().hex[:12]}"
                    result["patches_created"].append(patch_id)
                    try:
                        from app.graph.correction_patch_layer import get_correction_patch_layer, CorrectionPatch
                        from app.schemas.models import _now_iso
                        from dataclasses import asdict
                        p_layer = get_correction_patch_layer()
                        p_obj = CorrectionPatch(
                            patch_id=patch_id,
                            entity_id=str(claim.get("entity_id") or "unknown_entity"),
                            attribute=str(claim.get("attribute") or "general"),
                            canonical_value=canonical_val,
                            corrected_value=corrected_val,
                            confidence=conf,
                            provenance={"source": "unified_feedback_loop", "response_id": record.response_id},
                            approved=claim_is_auto_approved,
                            created_at=_now_iso(),
                            expires_at=None if claim_is_auto_approved else (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z",
                        )
                        p_layer._mem_store[patch_id] = asdict(p_obj)
                        k = p_layer._make_key(p_obj.entity_id, p_obj.attribute)
                        p_layer._mem_store[k] = asdict(p_obj)
                    except Exception as p_sync_err:
                        logger.debug("Local patch store sync notice: %s", p_sync_err)
                    log_step_info(
                        logger,
                        "PATCH_CREATED",
                        "Step 2b: Created correction patch %s (%d/%d): entity=%s, attribute=%s, auto_approved=%s",
                        patch_id,
                        idx,
                        len(correction_claims),
                        claim.get("entity_id", "?"),
                        claim.get("attribute", "?"),
                        claim_is_auto_approved,
                    )
                
                except Exception as exc:
                    error_msg = f"Exception creating patch: {exc}"
                    result["patches_failed"].append(claim)
                    result["errors"].append(error_msg)
                    log_step_error(
                        logger,
                        "PATCH_ERROR",
                        "Patch %d/%d exception: %s",
                        idx,
                        len(correction_claims),
                        exc
                    )
        
        log_step_info(
            logger,
            "REPAIR_RESULT",
            "Step 3: Repair engine generated %d patch(es) for response %s (%d failed)",
            len(result["patches_created"]),
            record.response_id,
            len(result["patches_failed"])
        )

        if result["patches_created"]:
            try:
                from app.retrieval.cache import get_semantic_cache
                get_semantic_cache().clear()
                log_step_info(logger, "CACHE_CLEARED", "Step 4: Cleared semantic cache for %s so patched truth is immediately live", record.response_id)
            except Exception as cache_exc:
                log_step_debug(logger, "CACHE_CLEAR_NOTICE", "Could not clear semantic cache: %s", cache_exc)

            # Option 3: Ingest synthetic patch chunk into vector store
            try:
                from app.vector.client import get_base_vector_store
                vstore = get_base_vector_store()
                for patch_id, claim in zip(result["patches_created"], correction_claims):
                    entity = claim.get("entity_id") or claim.get("entity_name") or "Fund"
                    attr = claim.get("attribute") or "general"
                    val = claim.get("asserted_value")
                    await vstore.ingest_synthetic_patch_chunk(
                        patch_id=patch_id,
                        entity_id=entity,
                        attribute=attr,
                        value=val,
                    )
            except Exception as v_exc:
                logger.debug("Option 3 synthetic chunk ingestion notice: %s", v_exc)

            # Hands-Free Auto-Approval: automatically promote high-confidence (>= 0.95) & LOW-risk patches
            for patch_id, claim in zip(result["patches_created"], correction_claims):
                try:
                    conf = float(claim.get("confidence") or record.adjudication_confidence or 0.0)
                    canonical_val = claim.get("rejected_value") or "canonical"
                    corrected_val = claim.get("asserted_value") or claim.get("rejected_value") or "repair_flagged"
                    if conf >= 0.95:
                        risk = assess_risk_level(conf, canonical_val, corrected_val)
                        if risk == "LOW":
                            from app.graph.correction_patch_layer import get_correction_patch_layer
                            p_layer = get_correction_patch_layer()
                            patch_obj = p_layer.get_patch_by_id(patch_id)
                            if patch_obj and patch_obj.approved:
                                logger.debug("Patch %s is already approved and permanent; skipping redundant auto-promote", patch_id)
                                continue
                            log_step_info(logger, "HANDS_FREE_AUTO_APPROVE", "Step 5: Auto-approved low-risk patch %s (confidence=%.2f, risk=LOW)", patch_id, conf)
                            from app.graph.correction_patch_layer import get_correction_patch_layer
                            from app.engine.graph_store import get_driver, config as g_config
                            p_layer = get_correction_patch_layer()
                            n_session = None
                            try:
                                driver = get_driver()
                                if driver:
                                    n_session = driver.session(database=getattr(g_config, "NEO4J_DATABASE", "neo4j"))
                                p_layer.promote_to_permanent(patch_id, neo4j_session=n_session)
                            finally:
                                if n_session:
                                    try:
                                        n_session.close()
                                    except Exception:
                                        pass
                            try:
                                await self.promote_patch(patch_id)
                            except Exception as ms_err:
                                logger.debug("Promote patch microservice sync notice: %s", ms_err)
                            result.setdefault("auto_approved", []).append(patch_id)
                except Exception as auto_exc:
                    logger.debug("Hands-free auto-approval notice: %s", auto_exc)

        is_auto_approved = bool(result.get("auto_approved"))

        if db and (result.get("patches_created") or record.repair):
            try:
                from app.services.repair_proposal_service import RepairProposalService
                proposal_svc = RepairProposalService()
                proposal = proposal_svc.create_proposal_from_record(record, db, is_approved=is_auto_approved)
                result["proposal_id"] = proposal.proposal_id
                log_step_info(logger, "PROPOSAL_CREATED", "Step 6: Created repair proposal %s (auto_approved=%s)", proposal.proposal_id, is_auto_approved)
            except Exception as prop_exc:
                logger.debug("Repair proposal creation notice: %s", prop_exc)

            if is_auto_approved:
                try:
                    from app.schemas.models import LifecycleStatus, _now_iso
                    record.lifecycle_status = LifecycleStatus.RESOLVED
                    record.updated_at = _now_iso()
                    db.commit()
                    log_step_info(logger, "UNIFIED_RECORD_RESOLVED", "Step 7: Marked Unified Evaluation Record %s as resolved", record.response_id)
                except Exception as rec_exc:
                    logger.debug("Unified record status update notice: %s", rec_exc)

            # Link repair outcome back to FeedbackIssue so frontend reflects the new status
            try:
                from app.schemas.response_feedback_table import ResponseFeedback
                from app.feedback import issue_store
                from app.schemas.feedback_issues_table import IssueStatus
                from app.feedback.repair_linkage import RepairLinkageService
                from app.feedback.intent_matcher import clear_pending_feedback_cache
                from app.feedback.feedback_cache import get_feedback_cache
                from app.feedback.issue_matcher import get_issue_matcher

                fb_row = db.query(ResponseFeedback).filter(ResponseFeedback.response_id == record.response_id).first()
                if fb_row and fb_row.issue_id:
                    issue = issue_store.get_issue_by_id(db, fb_row.issue_id)
                    if issue:
                        primary_task = (
                            result["patches_created"][0]
                            if result.get("patches_created")
                            else result.get("proposal_id")
                        )
                        linkage_svc = RepairLinkageService()
                        if is_auto_approved:
                            linkage_svc.transition_issue_status(
                                db=db,
                                issue_id=issue.issue_id,
                                new_status=IssueStatus.RESOLVED.value,
                                resolution_notes=f"Auto-repaired: high-confidence (>0.95) correction applied (task={primary_task}).",
                                repair_task_id=primary_task,
                            )
                            log_step_info(
                                logger,
                                "ISSUE_AUTO_RESOLVED",
                                "FeedbackIssue %s transitioned to 'resolved' following auto-repair (task=%s)",
                                issue.issue_id,
                                primary_task,
                            )
                        else:
                            if issue.status == IssueStatus.REPORTED.value:
                                linkage_svc.transition_issue_status(
                                    db=db,
                                    issue_id=issue.issue_id,
                                    new_status=IssueStatus.IN_REPAIR.value,
                                    repair_task_id=primary_task,
                                )
                                log_step_info(
                                    logger,
                                    "ISSUE_IN_REPAIR",
                                    "FeedbackIssue %s transitioned to 'in_repair' (task=%s)",
                                    issue.issue_id,
                                    primary_task,
                                )

                        try:
                            from app.feedback.intent_matcher import clear_pending_feedback_cache
                            clear_pending_feedback_cache(suppress_prior_feedbacks=False)
                            get_feedback_cache().invalidate_issue(issue.issue_id)
                            get_issue_matcher().sync_open_issues(db)
                        except Exception as cache_err:
                            logger.debug("Cache invalidation notice in repair_integration: %s", cache_err)

            except Exception as issue_sync_err:
                log_step_warning(
                    logger,
                    "ISSUE_SYNC_WARNING",
                    "Could not link repair result to FeedbackIssue for response_id=%s: %s",
                    record.response_id,
                    issue_sync_err,
                )

        return result
    
    async def _create_patch_via_api(
        self,
        client: httpx.AsyncClient,
        claim: Dict[str, Any],
        response_id: str,
        approved: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a single patch via HTTP API.
        
        Args:
            client: httpx AsyncClient
            claim: Correction claim from evidence
            response_id: Source response ID
            approved: Whether patch is pre-approved
        
        Returns:
            API response dict or None on failure
        """
        url = f"{self.repair_service_url}/api/patches"
        
        payload = {
            "entity_id": claim.get("entity_id") or claim.get("entity_name") or "unknown_entity",
            "attribute": claim.get("attribute") or "general",
            "canonical_value": claim.get("rejected_value") or "canonical",
            "corrected_value": claim.get("asserted_value") or claim.get("rejected_value") or "repair_flagged",
            "confidence": float(claim.get("confidence", 0.75)),
            "provenance": {
                "source": "unified_feedback_loop",
                "response_id": response_id,
                "entity_name": claim.get("entity_name"),
                "extraction_method": claim.get("source", "unknown")
            },
            "approved": approved
        }
        
        try:
            logger.debug(
                "📡 HTTP POST to repair engine: %s with entity_id=%s, attr=%s",
                url,
                payload["entity_id"],
                payload["attribute"]
            )
            
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                logger.debug("Repair engine response: %s", data)
                return data
            else:
                logger.warning(
                    "Repair engine HTTP %d: %s",
                    response.status_code,
                    response.text[:200]
                )
                return None
        
        except (httpx.TimeoutException, TimeoutError):
            logger.warning("Repair engine timeout (%.1f seconds)", self.timeout)
            return None
        except Exception as exc:
            logger.debug("Repair engine communication notice: %s", exc)
            return None
    
    async def get_patches_for_entities(
        self,
        entity_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Fetch applicable patches for entities (used during query retrieval).
        
        Args:
            entity_ids: List of entity IDs to get patches for
        
        Returns:
            List of patch dicts
        """
        if not self.repair_service_url or not entity_ids:
            return []
        
        try:
            entity_ids_str = ",".join(entity_ids)
            url = f"{self.repair_service_url}/api/patches/for-entities"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params={"entity_ids": entity_ids_str})
                
                if response.status_code == 200:
                    data = response.json()
                    patches = data.get("patches", [])
                    if patches:
                        logger.debug("🔧 Retrieved %d patches for %d entities", len(patches), len(entity_ids))
                    return patches
                else:
                    logger.warning("Failed to fetch patches: HTTP %d", response.status_code)
                    return []
        
        except Exception as exc:
            logger.warning("Could not fetch patches: %s", exc)
            return []
    
    async def run_governance_batch(
        self,
        auto_approve_threshold: float = 0.95
    ) -> Optional[Dict[str, Any]]:
        """
        Trigger governance batch in repair engine.
        
        Args:
            auto_approve_threshold: Confidence threshold for auto-approval
        
        Returns:
            Governance batch result or None
        """
        if not self.repair_service_url:
            logger.debug("Repair service URL not configured, skipping governance batch")
            return None
        
        try:
            url = f"{self.repair_service_url}/api/governance/run-batch"
            payload = {"auto_approve_threshold": auto_approve_threshold}
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                log_step_info(logger, "GOVERNANCE_START", "Starting governance batch with threshold=%.2f", auto_approve_threshold)
                
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    log_step_info(
                        logger,
                        "GOVERNANCE_COMPLETE",
                        "Governance batch completed: evaluated=%d, approved=%d, deployed=%d",
                        result.get("total_evaluated", 0),
                        result.get("approved", 0),
                        result.get("deployed", 0)
                    )
                    return result
                else:
                    log_step_warning(logger, "GOVERNANCE_WARN", "Governance batch failed: HTTP %d", response.status_code)
                    return None
        
        except Exception as exc:
            log_step_error(logger, "GOVERNANCE_ERROR", "Governance batch error: %s", exc)
            return None

    async def promote_patch(self, patch_id: str) -> bool:
        """Trigger canonical promotion of patch on repair service.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if not self.repair_service_url:
            return False
        try:
            url = f"{self.repair_service_url}/api/governance/promote/{patch_id}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url)
                return res.status_code == 200
        except Exception as exc:
            log_step_warning(logger, "PROMOTE_PATCH_WARN", "Error calling promote_patch on repair engine: %s", exc)
            return False


# Singleton instance
_repair_integration: Optional[RepairEngineIntegration] = None


def get_repair_integration() -> RepairEngineIntegration:
    """Get or create repair integration singleton.

    Returns:
        RepairEngineIntegration: Resulting RepairEngineIntegration instance.
    """
    global _repair_integration
    if _repair_integration is None:
        _repair_integration = RepairEngineIntegration()
    return _repair_integration


async def trigger_repair_on_feedback(
    record: UnifiedEvaluationRecord,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """Public API to trigger repair engine when feedback creates a unified record.

    Called from feedback.py after UnifiedEvaluationRecord is created.

    Args:
        record (UnifiedEvaluationRecord): The record.
        db (Optional[Session]): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    log_step_info(
        logger,
        "REPAIR_INTEGRATION_INVOKED",
        "Repair integration called: response_id=%s, repair=%s, root_cause=%s",
        record.response_id,
        record.repair,
        record.root_cause
    )
    
    if not record.repair:
        logger.debug("Record doesn't require repair, skipping")
        return {"success": False, "reason": "repair_not_flagged"}
    
    integration = get_repair_integration()
    result = await integration.trigger_repair_engine(record, db)
    
    return result
