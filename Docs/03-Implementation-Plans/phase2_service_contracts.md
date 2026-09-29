# Phase 2: Service Contracts & Microservices Architecture Specification

## Executive Summary
This document formalizes the architecture, API contracts, database boundaries, and security protocols for modularizing the AMC Context Engineering Platform into three cohesive, independently scalable services:
1. **AMC Platform Orchestrator** (`amc-platform`)
2. **Feedback Loop Service** (`amc-feedback-loop`)
3. **Repair Engine Service** (`amc-repair-engine`)

---

## 1. Service Boundaries & Responsibilities

### Service 1: AMC Platform Orchestrator
- **Scope**: User query ingestion, hybrid retrieval orchestration (FAISS vector store + Neo4j graph store), prompt assembly with active patch injection, LLM response synthesis, session management, and caching.
- **REST Endpoints**:
  - `POST /api/query` - Single turn query execution.
  - `POST /api/chat` - Multi-turn conversational interaction.
  - `GET /api/query/{query_id}/status` - Check query processing status and trace logs.
  - `GET /api/health` - Health status of orchestrator, vector indices, and graph connections.
- **Data Ownership**:
  - Session histories and conversational turns.
  - FAISS index files (`faiss_indexes/`).
  - Request traces and runtime telemetry.
- **External Dependencies**:
  - Repair Engine Service (HTTP/REST or local adapter) for active correction patches.
  - Feedback Loop Service (HTTP/REST or local adapter) for follow-up passive detection.
  - Neo4j Knowledge Graph (read/traverse).
  - LLM Inference Provider (Groq / Gemini / Claude).

---

### Service 2: Feedback Loop Service
- **Scope**: Active and passive user feedback ingestion, entity extraction (spaCy + ONNX GLiNER), fuzzy entity matching against fund catalogs, dissatisfaction sentiment analysis, and compilation of unified evaluation records.
- **REST Endpoints**:
  - `POST /api/feedback` - Submit explicit user feedback (F01–F08 taxonomy categories).
  - `POST /api/feedback/follow-up-detection` - Passive correction detection across conversational turns.
  - `GET /api/feedback/{feedback_id}` - Retrieve feedback payload and metadata.
  - `GET /api/feedback/recent` - List recent feedback items with pagination.
  - `POST /api/unified-evaluation/build` - Construct unified evaluation record for downstream analysis.
  - `GET /api/health` - Status of feedback database and NER models.
- **Data Ownership**:
  - `response_feedback` records.
  - `query_evidence` storage.
  - `unified_evaluation_records` table.
  - NER entity cache.
- **External Dependencies**:
  - Repair Engine Service (to create proposed correction patches).
  - PostgreSQL / SQLite storage.
  - Fund master catalog (`data/raw/fund_names_cleaned.json`).

---

### Service 3: Repair Engine Service
- **Scope**: Hot correction patch storage and resolution, Tier 1/2/3 evaluation routing, automated and manual patch approval workflows, weekly scheduled governance batch processing, and canonical graph synchronization.
- **REST Endpoints**:
  - `POST /api/patches` - Register new candidate correction patch.
  - `GET /api/patches` - List active and pending correction patches.
  - `GET /api/patches/pending` - List patches awaiting human or batch approval.
  - `GET /api/patches/for-entities` - Fetch active patches for a list of entity identifiers.
  - `POST /api/patches/{patch_id}/approve` - Manually approve candidate patch.
  - `POST /api/patches/{patch_id}/reject` - Reject candidate patch.
  - `POST /api/patches/batch-approve` - Bulk approve patches.
  - `POST /api/governance/run-batch` - Trigger governance batch graph synchronization.
  - `GET /api/evaluation/evaluate` - Execute tiered evaluation rule set against an answer.
  - `GET /api/health` - Status of Redis cache, patch storage, and Neo4j write connection.
- **Data Ownership**:
  - Hot patch cache (Redis / in-memory layer).
  - `review_queue_items` and governance audit history.
  - Patch deployment manifests.
- **External Dependencies**:
  - Neo4j Knowledge Graph (write/mutate permissions for approved corrections).
  - Redis cache.
  - Relational database for audit logs.

---

## 2. Inter-Service Communication & Authentication

### Security Protocol
Inter-service calls are authenticated using lightweight signed JWT service tokens or mutual API keys.
```http
Authorization: Bearer <JWT_SERVICE_TOKEN>
X-Request-ID: <UUIDv4>
X-Correlation-ID: <TRACE_ID>
X-Service-Name: amc-platform
```

#### JWT Claims Schema
```json
{
  "sub": "service:amc-platform",
  "role": "internal_service",
  "permissions": ["patches:read", "feedback:write"],
  "iat": 1758800000,
  "exp": 1758803600
}
```

### Circuit Breaker Specification
To prevent cascading failures across services:
- **Failure Threshold**: 5 consecutive errors.
- **Reset Timeout**: 30 seconds.
- **Fallback Policy**:
  - If `Repair Engine` is unreachable: Orchestrator proceeds without hot patches, logging a degraded status event.
  - If `Feedback Loop` is unreachable: Orchestrator queues feedback locally or returns `202 Accepted` with a retry background task.

---

## 3. Database Isolation Strategy

### Phase 2.1 (Current - In-Process / Shared SQL & Redis)
- SQLite / PostgreSQL shared instance with distinct table namespaces (`response_feedback`, `unified_evaluation_records`, `review_queue_items`).
- Redis key namespacing:
  - `amc:platform:*` (query caches, sessions)
  - `amc:repair:patches:*` (active correction patches)
  - `amc:feedback:*` (temporary NER hashes)

### Phase 2.2 (Multi-Service / Independent Schemas)
- PostgreSQL with three isolated schemas: `amc_platform`, `amc_feedback`, `amc_repair`.
- Role-based table access per service credentials.
