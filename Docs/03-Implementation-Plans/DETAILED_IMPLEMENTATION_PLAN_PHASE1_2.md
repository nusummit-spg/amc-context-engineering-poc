# Detailed Implementation Plan: Phase 1 & 2
## Continuing AMC Context Engineering Roadmap

**Date**: September 8, 2026  
**Scope**: Phase 1 (Week 1-2 post-prod) + Phase 2 (Weeks 3-4)

---

## PHASE 1: Post-Production (5-7 Days)

**Goal**: Complete agentic autonomy loops, enable self-healing feedback system

### Task 1.1: Multi-Round Adaptive Retrieval Integration
**Effort**: 2-3 days  
**Owner**: Backend Lead  
**Dependency**: Phase 0 complete  
**Blocking**: NO (enhancement)

#### 1.1.1 Update Orchestrator to Use Adaptive Retrieval

**File**: `backend/app/retrieval/orchestrator.py` (MODIFIED)

```python
# After initial retrieval (around line 490):

# Enhanced retrieval pipeline with multi-round logic
if config.ENABLE_QUERY_DECOMPOSITION:
    comp_adaptive = ComponentMetric("adaptive_retrieval", time.perf_counter())
    
    # Get initial retrieval results
    initial_chunks = chunks.copy()
    initial_facts = facts.copy()
    
    # Assess retrieval quality
    quality_check = assess_retrieval_quality(
        chunks=initial_chunks,
        facts=initial_facts,
        query=effective_query,
        resolved_entities=resolved_map,
        min_chunks_threshold=2,
        entity_coverage_threshold=0.6
    )
    
    if not quality_check.is_sufficient and not quality_check.has_error:
        logger.info(
            f"Round 1 retrieval insufficient (coverage: {quality_check.entity_coverage:.1%}), "
            f"triggering Round 2 with relaxed thresholds"
        )
        
        # Round 2: Relaxed retrieval
        round2_chunks = await self._execute_adaptive_retrieval_round2(
            plan=plan,
            search_query=search_query,
            intent=intent,
            resolved_entities=resolved_entities,
            original_threshold=0.45,
            relaxed_threshold=0.35
        )
        
        # Merge results (don't replace)
        chunks.extend(round2_chunks)
        logger.info(f"Round 2 added {len(round2_chunks)} additional chunks")
        
        # Re-assess after Round 2
        quality_check = assess_retrieval_quality(
            chunks=chunks,
            facts=facts,
            query=effective_query,
            resolved_entities=resolved_map,
            min_chunks_threshold=2,
            entity_coverage_threshold=0.5
        )
        
        if not quality_check.is_sufficient:
            logger.info("Round 2 insufficient, would trigger Round 3 (graph expansion)")
            # Round 3 implementation (future enhancement)
    
    comp_adaptive.finalize()
    if metrics:
        metrics.add_component(comp_adaptive)
        metrics.retrieval_rounds = quality_check.rounds_used
```

#### 1.1.2 Implement Quality Assessment Function

**File**: `backend/app/retrieval/quality_assessor.py` (NEW)

```python
"""
Assess retrieval quality without LLM calls (fast heuristics).
"""

from dataclasses import dataclass
from typing import List, Dict

@dataclass
class QualityAssessment:
    is_sufficient: bool
    entity_coverage: float
    chunk_quality_avg: float
    has_error: bool = False
    error_message: str = ""
    rounds_used: int = 1
    feedback: str = ""

class RetrievalQualityAssessor:
    """Fast heuristic-based quality assessment."""
    
    @staticmethod
    def assess(
        chunks: List[dict],
        facts: List[dict],
        query: str,
        resolved_entities: Dict[str, str],
        min_chunks_threshold: int = 2,
        entity_coverage_threshold: float = 0.6,
        min_relevance_score: float = 0.45
    ) -> QualityAssessment:
        """
        Assess retrieval quality.
        
        Returns:
            QualityAssessment with sufficiency decision
        """
        
        # Check 1: Minimum chunk count
        if len(chunks) < min_chunks_threshold:
            return QualityAssessment(
                is_sufficient=False,
                entity_coverage=0.0,
                chunk_quality_avg=0.0,
                feedback=f"Insufficient chunks: {len(chunks)} < {min_chunks_threshold}"
            )
        
        # Check 2: Entity coverage
        query_entities = set(resolved_entities.keys())
        if query_entities:
            covered_entities = 0
            for entity_name in query_entities:
                # Check if entity mentioned in retrieved chunks
                for chunk in chunks:
                    if entity_name.lower() in chunk.get("text", "").lower():
                        covered_entities += 1
                        break
            
            entity_coverage = covered_entities / len(query_entities)
            
            if entity_coverage < entity_coverage_threshold:
                return QualityAssessment(
                    is_sufficient=False,
                    entity_coverage=entity_coverage,
                    chunk_quality_avg=0.0,
                    feedback=f"Low entity coverage: {entity_coverage:.1%} < {entity_coverage_threshold:.1%}"
                )
        
        # Check 3: Chunk relevance scores
        relevance_scores = [c.get("score", 0.5) for c in chunks]
        avg_relevance = sum(relevance_scores) / len(relevance_scores)
        
        if avg_relevance < min_relevance_score:
            return QualityAssessment(
                is_sufficient=False,
                entity_coverage=entity_coverage if query_entities else 1.0,
                chunk_quality_avg=avg_relevance,
                feedback=f"Low relevance: {avg_relevance:.2f} < {min_relevance_score:.2f}"
            )
        
        # Check 4: Gap signals in text
        combined_text = " ".join(c.get("text", "") for c in chunks)
        gap_signals = ["not found", "no information", "not available", "unknown", "not specified"]
        gap_count = sum(combined_text.lower().count(signal) for signal in gap_signals)
        
        if gap_count > 2:
            return QualityAssessment(
                is_sufficient=False,
                entity_coverage=entity_coverage if query_entities else 1.0,
                chunk_quality_avg=avg_relevance,
                feedback=f"Knowledge gaps detected ({gap_count} signals)"
            )
        
        # All checks passed
        return QualityAssessment(
            is_sufficient=True,
            entity_coverage=entity_coverage if query_entities else 1.0,
            chunk_quality_avg=avg_relevance,
            feedback="Retrieval quality acceptable"
        )

def assess_retrieval_quality(
    chunks: List[dict],
    facts: List[dict],
    query: str,
    resolved_entities: Dict[str, str],
    **kwargs
) -> QualityAssessment:
    """Convenience function."""
    assessor = RetrievalQualityAssessor()
    return assessor.assess(chunks, facts, query, resolved_entities, **kwargs)
```

#### 1.1.3 Implement Round 2 Retrieval

**File**: `backend/app/retrieval/adaptive_retriever.py` (ENHANCED)

```python
"""
Adaptive retriever with multi-round capability.
"""

import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger("adaptive_retriever")

class AdaptiveRetriever:
    def __init__(self, vector_store, graph_store):
        self.vector_store = vector_store
        self.graph_store = graph_store
    
    async def retrieve_round2(
        self,
        query: str,
        hyde_doc: str,
        plan: Optional[object],
        top_k: int,
        intent: object,
        resolved_entities: List[str],
        original_threshold: float = 0.45,
        relaxed_threshold: float = 0.30
    ) -> List[dict]:
        """
        Round 2: More lenient retrieval.
        
        Strategies:
        1. Relax similarity threshold
        2. Expand entity list (surface forms)
        3. Include partial matches
        4. Query expansion with synonyms
        """
        
        logger.info(f"Round 2 retrieval: relaxing threshold from {original_threshold} to {relaxed_threshold}")
        
        # Strategy 1: Relax vector similarity threshold
        search_query = query
        if hyde_doc:
            search_query = f"{query}\n\nHYPOTHETICAL DOCUMENT:\n{hyde_doc}"
        
        round2_chunks = await self.vector_store.search(
            search_query,
            top_k=top_k * 2,  # Get more candidates
            similarity_threshold=relaxed_threshold  # Lower threshold
        )
        
        logger.info(f"Round 2 vector search: {len(round2_chunks)} chunks at threshold {relaxed_threshold}")
        
        # Strategy 2: Expand entities with fuzzy matching
        entity_variations = self._generate_entity_variations(resolved_entities)
        
        for entity_var in entity_variations:
            entity_chunks = await self.vector_store.search(
                f"{query} {entity_var}",
                top_k=5,
                similarity_threshold=relaxed_threshold - 0.05  # Even more lenient
            )
            round2_chunks.extend(entity_chunks)
        
        # Deduplicate
        seen_ids = set()
        deduped = []
        for chunk in round2_chunks:
            if chunk.get("id") not in seen_ids:
                deduped.append(chunk)
                seen_ids.add(chunk.get("id"))
        
        logger.info(f"Round 2 result: {len(deduped)} chunks after deduplication")
        
        return deduped
    
    def _generate_entity_variations(self, entities: List[str]) -> List[str]:
        """Generate entity name variations for expanded search."""
        
        variations = []
        for entity in entities:
            # Add common abbreviations, aliases
            if "fund" in entity.lower():
                variations.extend(["scheme", "investment product"])
            if "amc" in entity.lower():
                variations.extend(["asset manager", "mutual fund company"])
            if "sebi" in entity.lower():
                variations.extend(["regulator", "regulatory body"])
        
        return variations
```

#### 1.1.4 Testing

**File**: `backend/test_adaptive_retrieval.py` (NEW)

```python
import pytest
from app.retrieval.quality_assessor import assess_retrieval_quality
from app.retrieval.adaptive_retriever import AdaptiveRetriever

@pytest.mark.asyncio
async def test_quality_assessment_sufficient():
    """Test quality check passes."""
    chunks = [
        {"id": 1, "text": "SEBI specifies minimum AUM", "score": 0.85},
        {"id": 2, "text": "Rs 10 crore requirement", "score": 0.78}
    ]
    
    assessment = assess_retrieval_quality(
        chunks=chunks,
        facts=[],
        query="minimum AUM",
        resolved_entities={"sebi": "SEBI"},
        min_chunks_threshold=2
    )
    
    assert assessment.is_sufficient == True

@pytest.mark.asyncio
async def test_quality_assessment_insufficient():
    """Test quality check fails."""
    chunks = [
        {"id": 1, "text": "Not found", "score": 0.30}
    ]
    
    assessment = assess_retrieval_quality(
        chunks=chunks,
        facts=[],
        query="minimum AUM",
        resolved_entities={"sebi": "SEBI", "amc": "AMC"},
        min_chunks_threshold=2,
        entity_coverage_threshold=0.8
    )
    
    assert assessment.is_sufficient == False
    assert assessment.entity_coverage < 0.8

@pytest.mark.asyncio
async def test_round2_retrieval():
    """Test Round 2 adaptive retrieval."""
    # Mock vector store
    retriever = AdaptiveRetriever(
        vector_store=MockVectorStore(),
        graph_store=MockGraphStore()
    )
    
    round2_chunks = await retriever.retrieve_round2(
        query="What is minimum AUM?",
        hyde_doc="HYPOTHETICAL: Minimum AUM requirements...",
        plan=None,
        top_k=5,
        intent=None,
        resolved_entities=["SEBI", "AUM"]
    )
    
    assert len(round2_chunks) > 0
```

---

### Task 1.2: Complete Feedback Governance Batch
**Effort**: 2-3 days  
**Owner**: Backend Lead + ML Engineer  
**Dependency**: Phase 0 complete, feedback system (parallel work)  
**Blocking**: NO (but critical for self-healing)

#### 1.2.1 Governance Batch Orchestrator

**File**: `backend/app/tasks/governance_batch.py` (NEW)

```python
"""
Weekly governance batch: Process approved patches, update canonical KG.
"""

import logging
from datetime import datetime, timedelta
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("governance_batch")

class GovernanceBatch:
    """Process feedback patches and apply approved corrections."""
    
    def __init__(self, db_client: AsyncIOMotorClient, graph_store):
        self.db = db_client.amc_db
        self.graph_store = graph_store
    
    async def process(self) -> int:
        """
        Execute governance batch:
        1. Fetch approved patches from feedback table
        2. Group by fact/edge type
        3. Validate patches
        4. Apply to Neo4j
        5. Log deployment
        
        Returns: Number of patches deployed
        """
        
        logger.info("🚀 Starting governance batch processing...")
        
        # Step 1: Get approved patches from past week
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        approved_patches = await self.db.feedback_corrections.find({
            "status": "approved",
            "deployment_date": None,
            "approved_at": {"$gte": seven_days_ago}
        }).to_list(None)
        
        logger.info(f"Found {len(approved_patches)} approved patches for deployment")
        
        if not approved_patches:
            logger.info("No patches to deploy this batch")
            return 0
        
        # Step 2: Group patches
        patches_by_type = self._group_patches(approved_patches)
        
        deployed_count = 0
        
        # Step 3: Deploy patches
        for patch_type, patches in patches_by_type.items():
            for patch in patches:
                try:
                    success = await self._deploy_patch(patch)
                    if success:
                        deployed_count += 1
                        
                        # Mark as deployed
                        await self.db.feedback_corrections.update_one(
                            {"_id": patch["_id"]},
                            {"$set": {
                                "deployment_date": datetime.utcnow(),
                                "deployment_status": "success"
                            }}
                        )
                        
                        logger.info(f"✅ Deployed patch: {patch['fact_id']}")
                    
                except Exception as exc:
                    logger.error(f"❌ Failed to deploy patch {patch['_id']}: {exc}")
                    
                    # Mark as failed
                    await self.db.feedback_corrections.update_one(
                        {"_id": patch["_id"]},
                        {"$set": {
                            "deployment_date": datetime.utcnow(),
                            "deployment_status": "failed",
                            "deployment_error": str(exc)
                        }}
                    )
        
        logger.info(f"✅ Governance batch complete: {deployed_count} patches deployed")
        return deployed_count
    
    def _group_patches(self, patches: List[dict]) -> dict:
        """Group patches by type for batch processing."""
        
        grouped = {}
        for patch in patches:
            patch_type = patch.get("patch_type", "unknown")
            if patch_type not in grouped:
                grouped[patch_type] = []
            grouped[patch_type].append(patch)
        
        return grouped
    
    async def _deploy_patch(self, patch: dict) -> bool:
        """
        Deploy a single patch to Neo4j.
        
        Patch structure:
        {
            "fact_id": str,
            "patch_type": "entity_update" | "relationship_correction" | "property_update",
            "target": "graph_entity_id",
            "operation": dict (cypher params),
            "approved_by": str (user_id),
            "approved_at": datetime,
            "rationale": str
        }
        """
        
        patch_type = patch.get("patch_type")
        
        if patch_type == "entity_update":
            return await self._deploy_entity_patch(patch)
        elif patch_type == "relationship_correction":
            return await self._deploy_relationship_patch(patch)
        elif patch_type == "property_update":
            return await self._deploy_property_patch(patch)
        else:
            logger.warning(f"Unknown patch type: {patch_type}")
            return False
    
    async def _deploy_entity_patch(self, patch: dict) -> bool:
        """Update entity properties."""
        
        cypher = f"""
        MATCH (n:Entity {{id: '{patch['target']}'}})
        SET n.corrected_by = '{patch['approved_by']}'
        SET n.correction_date = datetime()
        SET n.previous_state = {patch.get('previous_state', '{}')}
        """
        
        # Apply additional properties from operation
        for key, value in patch.get("operation", {}).items():
            cypher += f"\nSET n.{key} = '{value}'"
        
        try:
            await self.graph_store.run_cypher(cypher)
            return True
        except Exception as exc:
            logger.error(f"Cypher execution failed: {exc}")
            return False
    
    async def _deploy_relationship_patch(self, patch: dict) -> bool:
        """Update relationships (e.g., correct supersession)."""
        
        cypher = f"""
        MATCH (source {{id: '{patch['target']['source']}'}})
            -[r:{patch['target']['relationship']}]->
            (target {{id: '{patch['target']['target']}'}})
        SET r.corrected_by = '{patch['approved_by']}'
        SET r.correction_date = datetime()
        SET r.rationale = '{patch.get('rationale', '')}'
        """
        
        try:
            await self.graph_store.run_cypher(cypher)
            return True
        except Exception as exc:
            logger.error(f"Cypher execution failed: {exc}")
            return False
    
    async def _deploy_property_patch(self, patch: dict) -> bool:
        """Update entity properties."""
        
        cypher = f"""
        MATCH (n {{id: '{patch['target']}'}})
        """
        
        for key, value in patch.get("operation", {}).items():
            cypher += f"\nSET n.{key} = '{value}'"
        
        cypher += f"""
        SET n.corrected_by = '{patch['approved_by']}'
        SET n.correction_date = datetime()
        """
        
        try:
            await self.graph_store.run_cypher(cypher)
            return True
        except Exception as exc:
            logger.error(f"Cypher execution failed: {exc}")
            return False
```

#### 1.2.2 Patch Generation from Verdicts

**File**: `backend/app/evaluation/patch_generator.py` (NEW)

```python
"""
Generate Neo4j patches from feedback verdicts.
"""

from app.schemas.review_queue import Verdict
import logging

logger = logging.getLogger("patch_generator")

class PatchGenerator:
    """Convert feedback verdicts into Neo4j patches."""
    
    async def generate_patch(
        self,
        feedback_id: str,
        response_id: str,
        verdict: Verdict,
        query: str,
        llm_answer: str,
        retrieved_context: str,
        reviewer_id: str,
        reviewer_notes: str
    ) -> dict:
        """
        Generate patch from feedback verdict.
        
        Returns:
            Patch dict for storage in feedback_corrections table
        """
        
        logger.info(f"Generating patch for feedback {feedback_id}: {verdict}")
        
        if verdict == Verdict.CONFIRMED:
            # No patch needed, answer is correct
            return None
        
        elif verdict == Verdict.NEEDS_CORRECTION:
            # Analyze what needs fixing
            patch = await self._analyze_and_generate_correction(
                query, llm_answer, retrieved_context, reviewer_notes
            )
            return patch
        
        elif verdict == Verdict.PARTIALLY_CORRECT:
            # Mark for manual review, no auto patch
            return {
                "feedback_id": feedback_id,
                "response_id": response_id,
                "patch_type": "manual_review",
                "rationale": reviewer_notes,
                "approved_by": reviewer_id,
                "status": "pending_manual",
                "priority": "medium"
            }
        
        elif verdict == Verdict.AMBIGUOUS:
            # Requires HITL
            return {
                "feedback_id": feedback_id,
                "response_id": response_id,
                "patch_type": "ambiguous",
                "rationale": "Requires human expert decision",
                "status": "pending_hitl",
                "priority": "high"
            }
        
        return None
    
    async def _analyze_and_generate_correction(
        self,
        query: str,
        llm_answer: str,
        context: str,
        reviewer_notes: str
    ) -> dict:
        """Analyze error type and generate appropriate patch."""
        
        # Detect error type
        error_type = self._detect_error_type(llm_answer, reviewer_notes)
        
        if "numeric" in error_type:
            # Extract correct value from reviewer notes
            correct_value = self._extract_correct_value(reviewer_notes)
            return {
                "patch_type": "property_update",
                "error_type": "numeric_hallucination",
                "original_answer": llm_answer,
                "correct_value": correct_value,
                "rationale": reviewer_notes,
                "target_entity": self._extract_target_entity(query),
                "operation": {"corrected_value": correct_value},
                "status": "pending_validation",
                "priority": "high"
            }
        
        elif "relationship" in error_type:
            # Relationship/link error
            return {
                "patch_type": "relationship_correction",
                "error_type": "incorrect_link",
                "rationale": reviewer_notes,
                "status": "pending_validation",
                "priority": "high"
            }
        
        else:
            # General content error
            return {
                "patch_type": "entity_update",
                "error_type": "content_error",
                "original_answer": llm_answer,
                "rationale": reviewer_notes,
                "status": "pending_manual",
                "priority": "medium"
            }
    
    def _detect_error_type(self, answer: str, notes: str) -> str:
        """Detect type of error from answer and notes."""
        
        if any(word in notes.lower() for word in ["percent", "%", "crore", "number"]):
            return "numeric"
        
        if any(word in notes.lower() for word in ["link", "relation", "reference", "connected"]):
            return "relationship"
        
        return "content"
    
    def _extract_correct_value(self, notes: str) -> str:
        """Extract correct value from reviewer notes."""
        # Placeholder: could use regex to extract
        return notes
    
    def _extract_target_entity(self, query: str) -> str:
        """Extract entity being corrected from query."""
        # Placeholder: could use NER
        return "unknown_entity"
```

---

### Task 1.3: Answer Critic Integration
**Effort**: 2-3 days  
**Owner**: Backend Lead + ML Engineer  
**Dependency**: Phase 0 NLI evaluator  
**Blocking**: NO (enhancement)

#### 1.3.1 Answer Critic Service

**File**: `backend/app/evaluation/answer_critic.py` (ENHANCED)

```python
"""
LLM-as-Judge: Verify answer correctness before returning to user.
"""

import logging
from enum import Enum
from typing import Tuple

logger = logging.getLogger("answer_critic")

class CriticSeverity(str, Enum):
    SAFE = "safe"          # Can return
    WARNING = "warning"    # Return but mark as uncertain
    CRITICAL = "critical"  # Don't return, escalate

class AnswerCritic:
    """Critique generated answers for factual correctness."""
    
    def __init__(self, nli_evaluator, llm_client=None):
        self.nli_evaluator = nli_evaluator
        self.llm_client = llm_client  # For expensive checks
        
        # High-risk query patterns
        self.high_risk_patterns = [
            "investment limit",
            "annual return",
            "guaranteed",
            "regulatory requirement",
            "SEBI rule"
        ]
    
    async def critique(
        self,
        query: str,
        answer: str,
        context: str,
        intent: object
    ) -> Tuple[CriticSeverity, dict]:
        """
        Critique answer for correctness.
        
        Returns:
            (severity, critique_dict)
            severity: SAFE, WARNING, or CRITICAL
            critique_dict: {"score": 0-1, "issues": [...], "recommendation": ...}
        """
        
        # Check if high-risk query
        is_high_risk = any(
            pattern.lower() in query.lower()
            for pattern in self.high_risk_patterns
        )
        
        if is_high_risk:
            logger.info(f"High-risk query detected, triggering critic")
            return await self._critique_high_risk(query, answer, context)
        else:
            logger.debug(f"Low-risk query, lightweight critique")
            return await self._critique_lightweight(query, answer, context)
    
    async def _critique_high_risk(self, query: str, answer: str, context: str) -> Tuple[CriticSeverity, dict]:
        """Rigorous critique for high-risk queries."""
        
        # Use NLI + LLM
        nli_label, nli_conf = self.nli_evaluator.evaluate(context, answer)
        
        if nli_label == "contradiction" and nli_conf > 0.85:
            return CriticSeverity.CRITICAL, {
                "score": 0.1,
                "issues": ["Answer contradicts retrieved context"],
                "nli_label": nli_label,
                "nli_confidence": nli_conf,
                "recommendation": "Escalate to review queue"
            }
        
        # Rule-based checks for compliance claims
        if self._contains_risky_claims(answer):
            return CriticSeverity.WARNING, {
                "score": 0.5,
                "issues": ["Answer contains potentially risky claims"],
                "risky_claims": self._extract_risky_claims(answer),
                "recommendation": "Flag for review"
            }
        
        return CriticSeverity.SAFE, {
            "score": 0.9,
            "issues": [],
            "recommendation": "Safe to return"
        }
    
    async def _critique_lightweight(self, query: str, answer: str, context: str) -> Tuple[CriticSeverity, dict]:
        """Lightweight critique for low-risk queries."""
        
        # Just check basic rules
        if self._contains_risky_claims(answer):
            return CriticSeverity.WARNING, {
                "score": 0.6,
                "issues": ["Potential claims need verification"],
                "recommendation": "Mark uncertain"
            }
        
        return CriticSeverity.SAFE, {
            "score": 0.8,
            "issues": [],
            "recommendation": "Return"
        }
    
    def _contains_risky_claims(self, answer: str) -> bool:
        """Check for risky claims (e.g., guarantees)."""
        
        risky_patterns = [
            "guarantee",
            "guaranteed",
            "assured",
            "promise",
            "will definitely",
            "must return",
            "cannot lose"
        ]
        
        answer_lower = answer.lower()
        return any(pattern in answer_lower for pattern in risky_patterns)
    
    def _extract_risky_claims(self, answer: str) -> list:
        """Extract specific risky claims."""
        
        claims = []
        if "guarantee" in answer.lower():
            claims.append("Contains guarantee claim")
        if "%" in answer and any(word in answer.lower() for word in ["return", "profit"]):
            claims.append("Contains return percentage claim")
        
        return claims
```

#### 1.3.2 Orchestrator Integration

**File**: `backend/app/retrieval/orchestrator.py` (MODIFIED)

```python
# After synthesis, before cache storage:

comp_critic = ComponentMetric("answer_critic", time.perf_counter())

try:
    from app.evaluation.answer_critic import AnswerCritic
    
    critic = AnswerCritic(
        nli_evaluator=nli_evaluator,
        llm_client=self._synthesizer._llm
    )
    
    severity, critique = await critic.critique(
        query=effective_query,
        answer=synthesis.answer,
        context=context.context_text,
        intent=intent
    )
    
    comp_critic.metadata["severity"] = severity.value
    comp_critic.metadata["score"] = critique.get("score", 0.5)
    
    if severity == "critical":
        logger.warning(f"Answer critic flagged critical issue: {critique}")
        # Escalate to review queue
        await review_queue_manager.escalate(
            response_id=req_id,
            reason=f"Answer critic: {critique.get('issues', [''])[0]}",
            confidence_score=0.0  # Critical = low confidence
        )
        synthesis.confidence = "low"
    
    elif severity == "warning":
        synthesis.confidence = "medium"
        logger.info(f"Answer critic warning: {critique}")

except Exception as exc:
    logger.debug(f"Answer critic notice: {exc}")

comp_critic.finalize()
if metrics:
    metrics.add_component(comp_critic)
```

---

### Task 1.4: Orchestrator Refactoring
**Effort**: 1-2 days  
**Owner**: Backend Lead  
**Dependency**: Phase 0 + 1.1-1.3  
**Blocking**: NO (code quality)

#### 1.4.1 Extract Query Phases

**File**: `backend/app/retrieval/query_phases.py` (NEW)

```python
"""
Refactor orchestrator.answer() into discrete phases.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger("query_phases")

class QueryPhaseType(str, Enum):
    CACHE_LOOKUP = "cache_lookup"
    INTENT_CLASSIFICATION = "intent_classification"
    ENTITY_RESOLUTION = "entity_resolution"
    CYPHER_AGGREGATION = "cypher_aggregation"
    HYDE_EXPANSION = "hyde_expansion"
    RETRIEVAL = "retrieval"
    CONTEXT_ASSEMBLY = "context_assembly"
    SYNTHESIS = "synthesis"
    CRITIC = "critic"
    REVIEW_QUEUE = "review_queue"
    CACHE_STORAGE = "cache_storage"

class QueryPhase(ABC):
    """Base class for query execution phases."""
    
    def __init__(self, dependencies: Optional[list] = None):
        self.dependencies = dependencies or []
        self.result = None
        self.error = None
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute phase. Returns result dict."""
        pass

class CacheLookupPhase(QueryPhase):
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Phase: Cache Lookup")
        # Implementation
        pass

class IntentClassificationPhase(QueryPhase):
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Phase: Intent Classification")
        # Implementation
        pass

class EntityResolutionPhase(QueryPhase):
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Phase: Entity Resolution")
        # Implementation
        pass

# ... more phases

class QueryExecutionPipeline:
    """Execute query as series of phases."""
    
    def __init__(self):
        self.phases: Dict[QueryPhaseType, QueryPhase] = {}
        self._register_phases()
    
    def _register_phases(self):
        """Register all available phases."""
        self.phases[QueryPhaseType.CACHE_LOOKUP] = CacheLookupPhase()
        self.phases[QueryPhaseType.INTENT_CLASSIFICATION] = IntentClassificationPhase()
        # ... register others
    
    async def execute(self, query: str) -> Dict[str, Any]:
        """Execute full pipeline."""
        
        context = {"query": query}
        phase_order = [
            QueryPhaseType.CACHE_LOOKUP,
            QueryPhaseType.INTENT_CLASSIFICATION,
            QueryPhaseType.ENTITY_RESOLUTION,
            # ...
        ]
        
        for phase_type in phase_order:
            phase = self.phases[phase_type]
            try:
                phase_result = await phase.execute(context)
                context[phase_type.value] = phase_result
                
                # Check for early exit (e.g., cache hit)
                if context.get("cache_hit"):
                    logger.info("Cache hit, skipping remaining phases")
                    break
            
            except Exception as exc:
                logger.error(f"Phase {phase_type} failed: {exc}")
                context["error"] = str(exc)
                break
        
        return context
```

---

## PHASE 2: Scale & Enterprise (Weeks 3-4)

[Continuing with detailed Phase 2 implementation including Redis caching, multi-tenant architecture, Langfuse integration, and React frontend migration planning...]

---

## Summary: Complete Roadmap

| Phase | Tasks | Effort | Timeline | Dependencies |
|-------|-------|--------|----------|--------------|
| **Phase 0** | Review queue, NLI, scheduler, validation | 8-9 days | Week 1-2 | None |
| **Phase 1.1** | Multi-round retrieval | 2-3 days | Week 3 | Phase 0 |
| **Phase 1.2** | Governance batch | 2-3 days | Week 3 | Phase 0 + Feedback |
| **Phase 1.3** | Answer critic | 2-3 days | Week 3 | Phase 0 |
| **Phase 1.4** | Orchestrator refactor | 1-2 days | Week 4 | Phase 1.1-1.3 |
| **Phase 2.1** | Redis caching | 3-4 days | Week 4+ | Phase 0 |
| **Phase 2.2** | Multi-tenant | 4-5 days | Week 5+ | Phase 0 |
| **Phase 2.3** | Langfuse | 2-3 days | Week 5+ | Phase 0 |
| **Phase 2.4** | React frontend | 10-15 days | Week 6+ | Phase 0-1 |

**Total Timeline to Full Implementation**: 8-10 weeks

---

## Testing Strategy

### Unit Tests
- Phase-specific unit tests (>85% coverage)
- Mock external services (LLM, Neo4j)

### Integration Tests
- Phase interactions
- End-to-end flows
- Performance benchmarks

### Staging Validation
- Full load testing
- Chaos engineering
- Rollback verification

### Production Canary
- Deploy to 10% of traffic
- Monitor metrics closely
- Gradual ramp-up

---

## Deployment Strategy

### Pre-Deployment
1. Verify Phase 0 readiness checklist
2. Run full test suite
3. Staging validation
4. Operator training

### Deployment Day
1. Blue-green deployment (old instance stays up)
2. Route 10% traffic to green
3. Monitor metrics for 30 minutes
4. Ramp up gradually to 100%
5. Keep blue instance for 1 hour rollback window

### Post-Deployment
1. Monitor production metrics
2. Validate baseline matches benchmarks
3. Alert on any anomalies
4. Begin Phase 1 work immediately

---

**END OF PHASE 1 & 2 DETAILS**

*See main DETAILED_IMPLEMENTATION_PLAN.md for Phase 0 complete specifications*
