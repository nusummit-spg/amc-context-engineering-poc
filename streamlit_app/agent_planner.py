"""
AMC Context Engineering — Agentic Core: Query Planner & Decomposer
Decomposes complex multi-part questions into ordered sub-tasks (ExecutionPlan).
Allows dynamic multi-round execution across vector search, graph traversals, Cypher aggregations, and entity comparisons.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import llm_text_client
import config


PLANNING_PROMPT = """You are a research planner for an enterprise financial document AI system.
Given a user query, determine if it requires decomposition into sub-tasks.

Available execution tools:
  - graph_lookup: Get a specific entity fact from knowledge graph (params: entity, attribute)
  - vector_search: Semantic search over document corpus (params: query, top_k)
  - aggregate: Compute numeric aggregate or totals from graph (params: cypher_description)
  - compare: Compare multiple entities side-by-side (params: entity_list, attribute)
  - text_to_cypher: Convert natural language to Cypher query (params: question)

USER QUESTION: {query}
DOMAINS AVAILABLE: {domains}

Return ONLY valid JSON matching this schema:
{{
  "is_complex": true/false,
  "complexity_reason": "...",
  "sub_tasks": [
    {{"id": 1, "tool": "vector_search", "params": {{"query": "..."}}, "depends_on": []}},
    {{"id": 2, "tool": "graph_lookup", "params": {{"entity": "...", "attribute": "..."}}, "depends_on": [1]}}
  ],
  "synthesis_strategy": "prose|table|mixed"
}}
"""


@dataclass
class SubTask:
    id: int
    tool: str
    params: Dict[str, Any]
    depends_on: List[int] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    is_complex: bool
    complexity_reason: str
    sub_tasks: List[SubTask]
    synthesis_strategy: str

    @classmethod
    def simple_plan(cls, query: str) -> "ExecutionPlan":
        return cls(
            is_complex=False,
            complexity_reason="Single-pass standard lookup",
            sub_tasks=[SubTask(id=1, tool="vector_search", params={"query": query})],
            synthesis_strategy="prose"
        )


class AgentPlanner:
    def should_plan(self, query: str) -> bool:
        """Determines if query warrants multi-task planning based on complexity signals."""
        signals = [
            "compare" in query.lower() and ("vs" in query.lower() or "versus" in query.lower() or "and" in query.lower()),
            query.count("?") > 1,
            len(query.split()) > 25,
            bool(re.search(r"\b(top \d|rank|best|worst|difference|between)\b", query, re.I)),
        ]
        return sum(signals) >= 2

    def create_plan(self, query: str, active_domains: List[str] = None) -> ExecutionPlan:
        """Generates an ExecutionPlan for complex multi-part queries."""
        if not self.should_plan(query):
            return ExecutionPlan.simple_plan(query)

        domains = ", ".join(active_domains) if active_domains else "sebi_regulation, fund_performance, esg_sustainability"
        prompt = PLANNING_PROMPT.format(query=query, domains=domains)

        try:
            res = llm_text_client.call_llm_json(prompt, model_id=config.CLAUDE_MODEL_LIGHT)
            if isinstance(res, dict) and "sub_tasks" in res:
                sub_tasks = [
                    SubTask(
                        id=st.get("id", i + 1),
                        tool=st.get("tool", "vector_search"),
                        params=st.get("params", {"query": query}),
                        depends_on=st.get("depends_on", [])
                    )
                    for i, st in enumerate(res.get("sub_tasks", []))
                ]
                return ExecutionPlan(
                    is_complex=res.get("is_complex", True),
                    complexity_reason=res.get("complexity_reason", "Multi-task decomposition"),
                    sub_tasks=sub_tasks if sub_tasks else [SubTask(id=1, tool="vector_search", params={"query": query})],
                    synthesis_strategy=res.get("synthesis_strategy", "prose")
                )
        except Exception as exc:
            print(f"  [AgentPlanner Warning] Plan generation fallback: {exc}", flush=True)

        return ExecutionPlan.simple_plan(query)
