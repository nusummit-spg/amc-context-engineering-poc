# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_query_planner.py
======================
Unit tests for query decomposition, SubTask dependency resolution,
and ExecutionPlan parallel grouping.
"""
import pytest
from app.retrieval.planner import QueryPlanner, ExecutionPlan, ExecutionToolType, SubTask, get_planner


@pytest.fixture
def planner():
    return get_planner()


@pytest.mark.asyncio
async def test_simple_query_plan(planner):
    plan = await planner.plan("What is the NAV of Adani Growth fund?")
    assert plan.is_complex is False
    assert len(plan.sub_tasks) == 2
    assert plan.sub_tasks[0].tool == ExecutionToolType.VECTOR_SEARCH


@pytest.mark.asyncio
async def test_complex_comparison_query_plan(planner):
    query = "Compare the risk and return characteristics of Adani Growth vs Tata Balanced fund schemes?"
    plan = await planner.plan(query)
    assert plan.is_complex is True
    assert plan.synthesis_strategy == "comparison"
    assert len(plan.sub_tasks) >= 3


def test_parallel_groups_topological_sort():
    t1 = SubTask(id=1, tool=ExecutionToolType.VECTOR_SEARCH, params={"q": "A"}, depends_on=[])
    t2 = SubTask(id=2, tool=ExecutionToolType.VECTOR_SEARCH, params={"q": "B"}, depends_on=[])
    t3 = SubTask(id=3, tool=ExecutionToolType.SYNTHESIS, params={"strategy": "comparison"}, depends_on=[1, 2])

    plan = ExecutionPlan(
        query="Compare A vs B",
        is_complex=True,
        complexity_reason="Comparison",
        sub_tasks=[t1, t2, t3],
    )

    groups = plan.parallel_groups()
    assert len(groups) == 2
    # First wave has t1 and t2 in parallel
    assert set(t.id for t in groups[0]) == {1, 2}
    # Second wave has t3
    assert [t.id for t in groups[1]] == [3]
