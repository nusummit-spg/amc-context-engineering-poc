# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
query_phases.py
===============
Modular Query Execution Phases and Pipeline abstraction.
Refactors orchestrator retrieval execution into testable, discrete lifecycle phases.
Implements Task 1.4 of the Chief Architect Implementation Plan.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.retrieval.query_phases")


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
    """Base class for an isolated query processing phase."""

    def __init__(self, name: QueryPhaseType, dependencies: Optional[List[QueryPhaseType]] = None):
        self.name = name
        self.dependencies = dependencies or []

    @abstractmethod
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute phase logic and return state updates."""
        pass


class CacheLookupPhase(QueryPhase):
    def __init__(self, cache_instance: Optional[Any] = None):
        super().__init__(QueryPhaseType.CACHE_LOOKUP)
        self.cache = cache_instance

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        query = state.get("query", "")
        if self.cache and hasattr(self.cache, "lookup"):
            hit = self.cache.lookup(query)
            if hit:
                state["cache_hit"] = True
                state["cached_response"] = hit
        return state


class IntentClassificationPhase(QueryPhase):
    def __init__(self, classifier: Optional[Any] = None):
        super().__init__(QueryPhaseType.INTENT_CLASSIFICATION, [QueryPhaseType.CACHE_LOOKUP])
        self.classifier = classifier

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if state.get("cache_hit"):
            return state
        # Intent classification logic
        return state


class QueryExecutionPipeline:
    """Executes registered query phases sequentially or as an execution graph."""

    def __init__(self):
        self._phases: Dict[QueryPhaseType, QueryPhase] = {}
        self._phase_order: List[QueryPhaseType] = []

    def register_phase(self, phase: QueryPhase):
        """Register a phase into the pipeline."""
        self._phases[phase.name] = phase
        if phase.name not in self._phase_order:
            self._phase_order.append(phase.name)

    async def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run all phases in order with early exit support."""
        state = dict(initial_state)

        for phase_type in self._phase_order:
            phase = self._phases[phase_type]
            try:
                state = await phase.execute(state)
                # Early exit on cache hit
                if state.get("cache_hit") and phase_type == QueryPhaseType.CACHE_LOOKUP:
                    logger.info("Pipeline early exit: Cache hit satisfied query")
                    break
            except Exception as exc:
                logger.error("Error executing phase %s: %s", phase_type, exc)
                state["error"] = str(exc)
                state["failed_phase"] = phase_type.value
                break

        return state
