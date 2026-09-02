# HITL Implementation Guide: Integration & Deployment

## Quick Start

### 1. Install Dependencies

```bash
cd backend

# Add new dependencies to requirements.txt
pip install asyncpg  # PostgreSQL async client
pip install apscheduler  # Task scheduling
pip install python-dotenv  # Environment configuration

# Install all
pip install -r requirements.txt
```

### 2. Initialize PostgreSQL

```bash
# Create database and user
psql -U postgres -c "CREATE USER feedback WITH PASSWORD 'feedbackpass123';"
psql -U postgres -c "CREATE DATABASE amc_feedback OWNER feedback;"

# Run migrations
python -m app.engine.migrations.migration_runner up

# Verify schema
psql -U feedback -d amc_feedback -c "\dt"
```

### 3. Update Environment Configuration

```bash
# backend/.env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=feedback
POSTGRES_PASSWORD=feedbackpass123
POSTGRES_DB=amc_feedback
POSTGRES_POOL_SIZE=20

# Feedback configuration
FEEDBACK_ENABLED=true
FEEDBACK_MIN_QUALITY_SCORE=0.3
FEEDBACK_BATCH_SIZE=25
FEEDBACK_SCHEDULE_HOUR=*  # Every hour
FEEDBACK_CONFIDENCE_THRESHOLD=0.85
FEEDBACK_RETENTION_DAYS=90
```

### 4. Initialize in FastAPI

```python
# backend/app/main.py

from app.engine.postgres_client import PostgreSQLFeedbackClient
from app.engine.feedback_collector import init_feedback_collector, ResponseMetadataCache
from app.engine.feedback_processor import FeedbackProcessor
from app.engine.batch_evaluation import BatchEvaluationEngine
from app.engine.graph_corrector import GraphCorrectionEngine
from app.engine.cache_manager import init_cache_manager
from app.tasks.evaluation_orchestrator import (
    init_evaluation_orchestrator, start_scheduler, stop_scheduler
)

# Initialize PostgreSQL
postgres_client = PostgreSQLFeedbackClient(
    connection_string=settings.postgres_connection_string,
    pool_size=settings.postgres_pool_size
)

# Initialize response cache
response_cache = ResponseMetadataCache(ttl_seconds=86400)

# Initialize feedback collector
init_feedback_collector(
    postgres_client=postgres_client,
    ner_pipeline=container.ner_pipeline,
    response_cache=response_cache
)

# Initialize feedback processor
feedback_processor = FeedbackProcessor(postgres_client)

# Initialize batch evaluator
batch_evaluator = BatchEvaluationEngine(
    llm_client=container.llm_client,
    pg_client=postgres_client,
    graph_store=container.graph_store,
    entity_resolver=container.entity_resolver
)

# Initialize graph corrector
graph_corrector = GraphCorrectionEngine(
    neo4j_driver=container.neo4j_driver,
    postgres_client=postgres_client
)

# Initialize cache manager
init_cache_manager(
    faiss_client=container.faiss_client,
    entity_resolver=container.entity_resolver,
    redis_client=container.redis_client  # Optional
)

# Initialize orchestrator
init_evaluation_orchestrator(
    postgres_client=postgres_client,
    feedback_processor=feedback_processor,
    batch_evaluator=batch_evaluator,
    graph_corrector=graph_corrector,
    cache_manager=cache_manager,
    config=settings.feedback_config
)

@app.on_event("startup")
async def startup():
    # Initialize PostgreSQL
    await postgres_client.initialize()
    
    # Start evaluation scheduler
    await start_scheduler()

@app.on_event("shutdown")
async def shutdown():
    # Stop scheduler
    await stop_scheduler()
    
    # Close PostgreSQL pool
    await postgres_client.close()
```

### 5. Add Feedback Routes

```python
# backend/app/main.py

from app.api.routes import feedback as feedback_routes

app.include_router(feedback_routes.router)
```

### 6. Update Query Endpoint

Modify existing query endpoint to track response metadata:

```python
# backend/app/api/routes/query.py

from uuid import uuid4
from datetime import datetime

@router.post("/api/query")
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    # Existing query logic...
    response = generate_response(...)
    
    # NEW: Generate response metadata
    response_id = str(uuid4())
    response_metadata = {
        'response_id': response_id,
        'session_id': request.session_id,
        'query': request.query,
        'response_text': result['response_text'],
        'timestamp': datetime.utcnow(),
        'model_used': settings.llm_model,
        'context_tokens_used': result.get('context_tokens', 0)
    }
    
    # Cache metadata
    await container.response_cache.set(
        key=response_id,
        value=response_metadata,
        expire=86400  # 24 hours
    )
    
    # Return with feedback enabled
    return QueryResponse(
        ...existing fields...,
        response_id=response_id,
        feedback_enabled=True
    )
```

---

## Testing the HITL System

### 1. Unit Tests

```python
# backend/tests/test_feedback_collector.py

import pytest
from app.engine.feedback_collector import FeedbackCollector
from app.schemas.feedback import FeedbackRequest, RatingType, FeedbackType

@pytest.mark.asyncio
async def test_collect_feedback():
    collector = FeedbackCollector(
        postgres_client=mock_pg_client,
        ner_pipeline=mock_ner,
        response_cache=mock_cache
    )
    
    request = FeedbackRequest(
        response_id="550e8400-e29b-41d4-a716-446655440000",
        session_id="550e8400-e29b-41d4-a716-446655440001",
        rating=RatingType.NEGATIVE,
        feedback_type=FeedbackType.ENTITY_INCORRECT,
        entity_name="Axis Equity Direct",
        notes="This fund was liquidated"
    )
    
    result = await collector.collect_feedback(request)
    
    assert result['status'] == 'recorded'
    assert result['evaluation_status'] == 'pending'
    assert 'feedback_id' in result
```

### 2. Integration Tests

```python
# backend/tests/test_evaluation_cycle.py

@pytest.mark.asyncio
async def test_full_evaluation_cycle():
    # Setup mock data
    # Run evaluation cycle
    # Verify corrections applied
    # Check cache invalidation
    # Verify audit trail recorded
    pass
```

### 3. Manual Testing

```bash
# 1. Start backend
cd backend
uvicorn app.main:app --reload

# 2. Test query endpoint
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What funds are available?", "session_id": "test-session-1"}'

# Note the response_id in response

# 3. Submit feedback
curl -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "response_id": "<response_id_from_above>",
    "session_id": "test-session-1",
    "rating": "negative",
    "feedback_type": "entity_incorrect",
    "entity_name": "Axis Growth",
    "notes": "This fund is no longer available"
  }'

# 4. Check feedback status
curl http://localhost:8000/api/feedback/<feedback_id>

# 5. Manually trigger evaluation cycle
python -c "
import asyncio
from app.tasks.evaluation_orchestrator import get_orchestrator

async def run():
    metrics = await get_orchestrator().run_evaluation_cycle()
    print(metrics)

asyncio.run(run())
"

# 6. Check database
psql -U feedback -d amc_feedback -c "SELECT * FROM feedback_records;"
```

---

## Monitoring & Observability

### 1. Logging Configuration

```python
# backend/app/core/logging.py

import logging
import logging.handlers

def setup_logging():
    # Create logger
    logger = logging.getLogger('hitl_feedback')
    logger.setLevel(logging.DEBUG)
    
    # File handler for feedback events
    fh = logging.handlers.RotatingFileHandler(
        'logs/hitl_feedback.log',
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    
    # Console handler
    ch = logging.StreamHandler()
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger
```

### 2. Metrics Collection

```python
# backend/app/engine/metrics_collector.py

from prometheus_client import Counter, Histogram, Gauge

# Metrics
feedback_received = Counter(
    'feedback_received_total',
    'Total feedback received',
    ['feedback_type', 'rating']
)

correction_applied = Counter(
    'correction_applied_total',
    'Total corrections applied',
    ['correction_type']
)

evaluation_cycle_duration = Histogram(
    'evaluation_cycle_duration_seconds',
    'Evaluation cycle duration'
)

pending_feedback = Gauge(
    'pending_feedback_count',
    'Number of pending feedback items'
)
```

### 3. Dashboard Queries

```sql
-- Feedback trends
SELECT 
    DATE(created_at) as date,
    COUNT(*) as total,
    SUM(CASE WHEN rating = 'positive' THEN 1 ELSE 0 END) as positive,
    SUM(CASE WHEN rating = 'negative' THEN 1 ELSE 0 END) as negative
FROM feedback_records
GROUP BY date
ORDER BY date DESC
LIMIT 30;

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

-- Correction success rate
SELECT 
    status,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM correction_recommendations
GROUP BY status;
```

---

## Performance Tuning

### 1. Batch Size Optimization

```python
# Test different batch sizes
for batch_size in [10, 25, 50, 100]:
    # Measure tokens used
    # Measure latency
    # Measure LLM costs
    
# Optimal: 25 items per batch (balances context sharing with LLM costs)
```

### 2. Scheduling Optimization

```python
# Adjust evaluation schedule based on feedback volume
# Low volume: Daily evaluation
# Medium volume: 6-hourly evaluation
# High volume: Hourly evaluation
# Very high: Continuous background processing
```

### 3. Database Optimization

```bash
# Run maintenance
VACUUM ANALYZE feedback_records;
REINDEX TABLE correction_recommendations;

# Monitor slow queries
SELECT query, mean_exec_time FROM pg_stat_statements 
ORDER BY mean_exec_time DESC LIMIT 10;
```

---

## Troubleshooting

### PostgreSQL Connection Issues

```bash
# Check connection
psql -U feedback -d amc_feedback -c "SELECT 1"

# Check logs
tail -f /var/log/postgresql/postgresql.log

# Connection pool exhausted?
SELECT COUNT(*) FROM pg_stat_activity WHERE datname = 'amc_feedback';
```

### Missing Feedback IDs

```sql
-- Check if feedback is being stored
SELECT COUNT(*) FROM feedback_records WHERE created_at > NOW() - INTERVAL '1 hour';

-- Check for storage errors
SELECT * FROM feedback_records WHERE evaluation_status = 'failed';
```

### Evaluations Not Running

```bash
# Check scheduler status
python -c "
from app.tasks.evaluation_orchestrator import get_scheduler_manager
manager = get_scheduler_manager()
for job in manager.get_scheduled_jobs():
    print(job)
"

# Check for errors in logs
grep "ERROR" logs/hitl_feedback.log

# Manual trigger
python -c "
import asyncio
from app.tasks.evaluation_orchestrator import get_orchestrator
asyncio.run(get_orchestrator().run_evaluation_cycle())
"
```

### Graph Update Failures

```bash
# Check Neo4j connectivity
cypher-shell -u neo4j -p password "MATCH (n) RETURN COUNT(n)"

# Check audit trail for errors
SELECT * FROM audit_trail 
WHERE success = FALSE 
ORDER BY timestamp DESC LIMIT 10;

# Check for constraint violations
SELECT * FROM correction_recommendations 
WHERE status = 'failed' 
ORDER BY created_at DESC LIMIT 10;
```

---

## Security Considerations

### 1. PostgreSQL Security

```bash
# Use strong passwords
ALTER USER feedback WITH PASSWORD 'strong_password_here';

# Restrict connection privileges
```

### 2. API Authentication

```python
# Add authentication to feedback endpoints
from fastapi.security import HTTPBearer

security = HTTPBearer()

@router.post("/api/feedback/")
async def record_feedback(
    request: FeedbackRequest,
    credentials: HTTPAuthCredentials = Depends(security)
):
    # Verify token
    # Log user_id
    pass
```

### 3. Data Privacy

```python
# Redact PII from feedback before storing
from app.engine.pii_scrub import PIIScrubber

scrubber = PIIScrubber()
sanitized_notes = scrubber.scrub(feedback_request.notes)
```

### 4. Audit Trail

```sql
-- All corrections must be audited
-- Retention: Minimum 1 year
-- Cannot be deleted: immutable audit table
```

---

## Production Deployment

### 1. Docker Compose

```yaml
# docker-compose.yml

version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: feedback
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: amc_feedback
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  
  api:
    build: ./backend
    depends_on:
      - postgres
    environment:
      POSTGRES_HOST: postgres
      FEEDBACK_ENABLED: "true"
    ports:
      - "8000:8000"

volumes:
  postgres_data:
```

### 2. Kubernetes Deployment

```yaml
# kubernetes/hitl-deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: hitl-feedback-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: hitl-feedback
  template:
    metadata:
      labels:
        app: hitl-feedback
    spec:
      containers:
      - name: api
        image: amc-hitl-feedback:latest
        ports:
        - containerPort: 8000
        env:
        - name: POSTGRES_HOST
          valueFrom:
            configMapKeyRef:
              name: hitl-config
              key: postgres-host
        livenessProbe:
          httpGet:
            path: /api/feedback/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

---

## Maintenance Schedule

### Daily
- Monitor feedback volume
- Check evaluation cycle success
- Review audit trail for errors

### Weekly
- Analyze feedback trends
- Check database health
- Review correction effectiveness

### Monthly
- Cleanup old feedback (archive)
- Analyze system performance
- Update correction templates based on patterns
- Review user feedback quality trends

### Quarterly
- Performance optimization
- Security audit
- Backup integrity check
- Training data evaluation

---

## Success Metrics

Track these KPIs:

```python
metrics = {
    'feedback_volume_per_day': 0,
    'positive_feedback_percentage': 0.0,
    'feedback_quality_score': 0.0,
    'average_consensus_agreement': 0.0,
    'corrections_applied_per_cycle': 0,
    'correction_success_rate': 0.0,
    'average_confidence_score': 0.0,
    'token_savings_percentage': 0.0,  # vs naive evaluation
    'evaluation_cycle_duration_seconds': 0.0,
    'system_uptime_percentage': 0.0
}
```

---

## Support & Troubleshooting

For issues:
1. Check logs: `tail -f logs/hitl_feedback.log`
2. Query database: Check feedback_records, correction_recommendations tables
3. Verify scheduler: Check APScheduler status
4. Test connectivity: `psql -U feedback -d amc_feedback`
5. Check Neo4j: `cypher-shell "MATCH (n) RETURN COUNT(n)"`

---

## Next Steps

1. **Implement Missing Pieces**
   - Batch LLM evaluation engine (call LLM with batches)
   - Entity resolver integration
   - FAISS cache invalidation

2. **Add Advanced Features**
   - Manual human review UI
   - Correction templates
   - Feedback analytics dashboard
   - A/B testing framework

3. **Optimize**
   - Fine-tune batch sizes
   - Cache hit rate improvements
   - Database query optimization
   - LLM cost reduction

4. **Monitor**
   - Setup Prometheus/Grafana
   - Configure alerts
   - Track KPIs
   - Performance baselines

---

This guide provides the foundation for integrating and deploying the HITL feedback loop with self-correcting knowledge graphs.
