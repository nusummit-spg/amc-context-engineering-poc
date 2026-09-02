# HITL System Diagram & Component Relationships

## Complete System Architecture

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                         AMC CONTEXT ENGINEERING POC                         ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┌─────────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (User Interaction)                          │
│                                                                             │
│  [User Query] → [Query Input] → [Submit]                                   │
│                                   ↓                                         │
│                        [Display Response] ← [Response + Response ID]        │
│                                   ↓                                         │
│                      [Feedback Overlay] (Thumbs up/down)                    │
│                           ↓              ↓              ↓                   │
│                    [Rating] [Feedback Type] [Notes] [Submit]              │
│                                           ↓                                │
│                                [Feedback Confirmation]                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↕ HTTP
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND (Existing)                           │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │ POST /api/query                                            │           │
│  │ ├─ Retrieval Engine                                        │           │
│  │ ├─ Context Assembly                                        │           │
│  │ ├─ LLM Synthesis                                           │           │
│  │ ├─ Generate Response ID ← NEW                              │           │
│  │ └─ Cache Response Metadata ← NEW                           │           │
│  └─────────────────────────────────────────────────────────────┘           │
│                           ↓                                                 │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │ POST /api/feedback (NEW)                                   │           │
│  │ ├─ Validate response_id                                    │           │
│  │ ├─ FeedbackCollector.collect_feedback()                    │           │
│  │ │  ├─ Pre-classify (NER, sentiment, intent)              │           │
│  │ │  └─ Store in PostgreSQL                                 │           │
│  │ └─ Return feedback_id                                      │           │
│  └─────────────────────────────────────────────────────────────┘           │
│                           ↓                                                 │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │ GET /api/feedback/{feedback_id} (NEW)                      │           │
│  │ └─ Return evaluation_status                                │           │
│  └─────────────────────────────────────────────────────────────┘           │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │ GET /api/feedback/stats/daily (NEW)                        │           │
│  │ └─ Return pre-computed daily metrics                       │           │
│  └─────────────────────────────────────────────────────────────┘           │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │ GET /api/feedback/health (NEW)                             │           │
│  │ └─ Health check for feedback system                        │           │
│  └─────────────────────────────────────────────────────────────┘           │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │ Container (Dependency Injection)                           │           │
│  │ ├─ feedback_collector                                      │           │
│  │ ├─ feedback_db (PostgreSQL client)                         │           │
│  │ ├─ feedback_processor                                      │           │
│  │ ├─ response_cache                                          │           │
│  │ ├─ feedback_aggregator                                     │           │
│  │ └─ ... (existing services)                                │           │
│  └─────────────────────────────────────────────────────────────┘           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
        ↕                           ↕                           ↕
     HTTP                      TCP/IP                      TCP/IP
        ↕                           ↕                           ↕
┌────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
│  Response      │      │ PostgreSQL           │      │ Neo4j Graph DB       │
│  Metadata      │      │ (Feedback Store)     │      │ (Knowledge Graph)    │
│  Cache         │      │                      │      │                      │
│  (Memory)      │      │  feedback_records    │      │  Current Graph:      │
│                │      │  feedback_class...   │      │  • Entities          │
│                │      │  correction_recs     │      │  • Relationships     │
│                │      │  execution_hist...   │      │  • Taxonomy          │
│                │      │  audit_trail         │      │                      │
│                │      │  feedback_metrics    │      │  Self-Correcting:    │
│                │      │  + 6 cache tables    │      │  • Learn from FB     │
│                │      │                      │      │  • Apply corrections │
│                │      │  (90-day retention)  │      │  • Track provenance  │
│                │      └──────────────────────┘      └──────────────────────┘
└────────────────┘
```

---

## Feedback Collection Flow (Synchronous)

```
User submits feedback
         ↓
    [POST /api/feedback]
         ↓
    ┌────────────────────────────────────────────────┐
    │ FeedbackCollector.collect_feedback()            │
    ├────────────────────────────────────────────────┤
    │ STEP 1: Validate response_id                   │
    │ └─ Check ResponseMetadataCache                 │
    │    • Found? → Continue                         │
    │    • Not found? → Error 404                    │
    ├────────────────────────────────────────────────┤
    │ STEP 2: Pre-classify feedback                  │
    │ ├─ NER extraction (local model)                │
    │ ├─ Sentiment classification                    │
    │ ├─ Intent scoring (0.0-1.0)                    │
    │ └─ Quality score calculation (0.0-1.0)         │
    ├────────────────────────────────────────────────┤
    │ STEP 3: Store in PostgreSQL                    │
    │ ├─ INSERT into feedback_records                │
    │ └─ INSERT into feedback_classifications        │
    │    (non-blocking, commit immediately)          │
    ├────────────────────────────────────────────────┤
    │ STEP 4: Return response                        │
    │ └─ feedback_id, evaluation_status: "pending"   │
    └────────────────────────────────────────────────┘
         ↓
    [Response 201 Created]
    {
      "feedback_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "recorded",
      "evaluation_status": "pending",
      "recorded_at": "2024-01-19T10:30:00Z",
      "quality_score": 0.75
    }
    
TIMING: < 100ms (no waiting for evaluation)
```

---

## Evaluation Cycle (Asynchronous, Scheduled)

```
APScheduler Trigger (Hourly)
         ↓
    ┌────────────────────────────────────────────────────────────┐
    │ EvaluationOrchestrator.run_evaluation_cycle()              │
    └────────────────────────────────────────────────────────────┘
         ↓
    STEP 1: Prepare Feedback Batches
    ┌────────────────────────────────────────────────────────────┐
    │ FeedbackProcessor.prepare_evaluation_batches()             │
    │                                                            │
    │ ├─ Fetch pending feedback from PostgreSQL                 │
    │ │  SELECT * FROM feedback_records                         │
    │ │  WHERE evaluation_status = 'pending'                    │
    │ │  LIMIT 500                                              │
    │ │                                                         │
    │ ├─ Aggregate by entity/type                               │
    │ │  GROUP BY entity_name, feedback_type                    │
    │ │                                                         │
    │ ├─ Calculate consensus scores                             │
    │ │  FOR each group:                                        │
    │ │    consensus = max_votes / total_votes                  │
    │ │                                                         │
    │ ├─ Deduplicate similar feedback                           │
    │ │  Cluster by cosine similarity > 0.85                    │
    │ │  Keep representative + vote_count                       │
    │ │  Result: 40% reduction                                  │
    │ │                                                         │
    │ └─ Create batches (25 items per batch)                    │
    │    Total batches = ceil(items / 25)                       │
    └────────────────────────────────────────────────────────────┘
         ↓
    STEP 2: Batch LLM Evaluation
    ┌────────────────────────────────────────────────────────────┐
    │ FOR each batch (25 items):                                 │
    │                                                            │
    │   BatchEvaluationEngine.evaluate_batch()                  │
    │                                                            │
    │   ├─ FETCH Neo4j context (ONCE for batch)                 │
    │   │  • Extract affected entities from batch               │
    │   │  • Query Neo4j: MATCH (n) WHERE n.name IN (...)      │
    │   │  • Cache in Redis (1-hour TTL)                        │
    │   │  • Shared across all 25 items                         │
    │   │  Result: ~70% token savings                           │
    │   │                                                        │
    │   ├─ BUILD evaluation prompt                              │
    │   │  • Batch items (formatted clearly)                    │
    │   │  • Shared Neo4j context                               │
    │   │  • Few-shot examples (cached)                         │
    │   │  • System prompt (500 tokens)                         │
    │   │                                                        │
    │   ├─ CALL LLM ONCE                                        │
    │   │  • Model: claude-opus-4-8                             │
    │   │  • Max tokens: 2000                                   │
    │   │  • Structured output (JSON schema)                    │
    │   │  • Temperature: 0.2 (deterministic)                   │
    │   │                                                        │
    │   └─ PARSE structured response                            │
    │      Store in correction_recommendations table            │
    │                                                            │
    │   TOKEN BREAKDOWN (25 items):                             │
    │   • System prompt: 500                                    │
    │   • Context (shared): 800                                 │
    │   • Few-shot (cached): 400                                │
    │   • Batch items: 2500 (100 each)                          │
    │   • Output: 500                                           │
    │   ─────────────────────                                   │
    │   • TOTAL: 4700 tokens for 25 items = 188 tokens/item     │
    │   • vs Naive: ~1800 tokens/item (10x savings)             │
    └────────────────────────────────────────────────────────────┘
         ↓
    STEP 3: Apply Corrections
    ┌────────────────────────────────────────────────────────────┐
    │ GraphCorrectionEngine.apply_high_confidence_corrections()  │
    │                                                            │
    │ FOR each recommendation WHERE confidence > 0.85:          │
    │                                                            │
    │   ├─ VALIDATE correction                                  │
    │   │  • Cypher syntax check                                │
    │   │  • Dangerous ops detection (DROP, DELETE)             │
    │   │  • Business logic validation                          │
    │   │                                                        │
    │   ├─ EXECUTE in Neo4j transaction                         │
    │   │  BEGIN TRANSACTION                                    │
    │   │    • Capture before state (entity snapshot)           │
    │   │    • Execute Cypher mutation                          │
    │   │    • Capture after state                              │
    │   │  COMMIT                                               │
    │   │                                                        │
    │   ├─ RECORD audit trail                                   │
    │   │  INSERT INTO correction_execution_history             │
    │   │    correction_id, action, before_state,               │
    │   │    after_state, entities_affected,                    │
    │   │    operator: 'system', timestamp                      │
    │   │                                                        │
    │   ├─ UPDATE recommendation status                         │
    │   │  UPDATE correction_recommendations                    │
    │   │  SET status = 'applied', applied_at = NOW()           │
    │   │                                                        │
    │   └─ TRACK affected entities                              │
    │      For cache invalidation                               │
    └────────────────────────────────────────────────────────────┘
         ↓
    STEP 4: Invalidate Caches
    ┌────────────────────────────────────────────────────────────┐
    │ CacheManager.invalidate_entity_caches(affected_entities)   │
    │                                                            │
    │ FOR each affected entity:                                 │
    │   ├─ Invalidate FAISS embeddings                          │
    │   │  • Delete embeddings for this entity                  │
    │   │  • Force re-computation on next query                 │
    │   │                                                        │
    │   ├─ Invalidate entity resolver cache                     │
    │   │  • Clear entity alias mappings                        │
    │   │  • Clear entity type cache                            │
    │   │                                                        │
    │   ├─ Invalidate Redis cache (if configured)               │
    │   │  • Delete pattern: graph_context:*entity_name*        │
    │   │  • Delete pattern: entity:*entity_name*               │
    │   │                                                        │
    │   └─ Invalidate Neo4j traversal cache                     │
    │      • Clear affected query paths                         │
    │                                                            │
    │ EMIT invalidation event (for subscribed systems)          │
    └────────────────────────────────────────────────────────────┘
         ↓
    STEP 5: Record Metrics
    ┌────────────────────────────────────────────────────────────┐
    │ INSERT INTO feedback_metrics                               │
    │ date = TODAY()                                             │
    │ total_feedback = COUNT(*)                                  │
    │ positive_feedback = COUNT WHERE rating = 'positive'        │
    │ corrections_applied = ...                                  │
    │ avg_confidence_score = AVG(confidence)                     │
    │ tokens_used = ...                                          │
    └────────────────────────────────────────────────────────────┘
         ↓
    STEP 6: Cleanup
    ┌────────────────────────────────────────────────────────────┐
    │ Archive old feedback (> 90 days)                           │
    │ Delete rejected recommendations (> 7 days)                 │
    │ Cleanup expired cache entries                              │
    │ Run VACUUM on PostgreSQL                                   │
    └────────────────────────────────────────────────────────────┘
         ↓
    RETURN cycle metrics
    {
      "cycle_id": "...",
      "status": "completed",
      "batches_prepared": 5,
      "batches_evaluated": 5,
      "recommendations_generated": 87,
      "corrections_applied": 72,
      "corrections_failed": 2,
      "affected_entities": 45,
      "total_tokens_used": 23500,
      "tokens_saved_by_batching": 16800,  # 71% savings
      "duration_seconds": 245.3
    }
```

---

## Data Model Relationships

```
feedback_records (Raw User Input)
    │
    ├─ id (UUID) ◄─── Primary Key
    ├─ response_id (UUID) ◄─── Links to cached response
    ├─ session_id (UUID) ◄─── User session
    ├─ query (TEXT)
    ├─ response_text (TEXT)
    ├─ rating ('positive'|'negative'|'neutral')
    ├─ feedback_type ('entity_incorrect'|'missing'|...)
    ├─ entity_name (VARCHAR)
    ├─ entity_type (VARCHAR)
    ├─ notes (TEXT, max 2000 chars)
    ├─ corrections (JSONB)
    ├─ evaluation_status ('pending'|'processed'|'rejected')
    └─ created_at (TIMESTAMP)
         │
         ├── feedback_classifications
         │   │
         │   ├─ feedback_id (FK) ◄─── References feedback_records
         │   ├─ extracted_entities (JSONB)
         │   ├─ sentiment ('positive'|'negative'|'neutral')
         │   ├─ intent_classification (VARCHAR)
         │   ├─ confidence_score (FLOAT 0.0-1.0)
         │   └─ created_at (TIMESTAMP)
         │
         └── correction_recommendations
             │
             ├─ feedback_id (FK) ◄─── References feedback_records
             ├─ id (UUID) ◄─── Primary Key
             ├─ correction_type ('add_entity'|'update_entity'|...)
             ├─ target_entity (VARCHAR)
             ├─ target_type (VARCHAR)
             ├─ cypher_mutation (TEXT) ◄─── Ready to execute
             ├─ confidence_score (FLOAT 0.0-1.0)
             ├─ reasoning (TEXT)
             ├─ status ('pending'|'approved'|'applied'|'rejected')
             ├─ applied_at (TIMESTAMP)
             ├─ applied_by (VARCHAR)
             └─ created_at (TIMESTAMP)
                  │
                  └── correction_execution_history
                      │
                      ├─ correction_id (FK) ◄─── References correction_recommendations
                      ├─ id (UUID) ◄─── Primary Key
                      ├─ action ('applied'|'rolled_back'|'failed')
                      ├─ cypher_executed (TEXT)
                      ├─ before_state (JSONB) ◄─── Entity snapshot before
                      ├─ after_state (JSONB) ◄─── Entity snapshot after
                      ├─ entities_affected (JSONB)
                      ├─ operator (VARCHAR) ◄─── 'system' or user_id
                      ├─ timestamp (TIMESTAMP)
                      └─ metadata (JSONB)
                           │
                           └── audit_trail
                               │
                               ├─ execution_id (FK)
                               ├─ correction_id (FK)
                               ├─ feedback_id (FK)
                               ├─ action_type (VARCHAR)
                               ├─ actor (VARCHAR)
                               ├─ success (BOOLEAN)
                               ├─ error_message (TEXT)
                               └─ timestamp (TIMESTAMP)

CACHING TABLES (TTL):
├─ feedback_deduplication_cache (1 hour)
├─ graph_context_snapshot (1 hour)
└─ llm_evaluation_cache (24 hours)

AGGREGATION TABLES:
└─ feedback_metrics (daily)
    ├─ date (DATE)
    ├─ total_feedback (INT)
    ├─ positive_feedback (INT)
    ├─ negative_feedback (INT)
    ├─ avg_confidence_score (FLOAT)
    └─ ... (many more fields)

SESSIONS:
└─ feedback_sessions
    ├─ session_id (UUID)
    ├─ user_id (VARCHAR)
    ├─ feedback_count (INT)
    ├─ is_active (BOOLEAN)
    └─ ended_at (TIMESTAMP)
```

---

## Component Dependency Graph

```
┌─────────────────────────────────────────┐
│      FastAPI Application                │
└─────────────────────────────────────────┘
              │
              ├─ Router: feedback_routes
              │   ├─ POST /api/feedback → FeedbackCollector
              │   ├─ GET /api/feedback/* → PostgreSQL queries
              │   └─ GET /api/feedback/stats/* → Aggregator
              │
              └─ Container (Dependency Injection)
                  ├─ PostgreSQLFeedbackClient
                  │   └─ asyncpg.Pool
                  │
                  ├─ ResponseMetadataCache
                  │   └─ In-memory dict
                  │
                  ├─ FeedbackCollector
                  │   ├─ PostgreSQLFeedbackClient
                  │   ├─ NERPipeline
                  │   └─ ResponseMetadataCache
                  │
                  ├─ FeedbackProcessor
                  │   └─ PostgreSQLFeedbackClient
                  │
                  ├─ BatchEvaluationEngine
                  │   ├─ LLMClient
                  │   ├─ PostgreSQLFeedbackClient
                  │   ├─ GraphStore
                  │   └─ EntityResolver
                  │
                  ├─ GraphCorrectionEngine
                  │   ├─ Neo4jDriver
                  │   └─ PostgreSQLFeedbackClient
                  │
                  ├─ CacheManager
                  │   ├─ FAISSclient
                  │   ├─ EntityResolver
                  │   └─ RedisClient (optional)
                  │
                  ├─ EvaluationOrchestrator
                  │   ├─ FeedbackProcessor
                  │   ├─ BatchEvaluationEngine
                  │   ├─ GraphCorrectionEngine
                  │   └─ CacheManager
                  │
                  └─ SchedulerManager
                      └─ AsyncIOScheduler
                          └─ EvaluationOrchestrator
```

---

## Token Flow Optimization

```
PER-ITEM EVALUATION (Naive Approach):
┌─────────────────────────────────┐
│ Item 1                          │
│ ┌──────────────────────────────┐│
│ │ System prompt:          500  ││
│ │ Context (Neo4j fetch):  800  ││
│ │ Few-shot examples:      400  ││
│ │ Item data:              100  ││
│ │ Output:                 300  ││
│ │ ────────────────────────────── ││
│ │ Total: 2100 tokens/item     ││
│ └──────────────────────────────┘│
└─────────────────────────────────┘
    × 25 items = 52,500 tokens for batch

BATCH EVALUATION (Optimized):
┌─────────────────────────────────────┐
│ System prompt:              500    │
│ Context (shared, fetched ONCE): 800 │
│ Few-shot examples (cached):    400 │
│ ─────────────────────────────────── │
│ Subtotal (amortized):      1,700  │
│ ÷ 25 items = 68 tokens/item       │
│                                    │
│ + (25 items × 100 tokens):  2,500  │
│ + Output tokens (structured): 500  │
│ ───────────────────────────────────│
│ Total for batch:            4,700  │
│ ÷ 25 items = 188 tokens/item       │
│                                    │
│ SAVINGS: (2100-188)/2100 = 91%    │
│                                    │
│ vs naive: 52,500 → 4,700           │
└─────────────────────────────────────┘

DEDUPLICATION BONUS:
• 40 feedback items before dedup
• Cluster similar items → 25 representatives
• Evaluate 25 instead of 40
• Additional 37% savings
• Total feedback items: 40 with vote counts
• LLM evaluates: 25 representatives
```

---

## Performance Timeline

```
User Interaction Timeline:
─────────────────────────────────────────
User: [Submits Feedback]
Backend receives → 0ms
│
├─ Validate response_id: 5ms
├─ NER extraction: 15ms
├─ Sentiment classification: 5ms
├─ PostgreSQL INSERT: 20ms
│
└─ Return feedback_id: 50ms (Total)
   └─ User sees: "Feedback recorded" ✓

Evaluation Cycle Timeline (Hourly):
─────────────────────────────────────────
[Scheduler trigger at :00 past hour]
│
├─ Fetch feedback: 500ms
├─ Aggregate & deduplicate: 1000ms
├─ FOR each batch (5 batches):
│  ├─ Fetch Neo4j context: 2000ms
│  ├─ Build prompt: 200ms
│  ├─ LLM call: 30,000ms (typical)
│  └─ Parse response: 500ms
│  └─ Subtotal: 32,700ms per batch
│  └─ 5 batches: 163,500ms (2.7 minutes)
│
├─ Apply corrections: 5000ms
├─ Invalidate caches: 2000ms
├─ Record metrics: 1000ms
├─ Cleanup: 1000ms
│
└─ Total cycle: ~175 seconds (3 minutes)

Concurrent with other system operations:
• Query responses: < 1 second (unaffected)
• Feedback collection: < 100ms (unaffected)
• Cache queries: < 10ms (uses Redis)
```

---

## Scalability Limits

```
CURRENT CONFIGURATION:
┌────────────────────────────────────────┐
│ PostgreSQL Connection Pool: 20         │
│ Batch Size: 25 items                   │
│ Evaluation Schedule: Hourly             │
│ LLM Concurrency: 4 calls max            │
│ FAISS Index Size: Unlimited             │
│ Redis Memory: Configurable              │
└────────────────────────────────────────┘

CAPACITY ESTIMATES:

Feedback Collection:
• 20 concurrent DB connections
• Each can handle ~100 writes/sec
• Total capacity: 2,000 feedback/sec (sustained)
• Burst capacity: 5,000 feedback/sec

Evaluation Processing:
• Hourly cycle: 500 feedback items
• 20 batches × 25 items
• LLM concurrency: 4 calls
• Cycle duration: ~3 minutes
• Capacity: 500-1000 items/hour → 12K-24K/day

Graph Updates:
• Neo4j transaction throughput: 1000 ops/sec
• Auto-applied corrections: ~72-100/cycle
• Update throughput: Limited by LLM evaluation, not Neo4j

SCALING STRATEGY:

If feedback > 1K/day:
  ├─ Increase evaluation frequency (every 30 min)
  ├─ Increase batch size (50 items/batch)
  └─ Add LLM concurrency (8 calls)

If feedback > 10K/day:
  ├─ Multiple evaluation cycles (3x per hour)
  ├─ Scale PostgreSQL (read replicas)
  ├─ Use Redis for distributed caching
  └─ Consider queue system (Kafka/RabbitMQ)

If feedback > 100K/day:
  ├─ Dedicated evaluation cluster
  ├─ Horizontal scaling of API servers
  ├─ Sharding PostgreSQL by session_id
  └─ Custom batch LLM service
```

This comprehensive diagram and documentation provides a complete visual and textual understanding of the HITL system architecture and operations.
