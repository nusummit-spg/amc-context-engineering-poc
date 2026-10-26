# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
repair_service.py
=================
Bridge between unified evaluation records and the correction patch layer.

Processes unified_evaluation_records flagged with repair=true and extracts
correction claims to create patches in the shadow graph (CorrectionPatchLayer).

This is the missing link that activates the repair module:
  1. Feedback loop creates unified_evaluation_records with repair=true
  2. This service extracts the dissatisfaction_evidence
  3. Creates CorrectionPatch objects in the shadow layer
  4. Patches are injected into retrieval context
  5. Governance batch promotes approved patches to canonical graph
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.feedback.correction_extractor import CorrectionExtractor, StructuredClaim
from app.feedback.fund_name_matcher import get_fund_name_matcher
from app.graph.correction_patch_layer import get_correction_patch_layer
from app.schemas.unified_evaluation_records_table import UnifiedEvaluationRecord
from app.schemas.query_evidence_table import QueryEvidence
from app.core.logging import (
    log_step_info,
    log_step_warning,
    log_step_error,
    log_step_debug,
)

logger = logging.getLogger("app.services.repair")


def extract_corrections_from_evidence(
    dissatisfaction_evidence: Optional[Dict[str, Any]],
    query_text: str = "",
    response_text: str = ""
) -> List[Dict[str, Any]]:
    """
    Extract correction claims from dissatisfaction evidence JSON.
    
    Attempts to find structured corrections in the evidence, with fallback
    to parsing the feedback text if structured data isn't present.
    
    Args:
        dissatisfaction_evidence: JSON object containing dissatisfaction signals
        query_text: Original query for context
        response_text: Original response for context
    
    Returns:
        List of correction dicts: {entity_id, entity_name, attribute, asserted_value, 
                                   rejected_value, confidence, source}
    """
    corrections = []
    
    if not dissatisfaction_evidence:
        return corrections
    
    # Path 1: Structured corrections already extracted by feedback loop
    if isinstance(dissatisfaction_evidence, dict):
        structured_claims = dissatisfaction_evidence.get("correction_claims", [])
        if structured_claims:
            for claim in structured_claims:
                if isinstance(claim, dict):
                    if claim.get("attribute") and (claim.get("asserted_value") or claim.get("rejected_value")):
                        corrections.append({
                            "entity_name": claim.get("entity_name"),
                            "entity_id": claim.get("entity_id"),
                            "attribute": claim.get("attribute"),
                            "asserted_value": claim.get("asserted_value"),
                            "rejected_value": claim.get("rejected_value"),
                            "confidence": claim.get("confidence", 0.75),
                            "source": "structured_claim"
                        })
        
        # Path 2: Feedback text that needs parsing
        feedback_text = dissatisfaction_evidence.get("feedback_text") or \
                       dissatisfaction_evidence.get("text") or \
                       dissatisfaction_evidence.get("user_feedback", "")
        
        if feedback_text and len(corrections) == 0:
            log_step_info(logger, "PARSE_FEEDBACK_TEXT", "Parsing feedback text for corrections: %s", feedback_text[:100])
            extractor = CorrectionExtractor()
            claim = extractor.extract_claim(
                feedback_text=feedback_text,
                original_response=response_text,
                original_query=query_text
            )
            if claim:
                corrections.append({
                    "entity_name": claim.entity_name,
                    "entity_id": claim.entity_id,
                    "attribute": claim.attribute,
                    "asserted_value": claim.asserted_value,
                    "rejected_value": claim.rejected_value,
                    "confidence": claim.confidence,
                    "source": "parsed_text"
                })
    
    return corrections


def resolve_entity_id(
    entity_name: Optional[str],
    query_text: str = ""
) -> Optional[str]:
    """
    Resolve fund name to entity ID (ISIN/dedup_key) using fund matcher.
    
    Args:
        entity_name: Human-readable fund or entity name
        query_text: Context query for disambiguation
    
    Returns:
        Entity ID (ISIN or dedup_key) if found, else None
    """
    if not entity_name:
        return None
    
    try:
        matcher = get_fund_name_matcher()
        result = matcher.match(
            user_input=entity_name,
            user_context=query_text
        )
        if result and result.resolved_id:
            log_step_info(logger, "RESOLVE_ENTITY", "Resolved entity '%s' → %s (confidence=%.2f)",
                       entity_name, result.resolved_id, result.confidence)
            return result.resolved_id
    except Exception as exc:
        log_step_debug(logger, "RESOLVE_ENTITY_NOTICE", "Entity resolution error for '%s': %s", entity_name, exc)
    
    return None


def create_patch_from_correction(
    correction: Dict[str, Any],
    response_id: str,
    db: Optional[Session] = None
) -> Optional[str]:
    """
    Create a correction patch in the shadow layer from a correction claim.
    
    Args:
        correction: Correction dict with entity_id, attribute, values, confidence
        response_id: Source response ID for provenance
        db: Database session for entity resolution (optional)
    
    Returns:
        Patch ID if successful, else None
    """
    # Resolve entity ID if not already resolved
    entity_id = correction.get("entity_id")
    if not entity_id:
        entity_id = resolve_entity_id(
            correction.get("entity_name"),
            ""  # TODO: could pass original query for context
        )
    
    if not entity_id:
        log_step_warning(logger, "RESOLVE_ENTITY_FAILED", "Could not resolve entity ID for correction: %s", correction)
        return None
    
    attribute = correction.get("attribute")
    if not attribute:
        log_step_warning(logger, "CREATE_PATCH_NO_ATTR", "Correction has no attribute; skipping")
        return None
    
    # Asserted value takes priority; if not present, reject_value indicates what's wrong
    corrected_value = correction.get("asserted_value") or correction.get("rejected_value")
    if not corrected_value:
        log_step_warning(logger, "CREATE_PATCH_NO_VAL", "Correction has neither asserted nor rejected value")
        return None
    
    # Canonical value is the rejected/original value
    canonical_value = correction.get("rejected_value") or "<unknown>"
    
    try:
        patch_layer = get_correction_patch_layer()
        patch_id = patch_layer.add_correction(
            entity_id=entity_id,
            attribute=attribute,
            canonical_value=canonical_value,
            corrected_value=corrected_value,
            confidence=correction.get("confidence", 0.70),
            provenance={
                "source": "unified_feedback_loop",
                "response_id": response_id,
                "extraction_method": correction.get("source", "unknown"),
                "entity_name": correction.get("entity_name")
            },
            approved=False
        )
        
        log_step_info(
            logger,
            "CREATE_PATCH",
            "Created correction patch %s: %s.%s %s → %s (confidence=%.2f)",
            patch_id, entity_id, attribute, canonical_value, corrected_value,
            correction.get("confidence", 0.70)
        )
        return patch_id
    
    except Exception as exc:
        log_step_error(logger, "CREATE_PATCH_ERROR", "Failed to create patch for correction %s: %s", correction, exc)
        return None


def process_unified_record_for_repair(
    response_id: str,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Main entry point: Process a unified evaluation record and extract corrections.
    
    This is called automatically after the feedback loop completes if repair=true.
    
    Args:
        response_id: Response ID of the unified evaluation record to process
        db: Database session (optional; creates one if not provided)
    
    Returns:
        Dict with processing results:
        {
            "success": bool,
            "patches_created": int,
            "patches": [patch_id, ...],
            "errors": [error_msg, ...],
            "record_id": response_id
        }
    """
    result = {
        "success": False,
        "patches_created": 0,
        "patches": [],
        "errors": [],
        "record_id": response_id
    }
    
    log_step_info(logger, "REPAIR_SERVICE_START", "Processing unified record for response_id=%s", response_id)
    
    local_db = db or SessionLocal()
    try:
        # 1. Fetch the unified evaluation record
        log_step_debug(logger, "FETCH_RECORD", "Fetching unified evaluation record for response_id=%s", response_id)
        record = local_db.query(UnifiedEvaluationRecord)\
            .filter(UnifiedEvaluationRecord.response_id == response_id)\
            .first()
        
        if not record:
            error_msg = f"Unified record not found for response_id={response_id}"
            result["errors"].append(error_msg)
            log_step_warning(logger, "FETCH_RECORD_NOT_FOUND", "%s", error_msg)
            return result
        
        log_step_info(logger, "RECORD_FOUND", "Unified record found: entry_route=%s, root_cause=%s, repair=%s, repair_target=%s",
                      record.entry_route, record.root_cause, record.repair, record.repair_target)
        
        # 2. Check if repair is needed
        if not record.repair:
            log_step_info(logger, "REPAIR_SKIPPED", "Record does not require repair; skipping")
            result["success"] = True
            return result
        
        log_step_info(logger, "REPAIR_PROCESSING", "Processing repair for response_id=%s", response_id)
        
        # 3. Fetch query evidence for context
        query_text = ""
        response_text = ""
        try:
            evidence = local_db.query(QueryEvidence)\
                .filter(QueryEvidence.response_id == response_id)\
                .first()
            if evidence:
                query_text = evidence.query_text or ""
                response_text = evidence.assembled_context_json or "" if evidence.assembled_context_json else ""
                log_step_debug(logger, "FETCH_EVIDENCE", "Query evidence found (query_len=%d)", len(query_text))
        except Exception as exc:
            log_step_debug(logger, "FETCH_EVIDENCE_NOTICE", "Could not fetch query evidence for context: %s", exc)
        
        # 4. Extract corrections from dissatisfaction evidence
        log_step_info(logger, "CORRECTION_EXTRACTION", "Extracting corrections from dissatisfaction evidence...")
        corrections = extract_corrections_from_evidence(
            dissatisfaction_evidence=record.dissatisfaction_evidence_json,
            query_text=query_text,
            response_text=str(response_text) if response_text else ""
        )
        
        if not corrections:
            log_step_info(logger, "NO_CORRECTIONS", "No corrections extracted from record %s", response_id)
            result["success"] = True
            return result
        
        log_step_info(logger, "CORRECTIONS_EXTRACTED", "Extracted %d correction(s) for response_id=%s", len(corrections), response_id)
        for idx, corr in enumerate(corrections, 1):
            log_step_debug(logger, "CORRECTION_DETAIL", "[%d] %s.%s: %s → %s (conf=%.2f)",
                       idx,
                       corr.get("entity_id", "unknown"),
                       corr.get("attribute", "unknown"),
                       corr.get("rejected_value", "?"),
                       corr.get("asserted_value", "?"),
                       corr.get("confidence", 0))
        
        # 5. Create patches for each correction
        log_step_info(logger, "PATCH_CREATION", "Creating patches from %d correction(s)...", len(corrections))
        for correction in corrections:
            try:
                patch_id = create_patch_from_correction(
                    correction=correction,
                    response_id=response_id,
                    db=local_db
                )
                if patch_id:
                    result["patches"].append(patch_id)
                    result["patches_created"] += 1
                    log_step_info(logger, "PATCH_CREATED", "Patch created: %s", patch_id)
                else:
                    error_msg = f"Failed to create patch for correction: {correction}"
                    result["errors"].append(error_msg)
                    log_step_warning(logger, "PATCH_FAILED", "%s", error_msg)
            except Exception as exc:
                error_msg = f"Exception creating patch: {exc}"
                result["errors"].append(error_msg)
                log_step_error(logger, "PATCH_EXCEPTION", "%s", error_msg)
        
        result["success"] = True
        log_step_info(logger, "REPAIR_SERVICE_COMPLETE", "Repair service complete for %s (patches_created=%d)", response_id, result["patches_created"])
        return result
    
    except Exception as exc:
        error_msg = f"Repair processing failed: {exc}"
        result["errors"].append(error_msg)
        log_step_error(logger, "REPAIR_SERVICE_ERROR", "%s", error_msg)
        return result
    
    finally:
        if db is None:
            local_db.close()


def process_unified_record_for_repair_sync(
    response_id: str,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """Synchronous wrapper for process_unified_record_for_repair.

    Use this when calling from sync contexts (e.g., background tasks in FastAPI).

    Args:
        response_id (str): Unique identifier of the response.
        db (Optional[Session]): Database session instance.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    return process_unified_record_for_repair(response_id, db)
