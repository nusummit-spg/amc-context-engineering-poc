# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
amc_repair.conflict_resolver
=============================
Detects and resolves conflicting patches using precedence rules (GAP 1).
Implements versioning and patch lineage tracking for regulatory compliance.
"""

import logging
from dataclasses import dataclass
from typing import Any, List, Optional

logger = logging.getLogger("amc_repair.conflict_resolver")


@dataclass
class ConflictReport:
    """Details of a patch conflict."""
    conflict_type: str  # "attribute_collision", "value_divergence", "cascade_conflict"
    existing_patches: List[dict]
    new_patch: dict
    resolution_strategy: str  # "auto_supersede", "escalate_to_human", "confidence_based_supersede"
    confidence_delta: float
    recommended_action: str  # Human-readable explanation


class PatchConflictResolver:
    """Handles conflicting patches using version vectors and precedence rules."""
    
    CONFIDENCE_AUTO_RESOLVE_THRESHOLD = 0.15  # Auto-resolve if delta >= 0.15
    CONFIDENCE_HUMAN_ESCALATION_THRESHOLD = 0.10  # Escalate if delta < 0.10
    
    async def detect_conflict(
        self, 
        patch_layer: Any,
        new_patch: dict
    ) -> Optional[ConflictReport]:
        """Check if new patch conflicts with existing patches.

        Returns ConflictReport if conflict detected, else None.

        Args:
            patch_layer (Any): The patch layer.
            new_patch (dict): The new patch.

        Returns:
            Optional[ConflictReport]: Matching object or record if found, None otherwise.
        """
        entity_id = new_patch.get("entity_id")
        attribute = new_patch.get("attribute")
        
        # Query existing patches for this entity+attribute
        existing = await self._get_existing_patches(patch_layer, entity_id, attribute)
        
        if not existing:
            return None  # No conflict
        
        # Calculate confidence delta
        new_conf = float(new_patch.get("confidence", 1.0))
        existing_conf = max([float(p.get("confidence", 0.0)) for p in existing])
        confidence_delta = abs(new_conf - existing_conf)
        
        # Determine resolution strategy
        strategy = self._determine_strategy(existing, new_patch, confidence_delta)
        
        return ConflictReport(
            conflict_type="attribute_collision",
            existing_patches=existing,
            new_patch=new_patch,
            resolution_strategy=strategy,
            confidence_delta=confidence_delta,
            recommended_action=self._get_recommendation(strategy, existing, new_patch)
        )
    
    def _determine_strategy(
        self, 
        existing: List[dict], 
        new: dict, 
        conf_delta: float
    ) -> str:
        """Apply precedence rules to determine conflict resolution strategy.

        Precedence:
        1. Regulatory source beats user feedback
        2. Higher confidence wins if delta >= 0.15
        3. Escalate to human if delta < 0.10
        4. Most recent timestamp breaks ties

        Args:
            existing (List[dict]): The existing.
            new (dict): The new.
            conf_delta (float): The conf delta.

        Returns:
            str: Resulting str instance.
        """
        new_source = new.get("source_type", "user_feedback")
        existing_source = existing[0].get("source_type", "user_feedback")
        
        # Rule 1: Regulatory > User feedback
        if new_source == "regulatory" and existing_source == "user_feedback":
            return "auto_supersede"
        if new_source == "user_feedback" and existing_source == "regulatory":
            return "reject_new"
        
        # Rule 2: High confidence delta → confidence-based supersede
        if conf_delta >= self.CONFIDENCE_AUTO_RESOLVE_THRESHOLD:
            new_conf = float(new.get("confidence", 0.0))
            existing_conf = float(existing[0].get("confidence", 0.0))
            if new_conf > existing_conf:
                return "confidence_based_supersede"
            else:
                return "reject_new"
        
        # Rule 3: Low confidence delta → human escalation
        if conf_delta < self.CONFIDENCE_HUMAN_ESCALATION_THRESHOLD:
            return "escalate_to_human"
        
        # Rule 4: Medium delta → newer timestamp wins
        return "timestamp_based_supersede"
    
    def _get_recommendation(
        self, 
        strategy: str, 
        existing: List[dict], 
        new: dict
    ) -> str:
        """Generate human-readable recommendation.

        Args:
            strategy (str): The strategy.
            existing (List[dict]): The existing.
            new (dict): The new.

        Returns:
            str: Resulting str instance.
        """
        if strategy == "auto_supersede":
            return f"Automatically supersede existing patch (regulatory source override)"
        elif strategy == "confidence_based_supersede":
            return (
                f"Automatically supersede existing patch "
                f"(confidence {new.get('confidence'):.2f} > {existing[0].get('confidence'):.2f})"
            )
        elif strategy == "escalate_to_human":
            delta = abs(float(new.get('confidence', 0)) - float(existing[0].get('confidence', 0)))
            return (
                f"Escalate to human review "
                f"(confidence delta {delta:.2f} < {self.CONFIDENCE_HUMAN_ESCALATION_THRESHOLD})"
            )
        elif strategy == "reject_new":
            return f"Reject new patch (existing has higher authority/confidence)"
        elif strategy == "timestamp_based_supersede":
            return f"Supersede based on recency (newer patch preferred)"
        return "Unknown resolution strategy"
    
    async def _get_existing_patches(
        self, 
        patch_layer: Any, 
        entity_id: str, 
        attribute: str
    ) -> List[dict]:
        """Query patch layer for existing patches.

        Args:
            patch_layer (Any): The patch layer.
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.

        Returns:
            List[dict]: List of resulting items or records.
        """
        patch = patch_layer.get_correction(entity_id, attribute)
        if patch:
            return [{
                "entity_id": patch.entity_id,
                "attribute": patch.attribute,
                "canonical_value": patch.canonical_value,
                "corrected_value": patch.corrected_value,
                "confidence": patch.confidence,
                "source_type": getattr(patch, "source_type", "user_feedback"),
                "created_at": patch.created_at,
                "patch_id": patch.patch_id,
                "version": getattr(patch, "version", 1),
            }]
        return []
    
    async def resolve_conflict(
        self,
        patch_layer: Any,
        conflict: ConflictReport
    ) -> dict:
        """Execute automatic conflict resolution.

        Returns resolution report dict.

        Args:
            patch_layer (Any): The patch layer.
            conflict (ConflictReport): The conflict.

        Returns:
            dict: Dictionary containing result data or status.
        """
        strategy = conflict.resolution_strategy
        
        if strategy == "escalate_to_human":
            logger.warning(
                "🚨 Conflict requires human review: %s.%s (confidence delta %.2f < 0.10)",
                conflict.new_patch.get("entity_id"),
                conflict.new_patch.get("attribute"),
                conflict.confidence_delta
            )
            return {
                "resolution": "pending_human_review",
                "conflict_id": f"conflict_{conflict.new_patch.get('entity_id')}_{conflict.new_patch.get('attribute')}",
                "escalated": True
            }
        
        if strategy in ["auto_supersede", "confidence_based_supersede", "timestamp_based_supersede"]:
            # Supersede existing patch
            existing_patch = conflict.existing_patches[0]
            new_patch = conflict.new_patch
            
            # Update version and lineage
            new_version = existing_patch.get("version", 1) + 1
            new_patch["version"] = new_version
            new_patch["supersedes_patch_id"] = existing_patch.get("patch_id")
            new_patch["conflict_resolution_reason"] = conflict.recommended_action
            
            logger.info(
                "✅ Auto-resolved conflict: %s.%s via %s (version %d → %d)",
                new_patch.get("entity_id"),
                new_patch.get("attribute"),
                strategy,
                existing_patch.get("version", 1),
                new_version
            )
            
            return {
                "resolution": "auto_resolved",
                "strategy": strategy,
                "superseded_patch_id": existing_patch.get("patch_id"),
                "new_version": new_version
            }
        
        # Reject new patch
        logger.info(
            "❌ Rejected new patch for %s.%s (existing has higher authority)",
            conflict.new_patch.get("entity_id"),
            conflict.new_patch.get("attribute")
        )
        return {
            "resolution": "rejected",
            "reason": conflict.recommended_action
        }


# Singleton instance
_global_conflict_resolver: Optional[PatchConflictResolver] = None


def get_conflict_resolver() -> PatchConflictResolver:
    """Singleton accessor for PatchConflictResolver.

    Returns:
        PatchConflictResolver: Resulting PatchConflictResolver instance.
    """
    global _global_conflict_resolver
    if _global_conflict_resolver is None:
        _global_conflict_resolver = PatchConflictResolver()
    return _global_conflict_resolver
