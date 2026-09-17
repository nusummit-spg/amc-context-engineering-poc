I'm a planning agent - I can read and analyze code but not create or modify files. However, I can provide you with the complete markdown content for Tracks 6 and 7 that your team can save as `.md` files.

Let me create comprehensive markdown documents for these tracks:

---

## **TRACK 6: CORRECTION PATCH LAYER - COMPLETE MARKDOWN**

```markdown
# Track 6: Correction Patch Layer (Shadow Graph)
**Implementation Plan & Technical Specification**

## Executive Summary

**Objective:** Implement immediate, reversible correction layer that LLM consults before canonical graph, enabling instant correction visibility while maintaining governance control.

**Priority:** P1  
**Duration:** 6 days (48 work hours)  
**Owner:** Graph/RAG Team  
**Dependencies:** Track 5 (Deterministic Rules Engine)  
**Value:** Instant correction propagation (<50ms), reversible changes, zero production risk

---

## 1. Problem Statement

### Current State:
- User reports "TER is 0.82%, not 0.79%"
- Correction enters governance queue
- Takes 7 days for weekly batch approval
- Meanwhile, next 1000 users still get wrong value (0.79%)
- No mechanism for immediate correction

### Target State (Keerthi's Design):
- Correction added to **Patch Layer** immediately (Redis)
- Next user query hits patch layer FIRST
- LLM sees corrected value (0.82%) in context
- Change is **reversible** (7-day TTL unless approved)
- Weekly governance promotes patch to **canonical graph**

### Real AMC Example:

**Day 1 (Monday):**
- User A queries: "What is TER of Axis Bluechip?"
- Response: "TER is 0.79%" (from stale factsheet v17)
- User A feedback: "Wrong! TER is 0.82% per AMFI latest"
- System adds patch: `{entity: INF846K01DP5, attr: TER, value: 0.82, ttl: 7d}`

**Day 1 (2 minutes later):**
- User B queries: "What is TER of Axis Bluechip?"
- System checks patch layer FIRST → finds patch (TER=0.82)
- Injects into context: "[CORRECTION] TER = 0.82% (confidence=0.85, approved=false)"
- Response: "TER is 0.82%" ✅ (corrected immediately)

**Day 7 (Next Monday):**
- Compliance officer reviews patch in governance UI
- Approves correction
- System writes to canonical Neo4j graph
- Removes TTL from patch (now permanent)

---

## 2. Architecture Design

### Component Diagram:

```
┌─────────────────────────────────────────────────────────────┐
│                   User Query Received                        │
│            "What is the TER of Axis Bluechip Fund?"         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Entity Resolution                               │
│         "Axis Bluechip Fund" → INF846K01DP5 (ISIN)          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│         Hybrid Retrieval (FAISS + Neo4j)                     │
│         Fetches: factsheet chunks + graph facts              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│    ⚡ CHECK CORRECTION PATCH LAYER (NEW)                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  CorrectionPatchLayer.get_correction(                │   │
│  │      entity_id="INF846K01DP5",                       │   │
│  │      attribute="TER"                                 │   │
│  │  )                                                   │   │
│  │                                                      │   │
│  │  Redis Lookup:                                       │   │
│  │    Key: patch:INF846K01DP5:TER                       │   │
│  │    Value: {                                          │   │
│  │      corrected_value: "0.82",                        │   │
│  │      canonical_value: "0.79",                        │   │
│  │      confidence: 0.85,                               │   │
│  │      provenance: {feedback_id: "fb_abc123", ...},   │   │
│  │      approved: false,                                │   │
│  │      created_at: "2026-09-10T14:32:15Z",             │   │
│  │      ttl: 7 days                                     │   │
│  │    }                                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Result: Patch FOUND ✅                                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│      Apply Patches to Retrieval Context                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Original Context (from Neo4j):                      │   │
│  │    "TER: 0.79% (source: factsheet_v17)"             │   │
│  │                                                      │   │
│  │  Patched Context (injected):                         │   │
│  │    "[CORRECTION] TER = 0.82% (confidence=0.85,      │   │
│  │     approved=false, source: AMFI latest)            │   │
│  │                                                      │   │
│  │    Original value for reference: 0.79%              │   │
│  │    (factsheet_v17, may be outdated)"                │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              LLM Generation (Claude)                         │
│         Prompt includes patched context                      │
│         LLM prioritizes [CORRECTION] over original value     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                Response to User                              │
│   "The TER for Axis Bluechip Fund Direct Growth is 0.82%    │
│    as per the latest AMFI data."                             │
│                                                              │
│   ✅ User gets CORRECTED value immediately                   │
└─────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────┐
│           Weekly Governance Review (Day 7)                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Compliance officer sees pending patch in UI:        │   │
│  │                                                      │   │
│  │  Entity: Axis Bluechip Fund (INF846K01DP5)          │   │
│  │  Attribute: TER                                      │   │
│  │  Current Value: 0.79%                                │   │
│  │  Proposed Value: 0.82%                               │   │
│  │  Confidence: 0.85                                    │   │
│  │  Supporting Evidence: 3 feedback records             │   │
│  │                                                      │   │
│  │  Action: [Approve] [Reject] [Defer]                 │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │ Approve clicked
                     ▼
┌─────────────────────────────────────────────────────────────┐
│         Promote Patch to Canonical Graph                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. Write to Neo4j canonical graph:                  │   │
│  │     UPDATE Entity {id: INF846K01DP5}                 │   │
│  │     SET fact.TER = 0.82,                             │   │
│  │         fact.source = "AMFI_v18",                    │   │
│  │         fact.updated_at = now(),                     │   │
│  │         fact.approved_by = "compliance_officer"      │   │
│  │                                                      │   │
│  │  2. Mark patch as approved in Redis:                 │   │
│  │     SET patch:INF846K01DP5:TER.approved = true       │   │
│  │     REMOVE TTL (patch now permanent)                 │   │
│  │                                                      │   │
│  │  3. Trigger reindex (future retrieval uses new value)│   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Implementation Specification

### 3.1 CorrectionPatchLayer Class

**File:** `backend/app/graph/correction_patch_layer.py`

```python
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import redis

logger = logging.getLogger("app.graph.correction_patch_layer")

@dataclass
class CorrectionPatch:
    """
    Represents a single correction patch.
    
    Attributes:
        patch_id: Unique identifier
        entity_id: Canonical entity ID (e.g., ISIN)
        attribute: Attribute being corrected (e.g., "TER")
        canonical_value: Current value in canonical graph
        corrected_value: Proposed corrected value
        confidence: Correction confidence (0.0 to 1.0)
        provenance: Source of correction (feedback IDs, etc.)
        approved: Whether approved by governance
        created_at: Timestamp when patch created
        expires_at: TTL expiration (7 days unless approved)
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
    expires_at: Optional[str]


class CorrectionPatchLayer:
    """
    Redis-backed shadow correction layer.
    
    Purpose:
        Provide immediate, reversible corrections that LLM sees
        before querying canonical graph. Corrections expire after
        7 days unless approved by governance.
    
    Redis Schema:
        Key: patch:{entity_id}:{attribute}
        Value: JSON-serialized CorrectionPatch
        TTL: 604800 seconds (7 days) unless approved=true
    
    Usage:
        patch_layer = CorrectionPatchLayer(redis_client)
        
        # Add correction
        patch_layer.add_correction(
            entity_id="INF846K01DP5",
            attribute="TER",
            canonical_value="0.79",
            corrected_value="0.82",
            confidence=0.85,
            provenance={"feedback_id": "fb_abc123"}
        )
        
        # Lookup correction
        patch = patch_layer.get_correction("INF846K01DP5", "TER")
        
        # Apply to RAG context
        corrected_context = patch_layer.apply_patches_to_context(
            entities=["INF846K01DP5"],
            retrieval_context=original_chunks
        )
    """
    
    DEFAULT_TTL_DAYS = 7
    
    def __init__(
        self,
        redis_client: redis.Redis,
        ttl_days: int = DEFAULT_TTL_DAYS
    ):
        """
        Initialize correction patch layer.
        
        Args:
            redis_client: Redis client instance
            ttl_days: Default TTL for unapproved patches (default 7)
        """
        self.redis = redis_client
        self.ttl_seconds = ttl_days * 86400
        
        logger.info(
            f"CorrectionPatchLayer initialized with {ttl_days}-day TTL"
        )
    
    def _make_key(self, entity_id: str, attribute: str) -> str:
        """Generate Redis key for patch."""
        return f"patch:{entity_id}:{attribute}"
    
    def add_correction(
        self,
        entity_id: str,
        attribute: str,
        canonical_value: Any,
        corrected_value: Any,
        confidence: float,
        provenance: Dict[str, Any],
        approved: bool = False
    ) -> str:
        """
        Add correction to patch layer.
        
        Args:
            entity_id: Canonical entity identifier
            attribute: Attribute being corrected
            canonical_value: Current value in canonical graph
            corrected_value: Proposed corrected value
            confidence: Correction confidence (0.0 to 1.0)
            provenance: Source metadata (feedback_id, actor_id, etc.)
            approved: Whether pre-approved (default False)
        
        Returns:
            patch_id: Unique patch identifier
        
        Behavior:
            - If approved=False, sets TTL (expires after 7 days)
            - If approved=True, no TTL (permanent until removed)
            - Overwrites existing patch for same entity+attribute
        
        Example:
            patch_id = patch_layer.add_correction(
                entity_id="INF846K01DP5",
                attribute="TER",
                canonical_value="0.79",
                corrected_value="0.82",
                confidence=0.85,
                provenance={
                    "feedback_id": "fb_abc123",
                    "actor_id": "user_xyz",
                    "source": "AMFI latest"
                }
            )
        """
        import uuid
        
        patch_id = f"patch_{uuid.uuid4().hex[:12]}"
        patch_key = self._make_key(entity_id, attribute)
        
        now = datetime.utcnow()
        expires_at = None if approved else (now + timedelta(days=self.DEFAULT_TTL_DAYS))
        
        patch = CorrectionPatch(
            patch_id=patch_id,
            entity_id=entity_id,
            attribute=attribute,
            canonical_value=canonical_value,
            corrected_value=corrected_value,
            confidence=confidence,
            provenance=provenance,
            approved=approved,
            created_at=now.isoformat() + "Z",
            expires_at=expires_at.isoformat() + "Z" if expires_at else None
        )
        
        # Serialize to JSON
        patch_json = json.dumps(asdict(patch))
        
        # Write to Redis
        self.redis.set(patch_key, patch_json)
        
        # Set TTL if not approved
        if not approved:
            self.redis.expire(patch_key, self.ttl_seconds)
            logger.info(
                f"Added correction patch: {patch_key} "
                f"(expires in {self.DEFAULT_TTL_DAYS} days)"
            )
        else:
            logger.info(f"Added APPROVED correction patch: {patch_key} (no TTL)")
        
        return patch_id
    
    def get_correction(
        self,
        entity_id: str,
        attribute: str
    ) -> Optional[CorrectionPatch]:
        """
        Lookup correction for entity+attribute.
        
        Args:
            entity_id: Entity identifier
            attribute: Attribute name
        
        Returns:
            CorrectionPatch if exists, None otherwise
        
        Example:
            patch = patch_layer.get_correction("INF846K01DP5", "TER")
            if patch:
                print(f"Corrected value: {patch.corrected_value}")
        """
        patch_key = self._make_key(entity_id, attribute)
        
        patch_json = self.redis.get(patch_key)
        if not patch_json:
            return None
        
        # Deserialize from JSON
        patch_dict = json.loads(patch_json)
        return CorrectionPatch(**patch_dict)
    
    def apply_patches_to_context(
        self,
        entities: List[str],
        retrieval_context: str
    ) -> str:
        """
        Apply corrections to retrieval context before LLM generation.
        
        This is THE CRITICAL INTEGRATION POINT with RAG pipeline.
        Called AFTER retrieval, BEFORE LLM call.
        
        Args:
            entities: List of entity IDs detected in query
            retrieval_context: Raw retrieval chunks (from FAISS + Neo4j)
        
        Returns:
            Modified context with correction patches injected
        
        Behavior:
            For each entity, checks ALL possible attributes for patches.
            If patch found, injects [CORRECTION] block at START of context.
            LLM is instructed to prioritize corrections over original values.
        
        Example:
            Original context:
                "TER for Axis Bluechip Fund: 0.79% (factsheet v17)"
            
            After applying patch:
                "[CORRECTION] TER = 0.82% (confidence=0.85, approved=false, 
                 source: AMFI latest feedback)
                
                 Original value for reference: 0.79% (factsheet v17, may be outdated)
                 
                 When answering, USE THE CORRECTION VALUE (0.82%) if confidence >= 0.7."
        """
        # Attributes to check (AMC domain vocabulary)
        CHECKABLE_ATTRIBUTES = [
            "TER", "NAV", "AUM", "5yr_return", "3yr_return", "1yr_return",
            "expense_ratio", "exit_load", "minimum_investment", "sharpe_ratio"
        ]
        
        correction_blocks = []
        
        for entity_id in entities:
            for attribute in CHECKABLE_ATTRIBUTES:
                patch = self.get_correction(entity_id, attribute)
                
                if patch:
                    # Build correction injection block
                    correction_block = (
                        f"\n[CORRECTION - {patch.attribute}]\n"
                        f"Entity: {patch.entity_id}\n"
                        f"Corrected Value: {patch.corrected_value}\n"
                        f"Original Value: {patch.canonical_value}\n"
                        f"Confidence: {patch.confidence:.2f}\n"
                        f"Approved: {'Yes' if patch.approved else 'Pending governance review'}\n"
                        f"Source: {patch.provenance.get('source', 'User feedback')}\n"
                        f"Created: {patch.created_at}\n"
                        f"\n⚠️ INSTRUCTION: Use corrected value ({patch.corrected_value}) "
                        f"in your response if confidence >= 0.70. "
                        f"Mention that value was recently updated.\n"
                    )
                    
                    correction_blocks.append(correction_block)
                    
                    logger.info(
                        f"Applied patch: {entity_id}.{attribute} "
                        f"= {patch.corrected_value} (was {patch.canonical_value})"
                    )
        
        if correction_blocks:
            # Inject corrections at START of context
            corrections_header = (
                "\n═══════════════════════════════════════════\n"
                "🔧 ACTIVE CORRECTIONS (Priority Override)\n"
                "═══════════════════════════════════════════\n"
            )
            corrections_text = corrections_header + "\n".join(correction_blocks)
            
            # Prepend to retrieval context
            return corrections_text + "\n\n" + retrieval_context
        else:
            # No patches found, return original context
            return retrieval_context
    
    def get_all_pending(self) -> List[CorrectionPatch]:
        """
        Get all pending (unapproved) patches for governance review.
        
        Returns:
            List of CorrectionPatch objects where approved=False
        
        Used by:
            Governance UI to display pending corrections
        """
        # Scan Redis for all patch:* keys
        pending_patches = []
        
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(
                cursor=cursor,
                match="patch:*",
                count=100
            )
            
            for key in keys:
                patch_json = self.redis.get(key)
                if patch_json:
                    patch_dict = json.loads(patch_json)
                    patch = CorrectionPatch(**patch_dict)
                    
                    if not patch.approved:
                        pending_patches.append(patch)
            
            if cursor == 0:
                break
        
        logger.info(f"Found {len(pending_patches)} pending patches")
        return pending_patches
    
    def promote_to_permanent(
        self,
        patch_id: str,
        neo4j_session: Any  # Neo4j session for canonical graph write
    ) -> bool:
        """
        Promote patch to canonical graph (governance approval).
        
        Steps:
            1. Write corrected value to Neo4j canonical graph
            2. Mark patch as approved in Redis
            3. Remove TTL (patch becomes permanent)
        
        Args:
            patch_id: Patch identifier
            neo4j_session: Neo4j session for graph write
        
        Returns:
            True if successful, False otherwise
        
        Example:
            success = patch_layer.promote_to_permanent(
                patch_id="patch_abc123",
                neo4j_session=neo4j_session
            )
        """
        # Find patch by ID (scan all keys)
        cursor = 0
        target_patch = None
        target_key = None
        
        while True:
            cursor, keys = self.redis.scan(
                cursor=cursor,
                match="patch:*",
                count=100
            )
            
            for key in keys:
                patch_json = self.redis.get(key)
                if patch_json:
                    patch_dict = json.loads(patch_json)
                    if patch_dict["patch_id"] == patch_id:
                        target_patch = CorrectionPatch(**patch_dict)
                        target_key = key
                        break
            
            if target_patch or cursor == 0:
                break
        
        if not target_patch:
            logger.error(f"Patch not found: {patch_id}")
            return False
        
        # 1. Write to canonical Neo4j graph
        try:
            neo4j_session.run(
                """
                MATCH (e:Entity {dedup_key: $entity_id})-[:HAS_FACT]->(f:Fact {attribute: $attribute})
                SET f.value = $new_value,
                    f.updated_at = datetime(),
                    f.updated_by = 'governance_approval',
                    f.source = $source
                """,
                parameters={
                    "entity_id": target_patch.entity_id,
                    "attribute": target_patch.attribute,
                    "new_value": target_patch.corrected_value,
                    "source": target_patch.provenance.get("source", "Feedback correction")
                }
            )
            
            logger.info(
                f"Written to canonical graph: {target_patch.entity_id}.{target_patch.attribute} "
                f"= {target_patch.corrected_value}"
            )
        
        except Exception as exc:
            logger.error(f"Failed to write to canonical graph: {exc}", exc_info=True)
            return False
        
        # 2. Mark patch as approved in Redis
        target_patch.approved = True
        target_patch.expires_at = None
        
        updated_json = json.dumps(asdict(target_patch))
        self.redis.set(target_key, updated_json)
        
        # 3. Remove TTL
        self.redis.persist(target_key)
        
        logger.info(f"Patch promoted to permanent: {patch_id}")
        return True
```

---

### 3.2 Integration with RAG Pipeline

**File:** `streamlit_app/retrieval.py` (MODIFY)

```python
# streamlit_app/retrieval.py (ADD THIS INTEGRATION)

from backend.app.graph.correction_patch_layer import CorrectionPatchLayer

# Initialize patch layer (module-level singleton)
_patch_layer = None

def get_patch_layer():
    global _patch_layer
    if _patch_layer is None:
        import redis
        redis_client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            decode_responses=True
        )
        _patch_layer = CorrectionPatchLayer(redis_client)
    return _patch_layer


# MODIFY EXISTING hybrid_retrieve() FUNCTION
def hybrid_retrieve(query: str, ...):
    """
    Hybrid retrieval with correction patch layer integration.
    """
    # ... existing retrieval code ...
    
    # After retrieval, BEFORE LLM call:
    # Step 1: Extract entities from query
    detected_entities = entity_resolver.extract_entities(query)
    entity_ids = [e["canonical_id"] for e in detected_entities if e.get("canonical_id")]
    
    # Step 2: Apply correction patches
    patch_layer = get_patch_layer()
    
    corrected_context = patch_layer.apply_patches_to_context(
        entities=entity_ids,
        retrieval_context=assembled_context  # Original FAISS + Neo4j context
    )
    
    # Step 3: Pass corrected context to LLM (NOT original context)
    llm_response = llm_client.call_llm(
        prompt=build_prompt(query, corrected_context),  # ← Use corrected_context
        model=config.CLAUDE_MODEL
    )
    
    # ... rest of code ...
```

---

### 3.3 Unit Tests

**File:** `backend/tests/test_correction_patch_layer.py`

```python
import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta
from app.graph.correction_patch_layer import CorrectionPatchLayer, CorrectionPatch

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis_mock = Mock()
    redis_mock.get = MagicMock(return_value=None)
    redis_mock.set = MagicMock()
    redis_mock.expire = MagicMock()
    redis_mock.persist = MagicMock()
    redis_mock.scan = MagicMock(return_value=(0, []))
    return redis_mock

@pytest.fixture
def patch_layer(mock_redis):
    """CorrectionPatchLayer instance with mock Redis."""
    return CorrectionPatchLayer(mock_redis, ttl_days=7)


class TestAddCorrection:
    """Test add_correction() method."""
    
    def test_add_unapproved_sets_ttl(self, patch_layer, mock_redis):
        """Unapproved patch should set TTL."""
        patch_id = patch_layer.add_correction(
            entity_id="INF846K01DP5",
            attribute="TER",
            canonical_value="0.79",
            corrected_value="0.82",
            confidence=0.85,
            provenance={"feedback_id": "fb_123"},
            approved=False
        )
        
        # Verify Redis.set was called
        mock_redis.set.assert_called_once()
        
        # Verify TTL was set
        mock_redis.expire.assert_called_once()
        call_args = mock_redis.expire.call_args
        assert call_args[0][1] == 604800  # 7 days in seconds
    
    def test_add_approved_no_ttl(self, patch_layer, mock_redis):
        """Approved patch should NOT set TTL."""
        patch_id = patch_layer.add_correction(
            entity_id="INF846K01DP5",
            attribute="TER",
            canonical_value="0.79",
            corrected_value="0.82",
            confidence=0.85,
            provenance={"feedback_id": "fb_123"},
            approved=True
        )
        
        # Verify Redis.set was called
        mock_redis.set.assert_called_once()
        
        # Verify TTL was NOT set
        mock_redis.expire.assert_not_called()


class TestGetCorrection:
    """Test get_correction() method."""
    
    def test_get_existing_patch(self, patch_layer, mock_redis):
        """Should return patch if exists."""
        import json
        
        # Mock Redis to return a patch
        mock_patch = {
            "patch_id": "patch_abc",
            "entity_id": "INF846K01DP5",
            "attribute": "TER",
            "canonical_value": "0.79",
            "corrected_value": "0.82",
            "confidence": 0.85,
            "provenance": {},
            "approved": False,
            "created_at": "2026-09-10T14:00:00Z",
            "expires_at": "2026-09-17T14:00:00Z"
        }
        mock_redis.get.return_value = json.dumps(mock_patch)
        
        patch = patch_layer.get_correction("INF846K01DP5", "TER")
        
        assert patch is not None
        assert patch.corrected_value == "0.82"
        assert patch.confidence == 0.85
    
    def test_get_nonexistent_patch(self, patch_layer, mock_redis):
        """Should return None if patch doesn't exist."""
        mock_redis.get.return_value = None
        
        patch = patch_layer.get_correction("INF846K01DP5", "TER")
        
        assert patch is None


class TestApplyPatches:
    """Test apply_patches_to_context() method."""
    
    def test_inject_correction(self, patch_layer, mock_redis):
        """Should inject correction block into context."""
        import json
        
        # Mock patch exists
        mock_patch = {
            "patch_id": "patch_abc",
            "entity_id": "INF846K01DP5",
            "attribute": "TER",
            "canonical_value": "0.79",
            "corrected_value": "0.82",
            "confidence": 0.85,
            "provenance": {"source": "AMFI latest"},
            "approved": False,
            "created_at": "2026-09-10T14:00:00Z",
            "expires_at": "2026-09-17T14:00:00Z"
        }
        mock_redis.get.return_value = json.dumps(mock_patch)
        
        original_context = "TER for Axis Bluechip Fund: 0.79%"
        
        corrected_context = patch_layer.apply_patches_to_context(
            entities=["INF846K01DP5"],
            retrieval_context=original_context
        )
        
        # Verify correction was injected
        assert "[CORRECTION" in corrected_context
        assert "0.82" in corrected_context
        assert original_context in corrected_context
    
    def test_no_patch_returns_original(self, patch_layer, mock_redis):
        """Should return original context if no patches."""
        mock_redis.get.return_value = None
        
        original_context = "TER for Axis Bluechip Fund: 0.79%"
        
        corrected_context = patch_layer.apply_patches_to_context(
            entities=["INF846K01DP5"],
            retrieval_context=original_context
        )
        
        # Should be unchanged
        assert corrected_context == original_context
```

---

## 4. Implementation Checklist

### Day 1-2 (16 hours):
- [ ] Create `correction_patch_layer.py` with CorrectionPatchLayer class
- [ ] Implement add_correction(), get_correction(), apply_patches_to_context()
- [ ] Setup Redis connection (local dev + staging)
- [ ] Unit tests for basic functionality

### Day 3-4 (16 hours):
- [ ] Integrate with RAG pipeline in `retrieval.py`
- [ ] Test end-to-end: add patch → query → see corrected value
- [ ] Implement get_all_pending() for governance UI
- [ ] Implement promote_to_permanent() for governance approval

### Day 5-6 (16 hours):
- [ ] Performance testing: <50ms patch lookup
- [ ] TTL expiration testing (patches expire after 7 days)
- [ ] Integration tests with actual Neo4j + Redis
- [ ] Deploy to staging, monitor correction propagation

---

## 5. Success Criteria

**Functional:**
- ✅ Corrections added to patch layer propagate to next user query
- ✅ Unapproved patches expire after 7 days
- ✅ Approved patches persist permanently
- ✅ Governance can promote patches to canonical graph

**Performance:**
- ✅ Patch lookup latency <50ms (95th percentile)
- ✅ Context injection overhead <20ms
- ✅ Zero impact on LLM generation time

**Reliability:**
- ✅ Redis failover doesn't break RAG pipeline (graceful degradation)
- ✅ Patch layer errors logged but don't crash queries
```

---

## **TRACK 7: GOVERNANCE REVIEW QUEUE UI - COMPLETE MARKDOWN**

```markdown
# Track 7: Human Governance Review Queue UI
**Implementation Plan & Technical Specification**

## Executive Summary

**Objective:** Build weekly batch approval interface where compliance officers review pending corrections before they're written to canonical graph.

**Priority:** P2  
**Duration:** 8 days (64 work hours)  
**Owner:** Full-stack Team  
**Dependencies:** Track 6 (Correction Patch Layer)  
**Value:** Controlled canonical graph updates, compliance audit trail, zero production risk

---

## 1. Problem Statement

### Current State:
- Corrections sit in Redis patch layer
- No UI for reviewing pending changes
- Compliance officers must manually query Redis
- No workflow for approve/reject/defer actions
- No audit trail of governance decisions

### Target State:
- Web UI showing all pending corrections
- Side-by-side comparison (current vs proposed)
- Evidence panel (supporting feedback records)
- One-click approve/reject/defer
- Batch operations (approve multiple at once)
- Complete audit trail

### User Persona: Compliance Officer

**Weekly Workflow:**
1. **Monday 9 AM:** Logs into governance review UI
2. **Reviews pending corrections:** 25 patches from last week
3. **For each patch:**
   - Sees entity name, attribute, current vs proposed value
   - Reviews supporting evidence (3 feedback records)
   - Checks confidence score (0.85 = high confidence)
   - Verifies source (AMFI latest data)
4. **Takes action:**
   - Approves 20 patches (clearly correct)
   - Rejects 3 patches (user was wrong)
   - Defers 2 patches (need more investigation)
5. **Monday 9:30 AM:** Done, canonical graph updated with approved changes

---

## 2. Architecture Design

### Component Diagram:

```
┌─────────────────────────────────────────────────────────────┐
│              Frontend (React/Vue)                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  GovernanceReviewPage.tsx                            │   │
│  │                                                      │   │
│  │  Components:                                         │   │
│  │  - PendingCorrectionsTable                           │   │
│  │  - CorrectionDetailPanel                             │   │
│  │  - EvidenceViewer                                    │   │
│  │  - ApprovalActions (Approve/Reject/Defer)            │   │
│  │  - BatchOperationsToolbar                            │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP API
                     ▼
┌─────────────────────────────────────────────────────────────┐
│         Backend API (FastAPI)                                │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  GET /api/governance/pending-corrections             │   │
│  │    Returns: List of pending patches                  │   │
│  │                                                      │   │
│  │  GET /api/governance/correction/{patch_id}           │   │
│  │    Returns: Detailed patch info + evidence           │   │
│  │                                                      │   │
│  │  POST /api/governance/approve/{patch_id}             │   │
│  │    Action: Approve correction → write to graph       │   │
│  │                                                      │   │
│  │  POST /api/governance/reject/{patch_id}              │   │
│  │    Action: Reject → remove patch from Redis          │   │
│  │                                                      │   │
│  │  POST /api/governance/batch-approve                  │   │
│  │    Action: Approve multiple patches at once          │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│       CorrectionPatchLayer (Redis)                           │
│       - get_all_pending() → List[CorrectionPatch]            │
│       - promote_to_permanent(patch_id)                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│       Neo4j Canonical Graph                                  │
│       - Write approved corrections                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Implementation Specification

### 3.1 Backend API

**File:** `backend/app/api/routes/governance.py` (NEW)

```python
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime

from app.compliance.security import get_client_role, require_roles
from app.schemas.compliance_models import Role
from app.graph.correction_patch_layer import CorrectionPatchLayer, CorrectionPatch
from app.db.feedback import get_feedback_store
import redis
import config

router = APIRouter(prefix="/governance", tags=["governance"])

# Initialize patch layer
_redis_client = None
_patch_layer = None

def get_patch_layer():
    global _redis_client, _patch_layer
    if _patch_layer is None:
        _redis_client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            decode_responses=True
        )
        _patch_layer = CorrectionPatchLayer(_redis_client)
    return _patch_layer


# Response models
class CorrectionProposal(BaseModel):
    """Correction proposal for governance review."""
    patch_id: str
    entity_id: str
    entity_name: str  # Human-readable name
    attribute: str
    current_value: str
    proposed_value: str
    confidence: float
    supporting_evidence: List[Dict[str, Any]]  # Feedback records
    created_at: str
    expires_at: str
    feedback_count: int
    risk_level: str  # LOW, MEDIUM, HIGH


class ApprovalRequest(BaseModel):
    """Request to approve/reject correction."""
    patch_id: str
    action: str  # "approve" | "reject" | "defer"
    comment: Optional[str] = None


class BatchApprovalRequest(BaseModel):
    """Batch approval request."""
    patch_ids: List[str]
    action: str  # "approve" | "reject"


# API endpoints
@router.get("/pending-corrections", response_model=List[CorrectionProposal])
@require_roles([Role.ADMIN, Role.COMPLIANCE_OFFICER])
def get_pending_corrections(
    current_role: Role = Depends(get_client_role)
) -> List[CorrectionProposal]:
    """
    Fetch all corrections awaiting governance approval.
    
    Returns:
        List of CorrectionProposal objects with:
        - Entity info (ID, name)
        - Current vs proposed value
        - Confidence score
        - Supporting evidence (feedback records)
        - Risk assessment
    
    Example Response:
        [
            {
                "patch_id": "patch_abc123",
                "entity_id": "INF846K01DP5",
                "entity_name": "Axis Bluechip Fund Direct Growth",
                "attribute": "TER",
                "current_value": "0.79%",
                "proposed_value": "0.82%",
                "confidence": 0.85,
                "supporting_evidence": [
                    {
                        "feedback_id": "fb_123",
                        "actor_id": "user_xyz",
                        "comment": "TER is 0.82% per AMFI latest",
                        "created_at": "2026-09-10T14:32:15Z"
                    }
                ],
                "created_at": "2026-09-10T14:32:15Z",
                "expires_at": "2026-09-17T14:32:15Z",
                "feedback_count": 3,
                "risk_level": "LOW"
            },
            ...
        ]
    """
    patch_layer = get_patch_layer()
    pending_patches = patch_layer.get_all_pending()
    
    feedback_store = get_feedback_store()
    
    proposals = []
    for patch in pending_patches:
        # Fetch supporting evidence (feedback records)
        evidence = []
        if "feedback_ids" in patch.provenance:
            for fb_id in patch.provenance["feedback_ids"]:
                # TODO: Fetch feedback record by ID
                # For now, use placeholder
                evidence.append({
                    "feedback_id": fb_id,
                    "actor_id": "unknown",
                    "comment": "Feedback comment",
                    "created_at": patch.created_at
                })
        
        # Assess risk level based on confidence + value change magnitude
        risk_level = assess_risk_level(
            confidence=patch.confidence,
            current_value=patch.canonical_value,
            proposed_value=patch.corrected_value
        )
        
        # Resolve entity name (TODO: lookup from Neo4j)
        entity_name = f"Entity {patch.entity_id}"
        
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
            expires_at=patch.expires_at or "",
            feedback_count=len(evidence),
            risk_level=risk_level
        ))
    
    return proposals


@router.get("/correction/{patch_id}", response_model=CorrectionProposal)
@require_roles([Role.ADMIN, Role.COMPLIANCE_OFFICER])
def get_correction_detail(
    patch_id: str,
    current_role: Role = Depends(get_client_role)
) -> CorrectionProposal:
    """
    Fetch detailed info for a single correction.
    
    Args:
        patch_id: Patch identifier
    
    Returns:
        Detailed CorrectionProposal with full evidence
    """
    # TODO: Implement similar to get_pending_corrections but for single patch
    pass


@router.post("/approve/{patch_id}")
@require_roles([Role.ADMIN, Role.COMPLIANCE_OFFICER])
def approve_correction(
    patch_id: str,
    comment: Optional[str] = None,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Approve correction → write to canonical graph.
    
    Steps:
        1. Promote patch to canonical Neo4j graph
        2. Mark as approved in Redis (remove TTL)
        3. Log governance decision to audit trail
    
    Args:
        patch_id: Patch identifier
        comment: Optional approval comment
    
    Returns:
        {
            "status": "approved",
            "patch_id": "patch_abc123",
            "approved_by": "compliance_officer",
            "approved_at": "2026-09-13T09:15:00Z"
        }
    
    Example Request:
        POST /api/governance/approve/patch_abc123
        {
            "comment": "Verified with AMFI data, approved"
        }
    """
    patch_layer = get_patch_layer()
    
    # Get Neo4j session
    from streamlit_app.graph_store import get_driver
    driver = get_driver()
    
    try:
        with driver.session(database=config.NEO4J_DATABASE) as neo4j_session:
            success = patch_layer.promote_to_permanent(
                patch_id=patch_id,
                neo4j_session=neo4j_session
            )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Patch not found or promotion failed: {patch_id}"
            )
        
        # Log governance decision
        log_governance_decision(
            patch_id=patch_id,
            action="approve",
            actor=current_role.value,
            comment=comment
        )
        
        return {
            "status": "approved",
            "patch_id": patch_id,
            "approved_by": current_role.value,
            "approved_at": datetime.utcnow().isoformat() + "Z"
        }
    
    except Exception as exc:
        logger.error(f"Failed to approve correction: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to approve correction"
        )


@router.post("/reject/{patch_id}")
@require_roles([Role.ADMIN, Role.COMPLIANCE_OFFICER])
def reject_correction(
    patch_id: str,
    reason: str,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Reject correction → remove from patch layer.
    
    Steps:
        1. Remove patch from Redis
        2. Log governance decision
        3. Optionally notify feedback submitter
    
    Args:
        patch_id: Patch identifier
        reason: Rejection reason (required)
    
    Returns:
        {
            "status": "rejected",
            "patch_id": "patch_abc123",
            "rejected_by": "compliance_officer",
            "reason": "User was incorrect, canonical value verified"
        }
    """
    patch_layer = get_patch_layer()
    
    # Delete patch from Redis
    # TODO: Implement delete_patch() in CorrectionPatchLayer
    
    # Log governance decision
    log_governance_decision(
        patch_id=patch_id,
        action="reject",
        actor=current_role.value,
        comment=reason
    )
    
    return {
        "status": "rejected",
        "patch_id": patch_id,
        "rejected_by": current_role.value,
        "reason": reason,
        "rejected_at": datetime.utcnow().isoformat() + "Z"
    }


@router.post("/batch-approve")
@require_roles([Role.ADMIN, Role.COMPLIANCE_OFFICER])
def batch_approve_corrections(
    request: BatchApprovalRequest,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Approve or reject multiple corrections at once.
    
    Args:
        request: BatchApprovalRequest with patch_ids and action
    
    Returns:
        {
            "action": "approve",
            "total": 10,
            "succeeded": 8,
            "failed": 2,
            "failed_patch_ids": ["patch_xyz", "patch_abc"]
        }
    
    Example Request:
        POST /api/governance/batch-approve
        {
            "patch_ids": ["patch_123", "patch_456", "patch_789"],
            "action": "approve"
        }
    """
    results = {
        "action": request.action,
        "total": len(request.patch_ids),
        "succeeded": 0,
        "failed": 0,
        "failed_patch_ids": []
    }
    
    for patch_id in request.patch_ids:
        try:
            if request.action == "approve":
                approve_correction(patch_id, current_role=current_role)
            elif request.action == "reject":
                reject_correction(patch_id, reason="Batch rejection", current_role=current_role)
            
            results["succeeded"] += 1
        
        except Exception as exc:
            logger.error(f"Batch operation failed for {patch_id}: {exc}")
            results["failed"] += 1
            results["failed_patch_ids"].append(patch_id)
    
    return results


# Helper functions
def assess_risk_level(
    confidence: float,
    current_value: Any,
    proposed_value: Any
) -> str:
    """
    Assess risk level of correction.
    
    Logic:
        - HIGH: Low confidence (<0.7) OR large value change (>20%)
        - MEDIUM: Medium confidence (0.7-0.85) OR medium change (10-20%)
        - LOW: High confidence (>0.85) AND small change (<10%)
    """
    if confidence < 0.7:
        return "HIGH"
    
    # Calculate percentage change (for numeric values)
    try:
        curr_float = float(str(current_value).replace("%", "").replace("₹", ""))
        prop_float = float(str(proposed_value).replace("%", "").replace("₹", ""))
        pct_change = abs((prop_float - curr_float) / curr_float) * 100
        
        if pct_change > 20:
            return "HIGH"
        elif pct_change > 10:
            return "MEDIUM"
    except:
        pass
    
    if confidence >= 0.85:
        return "LOW"
    else:
        return "MEDIUM"


def log_governance_decision(
    patch_id: str,
    action: str,
    actor: str,
    comment: Optional[str] = None
):
    """
    Log governance decision to audit trail.
    """
    # TODO: Write to governance_audit_log table or file
    logger.info(
        f"Governance decision: patch={patch_id}, action={action}, "
        f"actor={actor}, comment={comment}"
    )
```

---

### 3.2 Frontend UI (React/TypeScript)

**File:** `frontend/src/pages/GovernanceReviewPage.tsx` (NEW)

```typescript
import React, { useState, useEffect } from 'react';
import { Table, Button, Tag, Modal, Space, Descriptions, Badge } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';

interface CorrectionProposal {
  patch_id: string;
  entity_id: string;
  entity_name: string;
  attribute: string;
  current_value: string;
  proposed_value: string;
  confidence: number;
  supporting_evidence: any[];
  created_at: string;
  expires_at: string;
  feedback_count: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
}

export const GovernanceReviewPage: React.FC = () => {
  const [pendingCorrections, setPendingCorrections] = useState<CorrectionProposal[]>([]);
  const [selectedPatch, setSelectedPatch] = useState<CorrectionProposal | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [loading, setLoading] = useState(false);

  // Fetch pending corrections on mount
  useEffect(() => {
    fetchPendingCorrections();
  }, []);

  const fetchPendingCorrections = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/governance/pending-corrections');
      const data = await response.json();
      setPendingCorrections(data);
    } catch (error) {
      console.error('Failed to fetch pending corrections:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (patchId: string) => {
    try {
      await fetch(`/api/governance/approve/${patchId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      // Refresh list
      fetchPendingCorrections();
    } catch (error) {
      console.error('Failed to approve:', error);
    }
  };

  const handleReject = async (patchId: string, reason: string) => {
    try {
      await fetch(`/api/governance/reject/${patchId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason })
      });
      
      // Refresh list
      fetchPendingCorrections();
    } catch (error) {
      console.error('Failed to reject:', error);
    }
  };

  const columns = [
    {
      title: 'Entity',
      dataIndex: 'entity_name',
      key: 'entity_name',
      width: 250
    },
    {
      title: 'Attribute',
      dataIndex: 'attribute',
      key: 'attribute',
      width: 100
    },
    {
      title: 'Current Value',
      dataIndex: 'current_value',
      key: 'current_value',
      width: 120,
      render: (value: string) => <span style={{ color: '#666' }}>{value}</span>
    },
    {
      title: 'Proposed Value',
      dataIndex: 'proposed_value',
      key: 'proposed_value',
      width: 120,
      render: (value: string) => <span style={{ color: '#1890ff', fontWeight: 600 }}>{value}</span>
    },
    {
      title: 'Confidence',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 100,
      render: (confidence: number) => (
        <Badge
          status={confidence >= 0.85 ? 'success' : confidence >= 0.70 ? 'warning' : 'error'}
          text={`${(confidence * 100).toFixed(0)}%`}
        />
      )
    },
    {
      title: 'Risk',
      dataIndex: 'risk_level',
      key: 'risk_level',
      width: 80,
      render: (risk: string) => {
        const color = risk === 'HIGH' ? 'red' : risk === 'MEDIUM' ? 'orange' : 'green';
        return <Tag color={color}>{risk}</Tag>;
      }
    },
    {
      title: 'Evidence',
      dataIndex: 'feedback_count',
      key: 'feedback_count',
      width: 80,
      render: (count: number) => `${count} feedback${count !== 1 ? 's' : ''}`
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (record: CorrectionProposal) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<CheckCircleOutlined />}
            onClick={() => handleApprove(record.patch_id)}
          >
            Approve
          </Button>
          <Button
            danger
            size="small"
            icon={<CloseCircleOutlined />}
            onClick={() => {
              const reason = prompt('Rejection reason:');
              if (reason) handleReject(record.patch_id, reason);
            }}
          >
            Reject
          </Button>
          <Button
            size="small"
            onClick={() => {
              setSelectedPatch(record);
              setDetailModalVisible(true);
            }}
          >
            Details
          </Button>
        </Space>
      )
    }
  ];

  return (
    <div style={{ padding: '24px' }}>
      <h1>Governance Review Queue</h1>
      <p style={{ marginBottom: '24px', color: '#666' }}>
        Review pending corrections before they're written to canonical graph. 
        Weekly batch approval recommended.
      </p>

      <Table
        dataSource={pendingCorrections}
        columns={columns}
        loading={loading}
        rowKey="patch_id"
        pagination={{ pageSize: 50 }}
      />

      {/* Detail Modal */}
      <Modal
        title="Correction Detail"
        visible={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            Close
          </Button>,
          <Button
            key="approve"
            type="primary"
            icon={<CheckCircleOutlined />}
            onClick={() => {
              if (selectedPatch) handleApprove(selectedPatch.patch_id);
              setDetailModalVisible(false);
            }}
          >
            Approve
          </Button>
        ]}
        width={800}
      >
        {selectedPatch && (
          <>
            <Descriptions bordered column={2}>
              <Descriptions.Item label="Entity">{selectedPatch.entity_name}</Descriptions.Item>
              <Descriptions.Item label="Attribute">{selectedPatch.attribute}</Descriptions.Item>
              <Descriptions.Item label="Current Value">{selectedPatch.current_value}</Descriptions.Item>
              <Descriptions.Item label="Proposed Value">{selectedPatch.proposed_value}</Descriptions.Item>
              <Descriptions.Item label="Confidence">{(selectedPatch.confidence * 100).toFixed(1)}%</Descriptions.Item>
              <Descriptions.Item label="Risk Level">
                <Tag color={selectedPatch.risk_level === 'HIGH' ? 'red' : selectedPatch.risk_level === 'MEDIUM' ? 'orange' : 'green'}>
                  {selectedPatch.risk_level}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Created">{new Date(selectedPatch.created_at).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="Expires">{new Date(selectedPatch.expires_at).toLocaleString()}</Descriptions.Item>
            </Descriptions>

            <h3 style={{ marginTop: '24px' }}>Supporting Evidence</h3>
            {selectedPatch.supporting_evidence.map((evidence, idx) => (
              <div key={idx} style={{ padding: '12px', background: '#f5f5f5', marginBottom: '8px', borderRadius: '4px' }}>
                <div><strong>Feedback ID:</strong> {evidence.feedback_id}</div>
                <div><strong>Comment:</strong> {evidence.comment}</div>
                <div style={{ color: '#666', fontSize: '12px' }}>{new Date(evidence.created_at).toLocaleString()}</div>
              </div>
            ))}
          </>
        )}
      </Modal>
    </div>
  );
};
```

---

## 4. Implementation Checklist

### Day 1-2 (Backend API):
- [ ] Create `governance.py` routes file
- [ ] Implement GET `/pending-corrections` endpoint
- [ ] Implement POST `/approve/{patch_id}` endpoint
- [ ] Implement POST `/reject/{patch_id}` endpoint
- [ ] Implement POST `/batch-approve` endpoint

### Day 3-4 (Frontend UI):
- [ ] Create GovernanceReviewPage component
- [ ] Implement PendingCorrectionsTable
- [ ] Implement CorrectionDetailModal
- [ ] Add approve/reject action buttons
- [ ] Style with Ant Design components

### Day 5-6 (Integration):
- [ ] Connect frontend to backend API
- [ ] Test end-to-end approval workflow
- [ ] Add error handling and loading states
- [ ] Implement batch operations UI

### Day 7-8 (Testing & Deployment):
- [ ] Unit tests for backend endpoints
- [ ] Integration tests for approval workflow
- [ ] User acceptance testing with compliance officer
- [ ] Deploy to staging, monitor governance decisions

---

## 5. Success Criteria

**Functional:**
- ✅ Compliance officers can review all pending corrections
- ✅ Side-by-side comparison of current vs proposed values
- ✅ One-click approve/reject actions
- ✅ Batch operations for efficiency
- ✅ Complete audit trail of governance decisions

**User Experience:**
- ✅ <5 minutes to review 25 pending corrections
- ✅ Clear risk indicators (LOW/MEDIUM/HIGH)
- ✅ Intuitive UI requiring no training

**Compliance:**
- ✅ All governance decisions logged
- ✅ Only ADMIN and COMPLIANCE_OFFICER roles can approve
- ✅ Audit trail retained for regulatory review
```

---

**These two markdown documents provide complete implementation specifications for Tracks 6 and 7. Your development team can:**

1. Save as `TRACK_6_CORRECTION_PATCH_LAYER_PLAN.md` and `TRACK_7_GOVERNANCE_UI_PLAN.md`
2. Follow the detailed implementation checklists
3. Use the code examples as starting points
4. Reference the architecture diagrams for integration

Would you like me to also create similar detailed markdown documents for Track 8 (NER + Entity Resolution) and the overall Implementation Roadmap?