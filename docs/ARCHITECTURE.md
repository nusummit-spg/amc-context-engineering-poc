# Architecture Overview

**AMC Context Engineering Platform** - Enterprise RAG System Architecture

---

## System Overview

The platform is a hybrid Retrieval-Augmented Generation (RAG) system that combines:
- **Knowledge Graphs** (Neo4j) - Structured relationships
- **Vector Search** (FAISS) - Semantic similarity
- **LLM Synthesis** (Groq) - Natural language generation

### Design Principles

1. **Hybrid Retrieval** - Combine graph precision with vector flexibility
2. **Multi-turn Context** - Maintain conversation history
3. **Passive Learning** - Learn from user feedback without explicit labeling
4. **Production-Grade** - Sub-second response times, high availability
5. **Compliance-First** - SEBI regulatory compliance built-in

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend Layer (React)                    │
│  • Chat Interface    • Compare View    • Admin Panel        │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/REST + SSE
┌────────────────────────▼────────────────────────────────────┐
│                   API Layer (FastAPI)                        │
│  • /api/query        • /api/chat       • /api/admin         │
│  • /api/feedback     • /api/compliance • /api/governance    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│              Core Processing Layer (V2 Engine)               │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │        Retrieval Orchestrator                       │   │
│  │  ┌──────────────────────────────────────────────┐  │   │
│  │  │ 1. Intent Classification                     │  │   │
│  │  │ 2. Entity Resolution                         │  │   │
│  │  │ 3. Query Planning & Decomposition            │  │   │
│  │  │ 4. Hybrid Retrieval (Graph + Vector)         │  │   │
│  │  │ 5. Context Assembly                          │  │   │
│  │  │ 6. LLM Synthesis                             │  │   │
│  │  │ 7. Quality Assessment                        │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  Supporting Services:                                        │
│  • Semantic Cache    • Feedback Manager                     │
│  • Compliance Engine • Document Ingestion                   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     Data Layer                               │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   Neo4j      │  │    FAISS     │  │     SQLite      │  │
│  │  Knowledge   │  │   Vector     │  │   Application   │  │
│  │    Graph     │  │   Indexes    │  │    Database     │  │
│  │              │  │              │  │                 │  │
│  │  • Entities  │  │  • Chunks    │  │  • Users        │  │
│  │  • Relations │  │  • Embeddings│  │  • Sessions     │  │
│  │  • Taxonomy  │  │  • Metadata  │  │  • Feedback     │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Frontend Layer

**Technology**: React 19 + Vite 8

**Components**:
- `ChatInterface.jsx` - Main conversation UI
- `CompareView.jsx` - Side-by-side comparison
- `AdminPanel.jsx` - User and document management
- `AnalyticsDashboard.jsx` - Query metrics

**Features**:
- Real-time streaming responses (SSE)
- Multi-turn conversation context
- Citation highlighting
- Graph visualization

---

### 2. API Layer

**Technology**: FastAPI 0.115+

**Key Endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/query` | POST | Single query execution |
| `/api/chat` | POST | Multi-turn conversation |
| `/api/sessions` | GET/POST | Session management |
| `/api/feedback` | POST | User feedback submission |
| `/api/admin/ingest` | POST | Document ingestion |
| `/api/compliance` | GET | Compliance rule check |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

**Authentication**:
- JWT-based token authentication
- User/tenant isolation
- Role-based access control (RBAC)

---

### 3. Retrieval Orchestrator (V2)

The heart of the RAG system. Orchestrates the entire query-to-answer pipeline.

#### 3.1 Intent Classification

```python
# Determines query type and extraction strategy
QueryIntent {
    query_type: "entity_lookup" | "comparison" | "compliance_check" | ...
    entities: ["Adani Enterprises", "FY25"]
    taxonomy: ["adani_corporate", "esg_sustainability"]
    confidence: 0.95
}
```

#### 3.2 Entity Resolution

```python
# Links mentions to canonical entities
"AEL" → Entity(name="Adani Enterprises", type="Issuer", id="...")
```

#### 3.3 Query Planning

```python
# Decomposes complex queries into parallel sub-tasks
"Compare Ambuja vs ACC" →
  ExecutionPlan {
    tasks: [
      Task(entity="Ambuja", metrics=["revenue", "esg"]),
      Task(entity="ACC", metrics=["revenue", "esg"])
    ],
    parallel: true
  }
```

#### 3.4 Hybrid Retrieval

**Graph Traversal**:
```cypher
MATCH (e:Issuer {name: $entity})
MATCH (e)-[r:HAS_METRIC]->(m:FinancialMetric)
WHERE m.fiscal_year = $year
RETURN e, r, m
```

**Vector Search**:
```python
# Semantic similarity search
query_embedding = embed(query)  # 384-dim vector
results = faiss_index.search(query_embedding, k=8)
# Filter by similarity threshold (0.45)
```

#### 3.5 Context Assembly

```python
# Token budget management (4000 tokens)
# Priority ranking: graph facts (high conf) > vector chunks (high score)
# Generates exposure tables for financial data
```

#### 3.6 LLM Synthesis

```python
# Generate grounded answer with citations
prompt = build_prompt(query, context)
response = await groq_client.complete(
    model="openai/gpt-oss-120b",
    temperature=0.1,
    max_tokens=2048
)
```

#### 3.7 Quality Assessment

```python
# Cross-validation of claims against evidence
# Confidence scoring
# Citation accuracy check
```

---

### 4. Data Layer

#### 4.1 Neo4j Knowledge Graph

**Schema**:
```cypher
// Entity Types
(:Issuer)          - Companies (Adani, Ambuja, etc.)
(:FinancialMetric) - Revenue, EBITDA, etc.
(:ESGMetric)       - Sustainability scores
(:Regulation)      - SEBI circulars
(:Fund)            - Mutual fund schemes

// Relationship Types
[:HAS_METRIC]      - Entity → Metric
[:COMPLIES_WITH]   - Fund → Regulation
[:OPERATES_IN]     - Company → Sector
[:SUBSIDIARY_OF]   - Company → Parent
```

**Indexes**:
```cypher
CREATE INDEX entity_name FOR (n:Issuer) ON (n.name)
CREATE INDEX metric_year FOR (n:FinancialMetric) ON (n.fiscal_year)
```

#### 4.2 FAISS Vector Store

**Configuration**:
- Index Type: IndexFlatIP (Inner Product for cosine similarity)
- Embedding Model: BAAI/bge-small-en-v1.5 (384 dimensions)
- Namespaces: sebi_regulation, adani_corporate, esg_sustainability, fund_performance

**Chunking Strategy**:
```python
parent_chunk_size = 1200  # ~4800 chars
parent_overlap = 150
child_chunk_size = 250    # ~1000 chars (for vector search)
child_overlap = 50
```

#### 4.3 SQLite Application Database

**Tables**:
- `users` - User accounts and authentication
- `chat_sessions` - Conversation history
- `query_evidence` - Retrieved context for each query
- `feedback` - User feedback and corrections
- `response_quality` - Quality metrics per response
- `audit_log` - Compliance audit trail

---

## Request Flow (End-to-End)

### Example: "What is Adani Enterprises' ESG score?"

```
1. User Input → React Frontend
   ├─ User types query in chat interface
   └─ POST /api/query {query: "..."}

2. API Layer → FastAPI
   ├─ JWT authentication check
   ├─ Rate limiting
   └─ Route to v2 orchestrator

3. Semantic Cache Check
   ├─ Hash-based exact match [MISS]
   └─ Embedding similarity check [MISS]

4. Intent Classification
   └─ Type: entity_lookup
   └─ Entities: ["Adani Enterprises"]
   └─ Taxonomy: ["esg_sustainability", "adani_corporate"]

5. Entity Resolution
   └─ "Adani Enterprises" → Canonical: "AEL"

6. Parallel Retrieval
   ├─ Graph: MATCH (e:Issuer {name:'AEL'})-[:HAS_ESG_SCORE]→(s)
   └─ Vector: Embed query → FAISS search (k=8, threshold=0.45)

7. Context Assembly
   └─ Merge graph facts + vector chunks
   └─ Rank by confidence
   └─ Fit within 4000 token budget

8. LLM Synthesis
   └─ Build prompt with context
   └─ Call Groq API (gpt-oss-120b)
   └─ Parse structured response

9. Quality Assessment
   └─ Cross-validate claims
   └─ Check citations

10. Response Assembly
    └─ Build JSON response with:
       - answer (markdown)
       - citations (with sources)
       - confidence_score
       - execution_time_ms

11. Cache Store
    └─ Store in semantic cache (TTL: 1h)

12. Frontend Render
    └─ Display answer with inline citations
    └─ Show source documents
    └─ Render graph visualization

Total Time: ~600ms (cold) | ~30ms (cached)
```

---

## Key Design Decisions

### 1. Why Hybrid RAG?

**Graph Alone**: High precision but limited coverage
**Vector Alone**: Good coverage but lower precision
**Hybrid**: Best of both worlds

### 2. Why V2 Engine?

V1 was monolithic. V2 is modular:
- Independent components (testable)
- Async/parallel execution (faster)
- Feature flags (canary deployments)
- Better observability

### 3. Why Semantic Caching?

- 40-50% of queries are similar/repeated
- Sub-30ms response (vs 600ms cold)
- Reduces LLM costs by 50%
- Better user experience

### 4. Why Passive Feedback?

- Users don't explicitly rate
- Learn from follow-up questions
- Detect corrections automatically
- Continuous improvement without friction

---

## Performance Characteristics

| Metric | Cold Query | Cached Query |
|--------|------------|--------------|
| Total Latency | ~600ms | ~30ms |
| Cache Lookup | 0ms | 25ms |
| Intent Classification | 50ms | - |
| Graph Traversal | 80ms | - |
| Vector Search | 120ms | - |
| LLM Synthesis | 300ms | - |
| Quality Assessment | 50ms | - |

**Optimization Strategies**:
1. Parallel retrieval (graph + vector)
2. Token budget management
3. Semantic caching (2-tier)
4. Connection pooling
5. Query result streaming

---

## Scalability & Reliability

### Horizontal Scaling

- **API Layer**: Stateless, can scale to N instances
- **Neo4j**: Cluster mode (read replicas)
- **FAISS**: Sharded by namespace
- **Cache**: Distributed cache (Redis) for production

### Fault Tolerance

- **LLM Fallback**: Groq → OpenAI → Gemini → Local
- **Graceful Degradation**: Cache-only mode if services down
- **Circuit Breakers**: Prevent cascade failures
- **Health Checks**: `/health` endpoint for monitoring

### Monitoring

- **Metrics**: Prometheus `/metrics` endpoint
- **Logging**: Structured JSON logs
- **Tracing**: Query execution telemetry
- **Alerts**: Latency, error rate, cache hit rate

---

## Security Architecture

### Authentication & Authorization

1. **JWT Tokens**: Secure session management
2. **Role-Based Access**: Admin, user, read-only
3. **Tenant Isolation**: Multi-tenant data separation

### Data Protection

1. **Secrets Management**: AWS Secrets Manager (production)
2. **API Rate Limiting**: Per-user quotas
3. **Input Validation**: Query sanitization
4. **Audit Logging**: All queries logged

### Compliance

1. **SEBI Validation**: Regulatory rule checking
2. **Data Retention**: Configurable retention policies
3. **Access Controls**: Document-level permissions

---

## Technology Choices Rationale

| Component | Technology | Why? |
|-----------|------------|------|
| **API** | FastAPI | Async, auto-docs, type hints |
| **Graph** | Neo4j | Best graph DB, Cypher query language |
| **Vector** | FAISS | Fastest similarity search (Facebook Research) |
| **LLM** | Groq | Ultra-fast inference, cost-effective |
| **Frontend** | React 19 | Modern, hooks-based, ecosystem |
| **Build** | Vite | Fast dev server, optimized builds |
| **Embeddings** | FastEmbed | Fast, lightweight, CPU-friendly |

---

## Future Architecture Plans

### Short-term (Q1 2027)
- Redis distributed cache
- Async task queue (Celery)
- GraphQL API layer

### Medium-term (Q2-Q3 2027)
- Multi-region deployment
- Real-time collaboration
- Advanced analytics

### Long-term (Q4 2027+)
- Microservices architecture
- Event-driven architecture
- ML model fine-tuning

---

**Last Updated**: October 19, 2026  
**Version**: 2.1
