# PostgreSQL Database Setup Guide for HITL Feedback Loop

## Quick Start

### 1. Prerequisites

Ensure PostgreSQL 12+ is installed:

```bash
# macOS
brew install postgresql@15

# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# Windows
# Download from https://www.postgresql.org/download/windows/
```

### 2. Create Database and User

```bash
# Connect to PostgreSQL default database
psql -U postgres

# In psql shell:
CREATE USER feedback WITH PASSWORD 'feedbackpass123';
ALTER USER feedback CREATEDB;

CREATE DATABASE amc_feedback OWNER feedback;
GRANT ALL PRIVILEGES ON DATABASE amc_feedback TO feedback;

-- Verify
\l  -- List databases
\du -- List users
```

### 3. Run Migrations

```bash
cd backend

# Run all pending migrations
python -m app.engine.migrations.migration_runner up

# Check status
python -m app.engine.migrations.migration_runner status
```

### 4. Verify Schema

```bash
# Connect to feedback database
psql -U feedback -d amc_feedback -h localhost

# In psql shell:
\dt  -- List all tables
\dv  -- List all views
\df  -- List all functions
```

---

## Database Schema Overview

### Core Tables

#### `feedback_records` (Primary)
- Stores raw user feedback on query responses
- ~100KB per 1000 records
- **Key Indexes**: session_id, user_id, evaluation_status, entity_name
- **Retention**: 90 days (configurable)

#### `feedback_classifications` (Metadata)
- Pre-classified feedback (NER, sentiment, intent)
- JSONB fields for extracted entities
- ~50KB per 1000 records
- **Key Indexes**: feedback_id, confidence_score, sentiment

#### `correction_recommendations` (Generated)
- LLM-generated correction proposals
- Cypher mutations ready for execution
- ~200KB per 1000 records
- **Key Indexes**: feedback_id, status, target_entity, confidence_score

#### `correction_execution_history` (Audit)
- Before/after snapshots of graph changes
- Enables rollback capability
- ~500KB per 1000 corrections
- **Key Indexes**: correction_id, timestamp, action

#### `audit_trail` (Compliance)
- All significant actions logged
- Retention: 1 year (immutable)
- Used for compliance and debugging

### Optimization Tables

#### `feedback_deduplication_cache`
- Cache for embedding-based clustering (1-hour TTL)
- ~10KB per batch
- Auto-cleaned by `cleanup_expired_cache()` function

#### `graph_context_snapshot`
- Cache for Neo4j subgraph fetches (1-hour TTL)
- ~50-200KB per snapshot
- Shared across multiple feedback items in batch

#### `llm_evaluation_cache`
- Cache LLM responses (24-hour TTL)
- ~100KB per batch
- Similar batches reuse cached responses

#### `feedback_metrics`
- Pre-aggregated daily statistics
- ~5KB per day
- Used for dashboards (avoids expensive aggregations)

---

## Connection Configuration

### Environment Variables

```bash
# backend/.env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=feedback
POSTGRES_PASSWORD=feedbackpass123
POSTGRES_DB=amc_feedback
POSTGRES_POOL_SIZE=20
POSTGRES_POOL_TIMEOUT=30
```

### Connection String

```
postgresql://feedback:feedbackpass123@localhost:5432/amc_feedback
```

### Python asyncpg Connection

```python
import asyncpg

pool = await asyncpg.create_pool(
    "postgresql://feedback:feedbackpass123@localhost:5432/amc_feedback",
    min_size=5,
    max_size=20,
    command_timeout=30
)
```

---

## Common Operations

### Check Pending Feedback

```sql
SELECT 
    f.id, 
    f.feedback_type, 
    f.entity_name, 
    c.confidence_score,
    f.created_at
FROM feedback_records f
LEFT JOIN feedback_classifications c ON f.id = c.feedback_id
WHERE f.evaluation_status = 'pending'
ORDER BY c.confidence_score DESC;
```

### Check Correction Status

```sql
SELECT 
    status, 
    COUNT(*) as count,
    AVG(confidence_score) as avg_confidence,
    MIN(created_at) as oldest
FROM correction_recommendations
GROUP BY status
ORDER BY count DESC;
```

### View Daily Metrics

```sql
SELECT 
    date,
    total_feedback,
    positive_feedback,
    entity_corrections,
    avg_confidence_score
FROM feedback_metrics
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY date DESC;
```

### Check Recent Audit Trail

```sql
SELECT 
    timestamp,
    action_type,
    actor,
    success,
    error_message
FROM audit_trail
ORDER BY timestamp DESC
LIMIT 100;
```

### Find Duplicate Feedback

```sql
SELECT 
    f1.id, 
    f2.id,
    f1.entity_name,
    f1.created_at,
    f2.created_at
FROM feedback_records f1
JOIN feedback_records f2 ON 
    f1.session_id = f2.session_id AND
    f1.entity_name = f2.entity_name AND
    f1.feedback_type = f2.feedback_type AND
    f1.id < f2.id AND
    ABS(EXTRACT(EPOCH FROM (f1.created_at - f2.created_at))) < 60
ORDER BY f1.created_at DESC;
```

---

## Maintenance

### Cleanup Expired Caches (Scheduled)

```sql
-- Run hourly
SELECT cleanup_expired_cache();
-- Returns: (deleted_dedup INT, deleted_snapshot INT, deleted_llm_cache INT)
```

### Archive Old Feedback (Scheduled, Daily)

```sql
-- Run daily at 2 AM
SELECT archive_old_feedback(90);  -- Archive feedback older than 90 days
-- Returns: (archived_count INT, from_date TIMESTAMP, to_date TIMESTAMP)
```

### Compute Daily Metrics (Scheduled, Daily)

```sql
-- Run daily at 3 AM
INSERT INTO feedback_metrics (
    date, total_feedback, positive_feedback, negative_feedback,
    entity_corrections, avg_confidence_score, computed_at
)
SELECT 
    DATE(created_at) as date,
    COUNT(*) as total_feedback,
    SUM(CASE WHEN rating = 'positive' THEN 1 ELSE 0 END) as positive_feedback,
    SUM(CASE WHEN rating = 'negative' THEN 1 ELSE 0 END) as negative_feedback,
    (SELECT COUNT(*) FROM correction_recommendations cr 
     WHERE cr.created_at::DATE = DATE(f.created_at) AND cr.status = 'applied') as entity_corrections,
    AVG(c.confidence_score) as avg_confidence_score,
    NOW() as computed_at
FROM feedback_records f
LEFT JOIN feedback_classifications c ON f.id = c.feedback_id
WHERE f.created_at::DATE = CURRENT_DATE
GROUP BY DATE(f.created_at);
```

### Rebuild Indexes (Monthly)

```sql
-- Optimize table and indexes (can be slow on large tables)
VACUUM ANALYZE feedback_records;
VACUUM ANALYZE correction_recommendations;
REINDEX TABLE feedback_records;
REINDEX TABLE correction_recommendations;
```

### Check Table Sizes

```sql
SELECT 
    schemaname, tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Monitor Database Health

```sql
-- Active connections
SELECT datname, count(*) 
FROM pg_stat_activity 
GROUP BY datname;

-- Slow queries (pg_stat_statements extension)
CREATE EXTENSION pg_stat_statements;

SELECT query, calls, mean_exec_time 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;

-- Table bloat
SELECT 
    schemaname, tablename,
    round(100*pg_relation_size(schemaname||'.'||tablename)/(pg_total_relation_size(schemaname||'.'||tablename))::numeric, 2) as table_pct,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

---

## Performance Tuning

### Index Optimization

Add these indexes if queries are slow:

```sql
-- For complex feedback queries
CREATE INDEX idx_feedback_composite 
ON feedback_records(session_id, evaluation_status, created_at DESC);

-- For correction aggregation
CREATE INDEX idx_correction_composite 
ON correction_recommendations(status, confidence_score DESC, created_at DESC);

-- For audit queries
CREATE INDEX idx_audit_composite 
ON audit_trail(timestamp DESC, actor, action_type);
```

### Connection Pool Configuration

```python
# backend/app/engine/postgres_client.py

pool = await asyncpg.create_pool(
    connection_string,
    min_size=5,           # Minimum connections kept open
    max_size=20,          # Maximum connections
    max_cached_statement_lifetime=300,  # 5 minutes
    max_cacheable_statement_size=15360,  # 15KB
    command_timeout=30     # 30 second timeout
)
```

### Query Optimization

```sql
-- Use EXPLAIN to analyze queries
EXPLAIN ANALYZE
SELECT * FROM feedback_records 
WHERE evaluation_status = 'pending' 
AND created_at > NOW() - INTERVAL '1 day'
ORDER BY created_at DESC;

-- Look for:
-- - Full table scans (should use indexes)
-- - High planning time (consider denormalization)
-- - High execution time (check network, server CPU)
```

---

## Backup and Recovery

### Backup Entire Database

```bash
# Compressed backup
pg_dump -U feedback amc_feedback | gzip > amc_feedback_$(date +%Y%m%d_%H%M%S).sql.gz

# Directory format (faster for large databases)
pg_dump -U feedback -Fd amc_feedback -f /backup/amc_feedback/
```

### Restore from Backup

```bash
# From compressed backup
gunzip -c amc_feedback_20240119_120000.sql.gz | psql -U feedback amc_feedback

# From directory format
pg_restore -U feedback -d amc_feedback /backup/amc_feedback/
```

### Point-in-Time Recovery

```bash
# Enable WAL archiving in postgresql.conf:
# wal_level = replica
# archive_mode = on
# archive_command = 'cp %p /backup/wal_archive/%f'

# Restore to specific point in time:
pg_restore -U feedback -d amc_feedback -X restore-point:my_checkpoint /backup/amc_feedback/
```

---

## Monitoring and Alerting

### Setup CloudWatch Monitoring (AWS RDS)

```python
import boto3

cloudwatch = boto3.client('cloudwatch')

# Monitor database connections
cloudwatch.put_metric_alarm(
    AlarmName='HighDatabaseConnections',
    MetricName='DatabaseConnections',
    Namespace='AWS/RDS',
    Statistic='Average',
    Period=300,
    EvaluationPeriods=2,
    Threshold=15,
    ComparisonOperator='GreaterThanThreshold',
    AlarmActions=['arn:aws:sns:...']
)

# Monitor disk space
cloudwatch.put_metric_alarm(
    AlarmName='LowDatabaseStorageSpace',
    MetricName='FreeStorageSpace',
    Namespace='AWS/RDS',
    Statistic='Average',
    Period=300,
    Threshold=1000000000,  # 1GB
    ComparisonOperator='LessThanThreshold'
)
```

### Setup Prometheus Monitoring

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'postgres'
    static_configs:
      - targets: ['localhost:9187']
        labels:
          database: 'amc_feedback'
```

---

## Troubleshooting

### Connection Issues

```bash
# Test connection
psql -U feedback -d amc_feedback -h localhost -c "SELECT 1"

# Check connection errors
tail -f /var/log/postgresql/postgresql.log

# Check open connections
lsof -i :5432
```

### Slow Queries

```sql
-- Find slow queries
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
WHERE mean_exec_time > 1000  -- > 1 second
ORDER BY mean_exec_time DESC;

-- Clear stats and rerun
SELECT pg_stat_statements_reset();
```

### Disk Space Issues

```sql
-- Find large tables
SELECT 
    schemaname, tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;

-- Cleanup strategy
DELETE FROM feedback_records 
WHERE created_at < NOW() - INTERVAL '90 days' 
AND evaluation_status = 'archived';

VACUUM FULL feedback_records;
```

### Lock Contention

```sql
-- Check for locks
SELECT 
    pid, usename, application_name, client_addr,
    state, query, query_start
FROM pg_stat_activity
WHERE state != 'idle';

-- Kill blocking queries (use with caution)
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE query_start < NOW() - INTERVAL '10 minutes'
AND state = 'active';
```

---

## Production Deployment

### PostgreSQL 15+ Configuration (postgresql.conf)

```ini
# Connection settings
max_connections = 100
superuser_reserved_connections = 5

# Memory
shared_buffers = 256MB          # 25% of system RAM
effective_cache_size = 1GB      # 50-75% of system RAM
maintenance_work_mem = 64MB

# WAL settings (backup/replication)
wal_level = replica
max_wal_senders = 3
wal_keep_size = 1GB

# Logging
log_min_duration_statement = 1000  # Log queries > 1 second
log_connections = on
log_disconnections = on
log_statement = 'all'  # or 'ddl' for prod

# Auto-cleanup
autovacuum = on
autovacuum_naptime = 1min

# Checkpoint settings
checkpoint_timeout = 15min
checkpoint_completion_target = 0.9
```

### Backup Schedule

```bash
# Daily backup (cron job)
0 2 * * * pg_dump -U feedback amc_feedback | gzip > /backups/amc_feedback_$(date +\%Y\%m\%d).sql.gz

# Weekly full backup
0 3 * * 0 pg_basebackup -U feedback -Ft -z -P -D /backups/base_backup_$(date +\%Y\%m\%d)

# Cleanup old backups (keep 30 days)
0 4 * * * find /backups -name "amc_feedback_*.sql.gz" -mtime +30 -delete
```

### Replication Setup (HA)

```bash
# Primary server (postgresql.conf)
wal_level = replica
max_wal_senders = 3
wal_keep_size = 1GB

# Standby server
pg_basebackup -h primary.example.com -U replication -D /var/lib/postgresql/15/main -Pv -W

# Create standby.signal to enable read-only mode
touch /var/lib/postgresql/15/main/standby.signal
```

---

## Summary

This PostgreSQL setup provides:

1. **Scalability**: Connection pooling, optimized indexes, materialized views
2. **Performance**: Caching layers, pre-aggregated metrics, deduplication cache
3. **Compliance**: Audit trail, immutable history, retention policies
4. **Reliability**: ACID transactions, WAL, point-in-time recovery
5. **Monitoring**: Health checks, slow query logs, alert integration

For questions or issues, refer to [PostgreSQL Documentation](https://www.postgresql.org/docs/).
