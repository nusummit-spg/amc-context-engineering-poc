# Integration Guide: Scheme Aggregation Routes

This document provides step-by-step instructions to integrate the scheme aggregation service into the main FastAPI application.

## Quick Start

### Step 1: Update main.py - Import Routes

In `backend/app/main.py`, find the import section and update:

**BEFORE:**
```python
from app.api.routes import (
    admin, auth, chat, compliance, docs, feedback, files, governance, graph, ingest, metrics, query, review_queue, sessions, status, taxonomy
)
```

**AFTER:**
```python
from app.api.routes import (
    admin, auth, chat, compliance, docs, feedback, files, governance, graph, ingest, metrics, query, review_queue, sessions, status, taxonomy,
    scheme_aggregation_routes  # NEW: Scheme aggregation routes
)
from app.api.routes import feedback_evaluation
from app.api.routes import audit
```

### Step 2: Update main.py - Register Routes

In the `create_app()` function, find the route registration section:

**BEFORE:**
```python
for router in (auth.router, admin.router, query.router, chat.router, sessions.router, taxonomy.router, graph.router,
               docs.router, ingest.router, status.router, compliance.router, feedback.router, review_queue.router, governance.router, files.router, metrics.router):
    app.include_router(router, prefix="/api")
```

**AFTER:**
```python
# All existing routers + scheme aggregation
routers = [
    auth.router, admin.router, query.router, chat.router, sessions.router,
    taxonomy.router, graph.router, docs.router, ingest.router, status.router,
    compliance.router, feedback.router, review_queue.router, governance.router,
    files.router, metrics.router
]

# Add scheme aggregation router if available
if scheme_aggregation_routes and hasattr(scheme_aggregation_routes, 'router'):
    routers.append(scheme_aggregation_routes.router)

for router in routers:
    app.include_router(router, prefix="/api")
```

### Step 3: (Optional) Add Lifespan Hook for Service Initialization

To ensure the SchemeAggregationService is initialized on app startup:

**In the `lifespan()` function, add after Neo4j initialization:**

```python
    # Initialize Scheme Aggregation Service
    try:
        from app.services.scheme_aggregation_service import get_aggregation_service
        service = get_aggregation_service()
        logger.info(f"✓ Scheme aggregation service initialized with {len(service.df)} records")
    except Exception as exc:
        logger.warning("Could not initialize scheme aggregation service at startup: %s", exc)
```

### Step 4: Verify Integration

After making changes, verify the integration:

```bash
cd backend
python -m app.main  # or: uvicorn app.main:app --reload
```

Check for the new endpoints in the API documentation:

```
http://localhost:8000/docs  # Swagger UI
```

Look for the `/api/schemes/aggregation/` endpoints.

---

## Detailed Integration Steps

### File Changes Required

#### 1. `backend/app/main.py`

**Location**: Line ~30 (imports section)

```python
# Add to imports
from app.api.routes import scheme_aggregation_routes
```

**Location**: Line ~265-270 (route registration in create_app)

```python
# Modify the router registration loop
if scheme_aggregation_routes and hasattr(scheme_aggregation_routes, 'router'):
    routers.append(scheme_aggregation_routes.router)
```

#### 2. `backend/app/services/__init__.py` (If exists)

Add export for the service:

```python
from app.services.scheme_aggregation_service import SchemeAggregationService, get_aggregation_service

__all__ = ['SchemeAggregationService', 'get_aggregation_service']
```

If the file doesn't exist, create it with above content.

#### 3. `backend/.env` (Environment Configuration)

Add or update:

```bash
# Scheme Aggregation Configuration
MUTUAL_FUND_DATA_PATH=backend/data/source_docs/mutual_fund_data.csv
CYPHER_MAX_ROWS=100
CYPHER_LIMIT_RANKING=100
CYPHER_LIMIT_COMPARISON=50
CYPHER_LIMIT_ENTITY=100
CYPHER_LIMIT_AGGREGATION=100
CYPHER_LIMIT_TRAVERSAL=200
```

---

## API Endpoints Available After Integration

### 1. Get Top Schemes (Main Endpoint)

```
GET /api/schemes/aggregation/top-schemes
```

Query Parameters:
- `limit`: Number of results (1-100, default 10)
- `sort_by`: Sorting criteria (max_aum, avg_aum, total_aum, plan_count; default max_aum)
- `include_plan_details`: Include plan breakdown (true/false; default true)
- `include_inactive`: Include closed schemes (true/false; default false)
- `min_plan_count`: Minimum plan variants (default 1)
- `amc_filter`: Filter by AMC name (optional)
- `category_filter`: Filter by scheme category (optional)

Example Request:
```bash
curl "http://localhost:8000/api/schemes/aggregation/top-schemes?limit=10&sort_by=max_aum&include_plan_details=true"
```

### 2. Get Single Scheme Details

```
GET /api/schemes/aggregation/scheme/{scheme_name}
```

Example Request:
```bash
curl "http://localhost:8000/api/schemes/aggregation/scheme/SBI%20Nifty%2050%20ETF"
```

### 3. Export Aggregations

```
POST /api/schemes/aggregation/export-aggregations
```

Query Parameters:
- `format`: Export format (csv or parquet; default csv)

Example Request:
```bash
curl -X POST "http://localhost:8000/api/schemes/aggregation/export-aggregations?format=csv"
```

### 4. Health Check

```
GET /api/schemes/aggregation/health
```

Example Request:
```bash
curl "http://localhost:8000/api/schemes/aggregation/health"
```

---

## Testing Integration

### Test 1: Verify Routes Registered

```bash
curl http://localhost:8000/api/schemes/aggregation/health
```

**Expected Response**:
```json
{
  "status": "healthy",
  "service": "scheme_aggregation",
  "rows_loaded": 8178,
  "message": "Scheme aggregation service is operational"
}
```

### Test 2: Get Top 5 Schemes

```bash
curl "http://localhost:8000/api/schemes/aggregation/top-schemes?limit=5&sort_by=max_aum"
```

**Expected Response**: JSON with scheme_level_rankings and plan_level_rankings

### Test 3: Check OpenAPI Documentation

Navigate to: `http://localhost:8000/docs`

Look for the `/schemes/aggregation` tag in the left sidebar.

---

## Troubleshooting

### Issue 1: Module Import Error

**Error**: `ModuleNotFoundError: No module named 'app.services.scheme_aggregation_service'`

**Solution**: 
1. Verify the file exists at: `backend/app/services/scheme_aggregation_service.py`
2. Check that Python can find the module: `python -c "from app.services.scheme_aggregation_service import SchemeAggregationService"`
3. Make sure `backend/app/services/` has `__init__.py`

### Issue 2: CSV Not Found

**Error**: `FileNotFoundError: mutual_fund_data.csv not found`

**Solution**:
1. Verify CSV exists at: `backend/data/source_docs/mutual_fund_data.csv`
2. Set environment variable: `export MUTUAL_FUND_DATA_PATH=/full/path/to/mutual_fund_data.csv`
3. Update default path in `SchemeAggregationService.__init__()` if needed

### Issue 3: Slow Initial Load

**Issue**: First request takes 10+ seconds

**Cause**: Service loads and parses CSV on first use (lazy loading)

**Solution**:
1. Warm up the service on startup (add to lifespan hook)
2. Consider pre-computing and caching aggregations

### Issue 4: Routes Not Showing in Swagger

**Issue**: `/schemes/aggregation` endpoints not visible in `/docs`

**Solution**:
1. Verify router is registered in main.py
2. Restart FastAPI server
3. Clear browser cache: `Ctrl+Shift+Delete`
4. Check console for import errors

---

## Performance Optimization

### Option 1: Async Loading (Recommended)

Make CSV loading async to prevent blocking on startup:

```python
# In SchemeAggregationService
async def load_data_async(self):
    """Async version of data loading"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, self._load_data)
```

### Option 2: Caching Aggregations

Pre-compute and cache materialized views:

```python
# In lifespan hook
service = get_aggregation_service()
cache_path = "backend/cache/scheme_aggregations.parquet"
service.export_scheme_aggregations(cache_path, format='parquet')
```

### Option 3: Database Materialization

Store aggregations in SQLite for fast retrieval:

```python
# In services/scheme_aggregation_service.py
def materialize_to_db(self, db_path: str):
    """Store aggregations in SQLite database"""
    # Implementation details
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| MUTUAL_FUND_DATA_PATH | `backend/data/source_docs/mutual_fund_data.csv` | Path to CSV data |
| CYPHER_MAX_ROWS | 100 | Global row limit |
| CYPHER_LIMIT_RANKING | 100 | Ranking query limit |
| CYPHER_LIMIT_COMPARISON | 50 | Comparison query limit |
| CYPHER_LIMIT_ENTITY | 100 | Entity lookup limit |
| CYPHER_LIMIT_AGGREGATION | 100 | Aggregation query limit |
| CYPHER_LIMIT_TRAVERSAL | 200 | Traversal query limit |

### Configuration File

Update `backend/app/engine/config.py` to add:

```python
# Scheme Aggregation Configuration
SCHEME_AGGREGATION_CSV_PATH = os.environ.get(
    "MUTUAL_FUND_DATA_PATH",
    str(PROJECT_ROOT.parent.parent / "data" / "source_docs" / "mutual_fund_data.csv")
)
SCHEME_AGGREGATION_CACHE_DIR = Path(os.environ.get(
    "SCHEME_AGGREGATION_CACHE_DIR",
    str(PROJECT_ROOT / "cache" / "scheme_aggregations")
))
SCHEME_AGGREGATION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
```

---

## Production Deployment Checklist

- [ ] Routes integrated in main.py
- [ ] Environment variables configured
- [ ] CSV data path verified
- [ ] Health check endpoint tested
- [ ] API documentation reviewed (/docs)
- [ ] Performance tested with production data
- [ ] Error handling verified
- [ ] Logging configured
- [ ] Monitoring/alerts set up
- [ ] Documentation updated
- [ ] Team trained on new endpoints

---

## Support & Documentation

For detailed information, refer to:

1. **Implementation Guide**: `Implementation Guide: AUM Query Improvements`
2. **API Documentation**: Auto-generated at `/api/docs` (Swagger UI)
3. **Schema Definitions**: `app/models/scheme_aggregation.py`
4. **Service Logic**: `app/services/scheme_aggregation_service.py`
5. **Endpoints**: `app/api/routes/scheme_aggregation_routes.py`

---

**Integration Date**: October 26, 2026
**Status**: Ready for Deployment
**Last Updated**: October 26, 2026
