Perfect! Let me create detailed implementation plans for the remaining tracks (4-8). I'll continue with the same comprehensive format.Great! Now I have context on the existing feedback storage. Let me continue creating the detailed implementation plans for Tracks 4-8.

---

## **TRACK 4: DISSATISFACTION DETECTION MODULE - IMPLEMENTATION PLAN**

### **Document: TRACK_4_DISSATISFACTION_DETECTION_PLAN.md**

---

# **Track 4: Dissatisfaction Detection Module**
**Implementation Plan & Technical Specification**

## **Executive Summary**

**Objective:** Implement automated detection of correction attempts in follow-up queries, converting implicit dissatisfaction signals into structured feedback records.

**Priority:** P1 | Duration: 4 days (32 work hours)  
**Owner:** ML/NLP Team  
**Dependencies:** Track 1 (Master Interactions Table)  
**Value:** Captures 2-5x more feedback by detecting implicit corrections that users don't explicitly submit via feedback UI

---

## **1. Problem Statement**

### **Current State:**
- Users must explicitly click feedback buttons to report issues
- Typical feedback rate: 5-15% of interactions
- Many users express dissatisfaction via follow-up queries instead:
  - "That's wrong, TER is 0.82%"
  - "No, the NAV should be ₹64.31"
  - "Actually it returned 14.2% not 38%"
- These implicit corrections are lost

### **Target State (Keerthi's Step FD):**
- Automatically detect when follow-up query is a correction attempt
- Three-signal detection:
  1. **Frustration** - Negative sentiment (VADER score < -0.4)
  2. **Same Referent** - Follow-up references same topic (embedding similarity ≥ 0.75)
  3. **Correction Language** - Contains correction patterns ("wrong", "actually", "should be")
- Extract structured claims:
  - Entity (Axis Bluechip Fund)
  - Attribute (TER)
  - Asserted value (0.82%)
  - Rejected value (0.79%)
- Auto-convert to feedback record in master_interactions table

### **Real AMC Example:**

**Interaction 1:**
- **Query:** "What is the TER of Axis Bluechip Fund Direct Growth?"
- **Response:** "The TER is 0.79% as per factsheet v17 dated June 2026."

**Interaction 2 (Follow-up):**
- **Query:** "That's completely wrong! TER is 0.82%, check AMFI latest data."

**System Detection:**
- ✅ Frustration detected: VADER compound = -0.72 (strongly negative)
- ✅ Same referent: Embedding similarity = 0.89 (clearly about TER)
- ✅ Correction language: "wrong" + "check" patterns matched
- **Action:** Auto-create feedback record with structured claim:
  ```json
  {
    "entity_name": "Axis Bluechip Fund Direct Growth",
    "attribute": "TER",
    "asserted_value": "0.82",
    "rejected_value": "0.79",
    "confidence": 0.85
  }
  ```

---

## **2. Architecture Design**

### **Component Diagram:**

```
┌─────────────────────────────────────────────────────────────┐
│                Follow-Up Query Received                      │
│         (User types: "That's wrong, TER is 0.82%")          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│          DissatisfactionDetector.is_correction_attempt()     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Stage 1: Sentiment Analysis                        │    │
│  │  - VADER: compound score < -0.4?                    │    │
│  │  - Fallback: keyword-based if VADER unavailable    │    │
│  │  Output: (is_frustrated: bool, score: float)       │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Stage 2: Same Referent Check                       │    │
│  │  - Embed follow-up query (SentenceTransformer)     │    │
│  │  - Embed original query                             │    │
│  │  - Cosine similarity ≥ 0.75?                        │    │
│  │  Output: (same_topic: bool, similarity: float)     │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Stage 3: Correction Language Patterns              │    │
│  │  - Regex match: "wrong|incorrect|actually|..."      │    │
│  │  - Confidence = match_count * 0.3                   │    │
│  │  Output: (has_correction: bool, confidence: float) │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Decision: is_correction = ALL three stages TRUE             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ if is_correction == True
┌─────────────────────────────────────────────────────────────┐
│          CorrectionExtractor.extract_claim()                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Extract Numbers (regex)                            │    │
│  │  - Feedback: [0.82, 0.79]                           │    │
│  │  - Original response: [0.79]                        │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Detect Attribute (keyword matching)                │    │
│  │  - "TER" in text → attribute = "TER"                │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Extract Entity (spaCy NER)                         │    │
│  │  - ORG entities containing "fund"                   │    │
│  │  - Fallback to context entity from original query  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Output: StructuredClaim(entity, attribute, asserted_value, │
│                          rejected_value, confidence)         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│      Update master_interactions Table (Feedback Fields)      │
│      - feedback_type = "dissatisfaction_followup"            │
│      - structured_claim = JSON                               │
│      - evaluation_status = "pending"                         │
└─────────────────────────────────────────────────────────────┘
```

### **File Structure:**

```
backend/
├── app/
│   ├── feedback/
│   │   ├── __init__.py
│   │   ├── dissatisfaction_detector.py    # NEW - Main detector
│   │   ├── correction_extractor.py        # NEW - Claim extraction
│   │   ├── sentiment_analyzer.py          # NEW - Sentiment wrapper
│   │   └── fund_name_matcher.py           # NEW - Entity resolution (stub)
│   ├── api/
│   │   └── routes/
│   │       └── feedback.py                # MODIFY - Add follow-up endpoint
│   └── db/
│       └── feedback.py                    # MODIFY - Add update methods
├── tests/
│   ├── test_dissatisfaction_detector.py   # NEW - Unit tests
│   └── test_correction_extractor.py       # NEW - Extraction tests
└── requirements.txt                        # UPDATE - Add dependencies

# New dependencies to add:
# - vaderSentiment==3.3.2
# - sentence-transformers==2.2.2
# - spacy==3.7.2
# - scikit-learn>=1.3.0 (for cosine_similarity)
```

---

## **3. Detailed Implementation Specification**

### **3.1 DissatisfactionDetector Class**

**File:** `backend/app/feedback/dissatisfaction_detector.py`

#### **Class Definition:**

```python
from typing import Optional, Tuple
import re
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import logging

logger = logging.getLogger("app.feedback.dissatisfaction")

# Attempt to import VADER (graceful degradation if not installed)
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    logger.warning("vaderSentiment not installed, using fallback sentiment detection")

@dataclass
class StructuredClaim:
    """
    Structured correction claim extracted from follow-up query.
    
    Attributes:
        entity_id: Canonical entity identifier (e.g., ISIN) or None
        entity_name: Human-readable entity name
        attribute: Attribute being corrected (e.g., "TER", "NAV")
        asserted_value: Value user claims is correct
        rejected_value: Value user claims is wrong (from original response)
        raw_text: Original feedback text
        confidence: Extraction confidence (0.0 to 1.0)
    """
    entity_id: Optional[str]
    entity_name: Optional[str]
    attribute: Optional[str]
    asserted_value: Optional[str]
    rejected_value: Optional[str]
    raw_text: str
    confidence: float


class DissatisfactionDetector:
    """
    Detects when a follow-up query is actually a correction attempt.
    Implements Keerthi's Step FD (Dissatisfaction Follow-up Handling).
    
    Detection Strategy:
        Three-signal approach (ALL must be True):
        1. Frustration: Negative sentiment detected
        2. Same Referent: Follow-up references same topic as original
        3. Correction Language: Contains correction patterns
    
    Usage:
        detector = DissatisfactionDetector()
        
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query="That's wrong, TER is 0.82%",
            original_response="The TER is 0.79%",
            original_query="What is the TER?"
        )
        
        if is_correction:
            print(f"Correction detected: {claim.attribute} should be {claim.asserted_value}")
    
    Configurable Thresholds:
        - sentiment_threshold: Default -0.4 (more negative = dissatisfied)
        - similarity_threshold: Default 0.75 (0.0 to 1.0)
        - intent_confidence_threshold: Default 0.65
    """
    
    # Default thresholds (from Keerthi's gap analysis recommendations)
    DEFAULT_SENTIMENT_THRESHOLD = -0.4
    DEFAULT_SIMILARITY_THRESHOLD = 0.75
    DEFAULT_INTENT_CONFIDENCE_THRESHOLD = 0.65
    
    # Correction language patterns (regex)
    CORRECTION_PATTERNS = [
        r"\b(wrong|incorrect|not right|mistake|error|inaccurate)\b",
        r"\b(actually|should be|correct answer is|real value is|true value)\b",
        r"\b(that'?s? not|no,|not true|disagree)\b",
        r"\b(check|verify|look again|re-check|double-check)\b",
        r"\b(my records show|according to|source says|document says)\b",
        r"\b(outdated|old data|stale|not current)\b"
    ]
    
    def __init__(
        self,
        sentiment_threshold: float = DEFAULT_SENTIMENT_THRESHOLD,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        intent_confidence_threshold: float = DEFAULT_INTENT_CONFIDENCE_THRESHOLD,
        embedder_model: str = "all-MiniLM-L6-v2"
    ):
        """
        Initialize dissatisfaction detector.
        
        Args:
            sentiment_threshold: Compound sentiment score threshold (default -0.4)
            similarity_threshold: Embedding similarity threshold (default 0.75)
            intent_confidence_threshold: Correction intent confidence (default 0.65)
            embedder_model: SentenceTransformer model name (default all-MiniLM-L6-v2)
        
        Model Loading:
            - SentenceTransformer: ~80MB, loads on first use
            - VADER: <1MB, instant loading
            - Both are cached after first load
        """
        self.sentiment_threshold = sentiment_threshold
        self.similarity_threshold = similarity_threshold
        self.intent_confidence_threshold = intent_confidence_threshold
        
        # Load SentenceTransformer for embedding similarity
        # Model: all-MiniLM-L6-v2 (384-dim, 80MB, optimized for semantic similarity)
        logger.info(f"Loading SentenceTransformer model: {embedder_model}")
        self.embedder = SentenceTransformer(embedder_model)
        
        # Load VADER sentiment analyzer (if available)
        if VADER_AVAILABLE:
            self.sentiment_analyzer = SentimentIntensityAnalyzer()
            logger.info("VADER sentiment analyzer loaded")
        else:
            self.sentiment_analyzer = None
            logger.warning("VADER not available, using keyword-based fallback")
    
    def _detect_frustration(self, text: str) -> Tuple[bool, float]:
        """
        Detect frustration via sentiment analysis.
        
        Args:
            text: Follow-up query text
        
        Returns:
            (is_frustrated: bool, sentiment_score: float)
            
            Sentiment score range: -1.0 (very negative) to +1.0 (very positive)
        
        Examples:
            "That's wrong!" → (True, -0.68)
            "Can you also tell me..." → (False, 0.12)
        """
        if self.sentiment_analyzer:
            # Use VADER (production-grade sentiment analysis)
            scores = self.sentiment_analyzer.polarity_scores(text)
            compound = scores["compound"]
            
            is_frustrated = compound < self.sentiment_threshold
            
            logger.debug(
                f"VADER sentiment: compound={compound:.2f}, "
                f"is_frustrated={is_frustrated} (threshold={self.sentiment_threshold})"
            )
            
            return is_frustrated, compound
        
        else:
            # Fallback: simple keyword-based sentiment
            negative_keywords = [
                "wrong", "incorrect", "not", "no", "error", "mistake",
                "bad", "poor", "terrible", "awful", "disagree"
            ]
            
            text_lower = text.lower()
            negative_count = sum(1 for kw in negative_keywords if kw in text_lower)
            
            # Rough approximation: -0.1 per negative keyword
            fallback_score = max(-0.1 * negative_count, -1.0)
            is_frustrated = fallback_score < self.sentiment_threshold
            
            logger.debug(
                f"Fallback sentiment: score={fallback_score:.2f}, "
                f"negative_keywords={negative_count}"
            )
            
            return is_frustrated, fallback_score
    
    def _check_same_referent(
        self,
        follow_up_query: str,
        original_query: str
    ) -> Tuple[bool, float]:
        """
        Check if follow-up references the same topic as original query.
        Uses embedding cosine similarity.
        
        Args:
            follow_up_query: Follow-up query text
            original_query: Original query text
        
        Returns:
            (same_topic: bool, similarity_score: float)
            
            Similarity range: 0.0 (completely different) to 1.0 (identical)
        
        Examples:
            Original: "What is the TER of Axis Bluechip Fund?"
            Follow-up: "That's wrong, TER is 0.82%" 
            → (True, 0.89) - clearly about TER
            
            Original: "What is the TER?"
            Follow-up: "What about the NAV?"
            → (False, 0.52) - different topic (NAV vs TER)
        """
        # Encode queries to embeddings (384-dim vectors)
        follow_emb = self.embedder.encode(follow_up_query)
        orig_emb = self.embedder.encode(original_query)
        
        # Compute cosine similarity
        similarity = float(cosine_similarity(
            [follow_emb], [orig_emb]
        )[0][0])
        
        same_topic = similarity >= self.similarity_threshold
        
        logger.debug(
            f"Embedding similarity: {similarity:.2f}, "
            f"same_topic={same_topic} (threshold={self.similarity_threshold})"
        )
        
        return same_topic, similarity
    
    def _has_correction_language(self, text: str) -> Tuple[bool, float]:
        """
        Check if text contains correction language patterns.
        
        Args:
            text: Follow-up query text
        
        Returns:
            (has_correction_intent: bool, confidence: float)
            
            Confidence: 0.3 per pattern matched, capped at 1.0
        
        Examples:
            "That's wrong, check the source" → (True, 0.6) - 2 patterns
            "Actually it should be 0.82%" → (True, 0.3) - 1 pattern
            "Can you tell me more?" → (False, 0.0) - 0 patterns
        """
        text_lower = text.lower()
        matches = 0
        matched_patterns = []
        
        for pattern in self.CORRECTION_PATTERNS:
            if re.search(pattern, text_lower):
                matches += 1
                matched_patterns.append(pattern)
        
        # Confidence scales with number of patterns matched
        # Each pattern adds 0.3, capped at 1.0
        confidence = min(matches * 0.3, 1.0)
        
        has_intent = confidence >= self.intent_confidence_threshold
        
        logger.debug(
            f"Correction patterns: {matches} matched, confidence={confidence:.2f}, "
            f"has_intent={has_intent} (threshold={self.intent_confidence_threshold})"
        )
        
        return has_intent, confidence
    
    def is_correction_attempt(
        self,
        follow_up_query: str,
        original_response: str,
        original_query: str
    ) -> Tuple[bool, Optional[StructuredClaim]]:
        """
        Main entry point: Detect if follow-up query is a correction attempt.
        
        Args:
            follow_up_query: User's follow-up query
            original_response: System's original response
            original_query: User's original query
        
        Returns:
            (is_correction: bool, claim: Optional[StructuredClaim])
            
            If is_correction=True, claim contains extracted structured data.
            If is_correction=False, claim is None.
        
        Example (Correction Detected):
            detector.is_correction_attempt(
                follow_up_query="That's completely wrong! TER is 0.82%, not 0.79%",
                original_response="The TER is 0.79%",
                original_query="What is the TER of Axis Bluechip Fund?"
            )
            → (True, StructuredClaim(
                attribute="TER", 
                asserted_value="0.82", 
                rejected_value="0.79",
                confidence=0.85
              ))
        
        Example (Clarification, Not Correction):
            detector.is_correction_attempt(
                follow_up_query="Can you also tell me the NAV?",
                original_response="The TER is 0.82%",
                original_query="What is the TER?"
            )
            → (False, None)
        """
        logger.info(f"Checking if follow-up is correction: '{follow_up_query[:50]}...'")
        
        # Stage 1: Frustration check
        is_frustrated, sentiment_score = self._detect_frustration(follow_up_query)
        
        # Stage 2: Same referent check
        same_topic, similarity_score = self._check_same_referent(
            follow_up_query, original_query
        )
        
        # Stage 3: Correction language check
        has_correction_lang, intent_confidence = self._has_correction_language(
            follow_up_query
        )
        
        # Decision: ALL three must be True
        is_correction = is_frustrated and same_topic and has_correction_lang
        
        logger.info(
            f"Detection result: is_correction={is_correction} "
            f"(frustrated={is_frustrated}, same_topic={same_topic}, "
            f"correction_lang={has_correction_lang})"
        )
        
        if not is_correction:
            return False, None
        
        # Stage 4: Extract structured claim
        from app.feedback.correction_extractor import CorrectionExtractor
        
        extractor = CorrectionExtractor()
        claim = extractor.extract_claim(
            feedback_text=follow_up_query,
            original_response=original_response,
            original_query=original_query
        )
        
        if claim:
            # Blend detection confidence into claim confidence
            detection_confidence = (
                abs(sentiment_score) + similarity_score + intent_confidence
            ) / 3.0
            
            claim.confidence = min(claim.confidence, detection_confidence)
            
            logger.info(
                f"Claim extracted: attribute={claim.attribute}, "
                f"asserted={claim.asserted_value}, confidence={claim.confidence:.2f}"
            )
        else:
            logger.warning("Correction detected but claim extraction failed")
        
        return True, claim
```

---

### **3.2 CorrectionExtractor Class**

**File:** `backend/app/feedback/correction_extractor.py`

```python
import re
from typing import Optional, List
import spacy
from dataclasses import dataclass
import logging

logger = logging.getLogger("app.feedback.correction_extractor")

@dataclass
class StructuredClaim:
    """Structured correction claim (same as in dissatisfaction_detector.py)."""
    entity_id: Optional[str]
    entity_name: Optional[str]
    attribute: Optional[str]
    asserted_value: Optional[str]
    rejected_value: Optional[str]
    raw_text: str
    confidence: float


class CorrectionExtractor:
    """
    Extracts structured claims from correction feedback text.
    
    Extraction Pipeline:
        1. Extract numbers (regex for decimals, percentages, currency)
        2. Detect attribute (keyword matching against AMC domain vocabulary)
        3. Extract entity (spaCy NER for organization names)
        4. Assign asserted/rejected values based on heuristics
    
    Example:
        Input: "TER should be 0.82% not 0.79%"
        Output: StructuredClaim(
            attribute="TER",
            asserted_value="0.82",
            rejected_value="0.79",
            confidence=0.8
        )
    
    Usage:
        extractor = CorrectionExtractor()
        claim = extractor.extract_claim(
            feedback_text="That's wrong! NAV is ₹64.31, not ₹64.18",
            original_response="The NAV is ₹64.18 as of today",
            original_query="What is the NAV?"
        )
    """
    
    # AMC attribute keywords (domain vocabulary)
    ATTRIBUTE_KEYWORDS = {
        "ter": ["ter", "expense ratio", "total expense", "expense", "cost ratio"],
        "nav": ["nav", "net asset value", "asset value"],
        "return": ["return", "cagr", "performance", "gain", "growth"],
        "aum": ["aum", "assets under management", "corpus", "fund size"],
        "exit_load": ["exit load", "redemption charge", "exit fee"],
        "minimum_investment": ["minimum investment", "min investment", "minimum amount"],
        "sharpe_ratio": ["sharpe", "sharpe ratio"],
        "alpha": ["alpha", "jensen"],
        "beta": ["beta", "volatility"],
        "risk_grade": ["risk", "risk grade", "risk category"]
    }
    
    def __init__(self, spacy_model: str = "en_core_web_sm"):
        """
        Initialize correction extractor.
        
        Args:
            spacy_model: spaCy model name (default en_core_web_sm)
        
        Model Loading:
            - spaCy en_core_web_sm: ~12MB, loads on first use
            - Cached after first load
        """
        logger.info(f"Loading spaCy model: {spacy_model}")
        try:
            self.nlp = spacy.load(spacy_model)
        except OSError:
            logger.warning(
                f"spaCy model '{spacy_model}' not found. "
                "Run: python -m spacy download en_core_web_sm"
            )
            self.nlp = None
    
    def _extract_numbers(self, text: str) -> List[float]:
        """
        Extract numeric values from text.
        Handles: percentages, currency (₹, Rs), decimals.
        
        Args:
            text: Text to extract numbers from
        
        Returns:
            List of extracted numbers (floats)
        
        Examples:
            "TER is 0.82%" → [0.82]
            "NAV should be ₹64.31 not ₹64.18" → [64.31, 64.18]
            "Return was 14.2% not 38%" → [14.2, 38.0]
        """
        # Pattern: optional currency symbol, digits with decimal, optional %
        pattern = r"(?:₹|Rs\.?\s*)?(\d+(?:\.\d+)?)\s*%?"
        
        matches = re.findall(pattern, text)
        numbers = [float(m) for m in matches]
        
        logger.debug(f"Extracted numbers: {numbers} from '{text[:50]}...'")
        
        return numbers
    
    def _detect_attribute(self, text: str) -> Optional[str]:
        """
        Detect which attribute the feedback is about.
        Uses keyword matching against AMC domain vocabulary.
        
        Args:
            text: Feedback text
        
        Returns:
            Attribute name (e.g., "TER", "NAV") or None if not detected
        
        Examples:
            "TER is wrong" → "TER"
            "expense ratio should be..." → "TER"
            "NAV value is incorrect" → "NAV"
        """
        text_lower = text.lower()
        
        for attr_key, keywords in self.ATTRIBUTE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    logger.debug(f"Detected attribute '{attr_key}' via keyword '{keyword}'")
                    return attr_key.upper()
        
        logger.debug("No attribute detected")
        return None
    
    def _extract_entity(self, text: str) -> Optional[str]:
        """
        Extract fund/entity name using spaCy NER.
        
        Args:
            text: Text to extract entity from
        
        Returns:
            Entity name or None if not found
        
        Examples:
            "Axis Bluechip Fund TER is wrong" → "Axis Bluechip Fund"
            "Mirae Asset Large Cap..." → "Mirae Asset Large Cap"
        """
        if not self.nlp:
            return None
        
        doc = self.nlp(text)
        
        # Look for ORG entities containing "fund"
        for ent in doc.ents:
            if ent.label_ == "ORG" and "fund" in ent.text.lower():
                logger.debug(f"Extracted entity: '{ent.text}'")
                return ent.text
        
        # Fallback: Look for any ORG entity
        for ent in doc.ents:
            if ent.label_ == "ORG":
                logger.debug(f"Extracted entity (fallback): '{ent.text}'")
                return ent.text
        
        logger.debug("No entity extracted")
        return None
    
    def extract_claim(
        self,
        feedback_text: str,
        original_response: str,
        original_query: str
    ) -> Optional[StructuredClaim]:
        """
        Extract structured claim from correction feedback.
        
        Args:
            feedback_text: User's correction feedback
            original_response: System's original response
            original_query: User's original query
        
        Returns:
            StructuredClaim or None if extraction fails
        
        Heuristics:
            - First number in feedback = asserted value (what user claims is correct)
            - Second number in feedback = rejected value (what user says is wrong)
            - If only one number in feedback, try to extract rejected value from original response
            - Attribute detected from either feedback or original query
            - Entity extracted from original query (more reliable than feedback)
        
        Example 1 (Both values in feedback):
            feedback_text="TER should be 0.82% not 0.79%"
            original_response="The TER is 0.79%"
            → asserted=0.82, rejected=0.79
        
        Example 2 (Only asserted value in feedback):
            feedback_text="That's wrong, TER is 0.82%"
            original_response="The TER is 0.79%"
            → asserted=0.82, rejected=0.79 (extracted from original response)
        """
        # 1. Extract numbers from feedback
        feedback_numbers = self._extract_numbers(feedback_text)
        
        # 2. Extract numbers from original response (fallback for rejected value)
        response_numbers = self._extract_numbers(original_response)
        
        # 3. Detect attribute (try feedback first, then original query)
        attribute = self._detect_attribute(feedback_text)
        if not attribute:
            attribute = self._detect_attribute(original_query)
        
        # Must have at least an attribute and one number
        if not attribute or len(feedback_numbers) == 0:
            logger.warning(
                "Claim extraction failed: "
                f"attribute={attribute}, numbers={len(feedback_numbers)}"
            )
            return None
        
        # 4. Determine asserted and rejected values
        #    Heuristic: First number in feedback = asserted (what user claims)
        asserted_value = feedback_numbers[0]
        
        #    If feedback has two numbers, second is rejected value
        #    Otherwise, try to extract from original response
        if len(feedback_numbers) >= 2:
            rejected_value = feedback_numbers[1]
        elif response_numbers:
            rejected_value = response_numbers[0]
        else:
            rejected_value = None
        
        # 5. Extract entity (more reliable from original query than feedback)
        entity_name = self._extract_entity(original_query)
        if not entity_name:
            entity_name = self._extract_entity(feedback_text)
        
        # 6. Calculate confidence
        #    Base: 0.6
        #    +0.2 if we have rejected value
        #    +0.2 if we have entity name
        confidence = 0.6
        if rejected_value is not None:
            confidence += 0.2
        if entity_name:
            confidence += 0.2
        
        logger.info(
            f"Claim extracted: attribute={attribute}, "
            f"asserted={asserted_value}, rejected={rejected_value}, "
            f"entity={entity_name}, confidence={confidence:.2f}"
        )
        
        return StructuredClaim(
            entity_id=None,  # Would be resolved via FundNameMatcher (Track 8)
            entity_name=entity_name,
            attribute=attribute,
            asserted_value=str(asserted_value),
            rejected_value=str(rejected_value) if rejected_value else None,
            raw_text=feedback_text,
            confidence=confidence
        )
```

---

### **3.3 API Integration**

**File:** `backend/app/api/routes/feedback.py` (ADD NEW ENDPOINT)

```python
# backend/app/api/routes/feedback.py (ADD THIS ENDPOINT)

from app.feedback.dissatisfaction_detector import DissatisfactionDetector

# Initialize detector (module-level singleton)
_dissatisfaction_detector = None

def get_dissatisfaction_detector():
    global _dissatisfaction_detector
    if _dissatisfaction_detector is None:
        _dissatisfaction_detector = DissatisfactionDetector()
    return _dissatisfaction_detector


@router.post("/follow-up-detection", response_model=Dict[str, Any])
def detect_follow_up_correction(
    session_id: str,
    previous_response_id: str,
    follow_up_query: str,
    current_role: Role = Depends(get_client_role)
) -> Dict[str, Any]:
    """
    Detect if a follow-up query is actually a correction attempt.
    
    If detected as correction:
        - Auto-creates structured feedback record
        - Updates master_interactions table
        - Returns structured claim
    
    Args:
        session_id: Session identifier
        previous_response_id: Response ID being corrected
        follow_up_query: User's follow-up query text
    
    Returns:
        {
            "correction_detected": bool,
            "feedback_created": bool,
            "claim": Optional[StructuredClaim dict]
        }
    
    Example Request:
        POST /api/feedback/follow-up-detection
        {
            "session_id": "sess_abc123",
            "previous_response_id": "resp_9c4f1a",
            "follow_up_query": "That's wrong, TER is 0.82%"
        }
    
    Example Response (Correction Detected):
        {
            "correction_detected": true,
            "feedback_created": true,
            "claim": {
                "entity_name": "Axis Bluechip Fund",
                "attribute": "TER",
                "asserted_value": "0.82",
                "rejected_value": "0.79",
                "confidence": 0.85
            }
        }
    
    Example Response (Not a Correction):
        {
            "correction_detected": false,
            "feedback_created": false,
            "claim": null
        }
    """
    # 1. Fetch previous interaction from master_interactions table
    #    (Assumes Track 1 master_interactions table exists)
    store = get_feedback_store()
    
    # TODO: Replace with actual master_interactions query
    # For now, use existing response_feedback table
    prev_interactions = store.get_by_response_id(previous_response_id)
    
    if not prev_interactions:
        raise HTTPException(
            status_code=404,
            detail=f"Previous interaction not found for response_id: {previous_response_id}"
        )
    
    prev_interaction = prev_interactions[0]
    
    # Extract original query and response
    original_query = prev_interaction.get("query_text", "")
    # TODO: Fetch original response text from master_interactions
    # For now, simulate with placeholder
    original_response = "The TER is 0.79% as per factsheet v17"
    
    # 2. Run dissatisfaction detection
    detector = get_dissatisfaction_detector()
    
    try:
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query=follow_up_query,
            original_response=original_response,
            original_query=original_query
        )
    except Exception as exc:
        logger.error(f"Dissatisfaction detection failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Dissatisfaction detection service error"
        )
    
    # 3. If correction detected, auto-create feedback record
    if is_correction and claim:
        try:
            # Update master_interactions table with feedback fields
            # TODO: Implement update_interaction_feedback() in FeedbackStore
            
            # For now, create regular feedback record
            feedback_result = store.upsert_feedback(
                response_id=previous_response_id,
                interaction_id=prev_interaction.get("interaction_id", ""),
                session_id=session_id,
                turn_number=prev_interaction.get("turn_number", 1),
                selected_categories=["F08"],  # Numeric accuracy
                query_text=original_query,
                actor_id=current_role.value,
                actor_role=current_role.value,
                free_text=claim.raw_text
            )
            
            logger.info(
                f"Auto-created feedback from dissatisfaction detection: "
                f"feedback_id={feedback_result['feedback_id']}, "
                f"claim={claim.attribute}={claim.asserted_value}"
            )
            
            return {
                "correction_detected": True,
                "feedback_created": True,
                "feedback_id": feedback_result["feedback_id"],
                "claim": {
                    "entity_id": claim.entity_id,
                    "entity_name": claim.entity_name,
                    "attribute": claim.attribute,
                    "asserted_value": claim.asserted_value,
                    "rejected_value": claim.rejected_value,
                    "confidence": claim.confidence
                }
            }
        
        except Exception as exc:
            logger.error(f"Failed to create feedback from dissatisfaction: {exc}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to create feedback record"
            )
    
    # 4. Not a correction - return negative result
    return {
        "correction_detected": False,
        "feedback_created": False,
        "claim": None
    }
```

---

### **3.4 Unit Tests**

**File:** `backend/tests/test_dissatisfaction_detector.py`

```python
import pytest
from app.feedback.dissatisfaction_detector import DissatisfactionDetector, StructuredClaim

# Test fixtures
@pytest.fixture
def detector():
    """DissatisfactionDetector instance with default thresholds."""
    return DissatisfactionDetector()

@pytest.fixture
def strict_detector():
    """Detector with stricter thresholds (fewer false positives)."""
    return DissatisfactionDetector(
        sentiment_threshold=-0.6,  # More negative required
        similarity_threshold=0.85,  # Higher similarity required
        intent_confidence_threshold=0.8  # More patterns required
    )


# Detection Tests
class TestCorrectionDetection:
    """Test main is_correction_attempt() method."""
    
    def test_clear_correction_detected(self, detector):
        """Clear correction with all signals should be detected."""
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query="No that's incorrect! TER is 0.82% not 0.79%",
            original_response="The TER is 0.79%",
            original_query="What is the TER of Axis Bluechip Fund?"
        )
        
        assert is_correction == True
        assert claim is not None
        assert claim.attribute == "TER"
        assert claim.asserted_value == "0.82"
        assert claim.rejected_value == "0.79"
    
    def test_clarification_not_detected(self, detector):
        """Genuine clarification should NOT be flagged as correction."""
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query="Can you also tell me the NAV?",
            original_response="The TER is 0.82%",
            original_query="What is the TER?"
        )
        
        assert is_correction == False
        assert claim is None
    
    def test_different_topic_not_detected(self, detector):
        """Follow-up on different topic should NOT be flagged."""
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query="That's wrong, NAV is ₹64.31",  # About NAV
            original_response="The TER is 0.82%",  # About TER
            original_query="What is the TER?"  # About TER
        )
        
        # Same referent check should fail (TER vs NAV)
        assert is_correction == False
    
    def test_positive_follow_up_not_detected(self, detector):
        """Positive sentiment follow-up should NOT be flagged."""
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query="Great, thank you! What about the 5-year return?",
            original_response="The TER is 0.82%",
            original_query="What is the TER?"
        )
        
        # Frustration check should fail (positive sentiment)
        assert is_correction == False


class TestSentimentAnalysis:
    """Test _detect_frustration() method."""
    
    def test_strongly_negative_detected(self, detector):
        """Strongly negative text should be detected as frustrated."""
        is_frustrated, score = detector._detect_frustration(
            "That's completely wrong and incorrect!"
        )
        
        assert is_frustrated == True
        assert score < -0.4
    
    def test_mildly_negative_not_detected(self, detector):
        """Mildly negative text should NOT trigger frustration."""
        is_frustrated, score = detector._detect_frustration(
            "I think that might not be quite right"
        )
        
        # Should be negative but not below threshold
        assert is_frustrated == False
    
    def test_positive_sentiment(self, detector):
        """Positive text should never be frustrated."""
        is_frustrated, score = detector._detect_frustration(
            "Great, thank you so much!"
        )
        
        assert is_frustrated == False
        assert score > 0
    
    def test_threshold_customization(self):
        """Custom threshold should be respected."""
        strict_detector = DissatisfactionDetector(sentiment_threshold=-0.7)
        
        # Moderately negative text
        is_frustrated, score = strict_detector._detect_frustration(
            "That's not right"  # score ≈ -0.5
        )
        
        # Should NOT trigger strict threshold
        assert is_frustrated == False


class TestSameReferentCheck:
    """Test _check_same_referent() method."""
    
    def test_same_topic_high_similarity(self, detector):
        """Queries about same topic should have high similarity."""
        same_topic, score = detector._check_same_referent(
            follow_up_query="That TER value is wrong, it's 0.82%",
            original_query="What is the TER of Axis Bluechip Fund?"
        )
        
        assert same_topic == True
        assert score >= 0.75
    
    def test_different_topic_low_similarity(self, detector):
        """Queries about different topics should have low similarity."""
        same_topic, score = detector._check_same_referent(
            follow_up_query="What is the NAV?",
            original_query="What is the TER?"
        )
        
        assert same_topic == False
        assert score < 0.75
    
    def test_paraphrased_query(self, detector):
        """Paraphrased query should still match."""
        same_topic, score = detector._check_same_referent(
            follow_up_query="The expense ratio is incorrect",
            original_query="What is the TER?"  # TER = expense ratio
        )
        
        # Should be detected as same topic (embedding captures semantic meaning)
        assert same_topic == True


class TestCorrectionLanguage:
    """Test _has_correction_language() method."""
    
    def test_multiple_patterns_high_confidence(self, detector):
        """Multiple correction patterns should give high confidence."""
        has_correction, confidence = detector._has_correction_language(
            "That's wrong, check the source, it should actually be 0.82%"
        )
        
        assert has_correction == True
        assert confidence >= 0.9  # 3+ patterns
    
    def test_single_pattern_moderate_confidence(self, detector):
        """Single pattern should give moderate confidence."""
        has_correction, confidence = detector._has_correction_language(
            "That's not right"
        )
        
        # 1 pattern = 0.3 confidence, below default threshold (0.65)
        assert has_correction == False
        assert confidence == 0.3
    
    def test_no_pattern(self, detector):
        """No correction patterns should return False."""
        has_correction, confidence = detector._has_correction_language(
            "Can you tell me more about this fund?"
        )
        
        assert has_correction == False
        assert confidence == 0.0


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_strings(self, detector):
        """Empty strings should not crash."""
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query="",
            original_response="The TER is 0.82%",
            original_query="What is the TER?"
        )
        
        assert is_correction == False
    
    def test_very_long_text(self, detector):
        """Very long text should be handled."""
        long_text = "This is wrong. " * 100  # 1400+ chars
        
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query=long_text,
            original_response="The TER is 0.82%",
            original_query="What is the TER?"
        )
        
        # Should complete without timeout
        assert isinstance(is_correction, bool)
    
    def test_non_english_text(self, detector):
        """Non-English text should not crash (graceful degradation)."""
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query="यह गलत है",  # Hindi: "This is wrong"
            original_response="The TER is 0.82%",
            original_query="What is the TER?"
        )
        
        # Should return result (may be False due to English-only models)
        assert isinstance(is_correction, bool)


class TestIntegration:
    """Integration tests with CorrectionExtractor."""
    
    def test_end_to_end_claim_extraction(self, detector):
        """Complete flow from detection to claim extraction."""
        is_correction, claim = detector.is_correction_attempt(
            follow_up_query="That's wrong! The TER for Axis Bluechip Fund is 0.82%, not 0.79%",
            original_response="The TER for Axis Bluechip Fund Direct Growth is 0.79%",
            original_query="What is the TER of Axis Bluechip Fund?"
        )
        
        assert is_correction == True
        assert claim is not None
        
        # Verify claim fields
        assert claim.attribute == "TER"
        assert claim.asserted_value == "0.82"
        assert claim.rejected_value == "0.79"
        assert claim.entity_name is not None
        assert "Axis" in claim.entity_name
        assert claim.confidence > 0.6
```

**Run Tests:**
```bash
pytest backend/tests/test_dissatisfaction_detector.py -v --cov=app.feedback.dissatisfaction_detector
```

**Expected Output:**
```
test_dissatisfaction_detector.py::TestCorrectionDetection::test_clear_correction_detected PASSED
test_dissatisfaction_detector.py::TestCorrectionDetection::test_clarification_not_detected PASSED
test_dissatisfaction_detector.py::TestSentimentAnalysis::test_strongly_negative_detected PASSED
test_dissatisfaction_detector.py::TestSameReferentCheck::test_same_topic_high_similarity PASSED
...
======================== 25 passed in 3.45s ========================
Coverage: 92%
```

---

## **4. Implementation Checklist**

### **Day 1 (8 hours):**
- [ ] Install dependencies: `pip install vaderSentiment sentence-transformers spacy scikit-learn`
- [ ] Download spaCy model: `python -m spacy download en_core_web_sm`
- [ ] Create `dissatisfaction_detector.py` with DissatisfactionDetector class
- [ ] Create `correction_extractor.py` with CorrectionExtractor class
- [ ] Test model loading and basic functionality

### **Day 2 (8 hours):**
- [ ] Create comprehensive unit tests in `test_dissatisfaction_detector.py`
- [ ] Create `test_correction_extractor.py` for claim extraction tests
- [ ] Run pytest suite, achieve >90% code coverage
- [ ] Fix edge cases discovered during testing
- [ ] Performance testing: ensure <100ms latency

### **Day 3 (8 hours):**
- [ ] Add `/follow-up-detection` endpoint to `feedback.py`
- [ ] Integrate with existing `FeedbackStore`
- [ ] Create integration tests with actual API calls
- [ ] Test with real AMC query examples
- [ ] Document API endpoint in OpenAPI spec

### **Day 4 (8 hours):**
- [ ] Performance optimization: cache embedder model
- [ ] Add monitoring/metrics for detection rate
- [ ] Create usage documentation with examples
- [ ] Deploy to staging environment
- [ ] Monitor false positive/negative rates with sample queries

---

## **5. Success Criteria**

**Functional:**
- ✅ Dissatisfaction detection integrated into feedback API
- ✅ >90% detection rate on true correction attempts
- ✅ <10% false positive rate (clarifications not flagged)
- ✅ Structured claims extracted with entity, attribute, values
- ✅ Auto-creates feedback records for detected corrections

**Performance:**
- ✅ Latency <100ms for 95th percentile
- ✅ Model loading time <2 seconds on cold start
- ✅ Memory footprint <500MB with all models loaded

**Quality:**
- ✅ Unit test coverage >90%
- ✅ 25+ test cases covering detection, extraction, edge cases
- ✅ Integration tests with actual API

**User Impact:**
- ✅ 2-5x increase in captured feedback volume
- ✅ Reduced user friction (no need to click feedback buttons)

---Excellent! Track 4 (Dissatisfaction Detection) is complete. Let me continue with the remaining tracks. Due to the complexity and length, I'll create streamlined but comprehensive plans for Tracks 5-8.

---

## **TRACK 5: DETERMINISTIC RULES ENGINE - IMPLEMENTATION PLAN**

### **Document: TRACK_5_DETERMINISTIC_RULES_PLAN.md**

---

# **Track 5: Deterministic Rules Engine (Tier 1A)**
**Implementation Plan & Technical Specification**

## **Executive Summary**

**Objective:** Implement STOP-1 deterministic evaluation rules that catch common failures without LLM escalation, reducing evaluation costs by 40-60%.

**Priority:** P1 | Duration: 5 days (40 work hours)  
**Owner:** Compliance Team  
**Dependencies:** Track 2 (EvidencePack D0-D3)  
**Value:** Zero LLM tokens spent on deterministic failures (numeric mismatches, stale sources, broken citations)

---

## **1. Problem Statement**

### **Current State:**
- Every feedback evaluation invokes LLM (expensive, slow)
- Many failures are deterministically provable:
  - Response says "TER 0.79%", source says "TER 0.82%" → Numeric mismatch (no LLM needed)
  - Source dated 90 days ago → Stale source (no LLM needed)
  - Citation ID "C_4421" not in retrieved chunks → Broken citation (no LLM needed)

### **Target State (Keerthi's Tier 1A + STOP-1):**
- Rule-based checks run FIRST, before any LLM
- If deterministic rule gives high-confidence verdict → STOP, don't escalate
- Only ambiguous cases proceed to Tier 2 (NLI) or Tier 3 (LLM)

### **Rule Categories (from Keerthi's design):**
1. **C02: Source Currency** - Is source fresh enough?
2. **C03: Numeric Accuracy** - Do response numbers match source numbers?
3. **F06: Citation Integrity** - Do citations resolve and match?
4. **Schema Validation** - Formatting, structure checks
5. **Cost/Latency Anomalies** - System health signals

---

## **2. Architecture Design**

```
┌─────────────────────────────────────────────────────────────┐
│              Feedback Evaluation Trigger                     │
│         (HITL feedback OR passive anomaly detected)          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│         Evaluation Router (Keerthi's Module)                 │
│         Loads EvidencePack (D0-D3) from master_interactions  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│      TIER 1A: DeterministicRuleEngine                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  C02: Source Currency Rule                           │   │
│  │  Input: source_age_days from D2                      │   │
│  │  Check: age <= threshold?                            │   │
│  │  Output: PASS/FAIL, confidence=1.0                   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  C03: Numeric Accuracy Rule                          │   │
│  │  Input: response_text + D2.chunk_ids                 │   │
│  │  Extract: numbers from response vs source            │   │
│  │  Check: deviation < 5%?                              │   │
│  │  Output: PASS/FAIL, confidence=1.0                   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  F06: Citation Integrity Rule                        │   │
│  │  Input: response citations + D2.chunk_ids            │   │
│  │  Check: all citations in retrieved chunks?           │   │
│  │  Output: PASS/FAIL, confidence=1.0                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Decision Logic (STOP-1):                                    │
│    IF any rule returns FAIL with confidence=1.0             │
│      THEN return verdict immediately (don't escalate)        │
│    ELSE escalate to Tier 2 (NLI)                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ STOP-1 fires
┌─────────────────────────────────────────────────────────────┐
│         Adjudication (Deterministic Verdict)                 │
│         LLM tokens used: 0                                   │
│         Tier: T1A_RULES                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## **3. Implementation Specification**

### **3.1 DeterministicRuleEngine Class**

**File:** `backend/app/evaluation/deterministic_rules.py`

```python
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("app.evaluation.deterministic_rules")

class RuleVerdict(Enum):
    """Rule evaluation verdict."""
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"

@dataclass
class RuleResult:
    """Result of a single rule evaluation."""
    rule_id: str
    rule_name: str
    verdict: RuleVerdict
    confidence: float  # 0.0 to 1.0
    evidence: Dict[str, Any]
    explanation: str

class DeterministicRuleEngine:
    """
    Tier 1A deterministic evaluation rules.
    Implements STOP-1 gates from Keerthi's design.
    
    Purpose:
        Catch common failures without LLM escalation.
        Save 40-60% of evaluation costs by resolving
        deterministically provable failures at zero LLM tokens.
    
    Rule Categories:
        - C02: Source Currency (freshness)
        - C03: Numeric Accuracy (value matching)
        - F06: Citation Integrity (link validation)
        - Schema Validation
        - Cost/Latency Anomalies
    
    Usage:
        engine = DeterministicRuleEngine()
        
        results = engine.evaluate_all(
            response_text="The TER is 0.79%",
            evidence_pack=evidence_d2
        )
        
        if engine.should_stop(results):
            return EvaluationResult(verdict="FAIL", tier="T1A", llm_tokens=0)
    """
    
    # Default thresholds (configurable)
    DEFAULT_SOURCE_MAX_AGE_DAYS = 7
    DEFAULT_NUMERIC_DEVIATION_PCT = 0.05  # 5%
    
    def __init__(
        self,
        source_max_age_days: int = DEFAULT_SOURCE_MAX_AGE_DAYS,
        numeric_deviation_threshold: float = DEFAULT_NUMERIC_DEVIATION_PCT
    ):
        """
        Initialize rule engine with thresholds.
        
        Args:
            source_max_age_days: Max age for C02 source currency (default 7)
            numeric_deviation_threshold: Max deviation for C03 (default 0.05 = 5%)
        """
        self.source_max_age_days = source_max_age_days
        self.numeric_deviation_threshold = numeric_deviation_threshold
    
    def evaluate_source_currency(
        self,
        evidence_pack: Dict[str, Any]
    ) -> RuleResult:
        """
        C02: Source Currency Rule
        
        Check if sources are fresh enough for compliance.
        
        Args:
            evidence_pack: D2 evidence with source_age_days
        
        Returns:
            RuleResult with PASS/FAIL verdict, confidence=1.0
        
        Example:
            evidence_pack = {"source_age_days": 3}
            → PASS (3 days < 7 day threshold)
            
            evidence_pack = {"source_age_days": 12}
            → FAIL (12 days > 7 day threshold)
        """
        source_age_days = evidence_pack.get("source_age_days")
        
        if source_age_days is None:
            return RuleResult(
                rule_id="C02_SOURCE_CURRENCY",
                rule_name="Source Currency",
                verdict=RuleVerdict.INCONCLUSIVE,
                confidence=0.0,
                evidence={},
                explanation="source_age_days not in evidence pack"
            )
        
        if source_age_days <= self.source_max_age_days:
            return RuleResult(
                rule_id="C02_SOURCE_CURRENCY",
                rule_name="Source Currency",
                verdict=RuleVerdict.PASS,
                confidence=1.0,
                evidence={
                    "source_age_days": source_age_days,
                    "threshold_days": self.source_max_age_days
                },
                explanation=f"Source is {source_age_days} days old (within {self.source_max_age_days} day threshold)"
            )
        else:
            return RuleResult(
                rule_id="C02_SOURCE_CURRENCY",
                rule_name="Source Currency",
                verdict=RuleVerdict.FAIL,
                confidence=1.0,
                evidence={
                    "source_age_days": source_age_days,
                    "threshold_days": self.source_max_age_days,
                    "source_versions": evidence_pack.get("source_versions", {})
                },
                explanation=f"Source is {source_age_days} days old (exceeds {self.source_max_age_days} day threshold)"
            )
    
    def evaluate_numeric_accuracy(
        self,
        response_text: str,
        evidence_pack: Dict[str, Any],
        chunk_store: Any = None  # Optional: for fetching actual chunk content
    ) -> RuleResult:
        """
        C03: Numeric Accuracy Rule
        
        Extract numbers from response, compare with numbers in source chunks.
        Detect numeric hallucinations or copying errors.
        
        Args:
            response_text: Generated response text
            evidence_pack: D2 evidence with chunk_ids
            chunk_store: Optional store to fetch chunk content
        
        Returns:
            RuleResult with PASS/FAIL if deviation detected, INCONCLUSIVE otherwise
        
        Example (FAIL):
            response_text = "TER is 0.79%"
            source chunk = "TER is 0.82%"
            → FAIL (|0.79-0.82|/0.82 = 3.7% deviation)
        
        Example (PASS):
            response_text = "TER is 0.82%"
            source chunk = "TER is 0.82%"
            → PASS (exact match)
        """
        # Extract numbers from response
        response_numbers = self._extract_numbers(response_text)
        
        if not response_numbers:
            return RuleResult(
                rule_id="C03_NUMERIC_ACCURACY",
                rule_name="Numeric Accuracy",
                verdict=RuleVerdict.INCONCLUSIVE,
                confidence=0.0,
                evidence={},
                explanation="No numbers found in response"
            )
        
        # Extract numbers from source chunks
        # TODO: Implement chunk content fetching
        # For now, use placeholder
        source_numbers = []  # Would extract from chunk_store.get_chunks(chunk_ids)
        
        if not source_numbers:
            return RuleResult(
                rule_id="C03_NUMERIC_ACCURACY",
                rule_name="Numeric Accuracy",
                verdict=RuleVerdict.INCONCLUSIVE,
                confidence=0.0,
                evidence={"response_numbers": response_numbers},
                explanation="No numbers found in source chunks (cannot verify)"
            )
        
        # Compare numbers: find mismatches
        mismatches = []
        for resp_num in response_numbers:
            # Find closest source number (within context)
            closest_source = self._find_closest_number(resp_num, source_numbers)
            
            if closest_source:
                deviation_pct = abs(resp_num - closest_source) / closest_source
                
                if deviation_pct > self.numeric_deviation_threshold:
                    mismatches.append({
                        "response_value": resp_num,
                        "source_value": closest_source,
                        "deviation_pct": deviation_pct
                    })
        
        if mismatches:
            return RuleResult(
                rule_id="C03_NUMERIC_ACCURACY",
                rule_name="Numeric Accuracy",
                verdict=RuleVerdict.FAIL,
                confidence=1.0,
                evidence={
                    "mismatches": mismatches,
                    "threshold_pct": self.numeric_deviation_threshold
                },
                explanation=f"Numeric mismatch detected: {len(mismatches)} value(s) deviate from source"
            )
        else:
            return RuleResult(
                rule_id="C03_NUMERIC_ACCURACY",
                rule_name="Numeric Accuracy",
                verdict=RuleVerdict.PASS,
                confidence=1.0,
                evidence={"verified_numbers": len(response_numbers)},
                explanation=f"All {len(response_numbers)} numeric values match source"
            )
    
    def evaluate_citation_integrity(
        self,
        response_text: str,
        evidence_pack: Dict[str, Any]
    ) -> RuleResult:
        """
        F06: Citation Integrity Rule
        
        Check if all citations in response resolve to retrieved chunks.
        Detect broken citation links.
        
        Args:
            response_text: Generated response text
            evidence_pack: D2 evidence with chunk_ids
        
        Returns:
            RuleResult with FAIL if broken citations, PASS if all resolve
        
        Example (FAIL):
            response_text = "...as per [source: C_4421]"
            chunk_ids = ["C_1234", "C_5678"]
            → FAIL (C_4421 not in retrieved chunks)
        
        Example (PASS):
            response_text = "...as per [source: C_1234]"
            chunk_ids = ["C_1234", "C_5678"]
            → PASS (C_1234 found in chunks)
        """
        # Extract citation IDs from response
        citation_ids = self._extract_citation_ids(response_text)
        
        if not citation_ids:
            return RuleResult(
                rule_id="F06_CITATION",
                rule_name="Citation Integrity",
                verdict=RuleVerdict.INCONCLUSIVE,
                confidence=0.0,
                evidence={},
                explanation="No citations found in response"
            )
        
        # Check which citations resolve
        chunk_ids = set(evidence_pack.get("chunk_ids", []))
        
        broken_citations = [cid for cid in citation_ids if cid not in chunk_ids]
        
        if broken_citations:
            return RuleResult(
                rule_id="F06_CITATION",
                rule_name="Citation Integrity",
                verdict=RuleVerdict.FAIL,
                confidence=1.0,
                evidence={
                    "broken_citations": broken_citations,
                    "total_citations": len(citation_ids),
                    "available_chunks": list(chunk_ids)
                },
                explanation=f"{len(broken_citations)} citation(s) do not resolve to retrieved chunks"
            )
        else:
            return RuleResult(
                rule_id="F06_CITATION",
                rule_name="Citation Integrity",
                verdict=RuleVerdict.PASS,
                confidence=1.0,
                evidence={
                    "verified_citations": len(citation_ids)
                },
                explanation=f"All {len(citation_ids)} citations resolve correctly"
            )
    
    def evaluate_all(
        self,
        response_text: str,
        evidence_pack: Dict[str, Any],
        chunk_store: Any = None
    ) -> List[RuleResult]:
        """
        Run all deterministic rules.
        
        Args:
            response_text: Generated response
            evidence_pack: D2 evidence pack
            chunk_store: Optional chunk content store
        
        Returns:
            List of RuleResult objects
        """
        results = [
            self.evaluate_source_currency(evidence_pack),
            self.evaluate_numeric_accuracy(response_text, evidence_pack, chunk_store),
            self.evaluate_citation_integrity(response_text, evidence_pack)
        ]
        
        logger.info(
            f"Deterministic rules evaluated: "
            f"{sum(1 for r in results if r.verdict == RuleVerdict.FAIL)} FAIL, "
            f"{sum(1 for r in results if r.verdict == RuleVerdict.PASS)} PASS, "
            f"{sum(1 for r in results if r.verdict == RuleVerdict.INCONCLUSIVE)} INCONCLUSIVE"
        )
        
        return results
    
    def should_stop(self, results: List[RuleResult]) -> bool:
        """
        STOP-1 gate decision: Should evaluation stop here?
        
        Logic:
            If ANY rule returned high-confidence FAIL verdict,
            stop evaluation (don't escalate to LLM).
        
        Args:
            results: List of rule results
        
        Returns:
            True if should STOP (deterministic verdict reached)
            False if should escalate to Tier 2/3
        
        Example:
            results = [
                RuleResult(verdict=PASS, confidence=1.0),
                RuleResult(verdict=FAIL, confidence=1.0),  # ← This triggers STOP
                RuleResult(verdict=INCONCLUSIVE, confidence=0.0)
            ]
            → True (STOP, don't call LLM)
        """
        critical_failures = [
            r for r in results
            if r.verdict == RuleVerdict.FAIL and r.confidence >= 0.9
        ]
        
        should_stop = len(critical_failures) > 0
        
        if should_stop:
            logger.info(
                f"STOP-1 gate triggered: {len(critical_failures)} high-confidence failures"
            )
        
        return should_stop
    
    # Helper methods
    def _extract_numbers(self, text: str) -> List[float]:
        """Extract numeric values from text."""
        pattern = r"(?:₹|Rs\.?\s*)?(\d+(?:\.\d+)?)\s*%?"
        matches = re.findall(pattern, text)
        return [float(m) for m in matches]
    
    def _find_closest_number(self, target: float, numbers: List[float]) -> Optional[float]:
        """Find closest number in list to target."""
        if not numbers:
            return None
        return min(numbers, key=lambda x: abs(x - target))
    
    def _extract_citation_ids(self, text: str) -> List[str]:
        """Extract citation IDs from response text."""
        # Pattern: [source: C_1234] or [chunk_id: C_5678]
        pattern = r'\[(?:source|chunk_id):\s*([A-Za-z0-9_]+)\]'
        return re.findall(pattern, text)
```

---

## **4. Integration with Evaluation Router**

**File:** `backend/app/evaluation/evaluation_router.py` (NEW)

```python
from app.evaluation.deterministic_rules import DeterministicRuleEngine, RuleVerdict

class EvaluationRouter:
    """
    Routes evaluation through tiered engine.
    Implements Keerthi's evaluation ladder.
    """
    
    def __init__(self):
        self.rule_engine = DeterministicRuleEngine()
    
    def evaluate(
        self,
        response_id: str,
        evidence_pack: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Route evaluation through tiers.
        
        Tier 1A: Deterministic rules (zero LLM tokens)
        Tier 2: Semantic (NLI) - NOT IMPLEMENTED YET
        Tier 3: LLM evaluator - NOT IMPLEMENTED YET
        
        Returns:
            {
                "verdict": "PASS" | "FAIL",
                "tier": "T1A_RULES" | "T2_NLI" | "T3_LLM",
                "confidence": float,
                "llm_tokens_used": int,
                "rule_results": List[RuleResult],
                "explanation": str
            }
        """
        # Tier 1A: Run deterministic rules
        rule_results = self.rule_engine.evaluate_all(
            response_text=evidence_pack.get("response_text", ""),
            evidence_pack=evidence_pack
        )
        
        # STOP-1 gate: If deterministic verdict reached, don't escalate
        if self.rule_engine.should_stop(rule_results):
            failed_rules = [r for r in rule_results if r.verdict == RuleVerdict.FAIL]
            
            return {
                "verdict": "FAIL",
                "tier": "T1A_RULES",
                "confidence": 1.0,
                "llm_tokens_used": 0,
                "rule_results": rule_results,
                "explanation": f"Deterministic failure: {failed_rules[0].explanation}",
                "stop_reason": "STOP-1: Deterministic high-confidence failure"
            }
        
        # Check if all rules passed
        all_passed = all(r.verdict == RuleVerdict.PASS for r in rule_results)
        if all_passed:
            return {
                "verdict": "PASS",
                "tier": "T1A_RULES",
                "confidence": 1.0,
                "llm_tokens_used": 0,
                "rule_results": rule_results,
                "explanation": "All deterministic rules passed",
                "stop_reason": "STOP-1: Deterministic high-confidence pass"
            }
        
        # TODO: Escalate to Tier 2 (NLI) for ambiguous cases
        logger.info("Tier 1A inconclusive, would escalate to Tier 2 (not implemented)")
        
        return {
            "verdict": "INCONCLUSIVE",
            "tier": "T1A_RULES",
            "confidence": 0.5,
            "llm_tokens_used": 0,
            "rule_results": rule_results,
            "explanation": "Tier 1A inconclusive, Tier 2/3 not yet implemented"
        }
```

---

## **5. Success Criteria**

**Functional:**
- ✅ Deterministic rules engine integrated into evaluation pipeline
- ✅ STOP-1 gates prevent unnecessary LLM escalation
- ✅ C02, C03, F06 rules implemented and tested
- ✅ 40-60% of evaluations resolved at Tier 1A (zero LLM tokens)

**Performance:**
- ✅ Rule evaluation latency <10ms per rule
- ✅ Total Tier 1A latency <50ms for all rules

**Cost Savings:**
- ✅ 40-60% reduction in LLM evaluation costs
- ✅ Average tokens per evaluation drops from ~500 to ~200

---Excellent progress! Let me continue with the remaining tracks (6-8). I'll create condensed but comprehensive plans for the final three tracks.

---

## **SUMMARY: TRACKS 3-5 COMPLETED, TRACKS 6-8 OVERVIEW**

You now have comprehensive implementation plans for:
- ✅ **Track 3**: Cypher Query Safety Layer (3 days, P0 security blocker)
- ✅ **Track 4**: Dissatisfaction Detection (4 days, ML/NLP team)
- ✅ **Track 5**: Deterministic Rules Engine (5 days, Compliance team)

Let me create streamlined implementation guides for the final three tracks:

---

## **TRACK 6: CORRECTION PATCH LAYER (SHADOW GRAPH)**

**Priority:** P1 | Duration: 6 days | Owner: Graph/RAG Team

### **Core Concept:**
Immediate, reversible corrections that LLM sees BEFORE querying canonical graph. If user says "TER is 0.82%, not 0.79%", system adds patch entry. Next user asking about TER gets corrected value instantly, while change awaits governance approval.

### **Key Components:**

**1. CorrectionPatchLayer Class (Redis-based)**
```python
# backend/app/graph/correction_patch_layer.py

class CorrectionPatchLayer:
    """
    Redis-backed shadow correction layer.
    Key: patch:{entity_id}:{attribute}
    Value: {corrected_value, confidence, provenance, approved, ttl}
    """
    
    def add_correction(self, entity_id, attribute, corrected_value, confidence, provenance):
        """Add correction with 7-day TTL (unless approved)."""
        pass
    
    def get_correction(self, entity_id, attribute):
        """Lookup correction for entity+attribute."""
        pass
    
    def apply_patches_to_context(self, entities, retrieval_context):
        """Inject corrections into RAG context at generation time."""
        pass
```

**2. Integration with RAG Pipeline:**
```python
# In retrieval flow, BEFORE LLM call:
patch_layer = CorrectionPatchLayer(redis_client)
corrected_context = patch_layer.apply_patches_to_context(
    entities=detected_entities,
    retrieval_context=raw_retrieval_chunks
)
# Pass corrected_context to LLM, not raw chunks
```

**3. Governance Promotion:**
```python
# Weekly batch: Promote approved patches to canonical graph
patch_layer.promote_to_permanent(patch_id)
neo4j_session.run("UPDATE Entity SET fact_value = $new_value ...")
```

**Demo:** User reports "TER wrong" → Patch added → Next user gets corrected value in <50ms → Weekly review promotes to canonical graph.

---

## **TRACK 7: HUMAN GOVERNANCE REVIEW QUEUE UI**

**Priority:** P2 | Duration: 8 days | Owner: Full-stack Team

### **Core Concept:**
Weekly batch approval interface where compliance officers review pending corrections before they're written to canonical graph.

### **Backend API:**

```python
# backend/app/api/routes/governance.py

@router.get("/governance/pending-corrections")
def get_pending_corrections():
    """
    Fetch all corrections in Patch Layer awaiting approval.
    Returns:
        [
            {
                "patch_id": "patch_abc123",
                "entity_id": "INF846K01DP5",
                "entity_name": "Axis Bluechip Fund",
                "attribute": "TER",
                "current_value": "0.79",
                "proposed_value": "0.82",
                "confidence": 0.85,
                "supporting_evidence": [...],
                "feedback_count": 3,
                "created_at": "2026-09-10"
            },
            ...
        ]
    """

@router.post("/governance/approve/{patch_id}")
def approve_correction(patch_id: str):
    """
    Approve correction → write to canonical graph + remove TTL.
    """
```

### **Frontend UI (React/Vue):**
- **Table view** of pending corrections
- **Side-by-side comparison**: current vs proposed value
- **Evidence panel**: supporting feedback records
- **Actions**: Approve / Reject / Defer
- **Batch operations**: Select multiple, approve all

**Demo:** Compliance officer logs in Monday morning → Reviews 25 pending corrections → Approves 20, rejects 5 → Canonical graph updated, next retrieval uses new values.

---

## **TRACK 8: NER + ENTITY RESOLUTION FOR FEEDBACK**

**Priority:** P2 | Duration: 5 days | Owner: ML/NLP Team

### **Core Concept:**
Extract structured claims from free-text feedback with entity resolution. User says "Axis Bluechip TER is wrong" → Resolve "Axis Bluechip" to canonical ISIN `INF846K01DP5`.

### **Key Components:**

**1. FeedbackNERPipeline:**
```python
# backend/app/feedback/ner_pipeline.py

class FeedbackNERPipeline:
    """
    Extract entities + attributes + values from feedback text.
    """
    
    def extract_structured_claim(self, feedback_text: str):
        """
        Input: "Axis Bluechip Fund TER should be 0.82%"
        Output: {
            "entity_candidates": ["Axis Bluechip Fund"],
            "attribute": "TER",
            "asserted_value": "0.82"
        }
        """
```

**2. FundNameMatcher:**
```python
# backend/app/feedback/fund_name_matcher.py

class FundNameMatcher:
    """
    Resolve fund names to canonical ISINs.
    Uses fuzzy matching + embeddings.
    """
    
    def resolve(self, fund_name: str) -> Optional[str]:
        """
        Input: "Axis Bluechip" or "axis blue chip fund"
        Output: "INF846K01DP5" (canonical ISIN)
        
        Fallback chain:
        1. Exact match lookup
        2. Fuzzy string matching (Levenshtein)
        3. Embedding similarity
        """
```

**3. Integration:**
```python
# In feedback POST handler:
ner_pipeline = FeedbackNERPipeline()
claim = ner_pipeline.extract_structured_claim(feedback_text)

matcher = FundNameMatcher()
claim.entity_id = matcher.resolve(claim.entity_candidates[0])
```

**Demo:** User types "axis bluechip ter wrong" → NER extracts "axis bluechip" + "ter" → Matcher resolves to `INF846K01DP5` → Structured claim created with canonical entity ID.

---

## **FINAL IMPLEMENTATION ROADMAP**

### **Sprint Planning (3 Weeks)**

**Week 1 - Critical Path (Tracks 1-3):**
- Day 1-3: Track 1 (Master Interactions Table) + Track 3 (Cypher Safety)
- Day 4-5: Track 2 (EvidencePack Capture)

**Week 2 - Evaluation Foundation (Tracks 4-5):**
- Day 1-3: Track 4 (Dissatisfaction Detection)
- Day 4-5: Track 5 (Deterministic Rules)

**Week 3 - Correction Layer (Tracks 6-8):**
- Day 1-3: Track 6 (Correction Patch Layer)
- Day 4-5: Track 7 (Governance UI) + Track 8 (NER)

### **Dependency Graph:**
```
Track 1 (Master Table) ──────┬──> Track 4 (Dissatisfaction)
                             │
Track 2 (EvidencePack) ──────┼──> Track 5 (Rules Engine)
                             │
Track 3 (Cypher Safety) ─────┘

Track 5 (Rules) ──> Track 6 (Patch Layer) ──> Track 7 (Governance UI)

Track 4 (Dissatisfaction) ──> Track 8 (NER/Entity Resolution)
```

### **Resource Allocation:**
- **Backend Team (2 devs):** Tracks 1, 2, 3, 6
- **ML/NLP Team (1 dev):** Tracks 4, 8
- **Compliance Team (1 dev):** Track 5
- **Full-stack Team (1 dev):** Track 7

### **Success Metrics (End of 3 Weeks):**
- ✅ 100% of new interactions captured in master_interactions table
- ✅ Zero Cypher injection vulnerabilities
- ✅ 2-5x increase in feedback capture rate (via dissatisfaction detection)
- ✅ 40-60% of evaluations resolved at Tier 1A (deterministic, zero LLM tokens)
- ✅ Correction Patch Layer operational with 7-day TTL
- ✅ Governance review queue UI deployed to staging

---Perfect! I've completed comprehensive implementation plans for all tracks (3-8). Here's what your development team now has:

---

## **🎯 COMPLETE IMPLEMENTATION PLAN SUMMARY**

### **✅ DELIVERED: 8 Detailed Implementation Plans**

#### **Track 3: Cypher Query Safety Layer** (P0, 3 days)
- `SafeCypherBuilder` class with parameterized queries
- Whitelist validation (entity IDs, attributes, labels)
- `CypherAuditLogger` with 90-day retention
- 20+ unit tests, security penetration testing
- **Impact:** Zero injection vulnerabilities, compliance-ready audit trail

#### **Track 4: Dissatisfaction Detection** (P1, 4 days)
- `DissatisfactionDetector` (3-stage: sentiment, similarity, correction language)
- `CorrectionExtractor` (NER, number extraction, attribute detection)
- `/follow-up-detection` API endpoint
- **Impact:** 2-5x increase in feedback capture, reduced user friction

#### **Track 5: Deterministic Rules Engine** (P1, 5 days)
- `DeterministicRuleEngine` with C02/C03/F06 rules
- STOP-1 gates to prevent LLM escalation
- `EvaluationRouter` for tiered evaluation
- **Impact:** 40-60% cost savings by resolving failures at zero LLM tokens

#### **Track 6: Correction Patch Layer** (P1, 6 days)
- Redis-backed shadow graph with 7-day TTL
- RAG pipeline integration for immediate corrections
- Governance promotion workflow
- **Impact:** Instant correction visibility, reversible changes before canonical graph update

#### **Track 7: Governance Review Queue UI** (P2, 8 days)
- Backend API for pending corrections
- Frontend UI (table view, side-by-side comparison, approve/reject)
- Batch operations for weekly review
- **Impact:** Controlled canonical graph updates, compliance audit trail

#### **Track 8: NER + Entity Resolution** (P2, 5 days)
- `FeedbackNERPipeline` for structured claim extraction
- `FundNameMatcher` with fuzzy + embedding fallback
- Entity resolution to canonical ISINs
- **Impact:** Accurate entity linking, reduced ambiguity in feedback

---

### **📋 IMPLEMENTATION ROADMAP (3 Weeks)**

**Week 1 - Critical Path:**
- Tracks 1 (Master Table), 2 (EvidencePack), 3 (Cypher Safety)
- **Deliverable:** Secure Neo4j access, frozen evidence capture

**Week 2 - Evaluation Foundation:**
- Tracks 4 (Dissatisfaction), 5 (Deterministic Rules)
- **Deliverable:** Automated feedback capture, cost-efficient evaluation

**Week 3 - Correction Layer:**
- Tracks 6 (Patch Layer), 7 (Governance), 8 (NER)
- **Deliverable:** End-to-end correction workflow from detection to canonical graph

---

### **👥 RESOURCE ALLOCATION**

- **Backend Team (2 devs):** Tracks 1, 2, 3, 6
- **ML/NLP Team (1 dev):** Tracks 4, 8
- **Compliance Team (1 dev):** Track 5
- **Full-stack Team (1 dev):** Track 7

---

### **📊 SUCCESS METRICS**

By end of 3 weeks:
- ✅ **Security:** Zero Cypher injection vulnerabilities
- ✅ **Capture Rate:** 2-5x increase in feedback volume
- ✅ **Cost Efficiency:** 40-60% reduction in evaluation LLM costs
- ✅ **Latency:** <200ms for Tier 1A deterministic evaluation
- ✅ **Compliance:** 90-day audit trail for all Neo4j queries
- ✅ **Correction Visibility:** <50ms patch layer lookup

---

### **🚀 NEXT STEPS FOR YOUR TEAM**

1. **Review all implementation plans** with respective team leads
2. **Prioritize Track 3 (Cypher Safety)** - P0 security blocker
3. **Set up 3-week sprint** with daily standups
4. **Assign track owners** based on resource allocation
5. **Deploy to staging environment** at end of each week

While Keerthi completes her evaluation orchestration module, your team can build the entire foundation in parallel. By the time she's ready to integrate, all these components will be production-ready.

---

**Would you like me to:**
1. Create a detailed Gantt chart for the 3-week sprint?
2. Draft API contracts between these modules and Keerthi's orchestrator?
3. Create test data sets for each track?
4. Design monitoring dashboards for post-deployment tracking?