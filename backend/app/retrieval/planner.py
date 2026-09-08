# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
app.retrieval.planner
=====================
Query decomposition and execution planning module ported to backend.
Analyzes incoming queries to determine whether multi-part decomposition
and parallel retrieval should be triggered.
"""
from dataclasses import dataclass, field
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional

from app.engine import config

logger = logging.getLogger("retrieval.planner")


class ExecutionToolType(str, Enum):
    """Supported execution tools in the retrieval pipeline."""
    VECTOR_SEARCH = "vector_search"
    GRAPH_LOOKUP = "graph_lookup"
    ENTITY_COMPARISON = "entity_comparison"
    AGGREGATION = "aggregation"
    SYNTHESIS = "synthesis"


@dataclass
class SubTask:
    """A discrete unit of work in an execution plan."""
    id: int
    tool: ExecutionToolType
    params: Dict[str, Any]
    depends_on: List[int] = field(default_factory=list)

    def is_parallel_with(self, other: "SubTask") -> bool:
        """True if neither task depends on the other."""
        return other.id not in self.depends_on and self.id not in other.depends_on


@dataclass
class ExecutionPlan:
    """Ordered, dependency-aware plan for executing a query."""
    query: str
    is_complex: bool
    complexity_reason: str
    sub_tasks: List[SubTask]
    synthesis_strategy: str = "prose"  # "prose" | "table" | "comparison"

    def parallel_groups(self) -> List[List[SubTask]]:
        """Topological sort grouping independent tasks into concurrent execution waves."""
        groups: List[List[SubTask]] = []
        executed_ids: set[int] = set()
        remaining_tasks = list(self.sub_tasks)

        while remaining_tasks:
            # Tasks whose dependencies have all been met
            ready_wave = [
                t for t in remaining_tasks
                if all(dep in executed_ids for dep in t.depends_on)
            ]
            if not ready_wave:
                # Cyclic or unresolvable dependency fallback: execute remaining in order
                groups.append(remaining_tasks)
                break

            groups.append(ready_wave)
            for t in ready_wave:
                executed_ids.add(t.id)
                remaining_tasks.remove(t)

        return groups

    @classmethod
    def simple_plan(cls, query: str) -> "ExecutionPlan":
        """Default plan for straightforward, single-hop queries."""
        return cls(
            query=query,
            is_complex=False,
            complexity_reason="Direct single-pass query",
            sub_tasks=[
                SubTask(id=1, tool=ExecutionToolType.VECTOR_SEARCH, params={"query": query}, depends_on=[]),
                SubTask(id=2, tool=ExecutionToolType.SYNTHESIS, params={"strategy": "prose"}, depends_on=[1]),
            ],
            synthesis_strategy="prose",
        )


class QueryPlanner:
    """Detects query complexity and generates execution plans."""

    def should_plan(self, query: str) -> bool:
        """Fast regex & heuristic check to detect multi-part or comparative queries."""
        q_lower = query.lower()
        if "compare" in q_lower and any(w in q_lower for w in [" vs ", " versus ", " with ", " against ", " and "]):
            return True
        signals = [
            query.count("?") > 1,
            len(query.split()) > 18,
            bool(re.search(r"\b(top \d|difference between|versus|\bvs\b|rank|highest and lowest)\b", q_lower)),
        ]
        return sum(signals) >= 2

    async def plan(self, query: str) -> ExecutionPlan:
        """Generates an execution plan for the query."""
        if not self.should_plan(query):
            return ExecutionPlan.simple_plan(query)

        # Check for comparison query decomposition pattern
        q_lower = query.lower()
        if "compare" in q_lower or " vs " in q_lower or " versus " in q_lower:
            parts = re.split(r"\b(?:vs|versus|and)\b", query, flags=re.I)
            clean_parts = [p.strip() for p in parts if len(p.strip()) > 3]
            if len(clean_parts) >= 2:
                sub_tasks = []
                task_id = 1
                for part in clean_parts[:3]:
                    sub_tasks.append(
                        SubTask(
                            id=task_id,
                            tool=ExecutionToolType.VECTOR_SEARCH,
                            params={"query": part},
                            depends_on=[],
                        )
                    )
                    task_id += 1

                sub_tasks.append(
                    SubTask(
                        id=task_id,
                        tool=ExecutionToolType.SYNTHESIS,
                        params={"strategy": "comparison"},
                        depends_on=[t.id for t in sub_tasks],
                    )
                )

                return ExecutionPlan(
                    query=query,
                    is_complex=True,
                    complexity_reason="Comparative entity query with parallel retrieval branches",
                    sub_tasks=sub_tasks,
                    synthesis_strategy="comparison",
                )

        return ExecutionPlan.simple_plan(query)


_planner: Optional[QueryPlanner] = None


def get_planner() -> QueryPlanner:
    global _planner
    if _planner is None:
        _planner = QueryPlanner()
    return _planner
