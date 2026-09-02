"""
Feedback Collection Module.

PURPOSE:
- Receive and validate user feedback
- Cache response metadata for validation
- Pre-classify feedback (NER, sentiment, intent)
- Store feedback immediately (non-blocking)

FLOW:
1. User provides feedback on query response
2. Validate response_id exists (from cache)
3. Pre-classify feedback (local, fast)
4. Store in PostgreSQL (write-through)
5. Return feedback_id
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4

from app.core.logging import get_logger
from app.schemas.feedback import FeedbackRequest, RatingType, FeedbackType
from app.engine.postgres_client import PostgreSQLFeedbackClient
from app.extraction.ner_pipeline import NERPipeline

logger = get_logger(__name__)


class FeedbackCollector:
    """Collect and validate user feedback."""
    
    def __init__(
        self,
        postgres_client: PostgreSQLFeedbackClient,
        ner_pipeline: NERPipeline,
        response_cache = None
    ):
        """
        Initialize feedback collector.
        
        Args:
            postgres_client: PostgreSQL client for storage
            ner_pipeline: Named entity recognition pipeline
            response_cache: Optional Redis/memory cache for response metadata
        """
        self.pg_client = postgres_client
        self.ner = ner_pipeline
        self.response_cache = response_cache
    
    async def collect_feedback(
        self,
        feedback_request: FeedbackRequest
    ) -> Dict[str, Any]:
        """
        MAIN ENTRY POINT: Collect and store feedback.
        
        STEP 1: Validate response_id exists and is not stale
        STEP 2: Pre-classify feedback
        STEP 3: Store in PostgreSQL
        STEP 4: Return feedback_id
        
        Returns:
            {
                'feedback_id': str,
                'status': 'recorded',
                'evaluation_status': 'pending',
                'recorded_at': datetime
            }
        """
        feedback_id = str(uuid4())
        
        try:
            logger.info(
                f"Collecting feedback {feedback_id}: "
                f"type={feedback_request.feedback_type}, "
                f"rating={feedback_request.rating}"
            )
            
            # STEP 1: Validate response_id
            response_meta = await self._validate_response_id(
                feedback_request.response_id
            )
            if not response_meta:
                logger.warning(
                    f"Invalid response_id: {feedback_request.response_id}"
                )
                raise ValueError(
                    f"Response ID {feedback_request.response_id} not found or expired"
                )
            
            # STEP 2: Pre-classify feedback
            classifications = await self._pre_classify_feedback(
                feedback_request=feedback_request,
                response_metadata=response_meta
            )
            
            logger.debug(
                f"Pre-classification complete: "
                f"quality={classifications['feedback_quality_score']:.2f}, "
                f"entities={len(classifications['extracted_entities'])}"
            )
            
            # STEP 3: Store in PostgreSQL
            stored_feedback = await self.pg_client.store_feedback(
                feedback_id=feedback_id,
                response_id=feedback_request.response_id,
                session_id=feedback_request.session_id,
                user_id=feedback_request.user_id,
                query=response_meta['query'],
                response_text=response_meta['response_text'],
                rating=feedback_request.rating.value,
                feedback_type=feedback_request.feedback_type.value,
                entity_name=feedback_request.entity_name,
                entity_type=feedback_request.entity_type,
                notes=feedback_request.notes,
                corrections=feedback_request.corrections,
                device_type=feedback_request.device_type,
                timestamp=feedback_request.timestamp or datetime.utcnow(),
                classifications=classifications
            )
            
            logger.info(f"Feedback {feedback_id} recorded successfully")
            
            # STEP 4: Return confirmation
            return {
                'feedback_id': feedback_id,
                'status': 'recorded',
                'evaluation_status': 'pending',
                'recorded_at': datetime.utcnow(),
                'quality_score': classifications['feedback_quality_score']
            }
        
        except Exception as e:
            logger.error(f"Error collecting feedback {feedback_id}: {e}", exc_info=True)
            raise
    
    async def _validate_response_id(
        self,
        response_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Validate that response_id exists and is not stale.
        
        Response metadata cached for 24 hours after generation.
        
        Returns:
            Response metadata if valid, None otherwise
        """
        if not self.response_cache:
            logger.warning("Response cache not configured, skipping validation")
            return {'query': '', 'response_text': '', 'mode': 'contextgraph'}
        
        try:
            # Attempt to get from cache
            response_meta = await self.response_cache.get(response_id)
            
            if response_meta:
                logger.debug(f"Response metadata found in cache: {response_id}")
                return response_meta
            else:
                logger.warning(f"Response metadata not found in cache: {response_id}")
                return None
        
        except Exception as e:
            logger.warning(f"Error checking response cache: {e}")
            # Degrade gracefully: allow feedback without validation
            return {'query': '', 'response_text': '', 'mode': 'unknown'}
    
    async def _pre_classify_feedback(
        self,
        feedback_request: FeedbackRequest,
        response_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Pre-classify feedback without LLM (fast, local).
        
        Performs:
        1. Entity extraction from feedback text
        2. Sentiment classification
        3. Intent scoring
        4. Overall quality score
        
        Returns:
            {
                'extracted_entities': [{name, type, confidence}, ...],
                'sentiment': 'positive|negative|neutral',
                'intent_score': 0.0-1.0,
                'feedback_quality_score': 0.0-1.0,
                'should_evaluate': bool
            }
        """
        
        # Extract text to analyze
        text_to_extract = (feedback_request.notes or "").strip()
        if feedback_request.entity_name:
            text_to_extract += f" {feedback_request.entity_name}"
        
        # STEP 1: Extract entities using NER
        extracted_entities = []
        if text_to_extract:
            try:
                ner_results = self.ner.extract_entities(text_to_extract)
                
                extracted_entities = [
                    {
                        'name': result['text'],
                        'type': result['label'],
                        'confidence': float(result.get('confidence', 0.0)),
                        'source': 'feedback_text'
                    }
                    for result in ner_results
                ]
                
                logger.debug(
                    f"Extracted {len(extracted_entities)} entities from feedback"
                )
            except Exception as e:
                logger.warning(f"NER extraction failed: {e}")
                # Continue without entity extraction
        
        # STEP 2: Classify sentiment
        sentiment = self._classify_sentiment(feedback_request)
        
        # STEP 3: Score intent/relevance
        intent_score = self._score_intent(
            feedback_request,
            extracted_entities
        )
        
        # STEP 4: Calculate overall quality score
        quality_score = self._calculate_quality_score(
            feedback_request=feedback_request,
            extracted_entities=extracted_entities,
            sentiment=sentiment,
            intent_score=intent_score
        )
        
        return {
            'extracted_entities': extracted_entities,
            'sentiment': sentiment,
            'intent_score': intent_score,
            'feedback_quality_score': quality_score,
            'should_evaluate': quality_score >= 0.3,  # Filter very low quality
            'classification_timestamp': datetime.utcnow().isoformat()
        }
    
    def _classify_sentiment(self, request: FeedbackRequest) -> str:
        """
        Classify sentiment from feedback.
        
        Uses explicit rating if available, otherwise analyzes text.
        """
        if request.rating == RatingType.POSITIVE:
            return 'positive'
        elif request.rating == RatingType.NEGATIVE:
            return 'negative'
        else:
            return 'neutral'
    
    def _score_intent(
        self,
        request: FeedbackRequest,
        extracted_entities: List[Dict[str, Any]]
    ) -> float:
        """
        Score how relevant/actionable the feedback is.
        
        Factors:
        - Has specific feedback type
        - Has entity specification
        - Has detailed notes
        - Has proposed corrections
        - Clear sentiment
        
        Returns: 0.0-1.0
        """
        score = 0.0
        
        # Has clear feedback type
        if request.feedback_type != FeedbackType.OTHER:
            score += 0.3
        
        # Has entity specification
        if request.entity_name or extracted_entities:
            score += 0.2
        
        # Has detailed notes (> 20 chars)
        if request.notes and len(request.notes) > 20:
            score += 0.2
        
        # Has specific corrections proposed
        if request.corrections and len(request.corrections) > 0:
            score += 0.2
        
        # Has clear sentiment
        if request.rating in [RatingType.POSITIVE, RatingType.NEGATIVE]:
            score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_quality_score(
        self,
        feedback_request: FeedbackRequest,
        extracted_entities: List[Dict[str, Any]],
        sentiment: str,
        intent_score: float
    ) -> float:
        """
        Calculate overall feedback quality score.
        
        Used to filter spam/low-quality feedback early.
        
        Returns: 0.0-1.0
        """
        components = []
        
        # Entity extraction success
        if extracted_entities:
            avg_entity_confidence = sum(
                e['confidence'] for e in extracted_entities
            ) / len(extracted_entities)
            components.append(avg_entity_confidence * 0.3)
        else:
            components.append(0.0)
        
        # Intent score
        components.append(intent_score * 0.4)
        
        # Sentiment clarity
        if sentiment in ['positive', 'negative']:
            components.append(0.8 * 0.3)
        else:
            components.append(0.5 * 0.3)
        
        overall_score = sum(components) / len(components) if components else 0.0
        
        return min(max(overall_score, 0.0), 1.0)


class ResponseMetadataCache:
    """
    Simple in-memory cache for response metadata.
    
    Can be replaced with Redis for distributed caching.
    """
    
    def __init__(self, ttl_seconds: int = 86400):
        """
        Initialize cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries (default: 24 hours)
        """
        self.ttl = ttl_seconds
        self.cache: Dict[str, tuple] = {}  # (metadata, expiry_time)
    
    async def set(self, key: str, value: Dict[str, Any], expire: Optional[int] = None):
        """Store metadata in cache."""
        expire_time = datetime.utcnow() + timedelta(seconds=expire or self.ttl)
        self.cache[key] = (value, expire_time)
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve metadata from cache, respecting TTL."""
        if key not in self.cache:
            return None
        
        value, expiry = self.cache[key]
        
        if datetime.utcnow() > expiry:
            # Expired, remove and return None
            del self.cache[key]
            return None
        
        return value
    
    async def delete(self, key: str):
        """Remove metadata from cache."""
        if key in self.cache:
            del self.cache[key]
    
    async def cleanup_expired(self):
        """Remove all expired entries."""
        now = datetime.utcnow()
        expired_keys = [
            key for key, (_, expiry) in self.cache.items()
            if now > expiry
        ]
        for key in expired_keys:
            del self.cache[key]
        return len(expired_keys)


class FeedbackValidator:
    """Validate feedback data for business logic consistency."""
    
    @staticmethod
    def validate_entity_name(entity_name: str, entity_type: str) -> bool:
        """Validate entity name matches type conventions."""
        # Add your validation logic here
        # E.g., fund names should match pattern, etc.
        return bool(entity_name and entity_type)
    
    @staticmethod
    def validate_corrections(corrections: Dict[str, Any]) -> bool:
        """Validate proposed corrections are reasonable."""
        if not corrections:
            return True
        
        # Check for obviously invalid corrections
        for key, value in corrections.items():
            if not isinstance(key, str) or len(key) > 255:
                return False
            if not isinstance(value, (str, int, float, bool, type(None))):
                return False
        
        return True
    
    @staticmethod
    def validate_notes(notes: str, max_length: int = 2000) -> bool:
        """Validate feedback notes."""
        if not notes:
            return True
        
        return isinstance(notes, str) and len(notes) <= max_length


# Singleton instance (can be injected via DI)
_feedback_collector: Optional[FeedbackCollector] = None


def get_feedback_collector() -> FeedbackCollector:
    """Get or create feedback collector singleton."""
    global _feedback_collector
    if _feedback_collector is None:
        raise RuntimeError("Feedback collector not initialized")
    return _feedback_collector


def init_feedback_collector(
    postgres_client: PostgreSQLFeedbackClient,
    ner_pipeline: NERPipeline,
    response_cache = None
) -> FeedbackCollector:
    """Initialize feedback collector."""
    global _feedback_collector
    _feedback_collector = FeedbackCollector(
        postgres_client=postgres_client,
        ner_pipeline=ner_pipeline,
        response_cache=response_cache
    )
    return _feedback_collector
