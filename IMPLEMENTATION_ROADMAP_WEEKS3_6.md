# Implementation Roadmap: Weeks 3-6
## Advanced Features, Aggregation Path, and Production Rollout

---

# WEEK 3-4: Advanced Features - Query Decomposition & Parallelization

## Task 3.1: Port Query Decomposition to Backend API

### Objective
Move query decomposition logic from Streamlit UI (`agent_planner.py`) to backend orchestrator for all clients to benefit.

### Current State (Streamlit only)
```python
# streamlit_app/agent_planner.py - NOT in backend API
class ExecutionPlan:
    is_complex: bool
    complexity_reason: str
    sub_tasks: List[SubTask]
    synthesis_strategy: str

def plan_query(query: str) -> ExecutionPlan:
    # LLM determines if decomposition needed
    # Returns execution plan with ordered tasks
```

### New Backend Implementation

**Step 1: Create query planner module** (`backend/app/retrieval/planner.py`):

```python
"""Query decomposition and execution planning."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import asyncio

from app.engine import llm_text_client

class ExecutionToolType(str, Enum):
    """Supported execution tools."""
    VECTOR_SEARCH = "vector_search"
    GRAPH_LOOKUP = "graph_lookup"
    ENTITY_COMPARISON = "entity_comparison"
    AGGREGATION = "aggregation"
    SYNTHESIS = "synthesis"

@dataclass
class SubTask:
    """Single execution step in plan."""
    id: int
    tool: ExecutionToolType
    params: Dict[str, Any]
    depends_on: List[int] = field(default_factory=list)
    
    def is_parallel_with(self, other: 'SubTask') -> bool:
        """Check if this task can run in parallel with another."""
        return len(set(self.depends_on) & {other.id}) == 0

@dataclass
class ExecutionPlan:
    """Query execution plan."""
    query: str
    is_complex: bool
    complexity_reason: str
    sub_tasks: List[SubTask]
    synthesis_strategy: str  # "prose", "structured", "comparison"
    
    def parallel_groups(self) -> List[List[SubTask]]:
        """Group tasks that can run in parallel."""
        groups = []
        remaining = set(t.id for t in self.sub_tasks)
        
        while remaining:
            group = []
            for task in self.sub_tasks:
                if task.id in remaining:
                    # Can include if all dependencies are met
                    if all(dep not in remaining for dep in task.depends_on):
                        group.append(task)
            
            if not group:
                break  # No progress
            
            groups.append(group)
            remaining -= {t.id for t in group}
        
        return groups

class QueryPlanner:
    """Analyzes queries and creates execution plans."""
    
    PLANNING_PROMPT = """You are a query decomposition expert for a financial RAG system.
    
Given a user query, determine:
1. Is it complex (requires multiple steps)?
2. If complex, what steps are needed?
3. What order/parallelization is optimal?

Query types:
- SIMPLE: Single entity lookup (e.g., "What is NAV of X?")
- COMPARISON: Multiple entities compared (e.g., "Compare X vs Y")
- AGGREGATION: Summary over many entities (e.g., "Total AUM of all schemes")
- COMPLEX: Multi-step reasoning (e.g., "How does Y affect X given Z?")

Respond in JSON:
{
  "is_complex": true/false,
  "complexity_reason": "...",
  "type": "SIMPLE|COMPARISON|AGGREGATION|COMPLEX",
  "sub_tasks": [
    {
      "id": 1,
      "tool": "vector_search|graph_lookup|entity_comparison|aggregation",
      "params": {...},
      "depends_on": []
    },
    {
      "id": 2,
      "tool": "synthesis",
      "params": {"strategy": "prose|structured|comparison"},
      "depends_on": [1]
    }
  ],
  "synthesis_strategy": "prose"
}

QUERY: {query}

Return ONLY valid JSON, no markdown or commentary."""
    
    async def plan(self, query: str) -> ExecutionPlan:
        """Generate execution plan for query."""
        prompt = self.PLANNING_PROMPT.format(query=query)
        
        try:
            result = llm_text_client.call_llm_json(
                prompt, 
                model_id="gpt-3.5-turbo"  # Fast model for planning
            )
            
            if not isinstance(result, dict):
                result = {}
            
            sub_tasks = [
                SubTask(
                    id=st.get("id", i + 1),
                    tool=ExecutionToolType(st.get("tool", "vector_search")),
                    params=st.get("params", {}),
                    depends_on=st.get("depends_on", [])
                )
                for i, st in enumerate(result.get("sub_tasks", []))
            ]
            
            # If no sub-tasks, create default
            if not sub_tasks:
                sub_tasks = [
                    SubTask(
                        id=1,
                        tool=ExecutionToolType.VECTOR_SEARCH,
                        params={"query": query},
                        depends_on=[]
                    ),
                    SubTask(
                        id=2,
                        tool=ExecutionToolType.SYNTHESIS,
                        params={"strategy": "prose"},
                        depends_on=[1]
                    )
                ]
            
            return ExecutionPlan(
                query=query,
                is_complex=result.get("is_complex", False),
                complexity_reason=result.get("complexity_reason", "Unable to determine"),
                sub_tasks=sub_tasks,
                synthesis_strategy=result.get("synthesis_strategy", "prose")
            )
        
        except Exception as e:
            logger.warning(f"Query planning failed: {e}, using default plan")
            # Default: simple single-pass plan
            return ExecutionPlan(
                query=query,
                is_complex=False,
                complexity_reason="Planning error, using default",
                sub_tasks=[
                    SubTask(
                        id=1,
                        tool=ExecutionToolType.VECTOR_SEARCH,
                        params={"query": query},
                        depends_on=[]
                    ),
                    SubTask(
                        id=2,
                        tool=ExecutionToolType.SYNTHESIS,
                        params={"strategy": "prose"},
                        depends_on=[1]
                    )
                ],
                synthesis_strategy="prose"
            )

# Global instance
_planner = None

def get_planner() -> QueryPlanner:
    global _planner
    if _planner is None:
        _planner = QueryPlanner()
    return _planner
```

**Step 2: Integrate planner into orchestrator**:

```python
# backend/app/retrieval/orchestrator.py

from app.retrieval.planner import get_planner, ExecutionPlan

class RetrievalOrchestrator:
    
    def __init__(self, ...):
        # ... existing init ...
        self._planner = get_planner()
    
    async def answer(
        self,
        query: str,
        top_k: int | None = None,
        history: list[dict] | None = None,
        session_id: str | None = None,
        enable_decomposition: bool = True,  # NEW
        track_metrics: bool = True,
        enable_hyde: bool = True,
    ) -> OrchestratorResponse:
        
        # NEW: Generate execution plan
        if enable_decomposition and config.ENABLE_QUERY_DECOMPOSITION:
            plan = await self._planner.plan(effective_query)
            logger.info(f"Query plan: complex={plan.is_complex}, tasks={len(plan.sub_tasks)}")
        else:
            # Default single-pass plan
            plan = ExecutionPlan(
                query=effective_query,
                is_complex=False,
                complexity_reason="Decomposition disabled",
                sub_tasks=[...],  # Default tasks
                synthesis_strategy="prose"
            )
        
        # Execute based on plan
        if plan.is_complex and len(plan.parallel_groups()) > 1:
            # Parallelize multi-group plans
            results = await self._execute_plan_parallel(plan)
        else:
            # Sequential execution (current behavior)
            results = await self._execute_plan_sequential(plan)
        
        # Continue with synthesis...
        return OrchestratorResponse(...)
    
    async def _execute_plan_parallel(self, plan: ExecutionPlan) -> Dict[int, Any]:
        """Execute plan with parallelization where possible."""
        results = {}
        
        for group in plan.parallel_groups():
            logger.info(f"Executing parallel group: {[t.id for t in group]}")
            
            # Run all tasks in group concurrently
            tasks = []
            for task in group:
                tasks.append(self._execute_task(task, results))
            
            # Gather results
            group_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for task, result in zip(group, group_results):
                if isinstance(result, Exception):
                    logger.error(f"Task {task.id} failed: {result}")
                    results[task.id] = None
                else:
                    results[task.id] = result
        
        return results
    
    async def _execute_task(self, task, context: Dict[int, Any]) -> Any:
        """Execute a single task."""
        from app.retrieval.planner import ExecutionToolType
        
        if task.tool == ExecutionToolType.VECTOR_SEARCH:
            return await self._execute_vector_search(task, context)
        elif task.tool == ExecutionToolType.GRAPH_LOOKUP:
            return await self._execute_graph_lookup(task, context)
        elif task.tool == ExecutionToolType.ENTITY_COMPARISON:
            return await self._execute_entity_comparison(task, context)
        elif task.tool == ExecutionToolType.AGGREGATION:
            return await self._execute_aggregation(task, context)
        else:
            logger.warning(f"Unknown tool: {task.tool}")
            return None
    
    async def _execute_vector_search(self, task, context: Dict) -> Dict:
        """Execute vector search sub-task."""
        query = task.params.get("query")
        hits = await self._vector.search(query, top_k=self._top_k)
        return {"hits": hits}
    
    async def _execute_graph_lookup(self, task, context: Dict) -> Dict:
        """Execute graph lookup sub-task."""
        entity = task.params.get("entity")
        hops = task.params.get("hops", 1)
        # ... graph traversal ...
        return {"facts": []}
    
    async def _execute_entity_comparison(self, task, context: Dict) -> Dict:
        """Execute entity comparison sub-task."""
        entities = task.params.get("entities", [])
        # Compare multiple entities
        return {"comparison": {}}
    
    async def _execute_aggregation(self, task, context: Dict) -> Dict:
        """Execute aggregation sub-task."""
        # Run Cypher query for aggregation
        return {"aggregation": {}}
```

**Step 3: Add configuration**:

```python
# backend/app/engine/config.py
ENABLE_QUERY_DECOMPOSITION = os.environ.get("ENABLE_QUERY_DECOMPOSITION", "true").lower() == "true"
```

### Testing for Task 3.1

**Create tests** (`backend/tests/test_query_planner.py`):

```python
"""Test query decomposition and execution planning."""
import pytest
from app.retrieval.planner import QueryPlanner, ExecutionPlan, ExecutionToolType

@pytest.fixture
def planner():
    return QueryPlanner()

@pytest.mark.asyncio
class TestQueryPlanner:
    
    async def test_simple_query_plan(self, planner):
        """Simple queries should not decompose."""
        plan = await planner.plan("What is the NAV of Adani Growth?")
        
        assert plan.is_complex is False
        assert len(plan.sub_tasks) <= 2
    
    async def test_complex_query_plan(self, planner):
        """Complex queries should decompose into multiple tasks."""
        plan = await planner.plan(
            "Compare the performance and risk profile of Adani Growth vs Tata Balanced "
            "considering SEBI regulations and current market conditions"
        )
        
        assert plan.is_complex is True
        assert len(plan.sub_tasks) > 1
    
    async def test_plan_parallelization(self, planner):
        """Should identify tasks that can run in parallel."""
        plan = await planner.plan("Compare Fund A vs Fund B")
        
        # Should have parallel groups
        groups = plan.parallel_groups()
        assert len(groups) >= 1
    
    async def test_execution_plan_structure(self, planner):
        """ExecutionPlan should have proper structure."""
        plan = await planner.plan("What is NAV?")
        
        assert hasattr(plan, 'is_complex')
        assert hasattr(plan, 'sub_tasks')
        assert len(plan.sub_tasks) > 0
        
        for task in plan.sub_tasks:
            assert hasattr(task, 'id')
            assert hasattr(task, 'tool')
            assert hasattr(task, 'params')
```

---

## Task 3.2: Implement Parallel Execution for Multi-Entity Queries

### Objective
Enable concurrent execution of independent sub-tasks to reduce latency on complex queries.

**Key Changes**:

1. **Parallelize entity resolution** - Resolve multiple entities concurrently:

```python
# In orchestrator.answer():
# OLD: Sequential entity resolution
resolved_entities: list[BaseEntity] = []
for surface in intent.entities_mentioned:
    res = self._resolver.resolve_surface_form(surface)
    if res and res.entity:
        resolved_entities.append(res.entity)

# NEW: Parallel entity resolution
async def resolve_entity(surface: str):
    res = self._resolver.resolve_surface_form(surface)
    return res.entity if res and res.entity else None

resolution_tasks = [
    resolve_entity(surface) for surface in intent.entities_mentioned
]
resolved_entities = [
    e for e in await asyncio.gather(*resolution_tasks) if e
]
```

2. **Parallelize graph and vector retrieval**:

```python
# They're independent, so gather them
t_retrieval_start = time.perf_counter()

graph_task = self._traversal.traverse(intent, resolved_entities) \
    if intent.requires_graph and resolved_entities else asyncio.sleep(0)

vector_task = self._vector.search(...) \
    if intent.requires_vector else asyncio.sleep(0)

# Run both concurrently
graph_result, vector_result = await asyncio.gather(
    graph_task,
    vector_task,
    return_exceptions=True
)

# Handle results
facts, traversal_paths, cyphers = (
    graph_result if not isinstance(graph_result, Exception) 
    else ([], [], [])
)
chunks = [... for h in vector_result ...] \
    if not isinstance(vector_result, Exception) \
    else []

t_retrieval_ms = (time.perf_counter() - t_retrieval_start) * 1000
```

**Expected latency improvement**:
- Graph: 42.6ms, Vector: 130ms (currently sequential = 172.6ms)
- With parallelization: max(42.6, 130) = 130ms
- **Savings: ~43ms (25% improvement on retrieval)**

### Testing

```python
# backend/tests/test_parallel_execution.py

@pytest.mark.asyncio
async def test_parallel_graph_and_vector(mock_orchestrator):
    """Graph and vector should run in parallel."""
    
    # Measure sequential (mock to force sequential)
    config.ENABLE_PARALLELIZATION = False
    t0 = time.perf_counter()
    await mock_orchestrator.answer("Compare Fund A vs Fund B")
    t_sequential = (time.perf_counter() - t0) * 1000
    
    # Measure parallel (enable parallelization)
    config.ENABLE_PARALLELIZATION = True
    t0 = time.perf_counter()
    await mock_orchestrator.answer("Compare Fund A vs Fund B")
    t_parallel = (time.perf_counter() - t0) * 1000
    
    # Parallel should be faster
    assert t_parallel < t_sequential * 0.9, \
        f"Parallel {t_parallel:.0f}ms should be faster than sequential {t_sequential:.0f}ms"
```

---

## Deliverables for Week 3-4

✅ Query decomposition logic ported to backend  
✅ ExecutionPlan and SubTask data structures  
✅ Parallel task execution framework  
✅ Parallelized entity resolution  
✅ Parallelized graph + vector retrieval  
✅ Comprehensive tests for decomposition and parallelization  

**Success Criteria**:
- Complex queries properly decomposed
- Parallel groups identified correctly
- Parallelization reducing latency by ~25% on retrieval phase
- Tests all passing

**Expected Outcomes**:
- ⏱️ -43ms latency on multi-entity queries (4.5% total improvement)
- 📊 100% of multi-entity queries executing optimally

---

# WEEK 4-5: Complementary Optimizations

## Task 4.1: Activate Cypher Correction for Aggregation Path

### Objective
Enable Cypher query generation, syntax correction, and caching for aggregation-type queries.

### Problem
Currently, aggregation queries bypass Cypher generation entirely. They could benefit from:
1. LLM → Cypher generation for complex aggregations
2. Rule-based syntax correction (avoid LLM retries)
3. Query caching (same aggregations don't regenerate)

### Solution

**Step 1: Add aggregation detection to intent classifier**:

```python
# backend/app/retrieval/intent.py

class QueryIntent:
    # ... existing fields ...
    requires_cypher: bool = False  # NEW
    aggregation_type: str = ""     # "count", "sum", "avg", "ranking"

# In IntentClassifier.classify():
def _detect_aggregation(query: str) -> tuple[bool, str]:
    """Detect if query needs Cypher aggregation."""
    query_lower = query.lower()
    
    agg_patterns = {
        "count": ["total", "how many", "number of", "all the"],
        "sum": ["total aum", "total assets", "combined"],
        "avg": ["average", "mean", "typical"],
        "ranking": ["top", "best", "worst", "ranked", "highest", "lowest"]
    }
    
    for agg_type, patterns in agg_patterns.items():
        if any(p in query_lower for p in patterns):
            return True, agg_type
    
    return False, ""
```

**Step 2: Add Cypher execution to orchestrator**:

```python
# In orchestrator.answer():

from app.engine import text_to_cypher

# After intent classification
if intent.requires_cypher:
    t_cypher_start = time.perf_counter()
    
    # Generate and execute Cypher
    product_names = {e.name for e in resolved_entities} if resolved_entities else set()
    cypher_rows, cypher_usage = text_to_cypher.generate_and_run_with_correction(
        query=effective_query,
        product_names=product_names
    )
    
    t_cypher_ms = (time.perf_counter() - t_cypher_start) * 1000
    
    if cypher_rows:
        logger.info(f"Cypher aggregation: {len(cypher_rows)} rows, {t_cypher_ms:.1f}ms")
        # Store cypher results in context for synthesis
        facts.extend([
            {"type": "aggregation", "value": row}
            for row in cypher_rows
        ])
```

**Step 3: Update synthesis prompt for aggregations**:

```python
# When synthesizing aggregation queries, include tabular context

if intent.aggregation_type:
    agg_context = f"""
    This is an aggregation query requesting {intent.aggregation_type} data.
    
    Structured data retrieved:
    {json.dumps(cypher_rows, indent=2)}
    
    Please provide:
    1. Clear summary of the numbers
    2. Explanation of what they mean
    3. Any relevant comparisons or trends
    """
```

### Testing

```python
# backend/tests/test_cypher_aggregation.py

@pytest.mark.asyncio
async def test_cypher_aggregation_detection(mock_orchestrator):
    """Should detect aggregation queries."""
    
    responses = []
    
    # Should trigger Cypher
    response1 = await mock_orchestrator.answer("What is the total AUM of all schemes?")
    assert response1.retrieval.intent.requires_cypher
    
    # Should not trigger Cypher
    response2 = await mock_orchestrator.answer("Tell me about Adani Growth")
    assert not response2.retrieval.intent.requires_cypher

@pytest.mark.asyncio
async def test_cypher_correction_prevents_retries(mock_orchestrator):
    """Syntax correction should reduce LLM retries."""
    
    # Mock Cypher generation to return invalid Cypher
    with patch('app.engine.text_to_cypher._correct_cypher_syntax') as mock_correct:
        mock_correct.return_value = "FIXED CYPHER"
        
        # Should auto-correct without LLM retry
        result = await mock_orchestrator.answer(
            "What is total AUM?"
        )
        
        # Correction should have been called
        assert mock_correct.called
```

---

## Task 4.2: Optimize Graph Query Merging

### Objective
Combine entity-scoped and product-scoped graph queries into single traversal when both are needed.

**Current inefficiency** (from LATENCY_TOKEN_EVALUATION.md):
- Query 1: Graph by entity (42ms)
- Query 1 returns empty → Query 2: Graph by product (42ms)
- Total: 84ms on 30% of queries

**Solution**: Single merged query

```python
# backend/app/engine/graph_store.py

def get_subgraph_with_fallback(
    query: str,
    entity_names: List[str],
    product_names: List[str],
    hops: int = 1,
    limit: int = 15,
) -> Dict:
    """
    Single query with dual scope: try entity scope first,
    then product scope, all in one roundtrip to Neo4j.
    """
    
    cypher = f"""
    // Try entity scope first
    UNWIND {entity_names} AS entity_scope
    MATCH (e:Entity {{text: entity_scope}})--[r]-->(o)
    RETURN DISTINCT e.text AS entity, type(r) AS rel, o.text AS obj,
           r.confidence AS conf, 1 AS source_priority
    
    UNION
    
    // Fallback to product scope (lower priority)
    UNWIND {product_names} AS product_scope
    MATCH (e:Entity {{product_name: product_scope}})--[r]-->(o)
    WHERE NOT EXISTS(
        (e)--[r2]--(o) 
        WHERE r2.confidence >= r.confidence
    )
    RETURN DISTINCT e.text AS entity, type(r) AS rel, o.text AS obj,
           r.confidence AS conf, 2 AS source_priority
    
    ORDER BY source_priority, conf DESC
    LIMIT {limit}
    """
    
    results = self._run_cypher(cypher)
    return {
        "edges": results,
        "dual_scope": True
    }
```

**Integration**:

```python
# In orchestrator:
# OLD: Two separate calls
graph_result_1 = await self._graph.traverse(...)
if not graph_result_1["edges"]:
    graph_result_1 = await self._graph.traverse(...)  # Second call

# NEW: Single merged query
graph_result = await self._graph.get_subgraph_with_fallback(...)
```

**Savings**:
- 30% of queries × 42ms second query = 12.6ms average saved
- **~2% overall improvement**

---

## Task 4.3: Fine-tune NER Saturation Thresholds

### Objective
Optimize when GLiNER is skipped based on actual query patterns in production.

**Current heuristic**:
```python
skip_gliner = len(confident_layer_a) >= 2 or (len(confident_layer_a) >= 1 and len(text) <= 300)
```

**Data-driven tuning**:

```python
# backend/scripts/tune_ner_thresholds.py

import json
from pathlib import Path
from collections import Counter

def analyze_ner_patterns():
    """Analyze metrics to find optimal thresholds."""
    
    metrics_dir = Path("backend/logs/metrics")
    ner_data = []
    
    # Collect NER metrics
    for metrics_file in metrics_dir.glob("metrics_*.json"):
        with open(metrics_file) as f:
            m = json.load(f)
            
            # Find NER component
            for comp in m.get('components', []):
                if comp['component'] == 'ner':
                    ner_data.append({
                        'query_type': m.get('query_type'),
                        'query_length': len(m.get('query', '')),
                        'entities_count': m.get('entities_count', 0),
                        'latency_ms': comp['latency_ms'],
                        'gliner_skipped': comp.get('gliner_skipped', False)
                    })
    
    # Analyze
    print("=" * 60)
    print("NER THRESHOLD ANALYSIS")
    print("=" * 60)
    
    # By entity count
    by_entity_count = {}
    for d in ner_data:
        ec = d['entities_count']
        if ec not in by_entity_count:
            by_entity_count[ec] = []
        by_entity_count[ec].append(d['latency_ms'])
    
    print("\nLatency by entity count:")
    for count in sorted(by_entity_count.keys()):
        lats = by_entity_count[count]
        avg = sum(lats) / len(lats)
        print(f"  {count} entities: {avg:.1f}ms avg ({len(lats)} queries)")
    
    # By query length
    by_length = {}
    for d in ner_data:
        length_bucket = (d['query_length'] // 50) * 50  # Buckets of 50 chars
        if length_bucket not in by_length:
            by_length[length_bucket] = []
        by_length[length_bucket].append(d['latency_ms'])
    
    print("\nLatency by query length:")
    for length in sorted(by_length.keys()):
        lats = by_length[length]
        avg = sum(lats) / len(lats)
        print(f"  {length}-{length+50} chars: {avg:.1f}ms avg ({len(lats)} queries)")
    
    # Recommendation
    print("\nRECOMMENDATIONS:")
    print("  If queries with 1 entity are fast, lower min_confident_entities to 1")
    print("  If queries under 200 chars are homogeneous, increase length threshold to 200")
    print("  If 2+ entities queries are slow, consider intermediate threshold (1.5)")
```

**Run analysis and update config**:

```bash
python backend/scripts/tune_ner_thresholds.py
# Update backend/app/engine/ner_pipeline.py with findings
```

---

## Deliverables for Week 4-5

✅ Aggregation intent detection  
✅ Cypher query generation and execution  
✅ Cypher syntax correction integrated into aggregation path  
✅ Query caching for aggregations  
✅ Graph query merging (single vs dual roundtrip)  
✅ NER threshold tuning analysis  
✅ Performance regression tests  

**Success Criteria**:
- Aggregation queries executing via Cypher
- Syntax correction preventing >60% of retries
- Graph queries reduced from 2 to 1 roundtrip on 30% of queries
- NER thresholds optimized for production patterns

**Expected Outcomes**:
- ⏱️ -30ms additional latency savings (aggregation + graph merge)
- 💰 $5-10K/month cost savings (eliminated Cypher retries)
- 📊 15% faster aggregation queries

---

# WEEK 5-6: Production Rollout & Monitoring

## Task 5.1: Canary Deployment (10% Traffic)

### Objective
Deploy all efficiency improvements to 10% of users and monitor for issues before full rollout.

**Setup canary deployment**:

```bash
#!/bin/bash
# scripts/deploy_canary.sh

set -e

echo "🚀 Deploying to canary (10% traffic)..."

# 1. Build
echo "[1/5] Building..."
cd backend
docker build -t context-engine:canary .

# 2. Tag for canary
echo "[2/5] Tagging canary version..."
docker tag context-engine:canary context-engine:canary-$(date +%s)

# 3. Update traffic split (if using service mesh)
echo "[3/5] Updating traffic split..."
kubectl patch service context-engine -p '
{
  "spec": {
    "traffic": {
      "canary": 0.10,
      "stable": 0.90
    }
  }
}'

# 4. Monitor
echo "[4/5] Starting monitoring..."
python scripts/monitor_canary.py &
MONITOR_PID=$!

# 5. Alert on issues
echo "[5/5] Monitoring for 24 hours..."
sleep 86400

# Check for issues
if python scripts/check_canary_health.py; then
    echo "✅ Canary healthy - promoting to 50%"
else
    echo "⚠️ Issues detected - rolling back"
    kubectl patch service context-engine -p '{"spec": {"traffic": {"canary": 0.0, "stable": 1.0}}}'
fi

kill $MONITOR_PID
```

**Monitoring script** (`backend/scripts/monitor_canary.py`):

```python
#!/usr/bin/env python3
"""Monitor canary deployment health."""
import asyncio
import time
import json
from datetime import datetime
from pathlib import Path

async def monitor_canary():
    """Continuous monitoring of canary metrics."""
    
    from app.core.metrics import get_metrics_store
    
    metrics_store = get_metrics_store()
    baseline_file = Path("backend/logs/baseline_metrics.json")
    
    # Load baseline
    with open(baseline_file) as f:
        baseline = json.load(f)["summary"]
    
    print("=" * 70)
    print("CANARY MONITORING - 24 HOUR HEALTH CHECK")
    print("=" * 70)
    print(f"Baseline latency:  {baseline['latency_avg_ms']:.0f}ms")
    print(f"Baseline token:    {baseline['token_avg']:.0f} tokens")
    print(f"Baseline accuracy: {baseline['citation_accuracy_avg']:.1%}")
    print()
    
    warning_thresholds = {
        'latency_regression': 1.1,      # 10% worse = fail
        'token_regression': 1.1,         # 10% worse = fail
        'accuracy_regression': 0.95,     # 5% worse = fail
        'error_rate': 0.05,              # 5% errors = fail
    }
    
    start_time = time.time()
    check_interval = 60  # Check every minute
    
    while time.time() - start_time < 86400:  # 24 hours
        
        # Get current metrics
        current = metrics_store.summary()
        
        if not current or not current.get('count'):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Not enough data yet...")
            await asyncio.sleep(check_interval)
            continue
        
        # Check for regressions
        issues = []
        
        # Latency regression
        if current['latency_avg_ms'] > baseline['latency_avg_ms'] * warning_thresholds['latency_regression']:
            issues.append(f"⚠️ Latency regression: {current['latency_avg_ms']:.0f}ms vs {baseline['latency_avg_ms']:.0f}ms baseline")
        
        # Token regression
        if current['token_avg'] > baseline['token_avg'] * warning_thresholds['token_regression']:
            issues.append(f"⚠️ Token regression: {current['token_avg']:.0f} vs {baseline['token_avg']:.0f} baseline")
        
        # Accuracy regression
        if current['citation_accuracy_avg'] < baseline['citation_accuracy_avg'] * warning_thresholds['accuracy_regression']:
            issues.append(f"⚠️ Accuracy regression: {current['citation_accuracy_avg']:.1%} vs {baseline['citation_accuracy_avg']:.1%} baseline")
        
        # Print status
        status = "🟢 HEALTHY" if not issues else "🔴 UNHEALTHY"
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {status}")
        print(f"  Queries:  {current.get('count', 0)}")
        print(f"  Latency:  {current.get('latency_avg_ms', 0):.0f}ms")
        print(f"  Accuracy: {current.get('citation_accuracy_avg', 0):.1%}")
        print(f"  Cache hit: {current.get('cache_hit_rate', 0):.1%}")
        
        for issue in issues:
            print(f"  {issue}")
        
        await asyncio.sleep(check_interval)
    
    print("\n" + "=" * 70)
    print("CANARY MONITORING COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(monitor_canary())
```

**Health check script** (`backend/scripts/check_canary_health.py`):

```python
#!/usr/bin/env python3
"""Final health check after 24h canary."""
import json
from pathlib import Path

def check_health() -> bool:
    """Return True if canary is healthy, False if issues."""
    
    baseline_file = Path("backend/logs/baseline_metrics.json")
    with open(baseline_file) as f:
        baseline = json.load(f)["summary"]
    
    # Get latest metrics
    from app.core.metrics import get_metrics_store
    metrics = get_metrics_store().summary()
    
    failures = []
    
    # Check criteria
    if metrics['latency_avg_ms'] > baseline['latency_avg_ms'] * 1.15:
        failures.append(f"Latency: {metrics['latency_avg_ms']:.0f}ms (>{baseline['latency_avg_ms']*1.15:.0f}ms threshold)")
    
    if metrics['token_avg'] > baseline['token_avg'] * 1.15:
        failures.append(f"Tokens: {metrics['token_avg']:.0f} (>{baseline['token_avg']*1.15:.0f} threshold)")
    
    if metrics['citation_accuracy_avg'] < baseline['citation_accuracy_avg'] * 0.95:
        failures.append(f"Accuracy: {metrics['citation_accuracy_avg']:.1%} (<{baseline['citation_accuracy_avg']*0.95:.1%} threshold)")
    
    if metrics['hallucination_rate'] > 0.15:
        failures.append(f"Hallucination: {metrics['hallucination_rate']:.1%} (>15% threshold)")
    
    if failures:
        print("❌ CANARY HEALTH CHECK FAILED:")
        for f in failures:
            print(f"  - {f}")
        return False
    else:
        print("✅ CANARY HEALTH CHECK PASSED")
        return True

if __name__ == "__main__":
    import sys
    sys.exit(0 if check_health() else 1)
```

---

## Task 5.2: Progressive Rollout

**50% Traffic** (after 24h canary):
```bash
kubectl patch service context-engine -p '{"spec": {"traffic": {"canary": 0.50, "stable": 0.50}}}'
# Monitor for another 12 hours
```

**100% Traffic** (after 12h at 50%):
```bash
kubectl patch service context-engine -p '{"spec": {"traffic": {"canary": 1.0, "stable": 0.0}}}'
```

**Rollback (if needed)**:
```bash
kubectl patch service context-engine -p '{"spec": {"traffic": {"canary": 0.0, "stable": 1.0}}}'
```

---

## Task 5.3: Post-Launch Monitoring Dashboard

**Create dashboard** (`backend/scripts/dashboard_realtime.py`):

```python
#!/usr/bin/env python3
"""Real-time monitoring dashboard for production."""
import time
import json
from datetime import datetime
from pathlib import Path

def display_dashboard():
    """Display real-time metrics dashboard."""
    from app.core.metrics import get_metrics_store
    
    metrics = get_metrics_store()
    
    while True:
        summary = metrics.summary()
        
        # Clear screen
        print("\033[2J\033[H")
        
        print("╔════════════════════════════════════════════════════════════════════╗")
        print("║           EFFICIENCY IMPLEMENTATION - PRODUCTION DASHBOARD         ║")
        print("╚════════════════════════════════════════════════════════════════════╝")
        print()
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        print("┌─ LATENCY ─────────────────────────────────────────────────────────┐")
        print(f"│ P50:  {summary['latency_p50_ms']:.0f}ms")
        print(f"│ P99:  {summary['latency_p99_ms']:.0f}ms")
        print(f"│ Avg:  {summary['latency_avg_ms']:.0f}ms")
        print("└───────────────────────────────────────────────────────────────────┘")
        print()
        
        print("┌─ CACHING ─────────────────────────────────────────────────────────┐")
        print(f"│ Hit Rate:      {summary['cache_hit_rate']:.1%}")
        print(f"│ Queries:       {summary['count']}")
        print("└───────────────────────────────────────────────────────────────────┘")
        print()
        
        print("┌─ QUALITY ─────────────────────────────────────────────────────────┐")
        print(f"│ Citation Accuracy: {summary['citation_accuracy_avg']:.1%}")
        print(f"│ Hallucination Rate: {summary['hallucination_rate']:.1%}")
        print("└───────────────────────────────────────────────────────────────────┘")
        print()
        
        print("┌─ TOKENS ──────────────────────────────────────────────────────────┐")
        print(f"│ Avg per query: {summary['token_avg']:.0f} tokens")
        print("└───────────────────────────────────────────────────────────────────┘")
        
        time.sleep(5)

if __name__ == "__main__":
    display_dashboard()
```

**Run dashboard**:
```bash
python backend/scripts/dashboard_realtime.py
```

---

## Task 5.4: Post-Launch Optimization

**After 1 week in production**, analyze metrics and fine-tune:

```bash
#!/bin/bash
# scripts/post_launch_analysis.sh

echo "POST-LAUNCH ANALYSIS - 1 WEEK PRODUCTION DATA"
echo

# Compare baseline vs current
python backend/scripts/compare_baseline_vs_production.py

# Identify slow queries
python backend/scripts/identify_slow_queries.py

# Suggest optimizations
python backend/scripts/suggest_optimizations.py

# Cache hit analysis
python backend/scripts/cache_hit_analysis.py
```

---

## Final Deliverables (Week 5-6)

✅ Canary deployment infrastructure  
✅ 24-hour health monitoring  
✅ Real-time dashboard  
✅ Progressive rollout plan  
✅ Rollback procedures  
✅ Post-launch analysis scripts  

**Success Criteria**:
- Zero critical issues during canary
- <5% error rate increase
- Latency improvement confirmed in production
- Cache hit rates achieving 40%+

**Final Outcomes**:
- ⏱️ 23% total latency improvement (-183ms)
- 💰 $36K/month cost savings
- 📊 40-50% cache hit rate
- 🎯 100% citation accuracy maintained

---

# Summary: Complete 6-Week Plan

| Week | Focus | Effort | Key Deliverables |
|------|-------|--------|-----------------|
| 1-2 | Foundation | 30h | Metrics framework, baseline, tests |
| 2-3 | Core wins | 20h | HyDE activation, cache consolidation |
| 3-4 | Advanced | 25h | Decomposition, parallelization |
| 4-5 | Optimization | 20h | Aggregation, query merging, tuning |
| 5-6 | Rollout | 15h | Canary, monitoring, production |
| **Total** | **All improvements** | **110h** | **23% latency + $36K/mo savings** |

---

# Quick Command Reference

```bash
# Week 1-2: Setup
cd backend
python scripts/benchmark_baseline.py
pytest tests/test_efficiency_suite.py -v
curl http://localhost:8000/api/metrics/summary

# Week 2-3: Core wins
pytest tests/test_hyde_integration.py tests/test_unified_cache.py -v
python scripts/measure_hyde_impact.py

# Week 3-4: Decomposition
pytest tests/test_query_planner.py tests/test_parallel_execution.py -v
python scripts/benchmark_phase3.py

# Week 4-5: Aggregation
pytest tests/test_cypher_aggregation.py -v
python scripts/tune_ner_thresholds.py
python scripts/benchmark_phase4.py

# Week 5-6: Rollout
bash scripts/deploy_canary.sh
python scripts/monitor_canary.py &
python scripts/dashboard_realtime.py
```

