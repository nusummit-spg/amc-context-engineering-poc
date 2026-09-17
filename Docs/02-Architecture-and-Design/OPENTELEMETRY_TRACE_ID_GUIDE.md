# OpenTelemetry Trace ID: Complete Guide

**What is it? Why is it in query_evidence? How to use it?**

---

## TL;DR

| Question | Answer |
|----------|--------|
| **What is it?** | A unique identifier (e.g., `int_5356a3041697`) that tracks a single request's journey through all microservices |
| **Why in query_evidence?** | To link query response to logs, spans, and performance metrics for end-to-end debugging |
| **Format?** | 32-character hex string or custom format (e.g., `int_5356a3041697`) |
| **Use case?** | "Show me everything that happened when user asked about liquid funds" → query by request_id |
| **Who uses it?** | DevOps, SRE, performance engineers for debugging production issues |

---

## Part 1: What is OpenTelemetry?

**OpenTelemetry** is an open-source standard for generating, collecting, and exporting telemetry data (traces, metrics, logs) from distributed systems.

It's maintained by the [Cloud Native Computing Foundation (CNCF)](https://www.cncf.io/) and supported by major vendors: DataDog, New Relic, Jaeger, Prometheus, etc.

### Key Components of OpenTelemetry

```
┌─────────────────────────────────────────────────────────┐
│ Application Request (e.g., GET /api/query)              │
└──────────┬──────────────────────────────────────────────┘
           │ (generated once at entry point)
           ▼
┌─────────────────────────────────────────────────────────┐
│ TRACE (Unique ID: trace-id-12345)                       │
│ └─ Span 1: API Router (1ms)                             │
│    └─ Span 1.1: Intent Classification (50ms)            │
│    └─ Span 1.2: Entity Extraction (30ms)                │
│    └─ Span 1.3: Neo4j Query (150ms)                     │
│       └─ Span 1.3.1: Connection Pool (5ms)              │
│       └─ Span 1.3.2: Cypher Execution (145ms)           │
│    └─ Span 1.4: LLM Synthesis (2000ms)                  │
│       └─ Span 1.4.1: Groq API Call (1950ms)             │
│       └─ Span 1.4.2: Response Parsing (50ms)            │
│ └─ Span 2: Database Logging (5ms)                       │
│ └─ Span 3: Response Serialization (10ms)                │
└─────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────┐
│ Exporter sends to: Jaeger, Datadog, or local logs       │
│ Timeline visualization available at: http://localhost:16686
└─────────────────────────────────────────────────────────┘
```

---

## Part 2: What is a Trace ID?

A **Trace ID** is a **unique identifier** that follows a request across:
- Multiple microservices
- Database queries
- API calls
- Cache operations
- Message queues

### Trace ID Format

```
Standard (W3C Trace Context spec):
┌─────────────────────┬──────────────────────┐
│ Trace ID            │ Span ID              │
├─────────────────────┼──────────────────────┤
│ 4bf92f3577b34da6a3ce929d0e0e4736 │ 00f067aa0ba902b7   │
│ (32 hex chars)      │ (16 hex chars)       │
└─────────────────────┴──────────────────────┘

Context Engineering Platform:
┌──────────────────────┐
│ request_id (custom)  │
├──────────────────────┤
│ int_5356a3041697     │
│ resp_b2dc46ac2da2    │
└──────────────────────┘
```

### Example from Your System

From `chat_evidence_83dc882e-6940-45eb-b767-740f77a12afc.json`:

```json
{
  "response_id": "resp_b2dc46ac2da2",
  "session_id": "83dc882e-6940-45eb-b767-740f77a12afc",
  "request_id": "int_5356a3041697",  ← THIS IS THE TRACE ID
  "query_text": "Can you give me the characteristics of the liquid fund",
  "latency_ms": 6485,
  "retrieval_latency_ms": 5555,
  "synthesis_latency_ms": 930
}
```

**Breakdown**:
- `request_id`: Unique identifier for this request's entire journey
- `response_id`: Specific response object ID
- `session_id`: Chat session grouping
- Together they form a complete audit trail

---

## Part 3: How Trace ID Works in Your System

### End-to-End Request Flow

```
User Query: "Tell me about liquid funds"
│
├─ Request enters API @ FastAPI (t=0ms)
│  └─ Generate request_id = "int_5356a3041697"
│  └─ Create root span
│
├─ Intent Classification (t=0-50ms)
│  └─ Span: "query_classification"
│  └─ Parent: root span
│  └─ Result: "fund_performance"
│
├─ Entity Extraction (t=50-80ms)
│  └─ Span: "entity_extraction"
│  └─ Entities: ["liquid fund"]
│
├─ Neo4j Graph Query (t=80-230ms)
│  └─ Span: "neo4j_traversal"
│  ├─ Span: "neo4j_connect" (t=80-85ms)
│  └─ Span: "cypher_execute" (t=85-230ms)
│     └─ Query: "MATCH (f:Fund {name:'Liquid Fund'}) RETURN f"
│
├─ FAISS Vector Search (t=230-350ms)
│  └─ Span: "vector_search"
│  └─ Top-K: 8 chunks retrieved
│
├─ LLM Synthesis (t=350-2350ms)
│  └─ Span: "llm_synthesis"
│  ├─ Span: "groq_api_call" (t=350-2300ms)
│  └─ Span: "response_parse" (t=2300-2350ms)
│
├─ Query Evidence Logging (t=2350-2360ms)
│  └─ Span: "store_query_evidence"
│  └─ Insert to query_evidence table
│     {
│       "response_id": "resp_b2dc46ac2da2",
│       "request_id": "int_5356a3041697",  ← Trace continues here
│       "assembled_context_json": {...},
│       "synthesis_output_json": {...},
│       "latency_ms": 2360
│     }
│
└─ Return Response to User (t=2360ms)
   └─ Response includes request_id in header: "X-Request-ID: int_5356a3041697"
```

---

## Part 4: request_id Field in query_evidence

### Column Definition

```sql
CREATE TABLE query_evidence (
    response_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    request_id TEXT,  ← OpenTelemetry trace ID
    query_text TEXT NOT NULL,
    assembled_context_json TEXT NOT NULL,
    synthesis_output_json TEXT NOT NULL,
    latency_ms INTEGER,
    ...
);
```

### Why Store request_id in query_evidence?

**Use Case 1: Debugging a Slow Query**

```bash
# In production, query evidence shows latency_ms = 5555ms (5+ seconds)
# But why is it slow?

# Trace the request_id through logs
curl http://your-jaeger-backend:16686/search?service=api&traceID=int_5356a3041697

# Jaeger shows:
# - Intent Classification: 50ms ✅
# - Entity Extraction: 30ms ✅
# - Neo4j Query: 150ms ✅
# - FAISS Vector Search: 2000ms ⚠️ (THIS IS THE BOTTLENECK!)
#   - Disk I/O: 1800ms
#   - KNN computation: 200ms
# - LLM Synthesis: 930ms ✅

# Action: Optimize FAISS index or upgrade hardware
```

**Use Case 2: Investigating Incorrect Answer**

```bash
# User reports: "The answer was wrong!"
# You have response_id: "resp_b2dc46ac2da2"

# Step 1: Query query_evidence table
SELECT * FROM query_evidence WHERE response_id = 'resp_b2dc46ac2da2';

# Step 2: Get request_id
request_id = 'int_5356a3041697'

# Step 3: Trace in Jaeger
curl http://jaeger:16686/search?traceID=int_5356a3041697

# Step 4: Inspect each span
# - Was entity extraction correct? (Liquid Fund ✅)
# - Was Neo4j query correct? (Schema traversal ✅)
# - Was vector search returning right chunks? (Check similarity scores)
# - Did LLM hallucinate? (Compare answer to context)

# Action: Identify which component failed, add audit info for ML training
```

**Use Case 3: Compliance Audit**

```bash
# Requirement: "Show all traces for fund "Liquid Fund" from Sept 1-7"

# Query:
SELECT
  qe.response_id,
  qe.request_id,
  qe.query_text,
  qe.created_at,
  qe.latency_ms,
  qe.confidence_level,
  rf.selected_categories,
  rf.free_text
FROM query_evidence qe
LEFT JOIN response_feedback rf ON qe.response_id = rf.response_id
WHERE qe.query_text LIKE '%Liquid Fund%'
  AND DATE(qe.created_at) BETWEEN '2026-09-01' AND '2026-09-07'
ORDER BY qe.created_at DESC;

# Result set includes:
# - request_id for full trace reconstruction
# - Latency, confidence, feedback
# - Can export to PDF as evidence pack with links to Jaeger traces
```

---

## Part 5: Distributed Tracing Architecture

### Your System's Tracing Setup

```
┌─────────────────────────────────────────────────────────────┐
│ FastAPI Backend (app/main.py)                               │
│                                                             │
│ @app.middleware("http")                                    │
│ async def add_process_time_header(request, call_next):     │
│   request_id = str(uuid.uuid4())  ← Generate trace ID      │
│   context.set_trace_id(request_id)                         │
│   response = await call_next(request)                      │
│   response.headers["X-Request-ID"] = request_id            │
│   return response                                           │
└───────────┬─────────────────────────────────────────────────┘
            │
        ┌───▼────────────────────────────────────────────┐
        │ All downstream operations inherit trace_id      │
        │                                                 │
        │ ├─ app/retrieval/query_engine.py               │
        │ │  └─ Uses context.get_trace_id()              │
        │ ├─ app/retrieval/synthesizer.py                │
        │ │  └─ Logs spans with trace_id                 │
        │ ├─ Neo4j Driver                                │
        │ │  └─ Custom span: "neo4j_query"               │
        │ ├─ Groq API Client                             │
        │ │  └─ Custom span: "llm_api_call"              │
        │ └─ query_evidence_recorder.py                  │
        │    └─ INSERT with request_id                   │
        └────────────┬──────────────────────────────────┘
                     │
        ┌────────────▼──────────────────────────┐
        │ Exporter (OpenTelemetry Protocol)      │
        │                                        │
        │ Sends traces to:                       │
        │ - Jaeger (visualization)               │
        │ - CloudWatch Logs (production)         │
        │ - Local file (development)             │
        └────────────┬──────────────────────────┘
                     │
        ┌────────────▼──────────────────────────┐
        │ Trace Backend                          │
        │                                        │
        │ Jaeger UI:                             │
        │ http://localhost:16686                │
        │ ?traceID=int_5356a3041697             │
        │                                        │
        │ - Full timeline visualization          │
        │ - Span dependencies                    │
        │ - Performance analysis                 │
        │ - Error tracking                       │
        └────────────────────────────────────────┘
```

---

## Part 6: Data Flow: request_id Through Your System

### Step 1: Request Arrives

```http
POST /api/query HTTP/1.1
Content-Type: application/json

{
  "query": "Tell me about liquid funds",
  "mode": "contextgraph"
}
```

### Step 2: Middleware Generates request_id

```python
# app/main.py
@app.middleware("http")
async def add_trace_middleware(request: Request, call_next):
    request_id = f"int_{secrets.token_hex(6)}"  # int_5356a3041697
    request.state.request_id = request_id
    
    # Attach to all logs & spans downstream
    contextvars.set("request_id", request_id)
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

### Step 3: Query Engine Creates Spans

```python
# app/retrieval/query_engine.py
async def query(self, query_text: str) -> QueryResponse:
    request_id = contextvars.get("request_id")
    
    with tracer.start_as_current_span("query_execution") as span:
        span.set_attribute("request_id", request_id)
        span.set_attribute("query_text", query_text[:100])
        
        # Span 1: Classification
        with tracer.start_as_current_span("intent_classification"):
            intent = await classifier.classify(query_text)
        
        # Span 2: Entity Extraction
        with tracer.start_as_current_span("entity_extraction"):
            entities = await extractor.extract(query_text)
        
        # Span 3: Neo4j Traversal
        with tracer.start_as_current_span("neo4j_traversal"):
            graph_facts = await neo4j_client.traverse(entities)
        
        # Span 4: Vector Search
        with tracer.start_as_current_span("vector_search"):
            chunks = await faiss_index.search(query_text)
        
        # Span 5: LLM Synthesis
        with tracer.start_as_current_span("llm_synthesis"):
            answer = await llm_client.synthesize(query_text, context)
        
        return QueryResponse(...)
```

### Step 4: Query Evidence Recorded with request_id

```python
# app/retrieval/query_evidence_recorder.py
async def record_synthesis(
    self,
    response_id: str,
    query: str,
    context: AssembledContext,
    synthesis: SynthesisOutput,
    latency_ms: int,
    request_id: str  ← Pass trace ID here
):
    request_id = contextvars.get("request_id")  # or pass as param
    
    insert_sql = """
    INSERT INTO query_evidence (
        response_id,
        request_id,  ← Store trace ID
        query_text,
        assembled_context_json,
        synthesis_output_json,
        latency_ms,
        created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    
    self.db.execute(insert_sql, [
        response_id,
        request_id,  ← NOW IT'S IN THE DATABASE
        query,
        json.dumps(context),
        json.dumps(synthesis),
        latency_ms,
        datetime.now().isoformat()
    ])
```

### Step 5: Response Sent with Trace ID in Header

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: int_5356a3041697  ← Client can log this

{
  "response_id": "resp_b2dc46ac2da2",
  "answer": "Liquid fund investments in debt...",
  "citations": [...],
  "latency_ms": 6485
}
```

---

## Part 7: Querying by request_id

### SQL Queries

**Get all operations for a trace**:
```sql
SELECT
  response_id,
  request_id,
  query_text,
  latency_ms,
  confidence_level,
  created_at
FROM query_evidence
WHERE request_id = 'int_5356a3041697';
```

**Correlate with feedback**:
```sql
SELECT
  qe.response_id,
  qe.request_id,
  qe.query_text,
  qe.latency_ms,
  rf.actor_role,
  rf.selected_categories,
  rf.free_text
FROM query_evidence qe
LEFT JOIN response_feedback rf ON qe.response_id = rf.response_id
WHERE qe.request_id = 'int_5356a3041697';
```

**Performance analysis by trace**:
```sql
SELECT
  request_id,
  COUNT(*) as query_count,
  AVG(latency_ms) as avg_latency_ms,
  MAX(latency_ms) as p_max_latency_ms,
  AVG(CAST(json_extract(synthesis_output_json, '$.confidence') AS REAL)) as avg_confidence
FROM query_evidence
WHERE created_at >= date('now', '-7 days')
GROUP BY request_id
ORDER BY avg_latency_ms DESC
LIMIT 20;
```

### Jaeger Trace Visualization

```bash
# CLI to fetch trace
curl -s "http://jaeger:16686/api/traces?service=api&traceID=int_5356a3041697" | jq .

# Or visit UI
http://jaeger:16686/?traceID=int_5356a3041697

# Output shows:
# Timeline:
#   ├─ intent_classification (50ms)
#   ├─ entity_extraction (30ms)
#   ├─ neo4j_traversal (150ms)
#   ├─ vector_search (2000ms)  ← Shows memory, disk I/O details
#   ├─ llm_synthesis (930ms)
#   └─ store_query_evidence (10ms)
#
# Total: 3170ms
```

---

## Part 8: Best Practices

### 1. Always Propagate request_id

```python
# ❌ DON'T: Create new ID in nested function
def nested_operation():
    new_id = generate_id()  # Wrong! Creates new trace
    
# ✅ DO: Use context variable
def nested_operation():
    request_id = contextvars.get("request_id")
    # Reuse same request_id for entire request lifetime
```

### 2. Store request_id in Every Audit Table

```sql
-- Good schema design
CREATE TABLE violations (
    violation_id TEXT PRIMARY KEY,
    request_id TEXT,  ← Link to trace
    audit_id TEXT,
    ...
    FOREIGN KEY(request_id) REFERENCES query_evidence(request_id)
);

CREATE TABLE response_feedback (
    feedback_id TEXT PRIMARY KEY,
    request_id TEXT,  ← Link to trace
    response_id TEXT,
    ...
    FOREIGN KEY(request_id) REFERENCES query_evidence(request_id)
);
```

### 3. Include request_id in Error Responses

```python
# ✅ DO: Return request_id to client for support
@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    request_id = request.state.get("request_id")
    logger.error(f"Error in request {request_id}: {exc}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "request_id": request_id,  ← Client reports this
            "message": "Contact support with this request_id"
        }
    )

# Client error message:
# "An error occurred. Please contact support with code: int_5356a3041697"
```

### 4. Set Sampling Rate for High-Traffic Systems

```python
# Don't trace EVERY request in production (too much overhead)
# Trace 10% by default, 100% on errors

from opentelemetry.sdk.trace.samplers import TraceIdRatioBased, ParentBasedSampler

sampler = ParentBasedSampler(
    root=TraceIdRatioBased(0.10),  # 10% normal, 100% if parent sampled
)

tracer_provider.add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)
```

### 5. Use request_id in Log Messages

```python
import logging
import contextvars

request_id_var = contextvars.ContextVar('request_id', default='no-trace')

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

logger = logging.getLogger(__name__)
logger.addFilter(RequestIdFilter())

# Log format includes request_id
logging.basicConfig(
    format='%(asctime)s - %(name)s - [%(request_id)s] - %(message)s'
)

# Logs now look like:
# 2026-09-08 14:31:01 - app.retrieval - [int_5356a3041697] - Starting query synthesis
# 2026-09-08 14:31:02 - app.retrieval - [int_5356a3041697] - Neo4j traversal complete in 150ms
```

---

## Part 9: Real-World Example: Debugging Slow Query

### Problem
User reports: "Query took 6.5 seconds, but usually it's <500ms"

### Investigation Steps

**Step 1: Get response_id from user**
```
User: "The request ID was int_5356a3041697"
```

**Step 2: Query database**
```sql
SELECT
  response_id,
  request_id,
  query_text,
  latency_ms,
  retrieval_latency_ms,
  synthesis_latency_ms,
  confidence_level
FROM query_evidence
WHERE request_id = 'int_5356a3041697';

-- Result:
-- response_id           | resp_b2dc46ac2da2
-- request_id            | int_5356a3041697
-- query_text            | Can you give me the characteristics of the liquid fund
-- latency_ms            | 6485
-- retrieval_latency_ms  | 5555  ← This is the bottleneck!
-- synthesis_latency_ms  | 930
-- confidence_level      | high
```

**Step 3: Check Jaeger for detailed breakdown**
```
Visit: http://jaeger:16686/?traceID=int_5356a3041697

Timeline view shows:
├─ intent_classification (50ms)
├─ entity_extraction (30ms)
├─ neo4j_traversal (150ms)
├─ vector_search (5000ms)  ← HERE'S THE PROBLEM!
│  ├─ faiss_load_index (100ms)
│  ├─ vector_encode (200ms)
│  ├─ knn_search (4500ms)  ← Disk read stall
│  └─ rerank (200ms)
└─ llm_synthesis (930ms)
```

**Step 4: Root Cause Analysis**
- FAISS KNN search took 4500ms (normally 200ms)
- Likely cause: Disk I/O stall, index not in memory cache
- Solution: Increase RAM, use SSD, or pre-load index

**Step 5: Implement Fix**
```python
# Before: Index loaded on-demand
self.faiss_index = None

# After: Pre-load in memory at startup
@app.on_event("startup")
async def startup():
    self.faiss_index = faiss.read_index("/indices/amc_master.index")
    # Pre-warm cache by doing 1-10 dummy queries
    _ = self.faiss_index.search(np.random.randn(10, 384).astype('float32'), k=8)
```

**Step 6: Verify Fix**
```sql
SELECT
  AVG(latency_ms),
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms),
  PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms)
FROM query_evidence
WHERE created_at >= date('now', '-1 day')
  AND serving_engine = 'legacy-stream';

-- Before:  avg=3000ms, p95=5000ms, p99=6500ms
-- After:   avg=400ms, p95=600ms, p99=800ms ✅
```

---

## Part 10: Integration Checklist

### Implementing request_id in Your System

- [ ] **Middleware**: Add `request_id` generation in FastAPI middleware
- [ ] **Schema**: Ensure `query_evidence.request_id` column exists (already there ✅)
- [ ] **Recording**: Update `QueryEvidenceRecorder` to pass `request_id`
- [ ] **Context Propagation**: Use `contextvars` to pass `request_id` through async calls
- [ ] **Logging**: Include `request_id` in all log messages
- [ ] **Error Handling**: Return `request_id` in error responses
- [ ] **Jaeger Setup**: Deploy Jaeger collector and UI for trace visualization
- [ ] **Audit Tables**: Add `request_id` FK to `violations`, `response_feedback` tables
- [ ] **Documentation**: Teach team how to use Jaeger for debugging
- [ ] **Dashboards**: Create Grafana dashboards querying latency by `request_id`

---

## Part 11: Summary Table

| Aspect | Details |
|--------|---------|
| **What is it?** | Unique identifier tracking a request across all services |
| **Format** | `int_5356a3041697` (custom) or 32-char hex (standard) |
| **Where stored?** | `query_evidence.request_id`, logs, Jaeger backend |
| **Lifetime** | Entire request (from entry to response) |
| **Who creates it?** | FastAPI middleware at request entry point |
| **Who uses it?** | DevOps, SRE, engineers debugging issues |
| **Key use cases** | Performance debugging, error investigation, compliance audit |
| **Retention** | Store in DB for 7 years (SEBI requirement) |
| **Performance impact** | Negligible (~1-2ms overhead per request) |
| **Standards** | W3C Trace Context (standard), custom in your system |
| **Tools** | Jaeger (visualization), Datadog, New Relic (backends) |

---

## Additional Resources

- [OpenTelemetry Official Docs](https://opentelemetry.io/docs/concepts/signals/traces/)
- [W3C Trace Context Spec](https://www.w3.org/TR/trace-context/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [Distributed Tracing Guide](https://clickhouse.com/resources/engineering/what-is-distributed-tracing)

---

**Bottom Line**: `request_id` is your golden thread through production. When something goes wrong, use it to trace exactly what happened. It's like a flight recorder for distributed systems.

