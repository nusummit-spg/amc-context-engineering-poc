# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
patch_generator.py
==================
Generates structured Neo4j graph patch instructions from feedback verdicts.
Implements Task 1.2.2 of the Chief Architect Implementation Plan.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from app.schemas.review_queue import Verdict

logger = logging.getLogger("app.evaluation.patch_generator")


class PatchGenerator:
    """Converts feedback decisions and reviewer notes into formal knowledge graph patches."""

    async def generate_patch(
        self,
        feedback_id: str,
        response_id: str,
        verdict: Verdict,
        query: str,
        llm_answer: str,
        retrieved_context: str = "",
        reviewer_id: str = "compliance_lead",
        reviewer_notes: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Generate knowledge graph patch dictionary from verdict.
        Returns None if no patch is required (e.g. for confirmed answers).
        """
        if verdict == Verdict.CONFIRMED:
            return None

        if verdict == Verdict.PARTIALLY_CORRECT:
            return {
                "feedback_id": feedback_id,
                "response_id": response_id,
                "patch_type": "manual_review",
                "status": "pending_manual",
                "priority": "medium",
                "rationale": reviewer_notes,
                "approved_by": reviewer_id,
            }

        if verdict == Verdict.AMBIGUOUS:
            return {
                "feedback_id": feedback_id,
                "response_id": response_id,
                "patch_type": "ambiguous",
                "status": "pending_hitl",
                "priority": "high",
                "rationale": "Ambiguous claim; requires senior compliance decision",
                "approved_by": reviewer_id,
            }

        # Verdict.NEEDS_CORRECTION
        return self._generate_correction_patch(
            feedback_id=feedback_id,
            response_id=response_id,
            query=query,
            llm_answer=llm_answer,
            reviewer_id=reviewer_id,
            reviewer_notes=reviewer_notes,
        )

    def _generate_correction_patch(
        self,
        feedback_id: str,
        response_id: str,
        query: str,
        llm_answer: str,
        reviewer_id: str,
        reviewer_notes: str,
    ) -> Dict[str, Any]:
        """Classify error pattern and format Cypher update operation."""
        notes_lower = reviewer_notes.lower()
        ans_lower = llm_answer.lower()

        # Check for numeric correction
        if any(w in notes_lower for w in ["%", "crore", "lakh", "number", "value", "aum", "ratio"]):
            # Extract target entity from query or answer
            target_entity = self._extract_entity_name(query, llm_answer)
            corrected_val = self._extract_corrected_value(reviewer_notes)
            return {
                "feedback_id": feedback_id,
                "response_id": response_id,
                "patch_type": "property_update",
                "error_type": "numeric_hallucination",
                "target_entity": target_entity,
                "operation": {"corrected_value": corrected_val},
                "rationale": reviewer_notes,
                "approved_by": reviewer_id,
                "status": "pending_deployment",
                "priority": "high",
            }

        # Check for supersession / relationship error
        if any(w in notes_lower for w in ["superseded", "amended", "replaced", "link", "relationship"]):
            return {
                "feedback_id": feedback_id,
                "response_id": response_id,
                "patch_type": "relationship_correction",
                "error_type": "incorrect_or_missing_link",
                "rationale": reviewer_notes,
                "approved_by": reviewer_id,
                "status": "pending_deployment",
                "priority": "high",
            }

        # General entity property patch
        return {
            "feedback_id": feedback_id,
            "response_id": response_id,
            "patch_type": "entity_update",
            "error_type": "content_correction",
            "target_entity": self._extract_entity_name(query, llm_answer),
            "rationale": reviewer_notes,
            "approved_by": reviewer_id,
            "status": "pending_deployment",
            "priority": "medium",
        }

    def _extract_corrected_value(self, notes: str) -> str:
        """Extract explicit numeric or phrase replacement from reviewer commentary."""
        match = re.search(
            r"(?:should be|correct value is|is actually|must be)\s+(.+?)(?:\s+as per|\s+under|\s+according|[\;\n]|\.\s*$)",
            notes,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return notes.strip()



    def _extract_entity_name(self, query: str, answer: str) -> str:
        """Infer target entity name."""
        tokens = re.findall(r"\b[A-Z][a-zA-Z0-9_-]+\b", query)
        if tokens:
            return tokens[0]
        return "UnknownEntity"
