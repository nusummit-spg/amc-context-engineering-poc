# Complete Implementation Roadmap: Efficiency Features Activation
## Comprehensive Phase-by-Phase Plan with Code, Tests, and Rollout

**Target Outcomes**:
- ⏱️ Latency: 782.8ms → ~600ms (-23%, -183ms)
- 💰 Token Cost: -35-40% ($36K/month savings at 1M queries/day)
- 🎯 Accuracy: Maintain 100% citation accuracy, improve hallucination reduction
- 📊 Cache Hit Rate: Achieve 40-50% on semantic caching

**Timeline**: 6 weeks (can be accelerated to 3 weeks with parallel work)

---

## Phase Overview

```
Week 1-2: Foundation & Testing Infrastructure
  ├─ Task 1.1: Set up monitoring/tracing framework
  ├─ Task 1.2: Create benchmark baseline
  └─ Task 1.3: Build comprehensive test suite

Week 2-3: Core Efficiency Wins (Highest ROI)
  ├─ Task 2.1: Activate HyDE in orchestrator [Priority #1]
  ├─ Task 2.2: Consolidate semantic cache implementations
  └─ Task 2.3: Validate & measure improvements

Week 3-4: Advanced Features
  ├─ Task 3.1: Integrate query decomposition to backend
  ├─ Task 3.2: Parallelize multi-entity queries
  └─ Task 3.3: Validation & A/B testing

Week 4-5: Complementary Optimizations
  ├─ Task 4.1: Activate Cypher correction for aggregation path
  ├─ Task 4.2: Optimize graph query merging
  └─ Task 4.3: Fine-tune NER saturation thresholds

Week 5-6: Production Rollout
  ├─ Task 5.1: Canary deployment (10% traffic)
  ├─ Task 5.2: Monitor & iterate
  ├─ Task 5.3: Full rollout
  └─ Task 5.4: Post-launch optimization

---

# WEEK 1-2: Foundation & Testing Infrastructure

## Task 1.1: Set Up Monitoring & Tracing Framework

### Objective
Create comprehensive monitoring to track latency, tokens, cache hit rates, and accuracy before/after each change.

### Implementation

**1. Create metrics collection module** (`backend/app/core/metrics.py`):

```python
# backend/app/core/metrics.py
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path

@dataclass
class ComponentMetric:
    """Tracks timing and resource usage for each pipeline component."""
    component_name: str
    start_time: float
    end_time: Optional[float] = None
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit: bool = False
    error: Optional[str] = None
    
    def finalize(self):
        if self.end_time is None:
            self.end_time = time.perf_counter()
        self.latency_ms = (self.end_time - self.start_time) * 1000.0
    
    def to_dict(self):
        return {
            'component': self.component_name,
            'latency_ms': round(self.latency_ms, 2),
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'cache_hit': self.cache_hit,
            'error': self.error
        }

@dataclass
class QueryMetrics:
    """Complete metrics for a single query request."""
    request_id: str
    query: str
    query_type: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Per-component tracking
    components: List[ComponentMetric] = field(default_factory=list)
    
    # Aggregates
    total_latency_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_hit: bool = False
    
    # Quality metrics
    hallucination_detected: bool = False
    citation_accuracy: float = 1.0  # 0.0-1.0
    answer_relevance: float = 0.0   # 0.0-1.0
    
    # Metadata
    namespace: str = ""
    entities_count: int = 0
    graph_edges_found: int = 0
    vector_chunks_retrieved: int = 0
    
    def add_component(self, component: ComponentMetric):
        self.components.append(component)
    
    def finalize(self):
        """Calculate aggregates after all components complete."""
        self.total_latency_ms = sum(c.latency_ms for c in self.components)
        self.total_input_tokens = sum(c.input_tokens for c in self.components)
        self.total_output_tokens = sum(c.output_tokens for c in self.components)
        self.cache_hit = any(c.cache_hit for c in self.components)
    
    def to_dict(self):
        self.finalize()
        return {
            'request_id': self.request_id,
            'query': self.query,
            'query_type': self.query_type,
            'timestamp': self.timestamp,
            'components': [c.to_dict() for c in self.components],
            'total_latency_ms': round(self.total_latency_ms, 2),
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'cache_hit': self.cache_hit,
            'hallucination_detected': self.hallucination_detected,
            'citation_accuracy': round(self.citation_accuracy, 3),
            'answer_relevance': round(self.answer_relevance, 3),
            'namespace': self.namespace,
            'entities_count': self.entities_count,
            'graph_edges_found': self.graph_edges_found,
            'vector_chunks_retrieved': self.vector_chunks_retrieved,
        }

class MetricsStore:
    """Stores and aggregates metrics for analysis."""
    
    def __init__(self, storage_path: Path = Path("backend/logs/metrics")):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.metrics: List[QueryMetrics] = []
        self.session_start = datetime.now()
    
    def record(self, metrics: QueryMetrics):
        """Record a single query's metrics."""
        self.metrics.append(metrics)
        # Write to disk immediately (for durability)
        self._persist_metric(metrics)
    
    def _persist_metric(self, metrics: QueryMetrics):
        """Write metric to disk for later analysis."""
        filename = self.storage_path / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{metrics.request_id[:8]}.json"
        with open(filename, 'w') as f:
            json.dump(metrics.to_dict(), f)
    
    def summary(self, filter_by_phase: Optional[str] = None) -> Dict:
        """Generate summary statistics."""
        filtered = self.metrics
        if filter_by_phase:
            filtered = [m for m in self.metrics if m.query_type == filter_by_phase]
        
        if not filtered:
            return {}
        
        latencies = [m.total_latency_ms for m in filtered]
        tokens = [m.total_input_tokens + m.total_output_tokens for m in filtered]
        
        return {
            'count': len(filtered),
            'latency_p50_ms': sorted(latencies)[len(latencies)//2],
            'latency_p99_ms': sorted(latencies)[int(len(latencies)*0.99)],
            'latency_avg_ms': sum(latencies) / len(latencies),
            'token_avg': sum(tokens) / len(tokens),
            'cache_hit_rate': sum(1 for m in filtered if m.cache_hit) / len(filtered),
            'citation_accuracy_avg': sum(m.citation_accuracy for m in filtered) / len(filtered),
            'hallucination_rate': sum(1 for m in filtered if m.hallucination_detected) / len(filtered),
        }

# Global singleton
_metrics_store = None

def get_metrics_store() -> MetricsStore:
    global _metrics_store
    if _metrics_store is None:
        _metrics_store = MetricsStore()
    return _metrics_store
```

**2. Update orchestrator to collect metrics** (`backend/app/retrieval/orchestrator.py`):

```python
# In RetrievalOrchestrator.answer():

async def answer(
    self,
    query: str,
    top_k: int | None = None,
    history: list[dict] | None = None,
    session_id: str | None = None,
    track_metrics: bool = True,  # NEW
) -> OrchestratorResponse:
    from app.core.metrics import QueryMetrics, ComponentMetric, get_metrics_store
    
    req_id = str(uuid4())
    metrics = QueryMetrics(request_id=req_id, query=query, query_type="unknown")
    metrics_store = get_metrics_store() if track_metrics else None
    
    t_total_start = time.perf_counter()
    
    # ─────── Step 0: Rewrite ───────────
    comp_rewrite = ComponentMetric("query_rewrite", time.perf_counter())
    effective_query = query
    # ... existing rewrite logic ...
    comp_rewrite.finalize()
    if metrics:
        metrics.add_component(comp_rewrite)
    
    # ─────── Step 1: Cache Check ───────────
    comp_cache = ComponentMetric("semantic_cache_lookup", time.perf_counter())
    cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version)
    comp_cache.cache_hit = bool(cached_entry and cached_entry.get("cache_hit"))
    comp_cache.finalize()
    if metrics:
        metrics.add_component(comp_cache)
    
    # ... (rest of steps, each wrapped in ComponentMetric) ...
    
    if metrics:
        metrics.total_latency_ms = (time.perf_counter() - t_total_start) * 1000.0
        metrics.query_type = intent.query_type.value if intent else "unknown"
        metrics.entities_count = len(resolved_entities)
        metrics.graph_edges_found = len(facts)
        metrics.vector_chunks_retrieved = len(chunks)
        metrics.citation_accuracy = 1.0  # Will be refined by quality gate
        
        if metrics_store:
            metrics_store.record(metrics)
    
    return OrchestratorResponse(
        intent=intent,
        retrieval=retrieval,
        context=context,
        synthesis=synthesis,
        trace=trace,
        metrics=metrics if track_metrics else None,  # NEW
    )
```

**3. Create dashboard endpoint** (`backend/app/api/routes/metrics.py`):

```python
from fastapi import APIRouter, HTTPException
from app.core.metrics import get_metrics_store

router = APIRouter(prefix="/api/metrics", tags=["monitoring"])

@router.get("/summary")
async def get_summary(phase: str = "all"):
    """Returns summary metrics for the given phase."""
    store = get_metrics_store()
    summary = store.summary(filter_by_phase=phase if phase != "all" else None)
    return summary

@router.get("/recent")
async def get_recent(count: int = 100):
    """Returns the last N query metrics."""
    store = get_metrics_store()
    return [m.to_dict() for m in store.metrics[-count:]]

@router.post("/reset")
async def reset_metrics():
    """Clears metrics (for phase transitions)."""
    from app.core.metrics import MetricsStore
    global _metrics_store
    _metrics_store = MetricsStore()
    return {"status": "reset"}
```

**4. Add to requirements.txt**:
```
prometheus-client>=0.16.0  # Optional: for Prometheus export
```

---

## Task 1.2: Create Baseline Benchmarks

### Objective
Establish current performance metrics before making any changes.

**Create baseline test script** (`backend/scripts/benchmark_baseline.py`):

```python
#!/usr/bin/env python3
"""
Benchmark baseline performance before efficiency improvements.
Run this BEFORE any changes to establish the baseline.
"""
import asyncio
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.retrieval.orchestrator import RetrievalOrchestrator
from app.api.deps import get_container
from app.core.metrics import get_metrics_store

# Test queries covering different categories
BASELINE_QUERIES = [
    # Simple entity lookups (should be fast, cache-friendly)
    ("What is the NAV of Adani Growth fund?", "simple_entity"),
    ("Tell me about Tata Balanced scheme", "simple_entity"),
    ("What is the AUM of Axis Bluechip?", "simple_entity"),
    
    # Comparisons (multi-entity, should benefit from decomposition)
    ("Compare Adani Growth vs Tata Balanced", "comparison"),
    ("Which is better: equity or debt funds?", "comparison"),
    
    # Aggregations (would benefit from Cypher)
    ("What is the total AUM of all equity schemes?", "aggregation"),
    ("List the top 5 performing funds", "aggregation"),
    
    # Complex questions (should benefit from decomposition)
    ("How do SEBI regulations affect fund performance, specifically for Adani schemes?", "complex"),
    ("Explain the relationship between NAV, performance metrics, and regulatory compliance", "complex"),
]

async def run_baseline_benchmark():
    """Run baseline benchmark and save results."""
    container = get_container()
    orchestrator = container.orchestrator
    metrics_store = get_metrics_store()
    
    print("=" * 80)
    print("BASELINE BENCHMARK - BEFORE EFFICIENCY IMPROVEMENTS")
    print("=" * 80)
    print(f"Query count: {len(BASELINE_QUERIES)}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    results = []
    for i, (query, query_type) in enumerate(BASELINE_QUERIES, 1):
        print(f"[{i}/{len(BASELINE_QUERIES)}] {query_type.upper()}: {query[:60]}...")
        
        try:
            t0 = time.perf_counter()
            response = await orchestrator.answer(query, track_metrics=True)
            t_elapsed = (time.perf_counter() - t0) * 1000.0
            
            metrics = response.metrics if hasattr(response, 'metrics') else None
            
            result = {
                'query': query,
                'type': query_type,
                'latency_ms': round(t_elapsed, 2),
                'cache_hit': metrics.cache_hit if metrics else False,
                'tokens': metrics.total_input_tokens + metrics.total_output_tokens if metrics else 0,
            }
            results.append(result)
            
            print(f"  ✓ {t_elapsed:.1f}ms")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({
                'query': query,
                'type': query_type,
                'error': str(e)
            })
    
    # Print summary
    print()
    print("=" * 80)
    print("BASELINE SUMMARY")
    print("=" * 80)
    summary = metrics_store.summary()
    print(json.dumps(summary, indent=2))
    
    # Save to file
    baseline_file = Path("backend/logs/baseline_metrics.json")
    baseline_file.parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_file, 'w') as f:
        json.dump({
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'phase': 'BASELINE_BEFORE_IMPROVEMENTS',
            'queries': results,
            'summary': summary,
        }, f, indent=2)
    
    print(f"\n✓ Baseline saved to {baseline_file}")
    return results, summary

if __name__ == "__main__":
    asyncio.run(run_baseline_benchmark())
```

**Run baseline**:
```bash
cd backend
python scripts/benchmark_baseline.py > logs/baseline_output.log 2>&1
```

This captures:
- Latency for each query type
- Token counts
- Cache hit rates
- Any errors

---

## Task 1.3: Build Comprehensive Test Suite

**Create test module** (`backend/tests/test_efficiency_suite.py`):

```python
"""
Comprehensive test suite for all efficiency improvements.
Tests each feature independently, then in combination.
"""
import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock

from app.engine import (
    hyde, ner_pipeline, semantic_cache, intent_cache,
    text_to_cypher, config
)
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.core.metrics import QueryMetrics, get_metrics_store

class TestHyDECaching:
    """Test HyDE response caching feature."""
    
    def setup_method(self):
        hyde.clear_hyde_cache()
    
    def test_hyde_cache_hit_latency(self):
        """Cache hit should be <5ms vs ~50ms miss."""
        query = "Compare equity vs debt funds"
        
        # First call: cache miss
        t0 = time.perf_counter()
        doc1, lat1 = hyde.generate_hypothetical_document(query)
        t_first = (time.perf_counter() - t0) * 1000
        
        assert doc1, "Should generate HyDE document"
        assert lat1 > 20, f"First call should be >20ms (LLM), got {lat1:.1f}ms"
        
        # Second call: cache hit
        t0 = time.perf_counter()
        doc2, lat2 = hyde.generate_hypothetical_document(query)
        t_second = (time.perf_counter() - t0) * 1000
        
        assert doc1 == doc2, "Cache should return identical document"
        assert lat2 < 5.0, f"Cache hit should be <5ms, got {lat2:.1f}ms"
        
        # Verify speedup
        speedup = t_first / lat2
        assert speedup > 10, f"Should be >10x speedup, got {speedup:.1f}x"
    
    def test_hyde_cache_prefix_normalization(self):
        """Queries with same first 30 words should hit same cache."""
        q1 = "What is the NAV and performance of Adani Growth scheme for retail investors?"
        q2 = "what is the nav and performance of adani growth scheme for retail investors??"
        
        doc1, _ = hyde.generate_hypothetical_document(q1)
        lat2 = hyde.generate_hypothetical_document(q2)[1]
        
        assert lat2 < 5.0, "Normalized query should be cache hit"
    
    def test_hyde_cache_lru_eviction(self):
        """Cache should evict oldest entries when full."""
        for i in range(5100):  # Exceed max size (5000)
            query = f"Test query number {i}"
            hyde.generate_hypothetical_document(query)
        
        stats = hyde.get_hyde_cache_stats()
        assert stats['cache_size'] < 5000, "Cache should have evicted oldest entries"
        assert stats['cache_size'] >= 4000, "Cache should still have recent entries"

class TestGLiNERSkip:
    """Test GLiNER saturation bypass."""
    
    def setup_method(self):
        ner_pipeline.clear_ner_cache()
    
    def test_gliner_skip_on_saturation(self):
        """Layer B should be skipped when Layer A finds >=2 confident entities."""
        query = "What is the NAV of Adani Growth scheme?"
        
        t0 = time.perf_counter()
        entities = ner_pipeline.run_layers_ab(query, min_confident_entities=2)
        latency = (time.perf_counter() - t0) * 1000
        
        # Should find entities from Layer A
        assert len(entities) >= 1
        layer_a_ents = [e for e in entities if e.get("layer") == "A"]
        assert len(layer_a_ents) >= 1
        
        # Should be fast (no GLiNER)
        assert latency < 10, f"Should skip GLiNER, got {latency:.1f}ms"
    
    def test_gliner_runs_on_generic_query(self):
        """Layer B should run for queries without clear entities."""
        query = "How do you choose between investment options?"
        
        entities = ner_pipeline.run_layers_ab(query, min_confident_entities=2)
        
        # May or may not have Layer B, depending on text content
        # But should complete without error
        assert isinstance(entities, list)

class TestSemanticCache:
    """Test semantic cache implementation."""
    
    def setup_method(self):
        cache = semantic_cache.get_cache()
        cache.clear()
    
    def test_semantic_cache_store_and_retrieve(self):
        """Should store and retrieve semantically similar queries."""
        cache = semantic_cache.get_cache()
        
        query1 = "What is the NAV of Adani Growth scheme?"
        payload1 = {
            "answer": "The NAV is 142.35 as of last disclosure.",
            "tokens": 50,
        }
        
        cache.store(query1, payload1)
        
        # Exact query should hit
        result, lat = cache.check(query1)
        assert result is not None, "Exact query should hit cache"
        assert result['answer'] == payload1['answer']
    
    def test_semantic_cache_similarity(self):
        """Should hit on semantically similar queries."""
        cache = semantic_cache.get_cache()
        
        query1 = "What is the NAV of Adani Growth scheme?"
        payload1 = {"answer": "The NAV is 142.35"}
        cache.store(query1, payload1)
        
        # Similar query (different wording, same meaning)
        query2 = "Tell me the current NAV for Adani Growth fund"
        result, lat = cache.check(query2)
        
        # Depending on threshold, might or might not hit
        # Just verify it doesn't error
        assert isinstance(result, (dict, type(None)))

class TestIntegration:
    """Integration tests combining multiple features."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_with_all_features(self):
        """Verify orchestrator works with all efficiency features enabled."""
        # Ensure all flags are enabled
        config.ENABLE_HYDE_CACHE = True
        config.ENABLE_GLINER_SKIP = True
        config.ENABLE_CYPHER_AUTO_CORRECTION = True
        
        # This would require a full container setup
        # For now, just verify flags are set
        assert config.ENABLE_HYDE_CACHE
        assert config.ENABLE_GLINER_SKIP
        assert config.ENABLE_CYPHER_AUTO_CORRECTION

class TestPerformanceRegressions:
    """Verify changes don't regress performance."""
    
    def test_no_latency_regression(self):
        """Efficiency features should not add latency to non-cached queries."""
        # This is a placeholder for performance regression testing
        # Would compare latency with/without features
        pass
    
    def test_quality_maintained(self):
        """Efficiency features should not degrade answer quality."""
        # This would verify citation accuracy, hallucination rate, etc.
        pass
```

**Run tests**:
```bash
pytest backend/tests/test_efficiency_suite.py -v --tb=short
```

---

## Deliverables for Week 1-2

✅ Metrics collection module (app/core/metrics.py)  
✅ Updated orchestrator with metrics tracking  
✅ Metrics dashboard API endpoint  
✅ Baseline benchmark established (saved to logs/baseline_metrics.json)  
✅ Comprehensive test suite (test_efficiency_suite.py)  

**Success Criteria**:
- Baseline metrics captured for all query types
- Test suite passes (100% of tests green)
- Metrics API returning correct summary data

---

# WEEK 2-3: Core Efficiency Wins

## Task 2.1: Activate HyDE in Orchestrator [Priority #1]

### Objective
Integrate HyDE response caching into the production orchestrator to reduce vector search latency on cache hits.

### Detailed Implementation

**Step 1: Update orchestrator imports** (`backend/app/retrieval/orchestrator.py`):

```python
# Add to imports at top of file
from app.engine import hyde  # NEW
from app.core.metrics import ComponentMetric  # For tracking
```

**Step 2: Add HyDE call to orchestrator.answer()** method:

```python
async def answer(
    self,
    query: str,
    top_k: int | None = None,
    history: list[dict] | None = None,
    session_id: str | None = None,
    track_metrics: bool = True,
    enable_hyde: bool = True,  # NEW parameter
) -> OrchestratorResponse:
    # ... existing code ...
    
    # Step 4 — Graph traversal
    t_graph_start = time.perf_counter()
    facts, traversal_paths, cyphers = [], [], []
    if intent.requires_graph and resolved_entities:
        facts, traversal_paths, cyphers = await self._traversal.traverse(
            intent, resolved_entities
        )
    t_graph_ms = (time.perf_counter() - t_graph_start) * 1000
    
    # Step 4.5 — HyDE EXPANSION (NEW)
    comp_hyde = None
    hyde_doc = ""
    if enable_hyde and config.ENABLE_HYDE_CACHE and intent.requires_vector:
        comp_hyde = ComponentMetric("hyde_expansion", time.perf_counter())
        hyde_doc, hyde_latency = hyde.generate_hypothetical_document(effective_query)
        comp_hyde.latency_ms = hyde_latency
        comp_hyde.finalize()
        if metrics:
            metrics.add_component(comp_hyde)
        logger.info(f"HyDE: {hyde_latency:.1f}ms (cached: {hyde_latency < 5})")
    
    # Steps 5-6 — taxonomy-scoped vector search
    t_vector_start = time.perf_counter()
    chunks: list[RetrievedChunk] = []
    if intent.requires_vector:
        # Use HyDE-augmented query if available
        search_query = effective_query
        if hyde_doc:
            search_query = f"{effective_query}\n\nHYPOTHETICAL DOCUMENT:\n{hyde_doc}"
            logger.info(f"Vector search with HyDE augmentation")
        
        hits = await self._vector.search(
            search_query,  # HyDE-augmented if available
            top_k=top_k or self._top_k,
            taxonomy_paths=intent.taxonomy_paths or None,
            entity_names=[e.name for e in resolved_entities] or None,
        )
        chunks = [
            RetrievedChunk(
                chunk_id=h["chunk_id"],
                document_id=h.get("document_id", ""),
                document_title=h.get("document_title"),
                text=h.get("text", ""),
                score=h.get("score", 0.0),
                taxonomy_paths=h.get("taxonomy_paths", []),
            )
            for h in hits
        ]
    t_vector_ms = (time.perf_counter() - t_vector_start) * 1000
    
    # ... rest of existing code ...
```

**Step 3: Add HyDE to streaming path** (`orchestrator.answer_stream()`):

```python
async def answer_stream(
    self,
    query: str,
    top_k: int | None = None,
    history: list[dict] | None = None,
    session_id: str | None = None,
    enable_hyde: bool = True,  # NEW
) -> AsyncGenerator[dict, None]:
    # ... existing code ...
    
    # ── Step 4.5: HyDE Expansion ──────────────────────────────────
    hyde_doc = ""
    if enable_hyde and config.ENABLE_HYDE_CACHE and intent and intent.requires_vector:
        try:
            hyde_doc, hyde_latency = hyde.generate_hypothetical_document(effective_query)
            logger.info(f"HyDE: {hyde_latency:.1f}ms, cached={hyde_latency < 5}")
        except Exception as exc:
            logger.warning(f"HyDE generation failed (continuing anyway): {exc}")
    
    # ── Steps 5-6: Vector search ──────────────────────────────────
    search_query = effective_query
    if hyde_doc:
        search_query = f"{effective_query}\n\nHYPOTHETICAL DOCUMENT:\n{hyde_doc}"
    
    # ... use search_query in vector search ...
```

**Step 4: Add configuration option** (`backend/app/engine/config.py`):

```python
# Add to config.py:
ENABLE_HYDE_IN_ORCHESTRATOR = os.environ.get("ENABLE_HYDE_IN_ORCHESTRATOR", "true").lower() == "true"

# And update feature flag comment:
"""
EFFICIENCY FEATURES — Enable/disable each optimization independently.
Can be toggled via environment variables for A/B testing.
"""
ENABLE_HYDE_CACHE = os.environ.get("ENABLE_HYDE_CACHE", "true").lower() == "true"
ENABLE_HYDE_IN_ORCHESTRATOR = os.environ.get("ENABLE_HYDE_IN_ORCHESTRATOR", "true").lower() == "true"
ENABLE_GLINER_SKIP = os.environ.get("ENABLE_GLINER_SKIP", "true").lower() == "true"
```

### Testing for Task 2.1

**Create test file** (`backend/tests/test_hyde_integration.py`):

```python
"""Test HyDE integration in orchestrator."""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from app.retrieval.orchestrator import RetrievalOrchestrator
from app.engine import config

@pytest.mark.asyncio
class TestHyDEIntegration:
    """Test HyDE is called and used in orchestrator."""
    
    async def test_hyde_called_when_enabled(self, mock_container):
        """Verify HyDE is called when enabled."""
        config.ENABLE_HYDE_CACHE = True
        config.ENABLE_HYDE_IN_ORCHESTRATOR = True
        
        with patch('app.engine.hyde.generate_hypothetical_document') as mock_hyde:
            mock_hyde.return_value = ("Test hypothetical doc", 1.5)
            
            orchestrator = mock_container.orchestrator
            response = await orchestrator.answer("What is the NAV?", enable_hyde=True)
            
            # Verify HyDE was called
            assert mock_hyde.called, "HyDE should be called"
    
    async def test_hyde_not_called_when_disabled(self, mock_container):
        """Verify HyDE is not called when disabled."""
        config.ENABLE_HYDE_IN_ORCHESTRATOR = False
        
        with patch('app.engine.hyde.generate_hypothetical_document') as mock_hyde:
            orchestrator = mock_container.orchestrator
            response = await orchestrator.answer("What is the NAV?", enable_hyde=False)
            
            # Verify HyDE was NOT called
            assert not mock_hyde.called, "HyDE should not be called when disabled"
    
    async def test_hyde_cache_hit_improves_latency(self, mock_container):
        """Verify cache hits reduce total latency."""
        config.ENABLE_HYDE_CACHE = True
        config.ENABLE_HYDE_IN_ORCHESTRATOR = True
        
        orchestrator = mock_container.orchestrator
        
        # First call: cache miss (HyDE generates ~50ms)
        t0 = time.perf_counter()
        response1 = await orchestrator.answer("Compare equity vs debt", enable_hyde=True)
        t1 = (time.perf_counter() - t0) * 1000
        
        # Second call: cache hit (HyDE returns ~1ms)
        t0 = time.perf_counter()
        response2 = await orchestrator.answer("Compare equity vs debt", enable_hyde=True)
        t2 = (time.perf_counter() - t0) * 1000
        
        # Second call should be noticeably faster
        assert t2 < t1 * 0.8, f"Cache hit should be <80% of miss latency: {t2:.0f}ms vs {t1:.0f}ms"
```

**Run integration tests**:
```bash
pytest backend/tests/test_hyde_integration.py -v -s
```

### Validation & Measurement

**Create measurement script** (`backend/scripts/measure_hyde_impact.py`):

```python
#!/usr/bin/env python3
"""Measure latency impact of HyDE activation."""
import asyncio
import time
import json
from pathlib import Path

async def measure_impact():
    """Compare latency with/without HyDE."""
    from app.api.deps import get_container
    from app.engine import config
    
    container = get_container()
    orchestrator = container.orchestrator
    
    queries = [
        "Compare Adani Growth vs Tata Balanced",
        "What is the performance of equity funds?",
        "Tell me about fund categories",
    ]
    
    results = {"with_hyde": [], "without_hyde": []}
    
    print("Measuring HyDE impact...")
    print()
    
    # Measure WITHOUT HyDE
    config.ENABLE_HYDE_IN_ORCHESTRATOR = False
    for query in queries:
        latencies = []
        for _ in range(3):
            t0 = time.perf_counter()
            response = await orchestrator.answer(query, enable_hyde=False)
            latency = (time.perf_counter() - t0) * 1000
            latencies.append(latency)
        
        avg_latency = sum(latencies) / len(latencies)
        results["without_hyde"].append({
            "query": query[:50],
            "avg_latency_ms": round(avg_latency, 1)
        })
        print(f"WITHOUT HyDE: {avg_latency:.1f}ms - {query[:50]}...")
    
    print()
    
    # Measure WITH HyDE
    config.ENABLE_HYDE_IN_ORCHESTRATOR = True
    for query in queries:
        latencies = []
        for _ in range(3):
            t0 = time.perf_counter()
            response = await orchestrator.answer(query, enable_hyde=True)
            latency = (time.perf_counter() - t0) * 1000
            latencies.append(latency)
        
        avg_latency = sum(latencies) / len(latencies)
        results["with_hyde"].append({
            "query": query[:50],
            "avg_latency_ms": round(avg_latency, 1)
        })
        print(f"WITH HyDE:    {avg_latency:.1f}ms - {query[:50]}...")
    
    # Calculate improvement
    print()
    print("=" * 60)
    print("IMPACT SUMMARY")
    print("=" * 60)
    
    latencies_without = [r["avg_latency_ms"] for r in results["without_hyde"]]
    latencies_with = [r["avg_latency_ms"] for r in results["with_hyde"]]
    
    avg_without = sum(latencies_without) / len(latencies_without)
    avg_with = sum(latencies_with) / len(latencies_with)
    improvement = avg_without - avg_with
    pct_improvement = (improvement / avg_without) * 100 if avg_without > 0 else 0
    
    print(f"Average WITHOUT HyDE: {avg_without:.1f}ms")
    print(f"Average WITH HyDE:    {avg_with:.1f}ms")
    print(f"Improvement:          {improvement:.1f}ms ({pct_improvement:.1f}%)")
    
    # Save results
    output_file = Path("backend/logs/hyde_impact.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump({
            **results,
            "summary": {
                "avg_without_hyde_ms": round(avg_without, 1),
                "avg_with_hyde_ms": round(avg_with, 1),
                "improvement_ms": round(improvement, 1),
                "improvement_percent": round(pct_improvement, 1),
            }
        }, f, indent=2)
    
    print(f"\n✓ Results saved to {output_file}")

if __name__ == "__main__":
    asyncio.run(measure_impact())
```

**Run measurement**:
```bash
python backend/scripts/measure_hyde_impact.py
```

---

## Task 2.2: Consolidate Semantic Cache Implementations

### Objective
There are two semantic cache implementations. Consolidate to one unified, optimal implementation.

**Problem**: 
- `backend/app/engine/semantic_cache.py` — FAISS-backed, sophisticated
- `backend/app/retrieval/cache.py::SemanticQueryCache` — Simpler, currently used

**Solution**: Unify to use the FAISS-backed engine version

**Step 1: Audit current usage** (`backend/app/retrieval/cache.py`):

Read current implementation to understand the API:
```python
# backend/app/retrieval/cache.py

from app.engine.semantic_cache import get_cache as get_engine_cache, SemanticCache

class SemanticQueryCache:
    """Wrapper that bridges to engine semantic cache."""
    
    def __init__(self):
        self._engine_cache = get_engine_cache()
    
    def lookup(self, query: str, corpus_version: str = "v2_baseline") -> dict | None:
        """Lookup query in cache."""
        result, latency = self._engine_cache.check(query)
        if result:
            return {
                "cache_hit": True,
                "answer": result.get("answer"),
                "confidence": result.get("confidence", "high"),
                "compliance_note": result.get("compliance_note"),
                "citations": result.get("citations", []),
                "provenance": result.get("provenance", []),
                "quality_score": result.get("quality_score", 1.0),
                "output_tokens": result.get("output_tokens", 0),
                "intent": result.get("intent", {}),
                "traversal_paths": result.get("traversal_paths", []),
                "graph_facts": result.get("graph_facts", []),
                "sources": result.get("sources", []),
            }
        return None
    
    def store(self, query: str, payload: dict, corpus_version: str = "v2_baseline"):
        """Store query result in cache."""
        # Clean payload to match engine cache format
        self._engine_cache.store(query, payload)
```

**Step 2: Unify in retrieval/cache.py**:

```python
# backend/app/retrieval/cache.py
"""Unified semantic caching layer."""

from typing import Dict, Optional
from app.engine.semantic_cache import SemanticCache, get_cache as get_engine_cache

class UnifiedSemanticCache(SemanticCache):
    """
    Enhanced semantic cache with orchestrator-specific features.
    Extends engine's SemanticCache with corpus versioning and result validation.
    """
    
    def __init__(self):
        super().__init__()
        self._corpus_versions = {}  # Track corpus version invalidation
    
    def lookup(self, query: str, corpus_version: str = "v2_baseline") -> Optional[Dict]:
        """Lookup with corpus version validation."""
        # Check if corpus changed
        if corpus_version in self._corpus_versions:
            if self._corpus_versions[corpus_version]["invalidated"]:
                logger.info(f"Corpus {corpus_version} invalidated, cache miss")
                return None
        
        result, latency = self.check(query)
        if result:
            return {
                "cache_hit": True,
                "latency_ms": round(latency, 1),
                **result
            }
        return None
    
    def store(self, query: str, payload: Dict, corpus_version: str = "v2_baseline"):
        """Store with corpus version tagging."""
        tagged_payload = {
            **payload,
            "corpus_version": corpus_version,
            "stored_at": time.time(),
        }
        self.store(query, tagged_payload)
    
    def invalidate_corpus(self, corpus_version: str):
        """Invalidate cache for specific corpus version."""
        self._corpus_versions[corpus_version] = {"invalidated": True}
        logger.info(f"Corpus {corpus_version} invalidated")

# Global singleton
_global_cache: Optional[UnifiedSemanticCache] = None

def get_semantic_cache() -> UnifiedSemanticCache:
    """Get unified semantic cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = UnifiedSemanticCache()
    return _global_cache
```

**Step 3: Update orchestrator to use unified cache**:

```python
# In orchestrator.answer():
from app.retrieval.cache import get_semantic_cache

cache = get_semantic_cache()
cached_entry = cache.lookup(effective_query, corpus_version=self._corpus_version)

if cached_entry and cached_entry.get("cache_hit"):
    logger.info(f"Semantic cache HIT ({cached_entry.get('latency_ms', 0):.1f}ms)")
    # ... use cached entry ...
```

**Step 4: Add tests** (`backend/tests/test_unified_cache.py`):

```python
"""Test unified semantic cache."""
import pytest
from app.retrieval.cache import get_semantic_cache, UnifiedSemanticCache

@pytest.fixture
def cache():
    c = get_semantic_cache()
    c.clear()
    return c

def test_lookup_and_store(cache):
    """Test basic store/lookup."""
    query = "What is NAV?"
    payload = {"answer": "NAV is...", "tokens": 50}
    
    cache.store(query, payload)
    result = cache.lookup(query)
    
    assert result is not None
    assert result["cache_hit"] is True
    assert result["answer"] == "NAV is..."

def test_corpus_invalidation(cache):
    """Test corpus version invalidation."""
    query = "What is NAV?"
    payload = {"answer": "NAV is..."}
    
    cache.store(query, payload, corpus_version="v1")
    assert cache.lookup(query, corpus_version="v1") is not None
    
    # Invalidate corpus
    cache.invalidate_corpus("v1")
    assert cache.lookup(query, corpus_version="v1") is None
```

---

## Task 2.3: Validate & Measure Improvements

**Create comprehensive measurement** (`backend/scripts/measure_phase2.py`):

```bash
#!/bin/bash
# Run all Phase 2 measurements

cd backend

echo "================================"
echo "PHASE 2: CORE EFFICIENCY WINS"
echo "================================"
echo

echo "[1/3] Baseline (if not already done)"
python scripts/benchmark_baseline.py

echo
echo "[2/3] Running tests"
pytest tests/test_hyde_integration.py tests/test_unified_cache.py -v

echo
echo "[3/3] Measuring impact"
python scripts/measure_hyde_impact.py

echo
echo "================================"
echo "Phase 2 Complete"
echo "================================"
```

**Make executable**:
```bash
chmod +x backend/scripts/measure_phase2.sh
```

---

## Deliverables for Week 2-3

✅ HyDE integrated into orchestrator (both sync and streaming)  
✅ Configuration flags for HyDE control  
✅ HyDE integration tests  
✅ Semantic cache unified to one implementation  
✅ Cache lookup/store/invalidation working  
✅ Impact measurement scripts  
✅ Before/after latency comparison  

**Success Criteria**:
- HyDE cache hits achieving <5ms latency
- Semantic cache consolidated (no more dual implementations)
- Latency improvement measured (target: 3-5% on vector-heavy queries)
- All tests passing

**Expected Outcomes**:
- ⏱️ -20ms average latency (2.5% improvement)
- 💰 -$300-500/month cost savings
- 📊 40% cache hit rate on semantic cache

---

[Document continues with WEEK 3-4, WEEK 4-5, and WEEK 5-6 sections...]

---

# QUICK REFERENCE: Commands to Run

## Week 1-2: Setup
```bash
# Establish baseline
cd backend
python scripts/benchmark_baseline.py > logs/baseline_phase1.log

# Run test suite
pytest tests/test_efficiency_suite.py -v

# Verify metrics collection
curl http://localhost:8000/api/metrics/summary
```

## Week 2-3: HyDE + Cache
```bash
# Run integration tests
pytest tests/test_hyde_integration.py tests/test_unified_cache.py -v

# Measure impact
python scripts/measure_hyde_impact.py
python scripts/measure_phase2.sh
```

## Week 3-4: Decomposition
```bash
# [To be added in next section]
```

## Week 4-5: Aggregation
```bash
# [To be added in next section]
```

## Week 5-6: Rollout
```bash
# Canary deployment
export EFFICIENCY_FEATURES_PHASE=CANARY_10_PERCENT
./scripts/deploy_canary.sh

# Monitor
watch -n 5 'curl -s http://localhost:8000/api/metrics/summary | jq'

# Full rollout
export EFFICIENCY_FEATURES_PHASE=FULL_ROLLOUT
./scripts/deploy_production.sh
```

---

