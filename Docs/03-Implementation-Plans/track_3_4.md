I'm a planning agent - I can read and analyze code but not modify it. I can help you plan the implementation instead.

Let me create a comprehensive implementation plan for Tracks 3-8 with detailed requirements, technical specifications, and task breakdowns.Perfect! Now I have context about the existing Neo4j implementation. Let me create a comprehensive implementation plan for Tracks 3-8.

---

# **DETAILED IMPLEMENTATION PLAN: TRACKS 3-8**
## **Independent Feedback Loop Module - Foundation Components**

---

## **TRACK 3: CYPHER QUERY SAFETY LAYER** 
**Priority: P0 - BLOCKING | Duration: 3 days | Owner: Graph/Security Team**

### **Problem Statement**
Current `graph_store.py` has basic write-keyword blocking (`_WRITE_KEYWORDS`, `_CALL_KEYWORD`), but Keerthi's design requires production-grade safety for user-facing feedback evaluation queries that will run at scale. Prior audit identified Cypher injection as a Phase 0 blocker.

### **Requirements**

**Functional:**
1. Parameterized query builder preventing SQL-injection-style attacks
2. Whitelist validation for entity IDs and attribute names
3. Query complexity limits (max depth, max returned rows, timeout)
4. Audit logging for all Cypher queries executed via feedback evaluation
5. Read-only enforcement for evaluation queries (existing `_WRITE_KEYWORDS` is good baseline)

**Non-Functional:**
- Query execution time <200ms for 95th percentile
- Support 1000+ concurrent evaluation queries (horizontal scaling via connection pooling)
- Audit log retention: 90 days minimum for compliance

### **Proposed Solution**

Create a three-layer defense:
1. **Input Validation Layer** - Whitelist checks before query construction
2. **Parameterized Query Builder** - Zero string concatenation
3. **Execution Safety Layer** - Timeouts, row limits, audit logging

### **Task Breakdown**

#### **Task 3.1: Create SafeCypherBuilder Class** (8 hours)

**Files to Create:**
- `backend/app/graph/safe_cypher_builder.py`
- `backend/app/graph/cypher_validators.py`
- `backend/tests/test_safe_cypher.py`

**Implementation:**

```python
# backend/app/graph/safe_cypher_builder.py

from typing import Any, Dict, List, Optional
import re
import logging
from datetime import datetime
from neo4j import GraphDatabase, Session

logger = logging.getLogger("app.graph.safe_cypher")

class CypherSecurityError(Exception):
    """Raised when a query fails security validation."""
    pass

class SafeCypherBuilder:
    """
    Parameterized Cypher query builder preventing injection attacks.
    All user-controlled inputs are validated and parameterized.
    """
    
    # Whitelist: valid entity attributes for AMC domain
    VALID_ATTRIBUTES = {
        "TER", "NAV", "AUM", "expense_ratio", "5yr_return", 
        "3yr_return", "1yr_return", "inception_date", "fund_manager",
        "benchmark", "risk_grade", "exit_load", "minimum_investment"
    }
    
    # Whitelist: valid entity types/labels
    VALID_LABELS = {
        "Entity", "ISIN", "FUND", "REGULATOR", "SCHEME_CLASS",
        "AMC", "BENCHMARK_INDEX", "MUTUAL_FUND_SCHEME_NAME"
    }
    
    # Whitelist: valid relationship types
    VALID_REL_TYPES = {
        "HAS_FACT", "HAS_BENCHMARK", "MANAGED_BY", "REGULATED_BY",
        "GOVERNS", "BELONGS_TO", "COMPARED_WITH"
    }
    
    def __init__(self, session: Session, max_rows: int = 100, timeout_seconds: int = 10):
        self.session = session
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds
    
    def validate_entity_id(self, entity_id: str) -> str:
        """
        Validate entity ID format.
        For ISIN: alphanumeric 12 chars (e.g., INF846K01DP5)
        For dedup_key: label::text format
        """
        if not entity_id or not isinstance(entity_id, str):
            raise CypherSecurityError(f"Invalid entity_id: {entity_id}")
        
        # ISIN format
        if re.match(r'^[A-Z]{2}[A-Z0-9]{10}$', entity_id):
            return entity_id
        
        # Dedup key format (label::text)
        if re.match(r'^[a-zA-Z_]+::[a-z0-9\s\-]+$', entity_id):
            return entity_id
        
        # Generic alphanumeric with underscore/hyphen
        if re.match(r'^[a-zA-Z0-9_\-]{1,100}$', entity_id):
            return entity_id
        
        raise CypherSecurityError(
            f"Entity ID '{entity_id}' failed whitelist validation. "
            "Allowed: ISIN format, dedup_key format, or alphanumeric with _-"
        )
    
    def validate_attribute(self, attribute: str) -> str:
        """Validate attribute name against whitelist."""
        if attribute not in self.VALID_ATTRIBUTES:
            raise CypherSecurityError(
                f"Attribute '{attribute}' not in whitelist. "
                f"Allowed: {sorted(self.VALID_ATTRIBUTES)}"
            )
        return attribute
    
    def validate_label(self, label: str) -> str:
        """Validate node label against whitelist."""
        if label not in self.VALID_LABELS:
            raise CypherSecurityError(
                f"Label '{label}' not in whitelist. "
                f"Allowed: {sorted(self.VALID_LABELS)}"
            )
        return label
    
    def get_entity_facts(
        self,
        entity_id: str,
        fact_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve facts for an entity (safe parameterized query).
        
        Example:
            builder.get_entity_facts("INF846K01DP5", fact_type="TER")
        
        Returns:
            [{"attribute": "TER", "value": "0.82", "source": "AMFI_v18", ...}]
        """
        # Validate inputs
        safe_entity_id = self.validate_entity_id(entity_id)
        if fact_type:
            safe_fact_type = self.validate_attribute(fact_type)
        
        # Build parameterized query
        query = """
        MATCH (e:Entity {dedup_key: $entity_id})-[:HAS_FACT]->(f:Fact)
        WHERE $fact_type IS NULL OR f.attribute = $fact_type
        RETURN 
            f.attribute AS attribute,
            f.value AS value,
            f.source AS source,
            f.effective_date AS effective_date,
            f.confidence AS confidence
        ORDER BY f.effective_date DESC
        LIMIT $limit
        """
        
        result_limit = min(limit or self.max_rows, self.max_rows)
        
        # Execute with audit logging
        start_time = datetime.utcnow()
        try:
            result = self.session.run(
                query,
                parameters={
                    "entity_id": safe_entity_id,
                    "fact_type": fact_type if fact_type else None,
                    "limit": result_limit
                },
                timeout=self.timeout_seconds
            )
            
            rows = [dict(record) for record in result]
            
            # Audit log
            logger.info(
                "SafeCypher executed: get_entity_facts | "
                f"entity={safe_entity_id} | fact_type={fact_type} | "
                f"rows_returned={len(rows)} | "
                f"duration_ms={(datetime.utcnow() - start_time).total_seconds() * 1000:.2f}"
            )
            
            return rows
        
        except Exception as exc:
            logger.error(
                f"SafeCypher failed: get_entity_facts | "
                f"entity={safe_entity_id} | error={exc}",
                exc_info=True
            )
            raise
    
    def compare_entity_attributes(
        self,
        entity_ids: List[str],
        attributes: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Compare specific attributes across multiple entities.
        
        Example:
            builder.compare_entity_attributes(
                entity_ids=["INF846K01DP5", "INF769K01EW8"],
                attributes=["TER", "NAV", "5yr_return"]
            )
        
        Returns:
            [
                {"entity_id": "INF846K01DP5", "attribute": "TER", "value": "0.82", ...},
                {"entity_id": "INF769K01EW8", "attribute": "TER", "value": "0.75", ...},
                ...
            ]
        """
        # Validate inputs
        safe_entity_ids = [self.validate_entity_id(eid) for eid in entity_ids]
        safe_attributes = [self.validate_attribute(attr) for attr in attributes]
        
        if len(safe_entity_ids) > 10:
            raise CypherSecurityError("Maximum 10 entities allowed for comparison")
        
        query = """
        UNWIND $entity_ids AS entity_id
        MATCH (e:Entity {dedup_key: entity_id})-[:HAS_FACT]->(f:Fact)
        WHERE f.attribute IN $attributes
        RETURN 
            entity_id,
            e.text AS entity_name,
            f.attribute AS attribute,
            f.value AS value,
            f.source AS source,
            f.effective_date AS effective_date
        ORDER BY entity_id, f.attribute
        """
        
        start_time = datetime.utcnow()
        try:
            result = self.session.run(
                query,
                parameters={
                    "entity_ids": safe_entity_ids,
                    "attributes": safe_attributes
                },
                timeout=self.timeout_seconds
            )
            
            rows = [dict(record) for record in result]
            
            logger.info(
                f"SafeCypher executed: compare_entity_attributes | "
                f"entities={len(safe_entity_ids)} | attributes={len(safe_attributes)} | "
                f"rows_returned={len(rows)} | "
                f"duration_ms={(datetime.utcnow() - start_time).total_seconds() * 1000:.2f}"
            )
            
            return rows
        
        except Exception as exc:
            logger.error(
                f"SafeCypher failed: compare_entity_attributes | error={exc}",
                exc_info=True
            )
            raise
    
    def get_correction_candidates(
        self,
        entity_id: str,
        attribute: str,
        feedback_value: Any
    ) -> Dict[str, Any]:
        """
        Retrieve current canonical value vs feedback-asserted value.
        Used for correction evaluation.
        
        Returns:
            {
                "entity_id": "INF846K01DP5",
                "attribute": "TER",
                "canonical_value": "0.82",
                "canonical_source": "AMFI_v18",
                "canonical_effective_date": "2026-08-17",
                "feedback_asserted_value": "0.79",
                "mismatch": True
            }
        """
        safe_entity_id = self.validate_entity_id(entity_id)
        safe_attribute = self.validate_attribute(attribute)
        
        query = """
        MATCH (e:Entity {dedup_key: $entity_id})-[:HAS_FACT]->(f:Fact {attribute: $attribute})
        RETURN 
            f.value AS canonical_value,
            f.source AS canonical_source,
            f.effective_date AS canonical_effective_date,
            f.confidence AS canonical_confidence
        ORDER BY f.effective_date DESC
        LIMIT 1
        """
        
        result = self.session.run(
            query,
            parameters={
                "entity_id": safe_entity_id,
                "attribute": safe_attribute
            },
            timeout=self.timeout_seconds
        )
        
        record = result.single()
        if not record:
            return {
                "entity_id": safe_entity_id,
                "attribute": safe_attribute,
                "canonical_value": None,
                "feedback_asserted_value": feedback_value,
                "mismatch": None,
                "error": "No canonical value found"
            }
        
        canonical = dict(record)
        return {
            "entity_id": safe_entity_id,
            "attribute": safe_attribute,
            "canonical_value": canonical["canonical_value"],
            "canonical_source": canonical["canonical_source"],
            "canonical_effective_date": canonical["canonical_effective_date"],
            "canonical_confidence": canonical["canonical_confidence"],
            "feedback_asserted_value": feedback_value,
            "mismatch": str(canonical["canonical_value"]) != str(feedback_value)
        }
```

**Demo:** After completing this task, the system can execute:
```python
from app.graph.safe_cypher_builder import SafeCypherBuilder

with neo4j_session() as session:
    builder = SafeCypherBuilder(session)
    
    # Safe parameterized query
    facts = builder.get_entity_facts("INF846K01DP5", fact_type="TER")
    print(facts)  # [{"attribute": "TER", "value": "0.82", ...}]
    
    # Injection attempt blocked
    try:
        builder.get_entity_facts("'; DROP TABLE Entity;--")
    except CypherSecurityError as e:
        print(f"Blocked: {e}")  # Entity ID validation failed
```

---

#### **Task 3.2: Integrate SafeCypherBuilder into Existing graph_store.py** (4 hours)

**Refactor `run_safe_cypher()` function:**

```python
# streamlit_app/graph_store.py (UPDATE)

from backend.app.graph.safe_cypher_builder import SafeCypherBuilder, CypherSecurityError

def run_safe_cypher(cypher: str, max_rows: int = 25) -> List[Dict]:
    """
    UPDATED: Enhanced safety validation + audit logging.
    Executes LLM-generated read-only Cypher with strict validation.
    """
    cypher = cypher.strip()
    
    # Existing write keyword checks (keep these)
    if _WRITE_KEYWORDS.search(cypher):
        raise ValueError("Write operations not allowed")
    if _CALL_KEYWORD.search(cypher):
        raise ValueError("CALL procedures blocked")
    
    # NEW: Complexity checks
    if cypher.count("MATCH") > 3:
        raise ValueError("Max 3 MATCH clauses allowed")
    if cypher.count("OPTIONAL MATCH") > 2:
        raise ValueError("Max 2 OPTIONAL MATCH clauses")
    if "UNION" in cypher.upper():
        raise ValueError("UNION queries not supported")
    
    driver = get_driver()
    with driver.session(database=config.NEO4J_DATABASE) as session:
        try:
            # Execute with timeout
            result = session.run(cypher, timeout=10)
            rows = [dict(rec) for rec in result][:max_rows]
            
            # Audit log
            logger.info(
                f"run_safe_cypher executed | "
                f"rows_returned={len(rows)} | "
                f"query_preview={cypher[:100]}..."
            )
            
            return rows
        except Exception as exc:
            logger.error(f"run_safe_cypher failed: {exc}", exc_info=True)
            return []
```

**Demo:** Existing `text_to_cypher.py` LLM-generated queries now have enhanced safety validation.

---

#### **Task 3.3: Add Cypher Audit Logging** (3 hours)

**Create audit logger:**

```python
# backend/app/graph/cypher_audit_log.py

import logging
from datetime import datetime
from typing import Optional
import json

class CypherAuditLogger:
    """
    Compliance audit trail for all Cypher queries executed via feedback evaluation.
    Logs to dedicated file for 90-day retention.
    """
    
    def __init__(self, log_file: str = "logs/cypher_audit.jsonl"):
        self.logger = logging.getLogger("cypher_audit")
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_query(
        self,
        query_method: str,
        parameters: dict,
        rows_returned: int,
        duration_ms: float,
        user_context: Optional[dict] = None,
        error: Optional[str] = None
    ):
        """
        Log every Cypher query execution.
        """
        audit_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "query_method": query_method,
            "parameters": parameters,
            "rows_returned": rows_returned,
            "duration_ms": duration_ms,
            "user_context": user_context or {},
            "error": error,
            "success": error is None
        }
        
        self.logger.info(json.dumps(audit_record))
```

**Integration:** Update `SafeCypherBuilder` methods to call `CypherAuditLogger.log_query()` after each execution.

**Demo:** Audit log file contains:
```json
{"timestamp": "2026-09-10T14:32:15Z", "query_method": "get_entity_facts", "parameters": {"entity_id": "INF846K01DP5", "fact_type": "TER"}, "rows_returned": 1, "duration_ms": 12.3, "success": true}
{"timestamp": "2026-09-10T14:33:02Z", "query_method": "compare_entity_attributes", "parameters": {"entity_ids": ["INF846K01DP5", "INF769K01EW8"], "attributes": ["TER", "NAV"]}, "rows_returned": 4, "duration_ms": 18.7, "success": true}
```

---

#### **Task 3.4: Unit Tests for SafeCypherBuilder** (4 hours)

**Create test suite:**

```python
# backend/tests/test_safe_cypher.py

import pytest
from app.graph.safe_cypher_builder import SafeCypherBuilder, CypherSecurityError

def test_validate_entity_id_valid_isin():
    builder = SafeCypherBuilder(mock_session())
    assert builder.validate_entity_id("INF846K01DP5") == "INF846K01DP5"

def test_validate_entity_id_injection_attempt():
    builder = SafeCypherBuilder(mock_session())
    with pytest.raises(CypherSecurityError):
        builder.validate_entity_id("'; DROP TABLE Entity;--")

def test_validate_attribute_whitelist():
    builder = SafeCypherBuilder(mock_session())
    assert builder.validate_attribute("TER") == "TER"
    
    with pytest.raises(CypherSecurityError):
        builder.validate_attribute("malicious_field")

def test_get_entity_facts_parameterization(mock_neo4j_session):
    builder = SafeCypherBuilder(mock_neo4j_session)
    
    # Mock should verify parameters, not string concatenation
    builder.get_entity_facts("INF846K01DP5", fact_type="TER")
    
    mock_neo4j_session.run.assert_called_once()
    call_args = mock_neo4j_session.run.call_args
    assert "parameters" in call_args.kwargs
    assert call_args.kwargs["parameters"]["entity_id"] == "INF846K01DP5"
```

**Demo:** Run `pytest backend/tests/test_safe_cypher.py -v` → All 15+ tests pass, injection attempts blocked.

---

### **Success Criteria (Track 3)**

✅ All Neo4j queries from feedback evaluation use `SafeCypherBuilder`  
✅ Zero successful Cypher injection attacks in penetration testing  
✅ All queries logged to audit trail with 90-day retention  
✅ Query timeout enforced at 10 seconds  
✅ Max 100 rows returned per query  
✅ Whitelist validation prevents unauthorized entity/attribute access  

---

## **TRACK 4: DISSATISFACTION DETECTION MODULE**
**Priority: P1 | Duration: 4 days | Owner: ML/NLP Team**

### **Problem Statement**
When a user's follow-up query is actually a correction attempt ("That's wrong, TER is 0.82%"), the system must detect it and convert to structured feedback. Keerthi's Step FD requires frustration detection + same-referent check + correction extraction.

### **Requirements**

**Functional:**
1. Sentiment analysis to detect frustration/dissatisfaction
2. Embedding similarity to confirm follow-up references same topic
3. Pattern matching for correction language ("actually", "should be", "wrong")
4. Structured claim extraction from free text
5. False positive rate <10% (don't treat genuine clarifications as corrections)

**Non-Functional:**
- Latency <100ms for 95th percentile
- Support English + financial domain terminology
- Graceful degradation if ML models unavailable (skip detection, don't block)

### **Proposed Solution**

Three-stage pipeline:
1. **Sentiment Classification** - Detect negative sentiment (VADER or transformer model)
2. **Topic Similarity** - Embedding cosine similarity between follow-up and original query
3. **Correction Extraction** - Regex + NER to extract asserted values

### **Task Breakdown**

#### **Task 4.1: Create DissatisfactionDetector Class** (10 hours)

**Files to Create:**
- `backend/app/feedback/dissatisfaction_detector.py`
- `backend/app/feedback/correction_extractor.py`
- `backend/tests/test_dissatisfaction_detector.py`

**Implementation:**

```python
# backend/app/feedback/dissatisfaction_detector.py

from typing import Optional, Tuple
import re
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Lightweight sentiment (consider replacing with transformers model for production)
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    vader_available = True
except ImportError:
    vader_available = False

@dataclass
class StructuredClaim:
    """Structured correction claim extracted from follow-up."""
    entity_id: Optional[str]
    entity_name: Optional[str]
    attribute: Optional[str]
    asserted_value: Optional[str]
    rejected_value: Optional[str]
    raw_text: str
    confidence: float  # 0.0 to 1.0

class DissatisfactionDetector:
    """
    Detects when a follow-up query is actually a correction attempt.
    Implements Keerthi's Step FD logic.
    """
    
    # Configurable thresholds (from Keerthi's gap analysis)
    DEFAULT_SENTIMENT_THRESHOLD = -0.4  # More negative = dissatisfied
    DEFAULT_SIMILARITY_THRESHOLD = 0.75  # 0.75 = same topic
    DEFAULT_INTENT_CONFIDENCE_THRESHOLD = 0.65
    
    # Correction language patterns
    CORRECTION_PATTERNS = [
        r"\b(wrong|incorrect|not right|mistake|error)\b",
        r"\b(actually|should be|correct answer is|real value is)\b",
        r"\b(that'?s? not|no,|not true)\b",
        r"\b(check|verify|look again|re-check)\b",
        r"\b(my records show|according to|source says)\b"
    ]
    
    def __init__(
        self,
        sentiment_threshold: float = DEFAULT_SENTIMENT_THRESHOLD,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        intent_confidence_threshold: float = DEFAULT_INTENT_CONFIDENCE_THRESHOLD
    ):
        self.sentiment_threshold = sentiment_threshold
        self.similarity_threshold = similarity_threshold
        self.intent_confidence_threshold = intent_confidence_threshold
        
        # Load models
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")  # 384-dim, fast
        
        if vader_available:
            self.sentiment_analyzer = SentimentIntensityAnalyzer()
        else:
            self.sentiment_analyzer = None
            print("VADER not available, using fallback sentiment detection")
    
    def _detect_frustration(self, text: str) -> Tuple[bool, float]:
        """
        Returns (is_frustrated, sentiment_score).
        Score: -1.0 (very negative) to +1.0 (very positive)
        """
        if self.sentiment_analyzer:
            scores = self.sentiment_analyzer.polarity_scores(text)
            compound = scores["compound"]
            is_frustrated = compound < self.sentiment_threshold
            return is_frustrated, compound
        else:
            # Fallback: simple keyword matching
            negative_keywords = ["wrong", "incorrect", "not", "no", "error", "mistake"]
            count = sum(1 for kw in negative_keywords if kw in text.lower())
            fallback_score = -0.1 * count  # rough approximation
            is_frustrated = fallback_score < self.sentiment_threshold
            return is_frustrated, fallback_score
    
    def _check_same_referent(
        self,
        follow_up_query: str,
        original_query: str
    ) -> Tuple[bool, float]:
        """
        Returns (same_topic, similarity_score).
        Uses embedding cosine similarity.
        """
        follow_emb = self.embedder.encode(follow_up_query)
        orig_emb = self.embedder.encode(original_query)
        
        similarity = cosine_similarity(
            [follow_emb], [orig_emb]
        )[0][0]
        
        same_topic = similarity >= self.similarity_threshold
        return same_topic, float(similarity)
    
    def _has_correction_language(self, text: str) -> Tuple[bool, float]:
        """
        Returns (has_correction_intent, confidence).
        Confidence based on pattern matches.
        """
        text_lower = text.lower()
        matches = 0
        for pattern in self.CORRECTION_PATTERNS:
            if re.search(pattern, text_lower):
                matches += 1
        
        # Confidence scales with number of matched patterns
        confidence = min(matches * 0.3, 1.0)  # Max 3 patterns = 0.9 confidence
        has_intent = confidence >= self.intent_confidence_threshold
        
        return has_intent, confidence
    
    def is_correction_attempt(
        self,
        follow_up_query: str,
        original_response: str,
        original_query: str
    ) -> Tuple[bool, Optional[StructuredClaim]]:
        """
        Main entry point: Detect if follow-up is a correction.
        
        Returns:
            (is_correction, structured_claim_or_none)
        
        Example:
            detector.is_correction_attempt(
                follow_up_query="That's wrong, TER is 0.82% not 0.79%",
                original_response="The TER is 0.79%",
                original_query="What is the TER of Axis Bluechip Fund?"
            )
            → (True, StructuredClaim(...))
        """
        # 1. Frustration check
        is_frustrated, sentiment_score = self._detect_frustration(follow_up_query)
        
        # 2. Same referent check
        same_topic, similarity_score = self._check_same_referent(
            follow_up_query, original_query
        )
        
        # 3. Correction language check
        has_correction_lang, intent_confidence = self._has_correction_language(
            follow_up_query
        )
        
        # Decision: ALL three must be true
        is_correction = is_frustrated and same_topic and has_correction_lang
        
        if not is_correction:
            return False, None
        
        # 4. Extract structured claim
        from app.feedback.correction_extractor import CorrectionExtractor
        extractor = CorrectionExtractor()
        
        claim = extractor.extract_claim(
            feedback_text=follow_up_query,
            original_response=original_response,
            original_query=original_query
        )
        
        if claim:
            # Add detection metadata
            claim.confidence = min(
                claim.confidence,
                (abs(sentiment_score) + similarity_score + intent_confidence) / 3
            )
        
        return True, claim
```

```python
# backend/app/feedback/correction_extractor.py

import re
from typing import Optional, List, Tuple
import spacy
from dataclasses import dataclass

@dataclass
class StructuredClaim:
    entity_id: Optional[str]
    entity_name: Optional[str]
    attribute: Optional[str]
    asserted_value: Optional[str]
    rejected_value: Optional[str]
    raw_text: str
    confidence: float

class CorrectionExtractor:
    """
    Extracts structured claims from correction feedback.
    
    Example:
        "TER should be 0.82% not 0.79%" 
        → {attribute: "TER", asserted_value: "0.82%", rejected_value: "0.79%"}
    """
    
    def __init__(self):
        # Load spaCy for NER
        self.nlp = spacy.load("en_core_web_sm")
        
        # AMC attribute keywords
        self.attribute_keywords = {
            "ter": ["ter", "expense ratio", "total expense"],
            "nav": ["nav", "net asset value"],
            "return": ["return", "cagr", "performance"],
            "aum": ["aum", "assets under management"],
            "exit_load": ["exit load", "redemption charge"],
            "minimum_investment": ["minimum investment", "min investment"]
        }
    
    def _extract_numbers(self, text: str) -> List[float]:
        """
        Extract numeric values from text.
        Handles: percentages, currency, decimals.
        """
        # Pattern: optional ₹ or Rs, digits with optional decimal, optional %
        pattern = r"(?:₹|Rs\.?\s*)?(\d+(?:\.\d+)?)\s*%?"
        matches = re.findall(pattern, text)
        return [float(m) for m in matches]
    
    def _detect_attribute(self, text: str) -> Optional[str]:
        """
        Detect which attribute the feedback is about.
        """
        text_lower = text.lower()
        for attr_key, keywords in self.attribute_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return attr_key
        return None
    
    def extract_claim(
        self,
        feedback_text: str,
        original_response: str,
        original_query: str
    ) -> Optional[StructuredClaim]:
        """
        Extract structured claim from correction feedback.
        
        Returns None if extraction fails.
        """
        # Extract numbers
        feedback_numbers = self._extract_numbers(feedback_text)
        response_numbers = self._extract_numbers(original_response)
        
        # Detect attribute
        attribute = self._detect_attribute(feedback_text) or self._detect_attribute(original_query)
        
        if not attribute or len(feedback_numbers) == 0:
            # Can't extract enough structure
            return None
        
        # Heuristic: first number in feedback is asserted value
        asserted_value = feedback_numbers[0]
        
        # If feedback mentions two numbers, second is likely the rejected value
        # Example: "should be 0.82% not 0.79%" → asserted=0.82, rejected=0.79
        rejected_value = feedback_numbers[1] if len(feedback_numbers) > 1 else None
        
        # If no rejected value in feedback, try to extract from original response
        if not rejected_value and response_numbers:
            rejected_value = response_numbers[0]
        
        # Entity extraction (simplified - would use fund name matcher in production)
        doc = self.nlp(original_query)
        entity_name = None
        for ent in doc.ents:
            if ent.label_ == "ORG" and "fund" in ent.text.lower():
                entity_name = ent.text
                break
        
        # Confidence based on completeness
        confidence = 0.6  # Base
        if rejected_value:
            confidence += 0.2
        if entity_name:
            confidence += 0.2
        
        return StructuredClaim(
            entity_id=None,  # Would be resolved via fund name matcher
            entity_name=entity_name,
            attribute=attribute,
            asserted_value=str(asserted_value),
            rejected_value=str(rejected_value) if rejected_value else None,
            raw_text=feedback_text,
            confidence=confidence
        )
```

**Demo:** After completing this task:
```python
detector = DissatisfactionDetector()

is_correction, claim = detector.is_correction_attempt(
    follow_up_query="That's completely wrong! TER is 0.82%, not 0.79%",
    original_response="The TER for Axis Bluechip Fund Direct Growth is 0.79%",
    original_query="What is the TER of Axis Bluechip Fund?"
)

print(is_correction)  # True
print(claim.attribute)  # "ter"
print(claim.asserted_value)  # "0.82"
print(claim.rejected_value)  # "0.79"
```

---

#### **Task 4.2: Integrate into Feedback API** (4 hours)

**Add follow-up detection endpoint:**

```python
# backend/app/api/routes/feedback.py (ADD NEW ENDPOINT)

from app.feedback.dissatisfaction_detector import DissatisfactionDetector, StructuredClaim

@router.post("/follow-up-detection")
def detect_follow_up_correction(
    session_id: str,
    previous_response_id: str,
    follow_up_query: str,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Detect if a follow-up query is actually a correction attempt.
    If detected, auto-converts to structured feedback.
    """
    # Fetch previous interaction from master_interactions table
    store = get_feedback_store()
    prev_interaction = store.get_interaction(session_id, previous_response_id)
    
    if not prev_interaction:
        raise HTTPException(status_code=404, detail="Previous interaction not found")
    
    detector = DissatisfactionDetector()
    
    is_correction, claim = detector.is_correction_attempt(
        follow_up_query=follow_up_query,
        original_response=prev_interaction["response_text"],
        original_query=prev_interaction["query_text"]
    )
    
    if is_correction and claim:
        # Auto-convert to structured feedback
        store.update_interaction_feedback(
            session_id=session_id,
            response_id=previous_response_id,
            feedback_data={
                "feedback_type": "dissatisfaction_followup",
                "feedback_text": claim.raw_text,
                "selected_categories": [f"F08"],  # Numeric accuracy
                "structured_claim": claim.__dict__,
                "actor_id": current_role.value,
                "evaluation_status": "pending"
            }
        )
        
        return {
            "correction_detected": True,
            "feedback_created": True,
            "claim": claim.__dict__
        }
    
    return {
        "correction_detected": False,
        "feedback_created": False
    }
```

**Demo:** User types follow-up "That's wrong, TER is 0.82%" → System auto-creates feedback record with structured claim.

---

#### **Task 4.3: Unit Tests** (3 hours)

```python
# backend/tests/test_dissatisfaction_detector.py

def test_detect_correction_with_clear_signals():
    detector = DissatisfactionDetector()
    
    is_correction, claim = detector.is_correction_attempt(
        follow_up_query="No that's incorrect! TER is 0.82% not 0.79%",
        original_response="The TER is 0.79%",
        original_query="What is the TER of Axis Bluechip Fund?"
    )
    
    assert is_correction == True
    assert claim.attribute == "ter"
    assert claim.asserted_value == "0.82"
    assert claim.rejected_value == "0.79"

def test_no_false_positive_on_clarification():
    detector = DissatisfactionDetector()
    
    is_correction, claim = detector.is_correction_attempt(
        follow_up_query="Can you also tell me the NAV?",
        original_response="The TER is 0.82%",
        original_query="What is the TER?"
    )
    
    assert is_correction == False  # This is a clarification, not correction

def test_sentiment_threshold_adjustment():
    # User wants stricter threshold
    detector = DissatisfactionDetector(sentiment_threshold=-0.6)
    
    # Mildly negative feedback should not trigger
    is_correction, _ = detector.is_correction_attempt(
        follow_up_query="I think TER might be 0.82%",  # Not strongly negative
        original_response="The TER is 0.79%",
        original_query="What is the TER?"
    )
    
    assert is_correction == False
```

**Demo:** Run tests → 95% detection accuracy on test set, <10% false positives.

---

### **Success Criteria (Track 4)**

✅ Dissatisfaction detection integrated into feedback API  
✅ >90% detection rate on correction attempts  
✅ <10% false positive rate (genuine clarifications not flagged)  
✅ Structured claims extracted with entity, attribute, asserted value  
✅ Latency <100ms for 95th percentile  
✅ Graceful degradation if ML models unavailable  

---

Due to length constraints, I'll provide a structured outline for the remaining tracks. Would you like me to continue with the detailed implementation plans for **Tracks 5-8** in the same format?

The remaining tracks are:
- **Track 5**: Deterministic Evaluation Rules (Tier 1A)
- **Track 6**: Correction Patch Layer (Shadow Graph)
- **Track 7**: Human Governance Review Queue UI
- **Track 8**: NER + Entity Resolution for Feedback

Should I proceed with detailed breakdowns for these tracks?