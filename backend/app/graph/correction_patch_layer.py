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
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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
        self.redis = redis_client
        self.ttl_days = ttl_days
        self.ttl_seconds = ttl_days * 86400
        self._lock = threading.Lock()
        # In-memory storage fallback when Redis is absent
        self._mem_store: Dict[str, Dict[str, Any]] = {}

    def _make_key(self, entity_id: str, attribute: str) -> str:
        return f"patch:{entity_id.strip()}:{attribute.strip()}"

    def _is_expired(self, patch: CorrectionPatch) -> bool:
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
        approved: bool = False
    ) -> str:
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
            expires_at=expires_at
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
                logger.info("Wrote patch %s to Redis key %s (approved=%s)", patch_id, patch_key, approved)
            except Exception as exc:
                logger.warning("Redis set failed, falling back to memory: %s", exc)

        with self._lock:
            self._mem_store[patch_key] = patch_dict

        return patch_id

    def get_correction(self, entity_id: str, attribute: str) -> Optional[CorrectionPatch]:
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
        for patch in self.get_all_patches():
            if patch.patch_id == patch_id:
                return patch
        return None

    def get_all_patches(self) -> List[CorrectionPatch]:
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

    def get_all_pending(self) -> List[CorrectionPatch]:
        return [p for p in self.get_all_patches() if not p.approved]

    def apply_patches_to_context(
        self,
        entities: List[str],
        retrieval_context: str
    ) -> str:
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
        target_patch = self.get_patch_by_id(patch_id)
        if not target_patch:
            logger.error("Cannot promote: Patch %s not found", patch_id)
            return False

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

        logger.info("Patch %s promoted to permanent", patch_id)
        return True

    def delete_patch(self, patch_id: str) -> bool:
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
        """Alias for promote_to_permanent."""
        return self.promote_to_permanent(patch_id, neo4j_session=neo4j_session)

    def get_active_patches(self, entity_id: Optional[str] = None) -> List[CorrectionPatch]:
        """Returns all non-expired patches, optionally filtered by entity_id."""
        patches = self.get_all_patches()
        if entity_id:
            patches = [p for p in patches if p.entity_id == entity_id.strip()]
        return patches


_global_patch_layer: Optional[CorrectionPatchLayer] = None
_layer_lock = threading.Lock()


def get_correction_patch_layer() -> CorrectionPatchLayer:
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
                client = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True, socket_timeout=1.0)
                client.ping()
                redis_client = client
                logger.info("Connected to Redis for CorrectionPatchLayer")
            except Exception as exc:
                logger.info("Redis unavailable for CorrectionPatchLayer (%s), running with in-memory fallback", exc)
            _global_patch_layer = CorrectionPatchLayer(redis_client=redis_client)
        return _global_patch_layer
