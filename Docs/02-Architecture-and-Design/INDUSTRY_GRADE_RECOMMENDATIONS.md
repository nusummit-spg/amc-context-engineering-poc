# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Industry-Grade System Enhancements
## Strategic Roadmap to Enterprise-Ready RAG Platform

**Current State**: Mature context-engineered hybrid RAG with smart retrieval, semantic caching, and comprehensive tracing.

**Target State**: Enterprise-grade system supporting 100K+ QPS, multi-tenant SaaS, regulatory compliance, and autonomous operations.

---

## 1. OBSERVABILITY & MONITORING (Critical Priority)

### Current State
- ✅ Component-level tracing with `QueryTracingContext`
- ✅ Structured error codes and logging
- ⚠️ **Gap**: No distributed tracing across services
- ⚠️ **Gap**: No real-time alerting or SLA tracking
- ⚠️ **Gap**: No metrics aggregation or dashboarding

### Recommendations

#### 1.1 Distributed Tracing (OpenTelemetry)
```python
# Add to backend/app/core/otel.py
from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Initialize with OTLP exporter (Jaeger/Datadog/NewRelic compatible)
trace.set_tracer_provider(TracerProvider(
    active_span_processor=BatchSpanProcessor(OTLPSpanExporter())
))
```

**Benefits:**
- Trace requests across microservices (API → Vector DB → Graph → LLM)
- Correlate client requests with backend operations
- Identify bottlenecks in dependency chains
- **Cost**: ~$0.30/million spans with Datadog

**Implementation Steps:**
1. Instrument retrieval pipeline with `tracer.start_as_current_span()`
2. Add parent-child relationships for nested calls
3. Export to OpenTelemetry collector (open-source or SaaS)
4. Correlate with application logs via trace_id

---

#### 1.2 Real-Time Metrics & SLA Dashboard
```python
# Add to backend/app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Latency percentiles
query_latency = Histogram(
    'query_latency_ms', 'Query latency in ms',
    buckets=[50, 100, 250, 500, 1000, 2000],
    labelnames=['query_type', 'cache_hit']
)

# Error rates
llm_errors = Counter(
    'llm_errors_total', 'LLM API errors',
    labelnames=['provider', 'error_type']
)

# Resource utilization
vector_index_size = Gauge(
    'vector_index_size_mb', 'FAISS index size in MB'
)
```

**Metrics to Track:**
- P50, P95, P99 latency by query type
- Cache hit rate (%) by time window
- Error rates by component (vector DB, graph, LLM)
- Token usage (cost tracking)
- Quality gate pass rate (%)
- Citation accuracy (%)

**Tools:**
- **Prometheus** + **Grafana** (open-source, self-hosted)
- **Datadog**, **New Relic**, or **Dynatrace** (SaaS, easier)

**Expected Dashboards:**
1. **System Health**: Latency, error rate, cache hit, SLA compliance
2. **Query Performance**: Breakdown by type, trend analysis
3. **Resource Utilization**: Vector index growth, graph DB connections, LLM tokens/cost
4. **Data Quality**: Citation accuracy, hallucination rate, policy compliance

---

#### 1.3 Structured Logging & Log Aggregation
```python
# Update backend/app/core/logging.py with ECS format
import logging
import json

class ECSFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "@timestamp": datetime.utcnow().isoformat(),
            "message": record.getMessage(),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": getattr(record, 'trace_id', None),
            "request_id": getattr(record, 'request_id', None),
            "service": "context-engineering-api",
            "environment": get_settings().environment,
        }
        if record.exc_info:
            log_obj["error"] = {"stack_trace": self.formatException(record.exc_info)}
        return json.dumps(log_obj)
```

**Tools:**
- **ELK Stack** (Elasticsearch, Logstash, Kibana) - open-source
- **Loki** + **Grafana** - lightweight Prometheus-like alternative
- **Splunk**, **Datadog**, **CloudWatch** - enterprise SaaS

**Log Events to Capture:**
- Query ingress (input length, session_id, user_id)
- Cache lookup (hit/miss, similarity score, latency)
- NER extraction (entities found, confidence)
- Graph traversal (nodes, edges, hops)
- Vector search (raw candidates, reranked, top score)
- LLM calls (model, tokens, cost, latency)
- Guardrail violations (type, user_id, timestamp)
- Errors (type, component, stack trace)

---

### Priority & Effort
| Feature | Effort | Impact | Timeline |
|---------|--------|--------|----------|
| OpenTelemetry integration | 3 days | High (tracing) | Weeks 1-2 |
| Prometheus/Grafana setup | 5 days | High (dashboards) | Weeks 2-3 |
| ECS logging & log aggregation | 4 days | High (debugging) | Weeks 2-3 |

---

## 2. PRODUCTION RESILIENCE & RELIABILITY (Critical)

### Current State
- ✅ Multi-provider LLM fallback (disabled by default)
- ✅ Retry logic with exponential backoff
- ⚠️ **Gap**: No circuit breakers for cascading failures
- ⚠️ **Gap**: No graceful degradation modes
- ⚠️ **Gap**: No chaos engineering / fault injection testing

### Recommendations

#### 2.1 Circuit Breaker Pattern
```python
# Add to backend/app/core/resilience.py
from pybreaker import CircuitBreaker

class ComponentCircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.breaker = CircuitBreaker(
            fail_max=failure_threshold,
            reset_timeout=recovery_timeout,
            name=name
        )
    
    async def call(self, func, *args, **kwargs):
        """Calls func; opens circuit on repeated failures."""
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            self.breaker.call(lambda: (_ for _ in ()).throw(e))
            raise

# Per-component breakers
vector_breaker = ComponentCircuitBreaker("vector_search", failure_threshold=5)
graph_breaker = ComponentCircuitBreaker("graph_traversal", failure_threshold=3)
llm_breaker = ComponentCircuitBreaker("llm_generation", failure_threshold=2)
```

**Graceful Degradation Mode:**
When circuit opens:
- Vector search: Return cached results or graph-only context
- Graph traversal: Return vector results only
- LLM: Return deterministic summary of context (no generation)

**Benefits:**
- Prevents cascading failures (one component doesn't crash the pipeline)
- Auto-recovery with exponential backoff
- Reduces load on failing services
- Improves MTTR (Mean Time To Recovery)

---

#### 2.2 Dependency Health Checks
```python
# Add to backend/app/api/health.py
from datetime import datetime, timedelta

class HealthChecker:
    async def check_vector_db(self) -> dict:
        """Verify FAISS index accessibility and performance."""
        try:
            start = time.time()
            faiss_store.retrieve("test query", top_k=1)
            latency_ms = (time.time() - start) * 1000
            return {
                "status": "healthy" if latency_ms < 500 else "degraded",
                "latency_ms": latency_ms,
                "index_size_mb": os.path.getsize(FAISS_PATH) / 1e6
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def check_graph_db(self) -> dict:
        """Verify Neo4j connectivity and query latency."""
        try:
            start = time.time()
            with graph_store.get_driver().session() as s:
                s.run("RETURN 1")
            latency_ms = (time.time() - start) * 1000
            return {"status": "healthy", "latency_ms": latency_ms}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def check_llm(self) -> dict:
        """Verify LLM provider API availability."""
        try:
            start = time.time()
            await llm_client.complete("ping", max_tokens=5)
            latency_ms = (time.time() - start) * 1000
            return {"status": "healthy", "latency_ms": latency_ms}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    @app.get("/health")
    async def health_check(self):
        """System-wide health report."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "healthy",  # computed from components
            "components": {
                "vector_db": await self.check_vector_db(),
                "graph_db": await self.check_graph_db(),
                "llm": await self.check_llm(),
            }
        }
```

**Endpoints:**
- `GET /health` → Quick status (< 100ms)
- `GET /health/detailed` → Full dependency check (< 5s)
- `GET /health/readiness` → Ready to serve traffic?
- `GET /health/liveness` → Process still running?

**Kubernetes Integration:**
```yaml
# kubernetes deployment
livenessProbe:
  httpGet:
    path: /health/liveness
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/readiness
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
```

---

#### 2.3 Chaos Engineering & Fault Injection
```python
# Add to backend/app/core/chaos.py (development/staging only)
import random

class ChaosMonkey:
    """Inject failures to test resilience."""
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
    
    async def inject_vector_failure(self):
        """Simulate vector DB timeout."""
        if self.enabled and random.random() < 0.1:  # 10% failure rate
            raise TimeoutError("Vector search timeout (chaos)")
    
    async def inject_graph_delay(self, base_latency: float):
        """Add random delays to graph queries."""
        if self.enabled:
            delay = random.uniform(0, 5)  # 0-5s jitter
            await asyncio.sleep(delay)
            return base_latency + delay

# Usage in retrieval.py
chaos = ChaosMonkey(enabled=get_settings().chaos_enabled)
await chaos.inject_vector_failure()
```

**Test Scenarios:**
1. Vector DB timeout → Falls back to graph + BM25
2. Graph DB connection reset → Falls back to vector search only
3. LLM rate limit → Rejects with retry-after header
4. Partial network partition → Degraded service, not total failure

---

### Priority & Effort
| Feature | Effort | Impact | Timeline |
|---------|--------|--------|----------|
| Circuit breakers | 3 days | High (prevents cascades) | Weeks 1-2 |
| Health checks | 2 days | High (k8s integration) | Week 1 |
| Chaos engineering | 3 days | Medium (testing) | Weeks 3-4 |

---

## 3. SECURITY & COMPLIANCE (Critical)

### Current State
- ✅ Cypher injection prevention
- ✅ Rate limiting for vision API
- ⚠️ **Gap**: No API authentication/authorization
- ⚠️ **Gap**: No audit logging for compliance
- ⚠️ **Gap**: No data encryption at rest/in transit
- ⚠️ **Gap**: No PII/data classification

### Recommendations

#### 3.1 API Authentication & Authorization
```python
# Add to backend/app/api/deps.py
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthCredential
import jwt

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthCredential = Security(security)):
    """Validate Bearer token or API key."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
        org_id = payload.get("org")
        if not user_id or not org_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"user_id": user_id, "org_id": org_id}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/query")
async def query_endpoint(
    query: QueryRequest,
    user: dict = Depends(verify_api_key),
    tracing: QueryTracingContext = Depends(get_tracing_context)
):
    """Protected endpoint requiring valid API key."""
    tracing.user_id = user["user_id"]
    tracing.org_id = user["org_id"]
    # ... rest of endpoint
```

**Auth Flows:**
1. **API Keys**: Simple Bearer tokens for programmatic access
2. **OAuth2**: For SaaS UI access
3. **SAML**: For enterprise SSO

**Tools:**
- **Auth0** (turnkey OAuth2/SAML)
- **Okta** (enterprise SAML/Kerberos)
- **Keycloak** (open-source identity server)
- **AWS Cognito** (if on AWS)

---

#### 3.2 Compliance & Audit Logging
```python
# Add to backend/app/core/compliance.py
from enum import Enum
import logging

class ComplianceEvent(str, Enum):
    API_KEY_CREATED = "api_key_created"
    API_KEY_DELETED = "api_key_deleted"
    USER_DATA_ACCESSED = "user_data_accessed"
    USER_DATA_EXPORTED = "user_data_exported"
    POLICY_VIOLATION = "policy_violation"
    AUTH_FAILURE = "auth_failure"
    GUARDRAIL_TRIGGERED = "guardrail_triggered"

class ComplianceLogger:
    def __init__(self):
        self.logger = logging.getLogger("compliance_audit")
        # Write to immutable log (append-only)
    
    def log_event(self, event: ComplianceEvent, **kwargs):
        """Log compliance-relevant events."""
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event.value,
            "user_id": kwargs.get("user_id"),
            "org_id": kwargs.get("org_id"),
            "resource": kwargs.get("resource"),
            "action": kwargs.get("action"),
            "result": kwargs.get("result"),  # success/failure
            "details": kwargs.get("details", {}),
        }
        self.logger.info(json.dumps(record))

compliance_logger = ComplianceLogger()

# Usage
compliance_logger.log_event(
    ComplianceEvent.USER_DATA_ACCESSED,
    user_id="user123",
    org_id="org456",
    resource="query_results",
    action="read",
    result="success",
    details={"query": "SELECT ...", "rows_returned": 100}
)
```

**Compliance Standards:**
- **GDPR**: Data retention, deletion, consent
- **HIPAA**: PHI encryption, access logs
- **SOC 2**: Availability, confidentiality, integrity
- **ISO 27001**: Information security management

**Audit Log Contents:**
- User identity, organization
- Data accessed (query, results)
- Timestamps (UTC)
- IP address
- API version
- Result (success/failure)
- Policy violations

---

#### 3.3 Data Encryption & PII Handling
```python
# Add to backend/app/core/encryption.py
from cryptography.fernet import Fernet
import hashlib

class PIIClassifier:
    """Detect and mask PII in queries/responses."""
    PII_PATTERNS = {
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    }
    
    @classmethod
    def mask_pii(cls, text: str) -> str:
        """Replace PII with masked values."""
        masked = text
        for pii_type, pattern in cls.PII_PATTERNS.items():
            masked = re.sub(pattern, f"[{pii_type.upper()}]", masked)
        return masked
    
    @classmethod
    def contains_pii(cls, text: str) -> bool:
        """Check if text contains PII."""
        for pattern in cls.PII_PATTERNS.values():
            if re.search(pattern, text):
                return True
        return False

class EncryptionManager:
    def __init__(self, key: str):
        self.cipher = Fernet(key)
    
    def encrypt_at_rest(self, plaintext: str) -> str:
        """Encrypt sensitive data before storing."""
        return self.cipher.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt sensitive data."""
        return self.cipher.decrypt(ciphertext.encode()).decode()

# Usage in retrieval pipeline
if PIIClassifier.contains_pii(query):
    masked_query = PIIClassifier.mask_pii(query)
    logger.warning(f"PII detected in query, logging masked version: {masked_query}")
```

**Data Classification:**
- **Public**: Product names, general info
- **Confidential**: User queries, results (access control)
- **Restricted**: API keys, credentials (encryption required)
- **PII**: Personally identifiable info (mask/encrypt)

---

### Priority & Effort
| Feature | Effort | Impact | Timeline |
|---------|--------|--------|----------|
| JWT auth + RBAC | 4 days | Critical (access control) | Weeks 1-2 |
| Compliance logging | 3 days | Critical (audit trail) | Weeks 2-3 |
| PII classification + encryption | 5 days | Critical (data privacy) | Weeks 3-4 |

---

## 4. SCALABILITY & PERFORMANCE (High Priority)

### Current State
- ✅ Batched embeddings (32-sample chunks)
- ✅ Connection pooling for Neo4j
- ⚠️ **Gap**: Single-node FAISS index (doesn't scale beyond ~10M vectors)
- ⚠️ **Gap**: No read replicas for graph DB
- ⚠️ **Gap**: No distributed caching (Redis)
- ⚠️ **Gap**: No request queuing or backpressure

### Recommendations

#### 4.1 Distributed Vector Search (Milvus / Weaviate)
**Current**: In-process FAISS index (~10M vector capacity)  
**Bottleneck**: Single node, no horizontal scaling, no multi-tenancy isolation

```python
# Migrate from faiss_store.py to milvus_client.py
from pymilvus import Collection, connections

class MilvusVectorStore:
    def __init__(self, host: str = "localhost", port: int = 19530):
        connections.connect("default", host=host, port=port)
        self.collection = Collection(name="documents")
    
    async def retrieve(self, embedding: np.ndarray, top_k: int = 5, 
                       filters: dict = None) -> List[dict]:
        """Search with multi-tenancy filters."""
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        
        # Filter by org_id for data isolation
        expr = f"org_id == '{filters['org_id']}'" if filters else ""
        
        results = self.collection.search(
            data=[embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr
        )
        return self._format_results(results)

# Benefits:
# - Horizontal scaling (add nodes as data grows)
# - Multi-tenant isolation (per-org indexes)
# - Advanced filtering (org_id, product_name, timestamp)
# - High availability (replication)
```

**Scaling Math:**
- **FAISS**: ~10M vectors / 384-dim = 15GB RAM (single node limit)
- **Milvus cluster**: 3+ nodes × 500M vectors = 1.5B vector capacity
- **Cost**: ~$200/month self-hosted vs $5k+/month for SaaS

**Migration Path:**
1. Deploy Milvus cluster (Week 1-2)
2. Run dual-write (FAISS + Milvus) for 2 weeks (Week 3)
3. Switch reads to Milvus, keep FAISS fallback (Week 4)
4. Decommission FAISS

---

#### 4.2 Graph Database Read Replicas
**Current**: Single Neo4j instance (single point of failure)  
**Bottleneck**: Read queries contend with write load; no geographic distribution

```python
# Multi-region setup with read replicas
class GraphStore:
    def __init__(self):
        self.primary = GraphDatabase.driver("bolt://neo4j-primary:7687")
        self.replicas = [
            GraphDatabase.driver(f"bolt://neo4j-replica-{i}:7687")
            for i in range(3)
        ]
    
    async def query(self, cypher: str):
        """Route read queries to replicas, writes to primary."""
        if "MATCH" in cypher and "RETURN" in cypher and "CREATE" not in cypher:
            # Read-only query
            replica = random.choice(self.replicas)
            return await self._execute(replica, cypher)
        else:
            # Write query
            return await self._execute(self.primary, cypher)

# Scaling:
# - Primary: 1 node (writes)
# - Replicas: 3+ nodes (reads, geographic distribution)
# - Replication lag: <100ms typically
# - Read throughput: 3-4x with 3 replicas
```

**Deployment:**
- **Docker Compose**: Dev/test (all 4 nodes on one machine)
- **Kubernetes**: Prod (primary + replicas on separate nodes)
- **AWS Neptune**: Managed alternative (handles replication, backups)

---

#### 4.3 Distributed Caching (Redis)
**Current**: In-process semantic cache (single-node only)  
**Problem**: Cache misses on process restart; no sharing across instances

```python
# Replace semantic_cache.py with redis_cache.py
import redis
import json

class RedisSemanticCache:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self.ttl = 86400 * 7  # 7 days
    
    async def check(self, query_embedding: np.ndarray) -> Tuple[Optional[dict], float]:
        """Check cache for similar queries across all processes."""
        # Quantize embedding to string for Redis key
        embedding_key = self._quantize_embedding(query_embedding)
        
        cached_response = self.redis.get(f"cache:{embedding_key}")
        if cached_response:
            return json.loads(cached_response), 0.5  # Redis latency ~0.5ms
        return None, 0.5
    
    async def store(self, query_embedding: np.ndarray, response: dict):
        """Store in shared cache."""
        embedding_key = self._quantize_embedding(query_embedding)
        self.redis.setex(
            f"cache:{embedding_key}",
            self.ttl,
            json.dumps(response)
        )

# Benefits:
# - Shared across all API instances
# - Survives process restarts
# - Fast (< 1ms latency)
# - Expirable (TTL-based cleanup)
# - Clustering support (Redis Cluster for HA)

# Scaling:
# - Single Redis: 100K ops/sec, 1-2GB memory
# - Redis Cluster: 1M ops/sec, 100GB+ memory
```

**Architecture:**
```
┌─────────────────────────────────────┐
│         Load Balancer               │
├─────────┬─────────┬─────────────────┤
│ API Pod │ API Pod │ API Pod         │
│  +Redis │  +Redis │  +Redis         │
│  cache  │  cache  │  cache          │
└────┬────┴────┬────┴────┬────────────┘
     │         │         │
     └────┬────┴────┬────┘
          │ Redis Cluster
          │ (3+ nodes)
          │
          ├─ Node 1: Cache data 1-N
          ├─ Node 2: Cache data N+1-2N
          └─ Node 3: Replicas of nodes 1-2
```

---

#### 4.4 Request Queuing & Backpressure
**Current**: Direct processing (can overload on traffic spikes)  
**Better**: Queue with priority, backpressure signals

```python
# Add to backend/app/core/queue.py
from fastapi import BackgroundTasks, HTTPException
import asyncio

class QueryQueue:
    def __init__(self, max_size: int = 1000):
        self.queue = asyncio.PriorityQueue(maxsize=max_size)
        self.active_queries = 0
        self.max_concurrent = 20
    
    async def enqueue(self, query_request: QueryRequest, priority: int = 0):
        """Add query to queue with priority."""
        if self.queue.full():
            raise HTTPException(
                status_code=429,
                detail="Queue full; retry in 1-2 seconds",
                headers={"Retry-After": "2"}
            )
        
        await self.queue.put((priority, query_request))
    
    async def process_queue(self):
        """Worker: process queue in priority order."""
        while True:
            priority, query_request = await self.queue.get()
            
            if self.active_queries >= self.max_concurrent:
                # Backpressure: requeue lower-priority queries
                if priority > 5:
                    await self.queue.put((priority + 1, query_request))
                    await asyncio.sleep(0.1)
                    continue
            
            self.active_queries += 1
            try:
                result = await process_query(query_request)
                return result
            finally:
                self.active_queries -= 1

# Usage
@app.post("/query")
async def query_endpoint(request: QueryRequest):
    if request.priority == "high":
        # Priority queue: high-priority queries get 10x weighting
        priority = 0
    else:
        priority = 10
    
    await query_queue.enqueue(request, priority)
```

**Benefits:**
- **Fairness**: FIFO + priority prevents starvation
- **Backpressure**: 429 signals to clients to retry later
- **Throttling**: Prevents resource exhaustion
- **SLA compliance**: Higher-priority queries finish faster

---

### Priority & Effort
| Feature | Effort | Impact | Timeline |
|---------|--------|--------|----------|
| Milvus migration | 10 days | Critical (enables scaling) | Weeks 2-4 |
| Graph read replicas | 5 days | High (HA + perf) | Weeks 1-2 |
| Redis distributed cache | 4 days | High (shared cache) | Weeks 2-3 |
| Request queuing | 3 days | Medium (fairness) | Week 4 |

---

## 5. QUALITY ASSURANCE & CONTINUOUS IMPROVEMENT

### Current State
- ✅ Comprehensive tracing for metrics
- ⚠️ **Gap**: No automated performance regression testing
- ⚠️ **Gap**: No A/B testing framework
- ⚠️ **Gap**: No automated data quality checks
- ⚠️ **Gap**: No model drift detection

### Recommendations

#### 5.1 Automated Performance Regression Testing
```python
# Add to backend/tests/test_performance_regressions.py
import pytest
from backend.app.core.tracing import QueryTracingContext

@pytest.mark.regression
async def test_query_latency_p99():
    """Ensure P99 latency doesn't regress."""
    latencies = []
    for _ in range(100):
        trace = await process_query("test query")
        latencies.append(trace.get_total_latency_ms())
    
    p99 = np.percentile(latencies, 99)
    assert p99 < 1000, f"P99 latency {p99}ms exceeds threshold 1000ms"

@pytest.mark.regression
async def test_cache_hit_rate_maintained():
    """Ensure cache hit rate doesn't degrade."""
    hits = 0
    for _ in range(100):
        # Reuse same queries to trigger cache
        trace = await process_query("What is Adani's revenue?")
        if trace.cache_metric and trace.cache_metric.hit:
            hits += 1
    
    hit_rate = hits / 100
    assert hit_rate > 0.3, f"Cache hit rate {hit_rate:.1%} below threshold 30%"

@pytest.mark.regression
async def test_token_efficiency_maintained():
    """Ensure context doesn't bloat."""
    tokens = []
    for query in ["revenue", "employees", "locations"]:
        trace = await process_query(f"How many {query}?")
        tokens.append(trace.llm_tokens_input)
    
    avg_tokens = sum(tokens) / len(tokens)
    assert avg_tokens < 1500, f"Avg tokens {avg_tokens} exceeds 1500"
```

**CI/CD Integration:**
- Run after every commit (baseline)
- Run nightly on staging (track trends)
- Block release if P99 latency increases > 10%

---

#### 5.2 A/B Testing Framework
```python
# Add to backend/app/core/experiments.py
from enum import Enum

class ExperimentVariant(str, Enum):
    CONTROL = "control"
    TREATMENT = "treatment"

class ABTesting:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def get_variant(self, user_id: str, experiment_name: str) -> ExperimentVariant:
        """Deterministic variant assignment (user_id → control/treatment)."""
        hash_value = int(hashlib.md5(f"{user_id}:{experiment_name}".encode()).hexdigest(), 16)
        return ExperimentVariant.TREATMENT if hash_value % 100 < 50 else ExperimentVariant.CONTROL
    
    async def log_result(self, experiment_name: str, user_id: str, 
                        variant: ExperimentVariant, metrics: dict):
        """Log experiment result for analysis."""
        event = {
            "experiment": experiment_name,
            "user_id": user_id,
            "variant": variant.value,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics,
        }
        await self.redis.rpush(f"experiment:{experiment_name}", json.dumps(event))

# Usage: Test new retrieval strategy
@app.post("/query")
async def query_endpoint(request: QueryRequest, ab_testing: ABTesting = Depends()):
    variant = ab_testing.get_variant(request.user_id, "hybrid_retrieval_v2")
    
    if variant == ExperimentVariant.TREATMENT:
        # New retrieval strategy
        result = await hybrid_retrieval_v2(request.query)
    else:
        # Baseline
        result = await traditional_rag(request.query)
    
    # Log metrics
    await ab_testing.log_result(
        "hybrid_retrieval_v2",
        request.user_id,
        variant,
        {
            "latency_ms": trace.get_total_latency_ms(),
            "citation_count": trace.citation_count,
            "quality_score": compute_quality_score(result),
        }
    )
```

**Experiments to Run:**
1. **Retrieval Strategy**: Graph-first vs Vector-first vs Hybrid
2. **Context Assembly**: Top-5 vs Top-10 documents
3. **LLM Model**: Llama 70B vs Llama 8B vs Qwen
4. **Caching Strategy**: Semantic similarity threshold (0.85 vs 0.95)

---

#### 5.3 Data Quality Monitoring
```python
# Add to backend/app/core/data_quality.py
class DataQualityMonitor:
    async def check_citation_accuracy(self, sample_size: int = 100) -> float:
        """Sample queries and verify citations."""
        correct = 0
        for _ in range(sample_size):
            result = await process_query(random_query())
            citations_valid = self._verify_citations(result)
            if citations_valid:
                correct += 1
        return correct / sample_size
    
    async def check_hallucination_rate(self, sample_size: int = 100) -> float:
        """Detect if LLM generates false facts."""
        hallucinations = 0
        for _ in range(sample_size):
            result = await process_query(random_query())
            hallucinated = await self._detect_hallucinations(result)
            if hallucinated:
                hallucinations += 1
        return hallucinations / sample_size
    
    async def check_entity_coverage(self) -> dict:
        """Ensure NER catches all important entities."""
        return {
            "layer_a_entities_avg": 2.5,  # rule-based NER
            "layer_b_entities_avg": 1.8,  # ML-based NER
            "missed_entities_sample": [...]  # manual review
        }

# Schedule checks (cron job)
@scheduler.scheduled_job('cron', hour=3)  # Run nightly at 3 AM
async def nightly_quality_check():
    monitor = DataQualityMonitor()
    citation_acc = await monitor.check_citation_accuracy()
    hallucination_rate = await monitor.check_hallucination_rate()
    
    logger.info(f"Citation accuracy: {citation_acc:.1%}")
    logger.info(f"Hallucination rate: {hallucination_rate:.1%}")
    
    # Alert if metrics degrade
    if citation_acc < 0.95:
        send_alert("Citation accuracy dropped below 95%")
```

---

#### 5.4 Model Drift & Performance Tracking
```python
# Add to backend/app/core/model_monitoring.py
class ModelMonitor:
    async def track_embedding_drift(self):
        """Monitor if embedding model quality degrades."""
        # Compare recent embeddings vs baseline
        baseline_dist = load_baseline_distribution()  # Saved on model deploy
        recent_embeddings = await get_recent_embeddings(hours=24)
        
        current_dist = np.mean(recent_embeddings, axis=0)
        drift_score = scipy.spatial.distance.cosine(baseline_dist, current_dist)
        
        if drift_score > 0.05:
            logger.warning(f"Embedding model drift detected: {drift_score:.3f}")
            send_alert("Embedding model drift may require retraining")
    
    async def track_llm_token_inflation(self):
        """Monitor if LLM token usage grows unexpectedly."""
        daily_tokens = {}
        for day in range(30):
            date = datetime.utcnow() - timedelta(days=day)
            daily_tokens[date] = sum(t.llm_tokens_input for t in get_traces(date))
        
        trend = np.polyfit(range(30), list(daily_tokens.values()), 1)[0]
        if trend > 100:  # Tokens/day increasing by > 100
            logger.warning(f"Token inflation trend: +{trend:.0f} tokens/day")

# Run on schedule
@scheduler.scheduled_job('cron', hour=2)
async def nightly_model_monitoring():
    monitor = ModelMonitor()
    await monitor.track_embedding_drift()
    await monitor.track_llm_token_inflation()
```

---

### Priority & Effort
| Feature | Effort | Impact | Timeline |
|---------|--------|--------|----------|
| Regression testing | 2 days | High (prevents degradation) | Week 1 |
| A/B testing framework | 3 days | High (continuous improvement) | Week 2 |
| Data quality monitoring | 3 days | Medium (quality assurance) | Weeks 2-3 |
| Model drift tracking | 2 days | Medium (long-term health) | Week 3 |

---

## 6. OPERATIONAL EXCELLENCE

### Current State
- ✅ Feature flags (query engine, canary routing)
- ⚠️ **Gap**: No deployment automation
- ⚠️ **Gap**: No runbooks or playbooks
- ⚠️ **Gap**: No incident response procedure
- ⚠️ **Gap**: No capacity planning

### Recommendations

#### 6.1 GitOps Deployment Pipeline
```yaml
# Add to .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          pytest backend/tests/ -v --cov
          pytest backend/tests/test_performance_regressions.py -v
  
  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build Docker image
        run: docker build -t api:${{ github.sha }} .
      - name: Push to registry
        run: docker push registry.example.com/api:${{ github.sha }}
  
  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging
        run: |
          kubectl set image deployment/api api=registry.example.com/api:${{ github.sha }} -n staging
          kubectl rollout status deployment/api -n staging
      
      - name: Run smoke tests
        run: pytest backend/tests/smoke_tests.py -v
      
      - name: Canary 10% to production
        run: |
          kubectl set image deployment/api api=registry.example.com/api:${{ github.sha }} -n prod
          kubectl patch service api -p '{"spec":{"selector":{"version":"canary"}}}'
      
      - name: Monitor canary metrics
        run: python scripts/monitor_canary.py --duration 5m --error-threshold 0.1%
      
      - name: Promote to 100% if healthy
        if: success()
        run: kubectl patch service api -p '{"spec":{"selector":{"version":"stable"}}}'
```

**Deployment Strategy:**
- **Staging**: Full deployment, run integration tests
- **Canary (10%)**: New version to 10% of traffic, monitor error rate
- **Rollout (100%)**: If canary healthy for 5 min, roll out to all traffic
- **Rollback (< 1s)**: If canary error rate > 0.1%, auto-rollback

---

#### 6.2 Runbooks & Incident Playbooks
```markdown
# Runbook: High Query Latency

## Symptoms
- P99 latency > 1.5s
- User complaints about slow responses

## Diagnosis

1. Check component breakdown in Grafana
   - Is LLM slow? Check Groq status page, token count
   - Is vector search slow? Check FAISS index size, query load
   - Is graph slow? Check Neo4j query log

2. Check error rates
   ```bash
   kubectl logs deployment/api --tail=100 | grep ERROR
   ```

3. Check resource utilization
   ```bash
   kubectl top pods -n prod | grep api
   ```

## Mitigation

### Option A: LLM is slow (common)
- Check Groq rate limit: `curl https://api.groq.com/status`
- Enable LLM fallback to cheaper model:
  ```bash
  kubectl set env deployment/api LLM_MODEL="llama-3.1-8b-instant" -n prod
  ```
- Monitor latency for 5 min, rollback if needed

### Option B: Vector search slow (growing corpus)
- Check FAISS index size:
  ```bash
  du -sh data/faiss/
  ```
- If > 30GB, trigger manual index rebuild:
  ```bash
  python scripts/rebuild_faiss_index.py --background
  ```
- Use temporary Milvus fallback during rebuild

### Option C: Graph slow (many traversal hops)
- Check query patterns:
  ```bash
  kubectl logs deployment/api | grep "traversal_hops" | sort | uniq -c
  ```
- If many deep queries, disable graph for this query type:
  ```bash
  kubectl set env deployment/api GRAPH_ENABLED="false" -n prod
  ```

## Escalation

- **If latency doesn't improve in 5 min**: Page on-call engineer
- **If error rate rises above 1%**: Auto-rollback to previous version
```

**Other Important Playbooks:**
- High memory usage (vector index too large)
- Database connection exhaustion (graph DB pool full)
- Cache eviction storms (Redis full)
- Deployment rollback procedure

---

#### 6.3 Capacity Planning & Cost Optimization
```python
# Add to backend/scripts/capacity_planner.py
import numpy as np
from datetime import datetime, timedelta

class CapacityPlanner:
    async def forecast_growth(self, days: int = 90):
        """Forecast resource needs for next N days."""
        # Get historical metrics
        qps_history = await get_historical_metric("requests_per_second", days=90)
        token_history = await get_historical_metric("llm_tokens_per_sec", days=90)
        vector_index_size = await get_historical_metric("vector_index_size_gb", days=90)
        
        # Fit trends
        qps_trend = np.polyfit(range(90), qps_history, 1)
        tokens_trend = np.polyfit(range(90), token_history, 1)
        index_trend = np.polyfit(range(90), vector_index_size, 1)
        
        # Forecast
        qps_90d = qps_history[-1] + qps_trend[0] * days
        tokens_90d = token_history[-1] + tokens_trend[0] * days
        index_90d = vector_index_size[-1] + index_trend[0] * days
        
        return {
            "qps_forecast": qps_90d,
            "tokens_per_sec_forecast": tokens_90d,
            "vector_index_size_gb": index_90d,
            "recommendation": self._resource_recommendation(qps_90d, tokens_90d, index_90d)
        }
    
    def _resource_recommendation(self, qps: float, tokens: float, index_size: float) -> dict:
        """Recommend infrastructure changes."""
        recs = []
        
        # API pods: 1 pod = 50 QPS
        api_pods_needed = max(3, int(np.ceil(qps / 50)))
        if api_pods_needed > current_pods():
            recs.append(f"Scale API to {api_pods_needed} pods (+{api_pods_needed - current_pods()})")
        
        # LLM tokens: $0.0001 / 1K tokens
        monthly_cost = (tokens * 86400 * 30) * 0.0001 / 1000
        if monthly_cost > 10000:
            recs.append(f"LLM cost ${monthly_cost:.0f}/mo — consider cheaper model")
        
        # Vector index: migrate from FAISS to Milvus at 50M vectors
        if index_size > 50:
            recs.append(f"Vector index {index_size:.0f}GB — migrate to Milvus cluster")
        
        return {"actions": recs, "estimated_cost_monthly": monthly_cost}

# Run weekly capacity check
@scheduler.scheduled_job('cron', day_of_week=0, hour=9)  # Sunday 9 AM
async def weekly_capacity_review():
    planner = CapacityPlanner()
    forecast = await planner.forecast_growth(days=90)
    
    print(f"90-Day Forecast:")
    print(f"  QPS: {forecast['qps_forecast']:.0f}")
    print(f"  Token cost/mo: ${forecast['estimated_cost_monthly']:.0f}")
    for action in forecast['recommendation']['actions']:
        print(f"  - {action}")
```

**Cost Optimization Levers:**
1. **Cheaper LLM model** for simple queries: llama-3.1-8b vs llama-3.1-70b
2. **Cache hit rate**: Current 40% → Target 60% (saves 6hrs/day LLM)
3. **Token efficiency**: Context 35.5% → Target 50% (fewer tokens/query)
4. **Batch processing**: Off-peak aggregation jobs at low cost

---

### Priority & Effort
| Feature | Effort | Impact | Timeline |
|---------|--------|--------|----------|
| GitOps CI/CD | 5 days | Critical (safe deployments) | Weeks 1-2 |
| Runbooks | 3 days | High (incident response) | Weeks 2-3 |
| Capacity planning | 2 days | Medium (cost optimization) | Week 3 |

---

## IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Weeks 1-4)
**Goal**: Production readiness basics
- [ ] OpenTelemetry integration (Week 1)
- [ ] Prometheus/Grafana dashboards (Week 2)
- [ ] Circuit breakers + health checks (Week 1)
- [ ] JWT authentication (Week 2)
- [ ] Compliance audit logging (Week 3)
- [ ] GitOps CI/CD pipeline (Weeks 1-2)

**Cost**: ~$2k/month (tools) + 80 eng days

**Outcome**: Observable, resilient, compliant system

---

### Phase 2: Scale (Weeks 5-10)
**Goal**: Support 10-100x traffic growth
- [ ] Milvus vector search (Weeks 2-4)
- [ ] Redis distributed cache (Week 3)
- [ ] Graph DB read replicas (Week 1-2)
- [ ] Request queuing (Week 4)
- [ ] Regression testing (Week 1)
- [ ] A/B testing framework (Week 2)

**Cost**: ~$5k/month (infra) + 60 eng days

**Outcome**: Horizontally scalable, measurable improvement

---

### Phase 3: Excellence (Weeks 11-16)
**Goal**: Industry-grade operations
- [ ] Data quality monitoring (Weeks 1-2)
- [ ] Model drift detection (Week 2)
- [ ] Capacity planning automation (Week 1)
- [ ] Advanced runbooks (Week 2)
- [ ] SLA monitoring + alerting (Week 1)
- [ ] Cost optimization automation (Week 3)

**Cost**: ~$3k/month (tools) + 40 eng days

**Outcome**: Autonomous, self-optimizing system

---

## SUMMARY: Quick Win vs Strategic

| Priority | Feature | Timeline | Impact |
|----------|---------|----------|--------|
| **Quick Win** | OpenTelemetry + Grafana | 2 weeks | Visibility into system |
| **Quick Win** | JWT auth + audit logging | 2 weeks | Compliance ready |
| **Strategic** | Milvus + Redis | 4 weeks | 10-100x scaling |
| **Strategic** | Multi-provider resilience | 2 weeks | 99.9% uptime |
| **Strategic** | Data quality monitoring | 3 weeks | Continuous improvement |

**Total Effort**: ~180 engineering days over 16 weeks (1-2 FTE + contractors)  
**Total Cost**: ~$100k infrastructure + tooling per year  
**Expected Outcome**: Industry-grade SaaS platform supporting millions of queries/day
