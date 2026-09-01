# Troubleshooting Guide

## Common Issues and Resolutions

### 1. Connection Refused / API Network Error
- **Symptom**: Red toast saying "Connection Refused" or queries failing immediately.
- **Resolution**:
  1. Ensure FastAPI backend is running: `uvicorn app.main:app --port 8000`.
  2. Verify Neo4j (`http://localhost:7474`) and Qdrant (`http://localhost:6333`) containers are healthy.
  3. Verify `VITE_API_BASE` in `frontend/.env` points to the correct backend host.

### 2. Slow or Timed-out Queries
- **Symptom**: Loading spinner persists for extended duration.
- **Resolution**: The client timeout is configured to 240 seconds. For large multi-hop graph queries, verify Neo4j indexes are created with `python -m scripts.seed_neo4j`.

### 3. Intent Cache Invalidation
- **Symptom**: Query results seem identical even after re-indexing documents.
- **Resolution**: Click the **🗑️ Clear Intent Cache** button in the sidebar or in the Compare / Chat action rows.
