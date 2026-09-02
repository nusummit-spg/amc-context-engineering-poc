# HITL Feedback Loop with Self-Correcting Knowledge Graphs - Architecture & Design

## Executive Summary

This document details the Human-in-the-Loop (HITL) feedback mechanism integrated into the AMC Context Engineering POC. The system captures user feedback on query responses, stores it temporarily in PostgreSQL, and runs a scheduled evaluation layer that uses self-correcting knowledge graph principles to:

1. **Evaluate feedback quality** and relevance to the knowledge graph
2. **Identify knowledge gaps and inaccuracies** in the current graph
3. **Generate correction recommendations** for entities, relationships, and taxonomy
4. **Update the Neo4j knowledge graph** with high-confidence corrections
5. **Optimize token utilization** through batch evaluation and smart context assembly

The architecture introduces a **temporary feedback buffer (PostgreSQL)** that decouples online query responses from expensive LLM-based evaluation, enabling efficient scheduled processing and historical audit trails.

---

## Part 1: System Architecture Overview

### 1.1 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXISTING QUERY PIPELINE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [User Query] → [Retrieval Engine] → [Context Assembly] → [LLM Synthesis]   │
│                                                                 ↓            │
│                                              [Query Response + Response ID]  │
│                                                                 ↓            │
│                                            ┌───────────────────────┐        │
│                                            │  HITL FEEDBACK LAYER  │        │
│                                            ├───────────────────────┤        │
│                                            │ • Feedback UI overlay │        │
│                                            │ • Response metadata   │        │
│                                            │ • User rating/notes   │        │
│                                            │ • Session context     │        │
│                                            └──────────┬────────────┘        │
│                                                       ↓                      │
└───────────────────────────────────────────────────────┼──────────────────────┘
                                                        │
┌───────────────────────────────────────────────────────┼──────────────────────┐
│                 NEW: TEMPORARY FEEDBACK BUFFER                               │
├───────────────────────────────────────────────────────┼──────────────────────┤
│                                                       ↓                      │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │  PostgreSQL Feedback Store (Temporary)                           │      │
│   ├──────────────────────────────────────────────────────────────────┤      │
│   │                                                                  │      │
│   │  • feedback_records (session_id, query, response, rating, etc)  │      │
│   │  • feedback_classifications (entity tags, taxonomy, sentiment)  │      │
│   │  • feedback_metadata (user_id, timestamp, device, context)      │      │
│   │  • evaluation_jobs (status, created_at, evaluated_at)           │      │
│   │  • correction_recommendations (proposed changes, confidence)    │      │
│   │  • audit_trail (all changes, rollback capability)               │      │
│   │                                                                  │      │
│   └────────────┬─────────────────────────────────────────────────────┘      │
│                │                                                             │
│                ├─ [BATCH 1] → Accumulated feedback over time window         │
│                ├─ [BATCH 2] → By taxonomy/entity type                       │
│                └─ [BATCH 3] → Scheduled collection cycle                    │
│                                                                             │
└────────────────┼─────────────────────────────────────────────────────────────┘
                 │
┌────────────────┼─────────────────────────────────────────────────────────────┐
│       NEW: SCHEDULED EVALUATION LAYER (Runs hourly/daily/weekly)             │
├────────────────┼─────────────────────────────────────────────────────────────┤
│                ↓                                                              │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ 1. FEEDBACK AGGREGATION ENGINE                                  │       │
│   │    • Group feedback by entity/relationship/taxonomy node        │       │
│   │    • Calculate consensus scores (inter-annotator agreement)     │       │
│   │    • Filter low-quality/spam feedback (confidence > threshold)  │       │
│   └──────────────────────┬──────────────────────────────────────────┘       │
│                          ↓                                                    │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ 2. KNOWLEDGE GAP & ERROR DETECTION                              │       │
│   │    • Compare feedback against current graph state               │       │
│   │    • Identify missing entities/relationships                    │       │
│   │    • Detect contradictions in graph                             │       │
│   │    • Score anomalies (deviation from base knowledge)            │       │
│   └──────────────────────┬──────────────────────────────────────────┘       │
│                          ↓                                                    │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ 3. BATCH LLM EVALUATION (Token-Optimized)                        │       │
│   │    • Batch feedback records (10-50 per LLM call)                │       │
│   │    • Provide graph context (affected nodes + 1-hop neighbors)   │       │
│   │    • Request structured correction recommendations              │       │
│   │    • Use cached embeddings for similarity matching              │       │
│   │    • Few-shot examples from previous corrections                │       │
│   └──────────────────────┬──────────────────────────────────────────┘       │
│                          ↓                                                    │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ 4. CORRECTION RECOMMENDATION GENERATION                          │       │
│   │    • Generate Cypher mutations (CREATE/MERGE/SET/DELETE)        │       │
│   │    • Assign confidence scores (0.0-1.0)                         │       │
│   │    • Link back to source feedback records                       │       │
│   │    • Store in correction_recommendations table                  │       │
│   └──────────────────────┬──────────────────────────────────────────┘       │
│                          ↓                                                    │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ 5. QUALITY GATE & HUMAN REVIEW                                  │       │
│   │    • Filter recommendations by confidence threshold             │       │
│   │    • Generate review summaries for human annotators             │       │
│   │    • Await manual approval (optional, configurable)             │       │
│   │    • Auto-apply low-risk corrections (high confidence)          │       │
│   └──────────────────────┬──────────────────────────────────────────┘       │
│                          ↓                                                    │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ 6. GRAPH UPDATE ENGINE (Neo4j Transaction)                      │       │
│   │    • Execute approved Cypher mutations                          │       │
│   │    • Record change provenance (feedback_id, source)             │       │
│   │    • Update document/taxonomy reference counts                  │       │
│   │    • Log audit trail (timestamp, operator, changes)             │       │
│   │    • Emit metrics (entities added/updated/removed)              │       │
│   └──────────────────────┬──────────────────────────────────────────┘       │
│                          ↓                                                    │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ 7. CACHE INVALIDATION & REINDEXING                              │       │
│   │    • Invalidate affected FAISS embeddings (if entity changed)   │       │
│   │    • Invalidate Neo4j traversal cache (affected paths)          │       │
│   │    • Update entity resolver caches                              │       │
│   │    • Emit invalidation notifications                            │       │
│   └──────────────────────┬──────────────────────────────────────────┘       │
│                          ↓                                                    │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ 8. FEEDBACK LOOP CLOSURE                                        │       │
│   │    • Mark feedback records as processed                         │       │
│   │    • Generate feedback report (changes made, impact)            │       │
│   │    • Archive old feedback (TTL-based cleanup)                   │       │
│   │    • Update system metrics & dashboards                         │       │
│   └──────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                             ↓
                [Neo4j Knowledge Graph]
                    (self-correcting)
```

### 1.2 Core Components

#### A. **Online Query Path** (Existing, minimal changes)
- Captures response metadata (response_id, context used, confidence scores)
- Exposes feedback UI endpoint for rating/annotation
- Records session context (user_id, timestamp, device, query intent)

#### B. **Feedback Capture Layer** (New)
- FastAPI endpoint: `POST /api/feedback` — accepts user ratings and annotations
- Validation & sanitization of feedback
- Immediate storage in PostgreSQL (write-through, no waiting)
- Response: Confirmation + feedback_id for tracking

#### C. **Temporary Feedback Buffer** (New, PostgreSQL)
- **Purpose**: Decouple online responses from expensive evaluation
- **Retention**: 30-90 days (configurable TTL)
- **Tables**:
  - `feedback_records` — raw feedback (query, response, rating, notes)
  - `feedback_classifications` — pre-classified entities, intent, sentiment
  - `evaluation_jobs` — batch evaluation status and scheduling
  - `correction_recommendations` — proposed graph mutations
  - `audit_trail` — all changes for compliance/debugging

#### D. **Scheduled Evaluation Orchestrator** (New)
- Runs on schedule (cron: hourly/daily/weekly, configurable)
- Aggregates feedback from buffer
- Initiates batch LLM evaluation
- Manages workflow state and error recovery

#### E. **Batch LLM Evaluation Engine** (New)
- Processes 10-50 feedback records per LLM call
- Provides rich context (affected nodes, relationships, taxonomy)
- Extracts corrections and generates Cypher mutations
- Assigns confidence scores
- Optimized for token efficiency (see Section 2.2)

#### F. **Self-Correcting Knowledge Graph Update Engine** (New)
- Validates corrections against current graph state
- Executes Neo4j transactions
- Records provenance (feedback_id, source, timestamp)
- Invalidates caches
- Generates audit trail

#### G. **Cache Invalidation & Reindexing** (New)
- Notifies vector store (FAISS) of entity changes
- Invalidates Neo4j traversal caches
- Updates entity resolver caches
- Emits events for downstream systems

---

## Part 2: Detailed Data Flow

### 2.1 Feedback Capture Flow

```
User Query Response
        ↓
   [UI Overlay]
   • Thumbs up/down
   • Incorrect entity
   • Missing information
   • Feedback notes
        ↓
POST /api/feedback
{
  "response_id": "uuid",
  "session_id": "uuid",
  "user_id": "string",
  "rating": "positive|negative|neutral",
  "feedback_type": "entity|relationship|missing|inaccurate",
  "entity_name": "optional",
  "entity_type": "optional",
  "notes": "optional",
  "corrections": {
    "proposed_entity": "optional",
    "proposed_relationship": "optional"
  }
}
        ↓
[Validation]
• Check response_id exists
• Validate session_id
• Sanitize text fields
        ↓
[Pre-classification]
• NER on feedback text (extract entities)
• Sentiment analysis (positive/negative/neutral)
• Intent classification (entity_issue|relationship_issue|missing_info|...)
        ↓
PostgreSQL:
INSERT feedback_records (...)
INSERT feedback_classifications (...)
        ↓
Response: 
{
  "feedback_id": "uuid",
  "status": "recorded",
  "evaluation_status": "pending"
}
```

### 2.2 Scheduled Evaluation Flow

```
Cron Trigger (hourly/daily)
        ↓
[Fetch Pending Feedback]
SELECT * FROM feedback_records
WHERE evaluation_status = 'pending'
AND created_at >= NOW() - INTERVAL '1 day'
        ↓
[Group & Aggregate]
GROUP BY:
  • Entity type (if entity feedback)
  • Relationship type (if relationship feedback)
  • Taxonomy node (if taxonomy feedback)
        ↓
[Calculate Consensus]
• Count positive/negative votes
• Calculate inter-annotator agreement (Kappa)
• Filter outliers (confidence < 0.6)
        ↓
[Batch LLM Evaluation]
FOR each batch of 10-50 records:
  1. Fetch Neo4j context (affected nodes + 1-hop)
  2. Assemble evaluation prompt (see Section 3.1)
  3. Call LLM with batched records
  4. Parse structured response (corrections + confidence)
  5. Store recommendations
        ↓
[Correction Recommendations]
INSERT correction_recommendations (...)
        ↓
[Quality Gate]
Filter by confidence >= threshold
        ↓
[Update Graph]
FOR each approved recommendation:
  1. Execute Cypher mutation in Neo4j transaction
  2. Record provenance
  3. Log audit trail
        ↓
[Cache Invalidation]
• Notify FAISS of entity changes
• Invalidate traversal caches
• Update entity resolver
        ↓
[Cleanup]
Mark feedback as 'processed'
Archive old records (TTL)
```

---

## Part 3: Database Schema (PostgreSQL)

### 3.1 Core Tables

```sql
-- feedback_records: Raw feedback from users
CREATE TABLE feedback_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    response_id UUID NOT NULL,
    session_id UUID NOT NULL,
    user_id VARCHAR(255),
    query TEXT NOT NULL,
    response_text TEXT NOT NULL,
    rating VARCHAR(20), -- positive, negative, neutral
    feedback_type VARCHAR(50), -- entity, relationship, missing, inaccurate
    entity_name VARCHAR(255),
    entity_type VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluation_status VARCHAR(20) DEFAULT 'pending', -- pending, processed, rejected
    INDEX (session_id),
    INDEX (response_id),
    INDEX (user_id),
    INDEX (created_at),
    INDEX (evaluation_status)
);

-- feedback_classifications: Pre-classified feedback metadata
CREATE TABLE feedback_classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id UUID REFERENCES feedback_records(id),
    extracted_entities JSONB, -- [{name, type, confidence}, ...]
    sentiment VARCHAR(20), -- positive, negative, neutral
    intent_classification VARCHAR(50), -- entity_issue, relationship_issue, ...
    confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX (feedback_id)
);

-- correction_recommendations: Proposed graph mutations
CREATE TABLE correction_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id UUID REFERENCES feedback_records(id),
    correction_type VARCHAR(50), -- add_entity, update_entity, add_relationship, ...
    target_entity VARCHAR(255), -- affected entity/relationship name
    target_type VARCHAR(50), -- entity_type or relationship_type
    cypher_mutation TEXT NOT NULL, -- Cypher query to execute
    confidence_score FLOAT NOT NULL, -- 0.0-1.0
    reasoning TEXT, -- Why this correction was recommended
    status VARCHAR(20) DEFAULT 'pending', -- pending, approved, applied, rejected
    applied_at TIMESTAMP,
    applied_by VARCHAR(255), -- user_id of approver
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX (feedback_id),
    INDEX (status),
    INDEX (target_entity),
    INDEX (created_at)
);

-- evaluation_jobs: Batch evaluation job tracking
CREATE TABLE evaluation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL,
    batch_size INT,
    status VARCHAR(20) DEFAULT 'pending', -- pending, running, completed, failed
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    processed_records INT,
    recommendations_generated INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX (batch_id),
    INDEX (status),
    INDEX (created_at)
);

-- audit_trail: Compliance and debugging
CREATE TABLE audit_trail (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    correction_id UUID REFERENCES correction_recommendations(id),
    action VARCHAR(50), -- applied, rejected, rolled_back
    cypher_executed TEXT,
    entities_affected JSONB, -- [{name, type, change}, ...]
    operator VARCHAR(255), -- system or user_id
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB, -- additional context
    INDEX (correction_id),
    INDEX (timestamp)
);

-- feedback_metrics: Aggregated statistics
CREATE TABLE feedback_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    total_feedback INT,
    positive_feedback INT,
    negative_feedback INT,
    entity_corrections INT,
    relationship_corrections INT,
    avg_confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (date)
);
```

---

## Part 4: Token Optimization Strategies

### 4.1 Batch Processing

**Problem**: Evaluating each feedback item individually would require N LLM calls.

**Solution**: Batch 10-50 feedback items per LLM call
- Reduce API overhead
- Share common context (Neo4j graph state)
- Amortize system prompt across batch

**Token Savings**: ~70% reduction in system prompt tokens

```python
# Pseudo-code
batch_size = 25
for i in range(0, len(feedback_records), batch_size):
    batch = feedback_records[i:i+batch_size]
    context = fetch_neo4j_context(batch)  # Unified context for all items
    prompt = build_evaluation_prompt(batch, context)
    response = call_llm_once(prompt)  # Single LLM call for 25 items
    parse_and_store_recommendations(response)
```

### 4.2 Contextualization with Graph Snapshots

**Problem**: Each LLM call needs to understand the current graph state.

**Solution**: Fetch minimal, focused subgraph
- Only include affected nodes + 1-hop neighbors
- Exclude irrelevant relationships
- Use graph snapshots (cached, computed hourly)

**Token Savings**: ~50% reduction in context tokens

```python
# Fetch only relevant context
affected_entities = extract_entity_names_from_batch(feedback_batch)
context = neo4j_client.get_subgraph(
    entity_names=affected_entities,
    max_depth=1,
    exclude_properties=['obsolete_fields']
)
# Result: 200-500 tokens instead of 2000+
```

### 4.3 Few-Shot Example Caching

**Problem**: Including few-shot examples in every call wastes tokens.

**Solution**: Pre-compute and cache few-shot examples
- Generate examples once per feedback type
- Embed and store in Redis/memory
- Retrieve only matching examples

**Token Savings**: ~15% reduction in prompt overhead

```python
few_shot_examples = {
    'entity_correction': [
        {'feedback': '...', 'correction': '...'},
        {'feedback': '...', 'correction': '...'},
    ],
    'relationship_correction': [...]
}
# Cache in Redis with TTL
redis_client.set('few_shot_entity', json.dumps(few_shot_examples[0]), ex=86400)
```

### 4.4 Structured Output with Constrained Generation

**Problem**: LLM output parsing requires buffering entire responses.

**Solution**: Use Claude's structured output feature
- Constrain LLM to JSON schema
- Reduce parsing errors
- Decrease output tokens (no explanation text)

**Token Savings**: ~30% reduction in output tokens

```python
correction_schema = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "feedback_id": {"type": "string"},
                    "action": {"enum": ["create_entity", "update_entity", ...]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "cypher": {"type": "string"}
                }
            }
        }
    }
}
# LLM output is guaranteed valid JSON, no wasted tokens on explanations
```

### 4.5 Conditional Evaluation Routing

**Problem**: Not all feedback needs LLM evaluation (some is obvious).

**Solution**: Rule-based filtering before LLM
- High-confidence feedback (inter-annotator agreement > 0.9) → auto-apply
- Low-confidence feedback (agreement < 0.3) → reject
- Medium confidence (0.3-0.9) → LLM evaluation

**Token Savings**: ~60% of feedback skips LLM entirely

```python
def should_evaluate_with_llm(feedback_group):
    agreement_score = calculate_inter_annotator_agreement(feedback_group)
    if agreement_score > 0.9:
        return 'auto_apply'
    elif agreement_score < 0.3:
        return 'reject'
    else:
        return 'llm_evaluate'
```

### 4.6 Semantic Deduplication

**Problem**: Similar feedback items are evaluated separately.

**Solution**: Cluster similar feedback before LLM evaluation
- Embed feedback using local model (Sentence Transformers)
- Cluster with cosine similarity > 0.85
- Send one representative per cluster + vote counts

**Token Savings**: ~40% reduction in feedback items evaluated

```python
embeddings = embed_feedback_batch(feedback_batch)
clusters = cluster_embeddings(embeddings, threshold=0.85)
representative_feedback = [cluster[0] for cluster in clusters]
vote_counts = [len(cluster) for cluster in clusters]
# Evaluate representative + aggregate votes
```

### 4.7 Caching Graph Context

**Problem**: Fetching Neo4j subgraph for each batch is slow and wasteful.

**Solution**: Cache frequently-accessed subgraphs in Redis
- TTL: 1 hour
- Invalidate on graph updates
- Key: hash(affected_entities, max_depth)

**Token Savings**: ~20% reduction in LLM calls due to faster context fetch

```python
cache_key = f"graph_context:{hash(frozenset(affected_entities))}"
cached_context = redis_client.get(cache_key)
if cached_context:
    context = json.loads(cached_context)
else:
    context = fetch_from_neo4j(affected_entities)
    redis_client.setex(cache_key, 3600, json.dumps(context))
```

---

## Part 5: Self-Correcting Knowledge Graph Principles

### 5.1 Correction Types

| Type | Example | Cypher | Confidence Threshold |
|------|---------|--------|----------------------|
| **Add Entity** | Missing fund "Axis Equity Direct Plan" | `CREATE (n:Scheme {name: "...", type: "..."})` | 0.85 |
| **Update Entity Properties** | Fund NAV increased from 10.5 to 11.2 | `MATCH (n) WHERE n.name = "..." SET n.nav = 11.2` | 0.80 |
| **Add Relationship** | Fund X manages scheme Y | `MATCH (f:Fund {name: "..."}) MATCH (s:Scheme {name: "..."}) CREATE (f)-[:MANAGES]->(s)` | 0.75 |
| **Remove Relationship** | Fund no longer manages scheme | `MATCH (f)-[r:MANAGES]-(s) DELETE r` | 0.85 |
| **Update Taxonomy** | Reclassify scheme from "Aggressive" to "Moderate" | `MATCH (s:Scheme) SET s.risk_category = "Moderate"` | 0.80 |
| **Merge Duplicates** | Two nodes represent same entity | `MATCH (a), (b) WHERE a.id = "..." CREATE (a)-[:DUPLICATE_OF]->(b)` | 0.90 |

### 5.2 Validation Rules

Before applying any correction, the system validates:

1. **Graph Integrity**
   - No orphaned nodes created
   - Relationship cardinality preserved
   - No circular self-relationships (except allowed types)

2. **Business Logic**
   - Fund name must match naming convention
   - Fund type must be in taxonomy
   - Asset class must be valid

3. **Data Freshness**
   - NAV can't be older than market close
   - Document references must exist

4. **Provenance**
   - Track feedback_id and source
   - Record human approver (if manual)
   - Timestamp all changes

### 5.3 Rollback & Audit Trail

Every correction is reversible:

```python
# Record before/after state
before_state = neo4j_client.get_node_state(node_id)
execute_correction(correction_cypher)
after_state = neo4j_client.get_node_state(node_id)

audit_trail.insert({
    'correction_id': correction_id,
    'before_state': before_state,
    'after_state': after_state,
    'cypher_executed': correction_cypher,
    'timestamp': now(),
    'operator': 'system'  # or user_id if manual
})

# Rollback capability
def rollback_correction(correction_id):
    audit = audit_trail.get(correction_id)
    reverse_cypher = generate_reverse_cypher(audit.before_state, audit.after_state)
    neo4j_client.execute(reverse_cypher)
```

---

## Part 6: Integration Points with Existing System

### 6.1 Changes to Query Response Path

**File**: `backend/app/api/routes/query.py`

```python
# Add response metadata tracking
@router.post("/api/query")
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    # Existing logic...
    response = generate_response(...)
    
    # NEW: Generate response metadata
    response_metadata = {
        'response_id': str(uuid4()),
        'session_id': request.session_id,  # NEW: required field
        'query': request.query,
        'timestamp': datetime.now(),
        'model_used': settings.llm_model,
        'context_tokens_used': len(context_tokens),
        'retrieval_mode': request.mode
    }
    
    # NEW: Expose feedback UI with response
    return QueryResponse(
        ...existing fields...,
        response_id=response_metadata['response_id'],
        feedback_enabled=True  # UI shows feedback button
    )
```

### 6.2 New Feedback Endpoint

**File**: `backend/app/api/routes/feedback.py` (new)

```python
@router.post("/api/feedback")
async def record_feedback(
    request: FeedbackRequest,
    container: Container = Depends(get_container)
) -> FeedbackResponse:
    """Record user feedback on query response."""
    # Validate response_id exists
    # Pre-classify feedback
    # Store in PostgreSQL
    # Return feedback_id
    pass
```

### 6.3 New Scheduled Evaluation Task

**File**: `backend/app/tasks/evaluation_scheduler.py` (new)

```python
async def run_scheduled_evaluation():
    """Scheduled task: runs hourly/daily/weekly."""
    try:
        # Fetch pending feedback
        pending = await postgres_client.fetch_pending_feedback(limit=500)
        
        # Batch by type
        batches = group_by_feedback_type(pending)
        
        # Evaluate each batch
        for batch in batches:
            corrections = await evaluate_batch(batch)
            await store_recommendations(corrections)
            
        # Apply high-confidence corrections
        await apply_auto_corrections(confidence_threshold=0.85)
        
        # Invalidate caches
        await invalidate_caches()
        
    except Exception as e:
        logger.error(f"Evaluation job failed: {e}")
        # Alert monitoring system
```

### 6.4 APScheduler Integration

**File**: `backend/app/main.py` (modified)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Add jobs
scheduler.add_job(
    run_scheduled_evaluation,
    'cron',
    hour='*',  # Every hour
    id='evaluation_job'
)

@app.on_event("startup")
async def startup_event():
    scheduler.start()
    logger.info("Evaluation scheduler started")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
```

---

## Part 7: Response Quality Metrics

### 7.1 Metrics to Track

```python
# Per evaluation cycle
metrics = {
    'feedback_received': 342,
    'feedback_processed': 312,
    'high_confidence_corrections': 78,
    'mid_confidence_corrections': 45,
    'low_confidence_rejected': 189,
    'entities_added': 23,
    'entities_updated': 15,
    'entities_merged': 3,
    'relationships_added': 34,
    'relationships_removed': 2,
    'avg_consensus_score': 0.72,
    'avg_llm_confidence': 0.81,
    'total_tokens_used': 45320,
    'tokens_saved_by_batching': 31224,  # 69% savings
    'avg_latency_per_feedback': 2.1  # seconds
}
```

### 7.2 Dashboard Queries

```sql
-- Feedback trends
SELECT 
    DATE(created_at) as date,
    COUNT(*) as feedback_count,
    SUM(CASE WHEN rating = 'positive' THEN 1 ELSE 0 END) as positive,
    SUM(CASE WHEN rating = 'negative' THEN 1 ELSE 0 END) as negative
FROM feedback_records
GROUP BY date
ORDER BY date DESC;

-- Top entities being corrected
SELECT 
    target_entity,
    COUNT(*) as correction_count,
    AVG(confidence_score) as avg_confidence
FROM correction_recommendations
WHERE status = 'applied'
GROUP BY target_entity
ORDER BY correction_count DESC
LIMIT 20;

-- Evaluation job performance
SELECT 
    DATE(created_at) as date,
    AVG(batch_size) as avg_batch_size,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_jobs
FROM evaluation_jobs
GROUP BY date;
```

---

## Part 8: Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] PostgreSQL schema setup
- [ ] Feedback endpoint + validation
- [ ] Basic pre-classification (NER + sentiment)
- [ ] Manual testing of feedback capture

### Phase 2: Evaluation Engine (Week 3-4)
- [ ] Batch aggregation logic
- [ ] LLM evaluation prompt design
- [ ] Correction recommendation storage
- [ ] Graph update transactions

### Phase 3: Scheduling & Automation (Week 5)
- [ ] APScheduler integration
- [ ] Scheduled evaluation workflow
- [ ] Cache invalidation system
- [ ] Audit trail logging

### Phase 4: Optimization & Monitoring (Week 6+)
- [ ] Token optimization (batching, deduplication, etc.)
- [ ] Performance dashboards
- [ ] Human review UI
- [ ] Rollback capabilities

---

## Part 9: Configuration & Tuning

```yaml
# config/feedback_config.yaml
feedback:
  postgresql:
    connection: "postgresql://user:pass@localhost:5432/feedback"
    pool_size: 20
    
  batch_evaluation:
    batch_size: 25
    schedule: "0 * * * *"  # Every hour
    max_workers: 4
    
  confidence_thresholds:
    auto_apply: 0.85
    human_review: 0.60
    reject: 0.30
    
  llm:
    model: "claude-opus-4-8"
    max_tokens: 2000
    temperature: 0.2  # Low for structured output
    
  graph:
    context_max_depth: 1
    neo4j_timeout: 30
    
  cache:
    redis_ttl: 3600  # 1 hour
    invalidate_on_write: true
    
  retention:
    feedback_ttl_days: 90
    audit_trail_ttl_days: 365
```

---

## Summary

This architecture provides a scalable, efficient HITL feedback loop that:

1. **Captures feedback** non-blocking (PostgreSQL buffer)
2. **Evaluates in batches** (70% token savings)
3. **Applies self-corrections** to the knowledge graph (with audit trail)
4. **Optimizes token usage** through batching, caching, deduplication, and conditional routing
5. **Enables human review** with confidence thresholds
6. **Maintains graph integrity** with validation and rollback capabilities

The self-correcting nature allows the system to learn from user feedback and continuously improve response quality without requiring manual graph updates.
