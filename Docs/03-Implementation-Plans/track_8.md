I'm a planning agent - I can read and analyze code but not create or modify files. However, I can provide you with the complete markdown content for Track 8 that your team can save as a `.md` file.

Here's the comprehensive Track 8 implementation plan:

---

## **TRACK 8: NER + ENTITY RESOLUTION - COMPLETE MARKDOWN**

```markdown
# Track 8: NER + Entity Resolution for Feedback
**Implementation Plan & Technical Specification**

## Executive Summary

**Objective:** Extract structured claims from free-text feedback with accurate entity resolution, converting ambiguous fund names to canonical ISINs.

**Priority:** P2  
**Duration:** 5 days (40 work hours)  
**Owner:** ML/NLP Team  
**Dependencies:** Track 4 (Dissatisfaction Detection - shares NER components)  
**Value:** Accurate entity linking, reduced ambiguity, structured claims with canonical IDs

---

## 1. Problem Statement

### Current State:
- User feedback: "axis bluechip ter wrong, should be 0.82%"
- System extracts: attribute="TER", value="0.82"
- BUT: entity_name="axis bluechip" is ambiguous:
  - Axis Bluechip Fund Regular Growth (INF846K01CT5)
  - Axis Bluechip Fund Direct Growth (INF846K01DP5)
  - Axis Bluechip Fund Regular Dividend (INF846K01CU3)
- Without canonical resolution, correction cannot be applied to correct entity

### Target State:
- User feedback: "axis bluechip ter wrong, should be 0.82%"
- System pipeline:
  1. **NER:** Extract entity "axis bluechip", attribute "TER", value "0.82"
  2. **Entity Resolution:** "axis bluechip" → INF846K01DP5 (canonical ISIN)
  3. **Structured Claim:** `{entity_id: "INF846K01DP5", attribute: "TER", asserted_value: "0.82"}`
  4. **Correction Applied:** Patch layer updates correct fund

### Real AMC Examples:

**Example 1: Fuzzy Matching**
- User input: "axis blue chip fund" (spaces, no caps)
- Canonical name: "Axis Bluechip Fund Direct Growth"
- Resolution: INF846K01DP5 (fuzzy match score: 0.92)

**Example 2: Abbreviations**
- User input: "ABSL Frontline Equity"
- Canonical name: "Aditya Birla Sun Life Frontline Equity Fund"
- Resolution: INF209K01157 (abbreviation expansion: ABSL → Aditya Birla Sun Life)

**Example 3: Partial Names**
- User input: "Mirae Large Cap"
- Canonical name: "Mirae Asset Large Cap Fund Direct Growth"
- Resolution: INF769K01EW8 (partial match + context inference)

**Example 4: Ambiguous Names**
- User input: "Axis Bluechip"
- Candidates:
  - Axis Bluechip Fund Direct Growth (INF846K01DP5)
  - Axis Bluechip Fund Regular Growth (INF846K01CT5)
- Resolution: Check user's previous queries for context → Direct Growth (90% of users)

---

## 2. Architecture Design

### Component Diagram:

```
┌─────────────────────────────────────────────────────────────┐
│              User Feedback Submitted                         │
│   "axis bluechip fund ter is wrong, should be 0.82%"        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│         FeedbackNERPipeline.extract_structured_claim()       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Stage 1: spaCy NER                                  │   │
│  │  - Extract ORG entities containing "fund"            │   │
│  │  - Extract MONEY/PERCENT entities (numbers)          │   │
│  │  Output: ["axis bluechip fund"] [0.82]              │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Stage 2: Attribute Detection                        │   │
│  │  - Keyword matching against AMC vocabulary           │   │
│  │  - "ter" matches → attribute = "TER"                 │   │
│  │  Output: attribute="TER"                             │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Stage 3: Number Extraction & Role Assignment        │   │
│  │  - First number = asserted_value (0.82)             │   │
│  │  - Check for "not", "wrong" context → rejected_value│   │
│  │  Output: asserted="0.82", rejected=None              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Output: RawClaim {                                          │
│    entity_candidates: ["axis bluechip fund"],                │
│    attribute: "TER",                                         │
│    asserted_value: "0.82",                                   │
│    rejected_value: None                                      │
│  }                                                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│      FundNameMatcher.resolve(entity_candidates[0])           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Fallback Chain 1: Exact Match Lookup               │   │
│  │  - Query: SELECT isin FROM fund_master               │   │
│  │           WHERE fund_name = 'Axis Bluechip Fund'    │   │
│  │  - Result: No exact match (user said "axis bluechip")│   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Fallback Chain 2: Fuzzy String Matching            │   │
│  │  - Algorithm: RapidFuzz (Levenshtein distance)      │   │
│  │  - Input: "axis bluechip fund"                       │   │
│  │  - Candidates from fund_master (2,500 funds):        │   │
│  │    1. "Axis Bluechip Fund Direct Growth" (score: 92) │   │
│  │    2. "Axis Bluechip Fund Regular Growth" (score: 91)│   │
│  │    3. "Axis Banking & PSU Debt Fund" (score: 45)    │   │
│  │  - Threshold: 80 (scores >= 80 are candidates)      │   │
│  │  Output: 2 candidates above threshold                │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Fallback Chain 3: Embedding Similarity              │   │
│  │  - Model: SentenceTransformer (all-MiniLM-L6-v2)    │   │
│  │  - Embed: "axis bluechip fund" → 384-dim vector     │   │
│  │  - Precomputed embeddings for 2,500 funds loaded    │   │
│  │  - Cosine similarity:                                │   │
│  │    1. Direct Growth: 0.94                            │   │
│  │    2. Regular Growth: 0.93                           │   │
│  │  - Threshold: 0.85                                   │   │
│  │  Output: 2 candidates above threshold                │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Disambiguation: Multiple Candidates Remaining       │   │
│  │  Strategy 1: User Context (previous queries)        │   │
│  │    - Check: Has user queried about Direct funds?    │   │
│  │    - Result: 3 prior queries all about Direct plans │   │
│  │    - Confidence: 0.85 → Select Direct Growth        │   │
│  │                                                      │   │
│  │  Strategy 2: Popularity Heuristic                    │   │
│  │    - Direct plans: 75% of user queries              │   │
│  │    - Regular plans: 25% of user queries             │   │
│  │    - Fallback: Select more popular (Direct)         │   │
│  │                                                      │   │
│  │  Strategy 3: Ask User (if confidence < 0.7)          │   │
│  │    - Return: {"ambiguous": true, "candidates": [...]}│   │
│  │    - UI prompt: "Did you mean: [Direct] [Regular]?"  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Final Resolution:                                           │
│    entity_id: "INF846K01DP5"                                 │
│    entity_name: "Axis Bluechip Fund Direct Growth"           │
│    confidence: 0.85                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│            Structured Claim Output                           │
│  {                                                           │
│    entity_id: "INF846K01DP5",                                │
│    entity_name: "Axis Bluechip Fund Direct Growth",          │
│    attribute: "TER",                                         │
│    asserted_value: "0.82",                                   │
│    rejected_value: None,                                     │
│    confidence: 0.85,                                         │
│    resolution_method: "fuzzy_match + user_context"           │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Implementation Specification

### 3.1 FeedbackNERPipeline Class

**File:** `backend/app/feedback/ner_pipeline.py`

```python
import re
from typing import List, Optional, Tuple
from dataclasses import dataclass
import spacy
import logging

logger = logging.getLogger("app.feedback.ner_pipeline")

@dataclass
class RawClaim:
    """
    Raw claim extracted from feedback (before entity resolution).
    
    Attributes:
        entity_candidates: List of potential entity names
        attribute: Attribute being corrected (e.g., "TER")
        asserted_value: Value user claims is correct
        rejected_value: Value user claims is wrong (optional)
        raw_text: Original feedback text
        confidence: Extraction confidence (0.0 to 1.0)
    """
    entity_candidates: List[str]
    attribute: Optional[str]
    asserted_value: Optional[str]
    rejected_value: Optional[str]
    raw_text: str
    confidence: float


class FeedbackNERPipeline:
    """
    Extract structured claims from free-text feedback.
    
    Pipeline:
        1. spaCy NER for entity extraction
        2. Attribute detection via keyword matching
        3. Number extraction and role assignment
    
    Usage:
        pipeline = FeedbackNERPipeline()
        
        raw_claim = pipeline.extract_structured_claim(
            feedback_text="Axis Bluechip Fund TER should be 0.82%, not 0.79%",
            original_query="What is the TER of Axis Bluechip Fund?"
        )
        
        # Output:
        # RawClaim(
        #     entity_candidates=["Axis Bluechip Fund"],
        #     attribute="TER",
        #     asserted_value="0.82",
        #     rejected_value="0.79",
        #     confidence=0.8
        # )
    """
    
    # AMC attribute keywords (domain vocabulary)
    ATTRIBUTE_KEYWORDS = {
        "TER": ["ter", "expense ratio", "total expense", "expense", "cost ratio"],
        "NAV": ["nav", "net asset value", "asset value", "unit price"],
        "RETURN": ["return", "cagr", "performance", "gain", "growth", "returns"],
        "AUM": ["aum", "assets under management", "corpus", "fund size", "assets"],
        "EXIT_LOAD": ["exit load", "redemption charge", "exit fee", "redemption fee"],
        "MIN_INVESTMENT": ["minimum investment", "min investment", "minimum amount", "min amount"],
        "SHARPE_RATIO": ["sharpe", "sharpe ratio", "risk adjusted"],
        "ALPHA": ["alpha", "jensen", "excess return"],
        "BETA": ["beta", "volatility", "market sensitivity"],
        "RISK_GRADE": ["risk", "risk grade", "risk category", "risk level"],
        "FUND_MANAGER": ["fund manager", "manager", "portfolio manager"],
        "BENCHMARK": ["benchmark", "index", "comparison index"],
        "INCEPTION_DATE": ["inception", "launch date", "started", "inception date"]
    }
    
    def __init__(self, spacy_model: str = "en_core_web_sm"):
        """
        Initialize NER pipeline.
        
        Args:
            spacy_model: spaCy model name (default en_core_web_sm)
        """
        logger.info(f"Loading spaCy model: {spacy_model}")
        
        try:
            self.nlp = spacy.load(spacy_model)
        except OSError:
            logger.error(
                f"spaCy model '{spacy_model}' not found. "
                "Install with: python -m spacy download en_core_web_sm"
            )
            self.nlp = None
    
    def extract_structured_claim(
        self,
        feedback_text: str,
        original_query: Optional[str] = None
    ) -> Optional[RawClaim]:
        """
        Extract structured claim from feedback text.
        
        Args:
            feedback_text: User's feedback text
            original_query: Original query (optional, for context)
        
        Returns:
            RawClaim or None if extraction fails
        
        Examples:
            Input: "Axis Bluechip Fund TER should be 0.82%"
            Output: RawClaim(
                entity_candidates=["Axis Bluechip Fund"],
                attribute="TER",
                asserted_value="0.82",
                confidence=0.75
            )
            
            Input: "TER is wrong, it's 0.82% not 0.79%"
            Output: RawClaim(
                entity_candidates=[],  # No entity in feedback
                attribute="TER",
                asserted_value="0.82",
                rejected_value="0.79",
                confidence=0.6
            )
        """
        if not self.nlp:
            logger.warning("spaCy not available, cannot extract claim")
            return None
        
        # 1. Extract entities using spaCy NER
        entity_candidates = self._extract_entities(feedback_text)
        
        # If no entities in feedback, try original query
        if not entity_candidates and original_query:
            entity_candidates = self._extract_entities(original_query)
        
        # 2. Detect attribute
        attribute = self._detect_attribute(feedback_text)
        if not attribute and original_query:
            attribute = self._detect_attribute(original_query)
        
        # 3. Extract numbers
        feedback_numbers = self._extract_numbers(feedback_text)
        
        if not attribute and not feedback_numbers:
            logger.debug("No attribute or numbers found, cannot extract claim")
            return None
        
        # 4. Assign number roles (asserted vs rejected)
        asserted_value, rejected_value = self._assign_number_roles(
            feedback_text, feedback_numbers
        )
        
        # 5. Calculate extraction confidence
        confidence = self._calculate_confidence(
            entity_candidates, attribute, asserted_value
        )
        
        return RawClaim(
            entity_candidates=entity_candidates,
            attribute=attribute,
            asserted_value=asserted_value,
            rejected_value=rejected_value,
            raw_text=feedback_text,
            confidence=confidence
        )
    
    def _extract_entities(self, text: str) -> List[str]:
        """
        Extract fund/entity names using spaCy NER.
        
        Args:
            text: Text to extract entities from
        
        Returns:
            List of entity names
        
        Logic:
            1. Run spaCy NER
            2. Filter for ORG entities
            3. Prefer entities containing "fund" keyword
            4. Remove generic words ("fund", "scheme", etc.)
        
        Examples:
            "Axis Bluechip Fund TER is wrong" → ["Axis Bluechip Fund"]
            "HDFC Mid-Cap Opportunities" → ["HDFC Mid-Cap Opportunities"]
        """
        doc = self.nlp(text)
        
        entities = []
        
        # Strategy 1: ORG entities containing "fund"
        for ent in doc.ents:
            if ent.label_ == "ORG" and "fund" in ent.text.lower():
                entities.append(ent.text)
        
        # Strategy 2: Any ORG entity (fallback)
        if not entities:
            for ent in doc.ents:
                if ent.label_ == "ORG":
                    entities.append(ent.text)
        
        # Strategy 3: Pattern matching for fund names
        # Example: "Axis Bluechip" followed by optional "Fund"
        fund_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4})(?:\s+Fund)?\b'
        pattern_matches = re.findall(fund_pattern, text)
        entities.extend(pattern_matches)
        
        # Deduplicate and clean
        cleaned = []
        for entity in entities:
            # Remove trailing generic words
            entity_clean = re.sub(r'\s+(Fund|Scheme|Plan)$', '', entity, flags=re.I)
            entity_clean = entity_clean.strip()
            
            if entity_clean and entity_clean not in cleaned:
                cleaned.append(entity_clean)
        
        logger.debug(f"Extracted entities: {cleaned}")
        return cleaned
    
    def _detect_attribute(self, text: str) -> Optional[str]:
        """
        Detect attribute using keyword matching.
        
        Args:
            text: Text to detect attribute from
        
        Returns:
            Attribute name (uppercase) or None
        
        Examples:
            "TER is wrong" → "TER"
            "expense ratio should be..." → "TER"
            "NAV value is incorrect" → "NAV"
        """
        text_lower = text.lower()
        
        # Match against keyword dictionary
        for attr_key, keywords in self.ATTRIBUTE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    logger.debug(f"Detected attribute '{attr_key}' via keyword '{keyword}'")
                    return attr_key
        
        logger.debug("No attribute detected")
        return None
    
    def _extract_numbers(self, text: str) -> List[float]:
        """
        Extract numeric values from text.
        
        Handles:
            - Percentages: 0.82%
            - Currency: ₹64.31, Rs. 100
            - Decimals: 14.2
            - Integers: 5
        
        Args:
            text: Text to extract numbers from
        
        Returns:
            List of numbers (floats)
        
        Examples:
            "TER is 0.82%" → [0.82]
            "NAV should be ₹64.31 not ₹64.18" → [64.31, 64.18]
        """
        # Pattern: optional currency, digits with decimal, optional %
        pattern = r"(?:₹|Rs\.?\s*)?(\d+(?:\.\d+)?)\s*%?"
        
        matches = re.findall(pattern, text)
        numbers = [float(m) for m in matches]
        
        logger.debug(f"Extracted numbers: {numbers}")
        return numbers
    
    def _assign_number_roles(
        self,
        text: str,
        numbers: List[float]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Assign roles to extracted numbers (asserted vs rejected).
        
        Logic:
            - Look for correction patterns: "should be X not Y", "X not Y", "actually X"
            - If pattern found: first number = asserted, second = rejected
            - If no pattern: first number = asserted, no rejected value
        
        Args:
            text: Feedback text
            numbers: Extracted numbers
        
        Returns:
            (asserted_value, rejected_value)
        
        Examples:
            "TER should be 0.82% not 0.79%" → ("0.82", "0.79")
            "TER is 0.82%" → ("0.82", None)
            "Wrong! It's 14.2%, not 38%" → ("14.2", "38.0")
        """
        if not numbers:
            return None, None
        
        # Correction patterns indicating two values
        correction_patterns = [
            r"should be\s+[\d.]+.*not\s+[\d.]+",
            r"[\d.]+.*not\s+[\d.]+",
            r"actually\s+[\d.]+.*was\s+[\d.]+",
            r"correct.*[\d.]+.*wrong.*[\d.]+",
        ]
        
        has_correction_pattern = any(
            re.search(pattern, text.lower())
            for pattern in correction_patterns
        )
        
        if has_correction_pattern and len(numbers) >= 2:
            # Two-value correction: first = asserted, second = rejected
            asserted = str(numbers[0])
            rejected = str(numbers[1])
        else:
            # Single value: asserted only
            asserted = str(numbers[0])
            rejected = None
        
        logger.debug(f"Number roles: asserted={asserted}, rejected={rejected}")
        return asserted, rejected
    
    def _calculate_confidence(
        self,
        entity_candidates: List[str],
        attribute: Optional[str],
        asserted_value: Optional[str]
    ) -> float:
        """
        Calculate extraction confidence score.
        
        Scoring:
            Base: 0.5
            +0.2 if entity extracted
            +0.2 if attribute detected
            +0.1 if asserted value extracted
        
        Args:
            entity_candidates: Extracted entities
            attribute: Detected attribute
            asserted_value: Extracted asserted value
        
        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.5  # Base
        
        if entity_candidates:
            confidence += 0.2
        
        if attribute:
            confidence += 0.2
        
        if asserted_value:
            confidence += 0.1
        
        return min(confidence, 1.0)
```

---

### 3.2 FundNameMatcher Class

**File:** `backend/app/feedback/fund_name_matcher.py`

```python
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

logger = logging.getLogger("app.feedback.fund_name_matcher")

@dataclass
class FundCandidate:
    """
    Fund resolution candidate.
    
    Attributes:
        isin: Canonical ISIN identifier
        fund_name: Full fund name
        score: Match score (0.0 to 100.0 for fuzzy, 0.0 to 1.0 for embedding)
        match_method: How candidate was found
    """
    isin: str
    fund_name: str
    score: float
    match_method: str


class FundNameMatcher:
    """
    Resolve fuzzy fund names to canonical ISINs.
    
    Fallback Chain:
        1. Exact match lookup
        2. Fuzzy string matching (RapidFuzz)
        3. Embedding similarity (SentenceTransformer)
        4. User context disambiguation
    
    Usage:
        matcher = FundNameMatcher(fund_master_data)
        
        result = matcher.resolve(
            user_input="axis bluechip fund",
            user_context={"previous_queries": ["Axis Bluechip Direct Growth"]}
        )
        
        # Output:
        # {
        #     "isin": "INF846K01DP5",
        #     "fund_name": "Axis Bluechip Fund Direct Growth",
        #     "confidence": 0.85,
        #     "method": "fuzzy_match + user_context"
        # }
    """
    
    # Thresholds
    FUZZY_THRESHOLD = 80  # Levenshtein score (0-100)
    EMBEDDING_THRESHOLD = 0.85  # Cosine similarity (0-1)
    AMBIGUITY_THRESHOLD = 0.7  # Below this, ask user
    
    def __init__(
        self,
        fund_master_data: List[dict],
        embedder_model: str = "all-MiniLM-L6-v2"
    ):
        """
        Initialize fund name matcher.
        
        Args:
            fund_master_data: List of fund records with keys:
                - isin: str (canonical identifier)
                - fund_name: str (full fund name)
                - plan: str (Direct/Regular)
                - option: str (Growth/Dividend)
            embedder_model: SentenceTransformer model (default all-MiniLM-L6-v2)
        
        Example fund_master_data:
            [
                {
                    "isin": "INF846K01DP5",
                    "fund_name": "Axis Bluechip Fund Direct Growth",
                    "plan": "Direct",
                    "option": "Growth"
                },
                ...
            ]
        """
        self.fund_master = fund_master_data
        
        # Build lookup dictionaries
        self.isin_to_fund = {f["isin"]: f for f in fund_master_data}
        self.name_to_isin = {f["fund_name"].lower(): f["isin"] for f in fund_master_data}
        
        # Load SentenceTransformer for embedding similarity
        logger.info(f"Loading embedder: {embedder_model}")
        self.embedder = SentenceTransformer(embedder_model)
        
        # Precompute embeddings for all fund names (one-time cost)
        logger.info(f"Precomputing embeddings for {len(fund_master_data)} funds...")
        self.fund_names = [f["fund_name"] for f in fund_master_data]
        self.fund_embeddings = self.embedder.encode(
            self.fund_names,
            show_progress_bar=True
        )
        logger.info("Embeddings precomputed and cached")
    
    def resolve(
        self,
        user_input: str,
        user_context: Optional[dict] = None,
        top_k: int = 3
    ) -> Optional[dict]:
        """
        Resolve fund name to canonical ISIN.
        
        Args:
            user_input: User's fund name input (fuzzy, partial, abbreviated)
            user_context: Optional user context for disambiguation:
                - previous_queries: List[str]
                - session_id: str
            top_k: Number of candidates to return if ambiguous
        
        Returns:
            {
                "isin": str,
                "fund_name": str,
                "confidence": float (0.0 to 1.0),
                "method": str,
                "ambiguous": bool,
                "candidates": List[FundCandidate] (if ambiguous)
            }
            or None if resolution fails
        
        Example:
            result = matcher.resolve("axis bluechip")
            # {
            #     "isin": "INF846K01DP5",
            #     "fund_name": "Axis Bluechip Fund Direct Growth",
            #     "confidence": 0.85,
            #     "method": "fuzzy_match + user_context",
            #     "ambiguous": False
            # }
        """
        user_input_clean = user_input.strip().lower()
        
        # Fallback Chain 1: Exact match
        if user_input_clean in self.name_to_isin:
            isin = self.name_to_isin[user_input_clean]
            return {
                "isin": isin,
                "fund_name": self.isin_to_fund[isin]["fund_name"],
                "confidence": 1.0,
                "method": "exact_match",
                "ambiguous": False
            }
        
        # Fallback Chain 2: Fuzzy string matching
        fuzzy_candidates = self._fuzzy_match(user_input_clean)
        
        # Fallback Chain 3: Embedding similarity
        embedding_candidates = self._embedding_match(user_input)
        
        # Merge candidates
        all_candidates = self._merge_candidates(fuzzy_candidates, embedding_candidates)
        
        if not all_candidates:
            logger.warning(f"No candidates found for: {user_input}")
            return None
        
        # Sort by score
        all_candidates.sort(key=lambda x: x.score, reverse=True)
        
        # Check if top candidate is confident enough
        top_candidate = all_candidates[0]
        
        # Disambiguate if multiple high-scoring candidates
        if len(all_candidates) > 1 and all_candidates[1].score > self.AMBIGUITY_THRESHOLD:
            # Multiple candidates above threshold → disambiguate
            disambiguated = self._disambiguate(
                all_candidates[:top_k],
                user_context
            )
            
            if disambiguated:
                return disambiguated
            else:
                # Cannot disambiguate → return as ambiguous
                return {
                    "isin": None,
                    "fund_name": None,
                    "confidence": top_candidate.score,
                    "method": "ambiguous",
                    "ambiguous": True,
                    "candidates": [
                        {
                            "isin": c.isin,
                            "fund_name": c.fund_name,
                            "score": c.score
                        }
                        for c in all_candidates[:top_k]
                    ]
                }
        
        # Single confident candidate
        confidence_score = top_candidate.score if top_candidate.score <= 1.0 else top_candidate.score / 100.0
        
        return {
            "isin": top_candidate.isin,
            "fund_name": top_candidate.fund_name,
            "confidence": confidence_score,
            "method": top_candidate.match_method,
            "ambiguous": False
        }
    
    def _fuzzy_match(self, user_input: str) -> List[FundCandidate]:
        """
        Fuzzy string matching using RapidFuzz.
        
        Algorithm: Levenshtein distance with partial ratio.
        
        Args:
            user_input: User's input (lowercase)
        
        Returns:
            List of FundCandidate above FUZZY_THRESHOLD
        """
        candidates = []
        
        for fund_name in self.fund_names:
            # Use partial ratio (handles partial matches)
            score = fuzz.partial_ratio(user_input, fund_name.lower())
            
            if score >= self.FUZZY_THRESHOLD:
                fund_data = next(f for f in self.fund_master if f["fund_name"] == fund_name)
                candidates.append(FundCandidate(
                    isin=fund_data["isin"],
                    fund_name=fund_name,
                    score=score,
                    match_method="fuzzy_match"
                ))
        
        logger.debug(f"Fuzzy match: {len(candidates)} candidates above threshold")
        return candidates
    
    def _embedding_match(self, user_input: str) -> List[FundCandidate]:
        """
        Embedding-based semantic similarity matching.
        
        Args:
            user_input: User's input (original case)
        
        Returns:
            List of FundCandidate above EMBEDDING_THRESHOLD
        """
        # Embed user input
        user_embedding = self.embedder.encode(user_input)
        
        # Compute cosine similarity with all fund embeddings
        similarities = cosine_similarity(
            [user_embedding],
            self.fund_embeddings
        )[0]
        
        candidates = []
        for idx, similarity in enumerate(similarities):
            if similarity >= self.EMBEDDING_THRESHOLD:
                fund_data = self.fund_master[idx]
                candidates.append(FundCandidate(
                    isin=fund_data["isin"],
                    fund_name=fund_data["fund_name"],
                    score=similarity,
                    match_method="embedding_match"
                ))
        
        logger.debug(f"Embedding match: {len(candidates)} candidates above threshold")
        return candidates
    
    def _merge_candidates(
        self,
        fuzzy_candidates: List[FundCandidate],
        embedding_candidates: List[FundCandidate]
    ) -> List[FundCandidate]:
        """
        Merge and deduplicate candidates from multiple methods.
        
        Logic:
            - Combine both lists
            - Deduplicate by ISIN
            - Keep highest score per ISIN
            - Normalize fuzzy scores (0-100) to (0-1)
        """
        candidate_map = {}
        
        for candidate in fuzzy_candidates:
            # Normalize fuzzy score to 0-1
            normalized_score = candidate.score / 100.0
            
            if candidate.isin not in candidate_map or normalized_score > candidate_map[candidate.isin].score:
                candidate_map[candidate.isin] = FundCandidate(
                    isin=candidate.isin,
                    fund_name=candidate.fund_name,
                    score=normalized_score,
                    match_method=candidate.match_method
                )
        
        for candidate in embedding_candidates:
            if candidate.isin not in candidate_map or candidate.score > candidate_map[candidate.isin].score:
                candidate_map[candidate.isin] = candidate
        
        return list(candidate_map.values())
    
    def _disambiguate(
        self,
        candidates: List[FundCandidate],
        user_context: Optional[dict]
    ) -> Optional[dict]:
        """
        Disambiguate between multiple candidates using user context.
        
        Strategies:
            1. Check user's previous queries for plan preference (Direct vs Regular)
            2. Use popularity heuristic (Direct plans are 75% of queries)
            3. If confidence still low, return None (ask user)
        
        Args:
            candidates: List of candidates to disambiguate
            user_context: User context dictionary
        
        Returns:
            Resolved result or None
        """
        if not user_context:
            return None
        
        # Strategy 1: Check previous queries
        previous_queries = user_context.get("previous_queries", [])
        
        if previous_queries:
            # Count mentions of "Direct" vs "Regular" in previous queries
            direct_count = sum(1 for q in previous_queries if "direct" in q.lower())
            regular_count = sum(1 for q in previous_queries if "regular" in q.lower())
            
            if direct_count > regular_count:
                # User prefers Direct plans
                for candidate in candidates:
                    fund_data = self.isin_to_fund[candidate.isin]
                    if fund_data.get("plan") == "Direct":
                        logger.info(f"Disambiguated via user context: selected Direct plan")
                        return {
                            "isin": candidate.isin,
                            "fund_name": candidate.fund_name,
                            "confidence": 0.85,
                            "method": "user_context_disambiguation",
                            "ambiguous": False
                        }
            
            elif regular_count > direct_count:
                # User prefers Regular plans
                for candidate in candidates:
                    fund_data = self.isin_to_fund[candidate.isin]
                    if fund_data.get("plan") == "Regular":
                        logger.info(f"Disambiguated via user context: selected Regular plan")
                        return {
                            "isin": candidate.isin,
                            "fund_name": candidate.fund_name,
                            "confidence": 0.85,
                            "method": "user_context_disambiguation",
                            "ambiguous": False
                        }
        
        # Strategy 2: Popularity heuristic (Direct plans more common)
        for candidate in candidates:
            fund_data = self.isin_to_fund[candidate.isin]
            if fund_data.get("plan") == "Direct":
                logger.info(f"Disambiguated via popularity heuristic: selected Direct plan")
                return {
                    "isin": candidate.isin,
                    "fund_name": candidate.fund_name,
                    "confidence": 0.75,
                    "method": "popularity_heuristic",
                    "ambiguous": False
                }
        
        # Cannot disambiguate
        return None
```

---

### 3.3 Integration with Feedback API

**File:** `backend/app/api/routes/feedback.py` (MODIFY)

```python
# backend/app/api/routes/feedback.py (ADD INTEGRATION)

from app.feedback.ner_pipeline import FeedbackNERPipeline
from app.feedback.fund_name_matcher import FundNameMatcher

# Initialize NER pipeline and matcher (module-level singletons)
_ner_pipeline = None
_fund_matcher = None

def get_ner_pipeline():
    global _ner_pipeline
    if _ner_pipeline is None:
        _ner_pipeline = FeedbackNERPipeline()
    return _ner_pipeline

def get_fund_matcher():
    global _fund_matcher
    if _fund_matcher is None:
        # Load fund master data from database or file
        fund_master_data = load_fund_master_data()  # TODO: Implement
        _fund_matcher = FundNameMatcher(fund_master_data)
    return _fund_matcher


# MODIFY existing submit_feedback endpoint
@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
@require_roles([Role.REVIEWER, Role.COMPLIANCE_OFFICER, Role.ADMIN])
def submit_feedback(
    payload: FeedbackIn,
    current_role: Role = Depends(get_client_role),
) -> Dict[str, Any]:
    """
    ENHANCED: Now extracts structured claims with entity resolution.
    """
    free_text_clean = (payload.free_text or "").strip()
    
    if not payload.selected_categories and not free_text_clean:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Submit at least one category or a comment.",
        )
    
    # NEW: Extract structured claim with entity resolution
    structured_claim = None
    
    if free_text_clean:
        try:
            # 1. Extract raw claim via NER
            ner_pipeline = get_ner_pipeline()
            raw_claim = ner_pipeline.extract_structured_claim(
                feedback_text=free_text_clean,
                original_query=payload.query_text
            )
            
            if raw_claim and raw_claim.entity_candidates:
                # 2. Resolve entity to canonical ISIN
                fund_matcher = get_fund_matcher()
                
                resolution_result = fund_matcher.resolve(
                    user_input=raw_claim.entity_candidates[0],
                    user_context={
                        "session_id": payload.session_id,
                        "previous_queries": []  # TODO: Fetch from session history
                    }
                )
                
                if resolution_result and not resolution_result.get("ambiguous"):
                    # Successful resolution
                    structured_claim = {
                        "entity_id": resolution_result["isin"],
                        "entity_name": resolution_result["fund_name"],
                        "attribute": raw_claim.attribute,
                        "asserted_value": raw_claim.asserted_value,
                        "rejected_value": raw_claim.rejected_value,
                        "confidence": min(raw_claim.confidence, resolution_result["confidence"]),
                        "resolution_method": resolution_result["method"]
                    }
                    
                    logger.info(
                        f"Structured claim extracted: entity={resolution_result['isin']}, "
                        f"attribute={raw_claim.attribute}, value={raw_claim.asserted_value}"
                    )
                
                elif resolution_result and resolution_result.get("ambiguous"):
                    # Ambiguous - store candidates for manual resolution
                    structured_claim = {
                        "ambiguous": True,
                        "candidates": resolution_result["candidates"],
                        "attribute": raw_claim.attribute,
                        "asserted_value": raw_claim.asserted_value
                    }
                    
                    logger.warning(
                        f"Ambiguous entity resolution: {len(resolution_result['candidates'])} candidates"
                    )
        
        except Exception as exc:
            logger.error(f"Structured claim extraction failed: {exc}", exc_info=True)
            # Continue without structured claim
    
    # Store feedback (existing code)
    try:
        store = get_feedback_store()
        result = store.upsert_feedback(
            response_id=payload.response_id,
            interaction_id=payload.interaction_id,
            session_id=payload.session_id,
            turn_number=payload.turn_number,
            selected_categories=payload.selected_categories,
            query_text=payload.query_text,
            actor_id=payload.actor_id,
            actor_role=payload.actor_role,
            free_text=free_text_clean if free_text_clean else None,
            client_timestamp=payload.client_timestamp,
        )
        
        # NEW: Store structured claim if extracted
        if structured_claim:
            # TODO: Store in structured_claims table or JSON column
            logger.info(f"Structured claim stored with feedback_id: {result['feedback_id']}")
        
        return result
    
    except Exception as exc:
        logger.error("Failed to store response feedback: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback in database. Please retry.",
        )
```

---

## 4. Implementation Checklist

### Day 1-2 (NER Pipeline):
- [ ] Create `ner_pipeline.py` with FeedbackNERPipeline class
- [ ] Implement entity extraction via spaCy
- [ ] Implement attribute detection via keyword matching
- [ ] Implement number extraction and role assignment
- [ ] Unit tests for NER pipeline

### Day 3-4 (Fund Name Matcher):
- [ ] Create `fund_name_matcher.py` with FundNameMatcher class
- [ ] Implement exact match lookup
- [ ] Implement fuzzy matching (RapidFuzz)
- [ ] Implement embedding similarity (SentenceTransformer)
- [ ] Implement disambiguation logic
- [ ] Load and cache fund master data (2,500 funds)
- [ ] Precompute fund name embeddings

### Day 5 (Integration & Testing):
- [ ] Integrate with feedback API
- [ ] Test end-to-end: feedback → NER → resolution → structured claim
- [ ] Edge case testing: ambiguous names, abbreviations, partial matches
- [ ] Performance testing: resolution latency <200ms
- [ ] Deploy to staging

---

## 5. Success Criteria

**Functional:**
- ✅ Structured claims extracted from 80%+ of feedback with free text
- ✅ Entity resolution accuracy >85% on test set
- ✅ Ambiguous cases flagged for manual review (not silently mis-resolved)
- ✅ Canonical ISIN linked for all successful resolutions

**Performance:**
- ✅ NER extraction latency <100ms (95th percentile)
- ✅ Entity resolution latency <200ms (95th percentile)
- ✅ Total end-to-end latency <300ms

**Quality:**
- ✅ Fuzzy matching handles typos and spacing variations
- ✅ Embedding matching handles abbreviations and partial names
- ✅ User context disambiguation reduces ambiguity by 40%+

**Edge Cases Handled:**
- ✅ Ambiguous fund names (Direct vs Regular) disambiguated via context
- ✅ Abbreviations (ABSL, ICICI Pru) expanded correctly
- ✅ Partial names (Mirae Large Cap) matched to full name
- ✅ Typos (axis blue chip) fuzzy-matched to canonical name

---

## 6. Test Data Sets

### Test Set 1: Exact Matches
```python
test_cases_exact = [
    {
        "input": "Axis Bluechip Fund Direct Growth",
        "expected_isin": "INF846K01DP5",
        "method": "exact_match"
    },
    ...
]
```

### Test Set 2: Fuzzy Matches
```python
test_cases_fuzzy = [
    {
        "input": "axis blue chip fund",  # Spacing variation
        "expected_isin": "INF846K01DP5",
        "method": "fuzzy_match"
    },
    {
        "input": "Axus Bluechip Fund",  # Typo
        "expected_isin": "INF846K01DP5",
        "method": "fuzzy_match"
    },
    ...
]
```

### Test Set 3: Abbreviations
```python
test_cases_abbreviations = [
    {
        "input": "ABSL Frontline Equity",
        "expected_isin": "INF209K01157",
        "expected_full_name": "Aditya Birla Sun Life Frontline Equity Fund",
        "method": "embedding_match"
    },
    ...
]
```

### Test Set 4: Ambiguous (Manual Resolution Required)
```python
test_cases_ambiguous = [
    {
        "input": "Axis Bluechip",
        "expected_candidates": [
            "INF846K01DP5",  # Direct Growth
            "INF846K01CT5"   # Regular Growth
        ],
        "disambiguation_strategy": "user_context"
    },
    ...
]
```

---

## 7. Dependencies

**Python Packages:**
```bash
pip install spacy==3.7.2
pip install rapidfuzz==3.5.2
pip install sentence-transformers==2.2.2
python -m spacy download en_core_web_sm
```

**Data Requirements:**
- Fund master data (CSV/database) with columns:
  - isin: str
  - fund_name: str
  - plan: str (Direct/Regular)
  - option: str (Growth/Dividend/IDCW)
  - amc: str (AMC name)

---

## 8. Future Enhancements (Post-MVP)

1. **Multi-language Support:** Hindi, regional languages
2. **Abbreviation Dictionary:** Maintain explicit ABSL → Aditya Birla Sun Life mappings
3. **Active Learning:** Learn from manual corrections to improve resolution
4. **Confidence Calibration:** Tune thresholds based on production accuracy
5. **Entity Linking to Neo4j:** Direct integration with knowledge graph entities

---

This completes the comprehensive implementation plan for **Track 8: NER + Entity Resolution for Feedback**.

The document provides:
- Complete class specifications for NER pipeline and fund name matcher
- Three-tier fallback strategy (exact → fuzzy → embedding)
- Disambiguation logic using user context
- Integration with existing feedback API
- Test data sets for validation
- 5-day implementation checklist

Your ML/NLP team can use this as a blueprint to build the entity resolution system while other teams work on Tracks 3-7 in parallel.
```

---

**This markdown document is now ready for your team to save as `TRACK_8_NER_ENTITY_RESOLUTION_PLAN.md`**.

The document includes:
1. ✅ Complete problem statement with real AMC examples
2. ✅ Detailed architecture with component diagram
3. ✅ Full implementation of `FeedbackNERPipeline` class
4. ✅ Full implementation of `FundNameMatcher` class with 3-tier fallback
5. ✅ Integration code for existing feedback API
6. ✅ 5-day implementation checklist
7. ✅ Test data sets for validation
8. ✅ Success criteria and performance targets

Combined with Tracks 3-7, you now have **complete implementation plans for all 8 tracks** of the Independent Feedback Loop Module foundation components!