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
from typing import Any, Dict, List, Optional

from app.monitoring.patch_metrics import get_patch_metrics  # GAP 2: Metrics

logger = logging.getLogger("app.graph.correction_patch_layer")


@dataclass
class CorrectionPatch:
    """
    Represents a single fact correction patch.
    """
    patch_id: str
    entity_id: str
    attribute: str
    canonical_value: Any
    corrected_value: Any
    confidence: float
    provenance: Dict[str, Any]
    approved: bool
    created_at: str
    expires_at: Optional[str] = None
    
    # NEW FIELDS for conflict resolution (GAP 1)
    version: int = 1  # Monotonic version counter
    supersedes_patch_id: Optional[str] = None  # Tracks patch lineage
    superseded_by_patch_id: Optional[str] = None  # Bidirectional link
    conflict_resolution_reason: Optional[str] = None  # Audit trail for auto-resolution
    source_type: str = "user_feedback"  # "user_feedback" or "regulatory"


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
                                if not self._is_expired(p):
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
                    found_patches.add(patch.patch_id)
                    block = (
                        f"\n[CORRECTION - {patch.attribute}]\n"
                        f"Entity: {patch.entity_id}\n"
                        f"Corrected Value: {patch.corrected_value}\n"
                        f"Original Value: {patch.canonical_value}\n"
                        f"Confidence: {patch.confidence:.2f}\n"
                        f"Approved: {'Yes' if patch.approved else 'Pending governance review'}\n"
                        f"Source: {patch.provenance.get('source', 'User feedback')}\n"
                        f"Created: {patch.created_at}\n"
                        f"\n⚠️ INSTRUCTION: Use corrected value ({patch.corrected_value}) "
                        f"in your response if confidence >= 0.70. Mention that value was recently updated.\n"
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
        """Returns all non-expired patches, optionally filtered by entity_id.

        Args:
            entity_id (Optional[str]): Unique identifier of the entity.

        Returns:
            List[CorrectionPatch]: List of resulting items or records.
        """
        patches = self.get_all_patches()
        if entity_id:
            patches = [p for p in patches if p.entity_id == entity_id.strip()]
        return patches


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
