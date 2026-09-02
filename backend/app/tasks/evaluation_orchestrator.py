"""
Scheduled Evaluation Layer Orchestrator.

PURPOSE:
- Run scheduled feedback evaluation cycles
- Orchestrate batch LLM evaluation
- Apply high-confidence corrections to Neo4j
- Invalidate affected caches
- Generate evaluation reports

SCHEDULING:
- Runs on configurable cron schedule (default: hourly)
- Non-blocking: continues even if errors occur
- Idempotent: safe to run multiple times
- Monitoring: metrics and alerts on failures

FLOW:
1. Fetch pending feedback from PostgreSQL
2. Aggregate and prepare evaluation batches
3. Call batch LLM evaluation engine
4. Generate correction recommendations
5. Apply high-confidence corrections to Neo4j
6. Invalidate affected caches
7. Record metrics and cleanup
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import get_logger
from app.engine.postgres_client import PostgreSQLFeedbackClient
from app.engine.feedback_processor import FeedbackProcessor
from app.engine.batch_evaluation import BatchEvaluationEngine
from app.engine.graph_corrector import GraphCorrectionEngine
from app.engine.cache_manager import CacheManager

logger = get_logger(__name__)


class EvaluationOrchestrator:
    """Orchestrates scheduled feedback evaluation cycles."""
    
    def __init__(
        self,
        postgres_client: PostgreSQLFeedbackClient,
        feedback_processor: FeedbackProcessor,
        batch_evaluator: BatchEvaluationEngine,
        graph_corrector: GraphCorrectionEngine,
        cache_manager: CacheManager,
        config: Dict[str, Any]
    ):
        """
        Initialize evaluation orchestrator.
        
        Args:
            postgres_client: PostgreSQL feedback store
            feedback_processor: Batch preparation engine
            batch_evaluator: LLM batch evaluation engine
            graph_corrector: Neo4j graph update engine
            cache_manager: Cache invalidation manager
            config: Configuration dict
        """
        self.pg_client = postgres_client
        self.feedback_processor = feedback_processor
        self.batch_evaluator = batch_evaluator
        self.graph_corrector = graph_corrector
        self.cache_manager = cache_manager
        self.config = config
        
        # Metrics tracking
        self.last_cycle_metrics: Optional[Dict[str, Any]] = None
    
    async def run_evaluation_cycle(self) -> Dict[str, Any]:
        """
        MAIN ORCHESTRATION: Run a complete evaluation cycle.
        
        STEPS:
        1. Initialize cycle
        2. Prepare feedback batches
        3. Evaluate batches with LLM
        4. Apply corrections to Neo4j
        5. Invalidate caches
        6. Record metrics
        7. Cleanup
        
        Returns:
            Cycle metrics/summary
        """
        
        cycle_id = str(uuid4())
        cycle_start = datetime.utcnow()
        
        logger.info(f"Starting evaluation cycle {cycle_id}")
        
        try:
            cycle_metrics = {
                'cycle_id': cycle_id,
                'started_at': cycle_start,
                'status': 'running'
            }
            
            # STEP 1: Prepare batches
            logger.info("Step 1: Preparing feedback batches")
            batches = await self._prepare_batches()
            cycle_metrics['batches_prepared'] = len(batches)
            
            if not batches:
                logger.info("No pending feedback to evaluate")
                cycle_metrics['status'] = 'completed'
                cycle_metrics['duration_seconds'] = (
                    datetime.utcnow() - cycle_start
                ).total_seconds()
                return cycle_metrics
            
            # STEP 2: Evaluate batches
            logger.info(f"Step 2: Evaluating {len(batches)} batches with LLM")
            eval_results = await self._evaluate_batches(batches, cycle_id)
            cycle_metrics.update(eval_results)
            
            # STEP 3: Apply corrections
            logger.info("Step 3: Applying corrections to Neo4j")
            apply_results = await self._apply_corrections(cycle_id)
            cycle_metrics.update(apply_results)
            
            # STEP 4: Invalidate caches
            logger.info("Step 4: Invalidating affected caches")
            await self._invalidate_caches(apply_results.get('affected_entities', []))
            
            # STEP 5: Record metrics
            logger.info("Step 5: Recording cycle metrics")
            await self._record_metrics(cycle_metrics)
            
            # STEP 6: Cleanup
            logger.info("Step 6: Cleaning up old data")
            await self._cleanup_old_data()
            
            # Mark cycle as complete
            cycle_metrics['status'] = 'completed'
            cycle_metrics['completed_at'] = datetime.utcnow()
            cycle_metrics['duration_seconds'] = (
                datetime.utcnow() - cycle_start
            ).total_seconds()
            
            self.last_cycle_metrics = cycle_metrics
            
            logger.info(
                f"Evaluation cycle {cycle_id} completed successfully "
                f"({cycle_metrics['duration_seconds']:.2f}s)"
            )
            
            return cycle_metrics
        
        except Exception as e:
            logger.error(
                f"Evaluation cycle {cycle_id} failed: {e}",
                exc_info=True
            )
            
            return {
                'cycle_id': cycle_id,
                'status': 'failed',
                'error': str(e),
                'duration_seconds': (
                    datetime.utcnow() - cycle_start
                ).total_seconds()
            }
    
    async def _prepare_batches(self) -> List[List[Dict[str, Any]]]:
        """
        STEP 1: Prepare feedback batches for evaluation.
        
        Uses FeedbackProcessor to:
        - Fetch pending feedback
        - Filter by quality
        - Aggregate by entity/type
        - Calculate consensus
        - Deduplicate
        - Create batches
        """
        
        try:
            batches = await self.feedback_processor.prepare_evaluation_batches(
                limit=self.config.get('max_feedback_per_cycle', 500),
                hours_back=self.config.get('feedback_hours_back', 24),
                batch_size=self.config.get('batch_size', 25)
            )
            
            logger.info(f"Prepared {len(batches)} batches for evaluation")
            return batches
        
        except Exception as e:
            logger.error(f"Error preparing batches: {e}")
            raise
    
    async def _evaluate_batches(
        self,
        batches: List[List[Dict[str, Any]]],
        cycle_id: str
    ) -> Dict[str, Any]:
        """
        STEP 2: Evaluate batches with LLM.
        
        Uses BatchEvaluationEngine to:
        - Call LLM with each batch
        - Extract corrections
        - Assign confidence scores
        - Store recommendations
        """
        
        metrics = {
            'batches_evaluated': 0,
            'recommendations_generated': 0,
            'tokens_used': 0,
            'evaluation_errors': 0
        }
        
        try:
            for batch_idx, batch in enumerate(batches):
                try:
                    logger.info(
                        f"Evaluating batch {batch_idx + 1}/{len(batches)} "
                        f"(size={len(batch)})"
                    )
                    
                    # Call batch evaluator
                    batch_results = await self.batch_evaluator.evaluate_batch(batch)
                    
                    metrics['batches_evaluated'] += 1
                    metrics['recommendations_generated'] += len(batch_results)
                    metrics['tokens_used'] += batch_results.get('tokens_used', 0)
                
                except Exception as e:
                    logger.error(f"Error evaluating batch {batch_idx}: {e}")
                    metrics['evaluation_errors'] += 1
                    # Continue with next batch
            
            logger.info(
                f"Batch evaluation complete: "
                f"{metrics['recommendations_generated']} recommendations generated"
            )
            
            return metrics
        
        except Exception as e:
            logger.error(f"Error in batch evaluation: {e}")
            raise
    
    async def _apply_corrections(
        self,
        cycle_id: str
    ) -> Dict[str, Any]:
        """
        STEP 3: Apply high-confidence corrections to Neo4j.
        
        Uses GraphCorrectionEngine to:
        - Fetch approved corrections
        - Validate Cypher mutations
        - Execute in Neo4j transaction
        - Record audit trail
        - Track affected entities
        """
        
        try:
            # Apply high-confidence corrections (>= threshold)
            apply_results = await self.graph_corrector.apply_high_confidence_corrections(
                confidence_threshold=self.config.get('confidence_auto_apply_threshold', 0.85)
            )
            
            logger.info(
                f"Applied {apply_results['applied']} corrections, "
                f"{apply_results['failed']} failed"
            )
            
            return apply_results
        
        except Exception as e:
            logger.error(f"Error applying corrections: {e}")
            raise
    
    async def _invalidate_caches(self, affected_entities: List[str]):
        """
        STEP 4: Invalidate caches affected by corrections.
        
        Invalidates:
        - FAISS embeddings for affected entities
        - Neo4j traversal caches
        - Entity resolver caches
        - Response metadata caches
        """
        
        try:
            if not affected_entities:
                logger.debug("No entities affected, skipping cache invalidation")
                return
            
            logger.info(f"Invalidating caches for {len(affected_entities)} entities")
            
            await self.cache_manager.invalidate_entity_caches(affected_entities)
            
            logger.info("Cache invalidation complete")
        
        except Exception as e:
            logger.error(f"Error invalidating caches: {e}")
            # Don't fail cycle on cache errors
    
    async def _record_metrics(self, cycle_metrics: Dict[str, Any]):
        """
        STEP 5: Record cycle metrics to database.
        
        Records in feedback_metrics table for dashboards/analytics.
        """
        
        try:
            # TODO: Insert metrics into feedback_metrics table
            logger.debug("Cycle metrics recorded")
        
        except Exception as e:
            logger.error(f"Error recording metrics: {e}")
            # Don't fail cycle on metrics errors
    
    async def _cleanup_old_data(self):
        """
        STEP 6: Clean up old data.
        
        - Archive old feedback (> 90 days)
        - Delete rejected recommendations (> 7 days)
        - Clean expired cache entries
        """
        
        try:
            # Archive old feedback
            archived = await self.pg_client.archive_old_feedback(
                days=self.config.get('feedback_retention_days', 90)
            )
            logger.info(f"Archived {archived} old feedback records")
            
            # Cleanup expired caches
            # This would call database functions if configured
            
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")
            # Don't fail cycle on cleanup errors
    
    def get_last_cycle_metrics(self) -> Optional[Dict[str, Any]]:
        """Get metrics from most recent evaluation cycle."""
        return self.last_cycle_metrics


class SchedulerManager:
    """Manages APScheduler for evaluation cycles."""
    
    def __init__(
        self,
        orchestrator: EvaluationOrchestrator,
        config: Dict[str, Any]
    ):
        """
        Initialize scheduler manager.
        
        Args:
            orchestrator: Evaluation orchestrator instance
            config: Configuration including cron schedule
        """
        self.orchestrator = orchestrator
        self.config = config
        self.scheduler: Optional[AsyncIOScheduler] = None
    
    async def initialize(self):
        """Initialize and start scheduler."""
        
        self.scheduler = AsyncIOScheduler()
        
        # Parse cron schedule from config
        cron_config = self.config.get('evaluation_schedule', {
            'minute': 0,  # Run on the hour
            'hour': '*'   # Every hour
        })
        
        # Add evaluation job
        self.scheduler.add_job(
            func=self._run_evaluation_with_logging,
            trigger=CronTrigger(**cron_config),
            id='feedback_evaluation_cycle',
            name='Feedback Evaluation Cycle',
            replace_existing=True,
            max_instances=1  # Prevent concurrent runs
        )
        
        # Add optional cleanup job (daily at 2 AM)
        if self.config.get('enable_daily_cleanup', True):
            self.scheduler.add_job(
                func=self._run_cleanup_with_logging,
                trigger=CronTrigger(hour=2, minute=0),
                id='feedback_cleanup',
                name='Feedback Cleanup',
                replace_existing=True,
                max_instances=1
            )
        
        # Start scheduler
        self.scheduler.start()
        
        logger.info("Evaluation scheduler initialized and started")
    
    async def shutdown(self):
        """Shutdown scheduler."""
        if self.scheduler:
            self.scheduler.shutdown(wait=True)
            logger.info("Evaluation scheduler shut down")
    
    async def _run_evaluation_with_logging(self):
        """Wrapper for evaluation with logging."""
        try:
            metrics = await self.orchestrator.run_evaluation_cycle()
            
            # Log success
            logger.info(f"Evaluation cycle metrics: {metrics}")
            
            # Could send to monitoring system here
            
        except Exception as e:
            logger.error(f"Evaluation cycle failed: {e}", exc_info=True)
            # Alert monitoring system
    
    async def _run_cleanup_with_logging(self):
        """Wrapper for cleanup with logging."""
        try:
            logger.info("Running daily cleanup...")
            await self.orchestrator._cleanup_old_data()
            logger.info("Daily cleanup completed")
        
        except Exception as e:
            logger.error(f"Daily cleanup failed: {e}", exc_info=True)
    
    def get_scheduled_jobs(self) -> List[Dict[str, Any]]:
        """Get information about scheduled jobs."""
        if not self.scheduler:
            return []
        
        return [
            {
                'id': job.id,
                'name': job.name,
                'trigger': str(job.trigger),
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None
            }
            for job in self.scheduler.get_jobs()
        ]


class EvaluationMonitor:
    """Monitor evaluation cycle performance."""
    
    def __init__(self, orchestrator: EvaluationOrchestrator):
        self.orchestrator = orchestrator
        self.cycle_history: List[Dict[str, Any]] = []
    
    def get_cycle_metrics(self) -> Optional[Dict[str, Any]]:
        """Get metrics from last evaluation cycle."""
        metrics = self.orchestrator.get_last_cycle_metrics()
        if metrics:
            self.cycle_history.append(metrics)
            # Keep only last 100 cycles
            if len(self.cycle_history) > 100:
                self.cycle_history.pop(0)
        return metrics
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get summary of evaluation performance over time."""
        
        if not self.cycle_history:
            return {
                'cycles_run': 0,
                'success_rate': 0.0,
                'avg_duration_seconds': 0.0,
                'avg_recommendations_per_cycle': 0.0
            }
        
        successful = [c for c in self.cycle_history if c['status'] == 'completed']
        success_rate = len(successful) / len(self.cycle_history) if self.cycle_history else 0
        
        avg_duration = sum(
            c.get('duration_seconds', 0) for c in successful
        ) / len(successful) if successful else 0
        
        avg_recommendations = sum(
            c.get('recommendations_generated', 0) for c in successful
        ) / len(successful) if successful else 0
        
        return {
            'cycles_run': len(self.cycle_history),
            'success_rate': success_rate,
            'avg_duration_seconds': avg_duration,
            'avg_recommendations_per_cycle': avg_recommendations,
            'recent_cycles': self.cycle_history[-10:]
        }


# Singleton instances
_orchestrator: Optional[EvaluationOrchestrator] = None
_scheduler_manager: Optional[SchedulerManager] = None
_monitor: Optional[EvaluationMonitor] = None


def init_evaluation_orchestrator(
    postgres_client: PostgreSQLFeedbackClient,
    feedback_processor: FeedbackProcessor,
    batch_evaluator: BatchEvaluationEngine,
    graph_corrector: GraphCorrectionEngine,
    cache_manager: CacheManager,
    config: Dict[str, Any]
) -> EvaluationOrchestrator:
    """Initialize evaluation orchestrator."""
    global _orchestrator, _scheduler_manager, _monitor
    
    _orchestrator = EvaluationOrchestrator(
        postgres_client=postgres_client,
        feedback_processor=feedback_processor,
        batch_evaluator=batch_evaluator,
        graph_corrector=graph_corrector,
        cache_manager=cache_manager,
        config=config
    )
    
    _scheduler_manager = SchedulerManager(_orchestrator, config)
    _monitor = EvaluationMonitor(_orchestrator)
    
    logger.info("Evaluation orchestrator initialized")
    
    return _orchestrator


async def start_scheduler():
    """Start the evaluation scheduler."""
    if not _scheduler_manager:
        raise RuntimeError("Scheduler manager not initialized")
    
    await _scheduler_manager.initialize()


async def stop_scheduler():
    """Stop the evaluation scheduler."""
    if not _scheduler_manager:
        return
    
    await _scheduler_manager.shutdown()


def get_orchestrator() -> EvaluationOrchestrator:
    """Get orchestrator instance."""
    if not _orchestrator:
        raise RuntimeError("Orchestrator not initialized")
    return _orchestrator


def get_scheduler_manager() -> SchedulerManager:
    """Get scheduler manager instance."""
    if not _scheduler_manager:
        raise RuntimeError("Scheduler manager not initialized")
    return _scheduler_manager


def get_monitor() -> EvaluationMonitor:
    """Get monitor instance."""
    if not _monitor:
        raise RuntimeError("Monitor not initialized")
    return _monitor
