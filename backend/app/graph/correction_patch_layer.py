# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
correction_patch_layer.py
=========================
Shadow correction layer providing immediate, reversible overrides to canonical facts.
Ensures user feedback corrections are immediately visible in retrieval context (<50ms)
before weekly governance review promotes them to the canonical Neo4j knowledge graph.
Backed by Redis with an in-memory fallback.
"""

import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from app.monitoring.patch_metrics import get_patch_metrics  # GAP 2: Metrics

logger = logging.getLogger("app.graph.correction_patch_layer")


class PatchStatus(str, Enum):
    """
    B01: Authoritative patch lifecycle states.
    
    Normal flow:
    PENDING -> APPROVED -> STAGED -> VERIFIED -> ACTIVE
    
    Terminal states:
    REJECTED - Declined by reviewer
    FAILED - Technical failure during promotion
    ROLLED_BACK - Reverted after deployment
    SUPERSEDED - Replaced by newer version
    """
    # Initial state
    PENDING = "PENDING"              # Created, awaiting approval
    
    # Approval states  
    APPROVED = "APPROVED"            # Human approved, not yet published
    
    # Publication states
    STAGED = "STAGED"                # Queued for publication
    VERIFIED = "VERIFIED"            # Published and verified
    ACTIVE = "ACTIVE"                # Serving in answers (requires VERIFIED + receipt)
    
    # Terminal/failure states
    REJECTED = "REJECTED"            # Declined by reviewer
    FAILED = "FAILED"                # Technical failure
    ROLLED_BACK = "ROLLED_BACK"     # Reverted after deployment
    SUPERSEDED = "SUPERSEDED"        # Replaced by newer version


# B01: Allowed state transitions
ALLOWED_TRANSITIONS = {
    PatchStatus.PENDING: [PatchStatus.APPROVED, PatchStatus.REJECTED],
    PatchStatus.APPROVED: [PatchStatus.STAGED, PatchStatus.REJECTED],
    PatchStatus.STAGED: [PatchStatus.VERIFIED, PatchStatus.FAILED],
    PatchStatus.VERIFIED: [PatchStatus.ACTIVE, PatchStatus.FAILED],
    PatchStatus.ACTIVE: [PatchStatus.ROLLED_BACK, PatchStatus.SUPERSEDED],
    # Terminal states have no valid transitions
    PatchStatus.REJECTED: [],
    PatchStatus.FAILED: [],
    PatchStatus.ROLLED_BACK: [],
    PatchStatus.SUPERSEDED: [],
}


class StateTransitionError(Exception):
    """B01: Raised when invalid state transition attempted."""
    pass


@dataclass
class CorrectionPatch:
    """
    Represents a single fact correction patch with B01 state machine.
    
    Normal lifecycle:
    PENDING -> APPROVED -> STAGED -> VERIFIED -> ACTIVE
    
    Terminal states:
    REJECTED, FAILED, ROLLED_BACK, SUPERSEDED
    """
    patch_id: str
    entity_id: str
    attribute: str
    canonical_value: Any
    corrected_value: Any
    confidence: float
    provenance: Dict[str, Any]
    
    # B01: State machine (replaces simple approved boolean)
    status: PatchStatus = PatchStatus.PENDING
    
    # B01: Backward compatibility - computed from status
    approved: bool = False  # Computed property
    
    # B01: Timestamps for state transitions
    approved_at: Optional[str] = None
    staged_at: Optional[str] = None
    verified_at: Optional[str] = None
    activated_at: Optional[str] = None
    
    # B01: Publication receipts
    publication_receipt: Optional[Dict[str, Any]] = None
    active_dataset_version: Optional[str] = None
    active_corpus_version: Optional[str] = None
    
    # Versioning fields for conflict resolution
    version: int = 1  # Monotonic version counter
    supersedes_patch_id: Optional[str] = None  # Tracks patch lineage
    superseded_by_patch_id: Optional[str] = None  # Bidirectional link
    conflict_resolution_reason: Optional[str] = None  # Audit trail for auto-resolution
    source_type: str = "user_feedback"  # "user_feedback" or "regulatory"
    
    created_at: str = ""
    expires_at: Optional[str] = None
    
    def __post_init__(self):
        """Set created_at if not provided and sync approved from status."""
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat() + "Z"
        # Sync approved from status for backward compatibility
        self.approved = self.status in [
            PatchStatus.APPROVED,
            PatchStatus.STAGED,
            PatchStatus.VERIFIED,
            PatchStatus.ACTIVE
        ]
    
    def can_serve(self) -> bool:
        """B01: Check if patch can serve in answers.
        
        Only ACTIVE patches with verified publication can serve.
        """
        return (
            self.status == PatchStatus.ACTIVE and
            self.publication_receipt is not None and
            self.verified_at is not None
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "patch_id": self.patch_id,
            "entity_id": self.entity_id,
            "attribute": self.attribute,
            "canonical_value": self.canonical_value,
            "corrected_value": self.corrected_value,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "status": self.status.value if hasattr(self.status, 'value') else str(self.status),
            "approved": self.approved,
            "approved_at": self.approved_at,
            "staged_at": self.staged_at,
            "verified_at": self.verified_at,
            "activated_at": self.activated_at,
            "publication_receipt": self.publication_receipt,
            "active_dataset_version": self.active_dataset_version,
            "active_corpus_version": self.active_corpus_version,
            "version": self.version,
            "supersedes_patch_id": self.supersedes_patch_id,
            "superseded_by_patch_id": self.superseded_by_patch_id,
            "conflict_resolution_reason": self.conflict_resolution_reason,
            "source_type": self.source_type,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class CorrectionPatchLayer:
    """
    Shadow correction layer storing temporary and approved fact corrections.
    """
    DEFAULT_TTL_DAYS = 7

    CHECKABLE_ATTRIBUTES = [
        "TER", "NAV", "AUM", "5yr_return", "3yr_return", "1yr_return",
        "expense_ratio", "exit_load", "minimum_investment", "sharpe_ratio",
        "alpha", "beta", "risk_grade", "fund_manager", "benchmark"
    ]

    def __init__(self, redis_client: Any = None, ttl_days: int = DEFAULT_TTL_DAYS):
        """Initialize a new instance of CorrectionPatchLayer.

        Args:
            redis_client (Any): The redis client.
            ttl_days (int): Collection or list of ttl days.
        """
        self.redis = redis_client
        self.ttl_days = ttl_days
        self.ttl_seconds = ttl_days * 86400
        self._lock = threading.Lock()
        # In-memory storage fallback when Redis is absent
        self._mem_store: Dict[str, Dict[str, Any]] = {}
    
    def _key(self, patch_id: str) -> str:
        """Key.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            str: Resulting str instance.
        """
        return f"patch:{patch_id}"

    def _make_key(self, entity_id: str, attribute: str) -> str:
        """Make key.

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.

        Returns:
            str: Resulting str instance.
        """
        return f"patch:{entity_id.strip()}:{attribute.strip()}"

    def _is_expired(self, patch: CorrectionPatch) -> bool:
        """Check whether expired.

        Args:
            patch (CorrectionPatch): The patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        if patch.approved or not patch.expires_at:
            return False
        try:
            exp_dt = datetime.fromisoformat(patch.expires_at.replace("Z", ""))
            return datetime.utcnow() > exp_dt
        except Exception:
            return False

    def add_correction(
        self,
        entity_id: str,
        attribute: str,
        canonical_value: Any,
        corrected_value: Any,
        confidence: float,
        provenance: Optional[Dict[str, Any]] = None,
        approved: bool = False,
        source_type: str = "user_feedback",  # NEW: For conflict resolution
    ) -> dict:  # Changed return type from str to dict (GAP 1)
        """Add or update a correction patch with conflict detection.

        Returns dict with keys: patch_id, conflict_detected, conflict_report, resolution, status

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.
            canonical_value (Any): The canonical value.
            corrected_value (Any): The corrected value.
            confidence (float): The confidence.
            provenance (Optional[Dict[str, Any]]): The provenance.
            approved (bool): The approved.
            source_type (str): The source type.

        Returns:
            dict: Dictionary containing result data or status.
        """
        # Step 0: Deduplication check - if identical patch already exists, reuse it
        existing_patch = self.get_correction(entity_id, attribute)
        if existing_patch and existing_patch.corrected_value == corrected_value:
            logger.info(
                "Exact duplicate patch found for %s.%s (%s), reusing existing patch %s",
                entity_id, attribute, corrected_value, existing_patch.patch_id
            )
            return {
                "patch_id": existing_patch.patch_id,
                "conflict_detected": False,
                "conflict_report": None,
                "resolution": None,
                "status": "reused"
            }

        # Step 1: Detect conflicts (GAP 1)
        try:
            from amc_repair.conflict_resolver import get_conflict_resolver
            conflict_resolver = get_conflict_resolver()
            
            new_patch_dict = {
                "entity_id": entity_id,
                "attribute": attribute,
                "canonical_value": canonical_value,
                "corrected_value": corrected_value,
                "confidence": confidence,
                "source_type": source_type,
                "provenance": provenance or {},
            }
            
            import inspect
            raw_conflict = conflict_resolver.detect_conflict(self, new_patch_dict)
            if inspect.iscoroutine(raw_conflict):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    raw_conflict.close()
                    conflict = None
                else:
                    conflict = asyncio.run(raw_conflict)
            else:
                conflict = raw_conflict
            
            # Step 2: Resolve conflict (if detected)
            resolution = None
            version = 1
            supersedes_patch_id = None
            conflict_resolution_reason = None
            
            if conflict:
                import asyncio
                resolution = asyncio.run(conflict_resolver.resolve_conflict(self, conflict))
                
                if resolution["resolution"] == "pending_human_review":
                    logger.warning("❓ Conflict escalated to human review: %s", resolution["conflict_id"])
                    return {
                        "patch_id": None,
                        "conflict_detected": True,
                        "conflict_report": conflict,
                        "resolution": resolution,
                        "status": "pending_human_review"
                    }
                
                if resolution["resolution"] == "rejected":
                    logger.info("❌ New patch rejected due to conflict: %s", resolution["reason"])
                    return {
                        "patch_id": None,
                        "conflict_detected": True,
                        "conflict_report": conflict,
                        "resolution": resolution,
                        "status": "rejected"
                    }
                
                # Auto-resolved: update versioning
                version = resolution.get("new_version", 1)
                supersedes_patch_id = resolution.get("superseded_patch_id")
                conflict_resolution_reason = conflict.recommended_action
                
        except Exception as e:
            logger.debug("Conflict detection disabled or error: %s", e)
            conflict = None
            resolution = None
        
        # Step 3: Create patch with versioning fields
        patch_id = f"patch_{uuid.uuid4().hex[:12]}"
        patch_key = self._make_key(entity_id, attribute)

        now = datetime.utcnow()
        expires_at = None if approved else (now + timedelta(days=self.ttl_days)).isoformat() + "Z"

        patch = CorrectionPatch(
            patch_id=patch_id,
            entity_id=entity_id.strip(),
            attribute=attribute.strip(),
            canonical_value=canonical_value,
            corrected_value=corrected_value,
            confidence=round(float(confidence), 3),
            provenance=provenance or {},
            approved=approved,
            created_at=now.isoformat() + "Z",
            expires_at=expires_at,
            version=version,  # NEW
            supersedes_patch_id=supersedes_patch_id,  # NEW
            superseded_by_patch_id=None,  # NEW
            conflict_resolution_reason=conflict_resolution_reason,  # NEW
            source_type=source_type,  # NEW
        )

        patch_dict = asdict(patch)
        patch_json = json.dumps(patch_dict)

        written_to_redis = False
        if self.redis is not None:
            try:
                self.redis.set(patch_key, patch_json)
                if not approved:
                    self.redis.expire(patch_key, self.ttl_seconds)
                written_to_redis = True
                logger.info("✅ Wrote patch %s v%d to Redis key %s (approved=%s)", 
                           patch_id, version, patch_key, approved)
            except Exception as exc:
                logger.warning("Redis set failed, falling back to memory: %s", exc)

        with self._lock:
            self._mem_store[patch_key] = patch_dict

        # GAP 2: Track patch confidence
        metrics = get_patch_metrics()
        metrics.record_patch_confidence(patch.confidence)
        
        # GAP 2: Track conflicts (if conflict resolver integrated)
        if conflict:
            metrics.record_patch_conflict(resolution["resolution"])

        return {
            "patch_id": patch_id,
            "conflict_detected": conflict is not None,
            "conflict_report": conflict,
            "resolution": resolution,
            "status": "created"
        }

    def get_correction(self, entity_id: str, attribute: str) -> Optional[CorrectionPatch]:
        """Retrieve correction.

        Args:
            entity_id (str): Unique identifier of the entity.
            attribute (str): The attribute.

        Returns:
            Optional[CorrectionPatch]: Matching object or record if found, None otherwise.
        """
        patch_key = self._make_key(entity_id, attribute)

        # 1. Try Redis
        if self.redis is not None:
            try:
                patch_json = self.redis.get(patch_key)
                if patch_json:
                    data = json.loads(patch_json)
                    patch = CorrectionPatch(**data)
                    if not self._is_expired(patch):
                        return patch
            except Exception as exc:
                logger.debug("Redis get notice: %s", exc)

        # 2. Fall back to in-memory store
        with self._lock:
            data = self._mem_store.get(patch_key)
            if data:
                patch = CorrectionPatch(**data)
                if not self._is_expired(patch):
                    return patch
                else:
                    del self._mem_store[patch_key]

        return None

    def get_patch_by_id(self, patch_id: str) -> Optional[CorrectionPatch]:
        """Retrieve patch by id.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            Optional[CorrectionPatch]: Matching object or record if found, None otherwise.
        """
        for patch in self.get_all_patches():
            if patch.patch_id == patch_id:
                return patch
        return None

    def get_all_patches(self) -> List[CorrectionPatch]:
        """Retrieve all patches.

        Returns:
            List[CorrectionPatch]: List of resulting items or records.
        """
        patches: List[CorrectionPatch] = []
        seen_keys = set()
        seen_patch_ids = set()

        if self.redis is not None:
            try:
                cursor = 0
                while True:
                    cursor, keys = self.redis.scan(cursor=cursor, match="patch:*", count=100)
                    for k in keys:
                        seen_keys.add(k)
                        val = self.redis.get(k)
                        if val:
                            try:
                                p = CorrectionPatch(**json.loads(val))
                                if not self._is_expired(p) and p.patch_id not in seen_patch_ids:
                                    seen_patch_ids.add(p.patch_id)
                                    patches.append(p)
                            except Exception:
                                pass
                    if cursor == 0:
                        break
            except Exception as exc:
                logger.debug("Redis scan notice: %s", exc)

        with self._lock:
            for k, data in list(self._mem_store.items()):
                if k not in seen_keys:
                    p = CorrectionPatch(**data)
                    if not self._is_expired(p):
                        if p.patch_id not in seen_patch_ids:
                            seen_patch_ids.add(p.patch_id)
                            patches.append(p)
                    else:
                        del self._mem_store[k]

        return patches

    def get_patches_for_entity(self, entity_id: str) -> List[CorrectionPatch]:
        """Retrieve patches for entity.

        Args:
            entity_id (str): Unique identifier of the entity.

        Returns:
            List[CorrectionPatch]: List of resulting items or records.
        """
        all_p = self.get_all_patches()
        return [p for p in all_p if p.entity_id.strip().lower() == entity_id.strip().lower()]

    def get_all_pending(self) -> List[CorrectionPatch]:
        """Retrieve all pending.

        Returns:
            List[CorrectionPatch]: List of resulting items or records.
        """
        return [p for p in self.get_all_patches() if not p.approved]

    def apply_patches_to_context(
        self,
        entities: List[str],
        retrieval_context: str
    ) -> str:
        """Convert apply patches into context.

        Args:
            entities (List[str]): List of entity identifiers or objects.
            retrieval_context (str): The retrieval context.

        Returns:
            str: Resulting str instance.
        """
        if not entities or not retrieval_context:
            return retrieval_context

        correction_blocks = []
        found_patches = set()

        for entity_id in entities:
            if not entity_id:
                continue
            for attribute in self.CHECKABLE_ATTRIBUTES:
                patch = self.get_correction(entity_id, attribute)
                if patch and patch.patch_id not in found_patches:
                    # W18-04 FIX: Use is_serving_eligible instead of patch.approved
                    # This ensures patch is ACTIVE + has verified receipt + not revoked
                    if not is_serving_eligible(patch, tenant="default"):
                        continue
                    found_patches.add(patch.patch_id)
                    block = (
                        f"\n[CORRECTION - {patch.attribute}]\n"
                        f"Entity: {patch.entity_id}\n"
                        f"Corrected Value: {patch.corrected_value}\n"
                        f"Original Value: {patch.canonical_value}\n"
                        f"Confidence: {patch.confidence:.2f}\n"
                        f"Approved: Yes\n"
                        f"Source: {patch.provenance.get('source', 'Governance Review')}\n"
                        f"Created: {patch.created_at}\n"
                    )
                    correction_blocks.append(block)

        if not correction_blocks:
            return retrieval_context

        header = (
            "\n═══════════════════════════════════════════\n"
            "🔧 ACTIVE CORRECTIONS (Priority Override)\n"
            "═══════════════════════════════════════════\n"
        )
        return header + "\n".join(correction_blocks) + "\n\n" + retrieval_context

    def promote_to_permanent(
        self,
        patch_id: str,
        neo4j_session: Any = None
    ) -> bool:
        """Convert promote into permanent.

        Args:
            patch_id (str): Unique identifier of the patch.
            neo4j_session (Any): The neo4j session.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        target_patch = self.get_patch_by_id(patch_id)
        if not target_patch:
            logger.error("Cannot promote: Patch %s not found", patch_id)
            return False

        if target_patch.approved:
            logger.info("Patch %s is already approved and permanent; skipping promotion", patch_id)
            return True

        patch_key = self._make_key(target_patch.entity_id, target_patch.attribute)

        # 1. Update canonical Neo4j graph if session provided
        if neo4j_session is not None:
            try:
                neo4j_session.run(
                    """
                    MATCH (e:Entity)
                    WHERE (e.dedup_key = $entity_id OR e.isin = $entity_id OR e.text = $entity_id)
                    MATCH (e)-[:HAS_FACT]->(f:Fact {attribute: $attribute})
                    SET f.value = $new_value,
                        f.updated_at = datetime(),
                        f.updated_by = 'governance_approval',
                        f.source = $source
                    """,
                    parameters={
                        "entity_id": target_patch.entity_id,
                        "attribute": target_patch.attribute,
                        "new_value": str(target_patch.corrected_value),
                        "source": target_patch.provenance.get("source", "Feedback correction")
                    }
                )
                # Direct property mutation on node (Scheme/Fund)
                neo4j_session.run(
                    f"""
                    MATCH (e) WHERE (e.dedup_key = $entity_id OR e.isin = $entity_id OR e.id = $entity_id OR e.name = $entity_id)
                    SET e.{target_patch.attribute} = $new_value,
                        e.{target_patch.attribute}_updated_at = datetime()
                    """,
                    parameters={
                        "entity_id": target_patch.entity_id,
                        "new_value": str(target_patch.corrected_value)
                    }
                )
                # Cleanup virtual shadow patch overlay now that canonical node is mutated
                neo4j_session.run(
                    """
                    MATCH (p:ShadowPatch {patch_id: $patch_id})
                    DETACH DELETE p
                    """,
                    parameters={"patch_id": patch_id}
                )
                logger.info("Promoted patch %s to canonical Neo4j graph for %s.%s",
                            patch_id, target_patch.entity_id, target_patch.attribute)
            except Exception as exc:
                logger.warning("Neo4j canonical write notice: %s", exc)

        # 2. Update status in stores
        target_patch.approved = True
        target_patch.expires_at = None
        updated_dict = asdict(target_patch)
        updated_json = json.dumps(updated_dict)

        if self.redis is not None:
            try:
                self.redis.set(patch_key, updated_json)
                self.redis.persist(patch_key)
            except Exception as exc:
                logger.debug("Redis persist notice: %s", exc)

        with self._lock:
            self._mem_store[patch_key] = updated_dict
            self._mem_store[patch_id] = updated_dict

        # GAP 2: Track promotion
        try:
            metrics = get_patch_metrics()
            raw_created = target_patch.created_at.replace("Z", "+00:00")
            created_dt = datetime.fromisoformat(raw_created)
            now_dt = datetime.now(timezone.utc)
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            time_to_promote_seconds = max(0.0, (now_dt - created_dt).total_seconds())
            metrics.record_patch_promotion(
                entity_id=target_patch.entity_id,
                attribute=target_patch.attribute,
                time_to_promote_seconds=time_to_promote_seconds
            )
        except Exception as m_exc:
            logger.debug("Metrics promotion recording notice: %s", m_exc)

        logger.info("🎯 Patch %s promoted to permanent (v%d)", patch_id, target_patch.version)
        return True

    def delete_patch(self, patch_id: str) -> bool:
        """Delete patch.

        Args:
            patch_id (str): Unique identifier of the patch.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        target_patch = self.get_patch_by_id(patch_id)
        if not target_patch:
            return False

        patch_key = self._make_key(target_patch.entity_id, target_patch.attribute)
        if self.redis is not None:
            try:
                self.redis.delete(patch_key)
            except Exception as exc:
                logger.debug("Redis delete notice: %s", exc)

        with self._lock:
            self._mem_store.pop(patch_key, None)

        logger.info("Deleted patch %s (%s)", patch_id, patch_key)
        return True

    def clear_all(self) -> None:
        """Clears all patches from memory and Redis (useful for test isolation)."""
        with self._lock:
            self._mem_store.clear()
        if self.redis is not None:
            try:
                for k in self.redis.scan_iter("patch:*"):
                    self.redis.delete(k)
            except Exception:
                pass

    def approve_patch(self, patch_id: str, neo4j_session: Any = None) -> bool:
        """Alias for promote_to_permanent.

        Args:
            patch_id (str): Unique identifier of the patch.
            neo4j_session (Any): The neo4j session.

        Returns:
            bool: True if condition is met or operation succeeded, False otherwise.
        """
        return self.promote_to_permanent(patch_id, neo4j_session=neo4j_session)

    def get_active_patches(self, entity_id: Optional[str] = None) -> List[CorrectionPatch]:
        """Returns all non-expired, approved patches, optionally filtered by entity_id.

        Args:
            entity_id (Optional[str]): Unique identifier of the entity.

        Returns:
            List[CorrectionPatch]: List of resulting items or records.
        """
        patches = [p for p in self.get_all_patches() if p.approved]
        if entity_id:
            patches = [p for p in patches if p.entity_id == entity_id.strip()]
        return patches

    # B01: State machine methods
    async def transition_patch(
        self,
        patch_id: str,
        new_status: PatchStatus,
        actor: Optional[str] = None,
        receipt: Optional[Dict[str, Any]] = None
    ) -> bool:
        """B01: Transition patch to new status with validation.
        
        Validates that the transition is allowed and updates timestamps.
        
        Args:
            patch_id: Patch ID to transition
            new_status: Target status
            actor: Username/identity performing transition
            receipt: Publication receipt (for VERIFIED/ACTIVE transitions)
        
        Returns:
            True if transition successful
            
        Raises:
            StateTransitionError: If transition not allowed
        """
        target_patch = self.get_patch_by_id(patch_id)
        if not target_patch:
            logger.error("PATCH_TRANSITION_MISS: Patch %s not found", patch_id)
            return False
        
        # B01: Validate transition
        current_status = target_patch.status if hasattr(target_patch, 'status') else PatchStatus.APPROVED
        if isinstance(current_status, str):
            current_status = PatchStatus(current_status)
        
        allowed = ALLOWED_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise StateTransitionError(
                f"Invalid transition from {current_status} to {new_status}. "
                f"Allowed transitions: {allowed}"
            )
        
        # Update status
        old_status = current_status
        target_patch.status = new_status
        
        # B01: Update transition timestamps
        now = datetime.now(timezone.utc).isoformat() + "Z"
        if new_status == PatchStatus.APPROVED:
            target_patch.approved_at = now
            target_patch.approved_by = actor
        elif new_status == PatchStatus.STAGED:
            target_patch.staged_at = now
        elif new_status == PatchStatus.VERIFIED:
            target_patch.verified_at = now
            if receipt:
                target_patch.publication_receipt = receipt
        elif new_status == PatchStatus.ACTIVE:
            target_patch.activated_at = now
            if receipt:
                target_patch.publication_receipt = receipt
        
        # Update store
        await self._update_patch(patch_id, target_patch)
        
        logger.info(
            "PATCH_TRANSITION: Patch %s: %s → %s (actor=%s)",
            patch_id, old_status, new_status, actor or "system"
        )
        return True
    
    async def approve_patch(self, patch_id: str, actor: Optional[str] = None) -> bool:
        """B01: Approve patch (PENDING → APPROVED).
        
        Args:
            patch_id: Unique identifier of the patch.
            actor: Username performing approval

        Returns:
            bool: True if transition successful
        """
        try:
            return await self.transition_patch(patch_id, PatchStatus.APPROVED, actor=actor)
        except StateTransitionError as e:
            logger.error("PATCH_APPROVE_INVALID: Cannot approve %s: %s", patch_id, e)
            return False
    
    async def reject_patch(self, patch_id: str, actor: Optional[str] = None) -> bool:
        """B01: Reject patch (PENDING/APPROVED → REJECTED).
        
        Args:
            patch_id: Unique identifier of the patch.
            actor: Username performing rejection

        Returns:
            bool: True if transition successful
        """
        try:
            success = await self.transition_patch(patch_id, PatchStatus.REJECTED, actor=actor)
            if success:
                await self.delete_patch(patch_id)
                logger.info("PATCH_REJECTED: Patch %s rejected and removed", patch_id)
            return success
        except StateTransitionError as e:
            logger.error("PATCH_REJECT_INVALID: Cannot reject %s: %s", patch_id, e)
            return False
    
    async def stage_patch(self, patch_id: str, receipt: Optional[Dict[str, Any]] = None) -> bool:
        """B01: Stage patch (APPROVED → STAGED).
        
        Args:
            patch_id: Unique identifier of the patch.
            receipt: Staging receipt (optional)

        Returns:
            bool: True if transition successful
        """
        try:
            return await self.transition_patch(patch_id, PatchStatus.STAGED, receipt=receipt)
        except StateTransitionError as e:
            logger.error("PATCH_STAGE_INVALID: Cannot stage %s: %s", patch_id, e)
            return False
    
    async def verify_patch(self, patch_id: str, receipt: Dict[str, Any]) -> bool:
        """B01: Verify patch (STAGED → VERIFIED).
        
        Args:
            patch_id: Unique identifier of the patch.
            receipt: Verification receipt (required)

        Returns:
            bool: True if transition successful
        """
        try:
            return await self.transition_patch(patch_id, PatchStatus.VERIFIED, receipt=receipt)
        except StateTransitionError as e:
            logger.error("PATCH_VERIFY_INVALID: Cannot verify %s: %s", patch_id, e)
            return False
    
    async def activate_patch(self, patch_id: str, receipt: Dict[str, Any]) -> bool:
        """B01: Activate patch (VERIFIED → ACTIVE).
        
        Args:
            patch_id: Unique identifier of the patch.
            receipt: Activation receipt (required)

        Returns:
            bool: True if transition successful
        """
        try:
            return await self.transition_patch(patch_id, PatchStatus.ACTIVE, receipt=receipt)
        except StateTransitionError as e:
            logger.error("PATCH_ACTIVATE_INVALID: Cannot activate %s: %s", patch_id, e)
            return False
    
    async def rollback_patch(self, patch_id: str, actor: Optional[str] = None) -> bool:
        """B01: Rollback patch (ACTIVE → ROLLED_BACK).
        
        Args:
            patch_id: Unique identifier of the patch.
            actor: Username performing rollback

        Returns:
            bool: True if transition successful
        """
        try:
            return await self.transition_patch(patch_id, PatchStatus.ROLLED_BACK, actor=actor)
        except StateTransitionError as e:
            logger.error("PATCH_ROLLBACK_INVALID: Cannot rollback %s: %s", patch_id, e)
            return False
    
    async def _update_patch(self, patch_id: str, patch: CorrectionPatch) -> None:
        """B01: Update patch in stores.
        
        Args:
            patch_id: Unique identifier of the patch.
            patch: The updated patch object.
        """
        patch_key = self._key(patch_id)
        
        patch_dict = patch.to_dict() if hasattr(patch, 'to_dict') else asdict(patch)
        patch_json = json.dumps(patch_dict)
        
        if self.redis is not None:
            try:
                self.redis.set(patch_key, patch_json)
            except Exception as exc:
                logger.debug("Redis update notice: %s", exc)
        
        with self._lock:
            self._mem_store[patch_key] = patch_dict
            self._mem_store[patch_id] = patch_dict


_global_patch_layer: Optional[CorrectionPatchLayer] = None
_layer_lock = threading.Lock()


def get_correction_patch_layer() -> CorrectionPatchLayer:
    """Retrieve correction patch layer.

    Returns:
        CorrectionPatchLayer: Resulting CorrectionPatchLayer instance.
    """
    global _global_patch_layer
    with _layer_lock:
        if _global_patch_layer is None:
            redis_client = None
            try:
                import redis
                from app.config import get_settings
                settings = get_settings()
                redis_host = getattr(settings, 'redis_host', 'localhost')
                redis_port = getattr(settings, 'redis_port', 6379)
                client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=0,
                    decode_responses=True,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2
                )
                client.ping()
                redis_client = client
                logger.info("Connected to Redis for CorrectionPatchLayer")
            except Exception as exc:
                logger.info("Redis unavailable for CorrectionPatchLayer (%s), running with in-memory fallback", exc)
            _global_patch_layer = CorrectionPatchLayer(redis_client=redis_client)
        return _global_patch_layer


def is_serving_eligible(patch: CorrectionPatch, tenant: str) -> bool:
    """Check if patch is eligible for serving in answers.
    
    B03/W18-04 FIX: Authoritative check using ACTIVE + verified receipt + not revoked.
    Does NOT trust patch.approved or in-memory state.
    
    Args:
        patch: The patch to check
        tenant: Current tenant ID
        
    Returns:
        True if patch can serve in answers
    """
    # Must be ACTIVE status
    if hasattr(patch, 'status'):
        current_status = patch.status if hasattr(patch.status, 'value') else patch.status
        if isinstance(current_status, str):
            current_status = PatchStatus(current_status)
        if current_status != PatchStatus.ACTIVE:
            logger.debug("is_serving_eligible: Patch %s not ACTIVE (status=%s)", 
                        patch.patch_id, current_status)
            return False
    
    # Must have publication receipt
    if patch.publication_receipt is None:
        logger.debug("is_serving_eligible: Patch %s missing publication_receipt", patch.patch_id)
        return False
    
    # Must be tenant-scoped correctly
    if hasattr(patch, 'tenant_id') and patch.tenant_id != tenant:
        logger.debug("is_serving_eligible: Patch %s tenant mismatch (patch.tenant=%s, request.tenant=%s)",
                    patch.patch_id, getattr(patch, 'tenant_id', 'unknown'), tenant)
        return False
    
    # Must not be revoked (no revoked_at field set)
    if hasattr(patch, 'revoked_at') and patch.revoked_at is not None:
        logger.debug("is_serving_eligible: Patch %s has been revoked", patch.patch_id)
        return False
    
    logger.debug("is_serving_eligible: Patch %s is serving eligible", patch.patch_id)
    return True
