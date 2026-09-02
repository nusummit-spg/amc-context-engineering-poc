"""
Feedback Processing Module.

PURPOSE:
- Aggregate feedback by type/entity
- Calculate consensus scores
- Filter low-quality feedback
- Prepare batches for LLM evaluation

FLOW:
1. Fetch pending feedback from PostgreSQL
2. Group by feedback type/entity
3. Calculate inter-annotator agreement
4. Filter by confidence threshold
5. Deduplicate similar feedback
6. Create batches ready for evaluation
"""

import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from statistics import mean, stdev

from app.core.logging import get_logger
from app.engine.postgres_client import PostgreSQLFeedbackClient

logger = get_logger(__name__)


class FeedbackProcessor:
    """Process and aggregate feedback for batch evaluation."""
    
    def __init__(
        self,
        postgres_client: PostgreSQLFeedbackClient,
        min_quality_score: float = 0.3,
        min_agreement_score: float = 0.6
    ):
        """
        Initialize feedback processor.
        
        Args:
            postgres_client: PostgreSQL client
            min_quality_score: Minimum quality score to include (0.0-1.0)
            min_agreement_score: Minimum inter-annotator agreement (0.0-1.0)
        """
        self.pg_client = postgres_client
        self.min_quality_score = min_quality_score
        self.min_agreement_score = min_agreement_score
    
    async def prepare_evaluation_batches(
        self,
        limit: int = 500,
        hours_back: int = 24,
        batch_size: int = 25
    ) -> List[List[Dict[str, Any]]]:
        """
        MAIN ENTRY POINT: Prepare feedback batches for LLM evaluation.
        
        STEPS:
        1. Fetch pending feedback
        2. Filter by quality threshold
        3. Aggregate by type/entity
        4. Calculate consensus scores
        5. Deduplicate
        6. Create batches
        
        Args:
            limit: Maximum feedback records to process
            hours_back: Only process feedback from last N hours
            batch_size: Number of items per batch
        
        Returns:
            List of batches, each batch is list of feedback records
        """
        
        logger.info(
            f"Preparing evaluation batches: "
            f"limit={limit}, hours_back={hours_back}, batch_size={batch_size}"
        )
        
        # STEP 1: Fetch pending feedback
        pending_feedback = await self.pg_client.fetch_pending_feedback(
            limit=limit,
            min_quality_score=self.min_quality_score,
            hours_back=hours_back
        )
        
        if not pending_feedback:
            logger.info("No pending feedback to process")
            return []
        
        logger.info(f"Fetched {len(pending_feedback)} pending feedback items")
        
        # STEP 2: Aggregate by entity/type
        aggregated = self._aggregate_feedback(pending_feedback)
        logger.debug(f"Aggregated into {len(aggregated)} groups")
        
        # STEP 3: Calculate consensus scores
        for group_key, items in aggregated.items():
            consensus = self._calculate_consensus_score(items)
            for item in items:
                item['consensus_score'] = consensus['overall_score']
                item['agreement_votes'] = consensus['votes']
        
        # STEP 4: Filter by agreement threshold
        filtered_items = [
            item for items in aggregated.values()
            for item in items
            if item.get('consensus_score', 0.0) >= self.min_agreement_score
        ]
        
        logger.info(
            f"Filtered by agreement threshold: "
            f"{len(filtered_items)}/{len(pending_feedback)} items"
        )
        
        # STEP 5: Deduplicate
        deduplicated_items = await self._deduplicate_feedback(filtered_items)
        
        logger.info(
            f"After deduplication: {len(deduplicated_items)} items "
            f"({100 * (1 - len(deduplicated_items)/len(filtered_items)):.1f}% reduction)"
        )
        
        # STEP 6: Create batches
        batches = self._create_batches(deduplicated_items, batch_size)
        
        logger.info(f"Created {len(batches)} evaluation batches")
        
        return batches
    
    def _aggregate_feedback(
        self,
        feedback_items: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Aggregate feedback by entity and feedback type.
        
        Groups similar feedback items together for consensus calculation.
        
        Returns:
            {
                'entity_name|feedback_type': [item1, item2, ...],
                ...
            }
        """
        aggregated = defaultdict(list)
        
        for item in feedback_items:
            # Create group key
            entity_name = item.get('entity_name', 'unknown')
            feedback_type = item.get('feedback_type', 'unknown')
            
            group_key = f"{entity_name}|{feedback_type}"
            aggregated[group_key].append(item)
        
        logger.debug(f"Created {len(aggregated)} feedback groups")
        
        return dict(aggregated)
    
    def _calculate_consensus_score(
        self,
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate inter-annotator agreement score for a group.
        
        Uses simple voting mechanism:
        - Count positive vs negative votes
        - Calculate agreement percentage
        - Return consensus score
        
        Returns:
            {
                'overall_score': 0.0-1.0,
                'votes': {'positive': N, 'negative': N, 'neutral': N},
                'agreement_percentage': 0.0-100.0
            }
        """
        
        if not items:
            return {'overall_score': 0.0, 'votes': {}, 'agreement_percentage': 0.0}
        
        # Count votes by rating
        votes = defaultdict(int)
        for item in items:
            rating = item.get('rating', 'neutral')
            votes[rating] += 1
        
        # Calculate agreement score
        total_votes = len(items)
        max_votes = max(votes.values())
        agreement_percentage = (max_votes / total_votes) * 100
        
        # Overall score: higher if consensus, lower if split
        overall_score = max_votes / total_votes
        
        # Adjust for confidence of individual items
        avg_confidence = mean([
            item.get('confidence_score', 0.5) for item in items
        ])
        
        weighted_score = (overall_score * 0.7) + (avg_confidence * 0.3)
        
        logger.debug(
            f"Consensus score: {weighted_score:.2f} "
            f"(agreement: {agreement_percentage:.1f}%, "
            f"votes: {dict(votes)})"
        )
        
        return {
            'overall_score': weighted_score,
            'votes': dict(votes),
            'agreement_percentage': agreement_percentage
        }
    
    async def _deduplicate_feedback(
        self,
        items: List[Dict[str, Any]],
        similarity_threshold: float = 0.85
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate similar feedback items.
        
        Clusters similar items (e.g., same entity, similar text)
        and keeps representative + vote counts.
        
        OPTIMIZATION: Reduces number of LLM evaluations.
        
        Args:
            items: Feedback items to deduplicate
            similarity_threshold: Cosine similarity threshold for clustering
        
        Returns:
            Deduplicated items with vote_count field
        """
        
        if len(items) <= 1:
            return items
        
        logger.debug(f"Deduplicating {len(items)} feedback items")
        
        # Simple deduplication: group by entity + feedback_type + first 50 chars of notes
        deduplicated = {}
        
        for item in items:
            entity_name = item.get('entity_name', 'unknown')
            feedback_type = item.get('feedback_type', 'unknown')
            notes_hash = (item.get('notes', '')[:50] or 'none').lower()
            
            dedup_key = f"{entity_name}|{feedback_type}|{notes_hash}"
            
            if dedup_key not in deduplicated:
                # First occurrence: use as representative
                item['vote_count'] = 1
                deduplicated[dedup_key] = item
            else:
                # Duplicate: increment vote count
                deduplicated[dedup_key]['vote_count'] += 1
        
        result = list(deduplicated.values())
        reduction = 100 * (1 - len(result) / len(items))
        
        logger.debug(
            f"Deduplication complete: "
            f"{len(items)} → {len(result)} items ({reduction:.1f}% reduction)"
        )
        
        return result
    
    def _create_batches(
        self,
        items: List[Dict[str, Any]],
        batch_size: int = 25
    ) -> List[List[Dict[str, Any]]]:
        """
        Create fixed-size batches from feedback items.
        
        Tries to group similar items in same batch (for shared context).
        
        Args:
            items: Feedback items to batch
            batch_size: Target batch size
        
        Returns:
            List of batches
        """
        
        if not items:
            return []
        
        # Sort by entity name to group similar items
        sorted_items = sorted(
            items,
            key=lambda x: (x.get('entity_name', ''), x.get('feedback_type', ''))
        )
        
        # Create batches
        batches = [
            sorted_items[i:i+batch_size]
            for i in range(0, len(sorted_items), batch_size)
        ]
        
        logger.debug(
            f"Created {len(batches)} batches "
            f"(avg size: {len(items)/len(batches):.1f})"
        )
        
        return batches


class FeedbackAggregator:
    """Aggregate feedback statistics for analytics."""
    
    def __init__(self, postgres_client: PostgreSQLFeedbackClient):
        self.pg_client = postgres_client
    
    async def compute_daily_metrics(self, date: Optional[datetime] = None):
        """
        Compute and store daily feedback metrics.
        
        Runs after feedback evaluation to record statistics.
        
        Args:
            date: Date to compute metrics for (default: today)
        """
        
        if date is None:
            date = datetime.utcnow().date()
        
        logger.info(f"Computing daily metrics for {date}")
        
        # TODO: Implement aggregation query
        # This would query feedback_records and correction_recommendations
        # and insert into feedback_metrics table
    
    async def get_feedback_summary(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get summary statistics for past N days.
        
        Returns:
            {
                'total_feedback': N,
                'positive_feedback': N,
                'negative_feedback': N,
                'avg_quality_score': X.XX,
                'trending_entities': [...]
            }
        """
        
        metrics = await self.pg_client.get_daily_stats(days=days)
        
        if not metrics:
            return {
                'total_feedback': 0,
                'positive_feedback': 0,
                'negative_feedback': 0,
                'avg_quality_score': 0.0
            }
        
        # Aggregate metrics
        total_feedback = sum(m.get('total_feedback', 0) for m in metrics)
        total_positive = sum(m.get('positive_feedback', 0) for m in metrics)
        total_negative = sum(m.get('negative_feedback', 0) for m in metrics)
        
        avg_quality = mean([
            m.get('avg_confidence_score', 0.0) for m in metrics
            if m.get('avg_confidence_score') is not None
        ])
        
        return {
            'period_days': days,
            'total_feedback': total_feedback,
            'positive_feedback': total_positive,
            'negative_feedback': total_negative,
            'positive_percentage': (total_positive / total_feedback * 100) if total_feedback > 0 else 0,
            'avg_quality_score': avg_quality,
            'daily_breakdown': metrics
        }


class FeedbackFilter:
    """Filter feedback by various criteria."""
    
    @staticmethod
    def filter_by_quality(
        items: List[Dict[str, Any]],
        min_quality: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Filter items by quality score."""
        return [
            item for item in items
            if item.get('confidence_score', 0.0) >= min_quality
        ]
    
    @staticmethod
    def filter_by_entity_type(
        items: List[Dict[str, Any]],
        entity_types: List[str]
    ) -> List[Dict[str, Any]]:
        """Filter items by entity type."""
        return [
            item for item in items
            if item.get('entity_type') in entity_types
        ]
    
    @staticmethod
    def filter_by_feedback_type(
        items: List[Dict[str, Any]],
        feedback_types: List[str]
    ) -> List[Dict[str, Any]]:
        """Filter items by feedback type."""
        return [
            item for item in items
            if item.get('feedback_type') in feedback_types
        ]
    
    @staticmethod
    def filter_by_rating(
        items: List[Dict[str, Any]],
        ratings: List[str]
    ) -> List[Dict[str, Any]]:
        """Filter items by rating (positive, negative, neutral)."""
        return [
            item for item in items
            if item.get('rating') in ratings
        ]
    
    @staticmethod
    def filter_by_date_range(
        items: List[Dict[str, Any]],
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Filter items by creation date range."""
        return [
            item for item in items
            if start_date <= item.get('created_at') <= end_date
        ]
